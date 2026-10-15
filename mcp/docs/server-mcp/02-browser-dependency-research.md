# 전체 편집·내보내기의 브라우저 의존성과 서버 실행 경로 (PEN-7)

기준 코드: `develop` `0c0336da4`. 조사일: 2026-10-14. 실험 환경: `verification-env.md`.

## 요약

1. **저장은 이미 브라우저가 필요 없다.** backend `update-file`은 공용 cljc 코드(`app.common.files.changes`)로 변경을 적용하고 검증한다. 공용 cljc로 사각형 변경을 JVM에서 만들어 access token으로 저장했고, 열린 두 브라우저에 0.73초 안에 반영됐다(E1).
2. **어려운 부분은 '파생 값' 계산이다.** backend는 변경을 적용만 하고 계산하지 않는다. 레이아웃 재배치 결과, 텍스트 크기·`position-data`, boolean 결과 path, 컴포넌트 동기화 변경, 토큰 해석 값은 지금 모두 브라우저(frontend)가 계산해 변경으로 보낸다. 서버 MCP는 이 계산을 서버에서 해야 한다.
3. **계산 엔진이 두 개다.** 이 버전은 `render-wasm/v1`을 기본으로 켠다(`common/src/app/common/flags.cljc:228`). 그래서 브라우저는 레이아웃·텍스트·boolean을 Rust render-wasm으로 계산한다. wasm이 꺼진 브라우저는 cljc 코드와 DOM 측정을 쓴다. 서버가 맞춰야 할 기준은 사용자가 실제로 쓰는 엔진이다.
4. **브라우저 없는 render-wasm 실행 경로가 이미 있다.**
   - exporter는 render-wasm을 Node worker에서 GPU 없이 띄우는 headless 경로(`is-wasm`)를 갖고 있다. 같은 도형을 Chromium export와 픽셀 차이 0으로 출력했고, 52배 빨랐다(E3).
   - render-wasm crate는 Linux native로도 컴파일되며, 단위 테스트 315개가 통과했다(E2).
   - 공용 직렬화 계층 `common/src/app/common/render_wasm/`은 DOM 없이 Node에서 돌도록 규칙이 정해져 있다.
5. **제안 경로**: Node 실행기 + headless render-wasm(경로 A). 브라우저와 같은 계산 엔진을 쓰므로 동등성을 맞추기 쉽다. JVM만 쓰는 경로(B)는 텍스트 측정을 새로 만들어야 한다. 서버 headless Chromium(C)은 '브라우저 없이'의 정의에 걸린다. A의 핵심인 계산을 Node에서 브라우저와 같은 값으로 얻는 것은 **E4에서 실증했다**(2026-10-15). frontend 편집 계층을 그대로 Node에서 돌리고 render-wasm만 headless로 띄운 실행기가 브라우저(wasm 모드)와 같은 값을 저장했다.

## 1. 현재 편집 경로

```
AI 클라이언트 ─MCP→ mcp server ─WebSocket→ 사용자 브라우저의 MCP 플러그인 (SES sandbox)
  → execute_code: penpot.* (frontend/src/app/plugins/*.cljs)
  → frontend 상태 이벤트 (app.main.data.workspace.*)
      · 파생 값 계산: render-wasm(Rust/WASM) 또는 cljc + DOM
      · 변경 생성: app.common.files.changes-builder (cljc)
  → RPC update-file (backend, JVM)
      · 권한 검사, 파일 lock, revn/vern 검사
      · app.common.files.changes/process-changes (cljc) 적용, 파일 검증 (cljc)
      · file_change 기록, msgbus → WebSocket :file-change
  → 다른 브라우저: 변경 적용, 렌더링
```

- 근거: 플러그인 실행 `mcp/packages/plugin/src/task-handlers/ExecuteCodeTaskHandler.ts`, 도형 생성 `frontend/src/app/plugins/api.cljs:66`(`cts/setup-shape` + `cb/add-object`), 저장 `backend/src/app/rpc/commands/files_update.clj:121-486`, 알림 `backend/src/app/http/websocket.clj:153-215`.
- wasm 분기: `frontend/src/app/main/data/workspace/transforms.cljs:380,430,562,582,597,660,701,793,950`, `texts.cljs:313,590,666,1122,1320`, `modifiers.cljs:358`.

