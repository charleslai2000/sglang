# CODE-20260909-HOST-ALLOC-EPOCH-TELEMETRY-FINAL

ENTRY: ACCEPT

status: done

Task ID: `CODE-20260909-HOST-ALLOC-EPOCH-TELEMETRY-FINAL`  
Orchestration epoch: `20260909-P4`  
Role: `coder`  
Branch: `3060-12g-qwen35-4b`  
Base review: `REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH-FINAL`  
Commit: `82ab235606`

## Artifacts

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `3090-dev/test_storage_regression.py`
- This report at the requested sibling-workspace path.

No remote, sibling 3090 repository, storage artifact, or unrelated branch file
was changed or staged.

## Summary

- F-HAE-FINAL-01: hybrid all-or-nothing and sidecar telemetry access is now
  optional-field safe for duck-typed transfers. Missing `hit_policy`, pool
  source/name, keys, or hit-page maps produce conservative observational
  values and cannot raise from telemetry. The hybrid validation path uses the
  same safe access for compatibility fixtures.
- F-HAE-FINAL-02: cache-side `host_allocability_change` records retain the
  complete monotonic generation and mutation sequence, but emission is bounded
  independently of scheduler wake decisions. Per `(pool, cause, request,
  trace)` key, the policy emits the first 16 mutations, samples every 128th
  mutation, and caps at 64 records; each cache instance caps the family at 256
  records. Sample fields retain the sequence, mutation count, sample index, and
  coalesced count for joins. Allocation, generation, and wake behavior are not
  suppressed.
- F-HAE-FINAL-03: discarded hybrid finalize telemetry now reports
  `restore_state_after=READY`, matching the existing `finalized` terminal handoff
  consumed by the scheduler. All-or-nothing discard behavior is unchanged.

## Verification evidence

Passed:

- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_drain_reentry.py` — 31/31.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_hicache_restore.py` — 92/92.
- Focused source-loaded regressions:
  `python3 3090-dev/test_storage_regression.py RestoreDurabilityMarkingTests HostAllocMutationTelemetryTests` — 5/5.
  This covers current `SimpleNamespace` transfer shapes, accepted and
  discarded finalize state, and 5,000 repeated cache mutations with a maximum
  of 64 emitted mutation records while generation/sequence reach 5,000.
- `python3 -m py_compile` for the changed source/test files — passed.
- `git diff --check` — passed before commit.

The dependency-free required bundle is therefore 123/123 passed.

Blocked at collection by the environment, not assertion failures:

- `registered.unit.managers.test_hicache_host_allocability` — missing `orjson`.
- `registered.unit.mem_cache.test_mem_pool_host` — missing `torch`.
- `3090-dev/test_hicache_restore_scheduler_feed.py` with `PYTHONPATH=python:test` — missing `orjson`.

The broad `test_storage_regression.py` invocation is not used as acceptance
evidence; its torch-free harness has unrelated pre-existing fixture failures
outside this task. The requested focused class subset passes 5/5.

## Followups

- Re-run the registered modules and scheduler-feed test in the repository’s
  normal environment with `orjson`, `torch`, and pytest/runtime dependencies.
- Fresh independent review remains with the named reviewer owner.

## Open issues

- Registered/live environment prerequisites remain unresolved: `orjson`,
  `torch`, and the normal 3060 runtime acceptance environment are unavailable
  in this workspace.
