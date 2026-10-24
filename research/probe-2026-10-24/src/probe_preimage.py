"""Probe: the bridge test — preimage-sampling histogram vs forward
orbit-density histogram (the comparison the field has never run, per
receipts/2026-10-24-probe-bridge.md).

Backward candidate: random inverse iteration (IIM) of f(z) = z^power + c with
FIXED c, uniform branch choice, generic start, burn-in, 4096 chains; visits
binned on the study's 512x512 ROI grid.  For connected Julia sets this
samples the measure of maximal entropy = harmonic measure from infinity
(Brolin 1965; Binder-Makarov-Smirnov Duke 2003).

Forward reference: the study's own orbit-density estimator.
  * julia bridge  : brot_farm.py BY_NAME["julia"] (fixed c = -0.7+0.27i,
                    seeds z0 ~ U((-1.8,1.8)^2), plot from z1, brot_farm.py:445-457)
                    rendered fresh at the study's reference grade (40M seeds,
                    10x top rung) + a cap-80 run for the cap trend.
  * mandel/z3     : the cached study references data/ref_{map}_1500.npz
                    (S0 @ 40M, cap 1500), ROI + nulls reused verbatim
                    (analyze.roi_from_ref; S0 4M study/control pair).

Metric: L1 between ROI-mass-1 histograms on the study's top-decile ROI.
NULL: L1 between statistically independent forward halves (one run split by
seed block; plus the study's own independent 4M study/control pair), and an
independent-preimage-replica floor.  VERDICT rule (pre-stated): licensed iff
bridge L1 <= ~3x the largest null on every map; refuted if it exceeds the
nulls by a wide structured margin; inconclusive only if compute binds.

Connectedness is verified numerically per map (critical-orbit boundedness,
cap 2e5) against the polynomial criterion J(f) connected <=> all critical
orbits bounded; source quotes are in the receipt.

Usage: python probe_preimage.py pilot | main
Writes experiments/results/probe_preimage.json progressively.
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

import conv_maps  # noqa: E402,F401  (repo path + study constants)
import brot_farm as bf  # noqa: E402  (imports follow the sys.path bootstrap above)
from analyze import roi_from_ref  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, ".."))
RES = os.path.join(ROOT, "results")
DATA = os.path.join(ROOT, "data")

SIZE = 512            # study SIZE (run_cell.py)
PRE_CHAINS = 4096     # preimage chains
PRE_BURN = 2_000      # preimage burn-in steps per chain
PRE_TARGET = 100_000_000   # preimage visits (main run)
PROBE_BASE_SEED = 20261024
JULIA_REF_BUDGET = 40_000_000   # = study ref grade (10x top rung)
JULIA_CAP80_BUDGET = 4_000_000  # = study top rung
MANDEL_FRESH_BUDGET = 4_000_000
MAX_REF_SECONDS = 1_800.0       # auto-scale guard for the julia render

W0 = 0.31 - 0.72j  # generic non-exceptional IIM start (not preperiodic to 0)


def l1_roi(raw_a: np.ndarray, raw_b: np.ndarray, roi: np.ndarray) -> float:
    """L1 between the two count histograms, each normalized to mass 1 on ROI."""
    a = raw_a.ravel()[roi]
    b = raw_b.ravel()[roi]
    sa, sb = a.sum(), b.sum()
    if sa <= 0 or sb <= 0:
        return float("nan")
    return float(np.abs(a / sa - b / sb).sum())


def roi_mass_on(raw: np.ndarray, roi: np.ndarray, support: np.ndarray) -> float:
    """Fraction of ROI-normalized mass landing on pixels where the full-grid
    boolean `support` is True (support is indexed down to ROI inside)."""
    v = raw.ravel()[roi]
    s = v.sum()
    if s <= 0:
        return float("nan")
    sup = support[roi]
    return float(v[sup].sum() / s)


def critical_orbit(c: complex, power: int, cap: int = 200_000) -> dict:
    """Polynomial connectedness criterion, numeric side: J(f) connected
    <=> every critical orbit bounded.  For z^power + c the only (finite)
    critical point is 0 (power-1fold).  Bounded test: |z| <= 1e6 for cap
    steps; escape radius max(2, |c|) already certifies escape."""
    z = 0j + 0.0
    m = 0.0
    for _ in range(cap):
        z = z ** power + c
        az = abs(z)
        if not math.isfinite(az) or az > 1e6:
            return {"bounded": False, "max_mod": m, "cap": cap}
        m = max(m, az)
    return {"bounded": True, "max_mod": m, "cap": cap}


def sample_preimage(c: complex, power: int, plotwin, seed: int,
                    target_points: int, chains: int = PRE_CHAINS,
                    burn: int = PRE_BURN, w0: complex = W0) -> dict:
    """Random inverse iteration with uniform branch choice, chains x depth,
    visits binned in-frame on the study grid.  z2: w -> +-(sqrt(w-c));
    z3: w -> roots-of-unity * principal (w-c)^(1/3).  First `burn` steps of
    every chain are dropped (mixing); the post-burn stream is also split by
    time into halves as a mixing diagnostic (the independence floor is the
    separate-replica run, not this split)."""
    rng = np.random.default_rng(seed)
    W = H = SIZE
    px0, px1, py0, py1 = plotwin
    sx, sy = W / (px1 - px0), H / (py1 - py0)
    K = chains
    w = np.full(K, complex(w0), dtype=np.complex128)
    roots3 = np.exp(2j * np.pi * np.arange(3) / 3)
    hist = np.zeros(W * H)
    hist_a = np.zeros(W * H)
    hist_b = np.zeros(W * H)
    n_steps = math.ceil(target_points / K)
    branch_counts = np.zeros(power, dtype=np.int64)
    n_in_post = 0
    n_nan = 0
    t0 = time.time()
    for si in range(burn + n_steps):
        if power == 2:
            br = rng.integers(0, 2, K)
            w = (1.0 - 2.0 * br) * np.sqrt(w - c)
        else:
            br = rng.integers(0, 3, K)
            w = roots3[br] * np.exp(np.log(w - c) / 3.0)
        branch_counts += np.bincount(br, minlength=power)
        n_nan += int((~np.isfinite(w)).sum())
        col = ((w.real - px0) * sx).astype(np.int64)
        row = ((w.imag - py0) * sy).astype(np.int64)
        inb = (col >= 0) & (col < W) & (row >= 0) & (row < H)
        if si >= burn:
            n_in_post += int(inb.sum())
            flat = row[inb] * W + col[inb]
            bc = np.bincount(flat, minlength=W * H).astype(np.float64)
            hist += bc
            half_a = (si - burn) < (n_steps // 2)
            (hist_a if half_a else hist_b)[:] += bc
    return {
        "hist": hist, "hist_a": hist_a, "hist_b": hist_b,
        "seed": seed, "chains": K, "burn": burn, "steps": n_steps,
        "visits": int(K * n_steps), "w0": str(complex(w0)),
        "inframe_visits": n_in_post, "nan_visits": n_nan,
        "branch_counts": [int(x) for x in branch_counts],
        "sec": time.time() - t0,
    }


def sample_uniform_julia(fj: dict, cap: int, budget: int, seed: int,
                         batch: int = 1_000_000, halves: int = 2) -> dict:
    """The study's S0 estimator on the farm's julia map, mirroring
    brot_farm.render_fractal's julia branch line-for-line (seeds z0 ~ U(samp),
    fixed c, escape via bf.escape_mask, escapers advanced once, plotted from
    z1 via bf.plot_orbits — brot_farm.py:445-457).  The seed stream is split
    into `halves` interleaved blocks, giving statistically independent
    half-histograms of the same reference."""
    rng = np.random.default_rng(seed)
    W = H = SIZE
    x0, x1, y0, y1 = fj["samp"]
    hists = [np.zeros(W * H) for _ in range(halves)]
    n_drawn = 0
    n_esc = 0
    jx, jy = fj["julia"]
    t0 = time.time()
    with np.errstate(over="ignore", invalid="ignore"):
        while n_drawn < budget:
            n = min(batch, budget - n_drawn)
            ax = rng.uniform(x0, x1, n)
            ay = rng.uniform(y0, y1, n)
            cx = np.full(n, jx)
            cy = np.full(n, jy)
            esc = bf.escape_mask(fj, ax, ay, cx, cy, cap)
            n_esc += int(esc.sum())
            if esc.any():
                px, py, pcx, pcy = ax[esc], ay[esc], cx[esc], cy[esc]
                px, py = fj["step"](px, py, pcx, pcy)
                h = hists[(n_drawn // batch) % halves]
                bf.plot_orbits(fj, px, py, pcx, pcy, cap, h, W, H)
            n_drawn += n
    return {
        "hists": hists, "seed": seed, "budget": n_drawn, "cap": cap,
        "n_escaped": n_esc, "points": float(sum(h.sum() for h in hists)),
        "sec": time.time() - t0,
    }


def sample_uniform_mandel_halves(cap: int, budget: int, seed: int,
                                 batch: int = 1_000_000) -> dict:
    """cs.sample_uniform on the mandel map, split into two independent
    halves by seed block (for the literal 'two halves of the reference'
    null).  Kernel order mirrors conv_samplers.sample_uniform exactly."""
    mapd = conv_maps.get("mandel")
    rng = np.random.default_rng(seed)
    W = H = SIZE
    x0, x1, y0, y1 = mapd["samp"]
    hist_a = np.zeros(W * H)
    hist_b = np.zeros(W * H)
    n_drawn = 0
    n_esc = 0
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
            esc = mapd["escape_mask"](cr, ci, cap)
            n_esc += int(esc.sum())
            h = hist_a if (n_drawn // batch) % 2 == 0 else hist_b
            mapd["plot_orbits"](cr[esc], ci[esc], cap, h, W, H)
            n_drawn += n
    return {
        "hist_a": hist_a, "hist_b": hist_b, "seed": seed, "budget": n_drawn,
        "n_escaped": n_esc, "n_culled": n_culled, "cap": cap,
        "points": float(hist_a.sum() + hist_b.sum()),
        "sec": time.time() - t0,
    }


def load_cached(map_name: str) -> dict:
    """Cached study reference (S0 @ 40M, cap 1500) + the two independent 4M
    S0 runs (study / control) used by the study's own SE machinery."""
    with np.load(os.path.join(DATA, f"ref_{map_name}_1500.npz")) as z:
        ref_raw = z["raw"].ravel()
    with open(os.path.join(RES, f"run_{map_name}_1500_S0_40000000_ref.json"),
              encoding="utf-8") as f:
        ref_meta = json.load(f)
    hists = {}
    for variant in ("study", "control"):
        with np.load(os.path.join(
                DATA, f"hist_{map_name}_1500_S0_4000000_{variant}.npz")) as z:
            hists[variant] = z["hist"].ravel()
        with open(os.path.join(
                RES, f"run_{map_name}_1500_S0_4000000_{variant}.json"),
                encoding="utf-8") as f:
            hists[f"{variant}_meta"] = json.load(f)
    return {"ref_raw": ref_raw, "ref_meta": ref_meta, "h4m": hists}


