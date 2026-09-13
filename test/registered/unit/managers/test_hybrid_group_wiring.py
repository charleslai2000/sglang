import threading
import unittest
from queue import Queue

import torch

from sglang.srt.mem_cache.hicache_storage import PoolName, PoolTransfer
from sglang.srt.mem_cache.hybrid_cache.hybrid_cache_controller import (
    HybridCacheController,
    StorageOperation,
)


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


if __name__ == "__main__":
    unittest.main()
