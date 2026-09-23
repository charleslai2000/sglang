"""P3 Ready Horizon v0 (3.1): speculative/demand inflight-budget split
(M1), centralized prefetch reservation bookkeeping (M5), and the no-evict
speculative-staging rule (M2).

- M1: `inflight_speculative_tokens` (speculative issues only) is capped by
  `prefetch_speculative_capacity_limit` while the physical counter
  `prefetch_tokens_occupied` (all inflight) stays capped by
  `prefetch_capacity_limit`. Demand restores skip the speculative track but
  stay bounded by the physical budget under Ready Horizon; with the flag
  off, the single-track baseline holds exactly (demand bypasses, spec is
  physical-only).
- M5: every prefetch issue reserves `PrefetchReservation` (tokens, kind,
  released); finalize / revoke / abort / hybrid-discard / detach all exit
  through the single `release_prefetch` helper -- exactly-once (double
  release idempotent), so the upstream #31445 abort-leak bug class cannot
  come back.
- M2: a speculative staging alloc failure must never call `evict_host`
  (speculative staging eats free host headroom only, and declines
  silently); demand restores (and the flag-off baseline) still evict.

Runs the real unified_radix_cache.py / cache_controller.py /
scheduler.py source against stub collaborators (torch-free when torch is
absent), the same pattern as test_drain_reentry.py / test_storage_regression.py.
"""

import os
import sys
import threading
import time
import unittest
from array import array as _array
from types import SimpleNamespace

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PYTHON_DIR = os.path.join(_REPO_ROOT, "python")
sys.path.insert(0, _PYTHON_DIR)

try:
    import torch  # noqa: F401
except ImportError:
    torch = None


def _harness():
    """Lazy import of the test_storage_regression harness (drives the real
    UnifiedRadixCache source; sets up the torch-free stubenv when torch is
    absent)."""
    import test_storage_regression

    return test_storage_regression


def _urc_module():
    """The module object unified_radix_cache.py was loaded under (real
    package or stubenv); None until the harness import runs."""
    for name in (
        "sglang.srt.mem_cache.unified_radix_cache",
        "stubenv_unified_radix_cache",
    ):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "PrefetchKind"):
            return mod
    raise AssertionError("unified_radix_cache not found: load the harness first")


def _kind():
    """The real PrefetchKind class from the loaded module."""
    return _urc_module().PrefetchKind


def _ongoing_prefetch(anchor, prefetch_key, host_indices, operation):
    """Build a real _OngoingPrefetch NamedTuple for the staged entries."""
    return _urc_module()._OngoingPrefetch(
        anchor_node_id=anchor,
        prefetch_key=prefetch_key,
        host_indices=host_indices,
        operation=operation,
        anchor_lock_params=None,
        comp_xfers={},
    )


def _harness_has_torch():
    return torch is not None


def _tokens(n):
    """A token suffix of length n for the prefetch issue path (tokens ==
    pages in these tests: page_size=1)."""
    return [1] * n


class _BudgetController:
    """Controller stub with configurable physical / speculative budgets and
    a recording prefetch() issue path."""

    storage_failure_reason = None

    def __init__(self, capacity=1000, spec_fraction=0.6):
        self.prefetch_capacity_limit = capacity
        self.prefetch_speculative_capacity_limit = int(spec_fraction * capacity)
        self.prefetch_tokens_occupied = 0
        self.inflight_speculative_tokens = 0
        self.speculative_release_epoch = 0
        self.issued = []
        self.mem_pool_host = SimpleNamespace(
            size=capacity,
            available_size=lambda: capacity,
            alloc=lambda n: None,
            free=lambda *a, **k: None,
        )
        self.prefetch_hit_queue = None
        self.ack_prefetch_queue = SimpleNamespace(
            empty=lambda: True, get=lambda: None
        )
        self.ack_backup_queue = SimpleNamespace(empty=lambda: True, get=lambda: None)
        self.host_mem_release_queue = SimpleNamespace(
            empty=lambda: True, get=lambda: None
        )
        self.prefetch_buffer = SimpleNamespace(put=lambda *a, **k: None)

    def prefetch_rate_limited(self):
        return self.prefetch_tokens_occupied >= self.prefetch_capacity_limit

    def prefetch_speculative_rate_limited(self):
        return (
            self.inflight_speculative_tokens
            >= self.prefetch_speculative_capacity_limit
        )

    def terminate_prefetch(self, operation):
        return operation.completed_tokens, operation.hash_value

    def append_host_mem_release(self, host_indices=None, extra_pools=None):
        pass

    def prefetch(
        self,
        req_id,
        prefetch_key,
        last_hash,
        prefix_keys,
        extra_pools=None,
        trace_context=None,
    ):
        self.issued.append(req_id)
        return SimpleNamespace(
            request_id=req_id,
            stats_requested_tokens=0,
            stats_total_tokens=0,
            start_time=0.0,
            hash_value=[],
            pool_transfers=[],
            pool_storage_result=SimpleNamespace(
                update_extra_pool_hit_pages=lambda *a, **k: None,
                extra_pool_hit_pages={},
            ),
            host_indices=None,
            completed_tokens=0,
            storage_hit_count=0,
            is_terminated=lambda: False,
            all_hash_values=None,
        )


