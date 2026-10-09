# G3-IQ3-LOCAL-ENV-RETRY-SHARED-007-20260909

status: blocked
invocation: INV-G3-IQ3-LOCAL-ENV-REBUILD-007
epoch: E29

## Summary

Using `sg dev -c`, shared `PIP_CACHE_DIR`, and the authorized PyTorch/NVIDIA
indexes, download reached `nvidia-nccl-cu13` but failed the unchanged required
hash: expected `edd815...e136d`, got `255215...f3da2`. Pip left no wheelhouse
files. No hash bypass, alternate package, installation, or other action was taken.

## Evidence

Raw command output: [download log](raw/g3-iq3-env-retry-shared-007-20260909/env-rebuild-download-007-20260909.log).
Wheelhouse: 0 files; venv: 16M; shared cache: 7.8G. Explicit Python 3.12.3,
CMake 4.4.3, and CUDA 13.0.48 were used/verified. No GPU, service, benchmark,
lock, or source changes.

## Followups

Requires fresh authorization to resolve the hash mismatch (e.g. corrected
artifact/index); do not bypass `--require-hashes`.

## Open issues

- Required NCCL artifact does not match the locked hash; environment setup incomplete.
