import threading
import unittest
from queue import Queue

import torch

from sglang.srt.mem_cache.hicache_storage import PoolName, PoolTransfer
from sglang.srt.mem_cache.hybrid_cache.hybrid_cache_controller import (
    HybridCacheController,
    StorageOperation,
)
from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache


class _GroupedBackend:
    def __init__(self, events, *, sidecar_ok=True, kv_ok=True, commit_ok=True):
        self.events = events
        self.sidecar_ok = sidecar_ok
        self.kv_ok = kv_ok
        self.commit_ok = commit_ok
        self.group = (b"g" * 16, 7)

    def open_group(self):
        self.events.append("open")
        return self.group

    def batch_set_v2(self, transfers, extra_info=None, group_id=None):
        self.events.append(("set", group_id, [t.name for t in transfers]))
        ok = self.sidecar_ok if any(t.name == PoolName.MAMBA for t in transfers) else self.kv_ok
        return {t.name: [ok] * len(t.keys or []) for t in transfers}

    def commit_group(self, group_id):
        self.events.append(("commit", group_id))
        return self.commit_ok

    def abort_group(self, group_id):
        self.events.append(("abort", group_id))
        return True


def _controller(backend, *, backup_skip=False):
    controller = object.__new__(HybridCacheController)
    controller.storage_backend = backend
    controller.backup_skip = backup_skip
    controller.page_size = 1
    controller.storage_backend_type = "extent"
    controller._t38c_expected_rank_set = []
    return controller


class _OneShotOperationQueue:
    """Hands the backup thread one operation and then requests a stop."""

    def __init__(self, operation, stop_event):
        self.operation = operation
        self.stop_event = stop_event

    def get(self, block=True, timeout=None):
        self.stop_event.set()
        return self.operation


class _RecordingAckQueue:
    def __init__(self):
        self.items = []

    def put(self, operation):
        self.items.append(operation)


