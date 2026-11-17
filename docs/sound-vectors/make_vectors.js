// Builds the test vectors in this folder with NUTCADE's own encoder:  node docs/sound-vectors/make_vectors.js
// All ecash here is FAKE: made-up secrets and signatures on the public test mint testnut.cashu.space. It can't be redeemed.
const fs = require('fs'), path = require('path'), { createHash } = require('crypto');
const { Chiptune, App, L, Framing } = require('./nutcade.js');
const SR = 48000;
const h = s => createHash('sha256').update(s).digest('hex');
const MINT = 'https://testnut.cashu.space', KEYSET = '00ad268c4d1f5826';
const proof = (i, amount, secret) => ({ id: KEYSET, amount, secret: secret || h('nutcade sound vector secret ' + i), C: '02' + h('nutcade sound vector C ' + i) });
const p2pk = i => JSON.stringify(['P2PK', { nonce: h('nonce ' + i).slice(0, 32), data: '02' + h('nutcade sound vector lock key'), tags: [['sigflag', 'SIG_INPUTS']] }]);
const tok = (proofs, memo) => L.getEncodedToken(Object.assign({ mint: MINT, unit: 'sat', proofs }, memo ? { memo } : {}));
const req = new L.PaymentRequest([{ type: 'nostr', target: L.nprofileEncode({ pubkey: h('nutcade sound vector nostr key'), relays: ['wss://relay.damus.io'] }), tags: [['n', '17']] }],
  'a1b2c3d4', 2100, 'sat', [MINT], 'coffee').toEncodedRequest();
const vectors = [
  { name: 'v1-short-token', note: 'A FAKE 8-sat cashuB token with one proof (test mint). Travels in the packed 0xC1 form.', input: tok([proof(1, 8)]) },
  { name: 'v2-payment-request', note: 'A NUT-18 payment request (creqA) for 2100 sat. Travels as plain UTF-8 text.', input: req },
  { name: 'v3-long-token', note: 'A FAKE 1000-sat cashuB token with 6 proofs, one of them P2PK-locked (a string secret), and a memo. Packed 0xC1 form, many frames.',
    input: tok([512, 256, 128, 64, 32].map((a, i) => proof(10 + i, a)).concat([proof(20, 8, p2pk(20))]), 'sound test vector') },
];
function wav(pcm, sr) {   // 16-bit PCM, mono
  const b = Buffer.alloc(44 + pcm.length * 2);
  b.write('RIFF', 0); b.writeUInt32LE(36 + pcm.length * 2, 4); b.write('WAVEfmt ', 8); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22);
  b.writeUInt32LE(sr, 24); b.writeUInt32LE(sr * 2, 28); b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34); b.write('data', 36); b.writeUInt32LE(pcm.length * 2, 40);
  for (let i = 0; i < pcm.length; i++) b.writeInt16LE(Math.round(Math.max(-1, Math.min(1, pcm[i])) * 32767), 44 + i * 2);
  return b;
}
const out = [];
for (const v of vectors) {
  // copy into this realm's Uint8Array: chiptune.js checks `instanceof Uint8Array`, and the vm sandbox has its own
  const payload = Uint8Array.from(App.soundBytes(v.input));
  const pcm = Chiptune.encode(payload, SR);
  fs.writeFileSync(path.join(__dirname, v.name + '.wav'), wav(pcm, SR));
  out.push({ name: v.name, note: v.note, kind: App.classify(v.input).kind, input: v.input, input_bytes: new TextEncoder().encode(v.input).length,
    payload_hex: Buffer.from(payload).toString('hex'), payload_bytes: payload.length,
    crc32_hex: Framing.crc32(payload).toString(16).padStart(8, '0'),
    frames_hex: Framing.frames(payload).map(f => Buffer.from(f).toString('hex')), frame_count: Chiptune.frameCount(payload),
    seconds_per_pass: +Chiptune.seconds(payload).toFixed(2), wav: v.name + '.wav', sample_rate: SR, samples: pcm.length });
}
module.exports = out;
if (require.main === module) {
  fs.writeFileSync(path.join(__dirname, 'vectors.json'), JSON.stringify(out, null, 1) + '\n');
  for (const v of out) console.log(v.name, v.kind, 'text', v.input_bytes, 'B -> payload', v.payload_bytes, 'B,', v.frame_count, 'frames,', v.seconds_per_pass, 's/pass,', v.samples, 'samples');
}
