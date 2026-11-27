#!/usr/bin/env bash
# Tests tools/release.sh without touching GitHub, the live site or your real key: a throwaway gpg key, a local stand-in for GitHub
# (a bare repository and a fake `gh`), and a local web server for the site. Run: bash tests/release_script_test.sh
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d); SRV=''; trap '[ -n "$SRV" ] && kill "$SRV" 2>/dev/null; rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { if eval "$2"; then echo "PASS $1"; pass=$((pass + 1)); else echo "FAIL $1"; fail=$((fail + 1)); fi; }
export GNUPGHOME=$T/gnupg; mkdir -m 700 "$GNUPGHOME"
gpg --batch --quiet --passphrase '' --quick-gen-key 'release test' ed25519 sign 1d 2>/dev/null
FPR=$(gpg --with-colons --list-secret-keys | awk -F: '/^fpr/ {print $10; exit}')
# GitHub: a bare repository with main (the page at version 9.9.9), and a fake gh that keeps releases in a folder
V=9.9.9
mkdir -p "$T/gh/Random21m"; git init -q --bare "$T/gh/Random21m/nutcade.git"
git clone -q "$T/gh/Random21m/nutcade.git" "$T/work" 2>/dev/null; cd "$T/work"
mkdir -p public tools; cp "$ROOT/tools/release.sh" tools/
printf "<script>\nconst APP_VERSION = '%s';\n</script>\n" "$V" > public/index.html; printf 'sw\n' > public/sw.js; printf 'wasm\n' > public/zxing_reader.wasm
git add -A; git -c user.name=t -c user.email=t@t commit -q -m one; git push -q origin HEAD:main 2>/dev/null; git branch -q -u origin/main 2>/dev/null || true
mkdir -p "$T/site"; (cd public && sha256sum index.html sw.js zxing_reader.wasm) > "$T/site/SHA256SUMS.txt"
python3 -m http.server 0 --bind 127.0.0.1 --directory "$T/site" > "$T/http.log" 2>&1 < /dev/null & SRV=$!
for i in $(seq 50); do PORT=$(grep -o 'port [0-9]*' "$T/http.log" | grep -o '[0-9]*' || true); [ -n "$PORT" ] && break; sleep 0.1; done
mkdir -p "$T/bin" "$T/rel"
cat > "$T/bin/gh" <<EOF
#!/usr/bin/env bash
# fake gh: release view / create / download, and api (the notes)
R=$T/rel
case "\$1 \$2" in
  "release view") [ -d "\$R/\$3" ] ;;
  "release create") tag=\$3; shift 3; target=""; notes=""; files=()
    while [ \$# -gt 0 ]; do case "\$1" in -R|--title) shift 2;; --target) target=\$2; shift 2;; --notes-file) notes=\$2; shift 2;; *) files+=("\$1"); shift;; esac; done
    mkdir -p "\$R/\$tag"; cp "\${files[@]}" "\$R/\$tag/"; cp "\$notes" "\$R/\$tag/notes.md"; git -C $T/gh/Random21m/nutcade.git tag "\$tag" "\$target" ;;
  "release download") tag=\$3; shift 3; dir=""; while [ \$# -gt 0 ]; do case "\$1" in -D) dir=\$2; shift 2;; *) shift;; esac; done
    cp "\$R/\$tag/SHA256SUMS.txt" "\$R/\$tag/SHA256SUMS.txt.asc" "\$dir/" ;;
  "api -H") [ -f "$T/notes/\${4##*/}" ] && cat "$T/notes/\${4##*/}" || exit 1 ;;
  *) echo "fake gh: \$*" >&2; exit 2 ;;
esac
EOF
chmod +x "$T/bin/gh"; mkdir -p "$T/notes"; printf 'Notes for v%s from the notebook\n' "$V" > "$T/notes/nutcade-v$V-notes.md"
export PATH="$T/bin:$PATH" NC_SIGNING_FPR=$FPR NC_SITE="http://127.0.0.1:$PORT" NC_REMOTE_OK=1
run() { (cd "$T/work" && echo "${2:-yes}" | bash tools/release.sh "$1" > "$T/out" 2>&1); }
# --pending: the version is live and not released yet
P1=$(cd "$T/work" && bash tools/release.sh --pending 2>/dev/null)
ok "--pending prints the version main has, and changes nothing" '[ "$P1" = "$V" ] && [ ! -d "$T/rel/v$V" ]'
# a wrong version is refused before anything is signed
run 9.9.8 && r=0 || r=$?
ok "a version main's page does not have is refused" '[ $r -ne 0 ] && grep -q "not 9.9.8" "$T/out" && [ ! -d "$T/rel/v9.9.8" ]'
# the site still on the old files: refused
cp "$T/site/SHA256SUMS.txt" "$T/sums.keep"; sed -i '1s/^./0/' "$T/site/SHA256SUMS.txt"
run $V && r=0 || r=$?
ok "a site that is not main yet is refused (nothing signed, no release)" '[ $r -ne 0 ] && grep -q "not the one in main" "$T/out" && [ ! -d "$T/rel/v$V" ]'
cp "$T/sums.keep" "$T/site/SHA256SUMS.txt"
# no is no
run $V no && r=0 || r=$?
ok "not typing yes signs nothing" '[ $r -ne 0 ] && grep -q "you did not type yes" "$T/out" && [ ! -d "$T/rel/v$V" ]'
# the real run: no version given, RELEASE_YES=1 (as the one-line release-all runs it)
(cd "$T/work" && RELEASE_YES=1 bash tools/release.sh < /dev/null > "$T/out" 2>&1) && r=0 || r=$?
ok "the release is made: signed checksums, the notebook's notes, the tag on main" '[ $r -eq 0 ] && grep -q "Done. Tell Claude" "$T/out" && gpg --verify "$T/rel/v$V/SHA256SUMS.txt.asc" "$T/rel/v$V/SHA256SUMS.txt" 2>/dev/null && cmp -s "$T/rel/v$V/SHA256SUMS.txt" "$T/site/SHA256SUMS.txt" && grep -q "from the notebook" "$T/rel/v$V/notes.md" && [ "$(git -C "$T/gh/Random21m/nutcade.git" rev-parse v$V)" = "$(git -C "$T/gh/Random21m/nutcade.git" rev-parse main)" ]'
# after: --pending prints nothing; with no version it says nothing to do
P2=$(cd "$T/work" && bash tools/release.sh --pending 2>/dev/null)
(cd "$T/work" && bash tools/release.sh < /dev/null > "$T/out" 2>&1) && r=0 || r=$?
ok "once released: --pending prints nothing, and with no version it says nothing to do" '[ -z "$P2" ] && [ $r -eq 0 ] && grep -q "already released" "$T/out"'
# and not twice
run $V && r=0 || r=$?
ok "a release that exists already is refused" '[ $r -ne 0 ] && grep -q "already exists" "$T/out"'
echo; echo "release.sh: $pass passed, $fail failed"; [ "$fail" -eq 0 ]
