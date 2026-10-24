"""Map-generic S0/S1/S2 estimators of the orbit-density histogram.

Mirrors brot_samplers.py (subject repo) algorithm-for-algorithm, including the
RNG consumption order, so that on the mandel map results are bit-identical for
S0/S1 (validated in validate_harness.py) and estimator-identical up to
floating-point summation order for S2 (streaming accumulation: the repo
buffers every post-burn state's cells in memory, which is infeasible at the
study's top budgets; the weights/ESS path is kept bit-identical).

Only deviations from brot_samplers.py, all mechanical:
  * step rule / escape predicate / frames come from the map adapter
    (conv_maps.MAPS) instead of module-level buddhabrot constants;
  * the interior cull (inside_main_sets) is applied only where the map has an
    analytic interior test (mandel); z3/cosmut run unculled — estimator-
    identical since culled seeds provably contribute 0 points;
  * S2 accumulates the histogram per step instead of at the end;
  * batch sizes are parameters (repo defaults are used for validation runs).
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from conv_maps import get


def _normalized(h: np.ndarray) -> np.ndarray:
    """brot_samplers._normalized, verbatim."""
    total = h.sum()
    if total > 0:
        return h / total
    return h * 0.0


def _ess(weights: np.ndarray) -> float:
    """brot_samplers._ess, verbatim (Kish)."""
    sq = float(np.square(weights).sum())
    if sq <= 0.0:
        return 0.0
    return float(weights.sum() ** 2 / sq)


# ------------------------------------------------------------------ kernels


def escape_times(mapd: dict, cr: np.ndarray, ci: np.ndarray, max_iter: int,
                 chunk: int = 16) -> np.ndarray:
    """brot_samplers.escape_times (:152-183) with the map's step/gone."""
    times = np.full(cr.shape, max_iter, dtype=np.int64)
    idx = np.arange(cr.size)
    zr, zi = cr.copy(), ci.copy()
    cr_w, ci_w = cr, ci
    step, gone = mapd["step"], mapd["gone_trace"]
    it = 0
    while zr.size and it < max_iter:
        steps = min(chunk, max_iter - it)
        for _ in range(steps):
            zr, zi = step(zr, zi, cr_w, ci_w)
        m = gone(zr, zi)
        if m.any():
            times[idx[m]] = it + steps
            keep = ~m
            idx = idx[keep]
            zr, zi = zr[keep], zi[keep]
            cr_w, ci_w = cr_w[keep], ci_w[keep]
        it += steps
    return times


def trace_orbits(mapd: dict, cr: np.ndarray, ci: np.ndarray, max_iter: int,
                 W: int, H: int) -> tuple[np.ndarray, list[np.ndarray]]:
    """brot_samplers.trace_orbits (:186-245) with the map's step/gone/plot
    window. Point semantics identical: plot z (starting z1=c) before
    stepping, escape-check after stepping, only escapers' points returned."""
    n = cr.size
    times = np.full(n, max_iter, dtype=np.int64)
    escaped = np.zeros(n, dtype=bool)
    px0, px1, py0, py1 = mapd["plot"]
    sx = W / (px1 - px0)
    sy = H / (py1 - py0)
    idx = np.arange(n)
    zr, zi = cr.copy(), ci.copy()
    cr_w, ci_w = cr, ci
    step, gone = mapd["step"], mapd["gone_trace"]
    owner_parts: list[np.ndarray] = []
    cell_parts: list[np.ndarray] = []
    it = 0
    while zr.size and it < max_iter:
        px = ((zr - px0) * sx).astype(np.int64)
        py = ((zi - py0) * sy).astype(np.int64)
        inb = (px >= 0) & (px < W) & (py >= 0) & (py < H)
        if inb.any():
            owner_parts.append(idx[inb])
            cell_parts.append(py[inb] * W + px[inb])
        zr, zi = step(zr, zi, cr_w, ci_w)
        m = gone(zr, zi)
        if m.any():
            times[idx[m]] = it + 1
            escaped[idx[m]] = True
            keep = ~m
            idx = idx[keep]
            zr, zi = zr[keep], zi[keep]
            cr_w, ci_w = cr_w[keep], ci_w[keep]
        it += 1
    if owner_parts:
        owner_all = np.concatenate(owner_parts)
        cell_all = np.concatenate(cell_parts)
        keep_pts = escaped[owner_all]
        owner, cell = owner_all[keep_pts], cell_all[keep_pts]
        order = np.argsort(owner, kind="stable")
        counts = np.bincount(owner, minlength=n)
        cells = np.split(cell[order], np.cumsum(counts)[:-1])
    else:
        cells = [np.empty(0, dtype=np.int64) for _ in range(n)]
    return times, cells


