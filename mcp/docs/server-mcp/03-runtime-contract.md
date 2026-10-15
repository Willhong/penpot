# 서버 런타임·계산·출력 계약 (PEN-8)

입력:
- `01-feature-contract.md`: 기능 범위, 사용자 정책
- `02-browser-dependency-research.md`: 기술 조사, 실험

상태: **기술 계약은 확정했다.** E4(레이아웃·텍스트·boolean)는 2026-10-15에 실증했다. 아래 'blocker'로 표시한 나머지 계산 경로는 실증 전이다. 그 경로를 쓰는 구현은 blocker 실험이 통과해야 완료할 수 있다. D10은 2026-10-15에 사용자가 선택지 1로 확정했다.

## 1. 구성 요소와 경계

```
MCP 클라이언트 ──HTTP(MCP)──▶ mcp server (기존 패키지, 도구 등록·인증·세션)
                                   │ 내부 RPC
                                   ▼
                        실행기 (Node, 별도 프로세스·컨테이너)
                          ├─ Sandbox: 사용자 JS 실행 (execute_code)
                          ├─ DocumentSession: 파일 작업본, penpot.* 서버 구현
                          ├─ Engine: headless render-wasm (계산·출력, D14), cljc (변경 생성)
                          └─ BackendClient: 사용자 token으로 RPC 호출
                                   │ Authorization: Token <사용자 token>
                                   ▼
                        backend (권한·저장·검증·알림)
```

**[기술 결정]**
- 사용자 코드는 backend JVM 안에서 실행하지 않는다. 실행기는 backend와 다른 프로세스에서 돈다. backend에는 원격 코드 실행 경로를 만들지 않는다.
- 실행기가 쓰는 cljs 빌드는 frontend와 같은 `common` 소스와 같은 render-wasm 빌드 산출물을 쓴다. 서로 다른 버전을 섞지 않는다. 배포 단위로 frontend 버전 문자열을 응답에 넣는다.
- mcp server는 지금처럼 도구 등록, 세션, multi-instance 라우팅을 맡는다. 실행 대상만 '브라우저 플러그인'에서 '실행기'로 바꾼다. 기존 플러그인 경로는 PEN-21 공존 기간 동안 남긴다.

### D10 [사용자 결정 · 2026-10-15 확정] '브라우저 없이'의 범위

- 선택지 1 (결정, 경로 A): 서버에서도 Chromium을 쓰지 않는다. 계산은 Node + headless render-wasm으로 하고, 출력도 exporter의 headless wasm 경로만 쓴다. (출력은 D14로 '같은 그리기 코드를 실행기 안에서'로 바뀌었다.)
- 선택지 2: 사용자 브라우저만 없으면 된다. 서버의 headless Chromium(경로 C)을 계산·출력의 보조 경로로 허용한다.
  - 장점: E4가 실패해도 기능을 낼 수 있다.
  - 비용: 세션당 수백 MB, 처리 시간이 수 초 단위로 는다.

선택지 1로 정했으므로 E4가 실패할 경우 PEN-12/13 구현이 막힌다. 그 경우 다시 결정을 요청한다.

## 2. 실행 격리와 자원 제한

### D12 [사용자 결정 · 2026-10-15 확정] 격리 단위

실행기는 frontend 편집 계층을 그대로 돌린다(E4). 열린 파일·엔진·`storage`가 실행 사이에 남아야 하므로, 실행마다 새 격리 단위를 만들면 호출마다 파일을 다시 읽고 엔진에 다시 적재해야 한다(파일 크기에 따라 수 초). `storage`에 넣은 함수도 사라진다.

- 선택지 1 (결정): (사용자, MCP 세션)마다 Node 프로세스 하나를 쓴다. 다른 사용자의 데이터와 비밀 환경 변수를 넣지 않고, 메모리 상한을 두며, 강제로 끌 수 있다. 실행마다 새 SES compartment를 쓴다(현재 브라우저 플러그인과 같다).
- 선택지 2: 실행마다 새 프로세스를 쓰고 `storage`는 직렬화 가능한 값만 넘긴다.