def _make_budget_cache(*, ready_horizon=True, controller=None):
    """The storage-regression cache harness plus the Ready Horizon state:
    the two new attrs, an empty component stack (no sidecar staging), and a
    budget controller."""
    h = _harness()
    cache = h._make_cache()
    cache.enable_ready_horizon = ready_horizon
    cache._prefetch_reservations = {}
    cache._t38c_node_context_index = {}
    cache._t38c_request_contexts = {}
    cache._t38c_residency_lock = threading.RLock()
    cache._t38c_residency_queue_blocked = set()
    # The storage-regression harness predates the outcome-counters schema;
    # the drain's below-threshold revoke feeds them.
    cache._prefetch_outcome_stats = {
        "attempts": 0,
        "issued": 0,
        "declined_too_short": 0,
        "declined_rate_limited": 0,
        "revoked_insufficient": 0,
        "revoked_full_miss": 0,
        "l3_demand_requests": 0,
        "l3_miss_tokens": 0,
        "l1l2_miss_tokens": 0,
        "l3_demand_total_tokens": 0,
        "l3_sum_rate_all": 0.0,
        "l3_sum_rate_main_weighted": 0.0,
    }
    cache.tree_components = ()
    cache.components = {}
    cache.enable_storage_metrics = False
    cache.storage_metrics_collector = None
    cache.cache_controller = controller or _BudgetController()
    # The registry FakeTreeCore has no chain model and no anchor info.
    cache.tree_core.prefetch_anchor_info = lambda node_id: (None, None)
    cache.tree_core.is_eagle = False
    return cache


def _issue(cache, rid, n_tokens, *, demand_restore=False):
    """Run the real prefetch_from_storage issue path for a fresh rid."""
    return cache.prefetch_from_storage(
        rid, 1, _tokens(n_tokens), None, demand_restore=demand_restore
    )


# ---------------------------------------------------------------------------
# M1: two-track inflight-budget admission at issue time
# ---------------------------------------------------------------------------


class PrefetchBudgetSplitTests(unittest.TestCase):
    """The issue-time rate check under Ready Horizon: speculative issues
    are bounded by the spec sub-budget AND the physical budget; demand
    restores are bounded by the physical budget only."""

    def test_spec_budget_full_declines_speculative_passes_demand(self):
        # Spec limit (600) exhausted by in-flight speculative staging: a
        # new speculative issue is declined while the physical budget still
        # has room and a demand restore issues.
        cache = _make_budget_cache()
        cc = cache.cache_controller
        cc.inflight_speculative_tokens = cc.prefetch_speculative_capacity_limit

        outcome = _issue(cache, "rid-spec", 600)
        self.assertEqual(outcome, "declined_rate_limited")
        self.assertEqual(cc.issued, [])
        self.assertIn("rid-spec", cache._storage_prefetch_missed_rids)

        outcome = _issue(cache, "rid-demand", 600, demand_restore=True)
        self.assertEqual(outcome, "issued")
        self.assertEqual(cc.issued, ["rid-demand"])
        # The demand issue charged only the physical counter.
        self.assertEqual(cc.inflight_speculative_tokens, 600)
        self.assertEqual(cc.prefetch_tokens_occupied, 600)

    def test_physical_budget_full_declines_both(self):
        # Physical budget (1000) exhausted: neither track may issue -- the
        # spec sub-budget is not a second pool, it is a slice of the same
        # physical budget (M1 diagram).
        cache = _make_budget_cache()
        cc = cache.cache_controller
        cc.prefetch_tokens_occupied = cc.prefetch_capacity_limit

        self.assertEqual(_issue(cache, "rid-spec", 600), "declined_rate_limited")
        self.assertEqual(
            _issue(cache, "rid-demand", 600, demand_restore=True),
            "declined_rate_limited",
        )
        self.assertEqual(cc.issued, [])

    def test_speculative_issue_charges_spec_counter(self):
        cache = _make_budget_cache()
        self.assertEqual(_issue(cache, "rid-spec", 600), "issued")
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 600)
        self.assertEqual(cache.cache_controller.prefetch_tokens_occupied, 600)
        reservation = cache._prefetch_reservations["rid-spec"]
        self.assertEqual(reservation.tokens, 600)
        self.assertIs(reservation.kind, _kind().SPECULATIVE)
        self.assertFalse(reservation.released)

    def test_demand_issue_not_charged_to_spec_counter(self):
        cache = _make_budget_cache()
        self.assertEqual(_issue(cache, "rid-demand", 600, demand_restore=True), "issued")
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 0)
        self.assertEqual(cache.cache_controller.prefetch_tokens_occupied, 600)
        reservation = cache._prefetch_reservations["rid-demand"]
        self.assertIs(reservation.kind, _kind().DEMAND)

    def test_physical_budget_pressure_declines_spec_under_spec_limit(self):
        # Physical usage from any source (here: demand restores) shrinks
        # the room left for speculative issues even while the spec counter
        # is below its sub-budget.
        cache = _make_budget_cache()
        cc = cache.cache_controller
        cc.prefetch_tokens_occupied = cc.prefetch_capacity_limit
        cc.inflight_speculative_tokens = 0

        self.assertEqual(_issue(cache, "rid-spec", 600), "declined_rate_limited")


