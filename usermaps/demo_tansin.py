"""User map: demo_tansin — x' = tan(x^2) - y, y' = 2xy.

Escape predicate includes the NaN guard (diverged orbits overflow to NaN and
NaN comparisons are False; without the guard the point is misclassified as a
prisoner forever — see the project's known-issues KB).
"""

from __future__ import annotations

import numpy as np
from typing import Any


def make() -> dict[str, Any]:
    def step(x, y, cx, cy):
        return np.tan(x * x) - y + cx, 2.0 * x * y + cy

    def gone(x, y):
        r = x * x + y * y
        return (r > 1e4) | ~np.isfinite(r)

    return dict(
        name="demo_tansin",
        title="D E M O _ T A N S I N",
        sub="x' = tan(x^2) - y, y' = 2xy",
        step=step,
        gone=gone,
        chunk=8,
        cull=False,
        invert=False,
        julia=None,
        samp=(-1.0, 1.0, -1.0, 1.0),
        plot=(-2.5, 2.5, -2.5, 2.5),
        size=(2048, 2048),
        batch=1_500_000,
        chans=((60, 8_000_000), (300, 5_000_000), (1000, 3_000_000)),
        grammar=dict(family="mutation", real="tan", imag="plain", power=2),
    )
