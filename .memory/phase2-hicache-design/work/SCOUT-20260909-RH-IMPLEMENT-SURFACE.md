ENTRY: ACCEPT

status: done
task_id: SCOUT3060-RH-IMPLEMENT-SURFACE-20260909
orchestration_epoch: 20260909-rh-ab19
role: scout

## Artifacts

- This report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/SCOUT-20260909-RH-IMPLEMENT-SURFACE.md`
- No source, test, gate, branch, or remote files were changed.

## Search limits

Read-only inspection was limited to the authorized source branch
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`, branch
`3060-12g-qwen35-4b`, its targeted `3090-dev`/`test` harnesses, the supplied
RH debugger/architecture/pattern artifacts, and the adjacent phase2 memory
reports. I did not inspect unrelated repositories, remote hosts, private
storage, or run tests. The source revision is not hash-pinned by this scout
invocation; the supplied Pattern Intake records `82ab235606233160701b15f657a71794cfd29a30`.

## Confirmed source surface

### 1. Queue admission boundary: one method, two relevant branches

`python/sglang/srt/managers/scheduler.py:4516-4530`
`Scheduler._add_request_to_queue` currently calls `_prefetch_kvcache(req)`
before appending to `waiting_queue` for normal (`DisaggregationMode.NULL`)
requests (`:4519-4524`). The PREFILL disaggregation branch also calls it at
`:4525-4530`, but there is no RH waiting-queue pass for that branch. The
minimal RH pre-admission change should be scoped to the normal waiting-queue
branch unless the architecture owner explicitly includes disaggregated
prefill.

Observed current behavior:

```text
NULL:    _prefetch_kvcache(req); waiting_queue.append(req)
PREFILL: _prefetch_kvcache(req); disagg_prefill_bootstrap_queue.add(...)
DECODE:  disagg_decode_prealloc_queue.add(...); no prefetch here
```

The RH-ON queue-first branch therefore needs to append/set queue-entry time
without issuing, while RH-OFF retains the current eager call/order. The RH pass
already sees the queue only after this method returns.

### 2. RH sole initial issue point

`python/sglang/srt/managers/scheduler.py:3804-3899`

- `:3804-3818`: `_ready_horizon_pass` is event/safety-gated and delegates
  each staging issue to `_prefetch_kvcache`.
- `:3819-3840`: RH-OFF exits before policy/epoch work; this is the existing
  no-op boundary to preserve.
- `:3842-3864`: frontier is trimmed, policy produces `declines` and `to_issue`,
  and declines are parked in the per-RID causal negative cache.
- `:3865-3887`: each `plan.to_issue` request currently receives a bare
  `_prefetch_kvcache(req)` call, then `RESTORING` is inferred from request
  state. This is the exact RH-ON call site for an explicit origin and
  request-local attempt claim.
- `:3888-3899`: remaining candidates are parked on speculative budget after
  the issue exhausts a budget.

The pass is invoked after restore reconciliation at
`python/sglang/srt/managers/scheduler.py:5022-5028`; this ordering makes a
queue-first request visible to RH before ordinary restore reconciliation can
consume it.

### 3. Lower storage/restore authority

`python/sglang/srt/managers/scheduler.py:3024-3178`
`Scheduler._prefetch_kvcache` performs the existing authoritative lower path:

- `:3031-3074`: request geometry/anchor refresh and storage gate.
- `:3074-3096`: `tree_cache.prefetch_from_storage(...)`, including the current
  `demand_restore` flag and `hicache_host_alloc_attempt_id`.
- `:3097-3144`: outcome-to-restore-state transitions, including issued,
  rate/alloc declines, and too-short handling.
- `:3145-3178`: frontier/gate-skip handling.

This function is the smallest place to require an explicit prefetch origin and
to acquire the active-attempt claim before any lower side effect. The claim
must be released only through the existing terminal/retirement paths; RH must
not implement allocation, eviction, or HOST_ALLOC wake policy.

Current non-initial/retry call sites that must remain classified separately:

- `:3415`: paced missed-storage retry (`DEMAND_RETRY`).
- `:3444-3448`: frontier/backup ACK wake re-issue (`DEMAND_RETRY`), with
  `demand_restore` selected by RH/backup state.
