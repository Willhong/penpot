# 전체 기능 목록 (생성 파일)

> `python3 -I mcp/docs/server-mcp/tools/gen_inventory.py`가 만든 파일이다. 직접 고치지 말고
> 생성기의 매핑을 고친 뒤 다시 만든다. 입력: `plugins/libs/plugin-types/index.d.ts`,
> `mcp/packages/server/src/tools/*.ts`. 계약 본문은 `01-feature-contract.md`에 있다.

## 요약

- Plugin API interface/object type: 108개, member: 716개
- 미매핑 member: 0개, 미매핑 MCP 도구: 0개
- frontend 구현 이름을 찾지 못한 member(값 객체 제외): 0개 — 아래 '구현 확인 필요' 참조

| 영역 | 담당 | member 수 | 조회 | 편집 | 조회·편집 | 출력 | 파일관리 | UI 전용 | 이벤트 | 런타임 | 값 객체 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 실행 컨텍스트·루트 객체 (`runtime`) | PEN-10 | 15 | 15 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 실행 플래그 (`flags`) | PEN-10 | 3 | 1 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| 플러그인 localStorage·MCP storage (`storage`) | PEN-10 | 5 | 3 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 현재 사용자·접속 사용자 (`users`) | PEN-10 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 이벤트 구독 (`events`) | PEN-10 | 15 | 0 | 0 | 0 | 0 | 0 | 0 | 15 | 0 | 0 |
| 브라우저 UI 전용(선택·뷰포트·테마·플러그인 창) (`ui`) | PEN-10 | 21 | 0 | 0 | 0 | 0 | 0 | 21 | 0 | 0 | 0 |
| 프로젝트·파일 관리 (`filemgmt`) | PEN-4 | 21 | 2 | 0 | 0 | 0 | 5 | 0 | 0 | 0 | 14 |
| 파일 메타데이터·버전·검증 (`file`) | PEN-4 | 19 | 9 | 5 | 1 | 0 | 0 | 0 | 0 | 0 | 4 |
| 페이지 관리 (`page`) | PEN-4 | 5 | 2 | 2 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 도형 조회 (`query`) | PEN-5 | 10 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 6 |
| 기본 도형 속성·생성·삭제 (`shape`) | PEN-5 | 89 | 12 | 7 | 26 | 0 | 0 | 0 | 0 | 0 | 44 |
| 계층·변환·정렬 (`hierarchy`) | PEN-11 | 33 | 4 | 19 | 10 | 0 | 0 | 0 | 0 | 0 | 0 |
| 패스·Boolean·마스크·flatten (`path`) | PEN-11 | 31 | 6 | 5 | 18 | 2 | 0 | 0 | 0 | 0 | 0 |
| 텍스트·폰트·부분 스타일 (`text`) | PEN-12 | 56 | 18 | 5 | 29 | 0 | 0 | 0 | 0 | 0 | 4 |
| Flex·Grid 레이아웃 (`layout`) | PEN-13 | 65 | 6 | 15 | 36 | 0 | 0 | 0 | 0 | 0 | 8 |
| 컴포넌트·인스턴스·Variants (`components`) | PEN-14 | 40 | 24 | 15 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 라이브러리 자산·연결 (`library`) | PEN-15 | 54 | 12 | 8 | 15 | 0 | 0 | 0 | 0 | 0 | 19 |
| 디자인 토큰 (`tokens`) | PEN-15 | 115 | 50 | 15 | 24 | 0 | 0 | 0 | 0 | 0 | 26 |
| 이미지·SVG (`media`) | PEN-16 | 14 | 2 | 4 | 1 | 0 | 0 | 0 | 0 | 0 | 7 |
| Flow·상호작용·가이드 (`prototype`) | PEN-17 | 75 | 7 | 11 | 8 | 0 | 0 | 0 | 0 | 0 | 49 |
| 댓글 (`comments`) | PEN-18 | 15 | 7 | 5 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| 내보내기·코드 생성 (`output`) | PEN-19 | 5 | 0 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 0 |
| 작업 단위·실행 취소 (`history`) | PEN-20 | 3 | 1 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## 영역별 검증 시나리오

