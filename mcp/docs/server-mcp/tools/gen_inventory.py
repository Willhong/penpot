#!/usr/bin/env python3
#
# Generates feature-inventory.md: every member of the Plugin API
# (plugins/libs/plugin-types/index.d.ts) and every MCP tool, each mapped to a
# feature area with an owning PEN ticket and a verification scenario.
#
#   python3 -I mcp/docs/server-mcp/tools/gen_inventory.py          # rewrite
#   python3 -I mcp/docs/server-mcp/tools/gen_inventory.py --check  # CI-style
#
# Exits non-zero when a member or tool is unmapped, or (with --check) when the
# committed Markdown is stale. Run from the repository root.

import argparse
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
TYPES = ROOT / "plugins/libs/plugin-types/index.d.ts"
FRONTEND_PLUGINS = ROOT / "frontend/src/app/plugins"
RUNTIME_API = ROOT / "plugins/libs/plugins-runtime/src/lib/api/index.ts"
MCP_TOOLS = ROOT / "mcp/packages/server/src/tools"
OUT = ROOT / "mcp/docs/server-mcp/feature-inventory.md"

# area id -> (ticket, title, verification scenario)
AREAS = {
    "runtime": ("PEN-10", "실행 컨텍스트·루트 객체",
                "브라우저 0개 상태에서 execute_code 동등 실행으로 penpot.version/currentFile/currentPage/root/utils를 읽고, 같은 코드의 브라우저 결과와 값이 같다."),
    "flags": ("PEN-10", "실행 플래그",
              "naturalChildOrdering/throwValidationErrors를 바꾼 뒤 children 순서와 검증 오류 동작이 브라우저와 같다."),
    "storage": ("PEN-10", "플러그인 localStorage·MCP storage",
                "setItem→다른 호출에서 getItem/getKeys→removeItem이 같은 사용자·세션 범위에서만 보이고 다른 사용자에게는 보이지 않는다."),
    "users": ("PEN-10", "현재 사용자·접속 사용자",
              "currentUser가 토큰 주인과 같고, 브라우저 사용자가 파일을 열면 activeUsers에 나타나며 서버 실행 주체도 정책대로 표시된다."),
    "events": ("PEN-10", "이벤트 구독",
               "on('shapechange'|'filechange'|'contentsave'...) 구독 후 다른 클라이언트의 변경·저장이 이벤트로 오고 off 후 오지 않는다."),
    "ui": ("PEN-10", "브라우저 UI 전용(선택·뷰포트·테마·플러그인 창)",
           "브라우저 0개에서 호출하면 PEN-1 결정표의 방식(서버 컨텍스트/관찰/명시적 UI 전용 오류)대로 응답하고 조용히 무시하지 않는다."),
    "filemgmt": ("PEN-4", "프로젝트·파일 관리",
                 "listProjects/listFiles/createProject/createFile/openFile을 브라우저 없이 실행하고 대시보드 재조회 결과와 같다; 권한 없는 사용자는 거부된다."),
    "file": ("PEN-4", "파일 메타데이터·버전·검증",
             "File.id/name/revn/pages를 읽고 saveVersion→findVersions→pin/restore/remove 결과가 대시보드 버전 목록과 같으며 validate가 오류 목록을 돌려준다."),
    "page": ("PEN-4", "페이지 관리",
             "createPage/이름 변경/remove 후 새로 연 브라우저와 get-file 결과에 같은 페이지 목록이 보인다."),
    "query": ("PEN-5", "도형 조회",
              "getShapeById/findShapes/root/children으로 얻은 도형 id·속성이 같은 파일의 브라우저 결과와 같다."),
    "shape": ("PEN-5", "기본 도형 속성·생성·삭제",
              "rect/ellipse/board 생성→속성 변경(fill·stroke·shadow·blur·opacity·radius·export·pluginData)→clone→remove를 서버에서 실행하고, 저장된 shape map이 브라우저 실행 결과와 정규화 후 같으며 열린 캔버스에 지연 기준 안에 반영된다."),
    "hierarchy": ("PEN-11", "계층·변환·정렬",
                  "group/ungroup/appendChild/insertChild/setParentIndex/z-order/resize/rotate/flip/constraints/align/distribute 결과의 parent·순서·selrect·points·transform이 브라우저 결과와 허용 오차 안에서 같다."),
    "path": ("PEN-11", "패스·Boolean·마스크·flatten",
             "createPath(content/d)·createBoolean 4종·flatten·makeMask 결과의 path content와 bool content가 브라우저 결과와 허용 오차 안에서 같다."),
    "text": ("PEN-12", "텍스트·폰트·부분 스타일",
             "createText→characters·폰트·부분 range 스타일·growType 변경 후 content 트리와 position-data·selrect가 브라우저 결과와 허용 오차 안에서 같다."),
    "layout": ("PEN-13", "Flex·Grid 레이아웃",
               "중첩 flex/grid 생성·트랙·셀·자식 속성 변경 후 모든 자식의 selrect가 브라우저 reflow 결과와 허용 오차 안에서 같고 waitForLayoutUpdate가 계산 완료 후에 끝난다."),
    "components": ("PEN-14", "컴포넌트·인스턴스·Variants",
                   "createComponent→instance→override→detach/swap/resetOverrides·variant 생성/전환/속성 편집 결과 shape map과 컴포넌트 동기화가 브라우저 결과와 같다."),
    "library": ("PEN-15", "라이브러리 자산·연결",
                "색상·타이포그래피 생성/수정/적용, 공유 라이브러리 연결과 연결 라이브러리 자산 조회 결과가 브라우저와 같다."),
    "tokens": ("PEN-15", "디자인 토큰",
               "token set/theme/token 생성·활성화·적용(applyToken/applyToShapes) 후 resolvedValue와 적용된 shape 속성이 브라우저 결과와 같다."),
    "media": ("PEN-16", "이미지·SVG",
              "uploadMediaUrl/Data→image fill·Image 도형, createShapeFromSvg(WithImages) 결과 shape map과 저장된 미디어 객체가 브라우저 결과와 같다."),
    "prototype": ("PEN-17", "Flow·상호작용·가이드",
                  "flow·interaction(모든 action/animation)·board guide·ruler guide 추가/수정/삭제 결과가 브라우저와 같고 viewer에서 같은 동작을 한다."),
    "comments": ("PEN-18", "댓글",
                 "스레드 생성·답글·resolved·삭제 결과가 브라우저 댓글 패널과 같고 열린 브라우저에 실시간 알림이 온다."),
    "output": ("PEN-19", "내보내기·코드 생성",
               "shape/file export(PNG·JPEG·WEBP·SVG·PDF, .penpot)와 generateMarkup/Style/FontFaces 결과가 브라우저 결과와 PEN-8 동등성 기준(픽셀 차이·구조 비교) 안에서 같다."),
    "history": ("PEN-20", "작업 단위·실행 취소",
                "undoBlockBegin/Finish로 묶은 서버 작업이 하나의 실행 취소 단위가 되고, 실패한 작업은 저장되지 않거나 정책대로 원복된다."),
}

