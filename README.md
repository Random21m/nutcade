<p align="center"><img src="logo.png" alt="NUTCADE" width="560"></p>

# NUTCADE

A Cashu ecash wallet with a 1980s arcade built in.

**Open it:** https://random21m.github.io/nutcade/

> **Moved from GitLab.** NUTCADE now lives on GitHub. The old address (nutcade-2c150c.gitlab.io) is no longer updated. Each address keeps its own wallet in your browser, so to move: write down your 12 words (Settings → Backup → Show recovery phrase), open the new address, and tap **Restore from recovery phrase**.

NUTCADE holds Bitcoin as Cashu ecash: fast, private payments you can send like a text message. It works in any modern browser on phone or desktop, with nothing to install, and keeps your wallet protected by a standard 12-word recovery phrase.

## Features

**Wallet**
- Send and receive **ecash**, **Lightning** and **on-chain** Bitcoin (on-chain needs a mint that supports NUT-30)
- **Scan QR codes** with the camera or from a photo: ecash tokens, Lightning invoices, Lightning addresses, LNURL, Bitcoin addresses (BIP21) and mint addresses
- Pay any **Lightning address** (like name@wallet.com) by typing or scanning it
- **Your own Lightning address** (npub…@npub.cash) that anyone can pay from any Lightning wallet. It comes from your 12 words, so it's the same address cashu.me gives them
- **Multinut payments** (NUT-15): pay one Lightning invoice from several mints at once when no single mint holds enough. Every part settles together, or all the sats come back
- **Payment requests** (NUT-18): make a request (amount and note optional) that any Cashu wallet, like cashu.me, can pay. The ecash arrives privately over Nostr, even while the request screen is closed. You can also pay requests other people send you, over Nostr or HTTP
- **NFC** (Chrome on Android): write ecash or a payment request onto an NFC card or sticker, and tap a card to receive. Small cards get a compact format that cashu.me also reads
- **Instant updates**: deposits, payments and claimed tokens show up the moment the mint confirms them (NUT-17), with a regular check as backup
- **Mint list backup on Nostr** (NUT-27): your mint list is saved encrypted, so restoring from 12 words finds your mints for you, here or in cashu.me
- **PIN lock** with your wallet encrypted on the device, plus optional **Face ID / fingerprint** unlock
- Use several mints at once and switch between them
- Pick mints from a curated list, by address, or from recommendations on Nostr (NIP-87)
- Claim ecash from a mint you don't use yet, or swap it into your own mint over Lightning
- Private **notes on every transaction**, searchable and filterable. Add **#tags** like #food or #rent to group them, and **export everything to CSV** for a spreadsheet or your taxes
- **Contacts**: save people with their Lightning address, their Nostr address for ecash, or both, and pay them by name. Friends can send you ecash over Nostr to your own **ecash address**, from NUTCADE or cashu.me
- **Amounts in your currency**: every amount field has a SAT / currency switch, and each transaction remembers the Bitcoin price at the time
- **Works offline**: NUTCADE opens without a connection once you've visited. Offline you can still send amounts that match the coins you hold, and save ecash people give you; it's claimed automatically when you're back online
- **Languages**: English, Español, Português (Brasil), Deutsch and Français, picked from your browser or chosen in Settings. Game titles stay in English, like arcade cabinets. Spotted a clumsy translation? Open an issue on GitHub
- **Live Bitcoin price chart** in arcade style: 1H, 1D, 1W, 1M and 1Y ranges, high and low markers, touch or hover to read any point, and your balance's value updating live
- **Send by sound**: play ecash, a payment request or an invoice as an 8-bit chirp, like loading a game from tape, and another phone running NUTCADE picks it up through its microphone. Works on iPhones and with no internet between the phones
- **Gifts that come back**: lock ecash to one person (NUT-11). Only they can claim it, and if they haven't by the date you pick (a day, a week or a month), it comes back to you on its own
- **Split a bill**: paid for the group? Turn the bill into a boss. Friends each pay their share from any Cashu wallet, and every payment knocks off some of its health until the boss is defeated
- **Mint health**: see how your sats are spread across mints, which mints are answering and how fast, and get a warning when one mint holds most of your sats or stops answering. **Move sats between mints** over Lightning in a couple of taps, or let NUTCADE suggest how to even them out
- **Cashier mode**: a full-screen till for a market stall or a café. Type the price, the customer scans, and coins drop with a chime when it's paid. Takes Lightning or ecash, keeps today's total and exports the day's sales as CSV
- **Round-up piggy bank**: each payment rounds up to the nearest 10, 100 or 1,000 sats and the difference is set aside. The sats stay in your wallet, but spending them means waiting through a "Continue?" countdown first
- Take back a sent token if nobody claimed it, and see when one was claimed
- Coin-drop and 1UP effects when sats arrive, and a launch effect when you send

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

