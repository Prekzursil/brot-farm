"""Probe (2026-10-24, numeric lane 3): randomized-horizon orbit-density
estimator S3 vs the study's S0 (and S2 at the top rung), head-to-head at
matched budget on mandel:1500 and cosmut:1500.

S3 — chosen form: single-sample randomized-level truncation (Rhee-Glynn
single-term structure, Rhee & Glynn 2015) applied to the escape-time orbit
density. Target per orbit is exactly the study's estimand
(conv_samplers.trace_orbits / buddhabrot.plot_orbits semantics: plot z_1=c
before stepping, escape-check after each step, keep only seeds escaping
within the cap C, in-frame points only):

    A(c) = 1[t(c) <= C] * sum_{i=1..t(c)} 1[in-frame](z_i) * delta_cell(z_i)

Estimator per orbit: draw a level H in {2..C} from p; run the orbit;
    t == 1  -> contribute z_1 with weight 1            (base term A_1)
    t == H  -> contribute z_1..z_t with weight 1/p_H   (level term)
    else    -> contribute nothing
Unbiasedness (telescoping; A_h - A_{h-1} = 1[t=h] sum_{i<=h} delta_i for
h >= 2):
    E[contrib|c] = 1[t=1] d_{z1}
                 + sum_{h=2..C} p_h * 1[t=h] * (sum_{i<=h} d_i) / p_h
                 = 1[t=1] d_{z1} + sum_{h=2..C} 1[t=h] sum_{i<=h} d_i
                 = 1[t<=C] sum_{i<=t} d_i = A(c).              (exact)
Level law (compute-constrained variance-optimal): p_h ∝ sqrt(E[D_h^2]/h)
on pilot-observed levels, with E[D_h^2] = (N(h)+alpha) * m_h^2 (the
orthogonal-increment variance is Var = sum_h E|D_h|^2 / p_h and the
per-draw cost is E[H] = sum_h p_h h; minimizing Var*cost gives
p ∝ sqrt(E D^2 / h) by Cauchy-Schwarz). N(h) = pilot count of orbits
escaping exactly at h (Laplace +0.5), m_h = their mean in-frame point
count (linear interp; slope-1 extrapolation capped at h). Levels with no
pilot escape (holes and the far tail) share a total mass delta_frac =
1e-4, spread proportional to m_h — full support over {2..C} is required
for exactness. Unbiasedness holds for ANY full-support p; the pilot only
shapes variance.

Both S0 and S3 share the same per-(rung, seed) c-draw stream (paired).
S0 here is an instrumented structure-clone of conv_samplers.sample_uniform
(chunked escape phase + per-step plot phase, same arithmetic via
conv_maps.MAPS kernels); `validate` checks it against the study's own
sample_uniform (same seed, TV on the normalized histograms) and checks S3's
unbiasedness at cap 40 against an S0 pair via the study's b / SE(b)
machinery (analyze.py).

Cost convention (identical unit for both estimators): iter_evals = count of
vectorized step() applications = phase-1 chunk work + resolve/plot per-step
work. Wall-clock sec is measured around the whole run. Run records carry
scalars only (rel stats vs the study's own 40M reference and ROI are
computed at run time; histograms are not persisted).

Tags: pilot | validate | h2h | s2 | extend | analyze
Usage: python probe_s3.py TAG
"""

from __future__ import annotations

import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import conv_maps  # noqa: E402,F401  (repo path + kernels)
import conv_samplers as cs  # noqa: E402  (imports follow the sys.path bootstrap above)
from conv_maps import CAP_IDS, MAP_IDS, get  # noqa: E402
from analyze import ols_slope, rel_stats, roi_from_ref, signed_mean  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, ".."))
RES = os.path.join(ROOT, "results")
DATA = os.path.join(ROOT, "data")
RUNS_JSON = os.path.join(RES, "probe_s3_runs.json")
PILOT_JSON = os.path.join(RES, "probe_s3_pilot.json")
VALIDATE_JSON = os.path.join(RES, "probe_s3_validate.json")
OUT_JSON = os.path.join(RES, "probe_s3_headtohead.json")

MAPS3 = ("mandel", "cosmut")
CAP = 1500
SIZE = 512
LADDER = (62_500, 250_000, 1_000_000, 4_000_000)
SEEDS = (0, 1, 2)
BASE3 = 20261024
S0_BATCH = 1_000_000
S3_BATCH = 200_000
PILOT_N = 2_000_000
S2_BUDGETS = (250_000, 4_000_000)

CFG = {
    "maps": list(MAPS3), "cap": CAP, "size": SIZE, "ladder": list(LADDER),
    "seeds_idx": list(SEEDS), "base_seed": BASE3,
    "seed_rule": "S0/S3 paired: BASE3+100+50*cid+1000*kind+10*rung+seed_idx "
                 "(kind 0 = h2h, 1 = extend rungs); S2: BASE3+300+50*cid+rung",
    "s0_batch": S0_BATCH, "s3_batch": S3_BATCH, "pilot_n": PILOT_N,
    "s2_budgets": list(S2_BUDGETS), "s2_chains": 1024, "s2_step": 0.02,
    "level_alpha": 0.5,
    "level_tail_mass_frac": 1e-4,
    "level_m_extrapolation": "linear interp between pilot-observed levels; "
                             "beyond the last: m_last + (h - h_last), capped "
                             "at h (one in-frame point per step at most)",
    "cost_convention": "iter_evals = vectorized step() applications "
                       "(phase-1 chunk work + resolve/plot per-step work)",
    "reference": "study data/ref_{map}_{cap}.npz (S0 @ 40M, 2026-10-21) + "
                 "analyze.roi_from_ref top-decile ROI, reused read-only",
    "repo_commit": "4d87ef33ca50b1b33c6f5736bd59bad94bd54e70",
}