| 영역 | 담당 | 검증 시나리오 |
|---|---|---|
| 실행 컨텍스트·루트 객체 (`runtime`) | PEN-10 | 브라우저 0개 상태에서 execute_code 동등 실행으로 penpot.version/currentFile/currentPage/root/utils를 읽고, 같은 코드의 브라우저 결과와 값이 같다. |
| 실행 플래그 (`flags`) | PEN-10 | naturalChildOrdering/throwValidationErrors를 바꾼 뒤 children 순서와 검증 오류 동작이 브라우저와 같다. |
| 플러그인 localStorage·MCP storage (`storage`) | PEN-10 | setItem→다른 호출에서 getItem/getKeys→removeItem이 같은 사용자·세션 범위에서만 보이고 다른 사용자에게는 보이지 않는다. |
| 현재 사용자·접속 사용자 (`users`) | PEN-10 | currentUser가 토큰 주인과 같고, 브라우저 사용자가 파일을 열면 activeUsers에 나타나며 서버 실행 주체도 정책대로 표시된다. |
| 이벤트 구독 (`events`) | PEN-10 | on('shapechange'|'filechange'|'contentsave'...) 구독 후 다른 클라이언트의 변경·저장이 이벤트로 오고 off 후 오지 않는다. |
| 브라우저 UI 전용(선택·뷰포트·테마·플러그인 창) (`ui`) | PEN-10 | 브라우저 0개에서 호출하면 PEN-1 결정표의 방식(서버 컨텍스트/관찰/명시적 UI 전용 오류)대로 응답하고 조용히 무시하지 않는다. |
| 프로젝트·파일 관리 (`filemgmt`) | PEN-4 | listProjects/listFiles/createProject/createFile/openFile을 브라우저 없이 실행하고 대시보드 재조회 결과와 같다; 권한 없는 사용자는 거부된다. |
| 파일 메타데이터·버전·검증 (`file`) | PEN-4 | File.id/name/revn/pages를 읽고 saveVersion→findVersions→pin/restore/remove 결과가 대시보드 버전 목록과 같으며 validate가 오류 목록을 돌려준다. |
| 페이지 관리 (`page`) | PEN-4 | createPage/이름 변경/remove 후 새로 연 브라우저와 get-file 결과에 같은 페이지 목록이 보인다. |
| 도형 조회 (`query`) | PEN-5 | getShapeById/findShapes/root/children으로 얻은 도형 id·속성이 같은 파일의 브라우저 결과와 같다. |
| 기본 도형 속성·생성·삭제 (`shape`) | PEN-5 | rect/ellipse/board 생성→속성 변경(fill·stroke·shadow·blur·opacity·radius·export·pluginData)→clone→remove를 서버에서 실행하고, 저장된 shape map이 브라우저 실행 결과와 정규화 후 같으며 열린 캔버스에 지연 기준 안에 반영된다. |
| 계층·변환·정렬 (`hierarchy`) | PEN-11 | group/ungroup/appendChild/insertChild/setParentIndex/z-order/resize/rotate/flip/constraints/align/distribute 결과의 parent·순서·selrect·points·transform이 브라우저 결과와 허용 오차 안에서 같다. |
| 패스·Boolean·마스크·flatten (`path`) | PEN-11 | createPath(content/d)·createBoolean 4종·flatten·makeMask 결과의 path content와 bool content가 브라우저 결과와 허용 오차 안에서 같다. |
| 텍스트·폰트·부분 스타일 (`text`) | PEN-12 | createText→characters·폰트·부분 range 스타일·growType 변경 후 content 트리와 position-data·selrect가 브라우저 결과와 허용 오차 안에서 같다. |
| Flex·Grid 레이아웃 (`layout`) | PEN-13 | 중첩 flex/grid 생성·트랙·셀·자식 속성 변경 후 모든 자식의 selrect가 브라우저 reflow 결과와 허용 오차 안에서 같고 waitForLayoutUpdate가 계산 완료 후에 끝난다. |
| 컴포넌트·인스턴스·Variants (`components`) | PEN-14 | createComponent→instance→override→detach/swap/resetOverrides·variant 생성/전환/속성 편집 결과 shape map과 컴포넌트 동기화가 브라우저 결과와 같다. |
| 라이브러리 자산·연결 (`library`) | PEN-15 | 색상·타이포그래피 생성/수정/적용, 공유 라이브러리 연결과 연결 라이브러리 자산 조회 결과가 브라우저와 같다. |
| 디자인 토큰 (`tokens`) | PEN-15 | token set/theme/token 생성·활성화·적용(applyToken/applyToShapes) 후 resolvedValue와 적용된 shape 속성이 브라우저 결과와 같다. |
| 이미지·SVG (`media`) | PEN-16 | uploadMediaUrl/Data→image fill·Image 도형, createShapeFromSvg(WithImages) 결과 shape map과 저장된 미디어 객체가 브라우저 결과와 같다. |
| Flow·상호작용·가이드 (`prototype`) | PEN-17 | flow·interaction(모든 action/animation)·board guide·ruler guide 추가/수정/삭제 결과가 브라우저와 같고 viewer에서 같은 동작을 한다. |
| 댓글 (`comments`) | PEN-18 | 스레드 생성·답글·resolved·삭제 결과가 브라우저 댓글 패널과 같고 열린 브라우저에 실시간 알림이 온다. |
| 내보내기·코드 생성 (`output`) | PEN-19 | shape/file export(PNG·JPEG·WEBP·SVG·PDF, .penpot)와 generateMarkup/Style/FontFaces 결과가 브라우저 결과와 PEN-8 동등성 기준(픽셀 차이·구조 비교) 안에서 같다. |
| 작업 단위·실행 취소 (`history`) | PEN-20 | undoBlockBegin/Finish로 묶은 서버 작업이 하나의 실행 취소 단위가 되고, 실패한 작업은 저장되지 않거나 정책대로 원복된다. |

