#!/usr/bin/env bash
# Rebuild the bundled libraries (src/lib.min.js) from the recipe in tools/lib/ (see src/README.md).
# Usage: tools/build_lib.sh [OUT]   (default OUT: tools/lib/out/lib.min.js; the shipped src/lib.min.js is never touched)
# Needs node and npm; installs the exact locked packages with `npm ci --ignore-scripts` (no install scripts run).
set -euo pipefail
here="$(cd "$(dirname "$0")/lib" && pwd)"
out="${1:-$here/out/lib.min.js}"
case "$out" in /*) ;; *) out="$PWD/$out";; esac
cd "$here"
npm ci --ignore-scripts --no-audit --no-fund >&2
mkdir -p "$(dirname "$out")"
node_modules/.bin/esbuild entry.js --bundle --format=iife --global-name=CashuLib --minify --log-level=warning > "$out"
echo "built $out ($(wc -c < "$out") bytes, sha256 $(sha256sum "$out" | cut -d' ' -f1))" >&2
