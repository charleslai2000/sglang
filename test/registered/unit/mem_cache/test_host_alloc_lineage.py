"""P0-B producer-owned HOST_ALLOC wait/wake lineage wiring.

These are stdlib ``unittest`` tests (no pytest in the local 3090 env).  They
import the real scheduler and cache modules and drive the real emission path,
so they prove the lineage wiring rather than a re-implementation:

  (a) ``predecessor_for`` is consulted at the grant path and its result +
      reason are emitted;
  (b) ``record_terminal`` is called on the release/abandon/timeout paths with
      the correct terminal state;
  (c) the cache producer publishes the same scheduler-authoritative
      ``lifecycle_key`` (``rid:session_generation``);
  (d) the granted ``wake_event_id`` reaches the READY (``rh_ready_host.v1``)
      record;
  (e) a missing/contradictory predecessor yields explicit nulls plus a
      fail-closed reason and never a fabricated join.

Run with:
    source /mnt/data/neuron/envs/sglang-3090-opt/activate-sglang-3090.sh
    python -m unittest 3090-dev.test_host_alloc_lineage -v
"""

import contextlib
import json
import logging
import os
import sys
import time
import unittest
from types import SimpleNamespace

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PYTHON_DIR = os.path.join(_REPO_ROOT, "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

from sglang.srt.managers.scheduler import (  # noqa: E402
    Scheduler,
    _HOST_ALLOC_RELEASED_TERMINAL_STATES,
)
from sglang.srt.managers.scheduler_components.hicache_restore import (  # noqa: E402
    HostAllocabilitySnapshot,
    HostAllocFailure,
    HostAllocWakeArbiter,
    RestoreDecision,
    RestoreEvent,
    RestoreState,
    RestoreWaitReason,
)
from sglang.srt.mem_cache.telemetry_context import (  # noqa: E402
    clear_host_alloc_lineage,
    host_alloc_lineage,
    lifecycle_key,
)


_SCHEDULER_LOGGER = "sglang.srt.managers.scheduler"
_CACHE_LOGGER = "sglang.srt.mem_cache.unified_radix_cache"


@contextlib.contextmanager
def _capture_log_records(logger_name):
    """Collect formatted log messages emitted synchronously by one logger."""
    messages = []

    class _Handler(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    logger = logging.getLogger(logger_name)
    handler = _Handler()
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield messages
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


def _hae_records(messages):
    """Parse the ``[HAE]`` JSON payloads out of captured scheduler logs."""
    payloads = []
    for message in messages:
        if "[HAE] " in message:
            payloads.append(json.loads(message.split("[HAE] ", 1)[1]))
    return payloads


def _snapshot(kv=3):
    return HostAllocabilitySnapshot(
        cache_instance_id=7,
        generation_by_pool={"kv": kv},
        free_units_by_pool={"kv": 1},
        evictable_units_by_pool={"kv": 0},
    )


class _TreeCache:
    """Minimal cache double for the scheduler lineage paths."""

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.terminal = None
        self.completion = None

    def pop_host_alloc_failure(self, rid):
        return None

    def host_allocability_snapshot(self, required_pools=None):
        return self.snapshot

    def pop_storage_prefetch_terminal(self, rid):
        terminal, self.terminal = self.terminal, None
        return terminal

    def pop_storage_prefetch_completion(self, rid):
        completion, self.completion = self.completion, None
        return completion

    def peek_prefetch_loaded_tokens(self, rid):
        return 123


class HostAllocLineageWiringTests(unittest.TestCase):
    def setUp(self):
        clear_host_alloc_lineage()

    # -- fixtures -----------------------------------------------------------

    def _scheduler(self, snapshot=None):
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.server_args = SimpleNamespace(hicache_restore_wait_timeout_s=60.0)
        scheduler.tree_cache = _TreeCache(snapshot or _snapshot())
        scheduler.ps = None
        scheduler._host_alloc_attempt_seq = 0
        scheduler.enable_ready_horizon = False
        return scheduler

    @staticmethod
    def _req(rid, session_generation=4):
        return SimpleNamespace(
            rid=rid,
            session_generation=session_generation,
            hicache_restore_state=None,
            hicache_restore_wait_reason=None,
            hicache_restore_state_ts=0.0,
            hicache_restore_miss_epoch=None,
            hicache_restore_miss_generation=None,
            hicache_restore_miss_anchor=None,
            trace_context=None,
            time_stats=None,
            hicache_prefetch_active_attempt_id=None,
            hicache_prefetch_active_origin=None,
            hicache_prefetch_attempt_seq=0,
        )

    def _park(self, scheduler, req, failed_domains=frozenset({"kv"})):
        failure = HostAllocFailure(
            requested_primary_tokens=100,
            required_aux_units={},
            failed_domains=failed_domains,
            positive_hit_tokens=0,
            sidecar_hit_pages={},
            allocability_snapshot=scheduler.tree_cache.snapshot,
        )
        scheduler._capture_host_alloc_wait(req, failure)

    def _grant(self, scheduler, req):
        with _capture_log_records(_SCHEDULER_LOGGER) as messages:
            event_id = scheduler._emit_host_alloc_wake_grant(req)
        grant = _hae_records(messages)[-1]
        return event_id, grant

    def _release(self, scheduler, req, event):
        req.hicache_restore_state = RestoreState.WAIT_CAPACITY
        req.hicache_restore_wait_reason = RestoreWaitReason.HOST_ALLOC
        req.hicache_restore_state_ts = time.perf_counter()
        with _capture_log_records(_SCHEDULER_LOGGER) as messages:
            decision = scheduler._apply_restore_event(
                req, event, capacity_fits=event is RestoreEvent.CAPACITY_FITS
            )
        return decision, _hae_records(messages)

    # -- (a) predecessor/terminal populate on a grant -----------------------

    def test_grant_populates_predecessor_and_terminal_from_release(self):
        scheduler = self._scheduler()
        first = self._req("r1")
        second = self._req("r2")
        self._park(scheduler, first)
        self._park(scheduler, second)

        # First grant has no predecessor: explicit nulls plus a reason.
        first_grant_id, first_grant = self._grant(scheduler, first)
        self.assertIsNotNone(first_grant_id)
        self.assertEqual(first_grant["decision"], "grant")
        self.assertEqual(first_grant["wake_event_id"], first_grant_id)
        self.assertIsNone(first_grant["predecessor_wait_id"])
        self.assertIsNone(first_grant["predecessor_terminal_event_id"])
        self.assertIsNone(first_grant["predecessor_terminal_state"])
        self.assertEqual(
            first_grant["predecessor_lineage_reason"], "no_released_predecessor"
        )

        # Release r1: the release record carries a real terminal identity.
        _, release_records = self._release(scheduler, first, RestoreEvent.TIMEOUT)
        release = release_records[-1]
        self.assertEqual(release["decision"], "release")
        self.assertEqual(release["terminal_state"], "TIMEOUT")
        self.assertEqual(release["terminal_event_id"], release["event_id"])
        self.assertEqual(release["terminal_reason"], "restore_event:TIMEOUT")

        # Second grant names the released r1 as its FIFO predecessor.
        second_grant_id, second_grant = self._grant(scheduler, second)
        self.assertEqual(second_grant["predecessor_wait_id"], "r1:wait:0")
        self.assertEqual(
            second_grant["predecessor_terminal_event_id"],
            release["terminal_event_id"],
        )
        self.assertEqual(second_grant["predecessor_terminal_state"], "TIMEOUT")
        self.assertIsNone(second_grant["predecessor_lineage_reason"])
        self.assertEqual(second_grant["wake_event_id"], second_grant_id)

        # The release terminal is visible through the producer registry.
        recorded = host_alloc_lineage("r1")
        self.assertEqual(recorded["terminal_event_id"], release["terminal_event_id"])
        self.assertEqual(recorded["terminal_state"], "TIMEOUT")
        self.assertIn("TIMEOUT", _HOST_ALLOC_RELEASED_TERMINAL_STATES)

    def test_release_terminal_state_for_timeout_and_abandon(self):
        scheduler = self._scheduler()
        timed_out = self._req("timeout")
        self._park(scheduler, timed_out)
        _, records = self._release(scheduler, timed_out, RestoreEvent.TIMEOUT)
        self.assertEqual(records[-1]["terminal_state"], "TIMEOUT")

        abandoned = self._req("abandon")
        self._park(scheduler, abandoned)
        with _capture_log_records(_SCHEDULER_LOGGER) as messages:
            scheduler._remove_host_alloc_waiter(
                "abandon",
                terminal_state="ABANDONED",
                reason="empty_waiting_queue",
            )
        self.assertEqual(_hae_records(messages)[-1]["terminal_state"], "ABANDONED")
        self.assertEqual(
            scheduler._host_alloc_wake_arbiter.ordered_rids(),
            (),
        )

    # -- (b)/(e) fail-closed predecessor ------------------------------------

    def test_contradictory_predecessor_fails_closed_incomplete(self):
        scheduler = self._scheduler()
        predecessor = self._req("pre")
        self._park(scheduler, predecessor)
        # Simulate a producer-owned terminal that lost its event id.
        scheduler._host_alloc_wake_arbiter.record_terminal(
            "pre",
            sequence=0,
            wait_id="pre:wait:0",
            terminal_event_id=None,
            terminal_state="TIMEOUT",
            blocked_domains=["kv"],
        )
        scheduler._host_alloc_wake_arbiter.remove("pre")

        target = self._req("tgt")
        self._park(scheduler, target)
        _, grant = self._grant(scheduler, target)
        self.assertIsNone(grant["predecessor_wait_id"])
        self.assertIsNone(grant["predecessor_terminal_event_id"])
        self.assertEqual(
            grant["predecessor_lineage_reason"],
            "predecessor_terminal_incomplete",
        )

    def test_contradictory_predecessor_fails_closed_unrecognized(self):
        scheduler = self._scheduler()
        predecessor = self._req("pre")
        self._park(scheduler, predecessor)
        scheduler._host_alloc_wake_arbiter.record_terminal(
            "pre",
            sequence=0,
            wait_id="pre:wait:0",
            terminal_event_id="ev-pre",
            terminal_state="NOT_A_RELEASE_STATE",
            blocked_domains=["kv"],
        )
        scheduler._host_alloc_wake_arbiter.remove("pre")

        target = self._req("tgt")
        self._park(scheduler, target)
        _, grant = self._grant(scheduler, target)
        self.assertIsNone(grant["predecessor_wait_id"])
        self.assertEqual(
            grant["predecessor_lineage_reason"],
            "predecessor_terminal_state_unrecognized",
        )

    def test_predecessor_from_other_blocked_domain_is_not_fabricated(self):
        arbiter = HostAllocWakeArbiter()
        arbiter.enqueue("pre")
        arbiter.record_terminal(
            "pre",
            sequence=0,
            wait_id="pre:wait:0",
            terminal_event_id="ev-pre",
            terminal_state="TIMEOUT",
            blocked_domains=["mamba"],
        )
        arbiter.remove("pre")
        arbiter.enqueue("tgt")
        entry, reason = arbiter.predecessor_for(
            "tgt",
            sequence=1,
            blocked_domains={"kv"},
            released_states=_HOST_ALLOC_RELEASED_TERMINAL_STATES,
        )
        self.assertIsNone(entry)
        self.assertEqual(reason, "no_released_predecessor")

    def test_repark_wait_identity_is_fresh_and_distinct(self):
        scheduler = self._scheduler()
        req = self._req("r1")
        self._park(scheduler, req)
        self.assertEqual(req.hicache_host_alloc_wait_id, "r1:wait:0")

        self._grant(scheduler, req)
        decision, _ = self._release(scheduler, req, RestoreEvent.CAPACITY_FITS)
        self.assertIs(decision, RestoreDecision.RETRY_PREFETCH)

        # A retry that fails allocation re-parks the request.
        req.hicache_host_alloc_attempt_id = "r1:9"
        req.hicache_host_alloc_attempt_number = 1
        self._park(scheduler, req)
        self.assertEqual(req.hicache_host_alloc_wait_id, "r1:wait:1")

        _, grant = self._grant(scheduler, req)
        self.assertEqual(grant["wait_id"], "r1:wait:1")
        self.assertEqual(grant["predecessor_wait_id"], "r1:wait:0")
        self.assertNotEqual(
            grant["wait_id"], grant["predecessor_wait_id"]
        )

    # -- (c) lifecycle_key consistency across producers ---------------------

    def test_cache_producer_reuses_scheduler_lifecycle_key(self):
        from sglang.srt.mem_cache.unified_radix_cache import (
            _host_alloc_join_fields,
            _log_host_alloc_telemetry as cache_log,
        )

        scheduler = self._scheduler()
        req = self._req("rid-c", session_generation=11)
        self._park(scheduler, req)
        grant_id, grant = self._grant(scheduler, req)

        expected = lifecycle_key("rid-c", 11)
        self.assertEqual(grant["lifecycle_key"], expected)

        join = _host_alloc_join_fields("rid-c")
        self.assertEqual(join["lifecycle_key"], expected)
        self.assertEqual(join["wake_event_id"], grant_id)
        self.assertEqual(join["wait_id"], "rid-c:wait:0")

        # A cache-side emission with the join fields carries the scheduler key.
        with _capture_log_records(_CACHE_LOGGER) as messages:
            cache_log(
                "restore_host_alloc_retry_result",
                rid="rid-c",
                attempt_id="rid-c:9",
                **join,
            )
        cache_payload = _hae_records(messages)[-1]
        self.assertEqual(cache_payload["lifecycle_key"], expected)
        self.assertEqual(cache_payload["wake_event_id"], grant_id)

        # Unknown request -> no fabricated identity.
        self.assertEqual(_host_alloc_join_fields("never-seen"), {})

    # -- (d) wake_event_id reaches READY ------------------------------------

    def test_wake_event_id_reaches_ready_record(self):
        scheduler = self._scheduler()
        req = self._req("rid-ready", session_generation=5)
        self._park(scheduler, req)
        grant_id, _ = self._grant(scheduler, req)
        self.assertEqual(req.hicache_host_alloc_wake_event_id, grant_id)

        # Drive the real finalize -> READY handoff.
        req.hicache_restore_state = RestoreState.RESTORING
        req.hicache_restore_state_ts = time.perf_counter()
        req.hicache_prefetch_active_attempt_id = "rid-ready:prefetch:1"
        scheduler.tree_cache.terminal = ("rid-ready:prefetch:1", "finalized")
        scheduler.tree_cache.completion = {
            "finalize_result": "accepted",
            "completed_kv_tokens": 5,
        }
        with _capture_log_records(_SCHEDULER_LOGGER) as messages:
            scheduler._feed_restore_terminal(req)
        self.assertIs(req.hicache_restore_state, RestoreState.READY)

        ready_lines = [
            message for message in messages if "rh_ready_host.v1" in message
        ]
        self.assertEqual(len(ready_lines), 1)
        ready = ready_lines[0]
        self.assertIn(f"wake_event_id={grant_id}", ready)
        self.assertIn(f"lifecycle_key={lifecycle_key('rid-ready', 5)}", ready)
        self.assertIn("wait_id=rid-ready:wait:0", ready)


if __name__ == "__main__":
    unittest.main()
