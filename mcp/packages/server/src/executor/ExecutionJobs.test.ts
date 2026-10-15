import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { ExecutionJobs } from "./ExecutionJobs";
import { ExecutorError } from "./ExecutorError";
import type { ExecutionResult } from "./ExecutorProtocol";

const result = (value: unknown): ExecutionResult => ({
    result: value,
    log: "",
    commit: null,
    engine: { frontendVersion: null, renderWasm: null },
});
const tick = (ms = 5) => new Promise((resolve) => setTimeout(resolve, ms));

describe("ExecutionJobs", () => {
    it("reports a job through its phases to its result", async () => {
        const jobs = new ExecutionJobs();
        let release!: () => void;
        const job = jobs.start("alice", async (_signal, progress) => {
            await tick();
            progress.started();
            await new Promise<void>((resolve) => (release = resolve));
            progress.saving();
            return result(7);
        });
        assert.equal(job.status, "pending");
        assert.equal(job.progress, "queued");
        await tick(20);
        assert.equal(jobs.get("alice", job.jobId).status, "running");
        assert.equal(jobs.get("alice", job.jobId).progress, "running");
        release();
        await tick();
        const done = jobs.get("alice", job.jobId);
        assert.equal(done.status, "done");
        assert.equal(done.progress, undefined);
        assert.equal(done.result?.result, 7);
        assert.ok(done.finishedAt);
    });

    it("keeps jobs to their owner", () => {
        const jobs = new ExecutionJobs();
        const job = jobs.start("alice", async () => result(1));
        assert.throws(
            () => jobs.get("bob", job.jobId),
            (error: unknown) => error instanceof ExecutorError && error.code === "not-found"
        );
        assert.throws(() => jobs.cancel("bob", job.jobId));
    });

    it("cancels a running job through its signal", async () => {
        const jobs = new ExecutionJobs();
        const job = jobs.start("alice", (signal, progress) => {
            progress.started();
            return new Promise((_, reject) =>
                signal.addEventListener("abort", () => reject(new ExecutorError("cancelled", "stopped")))
            );
        });
        await tick();
        jobs.cancel("alice", job.jobId);
        await tick();
        const cancelled = jobs.get("alice", job.jobId);
        assert.equal(cancelled.status, "cancelled");
        assert.equal(cancelled.error?.code, "cancelled");
    });

    it("records a failure with its contract code", async () => {
        const jobs = new ExecutionJobs();
        const job = jobs.start("alice", async () => {
            throw new ExecutorError("validation", "bad value");
        });
        await tick();
        const failed = jobs.get("alice", job.jobId);
        assert.equal(failed.status, "error");
        assert.equal(failed.error?.code, "validation");
    });
});
