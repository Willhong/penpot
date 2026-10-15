# 티켓별 확인 결과 (PEN-22)

모든 시험은 `verification-env.md`의 스택에서 실제 MCP 호출(`?executor=server`)로 한다. 각 스크립트는 JSON 보고를 내고 실패가 있으면 종료 코드 1을 낸다. 보고 원본은 `.mcp-verify/`(gitignore)에 남는다.

## PEN-3 세로 단면 (2026-10-15, `experiments/pen3_vertical_slice.py`)

editor가 MCP token과 `?executor=server`로 `execute_code`를 부른다. 브라우저에서 Connect를 누르지 않는다.

| 확인 | 결과 |
|---|---|
| 관찰 탭 두 개가 열린 상태에서 사각형 저장 | 저장 성공(revn 0→1). owner·editor 탭에 새로고침 없이 MCP 응답 뒤 46–186 ms에 나타남(D7 1초 이내). backend 재조회 x·y·크기·색이 같음 |
| owner 탭 새로고침 | 사각형이 남아 있음 |
| 두 탭을 닫은 상태에서 두 번째 사각형 저장 | 0.05–0.09초, 저장 성공. 탭을 다시 열면 두 사각형 모두 보임 |
| 플러그인 경로 | 연결된 세션 없음(`executor=plugin`은 실패) — Connect 불필요 |
| 잘못된 token / 일반 API token | `forbidden`, 변경 없음 |
| viewer / 팀 밖 사용자 / 없는 파일 | `not-found`, 변경 없음 |
| 잘못된 입력 / 편집 뒤 예외 | `execution-error`, 변경 없음. 세션도 실패 전 상태로 돌아감 |
| 첫 호출 | 프로세스 시작을 포함해 4–6초 |

## PEN-4 프로젝트·파일·페이지·메타데이터 (2026-10-15, `experiments/pen4_files_pages.py`)

| 확인 | 결과 |
|---|---|
| 브라우저 0개에서 `listProjects` | backend `get-projects`와 같은 목록 |
| `createProject`(이름 앞뒤 공백 제거) → `createFile` → `listFiles` → `openFile` | 만든 파일 하나만 보임, `workspace.status` none → ready, `currentFile`의 id·name·revn·pages 일치 |
| 페이지 생성·이름 변경, 파일·페이지 plugin data, shared plugin data | backend 재조회 결과에 그대로 있음 |
| 새로 연 브라우저 두 개 | 같은 페이지 목록 |
| 열린 브라우저에서 MCP로 페이지 추가·이름 변경 | 0.33초 안에 새로고침 없이 반영 |
| `saveVersion` → `findVersions` → 이름 변경 → 복원 | 복원 뒤 서버 세션·backend 모두 이전 내용, vern 바뀜. 열린 두 탭도 0.5초 안에 복원 내용으로 바뀜 |
| 자동 저장 버전 `pin()` → `remove()` | pin 뒤 `isAutosave` false, 삭제됨 |
| `validate()` | 빈 목록 |
| 메인 컴포넌트가 있는 페이지 삭제, 마지막 페이지 삭제 | 같은 코드를 브라우저(wasm)에서 실행한 결과와 같음: 남은 페이지, 컴포넌트 목록, 인스턴스 상태, 오류 문구 |
| viewer의 페이지 생성·이름 변경 | `not-found`(읽기 전용), 변경 없음 |
| 팀 밖 사용자 `openFile`, 잘못된 id, 빈 이름 | 거부, 변경 없음 |

이 작업에서 고친 frontend 문제(브라우저에도 있던 것):
- `FileVersion.pin()`: RPC 응답 이름이 버전 데이터 이름을 가려 응답(`true`)을 deref했다. 약속이 끝나지 않았다.
- 저장 상태 `:pending`이 이미 저장된 뒤 늦게 도착해 저장 대기가 끝나지 않았다(편집 직후 200ms 안에 강제 저장할 때, 예: 버전 복원).

