document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("server-info");
  if (!root) return;

  // Tell the site that a central provider is active on this page
  window.__otStatusProviderActive = true;

  const endpoint = root.dataset.endpoint; // from template data-endpoint
  const $ = (sel) => root.querySelector(sel);
  const setText = (sel, val) => { const n = $(sel); if (n) n.textContent = val; };

  function fmtUptime(sec) {
    sec = Number(sec||0);
    const d = Math.floor(sec/86400);
    sec %= 86400;
    const h = Math.floor(sec/3600);
    const m = Math.floor((sec%3600)/60);
    if (d) return `${d}d ${h}h ${m}m`;
    if (h) return `${h}h ${m}m`;
    return `${m}m`;
  }

  function updatePage(data) {
    const online = !!data.online;
    const statusEl = root.querySelector(".js-status");
    if (statusEl) statusEl.innerHTML = online ? `<span class="ok">ONLINE</span>` : `<span class="bad">OFFLINE</span>`;
    setText(".js-uptime", online ? fmtUptime((data.server||{}).uptime_sec) : "—");
    setText(".js-players", `${(data.players||{}).online||0}`);
    setText(".js-peak", (data.players||{}).peak||0);
    setText(".js-characters", (data.players||{}).max||0);
    setText(".js-rate-exp", (data.rates||{}).experience ?? "-");
    setText(".js-rate-magic", (data.rates||{}).magic ?? "-");
    setText(".js-rate-skill", (data.rates||{}).skill ?? "-");
    setText(".js-rate-loot", (data.rates||{}).loot ?? "-");
    setText(".js-rate-spawn", (data.rates||{}).spawn ?? "-");
    setText(".js-map-name", (data.map||{}).name ?? "-");
    setText(".js-map-author", (data.map||{}).author ?? "-");
    setText(".js-map-size", `${(data.map||{}).width||0}×${(data.map||{}).height||0}`);
    const motdEl = root.querySelector(".js-motd");
    if (motdEl) motdEl.textContent = data.motd || "";
    const upd = root.querySelector(".js-updated");
    if (upd) upd.textContent = `Last updated ${new Date().toLocaleTimeString()}`;
  }

  function broadcast(data) {
    window.dispatchEvent(new CustomEvent("ot-status:update", { detail: data }));
  }

  async function tick() {
    try {
      const res = await fetch(endpoint, { cache: "no-store" });
      const data = await res.json();
      updatePage(data);
      broadcast(data); // update the sidebar without another fetch
    } catch {
      updatePage({ online: false, players: { online: 0, max: 0, peak: 0 }, rates:{}, map:{} });
      broadcast({ online: false, players: { online: 0, max: 0, peak: 0 }, rates:{}, map:{} });
    }
  }

  tick();
  setInterval(tick, 60000); // single poll for the whole page
});
