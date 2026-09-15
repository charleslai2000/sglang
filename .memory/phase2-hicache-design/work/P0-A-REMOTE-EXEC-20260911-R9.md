# P0-A Remote Regression Execution R9

- Task ID: `P0-A-REMOTE-EXEC-20260911-R9`
- Invocation: `ses-p0a-exec-r9-20260911`
- Epoch: `2026-09-11`
- Status: done
- Acceptance: execution completed; P0-A VERIFIED DONE **not** claimed because command 2 and command 4 failed.

## Authorization and scope

Executed only on authorized RTX 3060 target `root@i-1.gpushare.com:27460`,
checkout `/root/sglang-3060-12g-hicache`, using key
`/home/dev-codex/.ssh/sglang_3060_ed25519` and Python
`/root/sglang-env-3060-4b/bin/python`. No product edits, 3090/production,
server/P1/P0-B work, or local git modifications were performed. No rollback was
needed or authorized.

## Hash gate

Immediately before pytest, the remote target was verified as hostname
`I2aff9805ac001019d1`, checkout directory existed, and these remote SHA256
hashes matched the supplied expected hashes:

```text
696ef7b89d8bec8f58c9c2751e24ca67b0540ac94571114ed953eacf7fc7ecfa  3090-dev/test_ready_horizon_unit.py
a5e1aa2367e68f472cf892ea3752c253269fcb67350340a6e0d26d2d31094bd7  3090-dev/test_prefetch_budget_split_unit.py
c46abd775e2f115172c94ace9d1fc5e6bcc59921a27e4164a18ae430fc3ce607  3090-dev/test_hicache_restore_scheduler_feed.py
```

The local workspace files were not modified; their hashes were separately
printed and differ from the supplied expected values because this invocation
used the R8 expected-hash baseline, not local source transfer.

## Commands and results

Every command was prefixed exactly with:
`PYTHONPATH=/root/sglang-3060-12g-hicache/python:/root/sglang-3060-12g-hicache/test /root/sglang-env-3060-4b/bin/python -m pytest -q`

1. Selected `test_ready_horizon_unit.py`: **13 passed, 61 deselected**, exit 0.
2. Selected `test_prefetch_budget_split_unit.py`: **6 passed, 3 failed, 15 deselected**, exit 1.
   Failures: `test_abort_path_releases_speculative_reservation`,
   `test_detach_path_releases_speculative_reservation`,
   `test_revoke_path_releases_speculative_reservation`.
3. Full `test_ready_horizon_unit.py`: **74 passed**, exit 0.
4. Full `test_prefetch_budget_split_unit.py`: **12 passed, 12 failed**, exit 1.
   Failure IDs are preserved verbatim in the transcript artifact.
5. Full `test_hicache_restore_scheduler_feed.py`: **46 passed**, exit 0.
6. `test_ready_horizon_partition.py`: **18 passed**, exit 0.
7. `test_prefetch_gate_skip_regression.py`: **2 passed**, exit 0.
8. `test_rh_contract_dependency_free.py`: **19 passed**, exit 0.

Warnings were CUDA deprecation warnings in commands 1, 3, 5, and 6; no warning
changed an exit code.

## Artifacts and evidence

- Complete combined stdout/stderr transcript, exact command headings, exit
  codes, summaries, and failure traces:
  `.memory/phase2-hicache-design/work/P0-A-REMOTE-EXEC-20260911-R9.transcript`
- This report:
  `.memory/phase2-hicache-design/work/P0-A-REMOTE-EXEC-20260911-R9.md`

## Summary

The authorized procedure executed after a successful immediate hash gate. Six
of eight commands passed and two failed. Therefore the invocation is `done`,
but P0-A VERIFIED DONE is not established.

## Followups

Investigate the reported remote test failures in a separately authorized
invocation. Preserve the existing R8 remote backup; no rollback was performed.

## Open issues

- Command 2 failed 3 selected tests with `AttributeError:
  UnifiedRadixCache._t38c_request_contexts`.
- Command 4 failed 12 tests, including the same missing
  `_t38c_request_contexts` and missing `_t38c_residency_lock` attributes.