실행기에서 바꾼 것:
- 시작할 때 기본 팀을 초기화한다(브라우저의 대시보드와 같다). 없으면 파일을 열기 전 `createFile`이 기능 목록 없이 요청되어 거부됐다.
- 읽기 전용 파일에서 workspace가 조용히 버리는 편집을 `not-found`로 알린다.
- 파일을 열 때 읽기 권한을 먼저 확인해 바로 실패한다(전에는 30초 시간 초과).
- 버전 복원 뒤 파일을 다시 읽을 때까지 실행을 끝내지 않는다.
- 실행이 저장한 revn을 기억해, 다음 실행의 `revnBefore`·`lagged`를 바로 잡는다.
- 처리되지 않은 예외가 프로세스를 끝내지 않는다(브라우저 콘솔처럼 기록만).

## 비교 방법 (PEN-5부터, `experiments/dual_run.py`)

같은 Plugin API 시나리오를 두 곳에서 각각 새 파일에 실행한다.
- 브라우저: editor 탭(renderer wasm)에서 MCP 플러그인과 같은 조건으로 실행한다(MCP 플러그인 id, 두 flag, strict mode, plugins runtime처럼 내장 객체 동결과 반환값 harden). `browser_run.js`.
- 서버: 실제 MCP 호출(`?executor=server`). 그동안 owner 탭이 서버 쪽 파일을 열어 두고, 새로고침 없이 결과를 받는지와 새로고침 뒤에도 같은지 본다.

비교: 시나리오 반환값과 backend에 저장된 모든 도형(이름으로 짝지음). id는 이름으로 바꾸고, 숫자는 소수 2자리로 맞춘다(`03` §6).

## PEN-5 기본 도형 (2026-10-15, `experiments/pen5_basic_shapes.py`)

| 시나리오 | 내용 | 결과 |
|---|---|---|
| `pen5_shapes.js` | 보드·사각형·타원 생성, 이름·위치·크기·모서리(전체·각각)·투명도·혼합·비율 고정·스크롤 고정·숨김·잠금·`visible`, 단색·선형·방사형 채우기, 선(점선·외곽·그라데이션), 그림자 2종, 흐림, 배경 흐림, 내보내기 설정 2개, plugin data·shared plugin data, 보드 clipContent·showInViewMode, 읽은 배열을 고쳐도 도형은 그대로인지, clone, remove, `root`·`getShapeById`·`findShapes`·`parent`·`bounds`·`center` | 반환값 차이 0, 저장 도형 7개 차이 0. 관찰 탭 0.21초에 반영, 새로고침 뒤 같음 |
| `pen5_refusals.js` | 잘못된 값 13종(투명도 2, 음수 크기, 없는 혼합 모드, 잘못된 색·투명도·선 모양·그림자 모양·내보내기 형식·모서리·이름·plugin data 값, 사각형의 clipContent, 지운 도형 수정) | 거부 문구와 남은 값이 브라우저와 같음. 저장 도형 차이 0 |
| 서버만 | viewer의 수정, 열려 있지 않은 페이지의 도형 수정 | `not-found` / 브라우저와 같은 문구로 거부, 변경 없음 |

## PEN-6 동시 편집·재시도·재연결 (2026-10-15, `experiments/pen6_consistency.py`)

사람은 관찰 탭 두 개(owner, editor)에서 Plugin API 코드를 실행하고, AI는 editor의 MCP 호출이다. 각 확인 뒤 backend, 두 탭, 서버 세션이 보는 값을 비교한다.

