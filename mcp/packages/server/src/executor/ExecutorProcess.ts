import { fork, type ChildProcess } from "node:child_process";
import { createLogger } from "../logger";
import { ExecutorError } from "./ExecutorError";
import type {
    ExecuteParams,
    ExecutionResult,
    ExecutorNotice,
    ExecutorRequest,
    ExecutorResponse,
    ExecutorStatus,
} from "./ExecutorProtocol";
import type { ExecutorConfig } from "./ExecutorConfig";

type Pending = { resolve: (value: unknown) => void; reject: (error: Error) => void };

/** a request without its correlation ID, which {@link ExecutorProcess} assigns */
type RequestBody = ExecutorRequest extends infer R ? (R extends ExecutorRequest ? Omit<R, "id"> : never) : never;

/**
 * Handle of one executor process: the headless workspace of one user and one executor session (D12).
 *
 * The process gets no secrets through its environment and a bounded heap; its user's token reaches it
 * through the `init` request. Requests are correlated by ID. Executions are not queued here: the caller
 * ({@link ExecutorPool}) runs one at a time.
 */
export class ExecutorProcess {
    private readonly logger = createLogger("ExecutorProcess");
    private readonly child: ChildProcess;
    private readonly pending = new Map<number, Pending>();
    private nextId = 1;
    private exited = false;
    private initialized = false;
    private exitReason: ExecutorError | null = null;
    /** whether the execution in progress has started saving */
    private saving = false;
    /** told when the execution in progress starts saving */
    private onSaving: (() => void) | undefined;
    private readonly exitedPromise: Promise<void>;

    /** time of the last request, for idle eviction */
    public lastUsed = Date.now();

    private constructor(
        private readonly config: ExecutorConfig,
        public readonly key: string
    ) {
        this.child = fork(config.childEntry, [], {
            // only what the executor needs: no MCP server secrets, no user tokens
            env: {
                PATH: process.env.PATH ?? "",
                NODE_ENV: process.env.NODE_ENV ?? "production",
                PENPOT_EXECUTOR_BUNDLE: config.bundlePath,
                PENPOT_EXECUTOR_WASM_DIR: config.wasmDir,
                PENPOT_EXECUTOR_SETTLE_TIMEOUT_MS: String(config.settleTimeoutMs),
                // the bundle builds the links it hands out on the users' address; it reaches the backend
                // at the executor's (internal) one
                PENPOT_PUBLIC_URI: config.uiUri,
                PENPOT_EXECUTOR_BACKEND_URI: config.publicUri,
                PENPOT_FLAGS: config.flags,
                PENPOT_VERSION: config.version,
            },
            // The process boundary is the security boundary (D12), not the SES compartment alone: the
            // Node permission model limits it to reading the code it runs, with no file writes, no child
            // processes and no worker threads. Network egress is limited by the deployment (PEN-21).
            execArgv: [
                `--max-old-space-size=${config.heapMb}`,
                "--permission",
                ...config.fsRead.map((path) => `--allow-fs-read=${path}`),
            ],
            stdio: ["ignore", "inherit", "inherit", "ipc"],
            serialization: "advanced",
        });
        this.child.on("message", (message: ExecutorResponse | ExecutorNotice) =>
            "notice" in message ? this.savingStarted() : this.onResponse(message)
        );
        // "close" comes after the IPC messages the process sent before it ended, such as a saving notice
        this.exitedPromise = new Promise((resolve) =>
            this.child.on("close", (code, signal) => {
                this.onExit(code, signal);
                resolve();
            })
        );
    }

    /**
     * Starts an executor process and boots its workspace for the user of `token`.
     */
    static async start(config: ExecutorConfig, key: string, token: string): Promise<ExecutorProcess> {
        const process = new ExecutorProcess(config, key);
        try {
            await process.request<ExecutorStatus>({ type: "init", token, sharedKey: config.sharedKey });
            process.initialized = true;
        } catch (error) {
            process.kill(null);
            throw error;
        }
        return process;
    }

    get alive(): boolean {
        return !this.exited;
    }

    /**
     * Runs one execution. When it exceeds `timeoutMs`, the process is killed and the execution fails with
     * `resource-limit`; nothing is saved, since an execution saves only at its end, unless it was saving
     * already (then the error says the changes may have been saved).
     */
    async execute(
        params: ExecuteParams,
        timeoutMs: number,
        signal?: AbortSignal,
        onSaving?: () => void
    ): Promise<ExecutionResult> {
        this.saving = false;
        this.onSaving = onSaving;
        try {
            return await this.request<ExecutionResult>({ type: "execute", params }, timeoutMs, signal);
        } finally {
            this.saving = false;
            this.onSaving = undefined;
        }
    }

