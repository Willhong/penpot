#!/usr/bin/env python3
#
# PEN-6: an MCP server stop (Ctrl-C) in the middle of an execution never
# reports a save it may have made as "nothing was saved", so a retry with
# the same `requestId` never applies a change twice (D5, D6).
#
#   python3 -I pen6_shutdown.py
#
# - bootStop: the stop arrives while the session's executor process boots.
# - saveStop: a large save (1500 shapes) is stopped at several points of
#   its run; each answer must match what the backend has, and the retry
#   must either run once (nothing saved), replay, or be refused (outcome
#   unknown) without adding a second copy.
#
# Prints a JSON report; exit status 1 when a check fails.

import json
import sys
import threading
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mcp_client  # noqa: E402
import mcpv  # noqa: E402
from pen6_consistency import restart_mcp  # noqa: E402

BULK = 1500
BULK_CODE = ("for (let i = 0; i < %d; i++) { const r = penpot.createRectangle(); r.name = 'bulk'; r.x = i; }"
             " return 1;") % BULK
CLEAR = "for (const s of penpot.currentPage.findShapes({ name: 'bulk' })) s.remove(); return 1;"


def count(file_id, name):
    data = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))
    page = data["data"]["pages"][0]
    return sum(1 for o in data["data"]["pagesIndex"][page]["objects"].values() if o["name"] == name)


class Shutdown:
    def __init__(self):
        self.ai = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
        self.report = {}

    def run(self, code, session, **kwargs):
        return self.ai.execute_code(code, sessionId=session, **kwargs)[0]

    def interrupted(self, code, session, request_id, after_seconds, file_id):
        """Runs `code`, stops the MCP server `after_seconds` into it, then retries with the same request ID."""
        first = {}

        def call():
            try:
                first["answer"] = self.run(code, session, requestId=request_id, fileId=file_id)
            except Exception as error:  # noqa: BLE001
                first["answer"] = str(error)[:200]

        thread = threading.Thread(target=call)
        thread.start()
        time.sleep(after_seconds)
        restart_mcp(hard=False)
        thread.join()
        self.ai = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
        return first["answer"]

    def retry(self, code, session, request_id, file_id):
        try:
            answer = self.run(code, session, requestId=request_id, fileId=file_id)
            return "replayed" if answer.get("replayed") else "ran"
        except mcp_client.ToolError as error:
            return str(error)[:200]

    def boot_stop(self):
        file_id, _ = mcpv.create_file("pen6-boot-stop")
        code = "const r = penpot.createRectangle(); r.name = 'boot'; return 1;"
        rounds = []
        for attempt in range(3):
            # a new session has no executor process: the stop hits its boot
            session = f"boot-{time.time_ns()}"
            request_id = f"{session}-r"
            answer = self.interrupted(code, session, request_id, 1.5, file_id)
            saved = count(file_id, "boot")
            retry = self.retry(code, session, request_id, file_id)
            rounds.append({"first": answer, "savedByFirst": saved - attempt, "retry": retry,
                           "copies": count(file_id, "boot") - attempt})
        ok = all("[cancelled]" in str(r["first"]) and "nothing was saved" in str(r["first"])
                 and r["savedByFirst"] == 0 and r["retry"] == "ran" and r["copies"] == 1 for r in rounds)
        self.report["bootStop"] = {"ok": ok, "rounds": rounds}

    def save_stop(self):
        file_id, _ = mcpv.create_file("pen6-save-stop")
        session = f"save-{time.time_ns()}"
        self.run("return 1;", session, fileId=file_id)
        started = time.monotonic()
        self.run(BULK_CODE, session)
        total = time.monotonic() - started
        self.run(CLEAR, session)
        rounds = []
        for fraction in (0.6, 0.75, 0.9, 0.97):
            request_id = f"{session}-{fraction}"
            answer = self.interrupted(BULK_CODE, session, request_id, total * fraction, file_id)
            saved = count(file_id, "bulk")
            retry = self.retry(BULK_CODE, session, request_id, file_id)
            final = count(file_id, "bulk")
            text = str(answer)
            consistent = (
                (isinstance(answer, dict) and saved == BULK and retry == "replayed" and final == BULK)
                or ("nothing was saved" in text and saved == 0 and retry == "ran" and final == BULK)
                # no answer, or one saying the save may have landed: the retry is refused either way
                or (("may have been saved" in text or "Remote end closed" in text)
                    and "precondition-failed" in retry and final == saved))
            rounds.append({"fraction": fraction, "first": answer if isinstance(answer, str) else "saved",
                           "savedByFirst": saved, "retry": retry[:80], "final": final, "consistent": consistent})
            self.run(CLEAR, session, fileId=file_id)
        self.report["saveStop"] = {"ok": all(r["consistent"] for r in rounds), "secondsPerRun": round(total, 2),
                                   "rounds": rounds}


def main():
    run = Shutdown()
    for step in (run.boot_stop, run.save_stop):
        try:
            step()
        except Exception as error:  # noqa: BLE001
            run.report[step.__name__] = {"ok": False, "crashed": repr(error)[:600]}
    failed = [name for name, check in run.report.items() if not check["ok"]]
    print(json.dumps({"failed": failed, "checks": run.report}, indent=2, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
