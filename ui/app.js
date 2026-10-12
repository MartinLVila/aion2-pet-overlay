// Main window. Python owns the data (pets, progress, settings) and pushes changes through window.app;
// this page renders them and calls back through window.pywebview.api.
const GENERA = ["Cogni", "Natura", "Fera", "Varian"];
const $ = id => document.getElementById(id);

let api = null;
let pets = [], byId = new Map();
let state = { levels: {}, points: {}, extra: {}, recent: [], synced: null, capturing: false, error: null };
let cfg = {};
// selected: the clicked row ({id, map}); mob: index into that pet's mobs shown on the minimap
const ui = { q: "", selected: null, mob: 0, settings: false, collapsed: false, flash: new Set(), maps: new Map() };

const progress = id => [state.levels[id] || 0, state.points[id] || 0];
const remaining = id => soulsLeft(...progress(id));
const isFarmable = p => p.genus !== "Special" && p.mobs.length > 0;
// a pet's mobs are sorted surest drop first, then most spawns, so the first match is the best one to farm
const mobMaps = m => m.zones.map(z => z[1]);
const petMaps = p => [...new Set(p.mobs.flatMap(mobMaps))];
const mobsOn = (p, map) => map ? p.mobs.filter(m => mobMaps(m).includes(map)) : p.mobs;
const zonesOn = (m, map) => [...new Set(m.zones.filter(z => !map || z[1] === map).map(z => z[0]))];
const chance = m => m.pct !== null && m.pct < 100 ? ` <em class="num">${m.pct}%</em>` : "";

// ---------- rendering ----------
function renderHeader() {
  const farmable = pets.filter(isFarmable);
  const done = farmable.filter(p => (state.levels[p.id] || 0) >= MAX).length;
  $("overall-text").textContent = `${done} of ${farmable.length} done`;
  $("overall-bar").style.width = `${farmable.length ? done / farmable.length * 100 : 0}%`;

  const status = $("status");
  let cls = "", text = "Live", tip = "Reading game traffic";
  if (state.error) { cls = "err"; text = state.error; tip = state.error; }
  else if (!state.synced) { cls = "wait"; text = "Waiting for sync"; tip = "Enter the world with your character (or change channel) to load every pet's progress"; }
  else if (!state.capturing) { cls = "off"; text = "Game not detected"; tip = `Last synced ${state.synced}`; }
  else tip = `Live. Last synced ${state.synced}`;
  status.className = "status " + cls;
  $("status-text").textContent = text;
  status.title = tip;
}

function renderNow() {
  const el = $("now");
  const id = state.recent.find(i => byId.has(i));
  if (id === undefined) {
    el.innerHTML = `<div class="hint">${state.synced ? "Loot a pet soul and its progress shows up here."
      : "Enter the world with your character to load your pets. Then loot a soul and it shows up here."}</div>`;
    return;
  }
  const p = byId.get(id), [l, pts] = progress(id), left = remaining(id);
  const labels = REQ.map((need, i) => {
    const txt = i < l ? `Lv${i + 1} done` : i === l ? `Lv${i + 1}: ${pts} of ${need}` : `Lv${i + 1}: 0 of ${need}`;
    return `<span class="${i === l ? "cur" : ""}">${txt}</span>`;
  }).join("");
  const wasted = !left && state.extra[id] ? `<span class="waste">${state.extra[id]} souls wasted since Lv3, switch mobs</span>` : "";
  const others = state.recent.filter(i => i !== id && byId.has(i)).slice(0, 2).map(i =>
    `<span><b>${esc(byId.get(i).name)}</b> ${remaining(i) ? remaining(i) + " left" : "done"}</span>`).join("");
  el.innerHTML = `
    <div class="now-head"><div class="now-name">${esc(p.name)}</div>
      <div class="now-left num">${left || "Lv3"}<small>${left ? "souls to Lv3" : "done"}</small></div></div>
    <div class="now-meta"><span class="genus-tag" style="color:${gvar(p.genus)}">${esc(p.genus)}</span>
      <span>${nowWhere(p)}</span>${wasted}</div>
    ${levelBar(l, pts, p.genus)}<div class="seg-labels num">${labels}</div>
    ${others ? `<div class="also">${others}</div>` : ""}`;
}

