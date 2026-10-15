# 전체 기능·MCP·인증·동시 편집 계약 (PEN-1)

상태: **기능 목록·담당 티켓·검증 시나리오는 확정했다. 사용자 결정 D1–D9는 2026-10-15에 사용자가 확정했다.** D1–D7·D9는 제안대로, D8은 다시 논의한 뒤 'AI 따라가기'를 더해 정했다.

표기:
- **[사실]**: 코드 또는 실측으로 확인한 내용이다. 근거 경로나 실험 번호를 붙인다.
- **[기술 결정]**: 구현자가 따를 기술 선택이다. 이 문서에서 정한다.
- **[사용자 결정]**: 사용자가 정해야 한다. 선택지와 제안만 적는다.
- **[미확인]**: 아직 확인하지 않았다. 확인할 티켓을 적는다.

## 1. 범위: 전체 기능 목록

현재 MCP가 할 수 있는 일은 `execute_code`로 실행하는 Plugin API 전체와 MCP 도구 10개다. 서버 MCP는 이 전부를 브라우저 없이 제공해야 한다. 고급 기능을 선택 사항으로 빼지 않는다. 기능을 지우거나 미루려면 사용자의 명시적 결정이 필요하다.

- 전체 member 목록과 담당 티켓: [`feature-inventory.md`](feature-inventory.md). `tools/gen_inventory.py`가 `plugins/libs/plugin-types/index.d.ts`와 `mcp/packages/server/src/tools/`에서 생성한다.
- **[사실]** interface/object type 108개, member 716개, MCP 도구 10개를 모두 23개 기능 영역에 연결했다. 미매핑은 0건이다(`gen_inventory.py --check` 종료 코드 0).
- API가 바뀌면 생성기가 새 member를 미매핑으로 보고하고 실패한다. 구현 티켓은 생성기를 다시 실행해 범위가 그대로인지 확인한다.

### 담당 티켓 요약

| 티켓 | 영역 | member 수 |
|---|---|---:|
| PEN-3 | 세로 단면: 브라우저 없이 사각형 저장 + 열린 캔버스 실시간 반영 (PEN-5·PEN-10 첫 조각) | — |
| PEN-4 | 프로젝트·파일 관리, 파일 메타데이터·버전·검증, 페이지 | 45 |
| PEN-5 | 도형 조회, 기본 도형 속성·생성·삭제 | 99 |
| PEN-6 | 동시 편집·재시도·재연결 일관성 (모든 쓰기 기능에 걸치는 계약, §5) | — |
| PEN-10 | 실행 컨텍스트, 플래그, storage, 사용자, 이벤트, UI 전용 응답 | 66 |
| PEN-11 | 계층·변환·정렬, 패스·Boolean·마스크·flatten | 64 |
| PEN-12 | 텍스트·폰트·부분 스타일 | 56 |
| PEN-13 | Flex·Grid 레이아웃 | 65 |
| PEN-14 | 컴포넌트·인스턴스·Variants | 40 |
| PEN-15 | 라이브러리 자산·연결, 디자인 토큰 | 169 |
| PEN-16 | 이미지·SVG | 14 |
| PEN-17 | Flow·상호작용·가이드 | 75 |
| PEN-18 | 댓글 | 15 |
| PEN-19 | 내보내기·코드 생성 | 5 |
| PEN-20 | 작업 단위·실패 원복·실행 취소 | 3 |
| PEN-24 | 'AI 따라가기': 켠 브라우저 탭에 페이지·선택·확대 적용 (D8, `ui` 영역의 브라우저 쪽) | — |

영역별 검증 시나리오는 `feature-inventory.md`의 '영역별 검증 시나리오'에 있다. 공통 판정 방법은 `03-runtime-contract.md` §6의 동등성 기준을 따른다. 같은 입력을 현재 MCP(브라우저 플러그인)와 서버 MCP에 각각 실행하고 결과를 비교한다.

### 목록 작성 중 발견한 구현 불일치

