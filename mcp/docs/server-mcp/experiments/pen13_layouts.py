#!/usr/bin/env python3
#
# PEN-13: flex, grid and nested layouts through MCP with no browser, compared
# with the same code in a browser workspace (dual_run.py).
#
#   python3 -I pen13_layouts.py --space <ego-browser task space>
#
# - pen13_layout.js (dual run): flex and grid with every option, nested
#   hugging layouts, then parent resize, children added, hidden, reordered and
#   removed, a deep child resized and a layout removed; after each step the
#   geometry of every shape must be equal, as must the saved shapes, and the
#   observer tab shows the result without a reload and after one.
# - pen13_refusals.js (dual run): invalid layout values; same answers and
#   same state left behind.
# - noBrowser (server only): the scenario runs while no browser has the file
#   open; a browser opened afterwards neither moves nor saves anything.
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


def no_browser(space, session):
    tabs = observers.Tabs(space, labels=("p1",))
    tabs.blank()
    file_id, page_id = mcpv.create_file("pen13-no-browser")
    client = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
    response, _ = client.execute_code((HERE / "pen13_layout.js").read_text(), fileId=file_id, sessionId=session)
    revn = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["revn"]
    before = dual_run.saved_shapes(file_id)
    tabs.open(file_id, page_id)
    time.sleep(6)
    after = dual_run.saved_shapes(file_id)
    revn_after = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["revn"]
    waits_ok = all(state == "ok" for _, state in response["result"]["waits"])
    return {
        "ok": waits_ok and response["commit"]["pending"] is None and revn == revn_after and before == after,
        "waits": response["result"]["waits"],
        "commit": {k: response["commit"][k] for k in ("revn", "computed", "pending")},
        "revnBeforeBrowser": revn,
        "revnAfterBrowser": revn_after,
        "savedUnchangedAfterBrowser": before == after,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", type=int, required=True)
    args = parser.parse_args()

    run = dual_run.DualRun(args.space)
    report = {
        "layouts": run.scenario("pen13-layouts", (HERE / "pen13_layout.js").read_text()),
        "refusals": run.scenario("pen13-refusals", (HERE / "pen13_refusals.js").read_text()),
    }
    try:
        report["noBrowser"] = no_browser(args.space, f"{run.session}-alone")
    except Exception as error:  # noqa: BLE001
        report["noBrowser"] = {"ok": False, "crashed": repr(error)[:600]}

    failed = [name for name, check in report.items() if not check.get("ok")]
    print(json.dumps({"failed": failed, "report": report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
