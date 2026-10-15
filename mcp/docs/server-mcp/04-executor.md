# 서버 실행기 구조와 interface (PEN-10)

입력: `01-feature-contract.md`(D1–D9, D11), `03-runtime-contract.md`(D10, D12, D13), 실험 E4.

상태: 공용 구성 요소의 interface를 확정했다(2026-10-15). PEN-3에서 실제 MCP 호출부터 열린 브라우저 반영까지 연결했다. 다른 티켓은 이 interface 위에서 기능을 채운다.

## 1. 방식

**[기술 결정]** `penpot.*`를 서버용으로 새로 짜지 않는다. frontend의 편집 계층(store, workspace 이벤트, `app.plugins.api`)을 Node에서 그대로 돌리고, render-wasm만 `_init_headless`로 띄운다(E4). 이유:

- 레이아웃·텍스트·boolean·컴포넌트 동기화는 workspace 이벤트 안에서 render-wasm 계산과 얽혀 있다(`apply-wasm-modifiers`, `resize-wasm-text`, 위치 데이터 묶음 저장 등). 서버에서 다시 쓰면 같은 결과를 보장할 수 없다.
- 같은 코드를 쓰면 같은 결과가 나온다. E4에서 브라우저(wasm 모드)와 이벤트 순서, 내부 작업 번호, 저장 값이 모두 같았다.
- Chromium을 쓰지 않는다(D10).

## 2. 구성 요소

```
MCP 클라이언트 ──HTTP──▶ MCP server (mcp/packages/server)
                          ├─ ExecuteCodeTool: ?executor=server 이면 실행기로 보낸다
                          └─ ExecutorPool ── (사용자 token, sessionId)마다 ExecutorProcess
                                               │ child_process.fork, IPC, 힙 상한
                                               ▼
                          실행기 프로세스 (dist/executor-child.js)
                          ├─ ExecutorRuntime: 실행 1회의 순서
                          ├─ Sandbox: 실행마다 새 SES compartment
                          ├─ ServerPluginApi: plugins-runtime `createApi` + D8 대응
                          └─ HeadlessEngine ── frontend `:executor` 빌드 (frontend/src/app/executor/)
                               ├─ session: 파일·페이지 열기 (headless 라우터)
                               ├─ api: 실행 시작·완료·취소
                               ├─ auth: backend 요청에 사용자 MCP token + mcp 공유 키
                               └─ wasm: render-wasm headless 부팅
                                         │ Authorization: Token <MCP token>, X-Shared-Key: mcp …
                                         ▼
                          backend (권한·저장·검증·알림)
```

| 구성 요소 | 위치 | 하는 일 |
|---|---|---|
| `ExecutorPool` | `server/src/executor/ExecutorPool.ts` | 세션별 프로세스, 세션 안 실행 순서, 동시 실행 상한(D9), 유휴 세션 정리, 실행 로그(D9) |
| `ExecutorProcess` | `server/src/executor/ExecutorProcess.ts` | 프로세스 시작(깨끗한 환경 변수, `--max-old-space-size`), 요청·응답 짝짓기, 시간 초과·취소 시 종료 |
| `ExecutorConfig` | `server/src/executor/ExecutorConfig.ts` | 환경 변수, 공유 키 파생, token 지문 |
| `ExecutorProtocol`, `ExecutorError` | `server/src/executor/` | IPC 메시지, 결과 envelope, 오류 코드(§7) |
| `ExecutorRuntime` | `server/src/executor/child/ExecutorRuntime.ts` | 실행 1회: 파일 열기 → 시작 → 코드 → 완료 또는 취소 |
| `Sandbox` | `server/src/executor/child/Sandbox.ts` | SES 정리·동결, compartment 전역 |
| `ServerPluginApi`, `ServerContext` | `server/src/executor/child/` | `penpot`, `penpotMgmt`; UI 전용 member 응답 |
| `HeadlessEngine` | `server/src/executor/child/HeadlessEngine.ts` | `:executor` 빌드의 export를 type이 있는 호출로 감싼다 |
| `app.executor.api` | `frontend/src/app/executor/api.cljs` | 아래 §3의 cljs interface |
| `app.executor.session` | `frontend/src/app/executor/session.cljs` | 프로필·팀·작업 공간·페이지 초기화, headless 라우터, 저장·폐기 |

