ENTRY: ACCEPT

status: done
task_id: OPS3060-DEPLOY-RH-FINAL-20260909
orchestration_epoch: 20260909-rh-ab34
role: devops-executor

## Summary

Deployed reviewed commit `6edf69ce29fe2598fba51c94a99315239cf1a8c8` runtime
Python files to `root@i-1.gpushare.com:27460` at
`/root/sglang-3060-12g-hicache`. The prior listener PID `102147` was stopped
with SIGTERM after staging. The final RH-OFF service is PID `107356`, bound to
`127.0.0.1:30000` and healthy.

## Commands and evidence

- Read and accepted final reviewer gate
  `review/gates/REVIEW-20260909-RH-PREADMISSION.md`: `final_verdict: ACCEPT`,
  revision `6edf69ce29fe2598fba51c94a99315239cf1a8c8`.
- Confirmed target host, source directory, listener PID, and seed storage
  baseline before deployment.
- Created remote staging directory `/tmp/ops3060-deploy-rh-final-20260909`.
- Streamed only the seven authorized runtime files from the reviewed commit
  using `git archive`; source and staged remote SHA-256 values matched.
- Preserved rollback copies at
  `/tmp/ops3060-deploy-rh-final-20260909-backup`; installed each staged file
  with preserved metadata via temporary sibling followed by atomic `mv`.
- Launch log: `/tmp/sglang3060-rh-final-20260909.log`.
- Final process command contains model `/hy-tmp/models/Qwen3.5-4B-AWQ`, FP8
  KV, CUDA graphs, HiCache ratio `2.0`, `--max-running-requests 1`, and
  `--random-seed 586963985`; no ready-horizon flags are present.
- Final environment contains `SGLANG_SEED=586963985`,
  `PYTHONHASHSEED=586963985`, `CUDA_VISIBLE_DEVICES=0`, and PATH beginning
  `/root/sglang-env-3060-4b/bin`.
- Three consecutive `/health` probes returned HTTP 200.
- Runtime reports `enable_ready_horizon': False`; fatal scan returned `NONE`.
- Kernel verification: `NVIDIA GeForce RTX 3060`, CUDA `12.4`, and
  `sgl_kernel` imported from `/root/sglang-env-3060-4b/.../site-packages`.
- Seed storage before/after: `83439616` bytes and `550080` files, unchanged.

## SHA-256 evidence

| Runtime file | Source and final remote SHA-256 |
|---|---|
| `python/sglang/srt/managers/schedule_batch.py` | `dc94b91af41786f5704901435ae4b846344717fb9399b2b16b898e6684fd30f8` |
| `python/sglang/srt/managers/scheduler.py` | `c9e4dd7795c5df6dd9b1ed07f67dbd51ff65d301e1d60a15fad3d99259089a03` |
| `python/sglang/srt/managers/scheduler_components/hicache_restore.py` | `92f4404de4935be47bddf4df3d24388a39fe3fb53b44371defa67f7564f8a5b2` |
| `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py` | `afa00fcc921ab78a46aa96fec5a1f3232eaaab3eaea9eec7bab53795b6a407d7` |
| `python/sglang/srt/mem_cache/hybrid_cache/hybrid_pool_assembler.py` | `bac2bd08b91897e608a9cd1df215c4b278d03d3227587eac38654d441a185633` |
| `python/sglang/srt/mem_cache/pool_host/group.py` | `beace6d3c6a92dcfb424794267e9cb33a346cea04b2918bf9588d438fb78f20f` |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | `482ee59f938110a8bee228beede55d8d4aa8dffabbf706110345b8ff463d966f` |

## Changed resources

- Seven authorized remote runtime files replaced.
- Seven rollback copies preserved under the timestamped `/tmp` backup path.
- One final launch log created under `/tmp`.
- Only the current SGLang listener was stopped; unrelated processes were not
  killed. The specified seed/storage directory was not altered.

## Followups

None. Runtime experiments beyond startup health require a fresh Task ID.

## Open issues

None.
