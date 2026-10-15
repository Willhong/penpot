/**
 * Guidance for AI clients whose connection runs `execute_code` in the server-side executor
 * (`mcp/docs/server-mcp/04-executor.md`): the parts of the plugin-based overview and API docs that do not
 * hold there.
 */
export class ServerExecutionGuide {
    /** line of the overview that only holds for the browser plugin */
    static readonly PLUGIN_PRECONDITION =
        "As a precondition, the user must connect the Penpot design project to the MCP server using the Penpot MCP Plugin.";

    private static readonly SERVER_PRECONDITION =
        "In this connection your code runs on the Penpot server; see 'Server-Side Execution' at the end, which " +
        "applies where it differs from the rest of this overview.";

    private static readonly VIEWPORT_READ =
        "Server-side execution: reads the screen of a browser tab where the same user has the file open; fails " +
        "with `ui-only` when there is none.";

    private static readonly VIEWPORT_MOVE =
        "Server-side execution: moves the screen of a browser tab with 'AI follow' on; fails with `ui-only` when " +
        "there is none.";

    private static readonly VIEWPORT_READ_MOVE =
        "Server-side execution: reading it reads the screen of a browser tab where the same user has the file " +
        "open; setting it needs a tab with 'AI follow' on. Without such a tab, it fails with `ui-only`.";

    private static readonly NO_WINDOW = "Server-side execution: fails with `ui-only`; there is no plugin window.";

    private static readonly LISTENER =
        "Server-side execution: the listener stays until the session ends and also hears the changes others " +
        "save; record what it sees in `storage`.";

    /**
     * Notes on the members `Penpot` shares with `Context` whose server-side meaning differs (D8 of
     * `01-feature-contract.md`).
     */
    private static readonly CONTEXT_NOTES: Record<string, string> = {
        viewport:
            "Server-side execution: reading it reads the screen of a browser tab where the same user has the file " +
            "open; moving it needs a tab with 'AI follow' on. Without such a tab, it fails with `ui-only`.",
        theme:
            'Server-side execution: the theme of a browser tab where the same user has the file open; "light" ' +
            "when there is none.",
        selection:
            "Server-side execution: this session's own selection, not what the user selected in a browser; setting " +
            "it also shows it on the user's tabs with 'AI follow' on.",
        openViewer: "Server-side execution: fails with `ui-only`; it would leave the editor.",
        openPage:
            "Server-side execution: changes the session's current page, and the page of the user's tabs with " +
            "'AI follow' on; with `newWindow` true it fails with `ui-only`.",
    };

    private static readonly NOTES: Record<string, Record<string, string>> = {
        Penpot: {
            ...ServerExecutionGuide.CONTEXT_NOTES,
            ui: ServerExecutionGuide.NO_WINDOW,
            closePlugin: ServerExecutionGuide.NO_WINDOW,
            on: ServerExecutionGuide.LISTENER,
        },
        Context: { ...ServerExecutionGuide.CONTEXT_NOTES, addListener: ServerExecutionGuide.LISTENER },
        Viewport: {
            center: ServerExecutionGuide.VIEWPORT_READ_MOVE,
            zoom: ServerExecutionGuide.VIEWPORT_READ_MOVE,
            bounds: ServerExecutionGuide.VIEWPORT_READ,
            zoomReset: ServerExecutionGuide.VIEWPORT_MOVE,
            zoomToFitAll: ServerExecutionGuide.VIEWPORT_MOVE,
            zoomIntoView: ServerExecutionGuide.VIEWPORT_MOVE,
        },
    };

    /**
     * The high-level overview for a server-side execution connection.
     *
     * @param overview - the overview for the browser plugin
     * @param serverSection - the 'Server-Side Execution' section (`data/server_execution_instructions.md`)
     */
    static overview(overview: string, serverSection: string): string {
        if (!overview.includes(ServerExecutionGuide.PLUGIN_PRECONDITION)) {
            throw new Error("the overview no longer has the plugin precondition the server guide replaces");
        }
        const text = overview.replace(
            ServerExecutionGuide.PLUGIN_PRECONDITION,
            ServerExecutionGuide.SERVER_PRECONDITION
        );
        // before the closing "--" line that tells the client it has read the overview
        const end = text.lastIndexOf("\n--\n");
        const section = serverSection.trim() + "\n";
        return end < 0 ? `${text}\n\n${section}` : `${text.slice(0, end)}\n\n${section}${text.slice(end)}`;
    }

    /**
     * The server-side note on one member, or null when it behaves as documented.
     */
    static memberNote(type: string, member: string): string | null {
        return ServerExecutionGuide.NOTES[type]?.[member] ?? null;
    }

    /**
     * The server-side notes on the members of a type, one per line, or null when there is none.
     */
    static typeNotes(type: string): string | null {
        const notes = ServerExecutionGuide.NOTES[type];
        if (!notes) {
            return null;
        }
        return Object.entries(notes)
            .map(([member, note]) => `- ${member}: ${note}`)
            .join("\n");
    }
}