# ------------------------------------------------------------------ samplers


def sample_uniform(map_name: str, size: int, max_iter: int, budget: int,
                   seed: int, batch: int = 200_000) -> dict[str, Any]:
    """S0 — brot_samplers.sample_uniform (:248-282) on any map."""
    mapd = get(map_name)
    rng = np.random.default_rng(seed)
    W = H = size
    x0, x1, y0, y1 = mapd["samp"]
    hist = np.zeros(W * H, dtype=np.float64)
    n_drawn = 0
    n_escaped = 0
    n_culled = 0
    t0 = time.time()
    with np.errstate(over="ignore", invalid="ignore"):
        while n_drawn < budget:
            n = min(batch, budget - n_drawn)
            cr = rng.uniform(x0, x1, n)
            ci = rng.uniform(y0, y1, n)
            if mapd["cull"] is not None:
                keep = ~mapd["cull"](cr, ci)
                n_culled += int(n - keep.sum())
                cr, ci = cr[keep], ci[keep]
            esc = mapd["escape_mask"](cr, ci, max_iter)
            n_escaped += int(esc.sum())
            mapd["plot_orbits"](cr[esc], ci[esc], max_iter, hist, W, H)
            n_drawn += n
    total = hist.sum()
    return {
        "sampler": "S0-uniform",
        "hist": _normalized(hist).reshape(H, W),
        "hist_raw": hist.reshape(H, W),
        "hist_raw_total": float(total),
        "n_drawn": n_drawn,
        "n_escaped": n_escaped,
        "n_culled": n_culled,
        "evals": n_drawn,
        "ess": float(budget),
        "total_mass": (total / budget) if budget else 0.0,
        "sec": time.time() - t0,
        "impl": "conv.generic",
    }


