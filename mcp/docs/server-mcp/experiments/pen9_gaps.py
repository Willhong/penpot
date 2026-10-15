#!/usr/bin/env python3
#
# PEN-9: Plugin API members no earlier experiment ran on the server
# (`pen9_coverage.py report`), run now.
#
#   python3 -I pen9_gaps.py --space <ego-browser task space>
#
# - core / assets / comments: pen9_gaps_*.js run in a browser workspace
#   (wasm) and on the server; returns and saved shapes (and library assets)
#   must be equal (dual_run.py).
# - imageShape: a legacy `image` shape, which the Plugin API cannot create,
#   is saved through the backend in two files; the same code reads and
#   repaints it in a browser and on the server.
# - users: `currentUser` is the token's owner; `activeUsers` lists the
#   people with the file open, with the zoom their tabs report (D8 (b)).
# - uiOnly: the plugin window members answer `ui-only` (D8 (c)).
# - utils: `penpot.utils` (from the plugins runtime, so not in the browser
#   side of the comparisons) agrees with the shapes' own type and geometry.
# - events: every event subscribes and unsubscribes through `on`/`off` and
#   `penpotMgmt.on`/`off` (also runtime members); a selection change and
#   another session's save reach them. `Penpot` omits `addListener`,
#   `removeListener` and `management`, and so does the server.
# - context: `penpot.version` is what a browser on the same build answers;
#   `penpot.localStorage` refuses, as the MCP plugin has no localstorage
#   permission in a browser either.
# - applyToSelected: a token applies to the session's selection (D8 (a)) and
#   is saved.
#
# Prints a JSON report; exit status 1 when a check fails.

import argparse
import base64
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dual_run  # noqa: E402
import mcp_client  # noqa: E402
import mcpv  # noqa: E402
import observers  # noqa: E402
from pen19_exports import multipart, png  # noqa: E402

PIXELS = png(32, 20, lambda x, y: bytes(((x * 31) % 256, (y * 47) % 256, ((x + y) * 13) % 256)))

# a legacy image shape, built by the backend's own change builder (as e1_server_write.py does)
IMAGE_SHAPE = """
(do
  (require '[app.common.types.shape :as cts]
           '[app.common.files.changes-builder :as pcb]
           '[app.common.transit :as t]
           '[app.common.uuid :as uuid])
  (let [shape   (cts/setup-shape {:type :image :name "legacy image" :x 10 :y 10 :width 32 :height 20
                                  :metadata {:id (uuid/uuid "%(media_id)s") :width 32 :height 20
                                             :mtype "image/png"}})
        changes (-> (pcb/empty-changes)
                    (pcb/with-page-id (uuid/uuid "%(page_id)s"))
                    (pcb/with-objects {})
                    (pcb/add-object shape))]
    (println "@@BEGIN@@" (t/encode-str {:id (uuid/uuid "%(file_id)s")
                                        :session-id (uuid/uuid "%(session_id)s")
                                        :revn 0 :vern 0
                                        :changes (:redo-changes changes)}) "@@END@@")))
"""

IMAGE_CODE = """
const img = penpot.currentPage.findShapes().find((s) => s.type === "image");
if (!img) return "no image shape";
const out = { type: img.type, name: img.name, fills: img.fills.map((f) => [f.fillOpacity ?? null, !!f.fillImage]) };
img.fills = [{ fillColor: "#FF0000", fillOpacity: 0.5 }];
out.after = img.fills.map((f) => [f.fillColor, f.fillOpacity]);
return out;
"""

USERS = """
const me = penpot.currentUser;
return {
  me: [me.id, me.name, typeof me.avatarUrl, typeof me.color, typeof me.sessionId],
  active: penpot.activeUsers.map((u) => [u.id, u.name, u.position ? [typeof u.position.x, typeof u.position.y] : null,
                                         u.zoom ?? null]),
};
"""

UI_ONLY = """
const out = {};
for (const [name, call] of [
  ["size", () => penpot.ui.size],
  ["setSize", () => { penpot.ui.size = { width: 10, height: 10 }; }],
  ["resize", () => penpot.ui.resize(10, 10)],
  ["sendMessage", () => penpot.ui.sendMessage({ a: 1 })],
  ["onMessage", () => penpot.ui.onMessage(() => {})],
]) {
  try {
    out[name] = "accepted " + JSON.stringify(call() ?? null);
  } catch (error) {
    out[name] = String(error.code || "") + " " + String(error.message || error);
  }
}
return out;
"""

