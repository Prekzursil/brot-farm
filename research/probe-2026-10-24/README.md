# 2026-10-24 breakthrough probe — lab record

**What this is:** probe-level lab material from the 2026-10-24 measurement
session against this repo's kernels (audited commit
`4d87ef33ca50b1b33c6f5736bd59bad94bd54e70`; HEAD `d29483d` differs by a
`.gitignore`-only commit, kernel files byte-identical). It is **not** the
manuscript: the paper is under a **pre-publication hold** and **no
paper.tex/pdf or figure content is included here** — only probe scripts,
their machine-readable outputs, and the receipts that narrate them.

**Layout:** `src/` probe scripts (as run), `results/` their JSON outputs,
`receipts/` the per-lane receipts (every number in a receipt was recomputed
from the JSON of record by code run the same session; each receipt opens with
the skeleton sentinel line and discharges it with a measured inventory).

## Lanes and verdicts (headline numbers; details in the receipts)

### 1. Folk bridge (preimage measure vs forward orbit-density histogram) — REFUTED

`src/probe_preimage.py`, `results/probe_preimage.json`,
`receipts/2026-10-24-probe-bridge.md`.

Five bridges at reference-grade budgets on both sides (40M-seed forward
renders through this repo's own kernels; 100M-visit inverse-iteration
preimage streams), the study's own grid/ROI/metric (L1 on mass-1 ROI
histograms; L1 range is [0,2]):

| bridge | L1 vs forward ref | largest null | ratio |
|---|---|---|---|
| julia_connected (z^2-1, basilica) | 1.8952 | 0.0686 | **27.6x** |
| julia_asconfigured (c=-0.7+0.27i, Cantor dust) | 1.9718 | 0.0087 | **225.7x** |
| mandel c=-1 | 1.9316 | 0.1540 | **12.5x** |
| mandel c=-0.1 | 1.9965 | 0.1540 | **13.0x** |
| z3 c=0.25 | 1.9820 | 0.1807 | **11.0x** |

L1 1.895-1.996 vs nulls 0.007-0.181 (11-226x; the pass bar was ~3x). The
mismatch is structured, not noise: 92.7-99.8% of forward-ROI pixels receive
zero preimage visits, the cap trend is ABSENT (moving the channel 80 -> 1500
moved the bridge L1 by 0.0001), and both samplers sit at self-noise floors
20-300x below the gap. The renderer's forward orbit-counting histogram does
not coincide with the max-entropy/harmonic measure on the study ROI. (Note
added in the receipt: the side finding's julia_asconfigured escape fractions
had a row swap with the connected map — corrected values: asconfigured
cap-1500 escape fraction 0.999860275, interior ~0.014%; 0.8909/~11% belongs
to the connected map. Erratum annotated in place, 2026-10-24.)

### 2. Horizon-truncation bias (the paper's "caps bias slow escapers") — LICENSED, and gated on the audited channel

`src/probe_horizon.py` (lane) + `src/probe_horizon_gate.py` (confirmation
gate), `results/probe_horizon.json` + `results/probe_horizon_gate.json`,
`receipts/2026-10-24-probe-horizon.md` + `receipts/2026-10-24-probe-horizon-gate.md`.

Lane (H=400, 2H=800, refH=1600, N=4M, identical draws across horizons):
doubling the horizon halves the structured truncation deficit — mean missing
mass per ROI bin vs the refH render 41.38 -> 20.59 (mandel, raw shrink ratio
0.4976) and 60.62 -> 29.09 (cosmut, 0.4799); normalized b -0.129 -> -0.058 /
-0.034 -> -0.015; boundary-localized exactly as predicted (top boundary-score
tercile carries 50.3% / 71.3% of ROI missing mass at 33% pixel share,
Spearman 0.90-0.95); the deposit replay identifies the deficit with the tiny
slow-escaper cohort (652/633 orbits of 4M at the gate depths) to machine
precision (corr/sum ratio 1.00000).

**Confirmation gate (adjudicator item 4; H=1500, 2H=3000, refH=6000 — the
audited channel, same maps, same seeds, same batch convention, N=4M):
gate = CONFIRMED.** Deciding numbers (raw shrink ratio 2H/H, audited cap-1500
ROI): **mandel 0.48490, cosmut 0.49287** — both inside the pre-declared
[0.35, 0.65] band; seed-b checks 0.50373 / 0.52374, normalized-b ratios
0.4434 / 0.4717, cap-400-mask ratios 0.4853 / 0.4935, and the
cohort-decomposition predictions 0.4849 / 0.4929 all land in-band too.
Missing mass at the audited channel: mandel 44.14 -> 21.40, cosmut 65.37 ->
32.22 per ROI bin per doubling; new-escaper mass halves per octave
(0.0113% -> 0.0050% of drawn); bias far outside noise (bias/SE 33-466 raw);
boundary-localized (top tercile 54.0% / 72.5%, Spearman 0.896 / 0.946);
identity checks exact.

Sharp corollary (lane, measured): the audited S2 bias/SE = 104-4001 is NOT
this mechanism — S2's deficit vs the same-cap reference is horizon-INDEPENDENT
across a doubling (ratios 1.031 / 1.076), so the truncation bias is a
property of the capped estimand shared by every sampler, while S2's excess
skew has a different cause ("incomplete chain exploration", per the paper).