KIND_LABEL = {
    "read": "조회",
    "edit": "편집",
    "rw": "조회·편집",
    "file": "파일관리",
    "output": "출력",
    "ui": "UI 전용",
    "runtime": "런타임",
    "event": "이벤트",
    "data": "값 객체",
}

# interface -> default area. Value-object interfaces (no behaviour, only
# fields of a parent feature) use the area of the feature they describe.
INTERFACE_AREA = {
    "Penpot": "runtime", "Context": "runtime", "ContextUtils": "runtime",
    "ContextGeometryUtils": "runtime", "ContextTypesUtils": "runtime",
    "Flags": "flags", "LocalStorage": "storage",
    "User": "users", "ActiveUser": "users",
    "EventsMap": "events",
    "Viewport": "ui",
    "PenpotMgmt": "filemgmt", "WorkspaceContext": "filemgmt",
    "ProjectSummary": "filemgmt", "FileSummary": "filemgmt",
    "File": "file", "FileVersion": "file", "FileValidationError": "file",
    "Page": "page",
    "PluginData": "shape", "ShapeBase": "shape", "Rectangle": "shape",
    "Ellipse": "shape", "Board": "shape", "Fill": "shape", "Stroke": "shape",
    "Shadow": "shape", "Blur": "shape", "Export": "shape", "Gradient": "shape",
    "Group": "hierarchy",
    "Path": "path", "Boolean": "path",
    "Text": "text", "TextRange": "text", "Font": "text",
    "FontVariant": "text", "FontsContext": "text",
    "CommonLayout": "layout", "FlexLayout": "layout", "GridLayout": "layout",
    "LayoutChildProperties": "layout", "LayoutCellProperties": "layout",
    "Track": "layout",
    "LibraryComponent": "components", "LibraryVariantComponent": "components",
    "Variants": "components", "VariantContainer": "components",
    "Library": "library", "LibraryElement": "library", "LibraryColor": "library",
    "LibraryTypography": "library", "LibrarySummary": "library",
    "LibraryContext": "library", "Color": "library", "ColorShapeInfo": "library",
    "ColorShapeInfoEntry": "library",
    "TokenCatalog": "tokens", "TokenSet": "tokens", "TokenTheme": "tokens",
    "TokenBase": "tokens", "TokenShadowValue": "tokens",
    "TokenShadowValueString": "tokens", "TokenTypographyValue": "tokens",
    "TokenTypographyValueString": "tokens",
    "Image": "media", "SvgRaw": "media",
    "Flow": "prototype", "Interaction": "prototype", "NavigateTo": "prototype",
    "OverlayAction": "prototype", "OpenOverlay": "prototype",
    "ToggleOverlay": "prototype", "CloseOverlay": "prototype",
    "PreviousScreen": "prototype", "OpenUrl": "prototype",
    "Dissolve": "prototype", "Slide": "prototype", "Push": "prototype",
    "GuideColumn": "prototype", "GuideColumnParams": "prototype",
    "GuideRow": "prototype", "GuideSquare": "prototype",
    "GuideSquareParams": "prototype", "RulerGuide": "prototype",
    "Comment": "comments", "CommentThread": "comments",
    "HistoryContext": "history",
    "Bounds": "query", "Point": "query",
    "ImageData": "media",
}

