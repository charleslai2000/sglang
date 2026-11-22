"""Full-host duplicate reclaim under write_through (r61).

Field symptom (r61 control, C-8): the 186,012-token Host KV pool stayed full of
prefixes whose device copy was still resident, no Full-host leaf ever formed, so
`_is_host_leaf` was false for every node; `evict_host` reclaimed 0 tokens and
both paths that need Host space failed -- the staging restore (523 revoked after
a validated L3 read) and, once the implicit floor was set, the D->H backup.

`_reclaim_full_host_duplicate` already frees *only* the Full host layer of a node
that keeps its device copy (no tree deletion, no children touched, no L3 state
touched), but `drive_host_eviction` restricted it to `write_back`.  These tests
pin the write_through behaviour that makes it usable there: the host copy set is
prefix-closed, so the release has to run bottom-up, and in-flight/locked nodes
must block themselves and their ancestors.
"""

import unittest
from unittest import mock

import torch

from sglang.srt.mem_cache.unified_cache.unified_tree_core import (
    UnifiedTreeCore,
    UnifiedTreeNode,
)
from sglang.srt.mem_cache.unified_cache.components import ComponentType

BASE = ComponentType.FULL


def _chain(length: int):
    """root -> n0 -> n1 -> ... with Full device + Full host on every node."""
    root = UnifiedTreeNode((BASE,))
    nodes = []
    parent = root
    for i in range(length):
        node = UnifiedTreeNode((BASE,))
        node.parent = parent
        node.key = list(range(i + 1))
        cd = node.component_data[BASE]
        cd.value = torch.tensor([100 + i], dtype=torch.int64)
        cd.host_value = torch.tensor([200 + i], dtype=torch.int64)
        parent.children[i] = node
        nodes.append(node)
        parent = node
    return root, nodes


def _core(root, nodes, *, is_write_back: bool):
    core = mock.Mock()
    core.is_write_back = is_write_back
    core.root_node = root
    core.full_host_duplicates = {n.id: n for n in nodes}
    core.evictable_device_leaves = set()
    core.kv_events = mock.Mock()
    core.write_back_duplicate_reclaim_digest = 0
    core.components_by_type = {BASE: mock.Mock(component_type=BASE)}
    core._can_reclaim_full_host_duplicate = mock.Mock(
        side_effect=lambda node, require_host_subtree_leaf=False: (
            UnifiedTreeCore._can_reclaim_full_host_duplicate(
                core, node, require_host_subtree_leaf
            )
        )
    )
    core._release_full_host_duplicate = mock.Mock(
        side_effect=lambda node, tracker, df, hf, **kw: _release(
            core, node, tracker, **kw
        )
    )
    return core


def _release(core, node, tracker, *, require_host_subtree_leaf=False):
    """Stand-in for the real release: assert the guard, drop Full host only."""
    assert UnifiedTreeCore._can_reclaim_full_host_duplicate(
        core, node, require_host_subtree_leaf
    ), f"node {node.id} is not a reclaimable Full host duplicate"
    freed = len(node.component_data[BASE].host_value)
    node.component_data[BASE].host_value = None
    tracker[BASE] += freed
    core.write_back_duplicate_reclaim_digest = (
        core.write_back_duplicate_reclaim_digest * 1000003 + node.id + 1
    ) & ((1 << 48) - 1)
    core.released.append(node)


def _run(core, num_tokens, *, require_host_subtree_leaf):
    core.released = []
    tracker = {BASE: 0}
    UnifiedTreeCore._reclaim_full_host_duplicates(
        core,
        num_tokens,
        tracker,
        {BASE: []},
        {BASE: []},
        require_host_subtree_leaf=require_host_subtree_leaf,
    )
    return tracker[BASE], core.released


def _assert_prefix_closed(testcase, root):
    """No node may hold Full host while its parent does not (write_through)."""
    stack = [root]
    while stack:
        node = stack.pop()
        for child in node.children.values():
            if child.backuped and node is not root:
                testcase.assertTrue(
                    node.backuped,
                    f"node {child.id} backed up under non-backed-up parent {node.id}",
                )
            stack.append(child)


