import { ExecutorError } from "../ExecutorError";
import type { ObservedScreen } from "./HeadlessEngine";

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
 * Viewport of the server session (D8). Reading it reads the screen of a browser tab of the same user on the
 * open file (b); moving it needs a tab with "AI follow" on (f, PEN-24). Without such a tab both fail with
 * `ui-only` (c).
 *
 * @param observe - the screen of the user's browser tab, or null when none reported one
 */
function createViewport(observe: () => ObservedScreen | null): object {
    // a tab with the file open reports its screen within a moment after this session opens the file
    const noTab =
        "no browser tab of this user has reported its screen on this file (a tab that has the file open " +
        "reports it within a second after this session opens the file)";
    const noFollow = "no browser tab of this user has 'AI follow' on";
    const screen = (member: string): ObservedScreen => observe() ?? uiOnly(member, noTab);
    return Object.freeze({
        get center() {
            const { vbox } = screen("Viewport.center");
            return Object.freeze({ x: vbox.x + vbox.width / 2, y: vbox.y + vbox.height / 2 });
        },
        set center(_value: unknown) {
            uiOnly("Viewport.center", noFollow);
        },
        get zoom() {
            return screen("Viewport.zoom").zoom;
        },
        set zoom(_value: unknown) {
            uiOnly("Viewport.zoom", noFollow);
        },
        get bounds() {
            const { vbox } = screen("Viewport.bounds");
            return Object.freeze({ x: vbox.x, y: vbox.y, width: vbox.width, height: vbox.height });
        },
        zoomReset: () => uiOnly("Viewport.zoomReset", noFollow),
        zoomToFitAll: () => uiOnly("Viewport.zoomToFitAll", noFollow),
        zoomIntoView: () => uiOnly("Viewport.zoomIntoView", noFollow),
    });
}

/**
 * Wraps the frontend plugin context for the server (D8): members tied to the browser window answer with
 * the contract's server meaning instead of acting on a window that does not exist.
 *
 * - `viewport`: read from the user's browser tab on the file, see {@link createViewport}
 * - `theme`: the theme of the user's browser tab on the file, else `"light"`
 * - `openViewer()`: `ui-only`, it leaves the editor
 * - `openPage(page, true)`: `ui-only`, it opens a new window; `openPage(page)` changes the session's page
 *
 * @param context - the frontend plugin context of the headless workspace
 * @param observe - the screen of the user's browser tab on the open file, or null when none reported one
 */
export function createServerContext(context: any, observe: () => ObservedScreen | null): any {
    const viewport = createViewport(observe);
    return new Proxy(context, {
        get(target, prop, receiver) {
            switch (prop) {
                case "viewport":
                    return viewport;
                case "theme":
                    return observe()?.theme ?? "light";
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