def bridge_record(key: str) -> dict:
    return {"key": key, "errors": []}


def main_pilot() -> None:
    t0 = time.time()
    fj = bf.F(
        "julia", "JULIABROT (probe)", "z -> z^2 + (-0.7+0.27i), fixed c",
        bf.s_std, bf.g_z, 32, julia=(-0.7, 0.27),
        samp=(-1.8, 1.8, -1.8, 1.8), plot=(-1.8, 1.8, -1.8, 1.8),
        chans=((1500, 0),),
    )
    r = sample_uniform_julia(fj, 1500, 200_000, PROBE_BASE_SEED, batch=200_000)
    per_seed = r["points"] / r["budget"]
    proj = JULIA_REF_BUDGET / 200_000 * r["sec"]
    print(f"[pilot] julia cap1500 200k seeds: sec={r['sec']:.1f} "
          f"esc={r['n_escaped']} pts/seed={per_seed:.1f} "
          f"-> 40M projection {proj:.0f}s", flush=True)
    p = sample_preimage(complex(-0.7, 0.27), 2, (-1.8, 1.8, -1.8, 1.8),
                        PROBE_BASE_SEED + 1, 2_000_000)
    print(f"[pilot] preimage 2M visits: sec={p['sec']:.2f} "
          f"inframe={p['inframe_visits'] / p['visits']:.4f} "
          f"nan={p['nan_visits']} branches={p['branch_counts']}", flush=True)
    for c, pw in ((-1 + 0j, 2), (-0.1 + 0j, 2), (0.25 + 0j, 3),
                  (complex(-0.7, 0.27), 2)):
        co = critical_orbit(c, pw)
        print(f"[pilot] critical orbit c={c}: bounded={co['bounded']} "
              f"max|z|={co['max_mod']:.4f}", flush=True)
    print(f"[pilot] total {time.time() - t0:.1f}s", flush=True)


