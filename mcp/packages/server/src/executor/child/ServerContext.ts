import { ExecutorError } from "../ExecutorError";

/**
 * Raises the `ui-only` error of D8 for a member that needs a browser window.
 *
 * @param member - the Plugin API member, as written in the type declarations
 * @param reason - why the member has no server-side meaning
 */
export function uiOnly(member: string, reason: string): never {
    throw new ExecutorError("ui-only", `${member} is only available in a browser: ${reason}`);
}

/**
 * Viewport of the server session. With no observed browser and no "AI follow" tab (PEN-24), reading or moving
 * the viewport has no meaning on the server (D8 (b)/(f) fall back to (c)).
 */
function createViewport(): object {
    const reason = "no browser tab of this user is open with 'AI follow' on";
    return Object.freeze({
        get center() {
            return uiOnly("Viewport.center", reason);
        },
        set center(_value: unknown) {
            uiOnly("Viewport.center", reason);
        },
        get zoom() {
            return uiOnly("Viewport.zoom", reason);
        },
        set zoom(_value: unknown) {
            uiOnly("Viewport.zoom", reason);
        },
        get bounds() {
            return uiOnly("Viewport.bounds", reason);
        },
        zoomReset: () => uiOnly("Viewport.zoomReset", reason),
        zoomToFitAll: () => uiOnly("Viewport.zoomToFitAll", reason),
        zoomIntoView: () => uiOnly("Viewport.zoomIntoView", reason),
    });
}

/**
 * Wraps the frontend plugin context for the server (D8): members tied to the browser window answer with
 * the contract's server meaning instead of acting on a window that does not exist.
 *
 * - `viewport`: `ui-only` (no observed browser yet; PEN-24 adds the followed tab)
 * - `theme`: `"light"`, the fixed server value
 * - `openViewer()`: `ui-only`, it leaves the editor
 * - `openPage(page, true)`: `ui-only`, it opens a new window; `openPage(page)` changes the session's page
 *
 * @param context - the frontend plugin context of the headless workspace
 */
export function createServerContext(context: any): any {
    const viewport = createViewport();
    return new Proxy(context, {
        get(target, prop, receiver) {
            switch (prop) {
                case "viewport":
                    return viewport;
                case "theme":
                    return "light";
                case "openViewer":
                    return () => uiOnly("openViewer()", "it leaves the editor for the viewer");
                case "openPage":
                    return (page: unknown, newWindow?: boolean) => {
                        if (newWindow === true) {
                            uiOnly("openPage(page, true)", "it opens a new browser window");
                        }
                        return target.openPage(page, false);
                    };
                default:
                    return Reflect.get(target, prop, receiver);
            }
        },
    });
}
