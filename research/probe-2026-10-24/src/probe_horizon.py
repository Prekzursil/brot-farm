"""Probe — horizon-truncation lane: does doubling the iteration horizon H
shrink the structured bias of the forward orbit-density histogram?

Tests the paper's limitation hypothesis ("Caps bias against slow escapers",
paper.tex ~:1011: every channel cap excludes late escapers; the reference
suffers the same truncation) by measuring the horizon-truncation structure
DIRECTLY, with the study's own estimator (S0 sample_uniform), the study's own
ROI binning, and seeds fixed ACROSS horizons so that the per-bin difference
between horizons is pure structure (identical c-draws: same seed, same batch
schedule, deterministic cull, escape_mask consumes no RNG).

Design (H = 400 = the audited mid channel; 2H = 800; refH = 1600 = 4H):
  1. S0 renders at cap in {H, 2H, refH} x duplicate seeds {a, b}, same N,
     same batch -> raw_{map}_{cap}_{seed}; identical-draw property verified
     pointwise (raw_H <= raw_2H <= raw_refH up to fp reordering).
  2. Deposit pass: the study's own conv_samplers.trace_orbits, batch-wise,
     replaying the exact S0 ensemble (same seed + batch schedule; the trace
     consumes no RNG) and accumulating per-bin (count, escape-time sum) plus
     the FULL deposition of the late-escaper cohorts (H,refH] and (2H,refH] —
     full because a cap-H render excludes those orbits entirely, so the
     measured horizon difference is the cohort's whole deposition.
  3. Metrics per map, ROI = the audited cap-400 cell ROI (analyze.roi_from_ref
     on data/ref_{map}_400.npz, the exact audited mask):
     - raw missing mass (points/seed units): d_H = raw_refH - raw_H,
       d_2H = raw_refH - raw_2H; mean signed/abs over ROI (nonneg by
       construction), totals, ROI share, shrink ratio d_2H/d_H.
     - audited-metric (normalized) companions: b = mean_ROI[(hat-ref)/ref]
       with ref = hat_refH, mean |rel|; duplicate-seed SE at each horizon in
       the study's convention SE = |b_a - b_b|/sqrt(2) (cap H additionally
       cross-checked against the audited 40M reference).
     - boundary localization: boundary score per ROI pixel = visitor-mean
       escape time (tsum/cnt at cap refH); terciles of score vs per-bin
       missing mass (mean + mass share + Spearman); prediction: shrinkage
       concentrated in the top (boundary-adjacent) tercile.
     - cohort decomposition: d_H = full deposition of (H,2H] escapers + full
       deposition of (2H,refH] escapers; the latter over the former's sum is
       the predicted raw shrink ratio.
  4. Secondary (audited-bias-specific): S2 (chains=1024, step=0.02, the
     study's config) at cap H and 2H: does |b(S2)| shrink with the horizon?

Usage: python probe_horizon.py [smoke|full]   (smoke = N=200k mechanics check)
Output: experiments/results/probe_horizon.json (written after every stage;
        status "ok" only if every stage completed; fail-closed otherwise).
"""

from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import conv_samplers as cs  # noqa: E402  (imports follow the sys.path bootstrap above)
from analyze import roi_from_ref, rel_stats, signed_mean  # noqa: E402
from conv_maps import MAPS  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, ".."))
RES = os.path.join(ROOT, "results")
DATA = os.path.join(ROOT, "data")

