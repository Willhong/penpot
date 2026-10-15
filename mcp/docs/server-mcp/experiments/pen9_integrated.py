#!/usr/bin/env python3
#
# PEN-9: the server MCP as a whole, on one build.
#
#   python3 -I pen9_integrated.py --space <ego-browser task space>
#
# - crossFeature: pen9_integrated.js (tokens, library assets, a variant
#   component, text in nested flex and grid layouts, an image fill, a
#   boolean, a prototype link, then token, main component and variant
#   changes) runs in a browser workspace (wasm) and on the server; returns,
#   saved shapes and library assets must be equal. Then the card is exported
#   on both sides: PNG against the browser's CPU raster (03 §6, D15); PDF
#   drawn to pixels by poppler against the same tolerance, with equal text.
# - textExports: the card's SVG export and generated HTML/CSS must be equal
#   once links and ids are normalized (03 §6). Also reports whether they are
#   equal once @font-face rules are sorted and numbers rounded to 2
#   decimals, the shape map rule (a user decision, not counted as passed).
# - pluginPath: the existing browser path still works: the editor's tab
#   connects the MCP plugin from its MCP menu, `executor=plugin` runs in that
#   tab and the browser saves; a server execution on the same file at the
#   same time is kept too. Disconnecting ends the plugin path.
# - browserless: with every observer tab blank, the plugin path has no
#   session, and the server path creates, changes, reads, exports and undoes
#   the same design. Meanwhile the main container's process list is sampled:
#   it must never hold a browser process (D10).
# - lateOpen / live / reconnect / refresh / mcpRestart: tabs that open the
#   file afterwards, that stay open while the AI edits, that lose their
#   notification socket, that reload, and an MCP server restart all end with
#   what the backend saved.
# - robustness: on the same file, a repeated requestId, an unread answer, a
#   cancelled job, a revoked edit right, a failure half way, too many
#   changes (D9) and a human editing at the same time.
# - svgRenderer (D13, a measurement): the owner's tab switched to the svg
#   renderer opens the file; reports whether it measures the server's texts
#   otherwise and saves new sizes. The renderer is switched back afterwards.
#
# Prints a JSON report; exit status 1 when a check fails. A check that
# cannot run counts as failed, not passed.

import argparse
import base64
import http.client
import json
import math
import re
import sys
import threading
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dual_run  # noqa: E402
import mcp_client  # noqa: E402
import mcpv  # noqa: E402
import observers  # noqa: E402
from pen19_exports import BROWSER_CPU, normalize_links, png, squash  # noqa: E402
from pen6_consistency import restart_mcp  # noqa: E402

OUT = mcpv.STATE / "pen9" / "integrated"
CONTAINER_OUT = "/home/penpot/penpot/.mcp-verify/pen9/integrated"
TOLERANCE = 0.001
BROWSER_PROCESS = re.compile(r"chrom|headless_shell|playwright|firefox|webkit|msedge", re.I)

IMAGE = base64.b64encode(png(32, 20, lambda x, y: bytes(((x * 29) % 256, (y * 61) % 256,
                                                         ((x * y) * 7) % 256)))).decode()
SCENARIO = (HERE / "pen9_integrated.js").read_text().replace("__PNG_BASE64__", IMAGE)

# the card's outputs, read the same way on both sides
EXPORT = """
const b64 = (bytes) => {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  let out = "";
  for (let i = 0; i < bytes.length; i += 3) {
    const [a, b, c] = [bytes[i], bytes[i + 1], bytes[i + 2]];
    const n = (a << 16) | ((b ?? 0) << 8) | (c ?? 0);
    out += alphabet[(n >> 18) & 63] + alphabet[(n >> 12) & 63];
    out += b === undefined ? "=" : alphabet[(n >> 6) & 63];
    out += c === undefined ? "=" : alphabet[n & 63];
  }
  return out;
};
const card = penpot.currentPage.findShapes({ name: "card" })[0];
return {
  id: card.id,
  png: b64(await card.export({ type: "png", scale: 1 })),
  svg: b64(await card.export({ type: "svg" })),
  pdf: b64(await card.export({ type: "pdf" })),
  html: penpot.generateMarkup([card], { type: "html" }),
  css: penpot.generateStyle([card], { type: "css", withChildren: true }),
};
"""

