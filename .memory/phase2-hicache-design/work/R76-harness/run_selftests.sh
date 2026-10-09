#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_reducer.py
python3 -m py_compile p0b_driver.py p0b_reducer.py test_reducer.py
printf '%s\n' 'R76 harness self-tests: PASS'
