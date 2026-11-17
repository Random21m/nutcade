# NUTCADE Sound Transfer, version 1

| | |
|---|---|
| **Status** | Implemented in NUTCADE since v1.8.0. This document describes the code as it is; it adds no new behavior. |
| **License** | MIT, the same as the repository ([LICENSE](../LICENSE)). |
| **Code** | Modem: [`src/chiptune.js`](../src/chiptune.js) (SHA-256 `77cb1714…c1c48f9`, the file timestamped in Bitcoin, see the README). Payload layer and screens: [`src/app_r4.js`](../src/app_r4.js) (`packToken`, `unpackToken`, `soundBytes`, `soundText`, `openSoundSend`, `openListen`). Receiving: [`src/app.js`](../src/app.js) (`classify`, `handleScan`). Simulator: [`tools/chiptune_sim.js`](../tools/chiptune_sim.js). Vectors: [`docs/sound-vectors/`](sound-vectors/). |

The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119. Sections 3 and the payload format in section 2 are normative; the decoder in section 4 is one way to receive the signal and is informative.

The transfer has two layers:

1. **Payload layer** (`src/app_r4.js`): turns the text on screen (a token, request, invoice...) into a byte string, the *payload*.
2. **Modem layer** (`src/chiptune.js`): turns the payload into frames, symbols and audio, and back.

## 1. Overview

A sender plays one *pass* of the signal on a loop until the user stops it. A pass carries the payload, followed by a CRC-32, split into frames of up to 48 bytes. Each frame starts with a fixed 8-symbol preamble and ends with a CRC-16. Each 20 ms symbol carries one byte as two simultaneous tones: the high nibble picks one of 16 tones in a low bank (1500 to 4500 Hz), the low nibble one of 16 tones in a high bank (5000 to 8000 Hz). A receiver keeps every frame whose CRC-16 is good, from any pass, and finishes when it holds frames 0 to *total*−1 and the CRC-32 over the joined payload is good.

## 2. What it carries

*Source: `src/app_r4.js`, `soundBytes()`, `soundText()`, `packToken()`, `unpackToken()`; `src/app.js`, `classify()`, `handleScan()`.*

**Where NUTCADE offers Play as sound** (`ctBtn(...)` calls): a sent ecash token or locked gift (`src/app.js`, the token screen and the pending-token notice), a NUT-18 payment request (`src/app.js` request screen; `src/app_r4.js` bill split), the cashier charge screen (a Lightning invoice, or an ecash payment request; `src/app_r4.js`), and an Extra Life heir's copy, which is a token (`src/app_r5.js`). Anything else the user passes would also work, since non-token text travels as plain text.

### 2.1 Sender: text to payload (`soundBytes`)

1. Run `classify(text)`. If it is a token (the text contains `cashuA` or `cashuB` followed by at least 20 base64/base64url characters), decode it with cashu-ts `getDecodedToken` and pack it in the **packed token form** (2.2). If decoding or packing throws for any reason, fall through to step 2.
2. Otherwise the payload is the UTF-8 encoding of the text, unchanged (`new TextEncoder().encode(String(text))`). This is how payment requests (`creqA...`, `creqb1...`), Lightning invoices and everything else travel.

There is no separate type byte for text. The first payload byte tells the two apart: `0xC1` never occurs in valid UTF-8, so a payload starting with `0xC1` cannot be text.

Packing fails, and the token travels as text instead, when: a keyset id is not even-length hex (for example an old base64 keyset id), a signature `C` is not `02`/`03` followed by 64 hex digits, or cashu-ts refuses the token (a multi-mint `cashuA` token does: checked, it travels as text).

### 2.2 Packed token form

`vint` is an unsigned LEB128 integer: 7 bits per byte, least significant group first, bit 7 (`0x80`) set on every byte except the last. `str` is `vint(byte length)` followed by that many UTF-8 bytes. `hex` fields are raw bytes (two hex digits per byte).

```
payload   = 0xC1  str(mint)  str(unit)  str(memo)  vint(G)  group × G
group     = vint(id_len)  id[id_len]  vint(P)  proof × P        ; id_len = keyset id length in bytes
proof     = vint(amount)  flags  secret  C[33]  [str(witness)]
flags     = bit 0: 1 = secret is a str, 0 = secret is 32 raw bytes
            bit 1: 1 = a witness follows
            other bits 0
secret    = 32 raw bytes        if the secret matches /^[0-9a-f]{64}$/ (lowercase only)
          | str(secret)         otherwise (P2PK/HTLC JSON secrets, uppercase hex, anything else)
```