# what a tab's workspace holds for the first page: one row per shape
TAB_STATE = """
const k = cljs.core.keyword, get = cljs.core.get;
const s = cljs.core.deref(app.main.store.state);
const objects = app.main.data.helpers.lookup_page_objects(s);
const arr = (v) => (v ? cljs.core.into_array(v) : []);
const name = (id) => { const o = get(objects, id); return o ? get(o, k("name")) : null; };
const texts = (node, acc) => {
  if (!node) return acc;
  const tx = get(node, k("text"));
  if (tx != null) acc.push(tx);
  arr(get(node, k("children"))).forEach((c) => texts(c, acc));
  return acc;
};
const fill = (f) => get(f, k("fill-color")) ? String(get(f, k("fill-color"))).toLowerCase()
  : get(f, k("fill-image")) ? "image:" + String(get(get(f, k("fill-image")), k("id")))
  : get(f, k("fill-color-gradient")) ? "gradient" : null;
const out = [];
arr(cljs.core.vals(objects)).forEach((o) => {
  const sr = get(o, k("selrect"));
  out.push([name(get(o, k("parent-id"))) + "/" + get(o, k("name")),
            ...["x", "y", "width", "height"].map((f) => Math.round(get(sr, k(f)) * 100) / 100),
            arr(get(o, k("fills"))).map(fill).join(","),
            texts(get(o, k("content")), []).join(""),
            get(o, k("component-id")) ? String(get(o, k("component-id"))) : null]);
});
return out.sort();
"""


def saved_rows(file_id):
    """What the backend saved for the first page, in the rows of TAB_STATE."""
    data = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["data"]
    objects = data["pagesIndex"][data["pages"][0]]["objects"]

    def texts(node, acc):
        if not isinstance(node, dict):
            return acc
        if node.get("text") is not None:
            acc.append(node["text"])
        for child in node.get("children") or []:
            texts(child, acc)
        return acc

    def fill(f):
        if f.get("fillColor"):
            return f["fillColor"].lower()
        if f.get("fillImage"):
            return "image:" + f["fillImage"]["id"]
        return "gradient" if f.get("fillColorGradient") else None

    def js_round(n):
        # as TAB_STATE's Math.round(n * 100) / 100, which rounds halves up, and prints whole numbers bare
        value = math.floor(n * 100 + 0.5) / 100
        return int(value) if value == int(value) else value

    rows = []
    for o in objects.values():
        parent = objects.get(o.get("parentId"), {}).get("name")
        sr = o["selrect"]
        rows.append([f"{parent}/{o['name']}", *[js_round(sr[f]) for f in ("x", "y", "width", "height")],
                     # Array.join writes null as nothing
                     ",".join(fill(f) or "" for f in o.get("fills") or []),
                     "".join(texts(o.get("content"), [])), o.get("componentId")])
    return canonical(rows)


def canonical(rows):
    """Rows in one order whatever produced them (JS sorts arrays by their string form)."""
    return sorted(rows, key=lambda row: json.dumps(row))


def row_diff(a, b):
    sa, sb = {json.dumps(r) for r in a}, {json.dumps(r) for r in b}
    return {"onlyTab": sorted(sa - sb)[:5], "onlyBackend": sorted(sb - sa)[:5]}


def sorted_faces(text):
    """The text with its @font-face rules in sorted order."""
    faces = re.findall(r"@font-face\s*\{[^}]*\}", text)
    rest = re.sub(r"@font-face\s*\{[^}]*\}", "\0", text)
    for face in sorted(faces):
        rest = rest.replace("\0", face, 1)
    return rest


def rounded_numbers(text):
    """The text with every number written with 2 decimals."""
    return re.sub(r"-?\d+(?:\.\d+)?", lambda m: f"{round(float(m.group(0)), 2):.2f}", text)


