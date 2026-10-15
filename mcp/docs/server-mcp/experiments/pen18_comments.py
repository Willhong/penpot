#!/usr/bin/env python3
#
# PEN-18: comment threads, replies and resolution through MCP with no browser.
#
#   python3 -I pen18_comments.py --space <ego-browser task space>
#
# - pen18_comments.js (dual run with a browser workspace): threads on the page
#   and on a board, replies, an edited reply, resolve, move, remove, queries;
#   the return values must be equal.
# - live: the owner's tab has the file open; each comment change the editor
#   makes on the server shows there without a reload, and after one.
# - permissions: the editor cannot edit or remove the owner's comments (the
#   browser's rule), can reply to and resolve them; a viewer can comment, as
#   in a browser; an outsider cannot read the threads; the author is always
#   the token's user.
# - duplicates: the same `requestId` twice creates one thread.
# - reconnect: a tab whose notification socket dropped while the server added
#   a thread shows it once it reconnects.
#
# Prints a JSON report; exit status 1 when a check fails.

import argparse
import json
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dual_run  # noqa: E402
import mcp_client  # noqa: E402
import mcpv  # noqa: E402
import observers  # noqa: E402

TAB_THREADS = """
const k = cljs.core.keyword;
const s = cljs.core.deref(app.main.store.state);
const threads = cljs.core.get(s, k("comment-threads"));
if (!threads) return null;
const out = [];
cljs.core.run_BANG_((e) => {
  const t = cljs.core.val(e);
  const p = cljs.core.get(t, k("position"));
  out.push({ seq: cljs.core.get(t, k("seqn")), resolved: cljs.core.get(t, k("is-resolved")),
             comments: cljs.core.get(t, k("count-comments")),
             position: p ? [cljs.core.get(p, k("x")), cljs.core.get(p, k("y"))] : null });
}, threads);
return out.sort((a, b) => a.seq - b.seq);
"""

READ_THREADS = """
const threads = await penpot.currentPage.findCommentThreads({ onlyYours: false, showResolved: true });
return threads.sort((a, b) => a.seqNumber - b.seqNumber).map((t) => ({ seq: t.seqNumber, resolved: t.resolved,
  position: [t.position.x, t.position.y], owner: t.owner && t.owner.name }));
"""


def wait_until(predicate, timeout=10.0):
    started = time.monotonic()
    while True:
        value = predicate()
        if value or time.monotonic() - started > timeout:
            return value, round(time.monotonic() - started, 2)
        time.sleep(0.3)


