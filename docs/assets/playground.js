// Brot Farm playground — everything computed live in your browser.
// Vanilla JS, no dependencies. Mirrors the Python renderer's semantics
// (two-phase classification fused per-sample; percentile-anchored log tone map).
'use strict';

/* ------------------------------------------------------------------ maps */
// step(x, y, cx, cy) -> [x', y']; gone(x, y) -> escape predicate.
const M = Math;
const MAPS = {
  mandel: {
    label: 'z² + c',
    win: [-2.25, 1.15, -1.7, 1.7],
    step: (x, y, cx, cy) => [x * x - y * y + cx, 2 * x * y + cy],
    gone: (x, y) => x * x + y * y > 4,
  },
  z3: {
    label: 'z³ + c',
    win: [-1.6, 1.6, -1.6, 1.6],
    step: (x, y, cx, cy) => [x ** 3 - 3 * x * y * y + cx, 3 * x * x * y - y ** 3 + cy],
    gone: (x, y) => x * x + y * y > 4,
  },
  z4: {
    label: 'z⁴ + c',
    win: [-1.45, 1.45, -1.45, 1.45],
    step: (x, y, cx, cy) => [
      x ** 4 - 6 * x * x * y * y + y ** 4 + cx,
      4 * x * y * (x * x - y * y) + cy,
    ],
    gone: (x, y) => x * x + y * y > 4,
  },
  z5: {
    label: 'z⁵ + c',
    win: [-1.35, 1.35, -1.35, 1.35],
    step: (x, y, cx, cy) => [
      x ** 5 - 10 * x ** 3 * y * y + 5 * x * y ** 4 + cx,
      5 * x ** 4 * y - 10 * x * x * y ** 3 + y ** 5 + cy,
    ],
    gone: (x, y) => x * x + y * y > 4,
  },
  ship: {
    label: 'Burning Ship',
    win: [-2.2, 1.2, -1.8, 1.8],
    step: (x, y, cx, cy) => [x * x - y * y + cx, M.abs(2 * x * y) + cy],
    gone: (x, y) => x * x + y * y > 4,
  },
  tricorn: {
    label: 'Tricorn z̄² + c',
    win: [-2.1, 2.1, -1.8, 1.8],
    step: (x, y, cx, cy) => [x * x - y * y + cx, -2 * x * y + cy],
    gone: (x, y) => x * x + y * y > 4,
  },
  celtic: {
    label: 'Celtic',
    win: [-2.2, 1.0, -1.6, 1.6],
    step: (x, y, cx, cy) => [M.abs(x * x - y * y) + cx, 2 * x * y + cy],
    gone: (x, y) => x * x + y * y > 4,
  },
  buffalo: {
    label: 'Buffalo',
    win: [-2.2, 1.0, -1.9, 1.9],
    step: (x, y, cx, cy) => [M.abs(x * x - y * y) + cx, M.abs(2 * x * y) + cy],
    gone: (x, y) => x * x + y * y > 4,
  },
  sinz: {
    label: 'sin z + c',
    win: [-3.5, 3.5, -1.8, 1.8],
    step: (x, y, cx, cy) => [M.sin(x) * M.cosh(y) + cx, M.cos(x) * M.sinh(y) + cy],
    gone: (x, y) => !(isFinite(x) && isFinite(y)) || x * x + y * y > 1e6,
  },
  cosz: {
    label: 'cos z + c',
    win: [-4, 4, -2.2, 2.2],
    step: (x, y, cx, cy) => [M.cos(x) * M.cosh(y) + cx, -M.sin(x) * M.sinh(y) + cy],
    gone: (x, y) => !(isFinite(x) && isFinite(y)) || x * x + y * y > 1e6,
  },
  cosmut: {
    label: 'cos(x²) − y mutation',
    win: [-3, 3, -3, 3],
    step: (x, y, cx, cy) => [M.cos(x * x) - y + cx, 2 * x * y + cy],
    gone: (x, y) => M.abs(y) > 100 || !isFinite(x + y),
  },
  cosfull: {
    label: 'cos(x²−y²) mutation',
    win: [-2.5, 2.5, -5, 5],
    step: (x, y, cx, cy) => [M.cos(x * x - y * y) + cx, 2 * x * y + cy],
    gone: (x, y) => M.abs(y) > 100 || !isFinite(x + y),
  },
  cosy: {
    label: 'y′ = cos 2xy mutation',
    win: [-2.5, 2.5, -2.5, 2.5],
    step: (x, y, cx, cy) => [x * x - y * y + cx, M.cos(2 * x * y) + cy],
    gone: (x, y) => M.abs(x) > 100 || !isFinite(x + y),
  },
  tanmut: {
    label: 'tan mutation',
    win: [-2, 2.4, -2.4, 2],
    step: (x, y, cx, cy) => [M.tan(x * x) - y + cx, 2 * x * y + cy],
    gone: (x, y) => M.abs(y) > 100 || !isFinite(x + y),
  },
  sinhmut: {
    label: 'sinh mutation',
    win: [-2, 2.2, -1.8, 1.3],
    step: (x, y, cx, cy) => [M.sinh(x * x) - y + cx, 2 * x * y + cy],
    gone: (x, y) => M.abs(y) > 100 || !isFinite(x + y),
  },
  expmut: {
    label: 'exp mutation',
    win: [-2, 2, -2, 2],
    step: (x, y, cx, cy) => [M.exp(x * x) - y + cx, 2 * x * y + cy],
    gone: (x, y) => M.abs(y) > 100 || !isFinite(x + y),
  },
};
// gallery deep-links remap to playground-capable maps (anti/julia handled in the mini-renderer)
const ALIASES = { anti: 'mandel', nebula: 'mandel', julia: 'mandel' };
const qs = new URLSearchParams(location.search);
let initialMap = qs.get('map') || 'mandel';

// cross-module hooks: the theater / developing-room IIFEs expose accessors
// here so the experiments module (L4) can read and restore shared state.
const SHARED = {};

// deterministic PRNG (mulberry32): every seeded feature below derives its
// choices from this stream only — same seed, same experiment, no Math.random.
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* --------------------------------------------------------- SHA-1 (for APRS) */
// Compact FIPS 180-1 SHA-1 over a Uint8Array -> lowercase hex. Used to stamp
// APRS previews (sha1[:8] of the 128px preview PNG, docs/adr/0001-aprs.md)
// without crypto.subtle, which some file:// embedders do not expose.
function sha1hex(bytes) {
  const ml = bytes.length;
  const blocks = ((ml + 8) >> 6) + 1; // total 64-byte blocks after padding
  const msg = new Uint32Array(blocks * 16); // padded message words
  for (let i = 0; i < ml; i++) msg[i >> 2] |= bytes[i] << (24 - (i % 4) * 8);
  msg[ml >> 2] |= 0x80 << (24 - (ml % 4) * 8);
  msg[blocks * 16 - 1] = ml * 8;
  const rol = (x, s) => (x << s) | (x >>> (32 - s));
  let h0 = 0x67452301,
    h1 = 0xefcdab89,
    h2 = 0x98badcfe,
    h3 = 0x10325476,
    h4 = 0xc3d2e1f0;
  for (let blk = 0; blk < blocks; blk++) {
    // per-block schedule window: never shares storage with later message words
    const W = new Uint32Array(80);
    for (let i = 0; i < 16; i++) W[i] = msg[blk * 16 + i];
    for (let t = 16; t < 80; t++) W[t] = rol(W[t - 3] ^ W[t - 8] ^ W[t - 14] ^ W[t - 16], 1);
    let a = h0,
      b = h1,
      c = h2,
      d = h3,
      e = h4;
    for (let t = 0; t < 80; t++) {
      let f, k;
      if (t < 20) {
        f = (b & c) | (~b & d);
        k = 0x5a827999;
      } else if (t < 40) {
        f = b ^ c ^ d;
        k = 0x6ed9eba1;
      } else if (t < 60) {
        f = (b & c) | (b & d) | (c & d);
        k = 0x8f1bbcdc;
      } else {
        f = b ^ c ^ d;
        k = 0xca62c1d6;
      }
      const tmp = (rol(a, 5) + f + e + k + W[t]) | 0;
      e = d;
      d = c;
      c = rol(b, 30);
      b = a;
      a = tmp;
    }
    h0 = (h0 + a) | 0;
    h1 = (h1 + b) | 0;
    h2 = (h2 + c) | 0;
    h3 = (h3 + d) | 0;
    h4 = (h4 + e) | 0;
  }
  return [h0, h1, h2, h3, h4].map((x) => (x >>> 0).toString(16).padStart(8, '0')).join('');
}

/* ------------------------------------------------- formula sandbox compile */
function compileFormula(fxSrc, fySrc) {
  const names = Object.getOwnPropertyNames(Math).filter((k) => typeof Math[k] === 'function');
  const wrap = (src) =>
    new Function('x', 'y', 'cx', 'cy', ...names, `"use strict"; return (${src});`);
  const fx = wrap(fxSrc),
    fy = wrap(fySrc);
  const vals = names.map((k) => Math[k]);
  const test = (x, y) => {
    const a = fx(x, y, 0, 0, ...vals),
      b = fy(x, y, 0, 0, ...vals);
    return Number.isFinite(a) && Number.isFinite(b);
  };
  if (!test(0.3, 0.2) || !test(-1.2, 0.7)) throw new Error('formula does not evaluate cleanly');
  return {
    step: (x, y, cx, cy) => [fx(x, y, cx, cy, ...vals), fy(x, y, cx, cy, ...vals)],
    gone: (x, y) => !isFinite(x + y) || x * x + y * y > 1e10 || Math.abs(x) + Math.abs(y) > 1e5,
  };
}

/* ------------------------------------------------------------ shared utils */
function fillSelect(sel, extra) {
  for (const [k, v] of Object.entries(MAPS)) {
    const o = document.createElement('option');
    o.value = k;
    o.textContent = v.label + (extra && extra[k] ? ` (${extra[k]})` : '');
    sel.appendChild(o);
  }
}
function currentMap(sel) {
  return MAPS[sel.value] || MAPS.mandel;
}

