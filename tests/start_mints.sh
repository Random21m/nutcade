#!/usr/bin/env bash
# Starts four local Nutshell test mints with fake Lightning:
# (fake Lightning that returns real payment preimages: see stub/sitecustomize.py)
#   3338 normal (input fees), 3339 no fees, 3340 every payment fails, 3341 every payment stays pending,
#   3342 no fees and at most 3 items per request (NUT-06 max_array_length), 3343 the same with input fees,
#   3344 no fees and at most 128 items per request (NUTCADE's minimum)
# With no arguments all seven start. Arguments (e.g. `start_mints.sh 3338 3339`) start only those ports.
set -euo pipefail
PY=${MINT_PY:-python3}
STUB="$(cd "$(dirname "$0")" && pwd)/stub"
ROOT=${MINT_DIR:-/tmp/nutcade-mints}
PORTS=("$@"); [ ${#PORTS[@]} -gt 0 ] || PORTS=(3338 3339 3340 3341 3342 3343 3344)
want() { local p; for p in "${PORTS[@]}"; do [ "$p" = "$1" ] && return 0; done; return 1; }
start() {
  local name=$1 port=$2; shift 2
  want "$port" || return 0
  local d="$ROOT/$port"; rm -rf "$d"; mkdir -p "$d"
  ( cd "$d" && env MINT_BACKEND_BOLT11_SAT=FakeWallet MINT_PRIVATE_KEY="nutcade-test-$port" MINT_LISTEN_HOST=127.0.0.1 MINT_LISTEN_PORT=$port \
      MINT_DATABASE=data/mint FAKEWALLET_BRR=TRUE FAKEWALLET_DELAY_INCOMING_PAYMENT=0.5 FAKEWALLET_DELAY_OUTGOING_PAYMENT=0.5 \
      MINT_INFO_NAME="$name" NUTCADE_PREIMAGE_DIR="$ROOT/preimages" "$@" PYTHONPATH="$STUB" nohup "$PY" -m uvicorn cashu.mint.app:app --host 127.0.0.1 --port $port > "$d/log" 2>&1 & )
}
start "Mint A" 3338 NUTCADE_FAKE_MPP=1
start "Mint B" 3339 MINT_INPUT_FEE_PPK=0 NUTCADE_FAKE_MPP=1
start "Fail Mint" 3340 MINT_INPUT_FEE_PPK=0 FAKEWALLET_PAY_INVOICE_STATE=FAILED FAKEWALLET_PAYMENT_STATE=FAILED
start "Pending Mint" 3341 MINT_INPUT_FEE_PPK=0 FAKEWALLET_PAY_INVOICE_STATE=PENDING FAKEWALLET_PAYMENT_STATE=PENDING
start "Small Mint" 3342 MINT_INPUT_FEE_PPK=0 MINT_MAX_REQUEST_LENGTH=3 NUTCADE_FAKE_MPP=1
start "Small Fee Mint" 3343 MINT_MAX_REQUEST_LENGTH=3 NUTCADE_FAKE_MPP=1
start "Mid Mint" 3344 MINT_INPUT_FEE_PPK=0 MINT_MAX_REQUEST_LENGTH=128 NUTCADE_FAKE_MPP=1
for p in "${PORTS[@]}"; do
  up() { "$PY" -c "import urllib.request,sys; sys.exit(0 if b'pubkey' in urllib.request.urlopen('http://127.0.0.1:$1/v1/info', timeout=2).read() else 1)" 2>/dev/null; }
  for i in $(seq 1 120); do up $p && break; sleep 0.5; done
  up $p || { echo "mint $p failed to start"; tail -20 "$ROOT/$p/log"; exit 1; }
done
echo "mints ready"
