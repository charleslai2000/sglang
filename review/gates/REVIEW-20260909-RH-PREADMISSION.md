ENTRY: ACCEPT

# RH preadmission independent final review — f629

```yaml
review_task_id: T3060-RH-F629-FINAL-REVIEW-20260909
orchestration_epoch: 20260909-rh-ab44
role: reviewer
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
parent_revision: 6edf69ce29fe2598fba51c94a99315239cf1a8c8
comparison_base: 67b39b5aca6aaacbf410d21efda9b7059eaa8d2c
corpus_revision: 82ab235606233160701b15f657a71794cfd29a30
scope: final independent code review of RH preadmission at f629; no remote load/restart
code_gate_verdict: PASS
runtime_rh_value_verdict: BLOCKED_UNPROVEN
final_verdict: PASS_FOR_CODE_ACCEPTANCE_BLOCKED_FOR_RUNTIME_VALUE_CLAIM
```

## Dispatch and scope

This replaces the stale review pinned to `6edf69ce29fe2598fba51c94a99315239cf1a8c8`.
The reviewed implementation is the exact branch HEAD
`f629d4e2c19eb74571b4154438fd651ce24ff53b`, whose parent is the requested
`6edf69ce29fe2598fba51c94a99315239cf1a8c8`. The requested comparison range
`67b39b5aca..f629d4e2c19eb74571b4154438fd651ce24ff53b` changes exactly three
files:

- `python/sglang/srt/managers/scheduler.py`
- `3090-dev/test_ready_horizon_unit.py`
- `3090-dev/test_rh_contract_dependency_free.py`

No product source, remote service, load, restart, or deployment state was
modified or exercised by this review. Only this gate artifact was written.

## Authoritative gate chain

The following accepted inputs are implementation-pinned to f629 and are
treated as design authorization, not as substitutes for this independent
review:

- `storage/review/gates/pattern-intake/PATTERN-INTAKE-20260909-RH-PREADMISSION.md`:
  Pattern Intake verdict `ACCEPT`.
- `review/gates/NOVEL-MECHANISM-20260909-RH-PREADMISSION.md`:
  Novel Mechanism verdict `ACCEPT`; RH-ON owns the initial issue while
  RH-OFF retains eager-before-append behavior.
- `review/gates/ARCH-20260909-RH-PREADMISSION.md`:
  G-ARCH/RH pre-admission design verdict `ACCEPT`; independent implementation
  review remains required.

The accepted chain preserves the boundaries that RH does not own physical
allocation, HOST_ALLOC generation/FIFO retry, hybrid finalization, or
persistent state.

## Independent source and diff assessment

The final f629 change fixes the reported live startup type mismatch. In
`scheduler.py:4192-4194`, the pass builds `frontier_views` keyed by RID,
iterates the raw frontier `Req` objects, and obtains the typed
`ReadyHorizonView` before reading `staging_eligible`, `state`, or other
policy-only fields. The production builder at `scheduler.py:4411-4440`
constructs one view for every request returned by the same frontier, so the
lookup is complete for the normal request identity contract.

The issue path remains correctly separated: the preliminary decision loop
skips planned issue candidates at `scheduler.py:4196-4200`; the sole
`READY_HORIZON` prefetch call is at `scheduler.py:4253-4257`; the returned
typed result and attempt ID are evaluated at `scheduler.py:4259-4278`; and
the authoritative issue decision is emitted only after an `ISSUED` result
with a non-null attempt ID at `scheduler.py:4279-4314`. This prevents a
false joinable issue event on a held, skipped, failed, or missing-attempt
result.

The f629 diff does not alter allocator, Mamba, HOST_ALLOC, finalizer, claim
ownership, persistence, or RH-OFF enqueue code. The range diff is
whitespace-clean. The added source tests cover the raw-Req/view identity,
attempt/event ordering, failed-issue classification, and the existing
finalizer/discarded-hybrid contract checks.

## Evidence matrix

| Requirement | Evidence | Result |
| --- | --- | --- |
| Exact final revision | `git rev-parse HEAD` = `f629d4e2c19eb74571b4154438fd651ce24ff53b`; branch `3060-12g-qwen35-4b` | PASS |
| Accepted Pattern/Novel/Architecture chain | Three f629-pinned accepted gate artifacts listed above | PASS |
| Reported raw-Req startup crash fixed | `scheduler.py:4192-4194`; `test_ready_pass_joins_raw_frontier_req_to_policy_view` | PASS |
| RH-ON sole initial issue owner | RH-ON queue-first path and `READY_HORIZON` call; RH unit/source checks | PASS structurally |
| Issue decision has actual attempt and correct ordering | f629 source at `4253-4314`; source test `test_issue_join_uses_returned_attempt_and_event_order`; 6/6 contract run | PASS |
| No false issue on hold/failure/missing ID | f629 result classification at `4264-4289`; source test `test_failed_issue_is_hold_and_never_false_issue` | PASS |
| Existing claim, hybrid, auxiliary, and discarded-readiness boundaries | 6/6 dependency-free contract run; tester evidence from `TEST3060-RH-VIEW-TYPE-20260909.md` | PASS for reviewed scope |
| Earlier gate-skip correction remains covered | `3090-dev/test_prefetch_gate_skip_regression.py`, 2/2 local; `TEST3060-RH-PREADMISSION-FIX-20260909.md` | PASS for inherited fix |
| RH-OFF compatibility | Existing RH-OFF ordering test/source audit; no RH-OFF code in f629 diff | PASS structurally |
| Scope and syntax | `git diff --check 67b39b5aca f629d4e2...`; Python compilation of the three changed Python files | PASS |
| Dependency-backed RH unit/integration coverage | `test_ready_horizon_unit.py` import stops at missing `orjson`; tester report records the same environment limit | OPEN evidence gap, not a code finding |
| Final RH-ON runtime eligibility and joined telemetry | `TEST3060-RH-FINAL-ON-TRACE-20260909.md` at f629: 5/5 HTTP 200, but all decisions `exclude/no_restore_potential`, zero issue attempts, no ready-stage/ready-host/admission join | BLOCKED/UNPROVEN runtime value |

