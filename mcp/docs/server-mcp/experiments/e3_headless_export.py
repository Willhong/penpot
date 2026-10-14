#!/usr/bin/env python3
#
# Experiment E3: export one shape through the exporter twice, once with the
# headless render-wasm backend (`is-wasm` true: Node worker, no Chromium) and
# once with the browser backend (Playwright Chromium), then compare pixels.
#
# Also checks whether an API access token (Authorization: Token) is accepted
# by the exporter, or only a login session cookie.
#
# Needs the mcp-verify stack up and seeded, and a shape to export, e.g. the
# rectangle written by e1_server_write.py:
#   python3 -I mcp/docs/server-mcp/experiments/e3_headless_export.py --file scratch [--shape-name server-rect]
#
# PNG files land in .mcp-verify/e3/. Prints one JSON report.

import argparse
import http.cookiejar
import json
import ssl
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / ".mcp-verify/fixtures.json"
OUT_DIR = ROOT / ".mcp-verify/e3"

CONTEXT = ssl.create_default_context()
CONTEXT.check_hostname = False
CONTEXT.verify_mode = ssl.CERT_NONE


def opener():
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=CONTEXT),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def post(op, url, body, headers):
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    started = time.monotonic()
    try:
        with op.open(request, timeout=180) as response:
            return response.status, response.read(), time.monotonic() - started
    except urllib.error.HTTPError as error:
        return error.code, error.read(), time.monotonic() - started


def transit_export(file_id, page_id, object_id, is_wasm):
    """
    Verbose (cache-free) transit for the export-shapes command.
    """
    export = ('["^ ","~:file-id","~u%s","~:page-id","~u%s","~:object-id","~u%s",'
              '"~:type","~:png","~:suffix","","~:scale",1,"~:name","e3"]' % (file_id, page_id, object_id))
    return ('["^ ","~:cmd","~:export-shapes","~:wait",true,"~:is-wasm",%s,'
            '"~:profile-id","~u00000000-0000-0000-0000-000000000000","~:exports",[%s]]'
            % ("true" if is_wasm else "false", export)).encode()


def png_rgba(data):
    """
    Decodes an 8-bit RGB/RGBA non-interlaced PNG into (width, height, rows).
    """
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, width = 8, b"", None
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
            assert depth == 8 and color in (2, 6) and interlace == 0, (depth, color, interlace)
            channels = 4 if color == 6 else 3
        elif kind == b"IDAT":
            idat += chunk
        pos += 12 + length
    raw = zlib.decompress(idat)
    stride = width * channels
    rows, prev, i = [], bytearray(stride), 0
    for _ in range(height):
        ftype, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - channels] if x >= channels else 0
            b = prev[x]
            c = prev[x - channels] if x >= channels else 0
            if ftype == 1:
                line[x] = (line[x] + a) & 255
            elif ftype == 2:
                line[x] = (line[x] + b) & 255
            elif ftype == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif ftype == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        if channels == 3:
            line = bytearray(v for px in range(width) for v in (*line[px * 3:px * 3 + 3], 255))
        rows.append(bytes(line))
    return width, height, rows


def compare(a, b):
    wa, ha, ra = png_rgba(a)
    wb, hb, rb = png_rgba(b)
    if (wa, ha) != (wb, hb):
        return {"sameSize": False, "a": [wa, ha], "b": [wb, hb]}
    diff, maxdelta = 0, 0
    for y in range(ha):
        for x in range(0, wa * 4, 4):
            delta = max(abs(ra[y][x + k] - rb[y][x + k]) for k in range(4))
            maxdelta = max(maxdelta, delta)
            if delta > 2:
                diff += 1
    return {"sameSize": True, "size": [wa, ha], "pixelsDifferingOver2": diff,
            "ratio": round(diff / (wa * ha), 6), "maxChannelDelta": maxdelta}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="scratch")
    parser.add_argument("--shape-name", default="server-rect")
    args = parser.parse_args()

    fixtures = json.loads(FIXTURES.read_text())
    base = fixtures["baseUri"]
    file = fixtures["files"][args.file]
    owner = fixtures["profiles"]["owner"]
    rpc_headers = {"content-type": "application/json", "accept": "application/json", "x-client": "mcp-verify-e3"}

    op = opener()
    status, body, _ = post(op, f"{base}/api/main/methods/login-with-password",
                           json.dumps({"email": owner["email"], "password": owner["password"]}).encode(), rpc_headers)
    assert status == 200, (status, body[:200])
    status, body, _ = post(op, f"{base}/api/main/methods/get-file", json.dumps({"id": file["id"]}).encode(), rpc_headers)
    objects = json.loads(body)["data"]["pagesIndex"][file["pageId"]]["objects"]
    shape_id = next(k for k, v in objects.items() if v.get("name") == args.shape_name)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {"shapeId": shape_id, "exports": {}}
    export_headers = {"content-type": "application/transit+json", "accept": "application/transit+json"}
    pngs = {}
    for label, is_wasm in (("headlessWasm", True), ("browser", False)):
        status, body, elapsed = post(op, f"{base}/api/export",
                                     transit_export(file["id"], file["pageId"], shape_id, is_wasm), export_headers)
        entry = {"status": status, "seconds": round(elapsed, 3)}
        if status == 200:
            resource = json.loads(body)
            # verbose transit map ({"~:uri": ..}) or array map (["^ ", "~:uri", ..])
            uri = (resource["~:uri"] if isinstance(resource, dict)
                   else next(resource[i + 1] for i, v in enumerate(resource) if v == "~:uri"))
            if isinstance(uri, dict):  # tagged value, e.g. {"~#uri": ".."}
                uri = next(iter(uri.values()))
            uri = uri[2:] if uri.startswith("~r") else uri
            with op.open(uri if uri.startswith("http") else base + uri, timeout=60) as response:
                pngs[label] = response.read()
            path = OUT_DIR / f"{label}.png"
            path.write_bytes(pngs[label])
            entry.update({"bytes": len(pngs[label]), "path": str(path.relative_to(ROOT))})
        else:
            entry["body"] = body[:300].decode(errors="replace")
        report["exports"][label] = entry

    if len(pngs) == 2:
        report["pixelCompare"] = compare(pngs["headlessWasm"], pngs["browser"])

    # an API access token instead of the session cookie
    token_headers = dict(export_headers, authorization=f"Token {owner['tokens']['api']}")
    status, body, _ = post(opener(), f"{base}/api/export",
                           transit_export(file["id"], file["pageId"], shape_id, True), token_headers)
    report["accessTokenOnly"] = {"status": status, "body": body[:200].decode(errors="replace")}

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, StopIteration, KeyError) as error:
        print(f"e3: {error!r}", file=sys.stderr)
        sys.exit(1)
