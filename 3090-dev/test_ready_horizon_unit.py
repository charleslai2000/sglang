"""P3 Ready Horizon v0 (3.2): ready_horizon.py policy unit tests.

Guards the 3.2 deliverables against the design corrections (including the
user's 2026-09-01 M3 rework adjudication: per-rid causal negative-cache,
NOT an epoch_sig + cooldown patch):

- M6 strict pool membership: READY && required prefix physically resident
  in the host tree (staged marker) && not consumed/inflight. V0
  conservative staging: the resident span must be the FULL requested
  prefix (a partial L3 restore is never a READY pool member).
- Candidate filtering: only NONE (with restore potential) and
  WAIT[DEVICE_QUOTA with host_hit == 0] / WAIT[PREFETCH_BUDGET] are
  stageable; FRONTIER / BACKUP_PENDING (ACK-event-driven) and the
  non-testable reasons (HOST_ALLOC / REVALIDATE) are excluded, as are
  in-flight fetches.
- Water math: ready < watermark_low triggers a refill, capped at
  watermark_high - ready per pass.
- M1 headroom: 2 x 20.9K READY residents are reachable under the host
  headroom model (the old inflight-budget cap would veto at 21.4K); the
  headroom gate declines silently (M2: no eviction, ever).
- M3 causal negative-cache rework (user adjudication):
  * Negative-cache: a decline parks the rid with its subscribed epoch's
    cursor; the rid is NOT re-eligible until that epoch advances past the
    cursor (or the request identity changed / the safety fuse expired) --
    NOT on the next pass, NOT on a READY pool / running batch change.
  * Deterministic-miss park: a NO_L3 miss is not transient; only an
    l3_publish advance (or identity/fuse) clears it (the e7 1289-issue /
    9.04s spin regression).
  * Epoch subscription: NO_L3 -> l3_publish, NO_HEADROOM ->
    host_headroom, SPEC_BUDGET -> spec_budget. A non-subscribed epoch
    advancing does NOT clear the park.
  * At most one staging attempt per rid per causal epoch.
  * Causal epochs gate the refill: only L3 published / host pages
    released / budget released / frontier changed fire an event; the
    refill's own traffic never does.

Runs the real scheduler_components/ready_horizon.py (torch-free) and the
real Scheduler._ready_horizon_pass source against stub collaborators, the
same pattern as test_hicache_restore_scheduler_feed.py.
"""

import time
import unittest
from types import SimpleNamespace
from unittest import mock

import sglang.srt.managers.scheduler as scheduler_mod
from sglang.srt.managers.scheduler import Scheduler
from sglang.srt.managers.scheduler_components.hicache_restore import (
    RestoreState,
    RestoreWaitReason,
)
from sglang.srt.managers.scheduler_components.ready_horizon import (
    CausalEpochs,
    DeclineReason,
    NegativeCacheEntry,
    ReadyHorizonPolicy,
    ReadyHorizonView,
)

NONE = RestoreState.NONE
WAIT = RestoreState.WAIT_CAPACITY
RESTORING = RestoreState.RESTORING
READY = RestoreState.READY

NO_L3 = DeclineReason.NO_L3
NO_HEADROOM = DeclineReason.NO_HEADROOM
SPEC_BUDGET = DeclineReason.SPEC_BUDGET

# One full M4T chain: the resident footprint of a single READY member.
CHAIN_TOKENS = 20_910
# A host pool sized like the M4T rig: prefetch_capacity_limit = 0.5 x pool
# = 21,392 (the old model's cap for READY residents).
POOL_TOKENS = 2 * 21_392

PREFIX_LEN = 100  # default identity fingerprint in the test views


def _req(rid, state=None, reason=None, host_hit=0, generation=None):
    return SimpleNamespace(
        rid=rid,
        last_host_node=1,
        full_untruncated_fill_ids=[1] * PREFIX_LEN,
        hicache_restore_state=state,
        hicache_restore_wait_reason=reason,
        hicache_restore_state_ts=0.0,
        host_hit_length=host_hit,
        session_generation=generation,
    )


def _view(
    rid,
    state,
    reason=None,
    staged=0,
    host_hit=0,
    eligible=True,
    req=None,
    full_prefix=True,
    prefix_len=PREFIX_LEN,
    generation=None,
):
    return ReadyHorizonView(
        req=req if req is not None else _req(rid),
        rid=rid,
        state=state,
        wait_reason=reason,
        staged_tokens=staged,
        full_prefix=full_prefix,
        host_hit_length=host_hit,
        staging_eligible=eligible,
        prefix_len=prefix_len,
        generation=generation,
    )


def _views(*specs):
    """Build views from tuples; full spec:
    (rid, state, reason, staged, host_hit, eligible, full_prefix)"""
    views = []
    for spec in specs:
        rid, state = spec[0], spec[1]
        reason = spec[2] if len(spec) > 2 else None
        staged = spec[3] if len(spec) > 3 else 0
        host_hit = spec[4] if len(spec) > 4 else 0
        eligible = spec[5] if len(spec) > 5 else True
        full_prefix = spec[6] if len(spec) > 6 else True
        views.append(_view(rid, state, reason, staged, host_hit, eligible, full_prefix=full_prefix))
    return views


