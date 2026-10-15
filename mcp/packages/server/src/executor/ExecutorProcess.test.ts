import { after, describe, it } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ExecutorConfig } from "./ExecutorConfig";
import { ExecutorError } from "./ExecutorError";
import { ExecutorProcess } from "./ExecutorProcess";

// A stand-in for the executor process: the code of an execution names what it does.
//   "hang": runs until cancelled; "save-hang": starts saving and never ends;
//   "save-finish": starts saving and answers after 300 ms; a cancel ends a run that is not saving.
const FAKE_CHILD = `
let running = null;
process.on("SIGINT", () => undefined);
process.on("disconnect", () => process.exit(0));
process.on("message", (request) => {
    if (request.type === "init") {
        process.send({ id: request.id, ok: true, value: {} });
    } else if (request.type === "execute") {
        running = { id: request.id, saving: request.params.code.startsWith("save") };
        if (running.saving) {
            process.send({ notice: "saving" });
        }
        if (request.params.code === "save-finish") {
            setTimeout(() => process.send({ id: request.id, ok: true, value: { result: "saved" } }), 300);
        }
    } else if (request.type === "cancel") {
        const cancelled = running !== null && !running.saving;
        process.send({ id: request.id, ok: true, value: cancelled });
        if (cancelled) {
            const message = "the execution was cancelled before its save";
            process.send({ id: running.id, ok: false, error: { code: "cancelled", message, saved: false } });
        }
    }
});
`;

describe("ExecutorProcess", () => {
    const dir = mkdtempSync(join(tmpdir(), "executor-process-test-"));
    const childEntry = join(dir, "fake-child.cjs");
    writeFileSync(childEntry, FAKE_CHILD);
    const config = new ExecutorConfig({
        PENPOT_MCP_EXECUTOR_CHILD: childEntry,
        PENPOT_MCP_EXECUTOR_BUNDLE: join(dir, "executor.js"),
        PENPOT_MCP_EXECUTOR_WASM_DIR: dir,
        PENPOT_MCP_EXECUTOR_PUBLIC_URI: "http://localhost",
        PENPOT_MCP_EXECUTOR_FS_READ: dir,
    });
    after(() => rmSync(dir, { recursive: true, force: true }));

    const failure = async (promise: Promise<unknown>): Promise<ExecutorError> => {
        try {
            await promise;
        } catch (error) {
            assert.ok(error instanceof ExecutorError);
            return error;
        }
        assert.fail("the execution succeeded");
    };

    it("reports nothing saved when the process ends before saving", async () => {
        const process = await ExecutorProcess.start(config, "a", "token");
        const error = await failure(process.execute({ code: "hang" }, 300));
        assert.equal(error.code, "resource-limit");
        assert.equal(error.saved, false);
    });

    it("reports an unknown outcome when the process ends while saving", async () => {
        const process = await ExecutorProcess.start(config, "b", "token");
        const error = await failure(process.execute({ code: "save-hang" }, 300));
        assert.equal(error.code, "resource-limit");
        assert.equal(error.saved, "unknown");
        assert.match(String(error), /may have been saved/);
    });

    it("cancels a running execution on shutdown", async () => {
        const process = await ExecutorProcess.start(config, "c", "token");
        const execution = failure(process.execute({ code: "hang" }, 10_000));
        const started = Date.now();
        await process.shutdown(3000);
        const error = await execution;
        assert.equal(error.code, "cancelled");
        assert.equal(error.saved, false);
        assert.ok(Date.now() - started < 1000);
        assert.equal(process.alive, false);
    });

    it("lets a save in progress complete on shutdown", async () => {
        const process = await ExecutorProcess.start(config, "d", "token");
        const execution = process.execute({ code: "save-finish" }, 10_000);
        await new Promise((resolve) => setTimeout(resolve, 50));
        await process.shutdown(3000);
        assert.deepEqual(await execution, { result: "saved" });
        assert.equal(process.alive, false);
    });

    it("ends a save that outlasts the shutdown grace with an unknown outcome", async () => {
        const process = await ExecutorProcess.start(config, "e", "token");
        const execution = failure(process.execute({ code: "save-hang" }, 10_000));
        await new Promise((resolve) => setTimeout(resolve, 50));
        await process.shutdown(200);
        const error = await execution;
        assert.equal(error.code, "cancelled");
        assert.equal(error.saved, "unknown");
    });
});
