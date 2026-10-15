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
| `ResultStore` | `server/src/executor/ResultStore.ts` | 1 MB를 넘는 결과를 15분 보관하고 주인만 받는 URL(`GET /results/:id`)을 준다(`03` §5). Redis가 있으면 Redis에 둔다 |
| `ExecutionJobs` | `server/src/executor/ExecutionJobs.ts` | `async: true` 실행(job)의 상태·결과·취소. 시작한 사용자만 본다 |
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
| `execute` | `ExecuteParams`: `code`, `fileId?`, `pageId?`, `settleTimeoutMs?`, `ifUnchangedSinceRevn?`, `history?`(`"undo"`/`"redo"`: 코드 대신 실행 취소·다시 실행) | `ExecutionResult` |
| `status` | — | `ExecutorStatus` |
| `cancel` | — | 코드 실행 중이면 `true`(그 실행은 `cancelled`로 끝남), 저장 중이면 `false` |

실패는 `{code, message, saved}`다. `code`는 `03` §7의 오류 코드다. `saved`는 `false`, `true`, 또는 저장 중에 프로세스가 끝나 저장이 반영됐는지 모를 때 `"unknown"`이다. token은 환경 변수가 아니라 `init` 요청으로만 건넨다.

실행기는 저장 요청을 보내기 전에 응답과 별개로 `{notice: "saving", save: {fileId, revnBefore, sessionId}}`를 보내고, MCP server가 `{ack: "saving"}`으로 답한 뒤(최대 10초) 저장한다. MCP server는 그 사이 `requestId` 기록에 저장을 찾을 단서를 남긴다. backend는 변경마다 저장한 세션을 기록하므로(`get-file-changes`) 응답이 사라져도 저장 여부를 나중에 알 수 있다(PEN-20). 저장 알림 뒤에 프로세스가 끝나면(시간 초과, 메모리, 종료 신호) MCP server는 "저장 없음" 대신 `saved: "unknown"`으로 답한다. 저장 중에 받은 종료 신호는 저장의 응답을 보낸 뒤에 따른다. 그 밖의 때에는 신호를 받는 즉시 끝난다(저장 전 취소).

### 같은 `requestId`의 재시도와 결과 조회 (D5, PEN-20)

`RequestLedger`가 (사용자, `requestId`)마다 진행 중인 실행(실행하는 MCP server 인스턴스, 저장 단서)이나 결과를 10분 둔다. 인스턴스는 15초 수명의 생존 기록을 5초마다 갱신한다(Redis). 재시도와 `request_status` 도구는 다음처럼 판단한다.

| 기록 | 판단 |
|---|---|
| 결과 있음 | 그 결과(`replayed: true`) |
| 진행 중, 그 인스턴스가 살아 있음 | 아직 실행 중(`precondition-failed`, 나중에 같은 ID로 재시도) |
| 진행 중, 인스턴스가 죽음, 저장 전 | 저장 없음: 재시도는 다시 실행한다(실행기는 MCP server와 함께 끝나 저장을 보낼 수 없다) |
| 진행 중, 인스턴스가 죽음, 저장 시작함 | backend의 변경 기록에 그 실행기 세션의 저장이 있으면 저장됨: 재시도는 그 revn을 담은 commit을 `result-lost` 경고와 함께 돌려준다(코드의 반환값은 남지 않는다). 없으면 저장 30초 뒤부터 저장 없음으로 본다. 기록이 지워졌으면 모름(`precondition-failed`, 파일을 읽고 새 ID로) |

정상 종료한 인스턴스는 생존 기록을 바로 지운다.

### 실행 취소 (PEN-20, D6)

- `undo` 도구(`sessionId`, `redo`, `fileId`, `pageId`, `requestId`)가 그 세션에서 저장한 마지막 실행 하나를 되돌리거나, 되돌린 것을 다시 적용한다. 결과는 실행과 같은 envelope이고 `result`는 `{undone|redone: 적용한 변경 수, canUndo, canRedo}`다.
- 실행 1회가 한 단계다. 브라우저의 실행 취소처럼 그 실행의 커밋 가운데 실행 취소에 넣는 것(`save-undo?`)의 undo 변경을 역순으로 저장하고, 레이아웃·텍스트 같은 파생 값은 실행처럼 다시 계산해 함께 저장한다. 실행 안의 `history.undoBlockBegin/Finish`는 단계를 나누지 않는다.
- 단계는 파일별로 세션이 살아 있는 동안 50개까지 둔다(브라우저와 같은 상한). 새 실행은 다시 실행할 단계를 지운다.
- 다른 사람의 작업을 덮지 않는다: 저장한 뒤 다른 세션(사람의 탭, 같은 사용자의 다른 세션 포함)이 그 단계가 바꾼 도형·페이지·라이브러리 자산·토큰·guide·flow를 바꿨으면 `precondition-failed`로 거부하고 아무것도 저장하지 않는다. 메시지에 그 대상을 적는다. 판단은 backend의 변경 기록(`get-file-changes`)으로 하므로 놓친 알림이나 파일을 다시 연 것과 상관없다. 기록이 지워졌거나 파일이 버전 복원됐으면 확인할 수 없어 거부한다. 확인과 저장 사이의 변경은 `ifUnchangedSinceRevn`과 같은 확인으로 막는다.
- 실행 밖에서 바로 저장되는 것(댓글, 파일·프로젝트 만들기 같은 파일 밖 작업)은 되돌리지 않는다.

