<p align="center"><img src="logo.png" alt="NUTCADE" width="560"></p>

# NUTCADE

A Cashu ecash wallet with a 1980s arcade built in.

**Play it:** https://nutcade-2c150c.gitlab.io

- Send and receive ecash, Lightning and on-chain Bitcoin (on-chain needs a mint that supports NUT-30)
- Pick mints from a curated list, by address, or from Nostr recommendations (NIP-87)
- Private notes on every transaction, searchable
- Seven original arcade games with high scores, chiptune sound and music
- Install it to your phone's home screen from the browser's share or menu button

The whole app is one file: `public/index.html`. GitLab Pages serves it from the `public/` folder.

## Important

Ecash is stored only in the browser that received it. There is no seed-phrase recovery yet.
Use **Mints → Copy backup** regularly and start with small amounts or a test mint.

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
