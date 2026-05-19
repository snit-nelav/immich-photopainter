// photopainter — vanilla JS UI. No localStorage / cookies: every preference
// (including the language) is persisted server-side in config.yaml.
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const I18N = {
  en: {
    "language": "Language",
    "header.subtitle": "e-paper photo frame",
    "status.title": "Last cycle status",
    "status.loading": "loading…",
    "status.never_run": "never run",
    "status.corrupted": "last_status corrupted",
    "status.fallback": "(degraded mode, cache)",
    "actions.title": "Actions",
    "actions.refresh": "↻ Refresh now",
    "actions.clear": "⚠ Clear screen",
    "source.title": "Source: Immich",
    "source.url": "Server URL",
    "source.api_key": "API key",
    "source.api_key_tuto.summary": "How to create an API key in Immich?",
    "source.api_key_tuto.step1": "In Immich, click your avatar (top right) → Account Settings.",
    "source.api_key_tuto.step2": 'Tab "API Keys" → "New API Key", name it "photopainter".',
    "source.api_key_tuto.step3": "Check only these permissions:",
    "source.api_key_tuto.step3_note": "No write/admin permission needed.",
    "source.api_key_tuto.step4": "Click Create, then copy the key (shown once).",
    "source.api_key_tuto.step5": "Paste it above and save.",
    "source.album": "Album to display",
    "source.album_placeholder": "— select an album —",
    "source.reload_albums": "↻ reload list",
    "frequency.title": "Refresh frequency",
    "frequency.next": "next refresh: —",
    "rotation.title": "Frame orientation",
    "rotation.help": "0° / 180° = portrait, 90° / 270° = landscape. Affects the logical canvas (480×800 or 800×480) and how photos get cropped.",
    "display.title": "Display mode",
    "display.compatible": "Photo with same orientation as frame",
    "display.inverted": "Photo with opposite orientation",
    "display.fill": "Fill frame",
    "display.fill_desc": "— crop, loses borders",
    "display.fill_inv_desc": "— heavy crop, loses much of the photo",
    "display.square": "Centered square",
    "display.square_desc": "— plain bands around",
    "display.original": "Original",
    "display.original_desc": "— full photo, plain bands",
    "display.bg_color": "Bands color",
    "display.bg_note": "(Square and Original modes)",
    "display.white": "White",
    "display.black": "Black",
    "cache.title": "Local cache",
    "cache.intro": "Downloaded photos are cached. If Immich is unavailable, the frame uses the cache. Old entries are auto-purged every night at midnight.",
    "cache.max_size": "Max size:",
    "save": "💾 Save configuration",
    "fb.saved": "✓ saved",
    "fb.saving": "saving…",
    "fb.refresh_started": "refresh started (pid {pid}). Panel ~25s.",
    "fb.refresh_new_photo": "new photo will appear on the panel in ~25s.",
    "fb.refresh_redraw": "redrawing the same photo with new display settings (~25s).",
    "fb.clear_confirm": "Clear screen? Use sparingly (uses screen charge cycles).",
    "fb.clear_started": "clear started",
    "fb.albums_loading": "loading album list…",
    "fb.albums_found": "{n} albums found",
    "fb.albums_fail": "✗ {err}. Check URL + API key + album.read permission.",
    "fb.cache_status": "Cache: <b>{used}</b> used / {max} GB max · {count} file(s)",
    "fb.next_refresh": "next refresh estimated: {date} (interval {interval} min)",
    "fb.load_error": "load error: {err}",
  },
  fr: {
    "language": "Langue",
    "header.subtitle": "cadre photo e-paper",
    "status.title": "État du dernier cycle",
    "status.loading": "chargement…",
    "status.never_run": "jamais exécuté",
    "status.corrupted": "last_status corrompu",
    "status.fallback": "(mode dégradé, cache)",
    "actions.title": "Actions",
    "actions.refresh": "↻ Refresh maintenant",
    "actions.clear": "⚠ Clear screen",
    "source.title": "Source : Immich",
    "source.url": "URL serveur",
    "source.api_key": "Clé API",
    "source.api_key_tuto.summary": "Comment créer une clé API dans Immich ?",
    "source.api_key_tuto.step1": "Dans Immich, clique sur ton avatar (haut droit) → Account Settings.",
    "source.api_key_tuto.step2": 'Onglet "API Keys" → "New API Key", nomme-la "photopainter".',
    "source.api_key_tuto.step3": "Coche uniquement ces permissions :",
    "source.api_key_tuto.step3_note": "Aucune permission write/admin n'est nécessaire.",
    "source.api_key_tuto.step4": "Clique Create, puis copie la clé (montrée une seule fois).",
    "source.api_key_tuto.step5": "Colle-la ci-dessus puis enregistre.",
    "source.album": "Album à afficher",
    "source.album_placeholder": "— sélectionne un album —",
    "source.reload_albums": "↻ recharger la liste",
    "frequency.title": "Fréquence de refresh",
    "frequency.next": "prochain refresh : —",
    "rotation.title": "Orientation du cadre",
    "rotation.help": "0° / 180° = portrait, 90° / 270° = paysage. Modifie le canvas logique (480×800 ou 800×480) et comment les photos sont croppées.",
    "display.title": "Mode d'affichage",
    "display.compatible": "Photo dans le même sens que le cadre",
    "display.inverted": "Photo dans le sens opposé au cadre",
    "display.fill": "Remplir le cadre",
    "display.fill_desc": "— crop, perd des bords",
    "display.fill_inv_desc": "— crop massif, perd beaucoup de la photo",
    "display.square": "Carré centré",
    "display.square_desc": "— bandes uni autour",
    "display.original": "Original",
    "display.original_desc": "— photo entière, bandes uni",
    "display.bg_color": "Couleur des bandes",
    "display.bg_note": "(modes Carré et Original)",
    "display.white": "Blanc",
    "display.black": "Noir",
    "cache.title": "Cache local",
    "cache.intro": "Les photos téléchargées sont mises en cache. Si Immich est indisponible, le cadre puisera dans le cache. Purge automatique des plus anciennes chaque nuit à minuit.",
    "cache.max_size": "Taille max :",
    "save": "💾 Enregistrer la configuration",
    "fb.saved": "✓ enregistré",
    "fb.saving": "enregistrement…",
    "fb.refresh_started": "refresh lancé (pid {pid}). Panneau ~25s.",
    "fb.refresh_new_photo": "nouvelle photo dans ~25s sur le cadre.",
    "fb.refresh_redraw": "redessin de la même photo avec les nouveaux réglages (~25s).",
    "fb.clear_confirm": "Clear screen ? À utiliser avec parcimonie (use chargeur de l'écran).",
    "fb.clear_started": "clear lancé",
    "fb.albums_loading": "chargement de la liste d'albums…",
    "fb.albums_found": "{n} albums trouvés",
    "fb.albums_fail": "✗ {err}. Vérifie URL + clé API + permission album.read.",
    "fb.cache_status": "Cache : <b>{used}</b> utilisés / {max} Go max · {count} fichier(s)",
    "fb.next_refresh": "prochain refresh estimé : {date} (intervalle {interval} min)",
    "fb.load_error": "erreur chargement : {err}",
  },
};

