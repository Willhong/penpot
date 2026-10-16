#!/usr/bin/env bash
#
# Builds the design.hktlabs.com images from one commit of this fork and
# pushes them to Harbor. Runs on nucbox (amd64), not on the Mac (arm64).
#
#   docker/hkt-deploy/build.sh <commit> [--push]
#
# The commit must be reachable from the build checkout: either pushed to
# origin, or fetched from a git bundle copied from the Mac (see README.md).
# Images: harbor.hktlabs.com/library/penpot-{frontend,backend,exporter,
# mcp-executor}:hkt-<short sha>.

set -euo pipefail

COMMIT="${1:?usage: build.sh <commit> [--push]}"
PUSH="${2:-}"
BUILD_DIR="${PENPOT_BUILD_DIR:-$HOME/build/penpot-deploy}"
REGISTRY="${PENPOT_REGISTRY:-harbor.hktlabs.com/library}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run from a copy: the checkout below may replace this very file.
if [[ -z "${HKT_BUILD_COPY:-}" ]]; then
    copy="$(mktemp -d)"
    cp "$HERE/build.sh" "$HERE/Dockerfile.mcp-executor" "$copy/"
    HKT_BUILD_COPY=1 exec bash "$copy/build.sh" "$@"
fi

# manage.sh `build` mounts this volume as the devenv home
export PENPOT_USER_DATA_VOLUME=penpot_build_user_data

step() { echo; echo "=== [$(date '+%F %T')] $*"; }

if [[ ! -d "$BUILD_DIR/.git" ]]; then
    step "clone"
    git clone --filter=blob:none https://github.com/Willhong/penpot.git "$BUILD_DIR"
fi

cd "$BUILD_DIR"
step "checkout $COMMIT"
git fetch --tags origin || true
git checkout --force "$COMMIT"
git clean -fdx >/dev/null
SHA="$(git rev-parse --short=9 HEAD)"
TAG="hkt-$SHA"
git describe --tags --match "*.*.*"

step "pull devenv"
docker pull penpotapp/devenv:latest

for module in frontend backend exporter mcp; do
    step "bundle $module"
    ./manage.sh "build-$module-bundle"
done

step "executor bundle"
docker run -t --rm \
    --mount source="$PENPOT_USER_DATA_VOLUME",type=volume,target=/home/penpot/ \
    --mount source="$(pwd)",type=bind,target=/home/penpot/penpot \
    -e EXTERNAL_UID="$(id -u)" \
    -w /home/penpot/penpot/frontend \
    penpotapp/devenv:latest \
    sudo -EH -u penpot bash -c 'NODE_ENV=production ./scripts/build-executor release'

for module in frontend backend exporter mcp; do
    step "image $module"
    ./manage.sh "build-$module-docker-image" --tag "$TAG"
done

# The executor resolves its npm imports from the frontend checkout's
# node_modules (dev dependencies included), so they ship as they are.
step "image mcp-executor"
ctx="$(mktemp -d)"
trap 'rm -rf "$ctx"' EXIT
mkdir -p "$ctx/executor-frontend/target" "$ctx/executor-frontend/wasm"
rsync -a frontend/node_modules frontend/packages frontend/text-editor frontend/package.json \
    "$ctx/executor-frontend/"
rsync -a --exclude '*.map' frontend/target/executor "$ctx/executor-frontend/target/"
cp bundles/frontend/js/render-wasm.js bundles/frontend/js/render-wasm.wasm "$ctx/executor-frontend/wasm/"
# the executor reads the version it reports from the index.html above the wasm directory
cp bundles/frontend/index.html "$ctx/executor-frontend/"
cp "$HERE/Dockerfile.mcp-executor" "$ctx/Dockerfile"
docker build --build-arg BASE="penpotapp/mcp:$TAG" -t "penpotapp/mcp-executor:$TAG" "$ctx"

step "smoke: executor bundle loads"
# the bundle's init starts timers, so exit explicitly once the exports are read
docker run --rm -e PENPOT_PUBLIC_URI=http://localhost -e PENPOT_FLAGS= "penpotapp/mcp-executor:$TAG" \
    node -e 'import("/opt/penpot/frontend/target/executor/executor.js").then(m => { console.log(Object.keys(m).join(",")); process.exit(0); }, e => { console.error(e); process.exit(1); })'

if [[ "$PUSH" == "--push" ]]; then
    for image in frontend backend exporter mcp-executor; do
        step "push $image"
        docker tag "penpotapp/$image:$TAG" "$REGISTRY/penpot-$image:$TAG"
        docker push -q "$REGISTRY/penpot-$image:$TAG"
    done
fi

step "done: $TAG"
