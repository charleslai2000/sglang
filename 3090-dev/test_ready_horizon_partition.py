"""P3 Ready Horizon v0 (3.3): partition_ready_first unit tests (M4).

Guards the 3.3 deliverable: the READY-first stable partition the
scheduler runs between calc_priority and PrefillAdder.

- Stability: within each group the partition preserves the original
  (policy) relative order on both sides -- FCFS arrival order and LPM
  order are not broken by the promotion.
- Explicit priority > READY > base policy: with priority scheduling
  enabled the reorder is scoped to maximal runs of equal req.priority;
  a READY request never overtakes one with a different explicit
  priority, in either direction. Without the flag the whole queue is
  one run (the policy never reads priority).
- Off / idle: nothing M6-ready in the queue => the output order equals
  the input order (off = the scheduler gate never calls the
  partition); a READY without a resident staged marker (M6) is not
  promoted.
- Head-of-line guard: [RESTORING, READY, WAIT] partitions to
  [READY, ...] and the admission loop's existing continue semantics
  (skip ongoing prefetch / WAIT_CAPACITY) admit the READY request even
  though it was not first in the policy order -- the partition adds no
  new skip mechanism.

Runs the real scheduler_components/ready_horizon.py (torch-free) and
the real Scheduler gate inside _get_new_batch_prefill_raw against stub
collaborators, the same pattern as test_ready_horizon_unit.py.
"""

import time
import unittest
from types import SimpleNamespace

from sglang.srt.managers.scheduler_components.hicache_restore import (
    RestoreState,
)
from sglang.srt.managers.scheduler_components.ready_horizon import (
    ReadyHorizonPolicy,
)

NONE = RestoreState.NONE
WAIT = RestoreState.WAIT_CAPACITY
RESTORING = RestoreState.RESTORING
READY = RestoreState.READY


def _req(rid, state=None, priority=None):
    return SimpleNamespace(
        rid=rid,
        hicache_restore_state=state,
        priority=priority,
        beam_group=None,
    )


def _tree(loaded=None, staged=None):
    """Tree stand-in: the M6 residency markers by rid (peek = the
    finalize-written loaded count; staged = the buffer-mode pipeline)."""
    loaded = dict(loaded or {})
    staged = dict(staged or {})
    return SimpleNamespace(
        peek_prefetch_loaded_tokens=lambda rid: loaded.get(rid, 0),
        staged_prefetch_tokens=lambda rid: staged.get(rid, 0),
    )


def _partition(queue, *, tree=None, **kw):
    return ReadyHorizonPolicy().partition_ready_first(queue, tree=tree or _tree(), **kw)


def _ids(queue):
    return [r.rid for r in queue]


class StablePartitionTests(unittest.TestCase):
    """READY members move to the front; both sides keep their relative
    order (the calc_priority group-internal order is not broken)."""

    def test_ready_first_within_group_preserving_both_orders(self):
        queue = [
            _req("r1", NONE),
            _req("r2", READY),
            _req("r3", NONE),
            _req("r4", READY),
            _req("r5", NONE),
        ]
        out = _partition(queue, tree=_tree(loaded={"r2": 100, "r4": 100}))
        self.assertEqual(_ids(out), ["r2", "r4", "r1", "r3", "r5"])

    def test_fcfs_arrival_order_kept_inside_ready_group(self):
        # Three READY requests that arrived interleaved with normals keep
        # their arrival order after promotion.
        queue = [
            _req("a", READY),
            _req("b", NONE),
            _req("c", READY),
            _req("d", NONE),
            _req("e", READY),
        ]
        out = _partition(queue, tree=_tree(loaded={"a": 1, "c": 1, "e": 1}))
        self.assertEqual(_ids(out), ["a", "c", "e", "b", "d"])

    def test_tail_readies_promote_to_front(self):
        queue = [_req("x", NONE), _req("y", NONE), _req("z", READY)]
        out = _partition(queue, tree=_tree(loaded={"z": 1}))
        self.assertEqual(_ids(out), ["z", "x", "y"])


