#!/usr/bin/env python3
#
# PEN-3: a real MCP call saves a rectangle with no browser involved, and
# open browsers show it without a reload.
#
#   python3 -I pen3_vertical_slice.py --space <ego-browser task space>
#
# The task space must hold the two observer tabs of verification-env.md:
# p1 = owner at http://localhost:3550, p2 = editor at http://127.0.0.1:3550.
# The MCP client is the editor with its MCP token and `?executor=server`;
# nobody presses "Connect" in a browser.
#
# Checks, in order:
#   1. observers open: execute_code saves a rectangle; both tabs show it
#      without a reload (timed), the backend re-read matches;
#   2. a reload of the owner tab still shows it;
#   3. observers closed (about:blank): execute_code saves a second
#      rectangle; opening the file afterwards shows both;
#   4. the plugin path has no connected session (no Connect was needed);
#   5. refused requests change nothing (backend revn and shapes the same):
#      bad token, viewer, outsider, unknown file, invalid input, code that
#      throws after editing.
#
# Prints a JSON report; exit status 1 when a check fails.

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mcp_client  # noqa: E402
import mcpv  # noqa: E402

RECT_CODE = """
const rect = penpot.createRectangle();
rect.name = %(name)s;
rect.x = %(x)d;
rect.y = %(y)d;
rect.resize(%(w)d, %(h)d);
rect.fills = [{ fillColor: %(color)s, fillOpacity: 1 }];
return { id: rect.id };
"""


def rect_code(name, x, y, w, h, color):
    return RECT_CODE % {"name": json.dumps(name), "x": x, "y": y, "w": w, "h": h, "color": json.dumps(color)}


def ego(script, timeout=180):
    out = subprocess.run(["ego-browser", "nodejs"], input=script, capture_output=True, text=True,
                         timeout=timeout)
    return out.stdout + out.stderr


def open_tabs(space, url_path):
    """Navigates p1 (owner) and p2 (editor) to the workspace path and waits until it is ready."""
    script = """
const task = await taskSpace(%d);
for (const [label, host] of [["p1", "localhost"], ["p2", "127.0.0.1"]]) {
  const page = task.page(label);
  await page.goto(`http://${host}:3550%s`);
  await page.waitForFunction(() => { try { const s = cljs.core.deref(app.main.store.state);
    return cljs.core.get(s, cljs.core.keyword("workspace-ready")) != null
        && cljs.core.get(s, cljs.core.keyword("current-page-id")) != null; } catch (e) { return false; } },
    undefined, { timeout: 60000 });
}
console.log("TABS-READY");
""" % (space, url_path)
    out = ego(script)
    if "TABS-READY" not in out:
        raise RuntimeError("observer tabs did not open: " + out[-1500:])


def blank_tabs(space):
    out = ego("""
const task = await taskSpace(%d);
for (const label of ["p1", "p2"]) { await task.page(label).goto("about:blank"); }
console.log("TABS-BLANK");
""" % space)
    if "TABS-BLANK" not in out:
        raise RuntimeError("could not blank the tabs: " + out[-1500:])


def tab_shapes(space, label, reload=False):
    """Names of the shapes the tab's workspace state holds for the current page."""
    out = ego("""
const task = await taskSpace(%d);
const page = task.page(%s);
if (%s) {
  await page.reload();
  await page.waitForFunction(() => { try { const s = cljs.core.deref(app.main.store.state);
    return cljs.core.get(s, cljs.core.keyword("workspace-ready")) != null
        && cljs.core.get(s, cljs.core.keyword("current-page-id")) != null; } catch (e) { return false; } },
    undefined, { timeout: 60000 });
}
const names = await page.evaluate(() => {
  const k = cljs.core.keyword;
  const s = cljs.core.deref(app.main.store.state);
  const objects = app.main.data.helpers.lookup_page_objects(s);
  return cljs.core.into_array(cljs.core.map((e) => cljs.core.get(cljs.core.val(e), k("name")), objects));
});
console.log("NAMES=" + JSON.stringify(names));
""" % (space, json.dumps(label), "true" if reload else "false"))
    line = [l for l in out.splitlines() if l.startswith("NAMES=")]
    if not line:
        raise RuntimeError("could not read the tab: " + out[-1500:])
    return json.loads(line[-1][len("NAMES="):])


def observe(space, expect):
    """Starts the observer on p1/p2; returns (process, ready file, report file)."""
    state = mcpv.STATE / "observe"
    state.mkdir(parents=True, exist_ok=True)
    ready = state / f"pen3-ready-{time.time_ns()}"
    options = {"space": space, "expect": expect, "timeout": 20000, "ready": str(ready)}
    script = "globalThis.OBS = " + json.dumps(options) + ";\n" + (HERE / "browser_observe.js").read_text()
    proc = subprocess.Popen(["ego-browser", "nodejs"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    proc.stdin.write(script)
    proc.stdin.close()
    for _ in range(300):
        if ready.exists():
            return proc
        time.sleep(0.1)
    proc.kill()
    raise RuntimeError("observer did not start: " + proc.stdout.read()[-1500:])


def observer_report(proc):
    out = proc.stdout.read()
    proc.wait(timeout=60)
    lines = [l for l in out.splitlines() if l.startswith("{")]
    return json.loads(lines[-1])


def backend_shapes(file_id):
    data = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))
    page_id = data["data"]["pages"][0]
    objects = data["data"]["pagesIndex"][page_id]["objects"]
    return data["revn"], {s["name"]: s for s in objects.values()}