- **[사실]** `TokenTheme.externalId`는 타입 선언에 있지만 frontend가 `external-id`라는 이름으로 노출한다(`frontend/src/app/plugins/tokens.cljs:670`). 2026-10-14 검증 환경에서 `execute_code`로 확인한 결과 `externalId`는 `undefined`이고, `external-id`는 문자열이었다. PEN-15는 선언대로 `externalId`를 제공한다. 현재 동작과의 차이는 PEN-9 동등성 시험에서 예외로 기록한다.
- **[사실]** 텍스트를 만든 직후 `await penpot.waitForLayoutUpdate()`를 기다려도 `width/height`가 1×1로 읽혔다. 다음 호출에서는 436×39였다(실험 E3b). 현재 MCP에서는 텍스트 크기 계산이 이 대기 함수와 별도로 늦게 끝난다. 서버 계약에서는 결과를 돌려줄 때 계산이 끝나 있어야 한다(`03-runtime-contract.md` §3).

## 2. 실행 인터페이스 호환

**[사실]** 현재 `execute_code`는 AI가 보낸 JavaScript를 사용자 브라우저의 플러그인 sandbox(SES compartment) 안에서 `new Function`으로 실행한다. 전역으로 `penpot`, `penpotMgmt`, `penpotUtils`, `storage`, `console`을 받는다(`mcp/packages/plugin/src/task-handlers/ExecuteCodeTaskHandler.ts`). AI 클라이언트용 지침(`high_level_overview`)과 API 문서(`penpot_api_info`)도 이 인터페이스를 기준으로 쓰여 있다.

### D1 [사용자 결정 · 2026-10-15 확정] 서버에서 무엇을 호환할 것인가

| 선택지 | 내용 | 장점 | 비용·위험 |
|---|---|---|---|
| A. 코드 호환 | 서버에서 `execute_code`가 같은 JS를 받아 같은 `penpot.*` 객체로 실행한다 | 기존 AI 지침·프롬프트를 그대로 쓴다. 기능 범위가 API 범위와 같다 | 서버에서 사용자 코드를 실행한다. 별도 격리 프로세스·자원 제한이 필수다(§7). backend JVM 안에서는 실행하지 않는다(PEN-8) |
| B. 명령 인터페이스 | 기능마다 구조화된 MCP 도구(create_shape, set_layout 등)를 둔다 | 입력 검증과 권한 검사가 단순하다. 임의 코드를 실행하지 않는다 | 716개 member를 도구로 옮겨야 한다. 기존 지침을 새로 써야 한다. 조합 작업이 여러 번의 왕복이 된다 |
| C. 둘 다 | A를 기본으로 하고, 자주 쓰는 작업과 export·파일 관리는 B 도구도 둔다 | 호환성과 안전한 경로를 모두 갖는다 | 두 경로의 동등성을 모두 시험해야 한다 |

**결정: C.** `execute_code`의 코드·결과 형식을 호환한다(A). 도구 목록과 이름도 지금과 같게 유지한다. 인터페이스 선택은 기능 삭제를 뜻하지 않는다. B를 고르더라도 716개 member는 모두 도구로 제공해야 한다.

## 3. 인증·토큰

**[사실]**
- backend는 `Authorization: Token <access token>`을 받는다. token은 `access_token` 테이블의 행으로 검증하며, 만료되거나 지운 token은 거부한다(`backend/src/app/http/access_token.clj:17`, `backend/src/app/http/middleware.clj:277`). 생성·조회·삭제 RPC는 `create-access-token`, `get-access-tokens`, `delete-access-token`이다(`backend/src/app/rpc/commands/access_token.clj`).
- MCP token은 `type = "mcp"`인 access token이다. 화면의 Integrations에서 만들며, frontend는 만료되지 않은 첫 MCP token을 쓴다(`frontend/src/app/main/data/workspace/mcp.cljs:200`).
- 현재 MCP 서버는 `userToken`을 backend에서 검증하지 않는다. 같은 token을 가진 플러그인과 MCP 클라이언트를 짝짓기만 한다. 실제 권한 검사는 브라우저 세션이 backend를 부를 때 일어난다(`mcp/packages/server/src/PluginBridge.ts`, `PenpotMcpServer.ts:290`).
- exporter는 로그인 세션 쿠키(`auth-token`)만 받는다. access token만 보낸 export 요청은 400으로 실패했다(실험 E3).
- 권한이 없는 쓰기는 viewer·outsider 모두 `404 object-not-found`로 응답한다(실험 E1).

