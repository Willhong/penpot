"""
Runs the same Plugin API scenario in a browser workspace (wasm renderer) and
in the server-side executor, then compares what each returned and what each
saved (03-runtime-contract §6).

    import dual_run
    run = dual_run.DualRun(space=2)
    report = run.scenario("shapes", open("pen5_shapes.js").read())

- browser: tab p2 (editor) on a fresh file B, through `browser_run.js`;
- server: a real MCP call (`?executor=server`) on a fresh file S, while tab
  p1 (owner) has S open, so the report also says whether the observer got
  the result without a reload, and whether a reload shows the same.

Shapes are matched by name, so scenarios name every shape they create. Ids
are replaced by names before comparing; maps keyed by other generated ids
(grid cells) are compared as lists of their entries; numbers are rounded to
2 decimals.
"""

import json
import re
import time

import mcp_client
import mcpv
import observers

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
UUID_IN_TEXT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
INST_IN_TEXT = re.compile(r'#inst "[^"]*"')

# attributes that differ between two runs by nature
VOLATILE = {"id", "modifiedAt", "createdAt"}


def normalize(value, names):
    """Replaces ids by shape names (or a placeholder) and rounds numbers."""
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, str) and UUID.match(value):
        return names.get(value, "<id>")
    if isinstance(value, str):
        # ids inside messages (e.g. a refused value echoed in an error)
        return INST_IN_TEXT.sub("#inst <time>", UUID_IN_TEXT.sub(lambda m: names.get(m.group(0), "<id>"), value))
    if isinstance(value, list):
        return [normalize(v, names) for v in value]
    if isinstance(value, dict):
        if value and all(UUID.match(k) and k not in names for k in value):
            # keyed by ids generated on each side (e.g. grid cells): compare the entries, in a stable order
            entries = [normalize(v, names) for v in value.values()]
            return sorted(entries, key=lambda entry: json.dumps(entry, sort_keys=True))
        return {k: normalize(v, names) for k, v in sorted(value.items()) if k not in VOLATILE}
    return value


def shape_keys(objects):
    """{id: key} naming each shape by its path from the page root, `parent/child`, with `[n]` for the
    n-th sibling of the same name (n > 0), so copies of a component that repeat names stay apart."""
    keys = {}

    def key_of(shape_id):
        if shape_id in keys:
            return keys[shape_id]
        shape = objects[shape_id]
        parent_id = shape.get("parentId")
        if parent_id is None or parent_id == shape_id or parent_id not in objects:
            keys[shape_id] = shape["name"]
            return keys[shape_id]
        parent = objects[parent_id]
        same = [s for s in parent.get("shapes", []) if s in objects and objects[s]["name"] == shape["name"]]
        index = same.index(shape_id) if shape_id in same else 0
        prefix = "" if parent.get("parentId") == parent_id else key_of(parent_id) + "/"
        keys[shape_id] = prefix + shape["name"] + (f"[{index}]" if index else "")
        return keys[shape_id]

    for shape_id in objects:
        key_of(shape_id)
    return keys


def saved_shapes(file_id):
    """{page/key: normalized shape} of every page of a file, as the backend has it (see `shape_keys`), plus
    `page/(page)` for the page's own data (flows, ruler guides)."""
    data = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["data"]
    shapes, names = {}, {}
    for page_id in data["pages"]:
        page = data["pagesIndex"][page_id]
        names[page_id] = "page:" + page["name"]
        names.update(shape_keys(page["objects"]))
    for page_id in data["pages"]:
        page = data["pagesIndex"][page_id]
        for shape_id, shape in page["objects"].items():
            shapes[f'{names[page_id]}/{names[shape_id]}'] = normalize(shape, names)
        # page-level data: flows, ruler guides
        shapes[f'{names[page_id]}/(page)'] = normalize({k: v for k, v in page.items() if k != "objects"}, names)
    return shapes


def page_shape_names(file_id):
    """Sorted names of the shapes of the file's first page, repeated names included."""
    data = mcpv.rpc_ok("get-file", {"id": file_id}, mcpv.token("editor"))["data"]
    return sorted(shape["name"] for shape in data["pagesIndex"][data["pages"][0]]["objects"].values())


def diff(a, b, path=""):
    """Paths where two normalized values differ (at most 20)."""
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            out += diff(a.get(key), b.get(key), f"{path}.{key}")
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f"{path}[{i}]")
    elif a != b:
        out.append({"path": path or ".", "browser": a, "server": b})
    return out[:20]