VALUE_OBJECTS = {
    "Fill", "Stroke", "Shadow", "Blur", "Export", "Gradient", "Color",
    "ColorShapeInfo", "ColorShapeInfoEntry", "Track", "LayoutCellProperties",
    "FontVariant", "GuideColumn", "GuideColumnParams", "GuideRow",
    "GuideSquare", "GuideSquareParams", "NavigateTo", "OverlayAction",
    "OpenOverlay", "ToggleOverlay", "CloseOverlay", "PreviousScreen",
    "OpenUrl", "Dissolve", "Slide", "Push", "TokenShadowValue",
    "TokenShadowValueString", "TokenTypographyValue",
    "TokenTypographyValueString", "FileValidationError", "ProjectSummary",
    "FileSummary", "LibrarySummary", "WorkspaceContext", "Bounds", "Point",
    "ImageData",
}

# (interface or "*", member) -> area. "*" applies to every interface.
MEMBER_AREA = {
    # Context: document features reached through the root object.
    ("Context", "management"): "filemgmt",
    ("Context", "currentFile"): "file",
    ("Context", "currentPage"): "page",
    ("Context", "viewport"): "ui",
    ("Context", "flags"): "flags",
    ("Context", "history"): "history",
    ("Context", "library"): "library",
    ("Context", "fonts"): "text",
    ("Context", "currentUser"): "users",
    ("Context", "activeUsers"): "users",
    ("Context", "theme"): "ui",
    ("Context", "localStorage"): "storage",
    ("Context", "selection"): "ui",
    ("Context", "shapesColors"): "library",
    ("Context", "replaceColor"): "library",
    ("Context", "uploadMediaUrl"): "media",
    ("Context", "uploadMediaData"): "media",
    ("Context", "group"): "hierarchy",
    ("Context", "ungroup"): "hierarchy",
    ("Context", "createRectangle"): "shape",
    ("Context", "createBoard"): "shape",
    ("Context", "createEllipse"): "shape",
    ("Context", "createPath"): "path",
    ("Context", "createBoolean"): "path",
    ("Context", "createShapeFromSvg"): "media",
    ("Context", "createShapeFromSvgWithImages"): "media",
    ("Context", "createText"): "text",
    ("Context", "generateMarkup"): "output",
    ("Context", "generateStyle"): "output",
    ("Context", "generateFontFaces"): "output",
    ("Context", "addListener"): "events",
    ("Context", "removeListener"): "events",
    ("Context", "openViewer"): "ui",
    ("Context", "createPage"): "page",
    ("Context", "openPage"): "ui",
    ("Context", "alignHorizontal"): "hierarchy",
    ("Context", "alignVertical"): "hierarchy",
    ("Context", "distributeHorizontal"): "hierarchy",
    ("Context", "distributeVertical"): "hierarchy",
    ("Context", "flatten"): "path",
    ("Context", "createVariantFromComponents"): "components",
    ("Context", "waitForLayoutUpdate"): "layout",
    ("Penpot", "ui"): "ui",
    ("Penpot", "ui.open"): "ui",
    ("Penpot", "ui.size"): "ui",
    ("Penpot", "ui.resize"): "ui",
    ("Penpot", "ui.sendMessage"): "ui",
    ("Penpot", "ui.onMessage"): "ui",
    ("Penpot", "closePlugin"): "ui",
    ("Penpot", "on"): "events",
    ("Penpot", "off"): "events",
    ("PenpotMgmt", "on"): "events",
    ("PenpotMgmt", "off"): "events",
    ("ActiveUser", "position"): "ui",
    ("ActiveUser", "zoom"): "ui",
    ("File", "export"): "output",
    ("Page", "root"): "query",
    ("Page", "getShapeById"): "query",
    ("Page", "findShapes"): "query",
    ("Page", "rulerGuides"): "prototype",
    ("Page", "flows"): "prototype",
    ("Page", "createFlow"): "prototype",
    ("Page", "removeFlow"): "prototype",
    ("Page", "addRulerGuide"): "prototype",
    ("Page", "removeRulerGuide"): "prototype",
    ("Page", "addCommentThread"): "comments",
    ("Page", "removeCommentThread"): "comments",
    ("Page", "findCommentThreads"): "comments",
    # ShapeBase: one shape API, many features.
    ("ShapeBase", "parent"): "query",
    ("ShapeBase", "parentIndex"): "hierarchy",
    ("ShapeBase", "setParentIndex"): "hierarchy",
    ("ShapeBase", "constraintsHorizontal"): "hierarchy",
    ("ShapeBase", "constraintsVertical"): "hierarchy",
    ("ShapeBase", "boardX"): "hierarchy",
    ("ShapeBase", "boardY"): "hierarchy",
    ("ShapeBase", "parentX"): "hierarchy",
    ("ShapeBase", "parentY"): "hierarchy",
    ("ShapeBase", "flipX"): "hierarchy",
    ("ShapeBase", "flipY"): "hierarchy",
    ("ShapeBase", "rotation"): "hierarchy",
    ("ShapeBase", "resize"): "hierarchy",
    ("ShapeBase", "rotate"): "hierarchy",
    ("ShapeBase", "bringToFront"): "hierarchy",
    ("ShapeBase", "bringForward"): "hierarchy",
    ("ShapeBase", "sendToBack"): "hierarchy",
    ("ShapeBase", "sendBackward"): "hierarchy",
    ("ShapeBase", "layoutChild"): "layout",
    ("ShapeBase", "layoutCell"): "layout",
    ("ShapeBase", "waitForLayoutUpdate"): "layout",
    ("ShapeBase", "tokens"): "tokens",
    ("ShapeBase", "applyToken"): "tokens",
    ("ShapeBase", "isComponentInstance"): "components",
    ("ShapeBase", "isComponentMainInstance"): "components",
    ("ShapeBase", "isComponentCopyInstance"): "components",
    ("ShapeBase", "isComponentRoot"): "components",
    ("ShapeBase", "isComponentHead"): "components",
    ("ShapeBase", "componentRefShape"): "components",
    ("ShapeBase", "componentRoot"): "components",
    ("ShapeBase", "componentHead"): "components",
    ("ShapeBase", "component"): "components",
    ("ShapeBase", "detach"): "components",
    ("ShapeBase", "swapComponent"): "components",
    ("ShapeBase", "resetOverrides"): "components",
    ("ShapeBase", "switchVariant"): "components",
    ("ShapeBase", "combineAsVariants"): "components",
    ("ShapeBase", "isVariantHead"): "components",
    ("ShapeBase", "export"): "output",
    ("ShapeBase", "interactions"): "prototype",
    ("ShapeBase", "addInteraction"): "prototype",
    ("ShapeBase", "removeInteraction"): "prototype",
    ("Board", "grid"): "layout",
    ("Board", "flex"): "layout",
    ("Board", "addFlexLayout"): "layout",
    ("Board", "addGridLayout"): "layout",
    ("Board", "guides"): "prototype",
    ("Board", "rulerGuides"): "prototype",
    ("Board", "addRulerGuide"): "prototype",
    ("Board", "removeRulerGuide"): "prototype",
    ("Board", "children"): "hierarchy",
    ("Board", "appendChild"): "hierarchy",
    ("Board", "insertChild"): "hierarchy",
    ("Board", "isVariantContainer"): "components",
    ("Board", "horizontalSizing"): "layout",
    ("Board", "verticalSizing"): "layout",
    ("Boolean", "children"): "hierarchy",
    ("Boolean", "appendChild"): "hierarchy",
    ("Boolean", "insertChild"): "hierarchy",
    ("Group", "isMask"): "path",
    ("Group", "makeMask"): "path",
    ("Group", "removeMask"): "path",
    ("Library", "components"): "components",
    ("Library", "createComponent"): "components",
    ("Library", "tokens"): "tokens",
    ("LibraryTypography", "applyToText"): "text",
    ("LibraryTypography", "applyToTextRange"): "text",
    ("Text", "applyTypography"): "library",
    ("TextRange", "applyTypography"): "library",
    ("TextRange", "fills"): "text",
    ("TokenBase", "applyToSelected"): "ui",
    ("ContextTypesUtils", "isVariantContainer"): "components",
    ("ContextTypesUtils", "isVariantComponent"): "components",
}