| 확인 | 결과 |
|---|---|
| 사람과 AI가 다른 도형을 동시에 수정 | 네 곳 모두 같은 값(4.4초 안에 수렴) |
| 같은 속성 충돌(D4 기본) | 나중에 저장한 값이 네 곳 모두에 남음(AI가 나중이든 사람이 나중이든) |
| 사람이 지운 도형을 AI가 예전 참조로 수정 | 아무 곳에서도 되살아나지 않음. 오류 없이 무시되는 것은 브라우저와 같은 Plugin API 동작 |
| `ifUnchangedSinceRevn`(D4 선택) | 사이에 사람이 고쳤으면 `precondition-failed`, 코드 실행·저장 없음. 최신 revn으로는 저장 |
| 다른 사람이 버전 복원 | 서버 세션이 복원 알림으로 파일을 다시 읽고, 다음 AI 저장이 복원된 내용 위에 들어감(`vern-conflict` 없음) |
| 같은 `requestId` 재시도·동시 중복(D5) | 첫 결과를 `replayed: true`로 돌려주고 도형은 하나 |
| 실행 중 클라이언트 연결 끊김 | 저장 전 취소(D6), 재시도는 한 번만 실행 |
| 서버는 저장했지만 클라이언트가 응답을 못 읽음 | 재시도가 기록된 결과를 돌려줌(`replayed`), 도형 하나 |
| 관찰 탭의 알림 연결 끊김 중 AI 저장 3회 | 재연결 뒤 놓친 변경을 받아 새로고침 없이 backend와 같아짐(약 9초, 재연결 대기 포함) |
| 두 세션에서 저장 50회 연속(E8) | 놓친 알림 없이 네 곳 모두 같음 |
| 실행 중 편집 권한 회수 | `not-found`, 변경 없음. 권한을 되돌리면 다음 실행은 저장 |
| 실행 중 MCP 서버 정상 종료(Ctrl-C) | `cancelled`, 저장 없음. 같은 `requestId` 재시도는 한 번 실행 |
| 실행 중 MCP 서버 강제 종료(SIGKILL) | 저장 없음. 같은 `requestId` 재시도는 결과를 알 수 없다며 `precondition-failed`(중복 위험 대신 거부) |
| 실행기 부팅 중 MCP 서버 정상 종료(`pen6_shutdown.py`, 3회) | `cancelled`, 저장 없음. 재시도는 한 번 실행 |
| 도형 1500개 저장을 실행 시간의 60·75·90·97% 시점에 정상 종료(`pen6_shutdown.py`) | 답이 실제 저장과 항상 일치: "저장 없음"이면 backend에도 없고 재시도가 한 번 실행. 응답이 끊기면 재시도를 거부하고 두 벌이 생기지 않음 |

이 작업에서 고친 결손:
- **브라우저(와 실행기)는 알림 연결이 끊긴 사이의 변경을 새로고침 전까지 받지 못했다.** 재연결하면 구독만 다시 보냈다. backend에 `get-file-changes`(어떤 revn 이후 저장된 변경, 읽기 권한 확인)를 추가하고, 재연결 때 다른 세션의 변경을 적용한다. 그 범위의 기록이 이미 지워졌거나 파일이 복원됐으면 파일을 다시 읽는다.
- 실행기가 알림 연결을 열지 않아 다른 사람의 변경을 몰랐다. 브라우저처럼 연결하고, 복원 알림으로 다시 읽은 뒤 엔진에도 도형을 다시 올린다.
- D5 `requestId` 기록(`RequestLedger`): 같은 사용자·ID의 결과를 10분 보관. Redis가 있으면 MCP 서버 인스턴스끼리 공유하고 재시작 뒤에도 남는다. 저장 없이 실패한 요청은 기록을 지워 다시 시도할 수 있다.
- D6 취소: 실행기에 취소를 요청한다. 코드 실행 중이면 저장 없이 끝내고, 이미 저장 중이면 끝까지 저장한다. 응답이 없으면(끝나지 않는 동기 코드) 프로세스를 끝낸다.
- (PEN-10 작업 중 발견) 실행기 프로세스가 저장 중에 끝나도 "nothing was saved"로 답하고 요청 ID 기록을 지웠다. 저장이 backend에 반영된 뒤라면 같은 `requestId` 재시도가 변경을 두 번 적용할 수 있었다. 이제 저장 시작을 먼저 알리고, 그 뒤에 끝나면 `saved: "unknown"`으로 답하며 기록을 남긴다. 저장 중 받은 종료 신호는 저장을 마친 뒤에 따른다.
- (같이 발견) MCP 서버가 멈출 때 요청 ID 기록 저장소를 실행기 정리보다 먼저 닫아, 저장 없이 끝난 요청의 기록이 남아 재시도가 불필요하게 거부될 수 있었다. 실행기를 먼저 정리한다.

