#!/usr/bin/env python3
#
# PEN-10: the server execution context against open browser tabs.
#
#   python3 -I pen10_context.py --space <ego-browser task space>
#
# The AI is the editor through MCP (`?executor=server`). Tab p2 is the
# same editor in a browser, tab p1 the owner (another user). Checks D8:
# `viewport` and `theme` read the screen of the same user's tab (b), and
# fall back to `ui-only` and "light" without one; listeners added with
# `penpot.on` stay for the session and hear other users' saves; the
# overview and API docs carry the server-mode guidance.
#
# Restarts the MCP server first so it runs the current build.
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
from pen6_consistency import restart_mcp, wait_until  # noqa: E402

SCREEN = """
const v = penpot.viewport;
return { zoom: v.zoom, center: v.center, bounds: v.bounds, theme: penpot.theme };
"""

AI_SCREEN = """
let screen = null, error = null;
try { const v = penpot.viewport; screen = { zoom: v.zoom, center: v.center, bounds: v.bounds }; }
catch (e) { error = e.code + ': ' + e.message; }
let move = null;
try { penpot.viewport.zoom = 3; move = 'moved'; } catch (e) { move = e.code + ': ' + e.message; }
return { screen, error, move, theme: penpot.theme };
"""

PRESENCE_OF = """
const k = cljs.core.keyword;
const s = cljs.core.deref(app.main.store.state);
const presence = cljs.core.get(s, k("workspace-presence"));
const out = {};
cljs.core.run_BANG_((e) => {
  const p = cljs.core.val(e);
  out[String(cljs.core.key(e))] = { profileId: String(cljs.core.get(p, k("profile-id"))),
                                    hasVbox: cljs.core.get(p, k("vbox")) != null,
                                    hasPoint: cljs.core.get(p, k("point")) != null };
}, presence);
return out;
"""


def close(a, b, tolerance=0.01):
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(close(a[k], b[k], tolerance) for k in a)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tolerance * max(1, abs(a), abs(b))
    return a == b