## MCP 도구

| 클래스 | 도구 이름 | 영역 | 담당 | 비고 |
|---|---|---|---|---|
| `CljCheckParentheses` | `clj_check_parentheses` | `runtime` | PEN-10 | Clojure 괄호 검사(devenv 개발 도구) |
| `CljsCompilerOutputTool` | `cljs_compiler_output` | `runtime` | PEN-10 | shadow-cljs 컴파일 출력(devenv 개발 도구) |
| `CljsReplTool` | `cljs_repl` | `runtime` | PEN-10 | frontend REPL(devenv 개발 도구) |
| `ExecuteCodeTool` | `execute_code` | `runtime` | PEN-10 | 모든 Plugin API 기능의 실행 경로 |
| `ExecutionJobTool` | `execution_job` | `output` | PEN-19 | `async` 실행(큰 내보내기 등)의 상태·결과·취소(서버 실행 전용) |
| `ExportShapeTool` | `export_shape` | `output` | PEN-19 | 도형 이미지 내보내기 |
| `HighLevelOverviewTool` | `high_level_overview` | `runtime` | PEN-10 | 지침 문서 제공 |
| `ImportImageTool` | `import_image` | `media` | PEN-16 | 로컬 파일 이미지 가져오기(로컬 모드 전용) |
| `ImportPenpotFileTool` | `import_penpot_file` | `filemgmt` | PEN-4 | .penpot 파일 가져오기(devenv 단일 사용자 전용) |
| `PenpotApiInfoTool` | `penpot_api_info` | `runtime` | PEN-10 | API 문서 조회 |
| `ReadTaigaIssueTool` | `read_taiga_issue` | `runtime` | PEN-10 | Taiga 이슈 조회(devenv 개발 도구) |
| `RequestStatusTool` | `request_status` | `history` | PEN-20 | 응답을 잃은 요청의 결과 조회(서버 실행 전용) |
| `UndoTool` | `undo` | `history` | PEN-20 | 저장한 실행의 실행 취소·다시 실행(서버 실행 전용) |

## 영역별 member

표기: `()`는 메서드, ✗는 frontend/runtime 구현에서 같은 이름을 찾지 못함(값 객체는 검사하지 않음).

### 실행 컨텍스트·루트 객체 (`runtime`) — PEN-10, 15개

| interface | 성격 | member |
|---|---|---|
| `Penpot` | 조회 | `utils` |
| `Context` | 조회 | `version`, `root` |
| `ContextGeometryUtils` | 조회 | `center()` |
| `ContextTypesUtils` | 조회 | `isBoard()`, `isGroup()`, `isMask()`, `isBool()`, `isRectangle()`, `isPath()`, `isText()`, `isEllipse()`, `isSVG()` |
| `ContextUtils` | 조회 | `geometry`, `types` |

### 실행 플래그 (`flags`) — PEN-10, 3개

| interface | 성격 | member |
|---|---|---|
| `Context` | 조회 | `flags` |
| `Flags` | 조회·편집 | `naturalChildOrdering`, `throwValidationErrors` |

### 플러그인 localStorage·MCP storage (`storage`) — PEN-10, 5개

| interface | 성격 | member |
|---|---|---|
| `Context` | 조회 | `localStorage` |
| `LocalStorage` | 조회 | `getItem()`, `getKeys()` |
| `LocalStorage` | 편집 | `setItem()`, `removeItem()` |

### 현재 사용자·접속 사용자 (`users`) — PEN-10, 7개

| interface | 성격 | member |
|---|---|---|
| `Context` | 조회 | `currentUser`, `activeUsers` |
| `User` | 조회 | `id`, `name`, `avatarUrl`, `color`, `sessionId` |

### 이벤트 구독 (`events`) — PEN-10, 15개

