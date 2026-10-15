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
