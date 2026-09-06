"""Regression tests for the P2-1 engine fixes (3090-24g-hicache branch).

- C: HybridCacheController._page_transfer must return the completed KV page
  count. The missing return used to yield None and kill the prefetch IO
  thread (the I7 incident). Covers the FULL component path (no sidecar) and
  the Mamba sidecar path: both must return the same page count as the base
  and leave the sidecar behavior unchanged.
- A: A storage thread that dies must record the fatal reason and mark storage
  unhealthy (never restarted transparently); the scheduler-side degradation
  must revoke every in-flight prefetch (no request hangs on a dead IO
  thread) and gate new L3 queries/issuance/writes.
- B: Graceful-exit ordering: release_host_resources must stop the storage
  threads before destroying the host pools (the 1318 NoneType crash).

Runs the real source modules against stub collaborators (no CUDA, no pools),
the same torch-free pattern as test_drain_reentry.py.
"""

import importlib.util
import os
import sys
import threading
import types
import unittest
from array import array as _array
from collections import defaultdict
from enum import Enum, IntEnum, IntFlag
from queue import Queue
from types import SimpleNamespace

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PYTHON_DIR = os.path.join(_REPO_ROOT, "python")
sys.path.insert(0, _PYTHON_DIR)

try:
    import torch  # noqa: F401 -- real sglang modules import torch
except ImportError:
    torch = None


def _split_cached_prefix_by_tier(prefix_len, host_hit_len, storage_hit_len):
    """Mirror of schedule_batch.split_cached_prefix_by_tier (M1a tests).

    The real schedule_batch module cannot load without torch; PrefillAdder's
    budget accounting needs the same pure arithmetic in the stubenv.
    """
    storage = min(host_hit_len, storage_hit_len)
    host = host_hit_len - storage
    device = max(0, prefix_len - host_hit_len)
    return device, host, storage


def _split_node_hash_value(child_hash_value, split_len, page_size):
    """Mirror of mem_cache.utils.split_node_hash_value (pure string slicing);
    the real utils module imports sglang.kernels and cannot load torch-free."""
    if child_hash_value is None:
        return None, None
    if page_size == 1:
        split_pages = split_len
    else:
        split_pages = split_len // page_size
    return child_hash_value[:split_pages], child_hash_value[split_pages:]


# ---------------------------------------------------------------------------
# Stubenv bootstrap (torch-less): fake the sglang import tree, then execute
# the REAL cache_controller.py / hybrid_cache_controller.py /
# unified_radix_cache.py / schedule_policy.py source against it.
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


class _EvictResult:
    """Torch-free stand-in for the real msgspec eviction result structs
    (unified_tree_core_interface.BaseEvictionResult): the e15 Z3 real-tree
    pins drive the real eviction steps, which read/write
    device_frees / host_frees / tracker on their results, and construct
    them with the struct field defaults (e.g. DropSubtreeNoHostResult(
    is_dropped=False))."""

    def __init__(self, **kwargs):
        self.device_frees = defaultdict(list)
        self.host_frees = defaultdict(list)
        self.tracker = defaultdict(int)
        self.backup_kv = None
        self.is_dropped = False
        self.node_id = None
        self.made_progress = False
        for key, value in kwargs.items():
            setattr(self, key, value)


