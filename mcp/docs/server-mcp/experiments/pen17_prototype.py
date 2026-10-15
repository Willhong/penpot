#!/usr/bin/env python3
#
# PEN-17: flows, interactions, guides and the viewer through MCP with no
# browser.
#
#   python3 -I pen17_prototype.py --space <ego-browser task space>
#
# - pen17_prototype.js (dual run with a browser workspace): interactions of
#   every action kind with animations, edits, flows, ruler and board guides,
#   a removed board that interactions and a flow point to. Return values,
#   saved shapes and saved page data (flows, guides) must be equal.
# - pen17_refusals.js (dual run): invalid triggers, actions, destinations,
#   delays, animations, flows and guides.
# - viewer (server writes, browser plays): `openViewer()` answers `ui-only`
#   with the viewer URL of the page; the prototype the server saved works in
#   the browser viewer at that URL: clicking the button goes to the next board.
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

PROTOTYPE = """
const home = penpot.createBoard(); home.name = "Home"; home.resize(300, 400);
home.fills = [{ fillColor: "#f1f3f5", fillOpacity: 1 }];
const detail = penpot.createBoard(); detail.name = "Detail"; detail.x = 400; detail.resize(300, 400);
detail.fills = [{ fillColor: "#d0ebff", fillOpacity: 1 }];
const button = penpot.createRectangle(); button.name = "button"; home.appendChild(button);
button.x = 50; button.y = 300; button.resize(200, 60); button.fills = [{ fillColor: "#e03131", fillOpacity: 1 }];
button.addInteraction("click", { type: "navigate-to", destination: detail });
try { penpot.openViewer(); return null; } catch (e) { return { code: e.code, message: String(e.message) }; }
"""

PLAY = """
const task = await taskSpace(%(space)d);
const page = task.page("p1");
const state = () => page.evaluate(() => {
  const c = document.querySelector("canvas");
  const r = c ? c.getBoundingClientRect() : null;
  const header = [...document.querySelectorAll("header *")]
    .map((e) => (e.childElementCount === 0 ? e.textContent.trim() : "")).filter(Boolean);
  return { canvas: r && [r.x, r.y, r.width, r.height], header };
});
let at = null;
for (const index of [0, 1]) {
  await page.goto(%(url)s + "&index=" + index);
  await page.waitForFunction(() => !!document.querySelector("canvas"), undefined, { timeout: 30000 });
  await page.waitForTimeout(2000);
  at = await state();
  if (at.header.includes("Home")) break;
}
const before = at;
const [x, y] = before.canvas;
// the button: board coordinates (50, 300) to (250, 360), the board drawn at 100%%
await page.mouse.click(x + 150, y + 330, { label: "click the prototype button" });
await page.waitForTimeout(2000);
const after = await state();
await page.screenshot({ path: %(shot)s });
console.log("RESULT=" + JSON.stringify({ before: before.header, after: after.header }));
"""


def viewer(space, session):
    file_id, _ = mcpv.create_file("pen17-viewer")
    client = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
    answer = client.execute_code(PROTOTYPE, fileId=file_id, sessionId=session)[0]["result"]
    url = answer["message"].split("The viewer of this page: ")[1]
    # the tabs reach the stack over plain HTTP on the host port
    query = url[url.index("?"):]
    play_url = "http://localhost:3550/" + query
    shot = str((HERE / "../../../../.mcp-verify/shots/pen17-viewer.png").resolve())
    played = observers.marked(observers.ego(PLAY % {"space": space, "url": json.dumps(play_url),
                                                    "shot": json.dumps(shot)}), "RESULT=")
    return {
        "openViewer": answer,
        "played": played,
        "screenshot": shot,
        "ok": answer["code"] == "ui-only" and f"file-id={file_id}" in url
              and "Home" in played["before"] and "Detail" in played["after"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()

    run = dual_run.DualRun(args.space)
    report = {
        "prototype": run.scenario("pen17-prototype", (HERE / "pen17_prototype.js").read_text()),
        "refusals": run.scenario("pen17-refusals", (HERE / "pen17_refusals.js").read_text()),
    }
    try:
        report["viewer"] = viewer(args.space, f"{run.session}-viewer")
    except Exception as error:  # noqa: BLE001
        report["viewer"] = {"ok": False, "crashed": repr(error)[:600]}

    failed = [name for name, check in report.items() if not check.get("ok")]
    print(json.dumps({"failed": failed, "report": report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
