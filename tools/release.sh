#!/usr/bin/env bash
# NUTCADE release in one command. On your own computer, in your clone of nutcade, after main is pushed and the site has
# deployed (the Actions run is green):
#
#   paste the one line in RELEASING.md (it runs this for every project that needs it), or by hand, in the clone:
#   bash tools/release.sh            (finds the version on main itself)
#   bash tools/release.sh 1.40.0     (or say which version it must be)
#   bash tools/release.sh --pending  (only prints the version if it is live but not released yet; changes nothing)
#
# 1. gets main from GitHub and reads the version on the page
# 2. downloads the live SHA256SUMS.txt and checks every file in it is the one in main (so the site is this release)
# 3. shows you the checksums and, after you type yes (RELEASE_YES=1: already said), signs SHA256SUMS.txt with your key (gpg asks for its passphrase itself)
# 4. makes the GitHub release vX: the notes (the checksums, signed with the release key), SHA256SUMS.txt and its signature
# 5. downloads the release again and checks the files, the signature and the tag
#
# Your private key never leaves this computer, and this script never sees its passphrase. Every step checks before it acts and
# stops at the first thing that does not match. Needs: git, gpg, gh (logged in: gh auth login), curl.
set -euo pipefail

RELEASE_KEY=2509D11503B72CBFBCB5408F4B729F056A529340   # the release key in RELEASING.md and nutcade-signing-key.asc
FPR=${NC_SIGNING_FPR:-$RELEASE_KEY}
REPO=${NC_REPO:-Random21m/nutcade}
REMOTE=${NC_REMOTE:-origin}
SITE=${NC_SITE:-https://random21m.github.io/nutcade}

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32mOK\033[0m  %s\n' "$*"; }
die()  { printf '\n\033[31mSTOP:\033[0m %s\nNothing after this point was done.\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "$1 is not installed. $2"; }
sha()  { if command -v sha256sum >/dev/null 2>&1; then sha256sum | cut -d' ' -f1; else shasum -a 256 | cut -d' ' -f1; fi; }

MODE=release; V=
case "${1:-}" in
  -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
  --pending) MODE=pending ;;
  "") ;;
  *) V=${1#v} ;;
esac
[ -z "$V" ] || [[ $V =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "the version should look like 1.40.0"
need git "Install git."; need gpg "Install GnuPG."; need gh "Install the GitHub CLI and run: gh auth login"; need curl "Install curl."
git rev-parse --show-toplevel >/dev/null 2>&1 || die "run this inside your clone of nutcade."
cd "$(git rev-parse --show-toplevel)"
[ "$FPR" = "$RELEASE_KEY" ] || printf '\n\033[33mNOTE:\033[0m signing and checking with %s, NOT the release key (NC_SIGNING_FPR is set). Only for testing.\n' "$FPR" >&2
shopt -s nocasematch   # GitHub names are not case-sensitive
case "$(git remote get-url "$REMOTE" 2>/dev/null)" in
  *"$REPO"|*"$REPO.git"|*"$REPO/") ;;
  *) [ -n "${NC_REMOTE_OK:-}" ] || die "the remote \"$REMOTE\" is $(git remote get-url "$REMOTE" 2>/dev/null || echo missing), not github.com/$REPO." ;;
esac
shopt -u nocasematch
[ "$MODE" = pending ] || gpg --list-secret-keys "$FPR" >/dev/null 2>&1 || die "the release key $FPR is not on this computer."

[ "$MODE" = pending ] || say "1/5  Getting main from GitHub"
git fetch -q "$REMOTE" main || die "could not fetch main."
M=$(git rev-parse FETCH_HEAD)
PV=$(git show "$M:public/index.html" | grep -o "const APP_VERSION = '[0-9.]*'" | head -1 | grep -o "[0-9][0-9.]*" || true)
[ -n "$PV" ] || die "could not read the version on main's page."
if [ "$MODE" = pending ]; then
  gh release view "v$PV" -R "$REPO" >/dev/null 2>&1 || echo "$PV"
  exit 0
fi
ok "main is $(git log --oneline -1 "$M")"
if [ -z "$V" ]; then
  V=$PV
  if gh release view "v$V" -R "$REPO" >/dev/null 2>&1; then say "NUTCADE $V is already released. Nothing to do."; exit 0; fi
fi
TAG=v$V
[ "$PV" = "$V" ] || die "main's page says it is $PV, not $V. Push the release to main first."
ok "main's page is $V"
! gh release view "$TAG" -R "$REPO" >/dev/null 2>&1 || die "a GitHub release $TAG already exists."

say "2/5  Checking the live site against main"
D=".release/$TAG"; mkdir -p "$D"; rm -f "$D/SHA256SUMS.txt" "$D/SHA256SUMS.txt.asc" "$D/notes.md"; rm -rf "$D/check"
curl -fsS -H "Cache-Control: no-cache" -o "$D/SHA256SUMS.txt" "$SITE/SHA256SUMS.txt?$(date +%s)" || die "could not download $SITE/SHA256SUMS.txt."
n=0
while read -r h f; do
  [ -n "${f:-}" ] || continue
  w=$(git show "$M:public/$f" 2>/dev/null | sha) || true
  [ "$h" = "$w" ] || die "$f on the site is not the one in main (site $h, main $w). The site may not have deployed yet: wait until the Actions run is green, then run this again."
  ok "$f  $h"; n=$((n + 1))
done < "$D/SHA256SUMS.txt"
[ "$n" -ge 1 ] || die "the live SHA256SUMS.txt lists no files."

say "3/5  Signing"
printf '  You are signing these checksums (the live site, the same as main %s):\n\n' "${M:0:7}"
sed 's/^/    /' "$D/SHA256SUMS.txt"
printf '\n  If Claude gave you checksums for this release, they must be these.\n'
if [ "${RELEASE_YES:-}" = 1 ]; then ok "you said yes in release"; else
  read -r -p "  Type yes to sign them with $FPR: " a; [ "$a" = yes ] || die "not signed (you did not type yes)."; fi
gpg --local-user "$FPR" --armor --detach-sign --yes --output "$D/SHA256SUMS.txt.asc" "$D/SHA256SUMS.txt"
gpg --status-fd 1 --verify "$D/SHA256SUMS.txt.asc" "$D/SHA256SUMS.txt" 2>/dev/null | grep -q "^\[GNUPG:\] VALIDSIG $FPR " || die "the new signature does not verify as made by $FPR."
ok "SHA256SUMS.txt.asc is a good signature by $FPR"

say "4/5  Making the GitHub release $TAG"
{ printf 'NUTCADE %s\n\nChecksums (SHA256SUMS.txt, signed with the release key %s):\n```\n' "$TAG" "$FPR"; cat "$D/SHA256SUMS.txt"; printf '```\n'; } > "$D/notes.md"
ok "notes: the checksums, signed with the release key (edit them on GitHub later if you like)"
gh release create "$TAG" -R "$REPO" --target "$M" --title "NUTCADE $TAG" --notes-file "$D/notes.md" "$D/SHA256SUMS.txt" "$D/SHA256SUMS.txt.asc" >/dev/null
ok "released: https://github.com/$REPO/releases/tag/$TAG"

say "5/5  Checking the release"
mkdir -p "$D/check"
gh release download "$TAG" -R "$REPO" -D "$D/check" -p SHA256SUMS.txt -p SHA256SUMS.txt.asc >/dev/null || die "could not download the release files again."
cmp -s "$D/check/SHA256SUMS.txt" "$D/SHA256SUMS.txt" && cmp -s "$D/check/SHA256SUMS.txt.asc" "$D/SHA256SUMS.txt.asc" || die "the files on the release page are not the ones signed here."
gpg --status-fd 1 --verify "$D/check/SHA256SUMS.txt.asc" "$D/check/SHA256SUMS.txt" 2>/dev/null | grep -q "^\[GNUPG:\] VALIDSIG $FPR " || die "the signature on the release page does not verify."
git fetch -q "$REMOTE" "refs/tags/$TAG:refs/tags/$TAG" 2>/dev/null || true
[ "$(git rev-parse "$TAG^{commit}" 2>/dev/null || true)" = "$M" ] || die "the tag $TAG on GitHub is not main ($M)."
ok "the release page holds the signed checksums, and $TAG is main ${M:0:7}"
say "Done. Tell Claude \"published\"."
