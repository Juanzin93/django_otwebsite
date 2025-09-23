// Robust multi-open accordion via event delegation + persistence
document.addEventListener('DOMContentLoaded', () => {
  const KEY = 'accordion-open-v1';
  const items = () => Array.from(document.querySelectorAll('.acc .acc__item'));

  // Restore open state (by index)
  try {
    const openIdxs = JSON.parse(localStorage.getItem(KEY) || '[]');
    items().forEach((it, i) => {
      const header = it.querySelector('.acc__header');
      const body   = it.querySelector('.acc__body');
      const isOpen = openIdxs.includes(i);
      it.classList.toggle('is-open', isOpen);
      header?.setAttribute('aria-expanded', String(isOpen));
      if (isOpen) body?.removeAttribute('hidden'); else body?.setAttribute('hidden', '');
    });
  } catch {}

  // Toggle + save
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.acc__header');
    if (!btn) return;

    const item = btn.closest('.acc__item');
    const body = item.querySelector('.acc__body');
    const expanded = btn.getAttribute('aria-expanded') === 'true';

    btn.setAttribute('aria-expanded', String(!expanded));
    item.classList.toggle('is-open', !expanded);
    if (expanded) body.setAttribute('hidden', ''); else body.removeAttribute('hidden');

    // Persist all currently-open sections
    const openIdxs = items().reduce((a, it, i) => (
      it.classList.contains('is-open') ? (a.push(i), a) : a
    ), []);
    localStorage.setItem(KEY, JSON.stringify(openIdxs));
  });
});