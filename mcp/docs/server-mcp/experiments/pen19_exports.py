#!/usr/bin/env python3
#
# PEN-19: exports and code generation through MCP with no browser.
#
#   python3 -I pen19_exports.py --space <ego-browser task space>
#
# - outputs: pen19_export.js runs in a browser workspace (wasm renderer, tab
#   p2) and on the server. Rasters must match the browser's CPU raster export
#   of the same shapes (the path the server takes, as the exporter does) and
#   have the size of the browser's GPU export; the difference to the GPU
#   export is reported as `renderer`. SVG and generated code must be equal
#   once origins and media ids are normalized; PDF once the image colour
#   space tag is.
# - large: a result over 1 MB comes back as a download URL that works for
#   its owner only, from execute_code and export_shape.
# - jobs: `async: true` answers with a job; it ends done and saved, or
#   cancelled and not saved; another user cannot see it.
# - export_shape: png, svg and fill exports of a server session.
# - file: `.penpot` export of a file with unsaved changes imports back with
#   the same shapes; the dropped zip format is refused with a message.
#
# Prints a JSON report; exit status 1 when a check fails.

import argparse
import base64
import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.request
import uuid
import zlib
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mcp_client  # noqa: E402
import mcpv  # noqa: E402
import observers  # noqa: E402

OUT = mcpv.STATE / "pen19"
CONTAINER_OUT = "/home/penpot/penpot/.mcp-verify/pen19"
TOLERANCE = 0.001

# raster outputs of pen19_export.js: shape name, scale, wasm format code
RASTERS = {
    "card.png": ("card", 1, 0),
    "card@2x.png": ("card", 2, 0),
    "card.jpeg": ("card", 1, 1),
    "card.webp": ("card", 1, 2),
    "title.png": ("title", 1, 0),
    "photo.png": ("photo", 1, 0),
}

# the browser's own CPU raster export of a shape (`render_shape_raster_extended`)
BROWSER_CPU = """
const mod = app.common.render_wasm.wasm.internal_module;
const out = {};
for (const [name, [id, scale, format]] of Object.entries(%s)) {
  const buf = app.common.uuid.get_u32(cljs.core.uuid(id));
  const off = mod._render_shape_raster_extended(buf[0], buf[1], buf[2], buf[3], scale, format);
  const len = mod.HEAPU32[off >> 2];
  const bytes = mod.HEAPU8.slice(off + 12, off + 12 + len);
  app.common.render_wasm.mem.free();
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  out[name] = btoa(s);
}
return out;
"""


