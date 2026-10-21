// Brot Farm docs — shared page behaviors: scroll reveal + the "developing
// photograph" hero animation (per-pixel grain reveal, mimicking Monte-Carlo
// sample accumulation under a fixed tone curve).
"use strict";

// ---------------------------------------------------------------- reveal
const io = new IntersectionObserver(
  (entries) => entries.forEach((e) => e.isIntersecting && e.target.classList.add("visible")),
  { threshold: 0.08 }
);
document.querySelectorAll(".reveal").forEach((el) => io.observe(el));

// --------------------------------------------------- developing photograph
// The hero image "develops" like film: each pixel carries a random threshold
// t in [0,1) (its "arrival time"); at exposure fraction f we show pixels with
// t < f, so structure appears progressively with photographic grain. Honors
// prefers-reduced-motion by skipping straight to fully developed.
(function develop() {
  const img = document.getElementById("develop-photo");
  const hud = document.getElementById("develop-hud");
  if (!img || !img.complete) {
    if (img) img.addEventListener("load", () => develop(), { once: true });
    return;
  }
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) {
    if (hud) hud.textContent = "";
    return;
  }
  const W = 560, H = Math.round(W * img.naturalHeight / img.naturalWidth);
  const src = document.createElement("canvas");
  src.width = W; src.height = H;
  src.getContext("2d").drawImage(img, 0, 0, W, H);
  const base = src.getContext("2d").getImageData(0, 0, W, H);

  const view = document.createElement("canvas");
  view.width = W; view.height = H;
  view.className = img.className;
  view.style.borderRadius = getComputedStyle(img).borderRadius;
  img.replaceWith(view);
  const ctx = view.getContext("2d");
  const out = ctx.createImageData(W, H);

  // deterministic per-pixel arrival times (xorshift hash of index)
  const t = new Float32Array(W * H);
  let seed = 0x9e3779b9;
  for (let i = 0; i < t.length; i++) {
    seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5;
    t[i] = ((seed >>> 0) % 100000) / 100000;
  }

  const DURATION = 7000, START_DELAY = 400;
  const t0 = performance.now() + START_DELAY;
  const lo = [10, 4, 2], hi = [235, 240, 250]; // slight per-channel lift for glow
  function frame(now) {
    const f = Math.min(1, Math.max(0, (now - t0) / DURATION));
    const d = out.data, b = base.data;
    for (let i = 0, p = 0; i < t.length; i++, p += 4) {
      const on = t[i] < f;
      const a = on ? 1 : 0.05;
      d[p]     = b[p]     * a + (on ? lo[0] : 0);
      d[p + 1] = b[p + 1] * a + (on ? lo[1] : 0);
      d[p + 2] = b[p + 2] * a + (on ? lo[2] : 0);
      d[p + 3] = 255;
    }
    ctx.putImageData(out, 0, 0);
    if (hud) hud.textContent = f < 1
      ? `exposure ${(f * 100).toFixed(1)}%  ·  ${(f * 74).toFixed(1)}M of 74M orbits`
      : "";
    if (f < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
