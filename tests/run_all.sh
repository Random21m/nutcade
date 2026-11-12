#!/usr/bin/env bash
# Runs NUTCADE's test suites against local test mints. Exits non-zero if any check fails.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PUB="$(cd "$HERE/../public" && pwd)"
export QA_OUT=${QA_OUT:-"$HERE/../qa-out"}; mkdir -p "$QA_OUT"
export NUTCADE_URL=${NUTCADE_URL:-http://localhost:8099/index.html}
PY=${QA_PY:-python3}
( cd "$PUB" && nohup "$PY" -m http.server 8099 --bind 127.0.0.1 > "$QA_OUT/http.log" 2>&1 & )
bash "$HERE/start_mints.sh" || exit 1
( nohup "${MINT_PY:-python3}" "$HERE/mock_nostr.py" 3350 > "$QA_OUT/mock_nostr.log" 2>&1 & )
for i in $(seq 1 40); do "$PY" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3350/test/state', timeout=1)" 2>/dev/null && break; sleep 0.25; done
fail=0
for suite in wallet_qa crash_qa pin_qa games_smoke round2_qa v16_qa r3_qa r4_qa r5_qa r6_qa; do
  echo "=== $suite ==="
  if ! "$PY" "$HERE/$suite.py" 2>&1 | tee "$QA_OUT/$suite.log" | grep -E "^(PASS|FAIL)|SUMMARY|Traceback|Error"; then :; fi
  if grep -q "^FAIL\|Traceback" "$QA_OUT/$suite.log"; then fail=1; echo "!!! $suite has failures"; fi
done
grep -h "^FAIL" "$QA_OUT"/*.log && echo "SOME CHECKS FAILED" || echo "ALL CHECKS PASSED"
exit $fail
