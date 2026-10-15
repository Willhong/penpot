import { z } from "zod";
import { Tool } from "../Tool";
import type { ToolResponse } from "../ToolResponse";
import { TextResponse } from "../ToolResponse";
import "reflect-metadata";
import { PenpotMcpServer } from "../PenpotMcpServer";

/**
 * Arguments class for RequestStatusTool
 */
export class RequestStatusArgs {
    static schema = {
        requestId: z.string().min(1).max(128).describe("The `requestId` you gave an `execute_code` or `undo` call."),
    };

    requestId!: string;
}

/**
 * Tells where a request ID stands without running anything (D5, PEN-20), e.g. after its answer was lost to a
 * restart of the MCP server. Offered on server-side execution only.
 */
export class RequestStatusTool extends Tool<RequestStatusArgs> {
    constructor(mcpServer: PenpotMcpServer) {
        super(mcpServer, RequestStatusArgs.schema);
    }

    public getToolName(): string {
        return "request_status";
    }

    public getToolDescription(): string {
        return (
            "Server-side execution only: where an `execute_code` or `undo` call made with a `requestId` stands, " +
            "without running it: `none` (not seen in the last 10 minutes), `running`, `done` (with its result), " +
            "or `interrupted` by a restart of the MCP server, with `saved` true (and the `revn` it saved), " +
            "false (nothing saved: retrying with the same requestId runs it) or 'unknown' (read the file)."
        );
    }

    protected async executeCore(args: RequestStatusArgs): Promise<ToolResponse> {
        const token = this.getSessionContext()?.userToken;
        if (!token) {
            throw new Error("server-side execution needs the user's MCP token (userToken)");
        }
        const status = await this.mcpServer.executorPool!.requestStatus(token, args.requestId);
        return new TextResponse(JSON.stringify(status, null, 2));
    }
}
