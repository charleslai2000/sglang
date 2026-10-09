# OPS-20260909-DEPLOY-CAPACITY-SEMANTICS

Status: blocked
Task ID: OPS-20260909-DEPLOY-CAPACITY-SEMANTICS
Epoch: 20260909-P4
Target: root@i-1.gpushare.com:27460 (RTX 3060, CUDA 12 / SM86)

## Summary

Reviewed commit `1e6a82194e` was copied to the authorized remote scheduler path and the
existing service was restarted. Startup failed because the reviewed scheduler imports
`short_tail_recompute_allowed`, which is absent from the unchanged remote
`scheduler_components/hicache_restore.py`. No file outside the authorized scheduler was
changed. The scheduler was restored from the timestamped backup and the existing service
was restarted successfully.

## Commands and evidence

- Preflight: PID `76671` owned `127.0.0.1:30000`; live launch matched the supplied Qwen3.5-4B
  AWQ / fp8_e4m3 / 0.82 / 65536 / max-running-1 / HiCache ratio 2.0 / file / wait_complete /
  retry 1/120 / restore timeout 180 profile.
- Reviewed local scheduler SHA256:
  `efe922c97be391bb223c8c6dd371589d99e310b6e857b0ea4e15c3fae92e1abe`.
- Remote pre-deploy scheduler SHA256:
  `1f741569d2015dbc8285dc81d4bad5e2c9f6c18a9165700d77fa1d25dc8bbe85`.
- Backup created:
  `/root/sglang-3060-12g-hicache/python/sglang/srt/managers/scheduler.py.bak-20260909-080238`
  with SHA256 `1f741569d2015dbc8285dc81d4bad5e2c9f6c18a9165700d77fa1d25dc8bbe85`.
- Failed reviewed-commit startup log:
  `/root/sglang-3060-12g-hicache-live-20260909.log`
  ending in `ImportError: cannot import name 'short_tail_recompute_allowed'`.
- Rollback scheduler SHA256:
  `1f741569d2015dbc8285dc81d4bad5e2c9f6c18a9165700d77fa1d25dc8bbe85`.
- Unified radix cache remained unchanged throughout:
  `395e55efc4d472547581d2a33d7b989933fb78990cf4a455d8daa0e02845a203`.
- Storage path remained present and was not deleted or cleared:
  `/hy-tmp/hicache-qwen35-4b-p4-retry-20260909` (22G before and after).
- Restored service PID: `81303`; port: `127.0.0.1:30000`.
- Final readiness: `GET http://127.0.0.1:30000/health` returned `HTTP=200`.
- Provenance evidence: process environment included
  `PATH=/root/sglang-env-3060-4b/bin:...` and
  `PYTHONPATH=/hy-tmp/ops-081-sm86-import-20260909:/root/sglang-3060-12g-hicache/python`;
  `nvidia-smi` reported `NVIDIA GeForce RTX 3060`, driver `550.144.03`.

## Changed resources

Only remote `scheduler.py` was temporarily replaced, backed up, and restored. No 3090
resource was accessed or altered. No CUDA installation or storage deletion was performed.

## Followups / open issues

The reviewed commit requires its matching `hicache_restore.py` dependency (or a separately
authorized compatible deployment bundle). Resolving that dependency is outside this Task ID
because the authorization permits replacing only scheduler.py. A fresh Task ID and revised
authorization are required before any additional remote source change.
