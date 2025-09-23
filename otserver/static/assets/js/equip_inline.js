// assets/js/equipment-inline.js
document.addEventListener('DOMContentLoaded', () => {
  const root = document.getElementById('equip-inline');
  if (!root) return;

  // Character name comes straight from data-name (may contain spaces)
  const charName = root.dataset.name || '';
  if (!charName) return;

  // Where item icons live (override with window.ITEM_ICON_BASE if needed)
  const iconBase =
    (window.ITEM_ICON_BASE) ||
    ((window.STATIC_URL || '/static/') + 'assets/img/items/'); // e.g. /static/assets/img/items/

  const iconExt = (window.ITEM_ICON_EXT || '.gif');

  // Helper: render one item into a slot
  function renderItem(slotEl, itemType, count, niceName) {
    // Clear any previous content so we never duplicate
    slotEl.innerHTML = '';
    slotEl.style.backgroundImage = 'none';
    slotEl.classList.remove('has-item');

    // Wrapper anchors the count badge (CSS: .equip-inline .item { position:relative; width:64px; height:64px; })
    const wrap = document.createElement('div');
    wrap.className = 'item';

    if (itemType) {
      const img = document.createElement('img');
      img.className = 'slot__icon';
      img.src = `${iconBase}${itemType}${iconExt}`;
      img.alt = '';
      wrap.appendChild(img);

      if (count && count > 1) {
        const badge = document.createElement('span');
        badge.className = 'item__count';
        badge.textContent = String(count);
        wrap.appendChild(badge);
      }

      slotEl.title = niceName || String(itemType);
      slotEl.classList.add('has-item');
    } else {
      // Empty slot: try a placeholder like no_head.gif / no_armor.gif etc.
      const slotName =
        (slotEl.dataset.slotName || slotEl.title || '').toLowerCase().replace(/\s+/g, '');
      const placeholder = slotName ? `${iconBase}no_${slotName}${iconExt}` : '';
      if (placeholder) {
        const img = document.createElement('img');
        img.className = 'slot__icon';
        img.src = placeholder;
        img.alt = '';
        wrap.appendChild(img);
      }
    }

    slotEl.appendChild(wrap);
  }

  // Fetch equipment JSON
  const url = `/character/${encodeURIComponent(charName)}/equipment.json`;
  fetch(url)
    .then(r => r.json())
    .then(data => {
      const list = Array.isArray(data.equipment) ? data.equipment : [];

      list.forEach(eq => {
        // eq = { slot, slot_name, itemtype, count, attributes_hex }
        const slotEl = root.querySelector(`.slot[data-slot="${eq.slot}"]`);
        if (!slotEl) return;

        // Store a normalized slot name so placeholders can work
        if (eq.slot_name && !slotEl.dataset.slotName) {
          slotEl.dataset.slotName = eq.slot_name;
        }

        // Optional: pretty name via window.ITEMS map if available
        const niceName =
          (window.ITEMS && eq.itemtype && window.ITEMS[eq.itemtype] && window.ITEMS[eq.itemtype].name)
            ? window.ITEMS[eq.itemtype].name
            : (eq.itemtype ? String(eq.itemtype) : '');

        renderItem(slotEl, eq.itemtype, eq.count, niceName);
      });
    })
    .catch(err => console.error('equipment load error:', err));
});