class DualRun:
    # The browser shows messages in its own language when the profile has none; the executor has no
    # browser language and uses the profile's (English when unset). The tabs of the stack run in Korean.
    LANGUAGE = "ko"

    def __init__(self, space, session=None):
        profile = mcpv.rpc_ok("get-profile", {}, mcpv.token("editor"))
        if profile.get("lang") != self.LANGUAGE:
            mcpv.rpc_ok("update-profile", {"fullname": profile["fullname"], "lang": self.LANGUAGE},
                        mcpv.token("editor"))
        self.space = space
        self.session = session or f"dual-{time.time_ns()}"
        self.client = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
        self.browser = observers.Tabs(space, labels=("p2",))
        self.observer = observers.Tabs(space, labels=("p1",))

    LIBRARY_STATE = """
const l = penpot.library.local;
const byName = (a, b) => (a.name + a.path).localeCompare(b.name + b.path);
return {
  colors: l.colors.map((c) => ({ name: c.name, path: c.path, color: c.color, opacity: c.opacity, gradient: c.gradient || null })).sort(byName),
  typographies: l.typographies.map((t) => ({ name: t.name, path: t.path, fontId: t.fontId, fontFamily: t.fontFamily,
    fontVariantId: t.fontVariantId, fontSize: t.fontSize, fontWeight: t.fontWeight, fontStyle: t.fontStyle,
    lineHeight: t.lineHeight, letterSpacing: t.letterSpacing, textTransform: t.textTransform })).sort(byName),
  components: l.components.map((c) => ({ name: c.name, path: c.path })).sort(byName),
  sets: l.tokens.sets.map((s) => ({ name: s.name, active: s.active,
    tokens: s.tokens.map((t) => ({ name: t.name, type: t.type, value: t.value, description: t.description }))
      .sort((a, b) => a.name.localeCompare(b.name)) })),
  themes: l.tokens.themes.map((t) => ({ group: t.group, name: t.name, active: t.active, sets: t.activeSets.map((s) => s.name).sort() })),
};"""

    def library_state(self, file_id):
        """The file's library assets as a fresh executor session reads them back (get-file does not return
        them as JSON)."""
        reader = mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
        response, _ = reader.execute_code(self.LIBRARY_STATE, fileId=file_id, sessionId=f"{self.session}-reader")
        return normalize(response["result"], {})

    def scenario(self, name, code, compare_saved=True, compare_library=False):
        browser_file, browser_page = mcpv.create_file(f"dual-{name}-browser")
        server_file, server_page = mcpv.create_file(f"dual-{name}-server")
        self.browser.open(browser_file, browser_page)
        self.observer.open(server_file, server_page)

        browser = self.browser.run_code("p2", code)
        try:
            response, seconds = self.client.execute_code(code, fileId=server_file, sessionId=self.session)
            server = {"ok": True, "result": response["result"], "commit": response["commit"], "seconds": seconds}
        except mcp_client.ToolError as error:
            server = {"ok": False, "error": str(error)}

        report = {"name": name, "browserFile": browser_file, "serverFile": server_file,
                  "browserOk": browser.get("ok"), "serverOk": server["ok"]}
        if not browser.get("ok") or not server["ok"]:
            report["browserError"] = browser.get("error")
            report["serverError"] = server.get("error")
            report["ok"] = False
            return report

        report["serverSeconds"] = round(server["seconds"], 3)
        report["commit"] = server["commit"]
        result_diff = diff(normalize(browser["result"], {}), normalize(server["result"], {}))
        report["resultDiff"] = result_diff

        saved_ok = True
        if compare_saved:
            # the browser saves on its own schedule: wait until its file settles
            browser_shapes = self.settled_shapes(browser_file)
            server_shapes = saved_shapes(server_file)
            missing = sorted(set(browser_shapes) ^ set(server_shapes))
            shape_diff = {key: diff(browser_shapes[key], server_shapes[key])
                          for key in sorted(set(browser_shapes) & set(server_shapes))}
            shape_diff = {key: value for key, value in shape_diff.items() if value}
            report["savedShapes"] = len(server_shapes)
            report["onlyInOne"] = missing
            report["savedDiff"] = shape_diff
            saved_ok = not missing and not shape_diff

            # the observer tab got the server's result without a reload, and keeps it after one
            expected = page_shape_names(server_file)
            live, live_s = wait_until(lambda: self.observer.shape_names("p1") == expected, timeout=10)
            reloaded = self.observer.shape_names("p1", reload=True) == expected
            report["observer"] = {"liveWithoutReload": bool(live), "seconds": live_s, "afterReload": reloaded}
            saved_ok = saved_ok and bool(live) and reloaded

        if compare_library:
            time.sleep(2)
            library_diff = diff(self.library_state(browser_file), self.library_state(server_file))
            report["libraryDiff"] = library_diff
            saved_ok = saved_ok and not library_diff

        report["ok"] = not result_diff and saved_ok
        return report

    def settled_shapes(self, file_id, timeout=10):
        last, stable_since = None, time.monotonic()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            shapes = saved_shapes(file_id)
            if shapes != last:
                last, stable_since = shapes, time.monotonic()
            elif time.monotonic() - stable_since > 2:
                break
            time.sleep(0.5)
        return last


def wait_until(predicate, timeout=5.0):
    started = time.monotonic()
    while True:
        value = predicate()
        if value or time.monotonic() - started > timeout:
            return value, round(time.monotonic() - started, 2)
        time.sleep(0.3)
