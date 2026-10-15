"""
PEN-9: which Plugin API members the server executor really ran during the
experiments, matched against every member of `feature-inventory.md`.

    python3 -I mcp/docs/server-mcp/experiments/pen9_coverage.py run --space 206   # traced regression
    python3 -I mcp/docs/server-mcp/experiments/pen9_coverage.py report            # match, from the log

`run` restarts the MCP server with `PENPOT_EXECUTOR_TRACE_API=1`, so every
execution prints the members its code read, wrote or called
(`executor/child/ApiTrace.ts`), runs `pen9_regression.py` into
`.mcp-verify/pen9/coverage-run/`, and restarts the server without the trace.
`report` reads those lines from the MCP log and writes
`.mcp-verify/pen9/coverage.json`: per member, whether some execution used it.
A member no execution used is "not run", never counted as verified.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))

import mcp_client  # noqa: E402
import mcpv  # noqa: E402

OUT = mcpv.STATE / "pen9"
LOG = mcpv.STATE / "logs" / "mcp.log"
MARK = OUT / "coverage-log-range.json"
MARKER = "[api-trace] "

# the MCP command of `docker/mcp-verify/files/start-services.sh` (multi-user), with the trace switch read
# from a file, so the window's "repeat last command" restart keeps the chosen mode
RUN_SCRIPT = """#!/usr/bin/env bash
cd ~/penpot/mcp
export PENPOT_EXECUTOR_TRACE_API="$(cat ~/penpot/.mcp-verify/trace-api 2>/dev/null || echo 0)"
echo "[mcp-verify] PENPOT_EXECUTOR_TRACE_API=$PENPOT_EXECUTOR_TRACE_API"
PENPOT_MCP_SERVER_HOST=0.0.0.0 PENPOT_MCP_REMOTE_MODE=true PENPOT_TENANT="$PENPOT_TENANT" \\
PENPOT_MCP_EXECUTOR=optional \\
PENPOT_MCP_EXECUTOR_BUNDLE=$HOME/penpot/frontend/target/executor/executor.js \\
PENPOT_MCP_EXECUTOR_WASM_DIR=$HOME/penpot/frontend/resources/public/js \\
PENPOT_MCP_EXECUTOR_PUBLIC_URI=http://localhost:3450 \\
PENPOT_MCP_SHARED_KEY=super-secret-mcp-key \\
PENPOT_FLAGS='enable-mcp enable-access-tokens' \\
PENPOT_MCP_REDIS_URI=redis://valkey/1 pnpm run start:multi-user
"""


def restart_mcp(trace):
    """Restarts the MCP server in its tmux window, with the API trace on or off."""
    (mcpv.STATE / "mcp-run.sh").write_text(RUN_SCRIPT)
    (mcpv.STATE / "trace-api").write_text("1" if trace else "0")
    wait = "for i in $(seq 1 100); do pgrep -f 'dist/[i]ndex.js --multi-user' >/dev/null || break; sleep 0.2; done; sleep 1"
    subprocess.run(["docker", "exec", "-u", "penpot", mcpv.MAIN, "bash", "-lc",
                    f"tmux send-keys -t mcpv:mcp C-c; {wait}; "
                    "tmux send-keys -t mcpv:mcp 'bash ~/penpot/.mcp-verify/mcp-run.sh' enter"], check=True)
    for _ in range(90):
        try:
            mcp_client.Client(mcpv.token("editor", "mcp"), executor="server")
            return
        except Exception:  # noqa: BLE001
            time.sleep(1)
    raise RuntimeError("the MCP server did not come back")


def traced_members(start, end):
    """Every `<kind>.<member>` the trace lines of the MCP log between two byte offsets name."""
    members = set()
    with LOG.open("rb") as log:
        log.seek(start)
        chunk = log.read(end - start).decode(errors="replace")
    for line in chunk.splitlines():
        at = line.find(MARKER)
        if at >= 0:
            try:
                members.update(json.loads(line[at + len(MARKER):]))
            except ValueError:
                pass
    return members


# Symbol.toStringTag of the frontend's API objects (`obj/reify {:name ...}`) -> Plugin API interfaces
TAGS = {
    "ActiveUserProxy": ["ActiveUser"], "CommentProxy": ["Comment"], "CommentThreadProxy": ["CommentThread"],
    "CurrentUserProxy": ["User"], "ExportProxy": ["Export"], "FileProxy": ["File"],
    "FileVersionProxy": ["FileVersion"], "FillProxy": ["Fill"], "FlagProxy": ["Flags"],
    "FlexLayoutProxy": ["FlexLayout"], "FlowProxy": ["Flow"], "FontProxy": ["Font"],
    "FontVariantProxy": ["FontVariant"], "GradientProxy": ["Gradient"], "GridCellProxy": ["LayoutCellProperties"],
    "GridLayoutProxy": ["GridLayout"], "HistorySubcontext": ["HistoryContext"], "ImageData": ["ImageData"],
    "InteractionProxy": ["Interaction"], "LayoutChildProxy": ["LayoutChildProperties"],
    "LibraryColorProxy": ["LibraryColor"], "LibraryComponentProxy": ["LibraryComponent", "LibraryVariantComponent"],
    "LibraryProxy": ["Library"], "LibraryTypographyProxy": ["LibraryTypography"], "LocalStorageProxy": ["LocalStorage"],
    "PageProxy": ["Page"], "PenpotContext": ["Penpot"], "PenpotFontsSubcontext": ["FontsContext"],
    "PenpotLibrarySubcontext": ["LibraryContext"], "PenpotManagementContext": ["PenpotMgmt"],
    "RulerGuideProxy": ["RulerGuide"], "ShadowProxy": ["Shadow"], "StrokeProxy": ["Stroke"],
    "TextRange": ["TextRange"], "TokenSetProxy": ["TokenSet"], "TokenThemeProxy": ["TokenTheme"],
    "TokensCatalog": ["TokenCatalog"], "TrackProxy": ["Track"], "UserProxy": ["User"], "VariantProxy": ["Variants"],
    "ViewportProxy": ["Viewport"],
}
SHAPES = {"rectangle": ["Rectangle"], "ellipse": ["Ellipse"], "board": ["Board", "VariantContainer"],
          "group": ["Group"], "boolean": ["Boolean"], "bool": ["Boolean"], "path": ["Path"], "text": ["Text"],
          "image": ["Image"], "svg-raw": ["SvgRaw"], "null": ["ShapeBase"]}
TOKENS = {"color": "TokenColor", "spacing": "TokenSpacing", "borderRadius": "TokenBorderRadius",
          "sizing": "TokenSizing", "opacity": "TokenOpacity", "borderWidth": "TokenBorderWidth",
          "fontSizes": "TokenFontSizes", "dimension": "TokenDimension", "fontFamilies": "TokenFontFamilies",
          "fontWeights": "TokenFontWeights", "letterSpacing": "TokenLetterSpacing", "number": "TokenNumber",
          "rotation": "TokenRotation", "textCase": "TokenTextCase", "textDecoration": "TokenTextDecoration",
          "typography": "TokenTypography", "shadow": "TokenShadow"}
ROOTS = {"penpot": ["Penpot"], "penpotMgmt": ["PenpotMgmt"]}
# members whose declared type the parser cannot follow: `PathCommand` is not exported, so the inventory
# (and `declarations`) list its members under `Path`
UNTYPED = {"commands": [("Path", "")]}
# members no MCP code can use, so a run cannot cover them: (interface, member or "*") -> reason
NOT_APPLICABLE = {
    ("Context", "addListener"): "`Penpot` omits it (Omit<Context, 'addListener' | 'removeListener' | 'management'>)",
    ("Context", "removeListener"): "`Penpot` omits it",
    ("Context", "management"): "`Penpot` omits it; MCP code has `penpotMgmt`",
    ("LocalStorage", "*"): "the MCP plugin manifest has no allow:localstorage permission: `penpot.localStorage` "
                           "refuses in a browser and on the server alike (pen9_gaps.py `context`)",
}
# elements of nested arrays the inventory does not list on their own
IGNORED_KINDS = re.compile(r"(^GradientStopProxy$|\.gradient\.stops$)")
GENERIC = {"Omit", "Pick", "Partial", "Promise", "Array", "Record", "Readonly", "Exclude"}


def declarations():
    """{interface: (parents, {member: type text})} of the Plugin API declarations, and the union types
    ({name: [members]})."""
    src = (mcpv.ROOT / "plugins/libs/plugin-types/index.d.ts").read_text()
    decls = list(re.finditer(r"^export (?:declare )?(interface|type) (\w+)", src, re.M))
    out, unions = {}, {}
    for i, m in enumerate(decls):
        kind, name = m.groups()
        body = src[m.end():decls[i + 1].start() if i + 1 < len(decls) else len(src)]
        if kind == "type":
            head = body.split(";", 1)[0]
            if "{" not in head.split("=", 1)[-1][:3]:
                unions[name] = re.findall(r"\b([A-Z]\w+)\b", re.sub(r"'[^']*'", "", head))
                continue
        clause = body.split("{", 1)[0]
        parents = [p for p in re.findall(r"\b([A-Z]\w+)\b", re.sub(r"'[^']*'", "", clause)) if p not in GENERIC]
        members = {}
        for mm in re.finditer(r"^ {2}(?:readonly )?(\w+)\??(\([^)]*\))?\s*:\s*([^;\n]+)", body, re.M):
            members[mm.group(1)] = mm.group(3)
        out[name] = (parents, members)
    return out, unions


def resolve_type(text, decls, unions):
    """Interfaces a member's declared type names (arrays, promises, unions and null taken apart)."""
    names = []
    for word in re.findall(r"\b([A-Z]\w+)\b", text):
        if word in decls:
            names.append(word)
        elif word in unions:
            names += [u for u in unions[word] if u in decls]
    return names


