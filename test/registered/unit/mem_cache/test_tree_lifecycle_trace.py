"""CPU-only validation for the opt-in TreeCore lifecycle trace."""

import os
import unittest
from collections import deque
from unittest import mock

from sglang.srt.mem_cache.unified_cache import unified_tree_core as tree_mod
from sglang.srt.mem_cache.unified_cache.components import ComponentType
from sglang.srt.mem_cache.unified_cache.unified_tree_core import (
    UnifiedTreeCore,
    UnifiedTreeNode,
)
from sglang.srt.mem_cache.radix_cache import RadixKey


class TreeLifecycleTraceTests(unittest.TestCase):
    def setUp(self):
        self.enabled = tree_mod._TREE_LIFECYCLE_TRACE_ENABLED
        self.records = tree_mod._TREE_LIFECYCLE_TRACE
        self.reported = tree_mod._TREE_LIFECYCLE_TRACE_REPORTED
        self.lock = tree_mod._TREE_LIFECYCLE_TRACE_LOCK
        self.capacity = tree_mod._TREE_LIFECYCLE_TRACE_CAPACITY
        tree_mod._TREE_LIFECYCLE_TRACE_ENABLED = True
        tree_mod._TREE_LIFECYCLE_TRACE = deque(maxlen=self.capacity)
        tree_mod._TREE_LIFECYCLE_TRACE_REPORTED = False

    def tearDown(self):
        tree_mod._TREE_LIFECYCLE_TRACE_ENABLED = self.enabled
        tree_mod._TREE_LIFECYCLE_TRACE = self.records
        tree_mod._TREE_LIFECYCLE_TRACE_REPORTED = self.reported
        tree_mod._TREE_LIFECYCLE_TRACE_LOCK = self.lock

    def _core(self):
        core = object.__new__(UnifiedTreeCore)
        core.is_write_back = False
        core._lifecycle_trace_sequence = 0
        core.root_node = UnifiedTreeNode((ComponentType.FULL,))
        core.root_node.id = -1
        core.root_node.parent = None
        parent = UnifiedTreeNode((ComponentType.FULL,))
        parent.id = 1
        parent.parent = core.root_node
        parent.key = RadixKey([1, 2])
        child = UnifiedTreeNode((ComponentType.FULL,))
        child.id = 2
        child.parent = parent
        child.key = RadixKey([3])
        return core, parent, child

    def test_normal_transition_records_shape_without_false_violation(self):
        core, parent, child = self._core()
        parent.component_data[ComponentType.FULL].host_value = object()
        child.component_data[ComponentType.FULL].host_value = object()
        core._trace_full_host_transition("split_old_child", child, True)
        event = tree_mod._TREE_LIFECYCLE_TRACE[-1]
        self.assertEqual(event["operation"], "split_old_child")
        self.assertEqual(event["node_id"], 2)
        self.assertEqual(event["parent_id"], 1)
        self.assertEqual(event["key_len"], 1)
        self.assertTrue(event["full_host_before"])
        self.assertTrue(event["full_host_after"])
        self.assertNotIn("first_violation", event)
        self.assertFalse(tree_mod._TREE_LIFECYCLE_TRACE_REPORTED)

    def test_first_illegal_transition_logs_bounded_order_and_only_once(self):
        core, parent, child = self._core()
        core._trace_full_host_transition("split_old_child", child, False)
        self.assertFalse(tree_mod._TREE_LIFECYCLE_TRACE_REPORTED)
        with mock.patch.object(tree_mod.logger, "error") as error:
            self.assertFalse(error.called)
            child.component_data[ComponentType.FULL].host_value = object()
            core._trace_full_host_transition("backup_commit", child, False)
            self.assertTrue(error.called)
            self.assertTrue(tree_mod._TREE_LIFECYCLE_TRACE[-1]["first_violation"])
            self.assertEqual(
                tree_mod._TREE_LIFECYCLE_TRACE[-1]["operation"], "backup_commit"
            )
            before = error.call_count
            core._trace_full_host_transition("duplicate_host_clear", child, True)
            self.assertEqual(error.call_count, before)

    def test_buffer_is_finite_and_does_not_capture_token_payload(self):
        core, parent, child = self._core()
        original_capacity = tree_mod._TREE_LIFECYCLE_TRACE_CAPACITY
        tree_mod._TREE_LIFECYCLE_TRACE_CAPACITY = 3
        tree_mod._TREE_LIFECYCLE_TRACE = deque(maxlen=3)
        try:
            for i in range(5):
                core._trace_full_host_transition(f"op{i}", child, False)
            self.assertEqual(len(tree_mod._TREE_LIFECYCLE_TRACE), 3)
            self.assertEqual(
                [event["operation"] for event in tree_mod._TREE_LIFECYCLE_TRACE],
                ["op2", "op3", "op4"],
            )
            self.assertTrue(
                all(
                    "token" not in str(event).lower()
                    for event in tree_mod._TREE_LIFECYCLE_TRACE
                )
            )
        finally:
            tree_mod._TREE_LIFECYCLE_TRACE_CAPACITY = original_capacity


if __name__ == "__main__":
    unittest.main()