def _neg(
    rid=None,
    reason=NO_L3,
    cursor=0,
    fuse_expiry=0.0,
    prefix_len=PREFIX_LEN,
    generation=None,
):
    """A negative-cache park input; rid is cosmetic (dict key carries it)."""
    return NegativeCacheEntry(
        reason=reason,
        epoch_cursor=cursor,
        fuse_expiry=fuse_expiry,
        prefix_len=prefix_len,
        generation=generation,
    )


class _Cc:
    """Controller stub: budgets, counters and the pool the policy reads."""

    def __init__(
        self,
        spec_inflight=0,
        spec_limit=10**9,
        physical_occupied=0,
        physical_limit=10**9,
        available=10**9,
        size=10**9,
    ):
        self.inflight_speculative_tokens = spec_inflight
        self.prefetch_speculative_capacity_limit = spec_limit
        self.prefetch_tokens_occupied = physical_occupied
        self.prefetch_capacity_limit = physical_limit
        self.available = available
        self.mem_pool_host = SimpleNamespace(
            size=size, available_size=lambda: self.available
        )

    def prefetch_rate_limited(self):
        return self.prefetch_tokens_occupied >= self.prefetch_capacity_limit

    def prefetch_speculative_rate_limited(self):
        return (
            self.inflight_speculative_tokens
            >= self.prefetch_speculative_capacity_limit
        )


def _tree(ongoing=(), l3_publish=0):
    terminal: dict = {}
    tree = SimpleNamespace(
        ongoing_prefetch=set(ongoing),
        has_restore_potential=lambda *a, **k: True,
        l3_publish_epoch=lambda: l3_publish,
        _storage_prefetch_terminal=terminal,
        # stale `_final_storage_survivability` (P3 instrumentation): the
        # recompute log reads these off the tree cache.
        node_exists=lambda *a, **k: False,
        is_l3_durable=lambda *a, **k: False,
    )
    # Mirror the real unified_radix_cache terminal-outcome methods so the
    # scheduler's _feed_restore_terminal can consume a recorded drain
    # terminal.
    def _record(req_id, outcome):
        terminal[req_id] = outcome

    def _pop(req_id):
        return terminal.pop(req_id, None)

    tree.record_storage_prefetch_terminal = _record
    tree.pop_storage_prefetch_terminal = _pop
    return tree


def _epochs(
    l3=0,
    headroom=10**9,
    spec=0,
    frontier=("r1",),
):
    return CausalEpochs(
        l3_publish=l3,
        host_headroom=headroom,
        spec_budget=spec,
        waiting_frontier=tuple(frontier),
    )


def _policy(low=2, high=4, frontier_n=8):
    return ReadyHorizonPolicy(
        frontier_n=frontier_n, watermark_low=low, watermark_high=high
    )


class FrontierTests(unittest.TestCase):
    """The staging input is the first N requests in current queue order."""

    def test_frontier_takes_first_n_in_queue_order(self):
        queue = [_req("r1"), _req("r2"), _req("r3"), _req("r4")]
        self.assertEqual(
            [r.rid for r in _policy(frontier_n=2).frontier(queue)], ["r1", "r2"]
        )

    def test_frontier_defaults_to_configured_n(self):
        queue = [_req(f"r{i}") for i in range(10)]
        self.assertEqual(len(_policy(frontier_n=8).frontier(queue)), 8)


class ReadyCountM6Tests(unittest.TestCase):
    """M6 strict membership: READY + physically resident FULL prefix, not
    consumed/inflight. READY produced by other paths does not count."""

    def test_ready_requires_resident_marker(self):
        views = _views(
            ("r1", READY, None, CHAIN_TOKENS),  # resident: counted
            ("r2", READY, None, 0),  # foreign READY, no material: not counted
            ("r3", RESTORING, None, CHAIN_TOKENS),  # not READY
            ("r4", WAIT, RestoreWaitReason.PREFETCH_BUDGET, CHAIN_TOKENS),
            ("r5", NONE, None, CHAIN_TOKENS),
        )
        self.assertEqual(_policy().ready_count(views), 1)
        self.assertEqual(_policy().ready_resident_tokens(views), CHAIN_TOKENS)

    def test_dropped_insert_is_not_pool_material(self):
        # A finalize that dropped the host insert writes loaded = 0: the
        # request is READY in name only.
        views = _views(("r1", READY, None, 0))
        self.assertEqual(_policy().ready_count(views), 0)

    def test_consumed_marker_not_counted(self):
        # Admission pops the marker (pop_prefetch_loaded_tokens): a
        # READY whose material was consumed is not pool material.
        views = _views(("r1", READY, None, 0))
        self.assertEqual(_policy().ready_count(views), 0)

    def test_partial_prefix_not_pool_material(self):
        # V0 conservative staging (user adjudication item 4): a READY whose
        # resident span is only PART of the requested prefix never counts
        # toward the watermark -- the pool must be full-execution-state.
        views = _views(
            ("full", READY, None, CHAIN_TOKENS),  # full_prefix default True
            ("partial", READY, None, CHAIN_TOKENS, 0, True, False),  # partial restore
        )
        self.assertEqual(_policy().ready_count(views), 1)
        self.assertEqual(_policy().ready_resident_tokens(views), CHAIN_TOKENS)


