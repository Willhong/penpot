#!/usr/bin/env python3
#
# Experiment E4: compares what the browser (wasm renderer) and the headless
# executor saved for the same Plugin API code (`e4_scenario.js`).
#
#   python3 -I e4_compare.py <browser-file-id> <executor-file-id>
#
# Both files are re-read from the backend. Shapes are matched by name and
# compared with the tolerances of 03-runtime-contract.md §6:
#   - geometry (selrect, points): 0.01 px; 0.5 px for children of a layout
#   - text width/height: 0.5 px; same number of position-data fragments and
#     the same text in each (same line breaks)
#   - boolean path content: 0.01 px per coordinate
#   - every other attribute: equal after rounding numbers to 2 decimals
#
# Prints a JSON report; exit status 1 when any shape differs.

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mcpv  # noqa: E402

GEOMETRY_KEYS = {"selrect", "points", "x", "y", "width", "height", "transform", "transformInverse"}
IGNORED_KEYS = {"id", "parentId", "frameId", "shapes", "positionData", "content",
                "modifiedAt", "touched", "boolContent"}


def shape_page(file_id):
    data = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))
    page_id = data["data"]["pages"][0]
    objects = data["data"]["pagesIndex"][page_id]["objects"]
    return {shape["name"]: shape for shape in objects.values()}, objects


def round_values(value):
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, list):
        return [round_values(v) for v in value]
    if isinstance(value, dict):
        return {k: round_values(v) for k, v in value.items()}
    return value


def numbers(value, path=""):
    """Flattens the numbers of a JSON value into {path: number}."""
    out = {}
    if isinstance(value, bool) or value is None:
        return out
    if isinstance(value, (int, float)):
        out[path] = float(value)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.update(numbers(v, f"{path}[{i}]"))
    elif isinstance(value, dict):
        for k, v in value.items():
            out.update(numbers(v, f"{path}.{k}"))
    return out


def max_delta(a, b):
    na, nb = numbers(a), numbers(b)
    if set(na) != set(nb):
        return float("inf"), sorted(set(na) ^ set(nb))[:5]
    worst = max((abs(na[k] - nb[k]) for k in na), default=0.0)
    return worst, None


def in_layout(objects, shape):
    parent = objects.get(shape.get("parentId"))
    return bool(parent and parent.get("layout"))


def compare(browser, executor, b_objects, e_objects):
    report = {}
    failed = False
    for name in sorted(set(browser) | set(executor)):
        b, e = browser.get(name), executor.get(name)
        if b is None or e is None:
            report[name] = {"ok": False, "reason": "missing in " + ("browser" if b is None else "executor")}
            failed = True
            continue
        entry = {"type": b["type"]}
        tolerance = 0.5 if (in_layout(b_objects, b) or b["type"] == "text") else 0.01
        geometry = {k: b.get(k) for k in GEOMETRY_KEYS}, {k: e.get(k) for k in GEOMETRY_KEYS}
        delta, mismatch = max_delta(*geometry)
        entry["geometryMaxDelta"] = delta
        entry["geometryTolerance"] = tolerance
        ok = delta <= tolerance and mismatch is None
        if mismatch:
            entry["geometryKeyMismatch"] = mismatch

        if b["type"] == "text":
            bp, ep = b.get("positionData") or [], e.get("positionData") or []
            entry["size"] = {"browser": [b["width"], b["height"]], "executor": [e["width"], e["height"]]}
            entry["fragments"] = {"browser": [p.get("text") for p in bp],
                                  "executor": [p.get("text") for p in ep]}
            same_lines = [p.get("text") for p in bp] == [p.get("text") for p in ep]
            pdelta, pmismatch = max_delta([{k: p.get(k) for k in ("x", "y", "width", "height")} for p in bp],
                                          [{k: p.get(k) for k in ("x", "y", "width", "height")} for p in ep])
            entry["positionDataMaxDelta"] = pdelta
            ok = ok and same_lines and pdelta <= 0.5 and pmismatch is None
            ok = ok and round_values(b.get("content")) == round_values(e.get("content"))

        if b["type"] == "bool":
            cdelta, cmismatch = max_delta(b.get("content"), e.get("content"))
            entry["contentMaxDelta"] = cdelta
            entry["contentSegments"] = [len(b.get("content") or []), len(e.get("content") or [])]
            ok = ok and cdelta <= 0.01 and cmismatch is None

        other_b = {k: v for k, v in b.items() if k not in GEOMETRY_KEYS | IGNORED_KEYS}
        other_e = {k: v for k, v in e.items() if k not in GEOMETRY_KEYS | IGNORED_KEYS}
        if round_values(other_b) != round_values(other_e):
            keys = sorted(k for k in set(other_b) | set(other_e)
                          if round_values(other_b.get(k)) != round_values(other_e.get(k)))
            entry["otherAttrDiff"] = {k: {"browser": other_b.get(k), "executor": other_e.get(k)} for k in keys}
            ok = False

        entry["ok"] = ok
        failed = failed or not ok
        report[name] = entry
    return report, failed


def main():
    browser_id, executor_id = sys.argv[1:3]
    browser, b_objects = shape_page(browser_id)
    executor, e_objects = shape_page(executor_id)
    report, failed = compare(browser, executor, b_objects, e_objects)
    summary = {"shapes": len(report), "differing": [n for n, r in report.items() if not r["ok"]]}
    print(json.dumps({"summary": summary, "shapes": report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
