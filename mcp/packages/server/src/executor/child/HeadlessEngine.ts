import { pathToFileURL } from "node:url";
import type { CommitReport } from "../ExecutorProtocol";

/**
 * Screen of a browser tab of the same user on the open file, from its pointer updates (D8 (b)).
 */
export interface ObservedScreen {
    pageId: string | null;
    zoom: number;
    /** visible area of the page, in page coordinates */
    vbox: { x: number; y: number; width: number; height: number };
    /** the tab's effective UI theme */
    theme: string | null;
    /** when the tab reported it, in ms since the epoch */
    updatedAt: number | null;
}

/**
 * Exports of the frontend `:executor` build (`frontend/src/app/executor/api.cljs`).
 */
interface ExecutorBundle {
    boot(options: { token: string; sharedKey: string | null; wasmDir: string; backendUri: string | null }): Promise<{
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
    observedScreen(): ObservedScreen | null;
    centerShapes(shapes: unknown[]): { x: number; y: number } | null;
    viewerQuery(): string | null;
    beginExecution(options: { ifUnchangedSinceRevn?: number }): void;
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
     * @param backendUri - the backend as reached from here, when it differs from the bundle's public URI
     */
    static async boot(
        bundlePath: string,
        wasmDir: string,
        token: string,
        sharedKey: string | null,
        backendUri: string | null
    ): Promise<HeadlessEngine> {
        const bundle = (await import(pathToFileURL(bundlePath).href)) as ExecutorBundle;
        const { profileId, sessionId } = await bundle.boot({ token, sharedKey, wasmDir, backendUri });
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

    /**
     * Query of the viewer URL of the current page (`?screen=viewer&...`), or null with no file open.
     */
    viewerQuery(): string | null {
        return this.bundle.viewerQuery() ?? null;
    }

    /**
     * Center of the shapes, as `penpot.utils.geometry.center` computes it.
     */
    centerShapes(shapes: unknown[]): { x: number; y: number } | null {
        return this.bundle.centerShapes(shapes);
    }

    /**
     * Screen of a browser tab of the same user on the open file, or null when no such tab reported one.
     */
    observedScreen(): ObservedScreen | null {
        return this.bundle.observedScreen() ?? null;
    }

    async openFile(fileId: string, pageId?: string): Promise<void> {
        await this.bundle.openFile(fileId, pageId ?? null);
    }

    /**
     * Starts an execution.
     *
     * @param ifUnchangedSinceRevn - D4 precondition, checked again right before the save
     */
    beginExecution(ifUnchangedSinceRevn?: number): void {
        this.bundle.beginExecution({ ifUnchangedSinceRevn });
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
