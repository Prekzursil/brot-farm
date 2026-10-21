# Contributing to Fractal Darkroom

Thanks for wanting to add something! There are **three ways in**, ordered by
effort — a picture for the collection (minutes, no code), a new fractal map
(the full quality bar), and platform/profile changes (operator-only).
A step-by-step walkthrough with screenshots lives at
[docs/contribute.html](https://prekzursil.github.io/fractal-darkroom/contribute.html).

Before anything: bugs and site errors go through the
[bug report form](https://github.com/Prekzursil/fractal-darkroom/issues/new?template=bug_report.yml) —
it asks for the **build hash** from the red error banner (bottom-left corner of
any site page) and the banner's **copy report** text, which is everything we
need to reproduce. Behavior that looks security-sensitive belongs in
[private vulnerability reporting](https://github.com/Prekzursil/fractal-darkroom/security/advisories/new),
never a public issue (see [SECURITY.md](SECURITY.md)).

For all code paths, one rule is absolute: **every gate must pass for the right
reason.** Never weaken a gate to pass it. Run
[`bash scripts/preflight.sh`](scripts/preflight.sh) before every push — it
reproduces every CI lane locally (ruff, basedpyright, oxlint, biome, and
pytest at 100 % line **and** branch coverage).

---

## Path 1 — Submit an APRS record (no code, minutes)

**APRS** = *Attractor Parameter Record Set*, the portable experiment record
(`.aprs.json`) defined in [docs/adr/0001-aprs.md](docs/adr/0001-aprs.md)
([schema](docs/aprs.schema.json)). Accepted records are curated into the
[community collection page](https://prekzursil.github.io/fractal-darkroom/collection.html).

1. **Find a variant in the playground.** Open
   [playground.html](https://prekzursil.github.io/fractal-darkroom/playground.html),
   scroll to *Build your own map* and *Experiments*. **Surprise me** composes a
   random valid grammar from a seed, **Mutate this** perturbs one operator of
   the current map, and the suggestion engine scores seeded candidates. Tune
   caps/window/gamma until the preview is worth keeping.
2. **Export.** Click **📦 export APRS** in the Experiments panel — the browser
   downloads `<name>.aprs.json` (validated in-browser against the same field
   set as the Python validator before it is ever written).
3. **Validate locally** (the exact check the intake bot runs):

   ```bash
   python scripts/validate_aprs.py my_map.aprs.json
   # -> OK my_map.aprs.json (schema v1)     (exit 0 = good)
   ```

   Prefer the CLI? Author the same record from a build-suite map:

   ```bash
   python brot_build.py aprs my_map --out my_map.aprs.json
   ```

4. **Open the APRS issue form**:
   [github.com/Prekzursil/fractal-darkroom/issues/new?template=aprs.yml](https://github.com/Prekzursil/fractal-darkroom/issues/new?template=aprs.yml).
   **Drag & drop the `.aprs.json` file into the attachment field** — the
   uploaded `…aprs.json` link in the issue body is what the bot downloads;
   pasted JSON without an attachment cannot be picked up. Add one line on why
   the map is worth keeping.
5. **The bot validates** ([`.github/workflows/aprs-intake.yml`](.github/workflows/aprs-intake.yml)):
   it downloads the attachment, re-runs `scripts/validate_aprs.py`, rejects
   `preview: null`, dedupes by preview hash against `collection/`, and comments
   pass/fail with reasons on your issue.
6. **A human merges.** On pass, the bot opens a curation PR adding
   `collection/<preview-hash>.aprs.json` plus the regenerated index
   (`scripts/build_collection.py`). Nothing merges automatically — every entry
   is curated by hand.

---

## Path 2 — Add a new fractal map (the full quality bar)

New maps enter through the build suite
([`brot_build.py`](brot_build.py)) and must clear **every** gate below. The two
`demo_*` maps in [`usermaps/`](usermaps) are the reference examples.

```bash
# 1. Scaffold a user map from the operator grammar
#    (real op f: cos sin tan sinh exp abs; imag op g: plain cos abs neg absxy;
#     power 2..5; families: mutation | fold | power)
python brot_build.py new my_map --family mutation --real tan --imag plain

# 2. Scout the sampling window (escape fraction per half-width;
#    you want a window whose escape fraction lands in 0.15–0.9)
python brot_build.py scout my_map

# 3. Fast deterministic preview (seconds) + the docs card thumb
#    (out/preview_my_map.png + docs/maps/my_map.jpg; regenerates the catalogue)
python brot_build.py preview my_map

# 4. The full quality bar: NaN-guarded escape predicate, channel sanity,
#    scalar smoke test, docs card present, playground catalogue parity
python brot_build.py check my_map      # must print: check: OK

# 5. Full-quality render (user maps join the farm list automatically)
python brot_farm.py render my_map
```

What `check` (and CI) enforce — all of it mandatory:

- **Grammar parity.** `docs/assets/catalogue.js` must list every
  `usermaps/*.py` entry; `test_build_suite.py::test_every_usermap_in_catalogue_js`
  and `test_python_javascript_map_parity` fail CI on drift. Never hand-edit
  `docs/assets/catalogue.js` — regenerate with `python brot_build.py catalogue`.
- **Docs card.** `docs/maps/<name>.jpg` (written by `preview`) + the generated
  catalogue entry that renders the card in the playground's build panel.
- **Tests at 100 % line *and* branch.** Any new Python line must be exercised
  by tests added in the same change; `# pragma: no cover` is only allowed on
  `__main__` guards. CI runs `python -m pytest --cov` with
  `fail_under = 100` (line and branch) on every supported Python.

Before pushing: `bash scripts/preflight.sh` (all lanes), and if you touched
anything under `docs/`, `python scripts/verify_site.py --browsers chromium --origin http`
plus `python scripts/version_assets.py` (then commit the re-stamped `?v=` hashes).

---

## Path 3 — Quality-platform profile & workflow changes (operator-only)

The CI quality lanes are **not defined in this repo**. `.github/workflows/quality.yml`
calls the reusable workflow of the
[quality-zero-platform](https://github.com/Prekzursil/quality-zero-platform)
(QZP) control plane, pinned to an exact commit; `scripts/preflight.sh` even
reads its biome version pin from QZP's `.quality/tool-pins.yml` at runtime so
local checks can never drift from CI.

- These changes are **operator-only** and happen **in the QZP repo**, via PR —
  never by editing lanes here and never by pushing QZP `main` directly
  (branch protection requires the *Control Plane Verify* and *CodeQL* checks).
- Every profile/workflow change PR **must include a drift report**: regenerate
  the ruleset payloads and show the diff is empty — see
  [`docs/audit/QZP-DRIFT-REPORT.md`](https://github.com/Prekzursil/quality-zero-platform/blob/main/docs/audit/QZP-DRIFT-REPORT.md)
  in the QZP repo for the exact command and format.
- Consumer repos like this one get updates through QZP's drift-sync PRs; if a
  lane change makes this repo red, the fix belongs in QZP — **never** weaken a
  gate locally to go green.

---

## Pull-request checklist (maps 1:1 to the CI gates)

See [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md) —
it is the same list CI enforces: preflight lanes green, 100 % line+branch
coverage, the Playwright site suite, asset versioning stamps, and the
map-parity tests.

## Conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md).
Reports go through [private vulnerability reporting](https://github.com/Prekzursil/fractal-darkroom/security/advisories/new)
or the maintainer's [GitHub profile](https://github.com/Prekzursil).
