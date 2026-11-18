#!/usr/bin/env bash
# Runs NUTCADE's test suites against local test mints. Exits non-zero if any check fails.
#   bash tests/run_all.sh                  every suite (all mints)
#   bash tests/run_all.sh --only r7,r8     only those suites, and only the mints they need
#   (names are the suite file names, with or without the _qa suffix: wallet, crash, pin, games_smoke, round2,
#    v16, r3 ... r9, grid_backup, polish, game_loop, game_daily, game_poker, game_neonroad. The CI runs the suites as parallel jobs this way.)
set -uo pipefail
ALL="wallet_qa crash_qa pin_qa games_smoke game_loop_qa game_daily_qa game_poker_qa game_neonroad_qa round2_qa v16_qa r3_qa r4_qa r5_qa r6_qa r7_qa grid_backup_qa polish_qa r8_qa r9_qa"
SUITES="$ALL"; ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --only) [ $# -ge 2 ] || { echo "--only needs a comma-separated list of suites"; exit 2; }; ONLY="$2"; shift 2 ;;
    --only=*) ONLY="${1#--only=}"; shift ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1 (try --help)"; exit 2 ;;
  esac
done
if [ -n "$ONLY" ]; then
  SUITES=""
  for n in ${ONLY//,/ }; do
    m=""; for s in $ALL; do [ "$s" = "$n" ] || [ "$s" = "${n}_qa" ] && m="$s"; done
    [ -n "$m" ] || { echo "unknown suite: $n (known: $ALL)"; exit 2; }
    SUITES="$SUITES $m"
  done
fi
# the mints each suite needs (a suite that adds no mint of its own still gets the wallet_qa defaults, 3338-3341)
ports_for() { case "$1" in
  r7_qa|grid_backup_qa|polish_qa) echo "3338 3339 3340" ;;
  r8_qa) echo "3338 3339 3340 3342 3343 3344" ;;
  r9_qa) echo "3338" ;;   # (r9 starts and restarts mints of its own, R9_PORT 3438-3441, to rotate their keys)
  *) echo "3338 3339 3340 3341" ;; esac; }
if [ -n "$ONLY" ]; then PORTS=$(for s in $SUITES; do ports_for "$s"; done | tr ' ' '\n' | sort -u | tr '\n' ' '); else PORTS=""; fi
HERE="$(cd "$(dirname "$0")" && pwd)"
PUB="$(cd "$HERE/../public" && pwd)"
export QA_OUT=${QA_OUT:-"$HERE/../qa-out"}; mkdir -p "$QA_OUT"
export NUTCADE_URL=${NUTCADE_URL:-http://localhost:8099/index.html}
PY=${QA_PY:-python3}
( cd "$PUB" && nohup "$PY" -m http.server 8099 --bind 127.0.0.1 > "$QA_OUT/http.log" 2>&1 & )
bash "$HERE/start_mints.sh" $PORTS || exit 1
( nohup "${MINT_PY:-python3}" "$HERE/mock_nostr.py" 3350 > "$QA_OUT/mock_nostr.log" 2>&1 & )
for i in $(seq 1 40); do "$PY" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3350/test/state', timeout=1)" 2>/dev/null && break; sleep 0.25; done
fail=0
for suite in $SUITES; do
  echo "=== $suite ==="
  if ! "$PY" "$HERE/$suite.py" 2>&1 | tee "$QA_OUT/$suite.log" | grep -E "^(PASS|FAIL)|SUMMARY|Traceback|Error"; then :; fi
  if grep -q "^FAIL\|Traceback" "$QA_OUT/$suite.log"; then fail=1; echo "!!! $suite has failures"; fi
done
grep -h "^FAIL" "$QA_OUT"/*.log && echo "SOME CHECKS FAILED" || echo "ALL CHECKS PASSED"
exit $fail
