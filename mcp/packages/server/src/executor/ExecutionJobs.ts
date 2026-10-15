import { randomUUID } from "node:crypto";
import { ExecutorError } from "./ExecutorError";
import type { ExecutionResult, ExecutorErrorData } from "./ExecutorProtocol";

/** where an execution run as a job stands (03-runtime-contract §5) */
export type JobStatus = "pending" | "running" | "done" | "error" | "cancelled";

/** what a job not over yet is doing: waiting for its session, running the code, or saving */
export type JobProgress = "queued" | "running" | "saving";

/**
 * What a client reads of a job (03-runtime-contract §5).
 */
export interface JobView {
    jobId: string;
    status: JobStatus;
    /** what the job is doing, until it is over */
    progress?: JobProgress;
    createdAt: string;
    finishedAt?: string;
    /** the execution's result, once done */
    result?: ExecutionResult;
    /** why it failed or was cancelled */
    error?: ExecutorErrorData;
}

interface Job {
    id: string;
    ownerKey: string;
    status: JobStatus;
    progress?: JobProgress;
    createdAt: number;
    finishedAt?: number;
    result?: ExecutionResult;
    error?: ExecutorErrorData;
    controller: AbortController;
}

/**
 * Callbacks an execution run as a job reports its progress through.
 */
export interface JobReporter {
    /** the execution left the session's queue and runs */
    started(): void;
    /** the execution started saving */
    saving(): void;
}

/**
 * Executions that run in the background (03-runtime-contract §5): the client gets a job ID at once, then
 * reads the job's status and result, or cancels it, with the ID. A job is visible to the user who started it
 * only, and is kept for `ttlMs` once over.
 *
 * Jobs live in this MCP server instance, like the executor sessions they run in.
 */
export class ExecutionJobs {
    private readonly jobs = new Map<string, Job>();

    constructor(private readonly ttlMs: number = 10 * 60 * 1000) {}

    /**
     * Starts `run` in the background for the user of `ownerKey`.
     *
     * @param run - the execution, given an abort signal for cancellation (D6) and the progress callbacks
     */
    start(ownerKey: string, run: (signal: AbortSignal, progress: JobReporter) => Promise<ExecutionResult>): JobView {
        this.prune();
        const job: Job = {
            id: randomUUID(),
            ownerKey,
            status: "pending",
            progress: "queued",
            createdAt: Date.now(),
            controller: new AbortController(),
        };
        this.jobs.set(job.id, job);
        const progress: JobReporter = {
            started: () => {
                if (job.progress === "queued") {
                    job.status = "running";
                    job.progress = "running";
                }
            },
            saving: () => {
                if (job.progress === "running") job.progress = "saving";
            },
        };
        run(job.controller.signal, progress).then(
            (result) => this.finish(job, "done", { result }),
            (error) => {
                const data =
                    error instanceof ExecutorError
                        ? error.toData()
                        : { code: "engine-error" as const, message: String(error), saved: false };
                this.finish(job, data.code === "cancelled" ? "cancelled" : "error", { error: data });
            }
        );
        return this.view(job);
    }

    /**
     * The job `id` of the user of `ownerKey`.
     *
     * @throws ExecutorError `not-found` when there is no such job of that user
     */
    get(ownerKey: string, id: string): JobView {
        return this.view(this.find(ownerKey, id));
    }

    /**
     * Asks the job to stop: before its save it ends `cancelled` and saves nothing; once saving it completes
     * (D6). Returns the job as it stands.
     */
    cancel(ownerKey: string, id: string): JobView {
        const job = this.find(ownerKey, id);
        if (job.progress === "queued" || job.progress === "running") {
            job.controller.abort();
        }
        return this.view(job);
    }

    private find(ownerKey: string, id: string): Job {
        this.prune();
        const job = this.jobs.get(id);
        if (!job || job.ownerKey !== ownerKey) {
            throw new ExecutorError("not-found", `there is no job ${id} of this user`);
        }
        return job;
    }

    private finish(job: Job, status: JobStatus, outcome: Pick<Job, "result" | "error">): void {
        job.status = status;
        job.progress = undefined;
        job.finishedAt = Date.now();
        Object.assign(job, outcome);
    }

    private view(job: Job): JobView {
        return {
            jobId: job.id,
            status: job.status,
            ...(job.progress ? { progress: job.progress } : {}),
            createdAt: new Date(job.createdAt).toISOString(),
            ...(job.finishedAt ? { finishedAt: new Date(job.finishedAt).toISOString() } : {}),
            ...(job.result ? { result: job.result } : {}),
            ...(job.error ? { error: job.error } : {}),
        };
    }

    private prune(): void {
        const now = Date.now();
        for (const [id, job] of this.jobs) {
            if (job.finishedAt && now - job.finishedAt > this.ttlMs) {
                this.jobs.delete(id);
            }
        }
    }
}
