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
from queue import Queue
from types import SimpleNamespace

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
DEMAND_RESTORE_MAX_INFLIGHT = _MOD.DEMAND_RESTORE_MAX_INFLIGHT
backup_wait_applies = _MOD.backup_wait_applies
backup_wake_applies = _MOD.backup_wake_applies
capacity_wake_applies = _MOD.capacity_wake_applies
demand_restore_available = _MOD.demand_restore_available
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

    # -- T15: backup-in-flight partial parks on the backup-completion wait --

    def test_t15_backup_pending_waits(self):
        # The lookup found the chain mid-backup (partial hit, L3 write in
        # flight): park in WAIT[BACKUP_PENDING] -- never a recompute. The
        # scheduler registers the M2 frontier waiter; the ack drain or the
        # per-pass in-flight predicate wakes it for one re-lookup.
        state, decision = next_restore(RESTORING, RestoreEvent.BACKUP_PENDING)
        self.assertIs(state, WAIT)
        self.assertIs(decision, RestoreDecision.WAIT)
        self.assertIs(
            wait_reason_for(RestoreEvent.BACKUP_PENDING),
            RestoreWaitReason.BACKUP_PENDING,
        )

    def test_t15_backup_pending_is_capacity_wait_not_recompute(self):
        # A backup-in-flight partial is a capacity-type wait: the backup
        # completes and the re-lookup serves the full chain. Recompute is
        # for genuine misses (T9) and the T13 bound only.
        state, decision = next_restore(RESTORING, RestoreEvent.BACKUP_PENDING)
        self.assertIs(state, WAIT)
        self.assertIsNot(decision, RestoreDecision.ADMIT_RECOMPUTE)

    def test_t15_wake_cycle_reissues_lookup_once(self):
        # Both wake sources re-issue the lookup exactly once: the T11
        # capacity wake (the ack drain flips the in-flight predicate) and
        # the T12 frontier-ACK wake (the anchor's promotion).
        state = next_restore(RESTORING, RestoreEvent.BACKUP_PENDING)[0]
        state, decision = next_restore(
            state, RestoreEvent.CAPACITY_FITS, capacity_fits=True
        )
        self.assertIs(state, RESTORING)
        self.assertIs(decision, RestoreDecision.RETRY_PREFETCH)
        state = next_restore(RESTORING, RestoreEvent.BACKUP_PENDING)[0]
        state, decision = next_restore(state, RestoreEvent.FRONTIER_READY)
        self.assertIs(state, RESTORING)
        self.assertIs(decision, RestoreDecision.RETRY_PREFETCH)

    def test_t15_repark_after_early_wake(self):
        # The anchor's ack can wake the wait while a deeper node's write is
        # still in flight: the re-lookup finds the chain still partial and
        # parks again (T15). The wait is event-rearmed, never a per-pass
        # poll -- the T11 predicate stays False while a write is in flight.
        state = next_restore(RESTORING, RestoreEvent.BACKUP_PENDING)[0]
        self.assertIs(state, WAIT)
        state = next_restore(state, RestoreEvent.FRONTIER_READY)[0]
        self.assertIs(state, RESTORING)
        state, decision = next_restore(state, RestoreEvent.BACKUP_PENDING)
        self.assertIs(state, WAIT)
        self.assertIs(decision, RestoreDecision.WAIT)

    def test_t15_timeout_still_bounds_the_wait(self):
        # The backup wait is a WAIT_CAPACITY: T13 still degrades to
        # recompute, so a chain whose backup never completes (write failed,
        # node evicted) cannot hang the request -- the no-deadlock bound.
        state = next_restore(RESTORING, RestoreEvent.BACKUP_PENDING)[0]
        state, decision = next_restore(state, RestoreEvent.TIMEOUT)
        self.assertIs(state, NONE)
        self.assertIs(decision, RestoreDecision.ADMIT_RECOMPUTE)

    def test_t15_miss_after_wake_still_recomputes(self):
        # T15 wait -> wake -> re-lookup finds a genuine miss (the chain was
        # evicted from L3 while waiting): recompute immediately, never
        # re-wait. Quota deny != recompute decision, but a miss IS one.
        state = next_restore(RESTORING, RestoreEvent.BACKUP_PENDING)[0]
        state = next_restore(
            state, RestoreEvent.CAPACITY_FITS, capacity_fits=True
        )[0]
        state, decision = next_restore(
            state, RestoreEvent.REVOKED_MISS, genuine_miss=True
        )
        self.assertIs(state, NONE)
        self.assertIs(decision, RestoreDecision.ADMIT_RECOMPUTE)

    def test_t15_clock_armed_like_any_wait(self):
        # The T13 base is armed at the T15 entry and kept across the wake
        # re-issue leg, exactly like the other capacity waits (a re-armed
        # clock would let the backup wait evade the T13 bound).
        ts = wait_clock_next(NONE, WAIT, 0.0, now=100.0)
        self.assertEqual(ts, 100.0)
        ts = wait_clock_next(WAIT, RESTORING, ts, now=105.0)
        self.assertEqual(ts, 100.0)

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
            RestoreEvent.BACKUP_PENDING,
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
            RestoreWaitReason.BACKUP_PENDING,
        ):
            self.assertTrue(capacity_wake_applies(reason), reason)

    def test_non_capacity_reasons_are_not_woken(self):
        for reason in (RestoreWaitReason.REVALIDATE, RestoreWaitReason.HOST_ALLOC):
            self.assertFalse(capacity_wake_applies(reason), reason)

    def test_no_reason_is_not_woken(self):
        self.assertFalse(capacity_wake_applies(None))


