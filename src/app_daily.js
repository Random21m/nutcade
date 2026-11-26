
/* Daily Challenge: the one thing it can send. A public Nostr note (kind 1), signed with your Nostr identity when you are
   signed in (idSign, app_identity.js; never the 12-word key instead), else the NUTCADE Nostr key, and
   published to the user's relays, and ONLY when daily.js calls publish() from the Post button. Nothing here runs
   on its own, and nothing touches ecash, mints or the vault. */
window.NutDailyNostr = {
  can: () => !!(S.seed && S.seed.backedUp),
  npub: () => { try { return L.npubEncode(idPub()); } catch (e) { return ''; } },
  own: () => idActive(),   // (signed in with your own Nostr identity)
  relayCount: () => relays().length,
  gen: () => idNow(),   // (the identity now: taken when the share sheet opens)
  sign: (content, tags, gen0) => idSign({ kind: 1, created_at: Math.floor(Date.now() / 1000), tags: tags || [], content: String(content) }, gen0),   // (a promise; another identity since gen0: nothing signed)
  publish: ev => (typeof navigator !== 'undefined' && navigator.onLine === false) ? Promise.resolve(0) : relayPublish(ev, 8000)
};
