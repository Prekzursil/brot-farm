# Receipt — Probe: preimage-sampling histogram vs forward orbit-density histogram (the bridge test)

If it still reads this way, the lane died before measuring anything and no verdict here may be cited.

Sentinel discharged — the lane measured, twice, end to end. Measured inventory of this run (all numbers
recomputed by `experiments/src/probe_preimage.py` this session, JSON of record
`experiments/results/probe_preimage.json`, `ok=true`, wall 1289.3 s):

- 5 bridge tests, each comparing an inverse-iteration (preimage) histogram of a fixed connectedness-verified
  map against a forward orbit-density histogram on the study's own 512x512 grid and top-decile ROI bins:
  1. `julia_connected_c-1` — fixed-map bridge, the decisive one: forward = the farm's `julia`-map estimator
     (brot_farm.py:445-457 flow, farm kernels `escape_mask`/`plot_orbits`) rendered fresh at reference grade
     (S0, 40M seeds, cap 1500) for f(z)=z^2-1 (basilica, connected J); backward = IIM on the same f.
     L1(preimage, forward-ref) = **1.8952** vs largest null **0.0686** (forward halves) → **27.6x**.
  2. `julia_asconfigured_c-0.7+0.27i` — same estimator flow at the farm's configured julia parameter,
     whose critical orbit ESCAPES (measured; J disconnected, a Cantor dust). L1 = **1.9718** vs null
     **0.0087** → **225.7x** (outside the connected-case identity; run anyway and labeled).
  3. `mandel_c-1` — IIM(f(z)=z^2-1) vs the study's cached cap-1500 40M Buddha reference
     (`data/ref_mandel_1500.npz`). L1 = **1.9316** vs null **0.1540** → **12.5x**.
  4. `mandel_c-0.1` — L1 = **1.9965** vs null **0.1540** → **13.0x**.
  5. `z3_c0.25` — IIM(f(z)=z^3+0.25) vs `data/ref_z3_1500.npz`. L1 = **1.9819** vs null **0.1807** → **11.0x**.
- L1 has range [0,2]; every bridge sits at 1.90-2.00, i.e. the supports are nearly disjoint at the study's
  bins — confirmed structurally (see "Structure of the mismatch" below). A pass needed within ~3x of the
  null. **Verdict: REFUTED on every map tested** (pre-stated rule in the script docstring and below).

- Date: 2026-10-24. Lane: numeric probe (bridge test), one 16-core machine, Git-Bash/Windows, Python
  3.14.6 / numpy 2.4.4. Everything ran solo this session; no audited-tree file other than the three
  artifacts listed at the end was created or modified.

## What was tested, in one paragraph

Background claims (each fetched and quoted this session, sources below): for polynomials, preimage mass
distributions converge to the measure of maximal entropy (Brolin 1965); random backward iteration with
uniform branch choice samples it (Hawkins-Taylor, IJBC 2003); for connected Julia sets that measure IS the
harmonic measure from infinity (Binder-Makarov-Smirnov, Duke 2003). The folk belief under test: that the
fractal-renderer FORWARD orbit-density histogram (the S0 estimator this paper measures convergence for)
targets the same measure. The test: render both on the study's grid, on the study's ROI, at comparable
budgets, and compare L1 distances against the estimator noise floor measured the same way. It fails by
more than an order of magnitude everywhere, and the failure is structured, not noise.

## Design (fixed in the script docstring before the long runs)

- Grid/binning: the study's own — 512x512 over each map's plot window; ROI = `analyze.roi_from_ref`
  verbatim (top decile of positive reference-count pixels, k = ceil(0.1*n_pos), threshold = k-th largest
  count), imported from the audited analysis module, so binning is identical to the convergence study.