def seed_for(map_name: str, kind_idx: int, rung_idx: int, seed_idx: int) -> int:
    cid = 3 * MAP_IDS[map_name] + CAP_IDS[CAP]
    return BASE3 + 100 + 50 * cid + 1000 * kind_idx + 10 * rung_idx + seed_idx


# ------------------------------------------------------------------ kernels


def phase1_escape(mapd: dict, cr: np.ndarray, ci: np.ndarray,
                  horizons: np.ndarray, chunk: int):
    """Chunked escape phase, structurally identical to buddhabrot.escape_mask
    (compaction every `chunk` steps), plus per-orbit horizons: an orbit still
    alive at the first chunk end j with horizons <= j is expired and dropped.
    Orbits detected as gone at chunk end j get det = j (upper bound of the
    exact per-step escape time; exact t is resolved in resolve_times)."""
    n = cr.size
    esc = np.zeros(n, dtype=bool)
    det = np.zeros(n, dtype=np.int64)
    idx = np.arange(n)
    zr, zi = cr.copy(), ci.copy()
    cr_w, ci_w = cr, ci
    step, gone = mapd["step"], mapd["gone_trace"]
    it = 0
    evals = 0
    hmax = int(horizons.max()) if n else 0
    with np.errstate(over="ignore", invalid="ignore"):
        while zr.size and it < hmax:
            steps = min(chunk, hmax - it)
            evals += zr.size * steps
            for _ in range(steps):
                zr, zi = step(zr, zi, cr_w, ci_w)
            m = gone(zr, zi)
            if m.any():
                esc[idx[m]] = True
                det[idx[m]] = it + steps
            hor = horizons[idx]
            drop = m | (~m & (hor <= it + steps))
            if drop.any():
                keep = ~drop
                idx = idx[keep]
                zr, zi = zr[keep], zi[keep]
                cr_w, ci_w = cr_w[keep], ci_w[keep]
            it += steps
    return esc, det, evals


def resolve_times(mapd: dict, cr: np.ndarray, ci: np.ndarray,
                  bound: np.ndarray, want_points: bool = False):
    """Per-step replay of detected escapers: exact escape time t (1-based,
    gone-check after each step, orbit started at z_1 = c). If want_points,
    also counts in-frame plot-window points per orbit (pilot). Every orbit
    must resolve at or before its chunk-quantized detection bound."""
    n = cr.size
    t = np.zeros(n, dtype=np.int64)
    pin = np.zeros(n, dtype=np.int64)
    idx = np.arange(n)
    zr, zi = cr.copy(), ci.copy()
    cr_w, ci_w = cr, ci
    px0, px1, py0, py1 = mapd["plot"]
    sx = SIZE / (px1 - px0)
    sy = SIZE / (py1 - py0)
    step, gone = mapd["step"], mapd["gone_trace"]
    it = 0
    evals = 0
    bmax = int(bound.max()) if n else 0
    with np.errstate(over="ignore", invalid="ignore"):
        while idx.size and it < bmax:
            if want_points:
                px = ((zr - px0) * sx).astype(np.int64)
                py = ((zi - py0) * sy).astype(np.int64)
                inb = (px >= 0) & (px < SIZE) & (py >= 0) & (py < SIZE)
                if inb.any():
                    pin[idx[inb]] += 1
            zr, zi = step(zr, zi, cr_w, ci_w)
            evals += zr.size
            m = gone(zr, zi)
            if m.any():
                t[idx[m]] = it + 1
                keep = ~m
                idx = idx[keep]
                zr, zi = zr[keep], zi[keep]
                cr_w, ci_w = cr_w[keep], ci_w[keep]
            it += 1
    if n:
        assert (t > 0).all(), "unresolved escaper (gone-persistence violated)"
    return t, pin, evals


def plot_weighted(mapd: dict, cr: np.ndarray, ci: np.ndarray,
                  weights: np.ndarray | None, hist: np.ndarray, W: int,
                  H: int, max_iter: int, flush_at: int = 24_000_000):
    """Per-step plot phase, structurally identical to buddhabrot.plot_orbits
    (plot before step, gone-check after step, in-frame test, buffered
    bincount flush at flush_at points), with optional per-orbit point
    weights. Returns (evals, n_points)."""
    idx = np.arange(cr.size)
    zr, zi = cr.copy(), ci.copy()
    cr_w, ci_w = cr, ci
    px0, px1, py0, py1 = mapd["plot"]
    sx = W / (px1 - px0)
    sy = H / (py1 - py0)
    step, gone = mapd["step"], mapd["gone_trace"]
    buf_c: list[np.ndarray] = []
    buf_w: list[np.ndarray] = []
    buffered = 0
    it = 0
    evals = 0
    n_pts = 0
    with np.errstate(over="ignore", invalid="ignore"):
        while idx.size and it < max_iter:
            px = ((zr - px0) * sx).astype(np.int64)
            py = ((zi - py0) * sy).astype(np.int64)
            inb = (px >= 0) & (px < W) & (py >= 0) & (py < H)
            if inb.any():
                cells = py[inb] * W + px[inb]
                buf_c.append(cells)
                if weights is not None:
                    buf_w.append(weights[idx[inb]])
                buffered += cells.size
                n_pts += cells.size
                if buffered >= flush_at:
                    if weights is None:
                        hist += np.bincount(np.concatenate(buf_c),
                                            minlength=W * H)
                    else:
                        hist += np.bincount(np.concatenate(buf_c),
                                            weights=np.concatenate(buf_w),
                                            minlength=W * H)
                    buf_c, buf_w, buffered = [], [], 0
            zr, zi = step(zr, zi, cr_w, ci_w)
            evals += zr.size
            m = gone(zr, zi)
            if m.any():
                keep = ~m
                idx = idx[keep]
                zr, zi = zr[keep], zi[keep]
                cr_w, ci_w = cr_w[keep], ci_w[keep]
            it += 1
    if buffered:
        if weights is None:
            hist += np.bincount(np.concatenate(buf_c), minlength=W * H)
        else:
            hist += np.bincount(np.concatenate(buf_c),
                                weights=np.concatenate(buf_w),
                                minlength=W * H)
    return evals, n_pts