| interface | 성격 | member |
|---|---|---|
| `Penpot` | 이벤트 | `on()`, `off()` |
| `PenpotMgmt` | 이벤트 | `on()`, `off()` |
| `Context` | 이벤트 | `addListener()`, `removeListener()` |
| `EventsMap` | 이벤트 | `workspacechange`, `logout`, `pagechange`, `filechange`, `selectionchange`, `themechange`, `finish`, `shapechange`, `contentsave` |

### 브라우저 UI 전용(선택·뷰포트·테마·플러그인 창) (`ui`) — PEN-10, 21개

| interface | 성격 | member |
|---|---|---|
| `Penpot` | UI 전용 | `ui`, `ui.open()`, `ui.size`, `ui.resize()`, `ui.sendMessage()`, `ui.onMessage()`, `closePlugin()` |
| `ActiveUser` | UI 전용 | `position`, `zoom` |
| `Context` | UI 전용 | `viewport`, `theme`, `selection`, `openViewer()`, `openPage()` |
| `TokenBase` | UI 전용 | `applyToSelected()` |
| `Viewport` | UI 전용 | `center`, `zoom`, `bounds`, `zoomReset()`, `zoomToFitAll()`, `zoomIntoView()` |

### 프로젝트·파일 관리 (`filemgmt`) — PEN-4, 21개

| interface | 성격 | member |
|---|---|---|
| `WorkspaceContext` | 값 객체 | `status`, `fileId`, `fileName`, `teamId` |
| `ProjectSummary` | 값 객체 | `id`, `teamId`, `name`, `isDefault`, `fileCount` |
| `FileSummary` | 값 객체 | `id`, `teamId`, `projectId`, `name`, `modifiedAt` |
| `PenpotMgmt` | 조회 | `workspace` |
| `PenpotMgmt` | 파일관리 | `listProjects()`, `listFiles()`, `createProject()`, `createFile()`, `openFile()` |
| `Context` | 조회 | `management` |

### 파일 메타데이터·버전·검증 (`file`) — PEN-4, 19개

| interface | 성격 | member |
|---|---|---|
| `Context` | 조회 | `currentFile` |
| `File` | 조회 | `id`, `name`, `revn`, `pages`, `findVersions()` |
| `File` | 편집 | `saveVersion()`, `validate()` |
| `FileValidationError` | 값 객체 | `code`, `hint`, `shapeId`, `pageId` |
| `FileVersion` | 조회·편집 | `label` |
| `FileVersion` | 조회 | `createdBy`, `createdAt`, `isAutosave` |
| `FileVersion` | 편집 | `restore()`, `remove()`, `pin()` |

### 페이지 관리 (`page`) — PEN-4, 5개

| interface | 성격 | member |
|---|---|---|
| `Context` | 조회 | `currentPage` |
| `Context` | 편집 | `createPage()` |
| `Page` | 조회 | `id` |
| `Page` | 조회·편집 | `name` |
| `Page` | 편집 | `remove()` |

### 도형 조회 (`query`) — PEN-5, 10개

| interface | 성격 | member |
|---|---|---|
| `Bounds` | 값 객체 | `x`, `y`, `width`, `height` |
| `Page` | 조회 | `root`, `getShapeById()`, `findShapes()` |
| `Point` | 값 객체 | `x`, `y` |
| `ShapeBase` | 조회 | `parent` |

### 기본 도형 속성·생성·삭제 (`shape`) — PEN-5, 89개

| interface | 성격 | member |
|---|---|---|
| `Blur` | 값 객체 | `id`, `value`, `hidden` |
| `Board` | 조회 | `type` |
| `Board` | 조회·편집 | `clipContent`, `showInViewMode`, `fills` |
| `Context` | 편집 | `createRectangle()`, `createBoard()`, `createEllipse()` |
| `Ellipse` | 조회 | `type` |
| `Ellipse` | 조회·편집 | `fills` |
| `Export` | 값 객체 | `type`, `scale`, `suffix`, `skipChildren` |
| `Fill` | 값 객체 | `fillColor`, `fillOpacity`, `fillColorGradient`, `fillColorRefFile`, `fillColorRefId`, `fillImage` |
| `Gradient` | 값 객체 | `type`, `startX`, `startY`, `endX`, `endY`, `width`, `stops` |
| `PluginData` | 조회 | `getPluginData()`, `getPluginDataKeys()`, `getSharedPluginData()`, `getSharedPluginDataKeys()` |
| `PluginData` | 편집 | `setPluginData()`, `setSharedPluginData()` |
| `Rectangle` | 조회 | `type` |
| `Rectangle` | 조회·편집 | `fills` |
| `Shadow` | 값 객체 | `id`, `style`, `offsetX`, `offsetY`, `blur`, `spread`, `hidden`, `color` |
| `ShapeBase` | 조회 | `id`, `width`, `height`, `bounds`, `center` |
| `ShapeBase` | 조회·편집 | `name`, `x`, `y`, `blocked`, `hidden`, `visible`, `proportionLock`, `fixedWhenScrolling`, `borderRadius`, `borderRadiusTopLeft`, `borderRadiusTopRight`, `borderRadiusBottomRight`, `borderRadiusBottomLeft`, `opacity`, `blendMode`, `shadows`, `blur`, `backgroundBlur`, `exports`, `fills`, `strokes` |
| `ShapeBase` | 편집 | `clone()`, `remove()` |
| `Stroke` | 값 객체 | `strokeColor`, `strokeColorRefFile`, `strokeColorRefId`, `strokeOpacity`, `strokeStyle`, `strokeWidth`, `strokeWidthType`, `strokeWidthTop`, `strokeWidthRight`, `strokeWidthBottom`, `strokeWidthLeft`, `strokeAlignment`, `strokeCapStart`, `strokeCapEnd`, `strokeColorGradient`, `strokeImage` |

