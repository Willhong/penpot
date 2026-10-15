#!/usr/bin/env python3
#
# PEN-20: units of work, failures, cancellation and undo of server edits.
#
#   python3 -I pen20_history.py --space <ego-browser task space>
#
# - undo/redo: two executions over several shapes (a Flex board, texts, a
#   path, a component); `undo` twice brings the saved file back to each
#   earlier state, `redo` twice forward again; the owner's open tab follows
#   without a reload; nothing left gives `not-found`.
# - others' work: the owner edits another shape in the browser, then the AI
#   undoes: the undo goes through and keeps the owner's edit. The owner
#   edits a shape the AI's last execution changed: the undo is refused with
#   `precondition-failed`, nothing saved.
# - browser undo: an AI change reaching the owner's tab is not in the tab's
#   own undo; the tab's undo reverts the owner's own edit only.
# - failures: an execution that throws after creating shapes, one cancelled
#   while it runs, and one refused by its precondition save nothing and
#   leave the undo steps alone. `undoBlockBegin/Finish` (closed or left open)
#   make no difference: an execution is one step.
# - lost answers: the same `requestId` twice runs (and undoes) once.
# - restarts: a run cut by a crash of the MCP server before saving is
#   reported `interrupted` and not saved, and its retry runs it; a run whose
#   save went through before the crash is reported saved, with its revn, and
#   its retry does not apply it again; a crash while saving ends with a
#   report that agrees with the file.
#
# Prints a JSON report; exit status 1 when a check fails.

import argparse
import hashlib
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
from pen6_consistency import restart_mcp  # noqa: E402

# what a browser shows of a page: names, geometry and fills of its shapes
TAB_SHAPES = """
const k = cljs.core.keyword;
const s = cljs.core.deref(app.main.store.state);
const fileId = cljs.core.get(s, k("current-file-id"));
const pageId = cljs.core.get(s, k("current-page-id"));
const data = cljs.core.get_in(s, cljs.core.vector(k("files"), fileId, k("data")));
const objects = cljs.core.get_in(data, cljs.core.vector(k("pages-index"), pageId, k("objects")));
const out = [];
cljs.core.run_BANG_((e) => {
  const o = cljs.core.val(e);
  const name = cljs.core.get(o, k("name"));
  if (name === "Root Frame") return;
  const fills = cljs.core.get(o, k("fills"));
  const fill = fills && cljs.core.count(fills) ? cljs.core.get(cljs.core.first(fills), k("fill-color")) || "" : "";
  const r = cljs.core.get(o, k("selrect"));
  out.push([name, Math.round(cljs.core.get(r, k("x"))), Math.round(cljs.core.get(r, k("y"))), fill]);
}, objects);
return out.sort();
"""

TAB_UNDO = "app.main.store.emit_BANG_(app.main.data.workspace.undo.undo); return 1;"

FIRST = """
const board = penpot.createBoard(); board.name = 'card'; board.resize(320, 200);
board.fills = [{ fillColor: '#ffffff', fillOpacity: 1 }];
const flex = board.addFlexLayout(); flex.dir = 'column'; flex.rowGap = 8; flex.horizontalPadding = 12;
const title = penpot.createText('Undo me'); title.name = 'title'; flex.appendChild(title);
const box = penpot.createRectangle(); box.name = 'box'; box.resize(80, 40);
box.fills = [{ fillColor: '#228be6', fillOpacity: 1 }]; flex.appendChild(box);
const path = penpot.createPath(); path.name = 'path'; path.d = 'M 0 0 L 40 20 L 0 40 Z';
path.x = 400; path.y = 0;
const badge = penpot.createRectangle(); badge.name = 'badge'; badge.resize(40, 20); badge.x = 400; badge.y = 100;
const component = penpot.library.local.createComponent([badge]);
return { board: board.id };
"""

SECOND = """
const shapes = penpot.currentPage.findShapes();
const by = (n) => shapes.find((s) => s.name === n);
by('box').fills = [{ fillColor: '#fa5252', fillOpacity: 1 }];
by('box').resize(120, 40);
by('title').characters = 'Changed';
by('path').x = 450;
by('card').name = 'card v2';
return 1;
"""


def comparable(objects):
    """Shapes keyed by name and parent name, without the fields a save stamps on its own."""
    names = {id: o["name"] for id, o in objects.items()}
    out = {}
    for o in objects.values():
        key = f"{names.get(o.get('parentId'), '-')}/{o['name']}"
        out[key] = {k: v for k, v in o.items() if k not in ("id", "parentId", "frameId", "shapes")}
        out[key]["children"] = [names.get(c) for c in o.get("shapes") or []]
    return out


