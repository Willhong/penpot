# 통합 검증 (PEN-9)

PEN-22에서 만든 서버 MCP 전체를 한 빌드로 시험했다. 기능별 동등성, 열린 브라우저 반영, 복구, 사용자 결정 D1–D16을 다시 확인했다. 기능 목록의 member를 실제 실행 증거에 연결했다.

## 빌드와 환경

- 최종 확인 커밋: `f5ff7d76f` (브랜치 `bb/pen-22-mcp-thr_shfqb6s93e`). 그 뒤 커밋은 테스트만 더한 `d0e07ed49`와 이 문서다.
- 검증 스택(`verification-env.md`)을 PEN-9 시작 커밋에서 새로 띄웠다. 시험 중 고친 코드는 그때마다 다시 빌드하고 재시작했다. 최종 회귀 보고에는 커밋, 작업 폴더 상태(깨끗함), 브라우저·실행기 번들 빌드 시각이 함께 남는다.
- 관찰 브라우저는 macOS의 ego-browser 탭이다(p1 owner, p2·p3 editor). 서버 실행기는 Docker 컨테이너 안의 Node 프로세스다. 두 곳은 서로 다른 머신에서 돈다.
- 판정: 각 시험 스크립트가 JSON 보고와 종료 코드를 낸다. 실행하지 못한 항목은 통과로 세지 않는다.

## 도구

| 도구 | 하는 일 |
|---|---|
| `experiments/pen9_regression.py` | PEN-3~24 시험 18개와 PEN-9 시험 2개를 같은 빌드로 차례로 돌리고 보고를 모은다 |
| `experiments/pen9_integrated.py` + `.js` | 기능을 엮은 시나리오, 브라우저 0개 실행, 복구·지연(D7)·presence(D3)·renderer(D13) |
| `experiments/pen9_gaps.py` + `pen9_gaps_*.js` | 다른 시험이 서버에서 쓰지 않은 Plugin API member를 실행한다 |
| `experiments/pen9_coverage.py` | 실행기가 실제로 읽고 쓰고 부른 member를 기록하고(`PENPOT_EXECUTOR_TRACE_API=1`, `executor/child/ApiTrace.ts`) 기능 목록과 맞춘다 |

## 결과 요약

| 완료 기준 (PEN-9) | 결과 |
|---|---|
| 실행 서비스에 브라우저 0개로 복합 디자인 제작·수정·조회·내보내기·취소 | 통과. 0.5초 간격 10회 표본 동안 컨테이너에 브라우저 프로세스 0개, 실행기 프로세스 최대 4개. 기존 플러그인 경로는 "연결된 세션 없음"으로 실패해 쓰이지 않았음을 보였다. 되돌리기 뒤 저장 상태가 바꾸기 전과 같다 |
| 두 브라우저 실시간 반영, 늦게 열기·재연결·새로고침·서버 재시작 뒤 일치 | 통과. 탭 두 개가 가진 도형(위치·크기·채우기·글자·컴포넌트 연결)이 backend 저장값과 같다 |
| 교차 기능 결과를 같은 입력·폰트로 원본과 비교 | 통과(문자열 비교 1건 결정 대기). 반환값·저장 도형 27개·라이브러리 자산이 같다. PNG는 브라우저 CPU export와 0.07% 차이(기준 0.1%), PDF는 그린 결과 0.08% 차이와 같은 글자. SVG·HTML 문자열은 아래 결정 대기 |
| 동시 편집·중복·응답 유실·취소·권한 회수·부분 실패·자원 초과 | 통과. 7가지 모두 저장 상태가 기대와 같다 |
| 기능별 결과·수치·화면·로그, 기존 MCP·편집기 회귀와 모듈 테스트 | 회귀 20개 중 18개 통과, 2개는 결정 대기 항목만 실패. 브라우저 플러그인 MCP 경로 통과. frontend 1,371, MCP 서버 121, 실행기 통합, backend 웹소켓 테스트 통과 |
| 모든 구현 기능의 검증 | 동작 member 530/530개와 값 객체 175/181개가 서버에서 실행됐다. 실행할 수 없는 11개는 이유와 함께 따로 셌다(권한·타입 선언 불일치·정상 파일에서 생기지 않는 오류 객체) |

