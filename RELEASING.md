# Releasing NUTCADE

## What happens automatically

Every push runs the GitHub Actions workflow `.github/workflows/test-and-deploy.yml`; only a push to `main` deploys. Its **test** jobs come first. The suites are split into parallel jobs (grid_backup, r7, r8, polish, and two groups of the shorter ones), each starting only the mints it needs through `tests/run_all.sh --only ...`, so the whole run takes about 20 minutes. Each job does this:

1. Local Nutshell test mints start with fake Lightning: a normal one (with input fees), a no-fee one, one where every payment fails, one where every payment stays pending, and (for the units suite) one that issues sat, usd and eur ecash and one that issues only usd. `tests/mock_nostr.py` starts a stand-in Nostr relay and npub.cash server, so the tests never touch public services. The two normal mints accept multi-path payments through a small test-only patch (`tests/stub/sitecustomize.py`).
2. The browser suites run against them:
   - `tests/wallet_qa.py`: wallet flows, failed and stuck payments, backup, restore after a wipe
   - `tests/crash_qa.py`: a deposit interrupted mid-way is recovered on the next open
   - `tests/pin_qa.py`: PIN lock, encryption at rest, lockout, change and removal, passkey unlock, auto-lock, forgot PIN
   - `tests/games_smoke.py`: every cabinet starts, pauses, resumes and exits
   - `tests/round2_qa.py`: trophies and share cards, instant updates (NUT-17), the Nostr mint-list backup (NUT-27) and the npub.cash Lightning address
   - `tests/v16_qa.py`: multinut payments (NUT-15), payment requests (NUT-18) and NFC, with a stand-in NFC reader
   - `tests/r3_qa.py`: amounts in your currency, #tags and CSV export, contacts, offline use and languages
   - `tests/r4_qa.py`: sending by sound (through a simulated microphone), refundable gifts, bill split, mint health and moving sats, cashier mode, challenges, piggy bank, and the new screens in every language
   - `tests/r7_qa.py`: LNURL-withdraw vouchers (limits, service errors, timeouts, expiry, double taps), blocked mints (refusals, Unblock, backup and restore), Nostr Wallet Connect (every method, NIP-44 and NIP-04, budgets, revoke, the PIN vault) and zaps, against stand-in LNURL services and an NWC app in `mock_nostr.py`, plus the new screens in every language
   - `tests/units_qa.py`: USD, EUR and CHF ecash (a unit at a mint as its own account, deposits and pay-outs by Lightning, tokens and payment requests per unit, the sats-only features refusing, backups and restores)
   - `tests/polish_qa.py`: layout at 320, 375 and 430 px in every language (game controls, the PIN pad, the tab bar), tap-target and text sizes, toasts, themes, units, dates and translations, and centered dialogs on a computer
3. Only on `main`, and only if the page check and every test job pass, does the **deploy** job publish `public/` to https://random21m.github.io/nutcade/ and write `SHA256SUMS.txt` next to the app.

Logs and screenshots from each run are kept for a week as the run's `qa-out-<job>` artifacts (Actions tab → the run → Artifacts).

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
# or only some suites (and only the mints they need), e.g. the ones of one CI job:
MINT_PY=/tmp/mint/bin/python QA_PY=/tmp/qa/bin/python bash tests/run_all.sh --only r7,r8
```

## Cutting a release (one command)

1. Push the change to `main` and wait for the workflow to pass (Actions tab): the site then serves the new version and its `SHA256SUMS.txt`.
2. On your own computer, in your clone of nutcade:

   ```bash
   git pull
   bash tools/release.sh 1.40.0
   ```

   It checks that main's page is that version and that every file in the live `SHA256SUMS.txt` is the one in main, shows you the
   checksums (compare them with the ones Claude gave you), and after you type `yes` signs them with the release key (gpg asks for
   the key's passphrase itself; the key never leaves your computer). Then it makes the GitHub release `v1.40.0` with the notes
   from the notebook (`releases/nutcade/nutcade-v1.40.0-notes.md`, or the checksums alone if there is none) and both files,
   downloads it again and checks the files, the signature and the tag. It stops at the first thing that does not match.
   It needs git, gpg, curl and the GitHub CLI (`gh auth login` once).

The script is tested with a throwaway key and stand-ins for GitHub and the site: `bash tests/release_script_test.sh`.

## Signing by hand (if you cannot run the script)

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

Then on GitHub, **Releases → Draft a new release**, create the tag (like `v1.40.0`) on `main`, paste the notes and attach
`SHA256SUMS.txt` and `SHA256SUMS.txt.asc`. The key expires on 5 November 2028; extend it before then with `gpg --quick-set-expire 2509D11503B72CBFBCB5408F4B729F056A529340 2y` and commit the re-exported public key.

## Timestamping a release (optional)

An OpenTimestamps proof shows the checksums existed by a certain Bitcoin block, so nobody can later claim a release was made earlier or later than it was. Install the client once with `pipx install opentimestamps-client`, then, in the release folder:

```bash
ots stamp SHA256SUMS.txt                 # creates SHA256SUMS.txt.ots, pending at first
ots upgrade SHA256SUMS.txt.ots           # run again after a few hours, until it says "Timestamp complete"
ots info SHA256SUMS.txt.ots              # shows which Bitcoin block it is anchored in
```

When it's complete, edit the release on GitHub and attach `SHA256SUMS.txt.ots` too. Anyone can check it with `ots verify SHA256SUMS.txt.ots` (this needs a Bitcoin node), or by dropping both files on https://opentimestamps.org.

## Checking a copy of NUTCADE

```bash
curl -O https://random21m.github.io/nutcade/index.html
sha256sum index.html                       # compare with SHA256SUMS.txt (sw.js and zxing_reader.wasm are listed too)
gpg --import nutcade-signing-key.asc       # from this repository
gpg --verify SHA256SUMS.txt.asc SHA256SUMS.txt   # SHA256SUMS.txt.asc is attached to each release
```

The signature must say "Good signature from Random21m" and the key's fingerprint must be `2509 D115 03B7 2CBF BCB5  408F 4B72 9F05 6A52 9340`. GPG may warn that the key isn't certified by someone you trust; that's normal unless you've signed the key yourself.
