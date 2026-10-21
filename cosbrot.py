#!/usr/bin/env python3
"""Cosbrot — Buddhabrot-style orbit plot for the mutated quadratic update:

    x' = cos(x^2) - y + cx      (mutation: cos of the squared real part, minus y)
    y' = 2*x*y     + cy         (unchanged from z^2 + c)

Escape is judged on |y|: large |x| folds back through cos(x^2) within one
step, while large |y| diverges monotonically, so y is the true exit direction.
The lone -y term breaks the top/bottom mirror symmetry of the classic
Buddhabrot, so the density figure comes out lopsided.

Usage:
    python mutant_brot.py render [--smoke]
"""
from __future__ import annotations

import argparse
import os
import time

import numpy as np
from buddhabrot import build_rgb, load_font

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

CXMIN, CXMAX = -1.2, 1.2   # c sampling window
CYMIN, CYMAX = -1.2, 1.2
XMIN, XMAX = -3.0, 3.0     # orbit plot window
YMIN, YMAX = -3.0, 3.0
RY2 = 100.0 ** 2           # |y| escape threshold squared

CONFIGS = {
    "full": dict(size=2048, channels=(
        ("blue", 60, 18_000_000, 101),
        ("green", 300, 12_000_000, 202),
        ("red", 1000, 8_000_000, 303),
    )),
    "smoke": dict(size=512, channels=(
        ("blue", 60, 1_500_000, 101),
        ("green", 300, 800_000, 202),
        ("red", 1000, 400_000, 303),
    )),
}


def step(x: np.ndarray, y: np.ndarray, cx: np.ndarray, cy: np.ndarray):
    xn = np.cos(x * x) - y + cx
    yn = 2.0 * x * y + cy
    return xn, yn


