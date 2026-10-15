#!/usr/bin/env python3
#
# PEN-14: components, copies, variants and libraries through MCP with no
# browser.
#
#   python3 -I pen14_libraries.py --space <ego-browser task space>
#
# - pen14_components.js (dual run with a browser workspace): create, copy,
#   override, propagate main changes, nest, detach, swap, reset, variants,
#   combine, remove a referenced main. Return values and saved shapes must be
#   equal, and the observer tab shows the result without a reload.
# - pen14_refusals.js (dual run): invalid component operations.
# - libraries (server only): a shared library file connected to another file,
#   its component placed there; a change of the library does not touch the
#   copy until it is synced, as in a browser; a library the user may not read
#   cannot be connected, and nothing is saved; removing the library component
#   leaves the copy usable.
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

    # a shared library in the user's team, with one component
    library_id, _ = mcpv.create_file("pen14-library")
    run("""
const b = penpot.createBoard(); b.name = 'LibCard'; b.resize(120, 80);
b.fills = [{ fillColor: '#f08c00', fillOpacity: 1 }];
const c = penpot.library.local.createComponent([b]); c.name = 'LibCard';
await penpot.waitForLayoutUpdate(10000);
return c.id;""", fileId=library_id)
    mcpv.rpc_ok("set-file-shared", {"id": library_id, "isShared": True}, mcpv.token("editor"))

    # a file that uses it
    file_id, _ = mcpv.create_file("pen14-uses-library")
    used = run(f"""
const available = (await penpot.library.availableLibraries()).map((l) => l.id);
const lib = await penpot.library.connectLibrary('{library_id}');
const comp = lib.components.find((c) => c.name === 'LibCard');
const copy = comp.instance(); copy.name = 'lib-copy'; copy.x = 50; copy.y = 50;
await penpot.waitForLayoutUpdate(10000);
return {{ available: available.includes('{library_id}'),
          connected: penpot.library.connected.map((l) => l.id),
          copy: copy.isComponentCopyInstance(), component: copy.component().name,
          fill: copy.fills[0].fillColor }};""", fileId=file_id)
    saved = dual_run.saved_shapes(file_id)
    copy_saved = saved.get("page:Page 1/lib-copy", {})

    # the library changes; the copy keeps its values until a sync, as in a browser
    run("""
const main = penpot.library.local.components.find((c) => c.name === 'LibCard').mainInstance();
main.fills = [{ fillColor: '#2f9e44', fillOpacity: 1 }];
await penpot.waitForLayoutUpdate(10000);
return 1;""", fileId=library_id)
    after_change = run("""
const copy = penpot.currentPage.findShapes({ name: 'lib-copy' })[0];
return { fill: copy.fills[0].fillColor, component: copy.component() && copy.component().name };""", fileId=file_id)

    # a library of another team the user is not in: refused, nothing saved
    outsider = mcpv.token("outsider")
    projects = mcpv.rpc_ok("get-all-projects", {}, outsider)
    outsider_project = next(p for p in projects if p.get("isDefault")) if projects else None
    foreign = mcpv.rpc_ok("create-file", {"name": "pen14-foreign-library", "projectId": outsider_project["id"]}, outsider)
    mcpv.rpc_ok("set-file-shared", {"id": foreign["id"], "isShared": True}, outsider)
    revn_before = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["revn"]
    try:
        run(f"""
const listed = (await penpot.library.availableLibraries()).some((l) => l.id === '{foreign["id"]}');
await penpot.library.connectLibrary('{foreign["id"]}');
return {{ listed }};""", fileId=file_id)
        foreign_outcome = "accepted"
    except mcp_client.ToolError as error:
        foreign_outcome = str(error)[:240]
    revn_after = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["revn"]

    # the library component goes away: the copy stays, with its own shapes, and can still be edited
    run("""
const main = penpot.library.local.components.find((c) => c.name === 'LibCard').mainInstance();
main.remove();
await penpot.waitForLayoutUpdate(10000);
return 1;""", fileId=library_id)
    orphan = run("""
const copy = penpot.currentPage.findShapes({ name: 'lib-copy' })[0];
copy.x = 300;
await penpot.waitForLayoutUpdate(10000);
return { x: copy.x, instance: copy.isComponentInstance() };""", fileId=file_id)

    report = {
        "used": used,
        "savedCopyReferencesLibrary": copy_saved.get("componentFile") == "<id>" and bool(copy_saved.get("componentId")),
        "afterLibraryChange": after_change,
        "foreign": foreign_outcome,
        "foreignSavedNothing": revn_before == revn_after,
        "orphan": orphan,
    }
    report["ok"] = (used["available"] and library_id in used["connected"] and used["copy"]
                    and used["fill"].lower() == "#f08c00"
                    and after_change["fill"].lower() == "#f08c00"
                    and foreign_outcome != "accepted" and revn_before == revn_after
                    and orphan["x"] == 300)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()

    run = dual_run.DualRun(args.space)
    report = {
        "components": run.scenario("pen14-components", (HERE / "pen14_components.js").read_text()),
        "refusals": run.scenario("pen14-refusals", (HERE / "pen14_refusals.js").read_text()),
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
