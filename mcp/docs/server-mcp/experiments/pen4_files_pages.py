#!/usr/bin/env python3
#
# PEN-4: projects, files, pages and file metadata through MCP with no
# browser, compared with the backend and with a browser workspace.
#
#   python3 -I pen4_files_pages.py --space <ego-browser task space>
#
# Checks:
#   1. browsers closed: listProjects/listFiles match the backend;
#      createProject/createFile/openFile; File.id/name/revn/pages;
#   2. pages: createPage, renames, file/page plugin data and shared plugin
#      data saved as the backend reads them;
#   3. a browser opened afterwards shows the pages; with it open, a page
#      created and renamed through MCP shows up without a reload;
#   4. versions: saveVersion, findVersions, label rename, restore (content
#      and vern), pin of an autosave, remove; validate();
#   5. page removal: the remaining pages, the last-page refusal, and the
#      interactions pointing at a removed page, each compared with the same
#      code run in a browser workspace;
#   6. refusals: viewer edits, outsider and invalid ids, invalid names.
#
# Prints a JSON report; exit status 1 when a check fails.

import argparse
import json
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mcp_client  # noqa: E402
import mcpv  # noqa: E402
import observers  # noqa: E402

# a fresh executor session per run: sessions keep their open file
SESSION = f"pen4-{time.time_ns()}"


class Checks:
    def __init__(self):
        self.report = {}

    def add(self, name, ok, **detail):
        self.report[name] = {"ok": bool(ok), **detail}

    @property
    def failed(self):
        return [name for name, check in self.report.items() if not check["ok"]]


def backend_file(file_id):
    return mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))


def page_names(data):
    return [data["pagesIndex"][page_id]["name"] for page_id in data["pages"]]


def wait_until(predicate, timeout=5.0):
    """Polls until predicate() is truthy; returns (value, seconds)."""
    started = time.monotonic()
    while True:
        value = predicate()
        if value or time.monotonic() - started > timeout:
            return value, round(time.monotonic() - started, 2)
        time.sleep(0.2)


# Removes the second page of a two-page file after making it hold the main of
# a component whose instance lives on the first page; returns what is left.
REMOVE_REFERENCED_PAGE = """
const [first] = penpot.currentFile.pages;
const second = penpot.createPage();
second.name = 'Components';
await penpot.openPage(second);
const rect = penpot.createRectangle();
rect.name = 'main-rect';
const component = penpot.library.local.createComponent([rect]);
component.name = 'Card';
await penpot.openPage(first);
const instance = component.instance();
instance.name = 'card-instance';
second.remove();
const after = penpot.currentPage.findShapes().find((s) => s.name === 'card-instance');
return {
  pages: penpot.currentFile.pages.map((p) => p.name),
  components: penpot.library.local.components.map((c) => c.name),
  instance: after ? { isInstance: after.isComponentInstance(), main: after.isComponentMainInstance() } : null,
  errors: penpot.currentFile.validate().map((e) => e.code),
};
"""

REMOVE_LAST_PAGE = """
try { penpot.currentFile.pages[0].remove(); return { removed: true }; }
catch (e) { return { error: String(e) }; }
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()

    checks = Checks()
    tabs = observers.Tabs(args.space)
    fixtures = mcpv.fixtures()
    team = fixtures["team"]["id"]
    editor = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")

    def run(code, **kwargs):
        return editor.execute_code(code, sessionId=SESSION, **kwargs)[0]

    # 1. browsers closed: discovery and creation
    tabs.blank()
    listed = run(f"return await penpotMgmt.listProjects({{ teamId: '{team}' }});")["result"]
    backend_projects = [p for p in mcpv.rpc_ok("get-projects", {"teamId": team}, mcpv.token("editor"))
                        if not p.get("deletedAt")]
    checks.add("listProjects", sorted(p["id"] for p in listed) == sorted(p["id"] for p in backend_projects),
               mcp=sorted(p["name"] for p in listed), backend=sorted(p["name"] for p in backend_projects))

    created = run(f"""
