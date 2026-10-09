# OPS-20260909-DEPLOY-HOST-ALLOC-FINAL

ENTRY: ACCEPT

status: done
task_id: OPS-20260909-DEPLOY-HOST-ALLOC-FINAL
orchestration_epoch: 20260909-P4
role: devops-executor

## Result

Reviewed commit `82ab235606233160701b15f657a71794cfd29a30` was deployed to
`root@i-1.gpushare.com:27460` in `/root/sglang-3060-12g-hicache`. Only the seven
authorized product files were replaced. No tests were copied, and no 3090, model,
storage, or existing logs were modified.

## Commands and evidence

- Baseline: PID `82493` was alive and listening on `127.0.0.1:30000`; storage was
  `23051071488` bytes and `550080` files.
- Backup directory:
  `/hy-tmp/ops-081-sm86-import-20260909/deploy-backup-20260909-110232`
- Transfer: `git archive --format=tar 82ab235606 <seven paths> | ssh ... tar -xf -`
- Source imports, with the required PATH/PYTHONPATH, returned `IMPORTS_OK` for all
  seven modules.
- Service restarted with the preserved Qwen3.5-4B-AWQ / fp8_e4m3 / mem 0.82 /
  max-total 65536 / max-running 1 / tp1 / CUDA graph / HiCache ratio 2.0,
  write_through, file, wait_complete, retry 1/120, restore timeout 180, RH off
  profile.
- Final PID: `87794`, alive (`Sl`), listening on `127.0.0.1:30000`.
- Health evidence: readiness probe `HTTP=200`, followed by three consecutive
  `GET /health` responses: `HTTP=200`, `HTTP=200`, `HTTP=200`.
- Final storage: `23051071488` bytes and `550080` files; unchanged from baseline.
- Launch log: `/tmp/sglang3060-host-alloc-final-20260909.log`.

## SHA-256 evidence

| Product file | Reviewed/local and final remote SHA-256 | Backup SHA-256 |
|---|---|---|
| `python/sglang/srt/managers/schedule_batch.py` | `9efd9159fa3491a3758d13dc2f751c4d9cf2e9fe726ca30238684b0014ddb7b6` | `cb60b756e4d1fb197f0355a85eb3e5b2b36c40fcabaf2f6828cb38ab196f2301` |
| `python/sglang/srt/managers/scheduler.py` | `ffda8d1b247195650924a059b3a0fdb1d38d670547810043021136d95559a249` | `efe922c97be391bb223c8c6dd371589d99e310b6e857b0ea4e15c3fae92e1abe` |
| `python/sglang/srt/managers/scheduler_components/hicache_restore.py` | `6300bb521fd684d28cd9ec94627b4f51b31ad582bc0ed4e04024b821b1012dd1` | `ec7954d18cee43dc39f7cf0263fff367aa93a03ccc38cf1fe80995c644b8875e` |
| `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py` | `afa00fcc921ab78a46aa96fec5a1f3232eaaab3eaea9eec7bab53795b6a407d7` | `5bc3ac23e3a1f375f116744ac0c8bf91f07410526ea01e49147bb4838479c501` |
| `python/sglang/srt/mem_cache/hybrid_cache/hybrid_pool_assembler.py` | `bac2bd08b91897e608a9cd1df215c4b278d03d3227587eac38654d441a185633` | `7c8a29f2c08c6daa31ef04983421fd4c073e0ea9d2159adf6e2da1609da97a95` |
| `python/sglang/srt/mem_cache/pool_host/group.py` | `beace6d3c6a92dcfb424794267e9cb33a346cea04b2918bf9588d438fb78f20f` | `2d191a40f7d6808d88d0ff31c51af7c5b0663c9bf09974c8245c1db8204ba8a8` |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | `46621e8a09df9bafdc9dd3aab83f19f9d7cb36831ef8a6d25758b86e67de2e1b` | `3021d3b0591a2e102c3d0f73d32680448080fb882fc9a2ef6722d4bca336cbe8` |

## Changed resources

- Seven authorized remote product files replaced.
- Seven timestamped backups preserved under the backup directory above.
- One new launch log created at `/tmp/sglang3060-host-alloc-final-20260909.log`.
- Service process replaced: old PID `82493` stopped; new PID `87794` healthy.

## Followups

None.

## Open issues

None. An initial launch attempt was rejected by JSON shell quoting and exited
before binding; it was corrected using the same authorized launch profile. The
final log and process state contain the successful corrected launch only.

Extra work requires a fresh Task ID.
