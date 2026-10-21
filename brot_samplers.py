#!/usr/bin/env python3
"""Three estimators of one orbit-density histogram (S0 / S1 / S2).

Estimand — identical for all three samplers
--------------------------------------------------
Draw c uniformly from the buddhabrot frame F = [XMIN, XMAX] x [YMIN, YMAX]
(the module constants of buddhabrot.py). Let orbit(c) be the pre-escape
orbit of z0 = c under z <- z^2 + c, escaped when |z|^2 > 4, truncated at
`max_iter` steps. buddhabrot.plot_orbits plots exactly the points of
orbit(c) that land in the W x H pixel grid, and only for seeds that escape
within `max_iter`. Define

    g_p(c) = number of orbit points of c falling in pixel p  (0 if c
             never escapes within max_iter),

    P[p] = E_c~U(F)[g_p(c)] / sum_p' E_c~U(F)[g_p'(c)].

P is *the* orbit-density histogram estimated here: a probability
distribution over pixels. Every sampler below returns a histogram
normalised to sum 1, an effective sample size (Kish), the number of orbit
evaluations consumed, and — where the method can see it — the total-mass
estimate E_U[sum_p g_p]. All samplers are seeded (numpy default_rng,
deterministic per seed) and hard-capped: `budget` is the maximum number of
seed-orbit evaluations per call, pre-passes and chain inits included.

S0 — uniform (wraps existing machinery)
--------------------------------------------------
Plain Monte Carlo: draw `budget` seeds uniformly, cull the provably
non-escaping cardioid/bulb interior (buddhabrot.inside_main_sets),
classify with buddhabrot.escape_mask, histogram with buddhabrot.plot_orbits.
P_hat0[p] = (sum_j g_p(c_j)) / (sum_p' sum_j g_p'(c_j)); weights are all 1,
so ESS = budget, and total mass is unbiased.

S1 — boundary importance via rejection on escape-time bands
--------------------------------------------------
Pre-pass (cheap, counted against budget): a G x G lattice of cell centres
over F; each centre gets its escape time t(cell) at cap `pre_cap`
(escape_times, chunked like buddhabrot.escape_mask). Weight

    w(cell) = 0            if the centre is inside the main cardioid or
                            period-2 bulb (provably never escapes ->
                            contributes exactly 0, so q = 0 there is legal)
    w(cell) = max(t, 1)    otherwise  (t = pre_cap if it did not escape,
                            i.e. boundary-adjacent -> heaviest).

Derivation of the weighting: the per-sample total contribution to the
histogram is sum_p g_p(c) = (number of plotted points) = the escape step
count itself — plot_orbits plots every pre-escape step. So E[contribution |
cell] is *exactly* proportional to the cell's expected escape time, and a
proposal q(c) proportional to the integrand's magnitude is the classic
zero-variance direction for importance sampling. Sampling: rejection —
draw uniform, accept with probability w(cell)/w_max. The proposal is
piecewise constant per cell, and each accepted seed carries importance
weight

    W(c) = w_bar / w(cell(c)),   w_bar = mean of the pre-pass grid,

so P_hat1[p] ∝ sum_i W(c_i) g_p(c_i). Because the estimator divides by
exactly the q that generated the samples, the *shape* (normalised
histogram) is unbiased; only the global total-mass scale carries the
grid-mean approximation of E_U[w]. Rejection efficiency (mean_w / w_max)
is reported as `acceptance`.

S2 — Metropolis-Hastings seed mutation
--------------------------------------------------
Target (precise): with hits(c) = number of in-frame pre-escape orbit
points of c and T(c) = the step at which the escape was observed
(max_iter if never observed),

    r(c) = 0                                if c outside F,
    r(c) = 0                                if hits(c) = 0,
    r(c) = hits(c) * bump(T(c))             otherwise,
    bump(t) = exp(-0.5 * ((t - t_mid)/t_sigma)^2),
    t_mid = t_mid_frac * max_iter, t_sigma = t_sigma_frac * max_iter.

So the target rewards seeds whose orbits hit the frame often AND whose
orbit length sits mid-range (gaussian bump on the escape step, peaked at
t_mid; defaults 0.5 / 0.25 of the cap). Note every escaper has hits >= 1
(the orbit starts at c, which is in-frame), so r > 0 exactly on escapers.

Chain: c' = c + N(0, step^2 I) — a symmetric Gaussian mutation, so the
MH acceptance ratio is min(1, r(c')/r(c)); out-of-frame proposals have
r = 0 and are rejected (equivalent to restricting r to F, detailed
balance preserved). `chains` independent chains run in lock-step,
vectorised; they are initialised by uniform rejection until r > 0
(guaranteed quickly — escapers dominate the frame). States before
`burn` = int(burn_frac * steps) are discarded. Each post-burn state is
accumulated with SNIS weight 1/r(c) against the unknown normaliser
Z_r = integral of r, so S2 estimates the *shape* P (self-normalised
importance sampling); total mass is not identifiable without Z_r and is
reported as None.

Mixing justification: independent parallel chains from dispersed
uniform starts collapse onto the target's support from different
regions; acceptance rate is recorded every call (healthy band roughly
0.2-0.6 for the default step; sustained ~0 or ~1 would mean the mutation
scale is wrong), and the Kish ESS of the 1/r weights diagnoses the
weight degeneracy that SNIS would suffer if the chain over-concentrated.

Usage:
    python brot_samplers.py [--full] [--size N] [--max-iter N]
                            [--budget N] [--grid N] [--chains N]
                            [--step S] [--seed N] [--save PATH]
"""

