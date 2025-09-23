document.addEventListener('DOMContentLoaded', () => {
  const els = document.querySelectorAll('.countdown[data-end]');
  const tick = () => {
    const now = Math.floor(Date.now()/1000);
    els.forEach(el => {
      const end = parseInt(el.dataset.end, 10) || 0;
      let left = Math.max(0, end - now);
      const h = Math.floor(left/3600); left %= 3600;
      const m = Math.floor(left/60); const s = left%60;
      el.textContent = `${h}h ${m}m ${s}s`;
    });
  };
  tick();
  setInterval(tick, 1000);
});
