import { after, describe, it } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ExecutorConfig } from "./ExecutorConfig";
import { ExecutorError } from "./ExecutorError";
import { ExecutorPool } from "./ExecutorPool";

// A stand-in for the executor process: "quick" answers at once, "hang" never does.
const FAKE_CHILD = `
process.on("disconnect", () => process.exit(0));
process.on("message", (request) => {
    if (request.type === "init") {
        process.send({ id: request.id, ok: true, value: {} });
    } else if (request.type === "execute" && request.params.code === "quick") {
        process.send({ id: request.id, ok: true, value: { result: "done", log: "", commit: null, engine: {} } });
    }
});
`;

describe("ExecutorPool session limits", () => {
    const dir = mkdtempSync(join(tmpdir(), "executor-pool-test-"));
    const childEntry = join(dir, "fake-child.cjs");
    writeFileSync(childEntry, FAKE_CHILD);
    const pools: ExecutorPool[] = [];
    const pool = (limits: Record<string, string>): ExecutorPool => {
        const created = new ExecutorPool(
            new ExecutorConfig({
                PENPOT_MCP_EXECUTOR_CHILD: childEntry,
                PENPOT_MCP_EXECUTOR_BUNDLE: join(dir, "executor.js"),
                PENPOT_MCP_EXECUTOR_WASM_DIR: dir,
                PENPOT_MCP_EXECUTOR_PUBLIC_URI: "http://localhost",
                PENPOT_MCP_EXECUTOR_FS_READ: dir,
                PENPOT_MCP_EXECUTOR_PER_USER: "10",
                ...limits,
            })
        );
        pools.push(created);
        return created;
    };
    const sessions = (target: ExecutorPool): string[] =>
        [...(target as any).sessions.values()].map((session: any) => session.name).sort();
    after(async () => {
        await Promise.all(pools.map((target) => target.close()));
        rmSync(dir, { recursive: true, force: true });
    });

    it("closes the least recently used idle session of the user past the per-user limit", async () => {
        const target = pool({ PENPOT_MCP_EXECUTOR_SESSIONS_PER_USER: "2" });
        await target.execute("alice", "a", { code: "quick" });
        await target.execute("alice", "b", { code: "quick" });
        await target.execute("bob", "a", { code: "quick" });
        await target.execute("alice", "a", { code: "quick" });
        await target.execute("alice", "c", { code: "quick" });
        // alice's "b" was the one idle longest; bob's session is not hers to close
        assert.equal((target as any).sessions.size, 3);
        assert.deepEqual(sessions(target), ["a", "a", "c"]);
    });

    it("refuses a new session when every session of the user is running", async () => {
        const target = pool({ PENPOT_MCP_EXECUTOR_SESSIONS_PER_USER: "2" });
        void target.execute("carol", "a", { code: "hang" }).catch(() => undefined);
        void target.execute("carol", "b", { code: "hang" }).catch(() => undefined);
        await assert.rejects(
            target.execute("carol", "c", { code: "quick" }),
            (error: unknown) => error instanceof ExecutorError && error.code === "resource-limit"
        );
        assert.deepEqual(sessions(target), ["a", "b"]);
    });

    it("closes the least recently used idle session of anyone past the global limit", async () => {
        const target = pool({ PENPOT_MCP_EXECUTOR_SESSIONS_MAX: "2" });
        await target.execute("dave", "x", { code: "quick" });
        await target.execute("erin", "y", { code: "quick" });
        await target.execute("frank", "z", { code: "quick" });
        assert.deepEqual(sessions(target), ["y", "z"]);
    });

    // D9: at most two executions per user at a time, and the server's maximum over everyone
    const started = () => new Promise((resolve) => setTimeout(resolve, 500));
    const refused = (message: string) => (error: unknown) =>
        error instanceof ExecutorError && error.code === "resource-limit" && error.message.includes(message);

    it("refuses a user's third execution at a time, not another user's", async () => {
        const target = pool({ PENPOT_MCP_EXECUTOR_PER_USER: "2" });
        void target.execute("gina", "a", { code: "hang" }).catch(() => undefined);
        void target.execute("gina", "b", { code: "hang" }).catch(() => undefined);
        await started();
        await assert.rejects(target.execute("gina", "c", { code: "quick" }), refused("at most 2 executions per user"));
        assert.equal((await target.execute("hank", "a", { code: "quick" })).result, "done");
    });

    it("refuses any execution past the server's maximum", async () => {
        const target = pool({ PENPOT_MCP_EXECUTOR_MAX: "1" });
        void target.execute("ivy", "a", { code: "hang" }).catch(() => undefined);
        await started();
        await assert.rejects(target.execute("jack", "a", { code: "quick" }), refused("maximum number of executions"));
    });
});
