#!/usr/bin/env python3
#
# PEN-15: library colors, typographies and design tokens through MCP with no
# browser.
#
#   python3 -I pen15_assets.py --space <ego-browser task space>
#
# - pen15_assets.js (dual run with a browser workspace): colors, typographies
#   and tokens created, edited, applied, replaced and propagated. Return
#   values, saved shapes and the saved library assets must be equal.
# - pen15_refusals.js (dual run): invalid values, alias cycles, missing
#   references.
# - libraries (server only): colors and typographies of a connected library
#   applied in another file; that library is read-only from there; a viewer
#   cannot change assets; nothing is saved by a refused change.
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


def libraries(session):
    editor = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
    run = lambda code, **kw: editor.execute_code(code, sessionId=session, **kw)[0]["result"]  # noqa: E731

    library_id, _ = mcpv.create_file("pen15-library")
    run("""
const c = penpot.library.local.createColor(); c.name = 'Shared'; c.color = '#0C8599';
const t = penpot.library.local.createTypography(); t.name = 'SharedType'; t.fontSize = '24';
return 1;""", fileId=library_id)
    mcpv.rpc_ok("set-file-shared", {"id": library_id, "isShared": True}, mcpv.token("editor"))

    file_id, _ = mcpv.create_file("pen15-uses-library")
    used = run(f"""
const lib = await penpot.library.connectLibrary('{library_id}');
const shared = lib.colors.find((c) => c.name === 'Shared');
const sharedType = lib.typographies.find((t) => t.name === 'SharedType');
const r = penpot.createRectangle(); r.name = 'uses-shared';
r.fills = [shared.asFill()];
const text = penpot.createText('Shared typography'); text.name = 'uses-type';
await penpot.waitForLayoutUpdate(10000);
sharedType.applyToText(text);
await penpot.waitForLayoutUpdate(10000);
const attempt = (fn) => {{ try {{ fn(); return 'accepted'; }} catch (e) {{ return String(e.message || e); }} }};
return {{
  fill: r.fills[0].fillColor, refFile: r.fills[0].fillColorRefFile === '{library_id}',
  fontSize: text.fontSize,
  editShared: attempt(() => {{ shared.color = '#000000'; }}),
  createInShared: attempt(() => lib.createColor()),
  sharedAfter: lib.colors.map((c) => [c.name, c.color]),
}};""", fileId=file_id)
    library_after = run("return penpot.library.local.colors.map((c) => [c.name, c.color]);", fileId=library_id)

    # a viewer cannot change the assets of a file
    revn_before = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["revn"]
    viewer = mcp_client.Client(mcpv.token("viewer", "mcp"), executor="server")
    try:
        viewer.execute_code("const c = penpot.library.local.createColor(); c.name = 'ByViewer'; c.color = '#123456'; "
                            "penpot.library.local.tokens.addSet({ name: 'viewer-set' }); return 1;",
                            fileId=file_id, sessionId=f"{session}-viewer")
        viewer_outcome = "accepted"
    except mcp_client.ToolError as error:
        viewer_outcome = str(error)[:240]
    revn_after = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["revn"]

    report = {"used": used, "libraryAfter": library_after, "viewer": viewer_outcome,
              "viewerSavedNothing": revn_before == revn_after}
    report["ok"] = (used["fill"].upper() == "#0C8599" and used["refFile"] and used["fontSize"] == "24"
                    and used["editShared"] != "accepted" and used["createInShared"] != "accepted"
                    and ["Shared", "#0C8599"] in [[n, c.upper()] for n, c in library_after]
                    and viewer_outcome != "accepted" and revn_before == revn_after)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()

    run = dual_run.DualRun(args.space)
    report = {
        "assets": run.scenario("pen15-assets", (HERE / "pen15_assets.js").read_text(), compare_library=True),
        "refusals": run.scenario("pen15-refusals", (HERE / "pen15_refusals.js").read_text(), compare_library=True),
    }
    try:
        report["libraries"] = libraries(f"{run.session}-libraries")
    except Exception as error:  # noqa: BLE001
        report["libraries"] = {"ok": False, "crashed": repr(error)[:800]}

    failed = [name for name, check in report.items() if not check.get("ok")]
    print(json.dumps({"failed": failed, "report": report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
