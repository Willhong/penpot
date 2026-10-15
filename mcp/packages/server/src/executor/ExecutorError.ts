import type { ExecutorErrorCode, ExecutorErrorData, SavedState } from "./ExecutorProtocol";

/**
 * Error with a contract error code (03-runtime-contract §7), raised by the executor or by the MCP server
 * on its behalf.
 */
export class ExecutorError extends Error {
    constructor(
        public readonly code: ExecutorErrorCode,
        message: string,
        public readonly saved: SavedState = false
    ) {
        super(message);
        this.name = "ExecutorError";
    }

    /**
     * Serializable form, sent over the IPC channel.
     */
    toData(): ExecutorErrorData {
        return { code: this.code, message: this.message, saved: this.saved };
    }

    /**
     * Restores an error received over the IPC channel.
     */
    static fromData(data: ExecutorErrorData): ExecutorError {
        return new ExecutorError(data.code, data.message, data.saved);
    }

    /**
     * Text returned to the MCP client: the code first, so clients can act on it.
     */
    toString(): string {
        const saved =
            this.saved === "unknown"
                ? " (it ended while saving, so the changes may have been saved: read the file before retrying)"
                : this.saved
                  ? " (changes were saved)"
                  : " (nothing was saved)";
        return `[${this.code}] ${this.message}${saved}`;
    }
}