def level_law(n_h: np.ndarray, pin_sum: np.ndarray, alpha: float,
              tail_frac: float):
    """p_h over levels h = 2..len(n_h)+1. Observed levels (n_h > 0):
    p ∝ sqrt((n_h+alpha) * m_h^2 / h) (compute-constrained variance
    optimum, see module docstring). Unobserved levels share tail_frac of
    the total mass, spread ∝ m_h (full support is required for exactness)."""
    lev = np.arange(2, n_h.size + 2)
    obs = np.nonzero(n_h > 0)[0]
    m_obs = pin_sum[obs] / n_h[obs]
    mhat = np.interp(lev, lev[obs], m_obs)
    last = obs[-1]
    beyond = lev > last
    mhat[beyond] = np.minimum(m_obs[-1] + (lev[beyond] - last), lev[beyond])
    wgt = np.where(n_h > 0, np.sqrt((n_h + alpha) * mhat ** 2 / lev), 0.0)
    p = wgt / wgt.sum()
    dead = n_h == 0
    if dead.any():
        p[dead] = tail_frac * mhat[dead] / mhat[dead].sum()
        p = p / p.sum()
    return lev, p


# ------------------------------------------------------------------ runners


def _ref_metrics(map_name: str, hist_flat: np.ndarray) -> dict:
    with np.load(os.path.join(DATA, f"ref_{map_name}_{CAP}.npz")) as z:
        refn = z["normalized"]
        raw = z["raw"]
    roi, _ = roi_from_ref(raw)
    st = rel_stats(hist_flat.reshape(SIZE, SIZE), refn, roi)
    st["b_signed"] = signed_mean(hist_flat.reshape(SIZE, SIZE), refn, roi)
    return st


def _draw_c(mapd: dict, rng, n: int):
    cr = rng.uniform(mapd["samp"][0], mapd["samp"][1], n)
    ci = rng.uniform(mapd["samp"][2], mapd["samp"][3], n)
    n_culled = 0
    if mapd["cull"] is not None:
        keep = ~mapd["cull"](cr, ci)
        n_culled = int(n - keep.sum())
        cr, ci = cr[keep], ci[keep]
    return cr, ci, n_culled


def run_s0_probe(map_name: str, budget: int, seed: int, cap: int = CAP,
                 batch: int = S0_BATCH) -> dict:
    """Instrumented structure-clone of conv_samplers.sample_uniform."""
    mapd = get(map_name)
    rng = np.random.default_rng(seed)
    W = H = SIZE
    hist = np.zeros(W * H, dtype=np.float64)
    n_drawn = n_esc = n_culled = n_pts = 0
    iter_evals = 0
    t0 = time.time()
    with np.errstate(over="ignore", invalid="ignore"):
        while n_drawn < budget:
            n = min(batch, budget - n_drawn)
            cr, ci, ncul = _draw_c(mapd, rng, n)
            n_culled += ncul
            hor = np.full(cr.size, cap, dtype=np.int64)
            esc, _, ev1 = phase1_escape(mapd, cr, ci, hor, mapd["chunk"])
            n_esc += int(esc.sum())
            ev2, pts = plot_weighted(mapd, cr[esc], ci[esc], None, hist,
                                     W, H, cap)
            iter_evals += ev1 + ev2
            n_pts += pts
            n_drawn += n
    sec = time.time() - t0
    out = {
        "map": map_name, "cap": cap, "estimator": "S0", "variant": "probe",
        "budget": budget, "seed": seed, "size": SIZE,
        "n_drawn": n_drawn, "n_escaped": n_esc, "n_culled": n_culled,
        "iter_evals": iter_evals, "sec": sec, "n_points": n_pts,
        "total_mass_per_draw": float(hist.sum()) / n_drawn,
    }
    out.update(_ref_metrics(map_name, hist / hist.sum()))
    out["hist"] = (hist / hist.sum()).tolist()
    return out


