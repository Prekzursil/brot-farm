#!/usr/bin/env python3
"""Brot farm — one generalized two-phase orbit-density renderer, many maps.

Each fractal is a config: a step rule (x,y,cx,cy)->(x',y'), an escape
predicate, sample/plot windows, and per-channel (iteration-cap, samples)
budgets. Phase 1 classifies samples as escaping or not; phase 2 replays the
chosen subset (escaped, or non-escaped for the anti-brot) and histograms
every orbit point. Three channels at different caps -> R/G/B.

Usage:
    python brot_farm.py --shard 0 --shards 4   # render this shard's fractals
    python brot_farm.py --list
    python brot_farm.py qc                     # stats table over all outputs
    python brot_farm.py tone NAME [--plo .. --pct .. --gamma .. --sat .. --gr/gg/gb ..]
"""

from __future__ import annotations

import argparse
import os
import time
from typing import Any

import numpy as np
from buddhabrot import build_rgb, load_font, inside_main_sets

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

# ---------------------------------------------------------------- step rules


def s_std(x, y, cx, cy):
    return x * x - y * y + cx, 2.0 * x * y + cy


def s_z3(x, y, cx, cy):
    return x**3 - 3 * x * y * y + cx, 3 * x * x * y - y**3 + cy


def s_z4(x, y, cx, cy):
    return x**4 - 6 * x * x * y * y + y**4 + cx, 4 * x * y * (x * x - y * y) + cy


def s_z5(x, y, cx, cy):
    return (
        x**5 - 10 * x**3 * y * y + 5 * x * y**4 + cx,
        5 * x**4 * y - 10 * x * x * y**3 + y**5 + cy,
    )


def s_ship(x, y, cx, cy):
    return x * x - y * y + cx, np.abs(2.0 * x * y) + cy


def s_tricorn(x, y, cx, cy):
    return x * x - y * y + cx, -2.0 * x * y + cy


def s_celtic(x, y, cx, cy):
    return np.abs(x * x - y * y) + cx, 2.0 * x * y + cy


def s_buffalo(x, y, cx, cy):
    return np.abs(x * x - y * y) + cx, np.abs(2.0 * x * y) + cy


def s_sinz(x, y, cx, cy):
    return np.sin(x) * np.cosh(y) + cx, np.cos(x) * np.sinh(y) + cy


def s_cosz(x, y, cx, cy):
    return np.cos(x) * np.cosh(y) + cx, -np.sin(x) * np.sinh(y) + cy


def s_tanmut(x, y, cx, cy):
    return np.tan(x * x) - y + cx, 2.0 * x * y + cy


def s_sinhmut(x, y, cx, cy):
    return np.sinh(x * x) - y + cx, 2.0 * x * y + cy


def s_expmut(x, y, cx, cy):
    return np.exp(x * x) - y + cx, 2.0 * x * y + cy


def s_cosfull(x, y, cx, cy):
    return np.cos(x * x - y * y) + cx, 2.0 * x * y + cy


def s_cosy(x, y, cx, cy):
    return x * x - y * y + cx, np.cos(2.0 * x * y) + cy


# ------------------------------------------------------------- escape tests


def g_z(x, y):
    r = x * x + y * y
    # NaN guard: a diverged orbit can overflow to NaN before the next chunked
    # check; NaN comparisons are False, so without this the point would be
    # misclassified as a prisoner forever.
    return (r > 4.0) | ~np.isfinite(r)


def g_big(x, y):
    r = x * x + y * y
    return (r > 1e6) | ~np.isfinite(r)


def g_y(x, y):
    return (y * y > 1e4) | ~np.isfinite(x) | ~np.isfinite(y)


def g_x(x, y):
    return (x * x > 1e4) | ~np.isfinite(x) | ~np.isfinite(y)


def F(
    name,
    title,
    sub,
    step,
    gone,
    chunk,
    *,
    cull=False,
    invert=False,
    julia=None,
    samp,
    plot,
    size=(2048, 2048),
    chans,
    batch=3_000_000,
) -> dict[str, Any]:
    """Build one map config. Values are deliberately heterogeneous (callables,
    windows, flags), so the value type is Any by design."""
    return dict(
        name=name,
        title=title,
        sub=sub,
        step=step,
        gone=gone,
        chunk=chunk,
        cull=cull,
        invert=invert,
        julia=julia,
        samp=samp,
        plot=plot,
        size=size,
        chans=chans,
        batch=batch,
    )