from __future__ import annotations

import argparse
import os
import time
from typing import Any

import numpy as np

import buddhabrot as bb
from buddhabrot import XMAX, XMIN, YMAX, YMIN

SMOKE: dict[str, int | float] = {
    "size": 256,
    "max_iter": 150,
    "budget": 150_000,
    "grid": 128,
    "chains": 64,
    "step": 0.03,
}
FULL: dict[str, int | float] = {
    "size": 512,
    "max_iter": 300,
    "budget": 1_500_000,
    "grid": 256,
    "chains": 96,
    "step": 0.02,
}


def _normalized(h: np.ndarray) -> np.ndarray:
    """Histogram -> pixel distribution (sums to 1; all-zero stays zero)."""
    total = h.sum()
    if total > 0:
        return h / total
    return h * 0.0


def _ess(weights: np.ndarray) -> float:
    """Kish effective sample size (sum w)^2 / sum w^2."""
    sq = float(np.square(weights).sum())
    if sq <= 0.0:
        return 0.0
    return float(weights.sum() ** 2 / sq)


def escape_times(
    cr: np.ndarray, ci: np.ndarray, max_iter: int, chunk: int = 16
) -> np.ndarray:
    """Steps applied when each orbit of c was observed escaped (chunked).

    Mirrors buddhabrot.escape_mask's compaction pattern but records the
    check index instead of a boolean: times[i] = it + steps at the check
    that first saw |z|^2 > 4 or NaN, or max_iter if never within the cap.
    The recorded value has chunk granularity (a cheap classifier — used
    for S1's pre-pass weights, never for the plotted points themselves).
    """
    times = np.full(cr.shape, max_iter, dtype=np.int64)
    idx = np.arange(cr.size)
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
        m = (r2 > 4.0) | np.isnan(r2)
        if m.any():
            times[idx[m]] = it + steps
            keep = ~m
            idx = idx[keep]
            zr, zi = zr[keep], zi[keep]
            cr_w, ci_w = cr_w[keep], ci_w[keep]
        it += steps
    return times


