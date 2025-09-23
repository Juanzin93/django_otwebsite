(function(){
  const ICON_BASE =
    (window.ITEM_ICON_BASE) ||
    ((window.STATIC_URL || '/static/') + 'assets/img/items/');

  // Map slot -> placeholder key (optional)
  const NO_ICON = {
    1: 'no_head', 2: 'no_neck', 3: 'no_backpack',
    4: 'no_armor', 5: 'no_handright', 6: 'no_handleft',
    7: 'no_legs', 8: 'no_boots', 9: 'no_ring', 10: 'no_ammo'
  };

  // Fill full equipment grid for each card
  document.querySelectorAll('.baz-equip').forEach(grid => {
    let equip = [];
    try { equip = JSON.parse(grid.dataset.eq || '[]'); } catch(e) {}
    const bySlot = {};
    equip.forEach(it => { if (it && it.slot) bySlot[it.slot] = it; });

    grid.querySelectorAll('.eq-slot').forEach(slotEl => {
      const slot = Number(slotEl.dataset.slot || 0);
      const it = bySlot[slot];

      // reset
      slotEl.style.backgroundImage = '';
      slotEl.classList.remove('has-item');
      let cnt = slotEl.querySelector('.cnt');
      if (cnt) cnt.remove();

      if (it && it.itemtype) {
        slotEl.style.backgroundImage = `url("${ICON_BASE}${it.itemtype}.gif")`;
        slotEl.classList.add('has-item');
        if (it.count && it.count > 1) {
          const b = document.createElement('span');
          b.className = 'cnt';
          b.textContent = String(it.count);
          slotEl.appendChild(b);
        }
        // optional title override using item id
        const nice = (window.ITEMS && window.ITEMS[it.itemtype]?.name) || `#${it.itemtype}`;
        slotEl.title = slotEl.title ? `${slotEl.title} — ${nice}` : nice;
      } else {
        // fallback silhouette (optional – remove if you don't have these files)
        const key = NO_ICON[slot];
        if (key) slotEl.style.backgroundImage = `url("${ICON_BASE}${key}.gif")`;
      }
    });
  });

  // Countdown (unchanged)
  function fmt(ms){
    if (ms <= 0) return 'ended';
    const s=Math.floor(ms/1000), h=Math.floor(s/3600), m=Math.floor((s%3600)/60), ss=s%60;
    const pad=n=>String(n).padStart(2,'0');
    return `in ${pad(h)}h ${pad(m)}m ${pad(ss)}s`;
  }
  function tick(){
    const now=Date.now();
    document.querySelectorAll('.baz-countdown').forEach(el=>{
      const end = Number(el.dataset.end)*1000; // expects unix seconds
      el.textContent = fmt(end - now);
    });
  }
  tick(); setInterval(tick, 1000);
})();