조사했지만 고치지 않은 것(결손을 재현하지 못함):
- backend `update-file`은 트랜잭션 안에서 알림을 먼저 보낸다(`files_update.clj` `send-notifications!`). 그 뒤 커밋이 실패하면 저장되지 않은 변경이 열린 화면에 나갈 수 있다. 커밋 실패를 일으키는 경로를 찾지 못했다. 고친다면 커밋 뒤에 알림을 보내야 한다.

## PEN-10 실행 컨텍스트 마무리 (2026-10-15, `experiments/pen10_context.py`)

AI는 editor의 MCP 호출, 탭 p2는 같은 editor의 브라우저, 탭 p1은 owner(다른 사용자)다.

| 확인 | 결과 |
|---|---|
| 같은 사용자의 탭이 없을 때 | `viewport` 읽기·쓰기 `ui-only`, `theme`는 `"light"` |
| p2에서 배율·중심을 바꾼 뒤 AI가 `viewport` 읽기 | p2의 `zoom`·`center`·`bounds`와 같음(0.01초 안). p1(다른 사용자)의 배율 0.5는 쓰지 않음. 포인터를 움직이지 않아도 반영 |
| `theme` | p2의 `penpot.theme`와 같음(`dark`) |
| p2가 화면을 정한 뒤 새 세션이 파일을 엶 | 두 번째 읽기(0.5초 뒤)부터 p2의 화면. 첫 읽기는 탭이 알리기 전이라 `ui-only`이며 메시지가 그 사정을 말한다 |
| 화면 쓰기(`zoom = 3`, `zoomToFitAll`) | `ui-only`("AI follow" 탭 없음) |
| owner 탭이 보는 presence | editor의 브라우저 탭은 화면을 알리고, 실행기 세션은 알리지 않음 |
| `penpot.on` (shapechange·selectionchange·contentsave) | 실행이 끝난 뒤에도 유지. 자기 변경(`a.x = 10`, 선택, 저장)과 p1이 저장한 변경(`a.x = 321`)을 모두 들음. `penpot.off` 뒤에는 듣지 않음 |
| `openViewer`, `ui.open`, `closePlugin`, `zoomToFitAll` | 모두 `ui-only` |
| `high_level_overview`·`penpot_api_info` | 서버 연결은 서버 실행 절과 member 설명을 받고, 플러그인 연결은 예전 그대로 |

고친 결손:
- 실행기가 실행이 끝날 때 `penpot.on` listener를 지워서, 다른 사람이 저장한 변경을 들을 수 없었다(계약은 `:file-change`로 만든 이벤트). 브라우저 플러그인처럼 세션 동안 남긴다.
- 브라우저 탭은 포인터를 움직일 때만 화면을 알렸다. 단축키 확대·스크롤처럼 포인터 없이 바뀐 화면과, 나중에 들어온 세션은 그 탭의 화면을 몰랐다.

## PEN-11 계층·변환·패스·Boolean (2026-10-15, `experiments/pen11_hierarchy.py`)

`dual_run.py`로 같은 코드를 브라우저(wasm)와 서버에서 실행해 비교했다. 실행기 변경은 필요 없었다.