**[기술 결정]**
- 격리 단위는 D12 선택지 1이다. 서로 다른 사용자나 MCP 세션은 프로세스를 공유하지 않는다. 한 세션의 실행끼리는 `storage`와 열린 파일 상태를 공유하고, 전역 변수는 공유하지 않는다(compartment마다 새 전역).
- sandbox에 주는 전역은 `penpot`, `penpotMgmt`, `penpotUtils`, `storage`, `console`뿐이다. `require`/`import`, 파일 시스템, 네트워크, 타이머 남용을 막는다. `setTimeout`은 실행 제한 시간 안에서만 허용한다.
- 제한값(D9): 시간 120초, 힙 256 MB, 변경 5,000개, 결과 JSON 10 MB.
  - 힙은 D9대로 측정해 **512 MB**로 조정했다(2026-10-15). 실행기는 도형 1개 파일에서도 V8 힙을 285 MB(release 빌드) 쓴다. 측정값은 `04-executor.md` §6.
  - 초과하면 그 세션 프로세스를 종료하고 아무것도 저장하지 않은 채 `resource-limit`를 돌려준다. 그 세션의 `storage`는 사라진다.
  - render-wasm 힙은 별도로 센다. 초기 256 MB에 상한을 두고, 이미지 캐시는 exporter의 `wasm-worker-image-cache-size` 방식을 따른다.
- 취소: mcp server가 취소를 받으면 실행 단위를 종료한다. 저장 요청을 보내기 전이면 `cancelled`(저장 없음)로 응답한다. 이미 보냈으면 저장 결과(revn)로 응답한다(D6).

## 3. 문서 컨텍스트와 완료 단계

**[기술 결정]**
- `DocumentSession`은 (사용자, MCP 세션, 파일)마다 하나다. 처음 열 때 `get-file`로 읽는다. 파일 features와 migration은 backend가 처리한 결과를 쓴다.
- 작업본은 다른 클라이언트의 `:file-change`를 받아 최신으로 유지한다. 받지 못한 경우 저장 응답의 `lagged` 변경을 적용한다. revn이 연속하지 않으면 다시 읽는다.
- 한 번의 실행은 네 단계를 거친다. 응답에 어느 단계까지 끝났는지 적는다.
  1. **변경 계산**: `penpot.*` 호출이 작업본을 바꾸고 cljc changes-builder로 변경을 쌓는다.
  2. **파생 값 계산**: 바뀐 도형과 영향받는 조상·자식의 레이아웃, 텍스트 크기·`position-data`, boolean content, 컴포넌트 동기화 변경을 Engine으로 계산해 같은 변경 묶음에 넣는다.
     - 실행 중 `penpot.waitForLayoutUpdate()`는 이 단계가 끝날 때까지 기다린다.
     - 실행이 끝날 때는 항상 이 단계를 끝낸다. 현재 브라우저 MCP처럼 텍스트가 1×1로 남는 일을 허용하지 않는다.
  3. **저장**: 묶음을 `update-file` 한 번으로 보낸다. `session-id`는 MCP 세션 UUID로 하고, `revn`은 작업본의 값으로 한다.
  4. **반영**: backend 알림으로 열린 브라우저에 반영된다. 서버는 반영을 기다리지 않는다. 지연 기준은 D7을 따른다.
- 응답 형식(모든 쓰기 도구 공통):

```json
{
  "result": "<사용자 코드 반환값 또는 도구 결과>",
  "log": "<console 출력>",
  "commit": {
    "saved": true,
    "fileId": "…", "revnBefore": 4, "revn": 5,
    "changedShapeIds": ["…"],
    "lagged": 0,
    "computed": {"layout": true, "text": true, "bool": true, "componentSync": true},
    "warnings": [{"code": "font-fallback", "shapeId": "…", "fontId": "…"}]
  },
  "engine": {"frontendVersion": "…", "renderWasm": "…"}
}
```

- 읽기 전용 실행은 `commit`을 `null`로 둔다. 저장 전 실패에는 `saved: false`를 쓰고, 오류 코드를 붙인다(§7).

## 4. 계산 계약 (Engine)