CH_QUAD = ((80, 14_000_000), (400, 9_000_000), (1200, 6_000_000))
CH_POWER = ((80, 12_000_000), (400, 8_000_000), (1200, 5_000_000))
CH_MUT = ((60, 16_000_000), (300, 10_000_000), (1000, 7_000_000))

FRACS = [
    F(
        "nebula",
        "N E B U L A B R O T",
        "iteration caps 50 / 500 / 5000 \u00b7 z \u21a6 z\u00b2 + c",
        s_std,
        g_z,
        32,
        cull=True,
        samp=(-2.25, 1.15, -1.7, 1.7),
        plot=(-2.25, 1.15, -1.7, 1.7),
        chans=((50, 20_000_000), (500, 10_000_000), (5000, 5_000_000)),
    ),
    F(
        "anti",
        "A N T I B U D D H A B R O T",
        "orbits of points that never escape \u00b7 z \u21a6 z\u00b2 + c",
        s_std,
        g_z,
        32,
        invert=True,
        samp=(-2.25, 1.15, -1.7, 1.7),
        plot=(-2.25, 1.15, -1.7, 1.7),
        chans=((100, 5_000_000), (500, 3_500_000), (1500, 2_500_000)),
    ),
    F(
        "cosfull",
        "C O S F U L L B R O T",
        "x\u2032 = cos(x\u00b2 \u2212 y\u00b2) \u00b7 y\u2032 = 2xy",
        s_cosfull,
        g_y,
        8,
        samp=(-1, 1, -1, 1),
        plot=(-2.5, 2.5, -8, 8),
        size=(640, 2048),
        chans=((100, 10_000_000), (400, 7_000_000), (1500, 5_000_000)),
    ),
    F(
        "z3",
        "C U B I C B R O T",
        "z \u21a6 z\u00b3 + c",
        s_z3,
        g_z,
        32,
        samp=(-1.6, 1.6, -1.6, 1.6),
        plot=(-1.6, 1.6, -1.6, 1.6),
        chans=CH_POWER,
    ),
    F(
        "julia",
        "J U L I A B R O T",
        "orbit density through the Julia set \u00b7 c = \u22120.7 + 0.27i",
        s_std,
        g_z,
        32,
        julia=(-0.7, 0.27),
        samp=(-1.8, 1.8, -1.8, 1.8),
        plot=(-1.8, 1.8, -1.8, 1.8),
        chans=((30, 16_000_000), (100, 11_000_000), (300, 8_000_000)),
    ),
    F(
        "sinz",
        "S I N B R O T",
        "z \u21a6 sin z + c",
        s_sinz,
        g_big,
        8,
        samp=(-2, 2, -2, 2),
        plot=(-3.5, 3.5, -1.8, 1.8),
        size=(2048, 1050),
        chans=((60, 14_000_000), (250, 9_000_000), (800, 6_000_000)),
    ),
    F(
        "tanmut",
        "T A N B R O T",
        "x\u2032 = tan x\u00b2 \u2212 y \u00b7 y\u2032 = 2xy",
        s_tanmut,
        g_y,
        8,
        samp=(-1, 1, -1, 1),
        plot=(-1.6, 2.4, -2.4, 1.6),
        chans=CH_MUT,
    ),
    F(
        "z4",
        "Q U A R T I C B R O T",
        "z \u21a6 z\u2074 + c",
        s_z4,
        g_z,
        32,
        samp=(-1.45, 1.45, -1.45, 1.45),
        plot=(-1.45, 1.45, -1.45, 1.45),
        chans=CH_POWER,
    ),
    F(
        "cosz",
        "C O S B R O T",
        "z \u21a6 cos z + c",
        s_cosz,
        g_big,
        8,
        samp=(-2, 2, -2, 2),
        plot=(-4, 4, -2.2, 2.2),
        size=(2048, 1126),
        chans=((60, 14_000_000), (250, 9_000_000), (800, 6_000_000)),
    ),
    F(
        "ship",
        "B U R N I N G S H I P B R O T",
        "z \u21a6 (|Re z| + i|Im z|)\u00b2 + c",
        s_ship,
        g_z,
        32,
        samp=(-2.2, 1.2, -1.8, 1.8),
        plot=(-2.2, 1.2, -1.8, 1.8),
        chans=CH_QUAD,
    ),
    F(
        "sinhmut",
        "S I N H B R O T",
        "x\u2032 = sinh x\u00b2 \u2212 y \u00b7 y\u2032 = 2xy",
        s_sinhmut,
        g_y,
        8,
        samp=(-1, 1, -1, 1),
        plot=(-1.6, 2.2, -1.8, 1.3),
        chans=((40, 18_000_000), (200, 12_000_000), (600, 8_000_000)),
    ),
    F(
        "z5",
        "Q U I N T I C B R O T",
        "z \u21a6 z\u2075 + c",
        s_z5,
        g_z,
        32,
        samp=(-1.35, 1.35, -1.35, 1.35),
        plot=(-1.35, 1.35, -1.35, 1.35),
        chans=CH_POWER,
    ),
    F(
        "tricorn",
        "T R I C O R N B R O T",
        "z \u21a6 z\u0304\u00b2 + c",
        s_tricorn,
        g_z,
        32,
        samp=(-2.1, 2.1, -1.8, 1.8),
        plot=(-2.1, 2.1, -1.8, 1.8),
        chans=CH_QUAD,
    ),
    F(
        "celtic",
        "C E L T I C B R O T",
        "x\u2032 = |x\u00b2 \u2212 y\u00b2| \u00b7 y\u2032 = 2xy",
        s_celtic,
        g_z,
        32,
        samp=(-2.2, 1.0, -1.6, 1.6),
        plot=(-2.2, 1.0, -1.6, 1.6),
        chans=CH_QUAD,
    ),
    F(
        "cosy",
        "C O S Y B R O T",
        "x\u2032 = x\u00b2 \u2212 y\u00b2 \u00b7 y\u2032 = cos 2xy",
        s_cosy,
        g_x,
        8,
        samp=(-1, 1, -1, 1),
        plot=(-2.5, 2.5, -2.5, 2.5),
        chans=CH_MUT,
    ),
    F(
        "buffalo",
        "B U F F A L O B R O T",
        "x\u2032 = |x\u00b2 \u2212 y\u00b2| \u00b7 y\u2032 = |2xy|",
        s_buffalo,
        g_z,
        32,
        samp=(-2.2, 1.0, -1.9, 1.9),
        plot=(-2.2, 1.0, -1.9, 1.9),
        chans=CH_QUAD,
    ),
    F(
        "expmut",
        "E X P B R O T",
        "x\u2032 = exp x\u00b2 \u2212 y \u00b7 y\u2032 = 2xy",
        s_expmut,
        g_y,
        8,
        samp=(-0.5, 0.5, -0.5, 0.5),
        plot=(-2, 2, -2, 2),
        chans=((5, 24_000_000), (15, 14_000_000), (40, 8_000_000)),
    ),
]
BY_NAME = {f["name"]: f for f in FRACS}
CHAN_NAMES = ("blue", "green", "red")

