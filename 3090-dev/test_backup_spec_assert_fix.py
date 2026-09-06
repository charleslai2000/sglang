"""P0 unit tests: build_backup_spec `assert device_value is not None` fix.

Root cause (phase2-backupassert-architect-e3): the storage-gap-fill loop in
`UnifiedRadixCache.write_backup_storage` (RC:2143-2144) routed every gap node
with `is_backuped() == False` into the device->host backup
(`_execute_and_commit_kv_backup`), assuming "not backuped => has a device
value". That assumption is wrong: a legal cache state is an UNBACKED node whose
device value was already released (host-only unbacked ancestor, or a
forced-miss tombstone with no KV in any tier). The D->H backup then reached
`_build_backup_spec`'s `assert device_value is not None` (TC:2037) and crashed.

Fix semantics (frozen): explicitly check the device value before building a
D->H backup spec. Unbacked + device present -> keep the device->host path.
Unbacked + device absent + host present -> storage-write (host->L3) path.
Neither device nor host -> explicit invalid / un-backupable skip, recorded,
never silently faked.

These tests drive the real `write_backup_storage` gap-fill against a real
`UnifiedTreeCore` with a stub FULL component and no CUDA pools, stubbing only
the leaf sink methods (`_execute_and_commit_kv_backup` and
`_write_backup_storage_node`) to observe which path each gap node routes to.
"""

import os
import sys
import unittest
from array import array as _array
from types import SimpleNamespace

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
from sglang.srt.mem_cache.unified_cache.unified_tree_core import (
    UnifiedTreeCore as _RealTreeCore,
)
from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache as _RadixCache


class _FullComponentStub:
    """Minimal FULL component: the gap-fill path never drives FULL component
    eviction (the D->H backup is stubbed), so only the tree-core attachment and
    a transfer-free surface are needed."""

    component_type = BASE_COMPONENT_TYPE

    def __init__(self):
        self.tree_core = None

    def eviction_priority(self, is_leaf: bool) -> int:
        return 0 if is_leaf else 2

    def node_has_component_data(self, node, target=None):
        return True

    def discard_deleted_session_leaf(self, node):
        pass

    def evict_component(self, node, device_frees, host_frees, target=_evict_layer.DEVICE):
        return 0, 0

    def acquire_component_lock(self, node, result, lock_host: bool = False):
        return result

    def release_component_lock(self, node, params, lock_host: bool = False):
        pass

    def build_hicache_transfers(self, node, phase, **_kw):
        return None

    def commit_hicache_transfer(self, *a, **k):
        return None

    def redistribute_on_node_split(self, new_parent, child):
        return None


def _link(tree_core, parent, token):
    """Create a child of `parent` with a single-token key, registered in the
    arena, and return it."""
    node = tree_core._new_node()
    node.parent = parent
    node.key = _RadixKey(_array("q", [token]), None)
    child_key = node.key.child_key(tree_core.page_size)
    parent.children[child_key] = node
    node.component_data[BASE_COMPONENT_TYPE].value = torch.tensor([token])
    return node


