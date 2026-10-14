#!/usr/bin/env python3
#
# Creates the fixtures of the mcp-verify stack: four test profiles with
# different permissions, a shared team, a project, test files and access
# tokens. Idempotent; writes everything a test needs to --out (gitignored).
# Called by `scripts/mcp-verify-env seed`; only talks to the local stack.

import argparse
import http.cookiejar
import json
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

PASSWORD = "mcpv-test-password"
TEAM_NAME = "MCP Verify"
PROJECT_NAME = "Fixtures"
FILE_NAMES = ["basic", "concurrency", "scratch"]
TOKEN_PREFIX = "mcpv-"

# role -> (email, fullname, team membership: None | (is_admin, can_edit))
PROFILES = {
    "owner": ("mcpv-owner@example.com", "MCPV Owner", None),
    "editor": ("mcpv-editor@example.com", "MCPV Editor", (False, True)),
    "viewer": ("mcpv-viewer@example.com", "MCPV Viewer", (False, False)),
    "outsider": ("mcpv-outsider@example.com", "MCPV Outsider", None),
}


class RpcClient:
    """
    RPC client for one profile, authenticated by the session cookie.
    """

    def __init__(self, base_uri):
        self.base_uri = base_uri
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        )

    def call(self, method, params=None):
        request = urllib.request.Request(
            f"{self.base_uri}/api/main/methods/{method}",
            data=json.dumps(params or {}).encode(),
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "x-client": "mcp-verify-seed",
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=60) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:500]
            raise RuntimeError(f"{method} failed: HTTP {error.code}: {detail}") from None


def run(command, stdin=None):
    result = subprocess.run(command, input=stdin, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} failed: {result.stdout}{result.stderr}")
    return result.stdout


def psql(container, sql):
    return run(["docker", "exec", "-i", container, "psql", "-U", "penpot", "-d", "penpot",
                "-v", "ON_ERROR_STOP=1", "-At", "-c", sql])


def ensure_profile(main_container, postgres_container, email, fullname):
    found = psql(postgres_container,
                 f"SELECT id FROM profile WHERE email = '{email}' AND deleted_at IS NULL").strip()
    if found:
        return found
    run(["docker", "exec", main_container, "sudo", "-u", "penpot", "python3",
         "/home/penpot/penpot/backend/scripts/manage.py", "create-profile",
         "-n", fullname, "-e", email, "-p", PASSWORD,
         "--skip-tutorial", "--skip-walkthrough"])
    return psql(postgres_container,
                f"SELECT id FROM profile WHERE email = '{email}' AND deleted_at IS NULL").strip()


def login(base_uri, email):
    client = RpcClient(base_uri)
    client.call("login-with-password", {"email": email, "password": PASSWORD})
    return client


def find(items, name):
    return next((item for item in items if item.get("name") == name), None)


def ensure_tokens(client, role, previous, reset):
    """
    Returns {"mcp": ..., "api": ...} token values for one profile.

    MCP tokens are readable again through get-access-tokens; API tokens are
    only returned on creation, so they are reused from the previous fixtures
    file and recreated when missing.
    """
    existing = client.call("get-access-tokens") or []
    ours = [t for t in existing if t.get("name", "").startswith(TOKEN_PREFIX)]
    if reset:
        for token in ours:
            client.call("delete-access-token", {"id": token["id"]})
        ours = []

    mcp = next((t for t in ours if t.get("type") == "mcp" and t.get("token")), None)
    if mcp is None:
        mcp = client.call("create-access-token", {"name": f"{TOKEN_PREFIX}{role}-mcp", "type": "mcp"})

    api_value = (previous or {}).get("api")
    api_known = any(t.get("name") == f"{TOKEN_PREFIX}{role}-api" for t in ours)
    if not (api_value and api_known):
        for token in ours:
            if token.get("name") == f"{TOKEN_PREFIX}{role}-api":
                client.call("delete-access-token", {"id": token["id"]})
        api_value = client.call("create-access-token", {"name": f"{TOKEN_PREFIX}{role}-api"})["token"]

    return {"mcp": mcp["token"], "api": api_value}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-uri", required=True)
    parser.add_argument("--main-container", required=True)
    parser.add_argument("--postgres-container", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--reset-tokens", action="store_true")
    args = parser.parse_args()

    try:
        with open(args.out) as f:
            previous = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        previous = {}

    profiles = {}
    for role, (email, fullname, _) in PROFILES.items():
        profile_id = ensure_profile(args.main_container, args.postgres_container, email, fullname)
        profiles[role] = {"id": profile_id, "email": email, "password": PASSWORD}

    owner = login(args.base_uri, PROFILES["owner"][0])

    team = find(owner.call("get-teams"), TEAM_NAME) or owner.call("create-team", {"name": TEAM_NAME})
    project = (find(owner.call("get-projects", {"teamId": team["id"]}), PROJECT_NAME)
               or owner.call("create-project", {"teamId": team["id"], "name": PROJECT_NAME}))

    existing_files = owner.call("get-project-files", {"projectId": project["id"]}) or []
    files = {}
    for name in FILE_NAMES:
        file = find(existing_files, name) or owner.call("create-file", {"name": name, "projectId": project["id"]})
        data = owner.call("get-file", {"id": file["id"]})
        pages = data["data"]["pages"]
        files[name] = {"id": file["id"], "pageId": pages[0], "revn": data.get("revn")}

    # Memberships are written directly: invitations would need the mail
    # round trip and add nothing to what the tests check.
    for role, (_, _, membership) in PROFILES.items():
        if membership is None:
            continue
        is_admin, can_edit = membership
        psql(args.postgres_container,
             "INSERT INTO team_profile_rel (team_id, profile_id, is_owner, is_admin, can_edit) "
             f"VALUES ('{team['id']}', '{profiles[role]['id']}', false, {str(is_admin).lower()}, {str(can_edit).lower()}) "
             "ON CONFLICT (team_id, profile_id) DO UPDATE "
             "SET is_admin = EXCLUDED.is_admin, can_edit = EXCLUDED.can_edit")

    for role in PROFILES:
        client = owner if role == "owner" else login(args.base_uri, profiles[role]["email"])
        client.call("update-profile-props", {"props": {"mcpEnabled": True}})
        prev_tokens = (previous.get("profiles", {}).get(role) or {}).get("tokens")
        profiles[role]["tokens"] = ensure_tokens(client, role, prev_tokens, args.reset_tokens)

    fixtures = {
        "baseUri": args.base_uri,
        "team": {"id": team["id"], "name": TEAM_NAME},
        "project": {"id": project["id"], "name": PROJECT_NAME},
        "files": files,
        "profiles": profiles,
    }
    with open(args.out, "w") as f:
        json.dump(fixtures, f, indent=2)

    print(f"fixtures written to {args.out}")
    for role, profile in profiles.items():
        print(f"  {role:9} {profile['email']}")
    for name, file in files.items():
        print(f"  file {name:12} {args.base_uri}/#/workspace?team-id={team['id']}&file-id={file['id']}&page-id={file['pageId']}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"seed: {error}", file=sys.stderr)
        sys.exit(1)