**[기술 결정]**
- 서버 MCP는 요청마다 사용자 token을 backend에서 검증한다. 모든 backend 호출에 그 사용자의 token을 그대로 쓴다. 서버 MCP가 권한 검사를 대신하거나 관리자 키로 우회하지 않는다.
- token 발급·갱신·폐기는 기존 access token RPC와 화면을 쓴다. 폐기·만료된 token의 실행 중 요청은 다음 backend 호출에서 실패하고 그 작업은 중단된다. 갱신은 새 token 발급과 이전 token 삭제로 한다.
- 권한 거부를 '파일 없음'과 구분하지 않는 backend 동작(404)을 그대로 전달한다. 존재 여부를 노출하지 않기 위해서다.
- export도 같은 사용자 token으로 동작해야 한다(PEN-19, `03-runtime-contract.md` §5).

### D2 [사용자 결정 · 2026-10-15 확정] 어떤 token을 받을 것인가

- 선택지 1: MCP token(`type=mcp`)만 받는다. 지금 화면 흐름과 같다.
- 선택지 2: 일반 API token도 받는다.

**결정: 선택지 1.** 기본 만료 기한은 현재 화면 정책을 따르고, 이 문서에서 새로 정하지 않는다.

### D11 [사용자 결정 · 2026-10-15 확정] backend가 MCP token을 어떻게 인정할 것인가

**[사실]** MCP token의 발급자는 `urn:penpot:mcp-token`이다. backend는 발급자가 `access-token`인 token만 API 인증에 받는다(`backend/src/app/http/access_token.clj`). upstream은 이를 테스트 `mcp-tokens-cannot-be-used-as-access-tokens`로 고정했다. 따라서 D2와 위 기술 결정('모든 backend 호출에 그 사용자 token')을 함께 지키려면 backend를 고쳐야 한다.

- 선택지 1 (결정): backend는 MCP token을 서버 MCP 실행기가 `mcp` 공유 키(`X-Shared-Key: mcp <key>`, exporter와 같은 방식)와 함께 보낼 때만 인정한다. 공유 키만으로는 권한이 없다. token 만료·폐기 검사는 그대로다. MCP token을 다른 곳에서 API token처럼 쓸 수 없다는 upstream 규칙도 그대로다.
- 선택지 2: MCP token을 일반 API token처럼 받는다.
- 선택지 3: D2를 바꿔 일반 API token을 받는다.

구현: `backend/src/app/http/access_token.clj`(`mcp-service-request?`), 공유 키 설정 `PENPOT_MCP_SHARED_KEY`(없으면 secret key에서 파생). 알림 WebSocket도 같은 조건에서만 token으로 인증한다. 공유 키는 D3의 'AI(사용자명)' 구분에도 쓴다.

### D3 [사용자 결정 · 2026-10-15 확정] 서버 MCP 작업을 누구의 이름으로 표시할 것인가

- 선택지 1: token 주인의 이름으로만 표시한다(현재와 같음).
- 선택지 2: presence·감사 로그에서 "AI(사용자명)"처럼 구분해 표시한다.

**결정: 선택지 2.** audit log에 실행 주체 표시를 남기고, 화면 presence에서는 구분 아이콘을 쓴다.

## 4. 대상 지정과 실행 컨텍스트

