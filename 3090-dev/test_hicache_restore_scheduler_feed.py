"""P2-IO T15 scheduler wiring: the drain's revoked_backup_pending terminal
parks the request in WAIT[BACKUP_PENDING] and registers the M2 frontier
waiter, and the per-pass T11 predicate wakes it exactly when the chain's
durable frontier crosses the request's end with a DEMAND_RESTORE ticket
free -- the re-issue bypasses the speculative PREFETCH_BUDGET only.

Guards the scheduler-side mapping only (the state-machine semantics live in
test_hicache_restore.py): which future diff turns this red -- one that
drops the revoked_backup_pending branch of _feed_restore_terminal (the
terminal would fall through to revoked_miss and the request would recompute
mid-backup instead of waiting), one that removes the BACKUP_PENDING
predicate from _restore_wait_capacity_fits (the wait would then be unable
to wake and would idle out the full T13 clock), or one that drops the
demand_restore flag from the wake re-issue (the re-issue would hit the
PREFETCH_BUDGET again -- the e4 denied-rate loop).
"""

import time
import unittest
from types import SimpleNamespace

import sglang.srt.managers.scheduler as scheduler_mod
from sglang.srt.managers.scheduler import Scheduler
from sglang.srt.managers.scheduler_components.hicache_restore import (
    RestoreEvent,
    RestoreState,
    RestoreWaitReason,
    HiCachePrefetchOrigin,
)


class BackupPendingSchedulerFeedTests(unittest.TestCase):
    def _scheduler(self, tree_cache):
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.server_args = SimpleNamespace(hicache_restore_wait_timeout_s=60.0)
        scheduler.tree_cache = tree_cache
        scheduler.enable_hicache_storage = True
        # P3 Ready Horizon (3.1): off default keeps the pre-P3 T11/T12
        # wake classification these tests assert.
        scheduler.enable_ready_horizon = False
        return scheduler

    def _req(self):
        return SimpleNamespace(
            rid="r1",
            last_host_node=42,
            hicache_restore_state=None,
            hicache_restore_wait_reason=None,
            hicache_restore_state_ts=0.0,
            hicache_restore_miss_epoch=None,
            hicache_restore_miss_generation=None,
        )

    def test_backup_pending_terminal_parks_and_registers_waiter(self):
        # The drain recorded revoked_backup_pending: _feed_restore_terminal
        # must land the request in WAIT[BACKUP_PENDING] (not recompute) and
        # register the frontier waiter keyed by the anchor, so the backup
        # ACK drain / per-pass predicate can wake it.
        registrations = []
        tree_cache = SimpleNamespace(
            pop_storage_prefetch_terminal=lambda rid: "revoked_backup_pending",
            register_frontier_waiter=lambda rid, node: registrations.append(
                (rid, node)
            ),
        )
        scheduler = self._scheduler(tree_cache)
        req = self._req()

        scheduler._feed_restore_terminal(req)

        self.assertIs(req.hicache_restore_state, RestoreState.WAIT_CAPACITY)
        self.assertIs(
            req.hicache_restore_wait_reason, RestoreWaitReason.BACKUP_PENDING
        )
        self.assertEqual(registrations, [("r1", 42)])
        self.assertGreater(req.hicache_restore_state_ts, 0.0)

    def test_backup_pending_terminal_is_not_a_miss(self):
        # The terminal must not fall through to the revoked_miss branch:
        # a genuine-miss revoke degrades to recompute, which would restart
        # the chain mid-backup instead of waiting for its completion.
        tree_cache = SimpleNamespace(
            pop_storage_prefetch_terminal=lambda rid: "revoked_backup_pending",
            register_frontier_waiter=lambda rid, node: None,
        )
        scheduler = self._scheduler(tree_cache)
        req = self._req()

        scheduler._feed_restore_terminal(req)

        self.assertIsNot(req.hicache_restore_state, RestoreState.NONE)
        self.assertIs(req.hicache_restore_state, RestoreState.WAIT_CAPACITY)

    def test_wake_predicate_false_while_durable_frontier_behind(self):
        # The T11 predicate must NOT wake the wait while the chain's
        # durable frontier is still behind the request's end: waking
        # re-issues the lookup into the same partial chain every pass --
        # the poll loop the T15 park replaces.
        tree_cache = SimpleNamespace(
            backup_wait_ready=lambda rid: False,
            demand_restore_inflight=lambda: 0,
        )
        scheduler = self._scheduler(tree_cache)
        req = self._req()
        req.hicache_restore_state = RestoreState.WAIT_CAPACITY
        req.hicache_restore_wait_reason = RestoreWaitReason.BACKUP_PENDING

        self.assertFalse(scheduler._restore_wait_capacity_fits(req))

    def test_wake_predicate_true_after_frontier_crosses(self):
        # The ACK drain advances the durable frontier across the request's
        # end (backup_wait_ready) and a ticket is free: the predicate
        # flips and the wake re-issues the lookup exactly once.
        tree_cache = SimpleNamespace(
            backup_wait_ready=lambda rid: True,
            demand_restore_inflight=lambda: 0,
        )
        scheduler = self._scheduler(tree_cache)
        req = self._req()
        req.hicache_restore_state = RestoreState.WAIT_CAPACITY
        req.hicache_restore_wait_reason = RestoreWaitReason.BACKUP_PENDING

        self.assertTrue(scheduler._restore_wait_capacity_fits(req))

    def test_wake_held_while_demand_tickets_exhausted(self):
        # Thundering herd: the frontier crossed for a whole wake batch at
        # once, but the DEMAND_RESTORE pool is full (4 in flight). The
        # predicate holds the wake -- bounded concurrency, no stampede --
        # and the per-pass re-check wakes it when a ticket frees.
        tree_cache = SimpleNamespace(
            backup_wait_ready=lambda rid: True,
            demand_restore_inflight=lambda: 4,
        )
        scheduler = self._scheduler(tree_cache)
        req = self._req()
        req.hicache_restore_state = RestoreState.WAIT_CAPACITY
        req.hicache_restore_wait_reason = RestoreWaitReason.BACKUP_PENDING

        self.assertFalse(scheduler._restore_wait_capacity_fits(req))

    def test_backup_pending_wake_reissues_as_demand_restore(self):
        # End-to-end step 4: the T11 wake of a BACKUP_PENDING wait
        # re-issues the prefetch with the DEMAND_RESTORE flag (past the
        # speculative PREFETCH_BUDGET), not as a plain speculative
        # prefetch -- the e4 denied-rate loop must not come back.
        orig_get_memory = scheduler_mod.get_memory
        scheduler_mod.get_memory = lambda: SimpleNamespace(
            hicache_storage_prefetch_retry_poll_interval=0,
            hicache_storage_prefetch_retry_max_attempts=0,
        )
        try:
            issued = []
            tree_cache = SimpleNamespace(
                pop_storage_prefetch_terminal=lambda rid: None,
                pop_storage_prefetch_miss=lambda rid: False,
                pop_frontier_ready=lambda rid: False,
                backup_wait_ready=lambda rid: True,
                demand_restore_inflight=lambda: 0,
                discard_frontier_waiter=lambda rid: None,
            )
            scheduler = self._scheduler(tree_cache)
            scheduler.waiting_queue = [self._req()]
            req = scheduler.waiting_queue[0]
            req.hicache_restore_state = RestoreState.WAIT_CAPACITY
            req.hicache_restore_wait_reason = RestoreWaitReason.BACKUP_PENDING
            req.hicache_restore_state_ts = time.perf_counter()
            scheduler._prefetch_kvcache = lambda r, *, origin, demand_restore=False: (
                issued.append(demand_restore)
            )

            scheduler._reconcile_restore_states()

            self.assertEqual(issued, [True])
            self.assertIs(req.hicache_restore_state, RestoreState.RESTORING)
        finally:
            scheduler_mod.get_memory = orig_get_memory

    def test_quota_deny_semantics_unchanged(self):
        # T6 (admission deny) still lands WAIT[DEVICE_QUOTA] -- the T15
        # machinery must not touch the quota-deny path.
        tree_cache = SimpleNamespace(
            pop_storage_prefetch_terminal=lambda rid: None,
        )
        scheduler = self._scheduler(tree_cache)
        req = self._req()
        scheduler._apply_restore_event(req, RestoreEvent.ADMISSION_DENY)
        self.assertIs(req.hicache_restore_state, RestoreState.WAIT_CAPACITY)
        self.assertIs(
            req.hicache_restore_wait_reason, RestoreWaitReason.DEVICE_QUOTA
        )