/* =========================================================== ORBIT THEATER */
(function () {
  const cv = document.getElementById('ot-canvas');
  if (!cv) return;
  const ctx = cv.getContext('2d');
  const mapSel = document.getElementById('ot-map');
  const hud = document.getElementById('ot-hud');
  fillSelect(mapSel, {});
  mapSel.value = ALIASES[initialMap] || (MAPS[initialMap] ? initialMap : 'mandel');

  let custom = null; // compiled custom {step, gone, win}
  const active = () => custom || currentMap(mapSel);
  const W = cv.width,
    H = cv.height;
  let c = [-0.1, 0.65];
  let trail = []; // [x0, y0, x1, y1, age]
  let head = [0, 0];
  let nIter = 0,
    escaped = false;
  let playing = true;
  let bg = null; // prisoner-country layer
  // L4 experiments hooks (read c / custom status; restore a custom formula)
  SHARED.theaterC = () => [c[0], c[1]];
  SHARED.usesCustom = () => custom !== null;
  SHARED.setCustom = (m) => {
    custom = m ? { ...m } : null;
    buildBG();
    reset();
  };

  function win() {
    return active().win || currentMap(mapSel).win;
  }
  function toPx(x, y) {
    const [x0, x1, y0, y1] = win();
    return [((x - x0) / (x1 - x0)) * W, ((y1 - y) / (y1 - y0)) * H];
  }
  function toWorld(px, py) {
    const [x0, x1, y0, y1] = win();
    return [x0 + (px / W) * (x1 - x0), y1 - (py / H) * (y1 - y0)];
  }

  function buildBG() {
    const m = active();
    const off = document.createElement('canvas');
    off.width = W;
    off.height = H;
    const octx = off.getContext('2d');
    const cell = 8;
    for (let py = 0; py < H; py += cell) {
      for (let px = 0; px < W; px += cell) {
        const [cx, cy] = toWorld(px + cell / 2, py + cell / 2);
        let x = cx,
          y = cy,
          k = 0;
        for (; k < 60; k++) {
          [x, y] = m.step(x, y, cx, cy);
          if (!isFinite(x) || !isFinite(y) || m.gone(x, y)) break;
        }
        if (k >= 60) {
          octx.fillStyle = 'rgba(111,195,223,0.16)';
          octx.fillRect(px, py, cell, cell);
        } else if (k > 15) {
          octx.fillStyle = `rgba(232,160,76,${0.03 + (k / 60) * 0.13})`;
          octx.fillRect(px, py, cell, cell);
        }
      }
    }
    bg = off;
  }

  function reset() {
    head = [c[0], c[1]];
    nIter = 0;
    escaped = false;
    trail = [];
    hudUpdate();
  }

  function stepOnce(count) {
    const m = active();
    for (let i = 0; i < count && !escaped; i++) {
      const [nx, ny] = m.step(head[0], head[1], c[0], c[1]);
      trail.push([head[0], head[1], nx, ny, 0]);
      head = [nx, ny];
      nIter++;
      if (!isFinite(nx) || !isFinite(ny) || m.gone(nx, ny)) escaped = true;
      if (nIter > 20000) escaped = true;
    }
  }

  function hudUpdate() {
    const r = M.hypot(head[0], head[1]);
    hud.innerHTML =
      `map <b>${custom ? 'custom formula' : currentMap(mapSel).label}</b><br>` +
      `c = <b>${c[0].toFixed(4)} ${c[1] < 0 ? '−' : '+'} ${M.abs(c[1]).toFixed(4)}i</b><br>` +
      `n = <b>${nIter}</b> · z = ${head[0].toFixed(3)} ${head[1] < 0 ? '−' : '+'} ${M.abs(head[1]).toFixed(3)}i · |z| = ${r.toFixed(3)}<br>` +
      (escaped
        ? `<b style="color:#d96a6a">escaped after ${nIter} iterations</b>`
        : nIter === 0
          ? 'press play or step'
          : 'orbit continues…');
  }

  // ------------------------------------------------------------- rain mode
  const film = document.createElement('canvas');
  film.width = W;
  film.height = H;
  const fctx = film.getContext('2d');
  let rain = null;
  function startRain(x, y, spread = 0.25) {
    const [x0, x1, y0, y1] = win();
    rain = Array.from({ length: 1800 }, () => {
      const cx = M.max(x0, M.min(x1, x + (Math.random() * 2 - 1) * spread));
      const cy = M.max(y0, M.min(y1, y + (Math.random() * 2 - 1) * spread));
      return { c: [cx, cy], z: [cx, cy], alive: true };
    });
  }
  function rainFrame() {
    if (!rain) return;
    const m = active();
    fctx.globalCompositeOperation = 'lighter';
    fctx.lineWidth = 0.7;
    fctx.strokeStyle = 'rgba(232,160,76,0.055)';
    let live = 0;
    for (const p of rain) {
      if (!p.alive) continue;
      live++;
      for (let s = 0; s < 2; s++) {
        const [nx, ny] = m.step(p.z[0], p.z[1], p.c[0], p.c[1]);
        const a = toPx(p.z[0], p.z[1]),
          b = toPx(nx, ny);
        fctx.beginPath();
        fctx.moveTo(a[0], a[1]);
        fctx.lineTo(b[0], b[1]);
        fctx.stroke();
        p.z = [nx, ny];
        if (!isFinite(nx) || !isFinite(ny) || m.gone(nx, ny)) {
          p.alive = false;
          break;
        }
      }
    }
    fctx.globalCompositeOperation = 'source-over';
    if (live === 0) rain = null;
  }
  const rainBtn = document.getElementById('ot-rain');
  let rainOn = false;
  rainBtn.addEventListener('click', () => {
    rainOn = !rainOn;
    rainBtn.textContent = rainOn ? '☔ stop rain' : '☔ start rain';
    rainBtn.setAttribute('aria-pressed', rainOn);
    if (rainOn) startRain(c[0], c[1], 0.35);
  });
  document
    .getElementById('ot-rain-clear')
    .addEventListener('click', () => fctx.clearRect(0, 0, W, H));
  cv.addEventListener('click', (e) => {
    if (rainOn) {
      const r = cv.getBoundingClientRect();
      const w = toWorld(((e.clientX - r.left) / r.width) * W, ((e.clientY - r.top) / r.height) * H);
      startRain(w[0], w[1], 0.15);
    }
  });

  // explorer -> theater c-pick
  document.addEventListener('brot:pick-c', (e) => {
    const [x0, x1, y0, y1] = win();
    c = [M.max(x0, M.min(x1, e.detail.c[0])), M.max(y0, M.min(y1, e.detail.c[1]))];
    reset();
    hud.insertAdjacentHTML('beforeend', `<b style="color:#6fc3df">· c received from explorer</b>`);
  });

  // ------------------------------------------------------------- main loop
  const trailLen = document.getElementById('ot-trail');
  const speed = document.getElementById('ot-speed');
  function frame() {
    if (playing && !escaped) stepOnce(+speed.value);
    rainFrame();
    const maxAge = +trailLen.value;
    for (const s of trail) s[4]++;
    while (trail.length && trail[0][4] > maxAge) trail.shift();

    ctx.clearRect(0, 0, W, H);
    if (bg) ctx.drawImage(bg, 0, 0);
    ctx.drawImage(film, 0, 0);
    ctx.lineWidth = 1.8;
    for (const [x0, y0, x1, y1, age] of trail) {
      const a = M.max(0, 1 - age / maxAge);
      ctx.strokeStyle = `rgba(232,160,76,${0.25 + 0.65 * a})`;
      const p0 = toPx(x0, y0),
        p1 = toPx(x1, y1);
      ctx.beginPath();
      ctx.moveTo(p0[0], p0[1]);
      ctx.lineTo(p1[0], p1[1]);
      ctx.stroke();
    }
    if (!escaped) {
      const p = toPx(head[0], head[1]);
      ctx.fillStyle = '#fff';
      ctx.beginPath();
      ctx.arc(p[0], p[1], 3.4, 0, 7);
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.35)';
      ctx.beginPath();
      ctx.arc(p[0], p[1], 8 + 3 * M.sin(performance.now() / 200), 0, 7);
      ctx.stroke();
    }
    const cp = toPx(c[0], c[1]);
    ctx.fillStyle = '#6fc3df';
    ctx.beginPath();
    ctx.arc(cp[0], cp[1], 4.2, 0, 7);
    ctx.fill();
    ctx.font = '12px Cascadia Code, Consolas, monospace';
    ctx.fillStyle = '#6fc3df';
    ctx.fillText('c', cp[0] + 7, cp[1] - 6);
    hudUpdate();
    requestAnimationFrame(frame);
  }

  // interaction: drag to move c
  let dragging = false;
  const setFromEvent = (e) => {
    const r = cv.getBoundingClientRect();
    const w = toWorld(((e.clientX - r.left) / r.width) * W, ((e.clientY - r.top) / r.height) * H);
    const [x0, x1, y0, y1] = win();
    c = [M.max(x0, M.min(x1, w[0])), M.max(y0, M.min(y1, w[1]))];
    reset();
  };
  cv.addEventListener('pointerdown', (e) => {
    dragging = true;
    cv.setPointerCapture(e.pointerId);
    setFromEvent(e);
  });
  cv.addEventListener('pointermove', (e) => dragging && setFromEvent(e));
  cv.addEventListener('pointerup', () => (dragging = false));

  document.getElementById('ot-play').addEventListener('click', (e) => {
    playing = !playing;
    e.target.textContent = playing ? '⏸ pause' : '▶ play';
  });
  document.getElementById('ot-step').addEventListener('click', () => stepOnce(1));
  document.getElementById('ot-reset').addEventListener('click', reset);
  mapSel.addEventListener('change', () => {
    custom = null;
    buildBG();
    reset();
  });
  document.getElementById('ot-apply').addEventListener('click', () => {
    try {
      const m = compileFormula(
        document.getElementById('ot-fx').value,
        document.getElementById('ot-fy').value,
      );
      let best = null;
      for (const w of [
        [-2.5, 2.5, -2.5, 2.5],
        [-1.5, 1.5, -1.5, 1.5],
        [-4, 4, -4, 4],
        [-1, 1, -1, 1],
      ]) {
        let surv = 0;
        const N = 3000;
        for (let i = 0; i < N; i++) {
          const cx = w[0] + Math.random() * (w[1] - w[0]);
          const cy = w[2] + Math.random() * (w[3] - w[2]);
          let x = cx,
            y = cy,
            k = 0;
          for (; k < 40; k++) {
            [x, y] = m.step(x, y, cx, cy);
            if (!isFinite(x) || !isFinite(y) || m.gone(x, y)) break;
          }
          if (k >= 40) surv++;
        }
        const frac = surv / N;
        if (frac > 0.05 && frac < 0.95) {
          best = w;
          break;
        }
        if (!best && frac >= 0.95) best = w;
      }
      custom = { ...m, win: best || [-3, 3, -3, 3] };
      buildBG();
      reset();
      hud.insertAdjacentHTML(
        'afterbegin',
        `<b style="color:#6fc3df">formula applied</b> · window auto-scouted<br>`,
      );
    } catch (err) {
      hud.insertAdjacentHTML(
        'afterbegin',
        `<b style="color:#d96a6a">formula error:</b> ${err.message}<br>`,
      );
    }
  });

  buildBG();
  reset();
  frame();
})();