let currentLang = "en";
let currentInterval = 15;
let currentRotation = 0;
let currentBg = "white";
let initialSnapshot = null;   // serialized form state at last load, for dirty diff

function t(key, vars = {}) {
  const dict = I18N[currentLang] || I18N.en;
  let s = dict[key] || I18N.en[key] || key;
  for (const [k, v] of Object.entries(vars)) s = s.replaceAll("{" + k + "}", v);
  return s;
}

function applyI18n() {
  document.documentElement.lang = currentLang;
  $$("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
  $("#lang-select").value = currentLang;
}

async function jget(url) { const r = await fetch(url); if (!r.ok) throw new Error(`${url} → ${r.status}`); return r.json(); }
async function jpost(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  if (!r.ok) { const txt = await r.text(); throw new Error(`${url} → ${r.status} ${txt}`); }
  return r.json();
}

function fmtSeconds(s) { s = Math.round(s); if (s < 60) return s + " s"; return Math.floor(s/60) + " min " + (s%60) + " s"; }
function fmtDate(iso) { if (!iso) return "—"; const locale = currentLang === "fr" ? "fr-FR" : "en-GB"; return new Date(iso).toLocaleString(locale, { dateStyle: "short", timeStyle: "medium" }); }
function fmtBytes(b) { if (b < 1024) return b + " B"; if (b < 1024*1024) return (b/1024).toFixed(1) + " KB"; if (b < 1024*1024*1024) return (b/1024/1024).toFixed(1) + " MB"; return (b/1024/1024/1024).toFixed(2) + " GB"; }

function renderStatus(s) {
  const body = $("#status-body");
  if (!s || s.status === "never_run") { body.innerHTML = "<em>" + t("status.never_run") + "</em>"; return; }
  if (s.status === "corrupted") { body.innerHTML = "<em>" + t("status.corrupted") + "</em>"; return; }
  const d = s.durations || {};
  const fb = s.status === "success_fallback" ? " <span class='muted'>" + t("status.fallback") + "</span>" : "";
  body.innerHTML = `
    <div><strong>${s.status}</strong>${fb} · ${fmtDate(s.timestamp)}</div>
    <div class="muted">asset: <code>${s.asset_id || "—"}</code></div>
    <div class="muted">fetch ${fmtSeconds(d.fetch_list||0)} · download ${fmtSeconds(d.download||0)} · process ${fmtSeconds(d.process||0)} · display ${fmtSeconds(d.display||0)}</div>`;
  if (s.timestamp && currentInterval) {
    const next = new Date(new Date(s.timestamp).getTime() + currentInterval * 60 * 1000);
    $("#next-refresh").textContent = t("fb.next_refresh", { date: fmtDate(next.toISOString()), interval: currentInterval });
  }
}

function renderPills(containerId, values, current, suffix, setter) {
  const c = $("#" + containerId);
  c.innerHTML = "";
  for (const v of values) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = v + (suffix || "");
    b.dataset.value = v;
    if (v === current) b.classList.add("active");
    b.onclick = () => {
      setter(v);
      c.querySelectorAll("button").forEach(x => x.classList.toggle("active", +x.dataset.value === v));
      updateDirty();
    };
    c.appendChild(b);
  }
}

