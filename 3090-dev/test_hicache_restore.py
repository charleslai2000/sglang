"""P2-1 M1b: restore retry state machine (design §2.2 transition table).

The state machine is a pure module (scheduler_components/hicache_restore.py,
torch-free) so the full transition table is testable without the engine:
every row T1-T14 of the design table, the WAIT-wake predicate semantics
(capacity_fits / genuine_miss), the wait_reason mapping, and the defensive
no-ops for events applied to unexpected states.
"""

import importlib.util
import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PYTHON_DIR = os.path.join(_REPO_ROOT, "python")
sys.path.insert(0, _PYTHON_DIR)

# The pure state-machine module imports only stdlib, so it is loaded by file
# path without pulling in the (torch-dependent) sglang package __init__.
_SPEC = importlib.util.spec_from_file_location(
    "hicache_restore_under_test",
    os.path.join(
        _PYTHON_DIR,
        "sglang",
        "srt",
        "managers",
        "scheduler_components",
        "hicache_restore.py",
    ),
)
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MOD
_SPEC.loader.exec_module(_MOD)

RestoreDecision = _MOD.RestoreDecision
RestoreEvent = _MOD.RestoreEvent
RestoreState = _MOD.RestoreState
RestoreWaitReason = _MOD.RestoreWaitReason
capacity_wake_applies = _MOD.capacity_wake_applies
next_restore = _MOD.next_restore
too_short_wait_armed = _MOD.too_short_wait_armed
wait_clock_next = _MOD.wait_clock_next
wait_reason_for = _MOD.wait_reason_for

NONE = RestoreState.NONE
WAIT = RestoreState.WAIT_CAPACITY
RESTORING = RestoreState.RESTORING
READY = RestoreState.READY


