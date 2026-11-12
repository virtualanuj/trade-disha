#!/usr/bin/env bash
# Runs every quality gate. A milestone is not done while this is red.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== backend: ruff check"
(cd backend && uv run ruff check .)
echo "== backend: ruff format --check"
(cd backend && uv run ruff format --check .)
echo "== backend: mypy"
(cd backend && uv run mypy)
echo "== backend: pytest"
(cd backend && uv run pytest -q)

echo "== frontend: typecheck + lint + format + test"
(cd frontend && npm run check --silent)

echo
echo "All checks passed."
