"""
PEN-9: runs every ticket's experiment on the same build, one after the other,
and keeps each JSON report in `.mcp-verify/pen9/<out>/<name>.json` (`--out`,
default `regression`).

    python3 -I mcp/docs/server-mcp/experiments/pen9_regression.py --space 206 [--only pen5 pen11]

A run passes only when the script exits 0 and printed a JSON report. A script
that crashes, times out or prints no report counts as failed, never as passed.
The summary names the build: the git commit, whether the work tree is clean,
and when the frontend and executor bundles in the stack were compiled.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import mcpv  # noqa: E402

# (name, script, takes --space, timeout seconds); order follows PEN-22, then PEN-9's own
RUNS = [
    ("e1", "e1_server_write.py", False, 600),
    ("pen3", "pen3_vertical_slice.py", True, 1200),
    ("pen4", "pen4_files_pages.py", True, 1200),
    ("pen5", "pen5_basic_shapes.py", True, 1200),
    ("pen6", "pen6_consistency.py", True, 2400),
    ("pen6-shutdown", "pen6_shutdown.py", False, 2400),
    ("pen10", "pen10_context.py", True, 1200),
    ("pen11", "pen11_hierarchy.py", True, 1200),
    ("pen12", "pen12_texts.py", True, 1200),
    ("pen13", "pen13_layouts.py", True, 1200),
    ("pen14", "pen14_libraries.py", True, 1200),
    ("pen15", "pen15_assets.py", True, 1200),
    ("pen16", "pen16_media.py", True, 1200),
    ("pen17", "pen17_prototype.py", True, 1200),
    ("pen18", "pen18_comments.py", True, 1200),
    ("pen19", "pen19_exports.py", True, 1800),
    ("pen20", "pen20_history.py", True, 2400),
    ("pen24", "pen24_follow.py", True, 1200),
    ("pen9-integrated", "pen9_integrated.py", True, 2400),
    ("pen9-gaps", "pen9_gaps.py", True, 1800),
]

OUT = mcpv.STATE / "pen9" / "regression"


def build():
    """The commit under test and when the stack compiled the bundles it serves."""
    def git(*args):
        return subprocess.run(["git", "-C", str(mcpv.ROOT), *args], capture_output=True, text=True).stdout.strip()

    _, stamps, _ = mcpv.container(
        "cd ~/penpot; "
        "for f in frontend/resources/public/js/main.js frontend/target/executor/executor.js; do "
        "  [ -f $f ] && echo \"$f $(date -u -r $f +%FT%TZ)\"; done")
    return {"commit": git("rev-parse", "HEAD"),
            "commitTime": git("log", "-1", "--format=%cI"),
            "dirty": git("status", "--porcelain", "--untracked-files=no") != "",
            "bundles": stamps.strip().splitlines()}


def run(name, script, space, args, timeout):
    command = [sys.executable, "-I", str(HERE / script)] + (["--space", str(args.space)] if space else [])
    started = time.monotonic()
    try:
        out = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        code, stdout, stderr = out.returncode, out.stdout, out.stderr
    except subprocess.TimeoutExpired as error:
        code, stdout, stderr = "timeout", error.stdout or "", error.stderr or ""
        stdout = stdout.decode() if isinstance(stdout, bytes) else stdout
        stderr = stderr.decode() if isinstance(stderr, bytes) else stderr
    seconds = round(time.monotonic() - started, 1)
    (OUT / f"{name}.log").write_text(f"$ {' '.join(command)}\n--- stdout\n{stdout}\n--- stderr\n{stderr}")
    start = stdout.find("{")
    try:
        report = json.loads(stdout[start:]) if start >= 0 else None
    except ValueError:
        report = None
    if report is not None:
        (OUT / f"{name}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    failed = report.get("failed") if isinstance(report, dict) else None
    return {"name": name, "ok": code == 0 and report is not None, "exit": code, "seconds": seconds,
            "failedChecks": failed, "report": str((OUT / f"{name}.json").relative_to(mcpv.ROOT))
            if report is not None else None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--out", default="regression")
    args = parser.parse_args()
    global OUT
    OUT = mcpv.STATE / "pen9" / args.out
    OUT.mkdir(parents=True, exist_ok=True)

    summary = {"build": build(), "runs": []}
    for name, script, space, timeout in RUNS:
        if args.only and name not in args.only:
            continue
        result = run(name, script, space, args, timeout)
        summary["runs"].append(result)
        print(json.dumps({k: result[k] for k in ("name", "ok", "exit", "seconds", "failedChecks")},
                         ensure_ascii=False), file=sys.stderr, flush=True)
    summary["failed"] = [r["name"] for r in summary["runs"] if not r["ok"]]
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    sys.exit(1 if summary["failed"] else 0)


if __name__ == "__main__":
    main()
