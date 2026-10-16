#!/usr/bin/env python3
"""PEN-21 auth checks on design.hktlabs.com with a throwaway profile.

    python3 pen21_auth_check.py <id of a file the new profile may not read>

Needs `enable-registration` without email verification (as deployed).

1. register a test profile, enable MCP, create an MCP key
2. server execution with that key works on its own drafts
3. the same key cannot open the owner's file (permission denied)
4. delete the key -> the next call in the same MCP session is refused
5. delete the test profile
Never prints a key.
"""
import http.cookiejar, json, sys, time, urllib.error, urllib.request, uuid

BASE = "https://design.hktlabs.com"
OWNER_FILE = sys.argv[1]
EMAIL = f"pen21-check-{uuid.uuid4().hex[:8]}@example.com"
PASSWORD = "Pen21!" + uuid.uuid4().hex


class Rpc:
    def __init__(self):
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, params=None):
        req = urllib.request.Request(
            f"{BASE}/api/main/methods/{method}", data=json.dumps(params or {}).encode(),
            headers={"content-type": "application/json", "accept": "application/json"}, method="POST")
        try:
            with self.opener.open(req, timeout=60) as r:
                b = r.read()
                return json.loads(b) if b else None
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method}: HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from None


class Mcp:
    def __init__(self, token):
        self.url = f"{BASE}/mcp/stream?userToken={token}&executor=server"
        self.session = None
        self.id = 0
        self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                "clientInfo": {"name": "pen21-auth", "version": "0"}})
        self.rpc("notifications/initialized", {}, notify=True)

    def rpc(self, method, params, notify=False):
        body = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notify:
            self.id += 1
            body["id"] = self.id
        headers = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
        if self.session:
            headers["mcp-session-id"] = self.session
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                self.session = self.session or r.headers.get("mcp-session-id")
                text = r.read().decode()
        except urllib.error.HTTPError as e:
            return {"http": e.code, "body": e.read().decode(errors="replace")[:300]}
        if notify:
            return None
        lines = [l[5:] for l in text.splitlines() if l.startswith("data:")]
        return json.loads(lines[-1] if lines else text)

    def run(self, code, **extra):
        out = self.rpc("tools/call", {"name": "execute_code", "arguments": {"code": code, **extra}})
        if "result" in out:
            return out["result"]["content"][0]["text"][:400]
        return json.dumps(out)[:400]


def step(name, value):
    print(f"\n## {name}\n{value}")


rpc = Rpc()
token = rpc.call("prepare-register-profile", {"fullname": "PEN-21 check (delete me)", "email": EMAIL, "password": PASSWORD})["token"]
profile = rpc.call("register-profile", {"token": token, "fullname": "PEN-21 check (delete me)", "acceptTermsAndPrivacy": True})
rpc.call("login-with-password", {"email": EMAIL, "password": PASSWORD})
rpc.call("update-profile-props", {"props": {"mcpEnabled": True}})
key = rpc.call("create-access-token", {"name": "pen21-check", "type": "mcp"})
step("1. test profile + MCP key", f"profile={EMAIL} key_id={key['id']}")

try:
    mcp = Mcp(key["token"])
    step("2. own drafts via server execution",
         mcp.run("const ps = await penpotMgmt.listProjects(); return ps.map(p => p.name);"))
    step("3. owner's file with the test key (expect refusal)",
         mcp.run("return penpot.currentFile?.name;", fileId=OWNER_FILE))
    step("3b. same session still works on its own drafts",
         mcp.run("return (await penpotMgmt.listProjects()).length;"))

    rpc.call("delete-access-token", {"id": key["id"]})
    time.sleep(2)
    step("4. after deleting the key, same MCP session (expect refusal)",
         mcp.run("return (await penpotMgmt.listProjects()).length;"))
    step("4b. after deleting the key, new MCP session (expect refusal)",
         Mcp(key["token"]).run("return (await penpotMgmt.listProjects()).length;"))
finally:
    try:
        rpc.call("delete-access-token", {"id": key["id"]})
    except Exception:
        pass
    try:
        rpc.call("delete-profile", {})
        step("5. cleanup", "test profile deleted")
    except Exception as e:
        step("5. cleanup FAILED", str(e))
