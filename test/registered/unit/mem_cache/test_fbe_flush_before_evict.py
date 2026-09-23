"""Unit tests for the WriteBack mamba flush-before-evict invariant (FBE).

Root cause (coder-l0-loss-e1, gate2 FAIL): a mamba host checkpoint that is
not yet L3-durable can be host-evicted before its deferred L3 persist runs;
the BACKUP_STORAGE gate then silently drops the sidecar and the checkpoint
is lost from device + host + L3. The fix (decision (a)+(b), frozen scope):
`MambaComponent.drive_host_eviction` must spare a non-durable mamba host
victim, trigger write_backup_storage for it (which pins the host copy until
the L3 ack), and skip the eviction this round.

Black-box behaviors pinned here:
- non-durable mamba host victim -> deferred write_backup_storage + spared
  (host_value retained), never evicted before durable.
- durable mamba host victim -> normal eviction, no flush (no extra L3 write).
- already-pinned victim (host_lock_ref != 0) -> spared, but no repeated flush
  (no double pin / no duplicate write_backup_storage).
- storage disabled -> no flush path at all (normal pre-fix eviction).
- both the host-leaf atomic path and the internal-tombstone path carry the
  durable check.

Runs the real MambaComponent.drive_host_eviction / evict_component against a
real UnifiedTreeCore + real host LRU (the cursor's host_lock skip is the
mechanism that protects a pinned victim from a later round), with stub FULL
component and no CUDA pools.
"""