### 실행기 프로세스 → frontend 빌드 (`app.executor.api` export)

| 함수 | 의미 |
|---|---|
| `boot({token, sharedKey, wasmDir})` | render-wasm headless 부팅, 인증 설정, 프로필 읽기, router·persistence 시작 |
| `context()` | MCP 플러그인 id로 만든 plugin context (plugins-runtime이 받는 것과 같다) |
| `openFile(fileId, pageId?)` | `penpotMgmt.openFile`과 같은 경로로 연다 |
| `observedScreen()` | 같은 사용자가 이 파일을 연 브라우저 탭의 화면(`pageId`, `zoom`, `vbox`, `theme`). 없으면 null (D8 (b)) |
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
- 저장된 실행은 파생 값 계산을 모두 끝낸 것이다(`computed`가 모두 true, `pending`은 null). 계산이 `settleTimeout`(기본 10초) 안에 끝나지 않으면 저장하지 않고 `resource-limit`으로 실패하며, 메시지에 남은 작업을 도형 id별로 적는다(`03` §3, PEN-13).
- 아무것도 바꾸지 않은 실행은 `commit`이 `null`이다.

### `execute_code` 도구 인자 (서버 실행일 때)

| 인자 | 의미 |
|---|---|
| `fileId`, `pageId` | 실행 전에 열 파일·페이지 |
| `sessionId` | 실행기 세션 이름(기본 `default`) |
| `requestId` | D5: 같은 ID의 재시도는 10분 동안 첫 결과를 `replayed: true`로 돌려준다 |
| `ifUnchangedSinceRevn` | D4: 파일이 그 revn 뒤로 바뀌었으면 실행·저장하지 않고 `precondition-failed`. 시작할 때와 저장 직전에 확인한다 |
| `async` | `true`면 바로 job을 돌려주고 뒤에서 실행한다. `execution_job` 도구(`jobId`, `cancel`)로 상태·결과를 읽거나 취소한다 |

결과 값이 `Uint8Array`이면 1 MB까지는 base64 envelope(`{"__type":"base64","data":…}`)로, 그보다 크면 `{"__type":"resource", url, size, mtype, expiresAt}`로 돌려준다. URL은 같은 MCP token(`Authorization: Token …` 또는 `?userToken=`)으로만 받을 수 있다. `export_shape`도 서버 실행 연결에서는 같은 실행기 세션에서 내보낸다(`fileId`, `pageId` 인자).

클라이언트가 요청을 취소하거나 연결을 끊으면 실행기에 취소를 보낸다(D6).

MCP server가 멈출 때(`SIGINT`/`SIGTERM`)는 연결을 닫기 전에 실행기부터 정리한다. 진행 중인 실행에 취소를 보내고 3초까지 기다린 뒤(저장 중이면 저장을 마친다) 프로세스를 끝낸다. 요청 ID 기록이 정리된 다음에 기록 저장소(Redis)를 닫는다.

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
- 다른 MCP server 인스턴스로 간 요청은 그 인스턴스에서 새 세션을 연다. 인스턴스 사이 라우팅은 PEN-21에서 정한다. `requestId` 기록은 Redis로 인스턴스끼리 공유한다.
- 세션은 알림 WebSocket으로 다른 사람의 변경을 받아 열린 파일을 최신으로 둔다. 연결이 끊겼다 붙으면 놓친 변경을 `get-file-changes`로 받는다(브라우저와 같은 코드).

## 6. 자원 제한·로그 (D9) — 측정값

