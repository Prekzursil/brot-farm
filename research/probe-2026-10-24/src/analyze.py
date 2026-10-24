"""Analysis for the convergence study — implements the rules fixed in
receipts/2026-10-21-exp-convergence-budget.md:

  ROI per (map,cap) from the 40M reference raw counts: top decile among
  positive pixels (k = ceil(0.1*n_pos), threshold = k-th largest count,
  ROI = count >= threshold), defined once, reused for every run in the cell.

  Per-run per-pixel relative error over ROI: rel_p = |hat_p - ref_p|/ref_p
  (normalized histograms); mean / median / p90; global TV as secondary.

  Convergence slope: OLS of log(mean rel) on log(N) over the 4 rungs.

  S2 bias check at the top rung:
    b(X) = mean_ROI[(X_p - ref_p)/ref_p]; SE(b)=|b(S0s)-b(S0c)|/sqrt(2);
    verdict "no visible skew" <=> |b(S2)| <= 3*SE(b).
    Supplementary t-stat on the S0-calibrated z-field (see receipt).

Outputs: experiments/results/cell_{map}_{cap}.json and
experiments/results/summary_convergence.md
"""

from __future__ import annotations

import glob
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
RES = os.path.join(ROOT, "results")
DATA = os.path.join(ROOT, "data")

MAPS = ("cosmut", "mandel", "z3")
CAPS = (80, 400, 1500)
LADDER = (62_500, 250_000, 1_000_000, 4_000_000)


def roi_from_ref(raw: np.ndarray) -> tuple[np.ndarray, dict]:
    flat = raw.ravel()
    pos = flat[flat > 0]
    n_pos = int(pos.size)
    k = math.ceil(0.1 * n_pos)
    counts_sorted = np.sort(pos)[::-1]
    thresh = float(counts_sorted[k - 1])
    roi = flat >= thresh
    info = {
        "n_positive_pixels": n_pos, "decile_k": k,
        "threshold_count": thresh, "roi_pixels": int(roi.sum()),
        "roi_mass_fraction": float(flat[roi].sum() / flat.sum()),
        "rule": "top decile of positive-count pixels, count >= k-th largest",
    }
    return roi, info


def rel_stats(hat: np.ndarray, ref: np.ndarray, roi: np.ndarray) -> dict:
    h = hat.ravel()[roi]
    r = ref.ravel()[roi]
    rel = np.abs(h - r) / r
    return {
        "mean_rel_err": float(rel.mean()),
        "median_rel_err": float(np.median(rel)),
        "p90_rel_err": float(np.percentile(rel, 90)),
        "tv_global": float(0.5 * np.abs(hat - ref).sum()),
    }


def signed_mean(hat: np.ndarray, ref: np.ndarray, roi: np.ndarray) -> float:
    h = hat.ravel()[roi]
    r = ref.ravel()[roi]
    return float(((h - r) / r).mean())


def load_npz(path: str) -> np.ndarray:
    with np.load(path) as z:
        return z["hist"] if "hist" in z else z["normalized"]


def load_run(map_name: str, cap: int, kind: str, n: int, variant: str):
    jp = os.path.join(RES, f"run_{map_name}_{cap}_{kind}_{n}_{variant}.json")
    np_ = os.path.join(DATA, f"hist_{map_name}_{cap}_{kind}_{n}_{variant}.npz")
    if not (os.path.exists(jp) and os.path.exists(np_)):
        return None, None
    with open(jp, encoding="utf-8") as f:
        meta = json.load(f)
    return meta, load_npz(np_)


def ols_slope(xs: list[float], ys: list[float]) -> tuple[float, float]:
    x = np.asarray(xs)
    y = np.asarray(ys)
    b, a = np.polyfit(x, y, 1)
    return float(b), float(a)


