#!/usr/bin/env python3
#
# PEN-11: hierarchy, transforms, paths and booleans through MCP with no
# browser, compared with the same code in a browser workspace (dual_run.py).
#
#   python3 -I pen11_hierarchy.py --space <ego-browser task space>
#
# Scenarios:
#   - pen11_structure.js: group, ungroup, clone, reparent (also into a rotated
#     board), z-order, align, distribute, rotate, flip, constraints, masks,
#     path content, every boolean kind, flatten; the return values and the
#     saved shape maps must be equal, and the observer tab must show the
#     server's shapes without a reload and after one;
#   - pen11_refusals.js: parent cycles, invalid paths, boolean kinds, indices
#     and transforms; the answers and what is left behind must be equal.
# Plus, on the server only: structural edits followed by an error save
# nothing.
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
        "structure": run.scenario("pen11-structure", (HERE / "pen11_structure.js").read_text()),
        "refusals": run.scenario("pen11-refusals", (HERE / "pen11_refusals.js").read_text()),
    }

    # server only: a failure after structural edits saves none of them
    file_id, _ = mcpv.create_file("pen11-all-or-nothing")
    editor = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
    editor.execute_code("""
const b = penpot.createBoard(); b.name = 'b';
for (const n of ['x', 'y']) { const r = penpot.createRectangle(); r.name = n; b.appendChild(r); }
return 1;""", fileId=file_id, sessionId=run.session)
    before = dual_run.saved_shapes(file_id)
    try:
        editor.execute_code("""
const [x, y] = ['x', 'y'].map((n) => penpot.currentPage.findShapes({ name: n })[0]);
const g = penpot.group([x, y]); g.name = 'g';
g.rotate(45);
penpot.createBoolean('union', [penpot.createRectangle(), penpot.createEllipse()]);
throw new Error('stop here');""", sessionId=run.session)
        outcome = "accepted"
    except mcp_client.ToolError as error:
        outcome = str(error)[:200]
    after = dual_run.saved_shapes(file_id)
    tree = editor.execute_code("""
return penpot.currentPage.findShapes({ name: 'b' })[0].children.map((s) => [s.name, s.type, s.rotation]);""",
                               sessionId=run.session)[0]["result"]
    report["allOrNothing"] = {
        "outcome": outcome,
        "savedUnchanged": before == after,
        "sessionTree": tree,
        "ok": "stop here" in outcome and "nothing was saved" in outcome and before == after
              and sorted(t[0] for t in tree) == ["x", "y"] and all(t[2] == 0 for t in tree),
    }

    failed = [name for name, check in report.items() if not check.get("ok")]
    print(json.dumps({"failed": failed, "report": report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
