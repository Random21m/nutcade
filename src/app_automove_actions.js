/* Auto-move: my mint and "don't move below" in Settings (app_automove.js) */
document.addEventListener('change', e => {
  if (e.target.id === 'p_amMint') amSetMint(e.target.value);
  if (e.target.id === 'p_amMin') amSetMin(e.target.value);
});