## 회귀 (같은 빌드, `f5ff7d76f`)

| 시험 | 결과 | 시간 |
|---|---|---:|
| e1, PEN-3, 4, 5, 6, 6-shutdown, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 24 | 통과 | 1–176초 |
| PEN-19 | 이미지·PDF·SVG export와 HTML·CSS 코드 통과. SVG 마크업 코드 생성만 결정 대기 항목으로 실패 | 50초 |
| pen9-integrated | 13단계 중 12단계 통과. `textExports`만 결정 대기 항목으로 실패 | 304초 |
| pen9-gaps | 10단계 통과 | 121초 |

`pen6-shutdown`은 중간 회차에서 Ctrl-C 재시작 중 응답 하나를 잃은 적이 있다(12회 중 1회, `verification-env.md`). 개발용 pnpm 래퍼 문제이고 운영 이미지에는 없다. 최종 회귀에서는 통과했다.

## 통합 시험 (`pen9_integrated.py`)

| 단계 | 확인 | 결과 |
|---|---|---|
| crossFeature | token·라이브러리 색·타이포그래피가 꾸민 variant 컴포넌트, 중첩 flex·grid 안 텍스트(영문·한글), 이미지 채우기, Boolean, 프로토타입 연결을 만들고 token 값·main 라벨·variant를 바꾼다. 브라우저(wasm)와 서버에서 같은 코드 | 반환값·저장 도형 27개·라이브러리 같음. 서버 저장 변경 495개. 관찰 탭에 새로고침 없이 0.6초 |
| pluginPath | 편집 화면 MCP 메뉴로 플러그인 연결 → `executor=plugin` 실행 → 같은 파일에 서버 실행 | 0.1초 안에 연결, 두 경로의 저장이 0.9초 안에 모두 남음, 해제 뒤 플러그인 경로 실패 |
| browserless | 탭을 모두 비우고 만들기(변경 497개)·바꾸기·읽기·내보내기(PNG 320×330, PDF)·되돌리기 | 통과, 위 요약 참조 |
| lateOpen / live / reconnect / refresh / mcpRestart | 늦게 연 탭, 열린 채 AI 편집(token 값·variant 전환), 알림 연결 끊김 중 저장 2회, 새로고침, MCP 서버 정상 종료 뒤 새 세션 | 모두 backend와 같음(재연결 0.9초 안) |
| aiPresence (D3) | owner 탭의 사용자 목록 | "AI (MCPV Editor)"가 AI 표시와 함께 사람 owner와 따로 나온다 ([화면](../../../.mcp-verify/shots/pen9-ai-presence.png)) |
| latency (D7) | 저장 응답부터 두 탭에 보일 때까지 | 단일 저장 20회(표본 40) p95 0.096초(기준 1초), 도형 1,000개 저장 5회(표본 10) p95 1.55초(기준 3초) |
| robustness | 같은 `requestId` 두 번, 읽지 않은 응답 뒤 재시도, 실행 중 job 취소, 실행 중 편집 권한 회수, 교차 기능 변경 뒤 예외, 사각형 3,000개(변경 6,000개), 사람의 동시 편집 | 사본 1개, 사본 1개, `cancelled`·저장 없음, `not-found`·저장 없음, 저장 없음, `resource-limit`·저장 없음, 두 변경 모두 남음 |
| svgRenderer (D13) | owner 탭을 svg renderer로 바꿔 파일 열기 | 텍스트 9개 크기 그대로, revn 그대로 |
| textExports | 카드의 SVG export, HTML·CSS 코드 문자열 | CSS 같음. SVG·HTML은 결정 대기 항목 |

## 보충 시험 (`pen9_gaps.py`)

