#!/usr/bin/env python3
#
# Experiment E1: write to a Penpot file with no browser involved.
#
# 1. builds an `add-obj` change for a rectangle with the shared cljc code
#    (app.common.types.shape / changes-builder) on the backend JVM, through
#    the backend socket REPL (urepl, port 6062 inside the container);
# 2. sends it with the `update-file` RPC as an external client authenticated
#    by an access token (Authorization: Token ...);
# 3. re-reads the file and checks the rectangle and revn;
# 4. probes the contract edges: viewer/outsider tokens, stale revn, revn
#    ahead of the server, and replaying the same request.
#
# Needs the mcp-verify stack up and seeded:
#   scripts/mcp-verify-env up && scripts/mcp-verify-env wait && scripts/mcp-verify-env seed
#   python3 -I mcp/docs/server-mcp/experiments/e1_server_write.py [--file basic] [--x 100 --y 100]
#
# Prints one JSON report on stdout.

import argparse
import json
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / ".mcp-verify/fixtures.json"
MAIN = "penpot-mcpverify-main"

CONTEXT = ssl.create_default_context()
CONTEXT.check_hostname = False
CONTEXT.verify_mode = ssl.CERT_NONE

CLJ_TEMPLATE = """
(do
  (require '[app.common.types.shape :as cts]
           '[app.common.files.changes-builder :as pcb]
           '[app.common.transit :as t]
           '[app.common.uuid :as uuid])
  (let [shape   (cts/setup-shape {:type :rect
                                  :name "%(name)s"
                                  :x %(x)s :y %(y)s :width 200 :height 120
                                  :fills [{:fill-color "#E8590C" :fill-opacity 1}]})
        changes (-> (pcb/empty-changes)
                    (pcb/with-page-id (uuid/uuid "%(page_id)s"))
                    (pcb/with-objects {})
                    (pcb/add-object shape))]
    (println "@@SHAPE@@" (str (:id shape)) "@@END@@")
    (println "@@BEGIN@@" (t/encode-str {:id (uuid/uuid "%(file_id)s")
                                        :session-id (uuid/uuid "%(session_id)s")
                                        :revn %(revn)s
                                        :vern %(vern)s
                                        :changes (:redo-changes changes)}) "@@END@@")))
"""


def rpc(base_uri, method, params, token=None, transit_body=None):
    headers = {"accept": "application/json", "x-client": "mcp-verify-e1"}
    if token:
        headers["authorization"] = f"Token {token}"
    if transit_body is not None:
        headers["content-type"] = "application/transit+json"
        data = transit_body.encode()
    else:
        headers["content-type"] = "application/json"
        data = json.dumps(params).encode()
    request = urllib.request.Request(
        f"{base_uri}/api/main/methods/{method}", data=data, headers=headers, method="POST")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, context=CONTEXT, timeout=60) as response:
            body = response.read()
            return response.status, (json.loads(body) if body else None), time.monotonic() - started
    except urllib.error.HTTPError as error:
        body = error.read()
        try:
            payload = json.loads(body)
        except ValueError:
            payload = body.decode(errors="replace")[:300]
        return error.code, payload, time.monotonic() - started