class ExplicitPriorityTests(unittest.TestCase):
    """explicit priority > READY > base policy: with priority scheduling
    enabled, READY promotion is scoped to equal-priority runs."""

    def test_ready_does_not_overtake_higher_priority(self):
        queue = [
            _req("hi", NONE, priority=5),
            _req("rd", READY, priority=1),
        ]
        out = _partition(queue, tree=_tree(loaded={"rd": 1}), priority=True)
        self.assertEqual(_ids(out), ["hi", "rd"])

    def test_ready_promoted_within_equal_priority_run(self):
        queue = [
            _req("a", NONE, priority=1),
            _req("b", READY, priority=1),
            _req("c", NONE, priority=5),
        ]
        out = _partition(queue, tree=_tree(loaded={"b": 1}), priority=True)
        self.assertEqual(_ids(out), ["b", "a", "c"])

    def test_lower_priority_ready_does_not_cross_run_boundary(self):
        # The READY request is lower priority than the runs around it:
        # no promotion at all (the run boundary holds in both directions).
        queue = [
            _req("a", NONE, priority=5),
            _req("b", READY, priority=1),
            _req("c", NONE, priority=5),
        ]
        out = _partition(queue, tree=_tree(loaded={"b": 1}), priority=True)
        self.assertEqual(_ids(out), ["a", "b", "c"])

    def test_each_level_run_partitioned_independently(self):
        queue = [
            _req("a", NONE, priority=9),
            _req("b", READY, priority=9),
            _req("c", NONE, priority=9),
            _req("d", NONE, priority=3),
            _req("e", READY, priority=3),
        ]
        out = _partition(queue, tree=_tree(loaded={"b": 1, "e": 1}), priority=True)
        self.assertEqual(_ids(out), ["b", "a", "c", "e", "d"])

    def test_priority_off_treats_whole_queue_as_one_run(self):
        # Without priority scheduling the policy never reads req.priority:
        # the partition must not introduce priority semantics either.
        queue = [
            _req("hi", NONE, priority=5),
            _req("rd", READY, priority=1),
        ]
        out = _partition(queue, tree=_tree(loaded={"rd": 1}))
        self.assertEqual(_ids(out), ["rd", "hi"])


class OffModeAndIdleNoopTests(unittest.TestCase):
    """Off / idle horizon: the partition leaves the calc_priority output
    exactly as it was (off = the scheduler gate never calls it; here the
    function itself is proven identity when nothing is M6-ready)."""

    def test_noop_when_nothing_ready(self):
        queue = [
            _req("a", NONE),
            _req("b", WAIT),
            _req("c", RESTORING),
            _req("d", READY),  # READY in name only: no resident marker
        ]
        out = _partition(queue, tree=_tree())
        self.assertEqual(_ids(out), _ids(queue))

    def test_ready_without_resident_marker_not_promoted(self):
        # M6: a plain state == READY (dropped insert, foreign path) has
        # no resident material and is not pool material.
        queue = [
            _req("a", NONE),
            _req("b", READY),
            _req("c", READY),
        ]
        out = _partition(queue, tree=_tree(loaded={"b": 0, "c": 0}))
        self.assertEqual(_ids(out), ["a", "b", "c"])

    def test_buffer_mode_uses_the_staged_marker(self):
        # buffer_only surfaces the staged pipeline marker, not the loaded
        # count; a loaded-only READY is not promoted in buffer mode.
        queue = [
            _req("a", NONE),
            _req("b", READY),
        ]
        out = _partition(
            queue,
            tree=_tree(loaded={"b": 100}, staged={"b": 0}),
            buffer_mode=True,
        )
        self.assertEqual(_ids(out), ["a", "b"])
        # Default mode reads the loaded marker: promoted.
        out = _partition(queue, tree=_tree(loaded={"b": 100}))
        self.assertEqual(_ids(out), ["b", "a"])

    def test_empty_queue_unchanged(self):
        self.assertEqual(_partition([]), [])