def gone(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return (y * y > RY2) | ~np.isfinite(x) | ~np.isfinite(y)


def escape_mask(cr, ci, max_iter, chunk=8):
    idx = np.arange(cr.size)
    escaped: list[np.ndarray] = []
    x, y = cr.copy(), ci.copy()
    cx, cy = cr, ci
    it = 0
    while x.size and it < max_iter:
        steps = min(chunk, max_iter - it)
        for _ in range(steps):
            x, y = step(x, y, cx, cy)
        m = gone(x, y)
        if m.any():
            escaped.append(idx[m])
            keep = ~m
            idx = idx[keep]
            x, y = x[keep], y[keep]
            cx, cy = cx[keep], cy[keep]
        it += steps
    mask = np.zeros(cr.shape, dtype=bool)
    if escaped:
        mask[np.concatenate(escaped)] = True
    return mask


def plot_orbits(cr, ci, max_iter, hist, W, H, flush_at=24_000_000):
    sx = W / (XMAX - XMIN)
    sy = H / (YMAX - YMIN)
    x, y = cr.copy(), ci.copy()
    cx, cy = cr, ci
    buf: list[np.ndarray] = []
    buffered = 0
    it = 0
    while x.size and it < max_iter:
        px = ((x - XMIN) * sx).astype(np.int64)
        py = ((y - YMIN) * sy).astype(np.int64)
        inb = (px >= 0) & (px < W) & (py >= 0) & (py < H)
        if inb.any():
            flat = py[inb] * W + px[inb]
            buf.append(flat)
            buffered += flat.size
            if buffered >= flush_at:
                hist += np.bincount(np.concatenate(buf), minlength=W * H)
                buf, buffered = [], 0
        x, y = step(x, y, cx, cy)
        m = gone(x, y)
        if m.any():
            keep = ~m
            x, y = x[keep], y[keep]
            cx, cy = cx[keep], cy[keep]
        it += 1
    if buffered:
        hist += np.bincount(np.concatenate(buf), minlength=W * H)


def render_channel(name, max_iter, samples, seed, size, tag, batch=3_000_000):
    os.makedirs(OUT, exist_ok=True)
    cache = os.path.join(OUT, f"hist_cos_{tag}_{name}.npy")
    if os.path.exists(cache):
        print(f"[{name}] using cache {cache}", flush=True)
        return np.load(cache)
    rng = np.random.default_rng(seed)
    W = H = size
    hist = np.zeros(W * H, dtype=np.float64)
    t0, done = time.time(), 0
    with np.errstate(over="ignore", invalid="ignore"):
        while done < samples:
            n = min(batch, samples - done)
            cr = rng.uniform(CXMIN, CXMAX, n)
            ci = rng.uniform(CYMIN, CYMAX, n)
            esc = escape_mask(cr, ci, max_iter)
            plot_orbits(cr[esc], ci[esc], max_iter, hist, W, H)
            done += n
            print(f"  [{name:<5}] {100.0 * done / samples:5.1f}%   {time.time() - t0:7.1f}s", flush=True)
    hist = hist.reshape(H, W)[::-1]
    np.save(cache, hist)
    return hist


def make_poster(rgb_u8, path, total_orbits):
    from PIL import Image, ImageDraw
    img = Image.fromarray(rgb_u8)
    s = img.width
    m = int(s * 0.055)
    Wc = s + 2 * m
    Hc = m + s + int(s * 0.22)
    canvas = Image.new("RGB", (Wc, Hc), (8, 8, 11))
    canvas.paste(img, (m, m))
    d = ImageDraw.Draw(canvas)
    f_title = load_font(int(s * 0.050))
    f_sub = load_font(int(s * 0.021))
    title = "C O S B R O T"
    orbits_txt = f"{total_orbits:,}".replace(",", "\u2009")
    sub = f"x\u2032 = cos x\u00b2 \u2212 y    \u00b7    y\u2032 = 2xy    \u00b7    {orbits_txt} escaping orbits"
    y_line = m + s + int(s * 0.085)
    d.line([(int(Wc * 0.32), y_line), (int(Wc * 0.68), y_line)], fill=(70, 70, 84), width=1)
    y_title = y_line + int(s * 0.035)
    d.text(((Wc - d.textlength(title, font=f_title)) / 2, y_title), title, font=f_title, fill=(225, 223, 218))
    y_sub = y_title + int(s * 0.095)
    d.text(((Wc - d.textlength(sub, font=f_sub)) / 2, y_sub), sub, font=f_sub, fill=(128, 126, 134))
    canvas.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["render", "tone"])
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--plo", type=float, default=30.0)
    ap.add_argument("--pct", type=float, default=99.9)
    ap.add_argument("--gamma", type=float, default=1.35)
    ap.add_argument("--sat", type=float, default=1.15)
    ap.add_argument("--gr", type=float, default=1.15)
    ap.add_argument("--gg", type=float, default=1.05)
    ap.add_argument("--gb", type=float, default=0.90)
    args = ap.parse_args()

    tag = "smoke" if args.smoke else "full"
    cfg = CONFIGS[tag]
    hists = {}
    for name, max_iter, samples, seed in cfg["channels"]:
        print(f"[{name}] cap={max_iter} samples={samples:,}", flush=True)
        hists[name] = render_channel(name, max_iter, samples, seed, cfg["size"], tag)

    gains = {"red": args.gr, "green": args.gg, "blue": args.gb}
    rgb = build_rgb(hists, args.plo, args.pct, args.gamma, gains, args.sat)
    u8 = (rgb * 255.0 + 0.5).astype(np.uint8)
    suffix = "" if tag == "full" else f"_{tag}"
    from PIL import Image
    main_path = os.path.join(OUT, f"cosbrot{suffix}.png")
    Image.fromarray(u8).save(main_path, optimize=True)
    make_poster(u8, os.path.join(OUT, f"cosbrot{suffix}_poster.png"), sum(c[2] for c in cfg["channels"]))
    print("wrote", main_path, flush=True)


if __name__ == "__main__":
    main()