function bindBg(current) {
  currentBg = current;
  $("#bg-buttons").querySelectorAll("button").forEach(b => {
    b.classList.toggle("active", b.dataset.value === current);
    b.onclick = () => {
      currentBg = b.dataset.value;
      $("#bg-buttons").querySelectorAll("button").forEach(x => x.classList.toggle("active", x.dataset.value === currentBg));
      updateDirty();
    };
  });
}

function setRadio(name, value) { $$(`input[name="${name}"]`).forEach(i => { i.checked = (i.value === value); }); }
function getRadio(name) { const sel = document.querySelector(`input[name="${name}"]:checked`); return sel ? sel.value : null; }

function collectPatch() {
  return {
    sources: {
      immich: {
        base_url: $("#immich-url").value.trim(),
        api_key: $("#immich-api-key").value.trim(),
        album_id: $("#immich-album").value,
      },
    },
    display: {
      rotation: currentRotation,
      compatible_mode: getRadio("compatible_mode") || "fill",
      inverted_mode: getRadio("inverted_mode") || "original",
      background_color: currentBg,
    },
    scheduling: { refresh_interval_minutes: currentInterval },
    cache: { max_size_gb: parseFloat($("#cache-size").value) },
    ui: { language: currentLang },
  };
}

function snapshotForm() { return JSON.stringify(collectPatch()); }

function updateDirty() {
  const btn = $("#btn-save");
  if (!initialSnapshot) { btn.disabled = true; btn.classList.remove("dirty"); return; }
  const dirty = snapshotForm() !== initialSnapshot;
  btn.disabled = !dirty;
  btn.classList.toggle("dirty", dirty);
}

function bindDirtyInputs() {
  ["#immich-url", "#immich-api-key", "#immich-album", "#cache-size"].forEach(sel => {
    const el = $(sel);
    if (el) el.addEventListener("input", updateDirty);
    if (el) el.addEventListener("change", updateDirty);
  });
  $$('input[type="radio"]').forEach(r => r.addEventListener("change", updateDirty));
}