| 계산 | 엔진 | 입력 | 출력 | 실패 | 상태 |
|---|---|---|---|---|---|
| 도형 생성·속성·changes | cljc `setup-shape`, `changes-builder` | 작업본 objects, 속성 | 변경 목록 | 스키마 위반 → `validation` | 실증 E1 |
| 변환·constraints·레이아웃 reflow | render-wasm `propagate_modifiers` | 직렬화된 도형 트리, modifiers | 도형별 transform → selrect/points 변경 | 엔진 오류 → `engine-error` | 실증 E4 |
| 텍스트 크기·`position-data` | render-wasm `get_text_dimensions`, `calculate_position_data`, 필요 시 `update_shape_text_layout` | 텍스트 content, 폰트 바이트 | width/height, position-data | 폰트 없음 → 대체 폰트 + `font-fallback` 경고 | 실증 E4 |
| boolean | render-wasm `calculate_bool` | 자식 path, bool type | path content | `engine-error` | 실증 E4 |
| 컴포넌트 동기화 | cljc `app.common.logic.libraries` + 위 계산 | 라이브러리·파일 | 변경 목록 | `validation` | 읽기로 확인 |
| 토큰 해석 | npm `style-dictionary` + `sd-transforms` (frontend와 같은 버전) | token set/theme | resolvedValue | 해석 불가 → 토큰별 오류 목록 | **blocker E5** |
| SVG 가져오기 | `tubax` + `app.common.svg` (+ svgo) | SVG 문자열, 이미지 | shape 트리 변경 | 파싱 실패 → `svg-parser` | **blocker E6** |

**[기술 결정]**
- 폰트: 기본 폰트와 Google Fonts는 `app.common.fonts` 목록과 exporter의 폰트 URL 공급 방식을 쓴다. 팀 폰트는 사용자 token으로 `get-font-variants`를 불러 받는다. 폰트 바이트는 실행기 전체에서 font-id·variant 기준으로 캐시한다.
- 이미지: fill 이미지와 SVG 내부 이미지는 backend media RPC로 올린다. render-wasm에는 `store_image_url` 방식으로 공급한다.
- 숫자 정밀도: changes에 넣는 좌표는 frontend와 같은 cljc 반올림 규칙을 따른다(`app.common.geom.shapes.pixel-precision`, `mem:common/decimals-and-coordinates`).

## 5. 출력 계약 (PEN-19)

**[기술 결정]**
- 래스터·PDF·SVG export는 실행기 안의 headless render-wasm이 그린다. 브라우저 플러그인(wasm 모드)의 `shape.export()`와 같은 frontend 코드를 쓰고, 래스터는 GPU 대신 CPU에 그린다(`_render_shape_raster_extended`: 브라우저 export와 같은 영역, exporter headless와 같은 그리기 코드). exporter 서비스는 부르지 않는다(D14).
- ~~exporter 인증(E10)~~: D14로 필요 없어졌다. 실행기는 backend에만 사용자 MCP token과 `mcp` 공유 키로 요청한다(D11).
- 결과 전달:
  - 1 MB 이하는 base64로 응답 본문에 넣는다. 현재 `export_shape`와 같은 envelope `{"__type":"base64","data":…}`를 쓴다.
  - 그보다 크면 MCP server가 결과를 15분 보관하고 `{"__type":"resource", url, size, mtype, expiresAt}`를 돌려준다. URL(`GET /results/:id`)은 같은 MCP token으로만 받을 수 있다. Redis가 있으면 Redis에 보관해 다른 인스턴스에서도 받는다.
- `.penpot` 파일 내보내기·가져오기는 backend의 기존 binfile RPC를 쓴다.
- 코드 생성(`generateMarkup/Style/FontFaces`)은 frontend `app.util.code-gen`을 DOM 없이 Node에서 돌린다. 문자열 출력이 같아야 한다. 이것이 불가능하면(E7) 같은 결과를 내는 서버 구현을 PEN-19에서 만든다. 기능은 빼지 않는다.
- 비동기 결과: `{jobId, status: pending|running|done|error|cancelled, progress, resource?}`. 조회와 취소 도구를 둔다. job은 시작한 사용자만 볼 수 있다. 이는 exporter의 기존 job API 소유권 규칙과 같다.
  - 구현: `execute_code`의 `async: true`가 job을 시작하고 `execution_job` 도구(`jobId`, `cancel`)가 읽거나 취소한다. `progress`는 끝나기 전까지 `queued|running|saving`이다. 결과가 URL이면 `resource`에도 담는다. 저장을 시작한 job은 취소해도 끝까지 저장한다(D6).

### D14 [사용자 결정 · 2026-10-15 확정] 출력 경로

**[사실]** exporter는 보드를 보드 크기(selrect)로 잘라 그린다. 보드 밖으로 나간 그림자가 빠지므로, 같은 보드라도 브라우저 플러그인 export(그림자 포함 영역)와 크기·내용이 다르다. 또 exporter는 저장된 파일만 그린다. 같은 실행에서 바꾼 내용을 내보내려면 먼저 저장해야 하고, 사용자 token 인증(E10)도 새로 만들어야 한다.