class BackupWaitAppliesTests(unittest.TestCase):
    """backup_wait_applies: the T15 park fires only for a PARTIAL hit (not
    a zero hit, not a full hit) whose chain backup pipeline is targeted to
    cover the request's end (backup_target_frontier >= requested_pages)
    while the durable frontier is still behind it.

    A zero-hit span is never parked: it may simply never have been written
    (a fresh suffix recomputes), and parking would idle out the T13 clock
    for no event. A partial whose pipeline stops short of the request end
    (chain growth, a dropped-without-backup tail, a sibling chain's write)
    is never parked either: the wake could never serve the full hit, so
    the current restore-or-recompute behavior applies unchanged.
    """

    def test_partial_hit_with_pipeline_covering_request_parks(self):
        # durable=[0..6000) partially hit; the in-flight pipeline is
        # targeted to the request's end (20000): park, wake serves full hit.
        self.assertTrue(
            backup_wait_applies(
                6000, 20000, durable_frontier=6000, backup_target_frontier=20000
            )
        )

    def test_zero_hit_never_parks(self):
        self.assertFalse(
            backup_wait_applies(
                0, 20000, durable_frontier=0, backup_target_frontier=20000
            )
        )

    def test_full_hit_never_parks(self):
        self.assertFalse(
            backup_wait_applies(
                20000, 20000, durable_frontier=20000, backup_target_frontier=20000
            )
        )

    def test_pipeline_stops_short_of_request_end_never_parks(self):
        # The counter-example: durable=[0..6000), missing=[6000..20000),
        # in-flight write only to [6000..7000): backup_target=7000 <
        # requested=20000 -> no park; the current partial restore/recompute
        # path applies (a wake here would re-look-up into the same partial).
        self.assertFalse(
            backup_wait_applies(
                6000, 20000, durable_frontier=6000, backup_target_frontier=7000
            )
        )

    def test_no_in_flight_pipeline_never_parks(self):
        # target == durable (no in-flight write): nothing will advance the
        # frontier, so parking would idle out the T13 clock for no event.
        self.assertFalse(
            backup_wait_applies(
                6000, 20000, durable_frontier=6000, backup_target_frontier=6000
            )
        )

    def test_durable_past_request_never_parks(self):
        # durable >= requested: the lookup outcome was not mid-backup (a
        # full hit would have been served); never a park.
        self.assertFalse(
            backup_wait_applies(
                6000, 20000, durable_frontier=20000, backup_target_frontier=20000
            )
        )