def pdf_compare():
    """The two card PDFs drawn to pixels by poppler (same tolerance as rasters) and their text."""
    code, out, err = mcpv.container(
        f"cd {CONTAINER_OUT} && pdftoppm -r 144 -png -singlefile server-card.pdf pdf-server"
        f" && pdftoppm -r 144 -png -singlefile browser-card.pdf pdf-browser"
        f" && pdftotext server-card.pdf server-card.txt && pdftotext browser-card.pdf browser-card.txt")
    if code != 0:
        return {"ok": False, "error": err[-300:]}
    pixels = pixel_diff("pdf-server.png", "pdf-browser.png")
    same_text = (OUT / "server-card.txt").read_text() == (OUT / "browser-card.txt").read_text()
    return {"ok": pixels.get("sameSize") and pixels.get("ratio", 1) <= TOLERANCE and same_text,
            "pixels": pixels, "sameText": same_text}


def wait_until(predicate, timeout=10.0):
    started = time.monotonic()
    while True:
        value = predicate()
        if value or time.monotonic() - started > timeout:
            return value, round(time.monotonic() - started, 2)
        time.sleep(0.3)


def pixel_diff(a, b):
    code, out, err = mcpv.container(f"node /home/penpot/penpot/mcp/docs/server-mcp/experiments/pixel_diff.mjs "
                                    f"{CONTAINER_OUT}/{a} {CONTAINER_OUT}/{b}")
    return json.loads(out) if code == 0 else {"error": err[-300:]}


class ProcessWatch:
    """Samples the main container's process list until stopped; remembers every browser-like process and
    the most executor processes seen at once."""

    def __init__(self):
        self.browsers, self.executors, self.samples = set(), 0, 0
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True)

    def loop(self):
        while not self.stopped.is_set():
            code, out, _ = mcpv.container("ps -eo pid,args --no-headers", timeout=30)
            if code == 0:
                self.samples += 1
                lines = out.splitlines()
                self.browsers |= {l.strip()[:160] for l in lines if BROWSER_PROCESS.search(l)}
                self.executors = max(self.executors, sum(1 for l in lines if "executor-child.js" in l))
            self.stopped.wait(0.5)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stopped.set()
        self.thread.join(timeout=30)

    def report(self):
        return {"samples": self.samples, "browserProcesses": sorted(self.browsers),
                "maxExecutorProcesses": self.executors}