class HybridGroupWiringTests(unittest.TestCase):
    def _operation(self, *, with_sidecar=True, operation_id=None):
        transfers = (
            [
                PoolTransfer(
                    name=PoolName.MAMBA,
                    host_indices=torch.tensor([0]),
                    keys=["mamba-key"],
                )
            ]
            if with_sidecar
            else None
        )
        operation = StorageOperation(
            torch.tensor([0]),
            [11],
            hash_value=["kv-key"],
            pool_transfers=transfers,
        )
        if operation_id is not None:
            operation.id = operation_id
        return operation

    def test_same_backend_gid_is_used_for_sidecar_and_kv_before_commit(self):
        events = []
        backend = _GroupedBackend(events)
        controller = _controller(backend)

        operation = self._operation(operation_id=999)
        self.assertTrue(controller._page_backup(operation))

        self.assertEqual(events[0], "open")
        self.assertEqual(events[1][0], "set")
        self.assertEqual(events[2][0], "set")
        self.assertEqual(events[1][1], backend.group)
        self.assertEqual(events[2][1], backend.group)
        self.assertEqual(events[3], ("commit", backend.group))
        self.assertNotEqual(operation.id, backend.group)
        self.assertIsNone(operation.group_id)

    def test_failure_aborts_and_does_not_commit(self):
        events = []
        backend = _GroupedBackend(events, sidecar_ok=False)
        controller = _controller(backend)

        self.assertFalse(controller._page_backup(self._operation()))
        self.assertEqual(events, [
            "open",
            ("set", backend.group, [PoolName.MAMBA]),
            ("abort", backend.group),
        ])

    def test_backup_ack_is_enqueued_only_after_group_commit(self):
        events = []

        class AckQueue:
            def put(self, operation):
                events.append("ack")

        class OneOperationQueue:
            def __init__(self, operation, stop_event):
                self.operation = operation
                self.stop_event = stop_event

            def get(self, block=True, timeout=None):
                self.stop_event.set()
                return self.operation

        backend = _GroupedBackend(events)
        controller = _controller(backend)
        controller.storage_stop_event = threading.Event()
        operation = self._operation()
        controller.backup_queue = OneOperationQueue(operation, controller.storage_stop_event)
        controller.ack_backup_queue = AckQueue()

        controller.backup_thread_func()

        self.assertEqual(events[-1], "ack")
        self.assertEqual(events[-2], ("commit", backend.group))

    def test_failed_backup_is_attributable_and_routes_to_storage_failure(self):
        """A backend failure must never be a silent no-ack.

        Pre-fix the hybrid ``_page_backup`` returned False with no reason and
        ``backup_thread_func`` simply ``continue``d: no ack was ever enqueued
        and ``storage_failure_reason`` stayed None, so the in-run storage
        failure path (which releases the submit-time host pin) never fired.
        """
        events = []
        backend = _GroupedBackend(events, sidecar_ok=False)
        controller = _controller(backend)
        controller.storage_failure_reason = None
        controller.storage_stop_event = threading.Event()
        operation = self._operation(with_sidecar=True)
        operation.node_id = 4242
        controller.backup_queue = _OneShotOperationQueue(
            operation, controller.storage_stop_event
        )
        controller.ack_backup_queue = _RecordingAckQueue()

        controller.backup_thread_func()

        # Attributable: the op carries the reason and the controller degraded.
        self.assertEqual(operation.backup_failure_reason, "sidecar_set_failed")
        self.assertIsNotNone(controller.storage_failure_reason)
        self.assertIn("sidecar_set_failed", controller.storage_failure_reason)
        # A failed write must not produce an ack (no fabricated commit).
        self.assertEqual(controller.ack_backup_queue.items, [])
        # abort (not commit) happened for the opened group.
        self.assertEqual(events[-1], ("abort", backend.group))

    def test_commit_group_failure_is_attributable(self):
        events = []
        backend = _GroupedBackend(events, commit_ok=False)
        controller = _controller(backend)
        controller.storage_failure_reason = None
        controller.storage_stop_event = threading.Event()
        operation = self._operation(with_sidecar=True)
        controller.backup_queue = _OneShotOperationQueue(
            operation, controller.storage_stop_event
        )
        controller.ack_backup_queue = _RecordingAckQueue()

        controller.backup_thread_func()

        self.assertEqual(operation.backup_failure_reason, "group_commit_failed")
        self.assertIn("group_commit_failed", controller.storage_failure_reason)
        self.assertEqual(controller.ack_backup_queue.items, [])

    def test_backup_thread_exception_is_fatal_not_silent(self):
        """The base controller's fatal handler must survive the override.

        Pre-fix the hybrid thread had only ``except Empty``: an unexpected
        exception propagated out and killed the daemon thread without setting
        ``storage_failure_reason``, leaving every in-flight pin held forever.
        """

        class _RaisingBackend(_GroupedBackend):
            def batch_set_v2(self, transfers, extra_info=None, group_id=None):
                raise RuntimeError("backend exploded")

        controller = _controller(_RaisingBackend([]))
        controller.storage_failure_reason = None
        controller.storage_stop_event = threading.Event()
        operation = self._operation(with_sidecar=True)
        controller.backup_queue = _OneShotOperationQueue(
            operation, controller.storage_stop_event
        )
        controller.ack_backup_queue = _RecordingAckQueue()

        # Pre-fix this call raised RuntimeError out of backup_thread_func.
        controller.backup_thread_func()

        self.assertIsNotNone(controller.storage_failure_reason)
        self.assertIn(
            "RuntimeError: backend exploded", controller.storage_failure_reason
        )
        self.assertEqual(controller.ack_backup_queue.items, [])

    def test_successful_commit_does_not_degrade_or_fabricate_failure(self):
        """Negative control: a committed write must stay on the happy path."""
        events = []
        backend = _GroupedBackend(events)
        controller = _controller(backend)
        controller.storage_failure_reason = None
        controller.storage_stop_event = threading.Event()
        operation = self._operation(with_sidecar=True)
        controller.backup_queue = _OneShotOperationQueue(
            operation, controller.storage_stop_event
        )
        controller.ack_backup_queue = _RecordingAckQueue()

        controller.backup_thread_func()

        self.assertIsNone(controller.storage_failure_reason)
        self.assertFalse(hasattr(operation, "backup_failure_reason"))
        self.assertEqual(controller.ack_backup_queue.items, [operation])
        self.assertEqual(events[-1], ("commit", backend.group))

    def test_storage_failure_releases_unacked_backup_pin_exactly_once(self):
        """Controller failure -> existing ownership path releases the pin.

        The pin is acquired at submit (``ongoing_backup``); the ONLY in-run
        release for an unacked write is ``_handle_storage_failure``. This test
        binds the hybrid failure signal to that release and checks
        exactly-once.
        """
        events = []
        backend = _GroupedBackend(events, sidecar_ok=False)
        controller = _controller(backend)
        controller.storage_failure_reason = None
        controller.storage_stop_event = threading.Event()
        operation = self._operation(with_sidecar=True)
        operation.node_id = 4242
        controller.backup_queue = _OneShotOperationQueue(
            operation, controller.storage_stop_event
        )
        controller.ack_backup_queue = _RecordingAckQueue()

        controller.backup_thread_func()

        cache = UnifiedRadixCache.__new__(UnifiedRadixCache)
        cache._storage_failure_handled = False
        cache.ongoing_prefetch = {}
        cache.ongoing_backup = {operation.id: (4242, "lock-params")}
        released = []

        def _dec(node_id, params):
            released.append((node_id, params))

        cache.dec_host_lock_ref = _dec

        # Exactly the scheduler-poll gate: reason present -> handle failure.
        self.assertIsNotNone(controller.storage_failure_reason)
        cache._handle_storage_failure(controller.storage_failure_reason)
        self.assertEqual(released, [(4242, "lock-params")])
        self.assertEqual(cache.ongoing_backup, {})

        # Idempotent: a second scheduler pass must not double-dec.
        cache._handle_storage_failure(controller.storage_failure_reason)
        self.assertEqual(released, [(4242, "lock-params")])


if __name__ == "__main__":
    unittest.main()
