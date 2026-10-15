#!/usr/bin/env bash
#
# Starts the Penpot services of the mcp-verify stack inside its main
# container, one tmux window per service, each piped to a log file under
# ~/penpot/.mcp-verify/logs (visible on the host in the source checkout).
#
# Runs as the penpot user (see scripts/mcp-verify-env). Idempotent: when the
# tmux session already exists it does nothing.

set -e

sudo chown penpot:users /home/penpot
cd ~
source ~/.bashrc

SESSION="mcpv"
LOG_DIR="$HOME/penpot/.mcp-verify/logs"
MCP_MODE="${MCPV_MCP_MODE:-multi}"
WITH_EXPORTER="${MCPV_WITH_EXPORTER:-true}"

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "[mcp-verify] tmux session '$SESSION' already running"
    exit 0
fi

mkdir -p "$LOG_DIR"

# frontend/resources/public/js/config.js is gitignored; without enable-mcp the
# frontend never connects the MCP plugin.
CONFIG_JS="$HOME/penpot/frontend/resources/public/js/config.js"
if [ ! -f "$CONFIG_JS" ]; then
    mkdir -p "$(dirname "$CONFIG_JS")"
    echo 'var penpotFlags = "enable-mcp enable-access-tokens";' > "$CONFIG_JS"
fi

tmux -2 new-session -d -s "$SESSION" -n setup

# Opens a tmux window running COMMAND in DIR with output appended to
# $LOG_DIR/NAME.log.
function service {
    local name="$1" dir="$2" command="$3"
    tmux new-window -t "$SESSION" -n "$name"
    tmux pipe-pane -t "$SESSION:$name" -o "cat >> '$LOG_DIR/$name.log'"
    tmux send-keys -t "$SESSION:$name" "cd ~/penpot/$dir && $command" enter
}

{
    # The frontend and exporter watchers both build render-wasm and run
    # `rustup default` at the same moment; on a fresh container (the image
    # ships an older toolchain) the two downloads collide. Install the
    # toolchain once before either starts.
    echo "[mcp-verify] $(date -Is) preparing the render-wasm rust toolchain"
    (
        cd ~/penpot/render-wasm
        RUST_VERSION="$(sed -n 's/^export RUST_VERSION=//p' _build_env)"
        rustup default "$RUST_VERSION"
        rustup target add wasm32-unknown-emscripten
        rustup component add clippy rustfmt --toolchain "$RUST_VERSION"
    )

    echo "[mcp-verify] $(date -Is) installing node dependencies"
    (cd ~/penpot/frontend && ./scripts/setup)
    if [ "$WITH_EXPORTER" = "true" ]; then
        (cd ~/penpot/exporter && ./scripts/setup)
    fi
    (cd ~/penpot/mcp && ./scripts/setup && pnpm run build)
    echo "[mcp-verify] $(date -Is) dependencies ready"
} >> "$LOG_DIR/setup.log" 2>&1

service frontend frontend "./scripts/watch app"
service backend backend "./scripts/start-dev"

if [ "$WITH_EXPORTER" = "true" ]; then
    service exporter-watch exporter "rm -f target/app.js* && ./scripts/watch"
    # The public URI carries the host-side port, which nothing listens on
    # inside the container; the exporter must reach the backend and the
    # render page through the in-container proxy instead.
    service exporter exporter "PENPOT_INTERNAL_URI=http://localhost:3450 ./scripts/wait-and-start.sh"
fi

# Server-side MCP executor (PEN-22): the frontend `:executor` bundle, built
# once the frontend compiler is up (it reuses the watch's shadow-cljs server)
# and render-wasm is built. `optional` keeps the browser plugin as the default
# and lets a client pick the executor with `?executor=server`, so both paths
# can be compared on one MCP server.
service executor frontend "until grep -aq '\[:main\] Build completed' $LOG_DIR/frontend.log; do sleep 5; done; ./scripts/build-executor compile && echo '[mcp-verify] executor bundle ready'"

MCP_ENV="PENPOT_MCP_SERVER_HOST=0.0.0.0 PENPOT_MCP_REMOTE_MODE=true PENPOT_TENANT=$PENPOT_TENANT"
MCP_ENV="$MCP_ENV PENPOT_MCP_EXECUTOR=${MCPV_MCP_EXECUTOR:-optional}"
MCP_ENV="$MCP_ENV PENPOT_MCP_EXECUTOR_BUNDLE=$HOME/penpot/frontend/target/executor/executor.js"
MCP_ENV="$MCP_ENV PENPOT_MCP_EXECUTOR_WASM_DIR=$HOME/penpot/frontend/resources/public/js"
MCP_ENV="$MCP_ENV PENPOT_MCP_EXECUTOR_PUBLIC_URI=http://localhost:3450"
# devenv value, the same as backend/scripts/_env
MCP_ENV="$MCP_ENV PENPOT_MCP_SHARED_KEY=super-secret-mcp-key"
MCP_ENV="$MCP_ENV PENPOT_FLAGS='enable-mcp enable-access-tokens'"
if [ "$MCP_MODE" = "multi" ]; then
    # Valkey DB 1 keeps the MCP session claims apart from the backend (DB 0).
    service mcp mcp "$MCP_ENV PENPOT_MCP_REDIS_URI=redis://valkey/1 pnpm run start:multi-user"
else
    service mcp mcp "$MCP_ENV PENPOT_MCP_REPL_HOST=0.0.0.0 PENPOT_MCP_DEVENV=true pnpm run start"
fi

echo "[mcp-verify] $(date -Is) services started (mcp mode: $MCP_MODE)" >> "$LOG_DIR/setup.log"
