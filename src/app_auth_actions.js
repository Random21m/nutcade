/* Mint login (1.33): Log in, Log out (app_auth.js) */
Object.assign(A, {
  authLogin: b => openAuth(b.dataset.url || b.dataset.a),
  authLogout: b => { authLogout(acctUrl(b.dataset.url)); toast("Logged out. This mint's login is deleted from this device.", 'cyan'); render(); }
});
