"""Regression test: the D->H ack drain must not re-enter itself through the
L3 persist hook, and one drain pass must consume only the ack generation
present at entry (unbounded recursion seen on 3090 in load_back eviction).

The behavior that must not come back: finishing a write-through ack inside a
drain runs the anchor->leaf L3 gap-fill synchronously -- its D->H wait
re-enters the drain once per acked gap node. Persists are deferred and
flushed after the drain returns; a drain round claims exactly the acks
queued at its entry.

Runs the real UnifiedRadixCache drain/finish/gap-fill methods against stub
collaborators (no CUDA, no pools). Imports the real source either through the
installed package (torch available) or through a stubenv bootstrap that fakes
the sglang import tree (torch-less dev boxes).
"""

import importlib.util
import os
import sys
import types
import unittest
from enum import Enum
from types import SimpleNamespace

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PYTHON_DIR = os.path.join(_REPO_ROOT, "python")
_MODULE_PATH = os.environ.get(
    "DRAIN_TEST_MODULE_PATH",
    os.path.join(_PYTHON_DIR, "sglang", "srt", "mem_cache", "unified_radix_cache.py"),
)
sys.path.insert(0, _PYTHON_DIR)

try:
    import torch  # noqa: F401 -- real sglang modules import torch
except ImportError:
    torch = None


# ---------------------------------------------------------------------------
# Stubenv bootstrap (torch-less): fake the sglang import tree, then execute
# the REAL unified_radix_cache.py source against it.
# ---------------------------------------------------------------------------


def _fake_package(name, **names):
    mod = types.ModuleType(name)
    mod.__path__ = []  # submodules are pre-registered in sys.modules
    for key, value in names.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


def _identity_decorator(*args, **kwargs):
    def wrap(fn):
        return fn

    return wrap