## 2. 기능별 의존성과 서버 경로

분류:
- **cljc**: JVM과 JS 양쪽에서 돈다.
- **cljs**: JS 전용이지만 DOM이 없어도 된다.
- **npm**: JS 라이브러리다.
- **DOM**: 브라우저 API가 필요하다.
- **wasm**: render-wasm 모듈이 필요하다.
- **backend**: 이미 RPC로 있다.

| 기능 (티켓) | 현재 계산·실행 위치 | 런타임 의존성 | 서버 경로 대안 | 동등성 기준 | 상태 |
|---|---|---|---|---|---|
| 기본 도형 생성·속성 (PEN-3/5) | `app.common.types.shape/setup-shape`, `changes-builder` (`plugins/api.cljs:66`, `plugins/shape.cljs`) | cljc | JVM 또는 Node에서 그대로 재사용 | 정규화한 shape map이 같다 (id·시각 제외) | **실증 E1** |
| 저장·검증·알림 (PEN-3/6) | backend `update-file` | backend | 그대로 사용 | revn 증가, 재조회 일치, 관찰 브라우저 반영 | **실증 E1** |
| 이동·크기·회전·constraints (PEN-11) | modifiers. wasm 모드는 `_propagate_modifiers` (`frontend/src/app/render_wasm/api.cljs:2162`), 아니면 `app.common.geom.modifiers` (cljc) | wasm 또는 cljc | A: Node + headless render-wasm, B: cljc | selrect·points·transform 오차 0.01px 이하 | 미확인 E4 |
| 계층·그룹·정렬·z-order (PEN-11) | `dwg/*`, `changes-builder` | cljc (그룹 bounds 재계산은 modifiers) | 재사용 | parent·shapes 순서 동일 | 읽기로 확인 |
| Flex·Grid reflow (PEN-13) | wasm 모드 `_propagate_modifiers` (render-wasm `src/shapes/modifiers`, `layouts.rs`), 아니면 `app.common.geom.shapes.flex_layout`/`grid_layout` (cljc) | wasm 또는 cljc. 자식이 텍스트면 텍스트 측정이 필요하다 | A 권장. B는 텍스트 측정 문제가 남는다 | 모든 자식 selrect 오차 0.5px 이하 | 미확인 E4 |
| 텍스트 크기·`position-data` (PEN-12) | wasm 모드 `get-wasm-text-new-size` → `_get_text_dimensions`, `_calculate_position_data` (`api.cljs:1408,2832`, `data/workspace/wasm_text.cljs:32`). 아니면 DOM `document.createRange().getClientRects()` (`frontend/src/app/util/text_position_data.js:18`) | wasm(Skia paragraph + 폰트) 또는 DOM | A: headless render-wasm + 폰트 공급(exporter의 `provision-fonts!`, `update-text-layout!` 재사용), B: JVM에서 새 텍스트 엔진(위험 큼), C: headless Chromium | 같은 폰트로 width/height 오차 0.5px 이하, 줄바꿈 위치 동일 | 렌더 결과만 실증 E3b, 크기 API는 미확인 E4 |
| 폰트 목록·로딩 (PEN-12) | `app.common.fonts`(gfonts 목록 cljc), 사용자 폰트 RPC `get-font-variants` | cljc + backend | exporter `fetch-font-variants`·TTF 공급 재사용 | 같은 font-id·variant로 같은 측정값 | 읽기로 확인 |
| 패스 편집 (PEN-11) | `app.common.types.path.*` (cljc) | cljc | 재사용 | content 동일 | 읽기로 확인 |
| Boolean (PEN-11) | wasm `_calculate_bool` (`api.cljs:2772`), 아니면 `app.common.types.path.bool` (cljc) | wasm 또는 cljc | A: headless wasm, B: cljc(엔진이 달라 결과가 다를 수 있음) | path 점 오차 0.01px, 렌더 픽셀 차이 0.1% 이하 | 미확인 E4 |
| 컴포넌트·Variants·동기화 (PEN-14) | `app.common.logic.libraries` (`generate-sync-file` 등, cljc), 실행 시점은 frontend가 정한다 (`data/workspace/libraries.cljs`) | cljc. 동기화 후 레이아웃·텍스트 재계산이 필요하다 | 재사용 + A의 재계산 | 동기화 후 shape map 동일 | 읽기로 확인 |
| 라이브러리 자산·연결 (PEN-15) | 색상·타이포 변경은 cljc changes, 연결은 backend RPC | cljc + backend | 재사용 | 자산 map 동일 | 읽기로 확인 |
| 디자인 토큰 해석 (PEN-15) | `app.main.data.style-dictionary` → npm `style-dictionary`, `@tokens-studio/sd-transforms` (`frontend/src/app/main/data/style_dictionary.cljs:9-10`). 토큰 데이터 모델은 cljc (`types/tokens_lib.cljc`) | npm (Node 가능, JVM 불가) | A: Node에서 같은 라이브러리 실행. B: JVM 재구현(위험) | resolvedValue 문자열 동일 | 미확인 E5 |
| 이미지 업로드·fill (PEN-16) | backend RPC `upload-file-media-object`, `create-file-media-object-from-url` (`backend/src/app/rpc/commands/media.clj:56,230`) | backend | 그대로 사용 | 저장된 media 객체·fill 동일 | 읽기로 확인 |
| SVG 가져오기 (PEN-16) | `tubax/xml->clj` 파싱 (`frontend/src/app/main/data/workspace/media.cljs:54`), 변환은 `app.common.svg`, `svg_upload.cljs`. svgo는 frontend worker | cljs + cljc. svgo는 npm | A: Node에서 같은 코드. B: JVM XML 파서로 이식 | 생성된 shape 트리 동일 | 미확인 E6 |
| Flow·상호작용·가이드 (PEN-17) | shape `:interactions`, page `:flows`/`:guides` changes (cljc) | cljc | 재사용 | changes·shape map 동일 | 읽기로 확인 |
| 댓글 (PEN-18) | backend RPC `create-comment-thread` 등 15개 (`backend/src/app/rpc/commands/comments.clj:232-810`) | backend | 그대로 사용 | RPC 결과 동일, 열린 브라우저 알림 | 읽기로 확인 |
| 파일 버전 (PEN-4/20) | backend RPC `create/restore/lock-file-snapshot` (`files_snapshot.clj`) | backend | 그대로 사용 | 버전 목록 동일 | 읽기로 확인 |
| 실행 취소 (PEN-20) | frontend undo stack (`data/workspace/undo.cljs`) + `changes-builder`의 undo-changes | cljs 상태 + cljc | 서버 세션별 undo stack, undo-changes를 cljc로 생성 | undo 후 shape map이 작업 전과 동일 | 읽기로 확인 |
| 래스터·PDF·SVG export (PEN-19) | exporter: Chromium(`renderer/bitmap.cljs` 등) 또는 headless render-wasm(`renderer/wasm.cljs`, `app/wasm.cljs`) | Chromium 또는 wasm(Node) | headless wasm 경로 사용 | 픽셀 차이·크기 | **실증 E3/E3b** (인증 문제 있음) |
| 코드 생성 (PEN-19) | `app.util.code-gen.*`, `react-dom/server`의 `renderToStaticMarkup` + frontend UI 컴포넌트 (`frontend/src/app/util/code_gen/markup_svg.cljs:9`) | cljs + npm. UI 컴포넌트가 frontend 네임스페이스를 끌어온다 | A: 필요한 컴포넌트를 DOM 없이 Node에서 렌더(분리 작업 필요) | 생성 문자열 동일 | 미확인 E7 |
| 프로젝트·파일 관리 (PEN-4) | backend RPC | backend | 그대로 사용 | 대시보드 재조회 동일 | 읽기로 확인 |
| MCP 실행기 (PEN-10) | 브라우저 SES compartment + `new Function` | DOM 아님, 브라우저 플러그인 런타임 | Node 격리 프로세스(예: worker + 별도 V8 isolate)에서 `penpot.*` 서버 구현 | 같은 코드의 결과 JSON 동일 | 설계만 |

