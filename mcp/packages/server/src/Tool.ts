import { z } from "zod";
import "reflect-metadata";
import { TextResponse, ToolResponse } from "./ToolResponse";
import type { PenpotMcpServer, SessionContext } from "./PenpotMcpServer";
import { createLogger } from "./logger";
import { ExecutorError } from "./executor/ExecutorError";
import type { ExecuteParams, ExecutionResult } from "./executor/ExecutorProtocol";
import { ExecutorConfig } from "./executor/ExecutorConfig";
import type { JobReporter } from "./executor/ExecutionJobs";

/**
 * An empty arguments class for tools that do not require any parameters.
 */
export class EmptyToolArgs {
    static schema = {};
}

/**
 * Base class for type-safe tools with automatic schema generation and validation.
 *
 * This class provides type safety through automatic validation and strongly-typed
 * protected methods. All tools should extend this class.
 *
 * @template TArgs - The strongly-typed arguments class for this tool
 */
export abstract class Tool<TArgs extends object> {
    public static readonly SESSION_ID_SCHEMA = z
        .string()
        .min(1)
        .max(128)
        .optional()
        .describe(
            "Penpot session to use. Optional when exactly one session is connected. " +
                "If several sessions are listed in an error, ask the user to select one and pass its sessionId."
        );

    private readonly logger = createLogger("Tool");

    /** monotonically increasing counter for unique tool execution IDs */
    private static executionCounter = 0;

    protected constructor(
        protected mcpServer: PenpotMcpServer,
        private inputSchema: z.ZodRawShape
    ) {}

    /**
     * Executes the tool with automatic validation and type safety.
     *
     * This method handles the unknown args from the MCP protocol,
     * delegating to the type-safe implementation.
     */
    async execute(args: unknown, signal?: AbortSignal): Promise<ToolResponse> {
        const executionId = ++Tool.executionCounter;
        try {
            let argsInstance: TArgs = args as TArgs;
            this.logger.info("Tool execution #%d starting: %s", executionId, this.getToolName());
            if (this.logger.isLevelEnabled("debug")) {
                this.logger.debug("Tool execution #%d arguments: %s", executionId, this.formatArgs(argsInstance));
            }

            // execute the actual tool logic
            let result = await this.executeCore(argsInstance, signal);

            this.logger.info("Tool execution #%d complete: %s", executionId, this.getToolName());
            return result;
        } catch (error) {
            this.logger.error("Tool execution #%d failed: %s; error: %s", executionId, this.getToolName(), error);
            return new TextResponse(`Tool execution failed: ${String(error)}`);
        }
    }

    /**
     * Formats tool arguments for readable logging.
     *
     * Multi-line strings are preserved with proper indentation.
     */
    protected formatArgs(args: TArgs): string {
        const formatted: string[] = [];

        for (const [key, value] of Object.entries(args)) {
            if (typeof value === "string" && value.includes("\n")) {
                // multi-line string - preserve formatting with indentation
                const indentedValue = value
                    .split("\n")
                    .map((line, index) => (index === 0 ? line : "    " + line))
                    .join("\n");
                formatted.push(`  ${key}: ${indentedValue}`);
            } else if (typeof value === "string") {
                // single-line string
                formatted.push(`  ${key}: "${value}"`);
            } else if (value === null || value === undefined) {
                formatted.push(`  ${key}: ${value}`);
            } else {
                // other types (numbers, booleans, objects, arrays)
                const stringified = JSON.stringify(value, null, 2);
                if (stringified.includes("\n")) {
                    // multi-line JSON - indent it
                    const indented = stringified
                        .split("\n")
                        .map((line, index) => (index === 0 ? line : "    " + line))
                        .join("\n");
                    formatted.push(`  ${key}: ${indented}`);
                } else {
                    formatted.push(`  ${key}: ${stringified}`);
                }
            }
        }

        return formatted.length > 0 ? "\n" + formatted.join("\n") : "{}";
    }

    /**
     * Retrieves the current session context.
     *
     * @returns The session context for the current request, or undefined if not in a request context
     */
    protected getSessionContext(): SessionContext | undefined {
        return this.mcpServer.getSessionContext();
    }

    /**
     * Whether this request runs code in the server-side executor rather than the browser plugin.
     */
    protected usesServerExecution(): boolean {
        return this.mcpServer.executorPool !== null && this.getSessionContext()?.serverExecution === true;
    }

    /**
     * Runs code in the server-side executor session `sessionId` of the request's user.
     *
     * @param params - the execution
     * @param sessionId - the executor session, `default` when omitted
     * @param signal - aborts the execution before its save (D6)
     * @param requestId - the client's request ID, for deduplication (D5)
     * @param progress - told when the execution starts and starts saving (background jobs)
     */
    protected executeOnServer(
        params: ExecuteParams,
        sessionId?: string,
        signal?: AbortSignal,
        requestId?: string,
        progress?: JobReporter
    ): Promise<ExecutionResult> {
        const token = this.getSessionContext()?.userToken;
        if (!token) {
            throw new ExecutorError("forbidden", "server-side execution needs the user's MCP token (userToken)");
        }
        return this.mcpServer.executorPool!.execute(token, sessionId ?? "default", params, signal, requestId, progress);
    }

    /**
     * The execution with a result too large to send inline replaced by a download URL (03-runtime-contract §5).
     */
    protected async deliverLarge(result: ExecutionResult): Promise<ExecutionResult> {
        const context = this.getSessionContext();
        if (!context?.userToken || !this.mcpServer.executorPool) {
            return result;
        }
        const delivered = await this.mcpServer.executorPool.results.deliver(
            result.result,
            ExecutorConfig.ownerKey(context.userToken),
            context.baseUrl ?? ""
        );
        return delivered === result.result ? result : { ...result, result: delivered };
    }

    /**
     * Fingerprint of the request's user token, which owns its results and jobs.
     */
    protected ownerKey(): string {
        const token = this.getSessionContext()?.userToken;
        if (!token) {
            throw new ExecutorError("forbidden", "server-side execution needs the user's MCP token (userToken)");
        }
        return ExecutorConfig.ownerKey(token);
    }

    public getInputSchema() {
        return this.inputSchema;
    }

    /**
     * Returns the tool's unique name.
     */
    public abstract getToolName(): string;

    /**
     * Returns the tool's description.
     */
    public abstract getToolDescription(): string;

    /**
     * Executes the tool's core logic.
     *
     * @param args - The (typed) tool arguments
     * @param signal - Aborted when the client cancels the request
     */
    protected abstract executeCore(args: TArgs, signal?: AbortSignal): Promise<ToolResponse>;
}