class StagingCandidateTests(unittest.TestCase):
    """Who may be staged: NONE (with potential) / WAIT[DEVICE_QUOTA,
    host_hit == 0] / WAIT[PREFETCH_BUDGET]; everything else excluded."""

    _kw = dict(tree=None, cc=None, negatives=None, epochs=None, now=0.0)

    def _candidates(self, views, *, negatives=None, epochs=None, cc=None, tree=None, now=0.0):
        return [
            v.rid
            for v in _policy().staging_candidates(
                views,
                tree=tree or _tree(),
                cc=cc or _Cc(),
                negatives=negatives or {},
                epochs=epochs or _epochs(frontier=[v.rid for v in views]),
                now=now,
            )
        ]

    def test_device_quota_zero_hit_and_budget_included(self):
        views = _views(
            ("r1", WAIT, RestoreWaitReason.DEVICE_QUOTA, 0, 0),
            ("r2", WAIT, RestoreWaitReason.PREFETCH_BUDGET),
        )
        self.assertEqual(self._candidates(views), ["r1", "r2"])

    def test_none_with_potential_included(self):
        views = _views(("r1", NONE, None, 0, 0, True))
        self.assertEqual(self._candidates(views), ["r1"])

    def test_ack_driven_and_untestable_reasons_excluded(self):
        views = _views(
            ("f", WAIT, RestoreWaitReason.FRONTIER),
            ("b", WAIT, RestoreWaitReason.BACKUP_PENDING),
            ("h", WAIT, RestoreWaitReason.HOST_ALLOC),
            ("v", WAIT, RestoreWaitReason.REVALIDATE),
        )
        self.assertEqual(self._candidates(views), [])

    def test_device_quota_with_host_material_excluded(self):
        # T6 sources whose host material is already staged are the
        # promotion-budget items owned by the T11 predicate, not the
        # horizon's unrestricted L3->H staging.
        views = _views(("r1", WAIT, RestoreWaitReason.DEVICE_QUOTA, 0, 1000))
        self.assertEqual(self._candidates(views), [])

    def test_non_stageable_states_excluded(self):
        views = _views(
            ("r1", RESTORING, None),
            ("r2", READY, None, CHAIN_TOKENS),
            ("r3", NONE, None, 0, 0, False),  # no restore potential
        )
        self.assertEqual(self._candidates(views), [])

    def test_ongoing_prefetch_excluded(self):
        views = _views(
            ("r1", NONE, None, 0, 0, True),
            ("r2", WAIT, RestoreWaitReason.PREFETCH_BUDGET),
        )
        got = self._candidates(views, tree=_tree(ongoing=("r2",)))
        self.assertEqual(got, ["r1"])

    def test_exhausted_budgets_exclude_all(self):
        # Every speculative issue would decline identically: park the
        # refill until a budget-release epoch (M3) instead of attempting.
        views = _views(("r1", WAIT, RestoreWaitReason.PREFETCH_BUDGET))
        spec_full = _Cc(spec_inflight=10, spec_limit=10)
        self.assertEqual(self._candidates(views, cc=spec_full), [])
        physical_full = _Cc(physical_occupied=10, physical_limit=10)
        self.assertEqual(self._candidates(views, cc=physical_full), [])


