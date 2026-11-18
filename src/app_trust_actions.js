/* Trust & help actions: hiding amounts, checking your 12 words, update notices, Help & FAQ, mint details */
Object.assign(A, {
  hideToggle: () => { S.prefs.hideAmounts = !S.prefs.hideAmounts; save(); refresh(); sfx('blip'); },
  pwOpen: () => openPhraseCheck(),
  pwCheck: () => {
    if (!S.seed) return;
    const words = S.seed.mnemonic.split(' ');   // (compared here, on this phone: nothing is sent, shown or stored)
    const bad = [...document.querySelectorAll('[data-pw]')].filter(i => cleanPhrase(i.value) !== words[+i.dataset.pw]);
    if (bad.length) { sfx('err'); $('#sheetErr').innerHTML = errHTML(`Word #${+bad[0].dataset.pw + 1} doesn't match. Check your paper, or show the words again.`); bad[0].focus(); return; }
    setPhraseCheck({ done: Date.now(), next: Date.now() + PHRASE_AGAIN });
    sfx('levelup'); closeSheet(); render(); toast('Your 12 words check out. NUTCADE will ask again in about six months.', 'lime');
  },
  pwLater: () => { setPhraseCheck({ next: Date.now() + PHRASE_LATER }); closeSheet(); render(); },
  pwOff: () => { setPhraseCheck({ off: true }); closeSheet(); render(); toast('OK. You can still check your words any time in Settings, Backup.', 'cyan'); },
  whatsNew: () => openWhatsNew(),
  whatsNewDone: () => { seenNow(); refresh(); },
  reloadNow: () => {
    if (moneyBusy()) { toast("Finish what you're doing first, then reload.", 'gold'); sfx('err'); return; }   // (never in the middle of a payment or an open step)
    location.reload();
  },
  verCheck: async b => {
    const old = b.innerHTML; b.disabled = true; b.innerHTML = '<span class="spinner">CHECKING</span>';
    const v = await checkNewVersion(true);
    if (b.isConnected) { b.disabled = false; b.innerHTML = old; }
    if (v) { refresh(); toast(`New version v${v} is ready.`, 'cyan'); } else toast(v === false ? 'You have the newest version.' : "Couldn't check right now.", v === false ? 'lime' : 'gold');
  },
  helpOpen: () => openHelp(),
  mintInfo: b => openMintInfo(b.dataset.url)
});
