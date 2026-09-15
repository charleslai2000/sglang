# P0-A remote rerun R19

- status: done
- task_id: P0-A-REMOTE-RERUN-20260911-R19
- invocation: ses-p0a-rerun-r19-20260911
- epoch: 2026-09-11
- target: authorized 3060 only, `root@i-1.gpushare.com:27460`
- checkout: `/root/sglang-3060-12g-hicache`
- Python: `/root/sglang-env-3060-4b/bin/python`
- P0-A overall: **NOT VERIFIED** (7/8 commands passed; command 4 failed)

## Scope and file transfer evidence

Exact local source files:

```text
/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py
/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_prefetch_budget_split_unit.py
/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_hicache_restore_scheduler_feed.py
```

Local SHA-256 and matching remote SHA-256 after absolute-destination `scp`:

```text
696ef7b89d8bec8f58c9c2751e24ca67b0540ac94571114ed953eacf7fc7ecfa  test_ready_horizon_unit.py
82b4be92355c48de2e990404c5cd57216a98bfa47f08dad11639d07ba569e1c0  test_prefetch_budget_split_unit.py
c46abd775e2f115172c94ace9d1fc5e6bcc59921a27e4164a18ae430fc3ce607  test_hicache_restore_scheduler_feed.py
```

Per-file symbol gates passed locally and remotely. Ready gate was limited to `origin`, `PrefetchIssueResult`, `host_release`; budget gate to `_t38c_node_context_index`, `_t38c_request_contexts`, `_t38c_residency_lock`, `speculative_release_epoch`, `trace_context`; restore gate to `origin`, `pop_host_alloc_failure`.

Remote backup: `/root/sglang-3060-12g-hicache/.p0a-remote-rerun-20260911-r19-backup/3090-dev/`.

## Command results

All eight commands were run despite failures. Required prefix was used for every command:

```text
PYTHONPATH=/root/sglang-3060-12g-hicache/python:/root/sglang-3060-12g-hicache/test /root/sglang-env-3060-4b/bin/python -m pytest -q
```

1. Ready focused selector: **PASS**, exit 0 — 13 passed, 61 deselected.
2. Budget focused selector: **PASS**, exit 0 — 9 passed, 15 deselected.
3. Full `test_ready_horizon_unit.py`: **PASS**, exit 0 — 74 passed.
4. Full `test_prefetch_budget_split_unit.py`: **FAIL**, exit 1 — 3 failed, 21 passed. Failures:
   - `SpeculativeStagingNoEvictTests.test_demand_alloc_failure_still_evicts`
   - `SpeculativeStagingNoEvictTests.test_speculative_alloc_failure_never_evicts`
   - `ReadyHorizonOffModeTests.test_off_alloc_failure_evicts_like_baseline`
   - observed failure: `AttributeError: 'UnifiedRadixCache' object has no attribute '_t38c_residency_queue_blocked'` in `_t38c_residency_release_queues_drained`.
5. Full `test_hicache_restore_scheduler_feed.py`: **PASS**, exit 0 — 46 passed.
6. `test_ready_horizon_partition.py`: **PASS**, exit 0 — 18 passed.
7. `test_prefetch_gate_skip_regression.py`: **PASS**, exit 0 — 2 passed.
8. `test_rh_contract_dependency_free.py`: **PASS**, exit 0 — 19 passed.

## Transcript

Complete local transcript: `/tmp/p0a-r19-transcript.txt`, 223 lines, SHA-256 `cff7979b0bec844f6d1cbfc28e81b527a9e44cd823f5e634b98adfe3fce5d648`. The attempted remote `/tmp` retrieval was not available after the SSH session; the full captured output is preserved locally and summarized above.

## Followups and open issues

- Followup: investigate/fix the missing `_t38c_residency_queue_blocked` initialization before any rerun; no fix was attempted under this execution scope.
- Open issue: P0-A cannot be marked VERIFIED while command 4 has three failures.
