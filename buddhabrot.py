#!/usr/bin/env python3
"""Buddhabrot fractal renderer — vectorised numpy, two-phase orbit plotting.

Phase 1 classifies each random sample c as escaping / non-escaping within the
channel's iteration cap. Phase 2 replays only the escaping orbits and drops
every visited point into a 2-D histogram. Three histograms with different caps
become the R/G/B channels (deep orbits glow red, shallow ones blue).

Usage:
    python buddhabrot.py render [--smoke]
    python buddhabrot.py tone [--pct 99.9] [--gamma 1.05] [--sat 1.15]
                              [--gr 1.0] [--gg 1.0] [--gb 1.0]
"""
from __future__ import annotations

import argparse
import os
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

# complex-plane window (square)
XMIN, XMAX = -2.25, 1.15
YMIN, YMAX = -1.70, 1.70

CONFIGS = {
    "full": dict(size=2048, channels=(
        ("blue", 80, 36_000_000, 11),
        ("green", 400, 24_000_000, 22),
        ("red", 1500, 14_000_000, 33),
    )),
    "smoke": dict(size=512, channels=(
        ("blue", 60, 2_000_000, 11),
        ("green", 200, 1_200_000, 22),
        ("red", 500, 600_000, 33),
    )),
}


def inside_main_sets(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Analytic interior of the main cardioid and the period-2 bulb.

    Points in there provably never escape, so they are dropped before the
    expensive iteration — they would contribute nothing to a Buddhabrot.
    """
    u = x - 0.25
    q = u * u + y * y
    cardioid = q * (q + u) < 0.25 * y * y
    bulb = (x + 1.0) ** 2 + y * y < 0.0625
    return cardioid | bulb


def escape_mask(cr: np.ndarray, ci: np.ndarray, max_iter: int, chunk: int = 32) -> np.ndarray:
    """True where the orbit of c escapes (|z|^2 > 4) within max_iter.

    Compacts the still-alive arrays every `chunk` steps so the shrinkage from
    early escapees keeps the working set small.
    """
    idx = np.arange(cr.size)
    escaped: list[np.ndarray] = []
    zr, zi = cr.copy(), ci.copy()
    cr_w, ci_w = cr, ci
    it = 0
    while zr.size and it < max_iter:
        steps = min(chunk, max_iter - it)
        for _ in range(steps):
            t = zr * zr - zi * zi + cr_w
            zi = 2.0 * zr * zi + ci_w
            zr = t
        r2 = zr * zr + zi * zi
        m = (r2 > 4.0) | np.isnan(r2)  # nan = overflowed past an earlier >4
        if m.any():
            escaped.append(idx[m])
            keep = ~m
            idx = idx[keep]
            zr, zi = zr[keep], zi[keep]
            cr_w, ci_w = cr_w[keep], ci_w[keep]
        it += steps
    mask = np.zeros(cr.shape, dtype=bool)
    if escaped:
        mask[np.concatenate(escaped)] = True
    return mask


def plot_orbits(cr: np.ndarray, ci: np.ndarray, max_iter: int,
                hist: np.ndarray, W: int, H: int, flush_at: int = 24_000_000) -> None:
    """Histogram every pre-escape orbit point of the given escaping samples."""
    sx = W / (XMAX - XMIN)
    sy = H / (YMAX - YMIN)
    zr, zi = cr.copy(), ci.copy()  # z1 = c
    cr_w, ci_w = cr, ci
    buf: list[np.ndarray] = []
    buffered = 0
    it = 0
    while zr.size and it < max_iter:
        px = ((zr - XMIN) * sx).astype(np.int64)
        py = ((zi - YMIN) * sy).astype(np.int64)
        inb = (px >= 0) & (px < W) & (py >= 0) & (py < H)
        if inb.any():
            flat = py[inb] * W + px[inb]
            buf.append(flat)
            buffered += flat.size
            if buffered >= flush_at:
                hist += np.bincount(np.concatenate(buf), minlength=W * H)
                buf, buffered = [], 0
        t = zr * zr - zi * zi + cr_w
        zi = 2.0 * zr * zi + ci_w
        zr = t
        r2 = zr * zr + zi * zi
        m = (r2 > 4.0) | np.isnan(r2)
        if m.any():
            keep = ~m
            zr, zi = zr[keep], zi[keep]
            cr_w, ci_w = cr_w[keep], ci_w[keep]
        it += 1
    if buffered:
        hist += np.bincount(np.concatenate(buf), minlength=W * H)


def render_channel(name: str, max_iter: int, samples: int, seed: int,
                   size: int, tag: str, batch: int = 3_000_000) -> np.ndarray:
    os.makedirs(OUT, exist_ok=True)
    cache = os.path.join(OUT, f"hist_{tag}_{name}.npy")
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
            cr = rng.uniform(XMIN, XMAX, n)
            ci = rng.uniform(YMIN, YMAX, n)
            keep = ~inside_main_sets(cr, ci)
            cr, ci = cr[keep], ci[keep]
            esc = escape_mask(cr, ci, max_iter)
            plot_orbits(cr[esc], ci[esc], max_iter, hist, W, H)
            done += n
            print(f"  [{name:<5}] {100.0 * done / samples:5.1f}%   {time.time() - t0:7.1f}s", flush=True)
    hist = hist.reshape(H, W)[::-1]  # +imag up
    np.save(cache, hist)
    return hist


def tone_channel(h: np.ndarray, plo: float, phi: float, gamma: float, gain: float) -> np.ndarray:
    """Log-compress, anchor a black point at the plo-th percentile of lit pixels
    and a white point at the phi-th one, then gamma-shape what's in between."""
    v = np.log1p(h)
    pos = v[v > 0]
    lo, hi = (np.percentile(pos, plo), np.percentile(pos, phi)) if pos.size else (0.0, 1.0)
    return np.clip((v - lo) * gain / max(hi - lo, 1e-12), 0.0, 1.0) ** gamma


def build_rgb(hists: dict, plo: float, phi: float, gamma: float, gains: dict, sat: float) -> np.ndarray:
    rgb = np.stack([tone_channel(hists[k], plo, phi, gamma, gains[k])
                    for k in ("red", "green", "blue")], axis=2)
    if sat != 1.0:  # vibrance: push away from luminance
        lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
        rgb = np.clip(lum[..., None] + sat * (rgb - lum[..., None]), 0.0, 1.0)
    return rgb


def load_font(size: int, fonts_dir=None):
    """Best-effort UI font; fonts_dir injectable for tests and odd platforms."""
    from PIL import ImageFont
    if fonts_dir is None:
        fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for name in ("segoeuil.ttf", "segoeui.ttf", "arial.ttf"):
        path = os.path.join(fonts_dir, name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def make_poster(rgb_u8: np.ndarray, path: str, total_orbits: int) -> None:
    from PIL import Image, ImageDraw
    img = Image.fromarray(rgb_u8)
    s = img.width
    m = int(s * 0.055)
    Wc = s + 2 * m
    Hc = m + s + int(s * 0.22)
    canvas = Image.new("RGB", (Wc, Hc), (8, 8, 11))
    canvas.paste(img, (m, m))
    d = ImageDraw.Draw(canvas)
    f_title = load_font(max(1, int(s * 0.050)))
    f_sub = load_font(max(1, int(s * 0.021)))
    title = "B U D D H A B R O T"
    orbits_txt = f"{total_orbits:,}".replace(",", "\u2009")
    sub = f"z \u21a6 z\u00b2 + c    \u00b7    {orbits_txt} escaping orbits"
    y_line = m + s + int(s * 0.085)
    d.line([(int(Wc * 0.32), y_line), (int(Wc * 0.68), y_line)], fill=(70, 70, 84), width=1)
    y_title = y_line + int(s * 0.035)
    d.text(((Wc - d.textlength(title, font=f_title)) / 2, y_title),
           title, font=f_title, fill=(225, 223, 218))
    y_sub = y_title + int(s * 0.095)
    d.text(((Wc - d.textlength(sub, font=f_sub)) / 2, y_sub),
           sub, font=f_sub, fill=(128, 126, 134))
    canvas.save(path)


def save_outputs(hists: dict, tag: str, args) -> str:
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    gains = {"red": args.gr, "green": args.gg, "blue": args.gb}
    rgb = build_rgb(hists, args.plo, args.pct, args.gamma, gains, args.sat)
    u8 = (rgb * 255.0 + 0.5).astype(np.uint8)
    suffix = "" if tag == "full" else f"_{tag}"
    main_path = os.path.join(OUT, f"buddhabrot{suffix}.png")
    Image.fromarray(u8).save(main_path, optimize=True)
    total = sum(c[2] for c in CONFIGS[tag]["channels"])
    make_poster(u8, os.path.join(OUT, f"buddhabrot{suffix}_poster.png"), total)
    return main_path


def main() -> None:
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
    path = save_outputs(hists, tag, args)
    print("wrote", path, flush=True)


if __name__ == "__main__":  # pragma: no cover
    main()