- `mint` is the token's mint URL as decoded; `unit` defaults to `sat`; `memo` is empty when there is none.
- Proofs are grouped by keyset id, groups in order of first appearance, proofs in token order within a group.
- `witness` is sent as a string; an object witness is sent as its `JSON.stringify` form.
- **Dropped on purpose:** DLEQ proofs, and every proof or token field other than those above. The receiving wallet swaps the ecash with the mint anyway (comment in `src/app_r4.js`).

### 2.3 Receiver: payload to text (`soundText`)

1. First byte `0xC1`: unpack 2.2 and re-encode with cashu-ts `getEncodedToken({ mint, unit, proofs, memo? })` (memo omitted when empty). Hex fields come back lowercase. If bytes are left over after the last proof, it is an error. NUTCADE's bundled cashu-ts produces a `cashuB` (V4) token, so a `cashuA` token sent by sound arrives as the same proofs in a `cashuB` string; a `cashuB` token without DLEQ data comes back byte for byte (all three vectors do).
2. Else, if the payload is longer than 5 bytes and starts with ASCII `crawB`: it is cashu-ts's binary V4 token (`getEncodedTokenBinary`), and the text is `cashuB` + base64url (no padding) of the bytes after `crawB`. NUTCADE never sends this form; it only accepts it.
3. Else: UTF-8 decode (`TextDecoder`, non-fatal, so invalid bytes become U+FFFD).

The text then goes to `handleScan()`, exactly as if a QR code had been scanned: tokens open Receive, payment requests open the pay screen, invoices open a melt quote for the user to confirm, and so on (tokens, `creqA`/`creqb1` requests, `npub`/`nprofile`, `bitcoin:` URIs, `lnbc`/`lntb`/`lnbcrt`/`lntbs` invoices, LNURL, Lightning addresses, on-chain addresses, mint URLs, single-part `ur:bytes`, NUTCADE challenge and treasure-hunt links). Nothing is paid without the user's usual confirmation.

## 3. Encoding (modem layer)

*Source: `src/chiptune.js`, constants at the top, `crc16`, `crc32`, `frames()`, `symbolsFor()`, `encode()`, `seconds()`, `play()`.*

### 3.1 Constants

| Name | Value | Meaning |
|---|---|---|
| `SYM` | 0.020 s | symbol duration |
| `WIN` | 0.015 s | decoder analysis window (section 4) |
| `GAP_SYMS` | 2 | silent symbols after each frame |
| `FRAME` | 48 | maximum data bytes per frame |
| `MAGIC` | `0x4E` (`'N'`) | first header byte of every frame |
| `LOW[k]` | 1500 + 200·k Hz, k = 0..15 | 1500, 1700, ..., 4500 Hz |
| `HIGH[k]` | 5000 + 200·k Hz, k = 0..15 | 5000, 5200, ..., 8000 Hz |
| `PRE` | `[0,15] [15,0] [0,15] [15,0] [0,15] [15,0] [5,10] [10,5]` | preamble, as `[low index, high index]` |

### 3.2 Message and frames (`frames()`)

1. `message = payload ‖ CRC32(payload)`, the CRC-32 written as 4 bytes **big-endian**.
2. `total = ceil(len(message) / 48)`. If `total > 250` the sender refuses ("That is too long to send as sound."). So the payload is at most 11,996 bytes.
3. Frame *i* (i = 0..total−1) carries `part = message[48·i .. 48·i+48)`; only the last part can be shorter. The CRC-32 is not treated specially and can be split across the last two frames.
4. Frame bytes:

```
offset  0      1      2      3      4 .. 4+len-1   4+len        5+len
        0x4E   i      total  len    part           CRC16 high   CRC16 low
```

`len` is 1..48. The CRC-16 covers bytes 0 to 3+len (header and part, not the preamble) and is written **big-endian**.

