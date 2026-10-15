#!/usr/bin/env python3
#
# PEN-16: images and SVG through MCP with no browser.
#
#   python3 -I pen16_media.py --space <ego-browser task space>
#
# - pen16_media.js (dual run with a browser workspace): images uploaded from
#   bytes and from a public URL, image fills, an SVG with paths, gradients,
#   groups and transforms, an SVG with an embedded and an external image.
#   Return values and saved shapes must be equal.
# - pen16_refusals.js (dual run): URLs to internal addresses and other
#   schemes, disguised and oversized data, external entities, entity
#   expansion, scripts, malformed SVG; same answers, same shapes left.
# - server only: an SVG that does not parse fails the execution with
#   `svg-parser` and saves nothing; in remote (multi-user) mode no tool reads
#   files of the server (`import_image` is not offered).
#
# Prints a JSON report; exit status 1 when a check fails.

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dual_run  # noqa: E402
import mcp_client  # noqa: E402
import mcpv  # noqa: E402


def server_only(session):
    client = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
    file_id, _ = mcpv.create_file("pen16-svg-parser")
    client.execute_code("const r = penpot.createRectangle(); r.name = 'before'; return 1;", fileId=file_id,
                        sessionId=session)
    revn = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["revn"]
    try:
        client.execute_code("const r = penpot.createRectangle(); r.name = 'lost'; "
                            "penpot.createShapeFromSvg('<svg><rect></svg'); return 1;", sessionId=session)
        outcome = "accepted"
    except mcp_client.ToolError as error:
        outcome = str(error)[:200]
    revn_after = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["revn"]
    tools = [tool["name"] for tool in client.call("tools/list", {})["tools"]]
    return {
        "svgParser": outcome,
        "savedNothing": revn == revn_after,
        "tools": tools,
        "ok": outcome.startswith("Tool execution failed: [svg-parser]") and revn == revn_after
              and "import_image" not in tools and "execute_code" in tools,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()

    run = dual_run.DualRun(args.space)
    report = {
        "media": run.scenario("pen16-media", (HERE / "pen16_media.js").read_text()),
        "refusals": run.scenario("pen16-refusals", (HERE / "pen16_refusals.js").read_text()),
    }
    try:
        report["serverOnly"] = server_only(f"{run.session}-svg")
    except Exception as error:  # noqa: BLE001
        report["serverOnly"] = {"ok": False, "crashed": repr(error)[:600]}

    failed = [name for name, check in report.items() if not check.get("ok")]
    print(json.dumps({"failed": failed, "report": report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