## 3. 서버 실행 경로 대안

| | A. Node 실행기 + headless render-wasm | B. backend JVM(cljc)만 | C. 서버 headless Chromium에서 실제 frontend 실행 |
|---|---|---|---|
| 내용 | `penpot.*`를 Node(cljs 빌드)에서 서버용으로 구현한다. 파생 값은 exporter가 쓰는 render-wasm headless 모듈로 계산한다 | backend에 서버 편집 API를 두고 cljc 코드만 쓴다 | exporter처럼 Playwright로 서버에서 frontend를 열고 플러그인을 붙인다 |
| 재사용 | cljc 전부, `common/render_wasm` 직렬화, exporter의 모듈 부팅·폰트 공급, npm 토큰·SVG 라이브러리 | cljc 전부 | 현재 MCP 전체 |
| 새로 만드는 것 | frontend `app.render-wasm.api`의 계산 래퍼를 host 무관 계층으로 옮기는 일, `penpot.*` 서버 구현(frontend 상태 이벤트 대신 서버 상태) | 텍스트 측정 엔진, 토큰 해석 이식, SVG 파서 이식, `penpot.*` 실행 환경. JS 코드 호환(D1-A)은 JVM에서 사용자 JS를 돌려야 해 PEN-8의 '백엔드 임의 코드 실행 금지'와 충돌한다 | 세션별 브라우저 관리, 인증 위임 |
| 브라우저와의 동등성 | wasm 모드와 같은 엔진이라 높다 | 레이아웃·boolean은 비 wasm 모드와 같다. 텍스트는 새 엔진이라 낮다 | 같다 |
| 자원 | 세션당 wasm 힙(초기 256 MB, `render-wasm/_build_env`) | 가장 적다 | 세션당 Chromium(수백 MB), 기동 수 초 (E3 브라우저 export 2.6–2.75초) |
| 위험 | 계산 API의 Node 동작 미실증(E4). frontend 이벤트 로직을 서버로 옮기는 양이 크다 | 텍스트·토큰 동등성. 사용자 JS 실행 위치 | '브라우저 없이' 요구와 충돌할 수 있다. 확장성 |