- Metric: `L1 = sum_ROI |a_p/sum_ROI(a) - b_p/sum_ROI(b)|` on raw counts, both sides mass-1 on ROI.
- Nulls (pre-stated): (a) two statistically independent halves of the forward reference (seed-stream split
  into alternating blocks, both halves rendered through the same kernels); (b) the study's own independent
  4M S0 study/control pair (cached; two full independent runs); (c) independent-4M-vs-40M
  (`cached_study4M_vs_ref40M`); (d) preimage self-noise: two independent preimage replicas at half budget.
  VERDICT rule: licensed iff bridge L1 <= ~3x the largest null on EVERY map; refuted if it exceeds by a
  wide structured margin; inconclusive only if compute binds. Nothing was upgraded post hoc.
- Preimage sampler (candidate): random inverse iteration on f(z)=z^power+c, FIXED c; z2: w -> +-(w-c)^(1/2)
  with uniform +- branch; z3: uniform branch over the three roots of unity times the principal cube root;
  start w0 = 0.31-0.72i (generic, non-exceptional); 4096 chains x 24,415 steps + 2,000 burn-in steps per
  chain = 100,003,840 post-burn visits (replica: 50,003,968, independent seed); visits binned in-frame on
  the study grid. Diagnostics recorded: NaN visits 0 everywhere; branch frequencies balanced
  (z2: 0.50003/0.49997; z3: 0.33338/0.33330/0.33332); mixing check = preimage time-split L1 (first vs
  second half of the post-burn stream) 0.0049-0.0096, same scale as the replica floor -> burn-in is
  sufficient and no re-rooting/phase-doubling correction was needed. Naive-IIM critical-point imbalance:
  uniform branch choice is the Hawkins-Taylor-provable scheme; the measured branch balance and the tiny
  replica/time-split floors are the evidence the scheme behaved here (its effect, had it misfired, would
  have shown as preimage self-noise at the null scale — it does not).
- Forward references:
  - julia-flow bridges: the farm's own julia-map branch, mirrored line-for-line through the farm kernels
    (`bf.escape_mask`, `bf.plot_orbits`, step `bf.s_std`, escape `bf.g_z` chunk 32; seeds z0 ~ U((-1.8,1.8)^2),
    fixed c, escapers advanced once and plotted from z1 — brot_farm.py:445-457): fresh 40M-seed cap-1500
    reference (seed 20261101), plus a 4M-seed cap-80 run (seed 20261102) for the cap trend; halves of the
    40M run give the literal "two independent halves" null. 1M-seed rate pilot ran first with an auto-scale
    guard (40M projected 126 s < 1800 s guard; no scaling triggered).
  - mandel/z3 bridges: the study's cached cap-1500 references (`data/ref_{map}_1500.npz`, S0 @ 40M) exactly
    as used by `analyze.py`; nulls from the cached independent 4M study/control pair plus a fresh
    mandel S0 4M run split into halves (seed 20261103). z3 nulls reuse the cached pair only (equivalent
    statistic: two independent 4M S0 realizations) — recorded as a design choice, not an omission.
- Seeds (numpy default_rng): preimage main 20261024, replica 20261025, julia rate-pilot 20261023, julia
  ref 20261101, julia cap-80 20261102, mandel fresh halves 20261103. Study-cached runs keep their recorded
  study seeds. No probe seed collides with any study seed (study base 20261021).

## Connectedness of each tested map (numeric side of the criterion)

Criterion (Blanchard; Yale FG page; quotes below): J(f) connected iff the orbits of ALL finite critical
points are bounded; for single-critical-point families f(z)=z^n+c this is the connected/Cantor dichotomy
and c in M_n is exactly the connected case. Measured critical orbits (cap 200,000, escape if |z|>1e6):