class RestoreStateMachineTests(unittest.TestCase):
    """T1-T14 transition rows of the design §2.2 table."""

    # -- T1: NONE -> RESTORING (prefetch issued) --------------------------

    def test_t1_issue_lands_restoring(self):
        state, decision = next_restore(NONE, RestoreEvent.PREFETCH_ISSUED)
        self.assertIs(state, RESTORING)
        self.assertIs(decision, RestoreDecision.NONE)

    def test_t1_reissue_from_wait_lands_restoring(self):
        # The T11/T12 re-issue completion: WAIT -> RESTORING via the same event.
        state, decision = next_restore(WAIT, RestoreEvent.PREFETCH_ISSUED)
        self.assertIs(state, RESTORING)
        self.assertIs(decision, RestoreDecision.NONE)

    # -- T2-T5, T10: capacity-type declines land WAIT_CAPACITY -------------

    def test_t2_rate_limited_waits_for_prefetch_budget(self):
        state, decision = next_restore(NONE, RestoreEvent.DENIED_RATE)
        self.assertIs(state, WAIT)
        self.assertIs(decision, RestoreDecision.WAIT)
        self.assertIs(
            wait_reason_for(RestoreEvent.DENIED_RATE), RestoreWaitReason.PREFETCH_BUDGET
        )

    def test_t3_alloc_failed_waits_for_host_alloc(self):
        state, decision = next_restore(NONE, RestoreEvent.DENIED_ALLOC)
        self.assertIs(state, WAIT)
        self.assertIs(decision, RestoreDecision.WAIT)
        self.assertIs(
            wait_reason_for(RestoreEvent.DENIED_ALLOC), RestoreWaitReason.HOST_ALLOC
        )

    def test_t4_too_short_waits_for_revalidate(self):
        state, decision = next_restore(NONE, RestoreEvent.DENIED_SHORT)
        self.assertIs(state, WAIT)
        self.assertIs(decision, RestoreDecision.WAIT)
        self.assertIs(
            wait_reason_for(RestoreEvent.DENIED_SHORT), RestoreWaitReason.REVALIDATE
        )

    def test_t4_too_short_redecline_from_wait_stays_waiting(self):
        # A paced-retry re-decline stays WAIT: only a re-issue leg (wake)
        # makes the too-short judgment terminal.
        state, decision = next_restore(WAIT, RestoreEvent.DENIED_SHORT)
        self.assertIs(state, WAIT)
        self.assertIs(decision, RestoreDecision.WAIT)

    def test_t4_too_short_wait_requires_paced_retry(self):
        # The REVALIDATE wait is the device-match-decay bet, re-issuable
        # only by the paced retry. With the poll disabled (M2 default
        # hicache_storage_prefetch_retry_poll_interval=0) the first-time
        # too-short decline must not enter it: the wait has no wake source
        # and idles out the full T13 clock (the e13 K=1 t5 60s:
        # WAIT[REVALIDATE] with nothing to wake it).
        self.assertFalse(too_short_wait_armed(0))
        self.assertTrue(too_short_wait_armed(1))

    def test_rate_limited_wake_cycle_never_recomputes(self):
        # e13 denied_rate_limit semantics: a rate-limited rid is parked in
        # WAIT[PREFETCH_BUDGET] and woken by the T11 capacity predicate
        # when the budget frees -- woken restore, never abandonment.
        state = next_restore(NONE, RestoreEvent.DENIED_RATE)[0]
        self.assertIs(state, WAIT)
        self.assertIs(
            wait_reason_for(RestoreEvent.DENIED_RATE),
            RestoreWaitReason.PREFETCH_BUDGET,
        )
        state, decision = next_restore(
            state, RestoreEvent.CAPACITY_FITS, capacity_fits=True
        )
        self.assertIs(state, RESTORING)
        self.assertIs(decision, RestoreDecision.RETRY_PREFETCH)

    def test_denied_rate_never_degrades_to_recompute(self):
        # A rate-limit denial is a capacity denial: it must never emit
        # ADMIT_RECOMPUTE from any state (recompute is for misses T9 and
        # the T13 bound, never for a transient budget denial).
        for from_state in (NONE, WAIT, RESTORING, READY):
            state, decision = next_restore(from_state, RestoreEvent.DENIED_RATE)
            self.assertIs(state, WAIT, f"from {from_state}")
            self.assertIsNot(decision, RestoreDecision.ADMIT_RECOMPUTE, from_state)

    def test_wake_reissue_too_short_degrades_to_recompute(self):
        # T12 wake -> re-issued prefetch declined too-short must release
        # to recompute immediately, not idle out the old T13 clock in
        # WAIT[REVALIDATE] (the e12 residual: 60s waits after wake).
        state = next_restore(WAIT, RestoreEvent.FRONTIER_READY)[0]
        self.assertIs(state, RESTORING)
        state, decision = next_restore(state, RestoreEvent.DENIED_SHORT)
        self.assertIs(state, NONE)
        self.assertIs(decision, RestoreDecision.ADMIT_RECOMPUTE)

    def test_capacity_wake_reissue_too_short_degrades_to_recompute(self):
        # T11 capacity wake -> too-short re-issue: same terminal rule as
        # the T12 wake leg.
        state = next_restore(WAIT, RestoreEvent.CAPACITY_FITS, capacity_fits=True)[0]
        self.assertIs(state, RESTORING)
        state, decision = next_restore(state, RestoreEvent.DENIED_SHORT)
        self.assertIs(state, NONE)
        self.assertIs(decision, RestoreDecision.ADMIT_RECOMPUTE)

    def test_t5_gate_skip_waits_for_frontier(self):
        state, decision = next_restore(NONE, RestoreEvent.GATE_SKIP_FRONTIER)
        self.assertIs(state, WAIT)
        self.assertIs(decision, RestoreDecision.WAIT)
        self.assertIs(
            wait_reason_for(RestoreEvent.GATE_SKIP_FRONTIER),
            RestoreWaitReason.FRONTIER,
        )

    def test_t10_terminated_revoke_waits_for_prefetch_budget(self):
        state, decision = next_restore(RESTORING, RestoreEvent.REVOKED_TERMINATED)
        self.assertIs(state, WAIT)
        self.assertIs(decision, RestoreDecision.WAIT)
        self.assertIs(
            wait_reason_for(RestoreEvent.REVOKED_TERMINATED),
            RestoreWaitReason.PREFETCH_BUDGET,
        )

    # -- T6/T7: admission-time denies land WAIT[DEVICE_QUOTA] --------------

    def test_t6_admission_deny_waits_for_device_quota(self):
        state, decision = next_restore(NONE, RestoreEvent.ADMISSION_DENY)
        self.assertIs(state, WAIT)
        self.assertIs(decision, RestoreDecision.WAIT)
        self.assertIs(
            wait_reason_for(RestoreEvent.ADMISSION_DENY),
            RestoreWaitReason.DEVICE_QUOTA,
        )

    def test_t7_load_back_fail_waits_for_device_quota(self):
        # From READY (finalized prefetch, then denied at load-back) and NONE.
        for from_state in (READY, NONE):
            state, decision = next_restore(from_state, RestoreEvent.LOAD_BACK_FAIL)
            self.assertIs(state, WAIT)
            self.assertIs(decision, RestoreDecision.WAIT)
        self.assertIs(
            wait_reason_for(RestoreEvent.LOAD_BACK_FAIL),
            RestoreWaitReason.DEVICE_QUOTA,
        )

    # -- T8: finalize lands READY ------------------------------------------

    def test_t8_finalize_lands_ready(self):
        state, decision = next_restore(RESTORING, RestoreEvent.FINALIZED)
        self.assertIs(state, READY)
        self.assertIs(decision, RestoreDecision.NONE)

    def test_t8_finalize_from_unexpected_state_is_noop(self):
        # A finalize without a live RESTORING state is defensive no-op.
        state, decision = next_restore(NONE, RestoreEvent.FINALIZED)
        self.assertIs(state, NONE)
        self.assertIs(decision, RestoreDecision.NONE)

    # -- T9: genuine miss degrades to recompute (never waits) --------------

    def test_t9_revoked_miss_degrades_to_recompute(self):
        for from_state in (RESTORING, WAIT, READY, NONE):
            state, decision = next_restore(
                from_state, RestoreEvent.REVOKED_MISS, genuine_miss=True
            )
            self.assertIs(state, NONE, f"from {from_state}")
            self.assertIs(decision, RestoreDecision.ADMIT_RECOMPUTE)

    def test_t9_revoked_non_miss_is_capacity_wait(self):
        # genuine_miss=False (e.g. host staging shortfall): retryable.
        state, decision = next_restore(RESTORING, RestoreEvent.REVOKED_MISS)
        self.assertIs(state, WAIT)
        self.assertIs(decision, RestoreDecision.WAIT)
        self.assertIs(
            wait_reason_for(RestoreEvent.REVOKED_MISS, genuine_miss=False),
            RestoreWaitReason.HOST_ALLOC,
        )
        # A genuine miss carries no wait reason.
        self.assertIsNone(
            wait_reason_for(RestoreEvent.REVOKED_MISS, genuine_miss=True)
        )

    # -- T11: per-pass capacity wake ---------------------------------------

    def test_t11_capacity_fits_retries_prefetch(self):
        state, decision = next_restore(
            WAIT, RestoreEvent.CAPACITY_FITS, capacity_fits=True
        )
        self.assertIs(state, RESTORING)
        self.assertIs(decision, RestoreDecision.RETRY_PREFETCH)

    def test_t11_capacity_not_fits_stays_waiting(self):
        state, decision = next_restore(
            WAIT, RestoreEvent.CAPACITY_FITS, capacity_fits=False
        )
        self.assertIs(state, WAIT)
        self.assertIs(decision, RestoreDecision.NONE)

    def test_t11_capacity_fits_from_unexpected_state_is_noop(self):
        state, decision = next_restore(
            RESTORING, RestoreEvent.CAPACITY_FITS, capacity_fits=True
        )
        self.assertIs(state, RESTORING)
        self.assertIs(decision, RestoreDecision.NONE)

    # -- T12: frontier-ACK wake --------------------------------------------

    def test_t12_frontier_ready_retries_prefetch(self):
        state, decision = next_restore(WAIT, RestoreEvent.FRONTIER_READY)
        self.assertIs(state, RESTORING)
        self.assertIs(decision, RestoreDecision.RETRY_PREFETCH)

    def test_t12_frontier_ready_from_unexpected_state_is_noop(self):
        state, decision = next_restore(NONE, RestoreEvent.FRONTIER_READY)
        self.assertIs(state, NONE)
        self.assertIs(decision, RestoreDecision.NONE)

    # -- T13: timeout degrades to recompute; RESTORING never timed out ------

    def test_t13_timeout_degrades_to_recompute(self):
        state, decision = next_restore(WAIT, RestoreEvent.TIMEOUT)
        self.assertIs(state, NONE)
        self.assertIs(decision, RestoreDecision.ADMIT_RECOMPUTE)

    def test_t13_timeout_does_not_kill_restoring(self):
        # Design §2.5-3: wait_complete keeps in-flight prefetches running.
        state, decision = next_restore(RESTORING, RestoreEvent.TIMEOUT)
        self.assertIs(state, RESTORING)
        self.assertIs(decision, RestoreDecision.NONE)

    # -- T14: abort clears state -------------------------------------------

    def test_t14_abort_clears_any_state(self):
        for from_state in (NONE, WAIT, RESTORING, READY):
            state, decision = next_restore(from_state, RestoreEvent.ABORT)
            self.assertIs(state, NONE)
            self.assertIs(decision, RestoreDecision.NONE)

    # -- lifecycle round trips ---------------------------------------------

    def test_full_retry_cycle(self):
        # The C1/C2 causal chain (design §0.2), now retried: deny -> wait ->
        # capacity frees -> re-issue -> finalize -> ready.
        state = next_restore(NONE, RestoreEvent.DENIED_RATE)[0]
        self.assertIs(state, WAIT)
        state, decision = next_restore(state, RestoreEvent.CAPACITY_FITS, capacity_fits=True)
        self.assertIs(state, RESTORING)
        self.assertIs(decision, RestoreDecision.RETRY_PREFETCH)
        state, decision = next_restore(state, RestoreEvent.PREFETCH_ISSUED)
        self.assertIs(state, RESTORING)
        state, decision = next_restore(state, RestoreEvent.FINALIZED)
        self.assertIs(state, READY)

    def test_genuine_miss_chain_never_waits(self):
        # T9 after a re-issue: a true miss degrades to recompute even from
        # a WAIT-derived RESTORING.
        state = next_restore(WAIT, RestoreEvent.CAPACITY_FITS, capacity_fits=True)[0]
        state, decision = next_restore(state, RestoreEvent.REVOKED_MISS, genuine_miss=True)
        self.assertIs(state, NONE)
        self.assertIs(decision, RestoreDecision.ADMIT_RECOMPUTE)

    def test_frontier_wake_miss_degrades_to_recompute(self):
        # T12 wake -> genuine miss: immediate recompute, never a wait.
        state = next_restore(WAIT, RestoreEvent.FRONTIER_READY)[0]
        self.assertIs(state, RESTORING)
        state, decision = next_restore(state, RestoreEvent.REVOKED_MISS, genuine_miss=True)
        self.assertIs(state, NONE)
        self.assertIs(decision, RestoreDecision.ADMIT_RECOMPUTE)


