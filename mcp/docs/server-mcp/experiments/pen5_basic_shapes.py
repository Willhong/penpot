#!/usr/bin/env python3
#
# PEN-5: basic shapes (query and shape areas) through MCP with no browser,
# compared with the same code in a browser workspace (dual_run.py).
#
#   python3 -I pen5_basic_shapes.py --space <ego-browser task space>
#
# Scenarios:
#   - pen5_shapes.js: create, set every basic property, clone, remove, read
#     back; the return values and the saved shape maps must be equal, the
#     observer tab must show the server's shapes without a reload and after
#     one;
#   - pen5_refusals.js: invalid values and combinations; the API's answers
#     and the values left behind must be equal.
# Plus, on the server only: a viewer's edit and an edit of a shape on a page
# that is not the open one are refused and change nothing.
#
# Prints a JSON report; exit status 1 when a check fails.

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dual_run  # noqa: E402
import mcp_client  # noqa: E402
import mcpv  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()

    run = dual_run.DualRun(args.space)
    report = {
        "shapes": run.scenario("pen5-shapes", (HERE / "pen5_shapes.js").read_text()),
        "refusals": run.scenario("pen5-refusals", (HERE / "pen5_refusals.js").read_text()),
    }

    # server-only refusals
    file_id, _ = mcpv.create_file("pen5-server-refusals")
    editor = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
    editor.execute_code("const r = penpot.createRectangle(); r.name = 'base'; return r.id;", fileId=file_id,
                        sessionId=run.session)
    before = dual_run.saved_shapes(file_id)
    viewer = mcp_client.Client(mcpv.token("viewer", "mcp"), executor="server")
    try:
        viewer.execute_code("penpot.currentPage.findShapes({ name: 'base' })[0].x = 500; return 1;", fileId=file_id)
        viewer_outcome = "accepted"
    except mcp_client.ToolError as error:
        viewer_outcome = str(error)[:200]
    other_page = editor.execute_code("""
const first = penpot.currentPage;
const second = penpot.createPage();
await penpot.openPage(second);
const there = penpot.createRectangle();
there.name = 'on-second';
await penpot.openPage(first);
try { there.x = 300; return 'accepted'; } catch (e) { return String(e.message || e); }
""", sessionId=run.session)[0]["result"]
    after = dual_run.saved_shapes(file_id)
    report["serverRefusals"] = {
        "viewer": viewer_outcome,
        "otherPage": other_page,
        "baseUnchanged": before.get("page:Page 1/base") == after.get("page:Page 1/base"),
        "otherPageUnchanged": all(shape.get("x") != 300 for key, shape in after.items() if key.endswith("/on-second")),
    }
    report["serverRefusals"]["ok"] = (viewer_outcome.startswith("Tool execution failed: [not-found]")
                                      and other_page != "accepted"
                                      and report["serverRefusals"]["baseUnchanged"]
                                      and report["serverRefusals"]["otherPageUnchanged"])

    failed = [name for name, check in report.items() if not check.get("ok")]
    print(json.dumps({"failed": failed, "report": report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
