#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_reducer.py
python3 -m py_compile p0b_driver.py p0b_reducer.py test_reducer.py
rm -rf __pycache__
sha256sum -c manifest.sha256
printf 'R97 self-tests: PASS\n'
