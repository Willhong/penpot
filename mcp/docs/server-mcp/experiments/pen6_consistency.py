#!/usr/bin/env python3
#
# PEN-6: concurrent human and AI edits, retries and reconnections keep the
# file consistent (D4, D5, D6).
#
#   python3 -I pen6_consistency.py --space <ego-browser task space>
#
# Humans are the observer tabs (p1 owner, p2 editor) running Plugin API code
# in their workspace; the AI is the editor through MCP (`?executor=server`).
# Each check compares the backend, both tabs and the server session.
#
# Prints a JSON report; exit status 1 when a check fails.

import argparse
import http.client
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mcp_client  # noqa: E402
import mcpv  # noqa: E402
import observers  # noqa: E402

ROOT = HERE.parents[3]

STATE_OF = """
const pick = (s) => s && ({ x: s.x, y: s.y, fill: s.fills.length ? s.fills[0].fillColor : null });
const out = {};
for (const s of penpot.currentPage.findShapes()) { if (s.name !== 'Root Frame') out[s.name] = pick(s); }
return out;
"""


def backend_state(file_id):
    data = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))
    out = {}
    for page_id in data["data"]["pages"][:1]:
        for shape in data["data"]["pagesIndex"][page_id]["objects"].values():
            if shape["name"] != "Root Frame":
                out[shape["name"]] = {"x": round(shape["selrect"]["x"], 2), "y": round(shape["selrect"]["y"], 2),
                                      "fill": shape["fills"][0]["fillColor"] if shape.get("fills") else None}
    return data["revn"], data["vern"], out


def rounded(state):
    return {k: v and {**v, "x": round(v["x"], 2), "y": round(v["y"], 2),
                      "fill": v["fill"].lower() if v.get("fill") else v.get("fill")}
            for k, v in state.items()}


def wait_until(predicate, timeout=10.0):
    started = time.monotonic()
    while True:
        value = predicate()
        if value or time.monotonic() - started > timeout:
            return value, round(time.monotonic() - started, 2)
        time.sleep(0.3)