### 계층·변환·정렬 (`hierarchy`) — PEN-11, 33개

| interface | 성격 | member |
|---|---|---|
| `Board` | 조회·편집 | `children` |
| `Board` | 편집 | `appendChild()`, `insertChild()` |
| `Boolean` | 조회 | `children` |
| `Boolean` | 편집 | `appendChild()`, `insertChild()` |
| `Context` | 편집 | `group()`, `ungroup()`, `alignHorizontal()`, `alignVertical()`, `distributeHorizontal()`, `distributeVertical()` |
| `Group` | 조회 | `type`, `children` |
| `Group` | 편집 | `appendChild()`, `insertChild()` |
| `ShapeBase` | 조회 | `parentIndex` |
| `ShapeBase` | 조회·편집 | `constraintsHorizontal`, `constraintsVertical`, `boardX`, `boardY`, `parentX`, `parentY`, `flipX`, `flipY`, `rotation` |
| `ShapeBase` | 편집 | `setParentIndex()`, `resize()`, `rotate()`, `bringToFront()`, `bringForward()`, `sendToBack()`, `sendBackward()` |

### 패스·Boolean·마스크·flatten (`path`) — PEN-11, 31개

| interface | 성격 | member |
|---|---|---|
| `Boolean` | 조회 | `type`, `content`, `d`, `commands` |
| `Boolean` | 출력 | `toD()` |
| `Boolean` | 조회·편집 | `fills` |
| `Context` | 편집 | `createPath()`, `createBoolean()`, `flatten()` |
| `Group` | 조회 | `isMask()` |
| `Group` | 편집 | `makeMask()`, `removeMask()` |
| `Path` | 조회 | `type` |
| `Path` | 출력 | `toD()` |
| `Path` | 조회·편집 | `content`, `d`, `commands`, `fills`, `command`, `params`, `params.x`, `params.y`, `params.c1x`, `params.c1y`, `params.c2x`, `params.c2y`, `params.rx`, `params.ry`, `params.xAxisRotation`, `params.largeArcFlag`, `params.sweepFlag` |

### 텍스트·폰트·부분 스타일 (`text`) — PEN-12, 56개

| interface | 성격 | member |
|---|---|---|
| `Context` | 조회 | `fonts` |
| `Context` | 편집 | `createText()` |
| `Font` | 조회 | `name`, `fontId`, `fontFamily`, `fontStyle`, `fontVariantId`, `fontWeight`, `variants` |
| `Font` | 편집 | `applyToText()`, `applyToRange()` |
| `FontVariant` | 값 객체 | `name`, `fontVariantId`, `fontWeight`, `fontStyle` |
| `FontsContext` | 조회 | `all`, `findById()`, `findByName()`, `findAllById()`, `findAllByName()` |
| `LibraryTypography` | 편집 | `applyToText()`, `applyToTextRange()` |
| `Text` | 조회 | `type`, `textBounds`, `getRange()` |
| `Text` | 조회·편집 | `characters`, `growType`, `fontId`, `fontFamily`, `fontVariantId`, `fontSize`, `fontWeight`, `fontStyle`, `lineHeight`, `letterSpacing`, `textTransform`, `textDecoration`, `direction`, `align`, `verticalAlign` |
| `TextRange` | 조회 | `shape`, `characters` |
| `TextRange` | 조회·편집 | `fontId`, `fontFamily`, `fontVariantId`, `fontSize`, `fontWeight`, `fontStyle`, `lineHeight`, `letterSpacing`, `textTransform`, `textDecoration`, `direction`, `fills`, `align`, `verticalAlign` |