class Pen9:
    def __init__(self, space):
        self.space = space
        self.tabs = observers.Tabs(space, labels=("p1", "p2"))
        self.ai = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
        self.session = f"pen9-{time.time_ns()}"
        self.report = {}
        OUT.mkdir(parents=True, exist_ok=True)

    def run(self, code, session=None, client=None, **kwargs):
        return (client or self.ai).execute_code(code, sessionId=session or self.session, **kwargs)[0]

    def check(self, name, ok, **detail):
        self.report[name] = {"ok": bool(ok), **detail}

    def tab_matches(self, labels, file_id, timeout=15, reload=False):
        """Whether every tab holds what the backend saved, and how long it took."""
        expected = saved_rows(file_id)
        out = {}
        for label in labels:
            first = canonical(self.tabs.evaluate(label, TAB_STATE, reload=reload))
            if first == expected:
                out[label] = {"ok": True, "seconds": 0}
                continue
            seen, seconds = wait_until(lambda: canonical(self.tabs.evaluate(label, TAB_STATE)) == expected, timeout)
            out[label] = {"ok": bool(seen), "seconds": seconds}
            if not seen:
                out[label]["diff"] = row_diff(self.tabs.evaluate(label, TAB_STATE), expected)
        return out

    # --- checks

    def cross_feature(self):
        run = dual_run.DualRun(self.space, session=f"{self.session}-dual")
        scenario = run.scenario("pen9-integrated", SCENARIO, compare_library=True)
        report = {"scenario": scenario}
        ok = scenario.get("ok")
        if scenario.get("browserOk") and scenario.get("serverOk"):
            waits = [w for w in (scenario.get("commit") or {}).get("warnings") or []]
            server = self.run(EXPORT, fileId=scenario["serverFile"], session=f"{self.session}-export")["result"]
            browser = run.browser.run_code("p2", EXPORT, settle=300)["result"]
            cpu = self.tabs.evaluate("p2", BROWSER_CPU % json.dumps({"card.png": [browser["id"], 1, 0]}))
            for side, data in (("server", server["png"]), ("gpu", browser["png"]), ("cpu", cpu["card.png"])):
                (OUT / f"{side}-card.png").write_bytes(base64.b64decode(data))
            same = pixel_diff("server-card.png", "cpu-card.png")
            renderer = pixel_diff("server-card.png", "gpu-card.png")
            for side, data in (("server", server["pdf"]), ("browser", browser["pdf"])):
                (OUT / f"{side}-card.pdf").write_bytes(base64.b64decode(data))
            exports = {
                "png": {"ok": same.get("sameSize") and same.get("ratio", 1) <= TOLERANCE
                              and renderer.get("sameSize"), "browserCpu": same, "browserGpu": renderer},
                "pdf": pdf_compare(),
            }
            report.update(exports=exports, warnings=waits)
            ok = ok and all(e["ok"] for e in exports.values())
            self.text_exports(server, browser)
        self.report["crossFeature"] = {"ok": bool(ok), **report}

    def text_exports(self, server, browser):
        out = {}
        for key, get in (("svg", lambda x: base64.b64decode(x["svg"]).decode()), ("html", lambda x: x["html"]),
                         ("css", lambda x: x["css"])):
            a, b = squash(normalize_links(get(server))), squash(normalize_links(get(browser)))
            out[key] = {"equal": a == b,
                        "equalSortedFacesRounded": rounded_numbers(sorted_faces(a)) == rounded_numbers(sorted_faces(b))}
        self.report["textExports"] = {"ok": all(v["equal"] for v in out.values()), **out}

    def toggle_plugin(self, label):
        """Clicks the MCP plugin item of the tab's MCP menu (connect or disconnect); returns its label."""
        script = """
const task = await taskSpace(%d);
const page = task.page(%s);
await page.evaluate(() => document.querySelector("#left-sidebar-aside button").setAttribute("data-pen9", "menu"));
await page.click("loc=css:[data-pen9='menu']", { label: "open main menu" });
await page.waitForSelector("loc=css:#file-menu-mcp", { state: "visible", timeout: 5000 });
await page.hover("loc=css:#file-menu-mcp", { label: "open MCP menu" });
await page.waitForSelector("loc=css:#mcp-menu-toggle-mcp-plugin", { state: "visible", timeout: 5000 });
const text = await page.evaluate(() => document.querySelector("#mcp-menu-toggle-mcp-plugin").textContent.trim());
await page.click("loc=css:#mcp-menu-toggle-mcp-plugin", { label: "toggle MCP plugin" });
await page.waitForTimeout(1000);
console.log("RESULT=" + JSON.stringify(text));
""" % (self.space, json.dumps(label))
        return observers.marked(observers.ego(script), "RESULT=")

    def plugin_path(self):
        file_id, page_id = mcpv.create_file("pen9-plugin-path")
        self.tabs.open(file_id, page_id)
        connect_label = self.toggle_plugin("p2")
        plugin = mcp_client.Client(mcpv.token("editor", "mcp"), executor="plugin")
        code = "const r = penpot.createRectangle(); r.name = 'plugin-rect'; r.x = 40; return r.id;"
        answer = {}

        def plugin_ran():
            try:
                answer["value"] = plugin.execute_code(code)[0]
                return True
            except Exception as error:  # noqa: BLE001
                answer["error"] = str(error)[:200]
                return False

        ran, seconds = wait_until(plugin_ran, 30)
        server = self.run("const r = penpot.createEllipse(); r.name = 'server-ellipse'; return r.id;",
                          fileId=file_id, session=f"{self.session}-coexist")
        names = lambda: sorted(r[0].split("/", 1)[1] for r in saved_rows(file_id))  # noqa: E731
        saved, saved_s = wait_until(lambda: {"plugin-rect", "server-ellipse"} <= set(names()), 15)
        matches = self.tab_matches(("p1", "p2"), file_id)
        disconnect_label = self.toggle_plugin("p2")
        time.sleep(2)
        try:
            plugin.execute_code("return 1;")
            after = "ran"
        except Exception as error:  # noqa: BLE001
            after = str(error)[:200]
        self.check("pluginPath",
                   ran and bool(saved) and server["commit"]["saved"] and all(v["ok"] for v in matches.values())
                   and after != "ran",
                   menu=[connect_label, disconnect_label], connectSeconds=seconds, pluginAnswer=answer,
                   bothSavedSeconds=saved_s, tabs=matches, afterDisconnect=after)

    def browserless(self):
        self.tabs.blank()
        try:
            mcp_client.Client(mcpv.token("editor", "mcp"), executor="plugin").execute_code("return 1;")
            plugin = "ran"
        except Exception as error:  # noqa: BLE001
            plugin = str(error)[:200]
        self.file_id, self.page_id = mcpv.create_file("pen9-browserless")
        steps = {}
        with ProcessWatch() as watch:
            created = self.run(SCENARIO, fileId=self.file_id)
            steps["create"] = {"saved": created["commit"]["saved"], "changes": created["commit"].get("changes"),
                               "waits": [w for w in created["result"]["waits"] if w[1] != "ok"]}
            before_change = saved_rows(self.file_id)
            changed = self.run("""
const lib = penpot.library.local;
const card = penpot.currentPage.findShapes({ name: "card" })[0];
const title = card.children.find((c) => c.name === "title");
title.characters = "Changed on the server 서버에서 바꾼 제목입니다";
lib.tokens.sets[0].tokens.find((t) => t.name === "color.primary").value = "#E8590C";
await penpot.waitForLayoutUpdate(10000);
return { title: [title.width, title.height], card: [card.width, card.height] };""")
            steps["change"] = {"saved": changed["commit"]["saved"], "result": changed["result"]}
            after_change = saved_rows(self.file_id)
            read = self.run("""
const card = penpot.currentPage.findShapes({ name: "card" })[0];
return { title: card.children.find((c) => c.name === "title").characters,
         cta: penpot.currentPage.findShapes({ name: "cta" })[0].fills[0].fillColor,
         height: card.height };""", session=f"{self.session}-reader", fileId=self.file_id)["result"]
            steps["read"] = read
            exported = self.run(EXPORT)["result"]
            png_bytes = base64.b64decode(exported["png"])
            steps["export"] = {"png": png_bytes[:8] == b"\x89PNG\r\n\x1a\n",
                               "size": list(int.from_bytes(png_bytes[o:o + 4], "big") for o in (16, 20)),
                               "pdf": base64.b64decode(exported["pdf"])[:5] == b"%PDF-"}
            undone_text, _ = self.ai.tool("undo", sessionId=self.session)
            steps["undo"] = json.loads(undone_text)
            after_undo = saved_rows(self.file_id)
        title_row = next((r for r in after_change if r[0] == "card/title"), None)
        self.check(
            "browserless",
            plugin != "ran" and not watch.browsers and watch.samples > 3 and watch.executors >= 1
            and steps["create"]["saved"] and not steps["create"]["waits"] and steps["change"]["saved"]
            and before_change != after_change and title_row and "서버에서 바꾼" in title_row[6]
            and read["title"].startswith("Changed on the server") and read["cta"].lower() == "#e8590c"
            and steps["export"]["png"] and steps["export"]["pdf"]
            and after_undo == before_change,
            pluginPath=plugin, processes=watch.report(), steps=steps,
            undoRestored=after_undo == before_change)

    def late_open(self):
        self.tabs.open(self.file_id, self.page_id)
        matches = self.tab_matches(("p1", "p2"), self.file_id)
        self.check("lateOpen", all(v["ok"] for v in matches.values()), tabs=matches)

    def live(self):
        started = time.monotonic()
        self.run("""
penpot.library.local.tokens.sets[0].tokens.find((t) => t.name === "space.base").value = "4";
const copy = penpot.currentPage.findShapes({ name: "copy-2" })[0];
copy.switchVariant(0, "small");
await penpot.waitForLayoutUpdate(10000);
return 1;""")
        matches = self.tab_matches(("p1", "p2"), self.file_id)
        self.check("live", all(v["ok"] for v in matches.values()), tabs=matches,
                   secondsFromRequest=round(time.monotonic() - started, 2))

    def reconnect(self):
        self.tabs.open_droppable("p1", self.file_id, self.page_id)
        dropped = self.tabs.drop_notifications("p1")
        self.run("const r = penpot.createRectangle(); r.name = 'while-away-1'; return 1;")
        self.run("""
const card = penpot.currentPage.findShapes({ name: "card" })[0];
card.children.find((c) => c.name === "photo").resize(288, 90);
await penpot.waitForLayoutUpdate(10000);
return 1;""")
        matches = self.tab_matches(("p1",), self.file_id, timeout=30)
        self.check("reconnect", dropped >= 1 and matches["p1"]["ok"], dropped=dropped, tabs=matches)
        self.tabs.open(self.file_id, self.page_id)

    def refresh(self):
        matches = self.tab_matches(("p1", "p2"), self.file_id, reload=True)
        self.check("refresh", all(v["ok"] for v in matches.values()), tabs=matches)

    def mcp_restart(self):
        before = saved_rows(self.file_id)
        restart_mcp(signal="TERM")
        self.ai = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
        read = self.run("return penpot.currentPage.findShapes().map((s) => s.name).sort();",
                        session=f"{self.session}-after-restart", fileId=self.file_id)["result"]
        same_backend = saved_rows(self.file_id) == before
        # findShapes includes the root frame
        names = sorted(r[0].split("/", 1)[1] for r in before)
        edited = self.run("""
const card = penpot.currentPage.findShapes({ name: "card" })[0];
card.children.find((c) => c.name === "title").characters = "After the restart 재시작 뒤";
await penpot.waitForLayoutUpdate(10000);
return 1;""", session=f"{self.session}-after-restart")
        matches = self.tab_matches(("p1", "p2"), self.file_id)
        self.check("mcpRestart",
                   same_backend and read == names and edited["commit"]["saved"]
                   and all(v["ok"] for v in matches.values()),
                   sameBackend=same_backend, readMatches=read == names, tabs=matches)

    def robustness(self):
        file_id, session = self.file_id, f"{self.session}-after-restart"
        state = lambda: (mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["revn"],  # noqa: E731
                         saved_rows(file_id))
        out = {}

        # the same requestId twice
        code = "const r = penpot.createEllipse(); r.name = 'once-only'; return r.id;"
        first = self.run(code, session=session, requestId=f"{session}-dup")
        second = self.run(code, session=session, requestId=f"{session}-dup")
        count = sum(1 for r in saved_rows(file_id) if r[0].endswith("/once-only"))
        out["duplicate"] = {"ok": second.get("replayed") is True and first["result"] == second["result"]
                                  and count == 1, "copies": count}

        # the server saves, the client never reads the answer; the retry returns the recorded result
        code = "const r = penpot.createEllipse(); r.name = 'unread'; return r.id;"
        connection = http.client.HTTPConnection("localhost", 4501, timeout=30)
        body = {"jsonrpc": "2.0", "id": 99, "method": "tools/call",
                "params": {"name": "execute_code",
                           "arguments": {"code": code, "sessionId": session, "requestId": f"{session}-unread"}}}
        connection.request("POST", self.ai.url.replace("http://localhost:4501", ""), body=json.dumps(body),
                           headers={"content-type": "application/json",
                                    "accept": "application/json, text/event-stream"})
        time.sleep(4)
        connection.close()
        retry = self.run(code, session=session, requestId=f"{session}-unread")
        count = sum(1 for r in saved_rows(file_id) if r[0].endswith("/unread"))
        out["unreadAnswer"] = {"ok": retry.get("replayed") is True and count == 1, "copies": count}

        # a job cancelled while it runs
        before = state()
        job = json.loads(self.ai.tool("execute_code", sessionId=session, **{"async": True}, code=(
            "penpot.currentPage.findShapes({ name: 'card' })[0].resize(500, 500); "
            "await new Promise((r) => setTimeout(r, 6000)); return 1;"))[0])
        time.sleep(1)
        self.ai.tool("execution_job", jobId=job["jobId"], cancel=True)
        view, _ = wait_until(lambda: (lambda v: v if v["status"] in ("done", "error", "cancelled") else None)(
            json.loads(self.ai.tool("execution_job", jobId=job["jobId"])[0])), 20)
        out["cancel"] = {"ok": bool(view) and view["status"] == "cancelled" and state() == before,
                         "status": view and view["status"]}

        # edit right revoked
        fixtures = mcpv.fixtures()
        team, editor_id = fixtures["team"]["id"], fixtures["profiles"]["editor"]["id"]
        set_role = lambda role: mcpv.rpc_ok("update-team-member-role",  # noqa: E731
                                            {"teamId": team, "memberId": editor_id, "role": role},
                                            mcpv.token("owner"))
        before = state()
        set_role("viewer")
        try:
            time.sleep(1)
            try:
                self.run("penpot.currentPage.findShapes({ name: 'badge' })[0].x = 5; return 1;", session=session)
                revoked = "accepted"
            except mcp_client.ToolError as error:
                revoked = str(error)[:200]
            after = state()
        finally:
            set_role("editor")
        out["revoked"] = {"ok": revoked.startswith("Tool execution failed: [not-found]") and after == before,
                          "answer": revoked}

        # a failure half way through a cross-feature change
        before = state()
        try:
            self.run("""
penpot.library.local.tokens.sets[0].tokens.find((t) => t.name === "color.primary").value = "#000000";
penpot.currentPage.findShapes({ name: "copy-1" })[0].switchVariant(0, "small");
penpot.currentPage.findShapes({ name: "card" })[0].children.find((c) => c.name === "title").characters = "half";
await penpot.waitForLayoutUpdate(10000);
throw new Error("stop half way");""", session=session)
            partial = "accepted"
        except mcp_client.ToolError as error:
            partial = str(error)[:200]
        out["partialFailure"] = {"ok": "stop half way" in partial and state() == before, "answer": partial}

        # more changes than one save may hold (D9)
        before = state()
        try:
            self.run("for (let i = 0; i < 3000; i++) { penpot.createRectangle().name = 'flood'; } return 1;",
                     session=session)
            flood = "accepted"
        except mcp_client.ToolError as error:
            flood = str(error)[:200]
        out["tooManyChanges"] = {"ok": "[resource-limit]" in flood and state() == before, "answer": flood}

        # a person edits the same file at the same time
        human_done = {}

        def human():
            human_done["result"] = self.tabs.run_code("p1", (
                "const p = penpot.currentPage.findShapes({ name: 'photo' })[0]; p.borderRadius = 20; return 1;"),
                settle=1500)

        thread = threading.Thread(target=human)
        thread.start()
        self.run("penpot.currentPage.findShapes({ name: 'badge' })[0].fills = "
                 "[{ fillColor: '#2F9E44', fillOpacity: 1 }]; return 1;", session=session)
        thread.join()
        time.sleep(2)
        data = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["data"]
        objects = data["pagesIndex"][data["pages"][0]]["objects"]
        by_name = {o["name"]: o for o in objects.values()}
        matches = self.tab_matches(("p1", "p2"), file_id)
        out["concurrent"] = {"ok": (human_done.get("result") or {}).get("ok")
                                   and by_name["photo"].get("r1") == 20
                                   and by_name["badge"]["fills"][0]["fillColor"].lower() == "#2f9e44"
                                   and all(v["ok"] for v in matches.values()), "tabs": matches}

        self.check("robustness", all(v["ok"] for v in out.values()), **out)