OUTPUT_METHODS = {"export", "generateMarkup", "generateStyle", "generateFontFaces", "toD"}
READ_METHOD = re.compile(
    r"^(get|find|is|list|current|component|variantComponents|availableLibraries|"
    r"mainInstance|asFill|asStroke|center|getRange|toD|ui\.size)")

# MCP tool class -> (tool name, area, note). Developer tools exist only in
# the single-user devenv; they still need an owner and a decision.
MCP_TOOL_AREA = {
    "ExecuteCodeTool": ("execute_code", "runtime", "모든 Plugin API 기능의 실행 경로"),
    "HighLevelOverviewTool": ("high_level_overview", "runtime", "지침 문서 제공"),
    "PenpotApiInfoTool": ("penpot_api_info", "runtime", "API 문서 조회"),
    "ExportShapeTool": ("export_shape", "output", "도형 이미지 내보내기"),
    "ExecutionJobTool": ("execution_job", "output", "`async` 실행(큰 내보내기 등)의 상태·결과·취소(서버 실행 전용)"),
    "UndoTool": ("undo", "history", "저장한 실행의 실행 취소·다시 실행(서버 실행 전용)"),
    "RequestStatusTool": ("request_status", "history", "응답을 잃은 요청의 결과 조회(서버 실행 전용)"),
    "ImportImageTool": ("import_image", "media", "로컬 파일 이미지 가져오기(로컬 모드 전용)"),
    "ImportPenpotFileTool": ("import_penpot_file", "filemgmt", ".penpot 파일 가져오기(devenv 단일 사용자 전용)"),
    "CljsReplTool": ("cljs_repl", "runtime", "frontend REPL(devenv 개발 도구)"),
    "CljsCompilerOutputTool": ("cljs_compiler_output", "runtime", "shadow-cljs 컴파일 출력(devenv 개발 도구)"),
    "CljCheckParentheses": ("clj_check_parentheses", "runtime", "Clojure 괄호 검사(devenv 개발 도구)"),
    "ReadTaigaIssueTool": ("read_taiga_issue", "runtime", "Taiga 이슈 조회(devenv 개발 도구)"),
}