### Flex·Grid 레이아웃 (`layout`) — PEN-13, 65개

| interface | 성격 | member |
|---|---|---|
| `Board` | 조회 | `grid`, `flex` |
| `Board` | 조회·편집 | `horizontalSizing`, `verticalSizing` |
| `Board` | 편집 | `addFlexLayout()`, `addGridLayout()` |
| `CommonLayout` | 조회·편집 | `alignItems`, `alignContent`, `justifyItems`, `justifyContent`, `rowGap`, `columnGap`, `verticalPadding`, `horizontalPadding`, `topPadding`, `rightPadding`, `bottomPadding`, `leftPadding`, `paddingType`, `horizontalSizing`, `verticalSizing` |
| `CommonLayout` | 편집 | `remove()` |
| `Context` | 편집 | `waitForLayoutUpdate()` |
| `FlexLayout` | 조회·편집 | `dir`, `wrap` |
| `FlexLayout` | 편집 | `appendChild()` |
| `GridLayout` | 조회·편집 | `dir` |
| `GridLayout` | 조회 | `rows`, `columns` |
| `GridLayout` | 편집 | `addRow()`, `addRowAtIndex()`, `addColumn()`, `addColumnAtIndex()`, `removeRow()`, `removeColumn()`, `setColumn()`, `setRow()`, `appendChild()` |
| `LayoutCellProperties` | 값 객체 | `row`, `rowSpan`, `column`, `columnSpan`, `areaName`, `position` |
| `LayoutChildProperties` | 조회·편집 | `absolute`, `zIndex`, `horizontalSizing`, `verticalSizing`, `alignSelf`, `horizontalMargin`, `verticalMargin`, `topMargin`, `rightMargin`, `bottomMargin`, `leftMargin`, `marginType`, `maxWidth`, `maxHeight`, `minWidth`, `minHeight` |
| `ShapeBase` | 조회 | `layoutChild`, `layoutCell` |
| `ShapeBase` | 편집 | `waitForLayoutUpdate()` |
| `Track` | 값 객체 | `type`, `value` |

### 컴포넌트·인스턴스·Variants (`components`) — PEN-14, 40개

| interface | 성격 | member |
|---|---|---|
| `Board` | 조회 | `isVariantContainer()` |
| `VariantContainer` | 조회 | `variants` |
| `Context` | 편집 | `createVariantFromComponents()` |
| `ContextTypesUtils` | 조회 | `isVariantContainer()`, `isVariantComponent()` |
| `Library` | 조회 | `components` |
| `Library` | 편집 | `createComponent()` |
| `LibraryComponent` | 편집 | `instance()`, `transformInVariant()` |
| `LibraryComponent` | 조회 | `mainInstance()`, `isVariant()` |
| `LibraryVariantComponent` | 조회 | `variants`, `variantProps` |
| `LibraryVariantComponent` | 조회·편집 | `variantError` |
| `LibraryVariantComponent` | 편집 | `addVariant()`, `setVariantProperty()` |
| `ShapeBase` | 조회 | `isComponentInstance()`, `isComponentMainInstance()`, `isComponentCopyInstance()`, `isComponentRoot()`, `isComponentHead()`, `componentRefShape()`, `componentRoot()`, `componentHead()`, `component()`, `isVariantHead()` |
| `ShapeBase` | 편집 | `detach()`, `swapComponent()`, `resetOverrides()`, `switchVariant()`, `combineAsVariants()` |
| `Variants` | 조회 | `id`, `libraryId`, `properties`, `currentValues()`, `variantComponents()` |
| `Variants` | 편집 | `removeProperty()`, `renameProperty()`, `addVariant()`, `addProperty()` |

### 라이브러리 자산·연결 (`library`) — PEN-15, 54개

| interface | 성격 | member |
|---|---|---|
| `Color` | 값 객체 | `id`, `fileId`, `name`, `path`, `color`, `opacity`, `refId`, `refFile`, `gradient`, `image` |
| `ColorShapeInfo` | 값 객체 | `shapesInfo` |
| `ColorShapeInfoEntry` | 값 객체 | `property`, `index`, `shapeId` |
| `Context` | 조회 | `library` |
| `Context` | 편집 | `shapesColors()`, `replaceColor()` |
| `Library` | 조회 | `id`, `name`, `colors`, `typographies` |
| `Library` | 편집 | `createColor()`, `createTypography()` |
| `LibraryColor` | 조회·편집 | `color`, `opacity`, `gradient`, `image` |
| `LibraryColor` | 조회 | `asFill()`, `asStroke()` |
| `LibraryContext` | 조회 | `local`, `connected`, `availableLibraries()` |
| `LibraryContext` | 편집 | `connectLibrary()` |
| `LibraryElement` | 조회 | `id`, `libraryId` |
| `LibraryElement` | 조회·편집 | `name`, `path` |
| `LibrarySummary` | 값 객체 | `id`, `name`, `numColors`, `numComponents`, `numTypographies` |
| `LibraryTypography` | 조회·편집 | `fontId`, `fontFamily`, `fontVariantId`, `fontSize`, `fontWeight`, `fontStyle`, `lineHeight`, `letterSpacing`, `textTransform` |
| `LibraryTypography` | 편집 | `setFont()` |
| `Text` | 편집 | `applyTypography()` |
| `TextRange` | 편집 | `applyTypography()` |

