// shared with the browser plugin, so logs and utilities match (bundled from source, see `vendor.d.ts`)
import { ExecuteCodeTaskConsole } from "@penpot/mcp-plugin/console";
import { PenpotUtils } from "@penpot/mcp-plugin/utils";
import { ExecutorError } from "../ExecutorError";
import type { ExecuteParams, ExecutionResult, ExecutorStatus } from "../ExecutorProtocol";
import { HeadlessEngine } from "./HeadlessEngine";
import { Sandbox, hardenProcessIntrinsics } from "./Sandbox";
import { createServerContext } from "./ServerContext";
import { createServerPluginApi, type ServerPluginApi } from "./ServerPluginApi";

/**
 * Settings of an executor process, read from its environment by the entry point.
 */
export interface ExecutorRuntimeConfig {
    /** path of the frontend `:executor` build's `executor.js` */
    bundlePath: string;
    /** directory holding `render-wasm.js` and `render-wasm.wasm` */
    wasmDir: string;
    /** default bound for waiting on derived values after the code, in ms */
    settleTimeoutMs: number;
}

/**
 * The executor of one user and one executor session (D12): a headless workspace, the server Plugin API on
 * top of it, and a sandbox that runs each execution in a new compartment.
 *
 * Executions run one at a time (the MCP server queues them); `storage` and the open file carry over from one
 * execution to the next.
 */
export class ExecutorRuntime {
    /** contract codes the workspace bundle attaches to its failures */
    private static readonly WORKSPACE_CODES = new Set([
        "forbidden",
        "not-found",
        "validation",
        "revn-conflict",
        "vern-conflict",
        "precondition-failed",
        // derived values that did not finish within the settle bound
        "resource-limit",
    ]);

    private engine!: HeadlessEngine;
    private api!: ServerPluginApi;
    private readonly sandbox = new Sandbox();
    private readonly storage: Record<string, unknown> = {};
    /** phase of the execution in progress, for cancellation (D6) */
    private phase: "idle" | "running" | "saving" = "idle";
    private cancelRequested = false;

    /**
     * @param config - settings of the process
     * @param onSaving - tells the MCP server that the execution starts saving; resolves once it is sent
     */
    constructor(
        private readonly config: ExecutorRuntimeConfig,
        private readonly onSaving: () => Promise<void> = async () => undefined
    ) {}

    /**
     * Boots the workspace for the user of `token` and builds the server Plugin API.
     */
    async init(token: string, sharedKey: string | null): Promise<ExecutorStatus> {
        this.engine = await HeadlessEngine.boot(this.config.bundlePath, this.config.wasmDir, token, sharedKey);
        this.api = createServerPluginApi(
            createServerContext(this.engine.context(), () => this.engine.observedScreen()),
            (shapes) => this.engine.centerShapes(shapes)
        );
        // PenpotUtils refers to the `penpot` global of its own realm
        (globalThis as any).penpot = this.api.penpot;
        (globalThis as any).penpotMgmt = this.api.penpotMgmt;
        hardenProcessIntrinsics();
        return this.status();
    }

    status(): ExecutorStatus {
        const status = this.engine.status();
        return {
            profileId: this.engine.profileId,
            sessionId: this.engine.sessionId,
            fileId: status.fileId,
            pageId: status.pageId,
            revn: status.revn,
        };
    }

    /**
     * Runs one execution: opens the requested file, runs the code, completes the derived values and saves
     * everything the code changed in one request. On a failure before the save, nothing is saved and the
     * open file is reloaded.
     */
    async execute(params: ExecuteParams): Promise<ExecutionResult> {
        if (params.fileId) {
            await this.openFile(params.fileId, params.pageId);
        }
        if (params.ifUnchangedSinceRevn !== undefined) {
            const revn = this.engine.status().revn;
            if (revn !== null && revn > params.ifUnchangedSinceRevn) {
                throw new ExecutorError(
                    "precondition-failed",
                    `the file changed since revn ${params.ifUnchangedSinceRevn} (now ${revn}); the code did not run`
                );
            }
        }

        this.phase = "running";
        this.cancelRequested = false;
        try {
            return await this.run(params);
        } finally {
            this.phase = "idle";
        }
    }