def _install_stubenv():
    fake_torch = types.ModuleType("torch")
    fake_torch.distributed = types.ModuleType("torch.distributed")
    sys.modules["torch"] = fake_torch

    _fake_package("sglang")
    _fake_package("sglang.srt")
    _fake_package("sglang.srt.distributed")
    _fake_package("sglang.srt.distributed.communication_tags", P2PTag=object)
    _fake_package("sglang.srt.environ", envs=object())
    _fake_package("sglang.srt.managers")
    _fake_package("sglang.srt.managers.cache_controller", CacheOperation=object)
    _fake_package("sglang.srt.mem_cache")
    _fake_package("sglang.srt.mem_cache.base_prefix_cache", **{
        "BasePrefixCache": object,
        "DecLockRefParams": object,
        "DecLockRefResult": object,
        "EvictParams": object,
        # The real eviction path constructs this with keyword args.
        "EvictResult": type("EvictResult", (), {"__init__": lambda self, **kw: None}),
        "IncLockRefResult": object,
        "InitLoadBackParams": object,
        "InsertParams": object,
        "InsertResult": object,
        "MatchPrefixParams": object,
        "MatchResult": object,
    })
    _fake_package("sglang.srt.mem_cache.buffer_mode")
    _fake_package(
        "sglang.srt.mem_cache.buffer_mode.pipeline",
        BufferModePipeline=object,
        validate_buffer_only_stack=lambda *a, **k: None,
    )
    _fake_package(
        "sglang.srt.mem_cache.buffer_mode.storage_existence_cache",
        StorageExistenceCache=object,
    )
    _fake_package("sglang.srt.mem_cache.common", RetractionBackup=object)
    _fake_package("sglang.srt.mem_cache.hicache_storage", **{
        "PoolName": Enum("PoolName", {"KV": "kv", "SWA": "swa", "MAMBA": "mamba"}),
        "PoolTransfer": type("PoolTransfer", (), {"__init__": lambda self, **kw: None}),
        "SidecarPoolSpec": object,
    })
    _fake_package("sglang.srt.mem_cache.hybrid_cache")
    _fake_package(
        "sglang.srt.mem_cache.hybrid_cache.hybrid_cache_controller",
        HybridCacheController=object,
    )
    _fake_package("sglang.srt.mem_cache.memory_pool", MHATokenToKVPool=object)
    _fake_package("sglang.srt.mem_cache.radix_cache", RadixKey=object)
    _fake_package("sglang.srt.mem_cache.swa_memory_pool", SWAKVPool=object)
    _fake_package("sglang.srt.mem_cache.unified_cache")

    class _BackupKV:
        def __init__(self, node_ids):
            self.node_ids = node_ids

    _fake_package("sglang.srt.mem_cache.unified_cache.cache_action", **{
        "BackupKV": _BackupKV,
        "CacheAction": object,
        "ComponentAction": object,
        "FreeComponentDeviceSlot": object,
        "FreeDeviceKV": object,
        "FreeDeviceKVFullOnly": object,
        "ReplaceWriteThroughOnNodeSplit": object,
    })
    _component_type = Enum(
        "ComponentType", {"FULL": 0, "SWA": 1, "MAMBA": 2, "C128": 3}
    )
    _fake_package("sglang.srt.mem_cache.unified_cache.components", **{
        "ComponentType": _component_type,
        "CacheTransferPhase": Enum(
            "CacheTransferPhase",
            {
                "BACKUP_HOST": 0,
                "BACKUP_STORAGE": 1,
                "PREFETCH": 2,
                "LOAD_BACK": 3,
            },
        ),
        "BASE_COMPONENT_TYPE": _component_type.FULL,
        "FullComponent": object,
        "MambaComponent": object,
        "SWAComponent": object,
        "TreeComponent": object,
        "PrepareLoadBackResult": object,
    })
    _fake_package(
        "sglang.srt.mem_cache.unified_cache.session_ref_tracker",
        UnifiedSessionRefTracker=object,
    )
    _fake_package(
        "sglang.srt.mem_cache.unified_cache.storage_attachment",
        StorageAttachment=object,
    )
    _fake_package(
        "sglang.srt.mem_cache.unified_cache.tree_core_registry",
        create_tree_core=lambda *a, **k: None,
    )
    _fake_package("sglang.srt.mem_cache.unified_cache.unified_tree_core", **{
        "NodeId": int,
        "UnifiedTreeCore": object,
        "UnifiedTreeNode": object,
        "UnifiedLRUList": object,
    })
    _fake_package("sglang.srt.observability")
    _fake_package(
        "sglang.srt.observability.metrics_collector",
        StorageMetrics=object,
        StorageMetricsCollector=object,
    )
    _fake_package("sglang.srt.runtime_context", get_memory=lambda: None)
    _fake_package("sglang.srt.session")
    _fake_package(
        "sglang.srt.session.streaming_session", StreamingSession=object
    )
    _fake_package("sglang.srt.utils")
    _fake_package("sglang.srt.utils.common", ceil_align=lambda x: x)
    _fake_package(
        "sglang.srt.utils.rank_consensus_checker",
        rank_consensus=_identity_decorator,
    )


