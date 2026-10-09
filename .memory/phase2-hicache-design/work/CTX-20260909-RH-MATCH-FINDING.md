# CTX-20260909-RH-MATCH-FINDING

status: done
task_id: T3060-RH-CONTEXT-UPDATE-20260909
orchestration_epoch: 20260909-rh-ab45
role: context-manager

## Scope and provenance

This artifact records the latest 3060 Ready Horizon (RH) finding and current
frontier. It is a context update only. No product code, gate acceptance file,
ledger, plan, or root context file was changed.

Primary evidence:

- `OPS3060-DEPLOY-F629-RH-ON-20260909.md`
- `TEST3060-RH-FINAL-ON-TRACE-20260909.md`
- `TEST3060-RH-FINAL-OFF-TRACE-20260909.md`
- `DBG-20260909-RH-NO-STAGING.md`
- `ARCH3060-RH-ARCH-20260909.md`

## Observed facts

- Branch `3060-12g-qwen35-4b` revision `f629d4e2c19eb74571b4154438fd651ce24ff53b`
  was deployed with RH enabled. The service remained healthy at `/health`
  HTTP 200 during the final RH-ON replay.
- The final bounded RH-ON replay completed all five requests (`x`, `y`, `z`,
  `w`, `q`) with HTTP 200. This is a completion result, not a causal RH
  performance attribution.
- Every RH-ON request emitted only
  `rh_preadmission.v1 decision=exclude reason=no_restore_potential`.
  No RH-ON request emitted a joinable `decision=issue`; no non-null issue
  attempt ID, `ready_stage.v2`, `rh_ready_host.v1`, or test-RID
  `rh_admission.v2` join was available.
- RH-ON `restore_state` was `null` and `staging_eligible` was `false` in the
  observed RH decision records. The requested RH ready-host rate remains
  `not_computable`/undefined because the eligible denominator is unavailable;
  missing evidence is not treated as zero.
- The RH-OFF comparison completed 2/5 requests with HTTP 200 and had 3/5
  bounded timeouts. The ON/OFF completion difference is an observed comparison
  only; the ON trace did not contain the required RH/storage joins for causal
  attribution.
- Source/runtime diagnosis records that direct request enqueue performs eager
  ordinary prefetch before the request reaches the waiting queue, while the
  RH pass runs before waiting-request initialization (`init_next_round_input`).
  The source order therefore leaves the RH pass seeing a request after the
  ordinary prefetch state transition rather than at a clean pre-match point.

## Interpretation (explicitly non-final)

- The ordering above is the current likely pre-match eligibility defect: RH
  may exclude requests before it can perform the intended pre-admission match
  and staging decision. This is a likely diagnosis, not an accepted
  implementation or final root-cause verdict.
- The trace also contains real host-capacity constraints and incomplete RH
  observability. These remain separate from the likely ordering defect and
  must not be collapsed into a claim that RH caused the HTTP result change.

## Current frontier

1. Design and implement a safe pre-RH match-preparation path that preserves
   single-issue/claim identity, avoids duplicate I/O or reservations, and
   keeps RH-OFF behavior unchanged.
2. Obtain independent review of that design and implementation, including the
   required pattern/novel-mechanism records if the scheduling authority or
   boundary changes.
3. Deploy the reviewed revision to the authorized 3060 runtime.
4. Replay the same five-request trace with RH ON and the corresponding control
   comparison, preserving missing telemetry as missing; then reassess whether
   the RH ready-host rate is computable.

All design, implementation, deployment, replay, and acceptance work requires
a fresh Task ID. This context task does not authorize any of those actions.

## Stale or superseded context

The earlier phase2 snapshot classified RH as a deferred known issue and froze
the 3090 production baseline with RH OFF. That remains the 3090 baseline. The
facts above update only the later authorized 3060 RH investigation and do not
reopen the 3090 production state.

artifacts: `CTX-20260909-RH-MATCH-FINDING.md`
evidence: deployment pin/health report; final RH-ON and RH-OFF traces; source-order diagnosis; architecture frontier report
summary: f629 is deployed and healthy; RH-ON is 5/5 HTTP 200 but all RH decisions exclude/no_restore_potential with restore_state=null and staging_eligible=false; RH ready-host rate is not computable; pre-RH match preparation is the likely next defect boundary
followups: fresh Task ID for safe pre-RH match-preparation design/implementation, independent review, reviewed deploy, and same-trace replay
open_issues: likely ordering defect is not yet fixed or independently accepted; RH/storage join telemetry remains incomplete; host-capacity effects remain a separate observed constraint