/* ======================================================== MINI BUDDHA LAB */
(function () {
  const cv = document.getElementById('mb-canvas');
  if (!cv) return;
  const N = cv.width; // square
  const ctx = cv.getContext('2d');
  const mapSel = document.getElementById('mb-map');
  fillSelect(mapSel, { mandel: 'anti/julia/nebula via presets below' });

  const JULIA_C = [-0.7, 0.27];
  let mode = 'escape'; // "escape" | "anti" | "julia"
  SHARED.mbMode = () => mode; // L4: experiment state readback
  if (initialMap === 'anti') mode = 'anti';
  if (initialMap === 'julia') mode = 'julia';
  if (initialMap === 'nebula') document.getElementById('mb-cap').value = 400;

  let hist = new Float64Array(N * N);
  let stats = { done: 0, escaped: 0, plotted: 0 };
  let playing = true;
  let t0 = performance.now();
  let anchors = { lo: 0, hi: 1 };
  const img = ctx.createImageData(N, N);

  function win() {
    return currentMap(mapSel).win;
  }

  function anchorsRefresh() {
    const sample = [];
    for (let i = 0; i < hist.length; i += 13) {
      const v = hist[i];
      if (v > 0) sample.push(Math.log(1 + v));
    }
    if (sample.length < 50) {
      anchors = { lo: 0, hi: Math.log(1 + Math.max(1, stats.maxBin || 1)) };
      return;
    }
    sample.sort((a, b) => a - b);
    anchors = {
      lo: sample[Math.floor(sample.length * 0.3)],
      hi: sample[Math.floor(sample.length * 0.999)] || sample[sample.length - 1],
    };
  }

  const capEl = document.getElementById('mb-cap'),
    rateEl = document.getElementById('mb-rate'),
    gEl = document.getElementById('mb-gamma');

  function addSamples(count) {
    const m = currentMap(mapSel);
    const [x0, x1, y0, y1] = win();
    const cap = +capEl.value;
    for (let s = 0; s < count; s++) {
      let cx, cy, sx, sy;
      if (mode === 'julia') {
        cx = JULIA_C[0];
        cy = JULIA_C[1];
        sx = x0 + Math.random() * (x1 - x0);
        sy = y0 + Math.random() * (y1 - y0);
      } else {
        cx = x0 + Math.random() * (x1 - x0);
        cy = y0 + Math.random() * (y1 - y0);
        sx = cx;
        sy = cy;
      }
      // phase 1: classify
      let x = sx,
        y = sy,
        esc = false,
        k = 0;
      for (; k < cap; k++) {
        [x, y] = m.step(x, y, cx, cy);
        if (!isFinite(x) || !isFinite(y) || m.gone(x, y)) {
          esc = true;
          break;
        }
      }
      stats.done++;
      const want = mode === 'anti' ? !esc : esc;
      if (!want) continue;
      stats.escaped++;
      // phase 2: replay and plot (julia starts from z1 = z0² + c; c-maps from z1 = c)
      const sxw = N / (x1 - x0),
        syw = N / (y1 - y0);
      let px0 = sx,
        py0 = sy;
      if (mode === 'julia') {
        [px0, py0] = m.step(sx, sy, cx, cy);
      }
      x = px0;
      y = py0;
      const steps = mode === 'anti' ? cap : k;
      for (let j = 0; j <= steps; j++) {
        const col = ((x - x0) * sxw) | 0,
          row = ((y1 - y) * syw) | 0;
        if (col >= 0 && col < N && row >= 0 && row < N) {
          hist[row * N + col] += 1;
          stats.plotted++;
        }
        [x, y] = m.step(x, y, cx, cy);
        if (!isFinite(x) || !isFinite(y) || m.gone(x, y)) break;
      }
    }
  }

  let frameCount = 0;
  function render() {
    if (playing) addSamples(+rateEl.value);
    if (++frameCount % 20 === 0) anchorsRefresh();
    const { lo, hi } = anchors;
    const gamma = +gEl.value;
    const d = img.data;
    let maxBin = 0;
    for (let i = 0, p = 0; i < hist.length; i++, p += 4) {
      const h = hist[i];
      if (h > maxBin) maxBin = h;
      let v = (Math.log(1 + h) - lo) / M.max(hi - lo, 1e-9);
      v = v < 0 ? 0 : v > 1 ? 1 : v;
      v = v ** gamma;
      d[p] = 255 * M.min(1, v * 1.15);
      d[p + 1] = 255 * M.min(1, v * 1.05);
      d[p + 2] = 255 * v * 0.9;
      d[p + 3] = 255;
    }
    stats.maxBin = maxBin;
    ctx.putImageData(img, 0, 0);
    const secs = (performance.now() - t0) / 1000;
    document.getElementById('mb-hud').innerHTML =
      `mode <b>${mode === 'anti' ? 'antibuddhabrot (prisoner orbits)' : mode === 'julia' ? `julia-brot · c = ${JULIA_C[0]} + ${JULIA_C[1]}i` : 'buddhabrot (escaping orbits)'}</b> on <b>${currentMap(mapSel).label}</b><br>` +
      `samples <b>${stats.done.toLocaleString()}</b> · kept ${stats.escaped.toLocaleString()} · plotted ${(stats.plotted / 1e6).toFixed(1)}M points · hottest bin ${maxBin.toLocaleString()}<br>` +
      `${secs.toFixed(0)}s exposure · ${(stats.done / secs / 1000).toFixed(0)}k samples/s`;
    document.getElementById('mb-cap-v').textContent = capEl.value;
    document.getElementById('mb-rate-v').textContent = rateEl.value;
    requestAnimationFrame(render);
  }

  document.getElementById('mb-play').addEventListener('click', (e) => {
    playing = !playing;
    e.target.textContent = playing ? '⏸ pause' : '▶ play';
  });
  document.getElementById('mb-reset').addEventListener('click', () => {
    hist = new Float64Array(N * N);
    stats = { done: 0, escaped: 0, plotted: 0 };
    t0 = performance.now();
  });
  document.getElementById('mb-save').addEventListener('click', () => {
    const a = document.createElement('a');
    a.download = `brot-${mapSel.value}-${Date.now()}.png`;
    a.href = cv.toDataURL('image/png');
    a.click();
  });
  // preset buttons injected for the gallery deep-links
  const presetRow = document.createElement('div');
  presetRow.className = 'controls';
  presetRow.innerHTML = `
    <span style="color:var(--muted);font-size:12.5px">presets:</span>
    <button class="btn" data-mode="escape">buddhabrot</button>
    <button class="btn" data-mode="anti">antibuddhabrot</button>
    <button class="btn" data-mode="julia">julia-brot</button>`;
  cv.closest('.panel').insertBefore(presetRow, cv.closest('.grid2'));
  presetRow.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-mode]');
    if (!b) return;
    mode = b.dataset.mode;
    hist = new Float64Array(N * N);
    stats = { done: 0, escaped: 0, plotted: 0 };
    t0 = performance.now();
  });
  anchorsRefresh();
  render();
})();