    /**
     * Cancels the execution in progress unless it is saving already (D6). Returns whether it will end with
     * `cancelled` and save nothing.
     */
    cancel(): boolean {
        if (this.phase !== "running") {
            return false;
        }
        this.cancelRequested = true;
        return true;
    }

    private async run(params: ExecuteParams): Promise<ExecutionResult> {
        const flags = this.api.penpot.flags;
        const previousFlags = [flags.naturalChildOrdering, flags.throwValidationErrors];
        flags.naturalChildOrdering = true;
        flags.throwValidationErrors = true;

        // a console per execution: the sandbox hardens what it hands to user code
        const console = new ExecuteCodeTaskConsole();
        this.engine.beginExecution(params.ifUnchangedSinceRevn);
        let result: unknown;
        try {
            result = await this.sandbox.run(params.code, {
                penpot: this.api.penpot,
                penpotMgmt: this.api.penpotMgmt,
                penpotUtils: PenpotUtils,
                storage: this.storage,
                console,
            });
        } catch (error) {
            await this.engine.abortExecution();
            throw this.executionError(error);
        } finally {
            [flags.naturalChildOrdering, flags.throwValidationErrors] = previousFlags;
        }

        if (this.cancelRequested) {
            await this.engine.abortExecution();
            throw new ExecutorError("cancelled", "the execution was cancelled before its save");
        }
        this.phase = "saving";
        await this.onSaving();
        let commit;
        try {
            commit = await this.engine.finishExecution(params.settleTimeoutMs ?? this.config.settleTimeoutMs);
        } catch (error) {
            // the save was refused or failed: drop the local edits so the session matches the backend
            await this.engine.abortExecution().catch(() => undefined);
            throw this.executionError(error);
        }
        return {
            result: ExecutorRuntime.toJson(result),
            log: console.getLog(),
            commit: commit.saved || commit.changedShapeIds.length > 0 ? commit : null,
            engine: { frontendVersion: this.engine.status().frontendVersion, renderWasm: null },
        };
    }

    private async openFile(fileId: string, pageId?: string): Promise<void> {
        try {
            await this.engine.openFile(fileId, pageId);
        } catch (error) {
            const code = (error as { code?: unknown })?.code;
            if (code === "forbidden" || code === "engine-error") {
                throw new ExecutorError(code, String((error as Error).message ?? error));
            }
            // the backend answers "not found" for files the user may not read, too
            throw new ExecutorError("not-found", `cannot open file ${fileId}: ${String(error)}`);
        }
    }

    /**
     * Maps an error thrown by user code: contract errors keep their code, anything else is an
     * `execution-error` carrying the message, as the browser plugin reports it.
     */
    private executionError(error: unknown): ExecutorError {
        if (error instanceof ExecutorError) {
            return error;
        }
        const code = (error as { code?: unknown })?.code;
        const text = error instanceof Error ? error.message : String(error);
        if (/Code: :createShapeFromSvg\b/.test(text)) {
            // 03-runtime-contract §4: an SVG that does not parse is an input problem of its own
            return new ExecutorError("svg-parser", text);
        }
        if (typeof code === "string" && code !== "engine-error" && ExecutorRuntime.WORKSPACE_CODES.has(code)) {
            return new ExecutorError(code as any, (error as Error).message);
        }
        const status = this.engine.status();
        if (status.fileId && !status.canEdit) {
            // the plugin API fails in its own way on a read-only workspace; the contract answers like the
            // backend does to a write without edit rights (03-runtime-contract §7)
            return new ExecutorError(
                "not-found",
                `this user has read-only access to file ${status.fileId}; the code failed with: ${error instanceof Error ? error.message : String(error)}`
            );
        }
        const message = error instanceof Error ? error.message : String(error);
        return new ExecutorError("execution-error", message);
    }

    /**
     * Turns the code's return value into JSON data, as sending it to the MCP server from the browser plugin
     * does. A top-level `Uint8Array` becomes the base64 envelope `{__type: "base64", data}`.
     */
    private static toJson(value: unknown): unknown {
        if (value instanceof Uint8Array) {
            return { __type: "base64", data: Buffer.from(value).toString("base64") };
        }
        if (value === undefined) {
            return undefined;
        }
        return JSON.parse(JSON.stringify(value));
    }
}
