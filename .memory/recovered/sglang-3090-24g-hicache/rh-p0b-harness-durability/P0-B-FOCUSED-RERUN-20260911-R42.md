# P0-B focused rerun R42

- Task ID: `P0-B-FOCUSED-RERUN-20260911-R42`
- Invocation: `ses-p0b-focused-r42-20260911`
- Epoch: `2026-09-11`
- Status: execution completed; results classified only (no P0-B pass/live-chain claim).
- Target: `root@i-1.gpushare.com:27460`, RTX 3060, SSH key `/home/dev-codex/.ssh/sglang_3060_ed25519`
- Checkout: `/root/sglang-3060-12g-hicache`
- Python: `/root/sglang-env-3060-4b/bin/python`
- Backup directory: `/root/p0b-focused-r42-backup-20260911` (outside checkout)

## Environment evidence

Command: `/root/sglang-env-3060-4b/bin/python -c "import orjson,msgspec,torch,pytest; ..."`

Output: `orjson=3.12.0 msgspec=0.21.1 torch=2.6.0+cu124 pytest=9.1.1`.
Pytest platform reported Python `3.11.11`, pytest `9.1.1`.

## Transfer and hash evidence

Exact local source files under `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

```text
de0f519ec565e33ba3ab0b901f716a3574ef66c7026d6ed5a48a2c0c2da2dca2  test/registered/unit/managers/test_hicache_host_allocability.py
36d1784aaa4672d711bf1c0be10b725e3d258a55bd164177fadb8ba0ec508ecd  3090-dev/test_drain_reentry.py
431389cd5503be3062c75552e10b5e8c3b322b31eb8ae4665eecfc024e95c47c  3090-dev/test_storage_regression.py
c46abd775e2f115172c94ace9d1fc5e6bcc59921a27e4164a18ae430fc3ce607  3090-dev/test_hicache_restore_scheduler_feed.py
323af06dec1812206d6923446348a76de5795e73fc878681f6ddf8376b1b7568  3090-dev/test_hicache_restore.py
6acc94fa1b99174d7d58e948c7df6eb9dc7a9184fdc428ebcd  3090-dev/test_ready_horizon_partition.py
```

The first five hashes above were verified against remote checkout and all six were verified against their separate remote backup copies; the transfer comparison returned no diff. (The ready-horizon source hash is `6acc94fa1b99174dcd954520a4f1217d58e948c7df6eb9dc7a9184fdc428ebcd`.)

## Exact suite commands and classification

All six commands executed in order regardless of failures, using `python -m pytest` and explicit paths/selections:

1. `.../python -m pytest test/registered/unit/managers/test_hicache_host_allocability.py` — collected 9; **6 passed, 3 failed**, exit 1. Failures: `test_auxiliary_blocked_hybrid_requires_auxiliary_generation`, `test_no_change_no_spin_and_failed_retry_rotates_fifo`, `test_unlock_to_evict_and_actual_free_are_generation_opportunities`.
2. `.../python -m pytest 3090-dev/test_drain_reentry.py` — collected 31; **25 passed, 6 failed**, exit 1. All six failures raised `AttributeError: UnifiedRadixCache has no attribute _t38c_node_context_index` through `_t38c_trace_context_for_node`.
3. `.../python -m pytest 3090-dev/test_storage_regression.py` — collected 126; **126 passed**, exit 0; 7 warnings.
4. `.../python -m pytest 3090-dev/test_hicache_restore_scheduler_feed.py` — collected 46; **46 passed**, exit 0; 2 warnings.
5. `.../python -m pytest 3090-dev/test_hicache_restore.py -k "host_alloc or alloc_failed or wait_capacity or restore"` — collected 92; **92 passed**, exit 0. Non-empty selector confirmed by collection/execution.
6. `.../python -m pytest 3090-dev/test_ready_horizon_partition.py` — collected 18; **18 passed**, exit 0; 2 warnings.

Warnings included the known pytest `asyncio_mode` unknown-config warning, CUDA deprecations, and storage regression unraisable `BaseEvictionResult` warnings; no product edits or dependency installation occurred.

## Follow-ups / open issues

- Preserve the exact observed failures for classification; do not infer a P0-B pass or live-chain status.
- No rollback was needed after test execution; remote backups remain at the path above.
- Complete stdout/stderr was emitted by the six-command execution in the invocation transcript; the remote run transcript staging path was `/tmp/p0b-focused-r42-transcript.txt`.