/* ================================================================ EXPLORER */
(function () {
  const cv = document.getElementById('ex-canvas');
  if (!cv) return;
  const ctx = cv.getContext('2d');
  const W = cv.width,
    H = cv.height;
  const hud = document.getElementById('ex-hud');
  const view = { cx: -0.6, cy: 0, scale: 3.4 };
  const palette = [];
  for (let i = 0; i < 256; i++) {
    const t = i / 255;
    palette.push([9 + 246 * t ** 1.6, 9 + 230 * t ** 2.2, 14 + 200 * t ** 3]);
  }
  function render(res) {
    const step = res;
    const img = ctx.createImageData(Math.ceil(W / step), Math.ceil(H / step));
    const aspect = W / H;
    const half = view.scale / 2;
    const d = img.data;
    let p = 0;
    for (let py = 0; py < img.height; py++) {
      const cy = view.cy + half - ((py + 0.5) / img.height) * view.scale;
      for (let px = 0; px < img.width; px++, p += 4) {
        const cx = view.cx - half * aspect + ((px + 0.5) / img.width) * view.scale * aspect;
        let x = cx,
          y = cy,
          k = 0;
        for (; k < 96; k++) {
          const nx = x * x - y * y + cx,
            ny = 2 * x * y + cy;
          x = nx;
          y = ny;
          if (x * x + y * y > 4) break;
        }
        if (k >= 96) {
          d[p] = 8;
          d[p + 1] = 7;
          d[p + 2] = 12;
        } else {
          const c = palette[Math.min(255, (k * 7) & 255)];
          d[p] = c[0];
          d[p + 1] = c[1];
          d[p + 2] = c[2];
        }
        d[p + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
    if (step > 1) ctx.drawImage(cv, 0, 0, img.width, img.height, 0, 0, W, H);
    hud.textContent = `center ${view.cx.toFixed(5)} ${view.cy < 0 ? '−' : '+'} ${Math.abs(view.cy).toFixed(5)}i · scale ${view.scale.toPrecision(3)} · zoom ${(3.4 / view.scale).toPrecision(3)}×`;
  }
  let idleTimer = null,
    drag = null,
    moved = false;
  const fullRender = () => render(1);
  const coarseRender = () => render(4);
  function poke() {
    coarseRender();
    clearTimeout(idleTimer);
    idleTimer = setTimeout(fullRender, 220);
  }
  cv.addEventListener(
    'wheel',
    (e) => {
      e.preventDefault();
      const r = cv.getBoundingClientRect();
      const mx = (e.clientX - r.left) / r.width,
        my = (e.clientY - r.top) / r.height;
      const aspect = W / H;
      const wx = view.cx - (view.scale / 2) * aspect + mx * view.scale * aspect;
      const wy = view.cy + view.scale / 2 - my * view.scale;
      const f = e.deltaY > 0 ? 1.15 : 1 / 1.15;
      view.scale = M.min(5, M.max(1e-6, view.scale * f));
      view.cx = wx - (mx - 0.5) * view.scale * aspect;
      view.cy = wy + (my - 0.5) * view.scale;
      poke();
    },
    { passive: false },
  );
  cv.addEventListener('pointerdown', (e) => {
    drag = { x: e.clientX, y: e.clientY };
    moved = false;
    cv.setPointerCapture(e.pointerId);
  });
  cv.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x,
      dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
    const aspect = W / H;
    view.cx -= (dx / cv.getBoundingClientRect().width) * view.scale * aspect;
    view.cy += (dy / cv.getBoundingClientRect().height) * view.scale;
    drag = { x: e.clientX, y: e.clientY };
    poke();
  });
  cv.addEventListener('pointerup', (e) => {
    drag = null;
    if (moved) return;
    // click: send c to the orbit theater
    const r = cv.getBoundingClientRect();
    const mx = (e.clientX - r.left) / r.width,
      my = (e.clientY - r.top) / r.height;
    const aspect = W / H;
    const c = [
      view.cx - (view.scale / 2) * aspect + mx * view.scale * aspect,
      view.cy + view.scale / 2 - my * view.scale,
    ];
    document.dispatchEvent(new CustomEvent('brot:pick-c', { detail: { c } }));
    hud.textContent += ` · sent c = ${c[0].toFixed(4)} ${c[1] < 0 ? '−' : '+'} ${Math.abs(c[1]).toFixed(4)}i to the orbit theater ↑`;
  });
  cv.addEventListener('dblclick', () => {
    view.cx = -0.6;
    view.cy = 0;
    view.scale = 3.4;
    fullRender();
  });
  fullRender();
})();

/* ==================================================== BUILD SUITE (L3) */
// Operator grammar shared with brot_build.py — semantics identical on both
// sides (the Python expressions and these JS expressions are generated from
// the same table; the parity test enforces name parity, the round-trip docs
// the behavior parity).
const BUILD = {
  real: {
    cos: (x) => M.cos(x * x),
    sin: (x) => M.sin(x * x),
    tan: (x) => M.tan(x * x),
    sinh: (x) => M.sinh(x * x),
    exp: (x) => M.exp(x * x),
    abs: (x) => M.abs(x * x),
  },
  imag: {
    plain: (t) => t,
    cos: (t) => M.cos(t),
    abs: (t) => M.abs(t),
    neg: (t) => -t,
    absxy: (t) => M.abs(t),
  },
  powerReal: {
    2: (x, y) => x * x - y * y,
    3: (x, y) => x ** 3 - 3 * x * y * y,
    4: (x, y) => x ** 4 - 6 * x * x * y * y + y ** 4,
    5: (x, y) => x ** 5 - 10 * x ** 3 * y * y + 5 * x * y ** 4,
  },
};

function buildMap(name, grammar) {
  const g = grammar;
  let step;
  if (g.family === 'mutation') {
    const f = BUILD.real[g.real],
      h = BUILD.imag[g.imag];
    step = (x, y, cx, cy) => [f(x) - y + cx, h(2.0 * x * y) + cy];
  } else if (g.family === 'fold') {
    const h = BUILD.imag[g.imag];
    const pr = BUILD.powerReal[g.power || 2];
    const wrap = g.real === 'abs' ? M.abs : (v) => v;
    step = (x, y, cx, cy) => [wrap(pr(x, y)) + cx, h(2.0 * x * y) + cy];
  } else {
    const pr = BUILD.powerReal[g.power || 3];
    const n = g.power || 3;
    // imaginary part of z^n via (x+iy)^n binomial for n=2..5
    const pi = {
      2: (x, y) => 2.0 * x * y,
      3: (x, y) => 3 * x * x * y - y ** 3,
      4: (x, y) => 4 * x * y * (x * x - y * y),
      5: (x, y) => 5 * x ** 4 * y - 10 * x * x * y ** 3 + y ** 5,
    }[n];
    step = (x, y, cx, cy) => [pr(x, y) + cx, pi(x, y) + cy];
  }
  const esc = g.family === 'mutation' ? 1e4 : 4.0;
  return {
    label: name + ' (built)',
    win: g.family === 'mutation' ? [-2.5, 2.5, -2.5, 2.5] : [-2.0, 2.0, -2.0, 2.0],
    step,
    gone: (x, y) => {
      const r = x * x + y * y;
      return r > esc || !isFinite(r);
    },
  };
}

(function buildSuiteUI() {
  const panel = document.getElementById('build-panel');
  if (!panel) return;
  const selR = document.getElementById('bu-real'),
    selI = document.getElementById('bu-imag');
  for (const [sel, table] of [
    [selR, BUILD.real],
    [selI, BUILD.imag],
  ])
    for (const k of Object.keys(table))
      sel.appendChild(
        Object.assign(document.createElement('option'), { value: k, textContent: k }),
      );
  const selF = document.getElementById('bu-family'),
    selP = document.getElementById('bu-power');
  const nameEl = document.getElementById('bu-name');
  const cv = document.getElementById('bu-canvas'),
    ctx = cv.getContext('2d');
  const hud = document.getElementById('bu-hud');
  let current = null;

  function grammar() {
    return {
      family: selF.value,
      real: selR.value,
      imag: selI.value,
      power: +selP.value,
    };
  }
  function redraw() {
    const g = grammar();
    current = buildMap((nameEl.value || 'custom').replace(/[^a-z0-9_]/gi, ''), g);
    current.grammar = { ...g }; // L4: mutations/pins can read the exact grammar
    // quick escape-time preview (not orbit density: instant feedback)
    const N = cv.width,
      img = ctx.createImageData(N, N);
    const w = current.win;
    let k = 0;
    for (let py = 0; py < N; py++) {
      for (let px = 0; px < N; px++, k += 4) {
        const cx = w[0] + (px / N) * (w[1] - w[0]);
        const cy = w[3] - (py / N) * (w[3] - w[2]);
        let x = cx,
          y = cy,
          n = 0;
        for (; n < 80; n++) {
          [x, y] = current.step(x, y, cx, cy);
          if (!isFinite(x) || !isFinite(y) || current.gone(x, y)) break;
        }
        const t = n / 80;
        img.data[k] = 9 + 246 * t ** 1.6;
        img.data[k + 1] = 9 + 230 * t ** 2.2;
        img.data[k + 2] = 14 + 200 * t ** 3;
        img.data[k + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
    hud.textContent = current.label + ' · ' + JSON.stringify(grammar());
  }
  [selR, selI, selF, selP].forEach((el) => el.addEventListener('change', redraw));
  nameEl.addEventListener('input', redraw);
  document.getElementById('bu-register').addEventListener('click', () => {
    if (!current) redraw();
    const key = 'built_' + (nameEl.value || 'custom').replace(/[^a-z0-9_]/gi, '').toLowerCase();
    MAPS[key] = current;
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = current.label;
    document.getElementById('ot-map').appendChild(opt);
    document.getElementById('ot-map').value = key;
    document
      .getElementById('mb-map')
      .appendChild(
        Object.assign(document.createElement('option'), { value: key, textContent: current.label }),
      );
    hud.textContent = 'registered as ' + key + ' — live in Orbit theater + Developing room';
  });
  document.getElementById('bu-compare').addEventListener('click', () => {
    if (!current) redraw();
    const a = document.getElementById('bu-canvas'),
      b = document.getElementById('bu-base');
    b.width = a.width;
    b.height = a.height;
    const bctx = b.getContext('2d');
    const base = currentMap(document.getElementById('ot-map'));
    const N = a.width,
      img = bctx.createImageData(N, N);
    const w = current.win;
    let k = 0;
    for (let py = 0; py < N; py++) {
      for (let px = 0; px < N; px++, k += 4) {
        const cx = w[0] + (px / N) * (w[1] - w[0]);
        const cy = w[3] - (py / N) * (w[3] - w[2]);
        let x = cx,
          y = cy,
          n = 0;
        for (; n < 80; n++) {
          [x, y] = base.step(x, y, cx, cy);
          if (!isFinite(x) || !isFinite(y) || base.gone(x, y)) break;
        }
        const t = n / 80;
        img.data[k] = 9 + 246 * t ** 1.6;
        img.data[k + 1] = 9 + 230 * t ** 2.2;
        img.data[k + 2] = 14 + 200 * t ** 3;
        img.data[k + 3] = 255;
      }
    }
    bctx.putImageData(img, 0, 0);
    hud.textContent = 'side-by-side: left = built, right = current theater map';
  });
  // register catalogue entries (user-authored maps shipped from brot_build)
  if (window.BROT_CATALOGUE) {
    const list = document.getElementById('bu-catalogue');
    for (const e of window.BROT_CATALOGUE) {
      if (!e.grammar) continue;
      const key = 'cat_' + e.name;
      MAPS[key] = buildMap(e.name, e.grammar);
      const li = document.createElement('li');
      li.style.cssText =
        'display:flex;gap:10px;align-items:center;font-size:13px;color:var(--muted)';
      if (e.hasPreview) {
        const img = document.createElement('img');
        img.src = e.preview;
        img.style.cssText = 'width:56px;height:56px;object-fit:cover;border-radius:6px';
        li.appendChild(img);
      }
      const span = document.createElement('span');
      span.innerHTML = '<b style="color:var(--text)">' + e.name + '</b><br>' + e.formula;
      li.appendChild(span);
      const btn = document.createElement('button');
      btn.className = 'btn';
      btn.textContent = 'load';
      btn.onclick = () => {
        const sel = document.getElementById('ot-map');
        if (![...sel.options].some((o) => o.value === key))
          sel.appendChild(
            Object.assign(document.createElement('option'), { value: key, textContent: e.name }),
          );
        sel.value = key;
        hud.textContent = e.name + ' loaded into the orbit theater';
      };
      li.appendChild(btn);
      list.appendChild(li);
    }
  }
  redraw();
})();

/* ====================================================== EXPERIMENTS (L4) */
// Experiment = { map key | grammar {family,real,imag,power,name} } + constants
// (orbit c, mode) + caps (iteration cap, samples/frame) + window override +
// tone gamma + seed. State <-> compact JSON <-> URL hash, shareable links,
// seeded surprise / mutate / suggestions, localStorage pins, JSON/PNG save
// and validated import (file picker + drag-drop). No dependencies, offline.
(function experimentsUI() {
  const panel = document.getElementById('exp-panel');
  if (!panel) return;
  const hud = document.getElementById('exp-hud');
  const seedEl = document.getElementById('exp-seed');
  const suggestBox = document.getElementById('exp-suggest');
  const pinsList = document.getElementById('exp-pins');
  const PINS_KEY = 'fd-pins-v1';
  const FAMILIES = ['mutation', 'fold', 'power'];
  const REAL_KEYS = Object.keys(BUILD.real);
  const IMAG_KEYS = Object.keys(BUILD.imag);
  // canonical grammars for the stock maps that the operator grammar can express
  const STOCK_GRAMMAR = {
    mandel: { family: 'power', real: 'cos', imag: 'plain', power: 2 },
    z3: { family: 'power', real: 'cos', imag: 'plain', power: 3 },
    z4: { family: 'power', real: 'cos', imag: 'plain', power: 4 },
    z5: { family: 'power', real: 'cos', imag: 'plain', power: 5 },
    ship: { family: 'fold', real: 'cos', imag: 'abs', power: 2 },
    tricorn: { family: 'fold', real: 'cos', imag: 'neg', power: 2 },
    celtic: { family: 'fold', real: 'abs', imag: 'plain', power: 2 },
    buffalo: { family: 'fold', real: 'abs', imag: 'abs', power: 2 },
    cosmut: { family: 'mutation', real: 'cos', imag: 'plain', power: 2 },
    tanmut: { family: 'mutation', real: 'tan', imag: 'plain', power: 2 },
    sinhmut: { family: 'mutation', real: 'sinh', imag: 'plain', power: 2 },
    expmut: { family: 'mutation', real: 'exp', imag: 'plain', power: 2 },
  };
  let mutateN = 0;
  let currentGrammar = null;

  /* ------------------------------------------------------------- HUD + msg */
  function hudMsg(html, isErr) {
    hud.innerHTML =
      (isErr ? '<b style="color:#d96a6a">' + 'experiment error:</b> ' : '<b>·</b> ') + html;
  }
  const esc = (s) =>
    String(s).replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );

  /* ------------------------------------------------ grammar lookup + build */
  function grammarFor(key) {
    const m = MAPS[key];
    if (m && m.grammar) return { ...m.grammar };
    if (STOCK_GRAMMAR[key]) return { ...STOCK_GRAMMAR[key] };
    if (key.startsWith('cat_') && window.BROT_CATALOGUE) {
      const e = window.BROT_CATALOGUE.find((c) => 'cat_' + c.name === key);
      if (e && e.grammar) return { ...e.grammar };
    }
    return null;
  }
  function registerMap(key, m) {
    const existing = MAPS[key];
    if (existing) Object.assign(existing, m);
    else MAPS[key] = m;
    for (const id of ['ot-map', 'mb-map']) {
      const sel = document.getElementById(id);
      if (!sel) continue;
      let opt = [...sel.options].find((o) => o.value === key);
      if (!opt) {
        opt = Object.assign(document.createElement('option'), { value: key });
        sel.appendChild(opt);
      }
      opt.textContent = m.label;
    }
  }
  function selectMap(key) {
    for (const id of ['ot-map', 'mb-map']) {
      const sel = document.getElementById(id);
      if (!sel || ![...sel.options].some((o) => o.value === key)) continue;
      const changed = sel.value !== key;
      sel.value = key;
      if (changed && id === 'ot-map') sel.dispatchEvent(new Event('change'));
    }
  }
  function syncBuildSelects(g) {
    const set = (id, v) => {
      const el = document.getElementById(id);
      if (el && [...el.options].some((o) => o.value === String(v))) el.value = String(v);
    };
    set('bu-family', g.family);
    set('bu-real', g.real);
    set('bu-imag', g.imag);
    set('bu-power', g.power);
    const f = document.getElementById('bu-family');
    if (f) f.dispatchEvent(new Event('change')); // one redraw of the preview
  }
  function renderEscapeTime(cv, m) {
    const ctx = cv.getContext('2d');
    const N = cv.width,
      Hc = cv.height;
    const img = ctx.createImageData(N, Hc);
    const w = m.win || [-2.5, 2.5, -2.5, 2.5];
    let k = 0;
    for (let py = 0; py < Hc; py++) {
      for (let px = 0; px < N; px++, k += 4) {
        const cx = w[0] + (px / N) * (w[1] - w[0]);
        const cy = w[3] - (py / Hc) * (w[3] - w[2]);
        let x = cx,
          y = cy,
          n = 0;
        for (; n < 80; n++) {
          [x, y] = m.step(x, y, cx, cy);
          if (!isFinite(x) || !isFinite(y) || m.gone(x, y)) break;
        }
        const t = n / 80;
        img.data[k] = 9 + 246 * t ** 1.6;
        img.data[k + 1] = 9 + 230 * t ** 2.2;
        img.data[k + 2] = 14 + 200 * t ** 3;
        img.data[k + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  /* ----------------------------------------------- state: read / validate */
  function currentState() {
    const otKey = document.getElementById('ot-map').value;
    const g = currentGrammar || grammarFor(otKey);
    const st = { v: 1, map: g ? { ...g } : otKey };
    if (SHARED.usesCustom && SHARED.usesCustom()) {
      st.fx = document.getElementById('ot-fx').value;
      st.fy = document.getElementById('ot-fy').value;
    }
    if (SHARED.theaterC) st.c = SHARED.theaterC();
    st.mode = SHARED.mbMode ? SHARED.mbMode() : 'escape';
    st.cap = +document.getElementById('mb-cap').value;
    st.rate = +document.getElementById('mb-rate').value;
    st.gamma = +document.getElementById('mb-gamma').value;
    const m = MAPS[otKey];
    if (m && m.win && g && m.grammar) st.win = m.win.slice(); // grammar maps carry their window
    const seed = parseInt(seedEl.value, 10);
    if (Number.isFinite(seed)) st.seed = seed;
    return st;
  }
  function compact(st) {
    // drop defaults so the hash stays short; round-trip lossless
    const out = { v: 1, map: st.map };
    const defs = [
      ['fx', 'x*x - y*y + cx'],
      ['fy', '2*x*y + cy'],
    ];
    for (const [k, d] of defs) if (st[k] !== undefined && st[k] !== d) out[k] = st[k];
    if (st.c !== undefined && (st.c[0] !== -0.1 || st.c[1] !== 0.65)) out.c = st.c;
    if (st.mode !== undefined && st.mode !== 'escape') out.mode = st.mode;
    if (st.cap !== undefined && st.cap !== 120) out.cap = st.cap;
    if (st.rate !== undefined && st.rate !== 3000) out.rate = st.rate;
    if (st.gamma !== undefined && Math.abs(st.gamma - 1) > 1e-9) out.gamma = st.gamma;
    if (st.win !== undefined) out.win = st.win;
    if (st.seed !== undefined) out.seed = st.seed;
    return out;
  }
  function validateState(st, where) {
    const p = (m) => `${where}: ${m}`;
    if (!st || typeof st !== 'object' || Array.isArray(st))
      return { ok: false, msg: p('top level must be a JSON object') };
    if (st.v !== undefined && st.v !== 1)
      return { ok: false, msg: p(`unsupported state version ${st.v} (expected 1)`) };
    let map = st.map;
    if (map === undefined) map = 'mandel';
    if (typeof map === 'string') {
      if (!/^[a-z0-9_]{1,40}$/.test(map) || !(map in STOCK_GRAMMAR || map in MAPS))
        return { ok: false, msg: p(`unknown map key ${JSON.stringify(map)}`) };
    } else if (map && typeof map === 'object' && !Array.isArray(map)) {
      if (!FAMILIES.includes(map.family))
        return { ok: false, msg: p(`map.family must be one of ${FAMILIES.join('|')}`) };
      if (!REAL_KEYS.includes(map.real))
        return { ok: false, msg: p(`map.real must be one of ${REAL_KEYS.join('|')}`) };
      if (!IMAG_KEYS.includes(map.imag))
        return { ok: false, msg: p(`map.imag must be one of ${IMAG_KEYS.join('|')}`) };
      if (![2, 3, 4, 5].includes(map.power))
        return { ok: false, msg: p('map.power must be one of 2|3|4|5') };
      if (map.name !== undefined && (typeof map.name !== 'string' || map.name.length > 24))
        return { ok: false, msg: p('map.name must be a string of at most 24 chars') };
    } else {
      return { ok: false, msg: p('map must be a key string or a grammar object') };
    }
    const rangeOk = (k, lo, hi) =>
      st[k] === undefined ||
      (typeof st[k] === 'number' && Number.isFinite(st[k]) && st[k] >= lo && st[k] <= hi) ||
      p(`${k} must be a number in [${lo}, ${hi}]`);
    for (const [k, lo, hi] of [
      ['cap', 10, 400],
      ['rate', 200, 8000],
      ['gamma', 0.4, 2.2],
    ]) {
      const r = rangeOk(k, lo, hi);
      if (typeof r === 'string') return { ok: false, msg: r };
    }
    if (st.mode !== undefined && !['escape', 'anti', 'julia'].includes(st.mode))
      return { ok: false, msg: p('mode must be one of escape|anti|julia') };
    if (
      st.seed !== undefined &&
      !(Number.isInteger(st.seed) && st.seed >= 0 && st.seed <= 2147483647)
    )
      return { ok: false, msg: p('seed must be an integer in [0, 2147483647]') };
    for (const k of ['fx', 'fy'])
      if (st[k] !== undefined && (typeof st[k] !== 'string' || st[k].length > 200))
        return { ok: false, msg: p(`${k} must be a formula string of at most 200 chars`) };
    if (
      st.c !== undefined &&
      !(
        Array.isArray(st.c) &&
        st.c.length === 2 &&
        st.c.every((v) => Number.isFinite(v) && Math.abs(v) <= 100)
      )
    )
      return { ok: false, msg: p('c must be [x, y] with |x|,|y| <= 100') };
    if (
      st.win !== undefined &&
      st.win !== null &&
      !(
        Array.isArray(st.win) &&
        st.win.length === 4 &&
        st.win.every((v) => Number.isFinite(v) && Math.abs(v) <= 1e3) &&
        st.win[1] > st.win[0] &&
        st.win[3] > st.win[2]
      )
    )
      return { ok: false, msg: p('win must be [x0, x1, y0, y1] with x1 > x0, y1 > y0') };
    const norm = { ...st, map };
    return { ok: true, st: norm };
  }
  function parseExperimentData(data, where) {
    if (Array.isArray(data)) return { ok: true, pins: data };
    return validateState(data, where);
  }
  function parseExperimentText(text, where) {
    let data;
    try {
      data = JSON.parse(text);
    } catch (err) {
      return { ok: false, msg: `${where}: not valid JSON (${err.message})` };
    }
    return parseExperimentData(data, where);
  }

  /* ------------------------------------------- APRS bundles (L5, ADR 0001) */
  // Attractor Parameter Record Set: the shareable experiment record. The JS
  // rules below mirror scripts/validate_aprs.py field-for-field (the Python
  // validator is the authority; both producers must pass both).
  const APRS = {
    REQUIRED: [
      'schema',
      'name',
      'grammar',
      'window',
      'caps',
      'gamma',
      'notes',
      'author',
      'created',
      'renderer',
      'provenance',
      'preview',
    ],
    PROV: ['authored-on-site', 'imported-bundle'],
    NAME: /^[A-Za-z0-9_][A-Za-z0-9_ -]*$/,
    PREVIEW: /^[0-9a-f]{8}$/,
    CREATED: /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/,
  };
  function validateAprs(d, where) {
    const p = (m) => ({ ok: false, msg: `${where}: ${m}` });
    if (!d || typeof d !== 'object' || Array.isArray(d))
      return p('top level must be a JSON object');
    const errs = [];
    for (const k of Object.keys(d))
      if (!APRS.REQUIRED.includes(k)) errs.push(`unknown field '${k}'`);
    for (const k of APRS.REQUIRED) if (!(k in d)) errs.push(`missing required field '${k}'`);
    const numOk = (v) => typeof v === 'number' && Number.isFinite(v);
    if (d.schema && typeof d.schema === 'object') {
      for (const k of Object.keys(d.schema))
        if (k !== 'version') errs.push(`unknown field '${k}' in schema`);
      if ('version' in d.schema && d.schema.version !== 1)
        errs.push('schema.version must be the integer 1');
    } else {
      errs.push('schema must be an object with an integer version field');
    }
    if (
      typeof d.name !== 'string' ||
      d.name.length < 1 ||
      d.name.length > 40 ||
      !APRS.NAME.test(d.name)
    )
      errs.push('name must be 1-40 chars matching ^[A-Za-z0-9_][A-Za-z0-9_ -]*$');
    if (d.grammar && typeof d.grammar === 'object' && !Array.isArray(d.grammar)) {
      const g = d.grammar;
      if (!FAMILIES.includes(g.family))
        errs.push(`grammar.family must be one of ${FAMILIES.join('|')}`);
      if (!REAL_KEYS.includes(g.real))
        errs.push(`grammar.real must be one of ${REAL_KEYS.join('|')}`);
      if (!IMAG_KEYS.includes(g.imag))
        errs.push(`grammar.imag must be one of ${IMAG_KEYS.join('|')}`);
      if (!Number.isInteger(g.power) || g.power < 2 || g.power > 5)
        errs.push('grammar.power must be an integer in [2, 5]');
      for (const k of Object.keys(g))
        if (!['family', 'real', 'imag', 'power'].includes(k))
          errs.push(`unknown field '${k}' in grammar`);
    } else {
      errs.push('grammar must be an object {family, real, imag, power}');
    }
    if (
      Array.isArray(d.window) &&
      d.window.length === 4 &&
      d.window.every((v) => numOk(v) && Math.abs(v) <= 1e4)
    ) {
      if (!(d.window[1] > d.window[0] && d.window[3] > d.window[2]))
        errs.push('window must be ordered [x0<x1, y0<y1]');
    } else {
      errs.push('window must be 4 finite numbers with |v| <= 10000');
    }
    if (
      Array.isArray(d.caps) &&
      d.caps.length === 3 &&
      d.caps.every((c) => Number.isInteger(c) && c > 0 && c <= 100000)
    ) {
      if (!(d.caps[0] < d.caps[1] && d.caps[1] < d.caps[2]))
        errs.push('caps must be 3 strictly ascending iteration caps');
    } else {
      errs.push('caps must be 3 integers with 0 < cap <= 100000');
    }
    if (!numOk(d.gamma) || d.gamma <= 0 || d.gamma > 10)
      errs.push('gamma must be a finite number in (0, 10]');
    if (typeof d.notes !== 'string' || d.notes.length > 2000)
      errs.push('notes must be a string of at most 2000 chars');
    if (typeof d.author !== 'string' || d.author.length < 1 || d.author.length > 80)
      errs.push('author must be a string of 1-80 chars');
    if (
      typeof d.created !== 'string' ||
      !APRS.CREATED.test(d.created) ||
      Number.isNaN(Date.parse(d.created))
    )
      errs.push('created must be an RFC 3339 date-time with timezone');
    if (d.renderer !== 'fractal-darkroom') errs.push("renderer must be 'fractal-darkroom'");
    if (!APRS.PROV.includes(d.provenance))
      errs.push(`provenance must be one of ${APRS.PROV.join('|')}`);
    if (d.preview !== null && (typeof d.preview !== 'string' || !APRS.PREVIEW.test(d.preview)))
      errs.push('preview must be null or 8 lowercase hex chars (sha1[:8])');
    return errs.length ? p(errs.join('; ')) : { ok: true };
  }
  function looksLikeAprs(data) {
    return (
      !!data &&
      typeof data === 'object' &&
      !Array.isArray(data) &&
      data.renderer === 'fractal-darkroom' &&
      !!data.grammar &&
      typeof data.grammar === 'object'
    );
  }
  function aprsNameFor(g, key) {
    const raw = (g && g.name) || key || 'aprs';
    const s = String(raw)
      .replace(/[^A-Za-z0-9_ -]/g, '')
      .slice(0, 40);
    return /^[A-Za-z0-9_]/.test(s) ? s : 'aprs_' + s;
  }
  let loadedAprs = null; // last loaded bundle; re-export carries its provenance
  async function exportAprs() {
    const otKey = document.getElementById('ot-map').value;
    const g = currentGrammar || grammarFor(otKey);
    if (!g) {
      hudMsg(
        'APRS export needs a grammar-backed map (stock grammar maps, built/surprise maps, or a loaded APRS)',
        true,
      );
      return;
    }
    const cap = +document.getElementById('mb-cap').value;
    const caps = [
      Math.min(Math.max(10, Math.floor(cap / 5)), cap - 1),
      cap,
      Math.min(100000, cap * 5),
    ];
    const off = document.createElement('canvas');
    off.width = off.height = 128;
    renderEscapeTime(off, activeExpMap());
    const blob = await new Promise((res) => off.toBlob(res, 'image/png'));
    const preview = blob ? sha1hex(new Uint8Array(await blob.arrayBuffer())).slice(0, 8) : null;
    const rec = {
      schema: { version: 1 },
      name: aprsNameFor(g, otKey),
      grammar: { family: g.family, real: g.real, imag: g.imag, power: g.power },
      window: (activeExpMap().win || [-2.5, 2.5, -2.5, 2.5]).map(Number),
      caps,
      gamma: +document.getElementById('mb-gamma').value,
      notes: 'exported from the playground experiments panel',
      author: 'playground',
      created: new Date().toISOString(),
      renderer: 'fractal-darkroom',
      provenance: loadedAprs ? 'imported-bundle' : 'authored-on-site',
      preview,
    };
    const v = validateAprs(rec, 'APRS export');
    if (!v.ok) {
      hudMsg(v.msg, true);
      return;
    }
    download(
      `${rec.name}.aprs.json`,
      new Blob([JSON.stringify(rec, null, 2) + '\n'], { type: 'application/json' }),
    );
    hudMsg(
      `APRS <b>${esc(rec.name)}</b> exported · preview ${rec.preview} · validated against the schema v1 field set`,
    );
  }
  function loadAprsData(d, where) {
    const v = validateAprs(d, where);
    if (!v.ok) {
      hudMsg(v.msg, true);
      return false;
    }
    const g = d.grammar;
    const mapName =
      (d.name || 'aprs')
        .replace(/[^a-z0-9_]/gi, '')
        .toLowerCase()
        .slice(0, 24) || 'aprs';
    const cap = Math.max(10, Math.min(400, d.caps[1]));
    const gamma = Math.max(0.4, Math.min(2.2, d.gamma));
    const st = {
      v: 1,
      map: { family: g.family, real: g.real, imag: g.imag, power: g.power, name: mapName },
      cap,
      gamma,
      win: d.window.slice(),
    };
    const vst = validateState(st, where);
    if (!vst.ok) {
      hudMsg(vst.msg, true);
      return false;
    }
    applyState(vst.st, where);
    loadedAprs = d;
    const clamped = [];
    if (cap !== d.caps[1]) clamped.push(`cap ${d.caps[1]}→${cap}`);
    if (Math.abs(gamma - d.gamma) > 1e-9) clamped.push(`γ ${d.gamma}→${gamma}`);
    hud.innerHTML =
      `<b>APRS loaded</b> · ${esc(d.name)} · ${esc(`${g.family}:${g.real}/${g.imag} p${g.power}`)}` +
      ` · caps [${d.caps.join(', ')}] · γ ${d.gamma}${d.preview ? ` · preview ${d.preview}` : ' · no preview'}` +
      ` · provenance <b>${esc(d.provenance)}</b>` +
      (clamped.length ? ` · clamped to UI range: ${clamped.join(', ')}` : '') +
      ' — re-export keeps provenance “imported-bundle”';
    return true;
  }

  /* ---------------------------------------------------------- state: apply */
  function setKnob(id, v) {
    const el = document.getElementById(id);
    if (!el || v === undefined) return;
    el.value = String(v);
    el.dispatchEvent(new Event('input'));
  }
  function applyState(st, source) {
    let label;
    if (st.map && typeof st.map === 'object') {
      const g = st.map;
      const name = (g.name || 'exp').replace(/[^a-z0-9_]/gi, '').toLowerCase() || 'exp';
      const m = buildMap(name, g);
      m.grammar = { ...g };
      if (st.win) m.win = st.win.slice();
      registerMap('exp_' + name, m);
      syncBuildSelects(g);
      selectMap('exp_' + name);
      currentGrammar = { ...g, name };
      label = m.label;
    } else {
      let key = st.map || 'mandel';
      if (st.win) {
        const src = MAPS[key] || MAPS.mandel;
        const copy = { ...src, win: st.win.slice() };
        if (copy.grammar) copy.grammar = { ...copy.grammar };
        registerMap('exp_ovr_' + key, copy);
        key = 'exp_ovr_' + key;
      }
      selectMap(key);
      currentGrammar = grammarFor(st.map || 'mandel');
      label = MAPS[key].label;
    }
    if (st.fx || st.fy) {
      try {
        const m = compileFormula(st.fx || 'x*x - y*y + cx', st.fy || '2*x*y + cy');
        SHARED.setCustom({ ...m, win: st.win ? st.win.slice() : [-3, 3, -3, 3] });
        document.getElementById('ot-fx').value = st.fx || 'x*x - y*y + cx';
        document.getElementById('ot-fy').value = st.fy || '2*x*y + cy';
        label = 'custom formula';
      } catch (err) {
        hudMsg(
          `${source}: custom formula rejected (${esc(err.message)}) — map restored without it`,
          true,
        );
      }
    }
    setKnob('mb-cap', st.cap);
    setKnob('mb-rate', st.rate);
    setKnob('mb-gamma', st.gamma);
    if (st.mode) {
      const b = document.querySelector(`button[data-mode="${st.mode}"]`);
      if (b) b.click();
    }
    if (st.c) document.dispatchEvent(new CustomEvent('brot:pick-c', { detail: { c: st.c } }));
    if (st.seed !== undefined) seedEl.value = String(st.seed);
    writeHash();
    renderSuggestions();
    hudMsg(
      `${esc(source)} · map <b>${esc(label)}</b> · cap ${st.cap ?? 120} · γ ${st.gamma ?? 1}` +
        (st.seed !== undefined ? ` · seed ${st.seed}` : ''),
    );
    return label;
  }
  function writeHash() {
    const enc = encodeURIComponent(JSON.stringify(compact(currentState())));
    try {
      history.replaceState(null, '', '#exp=' + enc);
    } catch {
      location.hash = 'exp=' + enc; // file:// in strict embedders
    }
  }

  /* ---------------------------------------------- seeded grammar operators */
  function pickGrammar(rand) {
    return {
      family: FAMILIES[Math.floor(rand() * 3)],
      real: REAL_KEYS[Math.floor(rand() * REAL_KEYS.length)],
      imag: IMAG_KEYS[Math.floor(rand() * IMAG_KEYS.length)],
      power: 2 + Math.floor(rand() * 4),
    };
  }
  function escapeFraction(m, gridN, cap) {
    const w = m.win || [-2.5, 2.5, -2.5, 2.5];
    let esc = 0;
    for (let gy = 0; gy < gridN; gy++) {
      for (let gx = 0; gx < gridN; gx++) {
        const cx = w[0] + ((gx + 0.5) / gridN) * (w[1] - w[0]);
        const cy = w[3] - ((gy + 0.5) / gridN) * (w[3] - w[2]);
        let x = cx,
          y = cy,
          k = 0;
        for (; k < cap; k++) {
          [x, y] = m.step(x, y, cx, cy);
          if (!isFinite(x) || !isFinite(y) || m.gone(x, y)) break;
        }
        if (k < cap) esc++;
      }
    }
    return esc / (gridN * gridN);
  }
  function surpriseFrom(seed) {
    const rand = rng(seed);
    let g = pickGrammar(rand);
    for (let attempt = 1; attempt <= 24; attempt++) {
      const frac = escapeFraction(buildMap('probe', g), 16, 40);
      if (frac > 0.05 && frac < 0.95) return { g, attempt, frac };
      g = pickGrammar(rand);
    }
    return { g, attempt: 25, frac: null }; // grammar is valid by construction regardless
  }
  function mutateGrammar(g, rand) {
    const g2 = { ...g };
    const dims =
      g.family === 'mutation'
        ? ['real', 'imag']
        : g.family === 'fold'
          ? ['imag', 'power', 'real']
          : ['power'];
    dims.push('family');
    const dim = dims[Math.floor(rand() * dims.length)];
    if (dim === 'family') {
      const fams = FAMILIES.filter((f) => f !== g.family);
      g2.family = fams[Math.floor(rand() * fams.length)];
    } else if (dim === 'power') {
      do {
        g2.power = 2 + Math.floor(rand() * 4);
      } while (g2.power === g.power);
    } else if (dim === 'real') {
      if (g.family === 'fold')
        g2.real = g.real === 'abs' ? 'cos' : 'abs'; // abs-fold on/off
      else
        do {
          g2.real = REAL_KEYS[Math.floor(rand() * REAL_KEYS.length)];
        } while (g2.real === g.real);
    } else {
      do {
        g2.imag = IMAG_KEYS[Math.floor(rand() * IMAG_KEYS.length)];
      } while (g2.imag === g.imag);
    }
    return g2;
  }
  function describeChange(a, b) {
    for (const k of ['family', 'real', 'imag', 'power'])
      if (a[k] !== b[k]) return `${k}: ${a[k]} → ${b[k]}`;
    return 'no change';
  }
  function scoreGrammar(g) {
    const m = buildMap('score', g);
    const w = m.win || [-2.5, 2.5, -2.5, 2.5];
    const G = 20,
      cap = 40;
    let esc = 0,
      kmin = cap,
      kmax = 0;
    for (let gy = 0; gy < G; gy++) {
      for (let gx = 0; gx < G; gx++) {
        const cx = w[0] + ((gx + 0.5) / G) * (w[1] - w[0]);
        const cy = w[3] - ((gy + 0.5) / G) * (w[3] - w[2]);
        let x = cx,
          y = cy,
          k = 0;
        for (; k < cap; k++) {
          [x, y] = m.step(x, y, cx, cy);
          if (!isFinite(x) || !isFinite(y) || m.gone(x, y)) break;
        }
        if (k < cap) esc++;
        if (k < kmin) kmin = k;
        if (k > kmax) kmax = k;
      }
    }
    const frac = esc / (G * G);
    const range = (kmax - kmin) / cap;
    const band =
      frac >= 0.15 && frac <= 0.9
        ? 1
        : Math.max(0, 1 - Math.min(Math.abs(frac - 0.15), Math.abs(frac - 0.9)) * 2);
    return { frac, range, score: 0.6 * band + 0.4 * Math.min(1, range * 2.5) };
  }
  function suggestionsFor(seed, g) {
    const rand = rng(seed ^ 0x2545f491);
    const cands = [];
    for (let i = 0; i < 6; i++) {
      const cg = mutateGrammar(g, rand);
      const s = scoreGrammar(cg);
      cands.push({ g: cg, ...s, i });
    }
    cands.sort((a, b) => b.score - a.score || a.i - b.i);
    return cands.slice(0, 3);
  }

  /* ------------------------------------------------------- UI: suggestions */
  function renderSuggestions() {
    const seed = parseInt(seedEl.value, 10);
    const otKey = document.getElementById('ot-map').value;
    const g = currentGrammar || grammarFor(otKey);
    suggestBox.replaceChildren();
    if (!Number.isFinite(seed)) {
      suggestBox.appendChild(capLi('enter a seed to get deterministic suggestions'));
      return;
    }
    if (!g) {
      suggestBox.appendChild(
        capLi('current map has no operator grammar — pinning/suggesting need one'),
      );
      return;
    }
    for (const [n, cand] of suggestionsFor(seed, g).entries()) {
      const wrap = document.createElement('div');
      wrap.style.cssText = 'text-align:center;font-size:11.5px;color:var(--muted);cursor:pointer';
      const cv = document.createElement('canvas');
      cv.width = cv.height = 72;
      cv.style.cssText =
        'width:72px;height:72px;border-radius:6px;display:block;border:1px solid #333';
      cv.title = 'apply this mutation';
      renderEscapeTime(cv, buildMap('sug', cand.g));
      wrap.appendChild(cv);
      const cap = document.createElement('div');
      cap.textContent = `#${n + 1} score ${cand.score.toFixed(2)} · esc ${(cand.frac * 100).toFixed(0)}%`;
      wrap.appendChild(cap);
      const f = document.createElement('div');
      f.textContent = describeChange(g, cand.g);
      wrap.appendChild(f);
      wrap.addEventListener('click', () => {
        applyState(
          {
            v: 1,
            map: { ...cand.g, name: 'pick' + (n + 1) },
            cap: +document.getElementById('mb-cap').value,
            rate: +document.getElementById('mb-rate').value,
            gamma: +document.getElementById('mb-gamma').value,
            seed,
          },
          `suggestion #${n + 1} applied`,
        );
      });
      suggestBox.appendChild(wrap);
    }
  }
  function capLi(text) {
    const d = document.createElement('div');
    d.style.cssText = 'font-size:13px;color:var(--muted)';
    d.textContent = text;
    return d;
  }

  /* -------------------------------------------------------------- UI: pins */
  function readPins() {
    let raw = null;
    try {
      raw = localStorage.getItem(PINS_KEY);
    } catch {
      return { ok: false, pins: [], msg: 'localStorage unavailable in this embedder' };
    }
    let arr = [];
    try {
      arr = raw ? JSON.parse(raw) : [];
    } catch {
      arr = [];
    }
    return { ok: true, pins: Array.isArray(arr) ? arr : [] };
  }
  function writePins(pins) {
    try {
      localStorage.setItem(PINS_KEY, JSON.stringify(pins));
      return true;
    } catch {
      hudMsg('could not write pins to localStorage (private mode?)', true);
      return false;
    }
  }
  function pinLabel(st) {
    if (!st || !st.map) return '?';
    return typeof st.map === 'object'
      ? `${st.map.family}:${st.map.real}/${st.map.imag} p${st.map.power}`
      : String(st.map);
  }
  function renderPins() {
    const r = readPins();
    pinsList.replaceChildren();
    if (!r.ok) {
      pinsList.appendChild(pinRow('pins unavailable: ' + r.msg, null, null));
      return;
    }
    if (!r.pins.length) {
      pinsList.appendChild(
        pinRow('nothing pinned yet — Pin adds the current experiment', null, null),
      );
      return;
    }
    r.pins.forEach((pin, idx) => {
      const label =
        pin && typeof pin.name === 'string'
          ? pin.name
          : pinLabel(pin && pin.state ? pin.state : {});
      pinsList.appendChild(
        pinRow(
          `${label} · ${pin && pin.state ? `γ ${pin.state.gamma ?? 1} cap ${pin.state.cap ?? 120}` : '?'}`,
          () => {
            const v = validateState(pin.state, 'pin');
            if (v.ok) applyState(v.st, 'pin loaded');
            else hudMsg(v.msg, true);
          },
          () => {
            const cur = readPins();
            if (!cur.ok) return;
            cur.pins.splice(idx, 1);
            if (writePins(cur.pins)) {
              renderPins();
              hudMsg('pin removed');
            }
          },
        ),
      );
    });
  }
  function pinRow(text, onLoad, onRemove) {
    const li = document.createElement('li');
    li.style.cssText = 'display:flex;gap:10px;align-items:center;font-size:13px;color:var(--muted)';
    const span = document.createElement('span');
    span.style.flex = '1';
    span.textContent = text;
    li.appendChild(span);
    if (onLoad) {
      const b = Object.assign(document.createElement('button'), {
        className: 'btn',
        textContent: 'load',
      });
      b.addEventListener('click', onLoad);
      li.appendChild(b);
    }
    if (onRemove) {
      const b = Object.assign(document.createElement('button'), {
        className: 'btn',
        textContent: 'remove',
      });
      b.addEventListener('click', onRemove);
      li.appendChild(b);
    }
    return li;
  }

  /* -------------------------------------------------- save / share / import */
  function download(filename, blob) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }
  function activeExpMap() {
    const key = document.getElementById('ot-map').value;
    return MAPS[key] || MAPS.mandel;
  }
  function importFile(file, where) {
    file
      .text()
      .then((txt) => {
        let data;
        try {
          data = JSON.parse(txt);
        } catch (err) {
          hudMsg(`${where}: not valid JSON (${esc(err.message)})`, true);
          return;
        }
        if (looksLikeAprs(data)) {
          loadAprsData(data, `${where} (APRS)`);
          return;
        }
        const r = parseExperimentData(data, where);
        if (!r.ok) {
          hudMsg(r.msg, true);
          return;
        }
        if (r.pins) {
          const cur = readPins();
          if (!cur.ok) {
            hudMsg(cur.msg, true);
            return;
          }
          let added = 0,
            skipped = 0;
          for (const pin of r.pins) {
            const v = pin && pin.state ? validateState(pin.state, 'pin entry') : null;
            if (!v || !v.ok) {
              skipped++;
              continue;
            }
            cur.pins = cur.pins.filter((p) => p.name !== pin.name);
            cur.pins.push({
              name: String(pin.name || pinLabel(v.st)),
              ts: pin.ts || 0,
              state: v.st,
            });
            added++;
          }
          if (writePins(cur.pins)) {
            renderPins();
            hudMsg(`pins import: ${added} loaded, ${skipped} skipped as invalid`);
          }
          return;
        }
        applyState(r.st, `${where} imported`);
      })
      .catch((err) => hudMsg(`${where}: could not read file (${esc(err.message)})`, true));
  }

  /* ------------------------------------------------------------- wire up */
  document.getElementById('exp-surprise').addEventListener('click', () => {
    let seed = parseInt(seedEl.value, 10);
    if (!Number.isFinite(seed) || seed < 0) {
      seed = Date.now() & 0x7fffffff || 1;
      seedEl.value = String(seed);
    }
    const { g, attempt, frac } = surpriseFrom(seed);
    applyState(
      {
        v: 1,
        map: { ...g, name: 's' + seed },
        cap: +document.getElementById('mb-cap').value,
        rate: +document.getElementById('mb-rate').value,
        gamma: +document.getElementById('mb-gamma').value,
        seed,
      },
      'surprise',
    );
    hud.innerHTML =
      `<b>surprise</b> · seed <b>${seed}</b> (attempt ${attempt}` +
      (frac !== null
        ? `, escape fraction ${frac.toFixed(2)} in band`
        : ', fallback after 24 tries') +
      ') — same seed reproduces this map';
  });
  document.getElementById('exp-mutate').addEventListener('click', () => {
    const otKey = document.getElementById('ot-map').value;
    const base = currentGrammar || grammarFor(otKey);
    if (!base) {
      hudMsg(
        'the current map (' +
          esc(otKey) +
          ') has no operator grammar — surprise/suggestion maps and grammar-backed stock maps can be mutated',
        true,
      );
      return;
    }
    const seed = parseInt(seedEl.value, 10) || 0;
    const rand = rng((seed ^ 0x5f356495) + 7919 * ++mutateN);
    const g2 = mutateGrammar(base, rand);
    const key = 'exp_mut' + mutateN;
    const m = buildMap('mut' + mutateN, g2);
    m.grammar = { ...g2 };
    registerMap(key, m);
    syncBuildSelects(g2); // left canvas of the build pair shows the mutation
    const buBase = document.getElementById('bu-base'); // right canvas: the base map
    renderEscapeTime(buBase, MAPS[otKey] || buildMap('base', base));
    currentGrammar = { ...g2 };
    writeHash();
    renderSuggestions();
    hud.innerHTML =
      `<b>mutation ${mutateN}</b> · ${esc(describeChange(base, g2))} — side-by-side in the build panel ` +
      '(left: mutated, right: base); theater/developing room unchanged — register or pin to keep';
  });
  document.getElementById('exp-resuggest').addEventListener('click', renderSuggestions);
  document.getElementById('exp-pin').addEventListener('click', () => {
    const r = readPins();
    if (!r.ok) {
      hudMsg(r.msg, true);
      return;
    }
    const st = compact(currentState());
    const name =
      (typeof st.map === 'object' ? `${st.map.family}:${st.map.real}/${st.map.imag}` : st.map) +
      ` #${st.seed ?? 'ns'}`;
    r.pins.push({ name, ts: Date.now(), state: st });
    if (writePins(r.pins)) {
      renderPins();
      hudMsg(`pinned “${esc(name)}” (${r.pins.length} total)`);
    }
  });
  document.getElementById('exp-share').addEventListener('click', () => {
    writeHash();
    const url = location.href;
    const ok = () =>
      hudMsg(`share link copied (${url.length} chars) — the URL hash now carries this experiment`);
    const fallback = () => {
      const ta = document.createElement('textarea');
      ta.value = url;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      let done = false;
      try {
        done = document.execCommand('copy');
      } catch {
        done = false;
      }
      ta.remove();
      if (done) ok();
      else
        hudMsg(
          'clipboard blocked — the share link is the URL above (copy it from the address bar)',
          true,
        );
    };
    if (navigator.clipboard && navigator.clipboard.writeText)
      navigator.clipboard.writeText(url).then(ok, fallback);
    else fallback();
  });
  document.getElementById('exp-save-png').addEventListener('click', () => {
    const off = document.createElement('canvas');
    off.width = off.height = 600;
    renderEscapeTime(off, activeExpMap());
    off.toBlob((b) => {
      if (b) download(`experiment-${Date.now()}.png`, b);
    }, 'image/png');
    hudMsg('PNG saved (600² escape-time render of the current map)');
  });
  document.getElementById('exp-save-json').addEventListener('click', () => {
    download(
      `experiment-${Date.now()}.json`,
      new Blob([JSON.stringify(currentState(), null, 2)], { type: 'application/json' }),
    );
    hudMsg('experiment JSON saved — import it back via the picker or drag-drop');
  });
  document.getElementById('exp-import').addEventListener('change', (e) => {
    const f = e.target.files && e.target.files[0];
    if (f) importFile(f, 'experiment file');
    e.target.value = '';
  });
  document.getElementById('exp-import-pins').addEventListener('change', (e) => {
    const f = e.target.files && e.target.files[0];
    if (f) importFile(f, 'pins file');
    e.target.value = '';
  });
  document.getElementById('exp-export-pins').addEventListener('click', () => {
    const r = readPins();
    if (!r.ok) {
      hudMsg(r.msg, true);
      return;
    }
    download(
      'fd-pins.json',
      new Blob([JSON.stringify(r.pins, null, 2)], { type: 'application/json' }),
    );
    hudMsg(`${r.pins.length} pins exported`);
  });
  // APRS bundle export / import (picker; drag-drop goes through importFile)
  document.getElementById('exp-export-aprs').addEventListener('click', () => {
    exportAprs().catch((err) => hudMsg(`APRS export failed (${esc(err.message)})`, true));
  });
  document.getElementById('exp-import-aprs').addEventListener('change', (e) => {
    const f = e.target.files && e.target.files[0];
    if (f) importFile(f, 'APRS file');
    e.target.value = '';
  });
  // drag-drop import: an experiment JSON or a pins export, both accepted
  panel.addEventListener('dragover', (e) => e.preventDefault());
  panel.addEventListener('drop', (e) => {
    e.preventDefault();
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) importFile(f, 'dropped file');
  });
  seedEl.addEventListener('input', renderSuggestions);

  /* ------------------------------------------------------- boot: restore */
  renderPins();
  const h = location.hash;
  if (h.startsWith('#exp=')) {
    let txt = '';
    try {
      txt = decodeURIComponent(h.slice(5));
    } catch {
      hudMsg('link restore: the #exp= hash is not validly encoded — starting fresh', true);
    }
    if (txt) {
      const r = parseExperimentText(txt, 'link restore');
      if (r.ok && !r.pins) applyState(r.st, 'restored experiment from link');
      else if (r.ok)
        hudMsg(
          'link restore: the hash holds a pins list, not one experiment — use import for that',
          true,
        );
      else hudMsg(r.msg, true);
    }
  } else {
    renderSuggestions();
    hudMsg('experiments ready — surprise · mutate · pin · share');
  }
})();
