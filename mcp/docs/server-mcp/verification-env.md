# 서버 MCP 검증 환경 (PEN-2)

운영 서비스와 기존 개발 환경의 데이터를 건드리지 않고 `MCP 또는 서버 실행기 → backend → 저장 → 열린 브라우저` 흐름을 시험하는 Docker 스택이다. 이 스크립트가 들어 있는 checkout의 코드를 그대로 띄운다. 따라서 새 worktree에서도 같은 명령으로 다시 만들 수 있다.

## 무엇이 분리되어 있나

| 항목 | 기존 devenv (`manage.sh`) | mcp-verify |
|---|---|---|
| compose project | `penpotdev-infra` + `penpotdev-wsN` | `penpot-mcpverify` (`MCPV_PROJECT`로 변경 가능) |
| network | `penpot_shared` (모든 인스턴스 공유) | `penpot-mcpverify_net` |
| PostgreSQL DB `penpot` | 모든 ws가 공유 | 전용 컨테이너·볼륨 `penpot-mcpverify_postgres_data` |
| 객체 저장소 | 공유 RustFS bucket | 전용 RustFS·볼륨 |
| Valkey | 공유, DB 번호만 다름 | 전용 컨테이너 (backend DB 0, MCP DB 1) |
| 공개 포트 | 3449 등, 일부 모든 인터페이스 | `127.0.0.1`만: 3549(HTTPS), 3550(HTTP), 4501(MCP), 1180(Mailpit) |
| LDAP | 있음 | 없음 |

- 운영 DB·스토리지·MCP 키·글로벌 MCP 설정은 쓰지 않는다. 테스트 계정 비밀번호와 토큰은 이 스택 안에서만 쓰는 값이며 `.mcp-verify/`(gitignore)에만 저장된다.
- `destroy --yes`는 이 스택의 볼륨만 지운다. 다른 compose project의 볼륨은 이름이 달라 지워지지 않는다.

## 파일

| 경로 | 역할 |
|---|---|
| `scripts/mcp-verify-env` | 기동·대기·상태·fixture·로그·종료 명령. macOS 기본 Bash 3.2에서 동작한다. |
| `docker/mcp-verify/docker-compose.yml` | 전용 스택 정의. `penpotapp/devenv` 이미지와 `docker/devenv/files`의 PostgreSQL 설정을 재사용한다. |
| `docker/mcp-verify/files/start-services.sh` | 컨테이너 안에서 rust toolchain·node 의존성을 준비하고 frontend·backend·exporter·MCP를 tmux 창으로 띄운다. 창마다 로그를 남긴다. |
| `docker/mcp-verify/seed.py` | 테스트 사용자·팀·프로젝트·파일·토큰 생성 (멱등). |
| `mcp/docs/server-mcp/experiments/*.py` | 기술 실험 (`02-browser-dependency-research.md` 참조). |
| `.mcp-verify/` (gitignore) | `logs/<서비스>.log`, `fixtures.json`, 실험 결과 이미지. |

## 사용법

저장소 루트에서 실행한다.

```sh
scripts/mcp-verify-env up            # 기본: MCP multi-user 모드, exporter 포함
scripts/mcp-verify-env wait          # backend·frontend·plugin·MCP·exporter 준비까지 대기 (기본 2400초)
scripts/mcp-verify-env seed          # 테스트 데이터 생성/재확인
scripts/mcp-verify-env status        # 컨테이너, 준비 상태, 주소
scripts/mcp-verify-env logs backend 100
scripts/mcp-verify-env shell         # main 컨테이너 셸 (penpot 사용자)
scripts/mcp-verify-env psql -c 'select count(*) from file'
scripts/mcp-verify-env down          # 컨테이너 제거, 볼륨 유지
scripts/mcp-verify-env destroy --yes # 이 스택 볼륨까지 제거
```

옵션은 다음과 같다.
- `up --single-user`: 기존 devenv처럼 단일 사용자 MCP를 띄운다. REPL과 개발 도구가 켜진다.
- `up --no-exporter`: exporter를 띄우지 않는다.
- 포트·이름 변경: `MCPV_PROJECT=penpot-mcpverify2 MCPV_HTTPS_PORT=3649 MCPV_HTTP_PORT=3650 MCPV_MCP_PORT=4601 MCPV_MAIL_PORT=1280 scripts/mcp-verify-env up`. 두 스택을 동시에 띄우거나 다른 worktree에서 띄울 때 쓴다.

### 첫 기동 비용 (2026-10-14, Apple Silicon, Docker VM 18 CPU/16 GB에서 측정)

- 이미지 다운로드: `penpotapp/devenv:latest`의 arm64 압축 크기 1.91 GB와 postgres·rustfs·valkey·mailpit.
- 컨테이너를 새로 만들 때마다 Rust 1.99.0 toolchain을 내려받는다. 이미지에는 1.91.0이 들어 있다.
- 처음 실행할 때 node 의존성 설치에 1분 41초가 걸렸다. 캐시가 있는 재기동에서는 toolchain 15초, 의존성 1초가 걸렸고, frontend `:main` 컴파일(137초)까지 포함해 약 2분 30초 뒤 모두 준비됐다.
- 실행 중 메모리: main 컨테이너 약 7.2 GB, 나머지 컨테이너 합계 약 0.3 GB.
- pnpm store(`.pnpm-store/`)와 `node_modules`는 소스 checkout 안에 생긴다(gitignore). Maven·cargo 캐시는 `penpot-mcpverify_user_data` 볼륨에 남아 다음 기동이 빨라진다.

## 테스트 데이터 (`seed`)