class BackupSpecAssertFixTests(unittest.TestCase):
    def _make_cache(self, *, enable_storage=True):
        """A real tree core + a skeleton cache holding the real
        write_backup_storage and its gap-fill, with the L3 sink methods
        stubbed to record routing."""
        params = SimpleNamespace(
            page_size=1,
            is_eagle=False,
            enable_session_radix_cache=False,
            eviction_policy="lru",
            token_to_kv_pool_allocator=None,
            enable_kv_cache_events=False,
        )
        full = _FullComponentStub()
        tree_core = _RealTreeCore(params, {BASE_COMPONENT_TYPE: full})
        full.tree_core = tree_core

        cache = object.__new__(_RadixCache)
        cache.tree_core = tree_core
        cache.enable_storage = enable_storage
        cache.cache_controller = SimpleNamespace(storage_failure_reason=None)
        cache.hicache_storage_pass_prefix_keys = False
        cache.ongoing_write_through = {}
        cache._pending_storage_writes = []
        cache._storage_persist_skip_count = 0
        cache._storage_gap_skipped_d2h_count = 0
        cache._storage_gap_skipped_nokv_count = 0
        cache._drain_write_through_acks = lambda: None
        cache._flush_pending_storage_writes = lambda: None

        cache.d2h_backups = []
        cache.l3_writes = []

        def _commit_d2h(action, write_back=False):
            # Faithful to the real _execute_and_commit_kv_backup: the D->H
            # backup ends with commit_backup, which records a host copy and
            # makes the node `backuped` (host_value set). Without this the
            # second loop below would see the node as still unbacked.
            for nid in action.node_ids:
                node = tree_core.node_by_id(nid)
                dv = node.component_data[BASE_COMPONENT_TYPE].value
                node.component_data[BASE_COMPONENT_TYPE].host_value = dv
                cache.d2h_backups.append(nid)

        cache._execute_and_commit_kv_backup = _commit_d2h
        cache._write_backup_storage_node = lambda nid: cache.l3_writes.append(nid)
        return tree_core, cache

    # -- not backuped + device present -> original device->host path (no regress)

    def test_unbacked_device_present_takes_d2h_path(self):
        tree_core, cache = self._make_cache()
        a = _link(tree_core, tree_core.root_node, 1)   # unbacked, device present
        b = _link(tree_core, a, 2)                     # storage target
        # a and b: host_value None -> backuped False; device value present.
        self.assertFalse(a.backuped)
        self.assertIsNotNone(a.component_data[BASE_COMPONENT_TYPE].value)
        cache.write_backup_storage(b.id)
        # Every unbacked gap node with a device value routes to D->H backup
        # (both a and b). The D->H commit makes them `backuped`, so the
        # storage-write loop then persists their host copies to L3 -- the
        # correct post-backup L3 chain, exactly as before the fix.
        self.assertEqual(sorted(cache.d2h_backups), sorted([a.id, b.id]))
        self.assertEqual(sorted(cache.l3_writes), sorted([a.id, b.id]))
        self.assertEqual(cache._storage_gap_skipped_d2h_count, 0)

    # -- not backuped + device absent + host present -> storage (host->L3) path

    def test_unbacked_device_absent_host_present_goes_storage(self):
        tree_core, cache = self._make_cache()
        a = _link(tree_core, tree_core.root_node, 1)
        a.component_data[BASE_COMPONENT_TYPE].value = None          # device released
        a.component_data[BASE_COMPONENT_TYPE].host_value = torch.tensor([1])  # host copy
        b = _link(tree_core, a, 2)
        self.assertTrue(a.backuped)          # host_value present
        self.assertIsNone(a.component_data[BASE_COMPONENT_TYPE].value)
        cache.write_backup_storage(b.id)
        # host-only unbacked-by-device ancestor must NOT go D->H; it persists
        # to L3 from its host copy.
        self.assertNotIn(a.id, cache.d2h_backups)
        self.assertIn(a.id, cache.l3_writes)
        self.assertEqual(cache._storage_gap_skipped_d2h_count, 0)

    # -- device absent + host absent -> explicit invalid skip, no crash, recorded

    def test_both_absent_skipped_not_crashed(self):
        tree_core, cache = self._make_cache()
        a = _link(tree_core, tree_core.root_node, 1)
        a.component_data[BASE_COMPONENT_TYPE].value = None          # device released
        a.component_data[BASE_COMPONENT_TYPE].host_value = None     # no host copy
        b = _link(tree_core, a, 2)
        self.assertFalse(a.backuped)
        self.assertIsNone(a.component_data[BASE_COMPONENT_TYPE].value)
        # Before the fix, this reached _build_backup_spec's assert and crashed.
        cache.write_backup_storage(b.id)   # must not raise AssertionError
        self.assertNotIn(a.id, cache.d2h_backups)
        self.assertNotIn(a.id, cache.l3_writes)
        self.assertEqual(cache._storage_gap_skipped_d2h_count, 1)
        self.assertEqual(cache._storage_gap_skipped_nokv_count, 1)

    # -- repeated invocation is idempotent (no crash, no double work)

    def test_repeated_invocation_idempotent(self):
        tree_core, cache = self._make_cache()
        a = _link(tree_core, tree_core.root_node, 1)
        a.component_data[BASE_COMPONENT_TYPE].value = None
        a.component_data[BASE_COMPONENT_TYPE].host_value = None
        b = _link(tree_core, a, 2)
        b.component_data[BASE_COMPONENT_TYPE].value = None
        b.component_data[BASE_COMPONENT_TYPE].host_value = None
        # Every repeated call re-walks the same both-absent gap; each node is
        # skipped exactly once per call, never crashes, never D->H backs up,
        # never fabricates an L3 write.
        cache.write_backup_storage(b.id)
        cache.write_backup_storage(b.id)
        cache.write_backup_storage(b.id)
        self.assertEqual(cache._storage_gap_skipped_d2h_count, 3 * 2)
        self.assertEqual(cache._storage_gap_skipped_nokv_count, 3 * 2)
        self.assertEqual(cache.d2h_backups, [])
        self.assertEqual(cache.l3_writes, [])

    # -- storage disabled -> write_backup_storage is a no-op (pre-fix behavior)

    def test_storage_disabled_noop(self):
        tree_core, cache = self._make_cache(enable_storage=False)
        a = _link(tree_core, tree_core.root_node, 1)
        a.component_data[BASE_COMPONENT_TYPE].value = None
        b = _link(tree_core, a, 2)
        cache.write_backup_storage(b.id)
        self.assertEqual(cache.d2h_backups, [])
        self.assertEqual(cache.l3_writes, [])
        self.assertEqual(cache._storage_gap_skipped_d2h_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