UTILS = """
const named = (s, n) => { s.name = n; return s; };
const a = named(penpot.createRectangle(), "a");
const b = named(penpot.createEllipse(), "b");
b.x = 200;
const board = named(penpot.createBoard(), "board");
const g1 = named(penpot.createRectangle(), "g1");
const g2 = named(penpot.createRectangle(), "g2");
const group = named(penpot.group([g1, g2]), "group");
const m1 = named(penpot.createRectangle(), "m1");
const m2 = named(penpot.createEllipse(), "m2");
const mask = named(penpot.group([m1, m2]), "mask");
mask.makeMask();
const b1 = named(penpot.createRectangle(), "b1");
const b2 = named(penpot.createRectangle(), "b2");
const bool = named(penpot.createBoolean("union", [b1, b2]), "bool");
const path = named(penpot.createPath(), "path");
path.d = "M 0 0 L 10 10";
const text = named(penpot.createText("t"), "text");
const svg = penpot.createShapeFromSvg('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="10" cy="10" r="8"/></svg>');
const raw = svg ? [svg, ...(svg.children || [])].find((s) => s.type === "svg-raw") : null;
const chip = named(penpot.createBoard(), "Chip");
const tag = named(penpot.createBoard(), "Tag");
const lib = penpot.library.local;
const ca = lib.createComponent([chip]);
const cb = lib.createComponent([tag]);
const container = penpot.createVariantFromComponents([ca.mainInstance(), cb.mainInstance()]);
await penpot.waitForLayoutUpdate(10000);
const t = penpot.utils.types;
const shapes = [a, b, board, group, mask, bool, path, text].concat(raw ? [raw] : []);
const kinds = shapes.map((s) => [s.name || s.type, [t.isBoard(s), t.isGroup(s), t.isMask(s), t.isBool(s),
  t.isRectangle(s), t.isPath(s), t.isText(s), t.isEllipse(s), t.isSVG(s)],
  [s.type === "board", s.type === "group", s.type === "group" && s.isMask(), s.type === "boolean",
   s.type === "rectangle", s.type === "path", s.type === "text", s.type === "ellipse", s.type === "svg-raw"]]);
const center = penpot.utils.geometry.center([a, b]);
const expected = { x: (Math.min(a.x, b.x) + Math.max(a.x + a.width, b.x + b.width)) / 2,
                   y: (Math.min(a.y, b.y) + Math.max(a.y + a.height, b.y + b.height)) / 2 };
const variant = container.variants.variantComponents()[0];
return { kinds, svgRaw: !!raw, center: [center.x, center.y, expected.x, expected.y],
         variantContainer: [t.isVariantContainer(container), t.isVariantContainer(board)],
         variantComponent: [t.isVariantComponent(variant), t.isVariantComponent(lib.createComponent([named(penpot.createBoard(), "Plain")]))] };
"""

EVENTS = """
const watched = penpot.createRectangle();
watched.name = "watched";
const subscriptions = ["pagechange", "filechange", "selectionchange", "themechange", "shapechange", "contentsave",
  "finish", "workspacechange", "logout"].map((ev) => {
  const id = ev === "shapechange" ? penpot.on(ev, () => {}, { shapeId: watched.id }) : penpot.on(ev, () => {});
  penpot.off(id);
  return [ev, typeof id];
});
const mgmt = penpotMgmt.on("workspacechange", () => {});
penpotMgmt.off(mgmt);
let selections = 0;
const selection = penpot.on("selectionchange", () => selections++);
penpot.selection = [watched];
await new Promise((r) => setTimeout(r, 500));
penpot.off(selection);
storage.heard = 0;
penpot.on("shapechange", () => { storage.heard++; }, { shapeId: watched.id });
// `Penpot` omits these `Context` members (Omit<Context, 'addListener' | 'removeListener' | 'management'>)
return { subscriptions, mgmt: typeof mgmt, selection: selections > 0,
         omitted: [typeof penpot.addListener, typeof penpot.removeListener, typeof penpot.management] };
"""

APPLY_TO_SELECTED = """
const r = penpot.createRectangle();
r.name = "selected";
const set = penpot.library.local.tokens.addSet({ name: "sel", active: true });
const token = set.addToken({ type: "borderRadius", name: "sel.radius", value: "9" });
await penpot.waitForLayoutUpdate(10000);
penpot.selection = [r];
token.applyToSelected(["borderRadiusTopLeft"]);
await penpot.waitForLayoutUpdate(10000);
return [r.borderRadiusTopLeft, Object.keys(r.tokens || {}).sort()];
"""