def build_request(file_id, page_id, session_id, revn, vern, name, x, y):
    """
    Evaluates the change builder on the backend JVM and returns
    (shape id, transit-encoded update-file params). The whole request is
    encoded in one pass: transit caches keys, so encoded fragments cannot be
    spliced together.
    """
    form = CLJ_TEMPLATE % {"page_id": page_id, "name": name, "x": x, "y": y,
                           "file_id": file_id, "session_id": session_id,
                           "revn": revn, "vern": vern}
    form = " ".join(form.split())
    script = ("exec 3<>/dev/tcp/127.0.0.1/6062; "
              "cat >&3; printf '\\n:repl/quit\\n' >&3; timeout 60 cat <&3")
    result = subprocess.run(["docker", "exec", "-i", "-u", "penpot", MAIN, "bash", "-c", script],
                            input=form, capture_output=True, text=True)
    out = result.stdout
    if "@@BEGIN@@" not in out:
        raise RuntimeError(f"urepl evaluation failed: {out[-2000:]} {result.stderr[-500:]}")
    shape_id = out.split("@@SHAPE@@", 1)[1].split("@@END@@", 1)[0].strip()
    return shape_id, out.split("@@BEGIN@@", 1)[1].split("@@END@@", 1)[0].strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="basic")
    parser.add_argument("--x", type=int, default=100)
    parser.add_argument("--y", type=int, default=100)
    parser.add_argument("--skip-edges", action="store_true")
    args = parser.parse_args()

    fixtures = json.loads(FIXTURES.read_text())
    base = fixtures["baseUri"]
    file = fixtures["files"][args.file]
    tokens = {role: p["tokens"]["api"] for role, p in fixtures["profiles"].items()}
    report = {"file": args.file, "fileId": file["id"]}

    status, data, _ = rpc(base, "get-file", {"id": file["id"]}, tokens["editor"])
    assert status == 200, (status, data)
    revn, vern = data["revn"], data.get("vern", 0)
    report["before"] = {"revn": revn, "objects": len(data["data"]["pagesIndex"][file["pageId"]]["objects"])}

    started = time.monotonic()
    session_id = str(uuid.uuid4())
    shape_id, body = build_request(file["id"], file["pageId"], session_id, revn, vern,
                                   "server-rect", args.x, args.y)
    report["buildSeconds"] = round(time.monotonic() - started, 3)

    status, data, elapsed = rpc(base, "update-file", None, tokens["editor"], transit_body=body)
    report["write"] = {"status": status, "seconds": round(elapsed, 3), "shapeId": shape_id,
                       "sessionId": session_id, "response": data if status != 200 else "ok"}

    status, data, _ = rpc(base, "get-file", {"id": file["id"]}, tokens["owner"])
    objects = data["data"]["pagesIndex"][file["pageId"]]["objects"]
    saved = objects.get(shape_id)
    report["after"] = {"revn": data["revn"], "saved": saved is not None,
                       "selrect": saved and saved.get("selrect"),
                       "parentId": saved and saved.get("parentId")}

    if not args.skip_edges:
        edges = {}
        for role in ("viewer", "outsider"):
            _, b = build_request(file["id"], file["pageId"], uuid.uuid4(), data["revn"], vern,
                                 f"{role}-rect", 10, 10)
            st, d, _ = rpc(base, "update-file", None, tokens[role], transit_body=b)
            edges[f"{role}Write"] = {"status": st, "code": isinstance(d, dict) and d.get("code")}

        current = data["revn"]
        _, b = build_request(file["id"], file["pageId"], uuid.uuid4(), max(current - 1, 0), vern,
                             "stale-revn-rect", 400, 100)
        st, d, _ = rpc(base, "update-file", None, tokens["editor"], transit_body=b)
        edges["staleRevn"] = {"status": st, "sentRevn": max(current - 1, 0), "storedRevn": current,
                              "response": d if st != 200 else "ok"}

        _, b = build_request(file["id"], file["pageId"], uuid.uuid4(), current + 10, vern,
                             "ahead-revn-rect", 400, 300)
        st, d, _ = rpc(base, "update-file", None, tokens["editor"], transit_body=b)
        edges["aheadRevn"] = {"status": st, "code": isinstance(d, dict) and d.get("code")}

        st, d, _ = rpc(base, "update-file", None, tokens["editor"], transit_body=body)
        st2, d2, _ = rpc(base, "get-file", {"id": file["id"]}, tokens["owner"])
        names = [o.get("name") for o in d2["data"]["pagesIndex"][file["pageId"]]["objects"].values()]
        edges["replaySameRequest"] = {"status": st, "code": isinstance(d, dict) and d.get("code"),
                                      "revnAfter": d2["revn"],
                                      "serverRectCount": names.count("server-rect")}
        report["edges"] = edges

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, AssertionError) as error:
        print(f"e1: {error}", file=sys.stderr)
        sys.exit(1)