# ----------------------------------------------------------------- machinery


def escape_mask(f, x0, y0, cx, cy, max_iter):
    step, gone, chunk = f["step"], f["gone"], f["chunk"]
    idx = np.arange(x0.size)
    out: list[np.ndarray] = []
    x, y = x0.copy(), y0.copy()
    it = 0
    while x.size and it < max_iter:
        s = min(chunk, max_iter - it)
        for _ in range(s):
            x, y = step(x, y, cx, cy)
        m = gone(x, y)
        if m.any():
            out.append(idx[m])
            keep = ~m
            idx, x, y, cx, cy = idx[keep], x[keep], y[keep], cx[keep], cy[keep]
        it += s
    mask = np.zeros(x0.shape, dtype=bool)
    if out:
        mask[np.concatenate(out)] = True
    return mask


def plot_orbits(f, xi, yi, cx, cy, max_iter, hist, W, H, flush_at=24_000_000):
    step, gone = f["step"], f["gone"]
    px0, px1, py0, py1 = f["plot"]
    sx = W / (px1 - px0)
    sy = H / (py1 - py0)
    x, y = xi.copy(), yi.copy()
    buf: list[np.ndarray] = []
    buffered = 0
    it = 0
    while x.size and it < max_iter:
        col = ((x - px0) * sx).astype(np.int64)
        row = ((y - py0) * sy).astype(np.int64)
        inb = (col >= 0) & (col < W) & (row >= 0) & (row < H)
        if inb.any():
            flat = row[inb] * W + col[inb]
            buf.append(flat)
            buffered += flat.size
            if buffered >= flush_at:
                hist += np.bincount(np.concatenate(buf), minlength=W * H)
                buf, buffered = [], 0
        x, y = step(x, y, cx, cy)
        m = gone(x, y)
        if m.any():
            keep = ~m
            x, y, cx, cy = x[keep], y[keep], cx[keep], cy[keep]
        it += 1
    if buffered:
        hist += np.bincount(np.concatenate(buf), minlength=W * H)


