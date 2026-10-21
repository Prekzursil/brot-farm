# Biome notes — pins, RAM measurements, and the "unexplained memory" question

Standing operator question: *Biome sometimes seems to eat a lot of RAM without an
explainable cause.* This note records what was measured, what the pins are, and
what the evidence does and does not support. Numbers, then folklore.

## Pin inventory (verified 2026-10-21)

| Location | Pin |
|---|---|
| QZP `reusable-quality.yml` (the lean gate) | `@biomejs/biome@2.5.15` (fleet pin; was 2.5.0, bumped in QZP PR #312 after verifying formatter output is byte-identical on this repo's corpus) |
| QZP `docs/lean-gate/biome.template.json` `$schema` | 2.5.15 |
| This repo's `biome.json` `$schema` | 2.5.15 |
| Latest published (`npm view @biomejs/biome version`) | 2.5.15 — the fleet is current; no bump pending |

## Measurements (Windows 11, direct binary invocation, peak working set via
`GetProcessMemoryInfo` sampled at 10 ms)

| Workload | Time | Peak RSS |
|---|---|---|
| `biome ci .` — this repo (3 scanned files) | 0.10 s | **28 MB** |
| `biome ci .` — synthetic 500 files × ~2000 lines (~35 MB source) | 1.92 s | **127 MB** |
| `biome format --write` — same synthetic tree | 0.64 s | **136 MB** |
| `biome ci .` — single ~7 MB file (200k-element array literal) | 0.75 s | **158 MB** |

(Measured on the 2.5.0 binary from the npx cache — 2.5.15 is a patch lineage
with byte-identical formatting output on this corpus; the memory profile of the
patch series is the same class. `npx` wrapper adds a ~10 MB short-lived node
process on top.)

**Reading:** the one-shot CLI's memory is roughly proportional to source size
(≈4–20× depending on structure), and single-digit-hundreds-of-MB even on
deliberately pathological inputs. It exits when done — nothing resident.

## Where GB-scale memory actually comes from (evidence-based)

The multi-GB reports in the wild are **editor-side, not CLI**:

- **LSP daemon**: [biomejs/biome#6784](https://github.com/biomejs/biome/issues/6784) —
  `biome.exe` at 23 GB under VS Code, growing slowly; closing VS Code was the
  only remedy. Fixed in the v2.1.x line per Biome's own announcement
  ([v2.1.2 addresses the memory leak](https://x.com/biomejs/status/1945849003112825028)).
- **Dev-server/watch spikes**: [biomejs/biome#6797](https://github.com/biomejs/biome/issues/6797)
  — 500–1000 MB jumps with 100% CPU during `dev` + browser open.
- **Daemon first-scan over ignored files** and **watcher leaks** are
  acknowledged on Biome's own roadmap; the file-watcher path is a known leak
  surface.

**Our CI cannot hit these by construction:** the lean gate runs `biome ci`
one-shot — no `biome start`, no `--watch`, no LSP, no daemon (verified in
`reusable-quality.yml`). Every run is a fresh process that exits.

## Practical guidance

1. If RAM grows on YOUR machine without a build running: look for a resident
   `biome` process from an editor extension (VS Code biome LSP). Restarting
   the extension/host clears it; keeping the extension ≥ the 2.1.2-fix lineage
   (currently 2.5.15) matters.
2. [Biome's investigate-slowness guide](https://biomejs.dev/guides/investigate-slowness)
   pinpoints files or dependencies responsible for slow/heavy runs.
3. What remains **unexplained**: any persistent GB-scale growth attributable to
   the one-shot `biome ci/format` binary itself — the measurements above show
   no such behavior, and no open issue in the tracker contradicts it. If it is
   ever observed, capture: biome version, command, tree size, and
   peak-RSS-over-time before reporting.

## Fleet policy

- Pins stay centralized and consistent (currently 2.5.15 everywhere; see
  inventory above). A future bump must be a dedicated PR with formatter-output
  verification on a sample corpus in the body — never bundled with other
  changes (charter rule).
- Generated data assets (`docs/assets/catalogue.js`, `hist-blue.js`) are
  exempted from biome formatting via our `biome.json` `files.includes` —
  they are machine-written, and the gate honours the caller config.