def sample_boundary_importance(map_name: str, size: int, max_iter: int,
                               budget: int, seed: int, grid: int = 192,
                               pre_cap: int | None = None,
                               batch: int = 200_000) -> dict[str, Any]:
    """S1 — brot_samplers.sample_boundary_importance (:285-371) on any map."""
    mapd = get(map_name)
    if pre_cap is None:
        pre_cap = min(max_iter, 128)
    rng = np.random.default_rng(seed)
    W = H = size
    x0, x1, y0, y1 = mapd["samp"]
    t0 = time.time()
    prepass_evals = grid * grid
    dx = (x1 - x0) / grid
    dy = (y1 - y0) / grid
    gx = x0 + (np.arange(grid) + 0.5) * dx
    gy = y0 + (np.arange(grid) + 0.5) * dy
    cx, cy = np.meshgrid(gx, gy)
    with np.errstate(over="ignore", invalid="ignore"):
        t_pre = escape_times(mapd, cx.ravel(), cy.ravel(), pre_cap)
    if mapd["cull"] is not None:
        interior = mapd["cull"](cx.ravel(), cy.ravel())
    else:
        interior = np.zeros(cx.size, dtype=bool)
    w_grid = np.where(interior, 0.0, np.maximum(t_pre, 1).astype(np.float64))
    w_bar = float(w_grid.mean())
    w_max = float(w_grid.max())
    cell_w = w_grid.reshape(grid, grid)
    acc_cr: list[np.ndarray] = []
    acc_ci: list[np.ndarray] = []
    acc_w: list[np.ndarray] = []
    draws = 0
    budget_main = max(0, budget - prepass_evals)
    while draws < budget_main:
        n = min(batch, budget_main - draws)
        cr = rng.uniform(x0, x1, n)
        ci = rng.uniform(y0, y1, n)
        ix = np.clip(((cr - x0) / dx).astype(np.int64), 0, grid - 1)
        iy = np.clip(((ci - y0) / dy).astype(np.int64), 0, grid - 1)
        w = cell_w[iy, ix]
        u = rng.random(n)
        acc = u * w_max < w
        if acc.any():
            acc_cr.append(cr[acc])
            acc_ci.append(ci[acc])
            acc_w.append(w[acc])
        draws += n
    hist = np.zeros(W * H, dtype=np.float64)
    total = 0.0
    wsum = 0.0
    wsq = 0.0
    n_acc = int(sum(a.size for a in acc_w))
    if n_acc:
        cr_all = np.concatenate(acc_cr)
        ci_all = np.concatenate(acc_ci)
        w_all = np.concatenate(acc_w)
        uniq, inv = np.unique(w_all, return_inverse=True)
        tmp = np.zeros(W * H, dtype=np.float64)
        with np.errstate(over="ignore", invalid="ignore"):
            for k in range(uniq.size):
                sel = inv == k
                wk = float(uniq[k])
                weight = w_bar / wk
                cr_g, ci_g = cr_all[sel], ci_all[sel]
                esc = mapd["escape_mask"](cr_g, ci_g, max_iter)
                tmp[:] = 0.0
                mapd["plot_orbits"](cr_g[esc], ci_g[esc], max_iter, tmp, W, H)
                hist += weight * tmp
                total += weight * tmp.sum()
                wsum += float(sel.sum()) * weight
                wsq += float(sel.sum()) * weight * weight
    ess = (wsum * wsum / wsq) if wsq > 0.0 else 0.0
    return {
        "sampler": "S1-boundary-IS",
        "hist": _normalized(hist).reshape(H, W),
        "prepass_evals": prepass_evals,
        "pre_cap": pre_cap,
        "grid": grid,
        "n_drawn": draws,
        "n_accepted": n_acc,
        "acceptance": (n_acc / draws) if draws else 0.0,
        "evals": prepass_evals + draws,
        "ess": ess,
        "total_mass": (total / n_acc) if n_acc else 0.0,
        "sec": time.time() - t0,
        "impl": "conv.generic",
    }


