"""
Shared helpers for the server-MCP experiments: fixtures, backend RPC with an
access token, and running commands in the mcp-verify main container.

Import from an experiment script that lives in the same directory:

    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import mcpv
"""

import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
STATE = ROOT / ".mcp-verify"
FIXTURES = STATE / "fixtures.json"
MAIN = os.environ.get("MCPV_PROJECT", "penpot-mcpverify") + "-main"

CONTEXT = ssl.create_default_context()
CONTEXT.check_hostname = False
CONTEXT.verify_mode = ssl.CERT_NONE


def fixtures():
    return json.loads(FIXTURES.read_text())


def token(role, kind="api"):
    """Access token of a seeded profile; `kind` is "api" or "mcp"."""
    tokens = fixtures()["profiles"][role]["tokens"]
    return tokens[kind] if isinstance(tokens, dict) else tokens


def rpc(method, params, token=None, base_uri=None):
    """
    Calls a backend RPC method with a JSON body. Returns (status, payload,
    seconds). Errors are returned, not raised.
    """
    base_uri = base_uri or fixtures()["baseUri"]
    headers = {"accept": "application/json", "content-type": "application/json",
               "x-client": "mcp-verify-experiment"}
    if token:
        headers["authorization"] = f"Token {token}"
    request = urllib.request.Request(f"{base_uri}/api/main/methods/{method}",
                                     data=json.dumps(params).encode(),
                                     headers=headers, method="POST")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, context=CONTEXT, timeout=120) as response:
            body = response.read()
            return response.status, (json.loads(body) if body else None), time.monotonic() - started
    except urllib.error.HTTPError as error:
        body = error.read()
        try:
            payload = json.loads(body)
        except ValueError:
            payload = body.decode(errors="replace")[:500]
        return error.code, payload, time.monotonic() - started


def rpc_ok(method, params, token=None):
    status, payload, _ = rpc(method, params, token)
    if status != 200:
        raise RuntimeError(f"{method} failed: {status} {payload}")
    return payload


def container(command, input_text=None, timeout=600):
    """Runs a bash command as the penpot user inside the main container."""
    result = subprocess.run(["docker", "exec", "-i", "-u", "penpot", MAIN, "bash", "-lc", command],
                            input=input_text, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout, result.stderr


def create_file(name, role="editor"):
    """Creates a fresh file in the fixtures project and returns its id and first page id."""
    project_id = fixtures()["project"]["id"]
    file = rpc_ok("create-file", {"name": name, "projectId": project_id}, token(role))
    data = rpc_ok("get-file", {"id": file["id"]}, token(role))
    return file["id"], data["data"]["pages"][0]


def page_objects(file_id, page_id, role="editor"):
    data = rpc_ok("get-file", {"id": file_id}, token(role))
    return data["revn"], data["data"]["pagesIndex"][page_id]["objects"]
