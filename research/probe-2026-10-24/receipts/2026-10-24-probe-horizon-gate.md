# Receipt — Gate probe: horizon-truncation halving law on the audited 1500 channel (H=1500, 2H=3000, refH=6000)

If it still reads this way, the lane died before measuring anything and no verdict here may be cited.

**Discharge:** the lane completed. `experiments/results/probe_horizon_gate.json`
status `ok`, written 2026-10-24T04:58:26 by
`experiments/src/probe_horizon_gate.py full` (exit 0), wall 751 s
(04:45:55 -> 04:58:26). Measured inventory: 2 maps x (6 S0 renders + 1 deposit
replay) at N=4,000,000 each = 14 runs, all completed; dominance check
(raw1500 <= raw3000 <= raw6000 pointwise) max violation 0.0 on both maps;
deposit-replay identity checks corr = 1.00000 and sum-ratio = 1.00000 on both
maps at both horizon offsets on BOTH ROI masks (a 200k smoke pass ran first,
04:44:39-04:45:21, to validate mechanics). Every number below was extracted by
code from that JSON this session; nothing is quoted from memory.

## GATE VERDICT: **CONFIRMED** (adjudicator rule, fixed in the script header before the run)

The licensed truncation-bias halving law (measured on the 400/800/1600 lane,
`receipts/2026-10-24-probe-horizon.md`) holds on an audited-family channel:
per the rule "gate = CONFIRMED iff the raw missing-mass shrink ratio (ROI mean
at 2H / ROI mean at H, both vs refH) is in [0.35, 0.65] on BOTH maps", the four
deciding numbers are:

| map | shrink ratio raw, seed a | shrink ratio raw, seed b | in [0.35, 0.65]? |
|---|---|---|---|
| mandel | **0.48490** | 0.50373 | YES |
| cosmut | **0.49287** | 0.52374 | YES |

Both primary ratios sit mid-band; every recorded check ratio also lands inside
the band (normalized-b ratio 0.4434 mandel / 0.4717 cosmut; the lane's own
cap-400 mask as companion ROI 0.4853 / 0.4935; the cohort-decomposition
prediction 0.4849 / 0.4929 = the measured values to machine precision). The
limitation paragraph's quantitative halving claim stands on the audited
channel; no downgrade to qualitative is required.

## What was run (parameterized rerun of the 2026-10-24 lane)

`experiments/src/probe_horizon_gate.py` reuses the lane's protocol verbatim
(`experiments/src/probe_horizon.py`, read first; same estimator
`conv_samplers.sample_uniform` = S0, same ROI rule `analyze.roi_from_ref`,
same duplicate-seed SE convention |b_a - b_b|/sqrt(2), same batch schedule,
same seeds) with exactly three deltas, all recorded in the JSON config:

1. Horizon triple: H = 1500 (an audited channel: `data/ref_{map}_1500.npz`,
   `results/cell_{map}_1500.json`), 2H = 3000, refH = 6000 = 4H — the lane's
   400/800/1600 was NOT audited above 400.
2. Primary ROI = the audited cap-1500 cell mask (mandel 26,215 px thresh
   1240; cosmut 26,220 px thresh 3072); the lane's audited cap-400 mask
   (26,263 / 26,223 px) is carried as a companion and every headline metric is
   recorded on BOTH masks.
3. The S2 arm is NOT rerun (out of gate scope: the gate tests the S0-side
   truncation law; the lane measured S2's horizon-independence at 400/800 and
   the gate question does not touch it).