def trace_orbits(
    cr: np.ndarray, ci: np.ndarray, max_iter: int, W: int, H: int
) -> tuple[np.ndarray, list[np.ndarray]]:
    """Per-seed escape step and in-frame orbit cells (exact, per-step).

    Point semantics are those of buddhabrot.plot_orbits: plot z (starting
    with z1 = c) before stepping, check |z|^2 > 4 / NaN after stepping, and
    drop escaped seeds — so cells are exactly the points plot_orbits would
    histogram for an escaping seed. Returns (times[i], cells[i]) where
    times is the exact first step at which the escape was observed
    (max_iter if never) and cells[i] holds flat pixel indices
    row*W + col of the in-frame pre-escape points of seed i — empty for
    seeds that never escape within max_iter, matching the estimand's
    g_p(c) = 0 there (render_channel plots escapers only).
    """
    n = cr.size
    times = np.full(n, max_iter, dtype=np.int64)
    escaped = np.zeros(n, dtype=bool)
    sx = W / (XMAX - XMIN)
    sy = H / (YMAX - YMIN)
    idx = np.arange(n)
    zr, zi = cr.copy(), ci.copy()
    cr_w, ci_w = cr, ci
    owner_parts: list[np.ndarray] = []
    cell_parts: list[np.ndarray] = []
    it = 0
    while zr.size and it < max_iter:
        px = ((zr - XMIN) * sx).astype(np.int64)
        py = ((zi - YMIN) * sy).astype(np.int64)
        inb = (px >= 0) & (px < W) & (py >= 0) & (py < H)
        if inb.any():
            owner_parts.append(idx[inb])
            cell_parts.append(py[inb] * W + px[inb])
        t = zr * zr - zi * zi + cr_w
        zi = 2.0 * zr * zi + ci_w
        zr = t
        r2 = zr * zr + zi * zi
        m = (r2 > 4.0) | np.isnan(r2)
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
        # drop points of non-escaping seeds BEFORE splitting, so the split
        # boundaries stay aligned (zeroing counts alone would leak the
        # orphaned points into the last seed's segment)
        keep_pts = escaped[owner_all]
        owner, cell = owner_all[keep_pts], cell_all[keep_pts]
        order = np.argsort(owner, kind="stable")
        counts = np.bincount(owner, minlength=n)
        cells = np.split(cell[order], np.cumsum(counts)[:-1])
    else:
        cells = [np.empty(0, dtype=np.int64) for _ in range(n)]
    return times, cells


def sample_uniform(
    size: int, max_iter: int, budget: int, seed: int, batch: int = 200_000
) -> dict[str, Any]:
    """S0: uniform Monte Carlo over the frame, wrapping buddhabrot machinery."""
    rng = np.random.default_rng(seed)
    W = H = size
    hist = np.zeros(W * H, dtype=np.float64)
    n_drawn = 0
    n_escaped = 0
    n_culled = 0
    t0 = time.time()
    with np.errstate(over="ignore", invalid="ignore"):
        while n_drawn < budget:
            n = min(batch, budget - n_drawn)
            cr = rng.uniform(XMIN, XMAX, n)
            ci = rng.uniform(YMIN, YMAX, n)
            keep = ~bb.inside_main_sets(cr, ci)
            n_culled += int(n - keep.sum())
            cr, ci = cr[keep], ci[keep]
            esc = bb.escape_mask(cr, ci, max_iter)
            n_escaped += int(esc.sum())
            bb.plot_orbits(cr[esc], ci[esc], max_iter, hist, W, H)
            n_drawn += n
    total = hist.sum()
    return {
        "sampler": "S0-uniform",
        "hist": _normalized(hist).reshape(H, W),
        "n_drawn": n_drawn,
        "n_escaped": n_escaped,
        "n_culled": n_culled,
        "evals": n_drawn,
        "ess": float(budget),
        "total_mass": (total / budget) if budget else 0.0,
        "sec": time.time() - t0,
    }


