status: done

artifacts:
- This report: `.memory/phase2-hicache-design/work/P0-B-FAILURE-TRIAGE-20260911-R33.md`
- R32 raw transcripts under `work/R32-artifacts/`.

evidence:
- Exact HOST_ALLOC failures:
  1. FIFO test expected `None` but observed the next waiter `second` after
     failed-first rotation; this is a contract/assertion mismatch candidate.
  2. waiter-departure fixture lacks `hicache_restore_state_ts`.
- Targeted failure: `test_drain_reentry.py` fake controller lacks
  `speculative_release_epoch`.
- Focused failures are fixture/API-shape gaps: missing `components`,
  `_t38c_residency_lock`, and `_host_allocability_telemetry_seq` in object-new
  cache harnesses.
- No failure proves a live HOST_ALLOC defect; no live driver or correlated trace
  exists.

summary:
- Most R32 failures are safe test-only fixture completion candidates.
- The FIFO assertion requires an explicit contract adjudication: current
  `record_attempt_result()` rotates the failed RID and `choose()` scans the next
  eligible RID, making `second` consistent with current implementation.
- P0-B remains NOT_VERIFIED independently of these unit failures.

followups:
- Fresh coder may apply only the listed fixture initializations, preserving
  production behavior and assertions.
- Do not change the FIFO production arbiter without a separate decision.
- Re-run focused tests after fixture corrections, but still require a separate
  correlated live chain for P0-B closure.

open_issues:
- Exact FIFO contract semantics remain open.
- No complete live liveness trace.
