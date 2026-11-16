"""CPU regressions for node-ID keyed HiCache frontier waiter lifecycle."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from sglang.srt.mem_cache.unified_cache.components import ComponentType
from sglang.srt.mem_cache.unified_cache.unified_tree_core import UnifiedTreeCore
from sglang.srt.mem_cache.unified_cache.unified_tree_core import UnifiedTreeNode
from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache
from sglang.srt.mem_cache.radix_cache import RadixKey


class FrontierWaiterLifecycleTests(TestCase):
    def _cache(self):
        cache = object.__new__(UnifiedRadixCache)
        cache._storage_frontier_waiters = {}
        cache._storage_frontier_ready = set()
        cache._backup_wait_spans = {}
        cache.tree_core = Mock()
        cache.tree_core.node_exists.side_effect = lambda n: n in {0, 1}
        cache.tree_core.is_l3_durable.return_value = False
        cache.write_backup_storage = Mock()
        return cache

    def test_original_node_id_waiter_wakes_when_original_node_becomes_durable(self):
        cache = self._cache()
        cache.register_frontier_waiter("req", 1)
        self.assertEqual(cache._storage_frontier_waiters, {1: {"req"}})
        cache.tree_core.is_l3_durable.return_value = True
        UnifiedRadixCache._wake_frontier_waiters(cache, 1)
        self.assertTrue(UnifiedRadixCache.pop_frontier_ready(cache, "req"))
        self.assertFalse(UnifiedRadixCache.pop_frontier_ready(cache, "req"))
        self.assertEqual(cache._storage_frontier_waiters, {})

    def test_split_keeps_waiter_on_old_id_without_implicit_migration(self):
        """Real TreeCore split retains child ID but new prefix has a new ID."""
        core = object.__new__(UnifiedTreeCore)
        # Use a normal TreeCore fixture only for node topology/split. Avoid GPU
        # pools: split itself is CPU-only and FULL host slices are absent here.
        core.page_size = 1
        core.component_types = (ComponentType.FULL,)
        core.components = (
            SimpleNamespace(
                component_type=ComponentType.FULL,
                redistribute_on_node_split=lambda new_parent, child: None,
            ),
        )
        core._next_id = 0
        root = UnifiedTreeNode((ComponentType.FULL,))
        root.id = -1
        root.parent = None
        root.children = {}
        core.root_node = root
        core._node_arena = {}
        core._register_node = lambda n: core._node_arena.__setitem__(n.id, n)
        core._update_evictable_leaf_sets = lambda n: None
        core._update_duplicate_tracking = lambda n: None
        core._for_each_component_lru = lambda *args, **kwargs: None
        core.lru_lists = {ComponentType.FULL: Mock()}
        core.host_lru_lists = {ComponentType.FULL: Mock()}
        core._new_node = lambda priority=0: self._new_node(core, priority)
        core.is_write_back = False

        old = self._new_node(core)
        old.parent = root
        old.key = RadixKey([10, 11, 12, 13])
        old.children = {}
        old.hash_value = None
        old.event_hash_value = None
        old.component_data[ComponentType.FULL].value = None
        old.component_data[ComponentType.FULL].host_value = None
        old.component_data[ComponentType.FULL].lock_ref = 0
        old.component_data[ComponentType.FULL].host_lock_ref = 0
        root.children[old.key.child_key(1)] = old

        cache = self._cache()
        cache.tree_core.node_exists.side_effect = lambda n: n in core._node_arena
        cache.tree_core.is_l3_durable.side_effect = lambda n: (
            core.node_by_id(n).storage_persisted
        )
        cache.register_frontier_waiter("req", old.id)

        new_parent, action = UnifiedTreeCore._split_node(core, old.key, old, 1)
        self.assertIsNone(action)
        self.assertEqual(old.parent.id, new_parent.id)
        self.assertIn(old.id, core._node_arena)
        self.assertEqual(cache._storage_frontier_waiters, {old.id: {"req"}})

        # The old ID remains a valid waiter target and can wake if it itself
        # becomes durable. The fresh prefix ID does not implicitly own it.
        old.storage_persisted = True
        UnifiedRadixCache._wake_frontier_waiters(cache, old.id)
        self.assertTrue(UnifiedRadixCache.pop_frontier_ready(cache, "req"))

        # A waiter on the new prefix remains asleep if only the old suffix
        # becomes durable. Split has no hidden key migration operation.
        cache.register_frontier_waiter("other", new_parent.id)
        UnifiedRadixCache._wake_frontier_waiters(cache, old.id)
        self.assertFalse(UnifiedRadixCache.pop_frontier_ready(cache, "other"))
        self.assertEqual(cache._storage_frontier_waiters, {new_parent.id: {"other"}})

    @staticmethod
    def _new_node(core, priority=0):
        node = UnifiedTreeNode((ComponentType.FULL,), priority=priority)
        node.id = core._next_id
        core._next_id += 1
        core._node_arena[node.id] = node
        return node


if __name__ == "__main__":
    import unittest

    unittest.main()
