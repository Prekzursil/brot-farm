# Browser repair log (LANE 2)

Operator report under test: *"math and playground don't work."*
Verdict: **refuted for the current deployment** — the reproduction matrix (Playwright,
Chromium + Firefox + WebKit, desktop + 390 px, https and file://) found math.html and
playground.html fully functional, consoles clean, in every browser. The report was
nevertheless treated as true until disproven, and it caught four real defects on the way.

## Failure matrix (feature → observed → root cause → fix)

| # | Feature | Observed | Root cause | Fix |
|---|---------|----------|-----------|-----|
| 1 | Error banner (new defense) | `pageerror: Invalid or unexpected token` on every page after the banner shipped | The banner's inline JS contained a **literal newline inside a single-quoted string** (`'\n'` written as a real newline via an escaping chain) → unterminated string literal → the banner script never registered its listeners | Rewrote both joins with `String.fromCharCode(10)` (zero backslashes — immune to every escaping chain); `node --check` now passes |
| 2 | Hero "developing photograph" | `#develop-photo` lookup returned `null` on https runs | `app.js` replaces the `<img>` with a canvas **without carrying any id** — the element became unaddressable after animation start | Canvas now gets `id="develop-photo-view"` |
| 3 | Gallery thumbs | 1–5 thumbs reported `naturalWidth === 0` (varied per browser) | `loading="lazy"` thumbs below the fold are legitimately unloaded; the verifier counted them as broken, and at 390 px the single scroll pass raced the decode | Verifier now scrolls through the page twice with decode time before counting |
| 4 | Canvas interactions at 390 px | `Page.click` timeouts on `#orbit-demo` / `#ex-canvas` | Click positions were given in canvas **attribute** pixels (400/220); at mobile widths the CSS box is ~350 px so the point fell outside the element and Playwright's actionability check looped forever | Positions are now small element-relative coords that fit inside the CSS box at any width |
| 5 | Formula sandbox (suspect) | "formula applied" message absent from HUD | Not a defect: the message is transient (`insertAdjacentHTML`) and the rAF HUD overwrites it; the durable state is `map custom formula` in the HUD | Verifier asserts the durable state; manually confirmed the sandbox still compiles and runs post-Biome-reformat |

## Stale-cache hypothesis (tested)

The JS was Biome-reformatted after the last green live-browser pass, so a client
serving mixed old/new assets was a live suspect. Outcome: **the deployed pair was
consistent** (the reformat was semantics-preserving; every interaction passes).
The class of failure is now structurally impossible:

- **Asset versioning**: every `assets/*` reference in every page carries
  `?v=<sha1[:8] of the file>` (stamped by `scripts/version_assets.py`), so a deploy
  can never pair new HTML with old JS — a changed asset changes its URL.
- **Pages drift tripwire**: the Pages workflow re-runs the versioner with
  `--check` and **fails the deploy** if it would change anything, so the deployed
  site can never silently differ from the repo.
- **CI tripwire**: the `site` job runs the same `--check` on every push/PR.

## Durable defenses shipped

1. Asset versioning + drift tripwires (above). The build hash is stamped on
   `<html data-build="…">` and shown in error reports.
2. **On-page error banner** (inline, zero dependencies, runs before every other
   script): any `error` / `unhandledrejection` shows a fixed banner with the
   message, the build hash, and a *copy report* button (URL + build + UA + last
   2 kB of the error log). Future "doesn't work" reports arrive with data.
3. **Automated site suite** — `scripts/verify_site.py`: the full matrix (3
   browsers × desktop/mobile × http/file, detector self-test, canvas-pixel
   probes on every canvas, all interactions, degradation probe with the app.js
   asset blocked). Runs in CI (`site` job, Chromium, local server) on every
   push and PR. Site health is a gate, not a one-off.

## Decision record — coverage of the site tooling (charter §100%-line+branch)

- `scripts/version_assets.py` is fully unit-tested and inside the coverage set
  (100% line+branch).
- `scripts/verify_site.py` is deliberately **outside** the coverage set
  (`.coveragerc` note): it is the E2E harness itself — it requires real
  browsers, and its green run in CI *is* its test. Ruff and basedpyright still
  gate it.

## Verification evidence

- Local: `python scripts/verify_site.py --browsers chromium,firefox,webkit --origin http`
  → **81/81 PASS** (includes 390 px mobile lanes and the app.js-blocked degradation probe).
- Live: same matrix against the deployed Pages URL — all functional probes pass;
  versioning/banner checks flipped green after the L2 deploy (see CI run).
