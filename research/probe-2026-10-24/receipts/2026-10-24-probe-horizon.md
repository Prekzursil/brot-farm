# Receipt — Probe: horizon-truncation mechanism (does doubling H shrink the structured bias?)

If it still reads this way, the lane died before measuring anything and no verdict here may be cited.

**Discharge:** the lane completed. `experiments/results/probe_horizon.json`
status `ok`, written 2026-10-24T04:14:37 by
`experiments/src/probe_horizon.py full` (exit 0). Measured inventory: 2 maps x
(6 S0 renders + 2 S2 renders + 1 deposit replay) at N=4,000,000 each = 18 runs,
all completed; identity checks corr=1.00000 and sum-ratio=1.00000 on both maps
at both horizon offsets; dominance check (raw400 <= raw800 <= raw1600
pointwise) max violation 0.0 on both maps. Every number below was recomputed
this session by the script above plus `python -c` extractions over its JSON;
nothing is quoted from memory.

## What was asked (computed task scope, numeric lane 2)

The audited paper measured S2 bias/SE = 104--4001 (paper.tex:126, paper.tex:565,
Table 3 at paper.tex:861-886) and hypothesized escape-horizon truncation
("Caps bias against slow escapers", paper.tex:1011-1015: "Every channel cap
excludes orbits that escape later than the cap ... the reference suffers the
same truncation, so the convergence numbers describe agreement with the capped
estimand, not with the uncapped limit") as a mechanism. Test: render the
forward histogram at H and 2H with identical seeds/N and the study's ROI,
estimate the beyond-H contribution from the observed escape-time
distribution, and compare bias_H = hist_H - hist_ref vs bias_2H = hist_2H -
hist_ref (mean signed, mean abs, ROI aggregate); localize; verdict licensed
iff doubling H measurably shrinks bias toward zero with the predicted spatial
structure.

## Protocol (exact, reproducible)

- Harness: `experiments/src/probe_horizon.py` (new file, this session),
  importing the study's own `conv_samplers.py` / `conv_maps.py` /
  `analyze.py` — the audited estimator (`sample_uniform` = S0) and the
  audited ROI rule (`analyze.roi_from_ref`, "top decile of positive-count
  pixels, count >= k-th largest") on the audited cap-400 masks
  (`data/ref_{map}_400.npz`: mandel 26,263 px, cosmut 26,223 px — the exact
  audited cell ROIs; threshold counts 924 / 2972).
- Maps: mandel (study core family, z^2+c, cull inside_main_sets) and cosmut
  (mutation family, x'=cos(x^2)-y+cx, escape |y|>100, thin filament ridge).
- Horizons: H=400 (audited mid channel), 2H=800, refH=1600 (=4H).
- N = 4,000,000 seeds per run (the audited top rung), size 512.
- S0 batch = 50,000, identical across caps and maps: with the same seed the
  drawn c-sequence is then IDENTICAL at every horizon (escape_mask/plot_orbits
  consume no RNG), so per-bin horizon differences are pure structure, zero
  c-draw noise. Verified: pointwise dominance max(raw400 - raw800) = 0.0.
- Seeds (numpy default_rng, probe-private, disjoint from the study's
  20261xxx): cosmut a=867530900 b=867530901 s2=867530902; mandel
  a=867530910 b=867530911 s2=867530912. Duplicate seed pair (a,b) calibrates
  SE by the audited convention SE = |b_a - b_b|/sqrt(2).
- Deposit pass: the study's own `conv_samplers.trace_orbits`, batch-wise,
  over the exact S0 ensemble (same seed + batch schedule; the trace consumes
  no RNG), accumulating per-bin visitor count, visitor escape-time sum, and
  the FULL deposition of the late-escaper cohorts (400,1600] and (800,1600]
  (full, because a cap-400 render excludes those orbits entirely). Used for
  (i) the boundary score (visitor-mean escape time per bin), (ii) the
  escape-band decomposition, (iii) an exact identity check against the
  measured horizon differences.
- S2 arm (secondary): `sample_mh_mutation_stream`, chains=1024, step=0.02
  (audited config), caps 400 and 800, b(S2) vs the MATCHING-cap S0 reference
  (the audited convention), plus b(S2@400) vs the audited 40M reference for
  direct Table-3 comparability.
- Environment: python 3.14.6, numpy 2.4.4, 16-core Windows box. Subject repo
  brot-farm @ `d29483dc60ac630fe98743d61b8492ef1596b2b4` (HEAD moved once
  during the session, ceeb851 -> d29483d, a .gitignore-only commit; kernels
  buddhabrot.py / brot_farm.py / cosbrot.py / brot_samplers.py verified
  byte-identical to the audited commit `4d87ef33ca50b1b33c6f5736bd59bad94bd54e70`
  via `git diff --stat` at both heads; working tree deltas are .coverage and
  untracked paper-deliverables/, neither imported).
- Wall: 802 s total (04:01:15 -> 04:14:37). Per map: S0 42.7 s / 96.3 s;
  S2 101.5 + 213.3 s / 106.4 + 139.4 s; deposit 42.9 s / 58.8 s
  (mandel / cosmut).

## Results

### Mandel (core family)

| quantity | H=400 | 2H=800 |
|---|---|---|
| mean missing mass per ROI bin (points/seed, vs refH) | **41.379** | **20.589** |
| shrink ratio raw (2H/H) | \multicolumn{2}{c}{**0.4976**} |
| normalized b = mean_ROI[(hat-ref)/ref] | **-0.1286** | **-0.0577** |
| mean abs rel err over ROI | 0.1455 | 0.0716 |
| bias/SE (duplicate-pair SE = 0.220 raw / 0.00095 norm) | **188.3** / 135.5 | 169.2 / 82.7 |

- Alive fractions (seed-a ensemble, denominator = all drawn incl. culled):
  alive at 400 = **13.12%**; new escapers (400,800] = 0.0428% of drawn;
  (800,1600] = 0.0215%; the (400,1600] cohort is 2,568 seeds at N=4M that
  deposit 1.898M points globally (~739 points/orbit vs ~3.4 for the average
  escaper) — the truncation mass is a tiny cohort of deep-boundary orbits.
- Localization (boundary score = visitor-mean escape time, ROI terciles):
  bottom/mid/top terciles (equal 8,754-8,755 px) carry **16.3% / 33.4% /
  50.3%** of the ROI missing mass at H; Spearman(score, per-bin missing) =
  **0.896** (0.909 at 2H). The ROI itself (top density decile) holds 57.3%
  of the global missing mass.
- Identity: the deposit replay reproduces the measured horizon difference
  EXACTLY (corr 1.00000, sum ratio 1.00000, ROI and global; predicted shrink
  0.4976 == measured 0.4976) — the mechanism accounting closes to machine
  precision.
- Anchor vs the audited 40M reference (cap 400): my S0@4M gives b = -0.0029
  +/- 0.00001, mean rel err 0.0821 — consistent with the audited cell's S0
  top-rung behavior (b_S0_study -0.0015).

### Cosmut (mutation family, thin ridge)

| quantity | H=400 | 2H=800 |
|---|---|---|
| mean missing mass per ROI bin | **60.620** | **29.092** |
| shrink ratio raw | \multicolumn{2}{c}{**0.4799**} |
| normalized b | **-0.0335** | **-0.0154** |
| mean abs rel err | 0.0847 | 0.0401 |
| bias/SE (SE 1.50 raw / 0.00059 norm) | **40.3** / 57.0 | 16.0 / 17.0 |

- Alive at 400 = 13.03%; (400,1600] cohort 2,351 seeds; ROI holds **93.0%**
  of the global missing mass (its ROI is the filament).
- Terciles: **0.8% / 27.9% / 71.3%** of ROI missing mass; Spearman **0.946**
  (0.941 at 2H). Sharper boundary concentration than mandel, as the
  thin-ridge structure predicts.
- Identity exact as above (corr/sum 1.00000; predicted shrink 0.4799 ==
  measured). Anchor: b(S0@4M vs audited 40M) = -0.0001 +/- 0.00028, mean rel
  0.0398 (audited cell b_S0_study -0.0003).

### Secondary: is the AUDITED S2 bias (104--4001) truncation-driven? No.

- mandel: b(S2 vs same-cap S0 ref) = **-0.3804 @ 400 -> -0.3921 @ 800**,
  shrink ratio **1.031** (bias/SE 40,652 and 562). cosmut: **-0.0909 ->
  -0.0977**, ratio **1.076** (bias/SE 329 and 108).
- b(S2@400 vs the audited 40M reference): mandel -0.3891 (audited cell:
  -0.3535), cosmut -0.0931 (audited: -0.1005) — same order, different seed.

## Verdict

**LICENSED** — for the truncation mechanism exactly as the limitation item
states it: doubling the horizon measurably shrinks the structured bias toward
zero (raw ratios 0.498 mandel / 0.480 cosmut; normalized 0.449 / 0.461;
bias/SE 40-188, i.e. far outside noise at this N), with the predicted spatial
structure (missing mass concentrated in boundary-adjacent bins: top boundary
tercile carries 50.3%/71.3% of ROI missing mass at 33% pixel share, Spearman
0.90/0.95; the deposit decomposition identifies the mass with the tiny
slow-escaper cohort, ~739 points/orbit).

**With the sharp corollary (measured, not asserted):** the audited S2
bias/SE = 104--4001 is *not* this mechanism. S2's deficit vs the same-cap
reference is horizon-INDEPENDENT across a doubling (ratios 1.031 / 1.076 —
unchanged to slightly growing), so horizon truncation cannot explain it; both
S2 and S0 share the truncation, and the paper's own diagnosis — "incomplete
chain exploration of the target's support" (paper.tex:840) — is untouched.
What this lane adds: the truncation bias the paper flagged as a limitation is
real, structured, boundary-localized, and sized (normalized b = -0.13 mandel /
-0.034 cosmut at cap 400 vs a 1600-horizon render) — a property of the capped
estimand itself, present in every sampler including S0, shrinking by ~2x per
horizon doubling along the measured trajectory 0.043% -> 0.021% new escapers
per octave.

## Cautions

1. First execution defect, caught by the lane's own identity check: the first
   full run (03:41-03:58) had (a) a wrong band decomposition (tail-only
   instead of full cohort deposition) and (b) b(S2@800) referenced to the
   cap-1600 histogram instead of the matching cap-800 S0 histogram; the
   identity check failed visibly (sum ratio 0.39) and triggered the
   diagnosis. The stored JSON is from the corrected second run (status ok,
   04:14:37). Both defects were in the probe's derived metrics only; the S0
   renders and the audited estimator paths were identical in both runs.
2. refH=1600 is itself truncated: seeds alive at 1600 (13.05% mandel /
   12.97% cosmut of drawn) contribute nothing at any cap (escapers-only
   estimand), and the remaining bias is bounded by the unmeasured (1600,inf)
   cohort — extrapolating the measured halving (0.043% -> 0.021% per octave)
   it is small, but the fully uncapped limit is not measured here.
3. One budget (N=4M, the audited top rung), one channel pair (400/800; 800
   and 1600 are not audited channels — the audited ladder is 80/400/1500),
   one machine. The shrink ratio at other budgets/channels is untested.
4. b(S2@800) uses my S0@800 as reference (no audited 800-channel reference
   exists); audited-table comparability holds only at cap 400.
5. cosmut's 93% ROI-share of truncation mass is partly ROI composition (its
   top-decile ROI is the filament); the tercile analysis within ROI is the
   like-for-like localization.
6. No external literature was cited or needed; all paper quotes are internal
   (file:line read this session). Search channels were not used in this lane.
7. Artifacts: `experiments/src/probe_horizon.py`,
   `experiments/results/probe_horizon.json`. Run logs live OUTSIDE the
   audited tree (workflow temp dir), per the write-only-new-dated-files rule;
   no existing file in the paper tree or brot-farm was modified.

---
**2026-10-24 closeout annotation:** lint-only edit to `experiments/src/probe_horizon.py` (E402 noqa markers on the post-bootstrap imports; removal of one unused import / one unused variable). No numeric, protocol, or behavioral change; all measured values in this receipt are untouched. Repo copy under research/probe-2026-10-24/ re-synced and hash-verified.