def ancestors(name, decls, seen=None):
    seen = seen if seen is not None else set()
    if name in seen or name not in decls:
        return seen
    seen.add(name)
    for parent in decls[name][0]:
        ancestors(parent, decls, seen)
    return seen


def resolve_kind(kind, decls, unions):
    """[(interface, member prefix)] that a traced kind stands for; [] when unknown."""
    if kind in ROOTS:
        return [(i, "") for i in ROOTS[kind]]
    tag, _, sub = kind.partition(":")
    if tag == "ShapeProxy" and "." not in kind:
        return [(i, "") for i in SHAPES.get(sub, [])]
    if tag == "TokenProxy" and "." not in kind:
        return [(TOKENS[sub], "")] if sub in TOKENS else [("TokenBase", "")]
    if kind in TAGS:
        return [(i, "") for i in TAGS[kind]]
    if IGNORED_KINDS.search(kind):
        return [("", "")]
    # a path: the parent kind's member, through its declared type
    parent, _, member = kind.rpartition(".")
    call = member.endswith("()")
    member = member[:-2] if call else member
    out = []
    for interface, prefix in resolve_kind(parent, decls, unions) if parent else []:
        for owner in ancestors(interface, decls):
            text = decls[owner][1].get(prefix + member)
            if text is None:
                continue
            if text.strip().startswith("{"):
                out.append((owner, f"{prefix}{member}."))  # an inline object type: its members are nested names
            else:
                if call:
                    text = text.split("=>")[-1]
                out += [(t, "") for t in resolve_type(text, decls, unions)] or UNTYPED.get(member, [])
    return out