## 3. Interface

### MCP server → 실행기 프로세스 (IPC, `ExecutorProtocol.ts`)

| 요청 | 인자 | 응답 |
|---|---|---|
| `init` | `token`(사용자 MCP token), `sharedKey` | `ExecutorStatus` |
| `execute` | `ExecuteParams`: `code`, `fileId?`, `pageId?`, `settleTimeoutMs?` | `ExecutionResult` |
| `status` | — | `ExecutorStatus` |

실패는 `{code, message, saved}`다. `code`는 `03` §7의 오류 코드다. token은 환경 변수가 아니라 `init` 요청으로만 건넨다.

### 실행기 프로세스 → frontend 빌드 (`app.executor.api` export)

| 함수 | 의미 |
|---|---|
| `boot({token, sharedKey, wasmDir})` | render-wasm headless 부팅, 인증 설정, 프로필 읽기, router·persistence 시작 |
| `context()` | MCP 플러그인 id로 만든 plugin context (plugins-runtime이 받는 것과 같다) |
| `openFile(fileId, pageId?)` | `penpotMgmt.openFile`과 같은 경로로 연다 |
| `beginExecution()` | 자동 저장을 멈추고(`dps/autosave-held?`) 바뀐 도형 id 기록을 시작한다 |
| `finishExecution({settleTimeout})` | 레이아웃·텍스트 작업이 끝나길 기다리고, 위치 데이터를 바로 계산해 한 번의 `update-file`로 저장한다. `CommitReport`를 돌려준다 |
| `abortExecution()` | 쌓인 변경을 버리고(`::dps/discard-buffered`) 파일을 다시 읽는다 |
| `status()` | 파일·페이지·revn·편집 권한 |

### 결과 envelope (`03` §3)

```json
{"result": …, "log": "…",
 "commit": {"saved": true, "fileId": "…", "revnBefore": 0, "revn": 1,
            "changedShapeIds": ["…"], "lagged": 0,
            "computed": {"layout": true, "text": true, "bool": true, "componentSync": true},
            "pending": null},
 "engine": {"frontendVersion": "…", "renderWasm": null}}
```

- `revn`은 저장 뒤 backend의 revn이다. backend `update-file`은 저장 직전 revn을 돌려주고 frontend는 그 값을 그대로 둔다. 그래서 보고는 그 값 + 1이다.
- `computed`가 false면 `pending`에 아직 끝나지 않은 작업을 도형 id별로 적는다(`settleTimeout` 초과).
- 아무것도 바꾸지 않은 실행은 `commit`이 `null`이다.

## 4. 실행 1회의 순서

1. `fileId`가 있으면 연다. 없으면 세션이 마지막으로 연 파일을 쓴다.
2. `penpot.flags`의 `naturalChildOrdering`, `throwValidationErrors`를 켠다(현재 MCP 플러그인과 같다).
3. `beginExecution` — 자동 저장(3초 debounce)을 멈춘다. 실행이 길어도 중간 상태가 저장되지 않는다.
4. 새 compartment에서 코드를 실행한다. 전역: `penpot`, `penpotMgmt`, `penpotUtils`, `storage`, `console`, 그리고 브라우저 플러그인 sandbox와 같은 내장 객체. `fetch`, 모듈, 파일 시스템, `process`는 없다.
5. 성공: `finishExecution` → 한 번 저장 → envelope. 실패: `abortExecution` → 아무것도 저장하지 않고 파일을 다시 읽는다 → 오류 코드.
6. 저장이 거부되면(권한 등) 5의 실패와 같이 처리한다.

## 5. 세션·격리 (D12)

- 세션 키: (사용자 token 지문, `sessionId` 인자, 기본값 `default`). 세션마다 프로세스 하나다.
- 한 세션의 실행은 차례로 돈다. `storage`, 열린 파일, `penpot.localStorage`(메모리)가 세션 동안 남는다.
- MCP server의 비밀 값과 다른 사용자의 token은 프로세스에 없다. 환경 변수는 경로·URI·flag만 준다.
- 프로세스가 끝나면(시간 초과, 메모리 초과, 유휴 정리) 그 세션 상태는 사라진다. 다음 호출은 새 프로세스로 시작한다.
- 다른 MCP server 인스턴스로 간 요청은 그 인스턴스에서 새 세션을 연다. 인스턴스 사이 라우팅은 PEN-21에서 정한다.

