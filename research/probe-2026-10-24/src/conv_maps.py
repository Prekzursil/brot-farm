"""Map adapters for the convergence study — one uniform interface over the
subject repo's three representative maps.

Subject repo: brot-farm @
C:/Users/Prekzursil/.zcode/workspace/draft-56daea68-c3bd-4ae2-9987-e036cc496291/brot-farm

Maps (chosen per the ask: "mandel classic, z3 power, cosmut mutation"):
  mandel : buddhabrot.py  z <- z^2 + c, escape |z|^2>4, cull=inside_main_sets,
           sample frame == plot frame == [-2.25,1.15]x[-1.70,1.70]
           (buddhabrot.py:28-29)
  z3     : brot_farm.py  s_z3 (brot_farm.py:37-38), g_z (:99-104), chunk 32,
           frame (-1.6,1.6)^2, no analytic cull (FRACS "z3" entry, :198-208)
  cosmut : cosbrot.py    x' = cos(x^2)-y+cx, y' = 2xy+cy (cosbrot.py:55-58),
           escape |y|>100 (cosbrot.py:33,61-62), chunk 8,
           c-sample (-1.2,1.2)^2, plot window (-3,3)^2 (cosbrot.py:29-32)

Where a kernel already exists in the repo (escape_mask, plot_orbits per map
module) the adapter calls it directly; only escape_times / trace_orbits (which
brot_samplers.py provides for the mandel map only) are re-implemented
map-generically in conv_samplers.py, mirroring brot_samplers.py line-for-line.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Callable

import numpy as np

REPO = os.environ.get(
    "BROT_FARM_REPO",
    r"C:\Users\Prekzursil\.zcode\workspace"
    r"\draft-56daea68-c3bd-4ae2-9987-e036cc496291\brot-farm",
)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import buddhabrot as bb  # noqa: E402
import brot_farm as bf  # noqa: E402
import cosbrot as cb  # noqa: E402


def _s_std(x, y, cx, cy):
    # identical arithmetic to buddhabrot.escape_mask's inline step
    # (t = zr*zr - zi*zi + cr_w; zi = 2.0*zr*zi + ci_w; zr = t)
    return x * x - y * y + cx, 2.0 * x * y + cy


def _g_std_exact(zr, zi):
    # brot_samplers.escape_times / trace_orbits escape predicate, verbatim:
    # m = (r2 > 4.0) | np.isnan(r2), r2 = zr*zr + zi*zi
    r2 = zr * zr + zi * zi
    return (r2 > 4.0) | np.isnan(r2)


def _g_z3(zr, zi):
    return bf.g_z(zr, zi)


def _g_cosmut(zr, zi):
    return cb.gone(zr, zi)


def _s_z3(x, y, cx, cy):
    return bf.s_z3(x, y, cx, cy)


def _s_cosmut(x, y, cx, cy):
    return cb.step(x, y, cx, cy)


def _wrap_farm(f: dict[str, Any]) -> dict[str, Any]:
    def escape_mask(cr, ci, max_iter):
        return bf.escape_mask(f, cr, ci, cr, ci, max_iter)

    def plot_orbits(cr, ci, max_iter, hist, W, H):
        bf.plot_orbits(f, cr, ci, cr, ci, max_iter, hist, W, H)

    return {"escape_mask": escape_mask, "plot_orbits": plot_orbits}


Z3 = bf.BY_NAME["z3"]

MAPS: dict[str, dict[str, Any]] = {
    "mandel": {
        "repo_module": "buddhabrot.py",
        "step": _s_std,
        "gone_trace": _g_std_exact,  # bit-exact vs brot_samplers
        "chunk": 32,  # buddhabrot.escape_mask default
        "samp": (bb.XMIN, bb.XMAX, bb.YMIN, bb.YMAX),
        "plot": (bb.XMIN, bb.XMAX, bb.YMIN, bb.YMAX),
        "cull": bb.inside_main_sets,
        "escape_mask": bb.escape_mask,
        "plot_orbits": bb.plot_orbits,
    },
    "z3": {
        "repo_module": "brot_farm.py FRACS['z3']",
        "step": _s_z3,
        "gone_trace": _g_z3,
        "chunk": Z3["chunk"],
        "samp": Z3["samp"],
        "plot": Z3["plot"],
        "cull": None,
        **_wrap_farm(Z3),
    },
    "cosmut": {
        "repo_module": "cosbrot.py",
        "step": _s_cosmut,
        "gone_trace": _g_cosmut,
        "chunk": cb.escape_mask.__defaults__[0],  # 8
        "samp": (cb.CXMIN, cb.CXMAX, cb.CYMIN, cb.CYMAX),
        "plot": (cb.XMIN, cb.XMAX, cb.YMIN, cb.YMAX),
        "cull": None,
        "escape_mask": cb.escape_mask,
        "plot_orbits": cb.plot_orbits,
    },
}

MAP_IDS = {name: i for i, name in enumerate(sorted(MAPS))}
CAPS = (80, 400, 1500)
CAP_IDS = {c: i for i, c in enumerate(CAPS)}


def get(name: str) -> dict[str, Any]:
    return MAPS[name]