class BackupWakeAppliesTests(unittest.TestCase):
    """backup_wake_applies: the T15 wake fires exactly when the chain's
    durable frontier has crossed the request's end -- the wake guarantees
    the re-lookup serves the full hit (one lookup, one restore)."""

    def test_frontier_crossed_request_end_wakes(self):
        self.assertTrue(backup_wake_applies(20000, 20000))

    def test_frontier_past_request_end_wakes(self):
        self.assertTrue(backup_wake_applies(24000, 20000))

    def test_frontier_below_request_end_does_not_wake(self):
        self.assertFalse(backup_wake_applies(19999, 20000))

    def test_frontier_at_zero_does_not_wake(self):
        self.assertFalse(backup_wake_applies(0, 20000))


class DemandRestoreTicketTests(unittest.TestCase):
    """demand_restore_available: the T15 wake re-issue bypasses the
    speculative PREFETCH_BUDGET but is bounded by its own concurrency
    (anti-thundering-herd when a backup-complete wake batch re-issues
    together; the prefetch IO pipeline stays serialized per thread)."""

    def test_ticket_free_at_zero_inflight(self):
        self.assertTrue(demand_restore_available(0))

    def test_ticket_free_below_bound(self):
        self.assertTrue(demand_restore_available(DEMAND_RESTORE_MAX_INFLIGHT - 1))

    def test_ticket_exhausted_at_bound(self):
        self.assertFalse(demand_restore_available(DEMAND_RESTORE_MAX_INFLIGHT))

    def test_ticket_exhausted_beyond_bound(self):
        self.assertFalse(demand_restore_available(DEMAND_RESTORE_MAX_INFLIGHT + 3))


def _drain_harness():
    """Lazy import of the cache harness from test_drain_reentry (drives the
    real unified_radix_cache revoke/span/ready path). Works in both modes --
    the venv torch mode loads the local tree, the torch-less stubenv
    bootstrap fakes it -- while the pure state-machine suite above stays
    torch-free and standalone."""
    import test_drain_reentry

    return test_drain_reentry


def _parked_cache(backup_park=True):
    """The T15 bypass model: chain [10(6000 pages), 20(14000 pages)] =
    requested [0..20000); anchor 10 persisted (durable 6000), node 20's
    write in flight (target 20000)."""
    h = _drain_harness()
    tree_core = h._FakeTreeCore([[10, 20]])
    hashes = [f"h{i}" for i in range(20000)]
    tree_core.node_hashes = {10: hashes[:6000], 20: hashes[6000:]}
    tree_core._request_hashes = list(hashes)
    tree_core.persisted.add(10)
    cache = h._make_cache(tree_core, backup_park=backup_park)
    cache.ongoing_backup = {7: (20, "lock-params")}
    cache._storage_prefetch_terminal = {}
    operation = SimpleNamespace(
        request_id="r1",
        is_terminated=lambda: False,
        storage_hit_count=6000,
        token_ids=[0] * 20000,
        stats_requested_tokens=20000,
        all_hash_values=list(hashes),
        pool_storage_result=None,
        completed_tokens=0,
    )
    cache.ongoing_prefetch = {
        "r1": h._OngoingPrefetch(
            anchor_node_id=10,
            prefetch_key=[0] * 20000,
            host_indices=None,
            operation=operation,
            anchor_lock_params=None,
            comp_xfers={},
        )
    }
    return cache, tree_core, hashes