**[기술 결정]**
- 파일은 `fileId`로 지정한다. 열린 브라우저가 없으므로 '현재 파일'은 MCP 세션이 마지막으로 연 파일이다. `penpotMgmt.openFile()`과 같은 의미다. 연 파일이 없을 때 파일이 필요한 호출은 명시적 오류로 응답한다.
- 페이지는 `pageId`로 지정한다. `currentPage`는 세션 상태다. 처음에는 파일의 첫 페이지이고 `openPage`로 바꾼다. `openPage`가 브라우저 화면을 바꾸지는 않는다.
- 도형은 id로 지정한다. 이름은 중복될 수 있으므로 지정 수단으로 쓰지 않고 검색(`findShapes`)에만 쓴다.
- 실행 컨텍스트는 (사용자, MCP 세션) 단위로 둔다. `storage`와 서버 측 선택 상태는 이 단위로 격리하며 다른 사용자와 공유하지 않는다. 세션이 끝나면 지운다.
- **[사실]** 저장 요청의 `session-id`는 클라이언트가 정한다. backend WebSocket은 같은 `session-id`의 알림을 그 연결에 보내지 않는다(`backend/src/app/http/websocket.clj:163,186`). 따라서 서버 MCP는 MCP 세션마다 새 UUID를 `session-id`로 쓴다. 브라우저 탭의 `session-id`를 빌려 쓰면 그 탭이 서버 변경을 받지 못한다.

## 5. 저장 완료·버전·충돌·중복·취소 (PEN-6과 공유)

**[사실]** (`backend/src/app/rpc/commands/files_update.clj`, 실험 E1)
- `update-file`은 파일 단위 DB lock 안에서 순서대로 적용한다(`db/xact-lock!`).
- 요청의 `revn`이 저장된 값보다 작아도 **거부하지 않는다**. 변경을 최신 상태 위에 적용하고, 그 사이 다른 클라이언트의 변경(`lagged`)을 응답에 돌려준다. 실측: revn 1로 보낸 변경이 저장값 2 위에 적용됐다.
- 요청의 `revn`이 저장값보다 크면 `400 revn-conflict`로 거부한다. `vern`이 다르면(버전 복원 후) `vern-conflict`로 거부한다.
- 요청 식별자가 없어 같은 요청을 다시 보내면 다시 적용된다. 실측에서 `add-obj` 재전송은 같은 id를 덮어써 도형이 중복되지 않았다. 그래도 revn이 올라가고 변경 기록과 알림이 다시 나갔다. 상대 이동처럼 누적되는 변경은 두 번 적용된다(추론, 미측정).
- 다른 클라이언트에는 msgbus → WebSocket으로 `:file-change`를 보낸다. 연결별 버퍼는 64개이고 넘치면 버린다(`sp/dropping-buffer 64`, `websocket.clj:163,186`). 빠르게 연속 저장할 때 브라우저가 변경을 놓칠 수 있다. 실제로 놓치는지와 재동기화 여부는 [미확인 → PEN-6].
- 지연: 서버 저장 0.023–0.051초. 저장을 시작해 두 관찰 브라우저 레이어 목록에 반영되기까지 0.73초 이내였다(스크립트 시작 기준, 단일 변경).

**[기술 결정]**
- 저장 완료 응답에는 `revn`(저장 후), 바뀐 도형 id, `lagged` 적용 여부, 계산 완료 여부(레이아웃·텍스트)를 넣는다. 저장 전에 실패하면 아무것도 저장되지 않았음을 명시한다.
- 한 번의 `execute_code`나 도구 호출이 만든 변경은 한 번의 `update-file`로 보낸다. 실행 취소 단위도 하나로 묶는다(PEN-20).
- 연속 저장은 묶어서 보낸다. 알림 버퍼(64개) 때문에 변경 단위로 많이 보내지 않는다.

### D4 [사용자 결정 · 2026-10-15 확정] AI 변경과 사람 변경이 겹칠 때

- 선택지 1: 사람끼리와 같은 규칙을 쓴다. 변경 단위로 나중 저장이 이기고, 오래된 revn도 받는다.
- 선택지 2: AI 작업에는 사전 조건을 둔다. 읽은 뒤 대상 도형이 바뀌었으면 거부하고 다시 시도하게 한다.

**결정: 선택지 1을 기본으로 하고, 도구 인자로 선택적 사전 조건(`ifUnchangedSinceRevn`)을 제공한다.**

### D5 [사용자 결정 · 2026-10-15 확정] 같은 요청을 두 번 받았을 때

- 선택지 1: 서버 MCP가 클라이언트의 `requestId`로 일정 시간(제안: 10분) 결과를 기억하고 다시 적용하지 않는다.
- 선택지 2: 중복을 허용한다.