TAB_ZOOM = """
const s = cljs.core.deref(app.main.store.state);
return cljs.core.get_in(s, cljs.core.vector(cljs.core.keyword("workspace-local"), cljs.core.keyword("zoom")));
"""


class Gaps:
    def __init__(self, space):
        self.space = space
        self.ai = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
        self.session = f"pen9-gaps-{time.time_ns()}"
        self.report = {}

    def run(self, code, **kwargs):
        return self.ai.execute_code(code, sessionId=kwargs.pop("session", self.session), **kwargs)[0]

    def check(self, name, ok, **detail):
        self.report[name] = {"ok": bool(ok), **detail}

    def dual(self):
        run = dual_run.DualRun(self.space, session=f"{self.session}-dual")
        image = base64.b64encode(PIXELS).decode()
        for name, script, kwargs in (("core", "pen9_gaps_core.js", {}),
                                     ("assets", "pen9_gaps_assets.js", {"compare_library": True}),
                                     ("comments", "pen9_gaps_comments.js", {"compare_saved": False})):
            code = (HERE / script).read_text().replace("__PNG_BASE64__", image)
            report = run.scenario(f"pen9-gaps-{name}", code, **kwargs)
            self.report[name] = report

    def image_file(self, label):
        file_id, page_id = mcpv.create_file(f"pen9-gaps-image-{label}")
        status, text = multipart("upload-file-media-object", {"file-id": file_id, "is-local": "true", "name": "legacy"},
                                 {"content": ("legacy.png", "image/png", PIXELS)}, mcpv.token("editor"))
        media = json.loads(text)
        form = IMAGE_SHAPE % {"media_id": media["id"], "page_id": page_id, "file_id": file_id,
                              "session_id": str(uuid.uuid4())}
        form = " ".join(form.split())
        script = ("exec 3<>/dev/tcp/127.0.0.1/6062; "
                  "cat >&3; printf '\\n:repl/quit\\n' >&3; timeout 60 cat <&3")
        out = subprocess.run(["docker", "exec", "-i", "-u", "penpot", mcpv.MAIN, "bash", "-c", script],
                             input=form, capture_output=True, text=True).stdout
        if "@@BEGIN@@" not in out:
            raise RuntimeError("urepl evaluation failed: " + out[-1500:])
        body = out.split("@@BEGIN@@", 1)[1].split("@@END@@", 1)[0].strip()
        request = mcpv.urllib.request.Request(
            f"{mcpv.fixtures()['baseUri']}/api/main/methods/update-file", data=body.encode(), method="POST",
            headers={"content-type": "application/transit+json", "accept": "application/json",
                     "authorization": f"Token {mcpv.token('editor')}"})
        with mcpv.urllib.request.urlopen(request, context=mcpv.CONTEXT, timeout=60) as response:
            saved = response.status
        return file_id, page_id, [status, saved]

    def image_shape(self):
        browser_file, browser_page, browser_setup = self.image_file("browser")
        server_file, _, server_setup = self.image_file("server")
        tabs = observers.Tabs(self.space, labels=("p2",))
        tabs.open(browser_file, browser_page)
        browser = tabs.run_code("p2", IMAGE_CODE, settle=1500)
        server = self.run(IMAGE_CODE, fileId=server_file, session=f"{self.session}-image")
        time.sleep(2)
        saved = {}
        for side, file_id in (("browser", browser_file), ("server", server_file)):
            shapes = dual_run.saved_shapes(file_id)
            image = next((v for k, v in shapes.items() if k.endswith("/legacy image")), {})
            saved[side] = [image.get("type"), [[f.get("fillColor"), f.get("fillOpacity")] for f in image.get("fills") or []]]
        self.check("imageShape",
                   browser.get("ok") and isinstance(server.get("result"), dict)
                   and dual_run.normalize(browser["result"], {}) == dual_run.normalize(server["result"], {})
                   and saved["browser"] == saved["server"] == ["image", [["#ff0000", 0.5]]],
                   setup=[browser_setup, server_setup], browser=browser.get("result") or browser,
                   server=server.get("result"), saved=saved)

    def users(self):
        file_id, page_id = mcpv.create_file("pen9-gaps-users")
        tabs = observers.Tabs(self.space, labels=("p1", "p2"))
        tabs.open(file_id, page_id)
        # the owner's pointer over the canvas, so its presence carries a position
        observers.ego("""
const task = await taskSpace(%d);
const page = task.page("p1");
await page.mouse.move(700, 400, { label: "move over the canvas" });
await page.mouse.move(720, 420, { label: "move over the canvas" });
console.log("RESULT=true");""" % self.space)
        zooms = {label: tabs.evaluate(label, TAB_ZOOM) for label in ("p1", "p2")}
        self.run("return 1;", fileId=file_id, session=f"{self.session}-users")
        time.sleep(1.5)
        result = self.run(USERS, session=f"{self.session}-users")["result"]
        fixtures = mcpv.fixtures()["profiles"]
        owner = next((u for u in result["active"] if u[0] == fixtures["owner"]["id"]), None)
        self.check("users",
                   result["me"][:2] == [fixtures["editor"]["id"], "MCPV Editor"] and result["me"][3] == "string"
                   and owner is not None and owner[3] == zooms["p1"] and owner[2] == ["number", "number"],
                   result=result, tabZooms=zooms)

    def ui_only(self):
        result = self.run(UI_ONLY, session=f"{self.session}-users")["result"]
        self.check("uiOnly", all("ui-only" in v for v in result.values()), result=result)

    def utils(self):
        file_id, _ = mcpv.create_file("pen9-gaps-utils")
        result = self.run(UTILS, fileId=file_id, session=f"{self.session}-utils")["result"]
        center = result["center"]
        self.check("utils",
                   all(answer == truth for _, answer, truth in result["kinds"])
                   and abs(center[0] - center[2]) < 0.01 and abs(center[1] - center[3]) < 0.01
                   and result["variantContainer"] == [True, False] and result["variantComponent"] == [True, False],
                   result=result)

    def events(self):
        file_id, _ = mcpv.create_file("pen9-gaps-events")
        session = f"{self.session}-events"
        result = self.run(EVENTS, fileId=file_id, session=session)["result"]
        # another session saves; the listener the first execution left on `shapechange` hears it
        mcp_client.Client(mcpv.token("editor", "mcp"), executor="server").execute_code(
            "penpot.currentPage.findShapes({ name: 'watched' })[0].x = 321; return 1;",
            fileId=file_id, sessionId=f"{session}-other")
        time.sleep(2)
        heard = self.run("return storage.heard;", session=session)["result"]
        self.check("events",
                   all(e[1] == "symbol" for e in result["subscriptions"])
                   and result["mgmt"] == "symbol" and result["selection"]
                   and result["omitted"] == ["undefined", "undefined", "undefined"] and heard >= 1,
                   result=result, heardOtherSession=heard)

    def context(self):
        result = self.run("""
let storage;
try { penpot.localStorage.setItem("k", "v"); storage = "accepted"; } catch (e) { storage = String(e.message || e); }
return { version: penpot.version, storage };""", session=f"{self.session}-context")["result"]
        # what a browser on the same frontend build answers
        file_id, page_id = mcpv.create_file("pen9-gaps-context")
        tabs = observers.Tabs(self.space, labels=("p2",))
        tabs.open(file_id, page_id)
        browser = tabs.run_code("p2", "return penpot.version;", settle=0).get("result")
        self.check("context", bool(browser) and result["version"] == browser
                   and "Permission allow:localstorage is not granted" in result["storage"],
                   result=result, browserVersion=browser)

    def apply_to_selected(self):
        file_id, _ = mcpv.create_file("pen9-gaps-selected")
        result = self.run(APPLY_TO_SELECTED, fileId=file_id, session=f"{self.session}-selected")
        shapes = dual_run.saved_shapes(file_id)
        saved = next((v for k, v in shapes.items() if k.endswith("/selected")), {})
        self.check("applyToSelected",
                   result["result"][0] == 9 and saved.get("r1") == 9 and "borderRadiusTopLeft" in result["result"][1],
                   result=result["result"], savedRadius=saved.get("r1"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()
    run = Gaps(args.space)
    for step in (run.dual, run.image_shape, run.users, run.ui_only, run.utils, run.events, run.context,
                 run.apply_to_selected):
        try:
            step()
        except Exception as error:  # noqa: BLE001
            run.report[step.__name__] = {"ok": False, "crashed": repr(error)[:800]}
    failed = [name for name, check in run.report.items() if not check.get("ok")]
    print(json.dumps({"failed": failed, "checks": run.report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
