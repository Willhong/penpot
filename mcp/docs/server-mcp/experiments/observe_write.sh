#!/usr/bin/env bash
#
# Measures how long a browserless write takes to show up in the observer
# tabs (owner + editor) of the mcp-verify stack, without any reload.
#
#   observe_write.sh <space-id> <expect> -- <write command...>
#
# 1. starts browser_observe.js in the given ego-browser task space and
#    waits until it has its baseline;
# 2. runs the write command, timing it;
# 3. prints the observer report plus the write start/end epoch ms as JSON.
#
# The write command must exit 0 once the save has been acknowledged.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/../../../.." && pwd)"
SPACE="$1"; EXPECT="$2"; shift 2
[[ "${1:-}" == "--" ]] && shift

OUT="$ROOT/.mcp-verify/observe"
mkdir -p "$OUT"
READY="$OUT/ready.$$"
REPORT="$OUT/report.$$.json"
rm -f "$READY"

{ echo "globalThis.OBS = {\"space\": $SPACE, \"expect\": $EXPECT, \"timeout\": ${OBS_TIMEOUT:-15000}, \"ready\": \"$READY\"};"
  cat "$DIR/browser_observe.js"; } | ego-browser nodejs > "$REPORT" 2>&1 &
OBS_PID=$!

for _ in $(seq 1 300); do
    [[ -f "$READY" ]] && break
    sleep 0.1
done
[[ -f "$READY" ]] || { echo "observer did not start" >&2; cat "$REPORT" >&2; exit 1; }

START="$(python3 -c 'import time; print(int(time.time() * 1000))')"
"$@" > "$OUT/write.$$.log" 2>&1
END="$(python3 -c 'import time; print(int(time.time() * 1000))')"

wait "$OBS_PID" || true
python3 - "$REPORT" "$START" "$END" "$OUT/write.$$.log" <<'EOF'
import json, sys
report_path, start, end, log = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
raw = open(report_path).read().strip().splitlines()
report = json.loads([l for l in raw if l.startswith("{")][-1])
for tab in report.values():
    for shape in tab["newShapes"].values():
        shape["msAfterWriteStart"] = shape["seenAt"] - start
        shape["msAfterWriteEnd"] = shape["seenAt"] - end
print(json.dumps({"writeStart": start, "writeEnd": end, "writeMs": end - start,
                  "writeLog": log, "tabs": report}, indent=2))
EOF
rm -f "$READY"