**[기술 판단] A를 기본 경로로 제안한다.** C는 '브라우저 없이'의 정의에 달려 있어 사용자 결정이 필요하다(`03-runtime-contract.md` D10). B는 A의 일부로 쓴다. 저장·권한·검증은 backend를 그대로 쓴다.

## 4. 실험

모든 실험은 `verification-env.md`의 스택에서 다시 실행할 수 있다. 결과물은 `.mcp-verify/`에 남는다.

### E1 브라우저 없는 저장과 실시간 반영 — `experiments/e1_server_write.py`

```sh
python3 -I mcp/docs/server-mcp/experiments/e1_server_write.py --file scratch
```

순서:
1. backend JVM의 socket REPL(6062)에서 `cts/setup-shape` + `pcb/add-object`로 사각형 변경을 만들고 transit으로 encode한다.
2. editor의 API token으로 `update-file`을 호출한다.
3. 다시 조회해 확인한다.

| 측정 | 결과 |
|---|---|
| JVM 변경 생성 | 0.06초 |
| `update-file` | 200, 0.023–0.051초, revn +1, selrect (x,y,w,h)가 입력과 같음 |
| 관찰 브라우저 반영 | owner(`localhost`)·editor(`127.0.0.1`) 두 탭의 레이어 목록에 스크립트 시작 후 0.73초 이내에 나타남. 새로고침 없음 |
| 브라우저 0개 | 저장 성공(200). 같은 조건에서 현재 MCP `execute_code`는 `No Penpot sessions are connected` |
| viewer / outsider token | 404 `object-not-found` / 404 `object-not-found` |
| 오래된 revn (저장값−1) | 200. 최신 상태 위에 적용 |
| 저장값보다 큰 revn | 400 `revn-conflict` |
| 같은 요청 재전송 | 200. 도형은 같은 id로 덮어써져 중복 없음. revn은 증가 |

처음 시도한 방식은 실패했다. transit 문자열 조각을 이어 붙이면 key cache 참조가 깨져 backend가 matrix를 읽다가 NPE를 낸다. 요청 전체를 한 번에 encode해야 한다.

### E2 render-wasm native 빌드 — `render-wasm/test`

```sh
scripts/mcp-verify-env shell 'cd ~/penpot/render-wasm && CARGO_TARGET_DIR=target/native-test ./test'
```

