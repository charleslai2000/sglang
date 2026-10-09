# P0-A Budget Failure Triage R10

- Task ID: `P0-A-BUDGET-TRIAGE-20260911-R10`
- Invocation: `ses-p0a-budget-triage-r10-20260911`
- Epoch: `2026-09-11`
- Status: done
- Dispatch: `ENTRY: ACCEPT`

## Scope and limits

Read-only inspection of the local `sglang-3090-24g-opt` checkout, its budget
test, relevant `UnifiedRadixCache` APIs, the R9 report/transcript, R4 triage,
and current git diff. No files other than this report were changed; no remote,
3090 runtime, production execution, or 3060 execution was used. The R9
transcript is the only traceback source available; no fresh test run was made.

## Evidence

- R9 report says the full budget file had `12 passed, 12 failed`; failures
  involve missing `_t38c_request_contexts` and `_t38c_residency_lock`.
  Source: `.memory/phase2-hicache-design/work/P0-A-REMOTE-EXEC-20260911-R9.md`,
  lines 44-46 and 76-79.
- R9 transcript preserves all 12 IDs and tracebacks at lines 155-647.
- Current test fixture `_make_budget_cache()` creates its cache with
  `test_storage_regression._make_cache()` at
  `3090-dev/test_prefetch_budget_split_unit.py:157-190`.
- That legacy harness uses `object.__new__(UnifiedRadixCache)` and initializes
  neither `_t38c_request_contexts` nor `_t38c_residency_lock`; see
  `3090-dev/test_storage_regression.py:755-819`.
- Production `UnifiedRadixCache.__init__` initializes both attributes at
  `python/sglang/srt/mem_cache/unified_radix_cache.py:1677-1687`.
- `prefetch_from_storage()` unconditionally calls
  `_t38c_trace_context_for_prefetch()` at
  `python/sglang/srt/mem_cache/unified_radix_cache.py:5461-5463`; that helper
  iterates `_t38c_request_contexts` at lines 2418-2428.
- The storage-drain path unconditionally calls
  `_t38c_residency_release_queues_drained(self)` at
  `python/sglang/srt/mem_cache/unified_radix_cache.py:7262-7264`; the R9
  traceback shows that path entering `with cache._t38c_residency_lock`.
- The current test fixture already adds `_t38c_node_context_index = {}` at
  `test_prefetch_budget_split_unit.py:165`, demonstrating the same stale
  legacy-fixture contract is already being repaired there.
- The current test-only `_BudgetController.prefetch()` at
  `test_prefetch_budget_split_unit.py:136-154` does not accept the production
  call's `trace_context=` keyword. This is not visible in R9 because the
  missing request-context attribute aborts first; it is a predictable next
  fixture failure after the two missing attributes are supplied.

## Exact failing test IDs and traceback classes

All 12 failures are in `3090-dev/test_prefetch_budget_split_unit.py`:

1. `PrefetchBudgetSplitTests.test_demand_issue_not_charged_to_spec_counter`
   — `AttributeError: UnifiedRadixCache._t38c_request_contexts`, at product
   `unified_radix_cache.py:2424`.
2. `PrefetchBudgetSplitTests.test_spec_budget_full_declines_speculative_passes_demand`
   — same `_t38c_request_contexts` error at line 2424.
3. `PrefetchBudgetSplitTests.test_speculative_issue_charges_spec_counter`
   — same `_t38c_request_contexts` error at line 2424.
4. `PrefetchReservationExactlyOnceTests.test_abort_path_releases_speculative_reservation`
   — same `_t38c_request_contexts` error at line 2424.
5. `PrefetchReservationExactlyOnceTests.test_detach_path_releases_speculative_reservation`
   — same `_t38c_request_contexts` error at line 2424.
6. `PrefetchReservationExactlyOnceTests.test_revoke_path_releases_speculative_reservation`
   — same `_t38c_request_contexts` error at line 2424.
7. `SpeculativeStagingNoEvictTests.test_demand_alloc_failure_still_evicts`
   — `AttributeError: UnifiedRadixCache._t38c_residency_lock`, at product
   `unified_radix_cache.py:510`, reached from drain line 7264.
8. `SpeculativeStagingNoEvictTests.test_speculative_alloc_failure_never_evicts`
   — same `_t38c_residency_lock` error at line 510.
9. `ReadyHorizonOffModeTests.test_off_alloc_failure_evicts_like_baseline`
   — same `_t38c_residency_lock` error at line 510.
10. `ReadyHorizonOffModeTests.test_off_demand_bypasses_rate_check`
    — same `_t38c_request_contexts` error at line 2424.
11. `ReadyHorizonOffModeTests.test_off_single_track_physical_check_only`
    — same `_t38c_request_contexts` error at line 2424.
12. `ReadyHorizonOffModeTests.test_off_speculative_issue_never_grows_spec_counter`
    — same `_t38c_request_contexts` error at line 2424.

The focused R9 selection separately reports three of these (abort, detach,
revoke), all at issue time and all with `_t38c_request_contexts` missing.

## Classification

The 12 observed failures are fixture/setup contract failures, not evidence of
a budget or Ready Horizon product regression. The legacy `object.__new__`
harness bypasses the production constructor, while the current production
paths now assume constructor-owned durable-trace state. The failures occur
before each test's budget/release/eviction assertion executes.

The classification is limited to the observed failures. It does not establish
that the budget behavior is correct after fixture repair; a rerun is required.

## Minimal safe test-only correction proposal

In `3090-dev/test_prefetch_budget_split_unit.py`, update only the budget test
fixture/stub:

1. Import `threading`.
2. In `_make_budget_cache()`, initialize
   `cache._t38c_request_contexts = {}` and
   `cache._t38c_residency_lock = threading.RLock()` alongside the existing
   `_t38c_node_context_index = {}`.
3. Change `_BudgetController.prefetch()` to accept the production keyword,
   minimally by adding `trace_context=None` (unused by this stub), preserving
   all existing behavior.

This is the smallest fixture-only compatibility correction indicated by the
source and tracebacks. Do not weaken product guards, remove durable-trace
calls, or change budget assertions. After this correction, rerun the focused
and full budget suite; classify any new traceback independently rather than
assuming the current 12 are resolved.

## Artifacts

- This report: `.memory/phase2-hicache-design/work/P0-A-BUDGET-TRIAGE-20260911-R10.md`
- R9 report: `.memory/phase2-hicache-design/work/P0-A-REMOTE-EXEC-20260911-R9.md`
- R9 transcript: `.memory/phase2-hicache-design/work/P0-A-REMOTE-EXEC-20260911-R9.transcript`
- R4 triage: `.memory/phase2-hicache-design/work/P0-A-TRIAGE-20260911-R4.md`

## Followups

- Fresh executor/coder dispatch may apply only the three listed test-fixture
  corrections, then run the authorized verification procedure.

## Open issues

- No post-correction test result is available in this read-only inspection.
- The current checkout has unrelated dirty product files and many untracked
  review/memory artifacts; they were not modified or adjudicated.
- Exact constructor compatibility of any further stub keyword is unknown until
  the fixture is corrected and tests are rerun.