def parse_members(body, indent):
    """
    Yields (name, is_method, readonly, nested_body) for the members declared
    at `indent` spaces in an interface or object-type body.
    """
    pattern = re.compile(
        r"^ {%d}(readonly )?([A-Za-z_]\w*)(\?)?\s*([(:<])(.*)$" % indent, re.M)
    for m in pattern.finditer(body):
        readonly, name, _, sep, rest = m.groups()
        is_method = sep in "(<"
        nested = None
        if sep == ":" and rest.strip() == "{":
            close = body.find("\n" + " " * indent + "}", m.end())
            nested = body[m.end():close]
        elif sep == ":" and re.match(r"\s*(<[^>]*>)?\s*\(", rest):
            is_method = True
        yield name, is_method, bool(readonly), nested


def parse_api():
    src = TYPES.read_text()
    decls = list(re.finditer(
        r"^export (?:declare )?(interface|type) (\w+)([^\n]*)", src, re.M))
    interfaces = {}
    for i, m in enumerate(decls):
        kind, name, head = m.groups()
        end = decls[i + 1].start() if i + 1 < len(decls) else len(src)
        body = src[m.end():end]
        members = []
        inline = re.match(r"\s*=\s*\{(.*)\};\s*$", head)
        if kind == "type" and inline:
            for im in re.finditer(r"(readonly )?(\w+)\??:", inline.group(1)):
                members.append((im.group(2), False, bool(im.group(1))))
            interfaces[name] = members
            continue
        if kind == "type" and not head.strip().endswith("= {"):
            continue
        for mname, is_method, readonly, nested in parse_members(body, 2):
            members.append((mname, is_method, readonly))
            if nested is not None:
                for nname, nmethod, nro, _ in parse_members(nested, 4):
                    members.append((f"{mname}.{nname}", nmethod, nro))
        interfaces[name] = members
    return interfaces


