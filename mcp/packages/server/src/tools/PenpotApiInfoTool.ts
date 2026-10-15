import { z } from "zod";
import { Tool } from "../Tool";
import "reflect-metadata";
import type { ToolResponse } from "../ToolResponse";
import { TextResponse } from "../ToolResponse";
import { PenpotMcpServer } from "../PenpotMcpServer";
import { ServerExecutionGuide } from "../ServerExecutionGuide";
import { ApiDocs } from "../ApiDocs";

/**
 * Arguments class for the PenpotApiInfoTool
 */
export class PenpotApiInfoArgs {
    static schema = {
        type: z.string().min(1, "Type name cannot be empty"),
        member: z.string().optional(),
    };

    /**
     * The API type name to retrieve information for.
     */
    type!: string;

    /**
     * The specific member name to retrieve (optional).
     */
    member?: string;
}

/**
 * Tool for retrieving Penpot API documentation information.
 *
 * This tool provides access to API type documentation loaded from YAML files,
 * allowing retrieval of either full type documentation or specific member details.
 */
export class PenpotApiInfoTool extends Tool<PenpotApiInfoArgs> {
    private static readonly MAX_FULL_TEXT_CHARS = 2000;
    private readonly apiDocs: ApiDocs;

    /**
     * Creates a new PenpotApiInfo tool instance.
     *
     * @param mcpServer - The MCP server instance
     */
    constructor(mcpServer: PenpotMcpServer, apiDocs: ApiDocs) {
        super(mcpServer, PenpotApiInfoArgs.schema);
        this.apiDocs = apiDocs;
    }

    public getToolName(): string {
        return "penpot_api_info";
    }

    public getToolDescription(): string {
        return (
            "Retrieves Penpot API documentation for types and their members." +
            "Be sure to read the 'Penpot High-Level Overview' first."
        );
    }

    protected async executeCore(args: PenpotApiInfoArgs): Promise<ToolResponse> {
        const apiType = this.apiDocs.getType(args.type);

        if (!apiType) {
            throw new Error(`API type "${args.type}" not found`);
        }

        if (args.member) {
            // return specific member documentation
            const memberDoc = apiType.getMember(args.member);
            if (!memberDoc) {
                throw new Error(`Member "${args.member}" not found in type "${args.type}"`);
            }
            const note = this.serverExecution() ? ServerExecutionGuide.memberNote(args.type, args.member) : null;
            return new TextResponse(note ? `${memberDoc}\n\n${note}` : memberDoc);
        } else {
            // return full text or overview based on length
            const fullText = apiType.getFullText();
            const text =
                fullText.length <= PenpotApiInfoTool.MAX_FULL_TEXT_CHARS
                    ? fullText
                    : apiType.getOverviewText() +
                      "\n\nMember details not provided (too long). " +
                      "Call this tool with a member name for more information.";
            const notes = this.serverExecution() ? ServerExecutionGuide.typeNotes(args.type) : null;
            return new TextResponse(notes ? `${text}\n\nServer-side execution differences:\n${notes}` : text);
        }
    }

    private serverExecution(): boolean {
        return this.mcpServer.usesServerExecution();
    }
}
