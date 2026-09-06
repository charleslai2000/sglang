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
            scheduler._prefetch_kvcache = (
                lambda r, *, demand_restore=False: issued.append(demand_restore)
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
            hicache_restore_device_quota_timeouts=0,
            session_generation=generation,
            host_hit_length=0,
            full_untruncated_fill_ids=[0, 1, 2, 3, 4, 5, 6, 7],
        )

    def test_genuine_miss_records_epoch_and_generation(self):
        # The drain terminal revoked_miss: _feed_restore_terminal must land
        # the request in MISS_RECOMPUTE and record the L3 publish epoch at
        # which the miss was proven plus the identity generation.
        tree_cache = SimpleNamespace(
            pop_storage_prefetch_terminal=lambda rid: "revoked_miss",
            l3_publish_epoch=lambda: 7,
            node_exists=lambda nid: False,
        )
        scheduler = self._scheduler(tree_cache)
        req = self._req(generation=3)
        req.hicache_restore_state = RestoreState.RESTORING

        scheduler._feed_restore_terminal(req)

        self.assertIs(req.hicache_restore_state, RestoreState.MISS_RECOMPUTE)
        self.assertEqual(req.hicache_restore_miss_epoch, 7)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
