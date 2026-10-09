# G3-IQ3-LOCAL-ENV-RETRY-SHARED-005-20260909

status: blocked
invocation: INV-G3-IQ3-LOCAL-ENV-REBUILD-005
epoch: E27

## Summary

Repeated the authorized hash-locked wheelhouse download once after the reported
cache permission repair. Pip still warned that `/mnt/data/cache/pip` was not
writable and disabled caching. Download then failed with an HTTPS read timeout
while fetching `nvidia-cuda-nvrtc` (44.9/90.2 MB). Per dispatch, stopped without
retrying or installing partial packages.

## Evidence

Command (unchanged requirements, shared cache only):

```text
export PIP_CACHE_DIR=/mnt/data/cache/pip
/usr/bin/python3 -m pip download --require-hashes -r /mnt/data/qwen3-g3-baseline/artifacts/torch-cu130-wheelhouse-requirements.txt --dest /mnt/data/qwen3-g3-baseline/wheels --retries 2 --timeout 60
```

Raw output: [download log](raw/g3-iq3-env-retry-shared-005-20260909/env-rebuild-download-005-20260909.log).
Observed tools: Python 3.12.3, `/usr/local/bin/cmake` 4.4.3,
`/usr/local/cuda/bin/nvcc` CUDA 13.0.48. Wheelhouse remains empty (8.0K);
venv remains 16M/unpopulated; shared cache is 7.8G and reports
`charles:dev drwxrwsr-x`.

## Followups

Requires fresh dispatch after cache writability and/or network state is corrected.

## Open issues

- Hash-verified wheelhouse and offline venv/editable installation incomplete.
- Pip still cannot write shared cache despite reported repair; no permissions were changed.
