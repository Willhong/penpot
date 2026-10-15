/**
 * Entry point of an executor process, started by the MCP server's {@link ExecutorProcess} with
 * `child_process.fork`. Talks to its parent over the IPC channel only.
 *
 * Environment:
 * - `PENPOT_EXECUTOR_BUNDLE`: path of the frontend `:executor` build's `executor.js`
 * - `PENPOT_EXECUTOR_WASM_DIR`: directory of `render-wasm.js` / `render-wasm.wasm`
 * - `PENPOT_EXECUTOR_SETTLE_TIMEOUT_MS`: default bound for waiting on derived values
 * - `PENPOT_PUBLIC_URI`, `PENPOT_FLAGS`, `PENPOT_VERSION`: frontend configuration (read by the bundle);
 *   the public URI is the one users open Penpot at, so the links handed out work for them
 * - `PENPOT_EXECUTOR_BACKEND_URI`: the backend as reached from the executor, when it differs
 *
 * The user's token and the MCP shared key arrive with the `init` request, not through the environment.
 */
import { ExecutorError } from "../ExecutorError";
import type {
    ExecutorErrorCode,
    ExecutorErrorData,
    ExecutorNotice,
    ExecutorRequest,
    ExecutorResponse,
} from "../ExecutorProtocol";
import { installCjsInterop } from "./CjsInterop";
import { ExecutorRuntime } from "./ExecutorRuntime";
import { MemoryStorage } from "./MemoryStorage";
import { repairProcessIntrinsics } from "./Sandbox";

// `penpot.localStorage` lives as long as the executor session (there is no browser profile to keep it in)
(globalThis as any).localStorage = new MemoryStorage();

// before the workspace bundle is imported (see `repairProcessIntrinsics`)
repairProcessIntrinsics();

// before the workspace bundle is imported: its CommonJS npm imports (see `installCjsInterop`)
installCjsInterop(requireEnv("PENPOT_EXECUTOR_BUNDLE"));

const runtime = new ExecutorRuntime(
    {
        bundlePath: requireEnv("PENPOT_EXECUTOR_BUNDLE"),
        wasmDir: requireEnv("PENPOT_EXECUTOR_WASM_DIR"),
        settleTimeoutMs: parseInt(process.env.PENPOT_EXECUTOR_SETTLE_TIMEOUT_MS ?? "10000", 10),
        uiUri: requireEnv("PENPOT_PUBLIC_URI"),
        backendUri: process.env.PENPOT_EXECUTOR_BACKEND_URI ?? null,
    },
    // sent before the save request leaves, so the server never takes an ended save for "nothing saved"
    () => {
        holdStopSignals();
        return new Promise((resolve) => process.send!({ notice: "saving" } satisfies ExecutorNotice, () => resolve()));
    }
);

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

function reply(response: ExecutorResponse): Promise<void> {
    return new Promise((resolve) => process.send!(response, () => resolve()));
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
    handle(request)
        .then(
            (value) => reply({ id: request.id, ok: true, value }),
            (error) => reply({ id: request.id, ok: false, error: toErrorData(error) })
        )
        .then(() => {
            if (request.type === "execute") {
                releaseStopSignals();
            }
        });
});

// A stop signal (a Ctrl-C reaches the whole process group) ends the process at once, which cancels an
// execution before its save: the default action, which needs no turn of the event loop. While saving, the
// signal waits until the save is answered, so its outcome is known.
let deferredStop: NodeJS.Signals | null = null;
const deferStop = (signal: NodeJS.Signals) => {
    deferredStop = signal;
};

function holdStopSignals(): void {
    process.on("SIGINT", deferStop);
    process.on("SIGTERM", deferStop);
}

function releaseStopSignals(): void {
    process.off("SIGINT", deferStop);
    process.off("SIGTERM", deferStop);
    if (deferredStop) {
        process.kill(process.pid, deferredStop);
    }
}

// the parent going away ends the session
process.on("disconnect", () => process.exit(0));

// An error the workspace code throws outside an execution's promise chain (an observable subscriber, a
// timer) is reported and left behind, as the browser's console does; it does not end the session.
process.on("uncaughtException", (error) => console.error("[executor] uncaught error:", error?.stack ?? error));
process.on("unhandledRejection", (reason) =>
    console.error("[executor] unhandled rejection:", (reason as Error)?.stack ?? reason)
);