MODE = sys.argv[1] if len(sys.argv) > 1 else "full"
N = 200_000 if MODE == "smoke" else 4_000_000
H = 400
TWO_H = 800
REF_H = 1600
CAPS = (H, TWO_H, REF_H)
SIZE = 512
S0_BATCH = 50_000  # == TRACE_BATCH, fixed across caps: identical c-draws at
# every horizon, AND the deposit pass (trace_orbits consumes
# no RNG) replays the exact S0 seed sequence -> the band
# decomposition is an identity check, not an estimate
TRACE_BATCH = 50_000
S2_CHAINS = 1024
S2_STEP = 0.02
MAP_LIST = ("mandel", "cosmut")
SEED_BASE = 867_530_900  # probe-private; disjoint from the study's 20261xxx seeds
SEEDS = {  # per map: a/b = S0 duplicate pair, s2 = S2 arm
    m: {
        "a": SEED_BASE + 10 * i,
        "b": SEED_BASE + 10 * i + 1,
        "s2": SEED_BASE + 10 * i + 2,
    }
    for i, m in enumerate(sorted(MAP_LIST))
}
AUDITED_COMMIT = "4d87ef33ca50b1b33c6f5736bd59bad94bd54e70"

OUT = os.path.join(RES, "probe_horizon.json")


def log(msg: str) -> None:
    print(f"[{MODE}] {time.strftime('%H:%M:%S')} {msg}", flush=True)


