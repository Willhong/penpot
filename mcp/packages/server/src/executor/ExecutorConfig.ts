import { createHash, hkdfSync } from "node:crypto";
import { realpathSync } from "node:fs";
import { createRequire } from "node:module";
import { cpus, totalmem } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

/**
 * Settings of the server-side executor, read from the environment.
 *
 * - `PENPOT_MCP_EXECUTOR`: `server` runs `execute_code` in executor processes instead of the browser plugin;
 *   `optional` keeps the plugin by default and lets a client choose the executor with `?executor=server`
 * - `PENPOT_MCP_EXECUTOR_BUNDLE`: path of the frontend `:executor` build's `executor.js`
 * - `PENPOT_MCP_EXECUTOR_WASM_DIR`: directory of `render-wasm.js` / `render-wasm.wasm`
 * - `PENPOT_MCP_EXECUTOR_PUBLIC_URI`: backend URI the executor talks to (the internal one in a deployment)
 * - `PENPOT_MCP_SHARED_KEY`: the backend's `mcp` shared key (D11); derived from `PENPOT_SECRET_KEY` otherwise
 * - `PENPOT_MCP_EXECUTOR_FS_READ`: comma-separated directories the executor process may read (Node permission
 *   model); default: the frontend checkout holding the bundle, the wasm directory and this package
 * - limits (D9): `PENPOT_MCP_EXECUTOR_TIMEOUT_S` (120), `PENPOT_MCP_EXECUTOR_HEAP_MB` (512, see below),
 *   `PENPOT_MCP_EXECUTOR_PER_USER` (2), `PENPOT_MCP_EXECUTOR_MAX` (CPU count),
 *   `PENPOT_MCP_EXECUTOR_IDLE_S` (900, idle sessions are closed)
 * - live sessions, one process each (about 0.5–0.7 GB): `PENPOT_MCP_EXECUTOR_SESSIONS_PER_USER` (4),
 *   `PENPOT_MCP_EXECUTOR_SESSIONS_MAX` (one per GB of memory); past them the least recently used idle
 *   session is closed
 */
export class ExecutorConfig {
    /** entry point of the executor process (`dist/executor-child.js`, next to the server bundle) */
    readonly childEntry: string;
    readonly bundlePath: string;
    readonly wasmDir: string;
    readonly publicUri: string;
    readonly flags: string;
    readonly version: string;
    readonly sharedKey: string | null;
    readonly fsRead: string[];
    readonly timeoutMs: number;
    readonly heapMb: number;
    readonly perUser: number;
    readonly maxExecutions: number;
    readonly idleMs: number;
    readonly sessionsPerUser: number;
    readonly maxSessions: number;
    readonly settleTimeoutMs: number;
    /** Redis for the request ledger (D5), shared by MCP server instances; in memory without it */
    readonly redisUri: string | null;
    readonly tenant: string;