class NegativeCacheTests(unittest.TestCase):
    """M3 rework (user adjudication): a parked rid is not re-eligible until
    its SUBSCRIBED causal epoch advances past the decline cursor (or
    identity changed / fuse expired). Nothing else -- next pass, READY pool
    change, running batch change -- clears it."""

    def _cleared(self, entry, view=None, epochs=None, now=10.0):
        view = view or _view("r1", NONE, eligible=True)
        return _policy().entry_cleared(
            entry, view, epochs or _epochs(frontier=("r1",)), now
        )

    def test_same_cursor_not_cleared(self):
        # Park at l3_publish=5; the cursors are unchanged (5): the miss is
        # deterministic and the L3 coverage has not advanced.
        entry = _neg(reason=NO_L3, cursor=5)
        epochs = _epochs(l3=5, frontier=("r1",))
        self.assertFalse(self._cleared(entry, epochs=epochs))

    def test_l3_publish_advance_clears_no_l3(self):
        entry = _neg(reason=NO_L3, cursor=5)
        epochs = _epochs(l3=6, frontier=("r1",))
        self.assertTrue(self._cleared(entry, epochs=epochs))

    def test_no_l3_not_cleared_by_other_epochs(self):
        # A host-headroom or budget release is NOT causal for an L3 miss:
        # the full prefix is still not in L3.
        entry = _neg(reason=NO_L3, cursor=5)
        epochs = _epochs(l3=5, headroom=10**9 + 100, spec=0, frontier=("r1",))
        self.assertFalse(self._cleared(entry, epochs=epochs))

    def test_no_headroom_cleared_only_by_host_headroom(self):
        # Parked at host_headroom=100. An L3 publish advance does not free
        # host pages: the headroom gate still fails.
        entry = _neg(reason=NO_HEADROOM, cursor=100)
        self.assertFalse(self._cleared(entry, epochs=_epochs(l3=500, headroom=100)))
        # Host pages released (150 > 100): the headroom gate can now pass.
        self.assertTrue(self._cleared(entry, epochs=_epochs(headroom=150)))
        # Budget release is not causal for headroom.
        self.assertFalse(
            self._cleared(entry, epochs=_epochs(headroom=100, spec=0))
        )

    def test_spec_budget_cleared_only_by_budget_release(self):
        # Parked when inflight was 20 (the budget was exhausted). An L3
        # publish or a headroom release does not free the speculative
        # budget.
        entry = _neg(reason=SPEC_BUDGET, cursor=20)
        self.assertFalse(
            self._cleared(entry, epochs=_epochs(spec=20, l3=3, headroom=300))
        )
        # Budget released: inflight dropped to 0 (< 20).
        self.assertTrue(self._cleared(entry, epochs=_epochs(spec=0)))
        # Inflight still high / growing is not a release.
        self.assertFalse(self._cleared(entry, epochs=_epochs(spec=25)))

    def test_prefix_change_clears_any_park(self):
        # A new question deserves a new probe: the old negative judgment
        # was for the OLD prefix.
        entry = _neg(reason=NO_L3, cursor=5, prefix_len=100)
        view = _view("r1", NONE, eligible=True, prefix_len=500)
        self.assertTrue(self._cleared(entry, view=view))

    def test_generation_change_clears_any_park(self):
        entry = _neg(reason=NO_L3, cursor=5, generation=1)
        view = _view("r1", NONE, eligible=True, generation=2)
        self.assertTrue(self._cleared(entry, view=view))

    def test_fuse_expiry_is_only_a_safety_bound(self):
        # The fuse is NOT the retry cadence (a deterministic miss stays a
        # miss no matter how long you wait -- time alone never clears the
        # park). It only bounds a pathological repeat-fail loop once the
        # causal condition is otherwise met.
        entry = _neg(reason=NO_L3, cursor=5, fuse_expiry=20.0)
        self.assertFalse(self._cleared(entry, epochs=_epochs(l3=8), now=10.0))
        self.assertTrue(self._cleared(entry, epochs=_epochs(l3=8), now=25.0))

    def test_subscribe_decline_no_entry_eligible(self):
        # No park = never attempted = eligible for the one fresh probe.
        self.assertTrue(
            _policy().subscribe_decline(None, _view("r1", NONE, eligible=True), _epochs(), 0.0)
        )

    def test_staging_candidates_excludes_parked_rid(self):
        views = _views(("r1", NONE, None, 0, 0, True))
        negs = {"r1": _neg(reason=NO_L3, cursor=5)}
        epochs = _epochs(l3=5, frontier=("r1",))
        got = [
            v.rid
            for v in _policy().staging_candidates(
                views, tree=_tree(), cc=_Cc(), negatives=negs, epochs=epochs, now=0.0
            )
        ]
        self.assertEqual(got, [])


class WatermarkMathTests(unittest.TestCase):
    """low triggers a refill; the single-pass cap is high - ready."""

    def _plan(self, views, cc=None, epochs=None, negatives=None):
        return _policy().refill_plan(
            views,
            tree=_tree(),
            cc=cc or _Cc(),
            host_headroom=10**9,
            negatives=negatives or {},
            epochs=epochs or _epochs(frontier=[v.rid for v in views]),
            now=0.0,
        )

    def test_below_low_triggers_refill(self):
        views = _views(
            ("r1", NONE, None, 0, 0, True),
            ("r2", WAIT, RestoreWaitReason.PREFETCH_BUDGET),
        )
        plan = self._plan(views)
        self.assertEqual(plan.ready_count, 0)
        self.assertEqual([v.rid for v in plan.to_issue], ["r1", "r2"])

    def test_at_or_above_low_no_refill(self):
        views = _views(
            ("r1", READY, None, CHAIN_TOKENS),
            ("r2", READY, None, CHAIN_TOKENS),
            ("r3", NONE, None, 0, 0, True),
        )
        plan = self._plan(views)
        self.assertEqual(plan.ready_count, 2)
        self.assertEqual(plan.to_issue, [])

    def test_high_caps_single_pass(self):
        # ready = 1, watermark [2, 4]: the pass may issue at most 3.
        views = _views(
            ("r1", READY, None, CHAIN_TOKENS),
            ("r2", NONE, None, 0, 0, True),
            ("r3", NONE, None, 0, 0, True),
            ("r4", NONE, None, 0, 0, True),
            ("r5", NONE, None, 0, 0, True),
        )
        plan = self._plan(views)
        self.assertEqual(plan.ready_count, 1)
        self.assertEqual([v.rid for v in plan.to_issue], ["r2", "r3", "r4"])

    def test_ready_resident_tokens_summed(self):
        views = _views(
            ("r1", READY, None, CHAIN_TOKENS),
            ("r2", READY, None, 500),
            ("r3", READY, None, 0),  # M6: not resident
        )
        self.assertEqual(_policy().ready_resident_tokens(views), CHAIN_TOKENS + 500)