class CapacitySemanticsSchedulerFeedTests(unittest.TestCase):
    """P4 post-guard capacity semantics: positive hit allocation failure is
    a HOST_ALLOC wait, while a resident short suffix is admitted directly."""

    def _scheduler(self, tree_cache):
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.server_args = SimpleNamespace(hicache_restore_wait_timeout_s=60.0)
        scheduler.tree_cache = tree_cache
        scheduler.enable_hicache_storage = True
        scheduler.enable_ready_horizon = False
        scheduler.page_size = 16
        return scheduler

    def _req(self):
        return SimpleNamespace(
            rid="r1",
            last_host_node=42,
            hicache_restore_state=RestoreState.RESTORING,
            hicache_restore_wait_reason=None,
            hicache_restore_state_ts=0.0,
            hicache_restore_miss_epoch=None,
            hicache_restore_miss_anchor=None,
            hicache_restore_miss_generation=None,
        )

    def test_positive_alloc_failure_maps_to_host_capacity_wait(self):
        tree_cache = SimpleNamespace(
            pop_storage_prefetch_terminal=lambda rid: "revoked_alloc_failed",
            pop_host_alloc_failure=lambda rid: None,
        )
        scheduler = self._scheduler(tree_cache)
        req = self._req()

        scheduler._feed_restore_terminal(req)

        self.assertIs(req.hicache_restore_state, RestoreState.WAIT_CAPACITY)
        self.assertIs(req.hicache_restore_wait_reason, RestoreWaitReason.HOST_ALLOC)
        self.assertIsNone(req.hicache_restore_miss_epoch)
        self.assertIsNone(req.hicache_restore_miss_anchor)
        self.assertIsNone(req.hicache_restore_miss_generation)

    def test_host_alloc_wait_wakes_for_complete_requested_span(self):
        available = [54976]
        tree_cache = SimpleNamespace(
            cache_controller=SimpleNamespace(
                prefetch_rate_limited=lambda: False,
                mem_pool_host=SimpleNamespace(available_size=lambda: available[0]),
            ),
            prefetch_threshold=256,
        )
        scheduler = self._scheduler(tree_cache)
        req = self._req()
        req.hicache_restore_state = RestoreState.WAIT_CAPACITY
        req.hicache_restore_wait_reason = RestoreWaitReason.HOST_ALLOC
        req.prefix_indices = []
        req.host_hit_length = 0
        req.full_untruncated_fill_ids = list(range(55000))
        req._compute_max_prefix_len = lambda input_len: 55000

        self.assertTrue(scheduler._restore_wait_capacity_fits(req))
        available[0] = 54992
        self.assertTrue(scheduler._restore_wait_capacity_fits(req))

    def test_resident_short_tail_does_not_enter_revalidate(self):
        marker = ["r1"]
        tree_cache = SimpleNamespace(
            hicache_storage_pass_prefix_keys=False,
            prefetch_threshold=256,
            is_root=lambda node: node == 0,
            prefetch_gate_ok=lambda node, buffer_mode: True,
            get_last_hash_value=lambda node: "tail",
            prefetch_from_storage=lambda *args, **kwargs: "declined_too_short",
            pop_storage_prefetch_miss=lambda rid: marker.remove(rid) is None,
            pop_host_alloc_failure=lambda rid: None,
            node_exists=lambda node: False,
            is_l3_durable=lambda node: False,
        )
        scheduler = self._scheduler(tree_cache)
        scheduler.server_args.hicache_host_memory_mode = "cache"
        req = self._req()
        req.hicache_restore_state = RestoreState.NONE
        req.prefix_indices = list(range(54976))
        req.host_hit_length = 0
        req.full_untruncated_fill_ids = list(range(55000))
        req.init_next_round_input = lambda *args, **kwargs: None
        req._compute_max_prefix_len = lambda input_len: 55000

        scheduler._prefetch_kvcache(req, origin=HiCachePrefetchOrigin.DEMAND_RETRY)

        self.assertIs(req.hicache_restore_state, RestoreState.NONE)
        self.assertIsNone(req.hicache_restore_wait_reason)
        self.assertEqual(len(req.prefix_indices), 54976)
        self.assertEqual(marker, [])


