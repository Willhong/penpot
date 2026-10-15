import { z } from "zod";
import { Tool } from "../Tool";
import type { ToolResponse } from "../ToolResponse";
import { TextResponse } from "../ToolResponse";
import "reflect-metadata";
import { PenpotMcpServer } from "../PenpotMcpServer";

/**
 * Arguments class for ExecutionJobTool
 */
export class ExecutionJobArgs {
    static schema = {
        jobId: z.string().uuid().describe("The `jobId` an `execute_code` call with `async: true` answered with."),
        cancel: z
            .boolean()
            .optional()
            .describe("Stop the job: before its save it ends `cancelled` and saves nothing; once saving it completes."),
    };

    jobId!: string;

    cancel?: boolean;
}

/**
 * Reads, or cancels, an execution run in the background (03-runtime-contract §5). Offered on server-side
 * execution only.
 */
export class ExecutionJobTool extends Tool<ExecutionJobArgs> {
    constructor(mcpServer: PenpotMcpServer) {
        super(mcpServer, ExecutionJobArgs.schema);
    }

    public getToolName(): string {
        return "execution_job";
    }

    public getToolDescription(): string {
        return (
            "Server-side execution only: reads the status of an `execute_code` call made with `async: true` " +
            "(`status` pending, running, done, error or cancelled; `progress` queued, running or saving until it is " +
            "over), its result once done (`resource` too when it is a download URL), or cancels it. " +
            "Jobs are kept 10 minutes after they end and are visible to the user who started them only."
        );
    }

    protected async executeCore(args: ExecutionJobArgs): Promise<ToolResponse> {
        const jobs = this.mcpServer.executorPool!.jobs;
        const ownerKey = this.ownerKey();
        const job = args.cancel ? jobs.cancel(ownerKey, args.jobId) : jobs.get(ownerKey, args.jobId);
        const result = job.result ? await this.deliverLarge(job.result) : undefined;
        const resource = (result?.result as { __type?: unknown } | undefined)?.__type === "resource";
        const view = result ? { ...job, result, ...(resource ? { resource: result.result } : {}) } : job;
        return new TextResponse(JSON.stringify(view, null, 2));
    }
}