class RestoreWaitReasonMappingTests(unittest.TestCase):
    """wait_reason_for covers exactly the events that land in WAIT_CAPACITY."""

    def test_wait_events_have_reasons(self):
        for event in (
            RestoreEvent.DENIED_RATE,
            RestoreEvent.DENIED_ALLOC,
            RestoreEvent.DENIED_SHORT,
            RestoreEvent.GATE_SKIP_FRONTIER,
            RestoreEvent.ADMISSION_DENY,
            RestoreEvent.LOAD_BACK_FAIL,
            RestoreEvent.REVOKED_TERMINATED,
        ):
            self.assertIsNotNone(wait_reason_for(event), event)

    def test_non_wait_events_have_no_reason(self):
        for event in (
            RestoreEvent.PREFETCH_ISSUED,
            RestoreEvent.FINALIZED,
            RestoreEvent.CAPACITY_FITS,
            RestoreEvent.FRONTIER_READY,
            RestoreEvent.TIMEOUT,
            RestoreEvent.ABORT,
        ):
            self.assertIsNone(wait_reason_for(event), event)


class RestoreWaitClockTests(unittest.TestCase):
    """wait_clock_next: the T13 timeout base is armed once per restore
    episode and never re-armed by a WAIT re-entry. Re-arming on re-entry is
    what turned the capacity loop into an unbounded one: every per-pass
    re-issued prefetch that was declined reset state_ts, so the timeout
    never fired (tester e10: 834K cause=capacity retries, restore_recompute
    cause=timeout 0)."""

    def test_clock_armed_at_first_wait_entry(self):
        self.assertEqual(wait_clock_next(NONE, WAIT, 0.0, now=100.0), 100.0)

    def test_clock_kept_on_wait_reentry(self):
        # The loop: a re-issued prefetch declined straight back into WAIT.
        self.assertEqual(wait_clock_next(WAIT, WAIT, state_ts=10.0, now=100.0), 10.0)

    def test_clock_kept_across_reissue_leg(self):
        # WAIT -> RESTORING (T11/T12 re-issue) keeps the clock...
        self.assertEqual(
            wait_clock_next(WAIT, RESTORING, state_ts=10.0, now=100.0), 10.0
        )
        # ...and a decline from that leg re-entering WAIT still keeps it.
        self.assertEqual(
            wait_clock_next(RESTORING, WAIT, state_ts=10.0, now=100.0), 10.0
        )

    def test_clock_cleared_on_episode_end(self):
        for end_state in (READY, NONE):
            self.assertEqual(wait_clock_next(WAIT, end_state, 10.0, now=100.0), 0.0)

    def test_clock_cleared_on_wake_too_short_terminal(self):
        # The too-short terminal degradation ends the episode: the clock
        # clears, so the request is released immediately, not after the
        # remaining T13 wait.
        ts = wait_clock_next(NONE, WAIT, 0.0, now=100.0)
        ts = wait_clock_next(WAIT, RESTORING, ts, now=105.0)
        self.assertEqual(ts, 100.0)
        state, decision = next_restore(RESTORING, RestoreEvent.DENIED_SHORT)
        self.assertIs(state, NONE)
        self.assertIs(decision, RestoreDecision.ADMIT_RECOMPUTE)
        self.assertEqual(wait_clock_next(RESTORING, NONE, ts, now=105.0), 0.0)

    def test_clock_zero_on_fresh_restoring(self):
        # A fresh NONE -> RESTORING (T1) was never armed; the clock stays 0
        # so a later capacity deny arms a fresh episode.
        self.assertEqual(wait_clock_next(NONE, RESTORING, 0.0, now=100.0), 0.0)

    def test_clock_rearmed_after_episode_end(self):
        # READY -> WAIT (T7 load-back fail) is a new episode: fresh clock.
        self.assertEqual(wait_clock_next(READY, WAIT, 0.0, now=100.0), 100.0)

    def test_timeout_escape_after_loop(self):
        # End-to-end: the observed capacity loop (WAIT -> T11 re-issue ->
        # decline -> WAIT) now leaves the clock untouched, so T13 fires.
        ts = wait_clock_next(NONE, WAIT, 0.0, now=1.0)
        for _ in range(10):
            ts = wait_clock_next(WAIT, RESTORING, ts, now=ts + 1.0)
            ts = wait_clock_next(RESTORING, WAIT, ts, now=ts + 1.0)
        self.assertEqual(ts, 1.0)
        state, decision = next_restore(WAIT, RestoreEvent.TIMEOUT)
        self.assertIs(state, NONE)
        self.assertIs(decision, RestoreDecision.ADMIT_RECOMPUTE)


class CapacityWakeApplicabilityTests(unittest.TestCase):
    """capacity_wake_applies: the per-pass T11 wake only fires for reasons
    the capacity predicate can validate. REVALIDATE (suffix still below the
    prefetch threshold) and HOST_ALLOC (staging alloc still failing) are
    not capacity-testable: waking them re-issues a prefetch declined
    identically every pass (the capacity loop, tester e10)."""

    def test_capacity_testable_reasons_are_woken(self):
        for reason in (
            RestoreWaitReason.DEVICE_QUOTA,
            RestoreWaitReason.PREFETCH_BUDGET,
            RestoreWaitReason.FRONTIER,
        ):
            self.assertTrue(capacity_wake_applies(reason), reason)

    def test_non_capacity_reasons_are_not_woken(self):
        for reason in (RestoreWaitReason.REVALIDATE, RestoreWaitReason.HOST_ALLOC):
            self.assertFalse(capacity_wake_applies(reason), reason)

    def test_no_reason_is_not_woken(self):
        self.assertFalse(capacity_wake_applies(None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