class TestWriteThroughHostDuplicateReclaim(unittest.TestCase):
    def test_deepest_host_copy_is_released_first(self):
        root, nodes = _chain(3)
        core = _core(root, nodes, is_write_back=False)

        freed, released = _run(core, 1, require_host_subtree_leaf=True)

        self.assertEqual(freed, 1)
        self.assertEqual(released, [nodes[-1]])
        self.assertIsNone(nodes[-1].component_data[BASE].host_value)
        # Device copy stays -> the prefix is still served by L1.
        self.assertIsNotNone(nodes[-1].component_data[BASE].value)
        _assert_prefix_closed(self, root)

    def test_ancestors_are_released_in_later_passes_without_breaking_contiguity(self):
        root, nodes = _chain(3)
        core = _core(root, nodes, is_write_back=False)

        freed, released = _run(core, 3, require_host_subtree_leaf=True)

        self.assertEqual(freed, 3)
        self.assertEqual(released, [nodes[2], nodes[1], nodes[0]])
        _assert_prefix_closed(self, root)
        # Nothing was deleted: the tree still routes the full chain on device.
        self.assertEqual(len(nodes[2].children), 0)
        self.assertEqual(list(nodes[1].children.values()), [nodes[2]])

    def test_a_deep_chain_is_reclaimed_to_the_demand_in_one_call(self):
        """A 12-level chain must yield 12 K tokens, not one level per call.

        Measured on the r61 probe: a fixed 4-pass walk released 0.5-6.6 K tokens
        against a 4.9-10 K staging demand, so the restore still failed; the walk
        is now demand-driven (one tree level per pass, capped).
        """
        root, nodes = _chain(12)
        core = _core(root, nodes, is_write_back=False)

        freed, released = _run(core, 12, require_host_subtree_leaf=True)

        self.assertEqual(freed, 12)
        self.assertEqual(released, list(reversed(nodes)))
        _assert_prefix_closed(self, root)

    def test_the_walk_stops_at_the_demand(self):
        root, nodes = _chain(12)
        core = _core(root, nodes, is_write_back=False)

        freed, released = _run(core, 5, require_host_subtree_leaf=True)

        self.assertEqual(freed, 5)
        self.assertEqual(released, list(reversed(nodes))[:5])

    def test_root_host_copy_is_never_released(self):
        root, nodes = _chain(2)
        root.component_data[BASE].host_value = torch.tensor([1], dtype=torch.int64)
        core = _core(root, [root, *nodes], is_write_back=False)

        _freed, released = _run(core, 64, require_host_subtree_leaf=True)

        self.assertNotIn(root, released)
        self.assertIsNotNone(root.component_data[BASE].host_value)

    def test_locked_child_blocks_the_release_of_its_ancestors(self):
        root, nodes = _chain(3)
        nodes[2].component_data[BASE].host_lock_ref = 1
        core = _core(root, nodes, is_write_back=False)

        freed, released = _run(core, 3, require_host_subtree_leaf=True)

        self.assertEqual(freed, 0)
        self.assertEqual(released, [])
        # The lock barrier also protects the parents: their host set stays
        # prefix-closed and the pinned slice is never dropped.
        self.assertIsNotNone(nodes[2].component_data[BASE].host_value)
        _assert_prefix_closed(self, root)

    def test_in_flight_dma_blocks_the_node_and_its_ancestors(self):
        root, nodes = _chain(2)
        nodes[1].load_back_pending_id = 77
        core = _core(root, nodes, is_write_back=False)

        freed, released = _run(core, 2, require_host_subtree_leaf=True)

        self.assertEqual(freed, 0)
        self.assertEqual(released, [])

    def test_imminent_demote_leaf_is_spared_then_taken(self):
        root, nodes = _chain(1)
        core = _core(root, nodes, is_write_back=False)
        core.evictable_device_leaves = {nodes[0]}

        # Only the spared node is available -> the second pass still frees it.
        freed, released = _run(core, 1, require_host_subtree_leaf=True)

        self.assertEqual(freed, 1)
        self.assertEqual(released, [nodes[0]])

    def test_write_back_keeps_releasing_without_the_subtree_rule(self):
        root, nodes = _chain(2)
        core = _core(root, nodes, is_write_back=True)

        freed, released = _run(core, 2, require_host_subtree_leaf=False)

        self.assertEqual(freed, 2)
        self.assertEqual(set(released), set(nodes))


