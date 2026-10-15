#!/usr/bin/env python3
#
# PEN-24: "AI follow" — a browser tab of the user that turns it on shows
# where the user's server-side MCP session works; other tabs do not move.
#
#   python3 -I pen24_follow.py --space <ego-browser task space>
#
# Tabs: p2 = editor with AI follow on, p3 = editor with it off, p1 = owner
# (another user). AI calls are the editor's MCP session.
#
# - off: with no tab following, moving the viewport fails with `ui-only`,
#   `openPage`/`selection` change the session only (`follow.tabs` 0), and no
#   tab moves.
# - on: `openPage`, `selection`, `viewport.zoom`/`center`, `zoomIntoView`,
#   `zoomReset`, `zoomToFitAll` show on p2 within the D7 bound (p95 1 s from
#   the response), with `follow.tabs` 1; p3 and p1 never move.
# - show changes: p2 on another page goes to the page of the shapes a call
#   changed and shows them selected; on that page already, it stays put.
# - other file: a call on another file does not move p2.
# - user moves: scrolling p2 turns following off, with a notice; the next
#   viewport move is `ui-only` again.
# - menu: the editor's MCP menu turns it on and off.
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
import mcp_client  # noqa: E402
import mcpv  # noqa: E402
import observers  # noqa: E402

# records every change of the tab's screen with its time
RECORD = """
const k = cljs.core.keyword;
const g = (m, ...ks) => cljs.core.get_in(m, cljs.core.vec(ks.map((x) => k(x))));
const snap = (s) => {
  const vbox = g(s, "workspace-local", "vbox");
  const sel = g(s, "workspace-local", "selected");
  return JSON.stringify({
    page: String(g(s, "current-page-id")), zoom: g(s, "workspace-local", "zoom"),
    x: vbox ? cljs.core.get(vbox, k("x")) : null, y: vbox ? cljs.core.get(vbox, k("y")) : null,
    w: vbox ? cljs.core.get(vbox, k("width")) : null, h: vbox ? cljs.core.get(vbox, k("height")) : null,
    selected: sel ? cljs.core.into_array(sel).map(String).sort() : [],
    following: g(s, "workspace-ai-follow") === true });
};
cljs.core.remove_watch(app.main.store.state, "pen24");
window.__pen24 = [[Date.now(), snap(cljs.core.deref(app.main.store.state))]];
cljs.core.add_watch(app.main.store.state, "pen24", (key, ref, o, n) => {
  const s = snap(n);
  if (s !== window.__pen24[window.__pen24.length - 1][1]) window.__pen24.push([Date.now(), s]);
});
return 1;
"""

LOG = "return (window.__pen24 || []).map(([t, s]) => [t, JSON.parse(s)]);"
FOLLOW_ON = "app.main.store.emit_BANG_(app.main.data.workspace.ai_follow.start()); return 1;"
TOASTS = """return Array.from(document.querySelectorAll('[class*="toast"], [class*="notification"]'))
  .map((n) => n.textContent.trim()).filter(Boolean);"""

SETUP = """
const a = penpot.currentPage; a.name = 'A';
const r = penpot.createRectangle(); r.name = 'on A'; r.x = 0; r.y = 0;
const b = penpot.createPage(); b.name = 'B';
await penpot.openPage(b);
const far = penpot.createRectangle(); far.name = 'far on B'; far.x = 3000; far.y = 2000; far.resize(200, 100);
const near = penpot.createEllipse(); near.name = 'near on B'; near.x = 10; near.y = 10;
await penpot.openPage(a);
return { a: a.id, b: b.id, onA: r.id, far: far.id, near: near.id };
"""