def sample_boundary_importance(
    size: int,
    max_iter: int,
    budget: int,
    seed: int,
    grid: int = 192,
    pre_cap: int | None = None,
    batch: int = 200_000,
) -> dict[str, Any]:
    """S1: rejection sampling from a pre-pass escape-time-band importance."""
    if pre_cap is None:
        pre_cap = min(max_iter, 128)
    rng = np.random.default_rng(seed)
    W = H = size
    t0 = time.time()
    prepass_evals = grid * grid
    # cheap pre-pass: G x G lattice of cell centres, escape time per centre
    dx = (XMAX - XMIN) / grid
    dy = (YMAX - YMIN) / grid
    gx = XMIN + (np.arange(grid) + 0.5) * dx
    gy = YMIN + (np.arange(grid) + 0.5) * dy
    cx, cy = np.meshgrid(gx, gy)
    with np.errstate(over="ignore", invalid="ignore"):
        t_pre = escape_times(cx.ravel(), cy.ravel(), pre_cap)
    interior = bb.inside_main_sets(cx.ravel(), cy.ravel())
    w_grid = np.where(interior, 0.0, np.maximum(t_pre, 1).astype(np.float64))
    w_bar = float(w_grid.mean())
    w_max = float(w_grid.max())
    cell_w = w_grid.reshape(grid, grid)  # rows index y, cols index x
    # rejection sampling until the remaining budget is spent
    acc_cr: list[np.ndarray] = []
    acc_ci: list[np.ndarray] = []
    acc_w: list[np.ndarray] = []
    draws = 0
    budget_main = max(0, budget - prepass_evals)
    while draws < budget_main:
        n = min(batch, budget_main - draws)
        cr = rng.uniform(XMIN, XMAX, n)
        ci = rng.uniform(YMIN, YMAX, n)
        ix = np.clip(((cr - XMIN) / dx).astype(np.int64), 0, grid - 1)
        iy = np.clip(((ci - YMIN) / dy).astype(np.int64), 0, grid - 1)
        w = cell_w[iy, ix]
        u = rng.random(n)
        acc = u * w_max < w  # accept with probability w / w_max
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
                esc = bb.escape_mask(cr_g, ci_g, max_iter)
                tmp[:] = 0.0  # plot_orbits is a no-op on an empty escape set
                bb.plot_orbits(cr_g[esc], ci_g[esc], max_iter, tmp, W, H)
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
        "n_drawn": draws,
        "n_accepted": n_acc,
        "acceptance": (n_acc / draws) if draws else 0.0,
        "evals": prepass_evals + draws,
        "ess": ess,
        "total_mass": (total / n_acc) if n_acc else 0.0,
        "sec": time.time() - t0,
    }


def sample_mh_mutation(
    size: int,
    max_iter: int,
    budget: int,
    seed: int,
    chains: int = 64,
    step: float = 0.03,
    t_mid_frac: float = 0.5,
    t_sigma_frac: float = 0.25,
    burn_frac: float = 0.2,
    init_cap_frac: float = 0.4,
    batch: int = 4096,
) -> dict[str, Any]:
    """S2: Metropolis-Hastings Gaussian seed mutation targeting r(c)."""
    rng = np.random.default_rng(seed)
    W = H = size
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
        # init: uniform rejection until chains states with r > 0 are found;
        # each batch is capped at ~8x the still-missing chains because a
        # candidate succeeds whenever it escapes (the bulk of the frame)
        while len(cur_r_l) < chains and evals < init_cap and evals < budget:
            n = min(
                batch,
                init_cap - evals,
                budget - evals,
                max(64, 8 * (chains - len(cur_r_l))),
            )
            cr = rng.uniform(XMIN, XMAX, n)
            ci = rng.uniform(YMIN, YMAX, n)
            times, cells = trace_orbits(cr, ci, max_iter, W, H)
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
        all_cells: list[np.ndarray] = []
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
                    (prop_cr >= XMIN)
                    & (prop_cr <= XMAX)
                    & (prop_ci >= YMIN)
                    & (prop_ci <= YMAX)
                )
                r_prop = np.zeros(k_chains)
                # placeholders are replaced for every in-frame proposal;
                # accepted states always have r > 0, hence a real trace
                cells_prop: list[np.ndarray] = [np.empty(0, np.int64)] * k_chains
                sub = np.nonzero(inb)[0]
                if sub.size:
                    evals += int(sub.size)
                    times, cells = trace_orbits(
                        prop_cr[sub], prop_ci[sub], max_iter, W, H
                    )
                    hits = np.fromiter(
                        (c.size for c in cells), dtype=np.int64, count=sub.size
                    )
                    r_prop[sub] = hits * bump(times.astype(np.float64))
                    for j, s in enumerate(sub):
                        cells_prop[s] = cells[j]
                u = rng.random(k_chains)
                # cur_r > 0 is an invariant (init and every acceptance
                # require r > 0), so the plain ratio is always defined.
                acc = u < np.minimum(1.0, r_prop / cur_r)
                for k in np.nonzero(acc)[0]:
                    cur_cr[k] = prop_cr[k]
                    cur_ci[k] = prop_ci[k]
                    cur_r[k] = r_prop[k]
                    cur_cells[k] = cells_prop[k]
                if step_i >= burn:
                    n_states += k_chains
                    accepted_post += int(acc.sum())
                    all_w.append(1.0 / cur_r)
                    all_cells.extend(cur_cells)
    hist = np.zeros(W * H, dtype=np.float64)
    ess = 0.0
    if all_w:
        wts = np.concatenate(all_w)
        counts = np.fromiter(
            (c.size for c in all_cells), dtype=np.int64, count=len(all_cells)
        )
        cells_flat = np.concatenate(all_cells)
        hist = np.bincount(
            cells_flat, weights=np.repeat(wts, counts), minlength=W * H
        ).astype(np.float64)
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
    }


