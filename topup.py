#!/usr/bin/env python3
"""Top-up sparse brot histograms: crop canvas to the figure + add samples.

Usage: python topup.py NAME CROP_PX EXTRA_BLUE EXTRA_GREEN EXTRA_RED
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("farm", os.path.join(HERE, "brot_farm.py"))
farm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(farm)


def topup(name: str, crop_px: int, extra: list[int]):
    f = farm.BY_NAME[name]
    W0, H0 = f["size"]
    W = H = crop_px
    mx, my = (W0 - W) // 2, (H0 - H) // 2
    x0, x1, y0, y1 = f["plot"]
    ux, uy = (x1 - x0) / W0, (y1 - y0) / H0
    f["plot"] = f["samp"] = (x0 + mx * ux, x0 + (mx + W) * ux,
                             y0 + my * uy, y0 + (my + H) * uy)
    f["size"] = (W, H)
    print(f"[{name}] crop -> {W}x{H}, window {f['plot']}", flush=True)
    seed_base = sum(ord(ch) for ch in name) * 13
    for ci, add in enumerate(extra):
        if add <= 0:
            continue
        cap = f["chans"][ci][0]
        cache = os.path.join(HERE, "out", f"hist_{name}_{ci}.npy")
        hist2d = np.load(cache)
        if hist2d.shape == (H0, W0):
            hist = hist2d[::-1][my:my + H, mx:mx + W].ravel().copy()
        elif hist2d.shape == (H, W):
            hist = hist2d[::-1].ravel().copy()  # already cropped by an earlier top-up
        else:
            raise AssertionError(f"unexpected cached shape {hist2d.shape}")
        rng = np.random.default_rng(7777 + seed_base + ci)
        t0, done = time.time(), 0
        with np.errstate(over="ignore", invalid="ignore"):
            while done < add:
                n = min(f["batch"], add - done)
                ax = rng.uniform(f["samp"][0], f["samp"][1], n)
                ay = rng.uniform(f["samp"][2], f["samp"][3], n)
                if f["julia"] is not None:
                    cx = np.full(n, f["julia"][0])
                    cy = np.full(n, f["julia"][1])
                else:
                    cx, cy = ax, ay
                if f["cull"]:
                    keep = ~farm.inside_main_sets(cx, cy)
                    ax, ay, cx, cy = ax[keep], ay[keep], cx[keep], cy[keep]
                esc = farm.escape_mask(f, ax, ay, cx, cy, cap)
                sel = ~esc if f["invert"] else esc
                ax, ay, cx, cy = ax[sel], ay[sel], cx[sel], cy[sel]
                if f["julia"] is not None:
                    ax, ay = f["step"](ax, ay, cx, cy)
                farm.plot_orbits(f, ax, ay, cx, cy, cap, hist, W, H)
                done += n
                print(f"  [{name}.{farm.CHAN_NAMES[ci]:<5}] +{100.0 * done / add:5.1f}%  {time.time() - t0:7.1f}s", flush=True)
        np.save(cache, hist.reshape(H, W)[::-1])
    print(f"[{name}] top-up done", flush=True)


if __name__ == "__main__":
    name = sys.argv[1]
    crop_px = int(sys.argv[2])
    extra = [int(v) for v in sys.argv[3:6]]
    topup(name, crop_px, extra)
