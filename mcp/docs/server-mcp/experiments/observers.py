"""
Observer browser tabs of the mcp-verify stack, driven through ego-browser:
p1 = owner at http://localhost:3550, p2 = editor at http://127.0.0.1:3550
(see verification-env.md). The tabs only read; writes come from MCP.

    import observers
    tabs = observers.Tabs(space=2)
    tabs.open(file_id, page_id)
    tabs.evaluate("p1", "return cljs.core.count(...)")
"""

import json
import subprocess
import time
from pathlib import Path

import mcpv

HERE = Path(__file__).resolve().parent
HOSTS = {"p1": "localhost", "p2": "127.0.0.1"}

READY = """() => { try { const s = cljs.core.deref(app.main.store.state);
  return cljs.core.get(s, cljs.core.keyword("workspace-ready")) != null
      && cljs.core.get(s, cljs.core.keyword("current-page-id")) != null; } catch (e) { return false; } }"""


def ego(script, timeout=180):
    """Runs an ego-browser script; returns its combined output (the console goes to stderr)."""
    out = subprocess.run(["ego-browser", "nodejs"], input=script, capture_output=True, text=True,
                         timeout=timeout)
    return out.stdout + out.stderr


def marked(output, marker):
    lines = [l for l in output.splitlines() if l.startswith(marker)]
    if not lines:
        raise RuntimeError(f"no {marker} in ego output: {output[-1500:]}")
    return json.loads(lines[-1][len(marker):])


class Tabs:
    def __init__(self, space, labels=("p1", "p2")):
        self.space = space
        self.labels = labels

    def open(self, file_id, page_id=None):
        """Opens the file's workspace in every tab and waits until it is ready."""
        team = mcpv.fixtures()["team"]["id"]
        query = f"team-id={team}&file-id={file_id}" + (f"&page-id={page_id}" if page_id else "")
        script = "const task = await taskSpace(%d);\n" % self.space
        for label in self.labels:
            script += """
{ const page = task.page(%s);
  await page.goto(%s);
  await page.waitForFunction(%s, undefined, { timeout: 60000 }); }
""" % (json.dumps(label), json.dumps(f"http://{HOSTS[label]}:3550/#/workspace?{query}"), READY)
        script += 'console.log("RESULT=true");'
        return marked(ego(script), "RESULT=")

    def blank(self):
        script = "const task = await taskSpace(%d);\n" % self.space
        for label in self.labels:
            script += "await task.page(%s).goto('about:blank');\n" % json.dumps(label)
        script += 'console.log("RESULT=true");'
        return marked(ego(script), "RESULT=")

    def evaluate(self, label, body, reload=False):
        """Evaluates `body` (a function body that returns JSON data) in a tab's page."""
        script = """
const task = await taskSpace(%d);
const page = task.page(%s);
if (%s) { await page.reload(); await page.waitForFunction(%s, undefined, { timeout: 60000 }); }
const value = await page.evaluate(() => { %s });
console.log("RESULT=" + JSON.stringify(value));
""" % (self.space, json.dumps(label), "true" if reload else "false", READY, body)
        return marked(ego(script), "RESULT=")

    def shape_names(self, label, reload=False):
        return self.evaluate(label, """
const k = cljs.core.keyword;
const s = cljs.core.deref(app.main.store.state);
const objects = app.main.data.helpers.lookup_page_objects(s);
return cljs.core.into_array(cljs.core.map((e) => cljs.core.get(cljs.core.val(e), k("name")), objects)).sort();
""", reload=reload)

    def page_names(self, label, reload=False):
        """Names of the open file's pages, in order."""
        return self.evaluate(label, """
const k = cljs.core.keyword;
const s = cljs.core.deref(app.main.store.state);
const data = app.main.data.helpers.lookup_file_data(s);
const index = cljs.core.get(data, k("pages-index"));
return cljs.core.into_array(cljs.core.map((id) => cljs.core.get(cljs.core.get(index, id), k("name")),
                                          cljs.core.get(data, k("pages"))));
""", reload=reload)

    def run_code(self, label, code, settle=1500):
        """Runs Plugin API code in a tab's open workspace the way the MCP plugin does (`browser_run.js`).
        Returns {ok, ms, result | error}."""
        options = {"space": self.space, "page": label, "code": code, "settle": settle}
        script = "globalThis.RUN = " + json.dumps(options) + ";\n" + (HERE / "browser_run.js").read_text()
        out = ego(script, timeout=300)
        lines = [l for l in out.splitlines() if l.startswith("{")]
        if not lines:
            raise RuntimeError("browser run failed: " + out[-1500:])
        return json.loads(lines[-1])

    def observe(self, expect, timeout=20000):
        """Starts `browser_observe.js` on the tabs; returns a handle whose `report()` waits for the result."""
        state = mcpv.STATE / "observe"
        state.mkdir(parents=True, exist_ok=True)
        ready = state / f"ready-{time.time_ns()}"
        options = {"space": self.space, "pages": list(self.labels), "expect": expect,
                   "timeout": timeout, "ready": str(ready)}
        script = "globalThis.OBS = " + json.dumps(options) + ";\n" + (HERE / "browser_observe.js").read_text()
        proc = subprocess.Popen(["ego-browser", "nodejs"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        proc.stdin.write(script)
        proc.stdin.close()
        for _ in range(300):
            if ready.exists():
                return Observation(proc)
            time.sleep(0.1)
        proc.kill()
        raise RuntimeError("observer did not start: " + proc.stdout.read()[-1500:])


class Observation:
    def __init__(self, proc):
        self.proc = proc

    def report(self):
        out = self.proc.stdout.read()
        self.proc.wait(timeout=60)
        lines = [l for l in out.splitlines() if l.startswith("{")]
        return json.loads(lines[-1])
