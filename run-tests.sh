#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python -m harness.validate_openapi openapi.yaml --strict

for pass in 1 2; do
  echo
  echo "=== HARNESS TEST PASS ${pass}/2 ==="
  pytest -q
 done

echo
echo "PASS: OpenAPI + SQLite harness suite passed twice from disposable databases."
