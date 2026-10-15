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

    it("refuses to rerun a request whose earlier attempt left no outcome", async () => {
        const store = new MemoryLedgerStore();
        // an attempt that started and was never completed nor released (the server died meanwhile)
        await store.claim("user:r4", 60_000);
        const ledger = new RequestLedger(store);
        let runs = 0;
        await assert.rejects(
            ledger.once("user", "r4", async () => result(++runs)),
            (error: unknown) => error instanceof ExecutorError && error.code === "precondition-failed"
        );
        assert.equal(runs, 0);
    });
});
