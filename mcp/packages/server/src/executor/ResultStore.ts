import { randomUUID } from "node:crypto";
import { Redis } from "ioredis";
import { ExecutorError } from "./ExecutorError";

/**
 * Storage of result bytes, keyed by owner and result ID, kept for a while.
 */
export interface ResultBackend {
    put(key: string, bytes: Buffer, ttlMs: number): Promise<void>;
    get(key: string): Promise<Buffer | null>;
    close(): Promise<void>;
}

/**
 * Results kept in this process. Lost on restart; used without Redis.
 */
export class MemoryResultBackend implements ResultBackend {
    private readonly entries = new Map<string, { bytes: Buffer; expiresAt: number }>();

    async put(key: string, bytes: Buffer, ttlMs: number): Promise<void> {
        this.prune();
        this.entries.set(key, { bytes, expiresAt: Date.now() + ttlMs });
    }

    async get(key: string): Promise<Buffer | null> {
        this.prune();
        return this.entries.get(key)?.bytes ?? null;
    }

    async close(): Promise<void> {
        this.entries.clear();
    }

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
 * Results in Redis, readable from every MCP server instance and kept across restarts.
 */
export class RedisResultBackend implements ResultBackend {
    private readonly redis: Redis;

    constructor(
        uri: string,
        private readonly prefix: string
    ) {
        this.redis = new Redis(uri, { lazyConnect: false, maxRetriesPerRequest: 2 });
    }

    async put(key: string, bytes: Buffer, ttlMs: number): Promise<void> {
        await this.redis.set(this.prefix + key, bytes, "PX", ttlMs);
    }

    async get(key: string): Promise<Buffer | null> {
        return this.redis.getBuffer(this.prefix + key);
    }

    async close(): Promise<void> {
        this.redis.disconnect();
    }
}

/** a result handed out by URL instead of in the response */
export interface StoredResult {
    __type: "resource";
    /** download URL; the request must carry the same user token */
    url: string;
    /** size in bytes */
    size: number;
    /** media type, sniffed from the bytes */
    mtype: string;
    /** when the URL stops working (ISO 8601) */
    expiresAt: string;
}

/**
 * Delivery of large results (03-runtime-contract §5): bytes up to `inlineLimit` stay in the response as a
 * base64 envelope (`{"__type":"base64","data":…}`); larger ones are kept for `ttlMs` and the response carries
 * a URL that only their owner can download.
 */
export class ResultStore {
    /** the largest result kept */
    static readonly MAX_BYTES = 64 * 1024 * 1024;

    constructor(
        private readonly backend: ResultBackend,
        readonly inlineLimit: number = 1024 * 1024,
        private readonly ttlMs: number = 15 * 60 * 1000
    ) {}

    /**
     * Replaces a base64 envelope larger than the inline limit by a {@link StoredResult}; returns any other
     * value unchanged.
     *
     * @param value - a result value
     * @param ownerKey - fingerprint of the user's token
     * @param baseUrl - base URL of this MCP server as the client reaches it
     */
    async deliver(value: unknown, ownerKey: string, baseUrl: string): Promise<unknown> {
        const envelope = value as { __type?: unknown; data?: unknown };
        if (envelope?.__type !== "base64" || typeof envelope.data !== "string") {
            return value;
        }
        const size = Math.floor((envelope.data.length * 3) / 4);
        if (size <= this.inlineLimit) {
            return value;
        }
        return this.store(Buffer.from(envelope.data, "base64"), ownerKey, baseUrl);
    }

    /**
     * Keeps `bytes` for their owner and returns how to download them.
     */
    async store(bytes: Buffer, ownerKey: string, baseUrl: string): Promise<StoredResult> {
        if (bytes.length > ResultStore.MAX_BYTES) {
            throw new ExecutorError(
                "resource-limit",
                `the result has ${bytes.length} bytes; at most ${ResultStore.MAX_BYTES} are kept`
            );
        }
        const id = randomUUID();
        await this.backend.put(`${ownerKey}:${id}`, bytes, this.ttlMs);
        return {
            __type: "resource",
            url: `${baseUrl.replace(/\/+$/, "")}/results/${id}`,
            size: bytes.length,
            mtype: ResultStore.sniff(bytes),
            expiresAt: new Date(Date.now() + this.ttlMs).toISOString(),
        };
    }

    /**
     * The bytes of result `id` when `ownerKey` owns it and it has not expired, else null.
     */
    get(ownerKey: string, id: string): Promise<Buffer | null> {
        return this.backend.get(`${ownerKey}:${id}`);
    }

    close(): Promise<void> {
        return this.backend.close();
    }

    /**
     * Media type of the formats Penpot exports, from their first bytes.
     */
    static sniff(bytes: Buffer): string {
        const head = bytes.subarray(0, 16);
        const ascii = head.toString("latin1");
        if (head[0] === 0x89 && ascii.startsWith("PNG", 1)) return "image/png";
        if (head[0] === 0xff && head[1] === 0xd8) return "image/jpeg";
        if (ascii.startsWith("RIFF") && ascii.slice(8, 12) === "WEBP") return "image/webp";
        if (ascii.startsWith("%PDF")) return "application/pdf";
        if (ascii.startsWith("PK")) return "application/zip";
        if (/^\s*(<\?xml|<svg)/.test(bytes.subarray(0, 256).toString("utf8"))) return "image/svg+xml";
        return "application/octet-stream";
    }
}
