# P0-A final regression rerun R23

- status: done
- task_id: P0-A-FINAL-RERUN-20260911-R23
- invocation: ses-p0a-final-r23-20260911
- epoch: 2026-09-11
- target: authorized 3060 only, `root@i-1.gpushare.com:27460`
- checkout: `/root/sglang-3060-12g-hicache`
- Python: `/root/sglang-env-3060-4b/bin/python`
- P0-A overall: **VERIFIED DONE** (8/8 commands passed)

## Scope and transfer evidence

Only these exact local files were used:

```text
/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py
/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_prefetch_budget_split_unit.py
/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_hicache_restore_scheduler_feed.py
```

Local SHA-256; remote hashes after absolute-destination `scp` matched exactly:

```text
696ef7b89d8bec8f58c9c2751e24ca67b0540ac94571114ed953eacf7fc7ecfa  test_ready_horizon_unit.py
0f64c30c4f3db7e37cde46a6ccc5ed13af1e241c7bc4b9c2e815d8ec09bb1a0d  test_prefetch_budget_split_unit.py
c46abd775e2f115172c94ace9d1fc5e6bcc59921a27e4164a18ae430fc3ce607  test_hicache_restore_scheduler_feed.py
```

Remote backups were created exactly at each destination as `.P0-A-FINAL-RERUN-20260911-R23.bak`; each backup hash matched its pre-transfer destination hash.

Symbol gates passed locally before transfer: ready `origin`, `PrefetchIssueResult`, `host_release`; budget `_t38c_node_context_index`, `_t38c_request_contexts`, `_t38c_residency_lock`, `_t38c_residency_queue_blocked`, `speculative_release_epoch`, `trace_context`; restore `origin`, `pop_host_alloc_failure`.

## Commands and results

All commands used the required prefix:

```text
PYTHONPATH=/root/sglang-3060-12g-hicache/python:/root/sglang-3060-12g-hicache/test /root/sglang-env-3060-4b/bin/python -m pytest -q
```

1. Ready focused selector: **PASS**, exit 0 — 13 passed, 61 deselected.
2. Budget focused selector: **PASS**, exit 0 — 9 passed, 15 deselected.
3. Full `test_ready_horizon_unit.py`: **PASS**, exit 0 — 74 passed.
4. Full `test_prefetch_budget_split_unit.py`: **PASS**, exit 0 — 24 passed.
5. Full `test_hicache_restore_scheduler_feed.py`: **PASS**, exit 0 — 46 passed.
6. `test_ready_horizon_partition.py`: **PASS**, exit 0 — 18 passed.
7. `test_prefetch_gate_skip_regression.py`: **PASS**, exit 0 — 2 passed.
8. `test_rh_contract_dependency_free.py`: **PASS**, exit 0 — 19 passed.

All eight commands were run regardless of failures. No failure IDs. Warnings were CUDA deprecation warnings only.

## Artifacts and evidence

- Complete captured stdout/stderr transcript: `/tmp/P0-A-FINAL-RERUN-20260911-R23.transcript`.
- Transcript SHA-256: `af58ef5c936ad19d8e120c1314eeb719a698a3fee2ee15ef2a70b5e26797bf40`.
- Remote backup artifacts: the three destination `.P0-A-FINAL-RERUN-20260911-R23.bak` files under `/root/sglang-3060-12g-hicache/3090-dev/`.

## Summary, followups, open issues

Execution completed successfully. The approved fixture correction is verified by the passing full budget suite. No product edits, local git changes, 3090/production access, or additional targets were performed.

- Followups: none.
- Open issues: none.