# ---------------------------------------------------------------------------
# M5: reserve/release helper -- exactly-once, five release paths
# ---------------------------------------------------------------------------


class PrefetchReservationExactlyOnceTests(unittest.TestCase):
    """The reservation record is created at issue and every ongoing_prefetch
    removal point exits through release_prefetch. Double release is
    idempotent; the speculative counter returns to exactly zero."""

    def test_reserve_release_roundtrip(self):
        cache = _make_budget_cache()
        cache.reserve_prefetch("r1", 600, _kind().SPECULATIVE)
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 600)
        self.assertEqual(cache.cache_controller.speculative_release_epoch, 0)
        cache.release_prefetch("r1", "finalize")
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 0)
        self.assertEqual(cache.cache_controller.speculative_release_epoch, 1)
        self.assertEqual(cache._prefetch_reservations, {})

    def test_double_release_idempotent(self):
        cache = _make_budget_cache()
        cache.reserve_prefetch("r1", 600, _kind().SPECULATIVE)
        cache.release_prefetch("r1", "abort")
        self.assertEqual(cache.cache_controller.speculative_release_epoch, 1)
        cache.release_prefetch("r1", "revoke")  # second release: no-op
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 0)
        self.assertEqual(cache.cache_controller.speculative_release_epoch, 1)
        self.assertEqual(cache._prefetch_reservations, {})

    def test_release_without_reservation_noop(self):
        cache = _make_budget_cache()
        cache.release_prefetch("never-reserved", "detach")  # no exception
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 0)
        self.assertEqual(cache.cache_controller.speculative_release_epoch, 0)

    def test_demand_reservation_does_not_touch_spec_counter(self):
        cache = _make_budget_cache()
        cache.cache_controller.speculative_release_epoch = 7
        cache.reserve_prefetch("r1", 600, _kind().DEMAND)
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 0)
        cache.release_prefetch("r1", "finalize")
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 0)
        self.assertEqual(cache.cache_controller.speculative_release_epoch, 7)
        self.assertEqual(cache._prefetch_reservations, {})

    def test_revoke_path_releases_speculative_reservation(self):
        # Issue (reservation created) then revoke: the reservation is gone
        # and both counters return to zero.
        cache = _make_budget_cache()
        self.assertEqual(_issue(cache, "r1", 600), "issued")
        cache.revoke_pending_prefetch("r1")
        self.assertEqual(cache._prefetch_reservations, {})
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 0)
        self.assertEqual(cache.cache_controller.prefetch_tokens_occupied, 0)

    def test_abort_path_releases_speculative_reservation(self):
        cache = _make_budget_cache()
        self.assertEqual(_issue(cache, "r1", 600), "issued")
        cache.release_aborted_request("r1")
        self.assertEqual(cache._prefetch_reservations, {})
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 0)
        self.assertEqual(cache.cache_controller.prefetch_tokens_occupied, 0)

    def test_finalize_path_releases_speculative_reservation(self):
        # Drive the real _handle_prefetch_result with a completed hit: the
        # finalize bookkeeping must exit through release_prefetch.
        h = _harness()
        tree = h._RestoreMarkTree(inserted_node_id=77)
        cache = _make_budget_cache()
        cache.tree_core = tree
        operation = h._make_operation(4)
        operation.request_id = "r1"
        operation.completed_tokens = 4
        cache.reserve_prefetch("r1", 4, _kind().SPECULATIVE)
        cache.ongoing_prefetch["r1"] = _ongoing_prefetch(
            0,
            h._RadixKey(_array("q", list(range(4))), None),
            operation.host_indices,
            operation,
        )
        cache.cache_controller.prefetch_tokens_occupied = 4
        cache._handle_prefetch_result(operation)
        self.assertEqual(cache._prefetch_reservations, {})
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 0)
        self.assertEqual(cache.cache_controller.prefetch_tokens_occupied, 0)

    def test_hybrid_discard_path_releases_speculative_reservation(self):
        # All-or-nothing sidecar shortfall: the whole prefetch is
        # discarded in _check_hybrid_prefetch_result, whose cleanup must
        # exit through release_prefetch too (upstream #31445 class).
        h = _harness()
        transfer = SimpleNamespace(
            indices_from_pool=h._PoolName.SWA,
            name="swa",
            keys=["k1", "k2"],
        )
        tree = h._RestoreMarkTree(inserted_node_id=77)
        cache = _make_budget_cache()
        cache.tree_core = tree
        operation = h._make_operation(4, pool_transfers=[transfer])
        operation.request_id = "r1"
        operation.pool_transfers_done = False
        operation.completed_tokens = 4
        operation.pool_storage_result = SimpleNamespace(
            update_extra_pool_hit_pages=lambda *a, **k: None,
            extra_pool_hit_pages={},  # the sidecar served nothing
        )
        cache.reserve_prefetch("r1", 4, _kind().SPECULATIVE)
        cache.ongoing_prefetch["r1"] = _ongoing_prefetch(
            0,
            h._RadixKey(_array("q", list(range(4))), None),
            operation.host_indices,
            operation,
        )
        cache.cache_controller.prefetch_tokens_occupied = 4
        cache._handle_prefetch_result(operation)
        self.assertEqual(cache._prefetch_reservations, {})
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 0)
        self.assertEqual(cache.cache_controller.prefetch_tokens_occupied, 0)

    @unittest.skipUnless(
        _harness_has_torch(), "real StorageAttachment requires torch"
    )
    def test_detach_path_releases_speculative_reservation(self):
        # The detach safety net (_release_pending_storage_ops) exits every
        # still-tracked prefetch through release_prefetch.
        from sglang.srt.mem_cache.unified_cache.storage_attachment import (
            StorageAttachment,
        )

        cache = _make_budget_cache()
        self.assertEqual(_issue(cache, "r1", 600), "issued")
        attachment = StorageAttachment(cache)
        attachment._release_pending_storage_ops()
        self.assertEqual(cache._prefetch_reservations, {})
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 0)
        self.assertEqual(cache.cache_controller.prefetch_tokens_occupied, 0)
        self.assertEqual(cache.ongoing_prefetch, {})