class P1StickyMissSchedulerFeedTests(unittest.TestCase):
    """P1 restore re-arm churn: the T9 miss records the L3 publish epoch +
    generation evidence, and the T6 admission re-arm gate refuses to re-arm
    WAIT while the sticky miss holds (same epoch, same generation) -- the
    request recomputes forward instead of churning."""

    def _scheduler(self, tree_cache):
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.server_args = SimpleNamespace(hicache_restore_wait_timeout_s=60.0)
        scheduler.tree_cache = tree_cache
        scheduler.enable_hicache_storage = True
        scheduler.enable_ready_horizon = False
        return scheduler

    def _req(self, generation=None):
        return SimpleNamespace(
            rid="r1",
            last_host_node=42,
            hicache_restore_state=None,
            hicache_restore_wait_reason=None,
            hicache_restore_state_ts=0.0,
            hicache_restore_miss_epoch=None,
            hicache_restore_miss_generation=None,
            hicache_restore_miss_anchor=None,
            session_generation=generation,
            host_hit_length=0,
            full_untruncated_fill_ids=[0, 1, 2, 3, 4, 5, 6, 7],
        )

    def test_genuine_miss_records_epoch_and_generation(self):
        # The drain terminal revoked_miss: _feed_restore_terminal must land
        # the request in MISS_RECOMPUTE and record the ANCHOR's per-anchor
        # storage version at which the miss was proven (phase2-peranchor)
        # plus the anchor node and the identity generation.
        tree_cache = SimpleNamespace(
            pop_storage_prefetch_terminal=lambda rid: "revoked_miss",
            l3_publish_epoch=lambda: 7,
            node_exists=lambda nid: False,
            anchor_storage_version=lambda nid: 9,
        )
        scheduler = self._scheduler(tree_cache)
        req = self._req(generation=3)
        req.hicache_restore_state = RestoreState.RESTORING

        scheduler._feed_restore_terminal(req)

        self.assertIs(req.hicache_restore_state, RestoreState.MISS_RECOMPUTE)
        self.assertEqual(req.hicache_restore_miss_epoch, 9)
        self.assertEqual(req.hicache_restore_miss_anchor, 42)
        self.assertEqual(req.hicache_restore_miss_generation, 3)

    def test_same_epoch_miss_not_rearmed(self):
        # A MISS_RECOMPUTE request denied at admission with an unchanged L3
        # publish epoch and matching generation must NOT re-enter
        # WAIT[DEVICE_QUOTA] -- the request recomputes forward instead of
        # re-probing the same missing prefix (the churn).
        epoch = 7
        tree_cache = SimpleNamespace(
            pop_storage_prefetch_terminal=lambda rid: None,
            l3_publish_epoch=lambda: epoch,
            has_restore_potential=lambda *a, **k: True,
        )
        scheduler = self._scheduler(tree_cache)
        req = self._req(generation=3)
        req.hicache_restore_state = RestoreState.MISS_RECOMPUTE
        req.hicache_restore_miss_epoch = 7
        req.hicache_restore_miss_generation = 3

        scheduler._apply_restore_event(
            req, RestoreEvent.ADMISSION_DENY, rearm_allowed=False
        )

        self.assertIs(req.hicache_restore_state, RestoreState.MISS_RECOMPUTE)
        self.assertIsNone(req.hicache_restore_wait_reason)
        # The sticky evidence survives.
        self.assertEqual(req.hicache_restore_miss_epoch, 7)

    def test_epoch_advance_rearms_miss(self):
        # The L3 publish epoch advanced past the miss probe: the cache
        # coverage may really have changed, so the miss no longer binds and
        # the request re-arms into WAIT[DEVICE_QUOTA].
        tree_cache = SimpleNamespace(
            pop_storage_prefetch_terminal=lambda rid: None,
            l3_publish_epoch=lambda: 8,
        )
        scheduler = self._scheduler(tree_cache)
        req = self._req(generation=3)
        req.hicache_restore_state = RestoreState.MISS_RECOMPUTE
        req.hicache_restore_miss_epoch = 7
        req.hicache_restore_miss_generation = 3

        scheduler._apply_restore_event(
            req, RestoreEvent.ADMISSION_DENY, rearm_allowed=True
        )

        self.assertIs(req.hicache_restore_state, RestoreState.WAIT_CAPACITY)
        self.assertIs(
            req.hicache_restore_wait_reason, RestoreWaitReason.DEVICE_QUOTA
        )
        # Leaving the sticky state drops the negative evidence.
        self.assertIsNone(req.hicache_restore_miss_epoch)
        self.assertIsNone(req.hicache_restore_miss_generation)

    def test_generation_change_rearms_miss(self):
        # Same epoch but a new identity (generation): the old miss evidence
        # does not apply to this prefix's new identity, so it re-arms.
        tree_cache = SimpleNamespace(
            pop_storage_prefetch_terminal=lambda rid: None,
            l3_publish_epoch=lambda: 7,
        )
        scheduler = self._scheduler(tree_cache)
        req = self._req(generation=4)
        req.hicache_restore_state = RestoreState.MISS_RECOMPUTE
        req.hicache_restore_miss_epoch = 7
        req.hicache_restore_miss_generation = 3

        scheduler._apply_restore_event(
            req, RestoreEvent.ADMISSION_DENY, rearm_allowed=True
        )

        self.assertIs(req.hicache_restore_state, RestoreState.WAIT_CAPACITY)

    def test_forward_ready_drops_sticky_evidence(self):
        # A successful restore leaves MISS via the override: the re-arm
        # gate clears the negative evidence on the way out.
        tree_cache = SimpleNamespace(
            pop_storage_prefetch_terminal=lambda rid: None,
            l3_publish_epoch=lambda: 7,
        )
        scheduler = self._scheduler(tree_cache)
        req = self._req(generation=3)
        req.hicache_restore_state = RestoreState.MISS_RECOMPUTE
        req.hicache_restore_miss_epoch = 7
        req.hicache_restore_miss_generation = 3

        scheduler._apply_restore_event(
            req, RestoreEvent.ADMISSION_DENY, rearm_allowed=True
        )
        # Re-issue leg -> RESTORING -> READY.
        scheduler._apply_restore_event(req, RestoreEvent.PREFETCH_ISSUED)
        scheduler._apply_restore_event(req, RestoreEvent.FINALIZED)

        self.assertIs(req.hicache_restore_state, RestoreState.READY)
        self.assertIsNone(req.hicache_restore_miss_epoch)

    def test_repeated_invocation_idempotent(self):
        # Repeated re-arm-gate checks with unchanged epoch/generation stay
        # refused every time -- the gate is idempotent and never flips on
        # its own (recompute is the only correct forward exit).
        tree_cache = SimpleNamespace(
            pop_storage_prefetch_terminal=lambda rid: None,
            l3_publish_epoch=lambda: 7,
        )
        scheduler = self._scheduler(tree_cache)
        req = self._req(generation=3)
        req.hicache_restore_state = RestoreState.MISS_RECOMPUTE
        req.hicache_restore_miss_epoch = 7
        req.hicache_restore_miss_generation = 3

        for _ in range(3):
            scheduler._apply_restore_event(
                req, RestoreEvent.ADMISSION_DENY, rearm_allowed=False
            )
            self.assertIs(req.hicache_restore_state, RestoreState.MISS_RECOMPUTE)
            self.assertIsNone(req.hicache_restore_wait_reason)

    def _rearm_scheduler(self, tree_cache):
        """A scheduler whose T6 re-arm reads the tree's anchor version via
        the real `_anchor_version_or_zero` helper."""
        scheduler = self._scheduler(tree_cache)
        return scheduler

    def _rearm_gate(self, scheduler, req):
        """Compute the per-anchor re-arm verdict exactly as the admission
        loop does (scheduler.py T6, now the explicit three-branch
        `_miss_rearm_decision`) and feed it into the state machine."""
        miss_rearm = scheduler._miss_rearm_decision(req)
        return scheduler._apply_restore_event(
            req, RestoreEvent.ADMISSION_DENY, rearm_allowed=miss_rearm
        )

    def test_global_epoch_advance_does_not_rearm_same_anchor(self):
        # phase2-peranchor (frozen root cause): the GLOBAL l3_publish epoch
        # advanced (an unrelated chain's write ack bumped it to 99) while
        # THIS request's anchor version is unchanged (still 5). The T6 re-arm
        # must NOT re-enter WAIT -- the unrelated durability event is not
        # causal for this candidate's miss. Previously this re-armed (the
        # current_epoch > miss_epoch global test) -- the churn.
        tree_cache = SimpleNamespace(
            pop_storage_prefetch_terminal=lambda rid: None,
            l3_publish_epoch=lambda: 99,  # unrelated global bump
            anchor_storage_version=lambda nid: 5,  # this anchor unchanged
            node_exists=lambda nid: True,
        )
        scheduler = self._rearm_scheduler(tree_cache)
        req = self._req(generation=3)
        req.hicache_restore_state = RestoreState.MISS_RECOMPUTE
        req.hicache_restore_miss_epoch = 5
        req.hicache_restore_miss_anchor = 42
        req.hicache_restore_miss_generation = 3

        self._rearm_gate(scheduler, req)

        self.assertIs(req.hicache_restore_state, RestoreState.MISS_RECOMPUTE)
        self.assertIsNone(req.hicache_restore_wait_reason)
        self.assertEqual(req.hicache_restore_miss_epoch, 5)

    def test_same_anchor_version_advance_rearms(self):
        # The SAME anchor's per-anchor version advanced past the miss probe
        # (5 -> 6): THIS anchor's L3 coverage genuinely changed (a write ack
        # promotion / restore read-back / clear on its own chain), so the
        # miss no longer binds and the request re-arms into WAIT.
        tree_cache = SimpleNamespace(
            pop_storage_prefetch_terminal=lambda rid: None,
            l3_publish_epoch=lambda: 5,
            anchor_storage_version=lambda nid: 6,
            node_exists=lambda nid: True,
        )
        scheduler = self._rearm_scheduler(tree_cache)
        req = self._req(generation=3)
        req.hicache_restore_state = RestoreState.MISS_RECOMPUTE
        req.hicache_restore_miss_epoch = 5
        req.hicache_restore_miss_anchor = 42
        req.hicache_restore_miss_generation = 3

        self._rearm_gate(scheduler, req)

        self.assertIs(req.hicache_restore_state, RestoreState.WAIT_CAPACITY)
        self.assertIs(
            req.hicache_restore_wait_reason, RestoreWaitReason.DEVICE_QUOTA
        )

    def test_reanchor_to_different_node_rearms(self):
        # The request re-anchored to a DIFFERENT node (was 42, now 77): a
        # new candidate -- the old miss evidence does not apply, so it
        # re-arms even with an unchanged version.
        tree_cache = SimpleNamespace(
            pop_storage_prefetch_terminal=lambda rid: None,
            l3_publish_epoch=lambda: 5,
            anchor_storage_version=lambda nid: 5,
            node_exists=lambda nid: True,
        )
        scheduler = self._rearm_scheduler(tree_cache)
        req = self._req(generation=3)
        req.last_host_node = 77
        req.hicache_restore_state = RestoreState.MISS_RECOMPUTE
        req.hicache_restore_miss_epoch = 5
        req.hicache_restore_miss_anchor = 42
        req.hicache_restore_miss_generation = 3

        self._rearm_gate(scheduler, req)

        self.assertIs(req.hicache_restore_state, RestoreState.WAIT_CAPACITY)
        self.assertIs(
            req.hicache_restore_wait_reason, RestoreWaitReason.DEVICE_QUOTA
        )

    def test_generation_change_rearms_even_same_anchor(self):
        # Same anchor version but a new identity (generation 4 vs miss 3):
        # the old miss evidence does not apply to this prefix's new identity,
        # so it re-arms.
        tree_cache = SimpleNamespace(
            pop_storage_prefetch_terminal=lambda rid: None,
            l3_publish_epoch=lambda: 7,
            anchor_storage_version=lambda nid: 7,
            node_exists=lambda nid: True,
        )
        scheduler = self._rearm_scheduler(tree_cache)
        req = self._req(generation=4)
        req.hicache_restore_state = RestoreState.MISS_RECOMPUTE
        req.hicache_restore_miss_epoch = 7
        req.hicache_restore_miss_anchor = 42
        req.hicache_restore_miss_generation = 3

        self._rearm_gate(scheduler, req)

        self.assertIs(req.hicache_restore_state, RestoreState.WAIT_CAPACITY)
        self.assertIs(
            req.hicache_restore_wait_reason, RestoreWaitReason.DEVICE_QUOTA
        )


