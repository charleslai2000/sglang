status: done

artifacts:
- Triage report: `/home/dev-codex/workspaces/.memory/phase2-hicache-design/work/P0-A-RESIDENCY-TRIAGE-20260911-R20.md`
- Input transcript: `/tmp/p0a-r19-transcript.txt`
- R19 report: `/home/dev-codex/workspaces/.memory/phase2-hicache-design/work/P0-A-REMOTE-RERUN-20260911-R19.md`

evidence:
- R19 identifies exactly three failures in the full budget suite: `SpeculativeStagingNoEvictTests.test_demand_alloc_failure_still_evicts`, `SpeculativeStagingNoEvictTests.test_speculative_alloc_failure_never_evicts`, and `ReadyHorizonOffModeTests.test_off_alloc_failure_evicts_like_baseline` (R19 report lines 11-13; transcript lines 179-182).
- All three fail in the common helper path `_drain_one_hit` at `3090-dev/test_prefetch_budget_split_unit.py:437` in the supplied transcript, while calling `UnifiedRadixCache._drain_storage_control_queues_impl`; the common exception is `AttributeError: 'UnifiedRadixCache' object has no attribute '_t38c_residency_queue_blocked'` (transcript lines 41-80, 81-121, 122-169).
- The failing production call is `_t38c_residency_release_queues_drained(self)` at `python/sglang/srt/mem_cache/unified_radix_cache.py:7264`; its implementation reads a pending set and then unconditionally calls `cache._t38c_residency_queue_blocked.difference_update(pending)` (source lines 506-516 in the R19-matching `sglang-3090-24g-opt` checkout).
- The production constructor initializes the complete residency state, including `self._t38c_residency_lock = threading.RLock()` and `self._t38c_residency_queue_blocked = set()`, at `python/sglang/srt/mem_cache/unified_radix_cache.py:1686-1695` in the R19-matching checkout.
- The test fixture does not invoke the constructor: `3090-dev/test_storage_regression.py:_make_cache` creates the object with `object.__new__(UnifiedRadixCache)` at lines 736-737. Therefore constructor-owned residency attributes must be supplied by each legacy fixture that manually constructs the object.
- In the R19-matching budget fixture, `3090-dev/test_prefetch_budget_split_unit.py:_make_budget_cache` initializes `_t38c_residency_lock` at lines 174-176 but has no `_t38c_residency_queue_blocked` assignment. The sibling `3090-dev/test_drain_reentry.py:_make_cache` initializes the missing set at line 587, and the production constructor establishes the same empty-set invariant.
- Residency queue call sites use the set as mutable cache-owned state: add at `_t38c_residency_reconcile` queue-nonempty handling (source line 1262), discard on publication (line 1343), discard on retirement (line 490), clear during `_reset_full` (line 2620), and reconcile it after a drain (lines 506-516). The required type/invariant is therefore a per-cache mutable `set`, not `None`, a shared global, or a test-local temporary.
- The authoritative residency contract requires `release_queues_drained` reconciliation at the end of the owning drain transaction (ARCH report `ARCH-20260908-P0-RESIDENCY-R17-TIMING-CONTRACT.md:186-198`). The failure occurs before that reconciliation can run and is fixture setup, not evidence of a residency algorithm failure.
- R19's other suites passed: 13 ready-horizon selected tests, 9 budget selected tests, 74 ready-horizon tests, 46 restore scheduler-feed tests, 18 partition tests, 2 regression tests, and 19 dependency-free tests (transcript lines 3-35, 16-20, 185-222). This supports a single missing fixture attribute as the classification.

summary:
- Classification: all three R19 `_t38c_residency_queue_blocked` failures are the same test-harness initialization defect. They occur in three tests only because those tests are the first budget-suite cases to drain a storage hit and reach the new queue-reconciliation hook; the requested M2/off-mode assertions are not reached.
- Exact minimal test-only correction: in the R19-matching `3090-dev/test_prefetch_budget_split_unit.py`, inside `_make_budget_cache`, immediately after the existing `_t38c_residency_lock = threading.RLock()` initialization, add `cache._t38c_residency_queue_blocked = set()`.
- No production correction is indicated. Do not weaken the production hook with `getattr`, add global state, or alter queue reconciliation. The fixture is bypassing `UnifiedRadixCache.__init__` and must mirror the constructor-owned empty set.
- The correction is sufficient for the reported exception: all three failing tests call `_make_budget_cache`, and all three fail at the common post-drain hook before their assertions. It is test-only and preserves the expected per-cache mutable-set semantics.

followups:
- Apply/review only the one-line fixture initialization in the R19 test checkout, then rerun the full `test_prefetch_budget_split_unit.py` suite under the same command/environment before declaring P0-A verified.
- Confirm the rerun reaches the intended assertions for the three failure IDs and retains the previously passing suites; no source/product edit is needed for this triage.

open_issues:
- The workspace contains both `sglang-3090-24g-hicache` and `sglang-3090-24g-opt` checkouts. The supplied R19 transcript uses `/root/sglang-3060-12g-hicache` and production line numbers matching the `sglang-3090-24g-opt` source shape, while the local `sglang-3090-24g-hicache` checkout currently lacks the corresponding t38c symbols and also lacks `threading` in this test file. The exact rerun checkout should be confirmed before applying the one-line correction.
- This invocation performed read-only inspection and did not run tests or modify product/test source. The durable report itself is the requested coordination artifact.