const project = await penpotMgmt.createProject({{ teamId: '{team}', name: '  PEN-4 project  ' }});
const file = await penpotMgmt.createFile({{ projectId: project.id, name: 'PEN-4 file' }});
const files = await penpotMgmt.listFiles({{ projectId: project.id }});
const before = penpotMgmt.workspace.status;
await penpotMgmt.openFile(file.id, {{ teamId: file.teamId }});
const f = penpot.currentFile;
return {{ project, file, files, before, workspace: penpotMgmt.workspace,
         current: {{ id: f.id, name: f.name, revn: f.revn, pages: f.pages.map((p) => p.name) }} }};
""")["result"]
    file_id = created["file"]["id"]
    backend_files = mcpv.rpc_ok("get-project-files", {"projectId": created["project"]["id"]}, mcpv.token("editor"))
    checks.add("createAndOpen",
               created["project"]["name"] == "PEN-4 project" and created["project"]["fileCount"] == 0
               and [f["id"] for f in created["files"]] == [file_id] == [f["id"] for f in backend_files]
               and created["before"] == "none" and created["workspace"]["status"] == "ready"
               and created["current"]["id"] == file_id and created["current"]["pages"] == ["Page 1"],
               created=created)

    # 2. pages and metadata
    run("""
const file = penpot.currentFile;
file.pages[0].name = 'Cover';
const second = penpot.createPage();
second.name = 'Screens';
file.setPluginData('owner', 'pen4');
file.setSharedPluginData('pen4ns', 'shared', 'yes');
second.setPluginData('kind', 'screens');
return file.pages.map((p) => p.name);
""")
    data = backend_file(file_id)["data"]
    plugin_id = "96dfa740005d8020800755ede24a2bae"
    screens = data["pagesIndex"][data["pages"][1]]
    checks.add("pagesAndMetadata",
               page_names(data) == ["Cover", "Screens"]
               and data["pluginData"].get(plugin_id, {}).get("owner") == "pen4"
               and data["pluginData"].get("pen4ns", {}).get("shared") == "yes"
               and screens.get("pluginData", {}).get(plugin_id, {}).get("kind") == "screens",
               pages=page_names(data), pluginData=data["pluginData"], pagePluginData=screens.get("pluginData"))

    # 3. a new browser sees it; an open one follows without a reload
    tabs.open(file_id)
    opened = {label: tabs.page_names(label) for label in tabs.labels}
    run("""
const p = penpot.createPage();
p.name = 'Live';
penpot.currentFile.pages[1].name = 'Screens v2';
""")
    live, seconds = wait_until(lambda: all(tabs.page_names(label) == ["Cover", "Screens v2", "Live"]
                                           for label in tabs.labels))
    checks.add("browsers", all(names == ["Cover", "Screens"] for names in opened.values()) and live,
               opened=opened, liveWithoutReload=bool(live), liveSeconds=seconds)

    # 4. versions
    versions = run("""
const file = penpot.currentFile;
const v1 = await file.saveVersion('v1');
const rect = penpot.createRectangle();
rect.name = 'after-v1';
const all = await file.findVersions();
const own = all.find((v) => v.label === 'v1');
own.label = 'v1 renamed';
return { saved: { label: v1.label, isAutosave: v1.isAutosave, createdBy: v1.createdBy && v1.createdBy.name,
                  createdAt: v1.createdAt instanceof Date },
         labels: (await file.findVersions()).map((v) => v.label) };
""")["result"]
    tabs_saw_edit, _ = wait_until(
        lambda: all("after-v1" in tabs.shape_names(label) for label in tabs.labels), timeout=15)
    vern_before = backend_file(file_id)["vern"]
    run("""
const v = (await penpot.currentFile.findVersions()).find((v) => v.label === 'v1 renamed');
v.restore();
""")
    # the open tabs get the restore notification and reload the file
    tabs_restored, restore_seconds = wait_until(
        lambda: all("after-v1" not in tabs.shape_names(label) for label in tabs.labels), timeout=15)
    restored = run("return { names: penpot.currentPage.findShapes().map((s) => s.name), "
                   "pages: penpot.currentFile.pages.map((p) => p.name) };")["result"]
    after_restore = backend_file(file_id)
    backend_names = [s["name"] for p in after_restore["data"]["pagesIndex"].values() for s in p["objects"].values()]
    pinned = run("""
