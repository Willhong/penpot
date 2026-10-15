import { randomUUID } from "node:crypto";
import { Redis } from "ioredis";
import { createLogger } from "../logger";
import { ExecutorError } from "./ExecutorError";
import type { ExecutionResult, SaveInfo } from "./ExecutorProtocol";

/**
 * A request ID's run that has no outcome yet: the MCP server instance running it and, once it started saving,
 * what identifies its save.
 */
export type RunningEntry = {
    state: "running";
    startedAt: number;
    instance?: string;
    save?: SaveInfo;
    /** when the save was sent */
    savingAt?: number;
};

/**
 * Record of one client request ID (D5): its run in progress, or its outcome once known.
 */
export type LedgerEntry = RunningEntry | { state: "done"; result: ExecutionResult };

/**
 * What the backend's record of file changes says about a save whose answer was lost.
 */
export type SaveOutcome = { saved: true; revn: number } | { saved: false } | { saved: "unknown"; reason: string };

/**
 * Where a request ID stands, as {@link RequestLedger.status} reports it.
 */
export type RequestStatus =
    | { status: "none" }
    | { status: "running" }
    | { status: "done"; result: ExecutionResult }
    | { status: "interrupted"; saved: boolean | "unknown"; revn?: number; reason?: string };

/**
 * Storage of request outcomes, keyed by user and request ID, kept for the D5 window, and of the MCP server
 * instances that are alive.
 */
export interface RequestLedgerStore {
    /** claims the key for a new run; returns the existing entry instead when there is one */
    claim(key: string, entry: RunningEntry, ttlMs: number): Promise<LedgerEntry | null>;
    /** the entry of the key */
    get(key: string): Promise<LedgerEntry | null>;
    /** updates the claimed run of the key */
    mark(key: string, entry: RunningEntry, ttlMs: number): Promise<void>;
    /** replaces the entry of the key by `entry` if it is still `expected`; returns whether it did */
    replace(key: string, expected: LedgerEntry, entry: LedgerEntry, ttlMs: number): Promise<boolean>;
    /** records the outcome of a claimed run */
    complete(key: string, result: ExecutionResult, ttlMs: number): Promise<void>;
    /** releases a claimed run that saved nothing, so it may be retried */
    release(key: string): Promise<void>;
    /** records that the instance is alive for `ttlMs` */
    beat(instance: string, ttlMs: number): Promise<void>;
    /** whether the instance recorded itself alive and has not expired */
    alive(instance: string): Promise<boolean>;
    close(): Promise<void>;
}

/**
 * Ledger kept in this process. Lost on restart; used without Redis.
 */
export class MemoryLedgerStore implements RequestLedgerStore {
    private readonly entries = new Map<string, { entry: LedgerEntry; expiresAt: number }>();
    private readonly instances = new Map<string, number>();

    async claim(key: string, entry: RunningEntry, ttlMs: number): Promise<LedgerEntry | null> {
        this.prune();
        const existing = this.entries.get(key);
        if (existing) {
            return existing.entry;
        }
        this.entries.set(key, { entry, expiresAt: Date.now() + ttlMs });
        return null;
    }

    async get(key: string): Promise<LedgerEntry | null> {
        this.prune();
        return this.entries.get(key)?.entry ?? null;
    }

    async mark(key: string, entry: RunningEntry, ttlMs: number): Promise<void> {
        if (this.entries.has(key)) {
            this.entries.set(key, { entry, expiresAt: Date.now() + ttlMs });
        }
    }

    async replace(key: string, expected: LedgerEntry, entry: LedgerEntry, ttlMs: number): Promise<boolean> {
        const current = this.entries.get(key)?.entry;
        if (JSON.stringify(current) !== JSON.stringify(expected)) {
            return false;
        }
        this.entries.set(key, { entry, expiresAt: Date.now() + ttlMs });
        return true;
    }

    async complete(key: string, result: ExecutionResult, ttlMs: number): Promise<void> {
        this.entries.set(key, { entry: { state: "done", result }, expiresAt: Date.now() + ttlMs });
    }

    async release(key: string): Promise<void> {
        this.entries.delete(key);
    }

    async beat(instance: string, ttlMs: number): Promise<void> {
        this.instances.set(instance, Date.now() + ttlMs);
    }