### 디자인 토큰 (`tokens`) — PEN-15, 115개

| interface | 성격 | member |
|---|---|---|
| `Library` | 조회 | `tokens` |
| `ShapeBase` | 조회 | `tokens` |
| `ShapeBase` | 편집 | `applyToken()` |
| `TokenBase` | 조회 | `id`, `resolvedValueString` |
| `TokenBase` | 조회·편집 | `name`, `description` |
| `TokenBase` | 편집 | `duplicate()`, `remove()`, `applyToShapes()` |
| `TokenBorderRadius` | 조회 | `type`, `resolvedValue` |
| `TokenBorderRadius` | 조회·편집 | `value` |
| `TokenShadowValue` | 값 객체 | `color`, `inset`, `offsetX`, `offsetY`, `spread`, `blur` |
| `TokenShadowValueString` | 값 객체 | `color`, `inset`, `offsetX`, `offsetY`, `spread`, `blur` |
| `TokenShadow` | 조회 | `type`, `resolvedValue` |
| `TokenShadow` | 조회·편집 | `value` |
| `TokenColor` | 조회 | `type`, `resolvedValue` |
| `TokenColor` | 조회·편집 | `value` |
| `TokenDimension` | 조회 | `type`, `resolvedValue` |
| `TokenDimension` | 조회·편집 | `value` |
| `TokenFontFamilies` | 조회 | `type`, `resolvedValue` |
| `TokenFontFamilies` | 조회·편집 | `value` |
| `TokenFontSizes` | 조회 | `type`, `resolvedValue` |
| `TokenFontSizes` | 조회·편집 | `value` |
| `TokenFontWeights` | 조회 | `type`, `resolvedValue` |
| `TokenFontWeights` | 조회·편집 | `value` |
| `TokenLetterSpacing` | 조회 | `type`, `resolvedValue` |
| `TokenLetterSpacing` | 조회·편집 | `value` |
| `TokenNumber` | 조회 | `type`, `resolvedValue` |
| `TokenNumber` | 조회·편집 | `value` |
| `TokenOpacity` | 조회 | `type`, `resolvedValue` |
| `TokenOpacity` | 조회·편집 | `value` |
| `TokenRotation` | 조회 | `type`, `resolvedValue` |
| `TokenRotation` | 조회·편집 | `value` |
| `TokenSizing` | 조회 | `type`, `resolvedValue` |
| `TokenSizing` | 조회·편집 | `value` |
| `TokenSpacing` | 조회 | `type`, `resolvedValue` |
| `TokenSpacing` | 조회·편집 | `value` |
| `TokenBorderWidth` | 조회 | `type`, `resolvedValue` |
| `TokenBorderWidth` | 조회·편집 | `value` |
| `TokenTextCase` | 조회 | `type`, `resolvedValue` |
| `TokenTextCase` | 조회·편집 | `value` |
| `TokenTextDecoration` | 조회 | `type`, `resolvedValue` |
| `TokenTextDecoration` | 조회·편집 | `value` |
| `TokenTypographyValue` | 값 객체 | `letterSpacing`, `fontFamilies`, `fontSizes`, `fontWeights`, `lineHeight`, `textCase`, `textDecoration` |
| `TokenTypographyValueString` | 값 객체 | `letterSpacing`, `fontFamilies`, `fontSizes`, `fontWeight`, `lineHeight`, `textCase`, `textDecoration` |
| `TokenTypography` | 조회 | `type`, `resolvedValue` |
| `TokenTypography` | 조회·편집 | `value` |
| `TokenCatalog` | 조회 | `isEditableTokens`, `themes`, `sets`, `getThemeById()`, `getSetById()` |
| `TokenCatalog` | 편집 | `addTheme()`, `addSet()` |
| `TokenSet` | 조회 | `id`, `tokens`, `tokensByType`, `getTokenById()` |
| `TokenSet` | 조회·편집 | `name`, `active` |
| `TokenSet` | 편집 | `toggleActive()`, `addToken()`, `duplicate()`, `remove()` |
| `TokenTheme` | 조회 | `id`, `externalId`, `activeSets` |
| `TokenTheme` | 조회·편집 | `group`, `name`, `active` |
| `TokenTheme` | 편집 | `toggleActive()`, `addSet()`, `removeSet()`, `duplicate()`, `remove()` |

