"""
PEN-9: which Plugin API members the server executor really ran during the
experiments, matched against every member of `feature-inventory.md`.

    python3 -I mcp/docs/server-mcp/experiments/pen9_coverage.py run --space 206   # traced regression
    python3 -I mcp/docs/server-mcp/experiments/pen9_coverage.py report            # match, from the log

`run` restarts the MCP server with `PENPOT_EXECUTOR_TRACE_API=1`, so every
execution prints the members its code read, wrote or called
(`executor/child/ApiTrace.ts`), runs `pen9_regression.py` into
`.mcp-verify/pen9/coverage-run/`, and restarts the server without the trace.
`report` reads those lines from the MCP log and writes
`.mcp-verify/pen9/coverage.json`: per member, whether some execution used it.
A member no execution used is "not run", never counted as verified.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))

import mcp_client  # noqa: E402
import mcpv  # noqa: E402

OUT = mcpv.STATE / "pen9"
LOG = mcpv.STATE / "logs" / "mcp.log"
MARK = OUT / "coverage-log-range.json"
MARKER = "[api-trace] "

# the MCP command of `docker/mcp-verify/files/start-services.sh` (multi-user), with the trace switch read
# from a file, so the window's "repeat last command" restart keeps the chosen mode
RUN_SCRIPT = """#!/usr/bin/env bash
cd ~/penpot/mcp
export PENPOT_EXECUTOR_TRACE_API="$(cat ~/penpot/.mcp-verify/trace-api 2>/dev/null || echo 0)"
echo "[mcp-verify] PENPOT_EXECUTOR_TRACE_API=$PENPOT_EXECUTOR_TRACE_API"
PENPOT_MCP_SERVER_HOST=0.0.0.0 PENPOT_MCP_REMOTE_MODE=true PENPOT_TENANT="$PENPOT_TENANT" \\
PENPOT_MCP_EXECUTOR=optional \\
PENPOT_MCP_EXECUTOR_BUNDLE=$HOME/penpot/frontend/target/executor/executor.js \\
PENPOT_MCP_EXECUTOR_WASM_DIR=$HOME/penpot/frontend/resources/public/js \\
PENPOT_MCP_EXECUTOR_PUBLIC_URI=http://localhost:3450 \\
PENPOT_MCP_SHARED_KEY=super-secret-mcp-key \\
PENPOT_FLAGS='enable-mcp enable-access-tokens' \\
PENPOT_MCP_REDIS_URI=redis://valkey/1 pnpm run start:multi-user
"""


def restart_mcp(trace):
    """Restarts the MCP server in its tmux window, with the API trace on or off."""
    (mcpv.STATE / "mcp-run.sh").write_text(RUN_SCRIPT)
    (mcpv.STATE / "trace-api").write_text("1" if trace else "0")
    wait = "for i in $(seq 1 100); do pgrep -f 'dist/[i]ndex.js --multi-user' >/dev/null || break; sleep 0.2; done; sleep 1"
    subprocess.run(["docker", "exec", "-u", "penpot", mcpv.MAIN, "bash", "-lc",
                    f"tmux send-keys -t mcpv:mcp C-c; {wait}; "
                    "tmux send-keys -t mcpv:mcp 'bash ~/penpot/.mcp-verify/mcp-run.sh' enter"], check=True)
    for _ in range(90):
        try:
            mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
            return
        except Exception:  # noqa: BLE001
            time.sleep(1)
    raise RuntimeError("the MCP server did not come back")


def traced_members(start, end):
    """Every `<kind>.<member>` the trace lines of the MCP log between two byte offsets name."""
    members = set()
    with LOG.open("rb") as log:
        log.seek(start)
        chunk = log.read(end - start).decode(errors="replace")
    for line in chunk.splitlines():
        at = line.find(MARKER)
        if at >= 0:
            try:
                members.update(json.loads(line[at + len(MARKER):]))
            except ValueError:
                pass
    return members


def run(args):
    OUT.mkdir(parents=True, exist_ok=True)
    restart_mcp(trace=True)
    start = LOG.stat().st_size
    try:
        command = [sys.executable, "-I", str(HERE / "pen9_regression.py"), "--space", str(args.space),
                   "--out", "coverage-run"] + (["--only", *args.only] if args.only else [])
        code = subprocess.run(command).returncode
    finally:
        end = LOG.stat().st_size
        MARK.write_text(json.dumps({"start": start, "end": end}))
        restart_mcp(trace=False)
    print(json.dumps({"regressionExit": code, "traceLines": len(traced_members(start, end))}))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--space", type=int, required=True)
    run_parser.add_argument("--only", nargs="*")
    sub.add_parser("kinds")
    args = parser.parse_args()
    if args.command == "run":
        run(args)
    elif args.command == "kinds":
        mark = json.loads(MARK.read_text())
        kinds = {}
        for member in traced_members(mark["start"], mark["end"]):
            kind, _, name = member.rpartition(".")
            kinds.setdefault(kind, []).append(name)
        print(json.dumps({k: sorted(v) for k, v in sorted(kinds.items())}, indent=1))


if __name__ == "__main__":
    main()
