<p align="center"><img src="logo.png" alt="NUTCADE" width="560"></p>

# NUTCADE

A Cashu ecash wallet with a 1980s arcade built in.

**Play it:** https://nutcade-2c150c.gitlab.io

- Send and receive ecash, Lightning and on-chain Bitcoin (on-chain needs a mint that supports NUT-30)
- Pick mints from a curated list, by address, or from Nostr recommendations (NIP-87)
- Private notes on every transaction, searchable
- Seven original arcade games with high scores, chiptune sound and music
- Install it to your phone's home screen from the browser's share or menu button
- 12-word recovery phrase with restore on any device

The whole app is one file: `public/index.html`. GitLab Pages serves it from the `public/` folder.

## Safety

- **12-word recovery phrase.** NUTCADE uses Cashu's standard deterministic secrets (NUT-13). Write the phrase down when you create your wallet; with it, **Restore from recovery phrase** rebuilds your balance on any device by scanning your mints (NUT-09). Keep a list of the mints you use next to your words.
- **Find lost ecash** (Mints tab) rescans your mints if a payment was interrupted.
- **One tab at a time.** If NUTCADE is open in two tabs, the second one pauses so they can't overwrite each other.
- **Storage protection.** NUTCADE asks the browser not to clear its data. On iPhone, add it to your home screen so Safari keeps it.
- Wallets from before v1.1 are upgraded when you create your phrase: existing ecash is swapped into phrase-backed ecash (the mint may charge a small fee).

This is young software that hasn't been independently audited. Start with small amounts.

## Support the project

NUTCADE is free and open source, and it stays that way. Supporting it is optional and changes nothing about how it works. If you enjoy it, you can send a few sats over Lightning:

<p><img src="docs/support-qr.png" alt="QR code for the Lightning address dev@breez.tips" width="200"></p>

**dev@breez.tips**

You can also tip from inside NUTCADE: **Mints → Support NUTCADE → Donate**. The same address and code are on that screen. Be wary of any other "NUTCADE donation" address, and never send your backup or seed words to anyone, for any reason.

## Open-source components

The page bundles these MIT-licensed libraries (their license notices are at the end of the bundled script):

- [cashu-ts](https://github.com/cashubtc/cashu-ts)
- [noble-curves / noble-hashes / scure](https://paulmillr.com/noble/)
- [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator)