**CRC-16:** CRC-16/CCITT-FALSE: polynomial `0x1021`, initial value `0xFFFF`, not reflected, no final XOR. Check value: `"123456789"` → `0x29B1`.
**CRC-32:** the common CRC-32 (ISO-HDLC / zlib): reflected polynomial `0xEDB88320`, initial value `0xFFFFFFFF`, final XOR `0xFFFFFFFF`. Check value: `"123456789"` → `0xCBF43926`.

### 3.3 Symbols (`symbolsFor()`)

A pass is, for each frame in order 0, 1, ..., total−1:

```
8 preamble symbols (PRE)   then   one symbol per frame byte   then   2 silent symbols
```

A data byte `b` is the symbol `[b >> 4, b & 15]`: tone `LOW[b >> 4]` plus tone `HIGH[b & 15]`. Example: `0x4E` → 2300 Hz + 7800 Hz. The preamble symbols equal the bytes `0F F0 0F F0 0F F0 5A A5`. A frame with *len* data bytes is 8 + (6 + len) + 2 = 16 + len symbols, 64 symbols (1.28 s) at most.

### 3.4 Audio (`encode(data, sr)`)

- **Sample rate:** whatever the sender's audio output runs at (`AudioContext.sampleRate`, usually 44,100 or 48,000 Hz). The format is defined in seconds and hertz, not samples. `encode()` defaults to 48,000 Hz, the rate of the WAV vectors. All values below are rounded to whole samples with `Math.round`.
- **Symbol:** `n = round(0.020·sr)` samples (960 at 48 kHz, 882 at 44.1 kHz). Silent symbols are `n` zero samples.
- **Lead and tail:** `round(0.150·sr)` zero samples before the first symbol and after the last.
- **Tone shape:** for sample `i` of a symbol, with `A` = phase of the low tone and `B` = phase of the high tone:
  `x = env · 0.45 · ( 0.5·tanh(2.2·sin A)/tanh(2.2) + 0.5·tanh(2.2·sin B)/tanh(2.2) )`
  The soft clip (tanh) gives the 8-bit buzz; peak amplitude is 0.45 of full scale.
- **Envelope:** `env = min(1, i/ramp, (n−1−i)/ramp)` with `ramp = round(0.002·sr)`: a 2 ms linear rise and fall inside each symbol.
- **Phase:** `A` and `B` start at 0 at the start of the pass and advance by `2π·f/sr` per sample only while a tone plays; they are not reset between symbols. (Phase continuity is not needed to decode; it is how the reference sounds.)

### 3.5 Looping (`play()`)

The pass is put in a Web Audio buffer with `loop = true` and plays until stopped, so the 0.15 s tail of one pass and the 0.15 s lead of the next make a 0.3 s silence between passes. Every pass is identical: same frames, same order. A pass lasts `seconds() = 0.020 · (number of symbols) + 0.3` s, that is

```
seconds = 0.020 · (16 · total + len(message)) + 0.3          len(message) = len(payload) + 4
```

## 4. Decoding (informative)

*Source: `src/chiptune.js`, `class Decoder` (`push`, `analyse`, `sym`, `frameAt`, `scan`, `finish`), `listen()`.*

A receiver MAY decode any way it likes. NUTCADE's decoder:

- **Input:** microphone with `echoCancellation`, `noiseSuppression` and `autoGainControl` all off, in blocks of 4096 samples (a `ScriptProcessor`), at the device's sample rate. It keeps up to 8 s of samples; when full, it keeps the last 4 s.
- **Grid:** it analyses every *hop* of `n/4` samples (5 ms; fractional hops are rounded). Each hop is a 15 ms window (`round(0.015·sr)` samples) centred in a 20 ms slot, weighted with a Hann window `0.5 − 0.5·cos(2πi/(w−1))`.
- **Tone detection:** 32 Goertzel filters at the exact tone frequencies (coefficient `2·cos(2πf/sr)`, power `s1² + s2² − k·s1·s2`), no FFT and no bins.
- **Symbol decision (`sym`):** in each bank, the tone with the highest power wins. Its confidence is its power divided by the bank's total power. A symbol is accepted when the lower of the two confidences is above **0.22**. Against echo, the power of the same tone one symbol earlier (4 hops back) can be subtracted first, scaled by *a*, with negatives clipped to 0. Each candidate frame is tried with *a* = 0, then 0.4, then 0.8; the first that passes the checks below wins ("noise favours a = 0, echo favours a > 0, so the CRC says which one was right").
- **Frame sync (`frameAt`):** at each hop, read 8 symbols 4 hops apart. At least 7 of the 8 must match the preamble. The start is then moved by −1, 0 or +1 hop, whichever gives the highest summed confidence over the 8 preamble slots. The data bytes follow every 4 hops. A data symbol below the 0.22 threshold is still read with its best guess (the CRC decides).
- **Header checks:** magic `0x4E`; `1 ≤ len ≤ 48`; `total ≥ 1`; `i < total`; then the CRC-16. A frame that fails any check is ignored and the search goes on one hop later. After a good frame the search resumes at the frame's end.
- **Collecting:** good frames are stored by index `i`; a repeat overwrites the earlier copy, so duplicates are harmless. A missed frame is simply caught on a later pass. If a good frame arrives with a different `total` than the frames held, the held frames are discarded (a new message). There is no message id beyond `total`.
- **Completion (`finish`):** when frames 0..total−1 are all held, they are joined, the held frames are cleared, and the last 4 bytes must equal the CRC-32 (big-endian) of the rest; the message must be at least 5 bytes. On a CRC-32 failure everything is discarded and collecting starts over. A message already delivered (same first 64 bytes and same length) is not delivered twice by the same decoder. NUTCADE stops listening after the first message (`openListen`).
- **Level meter:** a smoothed peak level drives the on-screen meter only.

## 5. Timing

*Source: `src/chiptune.js`, `seconds()`; measured with `tools/chiptune_sim.js` and the vectors' scripts, Node v22.*

| Payload | Message | Frames | One pass |
|---|---|---|---|
| Vector 1: 1-proof token, packed, 112 B | 116 B | 3 | **3.58 s** |
| Vector 2: payment request, 265 B text | 269 B | 6 | **7.60 s** |
| Vector 3: 6-proof token (one P2PK), packed, 600 B | 604 B | 13 | **16.54 s** |
| Simulator default: 600 random bytes | 604 B | 13 | 16.5 s |

The same `testnut.cashu.space` token with 1, 2, 3, 4, 6, 8 and 10 proofs packs to 112, 179, 246, 313, 447, 582 and 718 bytes: 3.6, 5.2, 7.2, 8.9, 12.5, 16.2 and 19.9 s a pass. Sent as text instead, the same tokens would take 6.5 to 41.8 s. Full frames move 48 bytes in 64 symbols, 37.5 payload bytes a second (the raw symbol rate is 50 bytes a second). A longer mint URL or memo adds to each token.

`node tools/chiptune_sim.js` (resampled to 44.1 kHz, 80 ppm clock drift, echo at 12 and 31 ms, white noise, starting 37% into a pass, three passes available) decodes 600 bytes in 16.9 s of listening at 12, 6, 3, 0 and −3 dB SNR, at 300 and 1000 ppm drift, and at 48 kHz; 18.2 s at −6 dB; 3.7 s for 120 bytes; 33.4 s for 1200 bytes. Its last line, a synthetic room reverb test (`reverbTest`, RT60 0.25 s), printed `-- reverb 0.5:false 1:false 2:false 3:false` in this build: the decoder did not recover that signal at any of the four reverb levels. Real rooms are not covered by the simulator; the README advises holding the phones close in a fairly quiet room.

## 6. Security and privacy

- **Anyone in earshot can capture the payload**, exactly like photographing a QR code. A captured token can be claimed by whoever swaps it first. NUTCADE warns about this on the Play screen for tokens.
- **No encryption and no authentication in v1.** The CRCs detect errors, not tampering; anyone can play a signal to a listening phone. The receiver treats the result like a scanned QR code, with the same confirmations.
- **No DLEQ proofs** travel in the packed form, so the receiver cannot check the mint's signatures offline; it swaps with the mint.
- **Use locked tokens in public places.** The packed form keeps P2PK (NUT-11) secrets and witnesses intact (string secret, flags bit 0 and bit 1; vector 3 includes a P2PK proof), so a token locked to the receiver's key is safe to play aloud: an eavesdropper cannot spend it. NUTCADE's "gifts locked to one person" (NUT-11, `src/app_r4.js`) can be played as sound.
- The microphone runs only while a Listen screen is open; audio is decoded on the device and nothing is recorded or sent (README, Privacy).

