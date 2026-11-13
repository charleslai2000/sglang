"""Regression coverage for Mamba transitions updating host-leaf eligibility."""

from collections import defaultdict
from dataclasses import dataclass
from types import SimpleNamespace
from unittest import mock

import torch

from sglang.srt.mem_cache.unified_cache.components import ComponentType, EvictLayer
from sglang.srt.mem_cache.unified_cache.components.mamba_component import MambaComponent
from sglang.test.ci.ci_register import register_cpu_ci
from sglang.test.test_utils import CustomTestCase

register_cpu_ci(est_time=1, suite="base-a-test-cpu")


class TestMambaHostEvictionMembership(CustomTestCase):
    def test_leaf_refresh_propagates_through_all_ancestors(self):
        from sglang.srt.mem_cache.unified_cache.unified_tree_core import (
            UnifiedTreeCore,
        )

        root = SimpleNamespace(parent=None)
        parent = SimpleNamespace(parent=root)
        node = SimpleNamespace(parent=parent)
        core = SimpleNamespace(_update_evictable_leaf_sets=mock.Mock())

        UnifiedTreeCore._update_evictable_leaf_sets_with_ancestors(core, node)

        self.assertEqual(
            [call.args[0] for call in core._update_evictable_leaf_sets.call_args_list],
            [node, parent, root],
        )

    def test_cascade_evict_recomputes_host_leaf_parent_after_full_demotion(self):
        """Device demotion changes its parent H-leaf status even if Full survives."""
        from sglang.srt.mem_cache.unified_cache.unified_tree_core import (
            UnifiedTreeCore,
        )

        parent = SimpleNamespace()
        node = SimpleNamespace(
            parent=parent,
            component_data={
                ComponentType.FULL: SimpleNamespace(value=None),
                ComponentType.MAMBA: SimpleNamespace(value=None),
            },
        )
        core = SimpleNamespace(
            components=(),
            components_by_type={},
            evictable_device_leaves=set(),
            _is_cascade_evict_leaf=mock.Mock(return_value=False),
            _update_evictable_leaf_sets=mock.Mock(),
            _update_evictable_leaf_sets_with_ancestors=mock.Mock(),
        )
        UnifiedTreeCore._cascade_evict(
            core,
            node,
            SimpleNamespace(component_type=ComponentType.MAMBA),
            defaultdict(int),
            defaultdict(list),
            defaultdict(list),
            target=EvictLayer.DEVICE,
        )
        core._update_evictable_leaf_sets_with_ancestors.assert_called_once_with(node)

    def test_ack_clears_pending_and_refreshes_membership_idempotently(self):
        from sglang.srt.mem_cache.unified_cache.unified_tree_core import (
            UnifiedTreeCore,
        )

        node = SimpleNamespace(write_through_pending_id=41)
        core = SimpleNamespace(
            node_by_id=mock.Mock(return_value=node),
            _update_evictable_leaf_sets=mock.Mock(),
            _update_duplicate_tracking=mock.Mock(),
            kv_events=SimpleNamespace(record_store=mock.Mock()),
        )

        UnifiedTreeCore.finish_write_through(core, [7], 41)
        self.assertIsNone(node.write_through_pending_id)
        core._update_evictable_leaf_sets.assert_called_once_with(node)
        core._update_duplicate_tracking.assert_called_once_with(node)

        # A duplicate/stale ACK is harmless: no second eligibility transition.
        UnifiedTreeCore.finish_write_through(core, [7], 41)
        core._update_evictable_leaf_sets.assert_called_once_with(node)
        core._update_duplicate_tracking.assert_called_once_with(node)
        self.assertEqual(core.kv_events.record_store.call_count, 2)

    def test_host_detach_recomputes_full_host_leaf_eligibility(self):
        """Mamba eviction must refresh the unified host-leaf index."""
        component_type = ComponentType.MAMBA
        parent = SimpleNamespace()
        node = SimpleNamespace(
            id=7,
            parent=parent,
            component_data={
                component_type: SimpleNamespace(
                    value=None,
                    host_value=torch.tensor([4]),
                    host_lock_ref=0,
                    session_ids=None,
                )
            },
            get_last_hash_value=lambda: "target-hash",
        )
        host_lru = mock.Mock()
        host_lru.in_list.return_value = False
        core = mock.Mock()
        core.host_lru_lists = {component_type: host_lru}
        core.enable_storage = False
        core.enable_session_radix_cache = False
        core._update_evictable_leaf_sets_with_ancestors = mock.Mock()
        component = SimpleNamespace(
            component_type=component_type,
            tree_core=core,
            cache=mock.Mock(),
        )
        device_frees = {component_type: []}
        host_frees = {component_type: []}

        freed, host_freed = MambaComponent.evict_component(
            component,
            node,
            device_frees,
            host_frees,
            target=EvictLayer.HOST,
        )

        self.assertEqual((freed, host_freed), (0, 1))
        self.assertIsNone(node.component_data[component_type].host_value)
        self.assertEqual(len(host_frees[component_type]), 1)
        self.assertTrue(torch.equal(host_frees[component_type][0], torch.tensor([4])))
        core._update_evictable_leaf_sets_with_ancestors.assert_called_once_with(node)