| 단계 | 확인 |
|---|---|
| core (브라우저 비교) | 루트, 플래그 두 개와 그 효과, Group·Boolean의 `appendChild`/`insertChild`, `parentIndex`, `boardX/Y`, path `content`와 명령(호 매개변수 포함), Boolean의 `content`/`d`/`commands`, 글꼴 찾기와 Font·FontVariant 필드, `textBounds`, TextRange 7가지, 타이포그래피 적용(텍스트·범위), grid `dir`·트랙 삽입·변경·셀 이름, 자식 margin·minHeight, 도형별 `waitForLayoutUpdate`, 보드·페이지 ruler guide 삭제, column guide `itemLength`, Flow `page`/`remove`, Interaction `shape`, overlay `relativeTo`/위치, `removeInteraction` |
| assets (브라우저 비교) | `createVariantFromComponents`, variant `addVariant`/`variantError`/`removeProperty`/id, 컴포넌트 head·root·ref, 라이브러리 이름·`libraryId`, 이미지 라이브러리 색, `ImageData.data()`, `shapesColors` 값 객체, `availableLibraries` 요약, token 17종의 `type`/`value`/`resolvedValue`(그림자·타이포그래피 값 객체 포함), token·set·theme의 id·복제·삭제, `getSetById`/`getThemeById`/`getTokenById`/`tokensByType`, `applyToken` |
| comments (브라우저 비교) | 댓글 `date`, 답글 삭제, `removeCommentThread` |
| imageShape | Plugin API로 만들 수 없는 옛 `image` 도형을 backend로 넣고 읽기·채우기 변경 (브라우저와 같음) |
| users | `currentUser`(토큰 주인), `activeUsers`(owner 탭의 배율·포인터 위치) |
| uiOnly | `ui.size` 읽기·쓰기, `resize`, `sendMessage`, `onMessage` 모두 `ui-only` (D8) |
| utils | `utils.types` 10가지와 `geometry.center`가 도형의 답과 같음 |
| events | 9가지 이벤트 구독·해제, `penpotMgmt.on/off`, 선택 변경 이벤트, 다른 세션 저장이 `shapechange`로 옴. `addListener`/`removeListener`/`management`는 `Penpot`에 없음(타입 선언과 같음) |
| context | `penpot.version`이 같은 빌드의 브라우저와 같음. `localStorage`는 권한 없음으로 거부(브라우저 MCP와 같음) |
| applyToSelected | 세션 선택에 token 적용, 저장됨 (D8) |

`utils`, 이벤트, `version`, `localStorage`는 플러그인 런타임 계층이 붙이는 member라, 런타임을 거치지 않는 브라우저 비교 도구로는 비교할 수 없다. 그래서 서버에서 도형의 답이나 같은 빌드 브라우저의 값과 비교했다.

## 사용자 결정 점검

| 결정 | 확인 | 근거 |
|---|---|---|
| D1 코드 호환 + 기존 도구 유지 | `execute_code`·`export_shape`·`execution_job`·`undo`·`request_status`·`high_level_overview`·`penpot_api_info`가 서버 경로에서 실행됨 | 추적 기록의 도구 목록 |
| D2 MCP token만 | 일반 API token·잘못된 token은 `forbidden` | PEN-3 |
| D3 AI 구분 표시 | presence에 "AI (이름)", audit log에 `access-token-type: mcp`·`client-user-agent: node` | aiPresence, audit_log |
| D4 나중 저장 우선 + 선택적 사전 조건 | PEN-6, robustness의 동시 편집 | |
| D5 `requestId` 10분 | 중복·응답 유실 재시도 모두 사본 1개 | PEN-6, PEN-20, robustness |
| D6 저장 전 취소만 | 취소한 job은 저장 없음, 저장 뒤는 `undo` | PEN-20, robustness |
| D7 p95 1초 / 3초 | 0.096초 / 1.55초 | latency |
| D8 UI 전용 member | `ui-only`, 관찰, 서버 선택, 따라가기 | PEN-10, PEN-24, gaps |
| D9 제한·로그 | 시간·힙·변경 5,000개·사용자당 동시 2개·전체 최대, 로그 형식 | 실행기 통합 테스트, pool 테스트, robustness, MCP 로그 |
| D10 Chromium 없음 | 실행 중 브라우저 프로세스 0개 | browserless |
| D11 공유 키와 함께일 때만 MCP token | backend 테스트, PEN-3 | |
| D12 (사용자, 세션)마다 프로세스 | storage 격리, 동시 사용자 | 실행기 통합 테스트 |
| D13 wasm 기준 | svg renderer 탭도 크기 그대로 | svgRenderer |
| D14 실행기 안에서 그림 | exporter 로그에 내보내기 요청 없음 | exporter.log |
| D15 CPU 래스터 기준 | PNG 0.07%, PDF 0.08% | crossFeature, PEN-19 |
| D16 따라가기 | PEN-24 회귀 통과 | |