### 3. Randomized-horizon S3 (Rhee-Glynn single-term) — REFUTED as a practical improvement

`src/probe_s3.py`, `results/probe_s3_pilot.json`, `probe_s3_validate.json`,
`probe_s3_runs.json`, `probe_s3_headtohead.json`,
`receipts/2026-10-24-probe-s3.md`.

S3 is exactly unbiased (cap-40 z-test vs a shared S0@8M target:
z = +2.65 mandel / +2.35 cosmut, |z| <= 3; S0-harness clone bit-exact,
TV = 0.0) and still loses everywhere:

- Slope toward -0.5: S0 -0.461 / -0.486 vs S3 -0.076 / -0.265 (worse on both
  maps; MC theory -0.5).
- Matched compute at the top rung (S3 given S0@4M's budget): mean ROI rel err
  ratio S3/S0 = **15.98x (mandel) / 9.27x (cosmut)** per evaluator calls and
  **17.77x / 8.52x** per second.
- Variance cost: e_N (= mean_rel_err^2 x N) ratio S3/S0 = **278.9x / 253.2x**;
  weight ESS 3.1% of draws (mandel), max weight growing with N — the
  randomized-truncation variance premium does not converge.
- Mechanism (measured): escape-time orbit-density level increments do NOT
  decay — A_h - A_{h-1} is the entire trajectory of an orbit escaping exactly
  at h (m_h ~ h points) while P(t=h) collapses, so E|D_h|^2 is flat-to-rising
  across four decades of h (0.54 at h=2 vs 0.72 at h=1200) and the
  Rhee-Glynn premium sum never converges. Randomized truncation trades a
  decaying bias for a non-decaying variance — the opposite of the regime
  where it wins.
- The S3 verdict code's bias branch (the b in |b|/SE: per-run
  signed_mean = mean_ROI[(X-ref)/ref] on mass-1 histograms, seed-averaged
  over the S3 triple; SE from the first two seeds of the same-budget S0 pair;
  branch requires S3 within 3 SE of zero AND S2 >= 5x S3's ratio) is quoted
  verbatim in the receipt's 2026-10-24 addendum.

### 4. Literature-closure negatives (theses; CN/RU/patent blind spots)

`results/probe_theses_literature.json`, `results/probe_cnru_lit.json`,
`receipts/2026-10-24-probe-theses.md`,
`receipts/2026-10-24-probe-cnki-mathnet.md`. (The theses lane's scripted
probes live in the paper tree as `experiments/src/probe_theses_literature.py`;
the CN/RU lane was a fetch lane whose machine-readable inventory is the
`probe_cnru_lit.json` itself — no separate script file exists in src/.)

Honest negatives, 25/25 and 24/30 measurable probes respectively: no
thesis-level prior art on forward-orbit equidistribution of escaping seeds
(EThOS/theses.fr/arXiv: "buddhabrot" -> 0 entries); Bitterli's dissertation
does NOT formalize the inverse-Jacobian identity (it lives only on the live
grey portfolio page, re-anchored and Wayback-archived; doctorate = Dartmouth
2022, not EPFL); IIM sampling bias documented at master's level (Matteau
2014) with the peer-reviewed fix origin (Saupe 1987); CNKI/ChinaXiv are
channel-walled (logged outages, indexed sweeps substituted), SciChina/Acta
Sinica/Math-Net.Ru measured — no Chinese or Russian item on escape-time
occupation measures; Google Patents: no orbit-density-with-correction claim
in 4 query formulations (3 further queries rate-limited). "Not found" is
recorded as "not found", not "does not exist".

## Provenance

- Kernels: this repo @ `4d87ef3` (audited) == `d29483d` (session HEAD) for
  brot_farm.py / buddhabrot.py / cosbrot.py / brot_samplers.py.
- Estimators, ROI rule, metrics: the audited study modules (conv_samplers /
  conv_maps / analyze), imported read-only.
- Seeds: probe-private (bridge 20261024-20261103; horizon lanes
  867530900-867530912), documented per lane in the receipts; no study seed
  collision.
- Environment: python 3.14.6, numpy 2.4.4, one 16-core Windows box;
  walls 1289 s (bridge), 802 s (horizon lane), 751 s (gate), ~45 min (S3).

## Receipt index

| receipt | lane | verdict |
|---|---|---|
| `receipts/2026-10-24-probe-bridge.md` | folk bridge | REFUTED (11-226x; erratum annotated) |
| `receipts/2026-10-24-probe-horizon.md` | truncation lane 400/800/1600 | LICENSED |
| `receipts/2026-10-24-probe-horizon-gate.md` | gate 1500/3000/6000 | **CONFIRMED** |
| `receipts/2026-10-24-probe-s3.md` | randomized horizon S3 | REFUTED (dominated; honest negative) |
| `receipts/2026-10-24-probe-theses.md` | thesis prior art | closed (negatives + 2 premise corrections) |
| `receipts/2026-10-24-probe-cnki-mathnet.md` | CN/RU/patent blind spots | closed (negatives, outages logged) |
