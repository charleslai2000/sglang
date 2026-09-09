# Gate Review — RH SPEC_BUDGET re-trigger fix

Verdict: **PASS (narrow implementation gate)**

Reviewed scope:

- `python/sglang/srt/managers/scheduler.py`
- `3090-dev/test_ready_horizon_unit.py`

The fix records the speculative cursor after the prefetch issue result and uses it
for SPEC_BUDGET parks. It does not alter NO_L3/NO_HEADROOM cursor semantics and does
not turn physical-only capacity exhaustion into speculative negative-cache state.

Evidence:

- independent logical reviewer result: PASS, invocation
  `INV-20260910-REVIEW-RH-SPEC-BUDGET-RH-R4` (tool-free due approval-gated child
  runtime; exact live acceptance explicitly excluded);
- remote focused tests: 2 passed, 70 deselected;
- full Ready Horizon file: 66 passed, 6 existing fixture/API expectation failures;
- report: `work/REVIEW3060-RH-SPEC-BUDGET-RETRIGGER-R3-20260910.md`;
- test report: `work/TEST3060-RH-SPEC-BUDGET-RETRIGGER-R2-20260910.md`.

Blocking conditions for broader acceptance remain: the six broad-suite failures and
the required live RH OFF/ON blocker-horizon rerun. This gate authorizes only the
narrow code commit/deployment step, not a claim that RH is production-ready.
