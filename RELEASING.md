# Releasing NUTCADE

## What happens automatically

Every push to `main` runs the GitHub Actions workflow `.github/workflows/test-and-deploy.yml`. Its **test** job comes first:

1. Four local Nutshell test mints start with fake Lightning: a normal one (with input fees), a no-fee one, one where every payment fails, and one where every payment stays pending. `tests/mock_nostr.py` starts a stand-in Nostr relay and npub.cash server, so the tests never touch public services. The two normal mints accept multi-path payments through a small test-only patch (`tests/stub/sitecustomize.py`).
2. The browser suites run against them:
   - `tests/wallet_qa.py`: wallet flows, failed and stuck payments, backup, restore after a wipe
   - `tests/crash_qa.py`: a deposit interrupted mid-way is recovered on the next open
   - `tests/pin_qa.py`: PIN lock, encryption at rest, lockout, change and removal, passkey unlock, auto-lock, forgot PIN
   - `tests/games_smoke.py`: every cabinet starts, pauses, resumes and exits
   - `tests/round2_qa.py`: trophies and share cards, instant updates (NUT-17), the Nostr mint-list backup (NUT-27) and the npub.cash Lightning address
   - `tests/v16_qa.py`: multinut payments (NUT-15), payment requests (NUT-18) and NFC, with a stand-in NFC reader
   - `tests/r3_qa.py`: amounts in your currency, #tags and CSV export, contacts, offline use and languages
   - `tests/r4_qa.py`: sending by sound (through a simulated microphone), refundable gifts, bill split, mint health and moving sats, cashier mode, challenges, piggy bank, and the new screens in every language
3. Only if every check passes does the **deploy** job publish `public/` to https://random21m.github.io/nutcade/ and write `SHA256SUMS.txt` next to the app.

Logs and screenshots from each run are kept for a week as the run's `qa-out` artifact (Actions tab → the run → Artifacts).

## Making a change

1. Edit the files in `src/` (see [src/README.md](src/README.md)). For new on-screen text, add its translations to `tools/i18n_r4.py` and run `python3 tools/i18n_r4.py`.
2. Run `python3 build.py` to rebuild `public/index.html`.
3. Run the tests (below), then commit `src/` and `public/index.html` together. CI refuses a page that doesn't match `src/`.

## Running the tests on your own computer

You need Python 3.12 and Chromium, which Playwright installs for you.

```bash
python3 -m venv /tmp/mint && /tmp/mint/bin/pip install -r tests/mint-requirements.txt && /tmp/mint/bin/pip install --no-deps cashu==0.21.0 bip32==4.0
python3 -m venv /tmp/qa && /tmp/qa/bin/pip install playwright==1.48.0 && /tmp/qa/bin/playwright install chromium
MINT_PY=/tmp/mint/bin/python QA_PY=/tmp/qa/bin/python bash tests/run_all.sh
```

## Cutting a release

1. Push the change and wait for the workflow to pass (Actions tab).
2. Note the checksums at https://random21m.github.io/nutcade/SHA256SUMS.txt.
3. On GitHub, go to **Releases → Draft a new release**, create a tag like `v1.8.1`, and paste the checksums into the release notes.

## Signing a release (recommended)

A signature proves the release came from the project. Releases are signed with the key in `nutcade-signing-key.asc`:

```
Random21m
ed25519 key 4B729F056A529340
fingerprint 2509 D115 03B7 2CBF BCB5  408F 4B72 9F05 6A52 9340
```

```bash
curl -O https://random21m.github.io/nutcade/SHA256SUMS.txt
gpg --armor --detach-sign --local-user 4B729F056A529340 SHA256SUMS.txt   # creates SHA256SUMS.txt.asc
gpg --verify SHA256SUMS.txt.asc SHA256SUMS.txt                           # should say "Good signature"
```

Then edit the release on GitHub and attach `SHA256SUMS.txt` and `SHA256SUMS.txt.asc`. The key expires on 5 November 2028; extend it before then with `gpg --quick-set-expire 2509D11503B72CBFBCB5408F4B729F056A529340 2y` and commit the re-exported public key.

## Checking a copy of NUTCADE

```bash
curl -O https://random21m.github.io/nutcade/index.html
sha256sum index.html                       # compare with SHA256SUMS.txt (sw.js and zxing_reader.wasm are listed too)
gpg --import nutcade-signing-key.asc       # from this repository
gpg --verify SHA256SUMS.txt.asc SHA256SUMS.txt   # SHA256SUMS.txt.asc is attached to each release
```

The signature must say "Good signature from Random21m" and the key's fingerprint must be `2509 D115 03B7 2CBF BCB5  408F 4B72 9F05 6A52 9340`. GPG may warn that the key isn't certified by someone you trust; that's normal unless you've signed the key yourself.
