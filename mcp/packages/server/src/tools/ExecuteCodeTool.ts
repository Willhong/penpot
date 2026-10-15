import { z } from "zod";
import { Tool } from "../Tool";
import type { ToolResponse } from "../ToolResponse";
import { TextResponse } from "../ToolResponse";
import "reflect-metadata";
import { PenpotMcpServer } from "../PenpotMcpServer";
import { ExecuteCodePluginTask } from "../tasks/ExecuteCodePluginTask";
import { ExecuteCodeTaskParams } from "@penpot/mcp-common";
import { ExecutorError } from "../executor/ExecutorError";

/**
 * Arguments class for ExecuteCodeTool
 */
export class ExecuteCodeArgs {
    static schema = {
        code: z
            .string()
            .min(1, "Code cannot be empty")
            .describe("The JavaScript code to execute in the plugin context."),
        sessionId: Tool.SESSION_ID_SCHEMA,
        fileId: z
            .string()
            .uuid()
            .optional()
            .describe(
                "Server-side execution only: the file to open before running the code (like penpotMgmt.openFile). " +
                    "Without it, the code runs on the file the session opened last."
            ),
        pageId: z
            .string()
            .uuid()
            .optional()
            .describe("Server-side execution only: the page of `fileId` to open (default: its first page)."),
        requestId: z
            .string()
            .min(1)
            .max(128)
            .optional()
            .describe(
                "Server-side execution only: your ID for this request. Retrying with the same ID within 10 minutes " +
                    "returns the first run's result (`replayed: true`) instead of applying the change twice."
            ),
        ifUnchangedSinceRevn: z
            .number()
            .int()
            .min(0)
            .optional()
            .describe(
                "Server-side execution only: run and save only if the file is still at this revn (the `revn` of " +
                    "an earlier result); fails with `precondition-failed` when someone changed it since."
            ),
    };

    /**
     * The JavaScript code to execute in the plugin context.
     */
    code!: string;

    sessionId?: string;

    fileId?: string;

    pageId?: string;

    requestId?: string;

    ifUnchangedSinceRevn?: number;
}

/**
 * Tool for executing JavaScript code in the Penpot plugin context
 */
export class ExecuteCodeTool extends Tool<ExecuteCodeArgs> {
    /**
     * Creates a new ExecuteCode tool instance.
     *
     * @param mcpServer - The MCP server instance
     */
    constructor(mcpServer: PenpotMcpServer) {
        super(mcpServer, ExecuteCodeArgs.schema);
    }

    public getToolName(): string {
        return "execute_code";
    }

    public getToolDescription(): string {
        return (
            "Executes JavaScript code in the Penpot plugin context.\n" +
            "IMPORTANT: Before using this tool, make sure you have read the 'Penpot High-Level Overview' and know " +
            "which Penpot API functionality is necessary and how to use it.\n" +
            "You have access to `penpot` (of type `Penpot`), `penpotMgmt` (of type `PenpotMgmt`), `penpotUtils`, and `storage`.\n" +
            "If `penpotMgmt` is null, file management is unavailable and only the open file can be used.\n" +
            "`storage` is an object in which arbitrary data can be stored, simply by adding a new attribute; " +
            "stored attributes can be referenced in future calls to this tool, so any intermediate results that " +
            "could come in handy later should be stored in `storage` instead of just a fleeting variable; " +
            "you can also store functions and thus build up a library).\n" +
            "Think of the code being executed as the body of a function: " +
            "The tool call returns whatever you return in the applicable `return` statement, if any. " +
            "You can return arbitrary JS objects; no need to apply JSON.stringify.\n" +
            "If an exception occurs, the exception's message will be returned to you.\n" +
            "Any output that you generate via the `console` object will be returned to you separately; so you may use it " +
            "to track what your code is doing, but you should *only* do so only if there is an ACTUAL NEED for this! " +
            "VERY IMPORTANT: Don't use logging prematurely! NEVER log the data you are returning, as you will otherwise receive it twice!\n" +
            "VERY IMPORTANT: In general, try a simple approach first, and only if it fails, try more complex code that involves " +
            "handling different cases (in particular error cases) and that applies logging." +
            (this.mcpServer.executorPool ? ExecuteCodeTool.SERVER_MODE_NOTE : "")
        );
    }

    /**
     * Addition to the description when the code runs in a server-side executor.
     */
    private static readonly SERVER_MODE_NOTE =
        "\nSERVER-SIDE EXECUTION (when this connection uses it): the code runs on the Penpot server; no browser " +
        "needs to be open.\n" +
        "Open a file first, with the `fileId` argument or `await penpotMgmt.openFile(fileId)`; the session " +
        "(`sessionId`, default 'default') keeps that file open, and `storage`, across calls.\n" +
        "Everything one call changes is saved together when the code returns; if the code throws, nothing is saved. " +
        "The response has `result`, `log`, `commit` (saved revn, changed shape ids, whether layout and text values " +
        "were completed) and `engine`.\n" +
        "`penpot.viewport` and `penpot.theme` read the screen of a browser tab where the same user has the file " +
        "open; without one, reading the viewport fails with the error code `ui-only` and the theme is 'light'. " +
        "Members that need a browser window (`penpot.ui`, moving the viewport, `openViewer()`, " +
        "`openPage(page, true)`, `closePlugin()`) fail with `ui-only`. " +
        "Listeners added with `penpot.on` stay until the session ends.";

    protected async executeCore(args: ExecuteCodeArgs, signal?: AbortSignal): Promise<ToolResponse> {
        const pool = this.mcpServer.executorPool;
        if (pool && this.getSessionContext()?.serverExecution) {
            const token = this.getSessionContext()?.userToken;
            if (!token) {
                throw new ExecutorError("forbidden", "server-side execution needs the user's MCP token (userToken)");
            }
            const result = await pool.execute(
                token,
                args.sessionId ?? "default",
                {
                    code: args.code,
                    fileId: args.fileId,
                    pageId: args.pageId,
                    ifUnchangedSinceRevn: args.ifUnchangedSinceRevn,
                },
                signal,
                args.requestId
            );
            return new TextResponse(JSON.stringify(result, null, 2));
        }

        const taskParams: ExecuteCodeTaskParams = { code: args.code };
        const task = new ExecuteCodePluginTask(taskParams);
        const result = await this.mcpServer.pluginBridge.executePluginTask(task, args.sessionId);

        if (result.data !== undefined) {
            return new TextResponse(JSON.stringify(result.data, null, 2));
        } else {
            return new TextResponse("Code executed successfully with no return value.");
        }
    }
}