def main() -> None:
    cells = []
    for m in MAPS:
        for c in CAPS:
            refp = os.path.join(DATA, f"ref_{m}_{c}.npz")
            refj = os.path.join(RES, f"run_{m}_{c}_S0_40000000_ref.json")
            if not (os.path.exists(refp) and os.path.exists(refj)):
                print(f"[missing] ref {m}:{c}", flush=True)
                continue
            with np.load(refp) as z:
                raw = z["raw"]
                refn = z["normalized"]
            with open(refj, encoding="utf-8") as f:
                refmeta = json.load(f)
            roi, roi_info = roi_from_ref(raw)

            runs = []
            for kind in ("S0", "S1", "S2"):
                per_n = []
                for n in LADDER:
                    meta, hist = load_run(m, c, kind, n, "study")
                    if hist is None:
                        per_n.append(None)
                        continue
                    st = rel_stats(hist, refn, roi)
                    degenerate = (kind == "S1"
                                  and (meta.get("n_accepted") or 0) == 0)
                    st.update({
                        "sampler": kind, "budget": n, "seed": meta["seed"],
                        "sec": meta["sec"],
                        "samples_per_sec": n / meta["sec"] if meta["sec"] else None,
                        "acceptance": meta.get("acceptance"),
                        "ess": meta.get("ess"),
                        "n_escaped": meta.get("n_escaped"),
                        "n_accepted": meta.get("n_accepted"),
                        "evals": meta.get("evals"),
                        "degenerate": degenerate,
                        "degenerate_reason": (
                            "S1 pre-pass (grid^2 = 65,536 evals) consumed the "
                            "whole budget before any main-phase draw — no "
                            "estimate exists at this rung"
                            if degenerate else None),
                    })
                    per_n.append(st)
                runs.append({"sampler": kind, "by_budget": per_n})

            # convergence slopes
            slopes = {}
            for entry in runs:
                xs, ys = [], []
                for st in entry["by_budget"]:
                    if st and not st.get("degenerate"):
                        xs.append(math.log(st["budget"]))
                        ys.append(math.log(st["mean_rel_err"]))
                if len(xs) >= 2:
                    slopes[entry["sampler"]] = dict(
                        zip(("slope", "intercept"), ols_slope(xs, ys)))
                    slopes[entry["sampler"]]["n_rungs_used"] = len(xs)

            # bias check at top rung
            bias = {}
            m_s2, h_s2 = load_run(m, c, "S2", LADDER[-1], "study")
            m_s0s, h_s0s = load_run(m, c, "S0", LADDER[-1], "study")
            m_s0c, h_s0c = load_run(m, c, "S0", LADDER[-1], "control")
            if not (h_s2 is None or h_s0s is None or h_s0c is None):
                b_s2 = signed_mean(h_s2, refn, roi)
                b_s0s = signed_mean(h_s0s, refn, roi)
                b_s0c = signed_mean(h_s0c, refn, roi)
                se_b = abs(b_s0s - b_s0c) / math.sqrt(2.0)
                verdict = (abs(b_s2) <= 3.0 * se_b)
                # supplementary t-stat on S0-calibrated z-field
                d2 = (h_s2.ravel()[roi] - refn.ravel()[roi])
                se_p = np.abs(h_s0s.ravel()[roi] - h_s0c.ravel()[roi]) / math.sqrt(2.0)
                ok = se_p > 0
                z = d2[ok] / se_p[ok]
                n_ok = int(ok.sum())
                if n_ok > 2 and z.std() > 0:
                    t_stat = float(z.mean() / (z.std() / math.sqrt(n_ok)))
                else:
                    t_stat = None
                mr = rel_stats(h_s2, refn, roi)["mean_rel_err"]
                mr0 = rel_stats(h_s0s, refn, roi)["mean_rel_err"]
                bias = {
                    "b_S2_top": b_s2, "b_S0_study": b_s0s, "b_S0_control": b_s0c,
                    "SE_b_from_S0_pair": se_b,
                    "z_threshold_3SE": 3.0 * se_b,
                    "verdict_no_visible_skew": bool(verdict),
                    "supp_t_stat_S0calibrated": t_stat,
                    "supp_t_n_pixels": n_ok,
                    "mean_rel_ratio_S2_over_S0": mr / mr0 if mr0 > 0 else None,
                }

            cell = {
                "map": m, "cap": c, "grid": 512,
                "reference": {
                    "budget": refmeta["budget"], "seed": refmeta["seed"],
                    "sec": refmeta["sec"],
                    "raw_total_points": refmeta["raw_total_points"],
                    "n_escaped": refmeta["n_escaped"],
                    "escape_fraction": refmeta["n_escaped"] / refmeta["budget"],
                },
                "roi": roi_info,
                "runs": runs,
                "convergence_loglog_slopes": slopes,
                "bias_check_top_rung": bias,
            }
            cells.append(cell)
            outp = os.path.join(RES, f"cell_{m}_{c}.json")
            with open(outp, "w", encoding="utf-8") as f:
                json.dump(cell, f, indent=2)
            print(f"[cell] {m}:{c} -> {os.path.basename(outp)}", flush=True)

    # ---------------- summary markdown ----------------
    lines = [
        "# Convergence study — sampler suite S0/S1/S2 (brot-farm)",
        "",
        "Subject repo brot-farm @ 4d87ef3. Maps: mandel (z^2+c), z3 (z^3+c),",
        "cosmut (x'=cos(x^2)-y+cx). Channels: iteration caps 80/400/1500.",
        "Ladder N = 62,500 / 250,000 / 1,000,000 / 4,000,000; reference = S0 @",
        "40M (10x top rung). ROI = top decile of positive reference-count",
        "pixels (defined once per map x channel). rel = |hat_p - ref_p|/ref_p",
        "over ROI. Full per-run scalars: results/run_*.json; raw histograms:",
        "data/*.npz; per-cell analyses: results/cell_*.json.",
        "",
    ]
    for m in MAPS:
        for c in CAPS:
            cell = next((x for x in cells if x["map"] == m and x["cap"] == c), None)
            if cell is None:
                continue
            lines.append(
                f"## {m} / cap {c}  —  ref {cell['reference']['budget']:,} pts, "
                f"{cell['reference']['raw_total_points']:.2e} orbit points, "
                f"escape frac {cell['reference']['escape_fraction']:.3f}, "
                f"ROI {cell['roi']['roi_pixels']:,} px "
                f"({100 * cell['roi']['roi_mass_fraction']:.1f}% mass)"
            )
            lines.append("")
            lines.append(
                "| sampler | N | mean rel err | median rel | p90 rel | TV(global) "
                "| sec | samples/s | acceptance | ESS |")
            lines.append("|---|---|---|---|---|---|---|---|---|---|")
            for entry in cell["runs"]:
                for st in entry["by_budget"]:
                    if not st:
                        continue
                    acc = ("-" if st["acceptance"] is None
                           else f"{100 * st['acceptance']:.1f}%")
                    flag = " **(degenerate: no estimate — pre-pass ate the budget)**" \
                        if st.get("degenerate") else ""
                    lines.append(
                        f"| {st['sampler']} | {st['budget']:,} "
                        f"| {st['mean_rel_err']:.4f} | {st['median_rel_err']:.4f} "
                        f"| {st['p90_rel_err']:.4f} | {st['tv_global']:.4f} "
                        f"| {st['sec']:.1f} | {st['samples_per_sec']:,.0f} "
                        f"| {acc} | {st['ess']:,.0f} |{flag}")
            sl = cell["convergence_loglog_slopes"]
            if sl:
                lines.append("")
                lines.append(
                    "log-log slopes (mean rel err vs N): "
                    + ", ".join(
                        f"{k} {v['slope']:.3f}" for k, v in sl.items())
                    + "  (MC theory: -0.5)")
            b = cell["bias_check_top_rung"]
            if b:
                lines.append("")
                lines.append(
                    f"**S2 bias check @ top rung:** b(S2)={b['b_S2_top']:+.4f}, "
                    f"b(S0s)={b['b_S0_study']:+.4f}, b(S0c)={b['b_S0_control']:+.4f}, "
                    f"SE(b)={b['SE_b_from_S0_pair']:.4f}, "
                    f"3·SE={b['z_threshold_3SE']:.4f} → "
                    f"{'**no visible skew**' if b['verdict_no_visible_skew'] else '**SKEW FLAGGED**'}"
                    f" (supp t={b['supp_t_stat_S0calibrated']:.2f} on "
                    f"{b['supp_t_n_pixels']:,} px; mean-rel ratio S2/S0 = "
                    f"{b['mean_rel_ratio_S2_over_S0']:.2f})")
            lines.append("")
    outp = os.path.join(RES, "summary_convergence.md")
    with open(outp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("wrote", outp, flush=True)


if __name__ == "__main__":
    main()