def total_variation(a: np.ndarray, b: np.ndarray) -> float:
    """Total-variation distance between two pixel distributions."""
    return float(0.5 * np.abs(a - b).sum())


def compare(
    size: int = 128,
    max_iter: int = 100,
    budget: int = 60_000,
    seed: int = 20261021,
    grid: int = 128,
    chains: int = 64,
    step: float = 0.03,
) -> dict[str, Any]:
    """Run S0/S1/S2 on the same budget and compare their histograms."""
    s0 = sample_uniform(size, max_iter, budget, seed)
    s1 = sample_boundary_importance(size, max_iter, budget, seed + 1, grid=grid)
    s2 = sample_mh_mutation(size, max_iter, budget, seed + 2, chains=chains, step=step)
    return {
        "s0": s0,
        "s1": s1,
        "s2": s2,
        "tv": {
            "s1_vs_s0": total_variation(s0["hist"], s1["hist"]),
            "s2_vs_s0": total_variation(s0["hist"], s2["hist"]),
            "s2_vs_s1": total_variation(s1["hist"], s2["hist"]),
        },
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Three estimators of the same orbit-density histogram."
    )
    ap.add_argument("--full", action="store_true", help="full preset (default smoke)")
    ap.add_argument("--size", type=int, default=None)
    ap.add_argument("--max-iter", type=int, default=None)
    ap.add_argument("--budget", type=int, default=None)
    ap.add_argument("--grid", type=int, default=None)
    ap.add_argument("--chains", type=int, default=None)
    ap.add_argument("--step", type=float, default=None)
    ap.add_argument("--seed", type=int, default=20261021)
    ap.add_argument("--save", default=None, help="npz output path for the 3 hists")
    args = ap.parse_args(argv)

    cfg: dict[str, Any] = dict(FULL if args.full else SMOKE)
    for key in ("size", "max_iter", "budget", "grid", "chains", "step"):
        val = getattr(args, key)
        if val is not None:
            cfg[key] = val
    res = compare(**cfg, seed=args.seed)
    s0, s1, s2 = res["s0"], res["s1"], res["s2"]
    print(
        f"[S0] uniform draws={s0['n_drawn']:,} escaped={s0['n_escaped']:,} "
        f"mass={s0['total_mass']:.1f} ESS={s0['ess']:,.0f} ({s0['sec']:.1f}s)"
    )
    print(
        f"[S1] boundary-IS prepass={s1['prepass_evals']:,} draws={s1['n_drawn']:,} "
        f"accepted={s1['n_accepted']:,} ({100 * s1['acceptance']:.1f}%) "
        f"ESS={s1['ess']:,.0f} mass={s1['total_mass']:.1f} ({s1['sec']:.1f}s)"
    )
    print(
        f"[S2] MH chains={s2['chains']} steps={s2['steps']} burn={s2['burn']} "
        f"accept={100 * s2['acceptance']:.1f}% ESS={s2['ess']:,.0f} "
        f"states={s2['n_states']:,} ({s2['sec']:.1f}s)"
    )
    print(
        f"TV(P1,P0)={res['tv']['s1_vs_s0']:.4f}  "
        f"TV(P2,P0)={res['tv']['s2_vs_s0']:.4f}  "
        f"TV(P2,P1)={res['tv']['s2_vs_s1']:.4f}"
    )
    if args.save:
        os.makedirs(os.path.dirname(os.path.abspath(args.save)), exist_ok=True)
        np.savez(args.save, s0=s0["hist"], s1=s1["hist"], s2=s2["hist"])
        print("wrote", args.save)


if __name__ == "__main__":  # pragma: no cover
    main()
