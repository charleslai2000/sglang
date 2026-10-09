status: done
artifacts:
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/P0-A-FAILURE-TRIAGE-20260911.md
evidence:
  inspected:
    - work/TEST3060-RH-REALPATH-VERIFY-20260909.md
    - work/TEST-P0-A-RH-FOCUSED-REGRESSION-20260910.md
    - work/OPS-P0-A-REMOTE-RECONCILE-PREP-20260910.md
    - work/HANDOFF-2026-09-10-RH-SPEC-BUDGET-SESSION2.md
    - python/sglang/srt/managers/scheduler.py
    - python/sglang/srt/managers/scheduler_components/hicache_restore.py
    - python/sglang/srt/managers/scheduler_components/ready_horizon.py
    - python/sglang/srt/mem_cache/unified_radix_cache.py
    - 3090-dev/test_ready_horizon_unit.py
    - 3090-dev/test_hicache_restore_scheduler_feed.py
  observed:
    - The available remote reconciliation report is only a preparation report; it explicitly says no pytest command was run. The earlier source-identical 3060 report records 70 tests with 2 failures and 4 errors in ready_horizon_unit, and 46 tests with 1 failure and 2 errors in scheduler_feed.
    - The available reports enumerate six broad-suite mismatch sites, not a canonical list of 17 distinct failures. Therefore the remaining eleven entries of the user-referenced 17-failure R3 report are not present in the readable local evidence packet.
    - Real scheduler issue paths pass `origin=` to the prefetch callback (`scheduler.py` issue path around 3339 and READY_HORIZON wiring around 4779/4856). The deterministic-miss test doubles use a legacy `charge()` signature and reject that keyword.
    - `HiCachePrefetchIssueStatus` and `PrefetchIssueResult` are the current typed API. Compatibility aliases exist on `PrefetchIssueResult`, but the real method returns the result object, not the old bare enum identity.
    - Current ready-stage emission is `evt=ready_stage schema=rh_stage.v2 ... result=...` (`scheduler.py` around 4868). Existing runtime evidence also contains that exact token shape.
    - The real terminal allocation path conditionally calls `tree_cache.pop_host_alloc_failure(req.rid)` (`scheduler.py` around 3521); `UnifiedRadixCache.pop_host_alloc_failure()` is a real cache API and consumes the recorded failure (`unified_radix_cache.py` around 6105-6113).
    - `UnifiedRadixCache.__init__` initializes `_t38c_node_context_index` together with the related durable-trace maps (`unified_radix_cache.py` around 1677-1685). A fixture that constructs the object with `__new__` or a hand-made SimpleNamespace must initialize this map if it exercises durable-trace lookup.
    - The host-allocation wait predicate is intentionally span/capacity based; live evidence records required KV/Mamba span 54976/1, free 21057/104, and evictable 0/0. A test expectation that treats available size 54976 as insufficient is not self-evidently a product regression; it conflicts with the helper's current complete-span semantics and needs an explicit unit-contract decision.
  classification:
    - id: known-1
      failure: four DeterministicMissParkTests errors
      observed_fact: fixture-local charge() rejects the current origin= keyword.
      likely_owner: test fixture maintenance
      minimal_safe_fix_direction: update the fake charge() signature to accept origin (prefer keyword-only compatibility) and assert the origin where relevant; do not remove origin from production calls.
      blocks_p0_a: no, after fixture repair; current evidence does not indicate product failure.
    - id: known-2
      failure: active_prefetch_claim_blocks_duplicate_and_classifies_retry
      observed_fact: test expects legacy enum identity, while production returns PrefetchIssueResult(status=SKIPPED_ACTIVE, ...).
      likely_owner: test expectation/API migration
      minimal_safe_fix_direction: assert result.status against HiCachePrefetchIssueStatus.SKIPPED_ACTIVE and separately check attempt/origin/reason fields; do not regress the typed return API merely to satisfy identity comparison.
      blocks_p0_a: no, once the test oracle is migrated; the mismatch is deterministic and API-shaped.
    - id: known-3
      failure: test_ready_stage_log_reports_issue_result
      observed_fact: test searches for `evt=ready_stage.v2`, while implementation emits `evt=ready_stage schema=rh_stage.v2`.
      likely_owner: test telemetry-token oracle
      minimal_safe_fix_direction: match the structured event plus schema token (`evt=ready_stage` and `schema=rh_stage.v2`), and retain result=issued assertion. Do not add the obsolete dotted event token solely for the fixture.
      blocks_p0_a: no, assuming the required schema is rh_stage.v2; runtime reports corroborate the current form.
    - id: known-4
      failure: backup_pending_wake_reissues_as_demand_restore error
      observed_fact: scheduler_feed fixture lambda does not accept origin=.
      likely_owner: test fixture maintenance
      minimal_safe_fix_direction: make the lambda accept origin and assert DEMAND_RESTORE/appropriate origin if that is the contract; preserve production origin propagation.
      blocks_p0_a: no after fixture repair.
    - id: known-5
      failure: positive_alloc_failure_maps_to_host_capacity_wait error
      observed_fact: fixture tree_cache lacks pop_host_alloc_failure, which the current terminal path reads.
      likely_owner: incomplete fixture/API surface
      minimal_safe_fix_direction: add a pop_host_alloc_failure stub returning the intended HostAllocFailure (or None for non-failure cases), plus the corresponding cache state needed by the helper. Do not weaken production getattr/consumption semantics.
      blocks_p0_a: no, unless a real cache instance reproduces the missing method; current evidence is fixture-only.
    - id: known-6
      failure: host_alloc_wait_wakes_only_for_complete_requested_span
      observed_fact: fixture expects False at available size 54976, but current helper returns True for that fixture. The report provides no complete requested-span, page-alignment, or Mamba-sidecar values for the unit case.
      likely_owner: unresolved test semantic contract
      minimal_safe_fix_direction: first reconcile the fixture's requested KV/Mamba span and page-alignment values with `_restore_wait_capacity_fits`/HOST_ALLOC contract; only change production predicate if a concrete invariant says 54976 must fail. Preserve full-span and sidecar requirements.
      blocks_p0_a: yes for the specific semantic oracle, until the expected capacity invariant is made explicit; this is the only known item not safely classifiable as a stale fixture/API shape.
    - id: durable-trace-init
      failure: `_t38c_node_context_index` durable-trace initialization
      observed_fact: production initializes the index in UnifiedRadixCache.__init__; hand-built fixtures in the trace tests manually assign or omit it depending on the case.
      likely_owner: fixture construction if the failure is AttributeError/key absence before production init; implementation owner only if a real initialized UnifiedRadixCache loses the map during reset.
      minimal_safe_fix_direction: construct through the normal initializer or initialize the complete `_t38c_*` state bundle in the fixture; verify reset preserves an empty dict. No production change is justified by the available evidence.
      blocks_p0_a: unknown for the eleven unprovided failures; not a blocker on the known packet.
    - id: host-capacity-fixture
      failure: host alloc capacity fixture mismatch
      observed_fact: live trace shows genuine no-evictable-capacity (`free=21057/104`, `evictable=0/0`) and current helper accepts a 54976 value in one unit fixture. These are different observations and cannot be merged into one regression claim.
      likely_owner: test fixture/expectation pending exact case data
      minimal_safe_fix_direction: make KV, Mamba, free, evictable, page size, and requested span explicit in the fixture; assert the intended complete-span predicate. Do not tune production thresholds from this failure alone.
      blocks_p0_a: yes for semantic sign-off; not evidence of implementation regression by itself.
    - id: missing-eleven
      failure: eleven additional failures referenced by the user but absent from readable reports
      observed_fact: no names, tracebacks, assertions, or test identifiers for these entries were available locally; remote tests were not rerun per scope.
      likely_owner: unknown
      minimal_safe_fix_direction: obtain the exact R3 report or raw failure list before attribution. Do not infer fixture/API status from the count.
      blocks_p0_a: yes; causal triage of these entries is not sound without their discriminating evidence.