## 기능 목록과 실행 증거 (PEN-1 대응표)

`pen9_coverage.py`로 최종 추적 회귀(`f5ff7d76f`, 시험 20개)와 고친 보충 시험 한 번을 기록했다. 실행기가 사용자 코드의 API 접근을 감싸 `<종류>.<member>`로 남기고, proxy 이름과 타입 선언의 member 타입·상속을 따라 기능 목록 716개와 맞춘다. 추적 회차는 실행이 느려 지연 시험(D7)의 1,000개 묶음 표본 2개가 관찰 시간을 넘겼다. 지연과 판정은 추적을 끈 최종 회귀 값으로 한다.

- 동작 member: 서버에서 실행된 것 530/530개.
- 값 객체: 175/181개.
- 어떤 경로로도 실행할 수 없어 이유를 붙여 따로 센 것: 11개.
- MCP 도구: 서버 경로에서 `execute_code`, `high_level_overview`, `penpot_api_info`, `export_shape`, `execution_job`, `undo`, `request_status`가 실행됐다. `import_image`, `import_penpot_file`, `cljs_repl`, `cljs_compiler_output`, `clj_check_parentheses`, `read_taiga_issue`는 서버 MCP(multi-user)에 없는 도구다. `import_image`는 로컬 모드 전용이고(PEN-16), 나머지는 devenv 단일 사용자용 개발 도구다.

| 영역 | 담당 | 동작 member 실행 | 값 객체 실행 | 실행할 수 없음 |
|---|---|---:|---:|---:|
| 파일 메타데이터·버전·검증 (`file`) | PEN-4 | 15/15 | 0/0 | 4 |
| 프로젝트·파일 관리 (`filemgmt`) | PEN-4 | 7/7 | 14/14 |  |
| 페이지 관리 (`page`) | PEN-4 | 5/5 | 0/0 |  |
| 도형 조회 (`query`) | PEN-5 | 4/4 | 6/6 |  |
| 기본 도형 속성·생성·삭제 (`shape`) | PEN-5 | 45/45 | 44/44 |  |
| 이벤트 구독 (`events`) | PEN-10 | 15/15 | 0/0 |  |
| 실행 플래그 (`flags`) | PEN-10 | 3/3 | 0/0 |  |
| 실행 컨텍스트·루트 객체 (`runtime`) | PEN-10 | 15/15 | 0/0 |  |
| 플러그인 localStorage·MCP storage (`storage`) | PEN-10 | 0/0 | 0/0 | 5 |
| 브라우저 UI 전용(선택·뷰포트·테마·플러그인 창) (`ui`) | PEN-10 | 21/21 | 0/0 |  |
| 현재 사용자·접속 사용자 (`users`) | PEN-10 | 7/7 | 0/0 |  |
| 계층·변환·정렬 (`hierarchy`) | PEN-11 | 33/33 | 0/0 |  |
| 패스·Boolean·마스크·flatten (`path`) | PEN-11 | 31/31 | 0/0 |  |
| 텍스트·폰트·부분 스타일 (`text`) | PEN-12 | 52/52 | 4/4 |  |
| Flex·Grid 레이아웃 (`layout`) | PEN-13 | 57/57 | 8/8 |  |
| 컴포넌트·인스턴스·Variants (`components`) | PEN-14 | 40/40 | 0/0 |  |
| 라이브러리 자산·연결 (`library`) | PEN-15 | 35/35 | 19/19 |  |
| 디자인 토큰 (`tokens`) | PEN-15 | 89/89 | 24/24 | 2 |
| 이미지·SVG (`media`) | PEN-16 | 7/7 | 7/7 |  |
| Flow·상호작용·가이드 (`prototype`) | PEN-17 | 26/26 | 49/49 |  |
| 댓글 (`comments`) | PEN-18 | 15/15 | 0/0 |  |
| 내보내기·코드 생성 (`output`) | PEN-19 | 5/5 | 0/0 |  |
| 작업 단위·실행 취소 (`history`) | PEN-20 | 3/3 | 0/0 |  |

