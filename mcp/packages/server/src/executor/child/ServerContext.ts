import { ExecutorError } from "../ExecutorError";
import type { FollowAction, ObservedScreen } from "./HeadlessEngine";

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
 * What the server context needs from the session beyond the frontend plugin context.
 */
export interface ServerSession {
    /** the screen of the user's browser tab on the open file, or null when none reported one */
    observe: () => ObservedScreen | null;
    /** the viewer URL of the current page, or null with no file open */
    viewerUrl: () => string | null;
    /** shows a call on the user's tabs with "AI follow" on (PEN-24); returns how many tabs follow */
    follow: (action: FollowAction) => number;
}

function invalid(member: string, value: unknown): never {
    throw new ExecutorError("validation", `${member}: invalid value ${JSON.stringify(value)}`);
}

function shapeIds(member: string, shapes: unknown): string[] {
    if (!Array.isArray(shapes) || !shapes.every((shape) => typeof shape?.id === "string")) {
        invalid(member, "expected an array of shapes");
    }
    return shapes.map((shape) => shape.id as string);
}

/**
 * Viewport of the server session (D8). Reading it reads the screen of a browser tab of the same user on the
 * open file (b); moving it moves the screens of the user's tabs on the file that have "AI follow" on (f,
 * PEN-24). Without such a tab, reading and moving fail with `ui-only` (c).
 *
 * @param observe - the screen of the user's browser tab, or null when none reported one
 * @param follow - shows a call on the user's following tabs; returns how many follow
 */
function createViewport(observe: () => ObservedScreen | null, follow: (action: FollowAction) => number): object {
    // a tab with the file open reports its screen within a moment after this session opens the file
    const noTab =
        "no browser tab of this user has reported its screen on this file (a tab that has the file open " +
        "reports it within a second after this session opens the file)";
    const noFollow =
        "no browser tab of this user on this file has 'AI follow' on (MCP menu of the editor: 'Follow AI in this tab')";
    const screen = (member: string): ObservedScreen => observe() ?? uiOnly(member, noTab);
    const move = (member: string, action: FollowAction): void => {
        if (follow(action) === 0) {
            uiOnly(member, noFollow);
        }
    };
    return Object.freeze({
        get center() {
            const { vbox } = screen("Viewport.center");
            return Object.freeze({ x: vbox.x + vbox.width / 2, y: vbox.y + vbox.height / 2 });
        },
        set center(value: { x: number; y: number }) {
            if (!Number.isFinite(value?.x) || !Number.isFinite(value?.y)) {
                invalid("Viewport.center", value);
            }
            move("Viewport.center", { action: "center", x: value.x, y: value.y });
        },
        get zoom() {
            return screen("Viewport.zoom").zoom;
        },
        set zoom(value: number) {
            if (!Number.isFinite(value) || value <= 0) {
                invalid("Viewport.zoom", value);
            }
            move("Viewport.zoom", { action: "zoom", zoom: value });
        },
        get bounds() {
            const { vbox } = screen("Viewport.bounds");
            return Object.freeze({ x: vbox.x, y: vbox.y, width: vbox.width, height: vbox.height });
        },
        zoomReset: () => move("Viewport.zoomReset", { action: "zoom-reset" }),
        zoomToFitAll: () => move("Viewport.zoomToFitAll", { action: "zoom-fit-all" }),
        zoomIntoView: (shapes: unknown) =>
            move("Viewport.zoomIntoView", { action: "zoom-into-view", ids: shapeIds("Viewport.zoomIntoView", shapes) }),
    });
}

/**
 * Wraps the frontend plugin context for the server (D8): members tied to the browser window answer with
 * the contract's server meaning instead of acting on a window that does not exist.
 *
 * - `viewport`: read from the user's browser tab on the file, see {@link createViewport}
 * - `theme`: the theme of the user's browser tab on the file, else `"light"`
 * - `openViewer()`: `ui-only`, it leaves the editor; the error gives the viewer URL of the page (D8)
 * - `openPage(page, true)`: `ui-only`, it opens a new window; `openPage(page)` changes the session's page,
 *   and the page of the user's tabs with "AI follow" on (PEN-24)
 * - `selection`: the session's selection; setting it shows it on the user's following tabs too (PEN-24)
 *
 * @param context - the frontend plugin context of the headless workspace
 * @param session - what the server session knows beyond the plugin context
 */
export function createServerContext(context: any, session: ServerSession): any {
    const { observe, viewerUrl, follow } = session;
    const viewport = createViewport(observe, follow);
    return new Proxy(context, {
        get(target, prop, receiver) {
            switch (prop) {
                case "viewport":
                    return viewport;
                case "theme":
                    return observe()?.theme ?? "light";
                case "openViewer":
                    return () => {
                        const url = viewerUrl();
                        uiOnly(
                            "openViewer()",
                            url
                                ? `it leaves the editor for the viewer. The viewer of this page: ${url}`
                                : "it leaves the editor for the viewer"
                        );
                    };
                case "openPage":
                    return (page: unknown, newWindow?: boolean) => {
                        if (newWindow === true) {
                            uiOnly("openPage(page, true)", "it opens a new browser window");
                        }
                        return Promise.resolve(target.openPage(page, false)).then((value: unknown) => {
                            follow({ action: "page" });
                            return value;
                        });
                    };
                default:
                    return Reflect.get(target, prop, receiver);
            }
        },
        set(target, prop, value, receiver) {
            const done = Reflect.set(target, prop, value, receiver);
            if (prop === "selection") {
                const selected = (target.selection ?? []) as { id: string }[];
                follow({ action: "select", ids: selected.map((shape) => shape.id) });
            }
            return done;
        },
    });
}