**Challenges**: after a game, tap **Challenge a friend** to send your score to a contact over Nostr or share it as a link. Your friend's game starts from the same seed, so it's laid out the same way, and their score comes back to you. Challenges are signed with your NUTCADE key, so nobody can send one in your name.

**Trophies and score cards**: 26 trophies for wallet milestones and arcade feats (reach wave 3 in Star Swarm, grow Nibble to 30, play every cabinet…). Every high score and trophy can be turned into a share card for X or anywhere else. Cards show the game and score only, never anything about your wallet, and trophies stay on your device.

**Settings**
- **Security:** set, change or remove your PIN, turn on Face ID / fingerprint, lock now, and choose when the wallet locks itself
- **Backup:** show your phrase, find lost ecash, back up your mint list to Nostr, download or import a backup file, restore a wallet from 12 words, reset the wallet
- **Lightning address:** turn on your own address, choose which mint receives the payments, check for payments, turn it off
- **Contacts:** add, edit and pay contacts, and show your ecash address
- **Look & sound:** language, three cabinet themes (Neon, Amber CRT, Green phosphor), sound effects, music, CRT scanlines, amounts shown as ₿
- **Privacy:** turn the live price and price chart on or off (prices come from Coinbase, in your currency), choose whether to check if sent tokens were claimed, and whether to receive ecash sent over Nostr
- **Piggy bank:** turn round-ups on or off, choose what to round to, and empty the piggy bank
- **Wallet tools:** cashier mode and today's till, move sats between mints, remove spent ecash and check stuck payments
- **About:** version, links and donations

## Getting started

1. Open https://random21m.github.io/nutcade/. On iPhone, tap Share → **Add to Home Screen** first and open NUTCADE from that icon, so Safari keeps your wallet.
2. Tick the box to say you understand, then tap **Create a new wallet**.
3. Write your **12 words** on paper, in order. Then type back the three words NUTCADE asks for.
4. Set a PIN when NUTCADE offers it (recommended).
5. Choose a mint. Try **Testnut** first if you want to play with fake sats.
6. Tap **Receive** to add sats, and write the mints you use next to your 12 words.

### Moving from another wallet

Already have a Cashu wallet, like cashu.me or an earlier NUTCADE? On the welcome screen tap **Restore from recovery phrase**, or later go to **Settings → Backup → Restore wallet from 12 words**. Enter your 12 words, tap **Find my mints on Nostr** to tick the mints from your backup, and add any others you used. NUTCADE uses the same standard as cashu.me (NUT-13), so the same words work in both. If NUTCADE already holds sats, they move into the restored wallet.

### Requesting and paying with payment requests

To ask for sats, tap **Receive → Ecash → Request a payment**, add an amount and what it's for if you like, and share the code or QR. With **Only from my mints** on (the default), the payer has to use one of your mints, so you never receive ecash from a mint you don't trust. Payments land in your wallet whenever NUTCADE is open, and ones sent while it was closed arrive the next time you open it, for 30 days.

To pay someone's request, scan it or paste it (it starts with creqA). NUTCADE shows what it's for and which of your mints can pay, then sends the ecash straight to them. If it can't be delivered, the ecash stays in your notes so you can send it another way or take it back.

### Contacts and your ecash address

**Settings → Contacts** (or **Manage** on the Send screen) holds the people you pay. Give each a name and a Lightning address, a Nostr address (npub or nprofile), or both. Tap a contact on the Send screen to pay them: Lightning addresses are paid over Lightning, and Nostr addresses get ecash sent privately over Nostr. After paying a new Lightning address, NUTCADE offers to save it as a contact.

Your own **ecash address** is under Receive → Ecash. Friends can send ecash to it from NUTCADE or cashu.me, and it arrives whenever NUTCADE is open.

### Sending by sound

On a token, payment request or invoice screen, tap **Play as sound**. On the other phone, tap **Listen** on the wallet screen (or in the scanner, or under Receive → Ecash) and hold the phones close. The code plays on a loop until you stop it, so a block missed on one pass is picked up on the next; a typical token takes 10 to 20 seconds a pass. Turn the volume up and keep the room fairly quiet. Anyone close enough to hear it could catch a token, the same as photographing its QR code, so play tokens only near the person you're paying. Sound works between NUTCADE wallets only.