| 항목 | 값 | 근거 |
|---|---|---|
| 실행 시간 | 120초 (`PENPOT_MCP_EXECUTOR_TIMEOUT_S`) | D9. 넘으면 프로세스를 끄고 `resource-limit`, 저장 없음 |
| 힙 | **512 MB** (`PENPOT_MCP_EXECUTOR_HEAP_MB`) | D9는 256 MB를 '측정해 조정'으로 정했다. 도형 1개 파일에서도 V8 힙을 release 빌드 285 MB, 개발 빌드 350 MB 썼다. 256 MB에서는 GC가 계속 돌다 실제 파일에서 넘친다 |
| render-wasm 메모리 | 초기 256 MB, 힙 밖 | `external` 약 330–350 MB |
| 프로세스 RSS | 약 0.5–0.7 GB | 측정 |
| 동시 실행 | 사용자당 2, 전체 CPU 수 | D9. 넘으면 `resource-limit` |
| 유휴 세션 | 15분 뒤 종료 | `PENPOT_MCP_EXECUTOR_IDLE_S` |
| 살아 있는 세션(프로세스) 수 | 사용자당 4, 전체는 메모리 1GB당 1 | `PENPOT_MCP_EXECUTOR_SESSIONS_PER_USER`, `PENPOT_MCP_EXECUTOR_SESSIONS_MAX`. 넘으면 가장 오래 쉰 유휴 세션을 닫는다(그 세션의 `storage`와 열린 파일은 사라진다). 모두 실행 중이면 `resource-limit`. PEN-13 시험 중 세션 16개(약 13GB)가 쌓여 backend가 메모리 부족으로 죽은 뒤 넣었다 |
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
| `viewport` 읽기 | 같은 사용자가 이 파일을 연 브라우저 탭의 화면(b). 없으면 `ui-only` | — |
| `viewport` 쓰기, `zoomReset/zoomToFitAll/zoomIntoView` | `ui-only` | 따라가기(f)는 PEN-24 |
| `theme` | 같은 탭의 테마(b). 없으면 `"light"` | — |
| `penpot.on` 이벤트 | 세션이 끝날 때까지 유지(브라우저 플러그인은 닫힐 때까지). 세션의 변경과 다른 사람이 저장한 변경을 모두 듣는다 | — |
| `localStorage` | 세션 동안 남는 메모리 저장소 | — |

브라우저 탭의 화면은 기존 presence 메시지(`:pointer-update`)로 받는다. 탭은 포인터를 움직일 때 말고도 화면 위치·배율·테마가 바뀔 때와 다른 세션이 파일에 들어올 때 그 메시지를 보낸다. 실행기는 화면이 없으므로 보내지 않는다. 같은 사용자의 탭이 여럿이면 세션의 현재 페이지를 보는 탭 중 마지막으로 알린 탭을 쓴다.

AI 클라이언트 안내: 서버 실행 연결에서는 `high_level_overview`가 플러그인 연결 전제를 빼고 'Server-Side Execution' 절(`data/server_execution_instructions.md`)을 붙인다. `penpot_api_info`는 서버에서 의미가 다른 member(`ServerExecutionGuide.ts`)에 설명을 덧붙인다.

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
| 파일을 열고 코드 실행 | 사람이 조작하기 전에 라이브러리가 보통 다 들어와 있다 | 연결된 라이브러리 내용을 다 받은 뒤 코드를 돌린다(`all-libraries-resolved`) | 열자마자 코드를 돌린다 |
| 번역 | 프로필 언어, 없으면 브라우저 언어 | 프로필 언어, 없으면 영어 | 브라우저 언어가 없다 |
| npm CommonJS 패키지 | 번들러가 묶는다 | Node ESM `import` + 모듈 훅이 이름 붙은 내보내기를 만든다(`CjsInterop.ts`) | `sax` 같은 패키지는 Node가 내보내기를 찾지 못한다 |
| 이미지 불러오기 | 브라우저가 디코딩해 WebGL texture로 넘긴다 | 바이트를 그대로 넘겨 Skia가 디코딩한다(headless exporter와 같다) | 디코더와 WebGL이 없다 |
| 도형 래스터 export | GPU 화면에 그려 읽는다(`_render_shape_pixels`) | CPU에 그린다(`_render_shape_raster_extended`, 같은 영역·같은 그리기 코드) | GPU가 없다 |
| 주소 | 화면 주소가 곧 backend 주소 | 내보내는 링크(SVG의 이미지·폰트, viewer URL)는 사용자가 여는 주소(`PENPOT_MCP_EXECUTOR_UI_URI`, 없으면 `PENPOT_PUBLIC_URI`)로 만들고, 그 주소로 가는 요청은 실행기가 닿는 backend 주소(`PENPOT_MCP_EXECUTOR_PUBLIC_URI`)로 보낸다 | 실행기는 내부 주소로 backend에 닿는다 |