## Commands independently run

```text
PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_rh_contract_dependency_free.py -v
Ran 6 tests ... OK

PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_prefetch_gate_skip_regression.py -v
Ran 2 tests ... OK

PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
  python/sglang/srt/managers/scheduler.py \
  3090-dev/test_ready_horizon_unit.py \
  3090-dev/test_rh_contract_dependency_free.py
PASS

git diff --check 67b39b5aca f629d4e2c19eb74571b4154438fd651ce24ff53b
PASS

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  python3 3090-dev/test_ready_horizon_unit.py -v
BLOCKED during import: ModuleNotFoundError: No module named 'orjson'
```

The tester’s f629 evidence additionally reports the dependency-free contract
run 6/6, prefetch gate-skip regression 2/2, `test_hicache_restore.py` 92/92,
focused storage durability/waiter checks 5/5, and AST/in-memory compile
success. The earlier gate-skip report is pinned to `3785c99759`, so it is
supporting ancestor evidence rather than a direct f629 execution.

Evidence hashes independently observed:

- `TEST3060-RH-PREADMISSION-FIX-20260909.md`:
  `1a216952fc7f11f0bd40793c99072d6e0de209c7837e48e58a92dbcc7c10167e`
- `TEST3060-RH-FINAL-ON-TRACE-20260909.md`:
  `934f70c5aeb19e7fc7a42417aa05a6fb3fde21cb96f694dcf5fd017e2396e72f`
- `TEST3060-RH-VIEW-TYPE-20260909.md`:
  `f85a535ddba7cf88760a7c157cc171041f140c1186a102501fb24af83d7996b7`

## Findings

No blocking correctness, security, compatibility, regression, or scope
finding was identified in the f629 code range.

The following is an evidence-status finding, not a product defect:

- **Medium — runtime acceptance evidence blocked/unproven.** The final
  f629 RH-ON trace emitted only `rh_preadmission.v1 decision=exclude
  reason=no_restore_potential` for all five requests. It produced zero
  non-null RH issue attempts and no joinable `ready_stage.v2`,
  `rh_ready_host.v1`, or test-RID `rh_admission.v2` records. Therefore the
  runtime RH eligibility path, ready-host rate, and any RH performance/TTFT
  value are not accepted or inferred from that trace. Acceptance impact:
  this blocks a runtime/performance/value claim, but does not block the
  deterministic code gate for the startup-crash fix.

No questions are outstanding for this invocation.

## Verdict

**Code acceptance at f629: PASS.** The final revision fixes the reported
raw-`Req`/`ReadyHorizonView` startup crash, preserves the accepted RH ownership
boundaries, and passes the available independent deterministic checks.

**Runtime RH value at f629: BLOCKED/UNPROVEN.** The final ON trace did not
reach an eligible RH issue because every request was excluded for
`no_restore_potential`; it cannot establish ON telemetry joins, eligibility,
ready-host admission, or performance value.

This review therefore accepts the implementation code gate while explicitly
withholding runtime/value acceptance. Any runtime diagnosis, another replay,
or telemetry repair requires a fresh Task ID.

status: done
artifacts:
  - review/gates/REVIEW-20260909-RH-PREADMISSION.md
evidence:
  - f629 source/diff inspection and local command results above
  - accepted Pattern Intake, Novel Mechanism, and Architecture gates
  - TEST3060-RH-PREADMISSION-FIX-20260909.md
  - TEST3060-RH-FINAL-ON-TRACE-20260909.md
  - TEST3060-RH-VIEW-TYPE-20260909.md
summary: code gate PASS at exact revision f629; runtime RH value remains blocked/unproven because final ON trace had no_restore_potential for every request and no issue/ready join
followups:
  - Fresh Task ID: provide eligible RH-ON runtime evidence with non-null issue attempts and complete request-correlated storage/ready/admission telemetry if runtime/value acceptance is required.
  - Fresh Task ID: rerun dependency-backed RH unit/scheduler-feed tests when orjson and the required project environment are available.
open_issues:
  - Runtime RH eligibility, joined telemetry, ready-host admission, and performance/TTFT value are not established by the final trace.
  - `orjson` is unavailable for package-backed RH unit collection in this environment.
```
