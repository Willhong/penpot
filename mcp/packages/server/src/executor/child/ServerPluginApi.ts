// The plugins runtime's API factory: the same code that builds `penpot` and `penpotMgmt` for the MCP plugin
// in the browser, so both expose the same members with the same checks (bundled from source, see
// `build:executor` and `vendor.d.ts`).
import { createApi } from "@penpot/plugins-runtime/api";
import { uiOnly } from "./ServerContext";

/**
 * Manifest of the MCP plugin (`mcp/packages/plugin/public/manifest.json`), whose identity and permissions
 * the server-side executor takes over.
 */
const MCP_PLUGIN_MANIFEST = {
    pluginId: "96dfa740-005d-8020-8007-55ede24a2bae",
    name: "Penpot MCP Plugin",
    host: "",
    code: "",
    version: 2 as const,
    scope: "global" as const,
    permissions: [
        "user:read",
        "content:read",
        "content:write",
        "library:read",
        "library:write",
        "comment:read",
        "comment:write",
    ],
};

/**
 * Server counterpart of the plugins runtime's plugin manager (`createPluginManager`): the object `createApi`
 * builds the API on. There is no plugin window, so every window operation is `ui-only` (D8 (c)); events go
 * to the frontend context like in the browser.
 *
 * The browser plugin's listeners stay until the plugin closes; here they stay until the executor session
 * ends, so a listener added in one execution also hears the changes other sessions save between executions.
 */
class ServerPluginManager {
    readonly timeouts = new Set<ReturnType<typeof setTimeout>>();
    readonly intervals = new Set<ReturnType<typeof setInterval>>();
    constructor(public readonly context: any) {}

    get manifest() {
        return MCP_PLUGIN_MANIFEST;
    }

    get destroyed(): boolean {
        return false;
    }

    getModal(): null {
        return null;
    }

    openModal(): never {
        return uiOnly("ui.open()", "there is no plugin window");
    }

    resizeModal(): never {
        return uiOnly("ui.resize()", "there is no plugin window");
    }

    registerMessageCallback(): never {
        return uiOnly("ui.onMessage()", "there is no plugin window");
    }

    sendMessage(): never {
        return uiOnly("ui.sendMessage()", "there is no plugin window");
    }

    close(): never {
        return uiOnly("closePlugin()", "the server session has no plugin to close");
    }

    registerListener(type: string, callback: (...params: unknown[]) => void, props?: unknown): symbol {
        return this.context.addListener(type, callback, props);
    }

    destroyListener(listenerId: symbol): void {
        this.context.removeListener(listenerId);
    }
}

/**
 * The Plugin API objects of the server session.
 */
export interface ServerPluginApi {
    penpot: any;
    penpotMgmt: any;
}

/**
 * Builds `penpot` and `penpotMgmt` over the server context with the plugins runtime's factory, then replaces
 * the plugin window API (`penpot.ui`), which has no server meaning (D8 (c)).
 *
 * @param context - the server context (see {@link createServerContext})
 */
export function createServerPluginApi(context: any): ServerPluginApi {
    const manager = new ServerPluginManager(context);
    const api = createApi(manager as any) as { penpot: any; penpotMgmt: any };
    const ui = Object.freeze({
        open: () => uiOnly("ui.open()", "there is no plugin window"),
        get size() {
            return uiOnly("ui.size", "there is no plugin window");
        },
        resize: () => uiOnly("ui.resize()", "there is no plugin window"),
        sendMessage: () => uiOnly("ui.sendMessage()", "there is no plugin window"),
        onMessage: () => uiOnly("ui.onMessage()", "there is no plugin window"),
    });
    Object.defineProperty(api.penpot, "ui", { get: () => ui, enumerable: true });
    return { penpot: api.penpot, penpotMgmt: api.penpotMgmt };
}