class TestHostDuplicateReclaimIsWiredIntoWriteThroughEviction(unittest.TestCase):
    def test_drive_host_eviction_reclaims_duplicates_under_write_through(self):
        root, nodes = _chain(2)
        core = _core(root, nodes, is_write_back=False)
        core._reclaim_full_host_duplicates = mock.Mock()
        core.components_by_type[BASE].drive_host_eviction = mock.Mock()

        UnifiedTreeCore.drive_host_eviction(core, BASE, 4096)

        core._reclaim_full_host_duplicates.assert_called_once()
        kwargs = core._reclaim_full_host_duplicates.call_args.kwargs
        self.assertTrue(kwargs["require_host_subtree_leaf"])

    def test_drive_host_eviction_keeps_the_write_back_ordering(self):
        root, nodes = _chain(2)
        core = _core(root, nodes, is_write_back=True)
        core._reclaim_full_host_duplicates = mock.Mock()
        core.components_by_type[BASE].drive_host_eviction = mock.Mock()

        UnifiedTreeCore.drive_host_eviction(core, BASE, 4096)

        kwargs = core._reclaim_full_host_duplicates.call_args.kwargs
        self.assertFalse(kwargs["require_host_subtree_leaf"])


if __name__ == "__main__":
    unittest.main()


class TestSnapshotWalkersTolerateDeletedNodes(unittest.TestCase):
    """A snapshot heap must not hand a dead node id to the walk.

    r61 candidate-reclaim crashed with ``KeyError: 334`` in
    ``TreeCore.evict_device_leaf``: reclaiming a device-resident duplicate's
    host layer makes that leaf *unbacked*, so device eviction deletes it (and
    cascade-deletes tombstone ancestors) mid-walk, while the heap built at
    ``evict_device_start`` still holds the object and the leaf set still holds
    a stale entry.
    """

    def _component(self, *, is_host: bool):
        from sglang.srt.mem_cache.unified_cache.components.full_component import (
            FullComponent,
        )

        comp = FullComponent.__new__(FullComponent)
        return comp, is_host

    def test_device_walk_drops_a_stale_leaf_entry(self):
        from sglang.srt.mem_cache.unified_cache.components.full_component import (
            FullComponent,
        )

        node = UnifiedTreeNode((BASE,))
        node.component_data[BASE].value = torch.tensor([1], dtype=torch.int64)
        core = mock.Mock()
        core.evictable_device_leaves = {node}
        core.evictable_host_leaves = set()
        core.node_exists.return_value = False

        comp = FullComponent.__new__(FullComponent)
        comp.component_type = BASE
        comp.tree_core = core
        comp._evict_device_heap = [(0, node)]
        comp._evict_device_last_node = None
        comp._evict_device_request_cnt = 1
        comp._ensure_eviction_strategy = lambda: None

        result = comp._evict_device_next_node({BASE: 0}, {BASE: []}, {BASE: []})

        self.assertIsNone(result)
        # The stale entry is swept so the next walk does not re-pop it.
        self.assertEqual(core.evictable_device_leaves, set())

    def test_host_walk_drops_a_stale_leaf_entry(self):
        from sglang.srt.mem_cache.unified_cache.components.full_component import (
            FullComponent,
        )

        node = UnifiedTreeNode((BASE,))
        node.component_data[BASE].host_value = torch.tensor([1], dtype=torch.int64)
        core = mock.Mock()
        core.evictable_device_leaves = set()
        core.evictable_host_leaves = {node}
        core.node_exists.return_value = False

        comp = FullComponent.__new__(FullComponent)
        comp.component_type = BASE
        comp.tree_core = core
        comp._ensure_eviction_strategy = lambda: None
        comp.session_ref_eviction_strategy = lambda n: 0

        tracker = {BASE: 0}
        comp.drive_host_eviction(64, tracker, {BASE: []}, {BASE: []})

        self.assertEqual(tracker[BASE], 0)
        core._evict_host_leaf.assert_not_called()
        self.assertEqual(core.evictable_host_leaves, set())

    def test_evict_device_leaf_of_a_deleted_node_is_a_noop(self):
        core = mock.Mock()
        core.node_exists.return_value = False

        result = UnifiedTreeCore.evict_device_leaf(core, 334, False)

        self.assertEqual(result.tracker, {})
        self.assertIsNone(result.backup_kv)
        core.node_by_id.assert_not_called()

    def test_demote_of_a_deleted_node_is_a_noop(self):
        core = mock.Mock()
        core.node_exists.return_value = False

        result = UnifiedTreeCore.demote(core, 334)

        self.assertEqual(result.tracker, {})
        core.node_by_id.assert_not_called()
