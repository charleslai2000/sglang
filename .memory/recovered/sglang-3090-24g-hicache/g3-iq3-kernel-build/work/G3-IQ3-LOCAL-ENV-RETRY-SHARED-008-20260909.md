# G3-IQ3-LOCAL-ENV-RETRY-SHARED-008-20260909

status: blocked
invocation: INV-G3-IQ3-LOCAL-ENV-REBUILD-008
epoch: E30

## Summary

Copied the exact cached NCCL body into the task wheelhouse; SHA256 matched the
locked requirement. Hash-locked download with the authorized PyTorch and NVIDIA
indexes then reached the exact Torch wheel but failed on HTTPS read timeout at
198.2/526.5 MB. No install or retry was performed.

## Evidence

Raw log: [download log](raw/g3-iq3-env-retry-shared-008-20260909/env-rebuild-download-008-20260909.log).
NCCL wheel hash verified as `edd81538446786ec3b73972543e53bb43bcaf0bfc8ef76cb679fcc390ffe136d`.
Wheelhouse contains only that 205,976,000-byte wheel (197M total); venv 16M;
shared cache 7.8G. No source, service, benchmark, GPU, or lock changes.

## Followups

Requires fresh dispatch after Torch download/network state is available.

## Open issues

- Exact Torch wheel download timed out; full wheelhouse and venv/editable install incomplete.