- `aarch64-unknown-linux-gnu`로 22초 만에 컴파일됐다. Skia는 `penpot/skia-binaries` linux 바이너리를 쓴다.
- 테스트 315개가 통과했다. 영역별로 `render::svg` 103, `shapes::text` 41, `wasm::text` 10, `shapes::modifiers` 12, `math::bools` 6 등이다.
- 의미: Rust 계산 코드는 Emscripten 없이도 빌드된다. 다만 이것은 테스트용 빌드이며, 서버에서 쓸 native 렌더러나 계산 서비스는 아직 없다.

### E3 headless wasm export와 Chromium export — `experiments/e3_headless_export.py`

```sh
python3 -I mcp/docs/server-mcp/experiments/e3_headless_export.py --file scratch --shape-name server-rect
```

| 대상 | headless wasm (`is-wasm` true) | Chromium (`is-wasm` false) | 비교 |
|---|---|---|---|
| 사각형 200×120 | 0.053초, 200×120 | 2.751초, 200×120 | 픽셀 차이 0 (채널 차 >2 기준) |
| 텍스트 "Server MCP 텍스트 측정 Hello 123", Source Sans Pro 32 (E3b) | 0.693초, **445×43** | 2.643초, **436×39** | 글자 모양은 같아 보임. 잘린 영역이 다름: wasm은 글자 외곽, Chromium은 도형 크기 |
| access token만 사용 | 400 (세션 쿠키가 없어 render params 검증 실패) | — | exporter는 로그인 세션만 받는다 |

exporter 로그에서 `hint="render", backend="wasm"`을 확인했다. 브라우저 없이 Node worker에서 렌더했다는 뜻이다.

### E4 headless 계산과 브라우저(wasm 모드) 계산 — `experiments/e4_headless_compute.py`

```sh
# 컨테이너 안에서 실행기 빌드: cd frontend && clojure -M:dev:shadow-cljs compile executor
python3 -I mcp/docs/server-mcp/experiments/e4_headless_compute.py --space <ego-browser task space>
```

방법 (2026-10-15):
- 실행기는 frontend의 편집 계층(store, workspace 이벤트, `app.plugins.api`)을 그대로 Node에서 돌린다. render-wasm만 `_init_headless`로 띄운다. 빌드는 frontend `shadow-cljs.edn`의 `:executor`, 코드는 `frontend/src/app/executor/`.
- 같은 Plugin API 코드(`e4_scenario.js`)를 새 파일 두 개에 각각 실행한다. 하나는 editor 브라우저 탭(renderer wasm), 하나는 headless 실행기다. 두 파일을 backend에서 다시 읽어 도형 이름으로 맞춰 비교한다(`e4_compare.py`, 기준은 `03` §6).
- `e4b_scenario.js`는 저장된 도형을 다시 연 파일에서 고친다. 엔진이 backend에서 읽은 도형으로 계산하는 경로를 시험한다.

| 라운드 | 내용 | 결과 |
|---|---|---|
| 1 | wrap Flex(고정·fill·텍스트 자식) + 컨테이너 축소, auto-width 한글 혼합 텍스트, auto-height 문단, Boolean 4종 | 22개 도형 모두 같음. geometry·position-data·bool path 최대 차이 0.0 |
| 2 (다시 열기) | Flex 방향·간격·크기 변경, 텍스트 내용·크기 변경, Boolean 피연산자 이동 | 22개 도형 모두 같음. 최대 차이 0.0 |

- 실행 시간: 브라우저 8.2초 / 실행기 6.7초(1라운드), 3.1초 / 1.6초(2라운드). 둘 다 대기 5초와 저장 대기를 포함한다.
- 텍스트 줄바꿈 조각도 같다. 예: `The quick brown ` / `fox jumps over the ` / `lazy dog again and ` / `again`.

headless로 돌리려고 고친 곳:
- render-wasm: `init_headless`가 텍스트 편집·UI 상태도 만든다(GPU 불필요). 렌더 상태가 없을 때 `clean_modifiers`, `set_modifiers`, `set_modifiers_start/end`, `get_shape_extrect`, 타일 재구성이 타일 캐시 작업을 건너뛴다. 브라우저는 항상 렌더 상태가 있으므로 동작이 같다.
- common/frontend: `app.common.render-wasm.wasm/headless?`. 켜져 있으면 "타일 렌더 완료"를 기다리는 콜백을 바로 실행한다.

