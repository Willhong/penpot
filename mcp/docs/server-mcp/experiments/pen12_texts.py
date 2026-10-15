#!/usr/bin/env python3
#
# PEN-12: texts, fonts, range styles and text measurement through MCP with no
# browser, compared with the same code in a browser workspace (dual_run.py).
#
#   python3 -I pen12_texts.py --space <ego-browser task space>
#
# - pen12_text.js (dual run): Latin, Korean, emoji, right-to-left and
#   multi-paragraph texts, every style, ranges, grow types, wrapping, Google
#   fonts. Return values and saved shapes, position data included, must be
#   equal; the observer tab shows them without a reload and after one.
# - pen12_refusals.js (dual run): invalid text values; same answers and same
#   state left behind.
# - noBrowser (server only): the scenario runs while no browser has the file
#   open; the saved texts already have their final size and position data,
#   and a browser opened afterwards neither changes nor saves them again.
# - fontFallback (server only): a text whose font file cannot be had is
#   edited; the commit warns `font-fallback` for it (03-runtime-contract §3).
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

TEXT_STATE = """
const k = cljs.core.keyword;
const s = cljs.core.deref(app.main.store.state);
const objects = app.main.data.helpers.lookup_page_objects(s);
const out = {};
cljs.core.run_BANG_((e) => {
  const o = cljs.core.val(e);
  if (cljs.core._EQ_.call(null, cljs.core.get(o, k("type")), k("text"))) {
    const sr = cljs.core.get(o, k("selrect"));
    out[cljs.core.get(o, k("name"))] = {
      width: Math.round(cljs.core.get(sr, k("width")) * 100) / 100,
      height: Math.round(cljs.core.get(sr, k("height")) * 100) / 100,
      positionData: cljs.core.count(cljs.core.get(o, k("position-data"))),
    };
  }
}, objects);
return out;
"""


def text_shapes(file_id):
    data = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))
    page = data["data"]["pagesIndex"][data["data"]["pages"][0]]
    texts = {o["name"]: o for o in page["objects"].values() if o["type"] == "text"}
    return data["revn"], texts


def no_browser(space, session):
    """Runs the scenario with no browser on the file, then opens one."""
    tabs = observers.Tabs(space, labels=("p1",))
    tabs.blank()
    file_id, page_id = mcpv.create_file("pen12-no-browser")
    client = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
    response, _ = client.execute_code((HERE / "pen12_text.js").read_text(), fileId=file_id, sessionId=session)
    revn, saved = text_shapes(file_id)
    sizes = {name: {"width": round(o["selrect"]["width"], 2), "height": round(o["selrect"]["height"], 2),
                    "positionData": len(o.get("positionData") or [])} for name, o in saved.items()}
    complete = all(s["positionData"] > 0 and s["width"] > 1 and s["height"] > 1 for s in sizes.values())
    tabs.open(file_id, page_id)
    time.sleep(6)
    browser = tabs.evaluate("p1", TEXT_STATE)
    revn_after, saved_after = text_shapes(file_id)
    unchanged = all(saved[name]["selrect"] == saved_after[name]["selrect"]
                    and saved[name].get("positionData") == saved_after[name].get("positionData") for name in saved)
    changes = {name: dual_run.diff(dual_run.normalize(saved[name], {}), dual_run.normalize(saved_after[name], {}))
               for name in saved}
    changes = {name: change for name, change in changes.items() if change}
    browser_same = all(abs(browser[name]["width"] - sizes[name]["width"]) < 0.01
                       and abs(browser[name]["height"] - sizes[name]["height"]) < 0.01 for name in sizes)
    return {
        "ok": complete and revn_after == revn and unchanged and browser_same and response["commit"]["pending"] is None,
        "commit": {k: response["commit"][k] for k in ("revn", "computed", "pending")},
        "savedSizes": sizes,
        "complete": complete,
        "revnBeforeBrowser": revn,
        "revnAfterBrowser": revn_after,
        "savedUnchangedAfterBrowser": unchanged,
        "changedByBrowser": changes,
        "fileId": file_id,
        "browserSeesSameSizes": browser_same,
    }


def font_fallback(session):
    """A text whose font file cannot be had (here a custom font that does not exist, set through the
    backend) is edited on the server: the commit carries a `font-fallback` warning for it."""
    import uuid as uuidlib
    file_id, _ = mcpv.create_file("pen12-font-fallback")
    client = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
    created = client.execute_code("""
const t = penpot.createText("Missing font text"); t.name = 'missing';
await penpot.waitForLayoutUpdate(5000);
return { id: t.id, page: penpot.currentPage.id };""", fileId=file_id, sessionId=session)[0]["result"]
    data = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))
    shape = data["data"]["pagesIndex"][created["page"]]["objects"][created["id"]]
    missing_font = f"custom-{uuidlib.uuid4()}"

    def retarget(node):
        if isinstance(node, dict):
            if "fontId" in node:
                node["fontId"] = missing_font
            for value in node.values():
                retarget(value)
        elif isinstance(node, list):
            for value in node:
                retarget(value)

    content = shape["content"]
    retarget(content)
    mcpv.rpc_ok("update-file", {
        "id": file_id, "sessionId": str(uuidlib.uuid4()), "revn": data["revn"], "vern": data["vern"],
        "changes": [{"type": "mod-obj", "id": created["id"], "pageId": created["page"],
                     "operations": [{"type": "set", "attr": "content", "val": content}]}],
    }, mcpv.token("editor"))
    time.sleep(1)
    edited = client.execute_code("""
const t = penpot.currentPage.findShapes({ name: 'missing' })[0];
t.characters = "Missing font text, edited";
await penpot.waitForLayoutUpdate(10000);
return { fontId: t.fontId, width: t.width };""", sessionId=session)[0]
    warnings = edited["commit"].get("warnings") or []
    return {
        "ok": any(w.get("code") == "font-fallback" and w.get("shapeId") == created["id"]
                  and w.get("fontId") == missing_font for w in warnings) and edited["result"]["width"] > 1,
        "result": edited["result"],
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()

    run = dual_run.DualRun(args.space)
    report = {
        "texts": run.scenario("pen12-texts", (HERE / "pen12_text.js").read_text()),
        "refusals": run.scenario("pen12-refusals", (HERE / "pen12_refusals.js").read_text()),
    }
    try:
        report["noBrowser"] = no_browser(args.space, f"{run.session}-alone")
    except Exception as error:  # noqa: BLE001
        report["noBrowser"] = {"ok": False, "crashed": repr(error)[:600]}
    try:
        report["fontFallback"] = font_fallback(f"{run.session}-fallback")
    except Exception as error:  # noqa: BLE001
        report["fontFallback"] = {"ok": False, "crashed": repr(error)[:600]}

    failed = [name for name, check in report.items() if not check.get("ok")]
    print(json.dumps({"failed": failed, "report": report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