**결정: 선택지 1.** 재연결 뒤 재시도가 두 번 적용되는 일을 막는다.

### D6 [사용자 결정 · 2026-10-15 확정] 작업 취소

- 선택지 1: 저장 전 취소만 지원한다. 계산 중에 취소하면 아무것도 저장하지 않는다. 저장 후에는 실행 취소(undo) 도구로 되돌린다.
- 선택지 2: 저장 후 취소도 자동 원복으로 처리한다.

**결정: 선택지 1.** 저장 후 자동 원복은 그 사이 사람이 한 변경과 충돌할 수 있다.

### D7 [사용자 결정 · 2026-10-15 확정] 실시간 반영 지연 기준

**결정**: 단일 작업은 저장 응답부터 열린 브라우저 반영까지 p95 1초 이하로 한다. 도형 1,000개 이하를 바꾸는 묶음 작업은 p95 3초 이하로 한다. 측정 방법은 E1과 같다. 관찰 브라우저 두 개의 레이어 목록 또는 캔버스 변화를 기준으로 한다.

## 6. 브라우저 UI 전용 API

문서 기능은 UI 전용으로 분류하지 않는다. 예를 들어 `openPage`가 하는 '현재 페이지 바꾸기'는 서버 세션 상태로 제공하고, 화면 이동만 UI 전용으로 본다.

### D8 [사용자 결정 · 2026-10-15 확정] member별 대응 방식

방식:
- (a) 서버 컨텍스트: 서버 세션 상태로 같은 의미를 제공한다.
- (b) 관찰: 같은 사용자의 브라우저가 열려 있으면 그 상태를 읽는다.
- (c) 명시적 UI 전용 응답: 고정된 오류 코드 `ui-only`와 이유를 돌려준다.
- (f) 따라가기: 같은 사용자가 그 파일을 연 브라우저 탭에서 "AI 따라가기"를 켰을 때만 그 탭 화면에 적용한다. 켠 탭이 없으면 (c)로 응답한다. 구현은 PEN-24.

조용히 무시하거나 빈 값을 성공처럼 돌려주지 않는다.

**결정:**
- AI의 선택과 현재 페이지는 서버 세션 상태로 둔다. 사용자 화면은 기본적으로 움직이지 않는다. 사용자가 브라우저 탭에서 "AI 따라가기"를 켰을 때만 그 탭이 AI의 현재 페이지와 선택을 따라간다.
- 화면 확대·위치를 읽는 호출은 같은 사용자의 브라우저가 열려 있으면 그 값을 읽는다. 없으면 `ui-only`로 응답한다.
- 화면을 움직이는 호출은 따라가기를 켠 탭에만 적용한다. 켠 탭이 없으면 `ui-only`로 응답한다. 편집 화면을 떠나게 하는 `openViewer()`와 플러그인 창 API는 따라가기와 상관없이 (c)다.

| member | 방식 | 이유 |
|---|---|---|
| `selection` (읽기·쓰기) | (a) + (f) | 많은 AI 코드가 선택을 작업 대상 목록으로 쓴다. 세션별 가상 선택으로 제공하고, 따라가기를 켠 탭에는 같은 선택을 표시한다 |
| `TokenBase.applyToSelected()` | (a) | 위의 가상 선택에 적용한다 |
| `openPage()` | (a) + (f) | 세션의 현재 페이지를 바꾼다. 따라가기를 켠 탭만 그 페이지로 이동한다 |
| `viewport`, `Viewport.center/zoom/bounds` 읽기 | (b), 없으면 (c) | 화면 좌표·배율은 문서 상태가 아니다 |
| `Viewport.center/zoom` 쓰기, `Viewport.zoomReset/zoomToFitAll/zoomIntoView()` | (f), 없으면 (c) | 화면 조작이다 |
| `theme` | (b), 없으면 `light` 고정값과 표시 | 결과에 영향이 없는 값이다 |
| `openViewer()` | (c) | 편집 화면을 떠나는 이동이다. 대신 viewer URL을 돌려줄 수 있다 |
| `ActiveUser.position/zoom` | (b) | presence 정보로 읽는다 |
| `ui.open/size/resize/sendMessage/onMessage`, `closePlugin()` | (c) | 플러그인 창이 없다 |
| 이벤트 `selectionchange`, `themechange`, `workspacechange` | (a)/(b) | 세션 상태 변화 또는 관찰한 브라우저 변화로 낸다 |
| 이벤트 `shapechange`, `filechange`, `contentsave`, `pagechange` | 서버 이벤트 | 저장된 문서 변경 알림(`:file-change`)으로 만든다(PEN-10) |