class T15PositiveCaseTests(unittest.TestCase):
    """P2-IO Phase 1 positive case (--hicache-restore-backup-park on): a
    partial-hit revoke of a chain whose backup pipeline covers the request
    end parks (revoked_backup_pending + span), the ACK drain advances the
    durable frontier across the request end (backup_wait_ready), and the
    wake re-issues one demand restore that lands READY. The scheduler
    demand-flag leg of the wake re-issue is guarded by the feed suite's
    test_backup_pending_wake_reissues_as_demand_restore; the state-machine
    legs are asserted inline below.
    """

    def test_flag_on_parks_and_registers_span(self):
        cache, _tree_core, hashes = _parked_cache()
        cache.revoke_pending_prefetch("r1")
        self.assertEqual(
            cache._storage_prefetch_terminal.get("r1"), "revoked_backup_pending"
        )
        self.assertEqual(cache._backup_wait_spans["r1"], (10, 20000, hashes))

    def test_ack_advances_durable_frontier_to_wake(self):
        cache, tree_core, _hashes = _parked_cache()
        cache.revoke_pending_prefetch("r1")
        self.assertFalse(cache.backup_wait_ready("r1"))
        tree_core.advance_storage_persisted(20)
        self.assertTrue(cache.backup_wait_ready("r1"))

    def test_wake_reissue_chain_lands_ready(self):
        # The wake re-issue leg (scheduler feeds the demand flag -- guarded
        # by the feed suite); the state machine then runs: BACKUP_PENDING
        # wait -> CAPACITY_FITS re-issue -> FINALIZED full hit -> READY.
        state, decision = next_restore(
            RestoreState.RESTORING, RestoreEvent.BACKUP_PENDING
        )
        self.assertIs(state, RestoreState.WAIT_CAPACITY)
        self.assertIs(decision, RestoreDecision.WAIT)
        state, decision = next_restore(
            state, RestoreEvent.CAPACITY_FITS, capacity_fits=True
        )
        self.assertIs(state, RestoreState.RESTORING)
        self.assertIs(decision, RestoreDecision.RETRY_PREFETCH)
        state, decision = next_restore(state, RestoreEvent.FINALIZED)
        self.assertIs(state, RestoreState.READY)
        self.assertIs(decision, RestoreDecision.NONE)


class T15BypassOffTests(unittest.TestCase):
    """P2-IO Phase 1 negative case (--hicache-restore-backup-park off, the
    production default): the same partial-hit outcome is classified as the
    pre-T15 baseline -- revoked_miss, no span, no park -- so the request
    recomputes and the scheduler-side T15 machinery stays dead code."""

    def test_flag_off_revoke_classifies_miss(self):
        cache, _tree_core, _hashes = _parked_cache(backup_park=False)
        cache.revoke_pending_prefetch("r1")
        self.assertEqual(cache._storage_prefetch_terminal.get("r1"), "revoked_miss")
        self.assertNotIn("r1", cache._backup_wait_spans)
        self.assertNotIn("r1", cache.ongoing_prefetch)

    def test_flag_off_drain_precheck_never_parks(self):
        # The >=threshold drain branch: with the flag off the pre-check
        # falls through to the pre-T15 restore path (host alloc attempt ->
        # revoke), never to revoked_backup_pending.
        cache, _tree_core, hashes = _parked_cache(backup_park=False)
        operation = cache.ongoing_prefetch["r1"].operation
        operation.pool_storage_result = SimpleNamespace(
            update_extra_pool_hit_pages=lambda *a, **k: None
        )
        operation.stats_total_tokens = 20000
        operation.hash_value = list(hashes)
        cache.cache_controller.prefetch_hit_queue = Queue()
        cache.cache_controller.prefetch_hit_queue.put(operation)
        cache.evict_host = lambda n: None

        cache._drain_storage_control_queues_impl(1, 0, 0, 0, {}, False)

        self.assertEqual(cache._storage_prefetch_terminal.get("r1"), "revoked_miss")
        self.assertNotIn("r1", cache._backup_wait_spans)
        self.assertNotIn("r1", cache.ongoing_prefetch)


if __name__ == "__main__":
    unittest.main(verbosity=2)
