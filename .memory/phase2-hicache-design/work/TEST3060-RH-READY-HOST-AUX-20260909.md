ENTRY: ACCEPT

status: blocked
task_id: TEST3060-RH-READY-HOST-AUX-20260909
orchestration_epoch: 20260909-rh-ab28
role: tester
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
revision: 6881529acbb55c9dc55745d08fca62b585ecdbad
verdict: BLOCK

## Artifacts

- This independent report.
- No source, gate, remote, or test files were modified.
- Target commit and branch verified at the requested revision.

## Evidence

Passed:

- `python3 3090-dev/test_rh_contract_dependency_free.py` — 3 tests OK.
  The auxiliary fields are derived by `_host_alloc_hybrid_completion` from
  `_host_alloc_hybrid_sidecar_counts`, including actual Mamba pool names and
  fetched counts.
- `python3 3090-dev/test_prefetch_gate_skip_regression.py` — 2 tests OK.
  Gate skip performs no storage I/O and returns `HELD`; gate pass performs one
  storage issue and returns typed `ISSUED` with an attempt ID.
- `python3 3090-dev/test_storage_regression.py
  RestoreDurabilityMarkingTests` — 4 tests OK, including hybrid all-or-nothing
  discard and accepted/shortfall durability behavior.
- `python3 3090-dev/test_storage_regression.py
  FrontierWaiterRegistryTests.test_release_aborted_request_cleans_waiter_and_terminal`
  — OK.
- `python3 3090-dev/test_hicache_restore.py` — 92 tests OK.
- In-memory AST parse/compile of the two changed product files and the changed
  dependency-free test — PASS.
- `git diff --check 6881529^..6881529` — PASS. The commit diff is limited to
  `scheduler.py`, `unified_radix_cache.py`, and
  `test_rh_contract_dependency_free.py`; the worktree has no tracked changes.
- Independent wrapper harness — an issued result retains the active claim;
  stale release leaves it active. Independent terminal harness — a stale
  terminal leaves a newer active attempt and its completion handoff untouched.
- Independent finalizer harness using the real source methods produced:
  `accepted => ('test-rid:prefetch:1', {completed_kv_tokens: 4,
  required_aux_pools: ['swa'], completed_aux_units: {swa: 2},
  finalize_result: 'accepted'})` and
  `discarded => (..., {completed_aux_units: {swa: 1},
  finalize_result: 'discarded'})`.
- AST caller audit found explicit origins at all seven scheduler prefetch call
  sites. In `_add_request_to_queue`, RH-OFF calls
  `EAGER_RH_OFF` at lines 4924-4925 before queue append at 4927; RH-ON has no
  eager call and appends directly. RH pass uses `READY_HORIZON`; retries use
  `DEMAND_RETRY`; disaggregated prefill uses its explicit origin.

## Blocking findings

1. **Product defect — discarded hybrid material still emits ready_host.**

   `_handle_prefetch_result` correctly records `finalize_result="discarded"`
   after an all-or-nothing sidecar shortfall
   (`unified_radix_cache.py:5612-5645`) and records terminal outcome
   `"finalized"`. `_feed_restore_terminal` maps every `"finalized"` terminal
   to `RestoreEvent.FINALIZED`, applies `RESTORING -> READY`, and emits
   `rh_ready_host.v1` without checking `completion.finalize_result`
   (`scheduler.py:3786-3787,3826,3833-3865`).

   An independent AST-extracted scheduler harness reproduced a
   `ready_host` record with `completed_aux_units={'mamba': 1}` and
   `finalize_result='discarded'`, while the state became `READY`. This violates
   the supplied contract that only all-material success emits joined
   `ready_host` (ARCH RH-G08 and RH-PA-I7); it can falsely advertise hybrid
   readiness after the finalizer discarded the material. The existing discard
   regression proves no durable insert occurs, but does not cover scheduler
   terminal-to-ready integration.

2. **Gate authorization remains unresolved.**

   `review/gates/ARCH-20260909-RH-PREADMISSION.md` remains
   `status: proposed`, `implementation_authority: none`, and
   `implementation_admission: BLOCKED_PATTERN_INTAKE_AND_NOVEL_DECLARATION`.
   The Novel Mechanism is still proposed/non-self-approving and the Pattern
   Intake remains conditional, with both design inputs pinned to
   `82ab235606...`, not the verified implementation commit. This is a control
   plane admission blocker, not a code-test failure.

## Unavailable evidence

- `PYTHONPATH=python python3 3090-dev/test_ready_horizon_unit.py`,
  `test_hicache_restore_scheduler_feed.py`, and the package-backed restore
  budget test cannot import the project because `orjson` is unavailable.
- No packages were installed. No live 3060 runtime/E2E trace, performance
  result, or dependency-backed scheduler ready_host integration was possible.
  These are environment/evidence gaps and do not clear the product defect or
  gate blocker.

## Summary

The finalizer-owned auxiliary join, successful `ISSUED` claim lifetime,
stale-attempt fencing, gate-skip behavior, RH order/origin wiring, hybrid
discard cleanup, and dependency-free regressions pass. Overall acceptance is
BLOCKED by the discarded-hybrid false-ready path and by the unaccepted
architecture/Pattern Intake/Novel Mechanism gate chain.

## Followups

- Fresh implementation task: prevent discarded or otherwise incomplete hybrid
  finalization from applying `READY` or emitting `ready_host`; add a focused
  terminal-to-ready integration oracle.
- Fresh gate-owner/orchestrator task: accept and revision-pin the architecture,
  Pattern Intake, and Novel Mechanism chain before implementation acceptance.
- Fresh tester task after repair and environment setup: run the package-backed
  scheduler feed/ready-horizon tests plus bounded RH-OFF/RH-ON runtime and
  performance evidence.

## Open issues

- Dependency-backed tests, live runtime/E2E, and performance remain uncomputed
  because of the missing `orjson` environment dependency.
- Formatter/type-checker and remote deployment evidence were not part of this
  read-only verification and remain open.
- Further implementation, gate, or runtime work requires a fresh Task ID.