실행할 수 없는 member:
- `Context.localStorage`, `LocalStorage.getItem/setItem/removeItem/getKeys`: MCP 플러그인 manifest에 `allow:localstorage` 권한이 없다. 브라우저 MCP와 서버 모두 `penpot.localStorage`에서 권한 오류로 거부한다(`pen9_gaps.py` `context`에서 확인). 추적기는 값을 돌려준 읽기만 기록하므로 거부된 읽기는 남지 않는다.
- `FileValidationError.code/hint/shapeId/pageId`: 정상 파일에서는 `validate()`가 오류를 내지 않고, 파일 검증이 켜진 backend는 깨진 파일을 저장하지 않는다.
- `TokenTypographyValueString.fontFamilies/fontSizes`: 타입 선언에는 있지만 typography token의 값 객체에는 `fontFamily`·`fontSize`로 들어 있다. 브라우저와 서버가 같다.

member별 결과는 `.mcp-verify/pen9/coverage.json`(`ran`, `notApplicable`)에 있다.

## 예외 목록 (03 §6)

서버와 브라우저가 다르게 내는 것:
- 브라우저 GPU export와의 도형 가장자리 antialiasing 차이(D15).
- SVG 마크업 코드의 `@font-face`(사용자 결정으로 서버 결과 유지).
- PDF 이미지의 ICC profile. 이 때문에 PDF는 그린 결과와 글자로 비교한다.
- 내보낸 링크의 주소와 media id(비교 때 정규화).
- svg renderer 브라우저의 글자 그리기(D13). 크기와 저장은 같다.
- **결정 대기**: SVG export·HTML 코드 문자열의 0.01px 미만 좌표 잔차와 `@font-face` 순서. 같은 잔차가 내보내기 크기의 올림 경계에 걸리면 PNG 크기가 1px 다를 수 있다(추적 회차에서 카드 326px 대 327px, 통합 시험 약 5회 중 1회).

브라우저와 서버가 같지만 타입 선언과 다른 Plugin API 동작(서버 차이 아님, PEN-11·15에서 발견):
- `PathCommand.command`의 짧은 이름(`'M'`, `'L'` 등)과 2차 곡선을 `commands` setter가 받지 않는다.
- `createBoolean`이 도형 하나로도 Boolean을 만든다. `setParentIndex(-1)`, 범위 밖 `insertChild` index는 끝으로 맞춘다.
- 색 token이 `"not a color"` 같은 값을 받는다. 빈 색 이름을 받는다. 맞지 않는 속성에 token을 적용하면 오류 없이 아무것도 하지 않는다.
- (PEN-9) 보드 밖 도형의 `addInteraction("…", { type: "open-overlay", … })`은 오류 없이 저장되지 않고, 돌려받은 상호작용의 `action`이 `null`이다. 보드 안 도형에서는 저장된다.
- (PEN-9) typography token의 값 객체는 선언된 `fontFamilies`·`fontSizes` 대신 `fontFamily`·`fontSize`를 가진다.