def run_s3(map_name: str, budget: int, seed: int, p: np.ndarray,
           levels: np.ndarray, cap: int = CAP,
           batch: int = S3_BATCH) -> dict:
    """S3 randomized-horizon orbit density (module docstring: derivation)."""
    mapd = get(map_name)
    rng = np.random.default_rng(seed)
    W = H = SIZE
    hist = np.zeros(W * H, dtype=np.float64)
    p_cum = np.cumsum(p)
    inv_p = 1.0 / p
    lev0 = int(levels[0])
    n_drawn = n_esc = n_culled = n_contrib = n_pts = 0
    iter_evals = 0
    sum_w = sum_w2 = max_w = h_sum = 0.0
    t0 = time.time()
    with np.errstate(over="ignore", invalid="ignore"):
        while n_drawn < budget:
            n = min(batch, budget - n_drawn)
            cr, ci, ncul = _draw_c(mapd, rng, n)
            n_culled += ncul
            u = rng.random(cr.size)
            li = np.minimum(np.searchsorted(p_cum, u, side="right"),
                            levels.size - 1)
            hor = levels[li]
            h_sum += float(hor.sum())
            esc, det, ev1 = phase1_escape(mapd, cr, ci, hor, mapd["chunk"])
            n_esc += int(esc.sum())
            sub_cr, sub_ci = cr[esc], ci[esc]
            sub_h = hor[esc]
            t_ex, _, evA = resolve_times(mapd, sub_cr, sub_ci, det[esc])
            base = t_ex == 1
            hit = t_ex == sub_h
            contrib = base | hit
            w_all = np.where(base, 1.0, inv_p[np.clip(sub_h - lev0, 0,
                                                      levels.size - 1)])
            w = w_all[contrib]
            evB, pts = plot_weighted(mapd, sub_cr[contrib], sub_ci[contrib],
                                     w, hist, W, H, cap)
            n_contrib += int(contrib.sum())
            sum_w += float(w.sum())
            sum_w2 += float(np.square(w).sum())
            if w.size:
                max_w = max(max_w, float(w.max()))
            iter_evals += ev1 + evA + evB
            n_pts += pts
            n_drawn += n
    sec = time.time() - t0
    ess_w = (sum_w * sum_w / sum_w2) if sum_w2 > 0 else 0.0
    out = {
        "map": map_name, "cap": cap, "estimator": "S3", "variant": "probe",
        "budget": budget, "seed": seed, "size": SIZE,
        "n_drawn": n_drawn, "n_escaped": n_esc, "n_culled": n_culled,
        "n_contrib": n_contrib, "contrib_frac": n_contrib / n_drawn,
        "sum_w": sum_w, "sum_w2": sum_w2, "max_w": max_w, "ess_w": ess_w,
        "mean_H_drawn": h_sum / n_drawn,
        "iter_evals": iter_evals, "sec": sec, "n_points": n_pts,
        "total_mass_per_draw": float(hist.sum()) / n_drawn,
    }
    out.update(_ref_metrics(map_name, hist / hist.sum()))
    out["hist"] = (hist / hist.sum()).tolist()
    return out


# ------------------------------------------------------------------ tags


