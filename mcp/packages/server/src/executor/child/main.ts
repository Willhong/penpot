/**
 * Entry point of an executor process, started by the MCP server's {@link ExecutorProcess} with
 * `child_process.fork`. Talks to its parent over the IPC channel only.
 *
 * Environment:
 * - `PENPOT_EXECUTOR_BUNDLE`: path of the frontend `:executor` build's `executor.js`
 * - `PENPOT_EXECUTOR_WASM_DIR`: directory of `render-wasm.js` / `render-wasm.wasm`
 * - `PENPOT_EXECUTOR_SETTLE_TIMEOUT_MS`: default bound for waiting on derived values
 * - `PENPOT_PUBLIC_URI`, `PENPOT_FLAGS`, `PENPOT_VERSION`: frontend configuration (read by the bundle)
 *
 * The user's token and the MCP shared key arrive with the `init` request, not through the environment.
 */
import { ExecutorError } from "../ExecutorError";
import type { ExecutorErrorCode, ExecutorErrorData, ExecutorRequest, ExecutorResponse } from "../ExecutorProtocol";
import { ExecutorRuntime } from "./ExecutorRuntime";
import { MemoryStorage } from "./MemoryStorage";
import { repairProcessIntrinsics } from "./Sandbox";

// `penpot.localStorage` lives as long as the executor session (there is no browser profile to keep it in)
(globalThis as any).localStorage = new MemoryStorage();

// before the workspace bundle is imported (see `repairProcessIntrinsics`)
repairProcessIntrinsics();

const runtime = new ExecutorRuntime({
    bundlePath: requireEnv("PENPOT_EXECUTOR_BUNDLE"),
    wasmDir: requireEnv("PENPOT_EXECUTOR_WASM_DIR"),
    settleTimeoutMs: parseInt(process.env.PENPOT_EXECUTOR_SETTLE_TIMEOUT_MS ?? "10000", 10),
});

function requireEnv(name: string): string {
    const value = process.env[name];
    if (!value) {
        throw new Error(`missing environment variable ${name}`);
    }
    return value;
}

const CONTRACT_CODES = new Set<string>([
    "not-found",
    "forbidden",
    "validation",
    "revn-conflict",
    "vern-conflict",
    "precondition-failed",
    "ui-only",
    "resource-limit",
    "cancelled",
    "engine-error",
    "svg-parser",
    "font-unavailable",
    "execution-error",
]);

/**
 * Serializes a failure: contract errors and workspace errors carrying a contract `code` keep it, anything
 * else is an `engine-error`.
 */
function toErrorData(error: unknown): ExecutorErrorData {
    if (error instanceof ExecutorError) {
        return error.toData();
    }
    const code = (error as { code?: unknown })?.code;
    const message = error instanceof Error ? error.message : String(error);
    if (!(typeof code === "string" && CONTRACT_CODES.has(code))) {
        // an unexpected failure: keep its trace in the executor's log (never the user's code or data)
        console.error("[executor] engine error:", error instanceof Error ? error.stack : error);
    }
    return new ExecutorError(
        typeof code === "string" && CONTRACT_CODES.has(code) ? (code as ExecutorErrorCode) : "engine-error",
        message
    ).toData();
}

function reply(response: ExecutorResponse): void {
    process.send!(response);
}

async function handle(request: ExecutorRequest): Promise<unknown> {
    switch (request.type) {
        case "init":
            return runtime.init(request.token, request.sharedKey);
        case "execute":
            return runtime.execute(request.params);
        case "status":
            return runtime.status();
        case "cancel":
            return runtime.cancel();
    }
}

process.on("message", (request: ExecutorRequest) => {
    handle(request).then(
        (value) => reply({ id: request.id, ok: true, value }),
        (error) => reply({ id: request.id, ok: false, error: toErrorData(error) })
    );
});

// the parent going away ends the session
process.on("disconnect", () => process.exit(0));

// An error the workspace code throws outside an execution's promise chain (an observable subscriber, a
// timer) is reported and left behind, as the browser's console does; it does not end the session.
process.on("uncaughtException", (error) => console.error("[executor] uncaught error:", error?.stack ?? error));
process.on("unhandledRejection", (reason) =>
    console.error("[executor] unhandled rejection:", (reason as Error)?.stack ?? reason)
);