| 확인 | 결과 |
|---|---|
| `pen11_structure.js`: 그룹·중첩 그룹·해제, clone, 부모 변경(회전한 board 안으로 포함), `insertChild`, z-order 4종과 `setParentIndex`, 가로·세로 정렬과 분배, 회전(중심 지정 포함)·반전, constraints, 마스크 설정·해제, path `d`·`commands`, Boolean 4종, flatten | 반환값(트리·좌표·크기·회전·반전·`toD()`) 같음. 저장된 도형 41개의 모든 속성(selrect, points, transform, path·bool content) 같음. 관찰 탭에 새로고침 없이 0.5초 안에 반영, 새로고침 뒤에도 같음 |
| `pen11_refusals.js`: 부모 순환, 잘못된 path·Boolean 종류·index·변환 값 21가지 | 답(오류 메시지)과 남은 트리 같음 |
| 구조 편집 뒤 코드가 오류를 던짐(서버만) | 아무것도 저장되지 않고, 세션의 트리도 실행 전으로 돌아감 |

고친 결손(브라우저 플러그인과 공통인 Plugin API, `frontend/src/app/plugins/`):
- 도형을 자기 자신이나 자기 자식 안으로 옮기는 `appendChild`/`insertChild`가 오류 없이 무시됐다. 거부한다.
- 읽을 수 있는 path 명령이 하나도 없는 문자열을 `path.d`에 넣으면 오류 없이 도형 내용이 지워졌다. 거부하고 내용을 지킨다.
- `penpot.ungroup`에 그룹·Boolean·board가 아닌 도형을 주면 오류 없이 무시됐다. 거부한다.

바꾸지 않은 차이(브라우저와 서버가 같음, PEN-9 예외 목록 후보):
- 타입 선언은 `PathCommand.command`에 `'M'`, `'L'`, `'Q'` 같은 짧은 이름과 2차 곡선을 허용한다고 적지만, `commands` setter는 `move-to`, `line-to`, `curve-to`, `close-path`만 받는다.
- `createBoolean`은 도형 하나로도 Boolean을 만든다. `setParentIndex(-1)`, 범위 밖 `insertChild` index는 오류 없이 끝으로 맞춘다.

## PEN-12 텍스트·폰트·텍스트 크기 (2026-10-15, `experiments/pen12_texts.py`)

| 확인 | 결과 |
|---|---|
| `pen12_text.js`(dual run): 영문, 한글 자동 높이, 이모지·한글 섞인 글, 오른쪽→왼쪽(히브리어·아랍어), 빈 줄 포함 여러 문단, 부분 스타일 6구간, 고정 크기 상자의 줄바꿈과 세로 가운데 정렬, 구글 폰트(Roboto 전체, Work Sans 구간)와 모든 텍스트 속성 | 반환값(크기·속성·구간 스타일) 같음. 저장된 텍스트 10개의 모든 속성이 `position-data`까지 같음. 관찰 탭에 새로고침 없이 반영, 새로고침 뒤에도 같음 |
| `pen12_refusals.js`(dual run): 잘못된 텍스트 값 15가지 | 답과 남은 상태 같음 |
| 브라우저 0개에서 실행(새 실행기 세션) | 저장 결과에 최종 크기와 `position-data`가 이미 있음(`pending` 없음). 그 뒤 브라우저를 열어도 파일 revn이 그대로(1)이고 크기·`position-data`가 바뀌지 않으며, 브라우저가 보는 크기도 같음 |

고친 결손(브라우저와 공통인 workspace 코드, `frontend/src/app/main/data/workspace/`):
- **한글·이모지처럼 지정 폰트에 없는 글자의 대체 폰트를 기다리지 않고 쟀다.** 대체 폰트는 글자를 보고 그때 받는데, 측정은 지정 폰트만 확인했다. 그 폰트를 처음 받는 화면(새 실행기, 캐시 없는 브라우저)은 한글 문장 너비를 373 대신 163으로 저장했다. 측정 전에 대체 폰트도 확인하고, 없으면 요청해 받은 뒤 잰다(받기에 실패하면 기다리지 않는다).
- **같은 글꼴에서 굵기·기울기만 바꾸면 그 글꼴 파일이 오기 전에 쟀다.** 텍스트 전체 스타일 변경은 글꼴(`font-id`)이 바뀔 때만 기다렸다. 처음 굵게 만든 텍스트가 보통 굵기 너비(343, 맞는 값 357)로 저장되고, 브라우저는 나중에 폰트가 오면 다시 재서 저장했다. 이제 필요한 글꼴 파일이 없으면 기다린다.
- **grow type이 자동에서 고정으로 바뀌는 크기 변경 뒤 `waitForLayoutUpdate`가 시간 초과됐다**(E4에서 찾은 결손). 대기 표시를 바뀌기 전 grow type으로 판단해 걸었는데 고정 텍스트는 다시 재지 않으므로 아무도 풀지 않았다. 바뀐 뒤 grow type으로 판단한다. `resize(w, h)`가 자동 높이 텍스트를 고정으로 바꾸는 것은 높이를 직접 정했기 때문이며 UI 규칙과 같다.