## 7. Compatibility rules

To interoperate with NUTCADE v1, an implementation:

**MUST match**
- the tone tables `LOW`/`HIGH`, the nibble-to-bank mapping (high nibble → low bank), and the 20 ms symbol;
- the preamble `PRE`, the frame layout, `MAGIC = 0x4E`, the 48-byte maximum, the 250-frame limit, and the 2-symbol gap;
- CRC-16/CCITT-FALSE per frame and CRC-32 per message, both big-endian, over exactly the bytes in 3.2;
- the payload rules of section 2: UTF-8 text, or the `0xC1` packed token form; a receiver MUST accept both, and SHOULD accept `crawB`;
- for a sender: repeat identical passes until the user stops; for a receiver: collect frames across passes by index.

**MAY differ**
- the waveform: pure sines instead of soft-clipped ones, other amplitude, envelope and ramp; the 0.3 s silence between passes; the sample rate (it must be above 16 kHz to carry the 8000 Hz tone);
- the whole decoding method (section 4 is one way);
- whether a sender packs tokens (a token sent as UTF-8 text is valid, just about twice as slow) and the token version a receiver re-encodes to.

**Versioning.** v1 has **no version field.** The only markers are the frame magic `0x4E` and the payload's first byte (`0xC1` packed token, `crawB` binary token, anything else text). A v1 receiver ignores any frame whose magic is not `0x4E`, and decodes a payload with an unknown first byte as UTF-8 text, which normally matches nothing in `classify()` and is refused like an unknown QR code.

> **Suggestion for v2 (not implemented):** signal v2 with a new frame magic byte (for example `0x4F`) so v1 receivers drop v2 frames cleanly instead of mixing them, and keep the preamble so one listener can sync to both. New payload types should start with a byte that cannot begin valid UTF-8 (`0x80`–`0xC0` or `0xF5`–`0xFF`; `0xC1` is taken). A v2 could also add a message id to the header, so two messages with the same frame count can't mix (see section 9).

## 8. Test vectors

*Files: [`docs/sound-vectors/`](sound-vectors/). All ecash in them is FAKE: made-up secrets and signatures, keyset id `00ad268c4d1f5826`, test mint `https://testnut.cashu.space`. It cannot be redeemed.*

| File | What |
|---|---|
| `vectors.json` | per vector: input text, payload hex, CRC-32, every frame in hex, frame count, seconds per pass, sample count |
| `v1-short-token.wav`, `v2-payment-request.wav`, `v3-long-token.wav` | one pass each, mono, 16-bit PCM, 48,000 Hz (336 KB, 713 KB, 1.6 MB) |
| `nutcade.js` | loads NUTCADE's own code into Node unchanged: `src/chiptune.js`, the payload functions sliced out of `src/app_r4.js`, `classify()` from `src/app.js`, and the bundled cashu-ts (`src/lib.min.js`) |
| `make_vectors.js` | builds the vectors with `soundBytes()` and `Chiptune.encode()`, and prints the frames with the private `frames()`/`crc32()` of `src/chiptune.js` (run from its own source text) |
| `decode_wav.js` | decodes each WAV with `Chiptune.Decoder` and `soundText()`, and checks the text |

The WAV samples are `round(clamp(x, −1, 1) · 32767)`. Their SHA-256 (Node v22) are `f6eb5e66…0fc026a9`, `8014d6ad…fbd17733`, `b1e1cd9b…52bc29a0`; another JavaScript engine's `Math.sin`/`Math.tanh` can differ in the last bit and change a sample by one step, so compare frames and decoded text, not WAV hashes.

### Vector 1: short token (1 proof, 8 sat), packed