class HeadroomConstraintTests(unittest.TestCase):
    """M1: READY residents are bounded by the host headroom, NOT the
    inflight budget -- 2 x 20.9K READY chains are reachable only under
    the headroom model."""

    def test_two_chains_fit_the_headroom_model(self):
        # 2 READY residents = 41,820 tokens vs pool 42,784: the old model
        # (prefetch_capacity_limit = 0.5 x pool = 21,392 as the resident
        # cap) vetoes the second chain; the headroom model accepts it.
        policy = _policy()
        self.assertTrue(policy.headroom_fits(2 * CHAIN_TOKENS, 0, POOL_TOKENS))
        self.assertGreater(2 * CHAIN_TOKENS, 21_392)  # the old cap would veto

    def test_refill_not_vetoed_by_resident_footprint(self):
        # One READY chain resident, zero inflight: the refill issues the
        # second chain (ready 1 < low 2) -- the headroom gate must not
        # charge the resident footprint against free pages.
        views = _views(("r1", READY, None, CHAIN_TOKENS), ("r2", NONE, None))
        plan = _policy().refill_plan(
            views,
            tree=_tree(),
            cc=_Cc(available=POOL_TOKENS - CHAIN_TOKENS),
            host_headroom=POOL_TOKENS,
            negatives={},
            epochs=_epochs(frontier=("r1", "r2")),
            now=0.0,
        )
        self.assertEqual([v.rid for v in plan.to_issue], ["r2"])

    def test_headroom_insufficient_declines_silently(self):
        # One chain resident + one chain inflight on a 30K headroom: the
        # footprint (41,820) exceeds it -- no issue, no eviction.
        views = _views(("r1", READY, None, CHAIN_TOKENS), ("r3", NONE, None))
        plan = _policy().refill_plan(
            views,
            tree=_tree(),
            cc=_Cc(spec_inflight=CHAIN_TOKENS),
            host_headroom=30_000,
            negatives={},
            epochs=_epochs(frontier=("r1", "r3")),
            now=0.0,
        )
        self.assertEqual(plan.to_issue, [])
        # The causal-eligible candidate carries the headroom decline so the
        # scheduler can park it (NO_HEADROOM -> host_headroom epoch).
        self.assertEqual(
            [(rid, reason) for rid, reason in plan.declines],
            [("r3", NO_HEADROOM)],
        )

    def test_headroom_fits_bounds(self):
        policy = _policy()
        self.assertTrue(policy.headroom_fits(CHAIN_TOKENS, 0, CHAIN_TOKENS))
        self.assertTrue(policy.headroom_fits(CHAIN_TOKENS, 10, CHAIN_TOKENS + 10))
        self.assertFalse(policy.headroom_fits(CHAIN_TOKENS, 11, CHAIN_TOKENS + 10))


class EventDrivenRefillTests(unittest.TestCase):
    """M3: no event, no refill check; the periodic safety reconciliation
    is the only time-based path."""

    def test_no_event_within_interval_no_refill(self):
        now = time.perf_counter()
        policy = _policy()
        self.assertFalse(
            policy.should_refill(event=False, last_refill_ts=now - 1.0, now=now)
        )

    def test_event_triggers_refill(self):
        now = time.perf_counter()
        policy = _policy()
        self.assertTrue(
            policy.should_refill(event=True, last_refill_ts=now - 0.1, now=now)
        )

    def test_safety_reconciliation_after_interval(self):
        # Lost-event fallback: seconds, never the per-pass path.
        now = time.perf_counter()
        policy = _policy()
        self.assertTrue(
            policy.should_refill(event=False, last_refill_ts=now - 10.0, now=now)
        )


