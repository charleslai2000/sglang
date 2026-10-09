#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1
python3 -m unittest -v test_reducer.py
python3 - "$ROOT" <<'PY'
import ast
from pathlib import Path
import sys

for name in ("p0b_driver.py", "p0b_reducer.py", "test_reducer.py"):
    ast.parse((Path(sys.argv[1]) / name).read_text(encoding="utf-8"), filename=name)
print("syntax AST: PASS")
PY
sha256sum -c manifest.sha256
python3 - "$ROOT" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
artifacts = [path for path in root.rglob("*") if path.suffix == ".pyc" or path.name == "__pycache__"]
if artifacts:
    raise SystemExit("bytecode artifact present: " + ", ".join(str(path) for path in artifacts))
print("no-bytecode readback: PASS")
PY
printf 'R94 self-tests: PASS\n'