class Pen6:
    def __init__(self, space):
        self.tabs = observers.Tabs(space)
        self.ai = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
        self.session = f"pen6-{time.time_ns()}"
        self.report = {}

    def ai_run(self, code, **kwargs):
        return self.ai.execute_code(code, sessionId=self.session, **kwargs)[0]

    def human(self, label, code):
        result = self.tabs.run_code(label, code, settle=500)
        if not result.get("ok"):
            raise RuntimeError(f"{label} failed: {result}")
        return result["result"]

    def views(self, file_id):
        """The file as the backend, both tabs and the AI session see it."""
        revn, vern, backend = backend_state(file_id)
        return {
            "backend": rounded(backend),
            "p1": rounded(self.human("p1", STATE_OF)),
            "p2": rounded(self.human("p2", STATE_OF)),
            "ai": rounded(self.ai_run(STATE_OF)["result"]),
        }

    def consistent(self, file_id, timeout=10):
        views, seconds = wait_until(lambda: (lambda v: v if len({json.dumps(x, sort_keys=True) for x in v.values()}) == 1 else None)(self.views(file_id)), timeout)
        return views or self.views(file_id), seconds

    def check(self, name, ok, **detail):
        self.report[name] = {"ok": bool(ok), **detail}

    # --- checks

    def setup(self):
        self.file_id, self.page_id = mcpv.create_file("pen6-consistency")
        self.ai_run("""
for (const [name, x] of [['a', 0], ['b', 200], ['c', 400]]) {
  const r = penpot.createRectangle(); r.name = name; r.x = x; r.y = 0; r.resize(100, 100);
  r.fills = [{ fillColor: '#adb5bd', fillOpacity: 1 }];
}
return 1;""", fileId=self.file_id)
        self.tabs.open(self.file_id, self.page_id)

    def concurrent_different_shapes(self):
        errors = []

        def human():
            try:
                self.human("p1", "const a = penpot.currentPage.findShapes({ name: 'a' })[0]; a.x = 111; "
                                 "a.fills = [{ fillColor: '#e03131', fillOpacity: 1 }]; return 1;")
            except Exception as error:  # noqa: BLE001
                errors.append(str(error))

        thread = threading.Thread(target=human)
        thread.start()
        self.ai_run("const b = penpot.currentPage.findShapes({ name: 'b' })[0]; b.x = 222; "
                    "b.fills = [{ fillColor: '#2f9e44', fillOpacity: 1 }]; return 1;")
        thread.join()
        views, seconds = self.consistent(self.file_id)
        backend = views["backend"]
        self.check("concurrentDifferentShapes",
                   not errors and backend["a"]["x"] == 111 and backend["a"]["fill"] == "#e03131"
                   and backend["b"]["x"] == 222 and backend["b"]["fill"] == "#2f9e44"
                   and len({json.dumps(v, sort_keys=True) for v in views.values()}) == 1,
                   errors=errors, views=views, seconds=seconds)

    def same_property(self):
        self.human("p2", "penpot.currentPage.findShapes({ name: 'a' })[0].x = 300; return 1;")
        self.ai_run("penpot.currentPage.findShapes({ name: 'a' })[0].x = 400; return 1;")
        views1, _ = self.consistent(self.file_id)
        self.ai_run("penpot.currentPage.findShapes({ name: 'a' })[0].y = 50; return 1;")
        self.human("p2", "penpot.currentPage.findShapes({ name: 'a' })[0].y = 60; return 1;")
        views2, _ = self.consistent(self.file_id)
        same = lambda views: len({json.dumps(v, sort_keys=True) for v in views.values()}) == 1  # noqa: E731
        self.check("samePropertyLastWriteWins",
                   views1["backend"]["a"]["x"] == 400 and same(views1)
                   and views2["backend"]["a"]["y"] == 60 and same(views2),
                   aiLast=views1["backend"]["a"], humanLast=views2["backend"]["a"])

    def deleted_shape(self):
        # the AI keeps a reference across executions, a human deletes the shape, the AI edits through it
        self.ai_run("storage.c = penpot.currentPage.findShapes({ name: 'c' })[0]; return storage.c.id;")
        self.human("p1", "penpot.currentPage.findShapes({ name: 'c' })[0].remove(); return 1;")
        wait_until(lambda: "c" not in self.ai_run(STATE_OF)["result"])
        try:
            result = self.ai_run("storage.c.x = 999; return 'edited';")["result"]
        except mcp_client.ToolError as error:
            result = str(error)[:200]
        views, _ = self.consistent(self.file_id)
        # the plugin API ignores edits of a deleted shape in the browser too (checked with dual_run);
        # what matters is that the deletion wins everywhere
        self.check("editDeletedShape",
                   all("c" not in view for view in views.values()),
                   aiAnswer=result)

    def precondition(self):
        revn = backend_state(self.file_id)[0]
        self.human("p2", "penpot.currentPage.findShapes({ name: 'b' })[0].y = 20; return 1;")
        wait_until(lambda: backend_state(self.file_id)[0] > revn)
        before = backend_state(self.file_id)
        try:
            self.ai_run("penpot.currentPage.findShapes({ name: 'b' })[0].y = 999; return 1;",
                        ifUnchangedSinceRevn=revn)
            refused = None
        except mcp_client.ToolError as error:
            refused = str(error)[:200]
        after = backend_state(self.file_id)
        current = after[0]
        accepted = self.ai_run("penpot.currentPage.findShapes({ name: 'b' })[0].y = 30; return 1;",
                               ifUnchangedSinceRevn=current)["commit"]
        self.check("precondition",
                   refused is not None and "precondition-failed" in refused and before[2] == after[2]
                   and accepted and accepted["saved"],
                   refused=refused, acceptedRevn=accepted and accepted["revn"])

    def restored_file(self):
        version = self.human("p1", "const v = await penpot.currentFile.saveVersion('pen6'); return v.label;")
        self.ai_run("const r = penpot.createRectangle(); r.name = 'after-version'; return 1;")
        vern_before = backend_state(self.file_id)[1]
        self.human("p1", "const v = (await penpot.currentFile.findVersions()).find((v) => v.label === 'pen6'); "
                         "v.restore(); return 1;")
        wait_until(lambda: backend_state(self.file_id)[1] != vern_before)
        time.sleep(2)
        try:
            commit = self.ai_run("const r = penpot.createRectangle(); r.name = 'after-restore'; return 1;")["commit"]
            outcome = {"saved": commit["saved"], "revn": commit["revn"]}
        except mcp_client.ToolError as error:
            outcome = {"error": str(error)[:200]}
        self.tabs.open(self.file_id, self.page_id)
        views, _ = self.consistent(self.file_id)
        names = set(views["backend"])
        self.check("restoredFile",
                   version == "pen6" and outcome.get("saved") and "after-restore" in names
                   and "after-version" not in names
                   and len({json.dumps(v, sort_keys=True) for v in views.values()}) == 1,
                   aiAfterRestore=outcome, names=sorted(names))

    def dedup(self):
        code = "const r = penpot.createEllipse(); r.name = 'once'; return r.id;"
        first = self.ai_run(code, requestId=f"{self.session}-once")
        second = self.ai_run(code, requestId=f"{self.session}-once")
        results = []

        def concurrent():
            results.append(self.ai.execute_code(
                "await new Promise((r) => setTimeout(r, 800)); const e = penpot.createEllipse(); e.name = 'twice'; return e.id;",
                sessionId=self.session, requestId=f"{self.session}-twice")[0])

        threads = [threading.Thread(target=concurrent) for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        names = [n for n in self.ai_run("return penpot.currentPage.findShapes().map((s) => s.name);")["result"]]
        self.check("requestIdDedup",
                   first["result"] == second["result"] and second.get("replayed") is True
                   and names.count("once") == 1 and names.count("twice") == 1
                   and results[0]["result"] == results[1]["result"],
                   once=names.count("once"), twice=names.count("twice"))

    def lost_response(self):
        # A: the client drops the connection while the code runs: the request is cancelled before its save
        # (D6), so the retry runs once
        code_a = ("await new Promise((r) => setTimeout(r, 1500)); "
                  "const e = penpot.createEllipse(); e.name = 'dropped-request'; return e.id;")
        id_a = f"{self.session}-dropped"
        try:
            self.ai.call("tools/call", {"name": "execute_code",
                                        "arguments": {"code": code_a, "sessionId": self.session,
                                                      "requestId": id_a}}, timeout=0.5)
            dropped = False
        except Exception:  # noqa: BLE001
            dropped = True
        time.sleep(3)
        retry_a = self.ai_run(code_a, requestId=id_a)
        count_a = self.ai_run("return penpot.currentPage.findShapes({ name: 'dropped-request' }).length;")["result"]

        # B: the server saves and answers, but the client never reads the answer; the retry gets the
        # recorded result instead of running again (D5)
        code_b = "const e = penpot.createEllipse(); e.name = 'unread-answer'; return e.id;"
        id_b = f"{self.session}-unread"
        connection = http.client.HTTPConnection("localhost", 4501, timeout=30)
        body = {"jsonrpc": "2.0", "id": 99, "method": "tools/call",
                "params": {"name": "execute_code",
                           "arguments": {"code": code_b, "sessionId": self.session, "requestId": id_b}}}
        connection.request("POST", self.ai.url.replace("http://localhost:4501", ""), body=json.dumps(body),
                           headers={"content-type": "application/json",
                                    "accept": "application/json, text/event-stream"})
        time.sleep(4)
        connection.close()
        retry_b = self.ai_run(code_b, requestId=id_b)
        count_b = self.ai_run("return penpot.currentPage.findShapes({ name: 'unread-answer' }).length;")["result"]
        self.check("lostResponseRetry",
                   dropped and count_a == 1 and not retry_a.get("replayed")
                   and retry_b.get("replayed") is True and count_b == 1,
                   droppedRequest={"count": count_a, "retryReplayed": retry_a.get("replayed")},
                   unreadAnswer={"count": count_b, "retryReplayed": retry_b.get("replayed")})

    def browser_reconnect(self):
        self.tabs.open_droppable("p1", self.file_id, self.page_id)
        dropped = self.tabs.drop_notifications("p1")
        for i in range(3):
            self.ai_run(f"const r = penpot.createRectangle(); r.name = 'missed-{i}'; return 1;")
        views, seconds = self.consistent(self.file_id, timeout=20)
        names = set(views["p1"])
        self.check("browserReconnectCatchUp",
                   dropped == 1 and {"missed-0", "missed-1", "missed-2"} <= names
                   and views["p1"] == views["backend"],
                   dropped=dropped, seconds=seconds)
        self.tabs.open(self.file_id, self.page_id)

    def burst(self):
        """Many saves in a short time (E8: a connection buffers 64 notifications)."""
        errors = []

        def session(n):
            client = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
            for i in range(25):
                try:
                    client.execute_code(f"const r = penpot.createRectangle(); r.name = 'burst-{n}-{i}'; r.x = {i * 5}; return 1;",
                                        fileId=self.file_id, sessionId=f"{self.session}-burst-{n}")
                except Exception as error:  # noqa: BLE001
                    errors.append(str(error)[:120])

        threads = [threading.Thread(target=session, args=(n,)) for n in range(2)]
        started = time.monotonic()
        [t.start() for t in threads]
        [t.join() for t in threads]
        elapsed = round(time.monotonic() - started, 1)
        views, seconds = self.consistent(self.file_id, timeout=30)
        bursts = sum(1 for name in views["backend"] if name.startswith("burst-"))
        self.check("burst",
                   not errors and bursts == 50
                   and len({json.dumps(v, sort_keys=True) for v in views.values()}) == 1,
                   saves=50, elapsed=elapsed, settleSeconds=seconds, errors=errors[:3])

    def permission_revoked(self):
        fixtures = mcpv.fixtures()
        team, editor_id = fixtures["team"]["id"], fixtures["profiles"]["editor"]["id"]
        set_role = lambda role: mcpv.rpc_ok("update-team-member-role",  # noqa: E731
                                            {"teamId": team, "memberId": editor_id, "role": role},
                                            mcpv.token("owner"))
        before = backend_state(self.file_id)
        set_role("viewer")
        try:
            time.sleep(1)
            try:
                self.ai_run("penpot.currentPage.findShapes({ name: 'a' })[0].x = 5; return 1;")
                outcome = "accepted"
            except mcp_client.ToolError as error:
                outcome = str(error)[:200]
            after = backend_state(self.file_id)
        finally:
            set_role("editor")
        time.sleep(1)
        recovered = self.ai_run("penpot.currentPage.findShapes({ name: 'a' })[0].x = 6; return 1;")["commit"]
        self.check("permissionRevoked",
                   outcome.startswith("Tool execution failed: [not-found]") and before[2] == after[2]
                   and recovered and recovered["saved"],
                   outcome=outcome)

    def restart_in_flight(self):
        code = ("await new Promise((r) => setTimeout(r, 8000)); "
                "const r = penpot.createRectangle(); r.name = '%s'; return 1;")
        report = {}
        for mode in ("graceful", "crash"):
            name = f"interrupted-{mode}"
            request_id = f"{self.session}-{mode}"
            before = backend_state(self.file_id)
            errors = []

            def run():
                try:
                    self.ai_run(code % name, requestId=request_id, fileId=self.file_id)
                except Exception as error:  # noqa: BLE001
                    errors.append(str(error)[:200])

            thread = threading.Thread(target=run)
            thread.start()
            time.sleep(3)
            # a graceful stop as a deployment does it: SIGTERM to the server process only
            restart_mcp(hard=(mode == "crash"), signal="TERM")
            thread.join()
            after = backend_state(self.file_id)
            self.ai = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
            try:
                retry = self.ai_run(code % name, requestId=request_id, fileId=self.file_id)
                retry = {"ran": True, "replayed": retry.get("replayed")}
            except mcp_client.ToolError as error:
                retry = {"ran": False, "error": str(error)[:220]}
            final = backend_state(self.file_id)
            report[mode] = {"firstAttempt": errors, "nothingSavedByIt": name not in after[2] and before[0] == after[0],
                            "retry": retry, "copies": list(final[2]).count(name)}
        ok = (report["graceful"]["nothingSavedByIt"] and report["graceful"]["retry"]["ran"]
              and report["graceful"]["copies"] == 1
              and report["crash"]["nothingSavedByIt"] and not report["crash"]["retry"]["ran"]
              and "precondition-failed" in report["crash"]["retry"]["error"] and report["crash"]["copies"] == 0)
        self.check("restartInFlight", ok, **report)


def restart_mcp(hard=False, signal="INT"):
    """Restarts the MCP server: Ctrl-C (`signal="INT"`, the whole process group gets it, executors and
    the `pnpm` wrapper included), SIGTERM of the server alone (`signal="TERM"`, as a container stop sends
    it), or SIGKILL of the server alone (`hard`), as a crash would."""
    stop = ("pkill -9 -f 'dist/[i]ndex.js --multi-user'" if hard
            else "pkill -TERM -f 'dist/[i]ndex.js --multi-user'" if signal == "TERM"
            else "tmux send-keys -t mcpv:mcp C-c")
    # the window's shell takes the restart only once the old server has ended
    wait = "for i in $(seq 1 100); do pgrep -f 'dist/[i]ndex.js --multi-user' >/dev/null || break; sleep 0.2; done; sleep 1"
    subprocess.run(["docker", "exec", "-u", "penpot", mcpv.MAIN, "bash", "-lc",
                    f"{stop}; {wait}; tmux send-keys -t mcpv:mcp Up enter"], check=True)
    for _ in range(60):
        try:
            mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
            return
        except Exception:  # noqa: BLE001
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()
    run = Pen6(args.space)
    run.setup()
    for step in (run.concurrent_different_shapes, run.same_property, run.deleted_shape, run.precondition,
                 run.restored_file, run.dedup, run.lost_response, run.browser_reconnect, run.burst,
                 run.permission_revoked, run.restart_in_flight):
        try:
            step()
        except Exception as error:  # noqa: BLE001
            run.check(step.__name__, False, crashed=repr(error)[:400])
    failed = [name for name, check in run.report.items() if not check["ok"]]
    print(json.dumps({"fileId": run.file_id, "failed": failed, "checks": run.report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
