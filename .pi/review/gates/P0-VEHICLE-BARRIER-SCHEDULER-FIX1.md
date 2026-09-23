ENTRY: ACCEPT

# P0 vehicle barrier scheduler FIX1 independent gate

- Task ID: `REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX1`
- Orchestration epoch: `2026-09-08-P0`
- Role: `reviewer`
- Invocation status: **done**
- Admission: **ACCEPT**
- Gate verdict: **REJECT**

## Scope and inputs

Read-only review of:

- `tools/p0_session_barrier_vehicle.py`
- `test/registered/unit/mem_cache/test_p0_trace_context_v4.py`
- `TEST-20260908-P0-S25-LIVE-FIX2.md`
- `COD-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX1.md`
- `ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`
- `review/gates/P0-R7-JOIN-ROBUSTNESS-FIX5.md`

Only this gate and the assigned memory report were written. No scheduler,
fixture, product source, remote host, engine, or live endpoint was modified or
run. The aggregate worktree remains dirty and the reviewed vehicle/fixture are
untracked, so this review is against their exact current contents rather than a
task-specific commit.

## Verdict summary

The two-phase scheduling shape does remove the reported eight-worker deadlock:
`_run_build_phase` submits all planned builds without a readiness wait, and
`_run_warm_scheduler` uses a separate bounded warm pool. The frozen validation,
ordered KV/Mamba/durability/residency readiness predicates, restore watchdog,
and no-fixed-sleep structure are present.

The gate is nevertheless **REJECTED**. Independent probes found five
blocking boundary failures that can either produce a false P0 PASS or prevent
valid live evidence from being accepted:

1. failed build HTTP responses carrying an `id` are admitted as build contexts;
2. a tailer error after the final warm future can be omitted from the verdict;
3. a warm response with no response `id` can still satisfy PASS;
4. the synthetic post-response warm marker can overwrite an earlier product
   warm/restore order and create a false restore failure; and
5. conflicting node/hash identities do not invalidate `ready_for_warm` before
   warm submission.

These findings preserve the conclusion that FIX1 addresses the original
deadlock, but they prevent acceptance of the durable/warm gate.

## Findings

### F-1 — BLOCKING: build HTTP/build-finished failure is not fail-closed

- Location: `p0_session_barrier_vehicle.py:798-812`, final accounting
  `:678-691`.
- Evidence: `build_session` accepts any non-empty `build_metrics["rid"]` and
  calls `reducer.establish_build` without requiring `http == 200` or
  `finished is True`. `all_good` never checks `build_http` or
  `build_finished`.
- Independent probe: a mocked `http=500`, `finished=False`, non-empty `rid`
  produced `context_sessions=['p0-s25-s00000']` and `fatal_errors=[]`.
- Acceptance impact: a failed build response can enter the durable/warm
  scheduler and, if later trace events exist, is not intrinsically prevented
  from satisfying the final PASS conditions. This violates the explicit
  missing/build-failure fail-closed requirement.

### F-2 — BLOCKING: late tailer errors can be omitted from final PASS

- Location: `p0_session_barrier_vehicle.py:941-967` and
  `:678-701`.
- Evidence: the scheduler reports a tailer error only for sessions still in
  `barrier_pending` or `ready_to_warm`; once the last warm future is removed,
  an error in `tailer.error` does not itself enter `fatal_errors`. The final
  `all_good` expression checks `fatal_errors` and reducer errors, but not
  `tailer.error`.
- Independent probe: a custom tailer injected a valid restore, then set
  `error='late malformed JSONL'`; `_run_warm_scheduler` returned with
  `fatal_errors=[]`, and `_write_bundle` independently produced verdict
  `PASS` for the otherwise complete one-session bundle.
- Acceptance impact: a malformed/truncated terminal trace can occur after the
  final readiness wait and still be reported as P0 PASS. Tailer errors must be
  terminal for the entire run, including after all warm futures complete.

### F-3 — BLOCKING: missing warm response ID is accepted

- Location: `p0_session_barrier_vehicle.py:900-911` and
  `:678-691`.
- Evidence: `warm_session` records `warm_metrics` regardless of whether
  `warm_metrics["rid"]` is present. Final PASS checks `warm_http == 200` and
  `warm_finished`, but never requires a non-empty `warm_rid` or
  `rid_source == 'response.id'`.
- Independent probe: a mocked `http=200`, `finished=True`, `rid=None` warm
  response produced no fatal error and retained `warm_rid=None` while the
  reducer accepted a restore-success path.
- Acceptance impact: the client-side warm identity contract is weakened and a
  warm result can be accepted without an independently correlated response
  request ID. The prior contract states that missing response IDs prevent the
  session from proceeding.

### F-4 — BLOCKING: vehicle warm marker can overwrite causal product order

- Location: `Reducer.ingest` at `p0_session_barrier_vehicle.py:282-288`,
  `record_warm_request` at `:323-341`, and call site `:906`.
- Evidence: every `warm_lookup_start`/`warm_request` sets
  `state["warm_order"]` instead of preserving the first product lookup order.
  The vehicle calls `record_warm_request` only after `post_chat` has returned;
  a product `warm_lookup_start` and `restore_outcome` can therefore already
  be observed before this synthetic marker.
