<!-- Checklist maps 1:1 to the gates CI actually runs. Check items only when
     you ran them and they passed — reviewers re-run everything. -->

## What & why

<!-- One paragraph: what changes, and why (link the issue if there is one). -->

## Gate checklist — 1:1 with CI

### Preflight lanes (`bash scripts/preflight.sh` — run from the repo root)

- [ ] **gate 1a — ruff**: `ruff check .` + `ruff format --check .` clean
- [ ] **gate 2 — basedpyright (standard)**: zero errors
- [ ] **gate 1b — oxlint** (pinned 1.69.0): `docs/assets/*.js` clean, `--deny-warnings`
- [ ] **gate 1c — biome format** (pin read from QZP `tool-pins.yml` at runtime): no diffs

### Coverage gate

- [ ] **`python -m pytest --cov` at 100 % line AND branch** for every new/changed
      Python line — tests added in the same change; `# pragma: no cover` only
      on `__main__` guards

### Site suite (anything under `docs/`)

- [ ] **`python scripts/verify_site.py --browsers chromium --origin http`** green,
      and a probe added to it for any new interactive UI

### Research lab notebook (anything under `research/`)

- [ ] **`python scripts/check_research.py`** passes (also run by preflight): results
      parse and are non-empty, receipts carry the skeleton sentinel in their first
      5 lines, sources byte-compile

### Asset versioning (anything under `docs/assets/`)

- [ ] **`python scripts/version_assets.py`** run and the re-stamped `?v=` hashes +
      `data-build` committed; `python scripts/version_assets.py --check` exits 0

### Parity gate (new/changed maps or `usermaps/`, `docs/assets/catalogue.js`)

- [ ] **`test_build_suite.py::test_python_javascript_map_parity`** and
      **`test_every_usermap_in_catalogue_js`** pass; catalogue regenerated with
      `python brot_build.py catalogue` (never hand-edited)

## Not applicable

<!-- Strike the gate groups that don't apply, e.g.: -->
<!-- * Site suite — no docs/ changes in this PR. -->

---

**Never weaken a gate to pass it.** If a gate is wrong or impossible, say so in
the PR and link the quality-zero-platform change that fixes it (see
[CONTRIBUTING.md](https://github.com/Prekzursil/fractal-darkroom/blob/main/CONTRIBUTING.md),
Path 3).
