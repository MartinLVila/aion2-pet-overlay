// Shared by the main window and the soul popup.
const REQ = [5, 25, 75], TOTAL = 105, MAX = 3;

const gvar = genus => `var(--${(genus || "special").toLowerCase()})`;
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// Souls still needed to reach level 3.
function soulsLeft(level, points) {
  return level >= MAX ? 0 : TOTAL - REQ.slice(0, level).reduce((a, b) => a + b, 0) - points;
}

// Segmented bar, segments sized 5 : 25 : 75 like the game's level thresholds.
function levelBar(level, points, genus, mini) {
  const segs = REQ.map((need, i) => {
    const fill = i < level ? 100 : i === level ? Math.min(100, points / need * 100) : 0;
    return `<div class="seg"><i style="width:${fill}%;--g:${gvar(genus)}"></i></div>`;
  }).join("");
  return `<div class="levels${mini ? " mini" : ""}" aria-hidden="true">${segs}</div>`;
}

// App icon: a paw inside a ring split 5 : 25 : 75 (same drawing as assets/icon.ico).
function appIcon(size) {
  const arc = (r, a0, a1) => {
    const p = a => [32 + r * Math.cos(a * Math.PI / 180), 32 + r * Math.sin(a * Math.PI / 180)];
    const [x0, y0] = p(a0), [x1, y1] = p(a1);
    return `M${x0.toFixed(2)} ${y0.toFixed(2)}A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  };
  const [a, b, c] = [5, 25, 75].map(n => 330 * n / 105);
  let t = -85;
  const s1 = [t, t += a]; t += 10;
  const s2 = [t, t += b]; t += 10;
  const s3 = [t, t + c], fill = s3[0] + c * .55;
  return `<svg width="${size}" height="${size}" viewBox="0 0 64 64" aria-hidden="true" style="display:block">
    <rect x="1" y="1" width="62" height="62" rx="15" fill="var(--surface)" stroke="var(--line)" stroke-width="2"/>
    <g fill="none" stroke-width="5.5">
      <path d="${arc(23, ...s1)}" stroke="var(--accent)"/><path d="${arc(23, ...s2)}" stroke="var(--accent)"/>
      <path d="${arc(23, s3[0], fill)}" stroke="var(--accent)"/><path d="${arc(23, fill + 7, s3[1])}" stroke="var(--line)"/>
    </g>
    <g fill="var(--text)">
      <ellipse cx="32" cy="37.5" rx="7.6" ry="6.4"/>
      <ellipse cx="23.6" cy="30.5" rx="2.9" ry="3.6" transform="rotate(-18 23.6 30.5)"/>
      <ellipse cx="28.6" cy="25.4" rx="2.9" ry="3.7"/><ellipse cx="35.4" cy="25.4" rx="2.9" ry="3.7"/>
      <ellipse cx="40.4" cy="30.5" rx="2.9" ry="3.6" transform="rotate(18 40.4 30.5)"/>
    </g></svg>`;
}

// window.pywebview.api is ready only after this event; resolves at once if it already fired.
const apiReady = new Promise(resolve => {
  if (window.pywebview && window.pywebview.api) resolve(window.pywebview.api);
  else window.addEventListener("pywebviewready", () => resolve(window.pywebview.api), { once: true });
});
