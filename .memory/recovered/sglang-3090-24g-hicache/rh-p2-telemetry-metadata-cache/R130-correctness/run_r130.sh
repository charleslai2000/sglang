#!/usr/bin/env bash
# R130 correctness gate runner. Offline: no GPU, no server.
#   source activate -> py_compile -> stdlib unittest -> microbenchmark.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_ACTIVATE="/mnt/data/neuron/envs/sglang-3090-opt/activate-sglang-3090.sh"
# shellcheck disable=SC1090
source "$ENV_ACTIVATE"

cd "$HERE"
rc=0

echo "=== R130 py_compile ===" | tee _r130_compile.log
python -m py_compile test_r130_metadata_cache_correctness.py r130_microbench.py \
    2>&1 | tee -a _r130_compile.log
compile_rc=${PIPESTATUS[0]}
echo "py_compile_exit=$compile_rc" | tee -a _r130_compile.log
[ "$compile_rc" -eq 0 ] || rc=1

echo "=== R130 unittest ===" 
python -B -m unittest -v test_r130_metadata_cache_correctness \
    2>&1 | tee _r130_unittest.log
test_rc=${PIPESTATUS[0]}
echo "unittest_exit=$test_rc"
[ "$test_rc" -eq 0 ] || rc=1

echo "=== R130 microbenchmark ==="
python -B r130_microbench.py 2>&1 | tee _r130_microbench.log
bench_rc=${PIPESTATUS[0]}
echo "microbench_exit=$bench_rc"
[ "$bench_rc" -eq 0 ] || rc=1

echo "=== R130 overall exit=$rc ==="
exit "$rc"