def save(state: dict) -> None:
    state["written_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def repo_commit() -> str:
    import subprocess

    repo = os.environ.get(
        "BROT_FARM_REPO",
        r"C:\Users\Prekzursil\.zcode\workspace"
        r"\draft-56daea68-c3bd-4ae2-9987-e036cc496291\brot-farm",
    )
    try:
        out = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception as e:  # fail-open: recorded as unavailable, never guessed
        return f"unavailable: {e}"


def s0_run(map_name: str, cap: int, seed: int) -> dict:
    r = cs.sample_uniform(map_name, SIZE, cap, N, seed, batch=S0_BATCH)
    return {
        "raw": r["hist_raw"],
        "n_escaped": r["n_escaped"],
        "n_culled": r["n_culled"],
        "raw_total": r["hist_raw_total"],
        "sec": r["sec"],
    }


def fin(x: float, what: str) -> float:
    """Fail-closed guard: headline metrics must be finite (an empty ROI bin in
    the reference at probe-scale N would surface here as inf/nan). Smoke mode
    only warns (its 200k budget leaves ~1% of top-decile ROI bins empty); the
    full run enforces."""
    v = float(x)
    if not np.isfinite(v):
        msg = f"non-finite metric {what}: {v}"
        if MODE == "full":
            raise ValueError(msg)
        print(f"[smoke] WARNING {msg}", flush=True)
    return v


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    def ranks(v: np.ndarray) -> np.ndarray:
        order = np.argsort(v, kind="mergesort")
        r = np.empty(v.size, dtype=np.float64)
        r[order] = np.arange(v.size, dtype=np.float64)
        # average ties (continuous data: ties negligible, handled anyway)
        sv = v[order]
        i = 0
        while i < sv.size:
            j = i
            while j + 1 < sv.size and sv[j + 1] == sv[i]:
                j += 1
            if j > i:
                r[order[i : j + 1]] = (i + j) / 2.0
            i = j + 1
        return r

    rx, ry = ranks(x), ranks(y)
    if rx.std() == 0 or ry.std() == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def deposit_pass(map_name: str, seed: int) -> dict:
    """Study's trace_orbits, batch-wise, accumulating per-bin deposition:
    cnt/tsum over all escaper points, plus the FULL deposition of the two
    late-escaper cohorts (full_C1: escape time in (H, refH], full_C2: in
    (2H, refH]) — full, because a cap-H render excludes these orbits
    entirely, so the measured horizon difference d_H is the cohort's whole
    deposition, head included. Escaper semantics identical to
    conv_samplers.trace_orbits (plot z before stepping; escape-check after
    stepping; only escapers' points kept; in-frame only)."""
    mapd = MAPS[map_name]
    W = Hs = SIZE
    x0, x1, y0, y1 = mapd["samp"]
    rng = np.random.default_rng(seed)
    cnt = np.zeros(W * Hs, dtype=np.float64)
    tsum = np.zeros(W * Hs, dtype=np.float64)
    full_c1 = np.zeros(W * Hs, dtype=np.float64)
    full_c2 = np.zeros(W * Hs, dtype=np.float64)
    n_c1 = 0
    n_c2 = 0
    t0 = time.time()
    done = 0
    with np.errstate(over="ignore", invalid="ignore"):
        while done < N:
            nb = min(TRACE_BATCH, N - done)
            cr = rng.uniform(x0, x1, nb)
            ci = rng.uniform(y0, y1, nb)
            if mapd["cull"] is not None:
                keep = ~mapd["cull"](cr, ci)
                cr, ci = cr[keep], ci[keep]
            times, cells = cs.trace_orbits(mapd, cr, ci, REF_H, W, Hs)
            times = np.asarray(times)
            lens = np.fromiter(
                (c.size for c in cells), dtype=np.int64, count=len(cells)
            )
            esc = lens > 0
            long_ix = np.nonzero(esc & (times > H))[0]
            # bulk path: orbits with 0 < t <= H contribute cnt+tsum only
            bulk = np.nonzero(esc & (times <= H))[0]
            if bulk.size:
                cells_bulk = np.concatenate([cells[k] for k in bulk])
                cnt += np.bincount(cells_bulk, minlength=W * Hs)
                tsum += np.bincount(
                    cells_bulk,
                    weights=np.repeat(times[bulk].astype(np.float64), lens[bulk]),
                    minlength=W * Hs,
                )
            for k in long_ix:
                t = int(times[k])
                ck = cells[k]
                # bincount, not fancy-index +=: an orbit may revisit the same
                # bin many times (boundary hovering), and arr[idx] += 1 drops
                # duplicate indices
                cnt += np.bincount(ck, minlength=W * Hs)
                tsum += np.bincount(
                    ck, weights=np.full(ck.size, float(t)), minlength=W * Hs
                )
                if t > H:
                    full_c1 += np.bincount(ck, minlength=W * Hs)
                    n_c1 += 1
                    if t > TWO_H:
                        full_c2 += np.bincount(ck, minlength=W * Hs)
                        n_c2 += 1
            done += nb
            if done % (TRACE_BATCH * 10) == 0 or done == N:
                log(f"  deposit {map_name}: {done}/{N}")
    return {
        "cnt": cnt,
        "tsum": tsum,
        "full_c1": full_c1,
        "full_c2": full_c2,
        "n_c1": n_c1,
        "n_c2": n_c2,
        "sec": time.time() - t0,
    }


def roi_metrics(dmap: np.ndarray, roi: np.ndarray) -> dict:
    d = dmap.ravel()[roi]
    return {
        "mean_signed": float(d.mean()),
        "mean_abs": float(np.abs(d).mean()),
        "total": float(d.sum()),
    }


def main() -> None:
    state: dict = {
        "lane": "numeric-2-horizon-truncation",
        "mode": MODE,
        "status": "running",
        "date": time.strftime("%Y-%m-%d"),
        "config": {
            "maps": list(MAP_LIST),
            "H": H,
            "twoH": TWO_H,
            "refH": REF_H,
            "N": N,
            "size": SIZE,
            "s0_batch": S0_BATCH,
            "s0_batch_note": "batch = trace batch, fixed across caps and "
            "seeds: identical c-draws at every horizon; "
            "deposit pass replays the exact S0 ensemble",
            "trace_batch": TRACE_BATCH,
            "s2": {"chains": S2_CHAINS, "step": S2_STEP},
            "seeds": SEEDS,
            "seed_base": SEED_BASE,
            "roi_source": "data/ref_{map}_400.npz raw counts (audited 40M ref)",
            "roi_rule": "top decile of positive-count pixels, count >= k-th "
            "largest (analyze.roi_from_ref, audited convention)",
            "audited_commit": AUDITED_COMMIT,
            "repo_commit_head": repo_commit(),
            "python": sys.version.split()[0],
            "numpy": np.__version__,
        },
        "maps": {},
        "errors": [],
    }
    save(state)

    # ROI masks from the audited cap-400 references (+ audited anchor values)
    rois: dict[str, np.ndarray] = {}
    aud_refs: dict[str, np.ndarray] = {}
    for m in MAP_LIST:
        with np.load(os.path.join(DATA, f"ref_{m}_400.npz")) as z:
            raw_aud, norm_aud = z["raw"], z["normalized"]
        roi, info = roi_from_ref(raw_aud)
        rois[m] = roi
        aud_refs[m] = norm_aud
        with open(os.path.join(RES, f"cell_{m}_400.json"), encoding="utf-8") as f:
            cell = json.load(f)
        state["maps"][m] = {
            "roi": info,
            "audited_cell_400": {
                "b_S2_top": cell["bias_check_top_rung"]["b_S2_top"],
                "b_S0_study": cell["bias_check_top_rung"]["b_S0_study"],
                "b_S0_control": cell["bias_check_top_rung"]["b_S0_control"],
                "SE_b": cell["bias_check_top_rung"]["SE_b_from_S0_pair"],
                "escape_fraction": cell["reference"]["escape_fraction"],
            },
        }
        log(f"ROI {m}: {info['roi_pixels']} px, thresh {info['threshold_count']}")
    save(state)

    for m in MAP_LIST:
        log(f"=== map {m} ===")
        roi = rois[m]
        seeds = SEEDS[m]
        blk = state["maps"][m]
        try:
            # ---- S0 renders, duplicate seeds x 3 horizons (identical draws)
            runs: dict[tuple[int, str], dict] = {}
            for cap in CAPS:
                for sk in ("a", "b"):
                    r = s0_run(m, cap, seeds[sk])
                    runs[(cap, sk)] = r
                    log(
                        f"S0 {m} cap={cap} seed={sk} esc={r['n_escaped']} "
                        f"sec={r['sec']:.1f}"
                    )
            blk["runs"] = {
                f"cap{cap}_{sk}": {
                    "n_escaped": runs[(cap, sk)]["n_escaped"],
                    "n_culled": runs[(cap, sk)]["n_culled"],
                    "raw_total": runs[(cap, sk)]["raw_total"],
                    "sec": runs[(cap, sk)]["sec"],
                    "seed": seeds[sk],
                }
                for cap in CAPS
                for sk in ("a", "b")
            }
            raw = {k: v["raw"] for k, v in runs.items()}

            # identical-draw / dominance check: raw_H <= raw_2H <= raw_refH
            viol = max(
                float(np.max(raw[(H, "a")] - raw[(TWO_H, "a")])),
                float(np.max(raw[(TWO_H, "a")] - raw[(REF_H, "a")])),
            )
            scale = float(np.max(raw[(REF_H, "a")]))
            blk["dominance_check"] = {
                "max_violation_rawH_minus_raw2H": viol,
                "relative_to_max_bin": viol / scale,
                "note": "same seed + same batch schedule => identical c-draws; "
                "per-bin dominance must hold up to fp reordering",
            }

            # ---- escape fractions (same-seed ensemble)
            n = N
            f = {cap: runs[(cap, "a")]["n_escaped"] / n for cap in CAPS}
            blk["escape_fractions_seed_a"] = {
                "f_at_H": f[H],
                "f_at_2H": f[TWO_H],
                "f_at_refH": f[REF_H],
                "alive_at_H": 1.0 - f[H],
                "new_escapers_(H,2H]": f[TWO_H] - f[H],
                "new_escapers_(2H,refH]": f[REF_H] - f[TWO_H],
                "alive_at_refH": 1.0 - f[REF_H],
                "denominator": "n_drawn incl culled (study convention)",
            }

            # ---- raw truncation (primary), ROI-restricted
            d_H = raw[(REF_H, "a")] - raw[(H, "a")]
            d_2H = raw[(REF_H, "a")] - raw[(TWO_H, "a")]
            mH, m2H = roi_metrics(d_H, roi), roi_metrics(d_2H, roi)
            glob_H = float(d_H.sum())
            # duplicate-seed noise for the raw missing-mass statistic (cap H):
            # |missing(a) - missing(b)| / sqrt(2), each vs the common refH
            d_H_b = raw[(REF_H, "b")] - raw[(H, "b")]
            d_2H_b = raw[(REF_H, "b")] - raw[(TWO_H, "b")]
            se_mean_H = abs(
                roi_metrics(d_H, roi)["mean_signed"]
                - roi_metrics(d_H_b, roi)["mean_signed"]
            ) / np.sqrt(2)
            se_mean_2H = abs(
                m2H["mean_signed"] - roi_metrics(d_2H_b, roi)["mean_signed"]
            ) / np.sqrt(2)
            blk["truncation_raw_roi"] = {
                "missing_at_H": mH,
                "missing_at_2H": m2H,
                "missing_at_H_seed_b": roi_metrics(d_H_b, roi),
                "global_total_missing_H": glob_H,
                "roi_share_of_missing_H": mH["total"] / glob_H,
                "shrink_ratio_raw_2H_over_H": (
                    m2H["mean_signed"] / mH["mean_signed"]
                    if mH["mean_signed"]
                    else None
                ),
                "SE_mean_missing_H_duppair": se_mean_H,
                "SE_mean_missing_2H_duppair": se_mean_2H,
                "bias_over_SE_H": (
                    mH["mean_signed"] / se_mean_H if se_mean_H > 0 else None
                ),
                "bias_over_SE_2H": (
                    m2H["mean_signed"] / se_mean_2H if se_mean_2H > 0 else None
                ),
            }

            # ---- normalized (audited-metric) companions, ref = hat_refH
            hat = {
                (cap, sk): runs[(cap, sk)]["raw"] / runs[(cap, sk)]["raw_total"]
                for cap in CAPS
                for sk in ("a", "b")
            }
            ref_a, ref_b = hat[(REF_H, "a")], hat[(REF_H, "b")]
            b_H = fin(signed_mean(hat[(H, "a")], ref_a, roi), "b_H")
            b_2H = fin(signed_mean(hat[(TWO_H, "a")], ref_a, roi), "b_2H")
            b_H_b = fin(signed_mean(hat[(H, "b")], ref_b, roi), "b_H_seed_b")
            b_2H_b = fin(signed_mean(hat[(TWO_H, "b")], ref_b, roi), "b_2H_b")
            se_b_H = abs(b_H - b_H_b) / np.sqrt(2)
            se_b_2H = abs(b_2H - b_2H_b) / np.sqrt(2)
            blk["truncation_norm_roi"] = {
                "b_H": b_H,
                "b_2H": b_2H,
                "b_H_seed_b": b_H_b,
                "b_2H_seed_b": b_2H_b,
                "mean_abs_H": fin(
                    rel_stats(hat[(H, "a")], ref_a, roi)["mean_rel_err"], "mean_abs_H"
                ),
                "mean_abs_2H": fin(
                    rel_stats(hat[(TWO_H, "a")], ref_a, roi)["mean_rel_err"],
                    "mean_abs_2H",
                ),
                "SE_b_H_duppair": se_b_H,
                "SE_b_2H_duppair": se_b_2H,
                "bias_over_SE_H": (abs(b_H) / se_b_H if se_b_H > 0 else None),
                "bias_over_SE_2H": (abs(b_2H) / se_b_2H if se_b_2H > 0 else None),
                "shrink_ratio_abs_2H_over_H": (abs(b_2H) / abs(b_H) if b_H else None),
            }

            # ---- anchor: my S0@4M/cap-400 vs the audited 40M reference
            anch_b_a = signed_mean(hat[(H, "a")], aud_refs[m], roi)
            anch_b_b = signed_mean(hat[(H, "b")], aud_refs[m], roi)
            blk["anchor_vs_audited_40M"] = {
                "b_S0_4M_seed_a": anch_b_a,
                "b_S0_4M_seed_b": anch_b_b,
                "SE_b_duppair": abs(anch_b_a - anch_b_b) / np.sqrt(2),
                "mean_rel_err_seed_a": rel_stats(hat[(H, "a")], aud_refs[m], roi)[
                    "mean_rel_err"
                ],
                "note": "comparable to the audited cap-400 S0 top-rung run",
            }

            # ---- S2 arm (secondary; study config). The audited b(S2) is
            # S2 vs the SAME-cap S0 reference — the horizon-matched
            # comparison below is against hat_cap (seed a), not refH, so the
            # shrink ratio isolates the horizon dependence of the audited
            # bias rather than mixing in the truncation offset itself.
            s2_blk: dict = {}
            for cap in (H, TWO_H):
                r = cs.sample_mh_mutation_stream(
                    m, SIZE, cap, N, seeds["s2"], chains=S2_CHAINS, step=S2_STEP
                )
                b_match = fin(
                    signed_mean(r["hist"], hat[(cap, "a")], roi),
                    f"s2_b_vs_cap{cap}_ref",
                )
                b_vs = signed_mean(r["hist"], aud_refs[m], roi) if cap == H else b_match
                s2_blk[f"cap{cap}"] = {
                    "b_vs_matching_cap_S0_ref": b_match,
                    "ref_used": (
                        f"S0 seed a @cap{cap} (normalized)"
                        if cap != H
                        else "S0 seed a @cap400 (normalized); also vs "
                        "audited 40M ref @cap400 for audited-table "
                        "comparability"
                    ),
                    "b_vs_audited_40M_cap400": (b_vs if cap == H else None),
                    "acceptance": r["acceptance"],
                    "ess": r["ess"],
                    "n_states": r["n_states"],
                    "steps": r["steps"],
                    "sec": r["sec"],
                    "seed": seeds["s2"],
                }
                log(f"S2 {m} cap={cap} b_vs_capref={b_match:+.4f} sec={r['sec']:.1f}")
            s2_blk["SE_b_H_from_S0_duppair_vs_audref"] = abs(
                anch_b_a - anch_b_b
            ) / np.sqrt(2)
            s2_blk["bias_over_SE_H"] = (
                abs(s2_blk[f"cap{H}"]["b_vs_matching_cap_S0_ref"])
                / s2_blk["SE_b_H_from_S0_duppair_vs_audref"]
            )
            s2_blk["SE_b_2H_duppair"] = se_b_2H
            s2_blk["bias_over_SE_2H"] = (
                abs(s2_blk[f"cap{TWO_H}"]["b_vs_matching_cap_S0_ref"]) / se_b_2H
            )
            s2_blk["shrink_ratio_abs_b_2H_over_H"] = abs(
                s2_blk[f"cap{TWO_H}"]["b_vs_matching_cap_S0_ref"]
            ) / abs(s2_blk[f"cap{H}"]["b_vs_matching_cap_S0_ref"])
            blk["s2_arm"] = s2_blk

            # ---- deposit pass (boundary localization + band decomposition)
            dep = deposit_pass(m, seeds["a"])
            cnt = dep["cnt"]
            score = np.zeros_like(cnt)
            pos = cnt > 0
            score[pos] = dep["tsum"][pos] / cnt[pos]
            dH_dep = dep["full_c1"]  # predicted d_H: full (H,refH] cohort
            d2H_dep = dep["full_c2"]  # predicted d_2H: full (2H,refH] cohort
            roi_pos = (roi & pos.ravel()).reshape(SIZE, SIZE)
            sc = score.reshape(SIZE, SIZE)

            def tercile_stats(dmap: np.ndarray) -> list[dict]:
                s_vals = sc[roi_pos]
                d_vals = dmap[roi_pos]
                q1, q2 = np.percentile(s_vals, [100 / 3, 200 / 3])
                out = []
                for name, mask in (
                    ("bottom", s_vals <= q1),
                    ("mid", (s_vals > q1) & (s_vals <= q2)),
                    ("top", s_vals > q2),
                ):
                    dd = d_vals[mask]
                    out.append(
                        {
                            "band": name,
                            "pixels": int(mask.sum()),
                            "mean_score": float(s_vals[mask].mean()),
                            "mean_missing": float(dd.mean()),
                            "mass_share": float(dd.sum() / d_vals.sum()),
                            "pixel_share": float(mask.sum() / mask.size),
                        }
                    )
                return out

            blk["deposit"] = {
                "seed": seeds["a"],
                "cap": REF_H,
                "sec": dep["sec"],
                "identity_check": {
                    "corr_pred_dH_vs_meas_dH_roi": float(
                        np.corrcoef(dH_dep.ravel()[roi], d_H.ravel()[roi])[0, 1]
                    ),
                    "sum_ratio_pred_over_meas_dH": (
                        float(dH_dep.ravel()[roi].sum() / d_H.ravel()[roi].sum())
                        if d_H.ravel()[roi].sum()
                        else None
                    ),
                    "corr_pred_d2H_vs_meas_d2H_roi": float(
                        np.corrcoef(d2H_dep.ravel()[roi], d_2H.ravel()[roi])[0, 1]
                    ),
                    "sum_ratio_pred_over_meas_d2H": (
                        float(d2H_dep.ravel()[roi].sum() / d_2H.ravel()[roi].sum())
                        if d_2H.ravel()[roi].sum()
                        else None
                    ),
                    "note": "deposit pass replays the exact S0 ensemble (same "
                    "seed/batch schedule; trace consumes no RNG), so "
                    "pred ~= measured up to the escape_mask chunk-32 "
                    "checkpoint convention at the band edges "
                    "(escape_mask@400 classifies detection steps "
                    "<=384, the trace band uses the per-step time) "
                    "and fp accumulation order",
                },
                "cohort_sizes_seed_a": {
                    "n_cohort_(H,refH]": dep["n_c1"],
                    "n_cohort_(2H,refH]": dep["n_c2"],
                    "fraction_(H,refH]_of_drawn": dep["n_c1"] / N,
                    "fraction_(2H,refH]_of_drawn": dep["n_c2"] / N,
                },
                "band_decomposition_roi": {
                    "cohort_(H,2H]_mean_missing": float(
                        (dH_dep - d2H_dep).ravel()[roi].mean()
                    ),
                    "cohort_(H,2H]_total": float((dH_dep - d2H_dep).ravel()[roi].sum()),
                    "cohort_(2H,refH]_total": float(d2H_dep.ravel()[roi].sum()),
                    "predicted_shrink_ratio_2H_over_H": (
                        float(d2H_dep.ravel()[roi].sum() / dH_dep.ravel()[roi].sum())
                        if dH_dep.ravel()[roi].sum()
                        else None
                    ),
                },
                "terciles_missing_H": tercile_stats(d_H),
                "terciles_missing_2H": tercile_stats(d_2H),
                "spearman_score_vs_missing_H": spearman(sc[roi_pos], d_H[roi_pos]),
                "spearman_score_vs_missing_2H": spearman(sc[roi_pos], d_2H[roi_pos]),
                "roi_pixels_with_zero_visits": int((~roi_pos).sum()),
            }
            state["status"] = f"ok_through_deposit:{m}"
        except Exception as e:  # fail-closed: record and stop this map's lane
            import traceback

            blk["error"] = f"{type(e).__name__}: {e}"
            blk["traceback"] = traceback.format_exc()
            state["errors"].append(f"{m}: {blk['error']}")
            state["status"] = f"failed:{m}"
            save(state)
            raise
        save(state)

    state["status"] = "ok" if not state["errors"] else f"failed:{state['errors']}"
    save(state)
    log(f"COMPLETE status={state['status']}")


if __name__ == "__main__":
    main()
