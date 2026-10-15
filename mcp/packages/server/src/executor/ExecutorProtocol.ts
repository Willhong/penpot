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
    /** whether anything was saved before the failure; always false except for a failure after the save */
    saved: boolean;
}

/**
 * Commit report of a write: what was saved and which derived values were completed.
 */
export interface CommitReport {
    saved: boolean;
    fileId: string | null;
    revnBefore: number | null;
    revn: number | null;
    changedShapeIds: string[];
    /** number of changes of other sessions the backend applied in between */
    lagged: number;
    computed: { layout: boolean; text: boolean; bool: boolean; componentSync: boolean };
    /** layout work still in flight when the settle timeout passed, by shape id */
    pending?: Record<string, string[]> | null;
    warnings?: { code: string; shapeId?: string; message?: string }[];
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
    | { id: number; type: "status" };

/**
 * Response sent by an executor process, correlated by request ID.
 */
export type ExecutorResponse =
    { id: number; ok: true; value: unknown } | { id: number; ok: false; error: ExecutorErrorData };