async function loadAlbums(autoSelect) {
  const fb = $("#albums-feedback");
  fb.textContent = t("fb.albums_loading");
  try {
    const data = await jget("/api/sources/immich/albums");
    const sel = $("#immich-album");
    sel.innerHTML = `<option value="">${t("source.album_placeholder")}</option>`;
    for (const a of data.albums) {
      const o = document.createElement("option");
      o.value = a.id; o.textContent = `${a.name} (${a.count})`;
      sel.appendChild(o);
    }
    sel.value = autoSelect || data.selected || "";
    fb.textContent = t("fb.albums_found", { n: data.albums.length });
  } catch (e) {
    fb.textContent = t("fb.albums_fail", { err: e.message });
  }
}

async function loadCacheInfo() {
  try {
    const c = await jget("/api/cache/info");
    $("#cache-info").innerHTML = t("fb.cache_status", { used: fmtBytes(c.used_bytes), max: c.max_size_gb, count: c.file_count });
  } catch (e) { $("#cache-info").textContent = "✗ " + e.message; }
}

async function loadAll() {
  const cfg = await jget("/api/config");
  const meta = cfg._meta || {};
  const s = cfg.sources, d = cfg.display, sch = cfg.scheduling, ca = cfg.cache, ui = cfg.ui || {};

  // Language comes from the server, not localStorage
  currentLang = (ui.language === "fr") ? "fr" : "en";
  applyI18n();

  $("#immich-url").value = s.immich.base_url || "";
  $("#immich-api-key").value = s.immich.api_key || "";

  currentInterval = sch.refresh_interval_minutes;
  currentRotation = d.rotation;
  renderPills("interval-buttons", meta.allowed_intervals || [5,10,15,20,30,45,60], currentInterval, " min", v => currentInterval = v);
  renderPills("rotation-buttons", meta.allowed_rotations || [0,90,180,270], currentRotation, "°", v => currentRotation = v);

  setRadio("compatible_mode", d.compatible_mode);
  setRadio("inverted_mode", d.inverted_mode);
  bindBg(d.background_color);

  $("#cache-size").value = ca.max_size_gb;
  $("#cache-size-val").textContent = ca.max_size_gb.toFixed(1);
  $("#cache-size").oninput = e => { $("#cache-size-val").textContent = (+e.target.value).toFixed(1); updateDirty(); };

  renderStatus(await jget("/api/status"));
  loadCacheInfo();
  await loadAlbums();
  $("#preview").src = "/api/preview?t=" + Date.now();

  initialSnapshot = snapshotForm();
  updateDirty();
}

$("#btn-save").onclick = async () => {
  if ($("#btn-save").disabled) return;
  const fb = $("#save-feedback");
  fb.textContent = t("fb.saving");
  try {
    const res = await jpost("/api/config", collectPatch());
    fb.textContent = t("fb.saved");
    if (res.refresh === "new_photo") fb.textContent += " · " + t("fb.refresh_new_photo");
    else if (res.refresh === "redraw") fb.textContent += " · " + t("fb.refresh_redraw");
    setTimeout(() => { fb.textContent = ""; }, 4000);
    // refresh the preview after the trigger has had time to push
    if (res.refresh === "new_photo" || res.refresh === "redraw") setTimeout(loadAll, 30000);
    else await loadAll();
  } catch (e) { fb.textContent = "✗ " + e.message; }
};

$("#btn-refresh").onclick = async () => {
  const fb = $("#action-feedback");
  fb.textContent = t("fb.saving");
  try { const r = await jpost("/api/refresh"); fb.textContent = t("fb.refresh_started", { pid: r.pid }); setTimeout(loadAll, 30000); }
  catch (e) { fb.textContent = "✗ " + e.message; }
};

$("#btn-clear").onclick = async () => {
  if (!confirm(t("fb.clear_confirm"))) return;
  const fb = $("#action-feedback");
  try { await jpost("/api/clear"); fb.textContent = t("fb.clear_started"); }
  catch (e) { fb.textContent = "✗ " + e.message; }
};

$("#btn-reload-albums").onclick = () => loadAlbums();

// Language change is persisted server-side and treated like any other config edit
$("#lang-select").onchange = (e) => {
  currentLang = e.target.value;
  applyI18n();
  updateDirty();
};

bindDirtyInputs();
applyI18n();
loadAll().catch(e => $("#status-body").textContent = t("fb.load_error", { err: e.message }));
setInterval(() => jget("/api/status").then(renderStatus).catch(() => {}), 30000);
