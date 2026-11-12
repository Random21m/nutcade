# Security policy

NUTCADE holds real money, so security reports are taken seriously.

## Reporting a problem

Please **don't open a public issue** for anything that could put someone's sats at risk. Instead, open the [Security tab](https://github.com/Random21m/nutcade/security) and choose **Report a vulnerability**. Only the maintainer can see the report.

Useful things to include:

- what an attacker could do (steal ecash, read the wallet, spend without the PIN, and so on)
- the steps to reproduce it, and the browser and phone you used
- the NUTCADE version (Settings → About)

You'll get a reply within a few days. Once a fix is live, the changelog will credit you, unless you'd rather stay anonymous.

## What's covered

- the app at https://random21m.github.io/nutcade/ and the code in this repository
- how the app stores your recovery phrase, PIN and ecash in the browser
- tokens, payment requests and challenges that NUTCADE creates or reads

Problems in a mint, in Cashu itself, or in another wallet belong with those projects. Problems in the bundled libraries (cashu-ts, nostr-tools) belong upstream, but tell us too, so the bundle can be updated.

## Checking you have the real app

Every release lists SHA-256 sums for the app files, signed with the key in [`nutcade-signing-key.asc`](nutcade-signing-key.asc) (fingerprint in the README). The live site publishes the same sums at https://random21m.github.io/nutcade/SHA256SUMS.txt.