### Gifts that come back

Under Send → Ecash, tick **Lock it to one person**, pick a contact (or paste an npub or Cashu public key), and choose when it should come back: after a day, a week or a month. If the person is a contact with a Nostr address, the gift is also sent to them over Nostr. They claim it with NUTCADE, or with cashu.me using the same 12 words. If they haven't claimed it by the date, NUTCADE takes it back for you the next time it's open, or you can tap **Take it back** in your notes. Until then, nobody else can claim it, including you.

### Splitting a bill

Tap **Split a bill** on the wallet screen, enter the total and how many people are sharing it (you included), and NUTCADE summons a bill boss with a QR code for everyone else. Each friend scans it with NUTCADE, cashu.me or another Cashu wallet and pays their share; the ecash comes straight to you over Nostr, and the boss loses health with every payment. Open bills stay on the wallet screen until the boss is defeated.

### Mint health and moving sats

The **Mints** tab checks that each of your mints answers and how quickly, and shows how your sats are spread. If one mint holds most of them, NUTCADE suggests how much to move and where; **Move sats between mints** does it over Lightning. You see the Lightning fee before you confirm, and if NUTCADE closes halfway, the deposit at the receiving mint is still claimed the next time it opens.

### Cashier mode

Tap **Cashier mode** on the wallet screen (or in Settings → Wallet tools). Type the price on the keypad, in sats or your currency, add the item if you like, and tap **Charge**. The customer scans the QR code with any Lightning wallet, or switch to **Ecash** for a Cashu payment request. When it's paid you get a PAID! screen and a chime, and the next sale is ready. To leave, hold **Hold to exit** for a second, so a customer can't close it by accident. **Close the till** shows today's sales and exports them as CSV.

### Piggy bank

Turn on **Settings → Piggy bank → Round up my payments**. Each payment rounds up to the nearest 100 sats (or 10 or 1,000), and the difference is set aside: pay 1,234 and 66 goes in the piggy bank. Nothing is moved, so your balance is the same, but a payment that would dip into the piggy bank brings up **BREAK THE PIGGY BANK?** with a countdown. You can only go ahead after a few seconds, and if you do nothing, the payment is cancelled.

### Offline