class NoMaterialFastForwardSchedulerTests(unittest.TestCase):
    """phase2-peranchor: the GATE_SKIP_FRONTIER no-material fast-forward
    wiring. `_no_material_fast_forward_for` must return True only when ALL 5
    facts are absent, and False when any in-flight producer / deferred
    descendant / material / relevant change is present -- so the scheduler
    ADMIT_RECOMPUTEs a no-material frontier wait instead of idling the 60s
    T13, while keeping the P3 reconcile + frontier wait for every case with
    an in-flight causal producer."""

    def _scheduler(self, tree_cache):
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.server_args = SimpleNamespace(hicache_restore_wait_timeout_s=60.0)
        scheduler.tree_cache = tree_cache
        scheduler.enable_hicache_storage = True
        scheduler.enable_ready_horizon = False
        return scheduler

    def _req(self, anchor=42, host_hit=0):
        return SimpleNamespace(
            rid="r1",
            last_host_node=anchor,
            host_hit_length=host_hit,
            full_untruncated_fill_ids=[0, 1, 2, 3, 4, 5, 6, 7],
        )

    def _tree(
        self,
        *,
        node_exists=True,
        is_l3_durable=False,
        is_root=False,
        is_storage_written=False,
        has_deferred_desc=False,
        anchor_version=0,
        ongoing_backup=(),
        ongoing_load_back=(),
        deepest_durable_ancestor=None,
    ):
        tree = SimpleNamespace(
            node_exists=lambda nid: node_exists,
            is_l3_durable=lambda nid: is_l3_durable,
            is_root=lambda nid: is_root,
            is_storage_written=lambda nid: is_storage_written,
            has_acked_descendant=lambda nid: has_deferred_desc,
            anchor_storage_version=lambda nid: anchor_version,
            ongoing_backup=dict(ongoing_backup),
            ongoing_load_back=set(ongoing_load_back),
        )
        if deepest_durable_ancestor is not None:
            tree.deepest_durable_ancestor = lambda nid: deepest_durable_ancestor
        return tree

    def test_no_material_fast_forwards(self):
        # All five facts absent: recompute forward (no 60s idle).
        scheduler = self._scheduler(self._tree())
        self.assertTrue(scheduler._no_material_fast_forward_for(self._req(), 42))

    def test_host_material_keeps_wait(self):
        scheduler = self._scheduler(self._tree())
        self.assertFalse(
            scheduler._no_material_fast_forward_for(self._req(host_hit=8), 42)
        )

    def test_storage_material_keeps_wait(self):
        # L3-durable anchor: prefetch-issuable, keep the frontier wait.
        scheduler = self._scheduler(self._tree(is_l3_durable=True))
        self.assertFalse(
            scheduler._no_material_fast_forward_for(self._req(), 42)
        )

    def test_pending_write_ack_keeps_wait(self):
        # An L3 write for this anchor is in flight (storage_written): its ack
        # could promote the anchor durable -- must NOT fast-forward.
        scheduler = self._scheduler(self._tree(is_storage_written=True))
        self.assertFalse(
            scheduler._no_material_fast_forward_for(self._req(), 42)
        )
        # Or via the ongoing_backup table.
        scheduler2 = self._scheduler(self._tree(ongoing_backup={1: (42, None)}))
        self.assertFalse(
            scheduler2._no_material_fast_forward_for(self._req(), 42)
        )

    def test_deferred_descendant_keeps_wait(self):
        # The anchor anchors a deferred-ACK node (a P3 reconcile promotion
        # source): the P3 HOL fix depends on keeping this wait.
        scheduler = self._scheduler(self._tree(has_deferred_desc=True))
        self.assertFalse(
            scheduler._no_material_fast_forward_for(self._req(), 42)
        )

    def test_restorable_epoch_change_keeps_wait(self):
        # The anchor has L3 durability history (version > 0): a re-restore may
        # be redeemable, keep the wait.
        scheduler = self._scheduler(self._tree(anchor_version=3))
        self.assertFalse(
            scheduler._no_material_fast_forward_for(self._req(), 42)
        )
        # An in-flight restore read-back for this anchor also keeps the wait.
        scheduler2 = self._scheduler(self._tree(ongoing_load_back=(42,)))
        self.assertFalse(
            scheduler2._no_material_fast_forward_for(self._req(), 42)
        )

    # -- phase2-p0fix Q1: durable-ancestor resolution before judging --------

    def test_deeper_durable_ancestor_keeps_wait(self):
        # The shallow anchor is non-durable (its own flags all missing), but
        # a deeper ancestor's pages ARE durable -- the request's suffix can
        # restore from those pages, so no-material must NOT forward. The
        # storage fact is evaluated on the resolved durable ancestor.
        scheduler = self._scheduler(
            self._tree(
                node_exists=True,
                is_l3_durable=False,  # shallow anchor itself not durable
                deepest_durable_ancestor=7,  # but an ancestor at node 7 is
            )
        )
        self.assertFalse(scheduler._no_material_fast_forward_for(self._req(), 42))

    def test_no_durable_ancestor_forwards(self):
        # A pure device chain with no L3 content: walking the parent chain up
        # to the root finds no durable ancestor (root storage_persisted
        # defaults False) -> no-material holds -> forward (main benefit).
        scheduler = self._scheduler(
            self._tree(
                node_exists=True,
                is_l3_durable=False,
                deepest_durable_ancestor=None,
            )
        )
        self.assertTrue(scheduler._no_material_fast_forward_for(self._req(), 42))

    def test_durable_ancestor_with_deferred_descendant_keeps_wait(self):
        # Even with a durable ancestor resolved, the deferred-durable-descendant
        # fact is evaluated on the resolved anchor: a P3 reconcile promotion
        # source under it keeps the frontier wait (never fast-forward).
        scheduler = self._scheduler(
            self._tree(
                node_exists=True,
                is_l3_durable=False,
                deepest_durable_ancestor=7,
                has_deferred_desc=True,
            )
        )
        self.assertFalse(scheduler._no_material_fast_forward_for(self._req(), 42))

    def test_durable_ancestor_with_anchor_version_keeps_wait(self):
        # The restorable-epoch-change fact is evaluated on the resolved
        # durable ancestor: its per-anchor version > 0 keeps the wait.
        scheduler = self._scheduler(
            self._tree(
                node_exists=True,
                is_l3_durable=False,
                deepest_durable_ancestor=7,
                anchor_version=2,
            )
        )
        self.assertFalse(scheduler._no_material_fast_forward_for(self._req(), 42))


