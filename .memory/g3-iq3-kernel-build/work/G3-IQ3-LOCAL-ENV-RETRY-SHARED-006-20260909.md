# G3-IQ3-LOCAL-ENV-RETRY-SHARED-006-20260909

status: blocked
invocation: INV-G3-IQ3-LOCAL-ENV-REBUILD-006
epoch: E28

## Summary

Ran the unchanged hash-locked download under `sg dev -c` with the shared pip cache. Cache writability succeeded and no pip cache warning appeared. Cached dependencies were reused, but the configured index has no matching `torch==2.13.0+cu130`; pip stopped with resolution failure. No alternate package, hash bypass, retry, installation, or further action was taken.

## Evidence

Command and output are preserved in [raw download log](raw/g3-iq3-env-retry-shared-006-20260909/env-rebuild-download-006-20260909.log). Failure: `No matching distribution found for torch==2.13.0+cu130`.

Wheelhouse has 0 files; venv is 16M and unpopulated. `sg dev -c 'test -w /mnt/data/cache/pip'` returned 0. Cache usage is 7.8G. Python 3.12.3, CMake 4.4.3, and CUDA 13.0.48 were verified.

## Followups

Requires fresh authorized dispatch with an index/source providing the exact hash-locked torch wheel; no alternative package is permitted.

## Open issues

- Exact torch wheel unavailable from current index; wheelhouse and venv setup incomplete.