import os
import sys
import unittest
from array import array as _array
from types import SimpleNamespace
from unittest import mock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PYTHON_DIR = os.path.join(_REPO_ROOT, "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import torch  # noqa: F401  (real sglang modules import torch)

from sglang.srt.mem_cache.radix_cache import RadixKey as _RadixKey
from sglang.srt.mem_cache.unified_cache.components import (
    BASE_COMPONENT_TYPE,
    ComponentType as _ct,
    EvictLayer as _evict_layer,
)
from sglang.srt.mem_cache.unified_cache.components.mamba_component import (
    MambaComponent as _MambaComponent,
)
from sglang.srt.mem_cache.unified_cache.unified_tree_core import (
    UnifiedTreeCore as _RealTreeCore,
)


class _FullComponentStub:
    """Minimal FULL component for the real-tree fixture: the host-leaf atomic
    eviction path (tree_core._evict_host_leaf iterates every component's
    evict_component) and the host lock surface must exist. mamba host values
    on a node do not make it a host leaf -- that needs FULL host_value -- so
    the internal-tombstone mamba path never calls FULL.evict_component."""

    component_type = BASE_COMPONENT_TYPE

    def __init__(self):
        self.tree_core = None

    def eviction_priority(self, is_leaf: bool) -> int:
        return 0 if is_leaf else 2

    def node_has_component_data(self, node, target=None):
        cd = node.component_data[self.component_type]
        if target is None or _evict_layer.DEVICE in target:
            return cd.value is not None
        return cd.host_value is not None

    def discard_deleted_session_leaf(self, node):
        pass

    def evict_component(
        self, node, device_frees, host_frees, target=_evict_layer.DEVICE
    ):
        cd = node.component_data[self.component_type]
        freed = 0
        host_freed = 0
        if _evict_layer.DEVICE in target and cd.value is not None:
            device_frees[self.component_type].append(cd.value)
            freed = len(cd.value)
            self.tree_core.component_evictable_size_[self.component_type] -= freed
            cd.value = None
        if _evict_layer.HOST in target and cd.host_value is not None:
            host_freed = len(cd.host_value)
            host_frees[self.component_type].append(cd.host_value)
            cd.host_value = None
        return freed, host_freed

    def acquire_component_lock(self, node, result, lock_host: bool = False):
        if lock_host:
            cd = node.component_data[self.component_type]
            if cd.host_value is None:
                return result
            cd.host_lock_ref += 1
        return result

    def release_component_lock(self, node, params, lock_host: bool = False):
        if lock_host:
            cd = node.component_data[self.component_type]
            if cd.host_lock_ref == 0:
                return
            cd.host_lock_ref -= 1
            self.tree_core._update_evictable_leaf_sets(node)

    def build_hicache_transfers(self, node, phase, **_kw):
        return None

    def commit_hicache_transfer(self, *a, **k):
        return None

    def redistribute_on_node_split(self, new_parent, child):
        return None


class FbeHostEvictionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orig_write_backup_storage = None

    def _make_fixture(self, *, enable_storage=True):
        params = SimpleNamespace(
            page_size=1,
            is_eagle=False,
            enable_session_radix_cache=False,
            eviction_policy="lru",
            token_to_kv_pool_allocator=None,
            enable_kv_cache_events=False,
        )
        full = _FullComponentStub()
        # Real mamba component bound to the tree core, bypassing the pool-
        # heavy __init__ (drive_host_eviction only reads cache + tree_core).
        mamba = object.__new__(_MambaComponent)
        tree_core = _RealTreeCore(
            params,
            {BASE_COMPONENT_TYPE: full, _ct.MAMBA: mamba},
        )
        full.tree_core = tree_core
        mamba.tree_core = tree_core
        mamba.component_type = _ct.MAMBA
        tree_core.enable_storage = enable_storage
        # A stub cache: the component calls self.cache.write_backup_storage.
        flushed = []
        mamba.cache = SimpleNamespace(
            write_backup_storage=flushed.append,
        )
        return tree_core, mamba, flushed

    def _mamba_host_internal_node(self, tree_core, node_id=None):
        """A mamba-host-only internal node: mamba host_value present, FULL
        host_value None (so it is not a host leaf) -> internal tombstone path."""
        node = tree_core._new_node()
        node.parent = tree_core.root_node
        node.key = _RadixKey(_array("q", [node_id if node_id else node.id]), None)
        child_key = node.key.child_key(tree_core.page_size)
        tree_core.root_node.children[child_key] = node
        node.component_data[_ct.MAMBA].host_value = list(range(8))
        tree_core.host_lru_lists[_ct.MAMBA].insert_mru(node)
        return node

    def _mamba_host_leaf(self, tree_core):
        """A real host leaf: mamba AND FULL host_value present, device tombstoned,
        evicted+backuped -> atomic host-leaf path."""
        node = tree_core._new_node()
        node.parent = tree_core.root_node
        node.key = _RadixKey(_array("q", [node.id + 1000]), None)
        child_key = node.key.child_key(tree_core.page_size)
        tree_core.root_node.children[child_key] = node
        node.component_data[BASE_COMPONENT_TYPE].value = None
        node.component_data[BASE_COMPONENT_TYPE].host_value = list(range(8))
        node.component_data[_ct.MAMBA].host_value = list(range(8))
        tree_core.host_lru_lists[_ct.MAMBA].insert_mru(node)
        tree_core._update_evictable_leaf_sets(node)
        return node

    def _drive(self, tree_core, num_tokens):
        # Mirrors UnifiedRadixCache.evict_host: run the walk, then drain the
        # collected frees so the real DriveHostEvictionResult's __del__ guard
        # (undrained values) does not fire.
        result = tree_core.drive_host_eviction(_ct.MAMBA, num_tokens)
        # Drain (clear) the collected frees -- the real cache feeds them to
        # free_host_values; here the stub nodes carry no real host pool.
        result.host_frees.clear()
        result.device_frees.clear()
        return result.tracker

    # -- invariant: non-durable spared + flushed + never evicted early -------

    def test_non_durable_internal_victim_spared_and_flushed(self):
        tree_core, _mamba, flushed = self._make_fixture()
        node = self._mamba_host_internal_node(tree_core)
        # Not L3-durable: storage_enabled True, no storage flag set.
        self.assertFalse(tree_core.is_l3_durable(node.id))
        self._drive(tree_core, 100)
        # Flush triggered for the spared victim, exactly once.
        self.assertEqual(flushed, [node.id])
        # The victim was NOT evicted this round: host_value intact, still in LRU.
        self.assertIsNotNone(node.component_data[_ct.MAMBA].host_value)
        self.assertTrue(tree_core.host_lru_lists[_ct.MAMBA].in_list(node))

    def test_non_durable_host_leaf_victim_spared_and_flushed(self):
        # The atomic host-leaf path carries the same durable check: an
        # evictable host leaf whose mamba host is non-durable is spared
        # (not atomically evicted) and its L3 persist is triggered.
        tree_core, _mamba, flushed = self._make_fixture()
        node = self._mamba_host_leaf(tree_core)
        self.assertFalse(tree_core.is_l3_durable(node.id))
        self.assertIn(node, tree_core.evictable_host_leaves)
        self._drive(tree_core, 100)
        self.assertEqual(flushed, [node.id])
        self.assertIsNotNone(node.component_data[_ct.MAMBA].host_value)
        self.assertTrue(tree_core.host_lru_lists[_ct.MAMBA].in_list(node))

    # -- invariant: durable -> normal eviction, no flush --------------------

    def test_durable_internal_victim_evicted_without_flush(self):
        tree_core, _mamba, flushed = self._make_fixture()
        node = self._mamba_host_internal_node(tree_core)
        node.storage_persisted = True  # L3-durable by written+acked
        self.assertTrue(tree_core.is_l3_durable(node.id))
        self._drive(tree_core, 100)
        # No flush for a durable victim; it is evicted normally.
        self.assertEqual(flushed, [])
        self.assertIsNone(node.component_data[_ct.MAMBA].host_value)
        self.assertFalse(tree_core.host_lru_lists[_ct.MAMBA].in_list(node))

    def test_durable_host_leaf_evicted_atomically_without_flush(self):
        tree_core, _mamba, flushed = self._make_fixture()
        node = self._mamba_host_leaf(tree_core)
        node.storage_persisted = True
        self._drive(tree_core, 100)
        self.assertEqual(flushed, [])
        self.assertIsNone(node.component_data[_ct.MAMBA].host_value)
        self.assertFalse(tree_core.host_lru_lists[_ct.MAMBA].in_list(node))

    def test_storage_restored_counts_durable(self):
        # is_l3_durable also covers the restore source: a node just read back
        # from L3 must be evictable without a redundant persist.
        tree_core, _mamba, flushed = self._make_fixture()
        node = self._mamba_host_internal_node(tree_core)
        node.storage_restored = True
        self.assertTrue(tree_core.is_l3_durable(node.id))
        self._drive(tree_core, 100)
        self.assertEqual(flushed, [])
        self.assertIsNone(node.component_data[_ct.MAMBA].host_value)

    # -- invariant: already-pinned spared, no duplicate flush ----------------

    def test_pinned_victim_spared_without_duplicate_flush(self):
        # A node already pinned by an in-flight L3 write (host_lock_ref != 0)
        # must be spared (the pin protects the host copy) and must NOT trigger
        # a second write_backup_storage (double pin).
        tree_core, mamba, flushed = self._make_fixture()
        node = self._mamba_host_internal_node(tree_core)
        tree_core.inc_host_lock_ref(node.id)  # simulates the L3 write pin
        self.assertEqual(node.component_data[_ct.MAMBA].host_lock_ref, 1)
        self._drive(tree_core, 100)
        self.assertEqual(flushed, [])
        self.assertIsNotNone(node.component_data[_ct.MAMBA].host_value)
        # Still pinned (the cache's write_backup_storage was never called, so
        # it can't have double-incremented).
        self.assertEqual(node.component_data[_ct.MAMBA].host_lock_ref, 1)

    # -- invariant: storage disabled -> pre-fix eviction, no flush -----------

    def test_storage_disabled_evicts_without_flush(self):
        # Outside HiCache (enable_storage False) is_l3_durable is always
        # False, so the flush gate must be off or NO mamba host is ever
        # evictable again. Pre-fix behavior is preserved.
        tree_core, _mamba, flushed = self._make_fixture(enable_storage=False)
        node = self._mamba_host_internal_node(tree_core)
        self._drive(tree_core, 100)
        self.assertEqual(flushed, [])
        self.assertIsNone(node.component_data[_ct.MAMBA].host_value)
        self.assertFalse(tree_core.host_lru_lists[_ct.MAMBA].in_list(node))

    # -- invariant: no deadlock / both branches covered ----------------------

    def test_pin_then_ack_returns_victim_to_eviction_pool(self):
        # After the flush's pin is released (the L3 ack dec_host_lock_ref),
        # the fully durable node becomes a normal eviction candidate again --
        # the release path (mamba release_component_lock) re-inserts it into
        # the host LRU. Drives the pin -> ack -> durable -> evict cycle in
        # the same node.
        tree_core, _mamba, flushed = self._make_fixture()
        node = self._mamba_host_internal_node(tree_core)
        # Round 1: non-durable -> spared + flushed.
        self._drive(tree_core, 100)
        self.assertEqual(flushed, [node.id])
        self.assertIsNotNone(node.component_data[_ct.MAMBA].host_value)
        # The cache's write_backup_storage pins the host copy. Simulate the
        # synchronous pin exactly as _write_backup_storage_node does, then the
        # ack release (the _drain_backup dec_host_lock_ref path).
        tree_core.inc_host_lock_ref(node.id)
        self.assertFalse(tree_core.host_lru_lists[_ct.MAMBA].in_list(node))
        # The ack arrived: node is now durable, and the release re-inserts the
        # host slice into the LRU (mamba release_component_lock).
        node.storage_persisted = True
        # Ack: release the pin exactly once.
        tree_core.dec_host_lock_ref(node.id)
        self.assertEqual(node.component_data[_ct.MAMBA].host_lock_ref, 0)
        self.assertTrue(tree_core.host_lru_lists[_ct.MAMBA].in_list(node))
        # Round 2: durable -> normal eviction, no second flush.
        self._drive(tree_core, 100)
        self.assertEqual(flushed, [node.id])
        self.assertIsNone(node.component_data[_ct.MAMBA].host_value)


if __name__ == "__main__":
    unittest.main(verbosity=2)