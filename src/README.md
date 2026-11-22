# NUTCADE source

`python3 build.py` (in the repository root) inlines these files into `public/index.html`, which is the app. Edit here, build, and commit both `src/` and `public/index.html`; CI fails if they don't match.

| File | What it is |
|---|---|
| `template.html` | The page shell: meta tags, link previews, and `/*@@file@@*/` markers where each file below is inlined |
| `style.css` | All styles: the arcade-cabinet look, themes, and every screen |
| `fonts.css` | Press Start 2P and VT323, embedded so nothing loads from other servers |
| `app.js` | The wallet: storage and PIN vault, recovery phrase, mints, sending and receiving, Nostr, contacts, settings, every screen |
| `app_r4.js` | Round 4, inlined inside `app.js`: send by sound, refundable gifts, bill split, mint health, cashier mode, challenges, piggy bank |
| `app_r4_actions.js` | Round 4 button handlers, also inlined inside `app.js` |
| `app_r5.js` | Round 5, inlined inside `app.js`: high-score bounties (NUT-14), Extra Life (NUT-11 inheritance), mint report card |
| `app_r5_actions.js` | Round 5 button handlers, also inlined inside `app.js` |
| `app_r6.js` | Round 6, inlined inside `app.js`: treasure hunts (Shamir-split keys, prize on Nostr) and loaded score cards |
| `app_r6_actions.js` | Round 6 button handlers, also inlined inside `app.js` |
| `app_r7.js` | Round 7 (1.12), inlined inside `app.js`: LNURL-withdraw vouchers, blocked mints, Nostr Wallet Connect (the wallet side of NIP-47) and zaps (NIP-57) |
| `app_r7_actions.js` | Round 7 button handlers, also inlined inside `app.js` |
| `app_r8.js` | Round 8 (1.13), inlined inside `app.js`: the spending limit, the duress PIN (a second, separate wallet in the PIN vault), and mints that limit request size (NUT-06 `max_array_length`) |
| `app_r8_actions.js` | Round 8 button handlers, also inlined inside `app.js` |
| `app_r9.js` | Round 9 (1.14), inlined inside `app.js`: the keyset check-up (coins on a mint's retired or expiring keys moved to its current keys, tiny coins combined, coins the mint no longer accepts set aside) |
| `app_r9_actions.js` | Round 9 button handlers, also inlined inside `app.js` |
| `app_tokens.js` | Printable NUTCADE tokens and the QR code center (the acorn in QR codes, read back), inlined inside `app.js`; it also holds `qrCanvas` |
| `app_tokens_actions.js` | Printable tokens button handlers, also inlined inside `app.js` |
| `app_arrive.js` | Notices when money arrives, inlined inside `app.js`: a notice per arrival, the "while you were away" summary, optional system notifications (shown by the page or its service worker; no server, nothing sent anywhere) |
| `app_arrive_actions.js` | The notices' buttons, also inlined inside `app.js` |
| `arrive.css` | The notices' styles |
| `ur.js` | Animated QR codes: a BC-UR encoder and decoder (`ur:bytes`, multipart fountain codes), compatible with cashu.me |
| `chiptune.js` | The sound modem used by Send by sound (encoder, decoder, microphone and speaker) |
| `games.js` | The arcade engine (a fixed 60 steps a second clock, replays, challenges, the lobby), the eight original cabinets, and the shared kit it hands to every cabinet in a `game_*.js` file |
| `game_poker.js` | Nut Poker: free-credit video poker, a cabinet in its own file (its rules are unit-tested in `tests/game_poker_unit.js`) |
| `game_neonroad.js` | Neon Road: a pseudo-3D racer, a cabinet in its own file |
| `app_trust.js` | Trust & help, inlined inside `app.js`: the check of your 12 words, "Updated to vX" and "new version ready", Help & FAQ (the topic texts), a mint's contact, terms and description (NUT-06), Hide amounts. Nothing in it moves money |
| `app_trust_actions.js` | Trust & help button handlers, also inlined inside `app.js` |
| `app_sendall.js` | Send all (1.22), inlined inside `app.js`: everything at the active mint, less the fees, as an ecash token, to a Lightning address or LNURL, or on-chain (the amount worked out from the mint's quotes, shown before anything is sent) |
| `app_sendall_actions.js` | Send all button handlers, also inlined inside `app.js` |
| `app_backup.js` | Better backups (1.23), inlined inside `app.js`: the optional password on the backup file (PBKDF2-SHA256 and AES-256-GCM), contacts, settings, trophies and arcade progress in the file, and Back up / Restore with my phone (a passkey's PRF output locks the 12 words; the locked copy is kept on Nostr relays). Never offered by the duress PIN's wallet |
| `app_dleq.js` | Offline token check (1.26), inlined inside `app.js`: secp256k1 and NUT-12 DLEQ verification, each mint's public keys saved when it is loaded, and the check run on a token saved while offline (a token its mint didn't sign is refused). Nothing in it moves money or talks to the network |
| `app_backup_actions.js` | Better backups button handlers, also inlined inside `app.js` |
| `app_nutzap.js` | Nutzaps (1.28, NIP-61), inlined inside `app.js`: your nutzap info (kind 10019: relays, mints, the P2PK receiving key), nutzaps received (kind 9321 on your relays: checked, saved as a waiting line, claimed once through the journal) and sent (their 10019 looked up, coins locked to their key with the usual send, the event made once and kept until a relay takes it). Opt-in, off by default; never in the duress PIN's wallet |
| `app_nutzap_actions.js` | Nutzaps button handlers, also inlined inside `app.js` |
| `app_p2bk.js` | Pay to Blinded Key (1.29, NUT-28), inlined inside `app.js`: the "Hide who gets it (P2BK)" setting (off by default, per wallet), and our own check of a key blinded for us with a coin's `p2pk_e` (a nutzap's lock, a bounty sent to us). The blinding itself is cashu-ts `blindKeys`, applied only in `sendEcashNow` (`opts.blind`, from gifts, bounties and nutzaps); claiming derives the keys from `p2pk_e` in cashu-ts. Extra Life and treasure hunts are never blinded |
| `daily.js`, `app_daily.js` | The Daily Challenge (the date, seed, pick, streak, share note); `app_daily.js` is inlined inside `app.js` |
| `i18n_daily.js` | Daily Challenge translations; generated by `python3 tools/i18n_daily.py` |
| `trophies.js` | Trophies and share cards |
| `price.js` | The live Bitcoin price chart |
| `audio.js` | Sound effects and music |
| `i18n.js` | Translations (Spanish, Portuguese, German, French) for everything up to Round 3 |
| `i18n_trust.js` | Trust & help translations (Help & FAQ and the rest); generated by `python3 tools/i18n_trust.py`, so edit that file, not this one |
| `i18n_r4.js` | Translations added since; generated by `python3 tools/i18n_r4.py` from `tools/i18n_r4.py`, so edit that file, not this one |
| `i18n_arrive.js` | The notices' translations; generated by `python3 tools/i18n_arrive.py`, so edit that file, not this one |
| `i18n_tokens.js` | Translations for printable tokens and the QR code center; generated by `python3 tools/i18n_tokens.py` |
| `lib.min.js` | Prebuilt bundle of the libraries listed under "Open-source components" in the main README (cashu-ts, noble, scure, nostr-tools, qrcode-generator, jsQR, zxing-wasm loader), unchanged; their licence texts are in `public/THIRD_PARTY_LICENSES.txt` (the noble and scure banners also stay at its end) |

### Adding a cabinet

Every cabinet that is not one of the original eight lives in its own file, `src/game_<name>.js`, and joins the arcade the same way (Nut Poker and Neon Road do):

1. The file registers one factory, and nothing else touches `games.js`:
   ```js
   (window.NutCabinets = window.NutCabinets || []).push(function (K) {
     'use strict';
     const { W, H, C, Math, A, T, store, spr, text, rnd, ri, RNG, clamp, boom, tickFx, drawFx, hiOf, qualifies, addScore } = K;
     // ... the cabinet ...
     return { id: 'myGame', name: 'MY GAME', year: '1985', blurb: '...', track: 'action', help: '...', keys: '...', init(G, seed) {}, update(s, G) {}, draw(s, G, ctx) {}, thumb(ctx, t) {} };
   });
   ```
   `K` is the kit `games.js` builds once: the canvas size and colours, the deterministic `Math` (use it, not the browser's, for anything that affects play), the drawing helpers, `rnd`/`ri`/`RNG` (the seeded game randomness) and `K.withSeed(seed, fn)` for tests. The factory is called once, in script order, so the order of the `<script>` lines in `template.html` is the order in the lobby (after the eight originals).
2. Add `<script>/*@@game_<name>.js@@*/</script>` to `template.html`, before `games.js`.
3. Optional flags on the cabinet object: `daily: true` (can be the Daily Challenge; all gameplay randomness must come from `rnd`/`ri`/`RNG`), `noChallenge: true` (no challenges, replays or daily; for games that are random by design), `noSats: true` (its score card can never carry sats), `noStick: true`, `onKey(code, state, mode, event)` and `onExit(state, G)`.
4. Add its strings to `tools/i18n_r4.py` (or its own `tools/i18n_<name>.py` called from there) and regenerate; add a trophy to `trophies.js` if it has one. The GRAND TOUR trophy and the lobby count follow the cabinet list by themselves.
5. Cabinets update at 60 steps a second whatever the screen: count steps (`s.t++`), never time.

**Keys from the 12 words.** Everything comes from the BIP-39 seed of the 12 words, so a restore brings it all back: the ecash itself (NUT-13, `m/129372'/0'/<keyset>'/<counter>'/<0|1>`, done by cashu-ts), the Nostr key (the first 32 bytes of the seed, as cashu.me; also the key gifts and Extra Life lock to, as "02" + its x-only key), the mint-list backup key (sha256(seed ‖ "cashu-mint-backup")) and the **nutzap receiving key** (NIP-61): BIP-32 `m/129372'/61'/0'/0'/0'` (Cashu's purpose 129372', branch 61' for NIP-61), its private key negated if needed so its public key starts with 02, published in kind 10019 as "02" + x. It is deliberately not the Nostr key (NIP-61 forbids that). Changing that path would strand nutzaps locked to the old key, so never change it.

**Releases.** Update `WHATS_NEW` in `app_trust.js` (the lines "Updated to vX" shows) when you set the version number, and add the version to `APP_VERSION` in `app.js`: the update notice compares that number with the one in the live `index.html`. Other features can add Help topics with `window.NutHelpTopics.push({ q, a: [paragraphs] })` before the Help sheet opens (the printed tokens' first-scan rule is meant to arrive this way, with its text in the translation tool).

To add a translation, add a row to `tools/i18n_r4.py` (English first, then es, pt, de, fr) and run it. Text is matched whole and numbers are kept, so "Pay {#} SAT" matches "Pay 1,000 SAT".

`node tools/chiptune_sim.js` runs the sound modem through a simulated noisy, echoing channel.