def main() -> None:
    out_path = os.path.join(RES, "probe_preimage.json")
    rec: dict = {
        "probe": "bridge-preimage-vs-forward",
        "date": "2026-10-24",
        "protocol": {
            "grid": SIZE, "pre_chains": PRE_CHAINS, "pre_burn": PRE_BURN,
            "pre_target_visits": PRE_TARGET, "pre_w0": str(complex(W0)),
            "roi_rule": ("analyze.roi_from_ref verbatim: top decile of "
                         "positive reference-count pixels"),
            "l1": "sum_ROI |a_p/sum_ROI(a) - b_p/sum_ROI(b)|",
            "base_seed": PROBE_BASE_SEED,
            "note": ("mandel/z3 bridges reuse the cached cap-1500 40M study "
                     "references and their 4M study/control null pair; the "
                     "julia bridge renders its own 40M reference + cap-80 "
                     "trend run through the farm's own kernels."),
        },
        "maps": [],
        "ok": False,
    }
    t_all = time.time()

    # ---------------- bridges 1a/1b: julia-map flow, fixed-map bridge -----
    # 1a: c = -1 (basilica, CONNECTED J — decisive, connected-case identity)
    # 1b: c = -0.7+0.27i (the farm's as-configured julia map; its critical
    #     orbit escapes => J is Cantor-disconnected, reported as measured)
    for jtag, jc, jwin in (
        ("julia_connected_c-1", complex(-1, 0), (-1.8, 1.8, -1.8, 1.8)),
        ("julia_asconfigured_c-0.7+0.27i", complex(-0.7, 0.27),
         (-1.8, 1.8, -1.8, 1.8)),
    ):
        m = bridge_record(jtag)
        try:
            fj = bf.F(
                "julia", "JULIABROT (probe)",
                f"z -> z^2 + ({jc}), fixed c",
                bf.s_std, bf.g_z, 32,
                julia=(jc.real, jc.imag), samp=jwin, plot=jwin,
                chans=((1500, 0),),
            )
            m["step_rule"] = "brot_farm.s_std (z^2+c), escape g_z |z|^2>4"
            m["critical_orbit"] = critical_orbit(jc, 2)
            m["connected_J"] = bool(m["critical_orbit"]["bounded"])

            # auto-scale guard: rate measured at 1M seeds before committing
            t0 = time.time()
            sample_uniform_julia(fj, 1500, 1_000_000,
                                 PROBE_BASE_SEED - 1, batch=1_000_000,
                                 halves=1)
            proj = JULIA_REF_BUDGET / 1_000_000 * (time.time() - t0)
            budget = JULIA_REF_BUDGET
            if proj > MAX_REF_SECONDS:
                budget = int(max(4_000_000, JULIA_REF_BUDGET * MAX_REF_SECONDS
                                 / proj) // 1_000_000) * 1_000_000
                m["auto_scaled"] = {
                    "pilot_sec_1M": time.time() - t0,
                    "projected_sec_40M": proj, "scaled_budget": budget,
                    "reason": (f"40M projected {proj:.0f}s > "
                               f"{MAX_REF_SECONDS:.0f}s"),
                }
            fwd = sample_uniform_julia(fj, 1500, budget, PROBE_BASE_SEED + 77,
                                       batch=1_000_000)
            m["forward"] = {
                "source": "rendered fresh (farm kernels, julia branch)",
                "cap": 1500, "budget": fwd["budget"], "seed": fwd["seed"],
                "n_escaped": fwd["n_escaped"], "points": fwd["points"],
                "sec": fwd["sec"],
                "escape_fraction": fwd["n_escaped"] / fwd["budget"],
            }
            ref_raw = fwd["hists"][0] + fwd["hists"][1]
            roi, roi_info = roi_from_ref(ref_raw.reshape(SIZE, SIZE))
            m["roi"] = roi_info

            fwd80 = sample_uniform_julia(fj, 80, JULIA_CAP80_BUDGET,
                                         PROBE_BASE_SEED + 78,
                                         batch=1_000_000)
            m["forward_cap80"] = {
                "cap": 80, "budget": fwd80["budget"], "seed": fwd80["seed"],
                "n_escaped": fwd80["n_escaped"], "points": fwd80["points"],
                "sec": fwd80["sec"],
                "escape_fraction": fwd80["n_escaped"] / fwd80["budget"],
            }

            pre = sample_preimage(jc, 2, jwin, PROBE_BASE_SEED + 0,
                                  PRE_TARGET)
            rep = sample_preimage(jc, 2, jwin, PROBE_BASE_SEED + 1,
                                  PRE_TARGET // 2)
            m["preimage"] = preimage_scalars(pre)
            m["preimage_replica"] = preimage_scalars(rep)

            m["nulls"] = {
                "forward_halves": l1_roi(fwd["hists"][0], fwd["hists"][1],
                                         roi),
                "preimage_replica": l1_roi(pre["hist"], rep["hist"], roi),
                "preimage_timesplit": l1_roi(pre["hist_a"], pre["hist_b"],
                                             roi),
            }
            m["bridge"] = {
                "l1_pre_vs_ref": l1_roi(pre["hist"], ref_raw, roi),
                "l1_pre_vs_half0": l1_roi(pre["hist"], fwd["hists"][0], roi),
                "l1_pre_vs_cap80": l1_roi(pre["hist"], fwd80["hists"][0],
                                          roi),
                "l1_cap80_vs_ref": l1_roi(fwd80["hists"][0], ref_raw, roi),
            }
            pre_roi_counts = pre["hist"].ravel()[roi]
            m["overlap"] = {
                "ref_mass_on_pre_support": roi_mass_on(
                    ref_raw, roi, pre["hist"].ravel() > 0),
                "roi_pixels_with_pre_zero": int((pre_roi_counts == 0).sum()),
                "roi_pixels": int(roi.sum()),
                "pre_roi_mass_fraction": float(
                    pre["hist"].ravel()[roi].sum() / pre["hist"].sum()),
            }
            # reverse ROI: top decile of the preimage's own visited pixels
            roi_p, roi_p_info = roi_from_ref(pre["hist"].reshape(SIZE, SIZE))
            m["overlap"]["reverse_roi"] = roi_p_info
            m["overlap"]["reverse_l1_pre_vs_ref"] = l1_roi(
                pre["hist"], ref_raw, roi_p)
            m["overlap"]["reverse_null_replica"] = l1_roi(
                pre["hist"], rep["hist"], roi_p)
        except Exception as e:  # fail-closed
            m["errors"].append(f"{type(e).__name__}: {e}")
        rec["maps"].append(m)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2)
        print(f"[bridge] {jtag} done errors={m['errors']} "
              f"bridge={m.get('bridge')} nulls={m.get('nulls')}", flush=True)

    # -------- bridges 2-4: fixed c vs the cached study c-mixture refs -----
    for spec in (
        {"key": "mandel_c-1", "c": complex(-1, 0), "power": 2,
         "map": "mandel", "plotwin": (-2.25, 1.15, -1.7, 1.7),
         "step_rule": "buddhabrot z<-z^2+c, escape |z|^2>4, cardioid+bulb cull"},
        {"key": "mandel_c-0.1", "c": complex(-0.1, 0), "power": 2,
         "map": "mandel", "plotwin": (-2.25, 1.15, -1.7, 1.7),
         "step_rule": "buddhabrot z<-z^2+c, escape |z|^2>4, cardioid+bulb cull"},
        {"key": "z3_c0.25", "c": complex(0.25, 0), "power": 3,
         "map": "z3", "plotwin": (-1.6, 1.6, -1.6, 1.6),
         "step_rule": "brot_farm.s_z3 (z^3+c), escape g_z |z|^2>4"},
    ):
        m = bridge_record(spec["key"])
        try:
            cached = load_cached(spec["map"])
            m["critical_orbit"] = critical_orbit(spec["c"], spec["power"])
            m["step_rule"] = spec["step_rule"]
            ref_raw = cached["ref_raw"]
            roi, roi_info = roi_from_ref(ref_raw.reshape(SIZE, SIZE))
            m["roi"] = roi_info
            m["forward"] = {
                "source": f"cached data/ref_{spec['map']}_1500.npz "
                          "(S0 @ 40M, cap 1500)",
                "budget": cached["ref_meta"]["budget"],
                "seed": cached["ref_meta"]["seed"],
                "points": cached["ref_meta"]["raw_total_points"],
                "escape_fraction":
                    cached["ref_meta"]["n_escaped"]
                    / cached["ref_meta"]["budget"],
            }
            h4m = cached["h4m"]
            fresh = sample_uniform_mandel_halves(
                1500, MANDEL_FRESH_BUDGET, PROBE_BASE_SEED + 79)
            m["forward_fresh_halves"] = {
                "budget": fresh["budget"], "seed": fresh["seed"],
                "points": fresh["points"], "n_escaped": fresh["n_escaped"],
                "n_culled": fresh["n_culled"], "sec": fresh["sec"],
            }
            pre = sample_preimage(spec["c"], spec["power"], spec["plotwin"],
                                  PROBE_BASE_SEED + 0, PRE_TARGET)
            rep = sample_preimage(spec["c"], spec["power"], spec["plotwin"],
                                  PROBE_BASE_SEED + 1, PRE_TARGET // 2)
            m["preimage"] = preimage_scalars(pre)
            m["preimage_replica"] = preimage_scalars(rep)
            m["nulls"] = {
                "forward_fresh_halves": l1_roi(fresh["hist_a"],
                                               fresh["hist_b"], roi),
                "cached_study_vs_control_4M": l1_roi(h4m["study"],
                                                     h4m["control"], roi),
                "cached_study4M_vs_ref40M": l1_roi(h4m["study"], ref_raw, roi),
                "preimage_replica": l1_roi(pre["hist"], rep["hist"], roi),
                "preimage_timesplit": l1_roi(pre["hist_a"], pre["hist_b"],
                                             roi),
            }
            m["bridge"] = {
                "l1_pre_vs_ref": l1_roi(pre["hist"], ref_raw, roi),
                "l1_pre_vs_fresh_half0": l1_roi(pre["hist"], fresh["hist_a"],
                                                roi),
                "l1_pre_vs_study4M": l1_roi(pre["hist"], h4m["study"], roi),
            }
            pre_roi_counts = pre["hist"].ravel()[roi]
            m["overlap"] = {
                "ref_mass_on_pre_support": roi_mass_on(
                    ref_raw, roi, pre["hist"].ravel() > 0),
                "roi_pixels_with_pre_zero": int((pre_roi_counts == 0).sum()),
                "roi_pixels": int(roi.sum()),
                "pre_roi_mass_fraction": float(
                    pre["hist"].ravel()[roi].sum() / pre["hist"].sum()),
            }
            roi_p, roi_p_info = roi_from_ref(pre["hist"].reshape(SIZE, SIZE))
            m["overlap"]["reverse_roi"] = roi_p_info
            m["overlap"]["reverse_l1_pre_vs_ref"] = l1_roi(
                pre["hist"], ref_raw, roi_p)
            m["overlap"]["reverse_null_replica"] = l1_roi(
                pre["hist"], rep["hist"], roi_p)
            m["forward_cached_4m_meta"] = {
                "study_seed": h4m["study_meta"]["seed"],
                "control_seed": h4m["control_meta"]["seed"],
            }
        except Exception as e:  # fail-closed
            m["errors"].append(f"{type(e).__name__}: {e}")
        rec["maps"].append(m)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2)
        print(f"[bridge] {spec['key']} done errors={m['errors']} "
              f"bridge={m.get('bridge')}", flush=True)

    rec["wall_sec"] = time.time() - t_all
    rec["ok"] = all(not mm["errors"] for mm in rec["maps"])
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
    print(f"[done] ok={rec['ok']} wall={rec['wall_sec']:.1f}s -> {out_path}",
          flush=True)


def preimage_scalars(p: dict) -> dict:
    return {
        "seed": p["seed"], "chains": p["chains"], "burn": p["burn"],
        "steps": p["steps"], "visits": p["visits"], "w0": p["w0"],
        "inframe_fraction": p["inframe_visits"] / p["visits"],
        "nan_visits": p["nan_visits"],
        "branch_counts": p["branch_counts"],
        "branch_frequencies": [x / sum(p["branch_counts"])
                               for x in p["branch_counts"]],
        "sec": p["sec"],
    }


if __name__ == "__main__":
    if sys.argv[1] == "pilot":
        main_pilot()
    else:
        main()
