import { createLogger } from "../logger";
import { ExecutorConfig } from "./ExecutorConfig";
import { ExecutorError } from "./ExecutorError";
import type { ExecuteParams, ExecutionResult } from "./ExecutorProtocol";
import { ExecutorProcess } from "./ExecutorProcess";
import { MemoryLedgerStore, RedisLedgerStore, RequestLedger } from "./RequestLedger";

/**
 * One executor session: a process and the queue that runs its executions one at a time.
 */
class ExecutorSession {
    /** tail of the execution queue */
    private tail: Promise<unknown> = Promise.resolve();
    private process: Promise<ExecutorProcess> | null = null;

    constructor(
        public readonly key: string,
        public readonly userKey: string,
        public readonly name: string
    ) {}

    /**
     * The session's process, started on first use and restarted when it has exited (the previous one's
     * storage and open file are then gone).
     */
    async getProcess(config: ExecutorConfig, token: string): Promise<ExecutorProcess> {
        const current = this.process ? await this.process.catch(() => null) : null;
        if (!current || !current.alive) {
            this.process = ExecutorProcess.start(config, this.key, token);
        }
        return this.process!;
    }

    /**
     * Runs `task` after the executions queued before it.
     */
    enqueue<T>(task: () => Promise<T>): Promise<T> {
        const result = this.tail.then(task, task);
        this.tail = result.catch(() => undefined);
        return result;
    }

    get started(): Promise<ExecutorProcess> | null {
        return this.process;
    }
}

/**
 * Executor sessions of all users (D12): one executor process per (user token, session name), so no state is
 * shared between users or sessions. Enforces the D9 limits on concurrent executions and execution time,
 * closes idle sessions, and logs each execution without its code, results or tokens (D9).
 */
export class ExecutorPool {
    private readonly logger = createLogger("ExecutorPool");
    private readonly sessions = new Map<string, ExecutorSession>();
    private readonly runningByUser = new Map<string, number>();
    private running = 0;
    private readonly idleTimer: NodeJS.Timeout;
    private readonly ledger: RequestLedger;
    /** executions in progress, with their request ID records */
    private readonly inProgress = new Set<Promise<unknown>>();
    private closing = false;

    /** how long a shutdown lets the executions in progress end (a save in progress completes) */
    private static readonly SHUTDOWN_GRACE_MS = 3000;

    constructor(private readonly config: ExecutorConfig) {
        this.ledger = new RequestLedger(
            config.redisUri
                ? new RedisLedgerStore(config.redisUri, `penpot-mcp:${config.tenant}:executor-request:`)
                : new MemoryLedgerStore()
        );
        this.idleTimer = setInterval(() => this.closeIdleSessions(), Math.min(config.idleMs, 60_000));
        this.idleTimer.unref();
    }

    /**
     * Runs one execution in the session `sessionName` of the user of `token`.
     *
     * @param token - the user's MCP token
     * @param sessionName - the executor session; each name has its own process, storage and open file
     * @param params - the execution
     * @param signal - aborts the execution before its save (D6)
     * @param requestId - the client's ID of this request; a retry with the same ID within 10 minutes gets the
     *   first run's result instead of running again (D5)
     */
    execute(
        token: string,
        sessionName: string,
        params: ExecuteParams,
        signal?: AbortSignal,
        requestId?: string
    ): Promise<ExecutionResult> {
        const execution = requestId
            ? this.ledger.once(ExecutorConfig.fingerprint(token), requestId, () =>
                  this.enqueue(token, sessionName, params, signal)
              )
            : this.enqueue(token, sessionName, params, signal);
        this.inProgress.add(execution);
        execution.then(
            () => this.inProgress.delete(execution),
            () => this.inProgress.delete(execution)
        );
        return execution;
    }

    private enqueue(
        token: string,
        sessionName: string,
        params: ExecuteParams,
        signal?: AbortSignal
    ): Promise<ExecutionResult> {
        const userKey = ExecutorConfig.fingerprint(token);
        const key = `${userKey}:${sessionName}`;
        let session = this.sessions.get(key);
        if (!session) {
            session = new ExecutorSession(key, userKey, sessionName);
            this.sessions.set(key, session);
        }
        const target = session;
        return target.enqueue(() => this.run(target, token, params, signal));
    }

    private async run(
        session: ExecutorSession,
        token: string,
        params: ExecuteParams,
        signal?: AbortSignal
    ): Promise<ExecutionResult> {
        if (this.closing) {
            // queued behind an execution the shutdown cancelled: do not start another process
            throw new ExecutorError("cancelled", "the MCP server is shutting down");
        }
        this.acquire(session.userKey);
        const started = Date.now();
        let outcome = "ok";
        let result: ExecutionResult | undefined;
        try {
            const process = await session.getProcess(this.config, token);
            result = await process.execute(params, this.config.timeoutMs, signal);
            return result;
        } catch (error) {
            outcome = error instanceof ExecutorError ? error.code : "engine-error";
            throw error;
        } finally {
            this.release(session.userKey);
            this.logger.info(
                "execution user=%s session=%s file=%s ms=%d changes=%d result=%s",
                session.userKey,
                session.name,
                result?.commit?.fileId ?? params.fileId ?? "-",
                Date.now() - started,
                result?.commit?.changedShapeIds.length ?? 0,
                outcome
            );
        }
    }

    private acquire(userKey: string): void {
        const byUser = this.runningByUser.get(userKey) ?? 0;
        if (byUser >= this.config.perUser) {
            throw new ExecutorError(
                "resource-limit",
                `at most ${this.config.perUser} executions per user may run at the same time`
            );
        }
        if (this.running >= this.config.maxExecutions) {
            throw new ExecutorError("resource-limit", "the server is running its maximum number of executions");
        }
        this.runningByUser.set(userKey, byUser + 1);
        this.running++;
    }

    private release(userKey: string): void {
        const byUser = (this.runningByUser.get(userKey) ?? 1) - 1;
        if (byUser > 0) {
            this.runningByUser.set(userKey, byUser);
        } else {
            this.runningByUser.delete(userKey);
        }
        this.running--;
    }

    private async closeIdleSessions(): Promise<void> {
        const now = Date.now();
        for (const [key, session] of this.sessions) {
            const process = await session.started?.catch(() => null);
            if (!process || !process.alive) {
                this.sessions.delete(key);
            } else if (now - process.lastUsed > this.config.idleMs) {
                this.logger.info("closing idle executor session %s", key);
                process.kill(null);
                this.sessions.delete(key);
            }
        }
    }

    /**
     * Ends every executor process. Executions in progress are cancelled (one that is saving completes its
     * save) and their request ID records settled before the ledger closes.
     */
    async close(): Promise<void> {
        clearInterval(this.idleTimer);
        this.closing = true;
        const processes = await Promise.all(
            [...this.sessions.values()].map((session) => session.started?.catch(() => null) ?? null)
        );
        await Promise.all(
            processes.map((process) => process?.shutdown(ExecutorPool.SHUTDOWN_GRACE_MS) ?? Promise.resolve())
        );
        this.sessions.clear();
        await Promise.allSettled([...this.inProgress]);
        await this.ledger.close();
    }
}
