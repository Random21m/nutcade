# Releasing NUTCADE

## What happens automatically

Every push to `main` that changes the app or the tests runs the **test** job first:

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
3. Only if every check passes does the **pages** job publish `public/` and write `SHA256SUMS.txt` next to the app.

Logs and screenshots from each run are kept for a week under the job's artifacts (`qa-out/`).

## On GitHub

The repository is mirrored at https://github.com/Random21m/nutcade. Its workflow, `.github/workflows/test-and-deploy.yml`, runs the same suites and then publishes to https://random21m.github.io/nutcade/ with `SHA256SUMS.txt`. Push the same commit to both remotes so the two sites serve identical files.

## Running the tests on your own computer

You need Python 3.12 and Chromium, which Playwright installs for you.

```bash
python3 -m venv /tmp/mint && /tmp/mint/bin/pip install -r tests/mint-requirements.txt && /tmp/mint/bin/pip install --no-deps cashu==0.21.0 bip32==4.0
python3 -m venv /tmp/qa && /tmp/qa/bin/pip install playwright==1.48.0 && /tmp/qa/bin/playwright install chromium
MINT_PY=/tmp/mint/bin/python QA_PY=/tmp/qa/bin/python bash tests/run_all.sh
```

## Cutting a release

1. Push the change and wait for the pipeline to pass.
2. Note the checksums at https://nutcade-2c150c.gitlab.io/SHA256SUMS.txt.
3. In GitLab, go to **Deploy → Releases → New release**, create a tag like `v1.4.0`, and paste the checksums into the release notes.

## Signing a release (recommended)

A signature proves the release came from you. Use the same GPG key you sign voidforge with:

```bash
curl -O https://nutcade-2c150c.gitlab.io/SHA256SUMS.txt
gpg --armor --detach-sign SHA256SUMS.txt        # creates SHA256SUMS.txt.asc
```

Attach `SHA256SUMS.txt` and `SHA256SUMS.txt.asc` to the release, and commit your public key as `nutcade-signing-key.asc` so others can check it.

## Checking a copy of NUTCADE

```bash
curl -O https://nutcade-2c150c.gitlab.io/index.html
sha256sum index.html                       # compare with SHA256SUMS.txt (sw.js and zxing_reader.wasm are listed too)
gpg --verify SHA256SUMS.txt.asc SHA256SUMS.txt
```