함께 발견한 사실:
- **[사실]** 브라우저의 기본 renderer는 wasm이 아니다. `render-switch` flag가 켜져 있으면 프로필 설정 `:renderer`를 따르고 기본값은 `:svg`(DOM 측정)다(`frontend/src/app/main/features.cljs:35`). 시험 계정 owner·editor는 설정에서 wasm으로 바꿨다. 운영에서 사용자 대부분이 어느 renderer를 쓰는지는 E9에서 확인한다.
- **[사실]** wasm 모드에서 auto-height 텍스트의 크기를 바꾸면(`resize`) `:text-bridge` 대기 표시가 풀리지 않아 `waitForLayoutUpdate`가 시간 초과된다. 브라우저도 같다(내부 작업 번호까지 같음). 이때 높이도 다시 계산되지 않는다: 4줄인데 20px로 남는다. 서버 계약(§3 '실행이 끝날 때는 파생 값 계산을 끝낸다')을 지키려면 PEN-12에서 고쳐야 한다. → **PEN-12에서 고쳤다.** 원인: `resize(w, h)`가 높이를 정하면 grow type이 `fixed`로 바뀌어(UI와 같은 `next-grow-type` 규칙) 높이는 맞게 그대로 남는데, 대기 표시는 바뀌기 전 grow type으로 판단해 걸고 있었다(`05-results.md` PEN-12).

## 5. 미확인 항목과 다음 실험

| ID | 질문 | 왜 중요한가 | 방법 | 담당 |
|---|---|---|---|---|
| E4 | Node headless render-wasm으로 브라우저(wasm 모드)와 같은 계산 값을 얻는가 | 경로 A의 핵심 | §4 E4 | **완료 2026-10-15: 같음** |
| E5 | `style-dictionary` 토큰 해석이 frontend 밖 Node에서 같은 값을 내는가 | 토큰 적용 값 | `resolve-tokens`를 Node 빌드에서 실행해 브라우저 resolvedValue와 비교 | PEN-15 |
| E6 | SVG 가져오기(`tubax`, svgo)가 Node에서 같은 shape 트리를 만드는가 | SVG import | 같은 SVG를 두 경로로 가져와 비교 | PEN-16 |
| E7 | 코드 생성 컴포넌트를 DOM 없이 렌더할 수 있는가 | generateMarkup/Style | `code_gen` 의존 네임스페이스를 Node 빌드에 넣어 본다 | PEN-19 |
| E8 | WebSocket 알림 버퍼(64)가 넘칠 때 브라우저가 변경을 놓치는가, 놓치면 회복하는가 | 실시간 일관성 | 저장 200회를 연속으로 보내며 관찰 브라우저의 revn과 도형 수를 확인 | PEN-6 |
| E9 | 운영(design.hktlabs.com)의 버전과 `render-wasm` flag | 동등성 기준 엔진 | 운영 frontend `config.js`·버전 조회(읽기만) | PEN-21 전, 사용자 확인 |
| E10 | exporter가 access token으로 동작하도록 바꾸는 방법 | 서버 export 인증 | exporter `auth.cljs`가 `Authorization: Token`을 backend로 넘기게 하고 시험 | PEN-19 |
| E11 | ws1+ 기본 devenv에서도 exporter가 공개 포트 때문에 실패하는가 | 개발 환경 버그 여부 | `run-devenv --ws 1`에서 export | 선택 |

## 6. 원문 근거 목록

- 기능 목록과 member 위치: `feature-inventory.md`
- 공용 render-wasm 직렬화 규칙: `common/src/app/common/render_wasm/README.md` ("Nothing here may depend on a browser … It also has to run under plain Node")
- exporter headless 드라이버: `exporter/src/app/wasm.cljs:1-12`(`init_headless`, "GPU-free counterpart"), `exporter/src/app/renderer.cljs:35-56`(`headless?` 분기)
- render-wasm export 함수 목록: `render-wasm/src/**/*.rs`의 `#[no_mangle]` 함수 159개. 그중 계산용은 `propagate_modifiers`, `get_text_dimensions`, `calculate_position_data`, `calculate_bool`, `get_selection_rect`, `convert_stroke_to_path`, `current_to_path`
- render-wasm native 테스트 스크립트: `render-wasm/test` (`CARGO_BUILD_TARGET=<arch>-unknown-linux-gnu`)
