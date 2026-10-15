#!/usr/bin/env python3
#
# Experiment E4: do layout reflow, text size/position data and boolean paths
# computed by the headless executor (Node + headless render-wasm, no
# browser) equal what a browser workspace in wasm mode computes?
#
# Runs the same Plugin API code twice on two fresh files:
#   - in the editor's browser tab (ego-browser task space, wasm renderer on),
#   - in the headless executor (`frontend` build `:executor`) in the
#     mcp-verify main container,
# then re-reads both files from the backend and compares them shape by shape
# (`e4_compare.py`). Then repeats with `e4b_scenario.js`, which edits the
# saved shapes after reopening the files.
#
# Needs: the mcp-verify stack, the executor build
#   (cd frontend && clojure -M:dev:shadow-cljs compile executor, inside the
#   container) and an ego-browser task space whose page "p2" is logged in as
#   the editor at http://127.0.0.1:3550 with the wasm renderer enabled.
#
#   python3 -I e4_headless_compute.py --space <task-space-id>
#
# Prints a JSON report; exit status 1 when anything differs.

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mcpv  # noqa: E402


def run_browser(space, file_id, page_id, scenario):
    team = mcpv.fixtures()["team"]["id"]
    url = f"http://127.0.0.1:3550/#/workspace?team-id={team}&file-id={file_id}&page-id={page_id}"
    options = {"space": space, "page": "p2", "url": url, "code": (HERE / scenario).read_text()}
    script = "globalThis.RUN = " + json.dumps(options) + ";\n" + (HERE / "browser_run.js").read_text()
    out = subprocess.run(["ego-browser", "nodejs"], input=script, capture_output=True, text=True, timeout=300)
    # ego-browser relays the script's console to stderr
    lines = [l for l in (out.stdout + out.stderr).splitlines() if l.startswith("{")]
    if not lines:
        raise RuntimeError(f"browser run failed: {out.stdout[-2000:]} {out.stderr[-1000:]}")
    return json.loads(lines[-1])


def run_executor(file_id, page_id, scenario):
    token = mcpv.token("editor", "api")
    command = (f"cd ~/penpot/frontend && PENPOT_EXECUTOR_TOKEN='{token}' "
               "PENPOT_PUBLIC_URI=http://localhost:3450 "
               f"timeout 300 node target/executor/executor.js run "
               f"../mcp/docs/server-mcp/experiments/{scenario} {file_id} {page_id}")
    code, stdout, stderr = mcpv.container(command)
    lines = [l for l in stdout.splitlines() if l.startswith('{"ok"')]
    if code != 0 or not lines:
        raise RuntimeError(f"executor run failed ({code}): {stdout[-2000:]} {stderr[-2000:]}")
    return json.loads(lines[-1])


def compare(browser_file, executor_file):
    out = subprocess.run([sys.executable, "-I", str(HERE / "e4_compare.py"), browser_file, executor_file],
                         capture_output=True, text=True)
    return json.loads(out.stdout), out.returncode == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()

    browser_file, browser_page = mcpv.create_file("e4-browser")
    executor_file, executor_page = mcpv.create_file("e4-executor")
    report = {"files": {"browser": browser_file, "executor": executor_file}, "rounds": []}
    passed = True
    for scenario in ("e4_scenario.js", "e4b_scenario.js"):
        browser = run_browser(args.space, browser_file, browser_page, scenario)
        executor = run_executor(executor_file, executor_page, scenario)
        diff, ok = compare(browser_file, executor_file)
        passed = passed and ok and browser.get("ok") and executor.get("ok")
        report["rounds"].append({
            "scenario": scenario,
            "browserMs": browser.get("ms"),
            "executorMs": executor.get("ms"),
            "summary": diff["summary"],
            "texts": {name: {k: shape.get(k) for k in ("size", "fragments")}
                      for name, shape in diff["shapes"].items() if shape["type"] == "text"},
            "maxGeometryDelta": max(shape.get("geometryMaxDelta", 0) for shape in diff["shapes"].values()),
            "maxBoolDelta": max((shape.get("contentMaxDelta", 0) for shape in diff["shapes"].values()
                                 if shape["type"] == "bool"), default=None),
        })
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
