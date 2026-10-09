status: done

artifacts:
- This report: `.memory/phase2-hicache-design/work/P0-B-EVENT-CONTRACT-20260911-R101.md`

evidence:
- Read-only producer inventory for `p0_durable.v3`, `host_alloc.v1`,
  `rh_ready_host.v1`, wait/wake/retry/finalization/generation/FIFO/timing.
- No tests, remote, product/test/gate/storage/Git changes.

summary:
- verdict: NOT_VERIFIED
- Producers emit useful attempt/cache/generation/timing/durability/finalization
  data, but no non-forgeable FIFO predecessor/wait lineage or profile/source-build
  binding across the required event family.
- Missing fields: `wait_id`, `predecessor_wait_id`, predecessor ticket/event/state,
  wake-event ID, consistent attempt lineage, profile_id/source-build across
  HOST_ALLOC/READY, cache/generation in READY, and complete deadline semantics.
- `p0_durable.v3` supplies process/run/session/build only when marker-gated trace
  context is valid; otherwise it falls back to v2.
- A third reducer cannot make these joins non-forgeable from current output.

followups:
- Treat missing joins as an explicit NOT_VERIFIED blocker.
- Minimal producer observation change is documented in the full report; do not
  weaken the oracle or infer missing fields.

open_issues:
- No authoritative existing event source currently closes the required joins.
