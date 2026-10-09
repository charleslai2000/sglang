# OPS-20260909-DEPLOY-CAPACITY-BUNDLE

Status: done
Task ID: OPS-20260909-DEPLOY-CAPACITY-BUNDLE
Orchestration epoch: 20260909-P4
Role: devops-executor
Target: root@i-1.gpushare.com:27460 (RTX 3060, CUDA 12 / SM86)

## Summary

Deployed the complete reviewed capacity-semantics bundle from commit
`1e6a82194e7f5d071823e4abb68514c6d421e4b3` on branch `3060-12g-qwen35-4b`,
including the matching `hicache_restore.py` dependency. The preserved Qwen3.5-4B
AWQ / FP8 E4M3 / SM86-CUDA12 launch profile was restarted successfully.

## Changed resources

Only these three authorized remote product files were replaced:

| Remote file | Reviewed SHA-256 | Timestamped backup | Backup SHA-256 |
|---|---|---|---|
| `/root/sglang-3060-12g-hicache/python/sglang/srt/managers/scheduler.py` | `efe922c97be391bb223c8c6dd371589d99e310b6e857b0ea4e15c3fae92e1abe` | `scheduler.py.bak-20260909-capacity-20260909-081116` | `1f741569d2015dbc8285dc81d4bad5e2c9f6c18a9165700d77fa1d25dc8bbe85` |
| `/root/sglang-3060-12g-hicache/python/sglang/srt/managers/scheduler_components/hicache_restore.py` | `ec7954d18cee43dc39f7cf0263fff367aa93a03ccc38cf1fe80995c644b8875e` | `hicache_restore.py.bak-20260909-capacity-20260909-081116` | `6241f5689fd9940cb8369ce6c6a31c1c85bdc712e92ab4aea2d1c485f9d8ac05` |
| `/root/sglang-3060-12g-hicache/python/sglang/srt/mem_cache/unified_radix_cache.py` | `3021d3b0591a2e102c3d0f73d32680448080fb882fc9a2ef6722d4bca336cbe8` | `unified_radix_cache.py.bak-20260909-capacity-20260909-081116` | `395e55efc4d472547581d2a33d7b989933fb78990cf4a455d8daa0e02845a203` |

The existing service PID `81303` was stopped and replaced by PID `82493`.
No storage, logs, model files, 3090 resources, or CUDA installation were
modified or deleted.

## Commands and evidence

- Local source commit verified:
  `1e6a82194e7f5d071823e4abb68514c6d421e4b3`.
- Remote staging files were checksummed before replacement and matched the
  reviewed hashes above.
- Service log:
  `/tmp/qwen35-4b-hicache-p4-capacity-bundle-20260909-20260909-081116.log`
- PID file:
  `/tmp/qwen35-4b-hicache-p4-capacity-bundle-20260909-20260909-081116.pid`
  containing `82493`.
- Service command line preserved the requested model, FP8 E4M3, memory 0.82,
  max total tokens 65536, max running 1, TP1, CUDA graph settings, HiCache
  ratio 2.0, write-through/file/wait-complete, retry 1/120, restore timeout
  180, and RH OFF.
- Listener evidence: `127.0.0.1:30000` owned by Python PID `82493`.
- Readiness evidence: three consecutive `GET /health` probes returned HTTP 200.
- Startup log contains `The server is fired up and ready to roll!` and no
  `Traceback`, `ImportError`, CUDA error, out-of-memory, or `ERROR` matches.
- Log SHA-256:
  `011eb80519da61bd259004af9026450eb0f1791f13df1367c95b3b19cbc74a2f`.
- Import verification succeeded for all three modules using:
  `PYTHONPATH=/hy-tmp/ops-081-sm86-import-20260909:/root/sglang-3060-12g-hicache/python`.
  All resolved from `/root/sglang-3060-12g-hicache/python`.
- Live process provenance included:
  `PATH=/root/sglang-env-3060-4b/bin:$PATH` and the authorized SM86 staging
  path first in `PYTHONPATH`.
- Storage verification before and after:
  `/hy-tmp/hicache-qwen35-4b-p4-retry-20260909 83439616 1788909386 755 root:root`
  and `22G`.

## Rollback

Rollback artifacts are the three timestamped backups listed above. Rollback
would require restoring those exact files, stopping PID `82493`, and restarting
the prior profile; it was not executed because acceptance passed.

## Followups

- Keep PID `82493` and the service log as the active 3060 runtime evidence.
- Any request workload, shutdown, or further source change requires a fresh
  Task ID.

## Open issues

None for this authorized deployment and readiness acceptance.

## Invocation handoff

`status`: `done`  
`artifacts`: three timestamped remote backups, deployed files, PID file, service log, this report  
`evidence`: exact reviewed hashes, backup hashes, import provenance, process/listener state, health 200, launch-profile command line, unchanged storage metadata/size  
`summary`: complete reviewed 3060 capacity-semantics bundle deployed and ready  
`followups`: fresh Task ID for any additional operation  
`open_issues`: none