RENDERER = """
const k = cljs.core.keyword;
app.main.store.emit_BANG_(app.main.data.profile.update_profile_props(
  cljs.core.PersistentArrayMap.fromArray([k("renderer"), k("%s")], true)));
return new Promise((resolve) => setTimeout(() => resolve(String(cljs.core.get_in(
  cljs.core.deref(app.main.store.state), cljs.core.vector(k("profile"), k("props"), k("renderer"))))), 2000));
"""

TEXT_SIZES = """
const k = cljs.core.keyword, get = cljs.core.get;
const s = cljs.core.deref(app.main.store.state);
const objects = app.main.data.helpers.lookup_page_objects(s);
const out = [];
cljs.core.into_array(cljs.core.vals(objects)).forEach((o) => {
  if (get(o, k("type")) !== k("text")) return;
  const parent = get(objects, get(o, k("parent-id")));
  out.push([get(parent, k("name")) + "/" + get(o, k("name")), get(o, k("width")), get(o, k("height"))]);
});
return { renderer: String(get(get(get(s, k("profile")), k("props")), k("renderer"))), texts: out.sort() };
"""


def shot(space, label, path):
    """Screenshot of a tab, after a fit-all zoom so the whole page shows."""
    script = """
const task = await taskSpace(%d);
const page = task.page(%s);
await page.evaluate(() => app.main.store.emit_BANG_(app.main.data.workspace.zoom.zoom_to_fit_all));
await page.waitForTimeout(1500);
await page.screenshot({ path: %s });
console.log("RESULT=true");
""" % (space, json.dumps(label), json.dumps(str(path)))
    return observers.marked(observers.ego(script), "RESULT=")


