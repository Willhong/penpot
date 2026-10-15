import { Redis } from "ioredis";
import { createLogger } from "../logger";
import { ExecutorError } from "./ExecutorError";
import type { ExecutionResult } from "./ExecutorProtocol";

/**
 * Record of one client request ID (D5): its outcome once known.
 */
type LedgerEntry = { state: "running"; startedAt: number } | { state: "done"; result: ExecutionResult };

/**
 * Storage of request outcomes, keyed by user and request ID, kept for the D5 window.
 */
export interface RequestLedgerStore {
    /** claims the key for a new run; returns the existing entry instead when there is one */
    claim(key: string, ttlMs: number): Promise<LedgerEntry | null>;
    /** records the outcome of a claimed run */
    complete(key: string, result: ExecutionResult, ttlMs: number): Promise<void>;
    /** releases a claimed run that saved nothing, so it may be retried */
    release(key: string): Promise<void>;
    close(): Promise<void>;
}

/**
 * Ledger kept in this process. Lost on restart; used without Redis.
 */
export class MemoryLedgerStore implements RequestLedgerStore {
    private readonly entries = new Map<string, { entry: LedgerEntry; expiresAt: number }>();

    async claim(key: string, ttlMs: number): Promise<LedgerEntry | null> {
        this.prune();
        const existing = this.entries.get(key);
        if (existing) {
            return existing.entry;
        }
        this.entries.set(key, { entry: { state: "running", startedAt: Date.now() }, expiresAt: Date.now() + ttlMs });
        return null;
    }

    async complete(key: string, result: ExecutionResult, ttlMs: number): Promise<void> {
        this.entries.set(key, { entry: { state: "done", result }, expiresAt: Date.now() + ttlMs });
    }

    async release(key: string): Promise<void> {
        this.entries.delete(key);
    }

    async close(): Promise<void> {}

    private prune(): void {
        const now = Date.now();
        for (const [key, { expiresAt }] of this.entries) {
            if (expiresAt <= now) {
                this.entries.delete(key);
            }
        }
    }
}

/**
 * Ledger in Redis, shared by the MCP server instances and kept across restarts.
 */
export class RedisLedgerStore implements RequestLedgerStore {
    private readonly redis: Redis;

    constructor(
        uri: string,
        private readonly prefix: string
    ) {
        this.redis = new Redis(uri, { lazyConnect: false, maxRetriesPerRequest: 2 });
    }

    async claim(key: string, ttlMs: number): Promise<LedgerEntry | null> {
        const entry: LedgerEntry = { state: "running", startedAt: Date.now() };
        const claimed = await this.redis.set(this.prefix + key, JSON.stringify(entry), "PX", ttlMs, "NX");
        if (claimed === "OK") {
            return null;
        }
        const raw = await this.redis.get(this.prefix + key);
        return raw ? (JSON.parse(raw) as LedgerEntry) : null;
    }

    async complete(key: string, result: ExecutionResult, ttlMs: number): Promise<void> {
        const entry: LedgerEntry = { state: "done", result };
        await this.redis.set(this.prefix + key, JSON.stringify(entry), "PX", ttlMs);
    }

    async release(key: string): Promise<void> {
        await this.redis.del(this.prefix + key);
    }

    async close(): Promise<void> {
        this.redis.disconnect();
    }
}

/**
 * Deduplication of retried requests (D5): a request carrying a `requestId` runs once; a retry within the
 * window (10 minutes) gets the first run's result instead of running again, and a retry that arrives while
 * the first run is still going waits for it.
 *
 * A failure that saved nothing is not recorded, so the client may retry it. A run interrupted by a restart
 * leaves its claim behind: a retry then gets an error saying its outcome is unknown, rather than possibly
 * applying the change twice.
 */
export class RequestLedger {
    private readonly logger = createLogger("RequestLedger");
    /** runs of this process, so concurrent retries share them */
    private readonly inFlight = new Map<string, Promise<ExecutionResult>>();

    constructor(
        private readonly store: RequestLedgerStore,
        private readonly ttlMs: number = 10 * 60 * 1000
    ) {}

    /**
     * Runs `run` once per (user, request ID).
     *
     * @param userKey - fingerprint of the user's token
     * @param requestId - the client's request ID
     * @param run - the execution
     */
    async once(userKey: string, requestId: string, run: () => Promise<ExecutionResult>): Promise<ExecutionResult> {
        const key = `${userKey}:${requestId}`;
        const local = this.inFlight.get(key);
        if (local) {
            return this.replay(await local);
        }
        // registered before any await, so a retry arriving meanwhile joins this run
        const promise = this.claimAndRun(key, requestId, run);
        this.inFlight.set(key, promise);
        try {
            return await promise;
        } finally {
            this.inFlight.delete(key);
        }
    }

    private async claimAndRun(
        key: string,
        requestId: string,
        run: () => Promise<ExecutionResult>
    ): Promise<ExecutionResult> {
        const existing = await this.store.claim(key, this.ttlMs);
        if (existing?.state === "done") {
            return this.replay(existing.result);
        }
        if (existing?.state === "running") {
            throw new ExecutorError(
                "precondition-failed",
                `an earlier attempt of request ${requestId} did not finish here (interrupted or still running elsewhere); ` +
                    "its outcome is unknown: read the file before retrying with a new requestId"
            );
        }
        try {
            const result = await run();
            await this.store.complete(key, result, this.ttlMs);
            return result;
        } catch (error) {
            if (error instanceof ExecutorError && error.saved) {
                await this.store.complete(
                    key,
                    { result: null, log: "", commit: null, engine: { frontendVersion: null, renderWasm: null } },
                    this.ttlMs
                );
            } else {
                await this.store.release(key).catch((cause) => this.logger.warn("cannot release %s: %s", key, cause));
            }
            throw error;
        }
    }

    close(): Promise<void> {
        return this.store.close();
    }

    private replay(result: ExecutionResult): ExecutionResult {
        return { ...result, replayed: true };
    }
}