# ---------------------------------------------------------------------------
# M2: speculative staging must not force host eviction
# ---------------------------------------------------------------------------


def _drain_one_hit(cache, operation):
    from queue import Queue

    cache.cache_controller.prefetch_hit_queue = Queue()
    cache.cache_controller.prefetch_hit_queue.put(operation)
    cache._drain_storage_control_queues_impl(1, 0, 0, 0, {}, False)


class SpeculativeStagingNoEvictTests(unittest.TestCase):
    """The drain's hit-alloc may evict host pages only for demand restores
    (and the flag-off baseline); speculative staging declines silently."""

    def _stage_operation(self, cache, rid, n_pages, kind):
        """Stage an in-flight prefetch for rid with a ready hit and reserve
        it under `kind`; the drain's hit-alloc then runs."""
        h = _harness()
        operation = h._make_operation(n_pages)
        operation.request_id = rid  # the harness hardcodes "test-rid"
        operation.completed_tokens = n_pages
        operation.stats_total_tokens = n_pages  # the L3-miss accounting needs it
        operation.all_hash_values = [f"h{i}" for i in range(n_pages)]
        cache.ongoing_prefetch[rid] = _ongoing_prefetch(
            0,
            h._RadixKey(_array("q", list(range(n_pages))), None),
            None,
            operation,
        )
        cache.reserve_prefetch(rid, n_pages, kind)
        cache.cache_controller.inflight_speculative_tokens = (
            n_pages if kind is _kind().SPECULATIVE else 0
        )
        cache.cache_controller.prefetch_tokens_occupied = n_pages
        return operation

    def test_speculative_alloc_failure_never_evicts(self):
        # Host pool exhausted: the speculative hit is revoked (silent
        # decline) without a single evict_host call -- staging eats free
        # headroom only (M2).
        h = _harness()
        cache = _make_budget_cache()
        evicted = []
        cache.evict_host = lambda needed, *a, **k: evicted.append(needed) or 0
        operation = self._stage_operation(
            cache, "r1", 300, _kind().SPECULATIVE
        )

        _drain_one_hit(cache, operation)

        self.assertEqual(evicted, [])
        # Declined: the prefetch left ongoing_prefetch and released its
        # reservation; the request parks (revoked_miss -> WAIT).
        self.assertEqual(cache.ongoing_prefetch, {})
        self.assertEqual(cache._prefetch_reservations, {})
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 0)
        self.assertEqual(cache.cache_controller.prefetch_tokens_occupied, 0)

    def test_demand_alloc_failure_still_evicts(self):
        # The demand restore keeps the baseline behavior: alloc failure
        # triggers eviction before the revoke fallback.
        h = _harness()
        cache = _make_budget_cache()
        evicted = []
        cache.evict_host = lambda needed, *a, **k: evicted.append(needed) or 0
        operation = self._stage_operation(
            cache, "r1", 300, _kind().DEMAND
        )

        _drain_one_hit(cache, operation)

        self.assertEqual(evicted, [300])
        self.assertEqual(cache.ongoing_prefetch, {})
        self.assertEqual(cache._prefetch_reservations, {})
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 0)