class PolicyOrderPreservationTests(unittest.TestCase):
    """FCFS / LPM: the partition preserves the order calc_priority
    produced within each group. Runs the real schedule_policy sort
    statics -- the same code calc_priority dispatches to."""

    @staticmethod
    def _sort_req(rid, arrival=0.0, priority=0, matched=0):
        return SimpleNamespace(
            rid=rid,
            priority=priority,
            time_stats=SimpleNamespace(wait_queue_entry_time=arrival),
            num_matched_prefix_tokens=matched,
            hicache_restore_state=None,
            beam_group=None,
        )

    def test_fcfs_order_preserved_inside_groups(self):
        from sglang.srt.managers.schedule_policy import SchedulePolicy

        queue = [
            self._sort_req("a", arrival=1.0),
            self._sort_req("b", arrival=2.0),
            self._sort_req("c", arrival=3.0),
        ]
        SchedulePolicy._sort_by_priority_and_fcfs(queue, priority_sign=-1)
        self.assertEqual(_ids(queue), ["a", "b", "c"])  # arrival order
        queue[1].hicache_restore_state = READY
        out = _partition(queue, tree=_tree(loaded={"b": 1}))
        # READY promoted; the non-READY side keeps FCFS arrival order.
        self.assertEqual(_ids(out), ["b", "a", "c"])

    def test_lpm_order_preserved_inside_groups(self):
        from sglang.srt.managers.schedule_policy import SchedulePolicy

        queue = [
            self._sort_req("a", matched=10),
            self._sort_req("b", matched=30),
            self._sort_req("c", matched=20),
        ]
        SchedulePolicy._sort_by_longest_prefix(queue, set())
        self.assertEqual(_ids(queue), ["b", "c", "a"])  # longest prefix first
        queue[2].hicache_restore_state = READY
        out = _partition(queue, tree=_tree(loaded={"a": 1}))
        # READY promoted; the non-READY side keeps LPM order.
        self.assertEqual(_ids(out), ["a", "b", "c"])


class HeadOfLineGuardTests(unittest.TestCase):
    """The existing continue semantics (skip ongoing prefetch and
    WAIT_CAPACITY) still protect the queue behind a non-admissible
    request; the partition only fronts the READY request, it does not
    rely on any new skip mechanism."""

    @staticmethod
    def _admit_with_continue_semantics(queue):
        """Mirror the admission loop: ongoing prefetch and WAIT_CAPACITY
        are skipped with continue, everything else is admitted."""
        admitted = []
        for req in queue:
            if req.hicache_restore_state is RESTORING:
                continue
            if req.hicache_restore_state is WAIT:
                continue
            admitted.append(req.rid)
        return admitted

    def test_ready_admitted_ahead_of_restoring_and_wait(self):
        queue = [
            _req("r1", RESTORING),
            _req("r2", READY),
            _req("r3", WAIT),
        ]
        out = _partition(queue, tree=_tree(loaded={"r2": 1}))
        self.assertEqual(_ids(out), ["r2", "r1", "r3"])
        admitted = self._admit_with_continue_semantics(out)
        self.assertEqual(admitted, ["r2"])

    def test_partition_does_not_change_skip_behavior(self):
        # The continue skips fire on the partitioned queue exactly as on
        # the original one: RESTORING / WAIT never block the READY.
        queue = [
            _req("r1", RESTORING),
            _req("r2", READY),
            _req("r3", WAIT),
        ]
        original = self._admit_with_continue_semantics(queue)
        partitioned = self._admit_with_continue_semantics(
            _partition(queue, tree=_tree(loaded={"r2": 1}))
        )
        self.assertEqual(partitioned, original)