Input (226 bytes):
```
cashuBo2FteBtodHRwczovL3Rlc3RudXQuY2FzaHUuc3BhY2VhdWNzYXRhdIGiYWlIAK0mjE0fWCZhcIGjYWEIYXN4QDBhNzBiZWNlNjI3NDE4OTViNjAzNDhkZGYxMWVhNWZlNzRkNDBlYzkyYWRmOTBlNzU2Y2U4NzMwOWZlYTUzYjdhY1ghAlcKyd1Y-tBM5tuSYgYsXkeG-6p5hXhJ9SzQKJhD4U6I
```
Payload (112 bytes), annotated:
```
c1                                                         packed token
1b 68747470733a2f2f746573746e75742e63617368752e7370616365  mint (27 bytes) "https://testnut.cashu.space"
03 736174                                                  unit "sat"
00                                                         memo ""
01                                                         1 keyset group
08 00ad268c4d1f5826                                        keyset id (8 bytes)
01                                                         1 proof
08                                                         amount 8
00                                                         flags: hex secret, no witness
0a70bece62741895b60348ddf11ea5fe74d40ec92adf90e756ce87309fea53b7    secret (32 bytes)
02570ac9dd58fad04ce6db9262062c5e4786fbaa79857849f52cd0289843e14e88  C (33 bytes)
```
CRC-32 `bc04b8fc`. Frames (3; 3.58 s a pass):
```
4e000330c11b68747470733a2f2f746573746e75742e63617368752e73706163650373617400010800ad268c4d1f58260108000a20ec
4e01033070bece62741895b60348ddf11ea5fe74d40ec92adf90e756ce87309fea53b702570ac9dd58fad04ce6db9262062c5e47ea91
4e02031486fbaa79857849f52cd0289843e14e88bc04b8fc9164
```
Frame 0 reads: magic `4e`, index `00`, total `03`, length `30` (48), 48 data bytes, CRC-16 `20ec`. The last frame holds the last 16 payload bytes and the 4 CRC-32 bytes (`14` = 20 bytes).

### Vector 2: payment request (NUT-18, 2100 sat), text

Input (265 bytes; sent as these exact UTF-8 bytes, so the payload hex is the input in hex):
```
creqApmF0gaNhdGVub3N0cmFheGlucHJvZmlsZTFxeTI4d3VtbjhnaGo3dW45ZDNzaGp0bnl2OWtoMnVld2Q5aHNxZ3hzanM4amxxbmFycjVxdzhudGh5YWw1bGZyM3ZtZXgzMmt2cW0yYzY1MjNqN3k0NGYzZXNjaDlwcGthZ4GCYW5iMTdhaWhhMWIyYzNkNGFhGQg0YXVjc2F0YW2BeBtodHRwczovL3Rlc3RudXQuY2FzaHUuc3BhY2VhZGZjb2ZmZWU=
```
CRC-32 `5e064d49`. Frames (6; 7.60 s a pass):
```
4e0006306372657141706d463067614e686447567562334e30636d466865476c7563484a765a6d6c735a5446786554493464335600e0
4e01063074626a686e61476f33645734355a444e7a61477030626e6c324f57746f4d6e566c6432513561484e785a33687a616e4d6711
4e02063034616d7878626d4679636a5678647a6875644768355957773162475a794d335a745a58677a4d6d743263573079597a598e09
4e030630314d6a4e714e336b304e47597a5a584e6a61446c77634774685a344743595735694d546468615768684d574979597a4eaddf
4e0406306b4e474668475167305958566a63324630595732426542746f64485277637a6f764c33526c6333527564585175593246f631
4e05061d7a6148557563334268593256685a475a6a62325a6d5a57553d5e064d49ada5
```

### Vector 3: long token (6 proofs, 1000 sat, one P2PK-locked, memo), packed