# ---------------------------------------------------------------------------
# Off mode: byte-identical baseline behavior
# ---------------------------------------------------------------------------


class ReadyHorizonOffModeTests(unittest.TestCase):
    """enable_ready_horizon=False must leave the pre-P3 behavior exactly:
    no speculative counter growth, single-track physical rate check, demand
    bypass, no reservations."""

    def test_off_speculative_issue_never_grows_spec_counter(self):
        cache = _make_budget_cache(ready_horizon=False)
        self.assertEqual(_issue(cache, "rid-spec", 600), "issued")
        self.assertEqual(cache.cache_controller.inflight_speculative_tokens, 0)
        self.assertEqual(cache.cache_controller.prefetch_tokens_occupied, 600)
        # No reservation machinery at all (all issues unclassified).
        self.assertEqual(cache._prefetch_reservations, {})

    def test_off_single_track_physical_check_only(self):
        # Spec budget exhausted is irrelevant off-mode; only the physical
        # budget gates speculative issues.
        cache = _make_budget_cache(ready_horizon=False)
        cc = cache.cache_controller
        cc.inflight_speculative_tokens = cc.prefetch_speculative_capacity_limit
        cc.prefetch_tokens_occupied = 0

        self.assertEqual(_issue(cache, "rid-spec", 600), "issued")

    def test_off_demand_bypasses_rate_check(self):
        # Baseline T15 ticket semantics: demand restores bypass the
        # PREFETCH_BUDGET entirely, physical full or not.
        cache = _make_budget_cache(ready_horizon=False)
        cc = cache.cache_controller
        cc.prefetch_tokens_occupied = cc.prefetch_capacity_limit

        self.assertEqual(
            _issue(cache, "rid-demand", 600, demand_restore=True), "issued"
        )

    def test_off_alloc_failure_evicts_like_baseline(self):
        # The M2 gate must not change the flag-off behavior either: a
        # staging alloc failure still evicts (no reservation to classify).
        h = _harness()
        cache = _make_budget_cache(ready_horizon=False)
        evicted = []
        cache.evict_host = lambda needed, *a, **k: evicted.append(needed) or 0
        operation = h._make_operation(300)
        operation.request_id = "r1"
        operation.completed_tokens = 300
        operation.stats_total_tokens = 300
        operation.all_hash_values = [f"h{i}" for i in range(300)]
        cache.ongoing_prefetch["r1"] = _ongoing_prefetch(
            0,
            h._RadixKey(_array("q", list(range(300))), None),
            None,
            operation,
        )

        _drain_one_hit(cache, operation)

        self.assertEqual(evicted, [300])