def _load_module():
    """Load the real module: installed package when torch exists, otherwise
    the stubenv bootstrap (same source file, fake sglang import tree)."""
    if torch is not None:
        from sglang.srt.mem_cache.unified_radix_cache import (
            _OngoingWriteThrough,
            UnifiedRadixCache,
        )

        return UnifiedRadixCache, _OngoingWriteThrough
    _install_stubenv()
    spec = importlib.util.spec_from_file_location(
        "stubenv_unified_radix_cache", _MODULE_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.UnifiedRadixCache, mod._OngoingWriteThrough


UnifiedRadixCache, _OngoingWriteThrough = _load_module()


# ---------------------------------------------------------------------------
# Stub collaborators (instant-completing D->H writes, one unpersisted chain
# per evicted leaf).
# ---------------------------------------------------------------------------


class _FakeEvent:
    def synchronize(self):
        pass

    def query(self):
        return True


class _FakeAck:
    def __init__(self, node_ids):
        self.node_ids = list(node_ids)
        self.finish_event = _FakeEvent()
        self.start_event = _FakeEvent()
        self.num_tokens_by_pool = None
        self.num_bytes = 0
        self.timing_enabled = False


class _DeviceValue:
    """Stands in for a device KV tensor: len() and numel() only."""

    def __len__(self):
        return 16

    def numel(self):
        return 16


class _FakeTreeCore:
    """Stub for UnifiedTreeCore: one unpersisted chain per evicted leaf.

    collect_storage_gap models the real walk (skip nodes whose L3 write was
    already submitted; no persisted anchor exists in the test). The arena is
    modeled by ``deleted``: lookups on a deleted node raise KeyError exactly
    like the real ``_node_arena[node_id]``.
    """

    def __init__(self, chains):
        self.chains = [list(chain) for chain in chains]
        self.backuped = set()
        self.storage_written = set()
        self.deleted = set()
        self.enable_storage = False  # mirrored by the cache's property

    def _chain_of(self, node_id):
        for chain in self.chains:
            if node_id in chain:
                return chain
        return []

    def mark_deleted(self, *node_ids):
        self.deleted.update(node_ids)

    def node_exists(self, node_id):
        return node_id not in self.deleted

    def collect_storage_gap(self, node_id):
        if node_id in self.deleted:
            raise KeyError(node_id)
        return [
            nid for nid in self._chain_of(node_id) if nid not in self.storage_written
        ]

    def is_backuped(self, node_id):
        if node_id in self.deleted:
            raise KeyError(node_id)
        return node_id in self.backuped

    def commit_backup(self, node_id, host_indices, comp_xfers):
        self.backuped.add(node_id)

    def is_storage_written(self, node_id):
        if node_id in self.deleted:
            raise KeyError(node_id)
        return node_id in self.storage_written

    def mark_storage_written(self, node_id):
        self.storage_written.add(node_id)

    def build_backup_spec(self, node_id):
        return _DeviceValue(), {}

    def build_storage_backup_spec(self, node_id, pass_prefix_keys):
        return SimpleNamespace(
            host_value=[0] * 16,
            token_ids=[0],
            hash_value=[],
            prefix_keys=[],
            comp_xfers={},
        )

    def mark_write_through_pending(self, node_id):
        pass

    def finish_write_through(self, node_ids, ack_id):
        pass

    def inc_lock_ref(self, node_id, skip_lock_components=()):
        return SimpleNamespace(to_dec_params=lambda: None)

    def dec_lock_ref(self, node_id, params, skip_swa=False):
        return SimpleNamespace()

    def inc_host_lock_ref(self, node_id):
        return SimpleNamespace(to_dec_params=lambda: None)


class _FakeController:
    """Stub for HybridCacheController: D->H writes complete immediately."""

    write_policy = "write_back"

    def __init__(self):
        self.ack_write_queue = []
        self.storage_ops = []
        self.mem_pool_host = SimpleNamespace(available_size=lambda: 1 << 30)
        # Storage threads never started: the local drain short-circuits.
        self.prefetch_hit_queue = None

    def write(self, device_indices, node_id=-1, extra_pools=None):
        self.ack_write_queue.append(_FakeAck([node_id]))
        return [0] * len(device_indices)

    def write_storage(
        self, host_value, token_ids, hash_value, prefix_keys, extra_pools=None
    ):
        self.storage_ops.append(len(self.storage_ops))
        return len(self.storage_ops) - 1


def _make_cache(tree_core):
    cache = object.__new__(UnifiedRadixCache)
    cache.disable = False
    # tree_core must exist before enable_storage: the property proxies onto it.
    cache.tree_core = tree_core
    cache.enable_storage = True
    cache.buffer_pipeline = None
    cache.sidecar_pool_specs = []
    cache.hicache_storage_pass_prefix_keys = False
    cache.metrics_collector = None
    cache.session = SimpleNamespace(
        try_inc_lock_ref=lambda *a, **k: None,
        try_dec_lock_ref=lambda *a, **k: None,
    )
    cache.ongoing_write_through = {}
    cache.ongoing_backup = {}
    cache._pending_storage_writes = []
    cache._storage_persist_skip_count = 0
    cache.host_memory_mode = "default"
    cache._drain_write_through_depth = 0
    cache.cache_controller = _FakeController()
    return cache


class _EvictTreeCore(_FakeTreeCore):
    """FakeTreeCore plus the eviction-walk surface: yields one unbacked
    D-leaf (node 42), records the demote order."""

    def __init__(self, chains, order):
        super().__init__(chains)
        self.order = order
        self._yielded = False

    def evict_device_start(self, component_type, request_cnt):
        pass

    def evict_device_end(self, component_type):
        pass

    def evict_device_next_node(self, component_type, tracker):
        if self._yielded:
            return SimpleNamespace(
                node_id=None, device_frees={}, host_frees={}, tracker={},
                made_progress=False,
            )
        self._yielded = True
        return SimpleNamespace(
            node_id=42, device_frees={}, host_frees={}, tracker={},
            made_progress=True,
        )

    def evict_device_leaf(self, node_id, is_write_back):
        return SimpleNamespace(
            backup_kv=SimpleNamespace(node_ids=[node_id]),
            tracker={},
            device_frees={},
            host_frees={},
        )

    def demote(self, node_id):
        self.order.append("demote")
        return SimpleNamespace(tracker={}, device_frees={}, host_frees={})


class DrainReentryRegressionTest(unittest.TestCase):
    def test_write_back_evict_flushes_after_demote(self):
        # The write-back eviction walk must demote a node before any pending
        # L3 persist flush runs: the persist gap-fill may evict_host, whose
        # duplicate-reclaim pass takes D-leaves and would strip the
        # just-acked host copy, breaking _demote's backuped precondition
        # (3090 crash: assert not node.evicted and node.backuped).
        order = []
        tree_core = _EvictTreeCore([[42]], order)
        tree_core.is_write_back = True
        cache = _make_cache(tree_core)
        components_mod = sys.modules[
            "sglang.srt.mem_cache.unified_cache.components"
        ]
        cache.tree_components = (components_mod.ComponentType.FULL,)

        orig_flush = cache._flush_pending_storage_writes

        def flush_with_trace():
            order.append("flush")
            orig_flush()

        cache._flush_pending_storage_writes = flush_with_trace

        # Stubenv mode: the ABC the real cache inherits from is faked, so the
        # metrics hook is absent.
        cache.update_eviction_metrics = lambda num_evicted, start_time: None

        cache._evict(SimpleNamespace(num_tokens=16, swa_num_tokens=0, mamba_num=0))

        self.assertEqual(order[0], "demote")
        self.assertLess(order.index("demote"), order.index("flush"))
        # The walk's backup was demoted and its chain persisted to L3.
        self.assertEqual(cache._pending_storage_writes, [])
        self.assertEqual(tree_core.storage_written, {42})

    def test_write_back_drain_does_not_recurse(self):
        # Long unpersisted chain (leaf e = chain[-1]): the pre-fix code
        # nested one drain per acked gap node and died with RecursionError.
        chain = list(range(1, 601))
        cache = _make_cache(_FakeTreeCore([chain]))
        e = chain[-1]
        cache.ongoing_write_through[e] = _OngoingWriteThrough(e, None, [e])
        cache.cache_controller.ack_write_queue.append(_FakeAck([e]))

        cache.writing_check(write_back=True)

        self.assertEqual(cache.ongoing_write_through, {})
        self.assertEqual(cache.cache_controller.ack_write_queue, [])
        self.assertEqual(cache._pending_storage_writes, [])
        # Every gap node's KV reached L3 exactly once (dedupe guard).
        self.assertEqual(cache.tree_core.storage_written, set(chain))
        self.assertEqual(len(cache.cache_controller.storage_ops), len(chain))

    def test_finish_count_poll_persists_after_pop_loop(self):
        # The scheduler-step poll pops a bounded count of acks; the persist
        # must not steal the queue mid-loop (pre-fix: IndexError on pop).
        chain_a = list(range(1, 101))
        chain_b = list(range(1000, 1100))
        cache = _make_cache(_FakeTreeCore([chain_a, chain_b]))
        e1, e2 = chain_a[-1], chain_b[-1]
        cache.ongoing_write_through[e1] = _OngoingWriteThrough(e1, None, [e1])
        cache.ongoing_write_through[e2] = _OngoingWriteThrough(e2, None, [e2])
        cache.cache_controller.ack_write_queue.extend([_FakeAck([e1]), _FakeAck([e2])])

        cache.writing_check(finish_count=2)

        self.assertEqual(cache.ongoing_write_through, {})
        self.assertEqual(cache._pending_storage_writes, [])
        self.assertEqual(
            cache.tree_core.storage_written, set(chain_a) | set(chain_b)
        )

    def test_drain_processes_one_generation(self):
        # An ack enqueued by a callback is not claimed by the running round;
        # the next round drains it (generation boundary).
        cache = _make_cache(_FakeTreeCore([]))
        e1, e2, e3 = 1, 2, 3
        for e in (e1, e2, e3):
            cache.ongoing_write_through[e] = _OngoingWriteThrough(e, None, [e])
        cache.cache_controller.ack_write_queue.extend([_FakeAck([e1]), _FakeAck([e2])])

        orig_finish = cache._finish_write_through_ack

        def finish_with_side_effect(ack_id):
            orig_finish(ack_id)
            if ack_id == e2:
                cache.cache_controller.ack_write_queue.append(_FakeAck([e3]))

        cache._finish_write_through_ack = finish_with_side_effect

        cache._drain_write_through_acks()
        self.assertNotIn(e1, cache.ongoing_write_through)
        self.assertNotIn(e2, cache.ongoing_write_through)
        self.assertIn(e3, cache.ongoing_write_through)
        self.assertEqual(len(cache.cache_controller.ack_write_queue), 1)

        cache._drain_write_through_acks()
        self.assertNotIn(e3, cache.ongoing_write_through)
        self.assertEqual(cache.cache_controller.ack_write_queue, [])

    def test_drain_reentry_guard_returns(self):
        # Re-entering the drain from a callback must be a no-op: the
        # enclosing drain owns this round.
        cache = _make_cache(_FakeTreeCore([]))
        cache._drain_write_through_depth = 1
        cache.cache_controller.ack_write_queue.append(_FakeAck([7]))
        cache._drain_write_through_acks()
        self.assertEqual(len(cache.cache_controller.ack_write_queue), 1)
        self.assertEqual(cache._drain_write_through_depth, 1)

    def test_pending_node_deleted_before_flush_is_skipped(self):
        # A node whose D->H ack deferred an L3 persist can be deleted before
        # the flush runs: a later eviction step may drop its subtree or
        # reclaim its host leaf. Flushing it must skip, never KeyError on
        # the arena lookup (3090 crash family: stale _pending_storage_writes
        # references).
        tree_core = _FakeTreeCore([[42]])
        cache = _make_cache(tree_core)
        cache._pending_storage_writes.append(42)
        tree_core.mark_deleted(42)

        cache._flush_pending_storage_writes()

        self.assertEqual(cache._pending_storage_writes, [])
        self.assertEqual(cache._storage_persist_skip_count, 1)
        self.assertEqual(cache.cache_controller.storage_ops, [])

    def test_gap_node_deleted_mid_gapfill_is_skipped(self):
        # The gap-fill's own D->H backups evict_host when host space is
        # tight; host eviction deletes host-only leaves -- including the
        # demoted pending node -- so a gap collected up front can reference
        # a node that dies mid-loop (3090 crash: KeyError from is_backuped).
        tree_core = _FakeTreeCore([[10, 20, 30]])
        cache = _make_cache(tree_core)
        cache._pending_storage_writes.append(30)
        cache.cache_controller.mem_pool_host.available_size = lambda: 8
        tree_core.host_evict_deletes = [30]
        components_mod = sys.modules["sglang.srt.mem_cache.unified_cache.components"]

        def drive_host_eviction(component_type, num_tokens):
            # First call frees 16 tokens by deleting host leaf 30 (the
            # demoted pending node); later calls find nothing to delete.
            if tree_core.host_evict_deletes:
                tree_core.mark_deleted(tree_core.host_evict_deletes.pop(0))
                return SimpleNamespace(
                    device_frees={},
                    host_frees={},
                    tracker={components_mod.ComponentType.FULL: 16},
                )
            return SimpleNamespace(device_frees={}, host_frees={}, tracker={})

        tree_core.drive_host_eviction = drive_host_eviction

        cache._flush_pending_storage_writes()

        self.assertEqual(cache._pending_storage_writes, [])
        self.assertEqual(cache._storage_persist_skip_count, 1)
        self.assertIn(30, tree_core.deleted)
        # The live gap nodes still reached L3 exactly once.
        self.assertEqual(tree_core.storage_written, {10, 20})


if __name__ == "__main__":
    unittest.main(verbosity=2)