class TooShortWakeSchedulerFeedTests(unittest.TestCase):
    """too_short churn (independent P, T11 defense-in-depth): the per-pass
    capacity wake must not wake a DEVICE_QUOTA waiter whose current restore
    suffix is already sub-threshold AND can never grow back above it (the
    can-never-qualify prompt) -- waking would re-issue an inevitably
    declined_too_short prefetch (granted=0) and re-WAIT on the next pass
    (the tight wake->re-issue->declined->re-WAIT loop). The request is
    released to recompute its tail directly instead. The device-match-decay
    REVALIDATE bet is preserved: a prompt that CAN grow its suffix above the
    threshold keeps its capacity wake."""

    def _scheduler(self, tree_cache):
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.server_args = SimpleNamespace(
            hicache_restore_wait_timeout_s=60.0,
            hicache_promotion_margin_tokens=2048,
        )
        scheduler.tree_cache = tree_cache
        scheduler.enable_hicache_storage = True
        scheduler.enable_ready_horizon = False
        scheduler.page_size = 1
        return scheduler

    def _req(self):
        req = SimpleNamespace(
            rid="r1",
            last_host_node=42,
            hicache_restore_state=RestoreState.WAIT_CAPACITY,
            hicache_restore_wait_reason=RestoreWaitReason.DEVICE_QUOTA,
            hicache_restore_state_ts=0.0,
            hicache_restore_miss_epoch=None,
            hicache_restore_miss_generation=None,
            session_generation=None,
            host_hit_length=0,
            full_untruncated_fill_ids=None,
            output_ids=[],
            sampling_params=SimpleNamespace(max_new_tokens=16),
            prefix_indices=[],
        )
        # P4 gate reads the current match geometry via the real helper: the
        # default extend layout caps the match at input_len - 1 (logprob),
        # so match_end = len(fill_ids) - 1 for a fresh prefix match.
        req._compute_max_prefix_len = lambda input_len: max(input_len - 1, 0)
        return req

    def _capacity_tree(self, qualifies, prefetch_threshold=256):
        # DEVICE_QUOTA wake path stubs: no cache controller (rate-limit
        # bypass), a promotion allocator with full capacity (budget fits,
        # and the default non-SWA/non-mamba branch of
        # available_and_evictable_tokens), the never-case gate verdict, and
        # the prefetch_threshold the P4 current-suffix gate reads.
        alloc = SimpleNamespace(size_full=4096, available_size=lambda: 4096)
        return SimpleNamespace(
            cache_controller=None,
            prompt_can_qualify_for_prefetch=lambda prompt_len, host_hit: qualifies,
            token_to_kv_pool_allocator=alloc,
            inflight_promotion_reserved=0,
            supports_mamba=lambda: False,
            evictable_size=lambda: 0,
            prefetch_threshold=prefetch_threshold,
        ), alloc

    def test_sub_threshold_never_case_not_woken(self):
        # Current and theoretical-max suffix both sub-threshold (prompt 15,
        # host 0, prefetch_threshold 256): the capacity wake must hold --
        # the re-issued prefetch can never be granted.
        tree, alloc = self._capacity_tree(qualifies=False)
        scheduler = self._scheduler(tree)
        scheduler.req_to_token_pool = alloc
        req = self._req()
        req.full_untruncated_fill_ids = list(range(15))
        self.assertFalse(scheduler._restore_wait_capacity_fits(req))

    def test_qualifying_prompt_still_wakes(self):
        # population A (regression point 2): a prompt whose CURRENT suffix
        # already reaches the threshold keeps its capacity wake -- the
        # capacity release is the true rejection cause and the re-issue has
        # real output. Current suffix here = match_end(299) - (prefix 0 +
        # host 0) = 299 >= 256.
        tree, alloc = self._capacity_tree(qualifies=True)
        scheduler = self._scheduler(tree)
        scheduler.req_to_token_pool = alloc
        req = self._req()
        req.full_untruncated_fill_ids = list(range(300))
        self.assertTrue(scheduler._restore_wait_capacity_fits(req))

    def test_never_case_gate_idempotent(self):
        # The wake gate is a pure predicate: repeated checks with unchanged
        # inputs never flip (the request is held every time, so the tight
        # loop cannot start).
        tree, alloc = self._capacity_tree(qualifies=False)
        scheduler = self._scheduler(tree)
        scheduler.req_to_token_pool = alloc
        req = self._req()
        req.full_untruncated_fill_ids = list(range(15))
        for _ in range(3):
            self.assertFalse(scheduler._restore_wait_capacity_fits(req))

    def test_revalidate_bet_subthreshold_current_not_woken(self):
        # P4 gate (test 1): a REVALIDATE-bet waiter whose max suffix
        # qualifies (prompt_can_qualify True, so has_restore_potential is
        # preserved) but whose CURRENT suffix is still sub-threshold must
        # NOT be capacity-woken. Capacity release does not change the
        # inevitable declined_too_short result. Here prompt 1000, host 0,
        # device prefix match 750 -> current suffix 249 < 256; max suffix
        # 1000 >= 256 (qualifies=True).
        tree, alloc = self._capacity_tree(qualifies=True)
        scheduler = self._scheduler(tree)
        scheduler.page_size = 1
        scheduler.req_to_token_pool = alloc
        req = self._req()
        req.full_untruncated_fill_ids = list(range(1000))
        req.prefix_indices = list(range(750))
        self.assertFalse(scheduler._restore_wait_capacity_fits(req))

    def test_revalidate_bet_reward_after_current_suffix_grows(self):
        # P4 gate (test 2, bet reward): once the device match decays and the
        # CURRENT suffix grows past the threshold, the waiter IS woken -- the
        # re-issue now has real output and can be granted. Same prompt/host,
        # device match shortened from 750 to 740 -> current suffix 259 >= 256.
        tree, alloc = self._capacity_tree(qualifies=True)
        scheduler = self._scheduler(tree)
        scheduler.page_size = 1
        scheduler.req_to_token_pool = alloc
        req = self._req()
        req.full_untruncated_fill_ids = list(range(1000))
        req.prefix_indices = list(range(740))
        self.assertTrue(scheduler._restore_wait_capacity_fits(req))

    def test_p4_gate_page_aligned(self):
        # P4 gate reuses the page-aligned suffix geometry of
        # prompt_can_qualify_for_prefetch: with page_size 16, a current
        # suffix of 255 aligns to 240 < 256 (held), while 256 aligns to 256
        # >= 256 (woken).
        tree, alloc = self._capacity_tree(qualifies=True)
        scheduler = self._scheduler(tree)
        scheduler.page_size = 16
        scheduler.req_to_token_pool = alloc
        req = self._req()
        # current suffix 255 -> aligned 240 < 256 -> held.
        req.full_untruncated_fill_ids = list(range(256))
        req.prefix_indices = []
        self.assertFalse(scheduler._restore_wait_capacity_fits(req))
        # current suffix 256 -> aligned 256 >= 256 -> woken.
        req.full_untruncated_fill_ids = list(range(257))
        req.prefix_indices = []
        self.assertTrue(scheduler._restore_wait_capacity_fits(req))

    def test_p4_current_suffix_helper_direct(self):
        # Direct helper coverage: the helper reads the CURRENT match geometry
        # (match_end - (prefix + host)) and page-aligns it against the
        # threshold, independent of the capacity predicate.
        tree, alloc = self._capacity_tree(qualifies=True)
        scheduler = self._scheduler(tree)
        scheduler.page_size = 1
        scheduler.req_to_token_pool = alloc
        req = self._req()
        req.full_untruncated_fill_ids = list(range(1000))
        # host material 200 + device prefix 500 -> matched 700; current
        # suffix = 999 - 700 = 299 >= 256 -> not below threshold.
        req.host_hit_length = 200
        req.prefix_indices = list(range(500))
        self.assertFalse(scheduler._current_prefetch_suffix_lt_threshold(req))
        # device match deepens: prefix 800 -> current suffix 999 - 1000 -> 0
        # < 256 -> below threshold.
        req.prefix_indices = list(range(800))
        self.assertTrue(scheduler._current_prefetch_suffix_lt_threshold(req))