# ---------------------------------------------------------------------------
# Scheduler wiring: T11/T12 wake re-issue demand_restore classification
# ---------------------------------------------------------------------------


class ReadyHorizonSchedulerWiringTests(unittest.TestCase):
    """T11/T12 wake re-issues carry demand_restore=True under Ready Horizon;
    off keeps the pre-P3 classification (was_backup_pending only)."""

    def _scheduler(self, tree_cache, *, enable_ready_horizon):
        import sglang.srt.managers.scheduler as scheduler_mod
        from sglang.srt.managers.scheduler import Scheduler

        scheduler = Scheduler.__new__(Scheduler)
        scheduler.server_args = SimpleNamespace(hicache_restore_wait_timeout_s=60.0)
        scheduler.tree_cache = tree_cache
        scheduler.enable_hicache_storage = True
        scheduler.enable_ready_horizon = enable_ready_horizon
        return scheduler

    def _req(self, wait_reason):
        from sglang.srt.managers.scheduler_components.hicache_restore import (
            RestoreState,
        )

        return SimpleNamespace(
            rid="r1",
            last_host_node=42,
            hicache_restore_state=RestoreState.WAIT_CAPACITY,
            hicache_restore_wait_reason=wait_reason,
            hicache_restore_state_ts=time.perf_counter(),
        )

    def _reconcile_and_collect(self, *, enable_ready_horizon, wait_reason):
        """Run one T11/T12 reconciliation pass with a stubbed re-issue and
        return the demand_restore values the wake re-issues carried."""
        import sglang.srt.managers.scheduler as scheduler_mod
        from sglang.srt.managers.scheduler_components.hicache_restore import (
            RestoreWaitReason,
        )

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
                frontier_anchor_ready=lambda node: True,
                discard_frontier_waiter=lambda rid: None,
            )
            scheduler = self._scheduler(
                tree_cache, enable_ready_horizon=enable_ready_horizon
            )
            scheduler.waiting_queue = [self._req(wait_reason)]
            scheduler._prefetch_kvcache = lambda r, *, origin, demand_restore=False: (
                issued.append(demand_restore)
            )
            scheduler._reconcile_restore_states()
            return issued
        finally:
            scheduler_mod.get_memory = orig_get_memory

    def test_on_t11_frontier_wake_reissues_as_demand(self):
        from sglang.srt.managers.scheduler_components.hicache_restore import (
            RestoreWaitReason,
        )

        # Ready Horizon on: a FRONTIER capacity wake (not backup-related)
        # still re-issues as a demand restore -- the wake serves an
        # admitted restore episode, only the initial staging is
        # speculative.
        issued = self._reconcile_and_collect(
            enable_ready_horizon=True, wait_reason=RestoreWaitReason.FRONTIER
        )
        self.assertEqual(issued, [True])

    def test_off_t11_frontier_wake_keeps_speculative_classification(self):
        from sglang.srt.managers.scheduler_components.hicache_restore import (
            RestoreWaitReason,
        )

        # Off: a FRONTIER wake is NOT backup_pending, so the re-issue is a
        # plain speculative prefetch -- the pre-P3 baseline, byte for byte.
        issued = self._reconcile_and_collect(
            enable_ready_horizon=False, wait_reason=RestoreWaitReason.FRONTIER
        )
        self.assertEqual(issued, [False])

    def test_off_t11_backup_pending_wake_still_demand(self):
        from sglang.srt.managers.scheduler_components.hicache_restore import (
            RestoreWaitReason,
        )

        # Off: the T15 BACKUP_PENDING wake keeps its DEMAND_RESTORE ticket
        # (P2-IO R2 unchanged).
        issued = self._reconcile_and_collect(
            enable_ready_horizon=False, wait_reason=RestoreWaitReason.BACKUP_PENDING
        )
        self.assertEqual(issued, [True])

    def test_on_t11_backup_pending_wake_still_demand(self):
        from sglang.srt.managers.scheduler_components.hicache_restore import (
            RestoreWaitReason,
        )

        issued = self._reconcile_and_collect(
            enable_ready_horizon=True, wait_reason=RestoreWaitReason.BACKUP_PENDING
        )
        self.assertEqual(issued, [True])


if __name__ == "__main__":
    unittest.main(verbosity=2)
