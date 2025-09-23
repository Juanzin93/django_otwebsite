// assets/js/navspan.js
document.addEventListener('DOMContentLoaded', () => {
  // Click
  document.addEventListener('click', (e) => {
    const el = e.target.closest('.name-link[role="link"][data-url]');
    if (!el) return;
    window.location.href = el.dataset.url;
  });

  // Keyboard (Enter / Space)
  document.addEventListener('keydown', (e) => {
    const el = e.target.closest('.name-link[role="link"][data-url]');
    if (!el) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      window.location.href = el.dataset.url;
    }
  });
});
