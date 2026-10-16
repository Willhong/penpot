# 운영 배포 (PEN-21)

design.hktlabs.com(nucbox k3s, namespace `penpot`, Helm release `penpot`)에 서버 MCP를 배포하고, 기존 연결과 같이 쓰는지와 롤백을 확인한 기록이다. 빌드·배포 파일은 [`docker/hkt-deploy/`](../../../docker/hkt-deploy/)에 있다.

## 1. 사용 안내

1. 웹(https://design.hktlabs.com)에 로그인해 **Integrations** 메뉴에서 MCP 키를 한 번 만든다. 웹 없이 키를 발급하는 기능은 없다(사용자 결정, 2026-10-15).
2. MCP 클라이언트에 다음 주소를 등록한다. 이후 편집·조회·내보내기는 웹을 열지 않고 MCP만으로 한다.

   ```
   https://design.hktlabs.com/mcp/stream?userToken=<MCP 키>&executor=server
   ```

   - `&executor=server`를 빼면 지금까지처럼 브라우저 플러그인으로 실행한다. 그때는 Penpot 탭에서 메인 메뉴 → MCP → Connect가 필요하다.
   - 서버 실행은 `execute_code`의 `fileId`로 열 파일을 정한다. 처음 쓸 때는 `penpotMgmt.listProjects()` / `listFiles()` / `createFile()`로 파일을 찾거나 만든다.
3. 실패는 오류 코드로 온다(`03-runtime-contract.md` §7). 사용자가 흔히 보는 것:

   | 코드 | 뜻 | 할 일 |
   |---|---|---|
   | `forbidden` | MCP 키가 없거나 지워졌거나 만료됨 | 웹에서 키를 다시 만들고 클라이언트 설정을 바꾼다 |
   | `not-found` | 파일이 없거나 이 사용자가 읽을 수 없음, 읽기 전용 파일에 쓰기 | 파일 id와 공유 권한을 확인한다 |
   | `precondition-failed` | `ifUnchangedSinceRevn` 뒤에 다른 사람이 파일을 바꿈 | 파일을 다시 읽고 새 `requestId`로 시도한다 |
   | `resource-limit` | 시간·변경 수·계산 대기 상한을 넘음 | 작업을 나누거나 `async: true`로 실행한다 |

## 2. 배포 구성

| 구성 | 값 |
|---|---|
| 이미지 | `harbor.hktlabs.com/library/penpot-{frontend,backend,exporter,mcp-executor}:hkt-<sha>`. admin console은 upstream 2.18.3 그대로(소스가 이 저장소에 없다) |
| MCP 이미지 | release MCP 이미지 위에 frontend `:executor` 빌드, 그 빌드가 import하는 frontend `node_modules`, render-wasm, `index.html`(보고하는 버전)을 얹는다 (`Dockerfile.mcp-executor`) |
| 실행 방식 | `PENPOT_MCP_EXECUTOR=optional`: 브라우저 플러그인이 기본, 주소에 `executor=server`가 있으면 서버 실행 |
| 인증 | backend `enable-access-tokens` 필수. 없으면 backend가 `Authorization` 헤더를 읽지 않아 모든 서버 실행이 `forbidden`이다. MCP pod에 `PENPOT_SECRET_KEY`를 줘 backend와 같은 `mcp` 공유 키를 만든다 |
| 실행기 상한 | 동시 실행 8, 세션 8, pod 메모리 상한 8 GiB (기본값은 호스트 32 CPU·124 GB 기준이라 크다) |
| backend 주소 | 실행기는 `http://penpot:8080`(frontend nginx)로 backend를 부른다 |

## 3. 빌드와 배포

nucbox에서 빌드한다(맥은 arm64). 약 15분.

```sh
# 커밋이 origin에 없으면 맥에서 bundle로 옮긴다
git bundle create /tmp/hkt.bundle develop ^<nucbox에 있는 커밋>
scp /tmp/hkt.bundle will@100.77.154.10:build/
ssh will@100.77.154.10 'cd ~/build/penpot-deploy && git fetch ~/build/hkt.bundle develop:refs/heads/hkt-local'

# nucbox: 빌드와 Harbor push
docker/hkt-deploy/build.sh <commit> --push

# 맥: 배포 전 백업, 배포
kubectl -n penpot exec postgres-0 -- sh -c 'pg_dump -U "$POSTGRES_USER" -d penpot -Fc' > <백업>/penpot.pgdump
kubectl -n penpot exec deploy/penpot-backend -- tar -C /opt/data -czf - assets > <백업>/assets.tgz
helm -n penpot get values penpot -o yaml > <백업>/helm-values.yaml   # 처음 배포 때 한 번
T=hkt-<sha>
helm -n penpot upgrade penpot penpot/penpot --version 1.11.3 \
  -f <백업>/helm-values.yaml -f docker/hkt-deploy/values.yaml \
  --set-string frontend.image.tag=$T,backend.image.tag=$T,exporter.image.tag=$T,mcp.image.tag=$T \
  --wait --timeout 8m
```

## 4. 롤백

2.18.3 → 2.19 업그레이드는 DB 마이그레이션 0153~0156을 적용한다(`http_session` 테이블과 옛 썸네일 테이블 삭제 포함). 이미지만 되돌리면 2.18.3 backend가 바뀐 스키마로 돈다. 그래서 롤백은 DB 복원과 함께 한다.

```sh
kubectl -n penpot scale deploy penpot-backend penpot-exporter penpot-mcp penpot-frontend --replicas=0
kubectl -n penpot exec postgres-0 -- sh -c 'dropdb -U "$POSTGRES_USER" --force penpot && createdb -U "$POSTGRES_USER" penpot'
kubectl -n penpot exec -i postgres-0 -- sh -c 'pg_restore -U "$POSTGRES_USER" -d penpot --no-owner' < <백업>/penpot.pgdump
helm -n penpot rollback penpot <업그레이드 전 revision> --wait
# assets: /opt/data/assets 는 마운트 지점이라 맨 위 디렉터리를 건너뛰고 푼다
kubectl -n penpot exec -i deploy/penpot-backend -- tar -C /opt/data/assets --strip-components=1 --no-same-permissions -m -xzf - < <백업>/assets.tgz
```

업그레이드 뒤에 생긴 데이터는 롤백하면 사라진다.

리허설: `BACKUP_DIR=<백업> TAG=hkt-<sha> docker/hkt-deploy/rollback-rehearsal.sh`가 별도 namespace(`penpot-rollback-test`)에서 2.18.3 설치 → 업그레이드 → 위 절차로 롤백까지 돌린다. 운영 namespace는 건드리지 않는다.

## 5. 확인 결과 (2026-10-16, `41b20fcbe`, Helm revision 4)

| 완료 기준 | 결과 |
|---|---|
| 검증본과 같은 버전 | `41b20fcbe` = PEN-9 최종 확인 뒤 커밋 + 아래 결손 수정 1건. 네 이미지 모두 같은 커밋에서 빌드, 실행기가 보고하는 버전 `2.19.0-RC1-291-g41b20fcbe` |
| 브라우저 없이 편집·출력 | 서버 실행으로 파일 만들기 → flex 보드·한글 텍스트·사각형 저장 → 레이아웃 값 다시 읽기(텍스트 24,24 / 사각형 24,68) → PNG 내보내기(320×200, 한글 정상) |
| 열린 브라우저 실시간 반영 | 파일을 연 탭에 서버 변경(색·크기)이 새로고침 없이 나타남 |
| 기존 클라이언트 공존 | 같은 MCP 서버에서 브라우저 플러그인 경로(탭 Connect, `executor` 없음)로 읽기·쓰기 → 서버 실행으로 같은 값 읽힘. Hermes·Claude Code·BB의 등록 주소를 `executor=server`로 바꾼 뒤 BB·Claude Code에서 실제 호출 성공 |
| 인증 회수 | 새 프로필의 MCP 키로 실행 성공 → 키를 지운 뒤 같은 세션·새 세션 모두 `forbidden`, 저장 없음 (`experiments/pen21_auth_check.py`) |
| 권한 거부 | 그 키로 다른 사용자의 파일을 열면 `not-found`, 저장 없음. 같은 세션의 자기 파일 작업은 계속 됨 |
| 재시작 | MCP pod 재시작 뒤 첫 실행이 저장(revn 3→4). backend 재시작 뒤 같은 값 읽힘 |
| 롤백 | 리허설 통과: 2.18.3 (마이그레이션 163개) → 업그레이드 (170개, `http_session` 삭제) → 롤백 뒤 2.18.3 이미지 5개, 마이그레이션 163개, `http_session` 복구, 새 마이그레이션 적용 없음, backend 오류 0, assets 53/53, frontend·`/readyz` 정상 |

### 배포 중 고친 결손

- **키를 지운 뒤 오류 코드**: 세션이 살아 있는 동안 키를 지우면 다음 호출이 `forbidden`이 아니라 `execution-error: http error`였다. backend의 401이 Plugin API를 거쳐 사용자 코드의 예외로 올라왔고, 저장·파일 열기만 계약 코드로 바꾸고 있었다. 실행기 bundle의 `errorCode`가 그런 예외를 `forbidden`으로 알려 준다(`41b20fcbe`). 저장은 고치기 전에도 일어나지 않았다.
- **배포 조건**: `enable-access-tokens`가 없으면 서버 실행이 전부 거부된다(위 2절). 검증 스택에는 켜져 있어 PEN-9에서 드러나지 않았다.
- **실행기 이미지의 버전**: 실행기는 wasm 디렉터리 위의 `index.html`에서 버전을 읽는다. 이미지에 넣지 않으면 `penpot.version`이 빈 값이다.

### 남은 것

- backend 로그에 `audit-log-archive` cron 오류가 매번 남는다(`:app.db/pool` 누락). upstream develop 코드이고 편집 동작과 무관하다.
- 운영 데이터로 롤백을 실제 실행하지는 않았다. 같은 백업으로 별도 namespace에서 리허설했다.
- `build.sh`의 마지막 두 수정(스모크 단계가 끝나지 않던 문제, `index.html` 복사)은 이번 빌드에서 같은 단계를 손으로 돌려 반영했다. 고친 스크립트를 처음부터 끝까지 다시 돌리지는 않았다.