def expect_refused(label, call, file_id, report):
    revn_before, shapes_before = backend_shapes(file_id)
    try:
        response = call()
        outcome = {"refused": False, "response": str(response)[:300]}
    except (mcp_client.ToolError, RuntimeError) as error:
        outcome = {"refused": True, "error": str(error)[:300]}
    revn_after, shapes_after = backend_shapes(file_id)
    outcome["unchanged"] = revn_after == revn_before and set(shapes_after) == set(shapes_before)
    outcome["ok"] = outcome["refused"] and outcome["unchanged"]
    report["refusals"][label] = outcome


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()

    team = mcpv.fixtures()["team"]["id"]
    file_id, page_id = mcpv.create_file("pen3-vertical-slice")
    url_path = f"/#/workspace?team-id={team}&file-id={file_id}&page-id={page_id}"
    editor = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
    report = {"fileId": file_id, "checks": {}, "refusals": {}}

    # 1. observers open
    open_tabs(args.space, url_path)
    proc = observe(args.space, 1)
    started = time.time()
    response, seconds = editor.execute_code(rect_code("pen3-open", 100, 100, 200, 120, "#E8590C"), fileId=file_id)
    ended = time.time()
    seen = observer_report(proc)
    revn, shapes = backend_shapes(file_id)
    rect = shapes.get("pen3-open")
    tabs = {label: [dict(name=s["name"], msAfterResponse=s["seenAt"] - int(ended * 1000),
                         msAfterRequest=s["seenAt"] - int(started * 1000),
                         x=s["x"], y=s["y"], width=s["width"], height=s["height"])
                    for s in tab["newShapes"].values()]
            for label, tab in seen.items()}
    report["checks"]["open"] = {
        "mcpSeconds": round(seconds, 3),
        "commit": response.get("commit"),
        "backendRevn": revn,
        "backend": rect and {"x": rect["selrect"]["x"], "y": rect["selrect"]["y"],
                             "width": rect["selrect"]["width"], "height": rect["selrect"]["height"],
                             "fill": rect["fills"][0]["fillColor"]},
        "tabs": tabs,
        "ok": bool(rect and round(rect["selrect"]["x"]) == 100 and round(rect["selrect"]["width"]) == 200
                   and rect["fills"][0]["fillColor"].upper() == "#E8590C"
                   and all(any(s["name"] == "pen3-open" for s in tab) for tab in tabs.values())
                   and len(tabs) == 2),
    }

    # 2. reload keeps it
    names = tab_shapes(args.space, "p1", reload=True)
    report["checks"]["reload"] = {"names": names, "ok": "pen3-open" in names}

    # 3. observers closed, then opened
    blank_tabs(args.space)
    response, seconds = editor.execute_code(rect_code("pen3-closed", 400, 100, 160, 90, "#1971C2"))
    revn, shapes = backend_shapes(file_id)
    open_tabs(args.space, url_path)
    report["checks"]["closed"] = {
        "mcpSeconds": round(seconds, 3),
        "commit": response.get("commit"),
        "backendRevn": revn,
        "backendHas": "pen3-closed" in shapes,
        "tabs": {label: tab_shapes(args.space, label) for label in ("p1", "p2")},
    }
    report["checks"]["closed"]["ok"] = report["checks"]["closed"]["backendHas"] and all(
        {"pen3-open", "pen3-closed"} <= set(names) for names in report["checks"]["closed"]["tabs"].values())

    # 4. no plugin session was connected
    try:
        mcp_client.Client(mcpv.token("editor", "mcp"), executor="plugin").execute_code("return 1;")
        plugin = {"connected": True}
    except mcp_client.ToolError as error:
        plugin = {"connected": False, "error": str(error)[:200]}
    report["checks"]["noConnect"] = {**plugin, "ok": not plugin["connected"]}

    # 5. refusals change nothing
    good = rect_code("pen3-refused", 700, 100, 50, 50, "#2F9E44")
    expect_refused("badToken", lambda: mcp_client.Client("not-a-token", executor="server")
                   .execute_code(good, fileId=file_id), file_id, report)
    expect_refused("apiTokenInsteadOfMcp", lambda: mcp_client.Client(mcpv.token("editor", "api"), executor="server")
                   .execute_code(good, fileId=file_id), file_id, report)
    expect_refused("viewer", lambda: mcp_client.Client(mcpv.token("viewer", "mcp"), executor="server")
                   .execute_code(good, fileId=file_id), file_id, report)
    expect_refused("outsider", lambda: mcp_client.Client(mcpv.token("outsider", "mcp"), executor="server")
                   .execute_code(good, fileId=file_id), file_id, report)
    expect_refused("unknownFile", lambda: editor.execute_code(good, fileId="00000000-0000-4000-8000-000000000001"),
                   file_id, report)
    expect_refused("invalidInput", lambda: editor.execute_code(
        "const r = penpot.createRectangle(); r.name = 'pen3-invalid'; r.resize(-10, 'x'); return r.id;",
        fileId=file_id), file_id, report)
    expect_refused("throwsAfterEdit", lambda: editor.execute_code(
        "const r = penpot.createRectangle(); r.name = 'pen3-thrown'; throw new Error('boom');",
        fileId=file_id), file_id, report)
    # the session reloaded the file after the failure: the thrown shape is gone there too
    response, _ = editor.execute_code("return penpot.currentPage.findShapes().map((s) => s.name).sort();")
    report["checks"]["sessionAfterFailure"] = {"names": response["result"],
                                               "ok": "pen3-thrown" not in response["result"]}

    failed = [name for name, check in {**report["checks"], **report["refusals"]}.items() if not check["ok"]]
    report["failed"] = failed
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