class Pen10:
    def __init__(self, space):
        self.tabs = observers.Tabs(space)
        self.ai = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
        self.session = f"pen10-{time.time_ns()}"
        self.report = {}

    def ai_run(self, code, session=None, **kwargs):
        return self.ai.execute_code(code, sessionId=session or self.session, **kwargs)[0]

    def human(self, label, code):
        result = self.tabs.run_code(label, code, settle=500)
        if not result.get("ok"):
            raise RuntimeError(f"{label} failed: {result}")
        return result["result"]

    def check(self, name, ok, **detail):
        self.report[name] = {"ok": bool(ok), **detail}

    def setup(self):
        self.file_id, self.page_id = mcpv.create_file("pen10-context")
        self.ai_run("""
const r = penpot.createRectangle(); r.name = 'a'; r.x = 0; r.y = 0; r.resize(100, 100);
return r.id;""", fileId=self.file_id)
        self.tabs.blank()

    def no_tab(self):
        """No tab of the user on the file: reading the viewport is `ui-only`, theme is "light"."""
        seen = self.ai_run(AI_SCREEN)["result"]
        self.check("noTab",
                   seen["screen"] is None and "ui-only" in (seen["error"] or "") and "reported its screen" in seen["error"]
                   and "ui-only" in seen["move"] and seen["theme"] == "light", seen=seen)

    def observed(self):
        """The AI reads the screen of the same user's tab (p2), not the owner's (p1), and follows its changes
        made without moving the pointer."""
        self.tabs.open(self.file_id, self.page_id)
        self.human("p1", "penpot.viewport.zoom = 0.5; return 1;")
        rounds = []
        for zoom, center in ((2, {"x": 500, "y": 300}), (1.25, {"x": -200, "y": 40})):
            self.human("p2", f"penpot.viewport.zoom = {zoom}; penpot.viewport.center = {json.dumps(center)}; return 1;")
            browser = self.human("p2", SCREEN)

            def matches():
                seen = self.ai_run(AI_SCREEN)["result"]
                screen = seen["screen"]
                return seen if screen and close(screen, {k: browser[k] for k in ("zoom", "center", "bounds")}) else None

            seen, seconds = wait_until(matches, timeout=10)
            rounds.append({"browser": browser, "ai": seen or self.ai_run(AI_SCREEN)["result"], "seconds": seconds})
        ok = all(r["ai"]["screen"] and close(r["ai"]["screen"], {k: r["browser"][k] for k in ("zoom", "center", "bounds")})
                 and r["ai"]["theme"] == r["browser"]["theme"] and "ui-only" in r["ai"]["move"]
                 and "AI follow" in r["ai"]["move"] for r in rounds)
        self.check("observedScreen", ok, rounds=rounds)

    def joining_session(self):
        """A session that opens the file after the tab set its screen reads it at once: the tab sends its
        screen to sessions that join."""
        browser = self.human("p2", SCREEN)
        session = f"{self.session}-late"
        started = time.monotonic()
        seen = self.ai_run(AI_SCREEN, session=session, fileId=self.file_id)["result"]
        attempts = 1
        while not seen["screen"] and attempts < 10:
            time.sleep(0.5)
            seen = self.ai_run(AI_SCREEN, session=session)["result"]
            attempts += 1
        self.check("joiningSession",
                   seen["screen"] is not None and close(seen["screen"], {k: browser[k] for k in ("zoom", "center", "bounds")}),
                   attempts=attempts, browser=browser, ai=seen, seconds=round(time.monotonic() - started, 2))

    def presence(self):
        """The owner's tab sees the editor's tab screen and no screen from the executor session."""
        presence = self.tabs.evaluate("p1", PRESENCE_OF)
        editor = mcpv.fixtures()["profiles"]["editor"]["id"]
        mine = [p for p in presence.values() if p["profileId"] == editor]
        self.check("presence", any(p["hasVbox"] for p in mine) and any(not p["hasVbox"] for p in mine),
                   editorSessions=mine)

    def events(self):
        """Listeners stay across executions, hear the session's own changes and other users' saves, and stop
        after `penpot.off`."""
        first = self.ai_run("""
const a = penpot.currentPage.findShapes({ name: 'a' })[0];
storage.events = [];
storage.listeners = [
  penpot.on('shapechange', (s) => storage.events.push(['shape', s.name, s.x]), { shapeId: a.id }),
  penpot.on('selectionchange', (ids) => storage.events.push(['selection', ids.length])),
  penpot.on('contentsave', () => storage.events.push(['save'])),
];
penpot.selection = [a];
a.x = 10;
return 1;""")
        time.sleep(0.5)
        self.human("p1", "const a = penpot.currentPage.findShapes({ name: 'a' })[0]; a.x = 321; return 1;")

        def heard():
            events = self.ai_run("return storage.events;")["result"]
            return events if ["shape", "a", 321] in events else None

        events, seconds = wait_until(heard, timeout=15)
        events = events or self.ai_run("return storage.events;")["result"]
        self.ai_run("storage.listeners.forEach((id) => penpot.off(id)); storage.events = []; return 1;")
        self.human("p1", "const a = penpot.currentPage.findShapes({ name: 'a' })[0]; a.x = 555; return 1;")
        time.sleep(3)
        after = self.ai_run("const a = penpot.currentPage.findShapes({ name: 'a' })[0]; "
                            "return { events: storage.events, x: a.x };")["result"]
        self.check("events",
                   ["shape", "a", 10] in events and ["selection", 1] in events and ["save"] in events
                   and ["shape", "a", 321] in events and after["events"] == [] and after["x"] == 555,
                   first=first.get("result"), events=events, secondsToRemote=seconds, afterOff=after)

    def ui_only(self):
        seen = self.ai_run("""
const out = {};
for (const [name, f] of [['openViewer', () => penpot.openViewer()], ['ui.open', () => penpot.ui.open('x', '')],
                         ['zoomToFitAll', () => penpot.viewport.zoomToFitAll()], ['closePlugin', () => penpot.closePlugin()]]) {
  try { f(); out[name] = 'ran'; } catch (e) { out[name] = e.code + ': ' + e.message; }
}
return out;""")["result"]
        self.check("uiOnly", all("ui-only" in v for v in seen.values()), seen=seen)

    def guidance(self):
        server = self.ai.tool("high_level_overview")[0]
        plugin_client = mcp_client.Client(mcpv.token("editor", "mcp"), executor="plugin")
        plugin = plugin_client.tool("high_level_overview")[0]
        note_server = self.ai.tool("penpot_api_info", type="Viewport", member="zoom")[0]
        note_plugin = plugin_client.tool("penpot_api_info", type="Viewport", member="zoom")[0]
        type_server = self.ai.tool("penpot_api_info", type="Penpot")[0]
        self.check("guidance",
                   "# Server-Side Execution" in server and "Penpot MCP Plugin." not in server.split("\n")[1]
                   and "# Server-Side Execution" not in plugin and "Penpot MCP Plugin" in plugin
                   and "AI follow" in note_server and "AI follow" not in note_plugin
                   and "Server-side execution differences" in type_server,
                   serverOverviewChars=len(server), pluginOverviewChars=len(plugin),
                   serverNote=note_server[-300:])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    parser.add_argument("--no-restart", action="store_true")
    args = parser.parse_args()
    if not args.no_restart:
        restart_mcp()
    run = Pen10(args.space)
    run.setup()
    for step in (run.no_tab, run.observed, run.joining_session, run.presence, run.events, run.ui_only,
                 run.guidance):
        try:
            step()
        except Exception as error:  # noqa: BLE001
            run.check(step.__name__, False, crashed=repr(error)[:600])
    failed = [name for name, check in run.report.items() if not check["ok"]]
    print(json.dumps({"fileId": run.file_id, "failed": failed, "checks": run.report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