## 6. 자원 제한·로그 (D9) — 측정값

| 항목 | 값 | 근거 |
|---|---|---|
| 실행 시간 | 120초 (`PENPOT_MCP_EXECUTOR_TIMEOUT_S`) | D9. 넘으면 프로세스를 끄고 `resource-limit`, 저장 없음 |
| 힙 | **512 MB** (`PENPOT_MCP_EXECUTOR_HEAP_MB`) | D9는 256 MB를 '측정해 조정'으로 정했다. 도형 1개 파일에서도 V8 힙을 release 빌드 285 MB, 개발 빌드 350 MB 썼다. 256 MB에서는 GC가 계속 돌다 실제 파일에서 넘친다 |
| render-wasm 메모리 | 초기 256 MB, 힙 밖 | `external` 약 330–350 MB |
| 프로세스 RSS | 약 0.5–0.7 GB | 측정 |
| 동시 실행 | 사용자당 2, 전체 CPU 수 | D9. 넘으면 `resource-limit` |
| 유휴 세션 | 15분 뒤 종료 | `PENPOT_MCP_EXECUTOR_IDLE_S` |
| 첫 호출(프로세스 시작) | 약 4–5초 | PEN-3 측정 |
| 이어지는 호출 | 0.04–0.1초 (사각형 1개) | PEN-3 측정 |

로그 한 줄: 사용자 token 지문, 세션, 파일 id, 소요 시간, 바뀐 도형 수, 결과 코드. 코드·결과·token은 남기지 않는다. 예상하지 못한 엔진 오류는 stack만 남긴다.

## 7. UI 전용 member (D8) — 현재 상태

| member | 지금 | 남은 일 |
|---|---|---|
| `penpot.ui.*`, `closePlugin()` | `ui-only` | — |
| `openViewer()`, `openPage(page, true)` | `ui-only` | — |
| `openPage(page)` | 세션의 현재 페이지를 바꾼다 | 따라가기 탭 이동은 PEN-24 |
| `selection` | 세션 상태(frontend store) | 따라가기 탭 표시는 PEN-24 |
| `viewport` 읽기·쓰기 | `ui-only` | 같은 사용자의 열린 브라우저 관찰(b), 따라가기(f)는 PEN-24 |
| `theme` | `"light"` | 열린 브라우저 관찰(b)은 PEN-24 |
| `localStorage` | 세션 동안 남는 메모리 저장소 | — |

## 8. 사용 방법

- MCP server 환경 변수: `PENPOT_MCP_EXECUTOR=server`(기본이 서버 실행) 또는 `optional`(기본은 브라우저 플러그인, 연결 URL `?executor=server`로 선택). 나머지는 `ExecutorConfig.ts` 머리말.
- 빌드: frontend `./scripts/build-executor [compile|release]`(render-wasm frontend 빌드와 번역 파일이 먼저 있어야 한다), mcp `pnpm run build`(`dist/executor-child.js` 포함).
- 검증 스택은 `optional`로 띄운다. 같은 MCP server에서 브라우저 경로와 서버 경로를 비교할 수 있다(`verification-env.md`).

## 9. 티켓별 확인 결과

`05-results.md`에 모았다.

## 10. 브라우저와 다르게 처리한 곳

| 곳 | 브라우저 | 실행기 | 이유 |
|---|---|---|---|
| 파일·페이지 열기 | URL 이동 → 작업 공간 화면이 초기화 이벤트를 보낸다 | headless 라우터가 같은 이벤트를 보낸다 | 화면이 없다 |
| 도형을 엔진에 올리기 | `initialize-viewport` | `_init_shapes_pool` + `set-objects-callback` | 화면 설정(`_set_view`)에 렌더 상태가 필요하다 |
| "타일 렌더 완료" 대기 | WASM이 알린다 | 바로 끝난 것으로 본다(`wasm/headless?`) | 그릴 화면이 없다 |
| 저장 시점 | 3초 debounce 자동 저장 | 실행 끝에 한 번 | `03` §3 |
| 위치 데이터(text) | 마지막 변경 1초 뒤 | 저장 직전에 바로(`dw/flush-position-data`) | 같은 요청에 넣는다 |
| renderer | 프로필 설정(기본 `:svg`) | 항상 wasm | D10, D13 |
