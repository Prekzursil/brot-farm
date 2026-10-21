#!/usr/bin/env bash
# Pre-flight: reproduces every QZP lean-gate lane locally before a push.
# Reads the biome pin from the platform workflow at runtime so it can never
# drift from what CI actually runs.
set -euo pipefail
cd "$(dirname "$0")/.."

PIN=$(gh api repos/Prekzursil/quality-zero-platform/contents/.github/workflows/reusable-quality.yml \
  -q .content | base64 -d | grep -oE 'biome@[0-9.]+' | head -1 | cut -d@ -f2)
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
echo "PREFLIGHT OK"
