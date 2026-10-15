import { pathToFileURL } from "node:url";
import type { CommitReport } from "../ExecutorProtocol";

/**
 * Exports of the frontend `:executor` build (`frontend/src/app/executor/api.cljs`).
 */
interface ExecutorBundle {
    boot(options: { token: string; sharedKey: string | null; wasmDir: string }): Promise<{
        profileId: string;
        sessionId: string;
    }>;
    context(): any;
    status(): {
        fileId: string | null;
        pageId: string | null;
        canEdit: boolean;
        revn: number | null;
        frontendVersion: string | null;
    };
    openFile(fileId: string, pageId: string | null): Promise<unknown>;
    beginExecution(): void;
    finishExecution(options: { settleTimeout: number }): Promise<CommitReport>;
    abortExecution(): Promise<void>;
}

/**
 * The headless Penpot workspace of one executor process: the frontend's store, workspace events and plugin
 * API running under Node, with render-wasm booted headless (E4).
 *
 * Wraps the `:executor` build so the rest of the executor deals with typed calls only.
 */
export class HeadlessEngine {
    private constructor(
        private readonly bundle: ExecutorBundle,
        public readonly profileId: string,
        public readonly sessionId: string
    ) {}

    /**
     * Loads the bundle and boots the workspace for the user of `token`.
     *
     * @param bundlePath - path of the build's `executor.js`
     * @param wasmDir - directory holding `render-wasm.js` and `render-wasm.wasm`
     * @param token - the user's MCP token
     * @param sharedKey - the MCP shared key, which lets the backend accept that token (D11)
     */
    static async boot(
        bundlePath: string,
        wasmDir: string,
        token: string,
        sharedKey: string | null
    ): Promise<HeadlessEngine> {
        const bundle = (await import(pathToFileURL(bundlePath).href)) as ExecutorBundle;
        const { profileId, sessionId } = await bundle.boot({ token, sharedKey, wasmDir });
        return new HeadlessEngine(bundle, profileId, sessionId);
    }

    /**
     * The plugin API context (what the plugins runtime receives as `context`).
     */
    context(): any {
        return this.bundle.context();
    }

    status(): ReturnType<ExecutorBundle["status"]> {
        return this.bundle.status();
    }

    async openFile(fileId: string, pageId?: string): Promise<void> {
        await this.bundle.openFile(fileId, pageId ?? null);
    }

    beginExecution(): void {
        this.bundle.beginExecution();
    }

    /**
     * Completes the derived values of the execution and saves it in one request.
     *
     * @param settleTimeoutMs - bound for waiting on layout and text work
     */
    finishExecution(settleTimeoutMs: number): Promise<CommitReport> {
        return this.bundle.finishExecution({ settleTimeout: settleTimeoutMs });
    }

    /**
     * Saves nothing of the execution in progress and reloads the open file.
     */
    abortExecution(): Promise<void> {
        return this.bundle.abortExecution();
    }
}