class Pen24:
    def __init__(self, space):
        self.tabs = observers.Tabs(space, labels=("p1", "p2", "p3"))
        self.ai = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
        self.session = f"pen24-{time.time_ns()}"
        self.report = {}

    def run(self, code, **kwargs):
        started = time.time()
        try:
            answer = self.ai.execute_code(code, sessionId=self.session, **kwargs)[0]
        except mcp_client.ToolError as error:
            answer = {"error": str(error)[:300]}
        return answer, started, time.time()

    def record(self):
        for label in ("p1", "p2", "p3"):
            self.tabs.evaluate(label, RECORD)

    def log(self, label):
        return self.tabs.evaluate(label, LOG)

    def state(self, label):
        return self.log(label)[-1][1]

    def wait(self, label, predicate, since, timeout=5.0):
        """Time from `since` until the tab's screen first meets `predicate` (0 when it did before)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            for t, s in self.log(label):
                if t / 1000 >= since - 0.05 and predicate(s):
                    return max(0.0, round(t / 1000 - since, 3))
            time.sleep(0.2)
        return None

    def setup(self):
        self.file_id, page_id = mcpv.create_file("pen24-follow")
        ids, _, _ = self.run(SETUP, fileId=self.file_id)
        self.ids = ids["result"]
        self.tabs.open(self.file_id, self.ids["a"])
        self.record()
        self.before = {label: self.state(label) for label in ("p1", "p3")}

    def unmoved(self, label):
        now = self.state(label)
        before = self.before[label]
        return all(now[key] == before[key] for key in ("page", "zoom", "x", "y", "selected"))

    def off(self):
        zoom, _, _ = self.run("penpot.viewport.zoom = 2; return 1;")
        page, _, _ = self.run("const b = penpot.currentFile.pages.find((p) => p.name === 'B'); "
                              "await penpot.openPage(b); const a = penpot.currentFile.pages.find((p) => p.name === 'A'); "
                              "await penpot.openPage(a); return 1;")
        time.sleep(1.5)
        p2 = self.state("p2")
        self.report["off"] = {
            "ok": "ui-only" in zoom.get("error", "") and page.get("follow", {}).get("tabs") == 0
                  and p2["page"] == self.ids["a"] and p2["zoom"] != 2 and self.unmoved("p1") and self.unmoved("p3"),
            "zoom": zoom.get("error"), "openPageFollow": page.get("follow"),
        }

    def on(self):
        self.tabs.evaluate("p2", FOLLOW_ON)
        time.sleep(1.5)  # its presence message reaches the session
        timings = {}
        steps = [
            ("openPage", "await penpot.openPage(penpot.currentFile.pages.find((p) => p.name === 'B')); return 1;",
             lambda s: s["page"] == self.ids["b"]),
            ("selection", "penpot.selection = [penpot.currentPage.getShapeById(%s)]; return 1;" % json.dumps(self.ids["near"]),
             lambda s: s["selected"] == [self.ids["near"]]),
            ("zoom", "penpot.viewport.zoom = 2; return 1;", lambda s: abs(s["zoom"] - 2) < 1e-6),
            ("center", "penpot.viewport.center = { x: 500, y: 400 }; return 1;",
             lambda s: abs(s["x"] + s["w"] / 2 - 500) < 1 and abs(s["y"] + s["h"] / 2 - 400) < 1),
            ("zoomIntoView", "penpot.viewport.zoomIntoView([penpot.currentPage.getShapeById(%s)]); return 1;"
             % json.dumps(self.ids["far"]),
             lambda s: s["x"] <= 3000 and s["x"] + s["w"] >= 3200 and s["y"] <= 2000 and s["y"] + s["h"] >= 2100),
            ("zoomReset", "penpot.viewport.zoomReset(); return 1;", lambda s: abs(s["zoom"] - 1) < 1e-6),
            ("zoomToFitAll", "penpot.viewport.zoomToFitAll(); return 1;",
             lambda s: s["x"] <= 10 and s["x"] + s["w"] >= 3200),
        ]
        for round_ in range(2):
            for name, code, done in steps:
                answer, asked, answered = self.run(code)
                seconds = self.wait("p2", done, answered)
                timings.setdefault(name, []).append(
                    {"seconds": seconds, "fromRequest": self.wait("p2", done, asked),
                     "callSeconds": round(answered - asked, 3), "follow": answer.get("follow"),
                     "error": answer.get("error")})
            # back to A for the next round
            self.run("await penpot.openPage(penpot.currentFile.pages.find((p) => p.name === 'A')); return 1;")
            self.wait("p2", lambda s: s["page"] == self.ids["a"], time.time() - 0.5)
        flat = sorted(t["seconds"] if t["seconds"] is not None else 99 for ts in timings.values() for t in ts)
        p95 = flat[min(len(flat) - 1, int(round(0.95 * (len(flat) - 1))))]
        self.report["on"] = {
            "ok": all(t["seconds"] is not None and t["follow"] and t["follow"]["tabs"] == 1
                      for ts in timings.values() for t in ts)
                  and p95 <= 1.0 and self.state("p2")["following"] and self.unmoved("p1") and self.unmoved("p3"),
            "p95Seconds": p95, "timings": timings,
        }

    def show_changes(self):
        # p2 is on A; a call opens B through `pageId` (no openPage call) and changes a shape there: p2 goes
        # to B with the shape selected
        answer, _, answered = self.run(
            "penpot.currentPage.getShapeById(%s).x = 40; return 1;" % json.dumps(self.ids["near"]),
            fileId=self.file_id, pageId=self.ids["b"])
        moved = self.wait("p2", lambda s: s["page"] == self.ids["b"] and s["selected"] == [self.ids["near"]],
                          answered)
        # on B already: a change on B leaves the screen as it is
        before = self.state("p2")
        self.run("penpot.currentPage.getShapeById(%s).x = 60; return 1;" % json.dumps(self.ids["far"]))
        time.sleep(1.5)
        after = self.state("p2")
        self.report["showChanges"] = {
            "ok": moved is not None and moved <= 1.0 and "show-changes" in answer.get("follow", {}).get("actions", [])
                  and after["page"] == before["page"] and after["selected"] == before["selected"]
                  and after["following"] and self.unmoved("p1") and self.unmoved("p3"),
            "seconds": moved, "follow": answer.get("follow"), "error": answer.get("error"),
            "stayedOnPage": after["page"] == before["page"],
        }

    def other_file(self):
        other, _ = mcpv.create_file("pen24-other")
        before = self.state("p2")
        answer, _, _ = self.run("const r = penpot.createRectangle(); r.name = 'elsewhere'; "
                                "penpot.selection = [r]; try { penpot.viewport.zoom = 3; return 'moved'; } "
                                "catch (e) { return String(e.message || e); }", fileId=other)
        time.sleep(1.5)
        after = self.state("p2")
        # back to the followed file for what comes next
        self.run("return 1;", fileId=self.file_id)
        self.report["otherFile"] = {
            "ok": "only available in a browser" in str(answer.get("result")) and after["page"] == before["page"]
                  and after["zoom"] == before["zoom"] and after["selected"] == before["selected"],
            "zoomAnswer": answer.get("result"), "error": answer.get("error"), "before": before, "after": after,
        }

    def user_moves(self):
        # the user scrolls p2's canvas
        script = """
