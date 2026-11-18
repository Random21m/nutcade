<p align="center"><img src="logo.png" alt="NUTCADE" width="560"></p>

# NUTCADE

A Cashu ecash wallet with a 1980s arcade built in.

**Open it:** https://random21m.github.io/nutcade/

**Timestamped in Bitcoin:** NUTCADE v1.8.1, including the send-by-sound chiptune modem, is anchored in [block 975,501](https://mempool.space/block/00000000000000000000c8328fa2baa44180bc59c74d739bfb317dd984ade480), mined 11 November 2026. The proof covers the release checksums, and the checksum for `index.html` covers the sound code inside it. The proof, `SHA256SUMS.txt.ots`, is attached to the [v1.8.1 release](https://github.com/Random21m/nutcade/releases/tag/v1.8.1); check it at [opentimestamps.org](https://opentimestamps.org).

**Send by sound, timestamped on its own:** the sound modem's source, [`src/chiptune.js`](src/chiptune.js) (SHA-256 `77cb1714…c1c48f9`, unchanged since), is anchored in [block 975,513](https://mempool.space/block/00000000000000000000ffe72c5aff0f1b98e79bc4353e3345c48208cb23f1fb), mined 11 November 2026. The proof is [`docs/chiptune.js.ots`](docs/chiptune.js.ots); check it with `ots verify -f src/chiptune.js docs/chiptune.js.ots` or at [opentimestamps.org](https://opentimestamps.org).

> **Moved from GitLab.** NUTCADE now lives on GitHub. The old address (nutcade-2c150c.gitlab.io) is no longer updated. Each address keeps its own wallet in your browser, so to move: write down your 12 words (Settings → Backup → Show recovery phrase), open the new address, and tap **Restore from recovery phrase**.

NUTCADE holds Bitcoin as Cashu ecash: fast, private payments you can send like a text message. It works in any modern browser on phone or desktop, with nothing to install, and keeps your wallet protected by a standard 12-word recovery phrase.

## Get NUTCADE: add it to your home screen

**The only real address is https://random21m.github.io/nutcade/** · There's no app-store app; anything else calling itself NUTCADE isn't us.

Adding it to your home screen makes NUTCADE open full-screen like an app and work offline. **On iPhone it also keeps your wallet safe:** Safari can clear the storage of websites you haven't opened in a while, but a Home Screen app keeps it.

| Device | Steps |
|---|---|
| **iPhone / iPad** (Safari) | 1. Open the link above in **Safari**. 2. Tap **Share** (the square with an arrow; on newer iOS, tap **•••** first). 3. Tap **Add to Home Screen**, then **Add**. 4. From now on, open NUTCADE from the new icon. |
| **Android** (Chrome) | 1. Open the link in **Chrome**. 2. Tap **⋮** (top right). 3. Tap **Install app** or **Add to Home screen**, then **Install**. 4. Open it from the new icon. |
| **Computer** (Chrome or Edge) | Open the link and click the **install icon** at the right end of the address bar (or **⋮ → Install NUTCADE**). It opens in its own window. |
| **Mac** (Safari) | Open the link, then **File → Add to Dock**. |

**Good to know**
- Each browser and each icon keeps its own wallet. Set it up once in the place you'll use it.
- Write down your **12 words** when you create the wallet. They're the only way back if the phone is lost or the browser data is cleared.
- Updates arrive by themselves: the next time you open NUTCADE, it loads the new version.

<table>
<tr><td><img src="docs/screens/01-lightning.jpg" alt="Loading sats over Lightning: a 1UP and a coin shower"></td><td><img src="docs/screens/02-arcade.jpg" alt="Star Swarm, one of the 8 original arcade games"></td></tr>
<tr><td><img src="docs/screens/03-trophies.jpg" alt="The trophy room"></td><td><img src="docs/screens/04-send.jpg" alt="Sending sats to a friend: SENT! on one phone, 1UP! on the other"></td></tr>
<tr><td><img src="docs/screens/05-sound.jpg" alt="Send by sound: one phone plays the coins, the other listens and receives them"></td><td><img src="docs/screens/06-cashier.jpg" alt="Cashier mode: a paid sale of 5,000 sats"></td></tr>
<tr><td><img src="docs/screens/07-languages.jpg" alt="The wallet in English, Spanish, Portuguese, German and French"></td><td><img src="docs/screens/08-pin.jpg" alt="The PIN lock"></td></tr>
</table>

## Features

**Wallet**
- Send and receive **ecash**, **Lightning** and **on-chain** Bitcoin (on-chain needs a mint that supports NUT-30)
- **Scan QR codes** with the camera or from a photo: ecash tokens, Lightning invoices, Lightning addresses, LNURL, Bitcoin addresses (BIP21) and mint addresses
- Pay any **Lightning address** (like name@wallet.com) by typing or scanning it
- **LNURL vouchers** (LNURL-withdraw, LUD-03): scan or paste a voucher to load its sats into the mint you pick. You see its description and limits, choose the amount (the most it gives, unless you change it), and NUTCADE asks the voucher to pay an invoice for exactly that amount
- **Zaps** (NIP-57): zap a contact or any npub. NUTCADE finds the Lightning address in their Nostr profile and signs the zap with your wallet's Nostr key, the one that comes from your 12 words. The invoice must be for exactly what you asked, and you see the fee before you pay. If their address can't take zaps, you're offered a plain Lightning payment instead
- **Nostr Wallet Connect** (NIP-47): let another app, like a Nostr client, pay and receive with this wallet. Give each connection a name and, if you like, a budget per day, week, month or in total. It answers only while NUTCADE is open and unlocked in a tab
- **Block a mint**: tokens, payment requests and deposits from a blocked mint are refused, and you're always told why, with an Unblock button. Sats you already hold there stay yours to send or move out
- **Your own Lightning address** (npub…@npub.cash) that anyone can pay from any Lightning wallet. It comes from your 12 words, so it's the same address cashu.me gives them
- **Multinut payments** (NUT-15): pay one Lightning invoice from several mints at once when no single mint holds enough. Every part settles together, or all the sats come back
- **Payment requests** (NUT-18): make a request (amount and note optional) that any Cashu wallet, like cashu.me, can pay. The ecash arrives privately over Nostr, even while the request screen is closed. You can also pay requests other people send you, over Nostr or HTTP
- **NFC** (Chrome on Android): write ecash or a payment request onto an NFC card or sticker, and tap a card to receive. Small cards get a compact format that cashu.me also reads
- **Instant updates**: deposits, payments and claimed tokens show up the moment the mint confirms them (NUT-17), with a regular check as backup
- **Mint list backup on Nostr** (NUT-27): your mint list is saved encrypted, so restoring from 12 words finds your mints for you, here or in cashu.me
- **PIN lock** with your wallet encrypted on the device, plus optional **Face ID / fingerprint** unlock
- **Spending limit**: have NUTCADE ask for your PIN above an amount you pick for one payment, and cap what can leave in any 24 hours. It covers every way sats leave: Lightning, ecash (also by sound, NFC or QR), payment requests and bill splits, gifts, bounties (challenge stakes), treasure hunts and loaded cards, Extra Life, moves between your own mints (in full), Wallet Connect (on top of each app's budget), zaps, tips, Lightning addresses and LNURL, contacts, payments from several mints (judged as a whole before any part leaves), on-chain, and the sats you put in a duress PIN's wallet. Fees count. Over a limit, you see the amount and when the day frees up, and your PIN lets that one payment through
- **Duress PIN**: a second PIN that opens a small, separate wallet instead of yours, for when someone forces you to unlock NUTCADE (see [Safety](#safety) for what it does and doesn't hide)
- **Mints with a request limit** (NUT-06): NUTCADE honours a mint's `max_array_length` and needs at least 128 items per request; a mint below that can't be added (see [Safety](#safety))
- **Report a problem** from Settings → About, with a form that asks for what happened, the steps, your device and the version, and warns never to paste your 12 words, PIN or tokens
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
- **High-score bounties**: put sats on a challenge. The mint locks them to your friend and to a secret only your NUTCADE holds (NUT-14). Beat your score within a week and their NUTCADE gets the secret and claims the sats; otherwise they come back to you
- **Replays that prove scores**: every game records its inputs, so any phone can replay it and get exactly the same score. Challenges carry the challenger's replay, checked on arrival, and you race their ghost; a bounty only pays out when the winner's replay checks out
- **Treasure hunts**: hide sats behind printable clue cards. The prize is locked to a key split across the cards (Shamir's secret sharing), so any 3 of 5 (or whatever you choose) open the chest, and no single card can
- **Loaded score cards**: put sats in a high-score or trophy card before you share it. The card carries a QR code, and the first person to scan it wins them
- **Extra Life**: savings that pass to someone you trust if you stop playing. The sats stay yours and spendable, locked to your key with your heir as the refund key after a date (NUT-11). Each CONTINUE, or just opening NUTCADE, pushes the date back and sends your heir a fresh copy that makes their old one worthless
- **Mint report card**: a grade for each mint from uptime, speed, age, key history, your own payments with it and recommendations on Nostr. A mint whose identity key changes is flagged
- **Animated QR codes**: tokens too long for one QR code play as a looping animated QR in the BC-UR format cashu.me uses, and the scanner reads animated QR codes from NUTCADE and cashu.me
- **Round-up piggy bank**: each payment rounds up to the nearest 10, 100 or 1,000 sats and the difference is set aside. The sats stay in your wallet, but spending them means waiting through a "Continue?" countdown first
- Take back a sent token if nobody claimed it, and see when one was claimed
- Coin-drop and 1UP effects when sats arrive, and a launch effect when you send

**Arcade**: ten original cabinets with high-score tables, chiptune sound and music

| Cabinet | Style |
|---|---|
| Star Swarm | Diving-formation space shooter |
| Nut Maze | Maze chase with a new maze every level |
| Brick Blitz | Paddle and ball |
| Void Rocks | Vector rock shooter |
| Hop Lanes | Road and river crossing |
| Sky Shield | Missile defense |
| Nibble | Snake |
| Nut Flipper | Pinball: light N-U-T for a multiplier, drop the S-A-T targets, hunt the gold sat |
| Nut Poker | Five-card draw video poker, jacks or better, for **free credits only** (never sats) |
| Neon Road | Pseudo-3D night-highway racer: pass traffic, race the clock to each checkpoint |

Plays with keyboard, mouse, or on a phone with an on-screen joystick and buttons (tap **Use D-pad** above the controls if you'd rather have arrow buttons).

**Neon Road** (how to play): you drive down a neon highway toward the sunset, against a clock. The road curves and rolls over hills; slower cars share it, and the grass drags you down. Pass cars for points, hit the checkpoint arch at the end of each stage for extra time and points, and keep going until the time runs out. Every stage has its own colours and tighter curves, and the same seed always builds the same road, so a challenge or a Daily Challenge replays the same course.
- **Keyboard:** left/right arrows or A/D steer, up or W is gas (the car cruises by itself without it), down or S brakes.
- **Phone:** touch the left or right half of the screen to steer (the car accelerates while you touch), touch the top of the screen to brake, or use the joystick: left/right steers, up boosts, down brakes.
- Score is distance, plus 50 for every car you pass (100 for a close pass), plus a bonus at each checkpoint.
**Daily Challenge**: at the top of the arcade, one cabinet a day (picked from the UTC date) with the same seeded level for everyone. The first run of the day is your official score, you keep a streak of days played in a row, and you can share the score as a Nostr note only when you tap **Post**. See [Daily Challenge](#daily-challenge).

**Challenges and bounties**: after a game, tap **Challenge a friend** to send your score to a contact over Nostr or share it as a link. Your friend's game starts from the same seed, so it's laid out the same way, and their score comes back to you. Challenges are signed with your NUTCADE key, so nobody can send one in your name. Sending to a contact, you can also **put sats on it**: they're locked so only that friend can win them, and only by beating your score within a week.

**Replays**: every game is replayable. The games start from a seed and run on a fixed clock of 60 steps a second (the same speed on 60, 120 and 144 Hz screens), and NUTCADE records each step's input, so playing the inputs back gives exactly the same game and score on any phone. The games use their own sine, cosine and distance maths, so iPhones and Android phones agree to the last bit. A challenge carries your replay: your friend's NUTCADE plays it back to confirm your score is real before they accept, and then they race your ghost. Their result comes back with their replay too, which your NUTCADE checks before believing it.

**Trophies and score cards**: 28 trophies for wallet milestones and arcade feats (reach wave 3 in Star Swarm, grow Nibble to 30, play every cabinet…). Every high score and trophy can be turned into a share card for X or anywhere else. Cards show the game and score only, never anything about your wallet, and trophies stay on your device.

**Settings**
- **Security:** set, change or remove your PIN, turn on Face ID / fingerprint, lock now, and choose when the wallet locks itself
- **Backup:** show your phrase, find lost ecash, back up your mint list to Nostr, download or import a backup file, restore a wallet from 12 words, reset the wallet
- **Lightning address:** turn on your own address, choose which mint receives the payments, check for payments, turn it off
- **Contacts:** add, edit and pay contacts, and show your ecash address
- **Look & sound:** language, three cabinet themes (Neon, Amber CRT, Green phosphor), sound effects, music, CRT scanlines, amounts shown as ₿
- **Privacy:** turn the live price and price chart on or off (prices come from Coinbase, in your currency), choose whether to check if sent tokens were claimed, and whether to receive ecash sent over Nostr
- **Piggy bank:** turn round-ups on or off, choose what to round to, and empty the piggy bank
- **Wallet tools:** cashier mode and today's till, move sats between mints, remove spent ecash and check stuck payments
- **About:** version, links and support

## Getting started

1. Open https://random21m.github.io/nutcade/ and add it to your home screen ([how, for every device](#get-nutcade-add-it-to-your-home-screen)). Then open NUTCADE from that icon.
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

On a token, payment request or invoice screen, tap **Play as sound**. On the other phone, tap **Listen** on the wallet screen (or in the scanner, or under Receive → Ecash) and hold the phones close. The code plays on a loop until you stop it, so a block missed on one pass is picked up on the next; a pass takes about 4 seconds for a small token and up to about 20 seconds for a large one. Turn the volume up and keep the room fairly quiet. Anyone close enough to hear it could catch a token, the same as photographing its QR code, so play tokens only near the person you're paying. Sound works between NUTCADE wallets only.

The format is open: see [docs/SOUND-SPEC.md](docs/SOUND-SPEC.md). Other wallets are welcome to implement it.

### Gifts that come back

Under Send → Ecash, tick **Lock it to one person**, pick a contact (or paste an npub or Cashu public key), and choose when it should come back: after a day, a week or a month. If the person is a contact with a Nostr address, the gift is also sent to them over Nostr. They claim it with NUTCADE, or with cashu.me using the same 12 words. If they haven't claimed it by the date, NUTCADE takes it back for you the next time it's open, or you can tap **Take it back** in your notes. Until then, nobody else can claim it, including you.

### Splitting a bill

Tap **Split a bill** on the wallet screen, enter the total and how many people are sharing it (you included), and NUTCADE summons a bill boss with a QR code for everyone else. Each friend scans it with NUTCADE, cashu.me or another Cashu wallet and pays their share; the ecash comes straight to you over Nostr, and the boss loses health with every payment. Open bills stay on the wallet screen until the boss is defeated.

### High-score bounties

After a game, tap **Challenge a friend**, type an amount under **Put sats on it**, and tap the contact to send it to. The sats leave your balance as ecash locked two ways: to your friend's key, and to a secret that only your NUTCADE knows (NUT-14 hash lock). Your friend sees the bounty with the challenge. If they beat your score, their NUTCADE sends you the signed result with its replay. Your NUTCADE plays the replay back, and only if it really reaches that score does it reply with the secret, so a made-up score can't win the bounty. Theirs then claims the sats. If nobody wins within a week, the lock's refund path opens and the sats come back to you on their own. Your NUTCADE has to see the result before the week is up, so open it now and then while a bounty is running. Bounties need a mint that supports NUT-14.

### Treasure hunts

Tap **Treasure hunt** on the wallet screen. Enter a prize, how many clue cards to make (2 to 12) and how many of them are needed to open the chest, add a message if you like, and choose when an unopened prize comes back to you. NUTCADE makes a fresh key, locks the prize to it (NUT-11, with your refund key after the date), splits the key across the cards with Shamir's secret sharing, and puts the prize on Nostr encrypted with that key. Print the cards (**Print cards**) or show them on screen, and hide them.

Hunters scan the cards with their phone camera or the NUTCADE scanner. Each card shows the prize and how many clues are still missing; when someone has enough, their NUTCADE rebuilds the key, fetches and decrypts the prize, and claims it. A copied or altered card can't open the chest, and once someone has opened it, the others find it empty.

### Loaded score cards

When you share a high-score or trophy card, type an amount under **Put sats in it** and tap **Load card**. The card is redrawn with a QR code and "INSERT COIN: SCAN TO WIN". It works like a one-card treasure hunt: the first person to scan it wins the sats, and if nobody does within a week, they come back to you. Anyone who sees the card can scan it, so only load what you're happy to give away.

### Nut Poker (free credits only)

Pick **Nut Poker** in the Arcade. You start with 100 credits. Tap **Bet one** (1 to 5 credits, it wraps round) or **Bet max**, then **Deal**: five cards are dealt face up. Tap a card to **HOLD** it (shown under the card), then **Draw** to swap the others for new cards from the same deck. The hand is scored against the pay table, which stays on screen with the current bet's column lit and the winning row flashing. It is the usual 9/6 jacks-or-better table, multiplied by your bet: royal flush 250 (4000 at max bet), straight flush 50, four of a kind 25, full house 9, flush 6, straight 4, three of a kind 3, two pair 2, jacks or better 1. A pair of 10s or lower pays nothing, and A-2-3-4-5 counts as a straight. The deck is shuffled fresh for every hand with the browser's cryptographic random numbers (`crypto.getRandomValues`), not the games' seeded generator, and the draw comes from the same shuffled deck. Keys: **1 to 5** hold, **D** or **Enter** deal / draw, **B** bet one, **M** bet max, **E** end the run, **P** pause.

**Free credits only, never sats.** The credits are play money. They can't be bought with sats, can't be cashed out, and aren't linked to your wallet, mints or any payment in any way. Run out and you get a **FREE REFILL** to 100. The high score is the most credits you have held in one run; it is saved when you end the run or leave. Because of this, a Nut Poker score card can never be loaded with sats (no **Put sats in it** / **Load card**), and there are no challenges or bounties for it. Nut Poker's code (`src/poker.js`) contains no wallet or payment code.
### Daily Challenge

The **DAILY CHALLENGE** card at the top of the arcade shows today's cabinet, your score for today and the time until the next challenge (and what time that is on your clock). Tap **Play daily**. The day is the **UTC date**, so everyone in the world gets the same cabinet and the same starting level; the cabinet and the seed are worked out from the date alone, on your phone, with no server. Your first run of the day is your **official score**; replays that day are for fun and only update your best for the day. A run you quit halfway keeps the score it had (quit at 0 points and the day isn't used up), and a run you start before midnight UTC counts for the day it began. History and your **streak** (days played in a row) stay on this phone.

Tap **Share my score** to see a short note, for example "NUTCADE Daily Challenge Nov 18: Star Swarm 12,340 🕹️ #nutcade", with the app link. Nothing is sent until you tap **Post**, which publishes that one public note, signed with your NUTCADE Nostr key, to your Nostr relays. If you're offline it says so and nothing is lost; with no Nostr key there is **Copy text** instead. There are no accounts, no leaderboard server and no tracking.

NUTCADE can't ask a server what day it is, so it watches the clock itself: if the device date moves back before a day it has already seen, or reads as before 2025, that day's runs are for fun (not official, not in the streak) and a notice says so until the clock catches up or you tap **My clock is right**. Moving the clock forward just moves you to that day's challenge.

Nine of the ten cabinets can be the daily: the eight originals and Neon Road. **Nut Poker never is**: its deck is shuffled for real, so two phones could never play the same deal. For cabinet authors: a cabinet joins with `daily: true` in its object (all its gameplay randomness must come from the engine's seeded `rnd()`/`ri()`/`RNG()`), and `init(G, seed)` receives the run's seed; a cabinet marked `noChallenge` can't join even with the flag. The details are at the top of `src/daily.js`.

### Extra Life

Tap **Extra Life** on the wallet screen (or in Settings → Wallet tools), enter an amount, pick an heir from your contacts (or paste their npub) and choose when it opens for them: after 3 months, 6 months or a year. The sats are locked to your own key, so you can still spend them any time, with your heir's key as the refund key after the date (NUT-11). Your heir's NUTCADE receives a copy over Nostr that only opens after that date.

Press **CONTINUE** to push the date back. With **Continue when I open NUTCADE** on (the default), opening NUTCADE after half the time has passed does it for you. Each CONTINUE swaps the ecash for fresh ecash with a later date and sends your heir the new copy, which also makes their old copy worthless. If you stop (you lost your phone and your words, or worse), your heir's NUTCADE claims the sats once the date passes. **Cash out** puts them back in your balance at any time. Extra Life depends on the mint still running when the date comes, so use one you trust for the long term. Restoring from your 12 words alone can't find Extra Life ecash (that's how it reaches your heir if you lose everything), but **Download backup** includes it, along with any copies you hold as someone's heir and the secrets for your open bounties.

### Mint report card

On the **Mints** tab, each mint shows a grade. Tap it for the report card:

| Grade | From |
|---|---|
| Uptime | How many of NUTCADE's health checks it answered |
| Speed | How fast it usually answers |
| Age | How long it's been known: since you first used it, or since its first mention on Nostr if that's earlier |
| Keys | Whether its identity key is the same as when you added it, and how often it rotates keysets. A changed identity key gets an F and caps the grade at D, because it can mean a new operator |
| Track record | How many of your own payments and swaps with it went through, counting only failures on the mint's side |
| Reviews | How many people recommend it on Nostr (NIP-87), and their average rating |

Everything is worked out on your phone from what NUTCADE can check itself; no outside rating service is involved. A good grade isn't a guarantee, so only keep at each mint what you can afford to lose.

### Mint health and moving sats

The **Mints** tab checks that each of your mints answers and how quickly, and shows how your sats are spread. If one mint holds most of them, NUTCADE suggests how much to move and where; **Move sats between mints** does it over Lightning. You see the Lightning fee before you confirm, and if NUTCADE closes halfway, the deposit at the receiving mint is still claimed the next time it opens.

### Cashier mode

Tap **Cashier mode** on the wallet screen (or in Settings → Wallet tools). Type the price on the keypad, in sats or your currency, add the item if you like, and tap **Charge**. The customer scans the QR code with any Lightning wallet, or switch to **Ecash** for a Cashu payment request. When it's paid you get a PAID! screen and a chime, and the next sale is ready. To leave, hold **Hold to exit** for a second, so a customer can't close it by accident. **Close the till** shows today's sales and exports them as CSV.

### Piggy bank

Turn on **Settings → Piggy bank → Round up my payments**. Each payment rounds up to the nearest 100 sats (or 10 or 1,000), and the difference is set aside: pay 1,234 and 66 goes in the piggy bank. Nothing is moved, so your balance is the same, but a payment that would dip into the piggy bank brings up **BREAK THE PIGGY BANK?** with a countdown. You can only go ahead after a few seconds, and if you do nothing, the payment is cancelled.

### Offline

Open NUTCADE once while online and it keeps a copy, so it opens without a connection after that. While offline, a banner says so. You can still send ecash for amounts made of the exact coins you hold (NUTCADE suggests the nearest amounts if yours doesn't fit), and ecash someone gives you is saved and claimed automatically when you're back online. Until it's claimed it isn't yours yet, because the sender could still spend it.

### Animated QR codes

Codes too long for a comfortable single QR code, like tokens with many coins or locked gifts, play as a looping animated QR. It uses BC-UR (`ur:bytes`), the format cashu.me uses, so cashu.me can scan NUTCADE's and NUTCADE can scan cashu.me's. Hold the scanner on it until the progress reaches 100%; missed frames don't matter, because later frames fill the gaps.

### Paying from several mints

If the mint you're using doesn't hold enough to pay a Lightning invoice, the quote screen offers **Pay from several mints**. NUTCADE asks each mint that supports multi-path payments for a share, shows you the split and the fees, then pays all the parts together. This needs at least two of your mints to support NUT-15.

### NFC cards

On an Android phone with Chrome, the scanner has a **Tap NFC** button, and token and request screens have **Write to NFC**. Hold a card to the back of the phone. iPhones don't allow websites to use NFC, so these buttons don't appear there.

### Loading an LNURL voucher

Scan the voucher's QR code (or paste it with **Scan → Paste**). NUTCADE reads it first and shows what it says it's for and how much it gives. Pick the mint it goes into and the amount, which starts at the most the voucher gives, and tap **Withdraw**. Your mint makes an invoice for exactly that amount, the voucher pays it, and the sats land in your wallet as a Lightning deposit with the voucher's description as its note. If the voucher was already used, has run out or says no for any other reason, you're told in plain words, and nothing was spent. If the voucher's service is slow to answer, NUTCADE keeps watching the invoice while it's open, until the invoice expires.

### Zaps

Open a contact who has a Nostr address and tap **Zap**, or paste anyone's npub into **Send → Lightning**. NUTCADE looks up their Nostr profile on your relays and finds their Lightning address. If it supports zaps, your zap request is signed with your wallet's Nostr key (the same one cashu.me derives from your 12 words), so it shows on Nostr as a zap from you, with your comment if you add one. Turn on **Anonymous zap** to sign it with a fresh one-time key instead. You see the Lightning fee before you confirm, and the zap shows in your notes as "Zap to" and their name. If their address doesn't support zaps, NUTCADE says so and offers a plain Lightning payment.

### Nostr Wallet Connect

**Settings → Wallet Connect → Connect an app** makes a connection link (nostr+walletconnect://…) for an app like a Nostr client. Name it after the app and, if you want a limit, set a budget per day, per week, per month or in total; there's none unless you set one. The link and its QR code are shown once: paste or scan it into the app. The app can then check your balance, pay invoices, make invoices and see the payments and invoices it made itself, or your whole Lightning history if you switch that on for it (NIP-47: get_info, get_balance, pay_invoice, make_invoice, lookup_invoice, list_transactions, plus notifications). Every payment it makes shows in your notes with its name. Rename a connection, change its budget, or revoke it from the same list; a revoked app gets no answer from then on.

Two honest limits: NUTCADE is a web page, so it only answers while it's open and unlocked in a browser tab; requests sent while it was closed or locked, or more than a minute old, are refused, never paid later. A budget counts the most each payment can cost, the mint's fees included. And whoever has the link can spend without asking you, up to its budget, or your whole balance if it has none.

### Blocking a mint

On the **Mints** tab, tap **Block** on a mint you no longer trust. From then on NUTCADE refuses ecash from it (pasted, scanned or sent over Nostr), payment requests that only take it, and Lightning deposits or vouchers into it, and each time it says why, with an **Unblock** button. Ecash sent to you over Nostr from a blocked mint waits in your notes in case you change your mind. Sats you already hold at that mint stay usable, so you can send them or **move them** to another mint, which the Block screen offers. The blocked list is kept on this device and in your backup file.

### Getting your own Lightning address

Go to **Settings → Lightning address → Set it up**, pick the mint that should receive payments, and tap **Turn on**. Share the address shown, or find it any time on the **Receive → Lightning** screen. Payments are turned into ecash at your mint by npub.cash, and NUTCADE claims them whenever it's open. If you used a Lightning address in cashu.me with the same 12 words, it's the same address here.

### Spending limit

**Settings → Security → Set a spending limit.** "Ask for my PIN above" makes any single payment over that amount (fees included) wait for your PIN, even while the wallet is unlocked; it needs a PIN to be set. "At most … in any 24 hours" caps everything that leaves the wallet in the last 24 hours: what was paid, what is in flight (on this phone, in another tab, or interrupted and not settled yet), and fees. A payment that fails and comes back frees its part again, except a fee the mint kept. Leave a box empty to turn that limit off; without a PIN the per-payment box stays off (shown greyed out with why). With a PIN, the limits are stored inside the encrypted vault, and changing or removing them needs the PIN. Moves between your own mints count in full (a thief could add a mint of their own), and so do the sats you put in a duress PIN's wallet (the PIN you just entered lets them through). Limits belong to this device: restoring from your 12 words or a backup, or resetting, starts without them. A Wallet Connect app that asks for more is refused with QUOTA_EXCEEDED. What comes in (claiming a token, deposits, swapping a token into your mint) is never limited.

### Duress PIN

**Settings → Security → Set a duress PIN** (needs your PIN). Pick a second PIN, different from yours, and optionally put a few sats in its wallet. Unlocking with it opens that small separate wallet, with its own 12 words, balance and history, instead of yours. It's a full wallet: you can receive, pay and play with it. Only your real PIN can change or turn off the duress PIN; turning it off brings its sats back into your wallet.

### Starting over

**Settings → Backup → Reset wallet** deletes the wallet from this browser and returns you to the start screen to create a new one or restore one. Write down your 12 words and mints first if there are sats in it.

## Safety

- **PIN lock and encryption.** With a PIN set, your phrase, ecash, history and notes are stored encrypted (AES-256-GCM). The key is unlocked by your PIN (PBKDF2, 600,000 rounds) or by a Face ID / fingerprint passkey (WebAuthn PRF). Five wrong PINs trigger a growing wait, and the wallet locks itself after the time you choose. A PIN stops someone who picks up your phone; it can't stop malware on a compromised device. If you forget it, reset and restore with your 12 words.
- **Recovery phrase first.** You can't use the wallet until you've written down your 12 words and confirmed them. Every piece of ecash is derived from them (NUT-13), and restoring scans your mints to rebuild your balance (NUT-09).
- **Interrupted payments are handled.** A failed Lightning payment returns your sats. A stuck one is tracked until the mint settles it. A deposit interrupted mid-way is recovered automatically the next time you open the app. A step the mint did is always booked as itself, never as "Ecash already spent elsewhere": when a repeat of the same request is refused (the library resends a request whose answer was lost to a mint that caches answers, NUT-19, and the mint's cache misses it; or two phones holding the wallet send the very same request), the answer is rebuilt from the mint's signatures for exactly the outputs on record; a step the mint is still working on stays open until it's done; and a step closed with nothing signed is kept aside for a day, so if its request reaches a slow mint late, it is settled again as itself (checked with one request per mint for all such steps, often at first and every 12 minutes after the first hour, and never while offline or in the background). Coins another device spent in a different way are still shown as spent elsewhere.
- **Mint list backup.** Your list of mints is saved to Nostr relays encrypted with a key from your 12 words (NUT-27, the same format cashu.me uses), so a restore can find them even if you lose your note. Only the list is saved, never ecash or amounts. You can turn this off in Settings → Backup.
- **Same phrase on two devices.** If a mint reports reused codes, NUTCADE catches up and retries on its own.
- **Wallet Connect keys are secrets too.** Each connection's key is stored like your phrase and ecash, encrypted when a PIN is set. The app's half of the link is shown once and never stored. A budget is checked before every payment, and payments are handled one at a time so two can't slip past it together.
- **Spending limit.** Every payment goes through one check, with the most it can cost (amount plus every fee), and that check and the hold on the amount happen in one step, so two taps, two mints paying at once or two tabs can't both slip under what is left. In-flight and interrupted payments count until they settle. See [Spending limit](#spending-limit).
- **Duress PIN: what it hides and what it can't.** With a PIN set, everything of a wallet (phrase, ecash, history, contacts, keys, and also its mint list, counters, logs, its own settings and trophies) lives inside the encrypted vault; plain storage keeps only the device's display settings, wrong-PIN tries and PIN changes, so it looks the same whichever wallet is open, and with or without a duress PIN. The vault always has a second encrypted part (random bytes until you set a duress PIN), and every PIN try runs both key derivations, so checking your PIN, the duress PIN or a wrong one takes the same time and gives the same messages; wrong tries count toward the same lockout. While the duress wallet is open, NUTCADE never decrypts, reads or writes your real wallet's data, makes no request about it, and the screens, settings, backups and errors show only the duress wallet. Changing the PIN, setting, changing or turning off a duress PIN and removing the PIN share one small allowance (3 in any 24 hours, the same in every wallet, not reset by unlocking); inside the duress wallet, a new PIN that would open your real wallet, a duress PIN of its own, Remove PIN and setting up Face ID all get the same "not available right now" answer as a used-up allowance, and use it up. Reset wallet inside the duress wallet empties only that wallet. Face ID / fingerprint unlock opens the real wallet only, so turn it off if you rely on the duress PIN. The sats you put in the duress wallet become its own coins (its own 12 words) right away, so a restore of your real words never finds them. A backup of your real wallet has no trace of the duress PIN, and turning the duress PIN off brings its sats back into your wallet with a history note. **What it can't do:** it helps against someone in front of you who makes you open the app. It does not help against someone who knows NUTCADE's (open) code and examines the phone: they can see that the vault has two encrypted parts and how big each is, try the steps above and notice the refusals, or copy the storage and test PINs elsewhere.
- **Mints that limit request size.** A mint may say how many items one request can carry (NUT-06 `max_array_length`). NUTCADE needs at least **128**: any amount is under 2^51 SAT, so at most 51 coins, and the biggest request a normal step makes (a token or the swap before a payment: the amount's coins, a few for the receiver's fee, and the change) is 108 outputs. A mint that says less can't be added. Its coin pick never takes more coins than the mint takes (the biggest coins first when needed); if even those are too many, the payment is refused before anything is sent. Checks and restores are asked in pieces of at most the mint's limit. If a mint you already use starts saying less than 128 (NUTCADE reads its info again when a request is refused), it takes no new deposits (Receive, moves into it, tokens swapped into it, Extra Life, the Lightning address are all refused before anything is paid), the Mints screen says so, and you can still move your sats out: in steps that fit, each recorded like any other, with the pay sheet saying that part of the unused fee reserve may be kept by the mint, inside its "Total, at most". Your own sats there always come back, in parts where needed: a token of yours taken back, a gift, bounty or treasure nobody opened, an Extra Life cashed out (or left to you), the 12 words on a new phone (the mint is added with its notice, and a restore never shows a silent 0: if nothing of yours is there, it says so and doesn't add the mint), another phrase swept in, and a backup. Someone else's token of that mint is new money in, so it's refused; its sender can still take it back.
- **One tab at a time.** If NUTCADE is open in a second tab, that tab pauses so the two can't overwrite each other.
- **Storage protection.** NUTCADE asks the browser not to clear its data, and Settings shows whether that was granted.
- **No outside code.** The app is one self-contained file with its fonts built in. The QR decoder loads from this same site, only when you open the scanner. Nothing is loaded from other servers.
- **Checked releases.** Every update runs the test suites automatically before it goes live, and the site publishes SHA-256 checksums at https://random21m.github.io/nutcade/SHA256SUMS.txt. Releases on GitHub include those checksums signed with the project's GPG key, [`nutcade-signing-key.asc`](nutcade-signing-key.asc) (fingerprint `2509 D115 03B7 2CBF BCB5  408F 4B72 9F05 6A52 9340`), and timestamped in Bitcoin with [OpenTimestamps](https://opentimestamps.org): v1.8.1's checksums are anchored in block 975,501 (11 November 2026). See [RELEASING.md](RELEASING.md) to check a copy yourself.
- **Shared GitHub domain.** GitHub serves every project site on an account from one domain (random21m.github.io), and browsers let pages on the same domain read each other's saved data. So only publish pages you trust under this account, and set a PIN: it keeps your phrase and ecash encrypted, so another page on the domain can't read them.

**Found a security problem?** Please report it privately, as described in [SECURITY.md](SECURITY.md), not in a public issue.

**Something else not working?** Use the [Report a problem form](https://github.com/Random21m/nutcade/issues/new?template=bug.yml) (also in **Settings → About**). Reports are public: never paste your 12 words, your PIN, a backup file or a token.

**Important:** your wallet lives in your browser. Keep your 12 words and your mint list somewhere safe and offline. Never type your words into a website or send them to anyone, including anyone claiming to be NUTCADE support. Mints hold the Bitcoin behind your ecash, so only use mints you trust. NUTCADE is young software that hasn't been independently audited, so start with small amounts.

## Testing

Every push runs the suites in `tests/` automatically on GitHub (GitHub Actions) against real Cashu mints (Nutshell), including mints set up to fail or stall payments. The site only updates if every check passes:

- 51 wallet checks: Lightning in and out, ecash between wallets, double-claim protection, failed and stuck payments, notes, multiple mints, backup files, and restoring from the phrase after a full wipe
- 27 settings checks: themes, ₿ display, backup download and import, restoring a phrase from another Cashu client, reset, and swapping received ecash into your own mint
- Crash recovery: a deposit interrupted mid-way comes back on the next open
- 28 PIN-lock checks: encryption at rest, wrong PINs and lockout, change and removal, Face ID / fingerprint unlock, auto-lock, and forgot PIN followed by restore
- 209 Round 7 checks: LNURL vouchers (limits, strict amounts, a triple tap asking once, every service error, a refused voucher paid later still minted, a slow service paying late, an invoice expiring), blocked mints (tokens, Nostr ecash, payment requests and deposits refused with the reason, Unblock, moving sats out, backup and restore), Nostr Wallet Connect (every method over NIP-44 and NIP-04, the info event and notifications, budgets per day and in total counting the mint's fees, a payment in flight through a reload keeping its budget and its change, change recovery that fails, is interrupted by reloads or races itself (on slow mints, and in two tabs) crediting the change exactly once, reloads in the middle of moving sats and of a payment split across mints, a restore from the 12 words finding nothing extra afterwards, real preimages, each app seeing only its own history, two payments racing a budget, requests over a minute old or sent while locked refused, repeated and stale requests, a failed payment, revoke, keys inside the PIN vault) and zaps (signed zap requests, no-zap endpoints, wrong invoice amounts, limits, anonymous zaps), against stand-in LNURL services and an NWC app that check every signature; plus every new screen in each language at 320, 375, 430 and 1440 pixels wide, no screen-reader label left in English, the most a payment can cost shown before paying, and the history adding up to the balance after every new money path; and interrupted steps: Find lost ecash while a payment, claim or token is in flight, deposits whose answer was lost (two at once, during scans, with a failed restore), reloads and takeovers mid-swap, coins already spent elsewhere, a mint that never answers, a preimage fetched later, and locked steps (gifts, bounties, Extra Life setup, CONTINUE, cash-out and heir claim, take-backs and reclaims) settling after a reload as exactly what they were, with every error message translated; Extra Life CONTINUE (one swap) interrupted every way on both mints, a takeover in the middle of CONTINUE or of a payment (the paused tab sends nothing more), no plain spendable coins anywhere with a PIN, a mint past its time limit named in the message, and a backup taken while a step is open settling on the restored device; importing older or repeated backups (every coin checked at its mint, no record settled twice, a mint that is down waiting aside), a browser that refuses Web Locks, a PIN on a wallet with a long history, and French written with vous
- 327 Round 8 checks: the spending limit on every way sats leave (Lightning, ecash, payment requests, bill splits, gifts, bounties, treasure hunts, Extra Life, moves, zaps, Lightning addresses, contacts, Wallet Connect, several mints at once, offline, a Numo-style checkout, the duress PIN's funding), what frees it (a token taken back, a failed payment), under, exactly at, one SAT over and over with the PIN, on a mint with fees and one without, with and without a PIN, three payments started at once, a payment in flight in another tab, a reload and the 24 hours moving on, and every kind of typed amount; the duress PIN (what each PIN opens, plain storage holding nothing of any wallet, no request to the real wallet's mints, every screen's text and buttons, unlock times, the real wallet's data untouched, shared lockout, the PIN-change allowance and the duress wallet's refusals, reset inside it, backups, change and turn off with its sats coming back); mints that limit request size (a mint of 3 items refused when added, in five languages, with and without fees; a mint at exactly 128 with 160 coins: coin picks within the limit, a payment needing too many coins refused with nothing sent, a restore, a 160-coin token claimed in parts; a mint that starts enforcing 3 later: the refused request and re-read info, the notice, Receive, a move in and a token swapped in all refused before paying, moving out in steps with an honest total; your own sats at a mint that dropped to 3, on a mint with fees and one without: a token taken back, an Extra Life cashed out, a gift, a bounty and a treasure nobody opened coming back, a 12-word restore on a new phone, a restore where nothing of yours is, a backup import and another phrase swept in, never a request over 3, while someone else's token there is still refused; the mint health panel's summary with that mint; "N SAT in flight." and the older-wallet notice in five languages with local number formatting; the journal, on a mint with fees and one without: a step the mint signed booked as itself after a NUT-19 resend (after a 502 and after a dropped connection), a refusal after signing (also with the tab killed at once) and the same request from two phones, a request reaching the mint late (after the reopened tab's first or second restore request, while the mint is still working on it, and after the step was settled), each with every coin held unspent, no "spent elsewhere" line and the 12 words finding the same balance, while coins another phone spent differently are still "spent elsewhere"; steps waiting aside checked with one request per mint, less often as they age, and never while offline); reset with a PIN and with a duress PIN leaving no vault; the duress wallet's sats being its own coins at once; phones held sideways (the main screens, a game and a payment usable, nothing lost when turning mid-game or mid-payment); the problem form; pinned actions; and every new screen in five languages at 320 px, with the PIN pad's OK on screen at 320x568
- 267 backup checks, on a mint with fees and one without: every kind of record a backup can hold (coins, a deposit whose answer was lost, a deposit paid but never claimed, tokens, gifts, bounties, Extra Life and CONTINUE, claims, treasure hunts, a payment in flight), backed up before the step, while the mint's answer is held, after it settles and after its coins were partly spent elsewhere, then imported into the same wallet, a fresh device, twice, and as a backup made while part of another waited for its mint, with the mint up or down (Check now) and with or without a PIN: the coins match the wallet that made the backup, the history adds up to the balance with no line twice and no fee the mint didn't keep, nothing is claimed twice, nothing is shown as holding coins the mint says were spent since (an Extra Life continued again elsewhere, a token claimed, a copy held as an heir, a bounty), and a restore from the 12 words finds nothing more; a backup restored on a second device while the first keeps using the wallet (a payment the mint refuses there books nothing, a deposit the first device collected is closed with no other coins); a request payment, a treasure hunt and a bounty's challenge that were cut off reach the other side exactly once; and every bounty, prize and Extra Life amount pattern translated at 999, 1,000, 2,500 and 1,234,567 SAT written the German, Spanish, Portuguese and French way
- Round 6 checks: every game played live with random input and replayed to exactly the same score and length, a challenge's replay verified and raced as a ghost, a faked bounty win refused and a real one paid, a treasure hunt opened with three of five cards (as a link and in the scanner), a slower hunter and a tampered card refused, an unopened hunt refunded, and a loaded card's QR code read back from the image and claimed
- Round 5 checks: Nut Flipper's physics (thousands of simulated games: the ball never leaves the table, and flipping keeps it in play), an animated QR scanned by a second browser through a (simulated) camera and claimed, a bounty won and released by a signed score, a bounty refunded after its date, an Extra Life continued, replaced, cashed out and finally claimed by the heir after the date, the mint report card, and translations
- 74 Round 4 checks: sending a token by sound from one browser to another through a (simulated) microphone, gifts locked to a contact and refunded after their date, a bill split paid off by a friend, mint health warnings and moving sats, cashier sales in Lightning and ecash, challenges sent and answered over Nostr (and a tampered one refused), the piggy bank countdown, and every new screen in each language at 320 pixels wide
- 37 checks for amounts in your currency, #tags and CSV export, contacts (Lightning address and ecash over Nostr), offline use, and languages
- 41 checks for multinut payments, payment requests (over Nostr and HTTP, including ecash sent by another wallet) and NFC reading and writing
- 39 checks for trophies, share cards, instant updates, the Nostr mint-list backup and the Lightning address, against a stand-in Nostr relay and npub.cash server that check every signature
- 24 scanner checks, run before release: camera scans of real tokens and invoices, photo scans, and recognising every kind of code
- All ten games played through to game over, with high scores, pause, exit, touch controls and sound
- The arcade clock: every cabinet takes 60 steps a second on a faked 30, 60, 120 and 144 Hz screen, a pause or tab switch never makes a game race to catch up, and recorded runs still verify as replays on every cabinet that has them (Nut Poker has none, by design)
- Nut Poker (43 rule checks and 88 play checks), Neon Road (69) and the Daily Challenge (138), each in five languages and at phone and desktop sizes; the arcade clock (15 checks); 37 arcade smoke checks, which include the GRAND TOUR trophy and the Support button in five languages
- Every screen at 320, 390, 768 and 1280 pixels wide, checked for overflow and clipped text, and again in each language

## Privacy

NUTCADE has no account, no tracking and no analytics. Your recovery phrase and notes stay in your browser, and mints only see the ecash you exchange with them. The app contacts other services only for these things:

- **Mints**: yours for every payment, and the ones listed in the mint picker to show whether they're online
- **Nostr relays, for the Daily Challenge**: only when you tap **Post** under **Share my score**, to publish the one note you just previewed
- **Coinbase**, for the price and chart, only while **Show Bitcoin price** is on
- **Nostr relays** (relay.damus.io, nos.lol, relay.primal.net), to send and receive game challenges with your contacts, to save your encrypted mint list when it changes and to look for it when you restore (turn this off in Settings → Backup), to receive payments for requests you made in the last 30 days, to deliver payments to requests you pay, to receive ecash friends send to your ecash address (turn this off in Settings → Privacy), and when you tap "Find mints people recommend". Payments you send over Nostr are signed with a one-time key, so they aren't linked to you. Challenges and their scores are signed with your NUTCADE Nostr key so friends know they're from you
- **npub.cash**, only while your Lightning address is turned on. It sees the amounts and times of payments to your address, not the rest of your wallet
- **The support address** (strike.me), only when you tip from inside the app

The **microphone** is used only while a Listen screen is open. The sound is decoded on your phone and nothing is recorded or sent anywhere.

## Sharing

Posting the link on X and most social sites shows a large preview card automatically. A bigger version of the picture for attaching to posts is at https://random21m.github.io/nutcade/nutcade-share.png.

## For maintainers

The app is one file, `public/index.html`, plus the QR decoder `public/zxing_reader.wasm` and the offline helper `public/sw.js`. `public/index.html` is built from the files in [`src/`](src/README.md): edit those, run `python3 build.py`, and commit both. On every push to `main`, `.github/workflows/test-and-deploy.yml` checks that the page matches `src/`, runs the test suites, and then publishes `public/` to GitHub Pages with fresh checksums. [RELEASING.md](RELEASING.md) covers running the tests yourself, cutting a release and signing it. Wallets people already have keep their sats, and visitors get the new version within a few minutes.

## Made by

<p><a href="https://github.com/Random21m"><img src="https://avatars.githubusercontent.com/u/344571732?v=4" alt="Random21m's GitHub profile picture" width="96"></a></p>

NUTCADE is made by **[Random21m](https://github.com/Random21m)**. Bug reports and ideas are welcome in [Issues](https://github.com/Random21m/nutcade/issues); security problems go through [SECURITY.md](SECURITY.md).

Follow NUTCADE on Nostr: **npub1mzmequd6893lj36mh5jcs9qayz0vf732m8qyycv79lfylyqv6gkqazgkys**

## Support the project

NUTCADE is free and open source, and it stays that way. Supporting it is optional and changes nothing about how it works. If you enjoy it, you can send a few sats over Lightning:

<p><img src="docs/support-qr.png" alt="QR code for the Lightning address keywest@strike.me" width="200"></p>

**keywest@strike.me**

You can also tip from inside NUTCADE: **Settings → About → Support**. The same address and code are on that screen. Be wary of any other "NUTCADE support" address.

## Changelog

- **v1.13.2:** the **Arcade Update**: two new cabinets and a Daily Challenge, plus a fix for fast games on fast screens.
  - **Nut Poker**: five-card draw video poker (jacks or better, 9/6 pay table) for free credits only. It is never linked to sats: no purchases, no cash-out, a free refill at 0 credits, and its score card can't be loaded with sats. Hands are dealt from a fair, cryptographically shuffled deck, so it has no challenges or replays.
  - **Neon Road**: a pseudo-3D night-highway racer with curves and hills, traffic, a clock with checkpoints, stages that change colours, a road built from the seed (so challenges and replays race the same course), keyboard and touch controls, and its own chiptune loop.
  - **Daily Challenge**: one cabinet and one seeded level a day for everyone (from the UTC date), a first-run-counts official score, a streak and history, and a Share my score note you post to Nostr only by tapping Post (or copy); clock changes, time zones, midnight UTC and offline posting are handled and tested in five languages. The eight old cabinets and Neon Road can be the daily; Nut Poker never is. The share preview now wraps at spaces instead of in the middle of a word.
  - **Fixed: games ran too fast on 120 Hz and 144 Hz screens.** The arcade took one game step per screen refresh, so every cabinet ran about twice as fast on a 120 Hz phone. It now runs a fixed 60 steps a second whatever the screen, catches up at most a few steps after a pause or a tab switch, and draws once per refresh. Replays and challenges count steps, so they verify as before.
  - The **GRAND TOUR** trophy now means every cabinet in the arcade ("Play all 10 cabinets"), counted from the cabinet list; players who already earned it keep it. A touch the system cancels (a call, a palm) no longer counts as letting go of Nut Flipper's plunger. The Daily's share sheet says "your relay" for one relay and "your 3 relays" for several, in every language. A made-up challenge link for Nut Poker now says plainly that the cabinet has no challenges, instead of offering to accept one. A result screen from one run can no longer land on the next cabinet you open.
  - Settings → About: the **Donate** button now says **Support** (its sheet was already called Support NUTCADE), in every language.
  - For developers: every cabinet lives in its own `src/game_*.js` and registers one factory in `window.NutCabinets` (see `src/README.md`).
- **v1.13.1:** a step the mint finished is always booked as itself, never as "Ecash already spent elsewhere", even when the connection drops, the app is closed, the mint answers late, or two phones holding the same wallet send the same step. When the mint turns down a repeat of a step it already did (as when the app resends one whose answer was lost), NUTCADE takes the result from the mint's own signatures for that step, so a token you send is shown right away; a step the mint is still working on waits until it's done; and if a step's request reaches a slow mint after the app had given up on it, the step is settled again as itself. A Lightning deposit the mint already issued is credited, even when the mint turns down a repeat of it. Coins that another device really spent in a different way are still shown as spent elsewhere. (This could happen since 1.12.0; until now Find lost ecash brought the sats back.)
  - Known issues in v1.13.1: if a step's request reaches the mint more than a day after the app gave up on it, its coins stay in your balance until NUTCADE notices they were spent (the next time you pay with them, or at once with **Remove spent ecash**, next to Find lost ecash, which then shows them as "Ecash already spent elsewhere"). Running **Find lost ecash** before that can show those sats twice for a moment; Remove spent ecash puts it right. Nothing is lost. The other v1.13.0 known issues still apply.
- **v1.13.0:** a **spending limit** for the whole wallet (ask for the PIN above an amount per payment, and a cap per 24 hours, over every way sats leave, fees included, held for each payment in one step so two taps or two tabs can't both slip under it; kept in the PIN vault, changed only with the PIN; Wallet Connect apps get QUOTA_EXCEEDED); a **duress PIN** that opens a small separate wallet instead of yours (funded with coins of its own) (the vault always has room for it, both keys are tried on every PIN, and the real wallet is never read while the other is open; see Safety for what it can't hide); mints with a request limit (NUT-06 `max_array_length`): NUTCADE needs at least 128, a mint below that can't be added, coin picks stay within a mint's limit, restores and checks go in pieces, big tokens are claimed in parts, and a mint that drops below 128 takes no deposits but its sats can still move out, and your own sats there (tokens taken back, gifts, bounties and treasures coming back, an Extra Life, a restore from the 12 words, another phrase, a backup) always come back, in parts where needed; a **Report a problem** form (Settings → About); every GitHub Action pinned to a commit. Fixes: a treasure hunt (or any step) that moved sats and then failed redraws the screen at once; "Need X SAT including fees" counts the mint's fee to spend ecash; a token taken back on a mint with fees shows one fee line for what it cost; "already spent" with nothing to remove no longer says "removed 0 SAT"; long mint names and notes wrap instead of being cut off; "(part 1 of 2)" on its own, "N SAT in flight." on the wallet screen and the older-wallet notice are shown in your language.
  - Known issues in v1.13.0: Wallet Connect can't ask for your PIN, so a payment over a limit from an app is refused (nothing paid, nothing taken from its budget), never let through. A mint that accepts fewer than 128 items per request can't be used for deposits; if a mint you use drops below that, npub.cash may still try to pay your Lightning address there (turn the address off or point it at another mint), a Lightning invoice you made there before the drop and that is paid afterwards may stay pending until the mint accepts enough coins per request again (only when its new limit is very small), and moving out of it may leave part of a payment's unused fee reserve with the mint (shown before you pay). On such a mint, an Extra Life's CONTINUE is one swap that may need more coins than the mint takes; it is then refused with nothing sent, so cash it out and set it up again at another mint before its date. Someone else's token of that mint (a payment, a bounty you won, a treasure you found) isn't claimed there; its sender can take it back. Inside the duress wallet a duress PIN, Remove PIN and Face ID set-up aren't available (the same answer as a used-up PIN-change allowance), and Reset wallet there keeps the PIN; the allowance counter is plain device storage that someone with developer tools can read or clear (they could attack the vault directly anyway): someone who studies NUTCADE can notice these. Rarely, if the connection drops or the app is closed just as a mint finishes a step, that step's own sats can be shown as "Ecash already spent elsewhere" and left out of the balance (also in 1.12.x): nothing is lost, and **Find lost ecash** (or a restore from your 12 words) brings them back; fixed in v1.13.1. The v1.12.1 known issues still apply.
- **v1.12.1:** fixes for a backup restored on a second phone while the first phone keeps using the same wallet: a payment the mint refuses to the second phone (the first phone already claimed it) no longer shows up there as received with a matching "Ecash already spent elsewhere" line, and a deposit the first phone collected is closed on the second phone with nothing, instead of being credited with other coins of the wallet; only what the mint signed for a step is ever booked to it. A payment to a payment request that was cut off (a reload, a closed tab, a lost answer from the mint) now reaches the requester when the wallet is back, once, with the same ecash (and if it can't be delivered after several tries, the sats come back with a line that says so); a treasure hunt whose prize no relay took is published on a later start; a recovered bounty's challenge goes to your friend at most once; an heir's copy or an offered bounty whose mint was down when a backup came in is checked again later; a token saved offline and claimed since on the phone it was saved on no longer shows as "failed" on a phone restored from both backups. In German, Spanish, Portuguese and French, bounty, prize and Extra Life lines with amounts of 1,000 SAT or more are translated too. Also: send by sound is now an open standard ([docs/SOUND-SPEC.md](docs/SOUND-SPEC.md), with test recordings), the README shows how to add NUTCADE to your home screen on every device, and two automatic history notes are now translated.
  - Known issues in v1.12.1 (none of them changes your balance): a bounty restored from a backup taken while it was being made sends its challenge only from the phone that made it, so if that phone is gone your friend isn't told (the sats come back after its date); a token saved offline and claimed since on another phone with the same wallet shows as "already claimed by someone else" on a phone that hasn't imported the newer backup.
- **v1.12.0:** LNURL vouchers (LNURL-withdraw): load a voucher's sats into the mint you pick, with its description, limits and every error said plainly; block a mint so its tokens, requests and deposits are refused (always with the reason and an Unblock button) while the sats you hold there stay usable and can be moved out; Nostr Wallet Connect (NIP-47): connect apps with an optional budget per day, week, month or in total, NIP-44 and NIP-04, notifications, payments marked in your notes, rename and revoke; zaps (NIP-57) to contacts and any npub, signed with the wallet's Nostr key, with the invoice amount checked before paying and a plain Lightning payment offered when zaps aren't supported; all of it in every language; a new home-screen icon (installed copies pick it up after their next visit); backups carry everything still open, deposits waiting to be claimed and payment requests included, and restoring one anywhere (twice, into its own wallet, or a backup made while part of another waited for its mint) gives the same coins and history, with no fee the mint didn't keep
- **v1.11.0:** polish: a compact one-row header after setup so Receive, Send and Scan fit on small phones; game controls that always fit (the fire button no longer slides off narrow screens), with the hint above them and keyboard wording on computers; a PIN pad that fits a 320 px phone and shows one box per digit typed; toasts above the tab bar that never cover a title or a button, shorter and queued; sheets as centered dialogs on wide screens; bigger tap targets (40 px or more) and no text under 9 px in the pixel font; Amber and Green themes reach the inputs and the marquee, and Send stands apart from Receive in Green; amount labels that follow the SAT/currency switch; SAT next to every amount; one date style; friendlier mint errors; a styled file picker for importing backups; a mint you just added is graded NEW rather than F; the last English left in the other languages translated, and German says Optionen on both the tab and the screen; numbers grouped the way each language writes them (30.000, 30 000); a cashier that keeps every key on screen with big amounts; a PIN pad with six boxes that fill as you type; long names and notes that wrap instead of widening the page; keyboard use on computers (Tab stays in a dialog, Enter submits, Esc returns you where you were, and the cashier keypad takes number keys); amounts typed in your currency read the way your language writes them (1.234,56 in German); typed amounts are read exactly or refused with a reason, never guessed (whole SAT only, strict digit grouping, exact conversion from your currency, strict amounts in bitcoin: links, Bitcoin addresses checked by checksum); switching between SAT and your currency keeps what you typed; on mints with fees the fee shown is what the balance dropped by, and sending everything offers the most you can send after the fee; one spelling per mint address (saved twins are merged); Enter charges on the till; no duplicate contacts; the history always adds up to the balance, failed payments included (a fee the mint kept is its own line); an amount typed in SAT and viewed in your currency is charged as typed; everything on screen translated, the game screens and trophies included
- **v1.10.0:** replays that prove scores (cross-phone deterministic games), ghosts to race, bounties that only pay on a verified replay; treasure hunts with Shamir-split clue cards; loaded score cards that pay the first person to scan them
- **v1.9.0:** Nut Flipper, an eighth cabinet (pinball); high-score bounties locked with NUT-14 hash locks; Extra Life, ecash inheritance with NUT-11 time locks; a report card for every mint; animated QR codes (BC-UR, compatible with cashu.me) for long tokens, and scanning them; a joystick for the games on phones, with the D-pad still available
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

## License

NUTCADE is open source under the [MIT License](LICENSE).

## Open-source components

The page bundles these libraries (their license notices are at the end of the bundled script):

- [cashu-ts](https://github.com/cashubtc/cashu-ts)
- [noble-curves, noble-hashes, scure-base, scure-bip32, scure-bip39](https://paulmillr.com/noble/)
- [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator)
- [zxing-wasm](https://github.com/Sec-ant/zxing-wasm) (MIT) with [zxing-cpp](https://github.com/zxing-cpp/zxing-cpp) (Apache-2.0), the QR decoder
- [jsQR](https://github.com/cozmo/jsQR) (Apache-2.0), the fallback QR decoder
- [nostr-tools](https://github.com/nbd-wtf/nostr-tools) (Unlicense) and [noble-ciphers](https://github.com/paulmillr/noble-ciphers) (MIT), for signing Nostr events and NIP-44 encryption

The animated QR codes (`src/ur.js`) are NUTCADE's own implementation of the Blockchain Commons BC-UR specs (BCR-2020-005, 006 and 012). Its frames were checked against [@gandlaf21/bc-ur](https://github.com/gandlaf21/bc-ur), the library cashu.me uses, and come out identical.

Fonts: [Press Start 2P](https://fonts.google.com/specimen/Press+Start+2P) and [VT323](https://fonts.google.com/specimen/VT323), both under the SIL Open Font License.