| map | critical orbit | bounded? | max |z| | J connected? |
|---|---|---|---|---|
| z^2 - 1 (basilica) | 0 -> -1 -> 0 (superattracting 2-cycle) | yes | 1.0000 | yes |
| z^2 - 0.1 | converges to attracting fixed point | yes | 0.1000 | yes |
| z^3 + 0.25 | converges to attracting fixed point ~0.2687 | yes | 0.2696 | yes |
| z^2 + (-0.7+0.27i) (farm's julia map) | escapes (~step 13) | **no** | > 1e6 | **no (Cantor)** |

The farm's configured julia parameter c = -0.7+0.27i is therefore OUTSIDE the Mandelbrot set: its Julia
set is a Cantor dust, the connected-case BMS identity does not apply, and the bridge was still run — as
measured, labeled `julia_asconfigured`, and excluded from the connected-case claim. The three connected
maps (z^2-1, z^2-0.1, z^3+0.25) carry the verdict.

## Results (L1 on ROI, both sides mass-1 on ROI)

| bridge | forward reference | bridge L1 | nulls (fwd halves / cached pair / 4M-vs-ref / pre-replica) | max null | ratio |
|---|---|---|---|---|---|
| julia_connected_c-1 | fresh 40M cap1500 (36,430,829 pts) | 1.8952 | 0.0686 / - / - / 0.0065 | 0.0686 | **27.6x** |
| julia_asconfigured | fresh 40M cap1500 | 1.9718 | 0.0057 / - / - / 0.0087 | 0.0087 | **225.7x** |
| mandel_c-1 | cached 40M cap1500 (135,455,437 pts) | 1.9316 | 0.1540 / 0.1116 / 0.0819 / 0.0070 | 0.1540 | **12.5x** |
| mandel_c-0.1 | cached 40M cap1500 | 1.9965 | 0.1540 / 0.1116 / 0.0819 / 0.0044 | 0.1540 | **13.0x** |
| z3_c0.25 | cached 40M cap1500 (97,483,584 pts) | 1.9820 | 0.1807 / 0.1705 / 0.1247 / 0.0049 | 0.1807 | **11.0x** |

Cross-check against the audited study: my `cached_study4M_vs_ref40M` null computes to 0.08190 (mandel)
and 0.12470 (z3); the study's own per-pixel mean rel err for S0 @ 4M on the same ROI is 0.0819 and 0.1243
(`results/cell_mandel_1500.json`, `results/cell_z3_1500.json`) — the probe's distance metric and ROI
reproduce the study's error scale exactly, so the nulls are the study's own noise floor, not a new one.

Cap trend (julia_connected bridge): L1(cap-80 cloud, cap-1500 ref) = 0.1563 — moving the channel from 80
to 1500 moves the forward cloud a sixth of the distance it would need to move to reach the preimage
measure, and L1(preimage, cap-80 cloud) = 1.8953 vs L1(preimage, cap-1500 ref) = 1.8952: no trend toward
the backward measure anywhere in the study's cap range.

## Structure of the mismatch (why "refuted" and not "inconclusive noise")

- Supports are near-disjoint at the study's bins. On the forward-defined ROI, the share of ROI pixels that
  receive ZERO preimage visits: 22,388/23,562 = 95.0% (julia_connected), 92.7% (julia_asconfigured),
  95.8% (mandel_c-1), 99.8% (mandel_c-0.1), 99.1% (z3_c0.25).
- Reference mass on pixels the preimage ever visits: 6.1% / 5.3% / 4.3% / 0.2% / 0.9% respectively.
- Reverse ROI (top decile of the preimage's own visited pixels — 126 to 565 px, the curves themselves):
  the forward reference puts L1 0.43-1.16 against the preimage there, vs preimage replica nulls 0.003-0.004.
  The mismatch survives the comparison being moved onto the backward measure's home bins.
- Preimage mass that falls inside the forward ROI at all: 27.1% / 14.6% / 25.7% / 4.1% / 14.8% — the
  backward measure mostly lives off the forward ROI (out of frame where the study window clips the curve:
  for z^2-1 on the mandel window, 19.8% of all IIM visits land outside the plot window, x > 1.15 basilica
  tip; in-frame fraction 0.802, recorded per bridge).
- Mechanical account on the fixed-map bridge (recorded, not excused): the study-style forward estimator at
  this frame plots only **1.02 in-frame points per escaping seed** (36,430,829 points / 35,634,753 escapers
  at cap 1500; the identical 1.02 ratio at cap 80) — with the escape radius |z|>2 against a frame that
  reaches 1.8, most seeds escape in 1-2 steps, so the S0 histogram is dominated by each escaper's first
  point: a broad 2D seed-density image, not a curve-hugging transient density. The preimage measure is
  singular on the Julia curve. At the study's bin size (0.0070 in the julia window) the two cannot and do
  not coincide; every null (both samplers' self-noise) is 20-300x smaller than the gap.

## Verdict

**REFUTED** — per the rule fixed before the runs: the preimage-vs-orbit distances are NOT the same order
of magnitude as the null on any map tested (11x-226x, threshold was 3x), and the margin is structured
(near-disjoint bin supports in both directions, cap-trend absent, both samplers individually converged to
floors 20-300x below the gap). The forward orbit-density histogram of this renderer family does not
numerically coincide with the backward-iteration (max-entropy / harmonic-measure) histogram on the study's
ROI at any tested cap (80, 1500) or map (connected basilica, connected near-circle, connected cubic,
Cantor dust), at reference-grade budgets on both sides.

What this does NOT refute: the theorems. Brolin/Hawkins-Taylor are about the backward limit (which the
preimage side reproduces, self-noise 0.0044-0.0087 after burn-in); Binder-Makarov-Smirnov identify that
limit with harmonic measure from infinity for connected J. What it refutes is the folk bridge — the claim
that the renderer's forward orbit-counting histogram is numerically that measure. The paper already
disclaims the identity explicitly (read this session; paper.tex:361-365): "What $P$ is not: it is not
harmonic measure (Brownian hitting measure \cite{Kakutani1944}), not the Brolin--Lyubich measure of
maximal entropy \cite{Brolin1965,Lyubich1981,Freire1983}, and not an invariant measure on the Julia set;
it is the expected orbit-counting density of a transient cloud". The measurement agrees with the paper,
and closes the gap in the record: nobody can now assert the bridge without contradicting a measured,
doubly-reproduced number.

## Side finding (gallery-relevant, measured)

The farm's configured `julia` map — "orbit density through the Julia set . c = -0.7 + 0.27i"
(brot_farm.py FRACS entry, read this session) — iterates z <- z^2 + (-0.7+0.27i) whose critical orbit
escapes: by the quoted criterion its Julia set is a Cantor (Fatou-dust) set, not a connected one. Any
caption or prose that reads that map as "the Julia set" as a connected curve would be wrong; its escape
fraction here measured 0.8881 at cap 80 and <del>0.8909 at cap 1500 (interior share ~11%)</del>, consistent with a
dust of zero area plus transient resonance).

> **[Correction, 2026-10-24 — closeout audit: row swap with `julia_connected_c-1`. Original text kept
> above; the struck clause is WRONG.]** Recomputed this session from the JSON of record
> `experiments/results/probe_preimage.json` (`ok=true`): the struck cap-1500 figures belong to the
> `julia_connected_c-1` map, not to `julia_asconfigured_c-0.7+0.27i`.
> - `julia_asconfigured_c-0.7+0.27i` (`maps[1]`): escape_fraction at cap 1500 (40M seeds, seed 20261101,
>   key `forward`) = **0.999860275** (39,994,411 of 40,000,000 escaped) → interior share
>   1 − 0.999860275 = 0.000139725 ≈ **0.014%**, not ~11%; at cap 80 (4M seeds, seed 20261102,
>   key `forward_cap80`) = 0.88808925 ≈ 0.8881 — the cap-80 figure as originally written is correct.
> - `julia_connected_c-1` (`maps[0]`): escape_fraction **0.890868825** at cap 1500 (interior 10.913%) and
>   **0.8908615** at cap 80 — these are the struck 0.8909 / ~11% values.
> Unaffected: the side finding's connectedness conclusion (critical orbit escapes by cap 200,000,
> `maps[1].critical_orbit.bounded=false` → J is a Cantor dust). The corrected reading is a *cleaner* dust
> signature, not a weaker one: escape fraction rises 0.8881 → 0.99986 as cap goes 80 → 1500 and the
> interior share at reference cap is ~0.014%, not ~11% (a persistent ~11% interior is the connected
> basilica's, which has a genuine filled interior).

## Sources (all fetched this session; mechanism named per claim)

- Random backward iteration samples the max-entropy measure — Hawkins & Taylor, "Maximal entropy measure
  for rational maps and a random iteration algorithm for Julia sets", Intl. J. of Bifurcation and Chaos
  13(6) (2003) 1442-1447. https://janehawkins.web.unc.edu/wp-content/uploads/sites/17111/2019/09/hawkins-taylor-IJBC.pdf
  (jina-reader). Abstract, verbatim: "We prove that for any rational map of degree d, the unique invariant
  measure of entropy log d can be obtained as the weak limit of atomic probability measures obtained by
  taking a random backward orbit along an arbitrary nonexceptional point. This proves that the computer
  algorithm suggested by Barnsley in some specific cases works for all rational maps and is the algorithm
  used to produce Julia sets in the paper." Publication line, verbatim: "This note has been published as
  an appendix in the paper 'Lebesgue ergodic rational maps in parameter space', by J. Hawkins, Intl. J.
  of Bifurcation and Chaos, Vol. 13, 6 (2003), 1423-1447, and is sometimes cited as: 'Maximal entropy
  measure for rational maps and a random iteration algorithm', with Michael Taylor, Intl. J. of Bif. and
  Chaos, Vol. 13, 6 (2003), 1442-1447."
- Harmonic measure from infinity = measure of maximal entropy (connected polynomial Julia sets) — Binder,
  Makarov & Smirnov, Duke Math. J. 120(3) (2003) 343-365. https://www.unige.ch/~smirnov/papers/bms-j.pdf
  (also https://doi.org/10.1215/s0012-7094-03-11725-1) (exa-search + jina-reader). Verbatim: "For a
  polynomial F, let Omega_F denote the basin of attraction to infinity: Omega_F = {z : F^n z -> infinity},
  so that J_F = dOmega_F is the Julia set of F. The harmonic measure omega_infinity of Omega_F is the
  measure of maximal entropy with respect to F."
- Preimage mass distributions converge to the balanced (= maximal-entropy) measure — Brolin, "Invariant
  sets under iteration of rational functions", Arkiv for Matematik 6 (1965) 103-144.
  https://doi.org/10.1007/bf02591353 (exa-search; full scan
  https://archive.ymsc.tsinghua.edu.cn/pacm_download/116/7043-11512_2007_Article_BF02591353.pdf via
  jina-reader; 1965 OCR degraded, cleaned characters bracketed). Verbatim (OCR-cleaned): "we define a
  mass distribution mu_k by placing the mass [1/d^k] at the k-th roots of the equation P^k(z) = z_0,
  where P(z) is a polynomial of degree k and z_0 any point in the plane with at most two exceptions. We
  prove that mu_k -> mu_* under weak convergence, where mu_* is the equilibrium distribution of F with
  respect to the logarithmic potential." And Theorem 16.1: "If {f_n} is the sequence of mass distributions
  defined above and f_* denotes the equilibrium distribution of F, then lim f_n = f_*, weak convergence."
  And: "by regarding P(z) as a transformation T on F we prove that T preserves mu_* and that T is strongly
  mixing."
- Connectedness criterion (critical orbits) — Blanchard, "Disconnected Julia Sets",
  http://www.its.caltech.edu/~matilde/DisconnectedJuliaSets.pdf (exa-search). Verbatim: "On the other
  hand, if the orbits of all of the finite critical points are bounded, then J is connected." Yale
  Fractal Geometry site, "The Role of Critical Points",
  https://gauss.math.yale.edu/public_html/People/frame/Fractals/MandelSet/MandelDef/MandelCritPts/MandelCritPts.html
  (exa-search). Verbatim: "the Julia set is connected if the orbits of all critical points remain bounded,
  and - the Julia set is a Cantor set if the orbits of all critical points escape to infinity." and "For
  polynomials having a single critical point, f(z) = z^n + c for example, Julia sets must be either
  connected or Cantor sets, and the Mandelbrot set is the collection of all c for which the Julia set is
  connected."
- Connectedness locus of z^2+c — Wikipedia "Julia set", https://en.wikipedia.org/wiki/Julia_set
  (jina-reader). Verbatim: "the Mandelbrot set is defined as the set of all c such that J(f_c) is
  connected. For parameters outside the Mandelbrot set, the Julia set is a Cantor space: in this case it
  is sometimes referred to as Fatou dust."
- Internal (read this session, not URLs): paper.tex:361-365 disclaimer quote above; brot_farm.py julia
  FRACS entry and julia render branch (lines ~205-215, 445-457); analyze.py:42-56 ROI rule;
  conv_maps.py / conv_samplers.py estimator conventions; cell_mandel_1500.json / cell_z3_1500.json error
  scales.

## Artifacts

- `experiments/src/probe_preimage.py` — the probe (pilot + main); deterministic seeds; verdict rule in the
  docstring.
- `experiments/results/probe_preimage.json` — per-map: bridge distances, all nulls, overlap structure,
  reverse-ROI numbers, connectedness, budgets, seeds, runtimes. `ok=true`.
- `receipts/2026-10-24-probe-bridge.md` — this receipt.

## Deviations, failures, and caveats (nothing smoothed over)

- Run 1 of `main` completed all five bridges but crashed each bridge's overlap-diagnostics block on an
  indexing bug (`roi_mass_on` indexed a ROI-length vector with a full-grid mask). Fail-closed: run 1's
  JSON was overwritten by a fixed rerun (run 2), which is the artifact of record (`ok=true`, zero errors).
  The bridge/null numbers are bit-identical across the two runs (same seeds) — recorded as a determinism
  check. Run-1 wall 1264.2 s; run-2 wall 1289.3 s.
- Two throwaway log files created by run 1/2 (`experiments/logs/probe_bridge_20261024*.log`) were deleted
  after extraction because the discipline restricts new files to probe_*.py / probe_*.json /
  2026-10-24-probe-*.md; their content (the per-bridge completion lines) is reproduced in the JSON and
  above.
- julia_asconfigured is outside the connected-case identity (J disconnected, measured) — it is reported
  and labeled, not used to support the connected-case statement.
- mandel_c-1 preimage in-frame fraction is 0.802 (the basilica tip x in [1.15, 1.618] is clipped by the
  study's plot window, exactly as the study's own plot_orbits would clip it); all other bridges >= 0.998.
- z3 nulls use the study's cached independent 4M study/control pair instead of a fresh rendered pair
  (equivalent statistic, stated in advance in the script docstring); mandel got both (fresh halves AND
  cached pair).
- Budgets are reference-grade on both sides (40M seeds forward; 100M preimage visits) but a single
  machine-lane scale: an even larger forward budget would move the forward halves null DOWN (n^-1/2), i.e.
  widen the ratios, not close them; the cap axis, not the N axis, is the only direction that could move
  the bridge, and 80 -> 1500 moved it by 0.0001 (measured, julia_connected: 1.8953 vs 1.8952).

---
**2026-10-24 closeout annotation:** lint-only/ruff-format edit to `experiments/src/probe_preimage.py` (E402 noqa markers on the post-bootstrap imports; removal of one unused import / one unused variable). No numeric, protocol, or behavioral change; all measured values in this receipt are untouched. Repo copy under research/probe-2026-10-24/ re-synced and hash-verified.