class Pen18:
    def __init__(self, space):
        self.space = space
        self.tabs = observers.Tabs(space, labels=("p1",))
        self.editor = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
        self.session = f"pen18-{time.time_ns()}"
        self.report = {}

    def run(self, code, client=None, session=None, **kwargs):
        client = client or self.editor
        return client.execute_code(code, sessionId=session or self.session, **kwargs)[0]

    def tab_threads(self):
        return self.tabs.evaluate("p1", TAB_THREADS)

    def live(self):
        self.file_id, page_id = mcpv.create_file("pen18-live")
        self.run("const b = penpot.createBoard(); b.name = 'B'; b.resize(300, 300); return 1;", fileId=self.file_id)
        self.tabs.open(self.file_id, page_id)
        steps = {}

        def step(name, code, expect):
            self.run(code)
            seen, seconds = wait_until(lambda: (lambda t: t if t is not None and expect(t) else None)(self.tab_threads()))
            steps[name] = {"ok": bool(seen), "seconds": seconds, "tab": seen or self.tab_threads()}

        step("created", "const t = await penpot.currentPage.addCommentThread('From the server', { x: 50, y: 60 }); "
                        "storage.t = t; return t.seqNumber;",
             lambda t: len(t) == 1 and t[0]["comments"] == 1)
        step("replied", "await storage.t.reply('A reply from the server'); return 1;",
             lambda t: len(t) == 1 and t[0]["comments"] == 2)
        step("resolved", "storage.t.resolved = true; return 1;", lambda t: t and t[0]["resolved"])
        step("moved", "storage.t.position = { x: 120, y: 90 }; return 1;",
             lambda t: t and t[0]["position"] == [120, 90])
        step("second", "storage.u = await penpot.currentPage.addCommentThread('Second', { x: 200, y: 10 }); return 1;",
             lambda t: len(t) == 2)
        step("removed", "await storage.u.remove(); return 1;", lambda t: len(t) == 1)
        reloaded = self.tabs.evaluate("p1", TAB_THREADS, reload=True)
        server = self.run(READ_THREADS)["result"]
        self.report["live"] = {
            "ok": all(s["ok"] for s in steps.values()) and len(reloaded) == 1 and reloaded[0]["resolved"]
                  and len(server) == 1 and server[0]["resolved"] and server[0]["position"] == [120, 90],
            "steps": steps, "afterReload": reloaded, "server": server,
        }

    def permissions(self):
        # the owner comments in the browser
        owner_thread = self.tabs.run_code("p1", """
const t = await penpot.currentPage.addCommentThread('Owner thread', { x: 10, y: 250 });
return t.seqNumber;""", settle=300)["result"]
        attempt = """
const t = (await penpot.currentPage.findCommentThreads({ onlyYours: false, showResolved: true }))
  .find((x) => x.seqNumber === %d);
const first = (await t.findComments())[0];
const out = {};
const tryIt = async (name, fn) => { try { await fn(); out[name] = 'accepted'; } catch (e) { out[name] = String(e.message || e).slice(0, 160); } };
await tryIt('editOwnersComment', () => { first.content = 'changed by the editor'; });
await tryIt('removeOwnersThread', () => t.remove());
await tryIt('reply', () => t.reply('The editor replies'));
await tryIt('resolve', () => { t.resolved = true; });
const after = await t.findComments();
return { out, comments: after.map((c) => [c.user.name, c.content]), author: after[after.length - 1].user.name,
         resolved: t.resolved };""" % owner_thread
        editor = self.run(attempt)["result"]

        viewer = mcp_client.Client(mcpv.token("viewer", "mcp"), executor="server")
        try:
            by_viewer = viewer.execute_code("""
const t = await penpot.currentPage.addCommentThread('From a viewer', { x: 300, y: 300 });
return { seq: t.seqNumber, owner: t.owner && t.owner.name };""", fileId=self.file_id, sessionId=f"{self.session}-v")[0]
            viewer_outcome = {"result": by_viewer["result"], "saved": by_viewer["commit"]}
        except mcp_client.ToolError as error:
            viewer_outcome = {"error": str(error)[:200]}

        outsider = mcpv.rpc("get-comment-threads", {"fileId": self.file_id}, mcpv.token("outsider"))
        self.report["permissions"] = {
            "editor": editor, "viewer": viewer_outcome, "outsiderStatus": outsider[0],
            "ok": editor["out"]["editOwnersComment"] != "accepted" and editor["out"]["removeOwnersThread"] != "accepted"
                  and editor["out"]["reply"] == "accepted" and editor["out"]["resolve"] == "accepted"
                  and editor["comments"][0] == ["MCPV Owner", "Owner thread"] and editor["author"] == "MCPV Editor"
                  and viewer_outcome.get("result", {}).get("owner") == "MCPV Viewer"
                  and outsider[0] != 200,
        }

    def duplicates(self):
        before = len(self.run(READ_THREADS)["result"])
        code = "const t = await penpot.currentPage.addCommentThread('Only once', { x: 400, y: 20 }); return t.seqNumber;"
        first = self.run(code, requestId=f"{self.session}-dup")
        second = self.run(code, requestId=f"{self.session}-dup")
        after = len(self.run(READ_THREADS)["result"])
        self.report["duplicates"] = {
            "ok": after == before + 1 and second.get("replayed") is True and first["result"] == second["result"],
            "before": before, "after": after, "replayed": second.get("replayed"),
        }

    def reconnect(self):
        file_id, page_id = mcpv.create_file("pen18-reconnect")
        self.run("return 1;", fileId=file_id)
        self.tabs.open_droppable("p1", file_id, page_id)
        dropped = self.tabs.drop_notifications("p1")
        self.run("await penpot.currentPage.addCommentThread('While the tab was offline', { x: 5, y: 5 }); return 1;")
        seen, seconds = wait_until(lambda: (lambda t: t if t else None)(self.tab_threads()), timeout=20)
        self.report["reconnect"] = {"ok": bool(seen) and len(seen) == 1, "dropped": dropped, "seconds": seconds,
                                    "tab": seen}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()

    dual = dual_run.DualRun(args.space)
    report = {"comments": dual.scenario("pen18-comments", (HERE / "pen18_comments.js").read_text())}
    run = Pen18(args.space)
    for step in (run.live, run.permissions, run.duplicates, run.reconnect):
        try:
            step()
        except Exception as error:  # noqa: BLE001
            run.report[step.__name__] = {"ok": False, "crashed": repr(error)[:600]}
    report.update(run.report)

    failed = [name for name, check in report.items() if not check.get("ok")]
    print(json.dumps({"failed": failed, "report": report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