    constructor(env: Record<string, string | undefined>) {
        const here = dirname(fileURLToPath(import.meta.url));
        this.childEntry = env.PENPOT_MCP_EXECUTOR_CHILD ?? resolve(here, "executor-child.js");
        this.bundlePath = ExecutorConfig.require(env, "PENPOT_MCP_EXECUTOR_BUNDLE");
        this.wasmDir = ExecutorConfig.require(env, "PENPOT_MCP_EXECUTOR_WASM_DIR");
        this.publicUri = ExecutorConfig.require(env, "PENPOT_MCP_EXECUTOR_PUBLIC_URI");
        this.flags = env.PENPOT_FLAGS ?? "";
        this.version = env.PENPOT_VERSION ?? "";
        this.sharedKey = env.PENPOT_MCP_SHARED_KEY ?? ExecutorConfig.deriveSharedKey(env.PENPOT_SECRET_KEY);
        this.fsRead = env.PENPOT_MCP_EXECUTOR_FS_READ
            ? env.PENPOT_MCP_EXECUTOR_FS_READ.split(",").map((path) => resolve(path.trim()))
            : [
                  // the bundle's npm imports resolve in the frontend checkout's node_modules
                  resolve(dirname(this.bundlePath), "..", ".."),
                  resolve(this.wasmDir),
                  // the child bundle's package, whose `node_modules` links `ses` ...
                  resolve(dirname(this.childEntry), ".."),
                  // ... into the pnpm store
                  ExecutorConfig.packageRoot("ses"),
              ];
        this.timeoutMs = 1000 * ExecutorConfig.int(env.PENPOT_MCP_EXECUTOR_TIMEOUT_S, 120);
        // D9 set 256 MB, to be adjusted once measured: the workspace alone takes about 285 MB of V8 heap
        // (release build, one-shape file; 350 MB with the development build), see 03-runtime-contract §2
        this.heapMb = ExecutorConfig.int(env.PENPOT_MCP_EXECUTOR_HEAP_MB, 512);
        this.perUser = ExecutorConfig.int(env.PENPOT_MCP_EXECUTOR_PER_USER, 2);
        this.maxExecutions = ExecutorConfig.int(env.PENPOT_MCP_EXECUTOR_MAX, cpus().length);
        this.idleMs = 1000 * ExecutorConfig.int(env.PENPOT_MCP_EXECUTOR_IDLE_S, 900);
        this.sessionsPerUser = ExecutorConfig.int(env.PENPOT_MCP_EXECUTOR_SESSIONS_PER_USER, 4);
        // an executor process takes about 0.5-0.7 GB (03-runtime-contract §2, PEN-3 measurements)
        this.maxSessions = ExecutorConfig.int(
            env.PENPOT_MCP_EXECUTOR_SESSIONS_MAX,
            Math.max(2, Math.floor(totalmem() / 1024 ** 3))
        );
        this.settleTimeoutMs = ExecutorConfig.int(env.PENPOT_MCP_EXECUTOR_SETTLE_TIMEOUT_MS, 10000);
        this.redisUri = env.PENPOT_MCP_REDIS_URI ?? null;
        this.tenant = env.PENPOT_TENANT ?? "default";
    }

    /**
     * Indicates whether executor processes are available, as configured by `PENPOT_MCP_EXECUTOR`.
     */
    static isEnabled(env: Record<string, string | undefined>): boolean {
        return env.PENPOT_MCP_EXECUTOR === "server" || env.PENPOT_MCP_EXECUTOR === "optional";
    }

    /**
     * Indicates whether `execute_code` runs in an executor when the client does not choose.
     */
    static isDefault(env: Record<string, string | undefined>): boolean {
        return env.PENPOT_MCP_EXECUTOR === "server";
    }

    /**
     * Derives the `mcp` shared key from the backend secret key, the way the backend derives the keys it is
     * not given explicitly (HKDF-BLAKE2b-512, salt = key name, 32 bytes, base64url).
     */
    static deriveSharedKey(secretKey: string | undefined): string | null {
        if (!secretKey) {
            return null;
        }
        return Buffer.from(hkdfSync("blake2b512", secretKey, "mcp", "", 32)).toString("base64url");
    }

    /**
     * Short, non-reversible fingerprint of a token, for keys and log lines (D9: tokens are never logged).
     */
    static fingerprint(token: string): string {
        return createHash("sha256").update(token).digest("hex").slice(0, 12);
    }

    /**
     * The directory a package's dependencies resolve from: the pnpm virtual store, which keeps each
     * dependency in its own directory, or the plain `node_modules` holding the package.
     */
    private static packageRoot(name: string): string {
        const entry = realpathSync(createRequire(import.meta.url).resolve(name));
        const store = "/node_modules/.pnpm/";
        const index = entry.indexOf(store);
        if (index >= 0) {
            return entry.slice(0, index + store.length - 1);
        }
        return entry.slice(0, entry.lastIndexOf("/node_modules/") + "/node_modules".length);
    }

    private static require(env: Record<string, string | undefined>, name: string): string {
        const value = env[name];
        if (!value) {
            throw new Error(`${name} must be set when PENPOT_MCP_EXECUTOR is enabled`);
        }
        return value;
    }

    private static int(value: string | undefined, fallback: number): number {
        const parsed = value === undefined ? NaN : parseInt(value, 10);
        return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
    }
}