**결정**: 실행기 안에서 그린다(위 §5). Chromium을 쓰지 않는다는 D10의 뜻은 그대로다. D10 설명의 '출력도 exporter의 headless wasm 경로만 쓴다'는 'exporter headless와 같은 render-wasm CPU 그리기 코드를 실행기 안에서 쓴다'로 바뀐다.

### D15 [사용자 결정 · 2026-10-15 확정] 래스터 비교 대상

**[사실]** 서버 래스터는 브라우저가 같은 CPU 경로로 그린 결과와 픽셀이 같다(PEN-19, 차이 0). 브라우저의 GPU export와는 픽셀 경계에 걸친 도형 가장자리만 antialiasing이 달라 0.1%를 넘을 수 있다(그림자가 있는 카드 1.07%, 텍스트·이미지 단독 0%). GPU 결과는 GPU 종류에 따라서도 다르다.

**결정**: §6의 래스터 기준은 브라우저 CPU 경로와 비교한다. GPU export와의 가장자리 차이는 예외 목록에 남기고 PEN-9에서 잰다.

## 6. 동등성 기준 (PEN-9 판정 기준)

같은 입력 파일과 같은 코드를 (1) 현재 MCP + wasm 모드 브라우저, (2) 서버 MCP로 각각 실행한 뒤 비교한다.

| 대상 | 정규화 | 기준 |
|---|---|---|
| shape map | id 재매핑(생성 순서 기준), 시각·session 필드 제거, 숫자는 소수 2자리 반올림 | 완전히 같음 |
| selrect / points / transform | — | 변환은 축별 0.01px, 레이아웃 결과는 0.5px |
| 텍스트 크기 | 같은 폰트 바이트 | width/height 0.5px, 줄 수와 줄바꿈 위치 같음 |
| 래스터 출력 | 같은 크기(텍스트는 도형 selrect 기준으로 자른 영역) | 채널 차이 2 초과 픽셀 0.1% 이하. 비교 대상은 브라우저의 CPU 래스터 export(D15). GPU export와는 크기가 같아야 한다 |
| SVG / 코드 생성 문자열 | 공백 정규화 | 같음 |
| 토큰 resolvedValue | — | 문자열 같음 |
| 실행 결과 JSON | 키 정렬 | 같음 (UI 전용 member는 D8 규칙) |

### D13 [사용자 결정 · 2026-10-15 확정] 브라우저 renderer와 기준 엔진

**[사실]** 브라우저 기본 renderer는 wasm이 아니라 `:svg`다. 프로필 설정 `:renderer`를 따른다(`frontend/src/app/main/features.cljs:35`). svg renderer는 텍스트를 DOM으로 잰다. 그래서 같은 텍스트라도 wasm 측정값과 몇 px 다를 수 있다(E3b: 445×43 / 436×39).

**결정**: 서버 계산 기준은 wasm으로 둔다(위 표와 같다). svg renderer 브라우저에서 보이는 차이와 재측정 여부는 PEN-9에서 재고 예외 목록에 남긴다. 이번 구현 범위는 바꾸지 않는다.

알려진 차이는 예외 목록에 남긴다. 예: `TokenTheme.externalId`, 텍스트 export의 잘린 영역 차이(E3b). 기준을 완화하려면 사용자 결정이 필요하다.

PEN-19에서 정한 예외(2026-10-15):
- 브라우저 GPU export와의 도형 가장자리 antialiasing 차이(D15).
- `generateMarkup({type: "svg"})`: 서버는 텍스트가 쓰는 폰트의 `@font-face`를 `<style>`에 넣고 브라우저는 비운다. frontend 공용 hook(rumext `use-ssr-effect`)이 화면이 없는 환경에서만 폰트 CSS를 바로 채우기 때문이다. 사용자 결정으로 서버 결과를 유지한다.
- PDF의 이미지: 서버는 이미지에 sRGB ICC profile을 붙이고(`/ICCBased`) 브라우저는 `/DeviceRGB`로 둔다. 서버는 Skia가 이미지를 디코딩하고 브라우저는 GPU texture를 읽기 때문이다. 이미지 픽셀 데이터는 같다.
- 내보낸 링크의 주소: 서버는 사용자가 여는 공개 주소로, 브라우저는 그 탭의 주소로 만든다. media id는 실행마다 새로 올리므로 다르다. 비교 때 정규화한다.

