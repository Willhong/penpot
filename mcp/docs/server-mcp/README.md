# 서버 MCP 준비 자료 (PEN-23)

브라우저를 열지 않고 Penpot 파일을 편집·출력하는 서버 MCP의 구현 준비 자료다. 범위는 현재 MCP가 할 수 있는 전부다. Plugin API member 716개와 MCP 도구 10개가 모두 포함된다.

흐름:
1. PEN-23 준비 (이 폴더)
2. PEN-22 전체 구현
3. PEN-9 통합 검증
4. PEN-21 운영 배포

## 문서

| 문서 | Plane | 내용 | 상태 |
|---|---|---|---|
| [01-feature-contract.md](01-feature-contract.md) | PEN-1 | 기능 범위, 인증, 대상 지정, 저장·충돌·중복·취소, UI 전용 API | 범위 확정, D1–D9·D11·D16 확정 |
| [feature-inventory.md](feature-inventory.md) | PEN-1 | member·도구별 담당 티켓과 검증 시나리오 (생성 파일) | 미매핑 0 |
| [verification-env.md](verification-env.md) | PEN-2 | 운영과 분리한 검증 스택 사용법 | 완료 |
| [02-browser-dependency-research.md](02-browser-dependency-research.md) | PEN-7 | 기능별 브라우저 의존성, 서버 경로 대안, 실험 E1–E3 | 완료, 미확인 E4–E11 목록 |
| [03-runtime-contract.md](03-runtime-contract.md) | PEN-8 | 실행 격리, 완료 단계, 계산·출력 계약, 동등성 기준, 오류 코드 | 기술 계약 확정, E4 실증, blocker E5–E7, D10·D12–D15 확정(D14로 E10 불필요) |
| [04-executor.md](04-executor.md) | PEN-10 | 서버 실행기 구성 요소와 interface, 실행 순서, 세션, 측정값 | interface 확정, PEN-3 연결 |
| [05-results.md](05-results.md) | PEN-22 | 티켓별 실제 MCP 시험 결과 | PEN-3, PEN-4 |

## 도구

- `tools/gen_inventory.py`: 기능 목록을 다시 만든다. `--check`는 미매핑 member가 있거나 생성 파일이 오래되면 실패한다.
- `experiments/e1_server_write.py`: 브라우저 없는 저장, 권한·revn·중복 요청 경계를 시험한다.
- `experiments/e3_headless_export.py`: headless wasm export와 Chromium export를 비교한다.
- `experiments/e4_headless_compute.py`: 같은 Plugin API 코드를 브라우저(wasm 모드)와 headless 실행기에서 실행해 저장 결과를 비교한다.
- `experiments/observe_write.sh` + `browser_observe.js`: 서버 저장이 관찰 브라우저 두 개에 나타나기까지의 시간을 잰다.
- `experiments/pen3_vertical_slice.py`: 실제 MCP 호출(서버 실행)로 사각형을 저장하고, 브라우저가 열렸을 때·닫혔을 때·새로고침 뒤, 거부 요청 무변경을 확인한다.
- `experiments/pen4_files_pages.py`: 프로젝트·파일·페이지·메타데이터·버전을 브라우저 없이 시험하고 브라우저 결과와 비교한다.
- `experiments/mcp_client.py`, `observers.py`: 실험용 MCP 클라이언트, 관찰 브라우저 조작.
- 검증 스택: 저장소 루트의 `scripts/mcp-verify-env`.

## 다음 구현 작업(PEN-22)이 시작할 때

1. 새 worktree에서 `scripts/mcp-verify-env up && scripts/mcp-verify-env wait && scripts/mcp-verify-env seed`를 실행한다. 이어서 E1을 실행해 환경을 확인한다.
2. `01`의 D1–D9와 `03`의 D10 결정 결과를 확인한다. D1–D10은 모두 확정됐다.
3. 첫 작업은 E4다. Node headless render-wasm으로 계산 API를 부르는 하네스를 만든다. 이 결과에 따라 PEN-11·12·13의 경로가 정해진다.
4. PEN-10에서 공용 구성 요소의 interface를 먼저 확정한다. 다른 티켓은 그 interface에 맞춰 병렬로 진행한다(`03` §9).
