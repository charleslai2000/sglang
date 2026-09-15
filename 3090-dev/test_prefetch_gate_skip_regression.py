"""Dependency-free regression tests for the HiCache prefetch gate split."""

import ast
import enum
import logging
import time
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Optional


class HiCachePrefetchIssueStatus(enum.Enum):
    ISSUED = enum.auto()
    HELD = enum.auto()
    SKIPPED_ACTIVE = enum.auto()
    SKIPPED_STATE = enum.auto()
    FAILED_BEFORE_ISSUE = enum.auto()


@dataclass(frozen=True)
class PrefetchIssueResult:
    status: HiCachePrefetchIssueStatus
    attempt_id: str | None
    origin: object
    reason: str
    state_before: str
    state_after: str


class RestoreEvent:
    GATE_SKIP_FRONTIER = object()
    PREFETCH_ISSUED = object()


class HiCachePrefetchOrigin:
    READY_HORIZON = object()
    pass


def _load_prefetch_impl():
    source_path = (
        Path(__file__).parents[1]
        / "python/sglang/srt/managers/scheduler.py"
    )
    module = ast.parse(source_path.read_text())
    function = next(
        node
        for node in ast.walk(module)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_prefetch_kvcache_impl"
    )
    namespace = {
        "PrefetchIssueResult": PrefetchIssueResult,
        "Optional": Optional,
        "_ReadyHorizonPreparedMatch": object,
        "HiCachePrefetchIssueStatus": HiCachePrefetchIssueStatus,
        "RestoreEvent": RestoreEvent,
        "HiCachePrefetchOrigin": HiCachePrefetchOrigin,
        "Req": object,
        "_t38c_log": lambda event: None,
        "get_memory": lambda: SimpleNamespace(
            hicache_storage_prefetch_retry_poll_interval=0
        ),
        "short_tail_recompute_allowed": lambda **kwargs: False,
        "logger": logging.getLogger(__name__),
        "time": time,
    }
    exec(compile(ast.Module([function], []), str(source_path), "exec"), namespace)
    return namespace["_prefetch_kvcache_impl"]


class PrefetchGateSkipRegressionTests(unittest.TestCase):
    def _scheduler(self, gate_pass):
        frontier_waits = []
        restore_events = []
        storage_calls = []

        class TreeCache:
            hicache_storage_pass_prefix_keys = False
            prefetch_threshold = 256

            @staticmethod
            def is_root(node):
                return False

            @staticmethod
            def is_backuped(node):
                return False

            @staticmethod
            def get_last_hash_value(node):
                return "anchor-hash"

            @staticmethod
            def prefetch_gate_ok(node, buffer_mode):
                return gate_pass

            def prefetch_from_storage(self, *args, **kwargs):
                storage_calls.append((args, kwargs))
                return "issued"

            @staticmethod
            def prompt_can_qualify_for_prefetch(prompt_len, host_hit):
                return True

            @staticmethod
            def register_frontier_waiter(rid, node):
                frontier_waits.append((rid, node))

        scheduler = SimpleNamespace(
            enable_hicache_storage=True,
            server_args=SimpleNamespace(hicache_host_memory_mode="cache"),
            tree_cache=TreeCache(),
            _no_material_fast_forward_for=lambda req, node: False,
            _apply_restore_event=lambda req, event: restore_events.append(event),
            _log_restore_recompute=lambda req, reason: None,
            page_size=16,
        )
        scheduler.req = SimpleNamespace(
            rid="r1",
            hicache_prefetch_active_attempt_id="r1:prefetch:1",
            hicache_prefetch_active_origin=object(),
            last_host_node=42,
            prefix_indices=[],
            host_hit_length=0,
            full_untruncated_fill_ids=list(range(512)),
            init_next_round_input=lambda *args, **kwargs: None,
            _compute_max_prefix_len=lambda input_len: input_len,
        )
        scheduler.frontier_waits = frontier_waits
        scheduler.restore_events = restore_events
        scheduler.storage_calls = storage_calls
        return scheduler

    def test_gate_skip_registers_wait_and_declines_without_storage_io(self):
        scheduler = self._scheduler(gate_pass=False)
        impl = _load_prefetch_impl()

        result = impl(scheduler, scheduler.req, origin=object())

        self.assertIs(result.status, HiCachePrefetchIssueStatus.HELD)
        self.assertEqual(scheduler.frontier_waits, [("r1", 42)])
        self.assertEqual(
            scheduler.restore_events, [RestoreEvent.GATE_SKIP_FRONTIER]
        )
        self.assertEqual(scheduler.storage_calls, [])

    def test_gate_pass_preserves_storage_issue_and_typed_result(self):
        scheduler = self._scheduler(gate_pass=True)
        impl = _load_prefetch_impl()

        result = impl(scheduler, scheduler.req, origin=object())

        self.assertIs(result.status, HiCachePrefetchIssueStatus.ISSUED)
        self.assertIsNotNone(result.attempt_id)
        self.assertEqual(scheduler.frontier_waits, [])
        self.assertEqual(len(scheduler.storage_calls), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