- `:3602-3606`: HOST_ALLOC/capacity retry (`DEMAND_RETRY`), with the existing
  attempt snapshot/id setup at `:3585-3600`.
- `:3867`: RH initial staging (`READY_HORIZON`).
- `:4522` and `:4526`: current eager enqueue calls; only `:4522` is the
  RH-OFF normal baseline for this task.

### 4. ReadyHorizonPolicy state funnel and request view

`python/sglang/srt/managers/scheduler_components/ready_horizon.py:409-475`

`ReadyHorizonPolicy._state_funnel` admits:

- `NONE` or `MISS_RECOMPUTE` only when `view.staging_eligible` is true
  (`:419-426`).
- `WAIT_CAPACITY/PREFETCH_BUDGET` (`:427-432`).
- `WAIT_CAPACITY/DEVICE_QUOTA` only when `host_hit_length == 0`
  (`:427-432`).

It rejects `RESTORING`, `HOST_ALLOC`, `FRONTIER`, `BACKUP_PENDING`, and
`REVALIDATE` by construction (`:427-432` and docstring `:414-417`). No change
to this funnel is required for pre-admission ownership transfer.

`Scheduler._ready_horizon_views` at
`python/sglang/srt/managers/scheduler.py:3943-3972` supplies the fields used
by the funnel and policy: `rid`, `state`, `wait_reason`, staged marker,
`host_hit_length`, `staging_eligible`, full prompt length, and session
generation. It does not currently carry an attempt/origin field; those belong
to the request-local control state and issue result, not policy eligibility.

### 5. Request-local fields and ownership location

`python/sglang/srt/managers/schedule_batch.py:831` defines `Req`.
The existing HiCache restore-control block is
`python/sglang/srt/managers/schedule_batch.py:1041-1064`:

- `:1043-1045`: `hicache_restore_state`, wait reason, and state timestamp.
- `:1046-1051`: HOST_ALLOC wait cursor, active attempt id, last attempt id,
  and attempt snapshot.
- `:1052-1064`: sticky miss epoch/generation/anchor identity.

This is the smallest existing owner for the new ephemeral fields required by
the architecture artifact: a monotonically increasing prefetch attempt
sequence, active attempt id, and active origin. They should be scheduler-owned
in-process fields on `Req`, non-serialized and retired with the request. Do
not reuse `hicache_host_alloc_attempt_id`: that id is already passed into the
storage call at `scheduler.py:3093-3095` and has HOST_ALLOC-specific meaning.

The existing restore state transition funnel is
`python/sglang/srt/managers/scheduler.py:3751-3802`; terminal restore outcome
feeding begins at `:3613-3710`. Claim cleanup must be inserted into these
existing issue terminal/retirement paths, not inferred from logger output or
queue position.

## Proposed smallest implementation write set

This is a recommended implementation surface, not an implementation.

1. `python/sglang/srt/managers/scheduler.py`

   - Add/consume the explicit `HiCachePrefetchOrigin` and typed issue/claim
     result at the existing scheduler boundary.
   - In `_add_request_to_queue` (`:4516-4530`), gate only normal NULL-mode
     enqueue: RH-OFF keeps `EAGER_RH_OFF` before append; RH-ON appends first
     and does not call `_prefetch_kvcache` there. Preserve priority rejection,
     queue-limit abort, timestamp, and disaggregation behavior.
   - In `_ready_horizon_pass` (`:3865-3887`), call the issue path with
     `READY_HORIZON`; issue/claim success must be the only source of the RH
     `ready_stage` issued result.
   - In `_prefetch_kvcache` (`:3024-3178`), require origin at every call,
     claim before `init_next_round_input`, gate, reservation, or I/O, and
     return a typed active/declined/issued result without changing the lower
     storage semantics.
   - Classify `:3415`, `:3444`, and `:3602` as `DEMAND_RETRY`; retain their
     existing demand-restore and HOST_ALLOC logic.
   - Release only the matching attempt id in terminal/reconcile/retirement
     paths (`:3613-3802` and request-retirement code around `:4580-4630`),
     after existing reservation/cleanup. A stale completion must not clear a
     newer attempt.
   - Emit/extend attempt-correlated telemetry at the existing RH stage and
     restore/finalize/admission observation points. Telemetry must not be a
     scheduling guard.