// where to farm the pet: on the map picked in the filter if it can drop there, else its best mob anywhere
function nowWhere(p) {
  if (!p.mobs.length) return "Chest or shop only";
  const here = mobsOn(p, cfg.map), m = here[0] || p.mobs[0];
  const zone = zonesOn(m, here.length ? cfg.map : "")[0];
  const map = here.length && cfg.map ? cfg.map : m.zones[0] && m.zones[0][1];
  const where = [zone, map].filter(Boolean).map(esc).join(", ");
  const more = p.mobs.length - 1;
  return `${esc(m.name)}${where ? ` in ${where}` : ""}${more ? ` <em>+${more} more ${more === 1 ? "mob" : "mobs"}</em>` : ""}`;
}

function renderChips() {
  const chip = (key, label, color, n, pressed) => `<button class="chip" type="button" style="--g:${color}" aria-pressed="${pressed}" data-chip="${key}">
      <span class="sw"></span>${label}<span class="count num">${n}</span></button>`;
  const open = p => remaining(p.id) > 0;
  $("chips").innerHTML = GENERA.map(g =>
      chip(g, g, gvar(g), pets.filter(p => p.genus === g && p.mobs.length && open(p)).length, !!cfg.genus[g])).join("") +
    chip("no_mob", "Chest or shop", "var(--special)", pets.filter(p => !p.mobs.length && open(p)).length, !!cfg.no_mob);
}

function renderMapFilter() {
  const maps = [...new Set(pets.flatMap(petMaps))].sort();
  const sel = $("map-filter");
  sel.innerHTML = `<option value="">All maps</option>` + maps.map(m => `<option>${esc(m)}</option>`).join("");
  sel.value = maps.includes(cfg.map) ? cfg.map : "";
}

// One row per pet and map it can be farmed on, so a pet whose mobs live on two maps shows under both.
// map is "" for chest or shop pets and null for mobs MetaBot has no spawns for.
function rows() {
  const q = ui.q.trim().toLowerCase();
  const out = [];
  for (const p of pets) {
    if (remaining(p.id) <= 0 || !(p.mobs.length ? cfg.genus[p.genus] : cfg.no_mob)) continue;
    const maps = p.mobs.length ? petMaps(p) : [""];
    if (p.mobs.some(m => !m.zones.length)) maps.push(null);
    for (const map of maps) {
      if (cfg.map && map !== cfg.map) continue;
      const mobs = map === null ? p.mobs.filter(m => !m.zones.length) : map ? mobsOn(p, map) : [];
      const text = `${p.name} ${mobs.map(m => `${m.name} ${zonesOn(m, map).join(" ")}`).join(" ")} ${map || ""}`;
      if (!q || text.toLowerCase().includes(q)) out.push({ p, map, mobs });
    }
  }
  return out;
}

function renderList() {
  const list = $("list"), items = rows(), top = list.scrollTop;
  if (!items.length) {
    list.innerHTML = `<div class="empty">No pets match these filters.<button class="btn" id="reset" type="button">Clear filters</button></div>`;
    return;
  }
  const groups = new Map();
  for (const r of items) {
    const k = r.map === null ? "Unknown map" : r.map || "Chest or shop";
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(r);
  }
  const sel = ui.selected;
  list.innerHTML = [...groups.entries()].sort((a, b) => b[1].length - a[1].length).map(([title, rs]) => {
    rs.sort((a, b) => remaining(a.p.id) - remaining(b.p.id));
    return `<div class="group-head">${esc(title)} <span class="num">${rs.length} ${rs.length === 1 ? "pet" : "pets"}</span></div>` +
      rs.map(({ p, map, mobs }) => {
        const [l, pts] = progress(p.id), m = mobs[0], others = mobs.length - 1;
        const zone = m ? zonesOn(m, map).join(", ") : "";
        return `<div class="row${ui.flash.has(p.id) ? " flash" : ""}" role="option" tabindex="0" data-id="${p.id}" data-map="${map === null ? "-" : esc(map)}"
            aria-selected="${!!sel && sel.id === p.id && sel.map === map}" style="--g:${gvar(p.genus)}">
          <span class="gdot" title="${esc(p.genus)}"></span><span class="pet">${esc(p.name)}</span>
          <span class="mob">${m ? `<span>${esc(m.name)} <em class="num">Lv ${m.lvl ?? "?"}</em>${chance(m)}</span>
            <span class="zone">${esc(zone || "Spawn unknown")}${others ? ` <em>+${others} more ${others === 1 ? "mob" : "mobs"} here</em>` : ""}</span>`
            : "<span>Chest or shop</span>"}</span>
          ${levelBar(l, pts, p.genus, true)}<span class="left num" title="Souls to Lv3">${remaining(p.id)}</span>
        </div>`;
      }).join("");
  }).join("");
  list.scrollTop = top;
  ui.flash.clear();
}

