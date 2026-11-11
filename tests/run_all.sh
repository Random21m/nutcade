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
fail=0
for suite in wallet_qa crash_qa pin_qa games_smoke; do
  echo "=== $suite ==="
  if ! "$PY" "$HERE/$suite.py" 2>&1 | tee "$QA_OUT/$suite.log" | grep -E "^(PASS|FAIL)|SUMMARY|Traceback|Error"; then :; fi
  if grep -q "^FAIL\|Traceback" "$QA_OUT/$suite.log"; then fail=1; echo "!!! $suite has failures"; fi
done
grep -h "^FAIL" "$QA_OUT"/*.log && echo "SOME CHECKS FAILED" || echo "ALL CHECKS PASSED"
exit $fail