class SchedulerGateWiringTests(unittest.TestCase):
    """The off gate: _get_new_batch_prefill_raw calls partition_ready_first
    only when enable_ready_horizon is set; off leaves the calc_priority
    order untouched (byte-identical to today). Runs the real method
    against stub collaborators (test_ready_horizon_unit pattern)."""

    def setUp(self):
        from sglang.srt.server_args import (
            ServerArgs,
            set_global_server_args_for_scheduler,
        )

        # PrefillAdder.__init__ reads the schedule config bag
        # (prefill_max_requests); publish a dummy scheduler config like
        # the upstream test_prefill_adder.py does.
        set_global_server_args_for_scheduler(ServerArgs(model_path="dummy"))

    def _scheduler(self, *, enable_ready_horizon, partition_spy):
        import sglang.srt.managers.scheduler as scheduler_mod
        from sglang.srt.disaggregation.utils import DisaggregationMode
        from sglang.srt.managers.scheduler import Scheduler

        scheduler = Scheduler.__new__(Scheduler)
        scheduler.server_args = SimpleNamespace(hicache_host_memory_mode="cache")
        scheduler.enable_ready_horizon = enable_ready_horizon
        scheduler.ready_horizon = SimpleNamespace(partition_ready_first=partition_spy)
        scheduler.enable_priority_scheduling = False
        scheduler.grammar_manager = SimpleNamespace(has_waiting_grammars=lambda: False)
        scheduler.enable_hierarchical_cache = False
        scheduler._last_deny_stats_ts = time.time()
        scheduler.waiting_queue = [_req("r1", NONE), _req("r2", NONE)]
        scheduler.chunked_req = None
        scheduler.min_free_slots_delayer = None
        scheduler.enable_priority_preemption = False
        scheduler.policy = SimpleNamespace(calc_priority=lambda q, rb: None)
        calls = {"n": 0}

        def _allocatable(*a, **k):
            calls["n"] += 1
            # First call (the early gate) must pass; later calls (the
            # admission-loop break) end the loop without touching a req.
            return 1 if calls["n"] == 1 else 0

        scheduler.get_num_allocatable_reqs = _allocatable
        scheduler.chunked_prefill_size = 1 << 30
        scheduler.enable_dynamic_chunking = False
        scheduler.tp_worker = SimpleNamespace(
            model_runner=SimpleNamespace(attn_backend=SimpleNamespace())
        )
        scheduler.page_size = 1
        scheduler.tree_cache = SimpleNamespace(supports_mamba=lambda: False)
        scheduler.token_to_kv_pool_allocator = SimpleNamespace()
        scheduler.req_to_token_pool = SimpleNamespace(mamba_allocator=None)
        scheduler.new_token_ratio_tracker = SimpleNamespace(current=1.0)
        scheduler.max_prefill_tokens = 1 << 30
        scheduler.is_mixed_chunk = False
        scheduler.priority_scheduling_preemption_threshold = 0
        scheduler.max_prefill_bs = 1 << 30
        scheduler.max_running_requests = None
        scheduler.dllm_config = None
        scheduler.enable_lora = False
        scheduler.disaggregation_mode = DisaggregationMode.NULL
        scheduler.enable_hicache_storage = False
        return scheduler

    def _run_admission(self, scheduler):
        import sglang.srt.managers.scheduler as scheduler_mod

        orig_get_memory = scheduler_mod.get_memory
        scheduler_mod.get_memory = lambda: SimpleNamespace(enable_flexkv=False)
        try:
            scheduler._get_new_batch_prefill_raw(
                prefill_delayer_single_pass=None,
                running_batch=SimpleNamespace(reqs=[], batch_is_full=False),
            )
        finally:
            scheduler_mod.get_memory = orig_get_memory

    def test_off_gate_keeps_calc_priority_order(self):
        seen = []

        def spy(queue, **kw):
            seen.append(queue)
            return queue

        scheduler = self._scheduler(enable_ready_horizon=False, partition_spy=spy)
        before = _ids(scheduler.waiting_queue)
        self._run_admission(scheduler)
        self.assertEqual(seen, [])  # the partition is never invoked
        self.assertEqual(_ids(scheduler.waiting_queue), before)

    def test_on_gate_partitions_before_admission(self):
        seen = []

        def spy(queue, **kw):
            seen.append(kw)
            return queue

        scheduler = self._scheduler(enable_ready_horizon=True, partition_spy=spy)
        self._run_admission(scheduler)
        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0]["tree"], scheduler.tree_cache)
        self.assertIs(seen[0]["buffer_mode"], False)
        self.assertIs(seen[0]["priority"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
