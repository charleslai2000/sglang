ENTRY: ACCEPT

status: done
task_id: REVIEW3060-RH-FINAL-JOIN-20260909
orchestration_epoch: 20260909-rh-ab33
role: reviewer
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
revision: 6edf69ce29fe2598fba51c94a99315239cf1a8c8
parent_revision: 67b39b5aca6aaacbf410d21efda9b7059eaa8d2c
verdict: ACCEPT

## Artifacts

- Final gate artifact:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/REVIEW-20260909-RH-PREADMISSION.md`
- This independent review report.
- No runtime source, tests, other gate documents, or remote systems were
  modified.

## Evidence

Revision and scope:

- `git rev-parse HEAD` matches the requested full revision.
- The target commit is a direct child of the accepted gate-pinned revision
  `67b39b5aca6aaacbf410d21efda9b7059eaa8d2c`.
- `git diff --name-status 67b39b5aca 6edf69ce29` shows exactly the scheduler
  and two focused test files listed in the dispatch.
- `git diff --check` passes.

Prior blocker closure:

- `_ready_horizon_pass` skips the prefetch-independent issue decision,
  executes `_prefetch_kvcache`, obtains `PrefetchIssueResult.attempt_id`, and
  emits the authoritative decision only afterward.
- `decision=issue` requires both `ISSUED` status and a non-null attempt ID.
  Missing-ID, held, skipped, and failed outcomes are non-issue decisions.
- The decision is emitted before `rh_stage.v2`; the same attempt ID is carried
  through ready-host terminal telemetry and the subsequent admission record.

Independent deterministic evidence at the target HEAD:

- `3090-dev/test_rh_contract_dependency_free.py` — 5 tests OK.
- `3090-dev/test_prefetch_gate_skip_regression.py` — 2 tests OK.
- `3090-dev/test_hicache_restore.py` — 92 tests OK.
- Focused storage/abort regressions — 5 tests OK.
- AST parse/compile of all three changed Python files — PASS.

Earlier invariants rechecked from source and accepted evidence:

- Typed successful issue retains its active claim.
- Terminal attempt IDs and expected-ID release prevent stale cleanup.
- Finalizer-owned KV/auxiliary completion feeds `ready_host`.
- Discarded/rejected hybrid finalization maps to recompute state `NONE` and
  emits no `rh_ready_host.v1`.
- RH-OFF preserves eager-before-append behavior; RH-ON remains queue-first and
  RH-owned.
- No allocator, Mamba, HOST_ALLOC-generation, persistence, or remote scope
  change is present.

Gate consistency conclusion:

- Accepted Pattern Intake, Novel Mechanism, and architecture gates are pinned
  to `67b`, which is an ancestor of the reviewed commit.
- The descendant is a narrow correction within the already accepted telemetry
  symbol and adds executable oracles; it creates no new authority/failure
  boundary or interface shape. Re-opening/re-pinning those design gates is
  therefore not required for this review. The final gate records the exact
  reviewed SHA.

## Summary

The final RH implementation commit is independently accepted. It resolves the
previous blocker: a successful RH issue now produces an attempt-correlated
`rh_preadmission.v1 decision=issue` after the actual prefetch result exists,
before `rh_stage.v2`, and without false issue classification on hold/failure.
The deterministic correctness and regression evidence passes.

## Followups

- Fresh tester/runtime task: rerun the package-backed RH unit/scheduler-feed
  suite when `orjson` is available.
- Fresh runtime/performance task: collect final-revision deploy-hash-pinned
  RH-OFF/RH-ON telemetry and operational/performance evidence.

## Open issues

- The package-backed RH unit suite could not collect because `orjson` is
  unavailable.
- No final live/deploy-hash runtime or performance trace was available; these
  are non-blocking under this dispatch.
- Formatter/type-checker tooling was unavailable.