| 역할 | 계정 | 팀 권한 | 용도 |
|---|---|---|---|
| owner | `mcpv-owner@example.com` | 소유자 | 관찰 브라우저 1, 파일 소유 |
| editor | `mcpv-editor@example.com` | 편집 가능 | 관찰 브라우저 2, 서버 쓰기 주체 |
| viewer | `mcpv-viewer@example.com` | 읽기 전용 (`can_edit=false`) | 쓰기 거부 확인 |
| outsider | `mcpv-outsider@example.com` | 팀 밖 | 접근 거부 확인 |

- 비밀번호는 모두 `mcpv-test-password`이다. 이 스택 전용 값이다.
- 팀 `MCP Verify` → 프로젝트 `Fixtures` → 파일 `basic`, `concurrency`, `scratch`.
- 사용자마다 access token 두 개를 만든다.
  - `mcpv-<역할>-api`: 일반 API token. `Authorization: Token <값>`으로 backend RPC를 호출할 때 쓴다.
  - `mcpv-<역할>-mcp`: MCP token. 현재 MCP의 `?userToken=`에 쓴다.
- 모든 사용자의 `mcp-enabled` 설정을 켠다.
- 팀 멤버십은 초대 메일을 거치지 않고 `team_profile_rel`에 직접 넣는다.
- `seed --reset-tokens`는 `mcpv-*` token을 지우고 새로 만든다.

## 브라우저 관찰 환경 두 개

자체 서명 인증서 때문에 자동화 브라우저에서 HTTPS 3549가 막힐 수 있다. 그럴 때는 HTTP 3550을 쓰고, 두 사용자를 **다른 host 이름**으로 연다. 쿠키는 port가 아니라 host 단위로 나뉜다.

- 관찰 브라우저 1 (owner): `http://localhost:3550/`
- 관찰 브라우저 2 (editor): `http://127.0.0.1:3550/`

두 주소는 모두 브라우저가 보안 컨텍스트로 취급한다. 화면 왼쪽 아래의 `shadow-cljs - Reconnecting` 표시는 hot reload 연결 실패를 뜻하며 시험에는 영향이 없다.

## 확인한 동작 (2026-10-14)

| 확인 항목 | 결과 |
|---|---|
| backend·frontend·exporter·MCP(multi-user) 기동 | `wait` 통과 |
| 기본 파일 저장·재조회 | 실험 E1: 브라우저 없이 `update-file` 200, `get-file`로 다시 읽은 revn과 도형 일치 |
| 두 클라이언트 공동 편집 | owner 화면에서 만든 Board가 editor 화면에 나타남. 서버가 저장한 사각형은 두 화면에 스크립트 시작 후 약 0.73초 만에 나타남 |
| 현재 MCP 연결 | owner 브라우저에서 MCP Connect → HTTP MCP 클라이언트가 같은 MCP token으로 `execute_code` 실행 성공 |
| 브라우저 0개 조건 | 두 탭을 닫으면 현재 MCP는 `No Penpot sessions are connected`로 즉시 실패, 서버 직접 저장(E1)은 성공 |
| 권한 | viewer·outsider token으로 쓰면 둘 다 `404 object-not-found` |
| fixture 멱등성 | `seed` 2회 실행 결과 `fixtures.json` 동일, 팀 1개 |

### 서버 쓰기와 관찰 브라우저를 나누는 방법

- 서버 쓰기 주체: `experiments/e1_server_write.py`처럼 브라우저 밖에서 API token으로 RPC를 호출하는 프로세스다. `session-id`는 매번 새 UUID를 쓴다.
- 관찰 브라우저: owner·editor로 로그인한 탭이다. 쓰지 않고 레이어 목록과 캔버스만 본다.
- 브라우저 0개 조건: 관찰 탭을 모두 닫거나 `about:blank`로 보낸 뒤 실행한다. 현재 MCP는 이 조건에서 실패한다. 이것이 비교 기준이다.

## 구성 중 발견해 고친 문제

1. **rustup 경쟁**: frontend watch와 exporter watch가 동시에 `rustup default 1.99.0`을 실행하면 같은 다운로드 파일을 두고 충돌한다. 그래서 `start-services.sh`가 서비스보다 먼저 toolchain을 한 번 설치한다.
2. **entrypoint 경쟁**: 이미지 entrypoint가 `/opt/rustup` 소유자를 바꾸기 전에 서비스를 시작하면 권한 오류가 난다. 그래서 `up`이 nginx 기동(entrypoint 완료)을 기다린다.
3. **exporter 내부 주소**: 공개 주소의 host port(3549)는 컨테이너 안에서 열려 있지 않다. 그래서 exporter에만 `PENPOT_INTERNAL_URI=http://localhost:3450`을 준다. 기본 devenv의 ws1+도 같은 이유로 export가 실패할 수 있다(미확인).
4. **frontend 준비 판정**: `main.js`는 컴파일이 끝나기 전에 생긴다. 그래서 로그의 마지막 `[:main] Build completed`를 준비 기준으로 쓴다.

## 다른 worktree에서 다시 만들기

1. 새 worktree에서 `scripts/mcp-verify-env up`을 실행한다. 이전 스택이 같은 포트로 떠 있으면 먼저 `down`하거나 `MCPV_*` 포트·이름을 바꾼다.
2. `wait` → `seed` → `python3 -I mcp/docs/server-mcp/experiments/e1_server_write.py --file scratch`로 저장 경로를 확인한다.
3. 볼륨은 project 이름 단위로 나뉜다. 같은 `MCPV_PROJECT`를 쓰면 이전 테스트 데이터를 이어 쓰고, 다른 이름을 쓰면 빈 DB로 시작한다.