### 이미지·SVG (`media`) — PEN-16, 14개

| interface | 성격 | member |
|---|---|---|
| `Context` | 편집 | `uploadMediaUrl()`, `uploadMediaData()`, `createShapeFromSvg()`, `createShapeFromSvgWithImages()` |
| `Image` | 조회 | `type` |
| `Image` | 조회·편집 | `fills` |
| `ImageData` | 값 객체 | `name`, `width`, `height`, `mtype`, `id`, `keepAspectRatio`, `data()` |
| `SvgRaw` | 조회 | `type` |

### Flow·상호작용·가이드 (`prototype`) — PEN-17, 75개

| interface | 성격 | member |
|---|---|---|
| `Board` | 조회·편집 | `guides` |
| `Board` | 조회 | `rulerGuides` |
| `Board` | 편집 | `addRulerGuide()`, `removeRulerGuide()` |
| `CloseOverlay` | 값 객체 | `type`, `destination`, `animation` |
| `Dissolve` | 값 객체 | `type`, `duration`, `easing` |
| `Flow` | 조회 | `page` |
| `Flow` | 조회·편집 | `name`, `startingBoard` |
| `Flow` | 편집 | `remove()` |
| `GuideColumn` | 값 객체 | `type`, `display`, `params` |
| `GuideColumnParams` | 값 객체 | `color`, `type`, `size`, `margin`, `itemLength`, `gutter` |
| `GuideRow` | 값 객체 | `type`, `display`, `params` |
| `GuideSquare` | 값 객체 | `type`, `display`, `params` |
| `GuideSquareParams` | 값 객체 | `color`, `size` |
| `Interaction` | 조회 | `shape` |
| `Interaction` | 조회·편집 | `trigger`, `delay`, `action` |
| `Interaction` | 편집 | `remove()` |
| `NavigateTo` | 값 객체 | `type`, `destination`, `preserveScrollPosition`, `animation` |
| `OpenOverlay` | 값 객체 | `type` |
| `OpenUrl` | 값 객체 | `type`, `url` |
| `OverlayAction` | 값 객체 | `destination`, `relativeTo`, `position`, `manualPositionLocation`, `closeWhenClickOutside`, `addBackgroundOverlay`, `animation` |
| `Page` | 조회 | `rulerGuides`, `flows` |
| `Page` | 편집 | `createFlow()`, `removeFlow()`, `addRulerGuide()`, `removeRulerGuide()` |
| `PreviousScreen` | 값 객체 | `type` |
| `Push` | 값 객체 | `type`, `direction`, `duration`, `easing` |
| `RulerGuide` | 조회 | `orientation` |
| `RulerGuide` | 조회·편집 | `position`, `board` |
| `RulerGuide` | 편집 | `remove()` |
| `ShapeBase` | 조회 | `interactions` |
| `ShapeBase` | 편집 | `addInteraction()`, `removeInteraction()` |
| `Slide` | 값 객체 | `type`, `way`, `direction`, `duration`, `offsetEffect`, `easing` |
| `ToggleOverlay` | 값 객체 | `type` |

### 댓글 (`comments`) — PEN-18, 15개

| interface | 성격 | member |
|---|---|---|
| `Comment` | 조회 | `user`, `date` |
| `Comment` | 조회·편집 | `content` |
| `Comment` | 편집 | `remove()` |
| `CommentThread` | 조회 | `seqNumber`, `board`, `owner`, `findComments()` |
| `CommentThread` | 조회·편집 | `position`, `resolved` |
| `CommentThread` | 편집 | `reply()`, `remove()` |
| `Page` | 편집 | `addCommentThread()`, `removeCommentThread()` |
| `Page` | 조회 | `findCommentThreads()` |

### 내보내기·코드 생성 (`output`) — PEN-19, 5개

| interface | 성격 | member |
|---|---|---|
| `Context` | 출력 | `generateMarkup()`, `generateStyle()`, `generateFontFaces()` |
| `File` | 출력 | `export()` |
| `ShapeBase` | 출력 | `export()` |

### 작업 단위·실행 취소 (`history`) — PEN-20, 3개

| interface | 성격 | member |
|---|---|---|
| `Context` | 조회 | `history` |
| `HistoryContext` | 편집 | `undoBlockBegin()`, `undoBlockFinish()` |

## 구현 확인 필요

없음.