def report(_args):
    os.chdir(mcpv.ROOT)
    import gen_inventory  # noqa: E402  (reads its inputs relative to the working directory)

    mark = json.loads(MARK.read_text())
    traced = traced_members(mark["start"], mark["end"])
    decls, unions = declarations()
    covered, unknown_kinds = set(), set()
    for entry in traced:
        kind, _, member = entry.rpartition(".")
        member, _, event = member.partition(":")
        if event:
            covered.add(("EventsMap", event))
        targets = resolve_kind(kind, decls, unions)
        if not targets:
            unknown_kinds.add(kind)
        for interface, prefix in targets:
            if not interface:
                continue
            for owner in ancestors(interface, decls):
                covered.add((owner, prefix + member))

    with LOG.open("rb") as log:
        log.seek(mark["start"])
        chunk = log.read(mark["end"] - mark["start"]).decode(errors="replace")
    tools_run = set(re.findall(r"Tool execution #\d+ starting: (\w+)", chunk))

    rows, by_area = [], {}
    for interface, members in sorted(gen_inventory.parse_api().items()):
        for name, is_method, readonly in members:
            area = gen_inventory.area_of(interface, name)
            kind = gen_inventory.classify(interface, name, is_method, readonly, area)
            ran = (interface, name) in covered
            reason = NOT_APPLICABLE.get((interface, name)) or NOT_APPLICABLE.get((interface, "*"))
            rows.append({"interface": interface, "member": name, "area": area,
                         "ticket": gen_inventory.AREAS[area][0], "class": kind, "ran": ran,
                         **({"notApplicable": reason} if reason and not ran else {})})
            if reason and not ran:
                by_area.setdefault(area, {"ticket": gen_inventory.AREAS[area][0], "members": 0, "ran": 0,
                                          "valueObjects": 0, "valueObjectsRan": 0, "notRun": []})
                by_area[area].setdefault("notApplicable", []).append(f"{interface}.{name}")
                continue
            entry = by_area.setdefault(area, {"ticket": gen_inventory.AREAS[area][0], "members": 0, "ran": 0,
                                              "valueObjects": 0, "valueObjectsRan": 0, "notRun": []})
            if kind == "data":
                entry["valueObjects"] += 1
                entry["valueObjectsRan"] += ran
            else:
                entry["members"] += 1
                entry["ran"] += ran
                if not ran:
                    entry["notRun"].append(f"{interface}.{name}")
    tools = {tool: tool in tools_run for tool, _, _ in gen_inventory.MCP_TOOL_AREA.values()}
    behaviour = [r for r in rows if r["class"] != "data" and "notApplicable" not in r]
    summary = {
        "members": len(behaviour), "ran": sum(r["ran"] for r in behaviour),
        "notApplicable": sum(1 for r in rows if "notApplicable" in r),
        "valueObjects": sum(1 for r in rows if r["class"] == "data"),
        "valueObjectsRan": sum(r["ran"] for r in rows if r["class"] == "data"),
        "tools": tools, "unknownKinds": sorted(unknown_kinds), "tracedEntries": len(traced),
    }
    out = {"summary": summary, "areas": by_area, "members": rows}
    (OUT / "coverage.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps({"summary": summary,
                      "areas": {a: {k: v for k, v in e.items() if k != "notRun"} | {"notRun": len(e["notRun"])}
                                for a, e in by_area.items()}}, indent=1, ensure_ascii=False))


def run(args):
    OUT.mkdir(parents=True, exist_ok=True)
    restart_mcp(trace=True)
    start = LOG.stat().st_size
    try:
        command = [sys.executable, "-I", str(HERE / "pen9_regression.py"), "--space", str(args.space),
                   "--out", "coverage-run"] + (["--only", *args.only] if args.only else [])
        code = subprocess.run(command).returncode
    finally:
        end = LOG.stat().st_size
        MARK.write_text(json.dumps({"start": start, "end": end}))
        restart_mcp(trace=False)
    print(json.dumps({"regressionExit": code, "traceLines": len(traced_members(start, end))}))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--space", type=int, required=True)
    run_parser.add_argument("--only", nargs="*")
    sub.add_parser("kinds")
    sub.add_parser("report")
    args = parser.parse_args()
    if args.command == "run":
        run(args)
    elif args.command == "report":
        report(args)
    elif args.command == "kinds":
        mark = json.loads(MARK.read_text())
        kinds = {}
        for member in traced_members(mark["start"], mark["end"]):
            kind, _, name = member.rpartition(".")
            kinds.setdefault(kind, []).append(name)
        print(json.dumps({k: sorted(v) for k, v in sorted(kinds.items())}, indent=1))


if __name__ == "__main__":
    main()
