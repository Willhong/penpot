import { z } from "zod";
import { Tool } from "../Tool";
import type { ToolResponse } from "../ToolResponse";
import { TextResponse } from "../ToolResponse";
import "reflect-metadata";
import { PenpotMcpServer } from "../PenpotMcpServer";

/**
 * Arguments class for UndoTool
 */
export class UndoArgs {
    static schema = {
        sessionId: Tool.SESSION_ID_SCHEMA,
        redo: z.boolean().optional().describe("Redo the last undone execution instead of undoing the last saved one."),
        fileId: z
            .string()
            .uuid()
            .optional()
            .describe("The file to open first (default: the file the session has open)."),
        pageId: z.string().uuid().optional().describe("The page of `fileId` to open (default: its first page)."),
        requestId: z
            .string()
            .min(1)
            .max(128)
            .optional()
            .describe(
                "Your ID for this request. Retrying with the same ID within 10 minutes returns the first result " +
                    "instead of undoing twice."
            ),
    };

    sessionId?: string;

    redo?: boolean;

    fileId?: string;

    pageId?: string;

    requestId?: string;
}

/**
 * Undoes or redoes a saved `execute_code` run of a server-side executor session (PEN-20, D6). Offered on
 * server-side execution only.
 */
export class UndoTool extends Tool<UndoArgs> {
    constructor(mcpServer: PenpotMcpServer) {
        super(mcpServer, UndoArgs.schema);
    }

    public getToolName(): string {
        return "undo";
    }

    public getToolDescription(): string {
        return (
            "Server-side execution only: undoes the last saved `execute_code` run of this session in the file " +
            "(one run is one step, up to 50), or redoes the last undone one with `redo: true`, and saves the " +
            "result like a run. Refused with `precondition-failed`, saving nothing, when someone else changed " +
            "what it would revert since: it never overwrites their work. Comments and actions outside the file " +
            "(creating files, projects) are not undone. The steps last as long as the session."
        );
    }

    protected async executeCore(args: UndoArgs, signal?: AbortSignal): Promise<ToolResponse> {
        const result = await this.executeOnServer(
            { code: "", history: args.redo ? "redo" : "undo", fileId: args.fileId, pageId: args.pageId },
            args.sessionId,
            signal,
            args.requestId
        );
        return new TextResponse(JSON.stringify(result, null, 2));
    }
}