Open NUTCADE once while online and it keeps a copy, so it opens without a connection after that. While offline, a banner says so. You can still send ecash for amounts made of the exact coins you hold (NUTCADE suggests the nearest amounts if yours doesn't fit), and ecash someone gives you is saved and claimed automatically when you're back online. Until it's claimed it isn't yours yet, because the sender could still spend it.

### Paying from several mints

If the mint you're using doesn't hold enough to pay a Lightning invoice, the quote screen offers **Pay from several mints**. NUTCADE asks each mint that supports multi-path payments for a share, shows you the split and the fees, then pays all the parts together. This needs at least two of your mints to support NUT-15.

### NFC cards

On an Android phone with Chrome, the scanner has a **Tap NFC** button, and token and request screens have **Write to NFC**. Hold a card to the back of the phone. iPhones don't allow websites to use NFC, so these buttons don't appear there.

### Getting your own Lightning address

Go to **Settings → Lightning address → Set it up**, pick the mint that should receive payments, and tap **Turn on**. Share the address shown, or find it any time on the **Receive → Lightning** screen. Payments are turned into ecash at your mint by npub.cash, and NUTCADE claims them whenever it's open. If you used a Lightning address in cashu.me with the same 12 words, it's the same address here.

### Starting over

**Settings → Backup → Reset wallet** deletes the wallet from this browser and returns you to the start screen to create a new one or restore one. Write down your 12 words and mints first if there are sats in it.

## Safety

- **PIN lock and encryption.** With a PIN set, your phrase, ecash, history and notes are stored encrypted (AES-256-GCM). The key is unlocked by your PIN (PBKDF2, 600,000 rounds) or by a Face ID / fingerprint passkey (WebAuthn PRF). Five wrong PINs trigger a growing wait, and the wallet locks itself after the time you choose. A PIN stops someone who picks up your phone; it can't stop malware on a compromised device. If you forget it, reset and restore with your 12 words.
- **Recovery phrase first.** You can't use the wallet until you've written down your 12 words and confirmed them. Every piece of ecash is derived from them (NUT-13), and restoring scans your mints to rebuild your balance (NUT-09).
- **Interrupted payments are handled.** A failed Lightning payment returns your sats. A stuck one is tracked until the mint settles it. A deposit interrupted mid-way is recovered automatically the next time you open the app.
- **Mint list backup.** Your list of mints is saved to Nostr relays encrypted with a key from your 12 words (NUT-27, the same format cashu.me uses), so a restore can find them even if you lose your note. Only the list is saved, never ecash or amounts. You can turn this off in Settings → Backup.
- **Same phrase on two devices.** If a mint reports reused codes, NUTCADE catches up and retries on its own.
- **One tab at a time.** If NUTCADE is open in a second tab, that tab pauses so the two can't overwrite each other.
- **Storage protection.** NUTCADE asks the browser not to clear its data, and Settings shows whether that was granted.
- **No outside code.** The app is one self-contained file with its fonts built in. The QR decoder loads from this same site, only when you open the scanner. Nothing is loaded from other servers.
- **Checked releases.** Every update runs the test suites automatically before it goes live, and the site publishes SHA-256 checksums at https://random21m.github.io/nutcade/SHA256SUMS.txt. See [RELEASING.md](RELEASING.md).
- **Shared GitHub domain.** GitHub serves every project site on an account from one domain (random21m.github.io), and browsers let pages on the same domain read each other's saved data. So only publish pages you trust under this account, and set a PIN: it keeps your phrase and ecash encrypted, so another page on the domain can't read them.

**Important:** your wallet lives in your browser. Keep your 12 words and your mint list somewhere safe and offline. Never type your words into a website or send them to anyone, including anyone claiming to be NUTCADE support. Mints hold the Bitcoin behind your ecash, so only use mints you trust. NUTCADE is young software that hasn't been independently audited, so start with small amounts.

## Testing

Every push runs the suites in `tests/` automatically on GitHub (GitHub Actions) against real Cashu mints (Nutshell), including mints set up to fail or stall payments. The site only updates if every check passes:

- 51 wallet checks: Lightning in and out, ecash between wallets, double-claim protection, failed and stuck payments, notes, multiple mints, backup files, and restoring from the phrase after a full wipe
- 27 settings checks: themes, ₿ display, backup download and import, restoring a phrase from another Cashu client, reset, and swapping received ecash into your own mint
- Crash recovery: a deposit interrupted mid-way comes back on the next open
- 28 PIN-lock checks: encryption at rest, wrong PINs and lockout, change and removal, Face ID / fingerprint unlock, auto-lock, and forgot PIN followed by restore
- 73 Round 4 checks: sending a token by sound from one browser to another through a (simulated) microphone, gifts locked to a contact and refunded after their date, a bill split paid off by a friend, mint health warnings and moving sats, cashier sales in Lightning and ecash, challenges sent and answered over Nostr (and a tampered one refused), the piggy bank countdown, and every new screen in each language at 320 pixels wide
- 37 checks for amounts in your currency, #tags and CSV export, contacts (Lightning address and ecash over Nostr), offline use, and languages
- 41 checks for multinut payments, payment requests (over Nostr and HTTP, including ecash sent by another wallet) and NFC reading and writing
- 39 checks for trophies, share cards, instant updates, the Nostr mint-list backup and the Lightning address, against a stand-in Nostr relay and npub.cash server that check every signature
- 24 scanner checks, run before release: camera scans of real tokens and invoices, photo scans, and recognising every kind of code
- All seven games played through to game over, with high scores, pause, exit, touch controls and sound
- Every screen at 320, 390, 768 and 1280 pixels wide, checked for overflow and clipped text, and again in each language

## Privacy

NUTCADE has no account, no tracking and no analytics. Your recovery phrase and notes stay in your browser, and mints only see the ecash you exchange with them. The app contacts other services only for these things:

- **Mints**: yours for every payment, and the ones listed in the mint picker to show whether they're online
- **Coinbase**, for the price and chart, only while **Show Bitcoin price** is on
- **Nostr relays** (relay.damus.io, nos.lol, relay.primal.net), to send and receive game challenges with your contacts, to save your encrypted mint list when it changes and to look for it when you restore (turn this off in Settings → Backup), to receive payments for requests you made in the last 30 days, to deliver payments to requests you pay, to receive ecash friends send to your ecash address (turn this off in Settings → Privacy), and when you tap "Find mints people recommend". Payments you send over Nostr are signed with a one-time key, so they aren't linked to you. Challenges and their scores are signed with your NUTCADE Nostr key so friends know they're from you
- **npub.cash**, only while your Lightning address is turned on. It sees the amounts and times of payments to your address, not the rest of your wallet
- **The donation address** (breez.tips), only when you tip from inside the app

The **microphone** is used only while a Listen screen is open. The sound is decoded on your phone and nothing is recorded or sent anywhere.

## Sharing

Posting the link on X and most social sites shows a large preview card automatically. A bigger version of the picture for attaching to posts is at https://random21m.github.io/nutcade/nutcade-share.png.

## For maintainers

The app is one file, `public/index.html`, plus the QR decoder `public/zxing_reader.wasm` and the offline helper `public/sw.js`. On every push to `main`, `.github/workflows/test-and-deploy.yml` runs the test suites and then publishes `public/` to GitHub Pages with fresh checksums. To ship an update, replace `public/index.html` and push. [RELEASING.md](RELEASING.md) covers running the tests yourself, cutting a release and signing it. Wallets people already have keep their sats, and visitors get the new version within a few minutes.

## Support the project

NUTCADE is free and open source, and it stays that way. Supporting it is optional and changes nothing about how it works. If you enjoy it, you can send a few sats over Lightning:

<p><img src="docs/support-qr.png" alt="QR code for the Lightning address dev@breez.tips" width="200"></p>

**dev@breez.tips**

You can also tip from inside NUTCADE: **Settings → About → Donate**. The same address and code are on that screen. Be wary of any other "NUTCADE donation" address.

## Changelog

- **v1.8.1:** moved to GitHub: new address https://random21m.github.io/nutcade/, share cards and preview images point there
- **v1.8.0:** send codes by sound between phones, gifts locked to one person that come back after a date (NUT-11), split a bill as a boss fight, mint health with moving sats between mints, cashier mode for selling, high-score challenges with friends, round-up piggy bank, 5 new trophies
- **v1.7.0:** contacts with Lightning and Nostr addresses, your own ecash address, amounts in your currency, #tags and CSV export, offline use (the app opens offline, exact-amount sends, tokens saved to claim later), Spanish, Portuguese, German and French
- **v1.6.0:** multinut payments across several mints (NUT-15), payment requests to create and pay (NUT-18 over Nostr and HTTP), NFC cards for ecash and requests, opening tokens from links
- **v1.5.0:** your own Lightning address (npub.cash, same as cashu.me), instant updates over mint websockets (NUT-17), encrypted mint-list backup on Nostr with "Find my mints" when restoring (NUT-27), 21 trophies, share cards for high scores and trophies

- **v1.4.0:** QR scanner (camera and photo), paying Lightning addresses, PIN lock with encrypted storage and Face ID / fingerprint unlock, auto-lock, coin-drop and 1UP effects, fonts built in (no more Google Fonts), automatic tests in GitLab before every release, published SHA-256 checksums
- **v1.3.0:** live Bitcoin price chart on the wallet screen, live balance value, share image and link preview for X and other social sites
- **v1.2.0:** wallet setup before entry, Settings tab, restore a wallet from 12 words (including from cashu.me), reset wallet, automatic recovery of interrupted deposits, automatic repair when one phrase is used on two devices, claiming ecash before choosing a mint, clearer error messages, brighter logo tagline
- **v1.1.0:** 12-word recovery phrase, restore, find lost ecash, one-tab lock, storage protection, donation section, logo and app icons
- **v1.0.0:** first release: ecash, Lightning and on-chain wallet, transaction notes, seven arcade games, sound

## Open-source components

The page bundles these libraries (their license notices are at the end of the bundled script):

- [cashu-ts](https://github.com/cashubtc/cashu-ts)
- [noble-curves, noble-hashes, scure-base, scure-bip32, scure-bip39](https://paulmillr.com/noble/)
- [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator)
- [zxing-wasm](https://github.com/Sec-ant/zxing-wasm) (MIT) with [zxing-cpp](https://github.com/zxing-cpp/zxing-cpp) (Apache-2.0), the QR decoder
- [jsQR](https://github.com/cozmo/jsQR) (Apache-2.0), the fallback QR decoder
- [nostr-tools](https://github.com/nbd-wtf/nostr-tools) (Unlicense) and [noble-ciphers](https://github.com/paulmillr/noble-ciphers) (MIT), for signing Nostr events and NIP-44 encryption

Fonts: [Press Start 2P](https://fonts.google.com/specimen/Press+Start+2P) and [VT323](https://fonts.google.com/specimen/VT323), both under the SIL Open Font License.