def render_fractal(f, force=False):
    name = f["name"]
    out_png = os.path.join(OUT, f"brot_{name}.png")
    if os.path.exists(out_png) and not force:
        print(f"[{name}] already rendered, skipping", flush=True)
        return
    W, H = f["size"]
    hists = {}
    for ci, (cap, samples) in enumerate(f["chans"]):
        cname = CHAN_NAMES[ci]
        cache = os.path.join(OUT, f"hist_{name}_{ci}.npy")
        if os.path.exists(cache) and not force:
            print(f"[{name}.{cname}] cached", flush=True)
            hists[cname] = np.load(cache)
            continue
        rng = np.random.default_rng(1000 + FRACS.index(f) * 31 + ci * 7)
        hist = np.zeros(W * H, dtype=np.float64)
        sx0, sx1, sy0, sy1 = f["samp"]
        t0, done = time.time(), 0
        with np.errstate(over="ignore", invalid="ignore"):
            while done < samples:
                n = min(f["batch"], samples - done)
                ax = rng.uniform(sx0, sx1, n)
                ay = rng.uniform(sy0, sy1, n)
                if f["julia"] is not None:
                    cx = np.full(n, f["julia"][0])
                    cy = np.full(n, f["julia"][1])
                else:
                    cx, cy = ax, ay  # parameter-space sampling: orbit starts at z1 = c
                if f["cull"]:
                    keep = ~inside_main_sets(cx, cy)
                    ax, ay, cx, cy = ax[keep], ay[keep], cx[keep], cy[keep]
                esc = escape_mask(f, ax, ay, cx, cy, cap)
                sel = ~esc if f["invert"] else esc
                ax, ay, cx, cy = ax[sel], ay[sel], cx[sel], cy[sel]
                if f["julia"] is not None:
                    ax, ay = f["step"](ax, ay, cx, cy)  # plot from z1 = z0^2 + c
                plot_orbits(f, ax, ay, cx, cy, cap, hist, W, H)
                done += n
                print(
                    f"  [{name}.{cname:<5}] {100.0 * done / samples:5.1f}%  {time.time() - t0:7.1f}s",
                    flush=True,
                )
        hist = hist.reshape(H, W)[::-1]
        np.save(cache, hist)
        hists[cname] = hist
    write_outputs(f, hists)


def write_outputs(f, hists, args=None):
    from PIL import Image

    os.makedirs(OUT, exist_ok=True)
    plo = args.plo if args else 30.0
    pct = args.pct if args else 99.9
    gamma = args.gamma if args else 1.35
    sat = args.sat if args else 1.15
    gains = {
        "red": args.gr if args else 1.15,
        "green": args.gg if args else 1.05,
        "blue": args.gb if args else 0.90,
    }
    rgb = build_rgb(hists, plo, pct, gamma, gains, sat)
    u8 = (rgb * 255.0 + 0.5).astype(np.uint8)
    out_png = os.path.join(OUT, f"brot_{f['name']}.png")
    Image.fromarray(u8).save(out_png, optimize=True)
    total = sum(c[1] for c in f["chans"])
    orbits_txt = f"{total:,}".replace(",", "\u2009")
    make_poster(
        u8,
        os.path.join(OUT, f"brot_{f['name']}_poster.png"),
        f["title"],
        f"{f['sub']} \u00b7 {orbits_txt} orbits",
    )
    print(f"[{f['name']}] wrote {out_png}", flush=True)


