# OPS-20260909-RESTART-SEEDED-HOST-ALLOC

ENTRY: ACCEPT

status: done
task_id: OPS-20260909-RESTART-SEEDED-HOST-ALLOC
orchestration_epoch: 20260909-P4
role: devops-executor

## Result

Restarted the deployed 3060 service on `root@i-1.gpushare.com:27460` with the
prescribed SM86/CUDA12 launch profile and explicit
`SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`.
No product or storage files were copied, modified, deleted, cleared, or moved.

## Commands and evidence

- Pre-restart PID `87794` was alive on `127.0.0.1:30000`.
- Pre-restart target storage: `23051071488` bytes, `550080` files.
- Sent `SIGTERM` to PID `87794`, waited for exit, and launched the same reviewed
  command/profile with the explicit storage-dir environment variable.
- New launch log: `/tmp/sglang3060-seeded-restart-20260909.log` (old log preserved).
- Final PID `90793`, state `Sl`, listening on `127.0.0.1:30000`.
- Final process environment proves:
  `SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`.
- Startup log proves `Creating storage backend 'file' (...HiCacheFile)` and
  application startup completion.
- Health evidence: three consecutive `GET /health` responses were `HTTP=200`.
- Post-restart target storage: `23051071488` bytes, `550080` files; unchanged.
- Deployed commit remains `82ab235606233160701b15f657a71794cfd29a30` per the
  preserved deployment record; all seven remote hashes below match that record.

## SHA-256 evidence

```text
9efd9159fa3491a3758d13dc2f751c4d9cf2e9fe726ca30238684b0014ddb7b6  python/sglang/srt/managers/schedule_batch.py
ffda8d1b247195650924a059b3a0fdb1d38d670547810043021136d95559a249  python/sglang/srt/managers/scheduler.py
6300bb521fd684d28cd9ec94627b4f51b31ad582bc0ed4e04024b821b1012dd1  python/sglang/srt/managers/scheduler_components/hicache_restore.py
afa00fcc921ab78a46aa96fec5a1f3232eaaab3eaea9eec7bab53795b6a407d7  python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py
bac2bd08b91897e608a9cd1df215c4b278d03d3227587eac38654d441a185633  python/sglang/srt/mem_cache/hybrid_cache/hybrid_pool_assembler.py
beace6d3c6a92dcfb424794267e9cb33a346cea04b2918bf9588d438fb78f20f  python/sglang/srt/mem_cache/pool_host/group.py
46621e8a09df9bafdc9dd3aab83f19f9d7cb36831ef8a6d25758b86e67de2e1b  python/sglang/srt/mem_cache/unified_radix_cache.py
```

## Changed resources

- Service process replaced: PID `87794` -> PID `90793`.
- New launch log created at `/tmp/sglang3060-seeded-restart-20260909.log`.
- No product files, storage directories, 3090 service, packages, or old log were modified.

## Followups

None.

## Open issues

None. The first launch attempt exited before serving due to shell JSON quoting;
the same authorized command was relaunched with corrected quoting and verified.

Extra work requires a fresh Task ID.