**[기술 결정]** 따라가기 규칙 (PEN-24):
- 따라가기는 브라우저 탭마다 켜고 끈다. 기본은 꺼짐이다.
- 대상은 같은 사용자가 같은 파일을 연 탭 중 따라가기를 켠 탭이다. 다른 사용자의 화면은 움직이지 않는다.
- (f) 호출의 결과에는 화면에 적용했는지(켠 탭이 있었는지)를 넣는다.
- 화면 반영 지연은 D7 기준을 따른다.
- **[미확인 → PEN-24]** 따라가기 중 사용자가 직접 화면을 움직일 때의 동작은 구현 전에 사용자와 정한다.

## 7. 장시간 작업·자원 제한·로그

**[사실]** 현재 도구 제한 시간은 `PENPOT_MCP_TOOL_TIMEOUT_S`이며 기본 120초다(`PenpotMcpServer.ts:154`). 현재 MCP 서버는 task 단위로 성공 여부만 기록하고, 코드나 결과는 기록하지 않는다(`PluginBridge.ts:325`).

### D9 [사용자 결정 · 2026-10-15 확정] 기본 제한값과 로그 보관

**결정 (구현 단계에서 측정해 조정)**:
- 실행당 제한: 시간 120초, 메모리 256 MB, 한 번에 저장하는 변경 5,000개.
- 사용자당 동시 실행 2개, 서버 전체 동시 실행은 CPU 수만큼.
- 초과하면 저장 전에 중단하고 `resource-limit` 오류를 돌려준다.
- 로그에는 사용자 id, 세션 id, 도구 이름, 파일 id, 소요 시간, 변경 개수, 결과 코드만 남긴다. 코드 본문, 결과 값, 텍스트 내용, token은 남기지 않는다. token은 지문(앞 몇 글자 hash)만 남긴다. 디버그용 코드 기록은 개발 환경에서만 켠다.

## 8. 사용자 결정 목록

| ID | 질문 | 결정 | 상태 |
|---|---|---|---|
| D1 | `execute_code` 코드 호환 / 명령 인터페이스 / 둘 다 | 둘 다 (코드 호환 기본) | 2026-10-15 확정 |
| D2 | 받을 token 종류 | MCP token만 | 2026-10-15 확정 |
| D3 | 서버 작업 표시 주체 | "AI(사용자명)" 구분 표시 | 2026-10-15 확정 |
| D4 | AI·사람 동시 편집 충돌 | 사람과 같은 규칙 + 선택적 사전 조건 | 2026-10-15 확정 |
| D5 | 중복 요청 | `requestId`로 10분 중복 제거 | 2026-10-15 확정 |
| D6 | 작업 취소 | 저장 전 취소만, 저장 후는 undo | 2026-10-15 확정 |
| D7 | 반영 지연 기준 | 단일 p95 1초, 묶음 p95 3초 | 2026-10-15 확정 |
| D8 | UI 전용 member 대응 | §6 표, 화면 조작은 'AI 따라가기'를 켠 탭에만 적용 | 2026-10-15 확정 |
| D9 | 자원 제한·로그 | §7 값 | 2026-10-15 확정 |
| D11 | backend의 MCP token 인정 방식 | 서버 MCP 실행기가 `mcp` 공유 키와 함께 보낼 때만 | 2026-10-15 확정 |

서버 실행 구조('브라우저 없이'를 어디까지로 볼지)는 기술 조사 결과에 달려 있어 `03-runtime-contract.md`의 D10에서 정했다(2026-10-15 확정).
