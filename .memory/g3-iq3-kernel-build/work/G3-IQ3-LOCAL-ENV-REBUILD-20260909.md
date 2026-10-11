# G3 IQ3 local environment rebuild — 2026-09-09

ENTRY: ACCEPT

## Status

blocked. The dedicated Python 3.12.3 venv was recreated, but the hash-locked
wheelhouse download failed on a network read timeout before pip committed any
wheels. Consequently torch and editable sglang installation/import verification
could not be performed. No service, benchmark, GPU kernel, or GPU lock was used.

## Authorized scope and baseline

Only `/mnt/data/qwen3-g3-baseline/{venv,wheels,build,artifacts}` and the current
checkout were touched. Existing checkout modifications were preserved. The
requirements source remained unchanged:
`/mnt/data/qwen3-g3-baseline/artifacts/torch-cu130-wheelhouse-requirements.txt`.

Explicit toolchain evidence:

```
/usr/bin/python3 --version       Python 3.12.3
/usr/local/bin/cmake --version   cmake version 4.4.3
/usr/local/cuda/bin/nvcc         Build cuda_13.0.r13.0/compiler.36260728_0
```

## Commands and evidence

1. `mkdir -p /mnt/data/qwen3-g3-baseline/{venv,wheels,build,artifacts}`
2. `/usr/bin/python3 -m venv --clear /mnt/data/qwen3-g3-baseline/venv`
3. `venv/bin/python -m pip --version` → pip 24.0
4. Hash-preserving command:

```
venv/bin/python -m pip download --only-binary=:all: --require-hashes \
  -r artifacts/torch-cu130-wheelhouse-requirements.txt -d wheels
```

Downloads progressed through `nvidia-nvshmem-cu13`, then failed while reading
the 60.4 MB wheel with `HTTPSConnectionPool(host='files.pythonhosted.org', port=443): Read timed out.`
The failed command did not bypass hashes. A duplicate invocation was observed
(both initiated by this invocation); the first identified PID 609348 was stopped
after confirmation, leaving no download process running.

5. Offline install verification command:

```
venv/bin/python -m pip install --no-index --find-links wheels --require-hashes \
  -r artifacts/torch-cu130-wheelhouse-requirements.txt
```

→ failed immediately: no matching distribution for MarkupSafe==3.0.2.

## Changed resources / disk evidence

`venv` exists (16M; freshly recreated), `wheels` is empty aside from directory
metadata (8.0K), `build` 8.0K, and existing `artifacts` 444K. No wheel hashes
can be recorded because no wheel completed. No product source was edited.

## Followups and open issues

Retry the same exact hash-locked download when network access is reliable, then
install from the wheelhouse, install editable sglang, and verify `import torch`
and `import sglang`. Preserve this timeout output as the reason for the block;
do not use unhashed or alternate packages.