## 이 작업에서 고친 결손

| 커밋 | 화면·동작에서 보이던 문제 |
|---|---|
| `86d7e6b38` | D9의 "한 번에 저장하는 변경 5,000개" 제한이 없었다. 사용자 코드가 던진 문구가 MCP 오류 로그에 남았다 |
| `eb248c033` | 서버에서 파일을 열자마자 내보내면 한글이 네모로, 보통 글자가 굵게 나왔다(글꼴을 받은 뒤 다시 배치하지 않음) |
| `aac56eb78` | 브라우저(wasm)에서 텍스트 색만 바꾸면 `waitForLayoutUpdate`가 길게는 60초 기다리다 시간 초과됐다 |
| `c5af56655` | 다른 사람 화면에 AI 세션이 사용자 본인과 똑같이 보였다(D3 미구현) |
| `1bc1b8999` | 서버에서 `penpot.currentUser`/`activeUsers`를 읽으면 `document is not defined`로 실패했다 |
| `1ea8367a3` | `penpot.version`과 결과의 `frontendVersion`이 비어 있었다. `ui.size =`이 `ui-only` 대신 TypeError를 냈다 |
| `c961c0ece` | (시험 도구) 추적 회차가 일반 회차와 다르게 동작했다 |
| `d0e07ed49` | (테스트) D9 동시 실행 제한을 확인하는 테스트가 없었다 |

시험 도구에서 고친 것: PEN-19의 PDF 비교가 stream을 잘못 읽었다. `dual_run`이 경로 문자열 안의 숫자에 반올림 규칙을 적용하지 않았다.

## 남은 것

- **사용자 결정 1건**: SVG export와 HTML 코드 생성 문자열을 비교할 때 숫자를 0.01 안에서 같게 보고 `@font-face` 순서를 무시할지. 아래 "결정 대기" 참고.
- **검증할 수 없음**: `FileValidationError`의 필드 4개. 정상 파일에서는 `validate()`가 오류를 내지 않고, backend가 파일 검증을 켠 채로는 깨진 파일을 저장하지 않는다.
- 범위 밖: PEN-21 배포. 운영 이미지의 `PENPOT_VERSION`·공유 키 설정은 배포 때 확인한다.

### 결정 대기: 텍스트 export 비교 기준

- 영향: SVG export와 HTML 코드 생성 결과에 0.01px보다 작은 좌표 차이(예: `62.000000298` 대 `62.00000036`)가 회차에 따라 나온다. 같은 파일의 `@font-face` 순서도 다를 때가 있다. 화면 결과(PNG·PDF)와 저장 도형은 기준 안에서 같다. 드물게 이 잔차가 PNG 크기를 1px 바꾼 적이 있다(위 예외 목록).
- 선택지:
  - A. 숫자를 0.01 안에서 같게 보고 `@font-face`를 정렬해 비교한다. 도형 데이터의 기준(03 §6)과 같은 허용 오차다. 지금 결과로는 통과한다.
  - B. 문자열을 그대로 비교한다. 출력 코드를 바꿔 좌표를 반올림하고 `@font-face` 순서를 고정해야 한다. 브라우저의 출력도 바뀐다. 내보내기 크기를 정할 때도 잔차를 버리게 해 1px 차이를 없앨 수 있다.
- 추천: A. 1px 크기 차이가 문제가 되면 그 부분만 B처럼 고친다.

## 다시 돌리는 법

```sh
scripts/mcp-verify-env up && scripts/mcp-verify-env wait && scripts/mcp-verify-env seed
python3 -I mcp/docs/server-mcp/experiments/pen9_regression.py --space <ego-browser task space>
python3 -I mcp/docs/server-mcp/experiments/pen9_coverage.py run --space <space>
python3 -I mcp/docs/server-mcp/experiments/pen9_coverage.py report
```