Input (1121 bytes):
```
cashuBpGFteBtodHRwczovL3Rlc3RudXQuY2FzaHUuc3BhY2VhdWNzYXRhdIGiYWlIAK0mjE0fWCZhcIajYWEZAgBhc3hAN2U0NGUyMmEyZTBjZGM5MWFmOTBjMTY4ZWFlY2E3NTNhN2Q3YjRhMjBiOTNkYThlNzBkNzZlNDY5NjBjNTdiNWFjWCECqpp5zGwFu7ZnZU3yEv_p-zCSC56jublv0Kb2BAREFuWjYWEZAQBhc3hAMDJmMzY5ZWE3NmEyMDAwNWFlMDE4NTI0MjU2ODlhNWIzODVkY2E3Y2Y4YmE2NWNmMWE0ZDNmNTNmNGE1Y2E2YmFjWCECKj2byB_hoVsSvsJeopA57UxLCKfTabZJkFhyb5Mf04mjYWEYgGFzeEAxOTRjOWYxZTIzMzg0OWNkZGIxMWUyNzQwOTRkZjY4NDQ5NjYyZjIyMWE4Yjk3MTRjM2ZkYWVlY2U0YmFlZDZiYWNYIQJBZxgHkGjGzxsbAfO1-yc594NFMRRoanWmmOftTgMi46NhYRhAYXN4QGQ2MTc2ODZlNWYxZWNiZWI1MjdlMzJiZGE3ZjA5ODNjZjc5YTFkMzUyMjA3ZTdkMjQ2MGZkZjI5MzhkZGZjYmNhY1ghAmrabu7dfHkPBLrhJZ9usl821y_YIcXutkS0cKMEGdnho2FhGCBhc3hAODc4NjhmZGZjZDQzMDA3MTM5ZTgzNTFlY2RlNTc1NGJjNzc5ZGUzMjZmOTNkZjI5MDFhYWY1ZWZkNTQ2MWZmMGFjWCECoyt1epJEH0IbYUkOVApYlX9rkaQgT4p2rTSt_jb3HlijYWEIYXN4o1siUDJQSyIseyJub25jZSI6IjQyNTk1NDY5YmM0NTM1MjEwNTg1MTY1OWExNTk0MDc4IiwiZGF0YSI6IjAyZDAyNTE2YmFiNmJjNmIzOTNmZWE4YzRlN2NjYjk1M2ZlNGMxNzgzZTE3NTZhN2Q0YWI4MDFmZDhjNzZiY2ExNiIsInRhZ3MiOltbInNpZ2ZsYWciLCJTSUdfSU5QVVRTIl1dfV1hY1ghAr97vJ6lmqQtTk0RLVr4S0FzZrRAedh63QxP0iLVqP-vYWRxc291bmQgdGVzdCB2ZWN0b3I
```
Payload: 600 bytes (in `vectors.json`). It starts `c1 1b <mint> 03 736174 11 <"sound test vector"> 01 08 00ad268c4d1f5826 06`, then the first proof `8004` (amount 512 as a vint) `00` (hex secret) ..., and the last proof `08 01` (amount 8, string secret) `a301 5b2250325042...` (a 163-byte P2PK secret). CRC-32 `fad29ac8`. Frames (13; 16.54 s a pass):
```
4e000d30c11b68747470733a2f2f746573746e75742e63617368752e73706163650373617411736f756e642074657374207665637ff3
4e010d30746f72010800ad268c4d1f5826068004007e44e22a2e0cdc91af90c168eaeca753a7d7b4a20b93da8e70d76e46960c57e073
4e020d30b502aa9a79cc6c05bbb667654df212ffe9fb30920b9ea3b9b96fd0a6f604044416e580020002f369ea76a20005ae01857f74
4e030d302425689a5b385dca7cf8ba65cf1a4d3f53f4a5ca6b022a3d9bc81fe1a15b12bec25ea29039ed4c4b08a7d369b64990583edc
4e040d30726f931fd389800100194c9f1e233849cddb11e274094df68449662f221a8b9714c3fdaeece4baed6b02416718079068fb94
4e050d30c6cf1b1b01f3b5fb2739f783453114686a75a698e7ed4e0322e34000d617686e5f1ecbeb527e32bda7f0983cf79a1d353abe
4e060d302207e7d2460fdf2938ddfcbc026ada6eeedd7c790f04bae1259f6eb25f36d72fd821c5eeb644b470a30419d9e1200087b238
4e070d30868fdfcd43007139e8351ecde5754bc779de326f93df2901aaf5efd5461ff002a32b757a92441f421b61490e540a58955231
4e080d307f6b91a4204f8a76ad34adfe36f71e580801a3015b225032504b222c7b226e6f6e6365223a22343235393534363962635d43
4e090d3034353335323130353835313635396131353934303738222c2264617461223a22303264303235313662616236626336624763
4e0a0d303339336665613863346537636362393533666534633137383365313735366137643461623830316664386337366263614154
4e0b0d303136222c2274616773223a5b5b22736967666c6167222c225349475f494e50555453225d5d7d5d02bf7bbc9ea59aa42df20c
4e0c0d1c4e4d112d5af84b417366b44079d87add0c4fd222d5a8ffaffad29ac8d285
```

### Decode proof

Each WAV is decoded three ways with NUTCADE's own `Decoder` and `soundText()`: the clean pass; two passes joined and heard from the middle of the first (so frames arrive out of order and are stitched across passes); and that signal with white noise at 6 dB SNR.