const file = penpot.currentFile;
const auto = (await file.findVersions()).find((v) => v.isAutosave);
if (!auto) return { autosave: false };
const pinned = await auto.pin();
const label = pinned.label;
await pinned.remove();
const left = (await file.findVersions()).map((v) => v.label);
return { autosave: true, pinnedIsAutosave: pinned.isAutosave, removed: !left.includes(label), left };
""")["result"]
    validation = run("return penpot.currentFile.validate();")["result"]
    checks.add("versions",
               versions["saved"] == {"label": "v1", "isAutosave": False, "createdBy": "MCPV Editor", "createdAt": True}
               # the label setter saves asynchronously (as in the browser): a later listing has it
               and "v1 renamed" in pinned.get("left", [])
               and "after-v1" not in restored["names"] and "after-v1" not in backend_names
               and after_restore["vern"] != vern_before
               and pinned.get("autosave") and not pinned["pinnedIsAutosave"] and pinned["removed"]
               and validation == [] and tabs_saw_edit and tabs_restored,
               tabsSawEdit=bool(tabs_saw_edit), tabsRestored=bool(tabs_restored), tabsRestoreSeconds=restore_seconds,
               versions=versions, restored=restored, vern=[vern_before, after_restore["vern"]],
               pinned=pinned, validation=validation)

    # 5. page removal, compared with a browser workspace
    server_file, _ = mcpv.create_file("pen4-remove-server")
    browser_file, browser_page = mcpv.create_file("pen4-remove-browser")
    server_removal = run(REMOVE_REFERENCED_PAGE, fileId=server_file)["result"]
    server_last = run(REMOVE_LAST_PAGE)["result"]
    tabs_p2 = observers.Tabs(args.space, labels=("p2",))
    tabs_p2.open(browser_file, browser_page)
    browser_removal = tabs_p2.run_code("p2", REMOVE_REFERENCED_PAGE)
    browser_last = tabs_p2.run_code("p2", REMOVE_LAST_PAGE)
    checks.add("pageRemoval",
               browser_removal.get("ok") and server_removal == browser_removal["result"]
               and browser_last.get("ok") and server_last == browser_last["result"]
               and server_removal["pages"] == ["Page 1"],
               server={"referenced": server_removal, "last": server_last},
               browser={"referenced": browser_removal.get("result"), "last": browser_last.get("result")})

    # 6. refusals
    refusals = {}

    def refused(label, call, target):
        before = backend_file(target)
        try:
            response = call()
            outcome = {"refused": False, "response": json.dumps(response)[:300]}
        except mcp_client.ToolError as error:
            outcome = {"refused": True, "error": str(error)[:220]}
        after = backend_file(target)
        outcome["unchanged"] = before["revn"] == after["revn"] and page_names(before["data"]) == page_names(after["data"])
        refusals[label] = outcome

    viewer = mcp_client.Client(mcpv.token("viewer", "mcp"), executor="server")
    outsider = mcp_client.Client(mcpv.token("outsider", "mcp"), executor="server")
    refused("viewerCreatePage", lambda: viewer.execute_code(
        "const p = penpot.createPage(); p.name = 'by-viewer'; return p.id;", fileId=server_file), server_file)
    refused("viewerRenamePage", lambda: viewer.execute_code(
        "penpot.currentFile.pages[0].name = 'by-viewer'; return 1;", fileId=server_file), server_file)
    refused("outsiderOpen", lambda: outsider.execute_code(
        f"await penpotMgmt.openFile('{server_file}'); return penpot.currentFile.name;"), server_file)
    refused("invalidFileId", lambda: editor.execute_code(
        "await penpotMgmt.openFile('not-a-uuid'); return 1;", sessionId=SESSION), server_file)
    refused("invalidProjectId", lambda: editor.execute_code(
        "return await penpotMgmt.createFile({ projectId: 'nope', name: 'x' });", sessionId=SESSION), server_file)
    refused("emptyName", lambda: editor.execute_code(
        f"return await penpotMgmt.createProject({{ teamId: '{team}', name: '   ' }});", sessionId=SESSION), server_file)
    checks.add("refusals", all(r["refused"] and r["unchanged"] for r in refusals.values()), refusals=refusals)

    print(json.dumps({"fileId": file_id, "failed": checks.failed, "checks": checks.report}, indent=2,
                     ensure_ascii=False))
    sys.exit(1 if checks.failed else 0)


if __name__ == "__main__":
    main()
