<p align="center"><img src="logo.png" alt="NUTCADE" width="560"></p>

# NUTCADE

A Cashu ecash wallet with a 1980s arcade built in.

**Open it:** https://nutcade-2c150c.gitlab.io

NUTCADE holds Bitcoin as Cashu ecash: fast, private payments you can send like a text message. It works in any modern browser on phone or desktop, with nothing to install, and keeps your wallet protected by a standard 12-word recovery phrase.

## Features

**Wallet**
- Send and receive **ecash**, **Lightning** and **on-chain** Bitcoin (on-chain needs a mint that supports NUT-30)
- Use several mints at once and switch between them
- Pick mints from a curated list, by address, or from recommendations on Nostr (NIP-87)
- Claim ecash from a mint you don't use yet, or swap it into your own mint over Lightning
- Private **notes on every transaction**, searchable and filterable
- **Live Bitcoin price chart** in arcade style: 1H, 1D, 1W, 1M and 1Y ranges, high and low markers, touch or hover to read any point, and your balance's value updating live
- Take back a sent token if nobody claimed it, and see when one was claimed

**Arcade**: seven original cabinets with high-score tables, chiptune sound and music

| Cabinet | Style |
|---|---|
| Star Swarm | Diving-formation space shooter |
| Nut Maze | Maze chase with a new maze every level |
| Brick Blitz | Paddle and ball |
| Void Rocks | Vector rock shooter |
| Hop Lanes | Road and river crossing |
| Sky Shield | Missile defense |
| Nibble | Snake |

Plays with keyboard, mouse, or the on-screen joystick and buttons on a phone.

**Settings**
- **Backup:** show your phrase, find lost ecash, download or import a backup file, restore a wallet from 12 words, reset the wallet
- **Look & sound:** three cabinet themes (Neon, Amber CRT, Green phosphor), sound effects, music, CRT scanlines, amounts shown as ₿
- **Privacy:** turn the live price and price chart on or off (prices come from Coinbase, in your currency), and choose whether to check if sent tokens were claimed
- **Wallet tools:** remove spent ecash and check stuck payments
- **About:** version, links and donations

## Getting started

1. Open https://nutcade-2c150c.gitlab.io. On iPhone, tap Share → **Add to Home Screen** first and open NUTCADE from that icon, so Safari keeps your wallet.
2. Tick the box to say you understand, then tap **Create a new wallet**.
3. Write your **12 words** on paper, in order. Then type back the three words NUTCADE asks for.
4. Choose a mint. Try **Testnut** first if you want to play with fake sats.
5. Tap **Receive** to add sats, and write the mints you use next to your 12 words.

### Moving from another wallet

Already have a Cashu wallet, like cashu.me or an earlier NUTCADE? On the welcome screen tap **Restore from recovery phrase**, or later go to **Settings → Backup → Restore wallet from 12 words**. Enter your 12 words and tick the mints you used. NUTCADE uses the same standard as cashu.me (NUT-13), so the same words work in both. If NUTCADE already holds sats, they move into the restored wallet.

### Starting over

**Settings → Backup → Reset wallet** deletes the wallet from this browser and returns you to the start screen to create a new one or restore one. Write down your 12 words and mints first if there are sats in it.

## Safety

- **Recovery phrase first.** You can't use the wallet until you've written down your 12 words and confirmed them. Every piece of ecash is derived from them (NUT-13), and restoring scans your mints to rebuild your balance (NUT-09).
- **Interrupted payments are handled.** A failed Lightning payment returns your sats. A stuck one is tracked until the mint settles it. A deposit interrupted mid-way is recovered automatically the next time you open the app.
- **Same phrase on two devices.** If a mint reports reused codes, NUTCADE catches up and retries on its own.
- **One tab at a time.** If NUTCADE is open in a second tab, that tab pauses so the two can't overwrite each other.
- **Storage protection.** NUTCADE asks the browser not to clear its data, and Settings shows whether that was granted.
- **No outside code.** The app is one self-contained file. Apart from its fonts, it loads nothing from other servers.

**Important:** your wallet lives in your browser. Keep your 12 words and your mint list somewhere safe and offline. Never type your words into a website or send them to anyone, including anyone claiming to be NUTCADE support. Mints hold the Bitcoin behind your ecash, so only use mints you trust. NUTCADE is young software that hasn't been independently audited, so start with small amounts.

## Testing

Each release is tested against real Cashu mints (Nutshell), including mints set up to fail or stall payments:

- 51 wallet checks: Lightning in and out, ecash between wallets, double-claim protection, failed and stuck payments, notes, multiple mints, backup files, and restoring from the phrase after a full wipe
- 27 settings checks: themes, ₿ display, backup download and import, restoring a phrase from another Cashu client, reset, and swapping received ecash into your own mint
- Crash recovery: a deposit interrupted mid-way comes back on the next open
- All seven games played through to game over, with high scores, pause, exit, touch controls and sound
- Every screen at 320, 390, 768 and 1280 pixels wide, checked for overflow and clipped text

## Privacy

NUTCADE has no account, no tracking and no analytics. Your recovery phrase and notes stay in your browser, and mints only see the ecash you exchange with them. The app contacts other services only for these things:

- **Mints**: yours for every payment, and the ones listed in the mint picker to show whether they're online
- **Coinbase**, for the price and chart, only while **Show Bitcoin price** is on
- **Nostr relays**, only when you tap "Find mints people recommend"
- **The donation address** (breez.tips), only when you tip from inside the app
- **Google Fonts**, to load the arcade fonts

## Sharing

Posting the link on X and most social sites shows a large preview card automatically. A bigger version of the picture for attaching to posts is at https://nutcade-2c150c.gitlab.io/nutcade-share.png.

## For maintainers

The whole app is one file, `public/index.html`. GitLab Pages publishes the `public/` folder on every push to `main` (see `.gitlab-ci.yml`). To ship an update, replace `public/index.html` and push. Wallets people already have keep their sats, and visitors get the new version within a few minutes.

## Support the project

NUTCADE is free and open source, and it stays that way. Supporting it is optional and changes nothing about how it works. If you enjoy it, you can send a few sats over Lightning:

<p><img src="docs/support-qr.png" alt="QR code for the Lightning address dev@breez.tips" width="200"></p>

**dev@breez.tips**

You can also tip from inside NUTCADE: **Settings → About → Donate**. The same address and code are on that screen. Be wary of any other "NUTCADE donation" address.

## Changelog

- **v1.3.0:** live Bitcoin price chart on the wallet screen, live balance value, share image and link preview for X and other social sites
- **v1.2.0:** wallet setup before entry, Settings tab, restore a wallet from 12 words (including from cashu.me), reset wallet, automatic recovery of interrupted deposits, automatic repair when one phrase is used on two devices, claiming ecash before choosing a mint, clearer error messages, brighter logo tagline
- **v1.1.0:** 12-word recovery phrase, restore, find lost ecash, one-tab lock, storage protection, donation section, logo and app icons
- **v1.0.0:** first release: ecash, Lightning and on-chain wallet, transaction notes, seven arcade games, sound

## Open-source components

The page bundles these MIT-licensed libraries (their license notices are at the end of the bundled script):

- [cashu-ts](https://github.com/cashubtc/cashu-ts)
- [noble-curves, noble-hashes, scure-base, scure-bip32, scure-bip39](https://paulmillr.com/noble/)
- [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator)
