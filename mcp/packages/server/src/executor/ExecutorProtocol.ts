/**
 * Messages exchanged between the MCP server and an executor process over the Node IPC channel,
 * and the result envelope of one execution (03-runtime-contract §3).
 *
 * The executor process runs the Penpot workspace headless for one user and one executor session (D12);
 * see `mcp/docs/server-mcp/`.
 */

/**
 * Error codes of 03-runtime-contract §7.
 */
export type ExecutorErrorCode =
    | "not-found"
    | "forbidden"
    | "validation"
    | "revn-conflict"
    | "vern-conflict"
    | "precondition-failed"
    | "ui-only"
    | "resource-limit"
    | "cancelled"
    | "engine-error"
    | "svg-parser"
    | "font-unavailable"
    | "execution-error";

/**
 * Serializable description of a failed request.
 */
export interface ExecutorErrorData {
    code: ExecutorErrorCode;
    message: string;
    /**
     * whether anything was saved before the failure: false except for a failure after the save, and
     * "unknown" when the process ended while saving (the backend may have applied the save)
     */
    saved: SavedState;
}

export type SavedState = boolean | "unknown";

/**
 * Commit report of a write: what was saved and which derived values were completed.
 */
export interface CommitReport {
    saved: boolean;
    fileId: string | null;
    revnBefore: number | null;
    revn: number | null;
    changedShapeIds: string[];
    /** number of changes the save held, derived ones included; at most the server's limit (D9) */
    changes?: number;
    /** number of changes of other sessions the backend applied in between */
    lagged: number;
    /** always all true: an execution whose derived values do not finish fails with `resource-limit` instead */
    computed: { layout: boolean; text: boolean; bool: boolean; componentSync: boolean };
    /** always null, see `computed` */
    pending?: Record<string, string[]> | null;
    warnings?: { code: string; shapeId?: string; fontId?: string; message?: string }[];
    /** calls shown on the user's tabs with "AI follow" on (PEN-24); moved to {@link ExecutionResult.follow} */
    follow?: FollowReport | null;
}

/**
 * What an execution showed on the screens of the user's browser tabs with "AI follow" on (PEN-24).
 */
export interface FollowReport {
    /** tabs of the user on the file that follow; 0 when none did */
    tabs: number;
    /** the calls shown, in order: `page`, `select`, `center`, `zoom`, ..., `show-changes` */
    actions: string[];
}

/**
 * Engine versions reported with every result.
 */
export interface EngineInfo {
    frontendVersion: string | null;
    renderWasm: string | null;
}

/**
 * Result envelope of one `execute_code` run.
 */
export interface ExecutionResult {
    /** the value returned by the user code, JSON-compatible */
    result: unknown;
    /** captured console output */
    log: string;
    /** commit report; null when the execution changed nothing */
    commit: CommitReport | null;
    engine: EngineInfo;
    /** true when this is the recorded result of an earlier run with the same `requestId` (D5) */
    replayed?: boolean;
    /** what the execution showed on the user's tabs with "AI follow" on, when it moved any screen (PEN-24) */
    follow?: FollowReport;
}

/**
 * Parameters of one execution.
 */
export interface ExecuteParams {
    /** the code: the body of an async function */
    code: string;
    /** file to open before running the code; the session's current file otherwise */
    fileId?: string;
    /** page to open with `fileId` */
    pageId?: string;
    /** bound for waiting on derived values (layout, text) after the code, in ms */
    settleTimeoutMs?: number;
    /**
     * Optional precondition (D4): run and save only if the file is still at this revn, i.e. nobody changed it
     * since the client read it; `precondition-failed` otherwise.
     */
    ifUnchangedSinceRevn?: number;
    /**
     * Instead of running `code`: undo or redo the last saved execution of this session in the file (PEN-20).
     * Refused with `precondition-failed` when another session changed what it would revert since.
     */
    history?: "undo" | "redo";
}

/**
 * Status of an executor session.
 */
export interface ExecutorStatus {
    profileId: string;
    sessionId: string;
    fileId: string | null;
    pageId: string | null;
    revn: number | null;
}

/**
 * Request sent by the MCP server to an executor process.
 */
export type ExecutorRequest =
    | { id: number; type: "init"; token: string; sharedKey: string | null }
    | { id: number; type: "execute"; params: ExecuteParams }
    | { id: number; type: "status" }
    /** cancels the running execution if it has not started saving (D6); answers whether it did */
    | { id: number; type: "cancel" };

/**
 * Notice sent by an executor process outside any response: the execution in progress starts saving, so
 * from then on its process must not be ended as if nothing was saved.
 */
export type ExecutorNotice = { notice: "saving"; save?: SaveInfo };

/**
 * The MCP server's answer to a saving notice: the save is recorded (its request ID's ledger entry knows how to
 * find it), so the executor may send it.
 */
export type ExecutorAck = { ack: "saving" };

/**
 * What identifies a save in the backend's record of file changes: the file, its revn before the save, and the
 * executor's session, which the backend records with each change. Lets the outcome of a save whose answer
 * was lost (a restart) be found out afterwards.
 */
export interface SaveInfo {
    fileId: string;
    revnBefore: number;
    sessionId: string;
}

/**
 * Response sent by an executor process, correlated by request ID.
 */
export type ExecutorResponse =
    { id: number; ok: true; value: unknown } | { id: number; ok: false; error: ExecutorErrorData };