def png(width, height, pixel):
    raw = b"".join(b"\x00" + b"".join(pixel(x, y) for x in range(width)) for y in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def multipart(method, fields, files, token):
    """Calls a backend RPC method with a multipart body; returns (status, text)."""
    boundary = uuid.uuid4().hex
    body = b""
    for name, value in fields.items():
        body += (f"--{boundary}\r\ncontent-disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode()
    for name, (filename, mtype, data) in files.items():
        body += (f"--{boundary}\r\ncontent-disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
                 f"content-type: {mtype}\r\n\r\n").encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    request = urllib.request.Request(f"{mcpv.fixtures()['baseUri']}/api/main/methods/{method}", data=body,
                                     method="POST", headers={
                                         "content-type": f"multipart/form-data; boundary={boundary}",
                                         "accept": "application/json", "authorization": f"Token {token}"})
    try:
        with urllib.request.urlopen(request, context=mcpv.CONTEXT, timeout=300) as response:
            return response.status, response.read().decode(errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(errors="replace")[:500]


def download(url, token=None):
    headers = {"authorization": f"Token {token}"} if token else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
            return response.status, response.headers.get("content-type"), response.read()
    except urllib.error.HTTPError as error:
        return error.code, None, b""


def pixel_diff(a, b):
    code, out, err = mcpv.container(f"node /home/penpot/penpot/mcp/docs/server-mcp/experiments/pixel_diff.mjs "
                                    f"{CONTAINER_OUT}/{a} {CONTAINER_OUT}/{b}")
    return json.loads(out) if code == 0 else {"error": err[-300:]}


def normalize_links(text):
    """Origins become ORIGIN, and ids (media and shape ids, and the 12-digit id ends in generated class
    names) their order of appearance (03-runtime-contract §6)."""
    text = re.sub(r"https?://(localhost|127\.0\.0\.1)(:\d+)?", "ORIGIN", text)
    ids = {}

    def name(match):
        return ids.setdefault(match.group(1), f"id{len(ids)}")

    text = re.sub(r"(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-([0-9a-f]{12})\b", name, text)
    return re.sub(r"(?<=-)([0-9a-f]{12})\b", name, text)


def squash(text):
    """Whitespace normalized (03-runtime-contract §6): runs become one space, none between tags."""
    return re.sub(r">\s+<", "><", re.sub(r"\s+", " ", text)).strip()


def pdf_streams(data):
    """The decompressed streams of a PDF, without ICC profiles, with resource names numbered away."""
    out = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        body = match.group(1)
        try:
            body = zlib.decompress(body)
        except zlib.error:
            pass
        if body[36:40] == b"acsp":  # an ICC profile
            continue
        out.append(re.sub(rb"/([GXPF])\d+", rb"/\1n", body))
    return out


class Pen19:
    def __init__(self, space):
        self.space = space
        self.tabs = observers.Tabs(space, labels=("p2",))
        self.editor = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
        self.owner = mcp_client.Client(mcpv.token("owner", "mcp"), executor="server")
        self.session = f"pen19-{time.time_ns()}"
        self.report = {}
        OUT.mkdir(parents=True, exist_ok=True)

    def run(self, code, client=None, **kwargs):
        return (client or self.editor).execute_code(code, sessionId=kwargs.pop("session", self.session), **kwargs)[0]

    def outputs(self):
        image = base64.b64encode(png(24, 16, lambda x, y: bytes(((x * 37) % 256, (y * 53) % 256,
                                                                    ((x + y) * 17) % 256)))).decode()
        code = (HERE / "pen19_export.js").read_text().replace("__PNG_BASE64__", image)
        server_file, _ = mcpv.create_file("pen19-export-server")
        server = self.run(code, fileId=server_file, session=f"{self.session}-out")["result"]
        browser_file, browser_page = mcpv.create_file("pen19-export-browser")
        self.tabs.blank()
        self.tabs.open(browser_file, browser_page)
        browser = self.tabs.run_code("p2", code, settle=300)["result"]
        by_name = {name: id for id, name in browser["ids"].items()}
        cpu = self.tabs.evaluate("p2", BROWSER_CPU % json.dumps(
            {name: [by_name[shape], scale, fmt] for name, (shape, scale, fmt) in RASTERS.items()}))

        rasters = {}
        for name in RASTERS:
            for side, data in (("server", server["outputs"][name]), ("gpu", browser["outputs"][name]),
                               ("cpu", cpu[name])):
                (OUT / f"{side}-{name}").write_bytes(base64.b64decode(data))
            same = pixel_diff(f"server-{name}", f"cpu-{name}")
            renderer = pixel_diff(f"server-{name}", f"gpu-{name}")
            rasters[name] = {
                "ok": same.get("sameSize") and same.get("ratio", 1) <= TOLERANCE and renderer.get("sameSize"),
                "browserCpu": same, "renderer": renderer,
            }

        public = mcpv.fixtures()["baseUri"]
        svg_server = base64.b64decode(server["outputs"]["card.svg"]).decode()
        svg_browser = base64.b64decode(browser["outputs"]["card.svg"]).decode()
        links = sorted(set(re.findall(r"(?:href=\"|url\(\")(https?://[^/\"]+)", svg_server)))
        svg = {"ok": normalize_links(svg_server) == normalize_links(svg_browser)
                     and links == [public], "serverLinkOrigins": links}

        (OUT / "server-card.pdf").write_bytes(base64.b64decode(server["outputs"]["card.pdf"]))
        (OUT / "gpu-card.pdf").write_bytes(base64.b64decode(browser["outputs"]["card.pdf"]))
        pdf_s = pdf_streams(base64.b64decode(server["outputs"]["card.pdf"]))
        pdf_b = pdf_streams(base64.b64decode(browser["outputs"]["card.pdf"]))
        pdf = {"ok": pdf_s == pdf_b, "streams": [len(pdf_s), len(pdf_b)]}

        code_out = {}
        for key in server["code"]:
            a = normalize_links(server["code"][key])
            b = normalize_links(browser["code"][key])
            code_out[key] = {"ok": squash(a) == squash(b), "length": [len(a), len(b)]}
        # Known difference (user decision, 03 §6): the server's SVG markup carries the @font-face rules of
        # its texts, with links on the public URI; the browser's leaves that <style> empty.
        faces = re.findall(r"@font-face\s*\{[^}]*\}", server["code"]["svg"])
        without_faces = normalize_links(re.sub(r"\s*@font-face\s*\{[^}]*\}", "", server["code"]["svg"]))
        face_links = sorted(set(re.findall(r"url\((https?://[^/)]+)", " ".join(faces))))
        code_out["svg"].update(
            ok=squash(without_faces) == squash(normalize_links(browser["code"]["svg"])) and face_links == [public],
            serverFontFaces=len(faces), fontFaceOrigins=face_links)
        self.report["outputs"] = {
            "ok": all(r["ok"] for r in rasters.values()) and svg["ok"] and pdf["ok"]
                  and all(c["ok"] for c in code_out.values()),
            "rasters": rasters, "svg": svg, "pdf": pdf, "code": code_out,
        }

    def large(self):
        file_id, _ = mcpv.create_file("pen19-large")
        noise = png(700, 700, lambda x, y: os.urandom(3))
        status, text = multipart("upload-file-media-object", {"file-id": file_id, "is-local": "true", "name": "noise"},
                                 {"content": ("noise.png", "image/png", noise)}, mcpv.token("editor"))
        media = json.loads(text)
        self.large_file = file_id
        self.large_code = """
const r = penpot.createRectangle();
r.name = 'noise';
r.resize(700, 700);
r.fills = [{ fillOpacity: 1, fillImage: { id: %s, width: 700, height: 700, mtype: 'image/png', name: 'noise',
                                           keepAspectRatio: false } }];
storage.noise = r.id;
return await r.export({ type: 'png', scale: 1 });""" % json.dumps(media["id"])
        result = self.run(self.large_code, fileId=file_id)["result"]
        checks = {"upload": status, "result": {k: v for k, v in result.items() if k != "data"}}
        if result.get("__type") == "resource":
            got = download(result["url"], mcpv.token("editor", "mcp"))
            other = download(result["url"], mcpv.token("owner", "mcp"))
            anonymous = download(result["url"])
            checks.update(owner=[got[0], got[1], len(got[2]), got[2][:8] == b"\x89PNG\r\n\x1a\n"],
                          otherUser=other[0], noToken=anonymous[0])
        shape_id = self.run("return storage.noise;")["result"]
        text, _ = self.editor.tool("export_shape", shapeId=shape_id, format="png", sessionId=self.session)
        exported = json.loads(text) if text.startswith("{") else {"text": text[:200]}
        checks["exportShape"] = exported
        self.report["large"] = {
            "ok": result.get("__type") == "resource" and checks["owner"][0] == 200
                  and checks["owner"][1] == "image/png" and checks["owner"][2] == result["size"] > 1024 * 1024
                  and checks["owner"][3] and checks["otherUser"] == 404 and checks["noToken"] == 404
                  and exported.get("__type") == "resource",
            **checks,
        }

    def job(self, client, job_id, cancel=False):
        text, _ = client.tool("execution_job", jobId=job_id, **({"cancel": True} if cancel else {}))
        return json.loads(text)

    def wait_job(self, job_id, timeout=120):
        seen = []
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            view = self.job(self.editor, job_id)
            state = view["status"] + (f"/{view['progress']}" if view.get("progress") else "")
            if not seen or seen[-1] != state:
                seen.append(state)
            if view["status"] in ("done", "error", "cancelled"):
                return view, seen
            time.sleep(0.2)
        return view, seen

    def jobs(self):
        file_id, page_id = mcpv.create_file("pen19-jobs")
        session = f"{self.session}-jobs"
        done_start = self.run("await new Promise((r) => setTimeout(r, 1500)); const s = penpot.createRectangle(); "
                              "s.name = 'job-done'; return s.id;", fileId=file_id, session=session, **{"async": True})
        done, done_seen = self.wait_job(done_start["jobId"])
        try:
            self.job(self.owner, done_start["jobId"])
            other = "visible"
        except mcp_client.ToolError as error:
            other = str(error)[:160]

        cancel_start = self.run("await new Promise((r) => setTimeout(r, 8000)); const s = penpot.createRectangle(); "
                                "s.name = 'job-cancelled'; return s.id;", session=session, **{"async": True})
        time.sleep(1)
        on_cancel = self.job(self.editor, cancel_start["jobId"], cancel=True)
        cancelled, _ = self.wait_job(cancel_start["jobId"])

        large_start = self.run(self.large_code, fileId=self.large_file, session=f"{self.session}-jl",
                               **{"async": True})
        large, _ = self.wait_job(large_start["jobId"])

        _, objects = mcpv.page_objects(file_id, page_id)
        names = sorted(o["name"] for o in objects.values() if o["name"].startswith("job-"))
        self.report["jobs"] = {
            "ok": done_start["status"] in ("pending", "running") and done["status"] == "done"
                  and re.fullmatch(r"[0-9a-f-]{36}", str(done["result"]["result"])) and "running/running" in done_seen
                  and "not-found" in other
                  and cancelled["status"] == "cancelled" and cancelled["error"]["code"] == "cancelled"
                  and names == ["job-done"]
                  and large["status"] == "done" and large.get("resource", {}).get("__type") == "resource",
            "doneStatuses": done_seen, "otherUser": other, "onCancel": on_cancel["status"],
            "cancelled": {"status": cancelled["status"], "error": cancelled.get("error")},
            "savedShapes": names, "large": {k: large.get(k) for k in ("status", "resource")},
        }

    def export_shape(self):
        session = f"{self.session}-out"
        ids = self.run("const all = penpot.currentPage.findShapes(); "
                       "return Object.fromEntries(all.map((s) => [s.name, s.id]));", session=session)["result"]
        result = self.editor.call("tools/call", {"name": "export_shape", "arguments": {
            "shapeId": ids["card"], "format": "png", "sessionId": session}})
        image = [c for c in result["content"] if c["type"] == "image"]
        png_bytes = base64.b64decode(image[0]["data"]) if image else b""
        svg_text, _ = self.editor.tool("export_shape", shapeId=ids["card"], format="svg", sessionId=session)
        fill = self.editor.call("tools/call", {"name": "export_shape", "arguments": {
            "shapeId": ids["photo"], "format": "png", "mode": "fill", "sessionId": session}})
        fill_image = [c for c in fill["content"] if c["type"] == "image"]
        fill_bytes = base64.b64decode(fill_image[0]["data"]) if fill_image else b""
        size = lambda b: struct.unpack(">II", b[16:24]) if b[:8] == b"\x89PNG\r\n\x1a\n" else None  # noqa: E731
        self.report["exportShape"] = {
            "ok": size(png_bytes) == (405, 285) and "<svg" in svg_text[:200]
                  and size(fill_bytes) == (24, 16),
            "png": size(png_bytes), "svg": svg_text[:60], "fill": size(fill_bytes),
        }

    def file(self):
        file_id, page_id = mcpv.create_file("pen19-file")
        session = f"{self.session}-file"
        self.run("const b = penpot.createBoard(); b.name = 'saved board'; b.resize(200, 100); return 1;",
                 fileId=file_id, session=session)
        # the export saves the changes of its own execution first
        exported = self.run("""
const t = penpot.createText('unsaved text'); t.name = 'unsaved text';
const e = penpot.createEllipse(); e.name = 'unsaved ellipse';
return await penpot.currentFile.export('penpot');""", session=session)["result"]
        zip_refused = self.run("""
try { await penpot.currentFile.export('zip'); return 'accepted'; } catch (err) { return String(err.message || err); }""",
                               session=session)["result"]
        data = base64.b64decode(exported["data"])
        status, events = multipart("import-binfile", {"name": "pen19-imported",
                                                      "project-id": mcpv.fixtures()["project"]["id"]},
                                   {"file": ("file.penpot", "application/zip", data)}, mcpv.token("editor"))
        # the last event names the files created
        imported = re.findall(r"~u([0-9a-f-]{36})", events.rsplit("event: end", 1)[-1])
        shapes = lambda fid: sorted(  # noqa: E731
            (o["type"], o["name"]) for page in mcpv.rpc_ok("get-file", {"id": fid}, mcpv.token("editor"))
            ["data"]["pagesIndex"].values() for o in page["objects"].values())
        original = shapes(file_id)
        copy = shapes(imported[0]) if imported else None
        self.report["file"] = {
            "ok": data[:2] == b"PK" and status == 200 and copy == original
                  and ("text", "unsaved text") in original and "no longer exported" in zip_refused,
            "bytes": len(data), "importStatus": status, "shapes": original, "importedSame": copy == original,
            "zip": zip_refused,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()
    run = Pen19(args.space)
    for step in (run.outputs, run.large, run.jobs, run.export_shape, run.file):
        try:
            step()
        except Exception as error:  # noqa: BLE001
            run.report[step.__name__] = {"ok": False, "crashed": repr(error)[:600]}
    failed = [name for name, check in run.report.items() if not check.get("ok")]
    print(json.dumps({"failed": failed, "report": run.report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
