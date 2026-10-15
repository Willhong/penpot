// Runs Plugin API code in an mcp-verify browser tab, the way the MCP plugin's
// executeCode handler does (MCP plugin id, naturalChildOrdering and
// throwValidationErrors on), and waits for the workspace to save.
//
// Runs inside `ego-browser nodejs`; prepend the options as a global:
//   { echo 'globalThis.RUN = {...}'; cat browser_run.js; } | ego-browser nodejs
// Options:
//   space   task space id (required)
//   page    page label (default "p2", the editor tab)
//   url     workspace URL to open first (optional)
//   code    Plugin API code: the body of an async function (required)
//   settle  ms to wait after the code before forcing persistence (default 1500)
//   timeout ms to wait for the whole run (default 120000)
//
// Prints one JSON line {ok, ms, result | error}.

const options = globalThis.RUN ?? {};
const task = await taskSpace(Number(options.space));
const page = task.page(options.page ?? "p2");

if (options.url) {
  await page.goto(options.url);
  await page.waitForFunction(
    () => {
      try {
        const state = cljs.core.deref(app.main.store.state);
        return cljs.core.get(state, cljs.core.keyword("workspace-ready")) != null;
      } catch (e) {
        return false;
      }
    },
    undefined,
    { timeout: 60000 }
  );
  await page.waitForTimeout(2000);
}

// `page.evaluate` gives up after 15 s, so the run is started in the page and
// its report polled.
await page.evaluate(
  ({ code, settle }) => {
    window.__mcpvRun = null;
    (async () => {
      const started = Date.now();
      const context = app.plugins.api.create_context("96dfa740-005d-8020-8007-55ede24a2bae");
      context.flags.naturalChildOrdering = true;
      context.flags.throwValidationErrors = true;
      try {
        const fn = new Function("penpot", "penpotMgmt", "storage", `return (async () => { ${code} })();`);
        const result = await fn(context, context.management, {});
        await new Promise((resolve) => setTimeout(resolve, settle));
        app.main.store.emit_BANG_(cljs.core.keyword("app.main.data.persistence", "force-persist"));
        await new Promise((resolve) => setTimeout(resolve, 1500));
        window.__mcpvRun = { ok: true, ms: Date.now() - started, result };
      } catch (e) {
        window.__mcpvRun = { ok: false, ms: Date.now() - started, error: String(e && e.stack ? e.stack : e) };
      }
    })();
    return true;
  },
  { code: options.code, settle: options.settle ?? 1500 }
);
await page.waitForFunction(() => window.__mcpvRun != null, undefined, { timeout: options.timeout ?? 120000 });
const report = await page.evaluate(() => window.__mcpvRun);

console.log(JSON.stringify(report));
