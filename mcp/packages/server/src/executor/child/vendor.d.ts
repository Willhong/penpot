/**
 * Types of the sources the executor bundles from other packages (aliases of `build:executor`). They are
 * typed here because their own sources need the DOM library and other compiler settings.
 */

declare module "@penpot/plugins-runtime/api" {
    /**
     * The plugins runtime's factory of `penpot` and `penpotMgmt` (`plugins-runtime/src/lib/api/index.ts`).
     */
    export function createApi(plugin: unknown): { penpot: any; penpotMgmt: any };
}

declare module "@penpot/mcp-plugin/console" {
    /**
     * The MCP plugin's capturing console (`plugin/src/task-handlers/ExecuteCodeTaskHandler.ts`).
     */
    export class ExecuteCodeTaskConsole {
        resetLog(): void;
        getLog(): string;
    }
}

declare module "@penpot/mcp-plugin/utils" {
    /**
     * The MCP plugin's `penpotUtils` (`plugin/src/PenpotUtils.ts`).
     */
    export const PenpotUtils: object;
}
