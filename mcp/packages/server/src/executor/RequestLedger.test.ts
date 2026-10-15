import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { ExecutorError } from "./ExecutorError";
import type { ExecutionResult } from "./ExecutorProtocol";
import { MemoryLedgerStore, RequestLedger } from "./RequestLedger";

const result = (value: unknown): ExecutionResult => ({
    result: value,
    log: "",
    commit: null,
    engine: { frontendVersion: null, renderWasm: null },
});

describe("RequestLedger", () => {
    it("runs a request once and replays its result to a retry", async () => {
        const ledger = new RequestLedger(new MemoryLedgerStore());
        let runs = 0;
        const run = async () => result(++runs);
        const first = await ledger.once("user", "r1", run);
        const retry = await ledger.once("user", "r1", run);
        assert.equal(runs, 1);
        assert.equal(first.result, 1);
        assert.equal(retry.result, 1);
        assert.equal(retry.replayed, true);
        assert.equal(first.replayed, undefined);
    });

    it("lets a concurrent retry wait for the run in flight", async () => {
        const ledger = new RequestLedger(new MemoryLedgerStore());
        let runs = 0;
        const run = () => new Promise<ExecutionResult>((resolve) => setTimeout(() => resolve(result(++runs)), 20));
        const [a, b] = await Promise.all([ledger.once("user", "r2", run), ledger.once("user", "r2", run)]);
        assert.equal(runs, 1);
        assert.equal(a.result, b.result);
    });

    it("keeps users apart", async () => {
        const ledger = new RequestLedger(new MemoryLedgerStore());
        let runs = 0;
        const run = async () => result(++runs);
        await ledger.once("alice", "same-id", run);
        await ledger.once("bob", "same-id", run);
        assert.equal(runs, 2);
    });

    it("forgets a failure that saved nothing, so it can be retried", async () => {
        const ledger = new RequestLedger(new MemoryLedgerStore());
        let runs = 0;
        const failing = async () => {
            runs++;
            throw new ExecutorError("execution-error", "boom");
        };
        await assert.rejects(ledger.once("user", "r3", failing), /boom/);
        const retry = await ledger.once("user", "r3", async () => result(++runs));
        assert.equal(runs, 2);
        assert.equal(retry.replayed, undefined);
    });

    it("keeps the claim of a run that may have saved, so a retry does not apply it twice", async () => {
        const ledger = new RequestLedger(new MemoryLedgerStore());
        let runs = 0;
        await assert.rejects(
            ledger.once("user", "r5", async () => {
                runs++;
                throw new ExecutorError("resource-limit", "ended while saving", "unknown");
            })
        );
        await assert.rejects(
            ledger.once("user", "r5", async () => result(++runs)),
            (error: unknown) => error instanceof ExecutorError && error.code === "precondition-failed"
        );
        assert.equal(runs, 1);
    });

    it("refuses to rerun a request recorded without its instance", async () => {
        const store = new MemoryLedgerStore();
        // an attempt recorded by an older server, never completed nor released
        await store.claim("user:r4", { state: "running", startedAt: Date.now() }, 60_000);
        const ledger = new RequestLedger(store);
        let runs = 0;
        await assert.rejects(
            ledger.once("user", "r4", async () => result(++runs)),
            (error: unknown) => error instanceof ExecutorError && error.code === "precondition-failed"
        );
        assert.equal(runs, 0);
    });

    it("tells a retry to wait while the instance running the request is alive", async () => {
        const store = new MemoryLedgerStore();
        await store.beat("other", 60_000);
        await store.claim("user:r6", { state: "running", startedAt: Date.now(), instance: "other" }, 60_000);
        const ledger = new RequestLedger(store);
        await assert.rejects(
            ledger.once("user", "r6", async () => result(1)),
            (error: unknown) => error instanceof ExecutorError && /still running/.test(error.message)
        );
    });

    it("reruns a request whose instance died before it started saving", async () => {
        const store = new MemoryLedgerStore();
        await store.claim("user:r7", { state: "running", startedAt: Date.now(), instance: "gone" }, 60_000);
        const ledger = new RequestLedger(store);
        const retry = await ledger.once("user", "r7", async () => result("ran"));
        assert.equal(retry.result, "ran");
        assert.equal(retry.replayed, undefined);
    });

    it("answers a retry with the save an interrupted run made, from the backend's record", async () => {
        const store = new MemoryLedgerStore();
        const save = { fileId: "f", revnBefore: 4, sessionId: "s" };
        await store.claim("user:r8", { state: "running", startedAt: 0, instance: "gone", save, savingAt: 0 }, 60_000);
        const ledger = new RequestLedger(store);
        let runs = 0;
        const probed: unknown[] = [];
        const retry = await ledger.once(
            "user",
            "r8",
            async () => result(++runs),
            async (info) => {
                probed.push(info);
                return { saved: true, revn: 5 };
            }
        );
        assert.equal(runs, 0);
        assert.deepEqual(probed, [save]);
        assert.equal(retry.replayed, true);
        assert.equal(retry.commit?.revn, 5);
        assert.equal(retry.commit?.warnings?.[0].code, "result-lost");
        // recorded: the next retry does not ask again
        const again = await ledger.once("user", "r8", async () => result(++runs));
        assert.equal(again.commit?.revn, 5);
    });

    it("reruns an interrupted run whose save did not go through, once it had time to arrive", async () => {
        const store = new MemoryLedgerStore();
        const save = { fileId: "f", revnBefore: 4, sessionId: "s" };
        const notSaved = async () => ({ saved: false as const });
        await store.claim("user:r9", { state: "running", startedAt: 0, instance: "gone", save, savingAt: 0 }, 60_000);
        await store.claim(
            "user:r10",
            { state: "running", startedAt: 0, instance: "gone", save, savingAt: Date.now() },
            60_000
        );
        const ledger = new RequestLedger(store);
        const retry = await ledger.once("user", "r9", async () => result("ran"), notSaved);
        assert.equal(retry.result, "ran");
        // a save sent a moment ago may still be on its way
        await assert.rejects(
            ledger.once("user", "r10", async () => result("ran"), notSaved),
            (error: unknown) => error instanceof ExecutorError && /in progress/.test(error.message)
        );
    });

    it("records what identifies a save before it is sent", async () => {
        const store = new MemoryLedgerStore();
        const ledger = new RequestLedger(store);
        const save = { fileId: "f", revnBefore: 2, sessionId: "s" };
        await ledger.once("user", "r11", async (recordSave) => {
            await recordSave(save);
            const entry = await store.get("user:r11");
            assert.equal(entry?.state, "running");
            assert.deepEqual(entry?.state === "running" ? entry.save : null, save);
            return result(1);
        });
        assert.equal((await store.get("user:r11"))?.state, "done");
    });

    it("reports where a request ID stands without running it", async () => {
        const store = new MemoryLedgerStore();
        const ledger = new RequestLedger(store);
        assert.deepEqual(await ledger.status("user", "unknown"), { status: "none" });
        await ledger.once("user", "r12", async () => result(3));
        const done = await ledger.status("user", "r12");
        assert.equal(done.status, "done");
        const save = { fileId: "f", revnBefore: 1, sessionId: "s" };
        await store.claim("user:r13", { state: "running", startedAt: 0, instance: "gone", save, savingAt: 0 }, 60_000);
        assert.deepEqual(await ledger.status("user", "r13", async () => ({ saved: true, revn: 2 })), {
            status: "interrupted",
            saved: true,
            revn: 2,
        });
    });
});