- Independent probe: with product `warm_lookup_start` followed by successful
  `restore_outcome`, `restore_ready` was `True`; after
  `record_warm_request(..., None)`, `warm_order=8` and `restore_order=7`, so
  `restore_ready` became `False`.
- Acceptance impact: a valid live restore can be converted into a watchdog
  failure/`NOT_VERIFIED` solely due to event-tailer and HTTP-response timing.
  The accepted causal order must use the first actual warm lookup/request and
  must not let a late client bookkeeping event move it after restore.

### F-5 — BLOCKING: conflicting exact identities can pass `ready_for_warm`

- Location: `Reducer.ingest` at `p0_session_barrier_vehicle.py:241-245` and
  readiness at `:343-354`.
- Evidence: `identities` records `(session_id, build_rid, node_id,
  final_kv_hash)`, but only a build-RID mismatch sets `invalid_join`. A second
  node/hash tuple with the same build RID leaves `invalid_join=False`, and
  `ready_for_warm` does not require `len(identities) == 1`.
- Independent probe: build identity `(n1,h1)` followed by KV/Mamba/barriers
  for `(n2,h2)` yielded `ready_for_warm=True`, `identity_count=2`,
  `invalid_join=False`, and no reducer errors.
- Acceptance impact: warm can be submitted using mixed evidence from different
  exact identities. Although the later `exact_identity` check blocks that row
  from final PASS, the warm gate itself is no longer exact and violates the
  authoritative rule that a changed node/hash identity invalidates the
  session rather than relying on last-write-wins or a late final-row rejection.

## Requirement review

| Requirement | Result | Evidence |
|---|---|---|
| Build phase does not wait on barriers and can submit all planned sessions | PASS structurally | `_run_build_phase` only builds/promotes response IDs; focused fixture observed 3/3 build calls and `ready_checks == 0`. |
| Warm is gated by exact KV + Mamba + durability + residency | REJECT | Nominal predicate is present at `:343-354`, but F-4 and F-5 show causal-order and exact-identity boundary failures. |
| Active warm-worker upper bound | PASS for frozen values | Separate pool uses `max_workers=args.build_workers` (`:928-930`); frozen validation keeps both active/build workers at 8. |
| Watchdog and restore timeout fail closed | REJECT | Nominal timeout paths exist (`:968-991`), but F-2 allows a late terminal tailer error to escape final accounting. |
| Tailer errors fail closed | REJECT | F-2; final verdict has no direct `tailer.error` terminal check. |
| Missing/build failure fail closed | REJECT | F-1. |
| Final bundle planned-session accounting | REJECT | Planned rows and missing sessions are emitted, but F-1/F-2/F-3 can make invalid runs PASS-shaped. |
| Frozen validation and no warm-before-barrier relaxation | PASS structurally / gate remains rejected | `_validate_frozen` enforces S=25, active/build-workers=8, 55K, RH off; no fixed sleep is used. |

## Evidence executed

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-vehicle-fix1 python3 test_p0_trace_context_v4.py` — **PASS** (`P0 trace-context V4.3 focused checks: PASS`).
- `python3 -m py_compile p0_session_barrier_vehicle.py test_p0_trace_context_v4.py` — **PASS**.
- Independent `ast.parse` over both reviewed files — **PASS**.
- `git diff --no-index --check /dev/null` over both untracked reviewed files — **PASS** (no whitespace diagnostics; expected difference status suppressed).
- Independent build HTTP failure probe — **FAIL** for the required invariant; a 500/unfinished response with an ID was admitted with no fatal error.
- Independent late tailer-error probe — **FAIL** for the required invariant; final bundle verdict was `PASS` after a late malformed-line error.
- Independent missing warm response-ID probe — **FAIL** for the required invariant; 200/finished with `rid=None` proceeded.
- Independent warm-order probe — **FAIL** for causal stability; valid restore readiness became false after the synthetic marker.
- Independent conflicting-identity probe — **FAIL** for exact-join readiness; mixed node/hash evidence returned `ready_for_warm=True`.
- No engine, launcher, remote host, or live endpoint was started.

## Followups

- Fresh coder Task ID: make build admission require successful HTTP/finished
  response semantics and make final accounting require the complete build row.
- Fresh coder Task ID: make `tailer.error` a terminal run-level failure checked
  immediately before bundle verdict, including after all warm futures drain.
- Fresh coder Task ID: require a non-empty warm response ID from `response.id`
  before/after warm admission and final PASS.
- Fresh coder Task ID: preserve the first actual warm lookup order and prevent
  synthetic bookkeeping from moving it after restore evidence.
- Fresh coder Task ID: invalidate a session on any changed exact identity before
  `ready_for_warm`; add focused regressions for all five boundaries.
- After a fresh implementation task, rerun the focused fixture and obtain a
  new independent review before any remote S=25 rerun. The supplied live
  FIX2 evidence remains `NOT_VERIFIED` and does not become acceptance evidence.

## Open issues

1. FIX1 resolves the original eight-worker scheduling deadlock in the tested
   control flow, but the durable/warm gate is not safe to accept.
2. No live rerun was performed under this review, by authorization.
3. The dirty aggregate worktree has no task-specific commit boundary; broad
   authorship attribution remains a process caveat.

done