    async alive(instance: string): Promise<boolean> {
        return (this.instances.get(instance) ?? 0) > Date.now();
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

    /** sets KEYS[1] to ARGV[2] (expiring after ARGV[3] ms) only while it holds ARGV[1] */
    private static readonly REPLACE =
        "if redis.call('GET', KEYS[1]) == ARGV[1] then " +
        "redis.call('SET', KEYS[1], ARGV[2], 'PX', ARGV[3]) return 1 else return 0 end";

    constructor(
        uri: string,
        private readonly prefix: string
    ) {
        this.redis = new Redis(uri, { lazyConnect: false, maxRetriesPerRequest: 2 });
    }

    async claim(key: string, entry: RunningEntry, ttlMs: number): Promise<LedgerEntry | null> {
        const claimed = await this.redis.set(this.prefix + key, JSON.stringify(entry), "PX", ttlMs, "NX");
        if (claimed === "OK") {
            return null;
        }
        return this.get(key);
    }

    async get(key: string): Promise<LedgerEntry | null> {
        const raw = await this.redis.get(this.prefix + key);
        return raw ? (JSON.parse(raw) as LedgerEntry) : null;
    }

    async mark(key: string, entry: RunningEntry, ttlMs: number): Promise<void> {
        await this.redis.set(this.prefix + key, JSON.stringify(entry), "PX", ttlMs, "XX");
    }

    async replace(key: string, expected: LedgerEntry, entry: LedgerEntry, ttlMs: number): Promise<boolean> {
        const done = await this.redis.eval(
            RedisLedgerStore.REPLACE,
            1,
            this.prefix + key,
            JSON.stringify(expected),
            JSON.stringify(entry),
            ttlMs
        );
        return done === 1;
    }

    async complete(key: string, result: ExecutionResult, ttlMs: number): Promise<void> {
        const entry: LedgerEntry = { state: "done", result };
        await this.redis.set(this.prefix + key, JSON.stringify(entry), "PX", ttlMs);
    }

    async release(key: string): Promise<void> {
        await this.redis.del(this.prefix + key);
    }

    async beat(instance: string, ttlMs: number): Promise<void> {
        await this.redis.set(`${this.prefix}instance:${instance}`, "1", "PX", ttlMs);
    }

    async alive(instance: string): Promise<boolean> {
        return (await this.redis.exists(`${this.prefix}instance:${instance}`)) === 1;
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
 * or crash of its MCP server instance leaves its claim behind; once that instance stops beating, the run's
 * outcome is found out (PEN-20): a run that had not started saving saved nothing and is run again; for one
 * that had, the backend's record of file changes tells whether its save went through (the retry then gets
 * that, without the code's return value). Only when that record cannot tell does a retry get an error
 * saying the outcome is unknown, rather than possibly applying the change twice.
 */
export class RequestLedger {
    private readonly logger = createLogger("RequestLedger");
    /** runs of this process, so concurrent retries share them */
    private readonly inFlight = new Map<string, Promise<ExecutionResult>>();
    /** identifies this MCP server instance in the claims of its runs */
    readonly instance = randomUUID();
    private readonly heartbeat: NodeJS.Timeout;

    /**
     * @param store - where the records live
     * @param ttlMs - how long an outcome is kept (D5 window)
     * @param heartbeatMs - how long an instance counts as alive after its last beat; it beats three times
     *   as often
     */
    constructor(
        private readonly store: RequestLedgerStore,
        private readonly ttlMs: number = 10 * 60 * 1000,
        private readonly heartbeatMs: number = 15_000
    ) {
        this.beat();
        this.heartbeat = setInterval(() => this.beat(), Math.max(1, Math.floor(heartbeatMs / 3)));
        this.heartbeat.unref();
    }

    /**
     * Runs `run` once per (user, request ID).
     *
     * @param userKey - fingerprint of the user's token
     * @param requestId - the client's request ID
     * @param run - the execution, given a callback that records what identifies its save before it is sent
     * @param probe - finds out from the backend whether a save went through
     */
    async once(
        userKey: string,
        requestId: string,
        run: (recordSave: (save: SaveInfo) => Promise<void>) => Promise<ExecutionResult>,
        probe?: (save: SaveInfo) => Promise<SaveOutcome>
    ): Promise<ExecutionResult> {
        const key = `${userKey}:${requestId}`;
        const local = this.inFlight.get(key);
        if (local) {
            return this.replay(await local);
        }
        // registered before any await, so a retry arriving meanwhile joins this run
        const promise = this.claimAndRun(key, requestId, run, probe);
        this.inFlight.set(key, promise);
        try {
            return await promise;
        } finally {
            this.inFlight.delete(key);
        }
    }

    /**
     * Where the request ID of a user stands, without running anything. A run interrupted by a restart is
     * looked up in the backend's record of file changes.
     */
    async status(userKey: string, requestId: string, probe?: (save: SaveInfo) => Promise<SaveOutcome>) {
        const key = `${userKey}:${requestId}`;
        if (this.inFlight.has(key)) {
            return { status: "running" } satisfies RequestStatus;
        }
        const entry = await this.store.get(key);
        if (!entry) {
            return { status: "none" } satisfies RequestStatus;
        }
        if (entry.state === "done") {
            return { status: "done", result: entry.result } satisfies RequestStatus;
        }
        const outcome = await this.interrupted(entry, probe);
        if (outcome === "running") {
            return { status: "running" } satisfies RequestStatus;
        }
        return {
            status: "interrupted",
            saved: outcome.saved,
            ...(outcome.saved === true ? { revn: outcome.revn } : {}),
            ...(outcome.saved === "unknown" ? { reason: outcome.reason } : {}),
        } satisfies RequestStatus;
    }

    private async claimAndRun(
        key: string,
        requestId: string,
        run: (recordSave: (save: SaveInfo) => Promise<void>) => Promise<ExecutionResult>,
        probe?: (save: SaveInfo) => Promise<SaveOutcome>
    ): Promise<ExecutionResult> {
        const claim: RunningEntry = { state: "running", startedAt: Date.now(), instance: this.instance };
        const existing = await this.store.claim(key, claim, this.ttlMs);
        if (existing?.state === "done") {
            return this.replay(existing.result);
        }
        if (existing) {
            const outcome = await this.interrupted(existing, probe);
            if (outcome === "running") {
                throw new ExecutorError(
                    "precondition-failed",
                    `request ${requestId} is still running on another MCP server instance; ` +
                        "retry it later with the same requestId"
                );
            }
            if (outcome.saved === "unknown") {
                throw new ExecutorError(
                    "precondition-failed",
                    `an earlier attempt of request ${requestId} was interrupted and its outcome is unknown ` +
                        `(${outcome.reason}): read the file before retrying with a new requestId`
                );
            }
            if (outcome.saved) {
                const result = RequestLedger.recovered(existing.save!, outcome.revn);
                await this.store.replace(key, existing, { state: "done", result }, this.ttlMs);
                return this.replay(result);
            }
            // it saved nothing: run it now, unless another retry took it over first
            if (!(await this.store.replace(key, existing, claim, this.ttlMs))) {
                throw new ExecutorError(
                    "precondition-failed",
                    `request ${requestId} is being retried elsewhere; retry it later with the same requestId`
                );
            }
        }
        const recordSave = (save: SaveInfo) =>
            this.store
                .mark(key, { ...claim, save, savingAt: Date.now() }, this.ttlMs)
                .catch((cause) => this.logger.warn("cannot record the save of %s: %s", key, cause));
        try {
            const result = await run(recordSave);
            await this.store.complete(key, result, this.ttlMs);
            return result;
        } catch (error) {
            if (error instanceof ExecutorError && error.saved === "unknown") {
                // keep the claim: a retry must not apply the change a second time; it finds out the outcome
                // once the save is recorded
            } else if (error instanceof ExecutorError && error.saved) {
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

    /**
     * The outcome of a run claimed and not finished: `"running"` while its instance is alive (and, for this
     * instance, while it runs it), else what its save did.
     */
    private async interrupted(
        entry: RunningEntry,
        probe?: (save: SaveInfo) => Promise<SaveOutcome>
    ): Promise<SaveOutcome | "running"> {
        if (!entry.instance) {
            return { saved: "unknown", reason: "it was recorded by an older MCP server" };
        }
        // a run of this instance is in `inFlight` while it goes; one that is not was left behind by a failure
        if (entry.instance !== this.instance && (await this.store.alive(entry.instance))) {
            return "running";
        }
        if (!entry.save) {
            // Its executor ends with its MCP server before sending any save. A run of this instance always
            // records its save before sending it; one left behind without a record did not get that far
            // only if the record itself failed.
            return entry.instance !== this.instance
                ? { saved: false }
                : { saved: "unknown", reason: "its save was not recorded" };
        }
        if (!probe) {
            return { saved: "unknown", reason: "the backend cannot be asked" };
        }
        const outcome = await probe(entry.save).catch((cause) => ({
            saved: "unknown" as const,
            reason: String(cause),
        }));
        if (outcome.saved === false && Date.now() - (entry.savingAt ?? 0) < RequestLedger.SAVE_SETTLE_MS) {
            // the save request may still be on its way to the backend
            return { saved: "unknown", reason: "its save may still be in progress; ask again in a moment" };
        }
        return outcome;
    }

    /** how long after a save was sent its absence from the backend's record means it did not go through */
    static SAVE_SETTLE_MS = 30_000;

    /**
     * The result handed to a retry of a run whose save went through before its answer was lost: the commit,
     * without the code's return value and log, which were not kept.
     */
    private static recovered(save: SaveInfo, revn: number): ExecutionResult {
        return {
            result: null,
            log: "",
            commit: {
                saved: true,
                fileId: save.fileId,
                revnBefore: save.revnBefore,
                revn,
                changedShapeIds: [],
                lagged: 0,
                computed: { layout: true, text: true, bool: true, componentSync: true },
                pending: null,
                warnings: [
                    {
                        code: "result-lost",
                        message:
                            "the run was interrupted after its save went through; its return value and log were lost",
                    },
                ],
            },
            engine: { frontendVersion: null, renderWasm: null },
        };
    }

    private beat(): void {
        this.store
            .beat(this.instance, this.heartbeatMs)
            .catch((cause) => this.logger.warn("cannot record this instance alive: %s", cause));
    }

    async close(): Promise<void> {
        clearInterval(this.heartbeat);
        // the runs of this instance are over: a retry need not wait for its heartbeats to lapse
        await this.store.beat(this.instance, 1).catch(() => undefined);
        await this.store.close();
    }

    private replay(result: ExecutionResult): ExecutionResult {
        return { ...result, replayed: true };
    }
}