def sample_mh_mutation_stream(map_name: str, size: int, max_iter: int,
                              budget: int, seed: int, chains: int = 64,
                              step: float = 0.03, t_mid_frac: float = 0.5,
                              t_sigma_frac: float = 0.25,
                              burn_frac: float = 0.2,
                              init_cap_frac: float = 0.4,
                              batch: int = 4096) -> dict[str, Any]:
    """S2 — brot_samplers.sample_mh_mutation (:374-503), streaming variant.

    Identical chain semantics and RNG consumption order; the histogram is
    accumulated per step (bincount over the step's current cells weighted by
    1/current-r) instead of buffering ~budget cell arrays in memory. The ESS
    weights array is kept and reduced exactly like the repo (_ess over the
    concatenated weights)."""
    mapd = get(map_name)
    rng = np.random.default_rng(seed)
    W = H = size
    x0, x1, y0, y1 = mapd["samp"]
    t_mid = t_mid_frac * max_iter
    t_sigma = max(t_sigma_frac * max_iter, 1e-9)

    def bump(t: np.ndarray) -> np.ndarray:
        return np.exp(-0.5 * ((t - t_mid) / t_sigma) ** 2)

    t0 = time.time()
    evals = 0
    init_cap = int(init_cap_frac * budget)
    cur_cr_l: list[float] = []
    cur_ci_l: list[float] = []
    cur_r_l: list[float] = []
    cur_cells_l: list[np.ndarray] = []
    with np.errstate(over="ignore", invalid="ignore"):
        while len(cur_r_l) < chains and evals < init_cap and evals < budget:
            n = min(
                batch,
                init_cap - evals,
                budget - evals,
                max(64, 8 * (chains - len(cur_r_l))),
            )
            cr = rng.uniform(x0, x1, n)
            ci = rng.uniform(y0, y1, n)
            times, cells = trace_orbits(mapd, cr, ci, max_iter, W, H)
            hits = np.fromiter((c.size for c in cells), dtype=np.int64, count=n)
            r = hits * bump(times.astype(np.float64))
            ok = np.nonzero(r > 0.0)[0]
            for k in ok[: chains - len(cur_r_l)]:
                cur_cr_l.append(float(cr[k]))
                cur_ci_l.append(float(ci[k]))
                cur_r_l.append(float(r[k]))
                cur_cells_l.append(cells[k])
            evals += n
        n_states = 0
        accepted_post = 0
        steps = 0
        burn = 0
        all_w: list[np.ndarray] = []
        hist = np.zeros(W * H, dtype=np.float64)
        k_chains = len(cur_r_l)
        if k_chains:
            cur_cr = np.asarray(cur_cr_l)
            cur_ci = np.asarray(cur_ci_l)
            cur_r = np.asarray(cur_r_l)
            cur_cells = list(cur_cells_l)
            steps = (budget - evals) // k_chains
            burn = int(burn_frac * steps)
            for step_i in range(steps):
                prop_cr = cur_cr + rng.normal(0.0, step, k_chains)
                prop_ci = cur_ci + rng.normal(0.0, step, k_chains)
                inb = (
                    (prop_cr >= x0) & (prop_cr <= x1)
                    & (prop_ci >= y0) & (prop_ci <= y1)
                )
                r_prop = np.zeros(k_chains)
                cells_prop: list[np.ndarray] = [np.empty(0, np.int64)] * k_chains
                sub = np.nonzero(inb)[0]
                if sub.size:
                    evals += int(sub.size)
                    times, cells = trace_orbits(
                        mapd, prop_cr[sub], prop_ci[sub], max_iter, W, H
                    )
                    hits = np.fromiter(
                        (c.size for c in cells), dtype=np.int64, count=sub.size
                    )
                    r_prop[sub] = hits * bump(times.astype(np.float64))
                    for j, s in enumerate(sub):
                        cells_prop[s] = cells[j]
                u = rng.random(k_chains)
                acc = u < np.minimum(1.0, r_prop / cur_r)
                for k in np.nonzero(acc)[0]:
                    cur_cr[k] = prop_cr[k]
                    cur_ci[k] = prop_ci[k]
                    cur_r[k] = r_prop[k]
                    cur_cells[k] = cells_prop[k]
                if step_i >= burn:
                    n_states += k_chains
                    accepted_post += int(acc.sum())
                    w_cur = 1.0 / cur_r
                    all_w.append(w_cur)
                    counts = np.fromiter(
                        (c.size for c in cur_cells),
                        dtype=np.int64,
                        count=k_chains,
                    )
                    if counts.sum() > 0:
                        cells_flat = np.concatenate(cur_cells)
                        hist += np.bincount(
                            cells_flat,
                            weights=np.repeat(w_cur, counts),
                            minlength=W * H,
                        )
    ess = 0.0
    if all_w:
        wts = np.concatenate(all_w)
        ess = _ess(wts)
    return {
        "sampler": "S2-MH-mutation",
        "hist": _normalized(hist).reshape(H, W),
        "chains": k_chains,
        "steps": steps,
        "burn": burn,
        "n_states": n_states,
        "acceptance": (accepted_post / n_states) if n_states else 0.0,
        "evals": evals,
        "ess": ess,
        "total_mass": None,
        "sec": time.time() - t0,
        "impl": "conv.streaming",
    }


def total_variation(a: np.ndarray, b: np.ndarray) -> float:
    """brot_samplers.total_variation, verbatim."""
    return float(0.5 * np.abs(a - b).sum())