class CausalEpochEventTests(unittest.TestCase):
    """M3 rework: the four causal epochs. Only availability-improving
    deltas (L3 published / host pages released / budget released / frontier
    changed) fire; the refill's own issue traffic never does."""

    def _epoch(self, l3=0, headroom=1000, spec=0, frontier=("r1",)):
        return CausalEpochs(l3_publish=l3, host_headroom=headroom, spec_budget=spec, waiting_frontier=frontier)

    def test_first_pass_is_event(self):
        self.assertTrue(_policy().epoch_event(None, self._epoch()))

    def test_identical_epochs_no_event(self):
        e = self._epoch()
        self.assertFalse(_policy().epoch_event(e, e))

    def test_refill_own_issue_traffic_no_event(self):
        # The refill issued: inflight up, free pages down, L3 unchanged.
        # None of these is an availability improvement (the e7 spin leg).
        prev = self._epoch(headroom=1000, spec=0)
        after = self._epoch(headroom=900, spec=CHAIN_TOKENS)
        self.assertFalse(_policy().epoch_event(prev, after))

    def test_budget_released_is_event(self):
        prev = self._epoch(spec=CHAIN_TOKENS)
        after = self._epoch(spec=0)
        self.assertTrue(_policy().epoch_event(prev, after))

    def test_host_pages_released_is_event(self):
        prev = self._epoch(headroom=900)
        after = self._epoch(headroom=1000)
        self.assertTrue(_policy().epoch_event(prev, after))

    def test_l3_published_is_event(self):
        prev = self._epoch(l3=0)
        after = self._epoch(l3=1)
        self.assertTrue(_policy().epoch_event(prev, after))

    def test_frontier_change_is_event(self):
        prev = self._epoch(frontier=("r1",))
        after = self._epoch(frontier=("r1", "r2"))
        self.assertTrue(_policy().epoch_event(prev, after))

    def test_resource_consumption_is_not_event(self):
        # Demand restores consuming the physical budget / host pages is
        # not an event: consuming resources never makes staging easier.
        prev = self._epoch(headroom=1000, spec=0)
        after = self._epoch(headroom=800, spec=5000)
        self.assertFalse(_policy().epoch_event(prev, after))


class NoOpIdleTests(unittest.TestCase):
    """Empty pass: no commands, no state mutation."""

    def test_no_candidates_zero_commands_no_mutation(self):
        views = _views(
            ("f", WAIT, RestoreWaitReason.FRONTIER),
            ("b", WAIT, RestoreWaitReason.BACKUP_PENDING),
            ("h", WAIT, RestoreWaitReason.HOST_ALLOC),
        )
        cc = _Cc()
        tree = _tree()
        before = [tuple((v.rid, v.state, v.staged_tokens)) for v in views]
        plan = _policy().refill_plan(
            views,
            tree=tree,
            cc=cc,
            host_headroom=10**9,
            negatives={},
            epochs=_epochs(frontier=[v.rid for v in views]),
            now=0.0,
        )
        self.assertEqual(plan.to_issue, [])
        self.assertEqual(plan.ready_count, 0)
        # Pure: nothing moved in the inputs.
        self.assertEqual(
            [tuple((v.rid, v.state, v.staged_tokens)) for v in views], before
        )
        self.assertEqual(tree.ongoing_prefetch, set())
        self.assertEqual(cc.inflight_speculative_tokens, 0)

    def test_empty_frontier_zero_commands(self):
        plan = _policy().refill_plan(
            [], tree=_tree(), cc=_Cc(), host_headroom=10**9, negatives={}, epochs=_epochs(), now=0.0
        )
        self.assertEqual(plan.to_issue, [])
        self.assertEqual(plan.ready_count, 0)


# ---------------------------------------------------------------------------
# Scheduler wiring: _ready_horizon_pass delegates to the policy and issues
# through _prefetch_kvcache; the causal epochs gate the refill; M2 never
# evicts; the per-rid negative cache records declines causally.
# ---------------------------------------------------------------------------


def _pass_scheduler(
    *,
    queue=(),
    cc=None,
    enable=True,
    tree_cache=None,
    l3_publish=0,
):
    scheduler = Scheduler.__new__(Scheduler)
    scheduler.server_args = SimpleNamespace(
        hicache_host_memory_mode="cache",
        ready_horizon_frontier_n=8,
        ready_host_watermark_low=2,
        ready_host_watermark_high=4,
        ready_host_watermark_low_count=2,  # legacy count-mode opt-in
        ready_host_watermark_high_count=4,
        ready_horizon_state_p95_tokens=0,
        hicache_writeback_reserve_state_tokens=None,
        ready_horizon_margin_state_tokens=None,
        hicache_restore_wait_timeout_s=60.0,
        ready_horizon_safety_margin_gb=0.0,
    )
    scheduler.enable_ready_horizon = enable
    scheduler.init_ready_horizon()
    scheduler.waiting_queue = list(queue)
    scheduler.tree_cache = tree_cache or _tree(l3_publish=l3_publish)
    scheduler.tree_cache.cache_controller = cc or _Cc()
    scheduler.tree_cache.staged_prefetch_tokens = lambda rid: 0
    scheduler.tree_cache.peek_prefetch_loaded_tokens = lambda rid: 0
    scheduler.tree_cache.has_restore_potential = lambda *a, **k: True
    if not hasattr(scheduler.tree_cache, "l3_publish_epoch"):
        scheduler.tree_cache.l3_publish_epoch = lambda: l3_publish
    scheduler.issued = []
    scheduler.evicted = []
    scheduler.tree_cache.evict_host = (
        lambda *a, **k: scheduler.evicted.append(a) or 0
    )

    def _issue(req, *, demand_restore=False):
        # Mirror the real T1 wiring: a successful issue transitions the
        # request to RESTORING, so it leaves the candidate set.
        req.hicache_restore_state = RESTORING
        scheduler.issued.append(req.rid)

    scheduler._prefetch_kvcache = _issue
    return scheduler