Unchanged from the lane: maps mandel + cosmut; N = 4,000,000 per run; size
512; S0 batch = trace batch = 50,000 fixed across caps and seeds (identical
c-draws at every horizon; escape_mask/plot_orbits consume no RNG); seeds
identical to the lane (cosmut a=867530900 b=867530901, mandel a=867530910
b=867530911, probe-private, disjoint from the study's 20261xxx); deposit pass
= the study's `conv_samplers.trace_orbits` replaying the exact S0 ensemble and
accumulating the FULL deposition of the late-escaper cohorts (1500,6000] and
(3000,6000]. Environment: python 3.14.6, numpy 2.4.4, same 16-core Windows
box; subject repo brot-farm @ `d29483dc60ac630fe98743d61b8492ef1596b2b4`
(= the lane's HEAD; kernel files brot_farm.py / buddhabrot.py / cosbrot.py /
brot_samplers.py re-verified byte-identical to the audited commit
`4d87ef33ca50b1b33c6f5736bd59bad94bd54e70` via `git diff --stat` this session).

## Results — mandel (core family)

| quantity | H=1500 | 2H=3000 |
|---|---|---|
| mean missing mass per ROI bin (points/seed, vs refH=6000, primary ROI) | **44.139** | **21.403** |
| ROI missing-mass total (of global 1,786,102) | 1,157,107 (64.8%) | 561,081 |
| shrink ratio raw (2H/H) | \multicolumn{2}{c}{**0.48490**} |
| normalized b = mean_ROI[(hat-ref)/ref], ref = cap-6000 same-seed | **-0.09990** | **-0.04429** |
| mean abs rel err over ROI | 0.11707 | 0.06119 |
| bias/SE (dup-pair SE 1.076 raw / 0.001249 norm at H; 0.0459 / 0.000925 at 2H) | **41.0** / 80.0 | 466.2 / 47.9 |

- Alive fractions (seed a, denominator = all drawn incl. culled): alive at
  1500 = **13.055%**; new escapers (1500,3000] = **0.01127%** of drawn;
  (3000,6000] = **0.00503%**; alive at 6000 = 13.039% (the unmeasured
  beyond-6000 reservoir). Escape fraction at 1500 = 0.869447 vs the audited
  40M reference's 0.869463 (cell_mandel_1500) — agreement 1.6e-5.
- Cohort decomposition (deposit replay, seed a): the (1500,6000] cohort is
  **652 orbits** of 4M drawn (0.0163%) — of which 201 escape in (3000,6000] —
  depositing ROI totals 596,026 (1500,3000] + 561,081 (3000,6000]; predicted
  shrink 561,081/1,157,107-equivalent = 0.48490, equal to the measured ratio
  (identity: corr 1.00000, sum ratio 1.00000, both offsets, both ROIs).
- Localization (boundary score = visitor-mean escape time at cap 6000, ROI
  terciles 8,739/8,738/8,738 px): bottom/mid/top carry **15.4% / 30.7% /
  54.0%** of ROI missing mass at H; Spearman(score, per-bin missing) =
  **0.896** (0.887 at 2H).
- Anchor: S0@4M@1500 vs the audited 40M cap-1500 reference: b = +0.00284
  (seed a) / -0.00161 (seed b), mean rel err 0.0823 — on the audited cell's
  S0 scale (cell_mandel_1500: b_S0_study -0.0046, mean rel err 0.082 at 4M;
  same order, different seed, consistent at a few times the dup-pair SE).

## Results — cosmut (mutation family, thin ridge)

| quantity | H=1500 | 2H=3000 |
|---|---|---|
| mean missing mass per ROI bin (points/seed, vs refH=6000, primary ROI) | **65.367** | **32.218** |
| ROI missing-mass total (of global 1,772,615) | 1,713,925 (**96.7%**) | 844,747 |
| shrink ratio raw (2H/H) | \multicolumn{2}{c}{**0.49287**} |
| normalized b (ref = cap-6000 same-seed) | **-0.02734** | **-0.01290** |
| mean abs rel err over ROI | 0.07812 | 0.03791 |
| bias/SE (dup-pair SE 2.000 raw / 0.001190 norm at H; 0.379 / 0.0000153 at 2H) | **32.7** / 23.0 | 85.0 / 842.4* |

- Alive at 1500 = **12.975%**; (1500,3000] = 0.01067% of drawn;
  (3000,6000] = 0.00515%; alive at 6000 = 12.960%. Escape fraction at 1500 =
  0.870246 vs audited 0.870043 (agreement 2.0e-4).
- Cohort decomposition: (1500,6000] = **633 orbits** (0.0158%), 206 in
  (3000,6000]; identity exact as above (predicted shrink 0.49287 == measured).
- Localization: terciles carry **0.44% / 27.1% / 72.5%**; Spearman **0.946**
  (0.942 at 2H) — sharper boundary concentration than mandel, as the
  thin-ridge structure predicts.
- Anchor: b = +0.00046 / +0.00126 vs the audited 40M cap-1500 ref, mean rel
  err 0.0394 (audited cell scale ~0.039).
- *The 842.4 normalized bias/SE at 2H is an artifact of a near-zero dup-pair
  SE (the two seeds' b agree to 2.2e-5), not of a large b — recorded as-is
  per the fail-closed convention; the raw channel (85.0) is the like-for-like
  number, and neither is a gate input.

## Why this confirms the law (mechanism, measured)

The truncation deficit is carried by a tiny, ever-deeper slow-escaper cohort:
the per-octave new-escaper mass halves along the measured trajectory
0.0428% -> 0.0215% (lane, 400/800/1600) -> 0.0113% -> 0.0050% (this gate,
1500/3000/6000), each cohort deposits orders of magnitude more points per
orbit than an average escaper (ROI mean missing 44.1 -> 21.4 mandel / 65.4 ->
32.2 cosmut per bin), and doubling the horizon again removes ~half of it
(raw ratios 0.485 / 0.493, predicted exactly by the cohort decomposition —
corr/sum 1.00000). The bias remains far outside noise at this N (bias/SE
33-466 raw) and remains boundary-localized (top tercile 54.0% / 72.5% of ROI
missing mass at 33% pixel share, Spearman 0.90/0.95). The halving law is
therefore not an artifact of the 400/800 channel pair: it persists at the
audited 1500 channel and beyond, over a 3.75x-deeper horizon span.

## Cautions and deviations (nothing smoothed over)

1. Primary ROI choice is a gate-design decision: the lane's protocol pinned
   its ROI to "the audited mask of channel H" (cap-400); this gate uses the
   audited cap-1500 mask for the same reason and carries the cap-400 mask as
   a companion with all headline metrics recorded on both — the shrink ratio
   moves < 0.001 between masks on both maps, so the verdict is mask-independent.
2. The S2 arm was not rerun (out of scope; see deltas above). The lane's
   S2 verdict (horizon-INDEPENDENT, ratios 1.031/1.076 — NOT the S2
   mechanism) is untouched by this gate; nothing here re-tests it.
3. refH = 6000 is itself truncated: 13.04% (mandel) / 12.96% (cosmut) of
   drawn seeds are still alive at 6000 and contribute nothing at any cap
   (escapers-only estimand); the remaining bias is bounded by the unmeasured
   (6000,inf) cohort. Extrapolating the measured halving (0.0113% -> 0.0050%
   per octave) it is small, but the fully uncapped limit is not measured here.
4. One budget (N=4M, the audited top rung), one machine, one seed pair per
   map. The 200k smoke pass (which showed seed-noise ratios 0.349/0.332, i.e.
   below the band at 20x smaller N) is recorded in the same JSON's history —
   the smoke JSON was overwritten by the full run, whose per-stage saves are
   the artifact of record; smoke exists only to validate mechanics (it did:
   identity checks already exact at 200k).
5. Run logs live OUTSIDE the audited tree (workflow temp dir), per the
   write-only-new-dated-files rule; no existing file in the paper tree or
   brot-farm was modified by this gate. New files: the script, the JSON, this
   receipt — all dated 2026-10-24.
6. cosmut cap-6000 renders took 58-67 s each (cap-linear cost); total wall
   751 s vs the lane's 802 s — the S2-arm omission roughly paid for the 3.75x
   deeper horizons.
7. No literature was cited or needed; this receipt is internal-measurement
   only. No API keys involved.

## Artifacts

- `experiments/src/probe_horizon_gate.py` — the gate probe (modes smoke |
  full; gate rule fixed in the header; fail-closed fin() guards on headline
  metrics; status/verdict blocks in the JSON).
- `experiments/results/probe_horizon_gate.json` — per-map: runs, dominance
  check, escape fractions, raw truncation on both ROIs (both seeds),
  normalized companions, anchor vs the audited 40M cap-1500 reference,
  deposit identity checks, cohort sizes, band decomposition, terciles,
  Spearman, gate inputs and verdict. status `ok`.
- `receipts/2026-10-24-probe-horizon-gate.md` — this receipt.

---
**2026-10-24 closeout annotation:** lint-only/ruff-format edit to `experiments/src/probe_horizon_gate.py` (E402 noqa markers on the post-bootstrap imports; removal of one unused import / one unused variable). No numeric, protocol, or behavioral change; all measured values in this receipt are untouched. Repo copy under research/probe-2026-10-24/ re-synced and hash-verified.
