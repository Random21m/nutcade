#!/usr/bin/env bash
# Starts the local Nutshell test mints with fake Lightning:
# (fake Lightning that returns real payment preimages: see stub/sitecustomize.py)
#   3338 normal (input fees), 3339 no fees, 3340 every payment fails, 3341 every payment stays pending,
#   3342 no fees and at most 3 items per request (NUT-06 max_array_length), 3343 the same with input fees,
#   3344 no fees and at most 128 items per request (NUTCADE's minimum),
#   3345 no fees, three units (sat, usd and eur, each with its own fake Lightning), 3346 no fees, usd only (no sat at all),
#   3347 no fees and a login (NUT-21/22: clear auth to get blind auth tokens, a blind auth token on every money endpoint,
#        at most 3 tokens per request), whose login server is mock_oidc.py on 3348 (started here first),
#   3349 the same with every payment staying pending (its coins PENDING at the mint while a payment waits)
# With no arguments all eleven start. Arguments (e.g. `start_mints.sh 3338 3339`) start only those ports.
set -euo pipefail
PY=${MINT_PY:-python3}
STUB="$(cd "$(dirname "$0")" && pwd)/stub"
ROOT=${MINT_DIR:-/tmp/nutcade-mints}
PORTS=("$@"); [ ${#PORTS[@]} -gt 0 ] || PORTS=(3338 3339 3340 3341 3342 3343 3344 3345 3346 3347 3349)
want() { local p; for p in "${PORTS[@]}"; do [ "$p" = "$1" ] && return 0; done; return 1; }
start() {
  local name=$1 port=$2; shift 2
  want "$port" || return 0
  local d="$ROOT/$port"; rm -rf "$d"; mkdir -p "$d"
  ( cd "$d" && env MINT_BACKEND_BOLT11_SAT=FakeWallet MINT_PRIVATE_KEY="nutcade-test-$port" MINT_LISTEN_HOST=127.0.0.1 MINT_LISTEN_PORT=$port \
      MINT_DATABASE=data/mint FAKEWALLET_BRR=TRUE FAKEWALLET_DELAY_INCOMING_PAYMENT=0.5 FAKEWALLET_DELAY_OUTGOING_PAYMENT=0.5 \
      MINT_INFO_NAME="$name" NUTCADE_PREIMAGE_DIR="$ROOT/preimages" "$@" PYTHONPATH="$STUB" nohup "$PY" -m uvicorn cashu.mint.app:app --host 127.0.0.1 --port $port > "$d/log" 2>&1 & )
}
if want 3347 || want 3349; then   # (the auth mint reads its login server's discovery document when it starts)
  mkdir -p "$ROOT/oidc"; ( nohup "$PY" "$(dirname "$STUB")/mock_oidc.py" 3348 > "$ROOT/oidc/log" 2>&1 & )
  for i in $(seq 1 60); do "$PY" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3348/test/state', timeout=1)" 2>/dev/null && break; sleep 0.25; done
fi
start "Mint A" 3338 NUTCADE_FAKE_MPP=1
start "Mint B" 3339 MINT_INPUT_FEE_PPK=0 NUTCADE_FAKE_MPP=1
start "Fail Mint" 3340 MINT_INPUT_FEE_PPK=0 FAKEWALLET_PAY_INVOICE_STATE=FAILED FAKEWALLET_PAYMENT_STATE=FAILED
start "Pending Mint" 3341 MINT_INPUT_FEE_PPK=0 FAKEWALLET_PAY_INVOICE_STATE=PENDING FAKEWALLET_PAYMENT_STATE=PENDING
start "Small Mint" 3342 MINT_INPUT_FEE_PPK=0 MINT_MAX_REQUEST_LENGTH=3 NUTCADE_FAKE_MPP=1
start "Small Fee Mint" 3343 MINT_MAX_REQUEST_LENGTH=3 NUTCADE_FAKE_MPP=1
start "Mid Mint" 3344 MINT_INPUT_FEE_PPK=0 MINT_MAX_REQUEST_LENGTH=128 NUTCADE_FAKE_MPP=1
# (a keyset per unit: the unit is the second step of its derivation path, sat 0, usd 2, eur 3)
start "Multi Mint" 3345 MINT_INPUT_FEE_PPK=0 MINT_BACKEND_BOLT11_USD=FakeWallet MINT_BACKEND_BOLT11_EUR=FakeWallet MINT_DERIVATION_PATH_LIST="[\"m/0'/0'/0'\",\"m/0'/2'/0'\",\"m/0'/3'/0'\"]"
start "Dollar Mint" 3346 MINT_INPUT_FEE_PPK=0 MINT_BACKEND_BOLT11_SAT= MINT_BACKEND_BOLT11_USD=FakeWallet MINT_DERIVATION_PATH="m/0'/2'/0'"
start "Auth Mint" 3347 MINT_INPUT_FEE_PPK=0 NUTCADE_FAKE_MPP=1 MINT_REQUIRE_AUTH=TRUE MINT_AUTH_OICD_DISCOVERY_URL=http://127.0.0.1:3348/.well-known/openid-configuration \
  MINT_AUTH_OICD_CLIENT_ID=cashu-client MINT_AUTH_MAX_BLIND_TOKENS=3 MINT_AUTH_RATE_LIMIT_PER_MINUTE=10000 \
  MINT_REQUIRE_BLIND_AUTH_PATHS='[["POST","/v1/swap"],["POST","/v1/mint/quote/bolt11"],["POST","/v1/mint/bolt11"],["POST","/v1/melt/quote/bolt11"],["POST","/v1/melt/bolt11"],["POST","/v1/checkstate"],["POST","/v1/restore"]]'
start "Auth Pending Mint" 3349 MINT_INPUT_FEE_PPK=0 FAKEWALLET_PAY_INVOICE_STATE=PENDING FAKEWALLET_PAYMENT_STATE=PENDING MINT_REQUIRE_AUTH=TRUE MINT_AUTH_OICD_DISCOVERY_URL=http://127.0.0.1:3348/.well-known/openid-configuration \
  MINT_AUTH_OICD_CLIENT_ID=cashu-client MINT_AUTH_MAX_BLIND_TOKENS=3 MINT_AUTH_RATE_LIMIT_PER_MINUTE=10000 \
  MINT_REQUIRE_BLIND_AUTH_PATHS='[["POST","/v1/swap"],["POST","/v1/mint/quote/bolt11"],["POST","/v1/mint/bolt11"],["POST","/v1/melt/quote/bolt11"],["POST","/v1/melt/bolt11"],["POST","/v1/checkstate"],["POST","/v1/restore"]]'
for p in "${PORTS[@]}"; do
  up() { "$PY" -c "import urllib.request,sys; sys.exit(0 if b'pubkey' in urllib.request.urlopen('http://127.0.0.1:$1/v1/info', timeout=2).read() else 1)" 2>/dev/null; }
  for i in $(seq 1 120); do up $p && break; sleep 0.5; done
  up $p || { echo "mint $p failed to start"; tail -20 "$ROOT/$p/log"; exit 1; }
done
echo "mints ready"