def wait_until(predicate, timeout=10.0):
    started = time.monotonic()
    while True:
        value = predicate()
        if value or time.monotonic() - started > timeout:
            return value, round(time.monotonic() - started, 2)
        time.sleep(0.3)


class Pen20:
    def __init__(self, space):
        self.tabs = observers.Tabs(space, labels=("p1",))
        self.ai = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
        self.session = f"pen20-{time.time_ns()}"
        self.report = {}

    def run(self, code, client=None, session=None, **kwargs):
        return (client or self.ai).execute_code(code, sessionId=session or self.session, **kwargs)[0]

    def undo(self, session=None, **kwargs):
        try:
            text, _ = self.ai.tool("undo", sessionId=session or self.session, **kwargs)
            return json.loads(text)
        except mcp_client.ToolError as error:
            return {"error": str(error)[:400]}

    def state(self):
        return comparable(mcpv.page_objects(self.file_id, self.page_id)[1])

    def revn(self):
        return mcpv.page_objects(self.file_id, self.page_id)[0]

    def tab_matches(self, objects):
        expected = sorted([o["name"], round(o["selrect"]["x"]), round(o["selrect"]["y"]),
                           ((o.get("fills") or [{}])[0]).get("fillColor") or ""]
                          for o in objects.values() if o["name"] != "Root Frame")
        seen, seconds = wait_until(lambda: self.tabs.evaluate("p1", TAB_SHAPES) == expected)
        return {"ok": bool(seen), "seconds": seconds}

    def undo_redo(self):
        self.file_id, self.page_id = mcpv.create_file("pen20-history")
        self.run("return 1;", fileId=self.file_id)
        self.tabs.open(self.file_id, self.page_id)
        empty = self.state()
        self.run(FIRST)
        after_first = self.state()
        self.run(SECOND)
        after_second = self.state()
        steps = {}
        for name, call, expected in (("undo1", {}, after_first), ("undo2", {}, empty),
                                     ("redo1", {"redo": True}, after_first),
                                     ("redo2", {"redo": True}, after_second)):
            answer = self.undo(**call)
            state = self.state()
            diff = sorted(set(state) ^ set(expected)) or [k for k in state if state[k] != expected[k]]
            steps[name] = {"ok": not diff and "error" not in answer, "answer": answer.get("result", answer),
                           "differs": diff[:5], "tab": self.tab_matches(mcpv.page_objects(self.file_id, self.page_id)[1])}
        self.undo()
        self.undo()
        nothing = self.undo()
        self.undo(redo=True)
        self.undo(redo=True)
        self.report["undoRedo"] = {
            "ok": all(s["ok"] and s["tab"]["ok"] for s in steps.values()) and "not-found" in nothing.get("error", ""),
            "steps": steps, "nothingLeft": nothing.get("error"),
        }

    def others_work(self):
        # the owner edits a shape the AI's last execution did not touch
        self.tabs.run_code("p1", "const b = penpot.currentPage.findShapes().find((s) => s.name === 'badge'); "
                                 "b.x = 520; return 1;", settle=300)
        time.sleep(4)  # the tab's autosave
        kept = self.undo()
        state = self.state()
        badge = next(o for k, o in state.items() if k.endswith("/badge") and o["type"] == "rect")["selrect"]
        # the owner edits a shape the AI's (now) last execution changed: the board
        self.run("penpot.currentPage.findShapes().find((s) => s.name === 'box').x = 5; return 1;")
        self.tabs.run_code("p1", "const b = penpot.currentPage.findShapes().find((s) => s.name === 'box'); "
                                 "b.rotation = 15; return 1;", settle=300)
        time.sleep(4)
        before = (self.revn(), self.state())
        refused = self.undo()
        after = (self.revn(), self.state())
        self.report["othersWork"] = {
            "ok": "error" not in kept and badge["x"] == 520
                  and "precondition-failed" in refused.get("error", "") and "box" in refused.get("error", "")
                  and before == after,
            "undoKeepingOwnerEdit": kept.get("result", kept), "ownerEditKept": badge["x"],
            "refused": refused.get("error"), "nothingSaved": before == after,
        }

    def browser_undo(self):
        self.run("penpot.currentPage.findShapes().find((s) => s.name === 'path').y = 300; return 1;")
        wait_until(lambda: any(s[0] == "path" and s[2] == 300 for s in self.tabs.evaluate("p1", TAB_SHAPES)))
        self.tabs.evaluate("p1", TAB_UNDO)
        time.sleep(1)
        after_tab_undo = [s for s in self.tabs.evaluate("p1", TAB_SHAPES) if s[0] == "path"]
        self.tabs.run_code("p1", "penpot.currentPage.findShapes().find((s) => s.name === 'badge').y = 250; return 1;",
                           settle=300)
        self.tabs.evaluate("p1", TAB_UNDO)
        time.sleep(4)
        tab = {s[0]: s for s in self.tabs.evaluate("p1", TAB_SHAPES)}
        saved = self.state()
        badge = next(o for k, o in saved.items() if k.endswith("/badge") and o["type"] == "rect")["selrect"]
        path = next(o for k, o in saved.items() if k.endswith("/path"))["selrect"]
        self.report["browserUndo"] = {
            "ok": after_tab_undo[0][2] == 300 and tab["badge"][2] != 250 and badge["y"] != 250 and path["y"] == 300,
            "pathAfterTabUndo": after_tab_undo, "badgeAfterTabUndo": tab["badge"], "savedPathY": path["y"],
        }

    def failures(self):
        before = (self.revn(), self.state())
        failed = {}
        try:
            self.run("for (let i = 0; i < 3; i++) { const r = penpot.createRectangle(); r.name = 'partial' + i; } "
                     "throw new Error('stop half way');")
        except mcp_client.ToolError as error:
            failed["throws"] = str(error)[:160]
        job = json.loads(self.ai.tool("execute_code", sessionId=self.session, **{"async": True}, code=(
            "for (let i = 0; i < 3; i++) { const r = penpot.createRectangle(); r.name = 'cancelled' + i; } "
            "await new Promise((r) => setTimeout(r, 6000)); return 1;"))[0])
        time.sleep(1)
        self.ai.tool("execution_job", jobId=job["jobId"], cancel=True)
        for _ in range(60):
            view = json.loads(self.ai.tool("execution_job", jobId=job["jobId"])[0])
            if view["status"] in ("done", "error", "cancelled"):
                break
            time.sleep(0.3)
        failed["cancelled"] = view["status"]
        try:
            self.run("const r = penpot.createRectangle(); r.name = 'stale'; return 1;", ifUnchangedSinceRevn=0)
        except mcp_client.ToolError as error:
            failed["precondition"] = str(error)[:160]
        after = (self.revn(), self.state())
        # blocks inside an execution: one step all the same, also when left open
        self.run("const id = penpot.history.undoBlockBegin(); "
                 "penpot.currentPage.findShapes().find((s) => s.name === 'path').x = 600; "
                 "penpot.history.undoBlockFinish(id); "
                 "penpot.history.undoBlockBegin(); "
                 "penpot.currentPage.findShapes().find((s) => s.name === 'path').y = 20; return 1;")
        blocks = self.undo()
        path = next(o for k, o in self.state().items() if k.endswith("/path"))["selrect"]
        self.report["failures"] = {
            "ok": before == after and "stop half way" in failed.get("throws", "")
                  and failed["cancelled"] == "cancelled" and "precondition-failed" in failed.get("precondition", "")
                  and "error" not in blocks and path["x"] == 400 and path["y"] == 300,
            **failed, "nothingSaved": before == after, "blocksUndoneAsOne": [path["x"], path["y"]],
        }

    def lost_answers(self):
        request = f"{self.session}-dup"
        first = self.run("const r = penpot.createEllipse(); r.name = 'once'; return r.id;", requestId=request)
        second = self.run("const r = penpot.createEllipse(); r.name = 'once'; return r.id;", requestId=request)
        names = [o["name"] for o in self.state().values()]
        undo_request = f"{self.session}-undo"
        u1 = self.undo(requestId=undo_request)
        u2 = self.undo(requestId=undo_request)
        names_after = [o["name"] for o in self.state().values()]
        self.report["lostAnswers"] = {
            "ok": names.count("once") == 1 and second.get("replayed") is True and first["result"] == second["result"]
                  and "error" not in u1 and u2.get("replayed") is True and names_after.count("once") == 0
                  and "path" in [n for n in names_after],
            "copies": names.count("once"), "undoReplayed": u2.get("replayed"),
            "afterUndo": names_after.count("once"),
        }

    # --- restarts ---

    def status(self, request_id):
        text, _ = self.ai.tool("request_status", requestId=request_id)
        return json.loads(text)

    def restarts(self):
        report = {}
        file_id, page_id = mcpv.create_file("pen20-restart")
        self.run("return 1;", fileId=file_id, session=f"{self.session}-r")

        def names():
            return [o["name"] for o in mcpv.page_objects(file_id, page_id)[1].values()]

        # (1) a crash while the code runs: nothing saved, the retry runs it
        request = f"{self.session}-crash-running"
        code = "await new Promise((r) => setTimeout(r, 8000)); const r = penpot.createRectangle(); r.name = 'after-crash'; return 1;"
        thread = threading.Thread(target=lambda: self.safe_run(code, request, f"{self.session}-r", file_id))
        thread.start()
        time.sleep(3)
        restart_mcp(hard=True)
        thread.join()
        self.ai = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
        time.sleep(16)  # the crashed instance stops counting as alive
        status = self.status(request)
        retry = self.safe_run(code, request, f"{self.session}-r", file_id)
        report["crashWhileRunning"] = {
            "ok": status == {"status": "interrupted", "saved": False} and retry.get("ran")
                  and names().count("after-crash") == 1,
            "status": status, "retry": retry, "copies": names().count("after-crash"),
        }

        # (2) a save that went through, its answer lost with its instance: as an interrupted run leaves it
        before = mcpv.page_objects(file_id, page_id)[0]
        self.run("const r = penpot.createRectangle(); r.name = 'saved-then-lost'; return 1;",
                 session=f"{self.session}-r", fileId=file_id)
        changes = mcpv.rpc_ok("get-file-changes", {"fileId": file_id, "sinceRevn": before}, mcpv.token("editor"))
        session_id = changes["changes"][0]["sessionId"]
        request = f"{self.session}-lost"
        owner_key = hashlib.sha256(mcpv.token("editor", "mcp").encode()).hexdigest()
        entry = {"state": "running", "startedAt": 0, "instance": "crashed-instance",
                 "save": {"fileId": file_id, "revnBefore": before, "sessionId": session_id}, "savingAt": 0}
        mcpv.container(f"redis-cli -h valkey -n 1 SET 'penpot-mcp:penpot-mcpverify:executor-request:"
                       f"{owner_key}:{request}' '{json.dumps(entry)}' PX 600000")
        status = self.status(request)
        retry = self.run("const r = penpot.createRectangle(); r.name = 'saved-then-lost'; return 1;",
                         session=f"{self.session}-r", requestId=request, fileId=file_id)
        report["savedThenLost"] = {
            "ok": status == {"status": "interrupted", "saved": True, "revn": before + 1}
                  and retry.get("replayed") is True and retry["commit"]["revn"] == before + 1
                  and retry["commit"]["warnings"][0]["code"] == "result-lost"
                  and names().count("saved-then-lost") == 1,
            "status": status, "retryCommit": retry.get("commit"), "copies": names().count("saved-then-lost"),
        }

        # (3) a crash while saving a large execution: the report agrees with the file
        request = f"{self.session}-crash-saving"
        big = ("for (let i = 0; i < 400; i++) { const t = penpot.createText('Saving ' + i); t.name = 'big-' + i; "
               "t.x = (i % 20) * 90; t.y = Math.floor(i / 20) * 30; } return 1;")
        job = json.loads(self.ai.tool("execute_code", code=big, sessionId=f"{self.session}-r", requestId=request,
                                      fileId=file_id, **{"async": True})[0])
        seen = None
        for _ in range(600):
            view = json.loads(self.ai.tool("execution_job", jobId=job["jobId"])[0])
            if view.get("progress") == "saving" or view["status"] != "running" and view["status"] != "pending":
                seen = view
                break
            time.sleep(0.05)
        if seen and seen.get("progress") == "saving":
            restart_mcp(hard=True)
        self.ai = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
        time.sleep(35)  # instance gone, and a save sent then has had time to arrive
        status = self.status(request)
        count = sum(1 for n in names() if n.startswith("big-"))
        report["crashWhileSaving"] = {
            "ok": seen is not None and seen.get("progress") == "saving" and status["status"] == "interrupted"
                  and ((status["saved"] is True and count == 400) or (status["saved"] is False and count == 0)),
            "killedAt": seen and (seen.get("progress") or seen["status"]), "status": status, "savedShapes": count,
        }
        self.report["restarts"] = {"ok": all(r["ok"] for r in report.values()), **report}

    def safe_run(self, code, request, session, file_id):
        try:
            self.run(code, requestId=request, session=session, fileId=file_id)
            return {"ran": True}
        except Exception as error:  # noqa: BLE001
            return {"ran": False, "error": str(error)[:200]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()
    run = Pen20(args.space)
    for step in (run.undo_redo, run.others_work, run.browser_undo, run.failures, run.lost_answers, run.restarts):
        try:
            step()
        except Exception as error:  # noqa: BLE001
            run.report[step.__name__] = {"ok": False, "crashed": repr(error)[:600]}
    failed = [name for name, check in run.report.items() if not check.get("ok")]
    print(json.dumps({"failed": failed, "report": run.report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
