function outfitUrl(p, { path = "latest", animated = true, direction = 2, mount = 0 } = {}) {
  const getNum = (obj, key, def = 0) => {
    const v = obj?.[key] ?? (typeof obj?.get === "function" ? obj.get(key) : undefined);
    const n = Number(v);
    return Number.isFinite(n) ? n : def;
  };
  const params = new URLSearchParams({
    id:        String(getNum(p, "looktype", 0)),
    addons:    String(getNum(p, "lookaddons", 0)),
    head:      String(getNum(p, "lookhead", 0)),
    body:      String(getNum(p, "lookbody", 0)),
    legs:      String(getNum(p, "looklegs", 0)),
    feet:      String(getNum(p, "lookfeet", 0)),
    mount:     String(Number(mount) || 0),
    direction: String(Number(direction) ?? 2),
  });
  const endpoint = animated ? "animoutfit.php" : "outfit.php";
  return `https://outfit-images.ots.me/${path}/${endpoint}?${params.toString()}`;
}

// Python's country_of(player) → JS
function countryOf(p, { fallback = "us" } = {}) {
  const raw = (p?.country ?? p?.account?.country ?? "").toString().trim();
  const alias = { uk: "gb" }; // normalize common non-ISO uses
  const c = raw.toLowerCase();
  const iso2 = alias[c] ?? c;
  return /^[a-z]{2}$/.test(iso2) ? iso2 : fallback;
}

function flagUrl(code, { base = "/static/assets/img/flags", ext = "gif" } = {}) {
  const c = (code || "").toLowerCase();
  return `${base}/${c}.${ext}`;
}

// (nice to have) basic HTML escaper for player names
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, m => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[m]));
}

document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("online-panel");
  if (!root) return;

  const endpoint = root.dataset.endpoint;
  const rows = root.querySelector(".js-rows");
  const summary = root.querySelector(".js-summary");
  const statusDot = root.querySelector(".dot--status");
  const updated = root.querySelector(".js-updated");

  function setOnline(on) {
    if (on) {
      statusDot.classList.add("on");
      statusDot.classList.remove("off");
    } else {
      statusDot.classList.add("off");
      statusDot.classList.remove("on");
    }
  }

  function render(list) {
    rows.innerHTML = "";
    if (!list || !list.length) {
      rows.innerHTML = `<tr><td colspan="5" style="text-align:center; opacity:.8;">No players online</td></tr>`;
      return;
    }

    list.forEach((p, idx) => {
      console.log(p);
      const code = countryOf(p);                           // <- from JS helper
      const flagSrcGif = flagUrl(code, { ext: "gif" });    // default
      const flagSrcPng = flagUrl(code, { ext: "png" });    // fallback if .gif missing

      // Build outfit URL on the fly unless backend already gave one
      const url = p.outfit_url || outfitUrl(p, { path: "latest", animated: true, direction: 3, mount: p.mount || 0 });

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${idx + 1}</td>
        <td>${url ? `<img src="${url}" width="64" height="64" style="image-rendering:pixelated;image-rendering:crisp-edges">` : "-"}</td>
        <td>${esc(p.name) || "-"}</td>
        <td>${p.level ?? "-"}</td>
        <td>
          <img class="flag" src="${flagSrcGif}" width="18" height="14"
              onerror="this.onerror=null; this.src='${flagSrcPng}'" alt="${code.toUpperCase()}">
        </td>
      `;
      rows.appendChild(tr);
    });
  }

  async function tick() {
    try {
      const res = await fetch(endpoint, { cache: "no-store" });
      const data = await res.json();
      const on = !!data.online;
      setOnline(on);
      const counts = data.players || {};
      summary.textContent = on
        ? `Online: ${counts.online || 0}  Record: ${counts.peak || 0}`
        : `Server offline`;
      render(data.list || []);
      if (updated) updated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
    } catch {
      setOnline(false);
      summary.textContent = "Server offline";
      rows.innerHTML = `<tr><td colspan="5" style="text-align:center; opacity:.8;">—</td></tr>`;
    }
  }

  tick();
  setInterval(tick, 30000); // 30s
});