def load_runs() -> list:
    if os.path.exists(RUNS_JSON):
        with open(RUNS_JSON, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_runs(runs: list) -> None:
    with open(RUNS_JSON, "w", encoding="utf-8") as f:
        json.dump(runs, f, indent=2)


def append_run(rec: dict) -> None:
    key = (rec["map"], rec["estimator"], rec["variant"], rec["budget"],
           rec["seed"])
    runs = load_runs()
    if any((r["map"], r["estimator"], r["variant"], r["budget"], r["seed"])
           == key for r in runs):
        print(f"[skip] {key}", flush=True)
        return
    runs.append({k: v for k, v in rec.items() if k != "hist"})
    save_runs(runs)
    ev = (f"{rec['iter_evals']:.2e}" if rec.get("iter_evals") is not None
          else "n/a")
    print(f"[done] {rec['map']} {rec['estimator']}@{rec['budget']} "
          f"seed{rec['seed']} sec={rec['sec']:.1f} "
          f"meanrel={rec['mean_rel_err']:.4f} "
          f"evals={ev}", flush=True)


def pilot_map(map_name: str, n: int, cap: int, seed: int) -> dict:
    """Exact escape-time + in-frame-point counts over n draws at `cap`."""
    mapd = get(map_name)
    rng = np.random.default_rng(seed)
    t0 = time.time()
    with np.errstate(over="ignore", invalid="ignore"):
        cr, ci, n_culled = _draw_c(mapd, rng, n)
        hor = np.full(cr.size, cap, dtype=np.int64)
        esc, det, ev1 = phase1_escape(mapd, cr, ci, hor, mapd["chunk"])
        t_ex, pin, evA = resolve_times(mapd, cr[esc], ci[esc], det[esc],
                                       want_points=True)
    nh = np.bincount(t_ex, minlength=cap + 1)[2:cap + 1].astype(np.float64)
    psum = np.bincount(t_ex, weights=pin.astype(np.float64),
                       minlength=cap + 1)[2:cap + 1]
    lev, p = level_law(nh, psum, CFG["level_alpha"],
                       CFG["level_tail_mass_frac"])
    return {
        "n_drawn": n, "n_culled": n_culled, "n_escaped": int(esc.sum()),
        "escape_frac": float(esc.sum()) / n,
        "sec": time.time() - t0, "iter_evals": ev1 + evA,
        "evals_per_draw": (ev1 + evA) / n,
        "n_h_at": {str(h): float(nh[h - 2]) for h in
                   (2, 10, 50, 100, 200, 400, 800, 1200, 1500) if h <= cap},
        "m_h_at": {str(h): float((psum / np.maximum(nh, 1))[h - 2])
                   for h in (2, 10, 50, 100, 200, 400, 800, 1200, 1500)
                   if h <= cap},
        "E_H_draw": float((lev * p).sum()),
        "p_max": float(p.max()), "p_min": float(p.min()),
        "levels": lev.tolist(), "p": p.tolist(),
    }


def tag_pilot() -> None:
    out = {"cfg": CFG, "pilots": {}}
    for map_name in MAPS3:
        rec = pilot_map(map_name, PILOT_N, CAP,
                        BASE3 + 7 + MAP_IDS[map_name])
        out["pilots"][map_name] = rec
        print(f"[pilot] {map_name}: esc={rec['escape_frac']:.3f} "
              f"E[H]={rec['E_H_draw']:.1f} "
              f"evals/draw={rec['evals_per_draw']:.1f} "
              f"sec={rec['sec']:.1f}", flush=True)
    with open(PILOT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("wrote", PILOT_JSON, flush=True)


def _pilots() -> dict:
    with open(PILOT_JSON, encoding="utf-8") as f:
        return json.load(f)["pilots"]


def tag_validate() -> None:
    recs = []
    # 1) S0 clone vs the study's own sample_uniform (same seed, same batches)
    for map_name in MAPS3:
        seed = BASE3 + 400 + MAP_IDS[map_name]
        r_study = cs.sample_uniform(map_name, SIZE, CAP, 250_000, seed,
                                    batch=200_000)
        r_probe = run_s0_probe(map_name, 250_000, seed, CAP, batch=200_000)
        tv = float(0.5 * np.abs(r_study["hist"].ravel()
                                - np.asarray(r_probe["hist"])).sum())
        recs.append({
            "check": "s0_clone_vs_study_sample_uniform", "map": map_name,
            "seed": seed, "budget": 250_000,
            "n_escaped_study": r_study["n_escaped"],
            "n_escaped_probe": r_probe["n_escaped"],
            "identical_escape_count":
                r_study["n_escaped"] == r_probe["n_escaped"],
            "tv_normalized_hist": tv,
            "mass_per_draw_study": r_study["total_mass"],
            "mass_per_draw_probe": r_probe["total_mass_per_draw"],
        })
        print(f"[validate] clone {map_name}: TV={tv:.3e} "
              f"esc_study={r_study['n_escaped']} "
              f"esc_probe={r_probe['n_escaped']}", flush=True)
    # 2) S3 unbiasedness at cap 40: high-precision S0 target + z-test using
    # S3's own seed spread (S3's variance premium means the S0-pair SE is not
    # the right scale for S3; the exactness is what is being checked here)
    for map_name in MAPS3:
        cap = 40
        pl = pilot_map(map_name, 100_000, cap,
                       BASE3 + 500 + MAP_IDS[map_name])
        lev = np.asarray(pl["levels"])
        p = np.asarray(pl["p"])
        ref = run_s0_probe(map_name, 8_000_000,
                           BASE3 + 550 + MAP_IDS[map_name], cap)
        tgt = np.asarray(ref.pop("hist")).reshape(SIZE, SIZE)
        roi, _ = roi_from_ref(np.load(
            os.path.join(DATA, f"ref_{map_name}_{CAP}.npz"))["raw"])
        # the cap-1500 ROI contains pixels a cap-40 orbit never visits;
        # restrict the bias mean to ROI pixels the target actually populates
        mask = roi & (tgt.ravel() > 0)

        def b_vs_tgt(hist2d: np.ndarray) -> float:
            return float(((hist2d.ravel()[mask] - tgt.ravel()[mask])
                          / tgt.ravel()[mask]).mean())

        b0 = []
        for s_idx in range(4):
            r = run_s0_probe(map_name, 2_000_000,
                             BASE3 + 600 + 10 * MAP_IDS[map_name] + s_idx,
                             cap)
            b0.append(b_vs_tgt(np.asarray(r.pop("hist")).reshape(SIZE, SIZE)))
        b3 = []
        for s_idx in range(6):
            r = run_s3(map_name, 2_000_000,
                       BASE3 + 650 + 10 * MAP_IDS[map_name] + s_idx,
                       p, lev, cap)
            b3.append(b_vs_tgt(np.asarray(r.pop("hist")).reshape(SIZE, SIZE)))
        b3m = float(np.mean(b3))
        sd3 = float(np.std(b3, ddof=1))
        z = b3m / (sd3 / math.sqrt(len(b3)))
        recs.append({
            "check": "s3_unbiased_cap40_ztest", "map": map_name,
            "cap_small": cap, "budget": 2_000_000, "n_S0_seeds": 4,
            "n_S3_seeds": 6, "n_mask_pixels": int(mask.sum()),
            "mask_rule": "study cap-1500 ROI ∩ (cap-40 S0@8M target > 0)",
            "target": "S0 @ 8M draws, cap 40 (shared target)",
            "b_S0_per_seed": b0, "b_S0_sd": float(np.std(b0, ddof=1)),
            "b_S3_per_seed": b3, "b_S3_mean": b3m, "b_S3_sd": sd3,
            "z_S3_vs_own_spread": z,
            "verdict_consistent_with_unbiased": abs(z) <= 3.0,
            "E_H_draw": pl["E_H_draw"],
        })
        print(f"[validate] cap40 {map_name}: b_S3={b3m:+.5f} sd={sd3:.5f} "
              f"z={z:+.2f} unbiased_consistent={abs(z) <= 3.0}", flush=True)
    with open(VALIDATE_JSON, "w", encoding="utf-8") as f:
        json.dump(recs, f, indent=2)
    print("wrote", VALIDATE_JSON, flush=True)


def tag_h2h() -> None:
    pilots = _pilots()
    for map_name in MAPS3:
        lev = np.asarray(pilots[map_name]["levels"])
        p = np.asarray(pilots[map_name]["p"])
        for rung_idx, budget in enumerate(LADDER):
            for s_idx in SEEDS:
                seed = seed_for(map_name, 0, rung_idx, s_idx)
                append_run(run_s0_probe(map_name, budget, seed))
                append_run(run_s3(map_name, budget, seed, p, lev))


def tag_s2() -> None:
    for map_name in MAPS3:
        for rung_idx, budget in enumerate(S2_BUDGETS):
            seed = (BASE3 + 300 + 50 * (3 * MAP_IDS[map_name] + CAP_IDS[CAP])
                    + rung_idx)
            key = (map_name, "S2", "study", budget, seed)
            if any((r["map"], r["estimator"], r["variant"], r["budget"],
                    r["seed"]) == key for r in load_runs()):
                print(f"[skip] {key}", flush=True)
                continue
            r = cs.sample_mh_mutation_stream(map_name, SIZE, CAP, budget,
                                             seed, chains=1024, step=0.02)
            rec = {
                "map": map_name, "cap": CAP, "estimator": "S2",
                "variant": "study", "budget": budget, "seed": seed,
                "size": SIZE, "evals": r["evals"], "ess": r["ess"],
                "acceptance": r["acceptance"], "n_states": r["n_states"],
                "chains": r["chains"], "steps": r["steps"],
                "sec": r["sec"], "iter_evals": None,
                "total_mass_per_draw": None,
            }
            rec.update(_ref_metrics(map_name, r["hist"].ravel()))
            append_run(rec)


def tag_extend() -> None:
    """Compute-matched S3 rungs: scale the top rung N so S3's measured sec
    (and separately iter_evals) matches S0's measured top rung."""
    runs = load_runs()
    pilots = _pilots()
    top = LADDER[-1]
    for map_name in MAPS3:
        s0_top = [r for r in runs if r["map"] == map_name
                  and r["estimator"] == "S0" and r["budget"] == top]
        s3_top = [r for r in runs if r["map"] == map_name
                  and r["estimator"] == "S3" and r["budget"] == top
                  and r["variant"] == "probe"]
        sec0 = float(np.mean([r["sec"] for r in s0_top]))
        sec3 = float(np.mean([r["sec"] for r in s3_top]))
        ev0 = float(np.mean([r["iter_evals"] for r in s0_top]))
        ev3 = float(np.mean([r["iter_evals"] for r in s3_top]))
        lev = np.asarray(pilots[map_name]["levels"])
        p = np.asarray(pilots[map_name]["p"])
        for kind, variant, n_ext in (
                (1, "extend_sec", int(top * sec0 / sec3)),
                (1, "extend_evals", int(top * ev0 / ev3))):
            n_ext = max(250_000, min(n_ext, 64_000_000))
            for s_idx in SEEDS:
                seed = seed_for(map_name, kind, 4, s_idx) \
                    + (0 if variant == "extend_sec" else 1)
                r = run_s3(map_name, n_ext, seed, p, lev)
                r["variant"] = variant
                r["matched_target"] = {
                    "rule": variant, "S0_top_sec_mean": sec0,
                    "S3_top_sec_mean": sec3, "S0_top_evals_mean": ev0,
                    "S3_top_evals_mean": ev3,
                }
                append_run(r)


def _fit(runs: list, map_name: str, estimator: str, variant: str) -> dict:
    """OLS of log(mean_rel_err) on log(budget): rung seed-means, plus a
    slope per seed across the rungs."""
    sel = [r for r in runs if r["map"] == map_name
           and r["estimator"] == estimator and r["variant"] == variant
           and r.get("mean_rel_err") is not None]
    by_n = {}
    for r in sel:
        by_n.setdefault(r["budget"], []).append(r)
    rungs = sorted(by_n)
    out = {"by_rung": []}
    for n in rungs:
        rr = by_n[n]
        out["by_rung"].append({
            "budget": n, "n_seeds": len(rr),
            "mean_rel_err_seedmean": float(np.mean(
                [r["mean_rel_err"] for r in rr])),
            "mean_rel_err_seedstd": (float(np.std(
                [r["mean_rel_err"] for r in rr], ddof=1))
                if len(rr) > 1 else None),
            "sec_seedmean": float(np.mean([r["sec"] for r in rr])),
            "iter_evals_seedmean": (float(np.mean([r["iter_evals"]
                                                   for r in rr]))
                                    if all(r.get("iter_evals") is not None
                                           for r in rr) else None),
        })
    if len(rungs) >= 2:
        sl, ic = ols_slope([math.log(n) for n in rungs],
                           [math.log(np.mean([r["mean_rel_err"]
                                              for r in by_n[n]]))
                            for n in rungs])
        out["slope_rungmeans"] = sl
        out["intercept_rungmeans"] = ic
    per_seed = []
    # replicate index = seed % 10 (seed rule: ...+10*rung_idx+seed_idx), since
    # the study-style seed value itself differs across rungs
    for s in sorted({r["seed"] % 10 for r in sel}):
        rr = sorted([r for r in sel if r["seed"] % 10 == s],
                    key=lambda r: r["budget"])
        if len(rr) >= 2:
            sl, _ = ols_slope([math.log(r["budget"]) for r in rr],
                              [math.log(r["mean_rel_err"]) for r in rr])
            per_seed.append(sl)
    if per_seed:
        out["slope_per_seed"] = per_seed
        out["slope_per_seed_mean"] = float(np.mean(per_seed))
        out["slope_per_seed_spread"] = (float(np.max(per_seed))
                                        - float(np.min(per_seed)))
    return out


def _eff_block(runs: list, map_name: str, estimator: str) -> dict:
    rr = [r for r in runs if r["map"] == map_name
          and r["estimator"] == estimator and r["variant"] == "probe"]
    by_n = {}
    for r in rr:
        by_n.setdefault(r["budget"], []).append(r)
    out = {}
    for n, group in sorted(by_n.items()):
        mr = np.array([r["mean_rel_err"] for r in group])
        ev = np.array([r["iter_evals"] for r in group], dtype=np.float64)
        sc = np.array([r["sec"] for r in group], dtype=np.float64)
        blk = {
            "n_seeds": len(group),
            "e_N": float((mr ** 2).mean() * n),
            "e_evals": float((mr ** 2).mean() * ev.mean()),
            "e_sec": float((mr ** 2).mean() * sc.mean()),
            "iter_evals_per_draw": float(ev.mean() / n),
            "sec_per_draw": float(sc.mean() / n),
            "mass_per_draw": float(np.mean([r["total_mass_per_draw"]
                                            for r in group])),
        }
        if estimator == "S3":
            blk.update({
                "contrib_frac": float(np.mean([r["contrib_frac"]
                                               for r in group])),
                "ess_w_mean": float(np.mean([r["ess_w"] for r in group])),
                "max_w_mean": float(np.mean([r["max_w"] for r in group])),
                "mean_H_drawn": float(np.mean([r["mean_H_drawn"]
                                               for r in group])),
            })
        out[str(n)] = blk
    return out


def tag_analyze() -> None:
    runs = load_runs()
    with open(PILOT_JSON, encoding="utf-8") as f:
        pilots = json.load(f)["pilots"]
    out = {"date": "2026-10-24", "cfg": CFG, "pilots": {
        m: {k: v for k, v in pilots[m].items() if k not in ("levels", "p")}
        for m in MAPS3}, "cells": {}}
    audited = {}
    for m in MAPS3:
        with open(os.path.join(RES, f"cell_{m}_{CAP}.json"),
                  encoding="utf-8") as f:
            cell = json.load(f)
        audited[m] = {
            "source": (f"results/cell_{m}_{CAP}.json (audited 2026-10-21; "
                       "cited for context, not recomputed by this probe)"),
            "slopes": cell["convergence_loglog_slopes"],
            "bias_top_rung": {
                "b_S2": cell["bias_check_top_rung"]["b_S2_top"],
                "b_S0_study": cell["bias_check_top_rung"]["b_S0_study"],
                "b_S0_control": cell["bias_check_top_rung"]["b_S0_control"],
                "SE_b": cell["bias_check_top_rung"]["SE_b_from_S0_pair"],
            },
            "S0_mean_rel_by_budget": {
                str(st["budget"]): st["mean_rel_err"]
                for st in cell["runs"][0]["by_budget"] if st},
        }
    out["audited_context"] = audited
    out["validate"] = json.load(open(VALIDATE_JSON, encoding="utf-8")) \
        if os.path.exists(VALIDATE_JSON) else None

    top = LADDER[-1]
    for m in MAPS3:
        cell = {"convergence": {}, "bias_se_top_rung": {},
                "matched_compute": {}, "variance_cost": {},
                "mass_check": {}}
        for est in ("S0", "S3"):
            cell["convergence"][est] = _fit(runs, m, est, "probe")
            cell["variance_cost"][est] = _eff_block(runs, m, est)
        s2_fit = _fit(runs, m, "S2", "study")
        if s2_fit["by_rung"]:
            cell["convergence"]["S2_this_session"] = s2_fit
        # bias / SE at the top rung (study machinery: SE from the S0 seed pair)
        s0 = sorted([r for r in runs if r["map"] == m
                     and r["estimator"] == "S0" and r["budget"] == top],
                    key=lambda r: r["seed"])
        s3 = sorted([r for r in runs if r["map"] == m
                     and r["estimator"] == "S3" and r["budget"] == top
                     and r["variant"] == "probe"], key=lambda r: r["seed"])
        b0 = [r["b_signed"] for r in s0]
        se_b = abs(b0[0] - b0[1]) / math.sqrt(2.0)
        b3s = [r["b_signed"] for r in s3]
        b3m = float(np.mean(b3s))
        cell["bias_se_top_rung"] = {
            "rule": "b(X)=mean_ROI[(X_p-ref_p)/ref_p]; "
                    "SE(b)=|b(S0_seed0)-b(S0_seed1)|/sqrt(2) from the "
                    "same-budget S0 pair (study's control-pair machinery)",
            "b_S0_per_seed": b0, "b_S0_mean": float(np.mean(b0)),
            "SE_b_from_S0_pair": se_b,
            "S0_abs_b_over_SE": (abs(float(np.mean(b0))) / se_b
                                 if se_b > 0 else None),
            "b_S3_per_seed": b3s, "b_S3_mean": b3m,
            "S3_abs_b_over_SE": (abs(b3m) / se_b if se_b > 0 else None),
            "S3_no_visible_skew": abs(b3m) <= 3.0 * se_b,
        }
        s2t = [r for r in runs if r["map"] == m and r["estimator"] == "S2"
               and r["budget"] == top]
        if s2t:
            cell["bias_se_top_rung"]["b_S2_this_session"] = s2t[0]["b_signed"]
            cell["bias_se_top_rung"]["S2_abs_b_over_SE_this_session"] = (
                abs(s2t[0]["b_signed"]) / se_b if se_b > 0 else None)
            cell["bias_se_top_rung"]["S2_skew_vs_3SE_this_session"] = (
                abs(s2t[0]["b_signed"]) > 3.0 * se_b)
        # mass check (estimand identity: E[weighted mass per draw] equal)
        cell["mass_check"] = {
            "S0_points_per_draw": cell["variance_cost"]["S0"][str(top)][
                "mass_per_draw"],
            "S3_weighted_per_draw": cell["variance_cost"]["S3"][str(top)][
                "mass_per_draw"],
            "ref_points_per_draw": json.load(open(
                os.path.join(RES, f"run_{m}_{CAP}_S0_40000000_ref.json"),
                encoding="utf-8"))["raw_total_points"] / 40_000_000,
        }
        mc = cell["mass_check"]
        mc["ratio_S3_over_S0"] = (mc["S3_weighted_per_draw"]
                                  / mc["S0_points_per_draw"])
        # matched-compute extend rungs vs the S0 top rung
        ext = [r for r in runs if r["map"] == m and r["estimator"] == "S3"
               and r["variant"].startswith("extend")]
        if ext:
            mr0 = float(np.mean([r["mean_rel_err"] for r in s0]))
            sc0 = float(np.mean([r["sec"] for r in s0]))
            ev0 = float(np.mean([r["iter_evals"] for r in s0]))
            for var in ("extend_sec", "extend_evals"):
                gg = [r for r in ext if r["variant"] == var]
                if not gg:
                    continue
                cell["matched_compute"][var] = {
                    "N_ext": gg[0]["budget"],
                    "S3_mean_rel": float(np.mean([r["mean_rel_err"]
                                                  for r in gg])),
                    "S3_sec_mean": float(np.mean([r["sec"] for r in gg])),
                    "S3_evals_mean": float(np.mean([r["iter_evals"]
                                                    for r in gg])),
                    "S0_top_mean_rel": mr0, "S0_top_sec": sc0,
                    "S0_top_evals": ev0,
                    "rel_ratio_S3_over_S0": float(
                        np.mean([r["mean_rel_err"] for r in gg])) / mr0,
                    "sec_ratio": float(np.mean([r["sec"] for r in gg])) / sc0,
                    "evals_ratio": float(np.mean([r["iter_evals"]
                                                  for r in gg])) / ev0,
                }
        out["cells"][m] = cell

    # ---------------- verdict (lane rule) ----------------
    verdict = {
        "rule": "licensed iff S3 measurably improves slope toward -0.5 "
                "and/or cuts bias/SE >=5x at matched budget (vs the study "
                "baselines; S2 is the only baseline with a bias/SE excess); "
                "refuted if no improvement or variance explodes",
        "variance_explosion_rule": "exploded iff matched-compute L1 ratio "
                                   "> 1 on BOTH sec- and evals-matched AND "
                                   "e_N ratio (S3/S0) >= 100",
        "per_map": {},
    }
    for m in MAPS3:
        cell = out["cells"][m]
        s0s = cell["convergence"]["S0"].get("slope_rungmeans")
        s3s = cell["convergence"]["S3"].get("slope_rungmeans")
        s2s = cell["convergence"].get("S2_this_session", {}).get(
            "slope_rungmeans")
        crit_slope = (s3s is not None and s0s is not None
                      and abs(s3s + 0.5) < abs(s0s + 0.5))
        bs = cell["bias_se_top_rung"]
        crit_bias = None
        if bs.get("S2_abs_b_over_SE_this_session") is not None:
            crit_bias = (bs["S3_no_visible_skew"]
                         and bs["S2_abs_b_over_SE_this_session"] >= 5.0
                         * max(bs["S3_abs_b_over_SE"], 1e-12))
        mc = cell["matched_compute"]
        r_sec = mc.get("extend_sec", {}).get("rel_ratio_S3_over_S0")
        r_ev = mc.get("extend_evals", {}).get("rel_ratio_S3_over_S0")
        e_n = (cell["variance_cost"]["S3"][str(top)]["e_N"]
               / cell["variance_cost"]["S0"][str(top)]["e_N"])
        exploded = (e_n >= 100.0 and r_sec is not None and r_sec > 1.0
                    and (r_ev is None or r_ev > 1.0))
        improved = bool(crit_slope) or bool(crit_bias)
        verdict["per_map"][m] = {
            "slope_S0": s0s, "slope_S3": s3s,
            "slope_S2_this_session": s2s,
            "slope_S3_closer_to_minus_half_than_S0": crit_slope,
            "bias_cut_5x_vs_S2": crit_bias,
            "matched_sec_rel_ratio": r_sec, "matched_evals_rel_ratio": r_ev,
            "e_N_ratio_S3_over_S0": e_n,
            "variance_exploded": exploded,
            "improvement": improved, "licensed": improved and not exploded,
        }
    maps_v = list(verdict["per_map"].values())
    verdict["licensed"] = all(v["licensed"] for v in maps_v)
    verdict["any_map_licensed"] = any(v["licensed"] for v in maps_v)
    verdict["verdict_label"] = ("licensed" if verdict["licensed"] else
                                ("refuted" if not any(v["improvement"]
                                                      for v in maps_v)
                                 else "mixed — see per_map"))
    out["verdict"] = verdict

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("wrote", OUT_JSON, flush=True)
    print(json.dumps(verdict, indent=2), flush=True)


def main() -> None:
    tag = sys.argv[1]
    {"pilot": tag_pilot, "validate": tag_validate, "h2h": tag_h2h,
     "s2": tag_s2, "extend": tag_extend, "analyze": tag_analyze}[tag]()


if __name__ == "__main__":
    main()
