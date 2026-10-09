# P0-A Budget Rerun R14

- Task ID: `P0-A-BUDGET-RERUN-20260911-R14`
- Invocation: `ses-p0a-budget-rerun-r14-20260911`
- Epoch: `2026-09-11`
- Status: done
- Target: `root@i-1.gpushare.com:27460`
- Checkout: `/root/sglang-3060-12g-hicache`
- Python: `/root/sglang-env-3060-4b/bin/python`

## Scope and authorization

Only the authorized RTX 3060 SSH target was used. No 3090/production target,
product edits, or local git edits were performed.

## Transfer and hash gate

Local source directory used: `3rdparty/sglang-3090-24g-hicache/3090-dev`.
Hashes were computed immediately before transfer:

```text
bd87b5b1165ae2e21d3c652f908af37b18ce3714fb6ff1d30b09221362f83e64  test_ready_horizon_unit.py
59da7cb4d706585e41cd5d9d81849601f8b91bb1f76135f1a635a0ba8eeb6ee0  test_prefetch_budget_split_unit.py
e725e9730ad4a22de8add159bf7e22cc0bf6b0c19614f240329d51b1c44b219d  test_hicache_restore_scheduler_feed.py
```

All three remote hashes matched exactly. A reversible backup was created at:
`/root/sglang-3060-12g-hicache/3090-dev/.p0-a-budget-rerun-20260911-r14-backup`.

## Commands and results

Required prefix used exactly:
`PYTHONPATH=/root/sglang-3060-12g-hicache/python:/root/sglang-3060-12g-hicache/test /root/sglang-env-3060-4b/bin/python -m pytest -q`

1. Focused budget selector: **6 passed, 3 failed, 15 deselected**, exit 1.
2. Full `3090-dev/test_prefetch_budget_split_unit.py`: **4 passed, 20 failed**, exit 1.
3. The six conditional R9 commands were correctly skipped because both budget
   commands did not pass.

Exact combined stdout/stderr, command headings, exit markers, and failure
traces are captured in tool artifact:
`/home/dev-codex/.local/share/opencode/tool-output/tool_08cd057bc001i0O19PzlS4lw21`.

Representative exact failures include `AttributeError` for missing
`UnifiedRadixCache._t38c_node_context_index` and
`TypeError` where the test lambda did not accept keyword argument `origin`.

## Summary

Remote execution occurred after a successful hash gate, so invocation status is
done. P0-A is **not verified**: the focused and full budget commands failed,
and the six dependent commands were not authorized to run under the supplied
conditional procedure.

## Followups

Investigate the reported test/remote checkout failures in a separately
authorized invocation. Preserve the backup; no rollback was performed.

## Open issues

- Focused budget selector failed 3 tests.
- Full budget suite failed 20 tests.
- Six conditional R9 commands were skipped by procedure.
- No in-workspace transcript file was created; complete transcript is retained
  at the OpenCode tool-output artifact path above.