    private savingStarted(): void {
        this.saving = true;
        this.onSaving?.();
    }

    /**
     * Ends the process for a shutdown of the MCP server: cancels the execution in progress (D6), lets it
     * end for at most `graceMs` (an execution that is saving completes its save), then ends the process.
     */
    async shutdown(graceMs: number): Promise<void> {
        if (this.exited) {
            return;
        }
        if (this.pending.size > 0) {
            this.cancel();
            const deadline = Date.now() + graceMs;
            while (this.pending.size > 0 && !this.exited && Date.now() < deadline) {
                await new Promise((resolve) => setTimeout(resolve, 50));
            }
        }
        this.kill(new ExecutorError("cancelled", "the MCP server is shutting down"));
        await this.exitedPromise;
    }

    status(): Promise<ExecutorStatus> {
        return this.request<ExecutorStatus>({ type: "status" });
    }

    /**
     * Cancels the running execution (D6): before its save it ends with `cancelled` and saves nothing; once
     * saving, it completes with its result. A process too busy to answer (user code that never yields) is
     * still before its save, so it is ended.
     */
    private cancel(): void {
        let answered = false;
        const timer = setTimeout(() => {
            if (!answered) {
                this.kill(new ExecutorError("cancelled", "the execution was cancelled before its save"));
            }
        }, ExecutorProcess.CANCEL_ANSWER_MS);
        this.request<boolean>({ type: "cancel" })
            .then(() => {
                answered = true;
                clearTimeout(timer);
            })
            .catch(() => clearTimeout(timer));
    }

    /** how long a cancelled execution's process may take to acknowledge before it is ended */
    private static readonly CANCEL_ANSWER_MS = 2000;

    /**
     * Ends the process. Pending requests fail with `reason`, or `cancelled` when none is given.
     */
    kill(reason: ExecutorError | null): void {
        if (!this.exited) {
            this.exitReason = reason ?? new ExecutorError("cancelled", "the executor session was closed");
            this.child.kill("SIGKILL");
        }
    }

    private request<T>(message: RequestBody, timeoutMs?: number, signal?: AbortSignal): Promise<T> {
        if (this.exited) {
            return Promise.reject(this.exitReason ?? new ExecutorError("engine-error", "the executor has exited"));
        }
        this.lastUsed = Date.now();
        const id = this.nextId++;
        return new Promise<T>((resolve, reject) => {
            let timer: NodeJS.Timeout | undefined;
            const onAbort = () => this.cancel();
            const settle = () => {
                clearTimeout(timer);
                signal?.removeEventListener("abort", onAbort);
                this.pending.delete(id);
            };
            this.pending.set(id, {
                resolve: (value) => {
                    settle();
                    resolve(value as T);
                },
                reject: (error) => {
                    settle();
                    reject(error);
                },
            });
            if (timeoutMs) {
                timer = setTimeout(
                    () =>
                        this.kill(
                            new ExecutorError(
                                "resource-limit",
                                `the execution exceeded the time limit of ${timeoutMs} ms`
                            )
                        ),
                    timeoutMs
                );
            }
            signal?.addEventListener("abort", onAbort, { once: true });
            this.child.send({ ...message, id } as ExecutorRequest);
            if (signal?.aborted) {
                // aborted while the process was starting: the listener above will not fire
                onAbort();
            }
        });
    }

    private onResponse(response: ExecutorResponse): void {
        const pending = this.pending.get(response.id);
        if (!pending) {
            return;
        }
        if (response.ok) {
            pending.resolve(response.value);
        } else {
            pending.reject(ExecutorError.fromData(response.error));
        }
    }

    private onExit(code: number | null, signal: NodeJS.Signals | null): void {
        this.exited = true;
        const stopped = signal === "SIGINT" || signal === "SIGTERM";
        let reason =
            this.exitReason ??
            (stopped
                ? new ExecutorError("cancelled", "the MCP server is shutting down")
                : this.initialized
                  ? new ExecutorError(
                        "resource-limit",
                        `the executor process ended (code ${code}, signal ${signal}); it may have run out of memory`
                    )
                  : new ExecutorError("engine-error", `the executor process failed to start (code ${code})`));
        if (this.saving) {
            // the save request may have reached the backend
            reason = new ExecutorError(reason.code, reason.message, "unknown");
        }
        this.exitReason = reason;
        // the key begins with the user's key: log its short form only
        const [user, ...session] = this.key.split(":");
        this.logger.info(
            "Executor %s:%s exited: code=%s signal=%s reason=%s",
            user.slice(0, 12),
            session.join(":"),
            code,
            signal,
            reason.code
        );
        for (const pending of [...this.pending.values()]) {
            pending.reject(reason);
        }
        this.pending.clear();
    }
}
