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
    host_release (Fix A: the MONOTONIC capacity-release counter, not the
    transient available level), SPEC_BUDGET -> spec_budget. A
    non-subscribed epoch advancing does NOT clear the park.
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
from sglang.srt.disaggregation.utils import DisaggregationMode
from sglang.srt.managers.scheduler import Scheduler
from sglang.srt.managers.scheduler_components.hicache_restore import (
    HiCachePrefetchOrigin,
    PrefetchIssueResult,
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


def _req(rid, state=None, reason=None, host_hit=0, generation=None, anchor=1):
    return SimpleNamespace(
        rid=rid,
        last_host_node=anchor,
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
    anchor=None,
):
    """A negative-cache park input; rid is cosmetic (dict key carries it)."""
    return NegativeCacheEntry(
        reason=reason,
        epoch_cursor=cursor,
        fuse_expiry=fuse_expiry,
        prefix_len=prefix_len,
        generation=generation,
        anchor=anchor,
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


def _tree(ongoing=(), l3_publish=0, anchor_versions=None, anchor_exists=True):
    terminal: dict = {}
    _av = anchor_versions if anchor_versions is not None else {}

    def _anchor_version(node_id):
        if not anchor_exists:
            return 0
        return _av.get(node_id, 0)

    tree = SimpleNamespace(
        ongoing_prefetch=set(ongoing),
        has_restore_potential=lambda *a, **k: True,
        l3_publish_epoch=lambda: l3_publish,
        anchor_storage_version=_anchor_version,
        _storage_prefetch_terminal=terminal,
        # stale `_final_storage_survivability` (P3 instrumentation): the
        # recompute log reads these off the tree cache.
        node_exists=lambda *a, **k: anchor_exists,
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
    release=0,
):
    return CausalEpochs(
        l3_publish=l3,
        host_headroom=headroom,
        spec_budget=spec,
        waiting_frontier=tuple(frontier),
        host_release=release,
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

    def _cleared(self, entry, view=None, epochs=None, now=10.0, anchor_version=None):
        view = view or _view("r1", NONE, eligible=True)
        return _policy().entry_cleared(
            entry,
            view,
            epochs or _epochs(frontier=("r1",)),
            now,
            anchor_version=anchor_version,
            anchor=view.req.last_host_node,
        )

    def test_same_cursor_not_cleared(self):
        # Park at the anchor's per-anchor version 5; the same anchor's
        # version is unchanged (5): the miss is deterministic and THIS
        # anchor's L3 coverage has not advanced.
        entry = _neg(reason=NO_L3, cursor=5, anchor=1)
        epochs = _epochs(frontier=("r1",))
        self.assertFalse(
            self._cleared(entry, epochs=epochs, anchor_version=5)
        )

    def test_anchor_version_advance_clears_no_l3(self):
        # The SAME anchor's per-anchor storage version advanced past the
        # decline cursor: THIS anchor's L3 coverage genuinely changed (a
        # write ack / restore read-back on its own chain), so the park
        # clears.
        entry = _neg(reason=NO_L3, cursor=5, anchor=1)
        epochs = _epochs(frontier=("r1",))
        self.assertTrue(
            self._cleared(entry, epochs=epochs, anchor_version=6)
        )

    def test_global_l3_publish_advance_does_not_clear_no_l3(self):
        # phase2-peranchor: the GLOBAL l3_publish diagnostic epoch advanced
        # (an unrelated chain wrote) but this anchor's per-anchor version is
        # unchanged -- the park must NOT clear. This is the frozen root
        # cause regression guard: previously the global advance re-armed the
        # park (the obsolesced-agent churn).
        entry = _neg(reason=NO_L3, cursor=5, anchor=1)
        epochs = _epochs(l3=99, frontier=("r1",))
        self.assertFalse(
            self._cleared(entry, epochs=epochs, anchor_version=5)
        )

    def test_reanchored_to_different_anchor_clears_no_l3(self):
        # The request now anchors a DIFFERENT node (miss proven on anchor 1,
        # now anchored on 2): a new candidate -- the old negative evidence
        # does not apply.
        entry = _neg(reason=NO_L3, cursor=5, anchor=1)
        epochs = _epochs(frontier=("r1",))
        view = _view("r1", NONE, eligible=True, req=_req("r1", anchor=2))
        self.assertTrue(
            self._cleared(
                entry,
                view=view,
                epochs=epochs,
                anchor_version=5,
            )
        )

    def test_no_anchor_context_never_cleared_on_epoch(self):
        # No anchor context on the park (an old-style entry with anchor=None)
        # but the request has an anchor now: conservative -- it is not
        # re-probed by the global epoch either (phase2-peranchor contract:
        # the global diagnostic counter never clears a NO_L3 park).
        entry = _neg(reason=NO_L3, cursor=5, anchor=None)
        epochs = _epochs(l3=99, frontier=("r1",))
        self.assertFalse(
            self._cleared(entry, epochs=epochs, anchor_version=7)
        )

    def test_no_l3_not_cleared_by_other_epochs(self):
        # A host-headroom or budget release is NOT causal for an L3 miss:
        # the full prefix is still not in L3.
        entry = _neg(reason=NO_L3, cursor=5, anchor=1)
        epochs = _epochs(headroom=10**9 + 100, spec=0, frontier=("r1",))
        self.assertFalse(
            self._cleared(entry, epochs=epochs, anchor_version=5)
        )

    def test_no_headroom_cleared_only_by_host_release(self):
        # Fix A: NO_HEADROOM subscribes to the MONOTONIC host_release
        # counter, NOT the transient available level. The park is recorded
        # at the release counter cursor observed at the decline.
        entry = _neg(reason=NO_HEADROOM, cursor=3)
        # An available-level rise is NOT causal: it is the transient signal
        # that flips 0->100->0 under a full working set and can never
        # sustain past the decline cursor (the B-run permanent freeze).
        self.assertFalse(
            self._cleared(entry, epochs=_epochs(l3=0, headroom=150, release=3))
        )
        # An L3 publish advance does not free the host pages: not causal.
        self.assertFalse(self._cleared(entry, epochs=_epochs(l3=500, release=3)))
        # Budget release is not causal for headroom.
        self.assertFalse(self._cleared(entry, epochs=_epochs(release=3, spec=0)))
        # A genuine host-capacity-releasing event advanced the release
        # counter past the decline cursor: the park clears.
        self.assertTrue(self._cleared(entry, epochs=_epochs(release=4)))
        # Same level, same counter: still parked.
        self.assertFalse(self._cleared(entry, epochs=_epochs(headroom=150, release=3)))

    def test_no_headroom_not_cleared_by_level_only_when_release_stalls(self):
        # The B-run freeze shape: headroom oscillates (0 -> 100 -> 0) with
        # no releasing event. The available LEVEL alone must never clear the
        # park, exactly as it never did in the OLD host_headroom-sample
        # subscription (the transient rise to 100 recorded a cursor that
        # the next alloc re-crossed before the refill ever ran).
        entry = _neg(reason=NO_HEADROOM, cursor=7)
        for level in (80, 100, 0, 100, 0):
            self.assertFalse(
                self._cleared(
                    entry, epochs=_epochs(headroom=level, release=7, spec=0)
                )
            )
        # The FIRST genuine release (counter 8) clears the park.
        self.assertTrue(self._cleared(entry, epochs=_epochs(release=8)))

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
        # causal condition is otherwise met. Here the causal condition is the
        # SAME anchor's version advancing (5 -> 8), not the global epoch.
        entry = _neg(reason=NO_L3, cursor=5, fuse_expiry=20.0, anchor=1)
        # Fuse not expired: not cleared even with the anchor version advanced.
        self.assertFalse(
            self._cleared(entry, epochs=_epochs(), now=10.0, anchor_version=8)
        )
        # Fuse expired AND the anchor's version advanced: cleared.
        self.assertTrue(
            self._cleared(entry, epochs=_epochs(), now=25.0, anchor_version=8)
        )
        # Fuse expired but the anchor's version is UNCHANGED (5): still held
        # -- the deterministic miss is not transient, time alone never clears.
        self.assertFalse(
            self._cleared(entry, epochs=_epochs(), now=25.0, anchor_version=5)
        )

    def test_subscribe_decline_no_entry_eligible(self):
        # No park = never attempted = eligible for the one fresh probe.
        self.assertTrue(
            _policy().subscribe_decline(None, _view("r1", NONE, eligible=True), _epochs(), 0.0)
        )

    def test_staging_candidates_excludes_parked_rid(self):
        # The rid is parked on NO_L3 at anchor 1 version 5; the tree's anchor
        # 1 version is still 5, so it stays parked (not re-probed) -- even
        # though the global l3_publish epoch is high.
        views = _views(("r1", NONE, None, 0, 0, True))
        negs = {"r1": _neg(reason=NO_L3, cursor=5, anchor=1)}
        epochs = _epochs(l3=99, frontier=("r1",))
        got = [
            v.rid
            for v in _policy().staging_candidates(
                views,
                tree=_tree(anchor_versions={1: 5}),
                cc=_Cc(),
                negatives=negs,
                epochs=epochs,
                now=0.0,
            )
        ]
        self.assertEqual(got, [])

    def test_staging_candidates_includes_rearmed_rid(self):
        # The SAME anchor's version advanced to 6 past the decline cursor: the
        # park clears and the rid is re-eligible for its one fresh probe.
        views = _views(("r1", NONE, None, 0, 0, True))
        negs = {"r1": _neg(reason=NO_L3, cursor=5, anchor=1)}
        epochs = _epochs(frontier=("r1",))
        got = [
            v.rid
            for v in _policy().staging_candidates(
                views,
                tree=_tree(anchor_versions={1: 6}),
                cc=_Cc(),
                negatives=negs,
                epochs=epochs,
                now=0.0,
            )
        ]
        self.assertEqual(got, ["r1"])


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

    def _epoch(self, l3=0, headroom=1000, spec=0, frontier=("r1",), release=0):
        return CausalEpochs(
            l3_publish=l3,
            host_headroom=headroom,
            spec_budget=spec,
            waiting_frontier=frontier,
            host_release=release,
        )

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

    def test_host_release_counter_advance_is_event(self):
        # Fix A: a genuine capacity-releasing event (host residency freed,
        # ready eviction, working-state release) -- even at a FLAT
        # available level (the freed pages were immediately re-consumed by
        # the working set) -- advances the release counter and must fire
        # the refill event gate.
        prev = self._epoch(headroom=100, release=0)
        after = self._epoch(headroom=100, release=1)
        self.assertTrue(_policy().epoch_event(prev, after))

    def test_host_release_counter_stall_releases_only_once(self):
        # The B-run freeze shape quantized: available bounces 0->100->0 at
        # a STALLED release counter. The event gate may fire on a level
        # rise (that is a legitimate refill-check trigger), but the PARK
        # (test_no_headroom_* below) is what must not clear: it subscribes
        # to the MONOTONIC release counter, so a release epoch advance
        # (0 -> 1) fires exactly once -- the next identical snapshot does
        # not fire again (no per-pass spin from a counter that never
        # recedes).
        prev = self._epoch(headroom=0, release=0)
        self.assertTrue(_policy().epoch_event(prev, self._epoch(headroom=0, release=1)))
        # Same release epoch, same level: no NEW event (the refill already
        # ran on the 0->1 advance).
        self.assertFalse(
            _policy().epoch_event(self._epoch(headroom=0, release=1), self._epoch(headroom=0, release=1))
        )

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
    anchor_versions=None,
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
    scheduler.tree_cache = tree_cache or _tree(
        l3_publish=l3_publish, anchor_versions=anchor_versions
    )
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

    def _issue(req, *, origin, demand_restore=False):
        # Mirror the real T1 wiring: a successful issue transitions the
        # request to RESTORING, so it leaves the candidate set.
        attempt_id = f"{req.rid}:prefetch:1"
        req.hicache_prefetch_active_attempt_id = attempt_id
        req.hicache_restore_state = RESTORING
        scheduler.issued.append(req.rid)
        scheduler.issue_origins.append(origin)
        return PrefetchIssueResult(
            status=PrefetchIssueResult.ISSUED,
            attempt_id=attempt_id,
            origin=origin,
            reason="issued",
            state_before=NONE.name,
            state_after=RESTORING.name,
        )

    scheduler._prefetch_kvcache = _issue
    scheduler.issue_origins = []
    return scheduler


class ReadyHorizonPassTests(unittest.TestCase):
    """_ready_horizon_pass: frontier views, causal-epoch-gated refill,
    delegation to _prefetch_kvcache, change-driven [P3] logging."""

    def _run(self, scheduler):
        scheduler._ready_horizon_pass()

    def _clock_patch(self):
        clock = _FakeClock()
        return mock.patch(
            "sglang.srt.managers.scheduler.time.perf_counter", new=clock
        ), clock

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

    def test_active_prefetch_claim_blocks_duplicate_and_classifies_retry(self):
        scheduler = Scheduler.__new__(Scheduler)
        req = SimpleNamespace(
            rid="r1",
            hicache_prefetch_attempt_seq=0,
            hicache_prefetch_active_attempt_id=None,
            hicache_prefetch_active_origin=None,
            hicache_prefetch_last_attempt_id=None,
            hicache_prefetch_last_origin=None,
        )
        impl_calls = []

        def impl(req, *, origin, demand_restore=False):
            impl_calls.append((origin, demand_restore))
            return PrefetchIssueResult.ISSUED

        scheduler._prefetch_kvcache_impl = impl

        first = scheduler._prefetch_kvcache(
            req, origin=HiCachePrefetchOrigin.READY_HORIZON
        )
        second = scheduler._prefetch_kvcache(
            req, origin=HiCachePrefetchOrigin.READY_HORIZON
        )

        self.assertIs(first, PrefetchIssueResult.ISSUED)
        self.assertIs(second, PrefetchIssueResult.ACTIVE)
        self.assertEqual(
            impl_calls, [(HiCachePrefetchOrigin.READY_HORIZON, False)]
        )

        scheduler._release_prefetch_claim(
            req, req.hicache_prefetch_active_attempt_id, "test_retry"
        )
        retry = scheduler._prefetch_kvcache(
            req,
            origin=HiCachePrefetchOrigin.DEMAND_RETRY,
            demand_restore=True,
        )
        self.assertIs(retry, PrefetchIssueResult.ISSUED)
        self.assertEqual(
            impl_calls,
            [
                (HiCachePrefetchOrigin.READY_HORIZON, False),
                (HiCachePrefetchOrigin.DEMAND_RETRY, True),
            ],
        )
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

    def test_no_headroom_park_wakes_on_release_epoch_not_level(self):
        # Fix A end-to-end (the B-run permanent-freeze regression):
        # 1) host headroom insufficient -> NO_HEADROOM park recorded at the
        #    release counter cursor;
        # 2) the level bounces (0 -> X -> 0) with NO release counter advance
        #    -> the park holds even past the safety fuse: no re-probe per
        #    pass (no busy loop), no silent release (the B-run freeze);
        # 3) a GENUINE release (available grew since the last snapshot ->
        #    the monotonic release counter advanced) wakes the waiter: the
        #    rid is re-probed and staged exactly once.
        patch, clock = self._clock_patch()
        with patch:
            cc = _Cc(spec_inflight=CHAIN_TOKENS, available=0)
            scheduler = _pass_scheduler(queue=[_req("r1", NONE)], cc=cc)
            epoch = scheduler.ready_horizon

            # Step 1: headroom gate fails (0 free + CHAIN_TOKENS inflight
            # + no READY footprint does not fit 0 headroom) -> the decline
            # parks r1 at release cursor 0.
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, [])
            entry = scheduler._ready_horizon_negatives.get("r1")
            self.assertIsNotNone(entry, "NO_HEADROOM decline must park the rid")
            self.assertEqual(entry.reason, NO_HEADROOM)
            self.assertEqual(entry.epoch_cursor, 0)  # release counter cursor

            # Step 2: the B-run shape quantized -- available oscillates
            # with no release-counter advance (the snapshot never sees a
            # sustained level rise), even past the safety fuse. The park
            # holds: no re-probe, no issue.
            for _ in range(3):
                clock.advance(10.0)
                cc.available = 0
                scheduler._ready_horizon_pass()
                self.assertEqual(scheduler.issued, [])
                self.assertEqual(
                    scheduler._ready_horizon_negatives["r1"].epoch_cursor,
                    0,
                    "no release epoch -> the park must not clear",
                )

            # Step 3: host residency freed / working-state released: the
            # available level GREW since the last snapshot -> the release
            # counter advances 0 -> 1 (a causal event). The park clears and
            # r1 is re-probed and staged once (past the fuse).
            clock.advance(10.0)
            cc.available = CHAIN_TOKENS
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1"])
            self.assertEqual(scheduler._ready_host_release_epoch, 1)

    def test_release_counter_monotonic_survives_reconsumption(self):
        # Fix A monotonicity at the pass level: a release (available grew
        # since the last snapshot -> counter 0 -> 1) that is IMMEDIATELY
        # re-consumed by the working set (available back to 0) must NOT
        # undo the park clear. The OLD host_headroom-LEVEL cursor would
        # re-park at the higher level and freeze (the B-run permanent
        # freeze root: a transient rise was each time recorded as a higher
        # cursor that the next alloc re-crossed before any re-probe).
        # New behavior: the release epoch advances ONCE; the park that was
        # at cursor 0 clears against cursor 1 even though the level
        # returned to 0; at most one fresh probe per release epoch.
        patch, clock = self._clock_patch()
        with patch:
            cc = _Cc(spec_inflight=CHAIN_TOKENS, available=0)
            scheduler = _pass_scheduler(queue=[_req("r1", NONE)], cc=cc)
            scheduler._ready_horizon_pass()
            self.assertEqual(
                scheduler._ready_horizon_negatives["r1"].epoch_cursor, 0
            )

            # Release observed (level rose), THEN the working set re-
            # consumes the freed pages before the refill ever runs: the
            # next snapshot sees available back at 0. The release epoch
            # advanced 0 -> 1 and stays there; the level is again 0.
            scheduler._ready_host_release_last_level = 0
            cc.available = CHAIN_TOKENS
            scheduler._ready_horizon_pass()  # snapshot: level rose (release)
            cc.available = 0
            clock.advance(10.0)  # past the safety fuse
            scheduler._ready_horizon_pass()  # snapshot: level fell (no release)
            self.assertEqual(scheduler._ready_host_release_epoch, 1)
            # The release epoch advanced past the park cursor 0 -> 1; the
            # headroom STILL fails (0 free) so the re-probe declines and
            # re-parks at the NEW cursor 1. No issue, no busy loop.
            self.assertEqual(scheduler.issued, [])
            self.assertEqual(
                scheduler._ready_horizon_negatives["r1"].epoch_cursor, 1
            )
            # The next identical pass (level 0, release epoch 1, fuse
            # expired): the re-park holds -- at most one probe per release
            # epoch, no freeze, no spin.
            clock.advance(10.0)
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, [])
            self.assertEqual(
                scheduler._ready_horizon_negatives["r1"].epoch_cursor, 1
            )

    def test_off_mode_is_a_noop(self):
        scheduler = _pass_scheduler(queue=[_req("r1", NONE)], enable=False)
        self._run(scheduler)
        self.assertEqual(scheduler.issued, [])

    def test_rh_on_enqueue_is_queue_first_and_rh_owned(self):
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.enable_priority_scheduling = False
        scheduler.abort_on_priority_when_disabled = False
        scheduler.disaggregation_mode = DisaggregationMode.NULL
        scheduler.max_queued_requests = None
        scheduler.waiting_queue = []
        scheduler.enable_ready_horizon = True
        scheduler.issued = []
        scheduler._prefetch_kvcache = mock.Mock()
        req = SimpleNamespace(
            rid="rh-on",
            priority=None,
            time_stats=SimpleNamespace(set_wait_queue_entry_time=mock.Mock()),
        )

        scheduler._add_request_to_queue(req)

        self.assertEqual(scheduler.waiting_queue, [req])
        scheduler._prefetch_kvcache.assert_not_called()

    def test_rh_off_enqueue_preserves_eager_order_and_origin(self):
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.enable_priority_scheduling = False
        scheduler.abort_on_priority_when_disabled = False
        scheduler.disaggregation_mode = DisaggregationMode.NULL
        scheduler.max_queued_requests = None
        scheduler.waiting_queue = []
        scheduler.enable_ready_horizon = False
        calls = []

        def issue(req, *, origin, demand_restore=False):
            calls.append((origin, len(scheduler.waiting_queue)))
            return PrefetchIssueResult.DECLINED

        scheduler._prefetch_kvcache = issue
        req = SimpleNamespace(
            rid="rh-off",
            priority=None,
            time_stats=SimpleNamespace(set_wait_queue_entry_time=mock.Mock()),
        )

        scheduler._add_request_to_queue(req)

        self.assertEqual(calls, [(HiCachePrefetchOrigin.EAGER_RH_OFF, 0)])
        self.assertEqual(scheduler.waiting_queue, [req])

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
            any("evt=ready_stage.v2 rid=r1" in m and "result=issued" in m for m in logs.output),
            logs.output,
        )

    def test_issue_decision_precedes_stage_with_claimed_attempt_id(self):
        scheduler = _pass_scheduler(queue=[_req("r1", NONE)])
        with self.assertLogs("sglang.srt.managers.scheduler", level="INFO") as logs:
            scheduler._ready_horizon_pass()
        decision = next(
            m for m in logs.output if "schema=rh_preadmission.v1" in m
        )
        stage = next(m for m in logs.output if "schema=rh_stage.v2" in m)
        self.assertIn("decision=issue", decision)
        self.assertIn("attempt_id=r1:prefetch:1", decision)
        self.assertIn("attempt_id=r1:prefetch:1", stage)
        self.assertLess(logs.output.index(decision), logs.output.index(stage))

    def test_failed_issue_is_hold_and_never_false_issue(self):
        scheduler = _pass_scheduler(queue=[_req("r1", NONE)])

        def decline(req, *, origin, demand_restore=False):
            return PrefetchIssueResult(
                status=PrefetchIssueResult.DECLINED,
                attempt_id="r1:prefetch:1",
                origin=origin,
                reason="declined_rate_limited",
                state_before=NONE.name,
                state_after=NONE.name,
            )

        scheduler._prefetch_kvcache = decline
        with self.assertLogs("sglang.srt.managers.scheduler", level="INFO") as logs:
            scheduler._ready_horizon_pass()
        decision = next(
            m for m in logs.output if "schema=rh_preadmission.v1" in m
        )
        stage = next(m for m in logs.output if "schema=rh_stage.v2" in m)
        self.assertIn("decision=hold", decision)
        self.assertIn("reason=physical_budget", decision)
        self.assertNotIn("decision=issue", decision)
        self.assertIn("result=held", stage)
        self.assertIn("reason=declined_rate_limited", stage)


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

    def _make_scheduler(self, cc=None, l3_publish=0, anchor_versions=None):
        cc = cc or _Cc()
        scheduler = _pass_scheduler(
            queue=[_req("r1", NONE)],
            cc=cc,
            l3_publish=l3_publish,
            anchor_versions=anchor_versions,
        )

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

    def test_anchor_version_advance_clears_and_reprobes_once(self):
        # phase2-peranchor: the park records the anchor's per-anchor version
        # (0 initially); a GLOBAL l3_publish advance alone does NOT clear it
        # (the frozen root cause -- the unrelated-chain bump), but the SAME
        # anchor's per-anchor version advancing (its own chain's durability
        # changed) + the expired fuse clears it and grants one fresh probe.
        patch, clock = self._clock_patch()
        with patch:
            cc = _Cc()
            scheduler, _ = self._make_scheduler(
                cc=cc, l3_publish=0, anchor_versions={1: 0}
            )
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1"])
            scheduler.waiting_queue[0].hicache_restore_state = NONE
            scheduler.tree_cache.record_storage_prefetch_terminal("r1", "revoked_miss")
            scheduler._feed_restore_terminal(scheduler.waiting_queue[0])
            entry = scheduler._ready_horizon_negatives["r1"]
            self.assertEqual(entry.reason, NO_L3)
            self.assertEqual(entry.epoch_cursor, 0)
            self.assertEqual(entry.anchor, 1)

            # Fuse still live: even with the anchor's version advanced the
            # park holds (the rate bound, not the retry cadence).
            scheduler.tree_cache.anchor_storage_version = lambda n: 3
            cc.inflight_speculative_tokens = 0
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1"])

            # Fuse expired AND the SAME anchor's version advanced: the park
            # clears and the rid gets its one fresh probe.
            clock.advance(10.0)
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1", "r1"])

    def test_unrelated_chain_global_bump_never_clears_no_l3(self):
        # The frozen root cause regression: the global l3_publish epoch
        # advanced to 3 (an unrelated chain's write ack / restore) while
        # THIS anchor's per-anchor version is still 0. The NO_L3 park must
        # hold even past the fuse -- the unrelated durability event is not
        # causal for this candidate's miss.
        patch, clock = self._clock_patch()
        with patch:
            cc = _Cc()
            scheduler, _ = self._make_scheduler(
                cc=cc, l3_publish=0, anchor_versions={1: 0}
            )
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1"])
            scheduler.waiting_queue[0].hicache_restore_state = NONE
            scheduler.tree_cache.record_storage_prefetch_terminal("r1", "revoked_miss")
            scheduler._feed_restore_terminal(scheduler.waiting_queue[0])
            self.assertEqual(scheduler._ready_horizon_negatives["r1"].reason, NO_L3)

            # Unrelated-chain global bump + fuse expired.
            scheduler.tree_cache.l3_publish_epoch = lambda: 42
            cc.inflight_speculative_tokens = 0
            clock.advance(10.0)
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1"], "unrelated global bump must not re-arm")

    def test_after_reprobe_miss_reparks_at_new_cursor(self):
        patch, clock = self._clock_patch()
        with patch:
            cc = _Cc()
            scheduler, _ = self._make_scheduler(
                cc=cc, l3_publish=0, anchor_versions={1: 0}
            )
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1"])
            scheduler.waiting_queue[0].hicache_restore_state = NONE
            scheduler.tree_cache.record_storage_prefetch_terminal("r1", "revoked_miss")
            scheduler._feed_restore_terminal(scheduler.waiting_queue[0])
            entry1 = scheduler._ready_horizon_negatives["r1"]
            self.assertEqual(entry1.epoch_cursor, 0)

            # The SAME anchor's version advances and the fuse expires: the
            # rid reprobes, misses again, and re-parks at the NEW cursor.
            scheduler.tree_cache.anchor_storage_version = lambda n: 1
            cc.inflight_speculative_tokens = 0
            clock.advance(10.0)
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1", "r1"])
            # The second miss lands (the drain records the revoked_miss
            # terminal); the re-park records the NEW anchor version cursor.
            scheduler.waiting_queue[0].hicache_restore_state = NONE
            scheduler.tree_cache.record_storage_prefetch_terminal("r1", "revoked_miss")
            scheduler._feed_restore_terminal(scheduler.waiting_queue[0])
            entry2 = scheduler._ready_horizon_negatives["r1"]
            self.assertEqual(entry2.epoch_cursor, 1)

            # Same causal epoch (cursor still 1) even with the fuse expired
            # again and an unrelated global bump: the next event pass holds
            # the park -- at most one staging attempt per rid per causal
            # anchor-version.
            clock.advance(10.0)
            scheduler.waiting_queue[0].hicache_restore_state = NONE
            cc.inflight_speculative_tokens = 0
            cc.available += 1
            scheduler._ready_horizon_pass()
            self.assertEqual(scheduler.issued, ["r1", "r1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