class ReadyHorizonPassTests(unittest.TestCase):
    """_ready_horizon_pass: frontier views, causal-epoch-gated refill,
    delegation to _prefetch_kvcache, change-driven [P3] logging."""

    def _run(self, scheduler):
        scheduler._ready_horizon_pass()

    def test_pass_issues_candidates_via_prefetch_kvcache(self):
        scheduler = _pass_scheduler(
            queue=[
                _req("r1", NONE),
                _req("r2", WAIT, RestoreWaitReason.PREFETCH_BUDGET),
                _req("f", WAIT, RestoreWaitReason.FRONTIER),
            ]
        )
        self._run(scheduler)
        # The frontier park is ACK-driven; the NONE and budget waiters are
        # staged through the real issue path (speculative).
        self.assertEqual(scheduler.issued, ["r1", "r2"])

    def test_no_event_epoch_no_refill(self):
        # A second pass with an unchanged causal epoch (and the refill just
        # run) issues nothing: M3's no-poll guarantee at the pass level. A
        # denied candidate's WAIT transition is not an event.
        scheduler = _pass_scheduler(queue=[_req("r1", NONE)])
        self._run(scheduler)
        self.assertEqual(scheduler.issued, ["r1"])
        self._run(scheduler)
        self.assertEqual(scheduler.issued, ["r1"])

    def test_causal_epoch_change_triggers_new_refill(self):
        # The frontier changed (a new request entered): a causal event.
        # The next pass re-checks and issues the new candidate.
        scheduler = _pass_scheduler(queue=[_req("r1", NONE)])
        self._run(scheduler)
        self.assertEqual(scheduler.issued, ["r1"])
        # Same epoch again: no refill (the issued request is now staged).
        self._run(scheduler)
        self.assertEqual(scheduler.issued, ["r1"])
        # Frontier composition changed (a fresh candidate entered).
        scheduler.waiting_queue.append(_req("r2", NONE))
        self._run(scheduler)
        self.assertEqual(scheduler.issued, ["r1", "r2"])

    def test_headroom_shortfall_never_evicts(self):
        # Pool full (available 0) with a chain in flight: the refill
        # declines silently -- zero issues, zero evict_host calls (M2).
        cc = _Cc(spec_inflight=CHAIN_TOKENS, available=0)
        scheduler = _pass_scheduler(queue=[_req("r1", NONE)], cc=cc)
        self._run(scheduler)
        self.assertEqual(scheduler.issued, [])
        self.assertEqual(scheduler.evicted, [])

    def test_off_mode_is_a_noop(self):
        scheduler = _pass_scheduler(queue=[_req("r1", NONE)], enable=False)
        self._run(scheduler)
        self.assertEqual(scheduler.issued, [])

    def test_ready_pool_log_on_change(self):
        scheduler = _pass_scheduler(
            queue=[_req("r1", READY, None), _req("r2", READY, None)],
        )
        scheduler.tree_cache.peek_prefetch_loaded_tokens = lambda rid: CHAIN_TOKENS
        with self.assertLogs("sglang.srt.managers.scheduler", level="INFO") as logs:
            self._run(scheduler)
        self.assertTrue(
            any("evt=ready_pool size=2 tokens=41820 watermark=[2/4]" in m for m in logs.output),
            logs.output,
        )

    def test_off_mode_never_constructs_epoch_plumbing(self):
        # The pass gates before any epoch/views work: off is a pure no-op
        # even with a broken tree stub.
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.enable_ready_horizon = False
        scheduler.tree_cache = None
        scheduler._ready_horizon_pass()

    def test_ready_stage_log_reports_issue_result(self):
        # The 3090 analysis needs attempted vs issued separable in the
        # [P3] stream (e7: 1144 silent declines were logged as stages).
        scheduler = _pass_scheduler(queue=[_req("r1", NONE)])
        with self.assertLogs("sglang.srt.managers.scheduler", level="INFO") as logs:
            scheduler._ready_horizon_pass()
        self.assertTrue(
            any("evt=ready_stage rid=r1 result=issued state=RESTORING" in m for m in logs.output),
            logs.output,
        )


class _FakeClock:
    """Deterministic replacement for time.perf_counter: the fuse window is
    controlled explicitly, so a test can expire the fuse independently of
    the causal-epoch assertion it is cross-checking."""

    def __init__(self, start=1000.0):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