def _install_stubenv():
    fake_torch = types.ModuleType("torch")
    fake_torch.distributed = types.ModuleType("torch.distributed")
    fake_torch.distributed.ReduceOp = Enum("ReduceOp", {"MAX": 0, "MIN": 1})
    fake_torch.int = "int"
    fake_torch.tensor = lambda x, **kw: SimpleNamespace(item=lambda: x)
    fake_torch.cat = lambda tensors, **kw: list(tensors[0]) + list(tensors[1])
    # The e14 real-tree pins construct UnifiedTreeCore under the stubenv;
    # its constructor touches only these three torch surfaces.
    fake_torch.device = lambda *a, **k: "cpu"
    fake_torch.int64 = "int64"
    fake_torch.empty = lambda *a, **k: []
    sys.modules["torch"] = fake_torch

    # msgspec: the real unified_tree_core subclasses msgspec.Struct for its
    # insert-walk state (never instantiated by the e14 pins).
    _fake_msgspec = types.ModuleType("msgspec")
    _fake_msgspec.Struct = type("Struct", (), {})
    sys.modules["msgspec"] = _fake_msgspec

    _fake_package("sglang")
    _fake_package("sglang.srt")
    _fake_package("sglang.srt.distributed")
    _fake_package("sglang.srt.distributed.communication_tags", P2PTag=object)
    _fake_package(
        "sglang.srt.environ",
        envs=SimpleNamespace(
            SGLANG_PREFILL_TILE_BUDGET=SimpleNamespace(get=lambda: "0"),
            SGLANG_PREFILL_TILE_BUDGET_MODE=SimpleNamespace(get=lambda: "legacy"),
            SGLANG_RADIX_FORCE_MISS=SimpleNamespace(get=lambda: False),
        ),
    )
    _fake_package("sglang.srt.layers")
    _fake_package(
        "sglang.srt.layers.dp_attention",
        get_attention_dp_rank=lambda: 0,
        is_dp_attention_enabled=lambda: False,
    )
    _fake_package("sglang.srt.managers")
    # sglang.srt.managers.cache_controller is replaced with the real module
    # after loading (see _load_modules).
    _fake_package("sglang.srt.managers.cache_controller", CacheOperation=object)
    # sglang.srt.managers.scheduler_components.hicache_restore is replaced
    # with the real module before unified_radix_cache loads (see
    # _load_modules): the P2-1c cache gates import promotion_budget_fits
    # from it, and the pure function must be the real one.
    _fake_package("sglang.srt.managers.scheduler_components")
    # schedule_policy dependencies (real module loaded later, see _load_modules).
    _fake_package(
        "sglang.srt.managers.prefill_delayer",
        PrefillDelayerSinglePassExecutor=object,
    )
    _fake_package(
        "sglang.srt.managers.schedule_batch",
        Req=object,
        ScheduleBatch=object,
        split_cached_prefix_by_tier=_split_cached_prefix_by_tier,
    )
    _fake_package("sglang.srt.dllm.config", DllmConfig=object)
    _fake_package(
        "sglang.srt.layers.attention.dsa.utils",
        is_dsa_prefill_cp_in_seq_split=lambda: False,
    )
    _fake_package(
        "sglang.srt.layers.utils.cp_utils",
        is_prefill_context_parallel_enabled=lambda: False,
    )
    _fake_package(
        "sglang.srt.mem_cache.allocator.hisparse",
        DeepSeekV4HiSparseTokenToKVPoolAllocator=type(
            "DeepSeekV4HiSparseTokenToKVPoolAllocator", (), {}
        ),
    )
    _fake_package(
        "sglang.srt.mem_cache.allocator.swa",
        PureSWATokenToKVPoolAllocator=type("PureSWATokenToKVPoolAllocator", (), {}),
        SWATokenToKVPoolAllocator=type("SWATokenToKVPoolAllocator", (), {}),
    )
    _fake_package(
        "sglang.srt.mem_cache.multi_ended_allocator",
        UnifiedMambaTokenToKVPoolAllocator=type(
            "UnifiedMambaTokenToKVPoolAllocator", (), {}
        ),
    )
    _fake_package("sglang.srt.server_args", ServerArgs=object)
    _fake_package("sglang.srt.mem_cache")
    # Lock-result fakes carry the real field surface (skip_lock_node_ids /
    # delta / to_dec_params): the P2-1c load-back pins drive the real
    # tree_core.inc_lock_ref, whose FullComponent-mirror stub records
    # tombstone skips and replays them at release.
    class _FakeDecLockRefParams:
        def __init__(self, skip_lock_node_ids=None, swa_uuid_for_lock=None):
            self.skip_lock_node_ids = skip_lock_node_ids or {}
            self.swa_uuid_for_lock = swa_uuid_for_lock

    class _FakeIncLockRefResult:
        def __init__(self):
            self.delta = None
            self.swa_uuid_for_lock = None
            self.swa_uuid_for_host_lock = None
            self.skip_lock_node_ids = {}

        def to_dec_params(self):
            return _FakeDecLockRefParams(
                skip_lock_node_ids=self.skip_lock_node_ids
            )

    _fake_package("sglang.srt.mem_cache.base_prefix_cache", **{
        "BasePrefixCache": object,
        "DecLockRefParams": _FakeDecLockRefParams,
        "DecLockRefResult": object,
        "EvictParams": type(
            "EvictParams", (), {"__init__": lambda self, **kw: vars(self).update(kw)}
        ),
        "EvictResult": type("EvictResult", (), {"__init__": lambda self, **kw: None}),
        "IncLockRefResult": _FakeIncLockRefResult,
        "InitLoadBackParams": type(
            "InitLoadBackParams", (), {"__init__": lambda self, **kw: None}
        ),
        "InsertParams": object,
        "InsertResult": object,
        "MatchPrefixParams": object,
        # kwargs-storing: the real UnifiedTreeCore.reset() constructs its
        # empty MatchResult (device_indices etc. ride the kwargs; the
        # P2-1c init_load_back empty-match path reads device_indices).
        "MatchResult": type(
            "MatchResult", (), {"__init__": lambda self, **kw: vars(self).update(kw)}
        ),
        "zero_match_result": lambda *a, **k: None,
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
    _fake_package("sglang.srt.mem_cache.deepseek_v4_memory_pool", **{
        "DeepSeekV4TokenToKVPool": object,
    })
    _pool_name = Enum(
        "PoolName", {"KV": "kv", "SWA": "swa", "MAMBA": "mamba", "INDEXER": "indexer"}
    )
    _fake_package("sglang.srt.mem_cache.hicache_storage", **{
        "STORAGE_BATCH_SIZE": 2,
        "PoolName": _pool_name,
        "PoolHitPolicy": Enum("PoolHitPolicy", {"ALL_PAGES": 0, "MATCHED_PAGES": 1}),
        "PoolTransfer": type("PoolTransfer", (), {"__init__": lambda self, **kw: None}),
        "PoolTransferResult": type(
            "PoolTransferResult",
            (),
            {
                "empty": staticmethod(
                    lambda: SimpleNamespace(update_extra_pool_hit_pages=lambda *a, **k: None)
                )
            },
        ),
        "HiCacheStorageConfig": object,
        "HiCacheStorageExtraInfo": type(
            "HiCacheStorageExtraInfo", (), {"__init__": lambda self, **kw: None}
        ),
        "SidecarPoolSpec": object,
        "count_pool_hits": lambda results: {},
    })
    # Module deps of the real radix_cache.py / unified_tree_core.py, loaded
    # by the e14 pins (radix_cache loads torch-free; utils imports
    # sglang.kernels and is stubbed with the pure mirror above).
    _fake_package(
        "sglang.srt.mem_cache.cache_init_params",
        CacheInitParams=object,
    )
    _fake_package("sglang.srt.disaggregation")
    _fake_package(
        "sglang.srt.disaggregation.kv_events",
        # The e15 Z3 real-tree pins record the device-layer removal event.
        StorageMedium=Enum("StorageMedium", {"GPU": 0, "CPU": 1}),
    )
    _fake_package(
        "sglang.srt.mem_cache.events",
        KVCacheEventRecorder=type(
            "KVCacheEventRecorder",
            (),
            {
                "__init__": lambda self, *a, **k: None,
                # The e15 Z3 real-tree pins drive the device-layer release,
                # which records the removal event.
                "record_remove": lambda self, *a, **k: None,
                "record_store": lambda self, *a, **k: None,
            },
        ),
    )
    _fake_package("sglang.srt.mem_cache.utils", **{
        "compute_node_hash_values": lambda *a, **k: None,
        "get_eviction_strategy": lambda strategy: None,
        "get_hash_str": lambda *a, **k: "h",
        "split_node_hash_value": _split_node_hash_value,
    })
    _fake_package("sglang.srt.mem_cache.hybrid_cache")
    _fake_package(
        "sglang.srt.mem_cache.hybrid_cache.hybrid_cache_controller",
        HybridCacheController=object,
    )
    _fake_package(
        "sglang.srt.mem_cache.l2_transfer",
        L2Transfer=object,
        L2TransferEngine=object,
    )
    _fake_package("sglang.srt.mem_cache.memory_pool", **{
        "MLATokenToKVPool": object,
        "MHATokenToKVPool": object,
    })
    _fake_package(
        "sglang.srt.mem_cache.pool_host", HostPoolGroup=object, PoolEntry=object
    )
    _fake_package("sglang.srt.mem_cache.pool_host.mha", MHATokenToKVPoolHost=object)
    _fake_package(
        "sglang.srt.mem_cache.radix_cache",
        RadixKey=object,
        RadixCache=object,
        TreeNode=object,
    )
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
    # IntEnum: component_data lists are indexed by ComponentType values.
    _component_type = IntEnum(
        "ComponentType", {"FULL": 0, "SWA": 1, "MAMBA": 2, "C128": 3}
    )
    _component_time_counter = [0]

    def _get_component_time_counter():
        _component_time_counter[0] += 1
        return _component_time_counter[0]

    class _ComponentData:
        """Dataclass defaults of the real ComponentData (tree_component.py),
        so fresh tree nodes carry every field the split walks read."""

        def __init__(self):
            self.value = None
            self.lock_ref = 0
            self.metadata = {}
            self.host_value = None
            self.host_lock_ref = 0
            self.session_ref = 0
            self.session_ids = None

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
        # The real UnifiedTreeCore imports these at module level; the e14
        # split pins never touch the LRU phase/evict-layer machinery. The
        # e15 Z3 real-tree pins DO drive device eviction, which tests
        # membership with `EvictLayer.DEVICE in target` -- the fake must be
        # an IntFlag with the real members, not a plain Enum.
        "_NUM_COMPONENT_TYPES": 4,
        "ComponentData": _ComponentData,
        "EvictLayer": IntFlag("EvictLayer", {"DEVICE": 1, "HOST": 2, "ALL": 3}),
        "LRURefreshPhase": Enum(
            "LRURefreshPhase", {"INSERT_START": 0, "INSERT_END": 1}
        ),
        "get_and_increase_time_counter": _get_component_time_counter,
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
    _fake_package(
        "sglang.srt.mem_cache.unified_cache.unified_tree_core_interface",
        DecSwaLockOnlyResult=object,
        DemoteResult=_EvictResult,
        DriveHostEvictionResult=object,
        DropSubtreeNoHostResult=_EvictResult,
        EvictDeviceLeafResult=_EvictResult,
        EvictDeviceNextNodeResult=_EvictResult,
        InsertStepResult=object,
        NodeId=int,
        RadixCacheWalkResult=object,
        UnifiedTreeCoreInterface=object,
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
    _fake_package(
        "sglang.srt.runtime_context",
        get_memory=lambda: None,
        get_parallel=lambda: SimpleNamespace(
            tp_rank=0,
            tp_size=1,
            pp_rank=0,
            pp_size=1,
            attn_tp_rank=0,
            attn_tp_size=1,
            dp_rank=0,
            enable_dp_attention=False,
        ),
        get_disagg=lambda: SimpleNamespace(
            disaggregation_decode_enable_radix_cache=False
        ),
    )
    _fake_package("sglang.srt.session")
    _fake_package(
        "sglang.srt.session.streaming_session", StreamingSession=object
    )
    _fake_package(
        "sglang.srt.utils",
        get_device_module=lambda: SimpleNamespace(
            Event=object,
            current_stream=lambda: SimpleNamespace(wait_event=lambda *a, **k: None),
        ),
        is_hip=lambda: False,
        get_bool_env_var=lambda name: False,
    )
    _fake_package("sglang.srt.utils.common", ceil_align=lambda x: x)
    _fake_package(
        "sglang.srt.utils.rank_consensus_checker",
        rank_consensus=_identity_decorator,
    )


def _load_real(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_modules():
    """Load the real modules: installed package when torch exists, otherwise
    the stubenv bootstrap (same source files, fake sglang import tree)."""
    if torch is not None:
        from sglang.srt.managers.cache_controller import HiCacheController
        from sglang.srt.managers.schedule_policy import AddReqResult, PrefillAdder
        from sglang.srt.mem_cache.hybrid_cache.hybrid_cache_controller import (
            HybridCacheController,
        )
        from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache

        return (
            HiCacheController,
            HybridCacheController,
            UnifiedRadixCache,
            AddReqResult,
            PrefillAdder,
        )
    _install_stubenv()
    # The real RadixKey (array-based, torch-free) replaces the bootstrap fake
    # so the cache module and the e14 restore-marking pins bind the real
    # class (insert_host slices prefetch_key[:completed_tokens]).
    _load_real(
        "sglang.srt.mem_cache.radix_cache",
        os.path.join(
            _PYTHON_DIR, "sglang", "srt", "mem_cache", "radix_cache.py"
        ),
    )
    # Real hicache_restore (pure module) BEFORE the cache module: the P2-1c
    # gates import promotion_budget_fits from it.
    _load_real(
        "sglang.srt.managers.scheduler_components.hicache_restore",
        os.path.join(
            _PYTHON_DIR,
            "sglang",
            "srt",
            "managers",
            "scheduler_components",
            "hicache_restore.py",
        ),
    )
    cc_mod = _load_real(
        "sglang.srt.managers.cache_controller",
        os.path.join(
            _PYTHON_DIR,
            "sglang",
            "srt",
            "managers",
            "cache_controller.py",
        ),
    )
    hcc_mod = _load_real(
        "sglang.srt.mem_cache.hybrid_cache.hybrid_cache_controller",
        os.path.join(
            _PYTHON_DIR,
            "sglang",
            "srt",
            "mem_cache",
            "hybrid_cache",
            "hybrid_cache_controller.py",
        ),
    )
    urc_mod = _load_real(
        "stubenv_unified_radix_cache",
        os.path.join(
            _PYTHON_DIR, "sglang", "srt", "mem_cache", "unified_radix_cache.py"
        ),
    )
    # The real UnifiedTreeCore under its canonical name: the e14 split /
    # durability pins run the real _split_node / mark_storage_restored /
    # advance_storage_persisted code against the fakes. The cache module
    # already bound its imports from the bootstrap fake above.
    _load_real(
        "sglang.srt.mem_cache.unified_cache.unified_tree_core",
        os.path.join(
            _PYTHON_DIR,
            "sglang",
            "srt",
            "mem_cache",
            "unified_cache",
            "unified_tree_core.py",
        ),
    )
    sp_mod = _load_real(
        "stubenv_schedule_policy",
        os.path.join(
            _PYTHON_DIR, "sglang", "srt", "managers", "schedule_policy.py"
        ),
    )
    return (
        cc_mod.HiCacheController,
        hcc_mod.HybridCacheController,
        urc_mod.UnifiedRadixCache,
        sp_mod.AddReqResult,
        sp_mod.PrefillAdder,
    )


HiCacheController, HybridCacheController, UnifiedRadixCache, AddReqResult, PrefillAdder = (
    _load_modules()
)

from sglang.srt.mem_cache.hicache_storage import PoolName as _PoolName
from sglang.srt.mem_cache.radix_cache import RadixKey as _RadixKey
from sglang.srt.mem_cache.unified_cache.components import (
    CacheTransferPhase as _cache_transfer_phase,
    ComponentType as _component_type,
    EvictLayer as _evict_layer,
)
from sglang.srt.mem_cache.unified_cache.unified_tree_core import (
    UnifiedTreeCore as _RealTreeCore,
)
from sglang.srt.managers.scheduler_components.hicache_restore import (
    RestoreDecision as _restore_decision,
    RestoreEvent as _restore_event,
    RestoreState as _restore_state,
    RestoreWaitReason as _restore_wait_reason,
    next_restore as _next_restore,
    promotion_budget_fits as _promotion_budget_fits,
    promotion_wait_blocked as _promotion_wait_blocked,
    wait_reason_for as _wait_reason_for,
)

try:
    from stubenv_schedule_policy import device_locked_tokens as _device_locked_tokens
except ImportError:  # real package (torch present)
    from sglang.srt.managers.schedule_policy import (
        device_locked_tokens as _device_locked_tokens,
    )


# ---------------------------------------------------------------------------
# Stub collaborators
# ---------------------------------------------------------------------------


class _FakeAck:
    def __init__(self, node_ids):
        self.node_ids = list(node_ids)
        self.finish_event = SimpleNamespace(query=lambda: True, synchronize=lambda: None)
        self.start_event = SimpleNamespace(query=lambda: True, synchronize=lambda: None)
        self.num_tokens_by_pool = None
        self.num_bytes = 0
        self.timing_enabled = False


class _FakeController:
    """Stub for (Hybrid)CacheController used by the UnifiedRadixCache harness."""

    write_policy = "write_back"
    storage_failure_reason = None
    prefetch_tokens_occupied = 0

    def __init__(self):
        self.ack_write_queue = []
        self.storage_ops = []
        self.released = []
        self.terminated = []
        self.stop_calls = 0
        self.mem_pool_host = SimpleNamespace(available_size=lambda: 1 << 30)
        # Storage threads never started: the local drain short-circuits.
        self.prefetch_hit_queue = None

    def write(self, device_indices, node_id=-1, extra_pools=None):
        self.ack_write_queue.append(_FakeAck([node_id]))
        return [0] * len(device_indices)

    def prefetch_rate_limited(self):
        return False

    def write_storage(
        self,
        host_value,
        token_ids,
        hash_value,
        prefix_keys,
        extra_pools=None,
        node_id=None,
    ):
        self.storage_ops.append(len(self.storage_ops))
        return len(self.storage_ops) - 1

    def terminate_prefetch(self, operation):
        self.terminated.append(operation)
        return 0, None

    def append_host_mem_release(self, host_indices=None, extra_pools=None):
        self.released.append((host_indices, extra_pools))

    def stop_storage_threads(self):
        self.stop_calls += 1


class _FakeTreeCore:
    def __init__(self):
        self.host_lock_decs = []
        self.node_exists = lambda node_id: True
        self.is_backuped = lambda node_id: False
        self.is_storage_written = lambda node_id: False
        self.is_root = lambda node_id: node_id == 0
        # No chain model in this registry harness: no node is on a modeled
        # request chain, so the T15 backup park never applies.
        self.page_block_in_request = lambda node_id, pos, requested_pages: None
        self.persisted_chain_frontier = lambda node_id, pos, requested_pages: 0
        self.persisted = set()
        # e14: the restore source of l3_durable (written chains are covered
        # by the persisted set -- acked implies durable).
        self.durable = set()
        # e15 (Y): anchors whose L3-durable belief a full-miss revoke cleared.
        self.durable_cleared = []
        self._publish_epoch = 0
        self.page_size = 1  # facade page_size property (prompt gate math)
        # The frontier-wait registration requests the anchor chain's L3
        # persistence; this registry harness has no chain model, so the gap
        # is empty (the anchor is already written/persisted) and the
        # trigger is a no-op. The gap-fill behavior itself is covered by
        # test_drain_reentry.py.
        self.collect_storage_gap = lambda node_id: []
        self.inc_host_lock_ref = lambda node_id: SimpleNamespace(
            to_dec_params=lambda: None
        )
        # P3 (phase2-p3-fix): deferred-ACK reconciliation scan. The registry
        # harness has no chain model, so there is never a deferred-ACK node;
        # the reconcile pass over an empty set is a no-op.
        self.deferred_acked_nodes = lambda: []

    def dec_host_lock_ref(self, node_id, params, skip_swa=False):
        self.host_lock_decs.append((node_id, params))
        return SimpleNamespace()

    def advance_storage_persisted(self, node_id):
        self.persisted.add(node_id)
        return [node_id]

    def is_storage_persisted(self, node_id):
        return node_id in self.persisted

    def is_l3_durable(self, node_id):
        # e14 unified predicate: written+acked chains are durable by
        # construction; the durable set covers the restore source.
        return node_id in self.durable or node_id in self.persisted

    def clear_storage_durable(self, node_id):
        # e15 (Y): a full-miss revoke clears the anchor's durable belief
        # (persisted and restored alike) -- the query covered the anchor's
        # prefix keys and found no pages.
        self.durable_cleared.append(node_id)
        self.durable.discard(node_id)
        self.persisted.discard(node_id)

    def l3_publish_epoch(self):
        # P3 prefetch_revoke instrumentation reads the publish epoch for the
        # storage_generation field.
        return self._publish_epoch


def _make_cache(tree_core=None):
    cache = object.__new__(UnifiedRadixCache)
    cache.disable = False
    cache.tree_core = tree_core or _FakeTreeCore()
    cache.enable_storage = True
    cache.buffer_pipeline = None
    cache.sidecar_pool_specs = []
    cache.hicache_storage_pass_prefix_keys = False
    cache.metrics_collector = None
    cache.session = SimpleNamespace(
        try_inc_lock_ref=lambda *a, **k: None,
        try_dec_lock_ref=lambda *a, **k: None,
        any_holding_kv=lambda: False,
    )
    cache.ongoing_write_through = {}
    cache.ongoing_backup = {}
    cache.ongoing_load_back = {}
    # P2-1c promotion admission state (defaults; the lifecycle pins drive
    # the real counters through the real load_back / loading_check paths).
    cache.inflight_promotion_reserved = 0
    cache._promotion_inflight_peak = 0
    cache._promotion_denied_count = 0
    cache._promotion_denied_exact_count = 0
    cache._promotion_reserve_count = 0
    cache._promotion_transfer_count = 0
    cache._promotion_release_count = 0
    cache.promotion_margin_tokens = 2048
    cache.is_swa_enabled = False
    cache.is_mamba_enabled = False
    cache.load_back_threshold = 10
    cache._pending_storage_writes = []
    cache._storage_persist_skip_count = 0
    cache.host_memory_mode = "cache"
    cache._drain_write_through_depth = 0
    cache._reconcile_depth = 0
    cache.pp_rank = 0
    cache.pp_size = 1
    cache.pp_group = None
    cache.tp_world_size = 1
    cache.attn_cp_group = None
    cache.attn_tp_group = None
    cache.prefetch_loaded_tokens_by_reqid = {}
    cache._storage_prefetch_missed_rids = set()
    cache._storage_frontier_waiters = {}
    cache._storage_frontier_ready = set()
    cache._storage_prefetch_terminal = {}
    cache._backup_wait_spans = {}
    cache._demand_restore_rids = set()
    # T15 bypass gate (P2-IO Phase 1): this registry harness never parks
    # (no chain model), but the revoke path reads the flag -- constant True
    # keeps the regression guard identical.
    cache.hicache_restore_backup_park = True
    # P3 Ready Horizon (3.1): off is the harness default -- the baseline
    # behavior the existing tests assert. The reservation dict exists so
    # the (no-op) release calls on the five removal paths stay safe.
    cache.enable_ready_horizon = False
    cache._prefetch_reservations = {}
    cache.ongoing_prefetch = {}
    cache.prefetch_threshold = 256
    cache.page_size = 1
    cache.prefetch_stop_policy = "wait_complete"
    cache.storage_existence_cache = SimpleNamespace(
        invalidate_beyond=lambda *a, **k: None
    )
    cache._storage_failure_handled = False
    cache.cache_controller = _FakeController()
    return cache


def _make_operation(n_pages, pool_transfers=None, requested=None):
    return SimpleNamespace(
        request_id="test-rid",
        hash_value=[f"h{i}" for i in range(n_pages)],
        host_indices=list(range(n_pages)),
        prefix_keys=None,
        pool_transfers=pool_transfers,
        stats_requested_tokens=requested if requested is not None else n_pages,
        storage_hit_count=n_pages,
        all_hash_values=None,
        pool_transfers_done=not bool(pool_transfers),
        pool_storage_result=SimpleNamespace(
            update_extra_pool_hit_pages=lambda *a, **k: None
        ),
        completed_tokens=0,
        is_terminated=lambda: False,
    )


def _make_hybrid_controller():
    cc = object.__new__(HybridCacheController)
    cc.page_size = 1
    cc.prefetch_sync_queue = Queue()
    cc.page_get_func = lambda operation, hashes, host_idx, extra: len(hashes)
    cc._sync_trailing_keys = lambda *a, **k: None
    cc._resolve_sidecar_nonkv_derived_pool_transfers = lambda *a, **k: None
    cc.storage_backend = SimpleNamespace(
        batch_get_v2=lambda transfers: {getattr(t.name, "value", t.name): [True] * len(t.keys or []) for t in transfers}
    )
    return cc


# ---------------------------------------------------------------------------
# C: hybrid _page_transfer return-value regression
# ---------------------------------------------------------------------------


class HybridPageTransferReturnTest(unittest.TestCase):
    def test_full_path_returns_kv_page_count(self):
        # FULL component normal path (no sidecar pool): the override must
        # return the completed KV page count exactly like the base class.
        # The pre-fix code returned None, killing the IO thread's arithmetic.
        cc = _make_hybrid_controller()
        operation = _make_operation(3)
        ret = cc._page_transfer(operation)
        self.assertIsInstance(ret, int)
        self.assertEqual(ret, 3)

    def test_mamba_sidecar_path_returns_kv_page_count(self):
        # Mamba component path: the sidecar transfer still executes (one extra
        # ack for the pool hits), and the return stays the KV page count.
        from sglang.srt.mem_cache.hicache_storage import (
            PoolName,
            STORAGE_BATCH_SIZE,
        )

        sidecar_called = []

        cc = _make_hybrid_controller()

        def tracking_batch_get_v2(transfers):
            sidecar_called.append(transfers)
            return {}

        cc.storage_backend.batch_get_v2 = tracking_batch_get_v2
        mamba_transfer = SimpleNamespace(
            name=PoolName.MAMBA,
            indices_from_pool=None,
            keys=["m0", "m1", "m2"],
        )
        operation = _make_operation(3, pool_transfers=[mamba_transfer])
        ret = cc._page_transfer(operation)
        self.assertIsInstance(ret, int)
        self.assertEqual(ret, 3)
        # Sidecar IO ran exactly once for the non-KV transfer.
        self.assertEqual(len(sidecar_called), 1)
        # One base ack per STORAGE_BATCH_SIZE batch + 1 sidecar ack.
        expected_acks = (3 + STORAGE_BATCH_SIZE - 1) // STORAGE_BATCH_SIZE + 1
        self.assertEqual(cc.prefetch_sync_queue.qsize(), expected_acks)


# ---------------------------------------------------------------------------
# A: storage-thread fatal handling (watchdog, no transparent restart)
# ---------------------------------------------------------------------------


def _make_bare_controller():
    cc = object.__new__(HiCacheController)
    cc.storage_stop_event = threading.Event()
    cc.storage_failure_reason = None
    cc.enable_storage = False
    cc.page_size = 1
    cc.prefetch_buffer = Queue()
    cc.prefetch_sync_queue = Queue()
    cc.backup_queue = Queue()
    cc.ack_backup_queue = Queue()
    cc.write_queue = []
    cc.load_queue = []
    cc.ack_write_queue = []
    cc.ack_load_queue = []
    cc.backup_skip = False
    return cc


class StorageThreadFatalTest(unittest.TestCase):
    def test_io_thread_exception_records_fatal_reason_and_exits(self):
        cc = _make_bare_controller()

        def boom(operation):
            raise ValueError("io boom")

        cc._page_transfer = boom
        cc.prefetch_buffer.put(SimpleNamespace(request_id="r1"))

        t = threading.Thread(target=cc.prefetch_io_aux_func)
        t.start()
        t.join(timeout=5)

        self.assertFalse(t.is_alive())
        self.assertIsNotNone(cc.storage_failure_reason)
        self.assertIn("io boom", cc.storage_failure_reason)

    def test_backup_thread_exception_records_fatal_reason_and_exits(self):
        cc = _make_bare_controller()

        def boom(operation):
            raise RuntimeError("backup boom")

        cc._page_backup = boom
        cc.backup_queue.put(SimpleNamespace())

        t = threading.Thread(target=cc.backup_thread_func)
        t.start()
        t.join(timeout=5)

        self.assertFalse(t.is_alive())
        self.assertIsNotNone(cc.storage_failure_reason)
        self.assertIn("backup boom", cc.storage_failure_reason)

    def test_graceful_stop_clears_failure_reason_for_explicit_restart(self):
        # reset() is the explicit control path: it may restart threads after
        # a failure, so it must clear the degradation marker.
        cc = _make_bare_controller()
        cc.storage_failure_reason = "old failure"
        cc.storage_stop_event.set()
        cc.storage_stop_event.clear()
        cc.reset()
        self.assertIsNone(cc.storage_failure_reason)


class StorageFailureDegradationTest(unittest.TestCase):
    def test_query_and_issue_gated_when_storage_unhealthy(self):
        cache = _make_cache()
        cache.cache_controller.storage_failure_reason = "backup_thread_func: boom"
        issued = []
        cache.cache_controller.prefetch = lambda *a, **k: issued.append(a)

        # Synchronous L3 probe returns 0 (recompute fallback).
        self.assertEqual(
            cache.query_storage_hit_length(1, [1, 2, 3], "hash"), 0
        )
        # Issue path no-ops; nothing reaches the controller.
        cache.prefetch_from_storage("rid-x", 1, [1, 2, 3], "hash")
        self.assertEqual(issued, [])

    def test_write_backup_gated_when_storage_unhealthy(self):
        cache = _make_cache()
        cache.cache_controller.storage_failure_reason = "backup_thread_func: boom"
        cache._write_backup_storage_node(42)
        # No L3 write submitted, no ack entry registered.
        self.assertEqual(cache.cache_controller.storage_ops, [])
        self.assertEqual(cache.ongoing_backup, {})

    def test_handle_storage_failure_revokes_inflight_and_releases_locks(self):
        cache = _make_cache()
        cc = cache.cache_controller
        cc.storage_failure_reason = "prefetch_io_aux_func: ValueError: io boom"

        # One pre-alloc prefetch (revoke path) and one post-alloc prefetch
        # (release_aborted_request path).
        pre_op = _make_operation(0, requested=100)
        pre_op.host_indices = None
        pre_op.storage_hit_count = 0
        cache.ongoing_prefetch["pre"] = (
            1,
            list(range(100)),
            None,
            pre_op,
            None,
            {},
        )
        post_op = _make_operation(3, requested=100)
        post_op.host_indices = [10, 11, 12]
        post_op.storage_hit_count = 64
        cache.ongoing_prefetch["post"] = (
            2,
            list(range(100)),
            [10, 11, 12],
            post_op,
            None,
            {},
        )
        cache.ongoing_backup = {7: (42, "lock-params")}

        cache._handle_storage_failure("prefetch_io_aux_func: ValueError: io boom")
        # Second call is a no-op (one-shot).
        cache._handle_storage_failure("again")

        self.assertTrue(cache._storage_failure_handled)
        self.assertEqual(cache.ongoing_prefetch, {})
        self.assertEqual(cache.ongoing_backup, {})
        # Backup lock released once; host memory of the post-alloc prefetch
        # released (tail + sidecar).
        self.assertIn((42, "lock-params"), cache.tree_core.host_lock_decs)
        self.assertGreaterEqual(len(cc.released), 1)

    def test_handle_storage_failure_unblocks_waiting_request(self):
        # After cleanup, check_prefetch_progress must return True (the request
        # falls back to recompute instead of hanging on the dead IO thread).
        cache = _make_cache()
        op = _make_operation(0, requested=100)
        op.host_indices = None
        op.storage_hit_count = 0
        cache.ongoing_prefetch["waiting"] = (
            1,
            list(range(100)),
            None,
            op,
            None,
            {},
        )
        self.assertFalse(cache.check_prefetch_progress("waiting"))

        cache._handle_storage_failure("prefetch_io_aux_func: ValueError: io boom")
        self.assertTrue(cache.check_prefetch_progress("waiting"))


# ---------------------------------------------------------------------------
# B: graceful-exit ordering (1318 race)
# ---------------------------------------------------------------------------


class GracefulExitOrderTest(unittest.TestCase):
    def test_release_host_resources_stops_threads_before_pool_destroy(self):
        events = []
        cache = _make_cache()
        cache.cache_controller.stop_storage_threads = lambda: events.append("stop")
        cache.host_pool_group = SimpleNamespace(destroy=lambda: events.append("destroy"))

        cache.release_host_resources()

        self.assertEqual(events, ["stop", "destroy"])

    def test_release_host_resources_no_controller_or_pool(self):
        cache = _make_cache()
        cache.cache_controller = None
        cache.host_pool_group = None
        cache.release_host_resources()  # must not raise


# ---------------------------------------------------------------------------
# M1a: incremental device-KV billing (P2-1 design §2.4 / §5 change 1)
#
# The admission charge must bill only the KV that becomes newly resident:
# the already-resident device prefix (len(prefix_indices)) is free, while
# host/storage hits are charged in full (load-back makes them resident).
# First-visit requests (no prefix) must charge exactly as before, and the
# gate must never oversell: sum(charge + device_hit) over admitted requests
# stays within the pool.
# ---------------------------------------------------------------------------


class _FakeAdmissionReq:
    """Minimal Req stand-in for the PrefillAdder admission tests."""

    def __init__(
        self,
        full_len,
        prefix_len=0,
        host_hit=0,
        storage_hit=0,
        max_new=1000,
        mamba_pool_idx=None,
        host_load_back=False,
    ):
        self.full_untruncated_fill_ids = list(range(full_len))
        # The real Req keeps a torch tensor; the stubenv uses a list (its
        # fake torch.cat concatenates lists).
        self.prefix_indices = (
            torch.arange(prefix_len) if torch is not None else list(range(prefix_len))
        )
        self.host_hit_length = host_hit
        self.storage_hit_length = storage_hit
        self.output_ids = []
        self.retracted_stain = False
        self.mamba_pool_idx = mamba_pool_idx
        self.last_node = object()
        self.best_match_node = object()
        self.sampling_params = SimpleNamespace(
            max_new_tokens=max_new, ignore_eos=False
        )
        self.skip_lock_node_ids = {}
        self._host_load_back = host_load_back

    def needs_host_load_back(self):
        return self._host_load_back

    def set_extend_range(self, start, end):
        self.extend_range = SimpleNamespace(length=end - start)


class _FakeAdmissionTree:
    def __init__(self, mamba=False):
        self._mamba = mamba

    def supports_mamba(self):
        return self._mamba

    def evictable_size(self):
        return 0

    def full_evictable_size(self):
        return 0

    def mamba_evictable_size(self):
        return 0

    def inc_lock_ref(self, node):
        return SimpleNamespace(to_dec_params=lambda: None)

    def dec_lock_ref(self, node, *args):
        pass

    def is_tree_cache(self):
        return False


class _FixedAllocator:
    def __init__(self, available=1 << 30):
        self._available = available

    def available_size(self):
        return self._available


class _SteppedAllocator:
    """available_size() returns queued values (gate-1 vs gate-2 divergence)."""

    def __init__(self, sizes):
        self._sizes = list(sizes)

    def available_size(self):
        if len(self._sizes) > 1:
            return self._sizes.pop(0)
        return self._sizes[0]


class IncrementalBillingAdmissionTests(unittest.TestCase):
    """P2-1 M1a: incremental device-KV charge at both admission gates."""

    def setUp(self):
        if torch is not None:
            # PrefillAdder.__init__ reads the parallel config bag
            # (is_dsa_prefill_cp_in_seq_split / is_prefill_context_parallel_enabled);
            # publish a dummy scheduler config like the upstream
            # test_prefill_adder.py does.
            from sglang.srt.server_args import (
                ServerArgs,
                set_global_server_args_for_scheduler,
            )

            set_global_server_args_for_scheduler(ServerArgs(model_path="dummy"))

    def _make_adder(self, allocator=None, mamba=False):
        return PrefillAdder(
            page_size=128,
            tree_cache=_FakeAdmissionTree(mamba=mamba),
            token_to_kv_pool_allocator=allocator or _FixedAllocator(),
            running_batch=None,
            new_token_ratio=1.0,
            rem_input_tokens=1 << 30,
            rem_chunk_tokens=None,
        )

    # -- formula level ----------------------------------------------------

    def test_first_visit_charge_equals_full_billing(self):
        # No device prefix: the charge is the full candidate span plus decode
        # headroom and page slack -- exactly the pre-M1a formula.
        adder = self._make_adder()
        req = _FakeAdmissionReq(full_len=27877, prefix_len=0, max_new=4096)
        self.assertEqual(
            adder._device_charge(req, len(req.full_untruncated_fill_ids), 4096),
            27877 + 4096 + 128,
        )

    def test_charge_subtracts_device_prefix_only(self):
        # A re-visit with a resident device prefix pays only the non-resident
        # span; host/storage hits are NOT subtracted (load-back makes them
        # resident).
        adder = self._make_adder()
        req = _FakeAdmissionReq(
            full_len=10000,
            prefix_len=4000,
            host_hit=2000,
            storage_hit=3000,
            max_new=1000,
        )
        charge = adder._device_charge(req, len(req.full_untruncated_fill_ids), 1000)
        self.assertEqual(charge, (10000 - 4000) + 1000 + 128)
        # The same request without the device prefix is charged the full span.
        req2 = _FakeAdmissionReq(
            full_len=10000,
            prefix_len=0,
            host_hit=2000,
            storage_hit=3000,
            max_new=1000,
        )
        charge2 = adder._device_charge(
            req2, len(req2.full_untruncated_fill_ids), 1000
        )
        self.assertEqual(charge2, 10000 + 1000 + 128)
        self.assertLess(charge, charge2)

    def test_full_device_hit_charges_decode_only(self):
        adder = self._make_adder()
        req = _FakeAdmissionReq(full_len=27877, prefix_len=27877, max_new=4096)
        self.assertEqual(
            adder._device_charge(req, len(req.full_untruncated_fill_ids), 4096),
            4096 + 128,
        )

    def test_negative_span_guard(self):
        # Retraction edge case: a prefix longer than the input must not slip
        # through the gates as a negative charge (the max(0, ...) guard).
        adder = self._make_adder()
        req = _FakeAdmissionReq(full_len=1000, prefix_len=2000, max_new=500)
        self.assertEqual(
            adder._device_charge(req, len(req.full_untruncated_fill_ids), 500),
            500 + 128,
        )

    def test_mamba_gap_folded_into_charge(self):
        # Shared Mamba pool: a new state (mamba_pool_idx None) adds the gap
        # cost to the charge; an existing state does not.
        adder = self._make_adder()
        adder._mamba_slot_cost = 512
        req = _FakeAdmissionReq(
            full_len=1000, prefix_len=0, max_new=100, mamba_pool_idx=None
        )
        self.assertEqual(
            adder._device_charge(req, len(req.full_untruncated_fill_ids), 100),
            1000 + 100 + 128 + 512,
        )
        req2 = _FakeAdmissionReq(
            full_len=1000, prefix_len=0, max_new=100, mamba_pool_idx=3
        )
        self.assertEqual(
            adder._device_charge(req2, len(req2.full_untruncated_fill_ids), 100),
            1000 + 100 + 128,
        )

    def test_charge_equivalent_to_legacy_formula(self):
        # The M1a formula is bit-for-bit the pre-M1a computation
        # (full_len - prefix) + max_new + page + gap for every non-pathological
        # (full, prefix) pair: the change is extraction, not a semantics shift.
        adder = self._make_adder()
        for full_len, prefix_len in [
            (1, 0),
            (128, 0),
            (27877, 0),
            (27877, 4096),
            (27877, 27877),
            (4096, 128),
            (32768, 10000),
            (10000, 9999),
        ]:
            req = _FakeAdmissionReq(
                full_len=full_len, prefix_len=prefix_len, max_new=777
            )
            charge = adder._device_charge(req, full_len, 777)
            legacy = (full_len - prefix_len) + 777 + 128
            self.assertEqual(
                charge, legacy, f"full={full_len} prefix={prefix_len}"
            )

    # -- gate level -------------------------------------------------------

    def test_gate1_admits_incremental_charge_only(self):
        # rem_total_tokens sits between the full-billing charge (9128) and the
        # incremental charge (5128): the no-prefix twin is denied at gate 1,
        # the prefix twin passes.
        adder = self._make_adder(_FixedAllocator(available=6000))
        no_prefix = _FakeAdmissionReq(full_len=8000, prefix_len=0, max_new=1000)
        res = adder.add_one_req(
            no_prefix, has_chunked_req=False, truncation_align_size=None
        )
        self.assertEqual(res, AddReqResult.NO_TOKEN)

        with_prefix = _FakeAdmissionReq(full_len=8000, prefix_len=4000, max_new=1000)
        res = adder.add_one_req(
            with_prefix, has_chunked_req=False, truncation_align_size=None
        )
        self.assertEqual(res, AddReqResult.CONTINUE)

    def test_gate2_recheck_uses_incremental_charge(self):
        # The locked re-check (gate 2) applies the same incremental charge: on
        # a budget that shrinks between the two reads, the no-prefix twin is
        # denied at gate 2 while the prefix twin still fits.
        adder = self._make_adder(_SteppedAllocator([20000, 6000]))
        with_prefix = _FakeAdmissionReq(full_len=8000, prefix_len=4000, max_new=1000)
        res = adder.add_one_req(
            with_prefix, has_chunked_req=False, truncation_align_size=None
        )
        self.assertEqual(res, AddReqResult.CONTINUE)

        adder2 = self._make_adder(_SteppedAllocator([20000, 6000]))
        no_prefix = _FakeAdmissionReq(full_len=8000, prefix_len=0, max_new=1000)
        res = adder2.add_one_req(
            no_prefix, has_chunked_req=False, truncation_align_size=None
        )
        self.assertEqual(res, AddReqResult.NO_TOKEN)

    # -- invariant --------------------------------------------------------

    def test_invariant_sum_resident_le_pool(self):
        # Design §2.4 invariant: the gate bounds sum(charge) by
        # available+evictable, and each request's device prefix already sits
        # in the used side, so sum(charge + device_hit) over admitted requests
        # never exceeds the pool. The incremental charge is what lets a
        # re-visit overlap a running request (the width-2 frame) without
        # overselling.
        pool = 32768
        budget = pool - 18000  # two resident 9000-token prefixes in used
        adder = self._make_adder(_FixedAllocator(available=budget))
        requests = [
            _FakeAdmissionReq(full_len=10000, prefix_len=9000, max_new=2000),
            _FakeAdmissionReq(full_len=10000, prefix_len=9000, max_new=2000),
            _FakeAdmissionReq(full_len=8000, prefix_len=0, max_new=1500),
        ]
        admitted = []
        for req in requests:
            res = adder.add_one_req(
                req, has_chunked_req=False, truncation_align_size=None
            )
            if res == AddReqResult.CONTINUE:
                admitted.append(req)
        # Both re-visits fit; the first-visit (9628 charge) does not.
        self.assertEqual(len(admitted), 2)

        resident = 0
        for req in admitted:
            charge = adder._device_charge(
                req,
                len(req.full_untruncated_fill_ids),
                req.sampling_params.max_new_tokens,
            )
            resident += charge + len(req.prefix_indices)
        self.assertLessEqual(resident, pool)


# ---------------------------------------------------------------------------
# M2: frontier-waiter registry (P2-1 design §3) -- all set-membership ops
# ---------------------------------------------------------------------------


class FrontierWaiterRegistryTests(unittest.TestCase):
    """P2-1 M2: register / wake / pop / discard semantics of the frontier
    waiters and the M1b terminal-outcome table. Every operation is a set
    membership change; nothing consumes queues or writes back."""

    def test_register_wake_pop_cycle(self):
        cache = _make_cache()
        cache.register_frontier_waiter("r1", 42)
        self.assertEqual(cache._storage_frontier_waiters, {42: {"r1"}})
        cache.tree_core.advance_storage_persisted(42)
        cache._wake_frontier_waiters(42)
        self.assertEqual(cache._storage_frontier_ready, {"r1"})
        self.assertEqual(cache._storage_frontier_waiters, {})
        self.assertTrue(cache.pop_frontier_ready("r1"))
        self.assertFalse(cache.pop_frontier_ready("r1"))  # consumed once

    def test_re_register_overwrites_old_key(self):
        cache = _make_cache()
        cache.register_frontier_waiter("r1", 42)
        cache.register_frontier_waiter("r1", 7)
        self.assertEqual(cache._storage_frontier_waiters, {7: {"r1"}})
        # A re-registered waiter is no longer pending wakeup.
        cache.tree_core.advance_storage_persisted(42)
        cache._wake_frontier_waiters(42)
        self.assertEqual(cache._storage_frontier_ready, set())

    def test_wake_skips_unpersisted_and_deleted_nodes(self):
        cache = _make_cache()
        cache.register_frontier_waiter("r1", 42)
        # Not persisted yet: no wake.
        cache._wake_frontier_waiters(42)
        self.assertEqual(cache._storage_frontier_ready, set())
        # Deleted node: no wake, no KeyError (stale NodeId never dereferenced).
        cache.tree_core.node_exists = lambda node_id: False
        cache.tree_core.advance_storage_persisted(42)
        cache._wake_frontier_waiters(42)
        self.assertEqual(cache._storage_frontier_ready, set())
        self.assertEqual(cache._storage_frontier_waiters, {42: {"r1"}})

    def test_wake_moves_only_that_nodes_waiters(self):
        cache = _make_cache()
        cache.register_frontier_waiter("r1", 42)
        cache.register_frontier_waiter("r2", 7)
        cache.tree_core.advance_storage_persisted(42)
        cache._wake_frontier_waiters(42)
        self.assertEqual(cache._storage_frontier_ready, {"r1"})
        self.assertEqual(cache._storage_frontier_waiters, {7: {"r2"}})

    def test_wake_requires_same_node_ack_not_ancestor(self):
        # The frontier dependency is the waiter's OWN anchor: an ack
        # advancing any other node -- including the anchor's ancestor --
        # must not wake it. Only the anchor's own ack does (design §3.1:
        # the anchor's ack arrives after its parents', so it is the
        # reliable signal). This pins the e10-01 mapping verdict: the wait
        # node and the ACK node are the same dependency.
        cache = _make_cache()
        cache.register_frontier_waiter("r1", 42)
        # Ancestor (or any non-anchor) ack: the waiter stays parked under
        # its own anchor.
        cache.tree_core.advance_storage_persisted(41)
        cache._wake_frontier_waiters(41)
        self.assertEqual(cache._storage_frontier_ready, set())
        self.assertEqual(cache._storage_frontier_waiters, {42: {"r1"}})
        # The anchor's own ack: wake, then consume.
        cache.tree_core.advance_storage_persisted(42)
        cache._wake_frontier_waiters(42)
        self.assertEqual(cache._storage_frontier_ready, {"r1"})
        self.assertEqual(cache._storage_frontier_waiters, {})
        self.assertTrue(cache.pop_frontier_ready("r1"))
        self.assertFalse(cache.pop_frontier_ready("r1"))

    def test_discard_frontier_waiter_idempotent(self):
        cache = _make_cache()
        cache.register_frontier_waiter("r1", 42)
        cache.register_frontier_waiter("r2", 42)
        cache.tree_core.advance_storage_persisted(42)
        cache._wake_frontier_waiters(42)
        cache.discard_frontier_waiter("r1")
        self.assertEqual(cache._storage_frontier_ready, {"r2"})
        cache.discard_frontier_waiter("r1")  # idempotent
        cache.discard_frontier_waiter("r2")
        self.assertEqual(cache._storage_frontier_ready, set())
        self.assertEqual(cache._storage_frontier_waiters, {})

    def test_release_aborted_request_cleans_waiter_and_terminal(self):
        cache = _make_cache()
        cache.register_frontier_waiter("r1", 42)
        cache.record_storage_prefetch_terminal("r1", "revoked_miss")
        cache.release_aborted_request("r1")
        self.assertEqual(cache._storage_frontier_waiters, {})
        self.assertEqual(cache._storage_frontier_ready, set())
        self.assertIsNone(cache.pop_storage_prefetch_terminal("r1"))

    def test_pop_prefetch_loaded_tokens_cleans_waiter_and_terminal(self):
        cache = _make_cache()
        cache.register_frontier_waiter("r1", 42)
        cache.record_storage_prefetch_terminal("r1", "finalized")
        cache.prefetch_loaded_tokens_by_reqid["r1"] = 256
        self.assertEqual(cache.pop_prefetch_loaded_tokens("r1"), 256)
        self.assertEqual(cache._storage_frontier_waiters, {})
        self.assertIsNone(cache.pop_storage_prefetch_terminal("r1"))

    def test_terminal_table_consumed_once(self):
        cache = _make_cache()
        cache.record_storage_prefetch_terminal("r1", "finalized")
        self.assertEqual(cache.pop_storage_prefetch_terminal("r1"), "finalized")
        self.assertIsNone(cache.pop_storage_prefetch_terminal("r1"))

    def test_has_restore_potential(self):
        # T6 precondition (design §2.5-1): host material, an in-flight or
        # registered restore intent, or an L3-queryable anchor chain.
        cache = _make_cache()
        self.assertTrue(cache.has_restore_potential("r1", 42, host_hit_length=10))
        cache.tree_core.is_backuped = lambda node_id: True
        self.assertTrue(cache.has_restore_potential("r1", 42, host_hit_length=0))
        cache.tree_core.is_backuped = lambda node_id: False
        cache.ongoing_prefetch["r1"] = "op"
        self.assertTrue(cache.has_restore_potential("r1", 42, 0))
        cache.ongoing_prefetch.clear()
        cache._storage_prefetch_missed_rids.add("r1")
        self.assertTrue(cache.has_restore_potential("r1", 42, 0))
        cache._storage_prefetch_missed_rids.clear()
        # Deleted anchor: no chain to query.
        cache.tree_core.node_exists = lambda node_id: False
        self.assertFalse(cache.has_restore_potential("r1", 42, 0))

    def test_frontier_anchor_ready_requires_persisted(self):
        # P2-1 M2 T11 (e8): the per-pass wake predicate must mirror the ACK
        # wake -- a backuped-but-unpersisted anchor re-issues the prefetch
        # into an empty L3. The pre-fix predicate woke on is_backuped
        # (committed at D->H submission, before the L3 write), which is the
        # premature wake that kept frontier_wake at zero.
        cache = _make_cache()
        self.assertFalse(cache.frontier_anchor_ready(42))  # not persisted
        cache.tree_core.is_backuped = lambda node_id: True
        # Regression: the old predicate returned True here.
        self.assertFalse(cache.frontier_anchor_ready(42))
        cache.tree_core.persisted.add(42)
        self.assertTrue(cache.frontier_anchor_ready(42))

    def test_frontier_anchor_ready_self_heals_deleted_or_root(self):
        # A deleted anchor wakes to re-match (design §3.3); the root is the
        # always-persisted anchor and never waits.
        cache = _make_cache()
        self.assertTrue(cache.frontier_anchor_ready(0))  # root anchor
        cache.tree_core.node_exists = lambda node_id: False
        self.assertTrue(cache.frontier_anchor_ready(42))  # deleted: re-match

    def test_prompt_can_qualify_for_prefetch(self):
        # Mirrors prefetch_from_storage's page-aligned threshold: a suffix
        # that can never reach prefetch_threshold (256, page_size 1 here)
        # is declined_too_short forever.
        cache = _make_cache()
        self.assertTrue(cache.prompt_can_qualify_for_prefetch(256, 0))
        self.assertFalse(cache.prompt_can_qualify_for_prefetch(255, 0))
        self.assertFalse(cache.prompt_can_qualify_for_prefetch(3, 0))
        # The host match reduces the longest possible suffix.
        self.assertTrue(cache.prompt_can_qualify_for_prefetch(300, 0))
        self.assertFalse(cache.prompt_can_qualify_for_prefetch(300, 100))

    def test_short_prompt_never_has_restore_potential(self):
        # Regression (tester e10): HEALTH_CHECK-class short prompts were
        # misjudged True via the root-anchor clause, entered WAIT[REVALIDATE]
        # and looped forever on the T11 capacity wake. A can-never-qualify
        # prompt has no restore intent regardless of the anchor chain.
        cache = _make_cache()
        cache.tree_core.is_root = lambda node_id: True  # root anchor
        self.assertFalse(cache.has_restore_potential("r1", 0, 0, prompt_len=3))
        # A registered intent (missed_rids, from its own earlier decline)
        # does not override the can-never-qualify gate either.
        cache._storage_prefetch_missed_rids.add("r1")
        self.assertFalse(cache.has_restore_potential("r1", 0, 0, prompt_len=3))
        # too_short churn (independent P): host material no longer overrides
        # the can-never-qualify gate -- a 15-token suffix (host match ate the
        # prompt) can never become a granted storage prefetch, so it must not
        # park WAIT[DEVICE_QUOTA] and loop on the capacity wake.
        self.assertFalse(cache.has_restore_potential("r1", 0, host_hit_length=10, prompt_len=3))
        # Long prompts keep the legacy clauses.
        cache._storage_prefetch_missed_rids.add("r1")
        self.assertTrue(cache.has_restore_potential("r1", 0, 0, prompt_len=300))
        # prompt_len unset = legacy behavior (existing callers unchanged).
        self.assertTrue(cache.has_restore_potential("r1", 0, 0))

    def test_never_case_gate_beats_host_material_for_sub_threshold_prompt(self):
        # too_short churn (main fix): a prompt whose BOTH current suffix and
        # theoretical-max suffix are below prefetch_threshold (256, page_size
        # 1 here) must NOT park WAIT[DEVICE_QUOTA] even though host material
        # is present -- its storage prefetch can never be granted, so the
        # capacity wake would only re-issue an inevitably declined_too_short
        # prefetch (wake -> re-issue -> declined -> re-WAIT tight loop). It
        # recomputes its tail directly.
        cache = _make_cache()
        # Current suffix (prompt_len - host_hit = 3-3 = 0) and max suffix
        # (3-3 = 0) both sub-threshold; host material present.
        self.assertFalse(cache.has_restore_potential("r1", 42, host_hit_length=3, prompt_len=3))
        # Host match ate nearly the whole prompt: only a 15-token tail left.
        self.assertFalse(cache.has_restore_potential("r1", 42, host_hit_length=300, prompt_len=315))

    def test_revalidate_bet_preserved_when_decay_can_grow_suffix(self):
        # too_short churn must NOT kill the device-match-decay REVALIDATE bet:
        # a prompt whose current suffix is sub-threshold but whose
        # theoretical-max suffix (prompt beyond the fixed host match) still
        # reaches the threshold can grow its suffix back above it once the
        # device match decays -- it keeps its restore potential.
        cache = _make_cache()
        # Current device match absorbs 100 tokens: suffix 300-10-100 = 190
        # < 256, but max suffix 300-10 = 290 >= 256 qualifies.
        self.assertTrue(cache.has_restore_potential("r1", 42, host_hit_length=10, prompt_len=300))
        # Boundary: max suffix exactly at the threshold still qualifies.
        self.assertTrue(cache.has_restore_potential("r1", 42, host_hit_length=100, prompt_len=356))
        # Max suffix just below the threshold: never-case, no restore intent.
        self.assertFalse(cache.has_restore_potential("r1", 42, host_hit_length=100, prompt_len=355))


# ---------------------------------------------------------------------------
# P2-1 e11: prefetch gate / wake agreement + the storage-backed hollow
# eviction fallback (the GPU-OOM deadlock breaker)
# ---------------------------------------------------------------------------


class _GateTree(_FakeTreeCore):
    """Prefetch-gate predicate states: backuped / root / persisted / hash."""

    def __init__(self):
        super().__init__()
        self.backuped = set()
        self.roots = {0}
        self.persisted = set()
        self.hashes = {}
        # _FakeTreeCore pre-binds is_backuped/is_root as instance lambdas;
        # rebind the class predicates so the overrides below take effect.
        self.is_backuped = self._is_backuped
        self.is_root = self._is_root
        self.is_storage_persisted = self._is_storage_persisted

    def _is_backuped(self, node_id):
        return node_id in self.backuped

    def _is_root(self, node_id):
        return node_id in self.roots

    def _is_storage_persisted(self, node_id):
        return node_id in self.persisted

    def get_last_hash_value(self, node_id):
        return self.hashes.get(node_id)


class PrefetchGateAgreementTests(unittest.TestCase):
    def test_gate_agrees_with_frontier_wake_on_persisted_anchor(self):
        # P2-1 e11 hot-loop pin: the T11/T12 wake predicate
        # (frontier_anchor_ready) wakes on a storage-persisted anchor, so the
        # prefetch gate must admit it even when the host copy was reclaimed
        # under host pressure. Pre-fix the gate demanded is_backuped, so the
        # wake re-registered the wait every scheduler pass (8,351 frontier_wait
        # registrations in the 1g run).
        cache = _make_cache(tree_core=_GateTree())
        cache.tree_core.persisted.add(175)
        self.assertTrue(cache.frontier_anchor_ready(175))  # the wake fires
        self.assertTrue(cache.prefetch_gate_ok(175))  # the gate agrees

    def test_gate_still_rejects_unpersisted_unbacked_anchor(self):
        # The original gate behavior is unchanged for a plain unbacked anchor:
        # no host copy, no L3 chain -- a re-issue would read an empty L3.
        cache = _make_cache(tree_core=_GateTree())
        self.assertFalse(cache.prefetch_gate_ok(175))
        self.assertFalse(cache.frontier_anchor_ready(175))

    def test_gate_accepts_backuped_root_and_buffer_hash(self):
        cache = _make_cache(tree_core=_GateTree())
        cache.tree_core.backuped.add(11)
        self.assertTrue(cache.prefetch_gate_ok(11))
        self.assertTrue(cache.prefetch_gate_ok(0))  # root anchor
        cache.tree_core.hashes[12] = "abc"
        self.assertTrue(cache.prefetch_gate_ok(12, buffer_mode=True))
        self.assertFalse(cache.prefetch_gate_ok(12, buffer_mode=False))


class _DeviceValue:
    """Stub device tensor: len() is the token count the backup path reads."""

    def __init__(self, n):
        self._n = n

    def __len__(self):
        return self._n

    def numel(self):
        return self._n


class _StubBackupKV:
    def __init__(self, node_ids):
        self.node_ids = node_ids


class _HollowWalkTree(_FakeTreeCore):
    """Walker stub for the hollow-eviction fallback: one D-leaf, then
    exhaustion; backup and subtree drop both blocked."""

    def __init__(self, persisted=True):
        super().__init__()
        self.steps = 0
        self.hollowed = []
        self.forced_drop = []
        self.is_write_back = True
        self.hollow_tracker = {_component_type.FULL: 2048}
        self.drop_tracker = {_component_type.FULL: 2048}
        self.freed_after_hollow = 2048
        if persisted:
            self.persisted.add(42)  # the leaf's chain is L3-persisted

    def evict_device_start(self, component_type, request_cnt):
        pass

    def evict_device_next_node(self, component_type, tracker):
        if self.steps == 0:
            self.steps += 1
            return _EvictNextNode(42)
        return _EvictNextNode(None)

    def evict_device_end(self, component_type):
        pass

    def evict_device_leaf(self, node_id, is_write_back):
        # Unbacked write-back leaf: the D->H backup action runs and fails.
        return SimpleNamespace(
            backup_kv=_StubBackupKV([node_id]),
            device_frees={},
            host_frees={},
            tracker={},
        )

    def drop_subtree_no_host(self, node_id):
        # Declined: the subtree's host values are DMA-locked (in-flight
        # prefetch), the P2-1 deadlock condition.
        return SimpleNamespace(
            is_dropped=False, device_frees={}, host_frees={}, tracker={}
        )

    def build_backup_spec(self, node_id):
        return _DeviceValue(2048), {}

    def evict_device_leaf_storage_backed(self, node_id):
        self.hollowed.append(node_id)
        return SimpleNamespace(
            device_frees={},
            host_frees={},
            tracker=dict(self.hollow_tracker),
        )

    def drop_device_leaf_to_miss(self, node_id):
        self.forced_drop.append(node_id)
        return SimpleNamespace(
            device_frees={},
            host_frees={},
            tracker=dict(self.drop_tracker),
        )

    def detach_miss_dropped(self, node_id):
        # The hollow-walk fixture drops nodes without a real tree parent
        # chain, so the post-drop detach is a faithful no-op.
        return SimpleNamespace(
            device_frees={}, host_frees={}, tracker={}, is_dropped=True
        )


class _EvictNextNode:
    def __init__(self, node_id):
        self.node_id = node_id
        self.made_progress = node_id is not None
        self.device_frees = {}
        self.host_frees = {}
        self.tracker = {}


class StorageBackedHollowEvictionTests(unittest.TestCase):
    def test_hollow_evict_breaks_backup_and_drop_deadlock(self):
        # P2-1 e11 OOM pin: backup fails (host full) and the subtree drop
        # declines (host locks), but the chain is L3-persisted -- the walker
        # must free the leaf's device layers instead of leaving it
        # unevictable until host space frees (the four-run GPU OOM). The
        # durable chain must hollow (L3-backed), never drop to a miss
        # (e15 Z3 regression pin).
        cache = _make_cache()
        cache.is_swa_enabled = False
        cache.tree_components = [_component_type.FULL, _component_type.MAMBA]
        cache.cache_controller.mem_pool_host = SimpleNamespace(
            available_size=lambda: 0
        )
        cache.evict_host = lambda needed: 0  # host full: no frees
        cache.tree_core = _HollowWalkTree()
        cache.token_to_kv_pool_allocator = SimpleNamespace(
            available_size=lambda: (
                cache.tree_core.freed_after_hollow
                if cache.tree_core.hollowed
                else 0
            )
        )
        tracker = {ct: 0 for ct in cache.tree_components}
        cache._evict_components(
            {_component_type.FULL: 2048, _component_type.MAMBA: 0},
            tracker,
            available_size_targets={_component_type.FULL: 2048},
        )
        self.assertEqual(cache.tree_core.hollowed, [42])
        self.assertEqual(cache.tree_core.forced_drop, [])
        self.assertEqual(tracker[_component_type.FULL], 2048)

    def test_drop_to_miss_when_chain_not_persisted(self):
        # P2-1 e15 Z3 contract flip (was test_no_hollow_when_chain_not_persisted):
        # a chain with no L3 copy still never hollows (there is no L3 copy to
        # hollow into), but it must also not stay device-resident until host
        # space frees -- that was the e11 deadlock shape. The dual-fail
        # fallback now sacrifices the device copy as a plain drop-to-miss:
        # cache persistence is lost (a future access recomputes), never faked
        # as a hollow with an L3 restore expectation.
        cache = _make_cache()
        cache.is_swa_enabled = False
        cache.tree_components = [_component_type.FULL, _component_type.MAMBA]
        cache.cache_controller.mem_pool_host = SimpleNamespace(
            available_size=lambda: 0
        )
        cache.evict_host = lambda needed: 0
        cache.tree_core = _HollowWalkTree(persisted=False)
        cache.token_to_kv_pool_allocator = SimpleNamespace(
            available_size=lambda: 0
        )
        tracker = {ct: 0 for ct in cache.tree_components}
        cache._evict_components(
            {_component_type.FULL: 2048, _component_type.MAMBA: 0},
            tracker,
            available_size_targets={_component_type.FULL: 2048},
        )
        self.assertEqual(cache.tree_core.hollowed, [])
        self.assertEqual(cache.tree_core.forced_drop, [42])
        self.assertEqual(tracker[_component_type.FULL], 2048)


# ---------------------------------------------------------------------------
# M1b T7: load-back failure returns RESTORE_DENIED (design C4)
# ---------------------------------------------------------------------------


class _FakeIndices(list):
    """Stubenv load-back result: list-shaped with numel() (the stubenv fake
    torch.cat concatenates lists)."""

    def numel(self):
        return len(self)


class _LoadBackTree(_FakeAdmissionTree):
    def __init__(self, result_len):
        super().__init__()
        self._result_len = result_len
        self.load_back_calls = 0

    def init_load_back(self, params):
        self.load_back_calls += 1
        if torch is not None:
            return torch.arange(self._result_len), object()
        return _FakeIndices(list(range(self._result_len))), object()


class LoadBackDeniedAdmissionTests(unittest.TestCase):
    """P2-1 M1b (T7): a load-back that comes back empty while the request
    still needs it must return RESTORE_DENIED -- the scheduler turns it into
    WAIT[DEVICE_QUOTA] instead of a silent full-span recompute (C4)."""

    def setUp(self):
        if torch is not None:
            from sglang.srt.server_args import (
                ServerArgs,
                set_global_server_args_for_scheduler,
            )

            set_global_server_args_for_scheduler(ServerArgs(model_path="dummy"))

    def _make_adder(self, tree):
        return PrefillAdder(
            page_size=128,
            tree_cache=tree,
            token_to_kv_pool_allocator=_FixedAllocator(),
            running_batch=None,
            new_token_ratio=1.0,
            rem_input_tokens=1 << 30,
            rem_chunk_tokens=None,
        )

    def test_empty_load_back_returns_restore_denied(self):
        tree = _LoadBackTree(0)
        adder = self._make_adder(tree)
        req = _FakeAdmissionReq(
            full_len=10000, prefix_len=4000, host_hit=2000, host_load_back=True
        )
        res = adder.add_one_req(req, has_chunked_req=False, truncation_align_size=None)
        self.assertIs(res, AddReqResult.RESTORE_DENIED)
        self.assertEqual(tree.load_back_calls, 1)
        # Not admitted, nothing mutated (the retry re-matches from scratch).
        self.assertEqual(adder.can_run_list, [])
        self.assertEqual(len(req.prefix_indices), 4000)

    def test_successful_load_back_still_admits(self):
        tree = _LoadBackTree(2000)
        adder = self._make_adder(tree)
        req = _FakeAdmissionReq(
            full_len=10000, prefix_len=4000, host_hit=2000, host_load_back=True
        )
        res = adder.add_one_req(req, has_chunked_req=False, truncation_align_size=None)
        self.assertIs(res, AddReqResult.CONTINUE)
        self.assertEqual(len(adder.can_run_list), 1)
        # The loaded span joined the device prefix.
        self.assertEqual(len(req.prefix_indices), 6000)

    def test_no_host_material_never_denied(self):
        # A first visit (no host hits) does not even attempt load-back.
        tree = _LoadBackTree(0)
        adder = self._make_adder(tree)
        req = _FakeAdmissionReq(full_len=10000, prefix_len=0, host_hit=0)
        res = adder.add_one_req(req, has_chunked_req=False, truncation_align_size=None)
        self.assertIs(res, AddReqResult.CONTINUE)
        self.assertEqual(tree.load_back_calls, 0)


# ---------------------------------------------------------------------------
# P2-1 e12: hollow-leaf sanity_check against the real UnifiedTreeCore
# ---------------------------------------------------------------------------


@unittest.skipIf(torch is None, "real UnifiedTreeCore needs torch")
class HollowStateSanityCheckTests(unittest.TestCase):
    """sanity_check must accept the e11 hollow leaf (Full released on both
    tiers, acked L3 chain is the durable copy) and still reject a genuinely
    dead node (no Full on any tier, no L3 chain)."""

    @staticmethod
    def _make_tree(persisted: bool):
        params = SimpleNamespace(
            page_size=1,
            is_eagle=False,
            enable_session_radix_cache=False,
            eviction_policy="lru",
            token_to_kv_pool_allocator=None,
            enable_kv_cache_events=False,
        )
        tree_core = _RealTreeCore(
            params,
            {
                _component_type.FULL: SimpleNamespace(tree_core=None),
                _component_type.MAMBA: SimpleNamespace(tree_core=None),
            },
        )
        tree_core.is_write_back = True
        node = tree_core._new_node()
        node.parent = tree_core.root_node
        node.key = _RadixKey(_array("q", [1, 2]), None)
        tree_core.root_node.children["only"] = node
        # Hollow state: Full device and host released, aux host slice kept.
        node.component_data[_component_type.FULL].value = None
        node.component_data[_component_type.FULL].host_value = None
        node.component_data[_component_type.MAMBA].host_value = object()
        node.storage_persisted = persisted
        # The surviving aux host slice must match the aux host LRU.
        tree_core.host_lru_lists[_component_type.MAMBA].insert_mru(node)
        return tree_core

    def test_hollow_persisted_leaf_passes(self):
        # e12 pin: the P2-1 idle crash (tester e16) -- node 511 had mamba
        # host present, Full host None, Full device None, chain L3-persisted.
        # The L3 chain is the durable backup and a later restore refills the
        # node, so sanity_check must not call it dead.
        tree_core = self._make_tree(persisted=True)
        tree_core.sanity_check([], [])  # must not raise

    def test_genuinely_dead_leaf_still_fails(self):
        # The dead-node invariant is unchanged for a node with no Full data
        # anywhere and no L3 chain: it is unrecoverable, so it must assert.
        tree_core = self._make_tree(persisted=False)
        with self.assertRaises(AssertionError) as ctx:
            tree_core.sanity_check([], [])
        self.assertIn("dead", str(ctx.exception))

    def test_aux_host_without_full_still_fails_outside_write_back(self):
        # The hollow escape is write_back-only: outside write_back an aux
        # host slice with no Full host on any tier is still a violation.
        tree_core = self._make_tree(persisted=False)
        tree_core.is_write_back = False
        with self.assertRaises(AssertionError) as ctx:
            tree_core.sanity_check([], [])
        self.assertIn("host present but Full.host_value=None", str(ctx.exception))


# ---------------------------------------------------------------------------
# P2-1 M1/M2: L3 write integrity and retroactive chain promotion (real tree)
# ---------------------------------------------------------------------------


@unittest.skipIf(torch is None, "real UnifiedTreeCore needs torch")
class StoragePromotionChainTests(unittest.TestCase):
    """advance_storage_persisted must not depend on ack order: a child acked
    before its parent is promoted retroactively when the parent's ack
    arrives; a node whose write was only submitted (never acked) is never
    promoted, and a partial-write ack clears the submission dedupe guard."""

    @staticmethod
    def _make_chain():
        params = SimpleNamespace(
            page_size=1,
            is_eagle=False,
            enable_session_radix_cache=False,
            eviction_policy="lru",
            token_to_kv_pool_allocator=None,
            enable_kv_cache_events=False,
        )
        tree_core = _RealTreeCore(
            params,
            {
                _component_type.FULL: SimpleNamespace(tree_core=None),
                _component_type.MAMBA: SimpleNamespace(tree_core=None),
            },
        )
        tree_core.is_write_back = True
        a = tree_core._new_node()
        a.parent = tree_core.root_node
        a.key = _RadixKey(_array("q", [1, 2]), None)
        tree_core.root_node.children["a"] = a
        b = tree_core._new_node()
        b.parent = a
        b.key = _RadixKey(_array("q", [3, 4]), None)
        a.children["b"] = b
        return tree_core, a, b

    def test_child_acked_before_parent_promotes_on_parent_ack(self):
        # P2-1 M2: child ack first leaves the child unpromoted; the later
        # parent ack retroactively promotes it, ancestors first. Re-advance
        # of an already persisted node promotes nothing (idempotent).
        tree_core, a, b = self._make_chain()
        a.storage_written = True
        b.storage_written = True  # both submitted, only b's ack arrived

        promoted = tree_core.advance_storage_persisted(b.id)
        self.assertEqual(promoted, [])
        self.assertFalse(tree_core.is_storage_persisted(b.id))

        promoted = tree_core.advance_storage_persisted(a.id)
        self.assertEqual(promoted, [a.id, b.id])
        self.assertTrue(tree_core.is_storage_persisted(a.id))
        self.assertTrue(tree_core.is_storage_persisted(b.id))
        self.assertEqual(tree_core.advance_storage_persisted(a.id), [])
        self.assertEqual(tree_core.advance_storage_persisted(b.id), [])

    def test_submitted_but_unacked_child_is_not_retroactively_promoted(self):
        # storage_written means submitted, not acked: promoting the child on
        # the parent's ack would release the device copy on an L3 copy that
        # may still be in flight or failed.
        tree_core, a, b = self._make_chain()
        a.storage_written = True
        b.storage_written = True  # submitted only, ack never arrived

        promoted = tree_core.advance_storage_persisted(a.id)
        self.assertEqual(promoted, [a.id])
        self.assertFalse(tree_core.is_storage_persisted(b.id))
        self.assertFalse(b.storage_acked)

    def test_partial_ack_clears_dedupe_guard_for_rewrite(self):
        # P2-1 M1: after a partial write ack the node must be re-collected
        # by the next gap fill (the dedupe guard would skip it forever).
        tree_core, a, _b = self._make_chain()
        a.storage_written = True

        tree_core.clear_storage_written(a.id)

        self.assertFalse(a.storage_written)
        self.assertEqual(tree_core.collect_storage_gap(a.id), [a.id])


# ---------------------------------------------------------------------------
# P3: deferred-ACK reconciliation (phase2-p3-fix) -- clear_storage_durable
# must not strand storage_acked && !storage_persisted descendants (B guard),
# and the reconciliation pass (A3) must re-fill a broken parent chain from
# the nearest persisted ancestor / root so every acked node is promoted
# through a real write ack, never by reconciliation itself.
# ---------------------------------------------------------------------------


@unittest.skipIf(torch is None, "real UnifiedTreeCore needs torch")
class DeferredAckReconcileTests(unittest.TestCase):
    """The P3 durability-state-machine pins. These drive the real
    UnifiedTreeCore storage-flag transitions directly (no radix-cache layer):
    acked nodes deferred by a non-contiguous parent chain must be re-promoted
    after their parent is cleared (B guard) or physically deleted (A2), the
    reconcile scan must converge in a single pass, be idempotent, and never
    manufacture durability by itself."""

    @staticmethod
    def _make_chain(depth):
        """root -> n1 -> n2 -> ... -> n{`depth`}, all under the arena, page
        size 1 (hash_value may stay None -- collect_storage_gap and the
        promotion flags never read it)."""
        params = SimpleNamespace(
            page_size=1,
            is_eagle=False,
            enable_session_radix_cache=False,
            eviction_policy="lru",
            token_to_kv_pool_allocator=None,
            enable_kv_cache_events=False,
        )
        tree_core = _RealTreeCore(
            params,
            {
                _component_type.FULL: SimpleNamespace(tree_core=None),
                _component_type.MAMBA: SimpleNamespace(tree_core=None),
            },
        )
        tree_core.is_write_back = True
        nodes = []
        parent = tree_core.root_node
        for i in range(depth):
            n = tree_core._new_node()
            n.parent = parent
            parent.children[f"n{i}"] = n
            nodes.append(n)
            parent = n
        return tree_core, nodes

    # -- l3ack-e2 §7 item 1: child ACK first, parent durable later -----------
    def test_child_acked_before_parent_chain_promotes_on_parent_ack(self):
        # Baseline behavior (existing test 1): must survive the P3 changes.
        tree_core, (a, b) = self._make_chain(2)
        a.storage_written = True
        b.storage_written = True
        promoted = tree_core.advance_storage_persisted(b.id)
        self.assertEqual(promoted, [])
        self.assertFalse(tree_core.is_storage_persisted(b.id))
        self.assertEqual(tree_core.deferred_acked_nodes(), [b.id])
        promoted = tree_core.advance_storage_persisted(a.id)
        self.assertEqual(promoted, [a.id, b.id])
        self.assertTrue(tree_core.is_storage_persisted(a.id))
        self.assertTrue(tree_core.is_storage_persisted(b.id))
        self.assertEqual(tree_core.deferred_acked_nodes(), [])

    # -- l3ack-e2 §7 item 2: parent clear then restore -> descendants promote
    def test_clear_no_acked_descendants_then_parent_repromotes_descendants(self):
        # B guard holds for the no-acked-dependency case: clear drops the
        # parent's flags; a subsequent real write ack re-promotes the whole
        # acked subtree (A1's re-write + ack drain re-push).
        tree_core, (a, b, c) = self._make_chain(3)
        promoted = tree_core.advance_storage_persisted(a.id)
        self.assertEqual(promoted, [a.id])  # b/c not acked yet
        tree_core.advance_storage_persisted(b.id)  # c not acked: b deferred
        tree_core.advance_storage_persisted(c.id)  # now c's chain contiguous
        self.assertTrue(tree_core.is_storage_persisted(a.id))
        self.assertTrue(tree_core.is_storage_persisted(b.id))
        self.assertTrue(tree_core.is_storage_persisted(c.id))
        # Clear a with no acked-deferred descendant below it: allowed.
        tree_core.clear_storage_durable(a.id)
        self.assertFalse(tree_core.is_l3_durable(a.id))
        # The whole subtree stays persisted -- clearing the anchor is
        # anchor-precise and does not re-clear descendants (existing contract).
        self.assertTrue(tree_core.is_storage_persisted(b.id))
        self.assertTrue(tree_core.is_storage_persisted(c.id))
        # Parent re-ack: a itself is re-promoted (it was cleared); the
        # already-persisted subtree is not re-walked.
        self.assertEqual(tree_core.advance_storage_persisted(a.id), [a.id])
        self.assertTrue(tree_core.is_storage_persisted(a.id))

    # -- l3ack-e2 §7 item 3: A->B->C->D out-of-order ACK convergence --------
    def test_out_of_order_acks_converge_in_single_reconcile_pass(self):
        # Four-level chain, acks arrive bottom-up (every node deferred on its
        # own ack because the parent chain was not contiguous yet). Once the
        # full chain is acked, a single promotion of the chain head (root
        # child) re-promotes all acked descendants in one pass -- the A3
        # single-pass convergence: one chain-head re-ack fills the whole
        # broken chain, no per-descendant repeated triggering.
        tree_core, (a, b, c, d) = self._make_chain(4)
        for n in (d, c, b):
            tree_core.advance_storage_persisted(n.id)
        # a not acked yet: b/c/d are acked-deferred (their parents unpromoted).
        self.assertEqual(
            set(tree_core.deferred_acked_nodes()), {b.id, c.id, d.id}
        )
        # Single promotion of the root child a: all acked descendants are
        # retroactively promoted in one pass.
        promoted = tree_core.advance_storage_persisted(a.id)
        self.assertEqual(promoted, [a.id, b.id, c.id, d.id])
        self.assertTrue(tree_core.is_storage_persisted(d.id))
        self.assertEqual(tree_core.deferred_acked_nodes(), [])

    # -- l3ack-e2 §7 item 4: repeated ACK / repeated reconcile idempotency ---
    def test_repeat_ack_and_reconcile_are_idempotent(self):
        # a is durable via restore (not persisted), so b's ack defers under
        # it. Repeated clear while b stays deferred is a no-op (B guard);
        # repeated advance is a no-op once persisted.
        tree_core, (a, b) = self._make_chain(2)
        tree_core.mark_storage_restored(a.id)
        tree_core.advance_storage_persisted(b.id)  # a not persisted: b deferred
        self.assertTrue(tree_core.is_l3_durable(a.id))
        self.assertFalse(tree_core.is_storage_persisted(b.id))
        # Clear a: B guard holds (b is acked-deferred) -> durable belief kept.
        tree_core.clear_storage_durable(a.id)
        self.assertTrue(tree_core.is_l3_durable(a.id))
        # A repeated clear while the descendant stays deferred: no-op (guard).
        tree_core.clear_storage_durable(a.id)
        self.assertTrue(tree_core.is_l3_durable(a.id))
        # A3 sees the deferred node. A real chain-head re-ack promotes a then b.
        self.assertEqual(tree_core.deferred_acked_nodes(), [b.id])
        tree_core.advance_storage_persisted(a.id)
        self.assertTrue(tree_core.is_storage_persisted(a.id))
        self.assertTrue(tree_core.is_storage_persisted(b.id))
        self.assertEqual(tree_core.deferred_acked_nodes(), [])
        # Repeated advance after promotion: idempotent no-op.
        self.assertEqual(tree_core.advance_storage_persisted(a.id), [])
        self.assertEqual(tree_core.advance_storage_persisted(b.id), [])
        # Now b is persisted, so clearing a has no acked-deferred dependency:
        # the clear is allowed (the subtree is already fully durable).
        tree_core.clear_storage_durable(a.id)
        self.assertFalse(tree_core.is_l3_durable(a.id))

    # -- l3ack-e2 §7 item 5: no fabricated durable promotion -----------------
    def test_reconcile_never_promotes_by_itself(self):
        # reconciliation only reports acked-deferred nodes; promoting requires
        # a real write ack. With no parent durable, an acked child stays
        # deferred even though the scan sees it.
        tree_core, (a, b) = self._make_chain(2)
        tree_core.advance_storage_persisted(b.id)
        self.assertEqual(tree_core.deferred_acked_nodes(), [b.id])
        # No ack for a: b remains deferred (scan sees it, promotes nothing).
        self.assertFalse(tree_core.is_storage_persisted(b.id))
        self.assertFalse(tree_core.is_l3_durable(b.id))
        # Once a really acks, b promotes.
        tree_core.advance_storage_persisted(a.id)
        self.assertTrue(tree_core.is_storage_persisted(b.id))

    # -- l3ack-e2 §7 B-guard extra: clear with acked-dependency is deferred ---
    def test_clear_with_acked_descendant_is_deferred_not_cleared(self):
        # The B guard: when a's subtree still holds an acked-deferred node,
        # clearing a's durable belief would strand it, so the clear is
        # deferred (the A1/A3 reconciliation re-writes a's chain instead).
        # Here a is durable via restore (storage_restored, not persisted): its
        # own ack never promoted it, so acked descendants stay deferred until
        # a's chain is re-written and really acked.
        tree_core, (a, b, c) = self._make_chain(3)
        tree_core.mark_storage_restored(a.id)  # a durable via restore
        tree_core.advance_storage_persisted(b.id)  # a not persisted: b deferred
        self.assertTrue(tree_core.is_l3_durable(a.id))
        self.assertFalse(tree_core.is_storage_persisted(a.id))
        self.assertFalse(tree_core.is_storage_persisted(b.id))
        self.assertEqual(tree_core.deferred_acked_nodes(), [b.id])
        tree_core.clear_storage_durable(a.id)
        # a's durable belief is preserved, so b's promotion path stays intact.
        self.assertTrue(tree_core.is_l3_durable(a.id))
        self.assertTrue(tree_core.has_acked_descendant(a.id))
        # c acks (also deferred). A3 re-writes a's chain; a's real re-ack
        # promotes a, then the already-acked b and c.
        tree_core.advance_storage_persisted(c.id)
        self.assertEqual(
            set(tree_core.deferred_acked_nodes()), {b.id, c.id}
        )
        promoted = tree_core.advance_storage_persisted(a.id)
        self.assertEqual(set(promoted), {a.id, b.id, c.id})
        self.assertTrue(tree_core.is_storage_persisted(b.id))
        self.assertTrue(tree_core.is_storage_persisted(c.id))
        self.assertEqual(tree_core.deferred_acked_nodes(), [])

    # -- A2: parent physically deleted -> write_backup on descendant fills ----
    def test_physical_parent_delete_chain_rebuilt_from_root_on_descendant_write(
        self,
    ):
        # Simulate a host eviction that physically deleted node a (detach /
        # tombstone cascade) and re-anchored the surviving deferred
        # descendant b directly under root (the detached-chain rebuild). A2/A3
        # repair b: its write is already complete (no gap to re-fill --
        # collect_storage_gap returns []), so the repair is re-running
        # promotion now that b's parent is root (contiguous), promoting b.
        tree_core, (a, b) = self._make_chain(2)
        tree_core.mark_storage_restored(a.id)  # a durable but not persisted
        tree_core.advance_storage_persisted(b.id)  # b deferred under a
        self.assertEqual(tree_core.deferred_acked_nodes(), [b.id])
        self.assertFalse(tree_core.is_storage_persisted(b.id))
        # a is physically deleted (arena membership dropped, like
        # _unregister_node); the surviving deferred b is re-anchored to root.
        tree_core._node_arena.pop(a.id, None)
        tree_core.root_node.children.pop("n0", None)
        b.parent = tree_core.root_node
        self.assertFalse(tree_core.node_exists(a.id))
        # b's write is already acked (storage_written), so no gap to re-fill.
        self.assertEqual(tree_core.collect_storage_gap(b.id), [])
        self.assertEqual(tree_core.deferred_acked_nodes(), [b.id])
        # Re-running promotion on b (its parent is now root = contiguous)
        # promotes it. This is the A2 reverse-path repair.
        promoted = tree_core.advance_storage_persisted(b.id)
        self.assertEqual(promoted, [b.id])
        self.assertTrue(tree_core.is_storage_persisted(b.id))
        self.assertEqual(tree_core.deferred_acked_nodes(), [])

    def test_collect_storage_gap_stops_at_nearest_persisted_ancestor(self):
        # The A1/A3 re-fill basis: gap collection walks ancestors from the
        # nearest persisted node (root when none) to the target, skipping
        # already-written nodes. A chain with a persisted middle ancestor
        # fills only the suffix above it; a cleared anchor extends the gap
        # back to root.
        tree_core, (a, b, c) = self._make_chain(3)
        tree_core.advance_storage_persisted(a.id)  # a persisted; b/c unacked
        # Gap for c: b and c (a is the persisted stop; nothing written yet).
        self.assertEqual(tree_core.collect_storage_gap(c.id), [b.id, c.id])
        # Gap for a: none (a itself is persisted).
        self.assertEqual(tree_core.collect_storage_gap(a.id), [])
        # Written dedupe: once b is written, the gap for c is [c] only.
        b.storage_written = True
        self.assertEqual(tree_core.collect_storage_gap(c.id), [c.id])
        # Clear a (no acked descendants): a is no longer persisted, but its
        # write was already submitted (storage_written), so the gap for c
        # walks from root skipping a and the already-written b: [c] only.
        tree_core.clear_storage_durable(a.id)
        self.assertFalse(tree_core.is_l3_durable(a.id))
        self.assertEqual(tree_core.collect_storage_gap(c.id), [c.id])
        # Undo b's write: now the gap for c is [b, c] (a is skipped as
        # already written, even though it is no longer persisted).
        b.storage_written = False
        self.assertEqual(tree_core.collect_storage_gap(c.id), [b.id, c.id])
        # No persisted ancestor at all: the full chain from root.
        tree_core2, (a2, b2, c2) = self._make_chain(3)
        self.assertEqual(
            tree_core2.collect_storage_gap(c2.id), [a2.id, b2.id, c2.id]
        )


class DeferredAckReconcileCacheTests(unittest.TestCase):
    """P3 A3 (phase2-p3-fix): the radix-cache reconcile entry
    (_flush_pending_storage_writes -> _reconcile_deferred_acked) re-promotes
    a deferred-ACK node whose parent chain was cleared / deleted, and wakes
    its frontier waiter -- the loop the T13 60s timeout used to cut short.
    Drives the REAL UnifiedTreeCore through the REAL radix-cache flush, so
    the write_backup_storage / advance_storage_persisted /
    _wake_frontier_waiters code paths all run."""

    @unittest.skipIf(torch is None, "real UnifiedTreeCore needs torch")
    def test_reconcile_repromotes_deferred_and_wakes_frontier(self):
        cache = _make_cache()
        # A real tree core (arena + promotion flags) behind the harness.
        params = SimpleNamespace(
            page_size=1,
            is_eagle=False,
            enable_session_radix_cache=False,
            eviction_policy="lru",
            token_to_kv_pool_allocator=None,
            enable_kv_cache_events=False,
        )
        tree_core = _RealTreeCore(
            params,
            {
                _component_type.FULL: SimpleNamespace(tree_core=None),
                _component_type.MAMBA: SimpleNamespace(tree_core=None),
            },
        )
        tree_core.is_write_back = True
        tree_core.enable_storage = True  # cache.enable_storage proxies to it
        cache.tree_core = tree_core
        a = tree_core._new_node()
        a.parent = tree_core.root_node
        tree_core.root_node.children["a"] = a
        b = tree_core._new_node()
        b.parent = a
        a.children["b"] = b
        # a was a persisted anchor, then its durable belief was cleared while
        # no acked-deferred descendant existed yet (B guard allowed it). Now
        # a is acked && !persisted, so it is itself deferred.
        tree_core.advance_storage_persisted(a.id)
        tree_core.clear_storage_durable(a.id)
        self.assertFalse(tree_core.is_storage_persisted(a.id))
        # b acks under the now-unpersisted a: b is deferred too.
        tree_core.advance_storage_persisted(b.id)
        self.assertEqual(
            set(tree_core.deferred_acked_nodes()), {a.id, b.id}
        )
        # A frontier waiter is parked on b.
        cache._storage_frontier_waiters[b.id] = {"r1"}
        # The reconcile pass (flush) promotes the deferred ack chain -- a
        # first (root is its anchor), then b -- and wakes the waiter.
        cache._flush_pending_storage_writes()
        self.assertTrue(tree_core.is_storage_persisted(a.id))
        self.assertTrue(tree_core.is_storage_persisted(b.id))
        self.assertEqual(tree_core.deferred_acked_nodes(), [])
        self.assertEqual(cache._storage_frontier_ready, {"r1"})
        self.assertEqual(cache._storage_frontier_waiters, {})
        self.assertTrue(cache.pop_frontier_ready("r1"))

    @unittest.skipIf(torch is None, "real UnifiedTreeCore needs torch")
    def test_reconcile_is_reentrant_safe_and_never_promotes_barely(self):
        # A deferred node whose write is in flight (not yet acked) is NOT in
        # deferred_acked_nodes, so reconcile leaves it alone -- reconcile
        # never promotes a node that has not really acked. Also: running the
        # flush twice is safe (re-entrancy guard) and idempotent.
        cache = _make_cache()
        params = SimpleNamespace(
            page_size=1,
            is_eagle=False,
            enable_session_radix_cache=False,
            eviction_policy="lru",
            token_to_kv_pool_allocator=None,
            enable_kv_cache_events=False,
        )
        tree_core = _RealTreeCore(
            params,
            {
                _component_type.FULL: SimpleNamespace(tree_core=None),
                _component_type.MAMBA: SimpleNamespace(tree_core=None),
            },
        )
        tree_core.is_write_back = True
        cache.tree_core = tree_core
        a = tree_core._new_node()
        a.parent = tree_core.root_node
        tree_core.root_node.children["a"] = a
        tree_core.mark_storage_restored(a.id)
        # No acked node yet: reconcile finds nothing to do.
        cache._flush_pending_storage_writes()
        cache._flush_pending_storage_writes()
        self.assertEqual(tree_core.deferred_acked_nodes(), [])
        self.assertFalse(tree_core.is_storage_persisted(a.id))
        # A node that is only written (never acked) is not deferred/promoted.
        a.storage_written = True
        cache._flush_pending_storage_writes()
        self.assertEqual(tree_core.deferred_acked_nodes(), [])
        self.assertFalse(tree_core.is_storage_persisted(a.id))
        self.assertFalse(a.storage_acked)


# ---------------------------------------------------------------------------
# P2-1 e14: L3-durability predicate covering the restore chain
# (written+ACK or restored-successfully -- the K=32 evict deadlock)
# ---------------------------------------------------------------------------


class _RestoreMarkTree(_FakeTreeCore):
    """insert_host stub for the restore-marking path: the inserted node
    spans exactly the fetched prefix (a shortfall split keeps the suffix out
    of it), so the marked id is the durable range by construction."""

    def __init__(self, inserted_node_id=77, dropped=False):
        super().__init__()
        self.marked = []
        self.commit_calls = 0
        self.inserted_key_len = None
        self.inserted_node_id = inserted_node_id
        self.dropped = dropped
        self.insert_host = self._insert_host
        self.commit_hicache_transfers = self._commit_hicache_transfers

    def _insert_host(self, last_host_node_id, key, host_indices, hash_value):
        self.inserted_key_len = len(key)
        return SimpleNamespace(
            prefix_len=0,
            total_len=len(key),
            cache_actions=[],
            inserted_host_node=None if self.dropped else self.inserted_node_id,
            host_insert_dropped=self.dropped,
        )

    def _commit_hicache_transfers(self, *a, **k):
        self.commit_calls += 1

    def mark_storage_restored(self, node_id):
        self.marked.append(node_id)


def _make_restore_cache(tree_core=None):
    cache = _make_cache(tree_core=tree_core)
    cache.page_size = 1
    cache.enable_storage_metrics = False
    cache.cache_controller.mem_pool_host = SimpleNamespace(
        available_size=lambda: 1 << 30, free=lambda *a, **k: None
    )
    return cache


def _drive_prefetch_result(cache, operation, anchor=0):
    """Stage an in-flight prefetch for rid and run the finalize path."""
    req_id = operation.request_id
    prefetch_key = _RadixKey(
        _array("q", list(range(len(operation.hash_value)))), None
    )
    cache.ongoing_prefetch[req_id] = (
        anchor,
        prefetch_key,
        operation.host_indices,
        operation,
        None,
        {},
    )
    cache._handle_prefetch_result(operation)


class RestoreDurabilityMarkingTests(unittest.TestCase):
    """_handle_prefetch_result must mark the inserted node l3_durable only
    after a complete, non-dropped insert: full restores mark, shortfalls
    mark only the completed prefix (exactly what insert_host inserted), and
    hybrid all-or-nothing discards mark nothing (P2-1 e14 constraint 1)."""

    def test_full_restore_marks_inserted_node_durable(self):
        tree = _RestoreMarkTree(inserted_node_id=77)
        cache = _make_restore_cache(tree_core=tree)
        operation = _make_operation(4)
        operation.completed_tokens = 4
        _drive_prefetch_result(cache, operation)
        self.assertEqual(tree.marked, [77])
        self.assertEqual(tree.commit_calls, 1)

    def test_shortfall_marks_only_completed_prefix(self):
        # A partial restore inserts exactly the completed prefix: the split
        # (inside insert_host) puts the durable range in the inserted node
        # and leaves the un-restored suffix out of it -- only the prefix node
        # may be marked.
        tree = _RestoreMarkTree(inserted_node_id=77)
        cache = _make_restore_cache(tree_core=tree)
        operation = _make_operation(8, requested=8)
        operation.completed_tokens = 4  # shortfall: half the span delivered
        _drive_prefetch_result(cache, operation)
        self.assertEqual(tree.inserted_key_len, 4)  # insert_host got the prefix
        self.assertEqual(tree.marked, [77])  # and nothing else was marked

    def test_hybrid_discard_marks_nothing(self):
        # All-or-nothing sidecar shortfall: the whole prefetch is discarded,
        # so no node may be marked durable (there is no confirmed L3 range).
        transfer = SimpleNamespace(
            indices_from_pool=_PoolName.SWA,
            name="swa",
            keys=["k1", "k2"],
        )
        tree = _RestoreMarkTree(inserted_node_id=77)
        cache = _make_restore_cache(tree_core=tree)
        operation = _make_operation(4, pool_transfers=[transfer])
        operation.pool_transfers_done = False
        operation.completed_tokens = 4
        operation.pool_storage_result = SimpleNamespace(
            update_extra_pool_hit_pages=lambda *a, **k: None,
            extra_pool_hit_pages={},  # the sidecar served nothing
        )
        _drive_prefetch_result(cache, operation)
        self.assertEqual(tree.marked, [])
        self.assertEqual(tree.commit_calls, 0)  # never reached the insert


class _SplitComponent:
    """Minimal faithful component stub for the real-tree split pins: the
    split redistribution copies lock/session refs and slices list-typed
    device/host values by length (the real FullComponent logic, tensor-free).
    The e15 Z3 real-tree pins additionally need the device-eviction surface
    (evict_component / eviction_priority / node_has_component_data), mirrored
    from FullComponent + TreeComponent on list-typed values."""

    def __init__(self, ct):
        self.component_type = ct
        self.tree_core = None

    def eviction_priority(self, is_leaf: bool) -> int:
        return 0 if is_leaf else 2

    def node_has_component_data(self, node, target=None):
        # TreeComponent.node_has_component_data (DEVICE by default).
        ct = self.component_type
        cd = node.component_data[ct]
        if target is None or _evict_layer.DEVICE in target:
            return cd.value is not None
        return cd.host_value is not None

    def discard_deleted_session_leaf(self, node):
        # All multi-component deletion paths (e.g. _remove_leaf_from_parent)
        # call this on every component; the e16 regression fixture has no
        # session bookkeeping, so this is a faithful no-op.
        pass

    def evict_component(
        self, node, device_frees, host_frees, target=_evict_layer.DEVICE
    ):
        # FullComponent.evict_component on list-typed values; the device
        # value tombstone is deferred to the cascade (SWA reads Full.value).
        cd = node.component_data[self.component_type]
        freed = 0
        host_freed = 0
        if _evict_layer.DEVICE in target and cd.value is not None:
            device_frees[self.component_type].append(cd.value)
            freed = len(cd.value)
            self.tree_core.component_evictable_size_[self.component_type] -= freed
        if _evict_layer.HOST in target and cd.host_value is not None:
            host_freed = len(cd.host_value)
            host_frees[self.component_type].append(cd.host_value)
            cd.host_value = None
        return freed, host_freed

    def acquire_component_lock(
        self, node, result, lock_host: bool = False
    ):
        # FullComponent.acquire_component_lock (full_component.py:259-301)
        # on list-typed values: locking a device-on chain moves its tokens
        # from the evictable into the protected size -- the synchronous
        # accounting the P2-1c double-count evidence measures.
        ct = self.component_type
        if lock_host:
            cd = node.component_data[ct]
            if cd.host_value is None and not self.tree_core.is_write_back:
                return result
            cd.host_lock_ref += 1
            self.tree_core._update_evictable_leaf_sets(node)
            return result
        root = self.tree_core.root_node
        cur = node
        while cur is not root and cur.component_data[ct].value is None:
            result.skip_lock_node_ids.setdefault(ct, set()).add(cur.id)
            cur = cur.parent
        delta = 0
        while cur is not root:
            cd = cur.component_data[ct]
            assert cd.value is not None, (
                f"FULL invariant broken: evicted ancestor {cur.id} above "
                "device-on segment"
            )
            if cd.lock_ref == 0:
                key_len = len(cd.value)
                self.tree_core.component_evictable_size_[ct] -= key_len
                self.tree_core.component_protected_size_[ct] += key_len
                delta += key_len
            cd.lock_ref += 1
            self.tree_core.evictable_device_leaves.discard(cur)
            cur = cur.parent
        result.delta = delta
        return result

    def release_component_lock(self, node, params, lock_host: bool = False):
        # FullComponent.release_component_lock (full_component.py:303-339).
        ct = self.component_type
        if lock_host:
            cd = node.component_data[ct]
            if cd.host_lock_ref == 0:
                return
            if cd.host_value is None and not self.tree_core.is_write_back:
                return
            cd.host_lock_ref -= 1
            self.tree_core._update_evictable_leaf_sets(node)
            return
        root = self.tree_core.root_node
        skip_lock_node_ids = params.skip_lock_node_ids.get(ct, ()) if params else ()
        cur = node
        while cur != root:
            if cur.id in skip_lock_node_ids:
                cur = cur.parent
                continue
            cd = cur.component_data[ct]
            assert cd.value is not None
            assert cd.lock_ref > 0
            if cd.lock_ref == 1:
                key_len = len(cd.value)
                self.tree_core.component_evictable_size_[ct] += key_len
                self.tree_core.component_protected_size_[ct] -= key_len
            cd.lock_ref -= 1
            if cd.lock_ref == 0:
                self.tree_core._update_evictable_leaf_sets(cur)
            cur = cur.parent

    def prepare_load_back(self, node_id, *, req=None):
        return SimpleNamespace()

    def finalize_load_back(self, req, prep, success):
        pass

    def build_hicache_transfers(
        self,
        node,
        phase,
        *,
        mamba_pool_idx=None,
        host_indices=None,
        token_ids=None,
        prefetch_tokens=0,
        last_hash=None,
    ):
        # FullComponent.build_hicache_transfers LOAD_BACK on list-typed
        # values (full_component.py:362-387): the evicted segment's host
        # values become the transfer. Aux components have no test-side
        # transfer, so only the FULL component answers.
        if phase != _cache_transfer_phase.LOAD_BACK:
            return None
        if self.component_type != _component_type.FULL:
            return None
        backed_up = []
        nodes = []
        cur = node
        while cur.evicted:
            cd = cur.component_data[self.component_type]
            assert cd.host_value is not None
            backed_up.append(cd.host_value)
            nodes.append(cur)
            cur = cur.parent
        backed_up.reverse()
        nodes.reverse()
        return [
            _PromoPoolTransfer(
                name=_PoolName.KV,
                host_indices=[i for part in backed_up for i in part],
                device_indices=None,
                nodes_to_load=[n.id for n in nodes],
            )
        ]

    def commit_hicache_transfer(
        self,
        node,
        phase,
        transfers=(),
        *,
        cache_actions=None,
        insert_result=None,
        pool_storage_result=None,
    ):
        # FullComponent.commit_hicache_transfer LOAD_BACK (full_component.py:
        # 407-425): write the transferred indices back as the device value
        # and re-enter the evictable accounting.
        if phase != _cache_transfer_phase.LOAD_BACK:
            return
        if not transfers or transfers[0].device_indices is None:
            self.tree_core._update_evictable_leaf_sets(node)
            return
        xfer = transfers[0]
        device_indices = xfer.device_indices
        offset = 0
        for nid in xfer.nodes_to_load or []:
            n = self.tree_core.node_by_id(nid)
            cd = n.component_data[self.component_type]
            n_len = len(cd.host_value)
            cd.value = device_indices[offset : offset + n_len]
            offset += n_len
            self.tree_core.component_evictable_size_[self.component_type] += n_len
            self.tree_core._update_evictable_leaf_sets(n)
        self.tree_core._update_evictable_leaf_sets(node)

    def redistribute_on_node_split(self, new_parent, child):
        ct = self.component_type
        new_parent.component_data[ct].lock_ref = child.component_data[ct].lock_ref
        new_parent.component_data[ct].session_ref = child.component_data[ct].session_ref
        split_len = len(new_parent.key)
        child_cd = child.component_data[ct]
        if child_cd.value is not None:
            new_parent.component_data[ct].value = child_cd.value[:split_len]
            child_cd.value = child_cd.value[split_len:]
        if child_cd.host_value is not None:
            new_parent.component_data[ct].host_value = child_cd.host_value[:split_len]
            child_cd.host_value = child_cd.host_value[split_len:]


def _make_real_tree():
    params = SimpleNamespace(
        page_size=1,
        is_eagle=False,
        enable_session_radix_cache=False,
        eviction_policy="lru",
        token_to_kv_pool_allocator=None,
        enable_kv_cache_events=False,
    )
    tree_core = _RealTreeCore(
        params,
        {
            _component_type.FULL: _SplitComponent(_component_type.FULL),
            _component_type.MAMBA: _SplitComponent(_component_type.MAMBA),
        },
    )
    tree_core.is_write_back = True
    return tree_core


def _attach_chain(tree_core, n_tokens, key_offset=0):
    """Root -> child with n_tokens of device KV and empty L3 flags.
    key_offset disambiguates sibling chains (page_size == 1 keys collide on
    their first token otherwise, orphaning the earlier chain)."""
    child = tree_core._new_node()
    child.parent = tree_core.root_node
    child.key = _RadixKey(
        _array("q", list(range(1 + key_offset, n_tokens + 1 + key_offset))), None
    )
    tree_core.root_node.children[child.key.child_key(tree_core.page_size)] = child
    child.component_data[_component_type.FULL].value = [0] * n_tokens
    return child


# ---------------------------------------------------------------------------
# P2-1c promotion admission harness: real load_back / loading_check against
# a real tree + fake pool/controller (torch-free).
# ---------------------------------------------------------------------------


class _PromoPoolTransfer:
    """List-typed stand-in for PoolTransfer (the stubenv fake drops kwargs,
    so the real transfer fields cannot ride on it)."""

    def __init__(self, name, host_indices, device_indices=None, nodes_to_load=None):
        self.name = name
        self.host_indices = host_indices
        self.device_indices = device_indices
        self.nodes_to_load = nodes_to_load or []


class _PromoAllocator:
    """Fake FULL-pool allocator for the P2-1c lifecycle pins: free tokens =
    size_full - allocated; alloc() hands out consecutive indices (the real
    allocator's full_available_size drops synchronously at load())."""

    def __init__(self, size_full):
        self._size_full = size_full
        self._allocated = 0

    @property
    def size_full(self):
        return self._size_full

    def available_size(self):
        return self._size_full - self._allocated

    def full_available_size(self):
        return self._size_full - self._allocated

    def alloc(self, need_size):
        assert need_size <= self.available_size(), "alloc overcommit"
        start = self._allocated
        self._allocated += need_size
        return list(range(start, start + need_size))

    def free(self, indices):
        self._allocated -= len(indices)


class _LoadBackController:
    """Fake controller driving the real load_back / loading_check: load()
    allocates from the fake pool and returns indices (or None when told to
    fail); the test appends ack entries before calling loading_check."""

    write_policy = "write_back"
    storage_failure_reason = None
    prefetch_tokens_occupied = 0

    def __init__(self, allocator, fail_load=False):
        self.allocator = allocator
        self.fail_load = fail_load
        self.ack_load_queue = []
        self.load_calls = 0

    def load(self, host_indices, node_id=-1, extra_pools=None):
        self.load_calls += 1
        if self.fail_load:
            return None
        return self.allocator.alloc(len(host_indices))

    def prefetch_rate_limited(self):
        return False


def _make_promo_tree():
    """Real tree whose FULL component is the lock/transfer-capable stub
    (list-typed values). No aux components: the promotion pins are
    FULL-pool-only."""
    params = SimpleNamespace(
        page_size=1,
        is_eagle=False,
        enable_session_radix_cache=False,
        eviction_policy="lru",
        token_to_kv_pool_allocator=None,
        enable_kv_cache_events=False,
    )
    tree_core = _RealTreeCore(
        params,
        {_component_type.FULL: _SplitComponent(_component_type.FULL)},
    )
    tree_core.is_write_back = True
    return tree_core


def _attach_host_chain(tree_core, n_tokens, key_offset=0):
    """Root -> child with n_tokens of host-only KV (device-less: value None,
    host_value present) -- the load_back entry state. key_offset
    disambiguates sibling chains (see _attach_chain)."""
    child = tree_core._new_node()
    child.parent = tree_core.root_node
    child.key = _RadixKey(
        _array("q", list(range(1 + key_offset, n_tokens + 1 + key_offset))), None
    )
    tree_core.root_node.children[child.key.child_key(tree_core.page_size)] = child
    child.component_data[_component_type.FULL].host_value = list(range(n_tokens))
    child.component_data[_component_type.FULL].value = None
    tree_core._update_evictable_leaf_sets(child)
    return child


def _make_loadback_cache(size_full=32768, tree_core=None, fail_load=False):
    """Cache harness driving the REAL load_back / loading_check against a
    real tree and a fake pool/controller."""
    cache = _make_cache(tree_core=tree_core or _make_promo_tree())
    cache.is_swa_enabled = False
    cache.is_mamba_enabled = False
    cache.token_to_kv_pool_allocator = _PromoAllocator(size_full)
    cache.req_to_token_pool = SimpleNamespace()
    cache.tree_components = [_component_type.FULL]
    cache.components = {
        _component_type.FULL: cache.tree_core.components_by_type[
            _component_type.FULL
        ]
    }
    cache._components_tuple = (cache.components[_component_type.FULL],)
    cache.cache_controller = _LoadBackController(
        cache.token_to_kv_pool_allocator, fail_load=fail_load
    )
    return cache


def _promo_req(host_hit_length, rid="r"):
    return SimpleNamespace(
        rid=rid,
        host_hit_length=host_hit_length,
        mamba_pool_idx=None,
        last_node=None,
    )


class SplitDurabilityInheritanceTests(unittest.TestCase):
    """_split_node must propagate the child's L3 state to the new prefix
    fragment: the prefix's pages are a subset of the child's, so every
    L3-backed property (durable / acked / persisted / written) of the child
    holds for it (P2-1 e14 constraint 2, E13 same-family flags)."""

    def test_restored_durable_split_keeps_both_fragments_durable(self):
        # The K=32 shape: a restored (never written) chain splits; both
        # fragments must stay hollowable.
        tree_core = _make_real_tree()
        child = _attach_chain(tree_core, 4)
        child.storage_restored = True
        new_node, action = tree_core._split_node(child.key, child, 2)
        self.assertIsNone(action)
        self.assertTrue(new_node.storage_restored)
        self.assertTrue(child.storage_restored)
        self.assertTrue(tree_core.is_l3_durable(new_node.id))
        self.assertTrue(tree_core.is_l3_durable(child.id))

    def test_persisted_split_keeps_all_storage_flags_on_both_fragments(self):
        tree_core = _make_real_tree()
        child = _attach_chain(tree_core, 4)
        child.storage_written = True
        child.storage_acked = True
        child.storage_persisted = True
        new_node, _action = tree_core._split_node(child.key, child, 2)
        for node in (new_node, child):
            self.assertTrue(node.storage_written, node.id)
            self.assertTrue(node.storage_acked, node.id)
            self.assertTrue(node.storage_persisted, node.id)
        # The write source keeps the unified predicate true on both halves.
        self.assertTrue(tree_core.is_storage_persisted(new_node.id))
        self.assertTrue(tree_core.is_l3_durable(new_node.id))
        self.assertTrue(tree_core.is_l3_durable(child.id))

    def test_unmarked_split_stays_unmarked(self):
        # A pure recompute chain (no L3 copy anywhere) splits into two
        # fragments that still must never hollow.
        tree_core = _make_real_tree()
        child = _attach_chain(tree_core, 4)
        new_node, _action = tree_core._split_node(child.key, child, 2)
        self.assertFalse(new_node.storage_restored)
        self.assertFalse(child.storage_restored)
        self.assertFalse(new_node.storage_persisted)
        self.assertFalse(child.storage_persisted)
        self.assertFalse(tree_core.is_l3_durable(new_node.id))
        self.assertFalse(tree_core.is_l3_durable(child.id))


class RestoreChainHollowEvictionTests(unittest.TestCase):
    """The K=32 deadlock breaker at the walker level: a chain restored from
    L3 (l3_durable via the restore source) must hollow exactly like a
    written+acked chain when the D->H backup fails and the subtree drop is
    declined. A pure recompute chain still never hollows."""

    def test_hollow_evict_breaks_deadlock_on_restored_chain(self):
        cache = _make_cache()
        cache.is_swa_enabled = False
        cache.tree_components = [_component_type.FULL, _component_type.MAMBA]
        cache.cache_controller.mem_pool_host = SimpleNamespace(
            available_size=lambda: 0
        )
        cache.evict_host = lambda needed: 0
        tree = _HollowWalkTree(persisted=False)
        tree.durable.add(42)  # restored 43s ago; never written by this engine
        cache.tree_core = tree
        cache.token_to_kv_pool_allocator = SimpleNamespace(
            available_size=lambda: (
                tree.freed_after_hollow if tree.hollowed else 0
            )
        )
        tracker = {ct: 0 for ct in cache.tree_components}
        cache._evict_components(
            {_component_type.FULL: 2048, _component_type.MAMBA: 0},
            tracker,
            available_size_targets={_component_type.FULL: 2048},
        )
        self.assertEqual(tree.hollowed, [42])
        self.assertEqual(tree.forced_drop, [])
        self.assertEqual(tracker[_component_type.FULL], 2048)

    def test_drop_to_miss_for_pure_recompute_chain(self):
        # P2-1 e15 Z3 contract flip (was test_no_hollow_for_pure_recompute_chain):
        # a pure recompute chain (no L3 copy anywhere -- neither acked nor
        # restored) still never hollows, but under the backup+drop dual fail
        # it now drops its device layers to a plain miss instead of leaving
        # the walker stuck: the eviction must keep making progress even when
        # no tier can take over the KV (the e11 K=32 deadlock shape).
        cache = _make_cache()
        cache.is_swa_enabled = False
        cache.tree_components = [_component_type.FULL, _component_type.MAMBA]
        cache.cache_controller.mem_pool_host = SimpleNamespace(
            available_size=lambda: 0
        )
        cache.evict_host = lambda needed: 0
        cache.tree_core = _HollowWalkTree(persisted=False)
        cache.token_to_kv_pool_allocator = SimpleNamespace(
            available_size=lambda: 0
        )
        tracker = {ct: 0 for ct in cache.tree_components}
        cache._evict_components(
            {_component_type.FULL: 2048, _component_type.MAMBA: 0},
            tracker,
            available_size_targets={_component_type.FULL: 2048},
        )
        self.assertEqual(cache.tree_core.hollowed, [])
        self.assertEqual(cache.tree_core.forced_drop, [42])
        self.assertEqual(tracker[_component_type.FULL], 2048)


class L3DurabilityWritePathTests(unittest.TestCase):
    """P2-1 e14 constraint 3 + test 6: the durable flag must not suppress
    future backups (a stale L3 copy degrades to restore-miss -> recompute,
    never a permanent false positive), and the write-ACK source keeps
    working (acked chains become durable exactly as before)."""

    def test_l3_durable_does_not_skip_future_backup(self):
        tree_core = _make_real_tree()
        child = _attach_chain(tree_core, 4)
        tree_core.mark_storage_restored(child.id)  # restored chain
        self.assertTrue(tree_core.is_l3_durable(child.id))
        # The write path never consults l3_durable: the gap fill still
        # collects and rewrites the node (no skip-backup false positive).
        self.assertEqual(tree_core.collect_storage_gap(child.id), [child.id])

    def test_write_ack_marks_l3_durable(self):
        tree_core = _make_real_tree()
        child = _attach_chain(tree_core, 4)
        tree_core.advance_storage_persisted(child.id)
        self.assertTrue(tree_core.is_l3_durable(child.id))
        self.assertTrue(tree_core.is_storage_persisted(child.id))


class DropToMissSafetyValveTests(unittest.TestCase):
    """P2-1 e15 Z3 on the real tree: the last-resort device-layer release
    (backup failed + drop declined + not L3-durable) must free the device
    copy, keep the node and its host-only subtree, and leave no
    device/host/L3 hit behind -- and must refuse a leaf with an active
    request lock or an in-flight D->H write (the walker never yields one;
    the helper pins the invariant)."""

    @staticmethod
    def _leaf_tree():
        tree_core = _make_real_tree()
        child = _attach_chain(tree_core, 4)
        tree_core._update_evictable_leaf_sets(child)
        return tree_core, child

    def test_drop_to_miss_releases_device_and_leaf_misses(self):
        # The device value is freed (evicted), no host value or L3 belief is
        # invented, and the leaf leaves the evictable set: a later access
        # finds no device/host/L3 source and recomputes.
        tree_core, child = self._leaf_tree()
        result = tree_core.drop_device_leaf_to_miss(child.id)
        self.assertEqual(result.tracker[_component_type.FULL], 4)
        self.assertTrue(child.evicted)  # device value tombstoned
        self.assertFalse(child.backuped)  # no host copy invented
        self.assertFalse(tree_core.is_l3_durable(child.id))  # no L3 belief
        self.assertNotIn(child, tree_core.evictable_device_leaves)
        self.assertFalse(tree_core._is_device_leaf(child))
        self.assertIs(tree_core.node_by_id(child.id), child)  # node kept

    def test_drop_to_miss_keeps_host_subtree(self):
        # The crash shape: a D-leaf with host-only descendants (an in-flight
        # L3 write reads those host slots). Only the device layer may go.
        tree_core = _make_real_tree()
        parent = _attach_chain(tree_core, 4)
        tree_core._update_evictable_leaf_sets(parent)
        leaf = tree_core._new_node()
        leaf.parent = parent
        leaf.key = _RadixKey(_array("q", list(range(5, 9))), None)
        parent.children[leaf.key.child_key(tree_core.page_size)] = leaf
        leaf.component_data[_component_type.FULL].value = None  # host-only
        leaf.component_data[_component_type.FULL].host_value = [0] * 4
        tree_core.drop_device_leaf_to_miss(parent.id)
        self.assertIn(leaf, parent.children.values())
        self.assertIsNotNone(leaf.component_data[_component_type.FULL].host_value)
        self.assertTrue(parent.evicted)

    def test_locked_device_leaf_refuses_drop(self):
        # Safety pin (Z3 condition 1): an active request's chain lock keeps
        # the leaf out of the evictable set, and the drop refuses it.
        tree_core, child = self._leaf_tree()
        child.component_data[_component_type.FULL].lock_ref = 1
        tree_core._update_evictable_leaf_sets(child)
        self.assertNotIn(child, tree_core.evictable_device_leaves)
        with self.assertRaises(AssertionError):
            tree_core.drop_device_leaf_to_miss(child.id)

    def test_inflight_d2h_write_refuses_drop(self):
        # Safety pin (Z3 condition 2): an in-flight D->H write reads the
        # device slots, so a marked leaf must not be dropped.
        tree_core, child = self._leaf_tree()
        child.write_through_pending_id = 7  # in-flight D->H DMA
        with self.assertRaises(AssertionError):
            tree_core.drop_device_leaf_to_miss(child.id)


class DropToMissEvictionOrderRegressionTests(unittest.TestCase):
    """P2-1 e16: the e15 last-resort forced-miss drop (backup failed + drop
    declined + not L3-durable) must not leave a device-less, non-host-only
    node reachable inside a later drop_subtree_no_host traverse.

    e15 regression: a descendant that was first released to a plain miss
    (evicted + not backuped = dead) survived inside its ancestor's subtree.
    When the ancestor's D->H backup later failed and triggered
    drop_subtree_no_host, its traverse asserted every descendant
    ``evicted and backuped`` (host-only) and crashed -- even though the
    walker had already emitted forced_drop_to_miss for that descendant
    ("node %d not host-only").

    The fix has two layers:
    - the controller detaches the freed node from its parent immediately
      (query visibility preserved -- the parent chain backspaces the dead
      leaf, which carried no host/L3 KV);
    - drop_subtree_no_host additionally skips any forced-miss tombstone it
      still encounters (belt-and-suspenders)."""

    def test_interleaved_descendant_forced_drop_then_ancestor_drop_subtree(self):
        """The crash shape: leaf B is forced-dropped to a miss inside
        ancestor A's subtree; a later D->H backup failure of A must drop the
        subtree WITHOUT asserting on B (drop_subtree_no_host skips the
        tombstone and the walker's detector for a dead descendant)."""
        tree_core = _make_real_tree()
        a = _attach_chain(tree_core, 4)
        tree_core._update_evictable_leaf_sets(a)
        # Leaf B inside A's subtree, with a host-only tail long enough to
        # stay a distinct node (no tombstone collapse would remove it).
        b = tree_core._new_node()
        b.parent = a
        b.key = _RadixKey(_array("q", list(range(10, 18))), None)
        a.children[b.key.child_key(tree_core.page_size)] = b
        b.component_data[_component_type.FULL].value = [0] * 8

        # First pass: leaf B's backup fails and A is not L3-durable; B is
        # released to a plain miss and detached from A by the controller.
        # Check b is not L3-durable BEFORE the detach (detach unregisters it).
        self.assertFalse(tree_core.is_l3_durable(b.id))
        tree_core.drop_device_leaf_to_miss(b.id)
        self.assertTrue(b.forced_miss_tombstone)
        tree_core.detach_miss_dropped(b.id)
        # Detach removes b from its parent and unregisters it — consistent
        # with a normal eviction deletion: the dead leaf carried no host/L3
        # KV, so nothing visible is lost.
        self.assertNotIn(b, a.children.values())
        self.assertFalse(tree_core.node_exists(b.id))

        # Second pass: A is now a D-leaf (its only descendant is gone) and
        # its own backup fails; drop_subtree_no_host must not run the
        # host-only assert on B (which is no longer a child anyway) and must
        # drop A's remaining subtree cleanly.
        tree_core._update_evictable_leaf_sets(a)
        self.assertTrue(tree_core._is_device_leaf(a))
        result = tree_core.drop_subtree_no_host(a.id)
        self.assertTrue(result.is_dropped)
        # The node is gone from the arena; the leaf sets must not hold it.
        self.assertFalse(tree_core.node_exists(a.id))
        self.assertNotIn(a, tree_core.evictable_device_leaves)

    def test_drop_subtree_skips_forced_miss_ancestor_standalone(self):
        """Belt-and-suspenders: a forced-miss tombstone that somehow remains
        a descendant of the drop root is skipped (never asserted on) and
        both the tombstone's and the sibling's KV are released."""
        tree_core = _make_real_tree()
        a = _attach_chain(tree_core, 4)
        tree_core._update_evictable_leaf_sets(a)
        b = tree_core._new_node()
        b.parent = a
        b.key = _RadixKey(_array("q", list(range(10, 18))), None)
        a.children[b.key.child_key(tree_core.page_size)] = b
        b.component_data[_component_type.FULL].value = [0] * 8
        tree_core._update_evictable_leaf_sets(b)
        # Force-drop B but leave it attached (as if detach were skipped).
        tree_core.drop_device_leaf_to_miss(b.id)
        self.assertIn(b, a.children.values())
        # A sibling inside the same subtree that is still host-only.
        sib = tree_core._new_node()
        sib.parent = a
        sib.key = _RadixKey(_array("q", list(range(20, 22))), None)
        a.children[sib.key.child_key(tree_core.page_size)] = sib
        sib.component_data[_component_type.FULL].value = None
        sib.component_data[_component_type.FULL].host_value = [0] * 2
        tree_core._update_evictable_leaf_sets(a)
        self.assertTrue(tree_core._is_device_leaf(a))
        result = tree_core.drop_subtree_no_host(a.id)
        self.assertTrue(result.is_dropped)
        self.assertTrue(b.forced_miss_tombstone)
        self.assertFalse(tree_core.node_exists(a.id))

    def test_detach_preserves_parent_chain_and_query_visibility(self):
        """The detach must not remove content a query could still see: after
        a forced drop, the dead leaf's KV is gone from all tiers, so its
        detach removes nothing; the parent remains and its chain (device/root
        backup) is untouched."""
        tree_core = _make_real_tree()
        a = _attach_chain(tree_core, 4)
        tree_core._update_evictable_leaf_sets(a)
        b = tree_core._new_node()
        b.parent = a
        b.key = _RadixKey(_array("q", list(range(10, 18))), None)
        a.children[b.key.child_key(tree_core.page_size)] = b
        b.component_data[_component_type.FULL].value = [0] * 8
        tree_core.drop_device_leaf_to_miss(b.id)
        # b is dead: no device / no host / no L3.
        self.assertFalse(b.backuped)
        self.assertFalse(tree_core.is_l3_durable(b.id))
        tree_core.detach_miss_dropped(b.id)
        self.assertNotIn(b, a.children.values())
        # Detaching a dead leaf is a full deletion (its KV is gone from all
        # tiers), so b is unregistered, exactly like a normal eviction delete.
        self.assertFalse(tree_core.node_exists(b.id))
        self.assertTrue(b.forced_miss_tombstone)
        # The parent chain is intact and reachable; the node's device KV is
        # still present (a stays a D-leaf) and the split/backspace path can
        # still recompute b's tokens on a miss.
        self.assertIs(a.parent, tree_core.root_node)
        self.assertTrue(a in tree_core.evictable_device_leaves)

    def test_detach_clears_orphaned_host_subtree_registrations(self):
        """P2-1 e17: detaching a forced-miss D-leaf must not orphan its
        host-only children. A host-only child of the drop leaf keeps its host
        copy, aux host LRU, and host-leaf-set registrations, plus any stale
        duplicate entry; if it becomes unreachable from the root while those
        registrations survive, sanity_check's root-traversal membership checks
        fire the node-68 crash shape:
          H-leaf extra / Duplicate ghost / stale host_leaves / mamba host LRU.
        The detach must free and deregister the whole subtree so none of the
        four sets holds the orphan."""

        def build():
            tree_core = _make_real_tree()
            leaf = _attach_chain(tree_core, 4)
            # The drop leaf is backuped (its D->H copy exists) so it is a
            # full duplicate while its own subtree is still device-resident.
            leaf.component_data[_component_type.FULL].host_value = [0] * 4
            tree_core._update_evictable_leaf_sets(leaf)
            # Host-only child C of the drop leaf (device absent, host present,
            # mamba host present). In the engine, C was a settled duplicate
            # before its device layer was evicted, leaving a stale duplicate
            # entry behind; simulate that stale entry directly.
            c = tree_core._new_node()
            c.parent = leaf
            c.key = _RadixKey(_array("q", list(range(50, 58))), None)
            leaf.children[c.key.child_key(tree_core.page_size)] = c
            c.component_data[_component_type.FULL].value = None  # host-only
            c.component_data[_component_type.FULL].host_value = [1] * 8
            c.component_data[_component_type.MAMBA].value = None
            c.component_data[_component_type.MAMBA].host_value = [2] * 8
            tree_core.host_lru_lists[_component_type.MAMBA].insert_mru(c)
            tree_core._update_evictable_leaf_sets(c)
            tree_core.full_host_duplicates[c.id] = c  # stale settled-dup entry
            return tree_core, leaf, c

        tree_core, leaf, c = build()
        self.assertTrue(c in tree_core.evictable_host_leaves)
        self.assertTrue(c.id in tree_core.full_host_duplicates)
        self.assertTrue(c.id in tree_core.host_lru_lists[_component_type.MAMBA].cache)
        # Drop the leaf to a plain miss, then detach its subtree.
        tree_core.drop_device_leaf_to_miss(leaf.id)
        tree_core.detach_miss_dropped(leaf.id)
        # The orphaned host-only child C must be gone everywhere reachability
        # is asserted: not in the tree, not in the arena, and in none of the
        # four registration sets.
        self.assertNotIn(c, tree_core._collect_all_nodes())
        self.assertFalse(tree_core.node_exists(c.id))
        self.assertNotIn(c, tree_core.evictable_host_leaves)
        self.assertFalse(c.id in tree_core.full_host_duplicates)
        self.assertFalse(
            c.id in tree_core.host_lru_lists[_component_type.MAMBA].cache
        )
        # The drop leaf itself is fully freed and the parent of the leaf (the
        # root's child) is gone too -- nothing reachable from the root points
        # into the freed subtree.
        self.assertFalse(tree_core.node_exists(leaf.id))

    def test_ancestor_drop_does_not_orphan_tombstone_host_children(self):
        """P2-1 e23 (node-104 shutdown shape): drop_subtree_no_host's walk
        skips a forced-miss tombstone descendant for the host-only release/
        assert, but must NOT skip the tombstone's live host-only children.
        The dead tombstone carries no KV, yet its subtree can still hold a
        host-only L3-durable node (a restored anchor). Skipping that subtree
        orphans it when the drop root is removed -- it stays in the arena and
        in evictable_host_leaves / full_host_duplicates / the aux-mamba host
        LRU while becoming unreachable from the root, so sanity_check's
        root-traversal membership checks fire:
          H-leaf extra / Duplicate ghost / stale host_leaves / mamba host LRU.
        The drop must free and deregister the tombstone's live host-only
        children and the tombstone itself, leaving none of the four sets
        holding a node that is unreachable from the root."""
        tree_core = _make_real_tree()
        a = _attach_chain(tree_core, 4)
        tree_core._update_evictable_leaf_sets(a)
        # Tombstone child of a: a D-leaf released to a plain miss (dead node).
        tomb = tree_core._new_node()
        tomb.parent = a
        tomb.key = _RadixKey(_array("q", list(range(10, 18))), None)
        a.children[tomb.key.child_key(tree_core.page_size)] = tomb
        tomb.component_data[_component_type.FULL].value = [0] * 8
        tree_core._update_evictable_leaf_sets(tomb)
        tree_core.drop_device_leaf_to_miss(tomb.id)
        self.assertTrue(tomb.forced_miss_tombstone)
        # A live host-only L3-durable child C still attached under the
        # tombstone (the e16/e17 detach never ran for this subtree).
        c = tree_core._new_node()
        c.parent = tomb
        c.key = _RadixKey(_array("q", list(range(18, 26))), None)
        tomb.children[c.key.child_key(tree_core.page_size)] = c
        c.component_data[_component_type.FULL].value = None  # host-only
        c.component_data[_component_type.FULL].host_value = [1] * 8
        c.component_data[_component_type.MAMBA].value = None
        c.component_data[_component_type.MAMBA].host_value = [2] * 8
        tree_core.host_lru_lists[_component_type.MAMBA].insert_mru(c)
        c.storage_restored = True  # L3-durable restored anchor
        tree_core._update_evictable_leaf_sets(c)
        tree_core.full_host_duplicates[c.id] = c  # stale settled-dup entry
        # Dropping a's subtree must free and deregister C (and the tombstone),
        # not leave C orphaned in the arena with stale host registrations.
        result = tree_core.drop_subtree_no_host(a.id)
        self.assertTrue(result.is_dropped)
        self.assertNotIn(c, tree_core._collect_all_nodes())
        self.assertFalse(tree_core.node_exists(c.id))
        self.assertNotIn(c, tree_core.evictable_host_leaves)
        self.assertFalse(c.id in tree_core.full_host_duplicates)
        self.assertFalse(
            c.id in tree_core.host_lru_lists[_component_type.MAMBA].cache
        )
        self.assertFalse(tree_core.node_exists(tomb.id))
        # Drain the drop result so the BaseEvictionResult tripwire does not
        # warn (mirrors how the engine's _drop_subtree_no_host drains it).
        for k in list(result.host_frees):
            result.host_frees[k].clear()
        for k in list(result.device_frees):
            result.device_frees[k].clear()


class RevokeMissDurableClearTests(unittest.TestCase):
    """P2-1 e15 Y: a full-miss prefetch revoke clears the restore anchor's
    L3-durable belief (persisted + restored) so gates/wakes/hollow stop
    trusting a chain whose pages the query proved absent. Partial hits keep
    the belief; a later write ack re-sets it; the clear is anchor-precise
    and never spreads to the subtree."""

    def _revoke(self, tree_core, storage_hit, terminated=False):
        cache = _make_cache(tree_core=tree_core)
        op = _make_operation(0, requested=100)
        op.storage_hit_count = storage_hit
        if terminated:
            op.is_terminated = lambda: True
        cache.ongoing_prefetch["r1"] = (
            42,  # last_host_node_id: the restore anchor
            list(range(100)),
            None,
            op,
            None,
            {},
        )
        cache.revoke_pending_prefetch("r1")
        return cache

    def test_full_miss_revoke_clears_anchor_durable(self):
        tree = _FakeTreeCore()
        tree.durable.add(42)  # restored source
        tree.persisted.add(42)  # written+acked source
        self._revoke(tree, storage_hit=0)
        self.assertEqual(tree.durable_cleared, [42])
        self.assertFalse(tree.is_l3_durable(42))

    def test_partial_hit_revoke_keeps_anchor_durable(self):
        # hit > 0: the query found pages in the span, so the anchor's prefix
        # may still be intact -- the belief is not cleared.
        tree = _FakeTreeCore()
        tree.persisted.add(42)
        self._revoke(tree, storage_hit=64)
        self.assertEqual(tree.durable_cleared, [])
        self.assertTrue(tree.is_l3_durable(42))

    def test_terminated_revoke_still_clears_on_zero_hit(self):
        # The e15 contract keys on the query outcome, not the revoke
        # classification: storage_hit == 0 proves the anchor's pages absent.
        tree = _FakeTreeCore()
        tree.persisted.add(42)
        self._revoke(tree, storage_hit=0, terminated=True)
        self.assertEqual(tree.durable_cleared, [42])
        self.assertFalse(tree.is_l3_durable(42))

    def test_write_ack_resets_cleared_durable(self):
        # Self-healing (e15): a later write ack re-sets the belief.
        tree_core = _make_real_tree()
        child = _attach_chain(tree_core, 4)
        tree_core.advance_storage_persisted(child.id)
        self.assertTrue(tree_core.is_l3_durable(child.id))
        tree_core.clear_storage_durable(child.id)
        self.assertFalse(tree_core.is_l3_durable(child.id))
        tree_core.advance_storage_persisted(child.id)
        self.assertTrue(tree_core.is_l3_durable(child.id))

    def test_clear_durable_is_anchor_precise(self):
        # Only the anchor loses its belief; descendants keep theirs (their
        # durability is a separate fact; global consistency is Test B's scope).
        tree_core = _make_real_tree()
        parent = _attach_chain(tree_core, 4)
        child = tree_core._new_node()
        child.parent = parent
        child.key = _RadixKey(_array("q", list(range(5, 9))), None)
        parent.children[child.key.child_key(tree_core.page_size)] = child
        child.component_data[_component_type.FULL].value = [0] * 4
        tree_core.advance_storage_persisted(parent.id)
        tree_core.advance_storage_persisted(child.id)
        self.assertTrue(tree_core.is_l3_durable(parent.id))
        self.assertTrue(tree_core.is_l3_durable(child.id))
        tree_core.clear_storage_durable(parent.id)
        self.assertFalse(tree_core.is_l3_durable(parent.id))
        self.assertTrue(tree_core.is_l3_durable(child.id))


# ---------------------------------------------------------------------------
# P2-1c promotion admission (H->D capacity reservation)
# ---------------------------------------------------------------------------


class PromotionBudgetFunctionTests(unittest.TestCase):
    """P2-1c §6.1-1: the budget pure-function boundaries -- the == edge
    (32K exactly fits 32768 - 2048; one token over rejects), margin=0 lets
    2x16K through (pinned so nobody resets it to 0 and re-opens the e11
    crash shape), the in-flight cover states serialize 2x16K at the default
    margin, and negative inputs clamp."""

    def test_exact_boundary_accepts_at_capacity_minus_margin(self):
        self.assertTrue(_promotion_budget_fits(30720, 0, 0, 32768, 2048))
        self.assertFalse(_promotion_budget_fits(30721, 0, 0, 32768, 2048))

    def test_margin_zero_does_not_serialize_two_16k(self):
        # Pinned arithmetic (design §3.1): 16K locked + 16K new == the 32K
        # pool, so margin=0 admits the crash shape (two 16K chains lock the
        # pool with no walker-reclaimable floor); the default 2048 rejects.
        self.assertTrue(_promotion_budget_fits(16384, 0, 16384, 32768, 0))
        self.assertFalse(_promotion_budget_fits(16384, 0, 16384, 32768, 2048))

    def test_inflight_promotion_serializes_at_margin_2048(self):
        # A 16K promotion in flight -- covered by the reservation at the
        # gate, by the derived locked term after the ownership transfer --
        # plus a new 16K promotion is 32K > 30720 in both cover states.
        self.assertFalse(_promotion_budget_fits(0, 16384, 16384, 32768, 2048))
        self.assertFalse(_promotion_budget_fits(16384, 0, 16384, 32768, 2048))

    def test_small_promotion_passes_while_16k_in_flight(self):
        # Expert ①: with the ownership transfer the reservation never stacks
        # on the locked term, so a 2K promotion passes while A's 16K is in
        # flight (18K <= 30720); the double-count formula would reject it
        # (34K > 30720) for the whole DMA window -- the throughput the
        # transfer preserves.
        self.assertTrue(_promotion_budget_fits(16384, 0, 2048, 32768, 2048))
        self.assertFalse(_promotion_budget_fits(16384, 16384, 2048, 32768, 2048))

    def test_zero_terms_trivially_pass(self):
        self.assertTrue(_promotion_budget_fits(0, 0, 0, 32768, 2048))

    def test_negative_inputs_clamped(self):
        # Derived values must never go negative; a negative margin must not
        # widen the budget, and a negative locked must not create headroom.
        self.assertTrue(_promotion_budget_fits(-5, 0, 0, 32768, 2048))
        self.assertTrue(_promotion_budget_fits(0, 0, -7, 32768, 2048))
        self.assertFalse(_promotion_budget_fits(30000, 0, 3000, 32768, -2048))
        self.assertTrue(_promotion_budget_fits(30000, 0, 2000, 32768, -2048))


class PromotionLockedDerivationEvidenceTests(unittest.TestCase):
    """Expert ① evidence (log/counter-style, not code intuition): measure
    the derived locked term (capacity - available - evictable, the exact
    production accessors) across a real load-back lifecycle on a real tree.

    The verdict this pins: at the gate (entry + precise checkpoints) the
    host-only span is NOT inside derived locked -- the reservation is its
    only cover (no double count at the gate, and the reserve is what
    serializes). Once the load commits and the load lock is registered, the
    span IS inside derived locked -- keeping the reservation until the ack
    would double-count the same tokens for the whole DMA window, so the
    reservation transfers to lock ownership at registration (reserved only
    counts the not-yet-locked part).
    """

    def test_gate_locks_do_not_move_span_into_derived_locked(self):
        # The load_back entry state (1567/1570 locks on a device-less chain):
        # inc_host_lock_ref + inc_lock_ref change no size counter (the
        # tombstone-skip path), so derived locked is unchanged -- the span
        # is still free and the reservation covers it.
        cache = _make_loadback_cache(size_full=8192)
        child = _attach_host_chain(cache.tree_core, 2048)
        locked0 = cache._device_locked_tokens()
        self.assertEqual(locked0, 0)
        host_params = cache.inc_host_lock_ref(child.id).to_dec_params()
        lock_params = cache.inc_lock_ref(child.id).to_dec_params()
        self.assertEqual(cache._device_locked_tokens(), locked0)
        cache.dec_lock_ref(child.id, lock_params)
        cache.dec_host_lock_ref(child.id, host_params)

    def test_post_commit_span_enters_locked_and_reservation_transferred(self):
        # After the real load_back commits and registers the load lock, the
        # derived locked term includes the span (allocated + protected)
        # while the reservation counter is 0 (transferred). The same tokens
        # are counted exactly once; the ack then moves them back to
        # evictable and the lifecycle returns to zero.
        cache = _make_loadback_cache(size_full=8192)
        tree = cache.tree_core
        child = _attach_host_chain(tree, 2048)
        self.assertTrue(cache.load_back(child.id, req=_promo_req(2048)))
        self.assertEqual(cache.inflight_promotion_reserved, 0)  # transferred
        self.assertEqual(cache._promotion_transfer_count, 1)
        self.assertEqual(cache._promotion_reserve_count, 1)
        self.assertEqual(cache._device_locked_tokens(), 2048)
        self.assertEqual(cache._promotion_inflight_peak, 2048)
        cache.cache_controller.ack_load_queue.append(_FakeAck([child.id]))
        cache.loading_check(finish_count=1)
        self.assertEqual(cache.inflight_promotion_reserved, 0)
        self.assertEqual(cache._device_locked_tokens(), 0)
        self.assertEqual(
            tree.component_evictable_size_[_component_type.FULL], 2048
        )
        self.assertEqual(cache.ongoing_load_back, {})

    def test_device_locked_tokens_helper_matches_pool_arithmetic(self):
        # The scheduler-side helper mirrors the pool arithmetic: FULL pool
        # locked = size_full - free - evictable (dispatch via the cache
        # facade, exactly what the T11 predicate passes).
        cache = _make_loadback_cache(size_full=8192)
        tree = cache.tree_core
        child = _attach_chain(tree, 2048)
        tree.component_evictable_size_[_component_type.FULL] += 2048
        tree._update_evictable_leaf_sets(child)
        cache.token_to_kv_pool_allocator.alloc(2048)
        self.assertEqual(
            _device_locked_tokens(cache.token_to_kv_pool_allocator, cache),
            8192
            - cache.token_to_kv_pool_allocator.available_size()
            - cache.tree_core.full_evictable_size(),
        )
        self.assertEqual(
            _device_locked_tokens(cache.token_to_kv_pool_allocator, cache), 0
        )
        cache.token_to_kv_pool_allocator.alloc(1024)
        self.assertEqual(
            _device_locked_tokens(cache.token_to_kv_pool_allocator, cache), 1024
        )


class PromotionLifecycleReleaseTests(unittest.TestCase):
    """P2-1c §6.1-2 (expert ②): every terminal state releases the
    reservation exactly once and the counter returns to 0 -- E3 (eviction
    shortfall), E4 (load failed), E5 (ack), cancel (ack still drains),
    exception (controller load raises), shutdown/fatal sweep, and the pure
    aux path (kv_tokens == 0 never reserves)."""

    def _assert_counter_zero(self, cache):
        self.assertEqual(cache.inflight_promotion_reserved, 0)
        self.assertEqual(
            sum(lb.reserved_tokens for lb in cache.ongoing_load_back.values()),
            0,
        )

    def test_e3_eviction_shortfall_releases(self):
        # Budget passes at the gate (locked 0 + 2048 <= 8192 - 2048) but
        # the pool has no free tokens and the (stubbed) eviction finds
        # nothing: E3 returns the reservation with the locks.
        cache = _make_loadback_cache(size_full=8192)
        tree = cache.tree_core
        # A device-on filler occupies the pool as evictable (the production
        # eviction would reclaim it; the stub declines, so E3 fires).
        _attach_chain(tree, 8192)
        tree.component_evictable_size_[_component_type.FULL] += 8192
        cache.token_to_kv_pool_allocator.alloc(8192)  # pool full
        child = _attach_host_chain(tree, 2048, key_offset=8192)
        evict_calls = []
        cache.evict_for_alloc = lambda params: evict_calls.append(params.num_tokens)
        self.assertFalse(cache.load_back(child.id, req=_promo_req(2048)))
        self.assertEqual(evict_calls, [2048])
        self.assertEqual(cache._promotion_release_count, 1)
        self.assertEqual(cache._promotion_transfer_count, 0)
        self._assert_counter_zero(cache)
        self.assertEqual(cache.ongoing_load_back, {})
        # The chain lock was released (the leaf can be evicted again).
        self.assertEqual(
            child.component_data[_component_type.FULL].lock_ref, 0
        )

    def test_e4_load_failure_releases(self):
        # The controller refuses the allocation: E4 returns the reservation.
        cache = _make_loadback_cache(size_full=8192, fail_load=True)
        child = _attach_host_chain(cache.tree_core, 2048)
        self.assertFalse(cache.load_back(child.id, req=_promo_req(2048)))
        self.assertEqual(cache._promotion_release_count, 1)
        self._assert_counter_zero(cache)
        self.assertEqual(cache.ongoing_load_back, {})

    def test_e5_ack_releases(self):
        cache = _make_loadback_cache(size_full=8192)
        child = _attach_host_chain(cache.tree_core, 2048)
        self.assertTrue(cache.load_back(child.id, req=_promo_req(2048)))
        cache.cache_controller.ack_load_queue.append(_FakeAck([child.id]))
        cache.loading_check(finish_count=1)
        self._assert_counter_zero(cache)
        self.assertEqual(cache.ongoing_load_back, {})
        self.assertEqual(cache._promotion_transfer_count, 1)

    def test_cancel_still_acks_and_releases(self):
        # Expert ② cancel: release_aborted_request does not cancel an
        # in-flight load (design E6); the load still acks and the ack
        # finalizer releases exactly once.
        cache = _make_loadback_cache(size_full=8192)
        child = _attach_host_chain(cache.tree_core, 2048)
        self.assertTrue(cache.load_back(child.id, req=_promo_req(2048)))
        cache.release_aborted_request("r")  # prefetch-side cleanup only
        self.assertEqual(len(cache.ongoing_load_back), 1)
        cache.cache_controller.ack_load_queue.append(_FakeAck([child.id]))
        cache.loading_check(finish_count=1)
        self._assert_counter_zero(cache)
        self.assertEqual(cache.ongoing_load_back, {})

    def test_exception_mid_load_releases(self):
        # Expert ② explicit failure: cache_controller.load raising between
        # the reserve and any transfer/release must return the reservation
        # (the finally in _load_back_transfers).
        cache = _make_loadback_cache(size_full=8192)
        child = _attach_host_chain(cache.tree_core, 2048)

        def boom(host_indices, node_id=-1, extra_pools=None):
            raise RuntimeError("load DMA failed")

        cache.cache_controller.load = boom
        with self.assertRaises(RuntimeError):
            cache.load_back(child.id, req=_promo_req(2048))
        self.assertEqual(cache._promotion_release_count, 1)
        self._assert_counter_zero(cache)
        self.assertEqual(cache.ongoing_load_back, {})

    def test_shutdown_sweep_releases(self):
        # Expert ② shutdown/fatal: entries that will never ack terminate in
        # the sweep; their locks are released and the counter stays 0.
        cache = _make_loadback_cache(size_full=8192)
        child = _attach_host_chain(cache.tree_core, 2048)
        self.assertTrue(cache.load_back(child.id, req=_promo_req(2048)))
        self.assertEqual(len(cache.ongoing_load_back), 1)
        cache._release_all_load_backs(cause="fatal")
        self.assertEqual(cache.ongoing_load_back, {})
        self._assert_counter_zero(cache)
        self.assertEqual(
            child.component_data[_component_type.FULL].lock_ref, 0
        )

    def test_pure_aux_load_never_reserves(self):
        # est == 0 / kv_tokens == 0 (aux-only restore) skips the FULL-KV
        # budget: no reserve, no release, no transfer. The aux transfer
        # keeps the load alive past the threshold early-exit so the precise
        # gate is actually reached with kv_tokens == 0.
        cache = _make_loadback_cache(size_full=8192)
        child = _attach_host_chain(cache.tree_core, 2048)
        cache.tree_core.build_load_back_spec = lambda node_id, req=None: (
            _PromoPoolTransfer(
                name=_PoolName.KV, host_indices=[], nodes_to_load=[]
            ),
            {
                # Non-empty comp_xfers keeps the load alive past the E1
                # threshold early exit; the FULL component's commit is a
                # no-op for the empty node list (the real aux components
                # would commit their own pools).
                _component_type.FULL: [
                    _PromoPoolTransfer(
                        name=_PoolName.MAMBA, host_indices=[1, 2, 3]
                    )
                ]
            },
        )
        self.assertTrue(cache.load_back(child.id, req=_promo_req(0)))
        self.assertEqual(cache._promotion_reserve_count, 0)
        self.assertEqual(cache._promotion_release_count, 0)
        self.assertEqual(cache._promotion_transfer_count, 0)
        self.assertEqual(cache.inflight_promotion_reserved, 0)

    def test_counter_never_goes_negative(self):
        # A buggy double release clamps with an error log instead of going
        # negative (R3: a negative counter would jam or over-issue budget).
        cache = _make_loadback_cache(size_full=8192)
        cache._release_promotion_reservation(100, 42, "test")
        self.assertEqual(cache.inflight_promotion_reserved, 0)
        cache._transfer_promotion_reservation(100, 42)
        self.assertEqual(cache.inflight_promotion_reserved, 0)


class PromotionDeniedPathTests(unittest.TestCase):
    """P2-1c §6.1-3: a budget rejection flows through the EXISTING
    RESTORE_DENIED -> LOAD_BACK_FAIL -> WAIT[DEVICE_QUOTA] path -- zero new
    states (design §3.5). The cache gates return False (entry gate on est,
    precise gate on kv), init_load_back turns that into the empty match the
    adder maps to RESTORE_DENIED, and the state machine maps LOAD_BACK_FAIL
    to DEVICE_QUOTA exactly as before the budget existed."""

    def test_entry_gate_rejects_est_over_budget(self):
        cache = _make_loadback_cache(size_full=8192)
        child = _attach_host_chain(cache.tree_core, 2048)
        cache.promotion_margin_tokens = 1000000  # nothing ever fits
        self.assertFalse(cache.load_back(child.id, req=_promo_req(2048)))
        self.assertEqual(cache._promotion_denied_count, 1)
        self.assertEqual(cache._promotion_reserve_count, 0)
        self.assertEqual(cache.inflight_promotion_reserved, 0)
        # No host anchor / chain lock was taken.
        self.assertEqual(
            child.component_data[_component_type.FULL].host_lock_ref, 0
        )
        self.assertEqual(
            child.component_data[_component_type.FULL].lock_ref, 0
        )

    def test_precise_gate_rejects_kv_over_budget(self):
        # est is under the budget (entry gate passes) but the exact spec is
        # over: the precise gate is authoritative.
        cache = _make_loadback_cache(size_full=8192)
        child = _attach_host_chain(cache.tree_core, 8192)
        cache.promotion_margin_tokens = 2048
        self.assertTrue(_promotion_budget_fits(0, 0, 2048, 8192, 2048))
        self.assertFalse(_promotion_budget_fits(0, 0, 8192, 8192, 2048))
        self.assertFalse(cache.load_back(child.id, req=_promo_req(2048)))
        self.assertEqual(cache._promotion_denied_exact_count, 1)
        self.assertEqual(cache._promotion_reserve_count, 0)
        self.assertEqual(cache.inflight_promotion_reserved, 0)

    def test_denied_load_back_returns_empty_match(self):
        # init_load_back with a budget-rejected load_back returns the empty
        # device_indices the adder maps to RESTORE_DENIED (numel == 0).
        cache = _make_loadback_cache(size_full=8192)
        child = _attach_host_chain(cache.tree_core, 2048)
        cache.promotion_margin_tokens = 1000000
        indices, node = cache.init_load_back(
            SimpleNamespace(
                req=_promo_req(2048),
                host_hit_length=2048,
                mem_quota=None,
                best_match_node=child.id,
            )
        )
        self.assertEqual(len(indices), 0)
        # The empty match carries the request's own last node (the adder's
        # numel()==0 + needs_host_load_back() check maps it to
        # RESTORE_DENIED regardless).
        self.assertIs(node, None)

    def test_load_back_fail_maps_to_device_quota_wait(self):
        # Zero-new-state pin: the budget rejection feeds the SAME event as
        # every other load-back failure, landing in the SAME WAIT reason
        # (LOAD_BACK_FAIL is a capacity event: WAIT_CAPACITY + WAIT).
        self.assertIs(
            _wait_reason_for(_restore_event.LOAD_BACK_FAIL),
            _restore_wait_reason.DEVICE_QUOTA,
        )
        state, decision = _next_restore(None, _restore_event.LOAD_BACK_FAIL)
        self.assertIs(state, _restore_state.WAIT_CAPACITY)
        self.assertIs(decision, _restore_decision.WAIT)


class PromotionWakeBudgetItemTests(unittest.TestCase):
    """P2-1c §6.1-4 (T11 budget item): the wake predicate's decision table
    and the state-machine gate. A DEVICE_QUOTA waiter with host material
    ready is not woken while the budget cannot hold it; a released budget
    wakes it (next pass re-read); T6 sources with host_hit_length == 0 are
    never blocked by the budget item."""

    def test_device_quota_ready_waiter_blocked_when_budget_full(self):
        self.assertTrue(
            _promotion_wait_blocked(
                _restore_wait_reason.DEVICE_QUOTA, 2048, budget_fits=False
            )
        )
        self.assertFalse(
            _promotion_wait_blocked(
                _restore_wait_reason.DEVICE_QUOTA, 2048, budget_fits=True
            )
        )

    def test_other_reasons_never_blocked(self):
        for reason in (
            _restore_wait_reason.PREFETCH_BUDGET,
            _restore_wait_reason.HOST_ALLOC,
            _restore_wait_reason.FRONTIER,
            _restore_wait_reason.REVALIDATE,
        ):
            self.assertFalse(
                _promotion_wait_blocked(reason, 2048, budget_fits=False)
            )

    def test_t6_source_without_material_never_blocked(self):
        # host_hit_length == 0: the next step is the unrestricted L3->H
        # prefetch, not the promotion.
        self.assertFalse(
            _promotion_wait_blocked(
                _restore_wait_reason.DEVICE_QUOTA, 0, budget_fits=False
            )
        )

    def test_capacity_fits_gate_keeps_waiter_until_budget_released(self):
        # The per-pass T11 re-read: with the budget blocked the predicate
        # reports not-fits, so CAPACITY_FITS does not fire and the request
        # stays in WAIT; after the reservation release the same event wakes
        # it into RESTORING (RETRY_PREFETCH).
        state, decision = _next_restore(
            _restore_state.WAIT_CAPACITY,
            _restore_event.CAPACITY_FITS,
            capacity_fits=False,
        )
        self.assertIs(state, _restore_state.WAIT_CAPACITY)
        self.assertIs(decision, _restore_decision.NONE)
        state, decision = _next_restore(
            _restore_state.WAIT_CAPACITY,
            _restore_event.CAPACITY_FITS,
            capacity_fits=True,
        )
        self.assertIs(state, _restore_state.RESTORING)
        self.assertIs(decision, _restore_decision.RETRY_PREFETCH)


class PromotionSerializationIntegrationTests(unittest.TestCase):
    """P2-1c §6.1-5: the 16K serialization on a 32K pool, driven through
    the real load_back / loading_check. A in flight -> B is rejected at the
    entry gate; A acked but its chain still locked by the running batch ->
    B still rejected (32K > 30720); A's chain lock released -> B passes.
    Also pins the double-count verdict: after A's commit the reservation
    counter is 0 while the derived locked term covers A -- the same tokens
    are never counted twice."""

    def test_two_16k_promotions_serialize(self):
        cache = _make_loadback_cache(size_full=32768)
        tree = cache.tree_core
        a = _attach_host_chain(tree, 16384)
        b = _attach_host_chain(tree, 16384, key_offset=16384)
        req_a = _promo_req(16384, rid="A")
        req_b = _promo_req(16384, rid="B")
        # A in flight (pre-ack): the entry gate rejects B (locked 16K after
        # the transfer + reserved 0 + new 16K == 32K > 30720).
        self.assertTrue(cache.load_back(a.id, req=req_a))
        self.assertEqual(cache.inflight_promotion_reserved, 0)  # transferred
        self.assertEqual(cache._device_locked_tokens(), 16384)
        self.assertFalse(cache.load_back(b.id, req=req_b))
        self.assertEqual(cache._promotion_denied_count, 1)
        # A acked; the running batch keeps A's chain locked, so B is still
        # rejected (16K locked + 16K new == 32K > 30720).
        cache.cache_controller.ack_load_queue.append(_FakeAck([a.id]))
        cache.loading_check(finish_count=1)
        cache.inc_lock_ref(a.id)  # the batch's chain lock on the loaded span
        self.assertEqual(cache._device_locked_tokens(), 16384)
        self.assertFalse(cache.load_back(b.id, req=req_b))
        self.assertEqual(cache._promotion_denied_count, 2)
        # A's chain lock released (batch finished): B passes.
        cache.dec_lock_ref(a.id)
        self.assertEqual(cache._device_locked_tokens(), 0)
        self.assertTrue(cache.load_back(b.id, req=req_b))
        cache.cache_controller.ack_load_queue.append(_FakeAck([b.id]))
        cache.loading_check(finish_count=1)
        self.assertEqual(cache.inflight_promotion_reserved, 0)
        self.assertEqual(cache._promotion_inflight_peak, 16384)
        cache.sanity_check()

    def test_small_promotion_passes_while_16k_in_flight(self):
        # Expert ①: the transfer keeps a small promotion flowing during A's
        # DMA window (18K <= 30720) instead of rejecting it until the ack.
        cache = _make_loadback_cache(size_full=32768)
        tree = cache.tree_core
        a = _attach_host_chain(tree, 16384)
        s = _attach_host_chain(tree, 2048, key_offset=16384)
        self.assertTrue(cache.load_back(a.id, req=_promo_req(16384, rid="A")))
        self.assertTrue(cache.load_back(s.id, req=_promo_req(2048, rid="S")))
        cache.cache_controller.ack_load_queue.append(_FakeAck([s.id]))
        cache.cache_controller.ack_load_queue.append(_FakeAck([a.id]))
        cache.loading_check(finish_count=2)
        self.assertEqual(cache.inflight_promotion_reserved, 0)
        self.assertEqual(cache.ongoing_load_back, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