def make_poster(rgb_u8, path, title, sub):
    from PIL import Image, ImageDraw

    img = Image.fromarray(rgb_u8)
    w, h = img.size
    m = int(min(w, h) * 0.06)
    block = int(min(w, h) * 0.24)
    Wc, Hc = w + 2 * m, m + h + block
    canvas = Image.new("RGB", (Wc, Hc), (8, 8, 11))
    canvas.paste(img, (m, m))
    d = ImageDraw.Draw(canvas)
    ft = load_font(max(1, int(min(w, h) * 0.042)))
    fs = load_font(max(1, int(min(w, h) * 0.020)))
    y_line = m + h + int(block * 0.38)
    d.line(
        [(int(Wc * 0.32), y_line), (int(Wc * 0.68), y_line)], fill=(70, 70, 84), width=1
    )
    d.text(
        ((Wc - d.textlength(title, font=ft)) / 2, y_line + int(block * 0.14)),
        title,
        font=ft,
        fill=(225, 223, 218),
    )
    d.text(
        ((Wc - d.textlength(sub, font=fs)) / 2, y_line + int(block * 0.62)),
        sub,
        font=fs,
        fill=(128, 126, 134),
    )
    canvas.save(path)


# ---------------------------------------------------------------------- CLI


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument(
        "cmd", nargs="?", default="render", choices=["render", "qc", "tone"]
    )
    ap.add_argument("target", nargs="?")
    ap.add_argument("--plo", type=float, default=30.0)
    ap.add_argument("--pct", type=float, default=99.9)
    ap.add_argument("--gamma", type=float, default=1.35)
    ap.add_argument("--sat", type=float, default=1.15)
    ap.add_argument("--gr", type=float, default=1.15)
    ap.add_argument("--gg", type=float, default=1.05)
    ap.add_argument("--gb", type=float, default=0.90)
    args = ap.parse_args()

    if args.list:
        for i, f in enumerate(FRACS):
            print(f"{i:2d} {f['name']:<9} {f['size']}  caps/samples={f['chans']}")
        return

    if args.cmd == "render":
        todo = [f for i, f in enumerate(FRACS) if i % args.shards == args.shard]
        print(
            f"shard {args.shard}/{args.shards}: {[f['name'] for f in todo]}", flush=True
        )
        for f in todo:
            print(f"[{f['name']}] start", flush=True)
            render_fractal(f, force=args.force)
        return

    if args.cmd == "tone":
        f = BY_NAME[args.target]
        hists = {}
        for ci, cname in enumerate(CHAN_NAMES):
            hists[cname] = np.load(os.path.join(OUT, f"hist_{f['name']}_{ci}.npy"))
        write_outputs(f, hists, args)
        return

    # args.cmd == "qc" is the remaining choice (argparse guarantees it;
    # the render/tone branches above both return).
    from PIL import Image

    print(
        f"{'name':<9} {'size':<11} {'mean':>5} {'vis%':>4} {'sym':>5} {'com_x':>5} {'com_y':>5}"
    )
    for f in FRACS:
        p = os.path.join(OUT, f"brot_{f['name']}.png")
        if not os.path.exists(p):
            print(f"{f['name']:<9} MISSING")
            continue
        a = np.asarray(Image.open(p)).astype(float) / 255.0
        lum = a.mean(axis=2)
        H, W = lum.shape
        top, bot = lum[: H // 2], lum[H // 2 :][::-1]
        sym = np.corrcoef(top.ravel(), bot.ravel())[0, 1]
        ys, xs = np.mgrid[0:H, 0:W]
        wgt = np.where(lum > 0.15, lum, 0)
        comx = (wgt * xs).sum() / max(wgt.sum(), 1e-9) / W
        comy = (wgt * ys).sum() / max(wgt.sum(), 1e-9) / H
        print(
            f"{f['name']:<9} {W}x{H:<7} {lum.mean():5.3f} {100 * (lum > 0.05).mean():3.0f} {sym:5.2f} {comx:5.2f} {comy:5.2f}"
        )


if __name__ == "__main__":  # pragma: no cover
    main()