def implemented_names():
    text = "\n".join(p.read_text() for p in FRONTEND_PLUGINS.glob("*.cljs"))
    text += RUNTIME_API.read_text()
    return text


def is_implemented(text, member):
    leaf = member.split(".")[-1]
    return bool(re.search(r"(:%s\b|\"%s\"|\b%s\s*[:(])" % (leaf, leaf, leaf), text))


def classify(interface, member, is_method, readonly, area):
    if area == "ui":
        return "ui"
    if area == "events":
        return "event"
    if area == "filemgmt" and is_method:
        return "file"
    if interface in VALUE_OBJECTS:
        return "data"
    leaf = member.split(".")[-1]
    if is_method:
        if leaf in OUTPUT_METHODS:
            return "output"
        if READ_METHOD.match(leaf):
            return "read"
        if area == "runtime":
            return "runtime"
        return "edit"
    return "read" if readonly else "rw"


def area_of(interface, member):
    return (MEMBER_AREA.get((interface, member))
            or MEMBER_AREA.get(("*", member))
            or INTERFACE_AREA.get(interface)
            or (interface.startswith("Token") and "tokens")
            or None)


def mcp_tools():
    tools = []
    for path in sorted(MCP_TOOLS.glob("*.ts")):
        if path.name.endswith(".test.ts"):
            continue
        cls = re.search(r"export class (\w+) extends Tool", path.read_text())
        if cls:
            tools.append(cls.group(1))
    return tools


