#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
python3 -m unittest -v test_reducer.py
python3 -m py_compile p0b_driver.py p0b_reducer.py test_reducer.py
sha256sum -c manifest.sha256
printf 'R89 self-tests: PASS\n'
