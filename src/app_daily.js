
/* Daily Challenge: the one thing it can send. A public Nostr note (kind 1), signed with the NUTCADE Nostr key and
   published to the user's relays, and ONLY when daily.js calls publish() from the Post button. Nothing here runs
   on its own, and nothing touches ecash, mints or the vault. */
window.NutDailyNostr = {
  can: () => !!(S.seed && S.seed.backedUp),
  npub: () => { try { return L.npubEncode(L.nostrPub(nostrKey())); } catch (e) { return ''; } },
  relayCount: () => relays().length,
  sign: (content, tags) => L.finalizeEvent({ kind: 1, created_at: Math.floor(Date.now() / 1000), tags: tags || [], content: String(content) }, nostrKey()),
  publish: ev => (typeof navigator !== 'undefined' && navigator.onLine === false) ? Promise.resolve(0) : relayPublish(ev, 8000)
};
