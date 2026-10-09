ENTRY: ACCEPT

# REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX2

- Task ID: `REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX2`
- Orchestration epoch: `2026-09-08-P0`
- Role: `reviewer`
- Invocation status: **done**
- Admission: **ACCEPT**
- Gate verdict: **REJECT**

## Artifacts

- Gate: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-VEHICLE-BARRIER-SCHEDULER-FIX2.md`
- Reviewed vehicle: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- Reviewed fixture: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

## Evidence

- Focused fixture — **PASS**.
- `py_compile` — **PASS** for vehicle and fixture.
- AST parsing — **PASS** for vehicle and fixture.
- Untracked-file whitespace checks — **PASS**.
- Independent probes closed all five FIX1 blockers: build response admission
  and final accounting, post-future tailer errors, warm response IDs, stable
  product warm order, and conflicting exact identities.
- Independent scheduler probe reproduced the original two-phase deadlock
  regression and no premature client warm in the nominal path.
- Independent additional probe found a blocking early-product-warm boundary:
  `lookup_before_barrier=True` did not prevent `ready_for_warm()`, and the
  scheduler submitted a warm after later barriers.
- No remote or live execution was performed.

## Summary

FIX2 correctly closes the five blockers from FIX1 in the tested repair paths.
However, the gate cannot accept the scheduler because a product warm event
that arrives before exact durability/residency barriers is recorded as
`lookup_before_barrier` but is not checked by `ready_for_warm()`. After the
barriers arrive, `_run_warm_scheduler` can submit a warm request anyway. This
violates the required causal order and can perturb the next live S=25 run even
though final accounting later rejects the row.

See the gate for exact lines, independent probe evidence, acceptance impact,
and the required fresh Task ID repair.

## Followups

- Fresh coder Task ID: invalidate warm readiness when prior product warm
  evidence was observed before the exact barriers, and add a scheduler-level
  focused regression.
- Fresh independent reviewer Task ID: rerun the gate after the repair.
- Keep live S=25 blocked until the fresh gate is accepted.

## Open issues

1. Blocking F-6 remains open: warm-before-exact-barrier product evidence can
   still lead to a client warm submission.
2. Supplied S=25 FIX2 live evidence remains `NOT_VERIFIED`; no runtime PASS is
   claimed.
3. The reviewed vehicle and fixture are untracked in the aggregate checkout;
   no task-specific revision boundary exists.

done
