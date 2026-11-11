# NUTCADE

A Cashu ecash wallet with a 1980s arcade built in.

- Send and receive ecash, Lightning and on-chain Bitcoin (on-chain needs a mint that supports NUT-30)
- Pick mints from a curated list, by address, or from Nostr recommendations (NIP-87)
- Private notes on every transaction, searchable
- Seven original arcade games with high scores, chiptune sound and music

The whole app is one file: `public/index.html`. GitLab Pages serves it from the `public/` folder.

## Important

Ecash is stored only in the browser that received it. There is no seed-phrase recovery yet.
Use **Mints → Copy backup** regularly and start with small amounts or a test mint.

## Open-source components

The page bundles these MIT-licensed libraries (their license notices are at the end of the bundled script):

- [cashu-ts](https://github.com/cashubtc/cashu-ts)
- [noble-curves / noble-hashes / scure](https://paulmillr.com/noble/)
- [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator)