summary:
  root_cause: >-
    The available failures are predominantly stale test harness/API/telemetry
    oracles caused by the current typed prefetch result, explicit prefetch
    origin propagation, and rh_stage.v2 structured event format. One capacity
    assertion remains semantically unresolved, and the user-referenced eleven
    additional failures cannot be attributed because their report is absent.
  confidence: medium
  causal_chain: >-
    production contract evolved (origin keyword, typed PrefetchIssueResult,
    structured ready-stage schema, terminal host-allocation API) -> legacy
    fixture/signature/string/identity assumptions fail before or at the test
    oracle -> broad suite reports errors/failures that do not demonstrate a
    production regression. Separately, the capacity fixture's expected boolean
    conflicts with the current helper under incompletely specified span data,
    so it remains an unresolved semantic gate rather than a proven bug.
  alternatives_rejected:
    - Removing origin= from production would hide provenance and contradict current RH wiring and tests.
    - Emitting the obsolete `evt=ready_stage.v2` token is rejected because current runtime evidence and code use `evt=ready_stage schema=rh_stage.v2`.
    - Declaring `_t38c_node_context_index` a production initialization regression is rejected because normal UnifiedRadixCache initialization creates it; fixture construction is the demonstrated difference.
    - Calling all 17 failures stale is rejected because the 11-entry failure packet is missing and the capacity assertion is not yet discriminated.
  minimal_fix_direction: >-
    Migrate the six identified tests/fixtures to the current contracts, then
    resolve the host-capacity assertion with an explicit complete-span oracle.
    Obtain the missing R3 failure list and triage each entry before any product
    edit. No production code change is justified by the known fixture/API
    failures alone.
followups:
  - Obtain and attach the remote R3 raw report containing all 17 test identifiers, tracebacks, and assertions.
  - Have coder/tester update only the deterministic-miss and scheduler-feed fixtures plus the enum/telemetry assertions, then run the exact focused tests in the reconciled namespace.
  - Decide the host-capacity invariant using explicit KV/Mamba requested-span and page-alignment values; retain P0-A NOT_VERIFIED until that oracle and the missing eleven failures are closed.
open_issues:
  - P0-A is not passed by this report; the available remote prep report explicitly ran no tests.
  - Eleven user-referenced failures lack local evidence and remain untriaged.
  - Host-capacity expectation is unresolved and can block P0-A acceptance.
  - `_t38c_node_context_index` has no demonstrated initialized-production failure in the available evidence.