def svg_renderer(run):
    """D13: what a browser on the svg renderer does with texts the server measured with wasm."""
    file_id = run.file_id
    revn = lambda: mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["revn"]  # noqa: E731
    data = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["data"]
    objects = data["pagesIndex"][data["pages"][0]]["objects"]
    saved = sorted([f"{objects[o['parentId']]['name']}/{o['name']}", o["width"], o["height"]]
                   for o in objects.values() if o["type"] == "text")
    before = revn()
    switched = run.tabs.evaluate("p1", RENDERER % "svg")
    try:
        run.tabs.open(file_id, run.page_id)
        time.sleep(8)
        seen = run.tabs.evaluate("p1", TEXT_SIZES)
        shots = mcpv.STATE / "shots"
        shots.mkdir(parents=True, exist_ok=True)
        shot(run.space, "p1", shots / "pen9-renderer-svg.png")
        after = revn()
        data = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["data"]
        objects = data["pagesIndex"][data["pages"][0]]["objects"]
        resaved = sorted([f"{objects[o['parentId']]['name']}/{o['name']}", o["width"], o["height"]]
                         for o in objects.values() if o["type"] == "text")
    finally:
        restored = run.tabs.evaluate("p1", RENDERER % "wasm")
        run.tabs.open(file_id, run.page_id)
        time.sleep(4)
        shot(run.space, "p1", mcpv.STATE / "shots" / "pen9-renderer-wasm.png")
    differences = [[a[0], [round(a[1], 2), round(a[2], 2)], [round(b[1], 2), round(b[2], 2)]]
                   for a, b in zip(saved, seen["texts"]) if a[0] == b[0]
                   and (abs(a[1] - b[1]) > 0.5 or abs(a[2] - b[2]) > 0.5)]
    run.report["svgRenderer"] = {
        # a measurement for the exception list (03 §6 D13), done when the renderer really switched
        "ok": switched == ":svg" and seen["renderer"] == ":svg" and restored == ":wasm",
        "renderer": [switched, seen["renderer"], restored], "texts": len(saved), "sizeDifferences": differences,
        "revnBefore": before, "revnAfter": after, "savedSizesChanged": resaved != saved,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()
    run = Pen9(args.space)
    steps = (run.cross_feature, run.plugin_path, run.browserless, run.late_open, run.live, run.reconnect, run.refresh,
             run.mcp_restart, run.robustness, lambda: svg_renderer(run))
    for step in steps:
        try:
            step()
        except Exception as error:  # noqa: BLE001
            name = "svgRenderer" if step.__name__ == "<lambda>" else step.__name__
            run.report[name] = {"ok": False, "crashed": repr(error)[:800]}
            if step is run.browserless:
                break
    failed = [name for name, check in run.report.items() if not check["ok"]]
    print(json.dumps({"failed": failed, "checks": run.report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