const task = await taskSpace(%d);
const page = task.page("p2");
await page.mouse.move(700, 450, { label: "over the canvas" });
await page.mouse.wheel(0, 300, { label: "scroll the canvas" });
await page.waitForTimeout(800);
console.log("RESULT=true");
""" % self.tabs.space
        observers.marked(observers.ego(script), "RESULT=")
        time.sleep(1)
        state = self.state("p2")
        toasts = self.tabs.evaluate("p2", TOASTS)
        time.sleep(1)  # its presence message reaches the session
        zoom, _, _ = self.run("penpot.viewport.zoom = 1.5; return 1;")
        self.report["userMoves"] = {
            "ok": not state["following"] and any("stopped following" in t or "따라가기를 껐습니다" in t for t in toasts)
                  and "ui-only" in zoom.get("error", ""),
            "following": state["following"], "toasts": toasts, "nextZoom": zoom.get("error"),
        }

    def menu(self):
        # p3 turns it on and off through the MCP menu of the editor
        on = self.toggle_by_menu("p3")
        time.sleep(1)
        following_on = self.state("p3")["following"]
        off = self.toggle_by_menu("p3")
        time.sleep(1)
        following_off = self.state("p3")["following"]
        self.report["menu"] = {"ok": on["clicked"] and following_on and off["clicked"] and not following_off,
                               "on": on, "off": off}

    def toggle_by_menu(self, label):
        script = """
const task = await taskSpace(%d);
const page = task.page(%s);
const out = { clicked: false };
// the main menu button is the first button of the left sidebar's header
await page.evaluate(() => document.querySelector("#left-sidebar-aside button").setAttribute("data-pen24", "menu"));
await page.click("loc=css:[data-pen24='menu']", { label: "open main menu" });
await page.waitForSelector("loc=css:#file-menu-mcp", { state: "visible", timeout: 5000 });
await page.hover("loc=css:#file-menu-mcp", { label: "open MCP menu" });
await page.waitForSelector("loc=css:#mcp-menu-toggle-ai-follow", { state: "visible", timeout: 5000 });
out.label = await page.evaluate(() => document.querySelector("#mcp-menu-toggle-ai-follow").textContent.trim());
await page.click("loc=css:#mcp-menu-toggle-ai-follow", { label: "toggle AI follow" });
out.clicked = true;
await page.waitForTimeout(500);
await page.screenshot({ path: %s });
console.log("RESULT=" + JSON.stringify(out));
""" % (self.tabs.space, json.dumps(label),
       json.dumps(str(mcpv.STATE / "shots" / f"pen24-menu-{time.time_ns()}.png")))
        try:
            return observers.marked(observers.ego(script), "RESULT=")
        except Exception as error:  # noqa: BLE001
            return {"clicked": False, "error": str(error)[:400]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()
    run = Pen24(args.space)
    run.setup()
    for step in (run.off, run.on, run.show_changes, run.other_file, run.user_moves, run.menu):
        try:
            step()
        except Exception as error:  # noqa: BLE001
            run.report[step.__name__] = {"ok": False, "crashed": repr(error)[:600]}
    failed = [name for name, check in run.report.items() if not check.get("ok")]
    print(json.dumps({"failed": failed, "report": run.report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
