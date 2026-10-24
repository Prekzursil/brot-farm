#!/usr/bin/env bash
# Pre-flight: reproduces every QZP lean-gate lane locally before a push,
# plus the CI 'research' job (the lab-notebook gate).
# Reads the biome pin from the platform workflow at runtime so it can never
# drift from what CI actually runs.
set -euo pipefail
cd "$(dirname "$0")/.."

PIN=$(curl -fsSL --max-time 15 \
  https://raw.githubusercontent.com/Prekzursil/quality-zero-platform/main/.quality/tool-pins.yml \
  2>/dev/null | sed -n 's/^  biome: "\(.*\)"$/\1/p' | head -1 || true)
# same fallback as the platform's own gate-lint-format-jsts lane: on any
# fetch/parse failure, pin to the last committed version — never garbage
case "$PIN" in ''|*[!0-9.]*) PIN="2.5.15" ;; esac
echo "== gate 1a: ruff =="
ruff check .
ruff format --check .
echo "== gate 2: basedpyright (standard) =="
basedpyright
echo "== gate 1b: oxlint =="
npx --yes oxlint@1.69.0 --deny-warnings --no-error-on-unmatched-pattern docs/assets/*.js
echo "== gate 1c: biome format (pin $PIN, read from QZP at runtime) =="
npx --yes "@biomejs/biome@$PIN" format --write docs/assets biome.json
npx --yes "@biomejs/biome@$PIN" ci --formatter-enabled=true --linter-enabled=false --assist-enabled=false .
echo "== gate 3: pytest --cov (100% line+branch required) =="
python -m pytest --cov -q
echo "== research: lab-notebook gate (CI research job) =="
python scripts/check_research.py
echo "PREFLIGHT OK"