class DeterministicMissParkTests(unittest.TestCase):
    """M3 rework: the deterministic-miss negative-cache lifecycle through
    _ready_horizon_pass -- probe once, park on the miss, hold across
    ordinary epoch changes, clear only on an l3_publish advance (or an
    identity change / fuse expiry) + a causal event.

    The safety fuse is a rate bound, not the retry cadence: a deterministic
    miss stays parked even past the fuse unless the subscribed causal epoch
    advanced. Both conditions are asserted independently here (epoch
    subscription correctness, item 2 of the adjudication)."""

    def _clock_patch(self):
        clock = _FakeClock()
        return mock.patch(
            "sglang.srt.managers.scheduler.time.perf_counter", new=clock
        ), clock

    def _make_scheduler(self, cc=None, l3_publish=0):
        cc = cc or _Cc()
        scheduler = _pass_scheduler(queue=[_req("r1", NONE)], cc=cc, l3_publish=l3_publish)

        def charge(req, *, demand_restore=False):
            cc.inflight_speculative_tokens += CHAIN_TOKENS
            req.hicache_restore_state = RESTORING
            scheduler.issued.append(req.rid)

        scheduler._prefetch_kvcache = charge
        return scheduler, cc

    def test_miss_recorded_and_held_across_ordinary_changes(self):
        patch, clock = self._clock_patch()
        with patch:
            cc = _Cc()
            scheduler, _ = self._make_scheduler(cc=cc, l3_publish=0)
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1"])
            # No park yet: the issue succeeded (RESTORING), the miss is async.
            self.assertFalse("r1" in scheduler._ready_horizon_negatives)

            # The drain's miss lands (T9 genuine miss): the req returns to
            # NONE and the NO_L3 negative cache is recorded.
            scheduler.waiting_queue[0].hicache_restore_state = NONE
            scheduler.tree_cache.record_storage_prefetch_terminal("r1", "revoked_miss")
            scheduler._feed_restore_terminal(scheduler.waiting_queue[0])
            self.assertEqual(
                scheduler._ready_horizon_negatives["r1"].reason, NO_L3
            )

            # Ordinary changes (host pages released, budget released,
            # frontier same), even past the fuse, do NOT clear a NO_L3 park:
            # the full prefix is still not in L3.
            clock.advance(10.0)  # past the 1s fuse
            cc.inflight_speculative_tokens = 0
            cc.available += 1
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1"])  # not re-probed

    def test_l3_publish_advance_clears_and_reprobes_once(self):
        patch, clock = self._clock_patch()
        with patch:
            cc = _Cc()
            scheduler, _ = self._make_scheduler(cc=cc, l3_publish=0)
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1"])
            scheduler.waiting_queue[0].hicache_restore_state = NONE
            scheduler.tree_cache.record_storage_prefetch_terminal("r1", "revoked_miss")
            scheduler._feed_restore_terminal(scheduler.waiting_queue[0])
            self.assertEqual(scheduler._ready_horizon_negatives["r1"].reason, NO_L3)

            # Fuse still live: even with the L3 counter advanced the park
            # holds (the rate bound, not the retry cadence).
            scheduler.tree_cache.l3_publish_epoch = lambda: 3
            cc.inflight_speculative_tokens = 0
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1"])

            # Fuse expired AND the L3 durable counter advanced: the park
            # clears and the rid gets its one fresh probe.
            clock.advance(10.0)
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1", "r1"])

    def test_after_reprobe_miss_reparks_at_new_cursor(self):
        patch, clock = self._clock_patch()
        with patch:
            cc = _Cc()
            scheduler, _ = self._make_scheduler(cc=cc, l3_publish=0)
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1"])
            scheduler.waiting_queue[0].hicache_restore_state = NONE
            scheduler.tree_cache.record_storage_prefetch_terminal("r1", "revoked_miss")
            scheduler._feed_restore_terminal(scheduler.waiting_queue[0])
            entry1 = scheduler._ready_horizon_negatives["r1"]
            self.assertEqual(entry1.epoch_cursor, 0)

            # L3 publishes once and the fuse expires: the rid reprobes,
            # misses again, and re-parks at the NEW cursor.
            scheduler.tree_cache.l3_publish_epoch = lambda: 1
            cc.inflight_speculative_tokens = 0
            clock.advance(10.0)
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1", "r1"])
            # The second miss lands (the drain records the revoked_miss
            # terminal); the re-park records the NEW l3_publish cursor.
            scheduler.waiting_queue[0].hicache_restore_state = NONE
            scheduler.tree_cache.record_storage_prefetch_terminal("r1", "revoked_miss")
            scheduler._feed_restore_terminal(scheduler.waiting_queue[0])
            entry2 = scheduler._ready_horizon_negatives["r1"]
            self.assertEqual(entry2.epoch_cursor, 1)

            # Same causal epoch (cursor still 1) even with the fuse expired
            # again: the next event pass holds the park -- at most one
            # staging attempt per rid per causal epoch.
            clock.advance(10.0)
            scheduler.waiting_queue[0].hicache_restore_state = NONE
            cc.inflight_speculative_tokens = 0
            cc.available += 1
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1", "r1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)