class MissRearmDurableCoverageSchedulerFeedTests(unittest.TestCase):
    """P4-round2 (点3): the T6 admission miss re-arm three-branch decision
    (`_miss_rearm_decision`). A SAME-anchor storage-version advance re-arms
    ONLY when the anchor chain now actually holds durable L3 material
    (`_miss_rearm_durable_coverage` = Q1 `deepest_durable_ancestor(anchor)`
    non-None). Clear / evict-rebuild bump the version WITHOUT leaving
    material -> re-probing is a structural guaranteed miss, so the request
    stays sticky (no re-arm). re-anchor / generation change still re-arm
    unconditionally (whitelist preserved, judged BEFORE the coverage gate);
    no-record / no-dda-proxy / no-anchor fall back to release (defensive)."""

    def _scheduler(self, tree_cache):
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.server_args = SimpleNamespace(hicache_restore_wait_timeout_s=60.0)
        scheduler.tree_cache = tree_cache
        scheduler.enable_hicache_storage = True
        scheduler.enable_ready_horizon = False
        return scheduler

    def _req(
        self,
        anchor=42,
        generation=3,
        miss_epoch=5,
        miss_anchor=42,
        miss_gen=3,
    ):
        return SimpleNamespace(
            rid="r1",
            last_host_node=anchor,
            session_generation=generation,
            hicache_restore_miss_epoch=miss_epoch,
            hicache_restore_miss_anchor=miss_anchor,
            hicache_restore_miss_generation=miss_gen,
        )

    def _tree(self, *, anchor_version=6, deepest_durable_ancestor=7, has_dda=True):
        if has_dda:
            return SimpleNamespace(
                anchor_storage_version=lambda nid: anchor_version,
                deepest_durable_ancestor=lambda nid: deepest_durable_ancestor,
            )
        # Tree without the Q1 proxy (older engine / restricted stub).
        return SimpleNamespace(
            anchor_storage_version=lambda nid: anchor_version,
        )

    # -- (1) same-anchor version advance + durable ancestor -> re-arm --------

    def test_same_anchor_version_advance_with_durable_material_rearms(self):
        # A genuine write-ack promotion / restore read-back gave the anchor
        # chain a durable ancestor: the re-probe may really restore now ->
        # re-arm. Point-5 legitimate same-anchor re-restore must keep working.
        scheduler = self._scheduler(
            self._tree(anchor_version=6, deepest_durable_ancestor=7)
        )
        req = self._req()
        self.assertTrue(scheduler._miss_rearm_decision(req))

    # -- (2) same-anchor version advance + NO durable ancestor -> sticky -----

    def test_same_anchor_version_advance_without_durable_material_stays_sticky(
        self,
    ):
        # The version advanced via a clear / evict-rebuild that left a pure
        # device chain (durable ancestor None): re-probing is guaranteed to
        # miss again -> stay sticky (no re-arm, no structural-guaranteed-miss
        # re-probe).
        scheduler = self._scheduler(
            self._tree(anchor_version=6, deepest_durable_ancestor=None)
        )
        req = self._req()
        self.assertFalse(scheduler._miss_rearm_decision(req))

    def test_same_anchor_version_unchanged_stays_sticky(self):
        # P1 regression guard: version unchanged, same anchor, same
        # generation -> sticky (the coverage gate is not even consulted).
        scheduler = self._scheduler(
            self._tree(anchor_version=5, deepest_durable_ancestor=7)
        )
        req = self._req()
        self.assertFalse(scheduler._miss_rearm_decision(req))
        # Coverage spring: the material gate must not fire when it must not.
        scheduler2 = self._scheduler(
            self._tree(anchor_version=5, deepest_durable_ancestor=None)
        )
        req2 = self._req()
        self.assertFalse(scheduler2._miss_rearm_decision(req2))

    # -- (3) re-anchor / generation change -> re-arm (whitelist preserved) ---

    def test_reanchor_rearms_regardless_of_material(self):
        # A different anchor node is a brand-new candidate: the old miss
        # evidence is void even though the new chain has no durable ancestor
        # yet -- the coverage gate must NOT block a fresh candidate.
        scheduler = self._scheduler(
            self._tree(anchor_version=6, deepest_durable_ancestor=None)
        )
        req = self._req(anchor=99, miss_anchor=42)
        self.assertTrue(scheduler._miss_rearm_decision(req))

    def test_generation_change_rearms_regardless_of_material(self):
        scheduler = self._scheduler(
            self._tree(anchor_version=6, deepest_durable_ancestor=None)
        )
        req = self._req(generation=9, miss_gen=3)
        self.assertTrue(scheduler._miss_rearm_decision(req))

    # -- (4) defensive fallbacks: no record / missing dda proxy / no anchor --

    def test_no_miss_record_releases(self):
        # Defensive branch: no recorded miss epoch (the state should not be
        # MISS_RECOMPUTE then) -> release regardless of the tree state.
        scheduler = self._scheduler(
            self._tree(anchor_version=6, deepest_durable_ancestor=None)
        )
        req = self._req(miss_epoch=None)
        self.assertTrue(scheduler._miss_rearm_decision(req))

    def test_missing_dda_proxy_falls_back_to_release(self):
        # The tree cache without the Q1 deepest_durable_ancestor proxy
        # (stub / older engine): conservative release preserves prior
        # behavior -- the material gate cannot over-block.
        scheduler = self._scheduler(self._tree(has_dda=False))
        req = self._req()
        self.assertTrue(scheduler._miss_rearm_decision(req))

    def test_coverage_helper_anchor_none_releases(self):
        # The coverage helper returns True when there is no anchor to judge:
        # nothing to gate here, let the identity/anchor criteria decide.
        scheduler = self._scheduler(self._tree())
        req = self._req(anchor=None)
        self.assertTrue(scheduler._miss_rearm_durable_coverage(req))

    def test_coverage_helper_direct(self):
        # Direct helper coverage: non-None deepest_durable_ancestor -> True;
        # pure device chain (None) -> False.
        scheduler = self._scheduler(self._tree(deepest_durable_ancestor=None))
        req = self._req()
        self.assertFalse(scheduler._miss_rearm_durable_coverage(req))
        scheduler2 = self._scheduler(self._tree(deepest_durable_ancestor=7))
        req2 = self._req()
        self.assertTrue(scheduler2._miss_rearm_durable_coverage(req2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
