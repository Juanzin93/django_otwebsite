// statusbox.js - sidebar SERVER INFO showbox
document.addEventListener("DOMContentLoaded", () => {
  const box = document.getElementById("server-status-box");
  if (!box) return;

  const endpoint = box.dataset.endpoint || "/server_status/";
  const $ = (sel) => box.querySelector(sel);
  const setHTML = (sel, html) => { const n = $(sel); if (n) n.innerHTML = html; };
  const setText = (sel, text) => { const n = $(sel); if (n) n.textContent = text; };

  function apply(data) {
    const online = !!(data && data.online);
    setHTML(".js-status", online ? `<span class="ok">ONLINE</span>` : `<span class="bad">OFFLINE</span>`);
    const p = data && data.players ? data.players : {};
    setText(".js-players", `${p.online ?? 0}`);
    setText(".js-peak", `${p.peak ?? 0}`);
  }

  // If the Server Info page is active, it will set this flag and emit updates.
  if (window.__otStatusProviderActive) {
    window.addEventListener("ot-status:update", (e) => apply(e.detail));
    return; // don't start our own polling
  }

  async function fetchOnce() {
    try {
      const res = await fetch(endpoint, { cache: "no-store" });
      const data = await res.json();
      apply(data);
    } catch {
      apply({ online: false, players: { online: 0, max: 0, peak: 0 } });
    }
  }

  fetchOnce();
  setInterval(fetchOnce, 60000); // 60s poll if no provider is pushing updates
});