2. `python/sglang/srt/managers/schedule_batch.py`

   - Add only the ephemeral request-local claim fields beside the existing
     restore-control fields (`:1041-1064`): sequence, active attempt id, and
     active origin (plus any typed state required by the accepted gate).
   - Keep them out of serialized request protocols and clear them on terminal
     retirement. Existing `hicache_host_alloc_*` fields remain distinct.

3. `python/sglang/srt/managers/scheduler_components/hicache_restore.py`

   - Preferred location for the origin enum and small typed issue result if
     the accepted architecture gate requires a reusable type. Existing
     restore enums/state machine live here (`:152-205`); avoid adding a new
     module for this one enum/result.
   - No change to `_state_funnel`, HOST_ALLOC authority, or lower allocation
     semantics.

### Exact test write surface

Smallest practical regression surface is the existing RH unit harness plus
the existing restore-feed harness; no integration/live test file is required
for the source-level ownership oracle.

1. `3090-dev/test_ready_horizon_unit.py`

   Existing helpers at `:67-220` and scheduler wiring at `:842-900` already
   run the real policy and real `_ready_horizon_pass` with stub collaborators.
   Extend this file with:

   - RH-ON queue-first test: `_add_request_to_queue` appends a normal request
     without calling the issue spy; a subsequent `_ready_horizon_pass` calls
     the issue spy once with `READY_HORIZON` and request becomes `RESTORING`.
   - RH-OFF equivalence test: normal enqueue calls once with `EAGER_RH_OFF`
     before append; RH pass remains a no-op. Existing OFF no-op coverage is
     `:1078-1086` and should be retained.
   - repeated RH pass/active transfer test: unchanged epochs or a request
     already active produce one issue, one reservation/issue trace, and no
     second call. Existing no-event coverage is `:912-925`.
   - state-funnel regression: `RESTORING`, `HOST_ALLOC`, `FRONTIER`,
     `BACKUP_PENDING`, and `REVALIDATE` remain excluded; `NONE`,
     `MISS_RECOMPUTE`, `WAIT[PREFETCH_BUDGET]`, and eligible
     `WAIT[DEVICE_QUOTA, host_hit=0]` remain eligible. Existing policy tests
     cover adjacent cases around `:330-430` and should receive the explicit
     HOST_ALLOC assertion.
   - decline/telemetry assertions: one deterministic `ready_stage` decision
     per attempted RH issue, explicit result for claim-active/declined/issued,
     and no `ready_host` on a non-ready/alloc-failed outcome. Do not use log
     count as the dedupe oracle; assert `(rid, attempt_id)` call traces.

2. `3090-dev/test_hicache_restore_scheduler_feed.py`

   Reuse existing request/scheduler fixtures (`:35-60`) and restore-state
   transition tests (`:60-280`, including HOST_ALLOC at `:201-280`) for:

   - demand retry receives `DEMAND_RETRY`, not RH origin;
   - a matching terminal outcome releases only the matching active claim;
   - stale completion cannot clear a newer claim;
   - positive storage hit with failed full allocation remains HOST_ALLOC/
     DENIED_ALLOC, not miss/READY;
   - Mamba-only generation advancement does not wake a KV-blocked waiter.

3. `3090-dev/test_prefetch_budget_split_unit.py`

   No new file is necessary, but extend only if the implementation changes the
   public call shape of `prefetch_from_storage`. Existing real lower-path and
   RH-OFF preservation coverage is at `:192-205` and `:493-559`; these tests
   already exercise ongoing-prefetch cleanup and `enable_ready_horizon=False`.

## Test oracle / acceptance assertions

For each direct normal request under RH-ON:

```text
queue append -> RH policy decision -> exactly one (rid, attempt_id) claim
-> exactly one lower prefetch submission/reservation -> terminal join
-> full hybrid READY/ready_host or typed non-ready outcome -> admission/retire
```

Required negative assertions:

