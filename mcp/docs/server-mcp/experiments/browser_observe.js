// Observer for the mcp-verify browsers: reports when shapes the observed
// tabs had not seen before appear in their workspace state, with no reload.
//
// Runs inside `ego-browser nodejs` (not plain node), whose process does not
// inherit the caller's environment. Prepend the options as a global:
//   { echo 'globalThis.OBS = {"space": 2}'; cat browser_observe.js; } | ego-browser nodejs
// Options:
//   space    task space id holding the observer tabs (required)
//   pages    page labels (default ["p1", "p2"])
//   timeout  ms to wait for the new shapes per tab (default 15000)
//   expect   number of new shapes to wait for per tab (default 1)
//   ready    path of a file created once the baseline is taken
//
// Prints one JSON line: per tab, the epoch ms at which each new shape was
// first seen in `app.main.store/state` and the shape's name and selrect.

const fs = await import("node:fs");

const options = globalThis.OBS ?? {};
const spaceId = Number(options.space);
const labels = options.pages ?? ["p1", "p2"];
const timeout = Number(options.timeout ?? 15000);
const expect = Number(options.expect ?? 1);

const task = await taskSpace(spaceId);
const pages = labels.map((label) => task.page(label));

// Returns {id: {name, x, y, width, height}} for the current page of a tab.
const readObjects = (page) =>
  page.evaluate(() => {
    const k = (n) => cljs.core.keyword(n);
    const get = (m, key) => cljs.core.get(m, k(key));
    const state = cljs.core.deref(app.main.store.state);
    const fileId = get(state, "current-file-id");
    const pageId = get(state, "current-page-id");
    const file = cljs.core.get(get(state, "files"), fileId);
    const page = cljs.core.get(get(get(file, "data"), "pages-index"), pageId);
    const objects = get(page, "objects");
    const result = {};
    for (const key of cljs.core.into_array(cljs.core.keys(objects) ?? cljs.core.List.EMPTY)) {
      const id = String(key);
      const shape = cljs.core.get(objects, key);
      const sr = get(shape, "selrect");
      result[id] = {
        name: get(shape, "name"),
        x: get(sr, "x"),
        y: get(sr, "y"),
        width: get(sr, "width"),
        height: get(sr, "height"),
      };
    }
    return { revn: get(file, "revn"), objects: result };
  });

const baseline = await Promise.all(pages.map(readObjects));
if (options.ready) {
  fs.writeFileSync(options.ready, String(Date.now()));
}

const report = {};
await Promise.all(
  pages.map(async (page, index) => {
    const seen = {};
    const known = new Set(Object.keys(baseline[index].objects));
    const deadline = Date.now() + timeout;
    let last = baseline[index];
    while (Date.now() < deadline && Object.keys(seen).length < expect) {
      last = await readObjects(page);
      const now = Date.now();
      for (const [id, shape] of Object.entries(last.objects)) {
        if (!known.has(id) && !seen[id]) {
          seen[id] = { seenAt: now, ...shape };
        }
      }
      await page.waitForTimeout(20);
    }
    report[page.label] = {
      url: await page.url(),
      revnBefore: baseline[index].revn,
      revnAfter: last.revn,
      newShapes: seen,
    };
  })
);

console.log(JSON.stringify(report));