// Side panel for the clicked pet: every mob that drops it (the clicked map's first) and one mob's minimap.
async function renderMap() {
  const main = $("main"), el = $("map"), sel = ui.selected;
  if (!sel || !byId.has(sel.id)) { el.hidden = true; main.classList.remove("with-map"); return; }
  const p = byId.get(sel.id);
  el.hidden = false; main.classList.add("with-map");
  const head = `<div class="map-head"><div><h2>${esc(p.name)}</h2><p>${p.mobs.length
      ? `Drops from ${p.mobs.length} ${p.mobs.length === 1 ? "mob" : "mobs"}` : "Doesn't drop from mobs"}</p></div>
      <button class="icon-btn" id="close-map" type="button" aria-label="Close map" title="Close map">
      <svg class="i" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>`;
  if (!p.mobs.length) {
    el.innerHTML = head + `<div class="view"><div class="note">This pet comes from chests or shops.</div></div>`;
    return;
  }
  const away = i => sel.map ? !mobMaps(p.mobs[i]).includes(sel.map) : false;
  const order = p.mobs.map((m, i) => i).sort((a, b) => away(a) - away(b));
  const mobList = `<ol class="mobs">${order.map(i => {
    const m = p.mobs[i];
    const zones = m.zones.length ? m.zones.map(([zone, map, n]) =>
      `<span>${esc(zone)}, ${esc(map)} <em class="num">${n} ${n === 1 ? "spawn" : "spawns"}</em></span>`).join("") : "<span>Spawn unknown</span>";
    return `<li><button class="mob-opt" type="button" data-mob="${i}" aria-pressed="${ui.mob === i}" style="--g:${gvar(p.genus)}">
      <b>${esc(m.name)} <em class="num">Lv ${m.lvl ?? "?"}</em>${chance(m)}</b>${zones}
      ${m.kisk ? `<span class="kisk">Nearest Kibelisk: ${esc(m.kisk)}</span>` : ""}</button></li>`;
  }).join("")}</ol>`;
  const m = p.mobs[ui.mob], s = m.spawn, key = `${p.id}:${ui.mob}`;
  const link = s && s.link ? `<span class="link" data-url="https://metabot.gg${esc(s.link)}">Open in MetaBot
      <svg class="i" viewBox="0 0 24 24" style="width:13px;height:13px"><path d="M14 5h5v5M19 5l-8 8M18 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4"/></svg></span>` : "";
  if (!s || !s.dots.length) {
    el.innerHTML = head + `<div class="view"><div class="note">${s ? `No minimap for ${esc(m.name)} here. Open MetaBot's map to see its spawns.`
      : `MetaBot has no spawn points for ${esc(m.name)} yet.`}</div></div>${link ? `<div class="map-foot">${link}</div>` : ""}` + mobList;
    return;
  }
  const dots = s.dots.map(([x, y]) => `<span class="dot" style="left:${x}%;top:${y}%;--g:${gvar(p.genus)}"></span>`).join("");
  const cached = ui.maps.get(key);
  el.innerHTML = head + `<div class="view">${cached ? `<img src="${cached}" alt="">` : `<div class="note">Loading map…</div>`}${dots}</div>
    <div class="map-foot"><span class="num">${s.dots.length} spawn points${s.map ? ` on ${esc(s.map)}` : ""}</span>${link}</div>` + mobList;
  if (cached) return;
  let uri = null;
  try { uri = await api.get_map(p.id, ui.mob); } catch (e) { console.error(e); }
  if (!ui.selected || `${ui.selected.id}:${ui.mob}` !== key) return; // another row or mob was clicked meanwhile
  const view = el.querySelector(".view");
  if (!uri) { view.querySelector(".note").textContent = "Map unavailable. Check your internet connection."; return; }
  ui.maps.set(key, uri);
  view.querySelector(".note").outerHTML = `<img src="${uri}" alt="">`;
}

function render() { renderHeader(); renderNow(); renderChips(); renderList(); }

// ---------- settings ----------
function applySettings() {
  const overlay = cfg.mode === "overlay";
  document.body.classList.toggle("overlay", overlay);
  document.querySelectorAll(".seg-opt").forEach(b => b.setAttribute("aria-checked", b.dataset.mode === cfg.mode));
  $("set-opacity").value = cfg.opacity; $("opacity-val").textContent = cfg.opacity + "%";
  $("set-opacity").disabled = !overlay; $("row-opacity").classList.toggle("off", !overlay);
  $("set-ontop").checked = overlay || cfg.on_top; $("set-ontop").disabled = overlay;
  $("row-ontop").classList.toggle("off", overlay);
  $("ontop-note").textContent = overlay ? "The overlay is always on top of the game." : "Stays above other windows while you play.";
  $("set-toast").checked = cfg.toast;
  $("set-toast-pos").value = cfg.toast_pos; $("set-toast-time").value = String(cfg.toast_time);
  $("set-toast-pos").disabled = $("set-toast-time").disabled = $("move-toast").disabled = !cfg.toast;
  for (const id of ["row-toast-pos", "row-toast-time", "row-toast-move"]) $(id).classList.toggle("off", !cfg.toast);
  const toTray = cfg.tray && cfg.close_to_tray;
  $("close").title = toTray ? "Hide to the tray (it keeps counting souls)" : "Quit";
  $("close").setAttribute("aria-label", $("close").title);
  $("set-tray").checked = cfg.tray;
  $("set-close-tray").checked = cfg.tray && cfg.close_to_tray; $("set-close-tray").disabled = !cfg.tray;
  $("row-close-tray").classList.toggle("off", !cfg.tray);
  $("set-updates").checked = cfg.check_updates;
}

async function save(changes) {
  Object.assign(cfg, changes);
  applySettings();
  try { cfg = await api.save_settings(changes); } catch (e) { console.error(e); }
}

function showSettings(open) {
  ui.settings = open;
  $("body").classList.toggle("settings-open", open);
  $("settings").hidden = !open;
  for (const id of ["now", "tools", "main"]) $(id).hidden = open;
  $("gear").setAttribute("aria-pressed", open);
}

// ---------- calls from Python ----------
window.app = {
  setState(next) {
    state = next;
    render();
    if (ui.selected && !$("map").hidden) renderMap();
  },
  flash(id) { ui.flash.add(id); },
  setSettings(next) { cfg = next; applySettings(); },
  setUpdate(u) {
    const btn = $("update");
    btn.hidden = !u;
    if (!u) return;
    btn.classList.toggle("failed", u.status === "failed");
    btn.disabled = u.status === "downloading";
    btn.textContent = u.status === "downloading" ? `Downloading ${Math.round((u.progress || 0) * 100)}%`
      : u.status === "failed" ? "Update failed, open page" : `Update to v${u.version}`;
  },
};

// ---------- events ----------
document.addEventListener("mousedown", e => {
  // buttons in the title bar must not start a window drag
  if (e.target.closest(".bar button")) e.stopPropagation();
}, true);

document.addEventListener("click", e => {
  const t = e.target;
  const chip = t.closest("[data-chip]");
  if (chip) {
    const k = chip.dataset.chip;
    if (k === "no_mob") save({ no_mob: !cfg.no_mob });
    else save({ genus: { ...cfg.genus, [k]: !cfg.genus[k] } });
    render();
    return;
  }
  if (t.closest("#reset")) {
    ui.q = ""; $("q").value = "";
    save({ genus: Object.fromEntries(GENERA.map(g => [g, true])), map: "" });
    $("map-filter").value = ""; render(); return;
  }
  const link = t.closest("[data-url]");
  if (link) { api.open_url(link.dataset.url); return; }
  if (t.closest("#close-map")) { ui.selected = null; renderList(); renderMap(); return; }
  if (t.closest("#gear")) { if (ui.collapsed) toggleCollapse(); showSettings(!ui.settings); return; }
  if (t.closest("#settings-done")) { showSettings(false); return; }
  if (t.closest("#collapse")) { toggleCollapse(); return; }
  if (t.closest("#close")) { api.close(); return; }
  if (t.closest("#update")) { api.start_update(); return; }
  if (t.closest("#move-toast")) { api.place_toast(); return; }
  const opt = t.closest(".seg-opt");
  if (opt && opt.dataset.mode !== cfg.mode) { save({ mode: opt.dataset.mode }); return; }
  const mob = t.closest("[data-mob]");
  if (mob) { ui.mob = +mob.dataset.mob; renderMap(); return; }
  const row = t.closest(".row");
  if (row) {
    const id = +row.dataset.id, map = row.dataset.map === "-" ? null : row.dataset.map, p = byId.get(id);
    const same = ui.selected && ui.selected.id === id && ui.selected.map === map;
    ui.selected = same ? null : { id, map };
    // open on the first mob of the clicked map (or, under "Unknown map", the first without spawns)
    if (!same) ui.mob = Math.max(0, p.mobs.findIndex(m => map ? mobMaps(m).includes(map) : !m.zones.length));
    renderList(); renderMap();
  }
});
document.addEventListener("keydown", e => { if (e.key === "Enter" && e.target.matches(".row")) e.target.click(); });
$("q").addEventListener("input", e => { ui.q = e.target.value; renderList(); });
$("map-filter").addEventListener("change", e => { save({ map: e.target.value }); renderList(); });
$("set-opacity").addEventListener("input", e => save({ opacity: +e.target.value }));
$("set-ontop").addEventListener("change", e => save({ on_top: e.target.checked }));
$("set-toast").addEventListener("change", e => save({ toast: e.target.checked }));
$("set-toast-pos").addEventListener("change", async e => {
  await save({ toast_pos: e.target.value });
  if (e.target.value === "custom" && !cfg.toast_xy) api.place_toast();  // nowhere chosen yet: pick it now
});
$("set-toast-time").addEventListener("change", e => save({ toast_time: +e.target.value }));
$("set-tray").addEventListener("change", e => save({ tray: e.target.checked }));
$("set-close-tray").addEventListener("change", e => save({ close_to_tray: e.target.checked }));
$("set-updates").addEventListener("change", e => save({ check_updates: e.target.checked }));

function toggleCollapse() {
  ui.collapsed = !ui.collapsed;
  document.body.classList.toggle("collapsed", ui.collapsed);
  api.set_collapsed(ui.collapsed, Math.ceil(document.querySelector(".bar").getBoundingClientRect().height) + 2);
}

// overlay resize grip: the window has no frame to grab, so resize it from here
(() => {
  const grip = $("grip");
  let start = null, pending = null;
  grip.addEventListener("pointerdown", e => {
    grip.setPointerCapture(e.pointerId);
    start = { x: e.screenX, y: e.screenY, w: window.innerWidth, h: window.innerHeight };
  });
  grip.addEventListener("pointermove", e => {
    if (!start) return;
    const w = Math.max(420, start.w + e.screenX - start.x), h = Math.max(220, start.h + e.screenY - start.y);
    if (!pending) requestAnimationFrame(() => { api.resize(pending.w, pending.h); pending = null; });
    pending = { w, h };
  });
  grip.addEventListener("pointerup", () => { start = null; });
})();

// ---------- start ----------
apiReady.then(async a => {
  api = a;
  document.querySelectorAll("[data-icon]").forEach(el => { el.innerHTML = appIcon(+el.dataset.icon); });
  const d = await api.init();
  pets = Object.entries(d.pets).map(([id, p]) => ({ id: +id, ...p }));
  byId = new Map(pets.map(p => [p.id, p]));
  cfg = d.settings;
  $("version").textContent = "v" + d.version;
  applySettings();
  renderMapFilter();
  window.app.setUpdate(d.update);
  window.app.setState(d.state);
  api.ready();
});