- zero `EAGER_RH_OFF` issue calls for RH-ON normal queue admission;
- zero `READY_HORIZON` calls for RH-OFF;
- no issue while request is already `RESTORING` or has an active attempt;
- no duplicate reservation/I/O on repeated RH passes, unchanged epochs, or
  self-generated budget traffic;
- no RH staging for `HOST_ALLOC`, `FRONTIER`, `BACKUP_PENDING`, or
  `REVALIDATE`;
- no RH eviction and no RH mutation of HOST_ALLOC generation/cursor;
- allocation failure remains `DENIED_ALLOC`/`HOST_ALLOC`, and Mamba-only
  generation changes do not grant a KV retry;
- claim cleanup is idempotent and attempt-correlated across success, decline,
  exception, cancellation, timeout, and late/stale completion;
- `ready_host` is emitted exactly once only after complete required material is
  physically resident and before admission; non-ready outcomes emit none;
- telemetry fields must join on `(rid, attempt_id)` and missing mandatory
  decision/attempt/readiness/admission fields fail the telemetry assertion,
  rather than being interpreted as zero.

## Followups

- Coder can use the three-file source surface above after architecture/novel
  mechanism admission and should produce a changed-symbol manifest before
  implementation review.
- Tester should add the two harness extensions above and capture immutable
  request/attempt call traces; a live 3060 run remains a separate runtime gate.
- Reviewer must compare the final diff against `review/gates/ARCH-20260909-RH-PREADMISSION.md`
  and the accepted Pattern Intake/Novel Mechanism artifacts.

## Open issues

- The accepted architecture artifact describes `HiCachePrefetchOrigin`,
  `active_prefetch_attempt_id`, and related telemetry but the current source
  has no such origin enum/result or active-prefetch fields. Their exact type
  names remain implementation decisions for coder, subject to the gate.
- `DisaggregationMode.PREFILL` still eagerly calls `_prefetch_kvcache` at
  `scheduler.py:4525-4530`; whether it is in scope for RH pre-admission is
  ambiguous and should not be silently widened.
- The current source has no explicit `ready_host` emitter in the inspected
  scheduler path; the architecture telemetry contract requires one. Exact
  finalize/admission emission symbol should be mapped by coder/tester against
  the accepted gate before implementation.
- Existing test stubs replace `_prefetch_kvcache` with two-argument-compatible
  functions (`test_ready_horizon_unit.py:892-900`), so tests must be updated
  together with the explicit origin signature.
- No tests were executed in this read-only scout invocation.

Extra implementation, test execution, gate work, or corpus work requires a
fresh Task ID.

evidence:

- `python/sglang/srt/managers/scheduler.py:3024-3178,3382-3610,3751-3802,3804-3990,4516-4538,5022-5028`
- `python/sglang/srt/managers/scheduler_components/ready_horizon.py:409-475,546-578`
- `python/sglang/srt/managers/schedule_batch.py:831,1041-1064`
- `3090-dev/test_ready_horizon_unit.py:1-1204`
- `3090-dev/test_ready_horizon_partition.py:303-404`
- `3090-dev/test_hicache_restore_scheduler_feed.py:35-280`
- `3090-dev/test_prefetch_budget_split_unit.py:192-205,493-559`
- `review/gates/ARCH-20260909-RH-PREADMISSION.md`
- `storage/review/gates/pattern-intake/PATTERN-INTAKE-20260909-RH-PREADMISSION.md`
- supplied `DBG-20260909-RH-NO-STAGING.md`

summary: The minimal RH-ON pre-admission implementation surface is the normal
NULL-mode branch of `Scheduler._add_request_to_queue`, the existing RH issue
loop and `_prefetch_kvcache` boundary in `scheduler.py`, plus ephemeral Req
claim fields in `schedule_batch.py` and a shared origin/result type in
`hicache_restore.py` if required by the accepted gate. Existing RH and restore
harnesses can express the required queue-order, dedupe, state-funnel, lower
failure, and telemetry oracles without a new integration harness.

followups: Dispatch coder after gate admission; dispatch tester for the listed
unit harness extensions; keep PREFILL disaggregation and live runtime evidence
as explicit decisions.

open_issues: origin/result/claim symbols do not exist yet; PREFILL scope and
ready_host emitter location are unresolved; no tests were run.
