ENTRY: ACCEPT

status: blocked
task_id: REVIEW3060-RH-FINAL-20260909
orchestration_epoch: 20260909-rh-ab31
role: reviewer
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
revision: 67b39b5aca6aaacbf410d21efda9b7059eaa8d2c
verdict: BLOCK

## Artifacts

- Final gate artifact:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/REVIEW-20260909-RH-PREADMISSION.md`
- This independent review report.
- No runtime source, tests, other gate documents, or remote systems were
  modified.

## Evidence

Authorization and scope:

- Pattern Intake, Novel Mechanism, and architecture gates all record `ACCEPT`
  and pin `implementation_revision` to
  `67b39b5aca6aaacbf410d21efda9b7059eaa8d2c`.
- `ARCH3060-RH-GATE-ACCEPT-20260909.md` records
  `AUTHORIZED_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW`. The prior authorization
  blocker is resolved.
- `git rev-parse HEAD` matches the requested full revision.
- `git diff --name-status 82ab235606..67b39b5aca` shows exactly the accepted
  nine-file implementation/test range; `git diff --check` passes.

Independent checks:

- `python3 3090-dev/test_rh_contract_dependency_free.py` — 4 tests OK.
- `python3 3090-dev/test_hicache_restore.py` — 92 tests OK.
- Focused storage regressions — 5 tests OK.
- Focused hybrid speculative-reservation regression — 1 test OK.
- `py_compile` for changed Python files — PASS.

Requirement review:

- Successful issue returns typed `ISSUED` and retains its active claim.
- Terminal records carry attempt IDs; stale terminal IDs return before state
  transition, and claim release compares the expected ID.
- Finalizer-owned KV and auxiliary completion fields feed `ready_host`.
- Discarded/rejected hybrid finalization maps to `DENIED_SHORT` with
  `short_tail_recompute=True`, leaves state `NONE`, and suppresses
  `rh_ready_host.v1`.
- RH-OFF retains the eager `EAGER_RH_OFF` issue before queue append. The final
  live equivalence trace remains a follow-up.
- No allocator, Mamba, or HOST_ALLOC-generation authority change is present in
  the reviewed range.

## Findings

### BLOCKER-1 — RH issue decision telemetry has no joinable attempt ID

Locations: `python/sglang/srt/managers/scheduler.py:4216-4240`,
`:4088-4123`; contract `review/gates/ARCH-20260909-RH-PREADMISSION.md:299-367`.

Evidence:

- `_ready_horizon_pass` emits `_emit_rh_decision` for `decision="issue"`
  before calling `_prefetch_kvcache` at lines `4248-4252`.
- That decision's `attempt_id` is read from the request's active claim at
  lines `4235-4238`, but `_claim_prefetch` creates the claim only inside
  `_prefetch_kvcache` at line `3098`.
- Thus every ordinary RH issue decision records both active and explicit
  `attempt_id` as `None`; the later stage and ready-host events have a real
  attempt ID.
- The accepted contract requires `(rid, attempt_id)` joins and says a missing
  mandatory attempt/order field makes the bounded rate `not_computable`.
- The committed event test checks field names only and does not check this
  ordering/null-value invariant.

Acceptance impact: the required bounded RH authorization → issue → finalizer →
admission join cannot be constructed for successful RH issues. This is a
code-level failure of the mandatory telemetry contract, so final acceptance is
blocked even though runtime integration/performance evidence may remain a
follow-up.

## Summary

The final revision closes the prior authorization blocker and the earlier code
blockers for typed successful issue, attempt-fenced terminal cleanup,
authoritative KV+aux readiness, and discarded-hybrid false readiness. Static
and dependency-free tests pass. Independent review remains BLOCKED solely by
the deterministic issue-event attempt correlation defect above.

## Followups

- Fresh implementation Task ID: bind the actual claimed attempt ID to every
  `rh_preadmission.v1` `decision=issue` record and add an executable
  decision/stage/ready-host/admission join test.
- Fresh tester Task ID: rerun dependency-backed scheduler-feed and final
  revision RH-OFF/RH-ON bounded runtime checks when `orjson` and the target
  environment are available.
- Fresh performance/deployment Task ID for any terminal runtime or performance
  acceptance claim.

## Open issues

- BLOCKER-1 must be repaired and independently retested before the final gate
  can be ACCEPT.
- Missing `orjson`, formatter/typechecker tooling, live final-revision trace,
  and performance evidence are non-blocking follow-ups after the code blocker.
