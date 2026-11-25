#!/usr/bin/env python3
"""CPU-only probe of host refill vs host-leaf eviction ordering."""

from array import array
from unittest import mock

import torch

from sglang.srt.mem_cache.unified_cache.components import ComponentType
from sglang.srt.mem_cache.unified_cache.unified_tree_core import UnifiedTreeCore
from sglang.srt.mem_cache.radix_cache import RadixKey


def main():
    core = object.__new__(UnifiedTreeCore)
    core.page_size = 1
    core.is_write_back = False
    core.root_node = mock.Mock()
    core.root_node.children = {}
    core.root_node.parent = None
    core.root_node.id = -1
    core.component_types = (ComponentType.FULL,)
    core.components_by_type = {ComponentType.FULL: mock.Mock()}
    core.components = (core.components_by_type[ComponentType.FULL],)
    core.full_host_duplicates = {}
    core.evictable_host_leaves = set()
    core.evictable_device_leaves = set()
    core.lru_lists = {ComponentType.FULL: mock.Mock(cache={})}
    core.host_lru_lists = {ComponentType.FULL: mock.Mock(cache={})}
    core._node_arena = {}
    core._register_node = lambda n: core._node_arena.__setitem__(n.id, n)
    core._unregister_node = lambda n: core._node_arena.pop(n.id, None)
    core._next_id = 0

    def mk(parent, ids, dev=None, host=None):
        from sglang.srt.mem_cache.unified_cache.unified_tree_core import UnifiedTreeNode

        n = UnifiedTreeNode((ComponentType.FULL,))
        n.id = core._next_id
        core._next_id += 1
        n.parent = parent
        n.key = RadixKey(array("q", ids))
        n.value = None
        n.hash_value = None
        n.children = {}
        cd = n.component_data[ComponentType.FULL]
        cd.value = dev
        cd.host_value = host
        cd.lock_ref = cd.host_lock_ref = 0
        core._register_node(n)
        parent.children[n.key.child_key(1)] = n
        return n

    parent = mk(core.root_node, [1], torch.tensor([1]), None)
    victim = mk(parent, [2], None, torch.tensor([2]))
    core._is_host_leaf = lambda n: (
        n is not core.root_node and n.evicted and n.backuped and not n.children
    )

    # Model the eligibility-to-unlink gap: the backed-up victim is host-only,
    # leaf-qualified and its parent has no host copy. It gains a child after
    # eligibility was sampled but before the eviction routine rechecks it.
    assert core._is_host_leaf(victim)
    refill = torch.tensor([4])
    result = UnifiedTreeCore.insert_host(core, victim.id, RadixKey(array("q", [4])), refill, ["h4"])
    assert result.inserted_host_node is not None
    assert not core._is_host_leaf(victim)

    # Production _evict_host_leaf revalidates and rejects this stale selection.
    # A parent-pointer removal without revalidation would instead orphan both
    # backed-up descendants below an unbacked ancestor.
    print(
        {
            "parent_id": parent.id,
            "victim_id": victim.id,
            "victim_parent_backed": parent.backuped,
            "victim_has_new_host_child": len(victim.children) == 1,
            "eviction_revalidated_live_leaf": not core._is_host_leaf(victim),
            "insert_host_result": result.inserted_host_node,
            "incident_first_transition_proven": False,
        }
    )


if __name__ == "__main__":
    main()