참고(브라우저와 같음): `createText` 직후 텍스트는 너비 1에서 시작해 첫 측정(약 0.25초) 뒤 제 크기가 된다. 그 전에 grow type을 `auto-height`로 바꾸면 너비 1에 맞춰 줄바꿈한다. 먼저 `waitForLayoutUpdate`를 기다리면 된다.

## PEN-13 Flex·Grid·중첩 레이아웃 (2026-10-15, `experiments/pen13_layouts.py`)

| 확인 | 결과 |
|---|---|
| `pen13_layout.js`(dual run): flex(방향·wrap·정렬 4종·간격·개별 padding), 자식 fill/auto/fix·min/max·margin·align-self·absolute·z-index, 내용을 감싸는(hug) 3단 중첩 flex, grid(fixed·flex·percent·auto 트랙, row/column span, 셀 정렬), flex 안의 grid. 이어서 부모 크기 변경, 자식 추가·숨김·순서 변경·삭제, 트랙 삭제, 깊은 자식 크기 변경, 레이아웃 제거 | 10단계마다 `waitForLayoutUpdate`가 끝나고, 단계별 모든 도형의 좌표·크기가 브라우저와 같음. 저장된 도형 22개 같음. 관찰 탭에 새로고침 없이 반영 |
| `pen13_refusals.js`(dual run): 잘못된 레이아웃 값 19가지 | 답과 남은 상태 같음 |
| 브라우저 0개에서 실행 | 저장 뒤 브라우저를 열어도 revn 그대로, 저장값 그대로 |
| 파생 값 계산이 제한 시간 안에 끝나지 않음(통합 시험, 제한 1ms로 강제) | `resource-limit`, 남은 작업을 도형 id별로 알림, 저장 없음. 같은 코드가 기본 제한에서는 저장됨 |

고친 결손:
- **flex·grid의 `appendChild`가 서버에서 실패했다.** 플러그인 proxy들은 서로를 브라우저 전용 `app.plugins` 네임스페이스가 로드될 때 연결하는데, 실행기는 그 네임스페이스(브라우저 플러그인 런타임을 불러옴)를 로드하지 않는다. 연결을 `app.plugins.wiring`으로 옮겨 양쪽이 로드한다. ruler guide, 라이브러리 타이포그래피·variant proxy 연결도 같이 해결된다.
- **`penpot.utils.geometry.center`가 서버에서 `window is not defined`로 실패했다**(PEN-10 범위에서 놓침). 플러그인 런타임이 `window.app`으로 frontend 함수를 부르기 때문이다. 실행기가 그 함수를 직접 넘긴다.
- **파생 값 계산이 10초 안에 끝나지 않으면 덜 끝난 채 저장했다**(`computed: false`). 계약 03 §3("실행이 끝날 때는 항상 파생 값 계산을 끝낸다")과 달리 나머지를 다음에 파일을 여는 브라우저에 떠넘긴다. 이제 저장하지 않고 `resource-limit`으로 실패한다.

비교 도구(`dual_run.py`): grid 셀처럼 실행마다 새로 만든 id를 키로 쓰는 값은 키 대신 내용으로 비교한다.