def render(interfaces, impl_text, tools):
    rows = []
    unmapped = []
    missing_impl = []
    for interface, members in interfaces.items():
        for member, is_method, readonly in members:
            area = area_of(interface, member)
            if area is None:
                unmapped.append(f"{interface}.{member}")
                continue
            kind = classify(interface, member, is_method, readonly, area)
            implemented = is_implemented(impl_text, member)
            if not implemented and interface not in VALUE_OBJECTS:
                missing_impl.append(f"{interface}.{member}")
            rows.append((area, interface, member, is_method, kind, implemented))

    unmapped_tools = [t for t in tools if t not in MCP_TOOL_AREA]

    out = []
    w = out.append
    w("# 전체 기능 목록 (생성 파일)")
    w("")
    w("> `python3 -I mcp/docs/server-mcp/tools/gen_inventory.py`가 만든 파일이다. 직접 고치지 말고")
    w("> 생성기의 매핑을 고친 뒤 다시 만든다. 입력: `plugins/libs/plugin-types/index.d.ts`,")
    w("> `mcp/packages/server/src/tools/*.ts`. 계약 본문은 `01-feature-contract.md`에 있다.")
    w("")
    w("## 요약")
    w("")
    w(f"- Plugin API interface/object type: {len(interfaces)}개, member: {len(rows) + len(unmapped)}개")
    w(f"- 미매핑 member: {len(unmapped)}개, 미매핑 MCP 도구: {len(unmapped_tools)}개")
    w(f"- frontend 구현 이름을 찾지 못한 member(값 객체 제외): {len(missing_impl)}개 — 아래 '구현 확인 필요' 참조")
    w("")
    w("| 영역 | 담당 | member 수 | 조회 | 편집 | 조회·편집 | 출력 | 파일관리 | UI 전용 | 이벤트 | 런타임 | 값 객체 |")
    w("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    order = ["read", "edit", "rw", "output", "file", "ui", "event", "runtime", "data"]
    for area, (ticket, title, _) in AREAS.items():
        arows = [r for r in rows if r[0] == area]
        counts = [sum(1 for r in arows if r[4] == k) for k in order]
        w(f"| {title} (`{area}`) | {ticket} | {len(arows)} | " + " | ".join(str(c) for c in counts) + " |")
    w("")
    w("## 영역별 검증 시나리오")
    w("")
    w("| 영역 | 담당 | 검증 시나리오 |")
    w("|---|---|---|")
    for area, (ticket, title, scenario) in AREAS.items():
        w(f"| {title} (`{area}`) | {ticket} | {scenario} |")
    w("")
    w("## MCP 도구")
    w("")
    w("| 클래스 | 도구 이름 | 영역 | 담당 | 비고 |")
    w("|---|---|---|---|---|")
    for cls in tools:
        name, area, note = MCP_TOOL_AREA.get(cls, ("?", None, "미매핑"))
        ticket = AREAS[area][0] if area else "미매핑"
        w(f"| `{cls}` | `{name}` | `{area}` | {ticket} | {note} |")
    w("")
    w("## 영역별 member")
    w("")
    w("표기: `()`는 메서드, ✗는 frontend/runtime 구현에서 같은 이름을 찾지 못함(값 객체는 검사하지 않음).")
    for area, (ticket, title, _) in AREAS.items():
        arows = [r for r in rows if r[0] == area]
        w("")
        w(f"### {title} (`{area}`) — {ticket}, {len(arows)}개")
        w("")
        by_iface = {}
        for _, interface, member, is_method, kind, implemented in arows:
            label = f"`{member}{'()' if is_method else ''}`"
            if not implemented and interface not in VALUE_OBJECTS:
                label += " ✗"
            by_iface.setdefault(interface, {}).setdefault(KIND_LABEL[kind], []).append(label)
        w("| interface | 성격 | member |")
        w("|---|---|---|")
        for interface, kinds in by_iface.items():
            for kind, labels in kinds.items():
                w(f"| `{interface}` | {kind} | {', '.join(labels)} |")
    w("")
    w("## 구현 확인 필요")
    w("")
    if missing_impl:
        w("선언은 있으나 `frontend/src/app/plugins/*.cljs`와 plugins-runtime API에서 같은 이름을 찾지 못한 member다.")
        w("이름 검색 기반이라 다른 이름으로 구현됐을 수 있다. 각 담당 티켓에서 실제 동작을 확인한다.")
        w("")
        for name in missing_impl:
            w(f"- `{name}`")
    else:
        w("없음.")
    if unmapped or unmapped_tools:
        w("")
        w("## 미매핑")
        w("")
        for name in unmapped + unmapped_tools:
            w(f"- `{name}`")
    w("")
    return "\n".join(out), unmapped, unmapped_tools


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="fail when feature-inventory.md is stale")
    args = parser.parse_args()

    interfaces = parse_api()
    text, unmapped, unmapped_tools = render(interfaces, implemented_names(), mcp_tools())

    if args.check:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"{OUT} is stale; regenerate it", file=sys.stderr)
            return 1
    else:
        OUT.write_text(text)
        print(f"wrote {OUT}")

    if unmapped or unmapped_tools:
        print("unmapped:", ", ".join(unmapped + unmapped_tools), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