## 7. 오류 코드

| 코드 | 의미 | 저장 여부 |
|---|---|---|
| `not-found` | 파일·페이지·도형이 없거나 권한이 없음 (backend 404 그대로) | 없음 |
| `forbidden` | token이 없거나 만료·폐기됨 | 없음 |
| `validation` | 입력 또는 변경이 스키마·파일 검증을 통과하지 못함 | 없음 |
| `revn-conflict` / `vern-conflict` | backend 충돌 (버전 복원 등) | 없음. 다시 읽은 뒤 재시도 가능 |
| `precondition-failed` | D4의 선택적 사전 조건 위반 | 없음 |
| `ui-only` | D8에서 (c)로 정한 member, 또는 (f) member를 'AI 따라가기'를 켠 탭 없이 호출했을 때 | 없음 |
| `resource-limit` | §2 제한 초과 | 없음 |
| `cancelled` | 저장 전 취소 | 없음 |
| `engine-error` | 계산 엔진 오류 | 없음 |
| `svg-parser` / `font-unavailable` | 입력 자산 문제 (`font-unavailable`은 대체 폰트를 쓸 수 없을 때만) | 없음 |
| `execution-error` | 사용자 코드 예외. 메시지는 지금처럼 돌려줌 | 없음 |

## 8. 티켓별 계약 요약

입력·출력의 세부는 `feature-inventory.md`의 member 표와 Plugin API 타입 선언을 따른다. 아래는 티켓마다 지켜야 할 계약과 의존 관계다.

| 티켓 | 쓰는 구성 요소 | 추가 계약 | 선행 |
|---|---|---|---|
| PEN-10 | Sandbox, DocumentSession, mcp server 연결 | §2·§3, D1·D8 | — |
| PEN-3 | cljc changes, BackendClient | E1을 실행기 경로로 재현. 지연 D7 | PEN-10 최소 골격 |
| PEN-4 | BackendClient | 파일·프로젝트·버전 RPC, `openFile`·`openPage` 세션 의미(§4 of 01) | PEN-10 |
| PEN-5 | cljc | 기본 도형 속성 전체. 파생 계산 없는 속성부터 | PEN-3 |
| PEN-6 | DocumentSession, BackendClient | revn·lagged·재읽기(§3), D4·D5, 알림 누락(E8) | PEN-3 |
| PEN-11 | cljc + Engine(modifiers, bool) | §4 | E4 |
| PEN-12 | Engine(text), 폰트 공급 | §4 폰트 규칙, 텍스트 동등성 | E4 |
| PEN-13 | Engine(modifiers) | 중첩 reflow, `waitForLayoutUpdate` 의미(§3) | E4, PEN-12 |
| PEN-14 | cljc logic.libraries + Engine | 동기화 후 재계산 | PEN-11·12·13 |
| PEN-15 | cljc + npm 토큰 해석 | `externalId` 선언대로 제공 | E5 |
| PEN-16 | media RPC, SVG 파서 | §4 이미지 공급 | E6 |
| PEN-17 | cljc | — | PEN-5 |
| PEN-24 | mcp server 연결, frontend 따라가기 UI, 화면 이동 신호 | D8 (f) 규칙, 지연 D7 | PEN-4, PEN-10 |
| PEN-18 | comments RPC | 알림은 backend가 보냄 | PEN-10 |
| PEN-19 | Engine(render-wasm CPU 출력), code-gen | §5, D14, D15 | E7 |
| PEN-20 | DocumentSession undo stack | 실행 1회 = undo 1단위, 실패 시 저장 없음 | PEN-10 |

## 9. 병렬 구현·독립 시험 방법

- 모든 티켓은 같은 검증 환경(`verification-env.md`)을 쓰고, `seed` 데이터 위에서 시험한다. 시험마다 새 파일을 만들어 서로 간섭하지 않게 한다.
- 각 티켓은 자기 영역의 동등성 시험을 `experiments/` 방식(재실행 가능한 스크립트 + JSON 보고)으로 남긴다. PEN-9가 이것을 모아 통합 시험을 만든다.
- 공용 구성 요소(Sandbox, DocumentSession, Engine, BackendClient)의 interface는 PEN-10이 먼저 확정한다. 다른 티켓은 그 interface에 맞춰 병렬로 구현한다.