```
$ node docs/sound-vectors/make_vectors.js
v1-short-token token text 226 B -> payload 112 B, 3 frames, 3.58 s/pass, 171840 samples
v2-payment-request request text 265 B -> payload 265 B, 6 frames, 7.6 s/pass, 364800 samples
v3-long-token token text 1121 B -> payload 600 B, 13 frames, 16.54 s/pass, 793920 samples
$ node docs/sound-vectors/decode_wav.js
v1-short-token [clean] OK: 112 payload bytes, frames heard 1/3 2/3 3/3, text matches input
v1-short-token [from mid-pass] OK: 112 payload bytes, frames heard 1/3 2/3 3/3, text matches input
v1-short-token [mid-pass + noise 6 dB] OK: 112 payload bytes, frames heard 1/3 2/3 3/3, text matches input
v2-payment-request [clean] OK: 265 payload bytes, frames heard 1/6 2/6 3/6 4/6 5/6 6/6, text matches input
v2-payment-request [from mid-pass] OK: 265 payload bytes, frames heard 1/6 2/6 3/6 4/6 5/6 6/6, text matches input
v2-payment-request [mid-pass + noise 6 dB] OK: 265 payload bytes, frames heard 1/6 2/6 3/6 4/6 5/6 6/6, text matches input
v3-long-token [clean] OK: 600 payload bytes, frames heard 1/13 2/13 3/13 4/13 5/13 6/13 7/13 8/13 9/13 10/13 11/13 12/13 13/13, text matches input
v3-long-token [from mid-pass] OK: 600 payload bytes, frames heard 1/13 2/13 3/13 4/13 5/13 6/13 7/13 8/13 9/13 10/13 11/13 12/13 13/13, text matches input
v3-long-token [mid-pass + noise 6 dB] OK: 600 payload bytes, frames heard 1/13 2/13 3/13 4/13 5/13 6/13 7/13 8/13 9/13 10/13 11/13 12/13 13/13, text matches input
```
"Frames heard" counts distinct frames held. The decoded text equals the input byte for byte in all nine runs, and `decode_wav.js` exits non-zero if any run fails.

Also checked with the same harness: the binary `crawB` form of vector 1 (cashu-ts `getEncodedTokenBinary`, 170 bytes) comes back through `soundText()` as the identical `cashuB` string; a multi-mint `cashuA` token is not packed and travels as text.

## 9. Ambiguities and limits in the v1 code

Stated as found, not fixed:

1. **No version field** (section 7).
2. **No message id.** Frames are told apart only by `total`. Two different messages with the same frame count heard at once can mix; the CRC-32 then fails, all frames are dropped, and collecting starts over, so a mix costs a pass but never yields a wrong message (barring a CRC-32 collision).
3. **One bad frame costs everything held.** On a CRC-32 failure the decoder discards all frames, not only a suspect one.
4. **Silent fallback to text.** A token the packer can't handle (2.1) goes as text, about twice as slow, with no notice.
5. **Not a byte-exact token copy.** The packed form drops DLEQ and unknown fields, and the receiver re-encodes with cashu-ts defaults (`cashuB`). The proofs are the same; the string may not be.
6. **Sample rate is the device's.** Symbol, ramp and lead lengths are rounded to whole samples (`Math.round`), so at a rate where 0.020·sr is not an integer a symbol is slightly off 20 ms. The usual rates (22.05, 44.1, 48, 96 kHz) give exact 20 ms symbols.
7. **Reverb.** The simulator's own reverb test fails at all four levels in this build (section 5).
8. **Throughput comment.** `src/app_r4.js` says "about 50 bytes a second"; that is the raw symbol rate. Payload throughput is at most 37.5 bytes a second (section 5).
9. **README timing.** The README says a typical token takes 10 to 20 seconds a pass; measured, a 1-proof token on the test mint takes 3.6 s and 6 to 10 proofs take 12.5 to 19.9 s (section 5).

## 10. Changelog

- **Version 1 (this document, written for NUTCADE v1.12.1):** first written description of the format, derived from the code. The format itself has not changed since NUTCADE v1.8.0, where send by sound first shipped; `src/chiptune.js` is unchanged since the v1.8.1 timestamp.
