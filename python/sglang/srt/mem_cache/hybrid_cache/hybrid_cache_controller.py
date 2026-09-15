from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import replace
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any, Callable, List, Optional

import torch

from sglang.srt.managers.cache_controller import (
    CacheOperation,
)
from sglang.srt.managers.cache_controller import (
    HiCacheController as BaseHiCacheController,
)
from sglang.srt.managers.cache_controller import (
    LayerDoneCounter,
    PrefetchAck,
)
from sglang.srt.managers.cache_controller import (
    StorageOperation as BaseStorageOperation,
)
from sglang.srt.mem_cache.hicache_storage import (
    HiCacheStorageExtraInfo,
    PoolHitPolicy,
    PoolName,
    PoolTransfer,
    PoolTransferResult,
    count_pool_hits,
)
from sglang.srt.mem_cache.l2_transfer import L2Transfer
from sglang.srt.mem_cache.pool_host import HostPoolGroup, PoolEntry
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost
from sglang.srt.mem_cache.trace_context import (
    attach_trace_context,
    durable_trace_enabled,
    INERT_RELEASE_TOKEN,
    ordered_key_set_digest,
    remember_slot_context,
)
from sglang.srt.mem_cache.telemetry_context import next_event_id, producer_context
from sglang.srt.mem_cache.p2a_timing_probe import begin_storage_query_probe

if TYPE_CHECKING:
    from sglang.srt.mem_cache.allocator import BaseTokenToKVPoolAllocator

logger = logging.getLogger(__name__)

_T38C_DURABLE_SEQ = {}
_T38C_DURABLE_SEQ_LOCK = threading.Lock()
_ACTIVE_PRODUCER_CONTEXT = None

# T38C-PROBE (L3 read-chain observation; log-only. Appends JSON lines to
# /tmp/t38c-probe.log only when /tmp/t38c-on exists; zero numeric-path change;
# removed after experiment)
def _t38c_log(rec):
    try:
        import json as _json
        import time as _time
        import os as _os
        if not _os.path.exists("/tmp/t38c-on"):
            return
        rec["ts"] = round(_time.time(), 3)
        with open("/tmp/t38c-probe.log", "a") as _f:
            _f.write(_json.dumps(rec, default=str) + "\n")
    except Exception:
        pass


def _t38c_durable_log(rec):
    """Marker-gated p0_durable.v2 trace; identities/counters only."""
    try:
        if not os.path.exists("/tmp/t38c-durable-trace"):
            return
        thread_id = threading.get_ident()
        with _T38C_DURABLE_SEQ_LOCK:
            local_seq = _T38C_DURABLE_SEQ.get(thread_id, 0) + 1
            _T38C_DURABLE_SEQ[thread_id] = local_seq
        run_id = os.environ.get("T38C_RUN_ID") or f"pid-{os.getpid()}"
        record = attach_trace_context(dict(rec))
        record.setdefault("schema_version", "p0_durable.v2")
        record.setdefault("run_id", run_id)
        record.setdefault(
            "event_id",
            f"{run_id}:{os.getpid()}:{thread_id}:controller:{local_seq}",
        )
        # Never overwrite the existing p0_durable run_id/process_id fields:
        # the non-forgeable producer identity is a nested record.
        record.setdefault(
            "producer",
            globals().get("_ACTIVE_PRODUCER_CONTEXT")
            or producer_context(component="storage"),
        )
        record["event_id"] = record.get("event_id") or next_event_id("durable")
        record.setdefault("lifecycle_key", record.get("operation_id"))
        record.setdefault("wait_id", None)
        record.setdefault("wake_event_id", None)
        record.setdefault("process_id", os.getpid())
        record.setdefault("rank", os.environ.get("RANK"))
        record.setdefault("thread_id", thread_id)
        record.setdefault("local_seq", local_seq)
        record.setdefault("operation", record.get("operation_id"))
        record.setdefault("attempt", record.get("attempt_id"))
        for field in (
            "operation_id",
            "attempt_id",
            "node_id",
            "anchor_id",
            "pool",
            "tier",
            "final_kv_hash",
            "storage_key",
            "mamba_key",
            "extent_id",
            "extent_generation",
            "old_generation",
            "new_generation",
            "slot_digest",
            "requested_pages",
            "succeeded_pages",
            "reason",
            "predecessor_event_id",
            "evidence_ref",
        ):
            record.setdefault(field, None)
        record.setdefault("result", None)
        record["ts_wall_ns"] = time.time_ns()
        record["ts_mono_ns"] = time.monotonic_ns()
        record["trace"] = "p0_durable"
        record["ts_ms"] = int(time.time() * 1000)
        with open("/tmp/t38c-probe.log", "a") as _f:
            _f.write(json.dumps(record, default=str) + "\n")
        return record["event_id"]
    except Exception:
        pass


def _t38c_slot_digest(pool, values) -> str | None:
    if not os.path.exists("/tmp/t38c-durable-trace"):
        return None
    import hashlib

    digest = hashlib.sha256()
    pool_name = getattr(pool, "value", pool)
    for value in values:
        try:
            tensor = value.detach()
            shape = tuple(int(dim) for dim in tensor.shape)
            indices = tensor.reshape(-1).to(device="cpu", dtype=torch.int64)
            raw = indices.contiguous().numpy().tobytes()
            dtype = str(tensor.dtype)
        except AttributeError:
            shape = (len(value),)
            dtype = type(value).__name__
            raw = bytes(str(tuple(value)), "utf-8")
        digest.update(str(pool_name).encode("utf-8"))
        digest.update(b"\0")
        digest.update(dtype.encode("utf-8"))
        digest.update(b"\0")
        digest.update(repr(shape).encode("utf-8"))
        digest.update(b"\0")
        digest.update(raw)
        digest.update(b"\0")
    return digest.hexdigest()




class StorageOperation(BaseStorageOperation):
    def __init__(
        self,
        host_indices: torch.Tensor,
        token_ids: List[int],
        last_hash: Optional[str] = None,
        hash_value: Optional[List[str]] = None,
        prefix_keys: Optional[List[str]] = None,
        pool_transfers: Optional[list[PoolTransfer]] = None,
        trace_context: Optional[dict] = None,
    ):
        super().__init__(host_indices, token_ids, last_hash, hash_value, prefix_keys)
        self.pool_transfers = pool_transfers
        self.pool_storage_result = PoolTransferResult.empty()
        self.trace_context = dict(trace_context) if trace_context else None


class PrefetchOperation(StorageOperation):
    def __init__(
        self,
        request_id: str,
        token_ids: List[int],
        last_hash: Optional[str] = None,
        prefix_keys: Optional[List[str]] = None,
        pool_transfers: Optional[list[PoolTransfer]] = None,
        trace_context: Optional[dict] = None,
    ):
        self.request_id = request_id
        self._lock = threading.Lock()
        self._terminated_flag = False
        self.storage_hit_count = 0
        self.start_time = time.monotonic()
        self.telemetry_enabled = False
        self.prefetch_issue_mono_ns = None
        self.telemetry_session_generation = None
        self.storage_query_start_mono_ns = None
        self.storage_query_end_mono_ns = None
        super().__init__(
            None,
            token_ids,
            last_hash,
            prefix_keys=prefix_keys,
            pool_transfers=pool_transfers,
            trace_context=trace_context,
        )
        self.pool_transfers_done = not bool(pool_transfers)

    def mark_terminate(self):
        with self._lock:
            self._terminated_flag = True

    def is_terminated(self) -> bool:
        with self._lock:
            return self._terminated_flag


class HybridCacheController(BaseHiCacheController):
    def __init__(
        self,
        token_to_kv_pool_allocator: BaseTokenToKVPoolAllocator,
        mem_pool_host: Any,
        page_size: int,
        tp_group: torch.distributed.ProcessGroup,
        load_cache_event: threading.Event,
        attn_cp_group: Optional[torch.distributed.ProcessGroup] = None,
        attn_tp_group: Optional[torch.distributed.ProcessGroup] = None,
        pp_group: Optional[torch.distributed.ProcessGroup] = None,
        write_policy: str = "write_through_selective",
        io_backend: str = "",
        storage_backend: Optional[str] = None,
        prefetch_threshold: int = 256,
        model_name: Optional[str] = None,
        storage_backend_extra_config: Optional[dict] = None,
        transfer_layer_num: Optional[int] = None,
        enable_storage_metrics: bool = False,
        host_memory_mode: str = "cache",
    ):
        startup_storage_backend = storage_backend
        self.extra_host_mem_release_queues: dict[PoolName, Queue[torch.Tensor]] = {}
        self._t38c_host_mem_release_tokens: Queue = Queue()
        self._t38c_extra_host_mem_release_tokens: dict[PoolName, Queue] = {}
        self._t38c_release_handoff_lock = threading.Lock()
        super().__init__(
            token_to_kv_pool_allocator=token_to_kv_pool_allocator,
            mem_pool_host=mem_pool_host,
            page_size=page_size,
            tp_group=tp_group,
            load_cache_event=load_cache_event,
            attn_cp_group=attn_cp_group,
            attn_tp_group=attn_tp_group,
            pp_group=pp_group,
            write_policy=write_policy,
            io_backend=io_backend,
            storage_backend=None,
            prefetch_threshold=prefetch_threshold,
            model_name=model_name,
            storage_backend_extra_config=storage_backend_extra_config,
            enable_storage_metrics=enable_storage_metrics,
            host_memory_mode=host_memory_mode,
        )
        self._t38c_expected_rank_set = self._t38c_rank_topology()
        # Override layer_num: hybrid models transfer all layers (For example, Linear Model (KV + Mamba)),
        # not just the full attention layers reported by full_kv_pool.
        if transfer_layer_num is not None and transfer_layer_num != self.layer_num:
            self.layer_num = transfer_layer_num
            self.layer_done_counter = LayerDoneCounter(self.layer_num)

        self.storage_host_pool = mem_pool_host.anchor_entry.host_pool
        if startup_storage_backend is not None:
            self.attach_storage_backend(
                storage_backend=startup_storage_backend,
                prefetch_threshold=prefetch_threshold,
                model_name=model_name,
                storage_backend_extra_config=storage_backend_extra_config,
                host_pools=getattr(mem_pool_host, "entries", None),
            )

    def _start_storage_threads(self):
        super()._start_storage_threads()
        self._init_extra_host_mem_release_queues()

    def attach_storage_backend(
        self,
        storage_backend: str,
        prefetch_threshold: int = 256,
        model_name: Optional[str] = None,
        storage_backend_extra_config: Optional[dict] = None,
        host_pools: Optional[list[PoolEntry]] = None,
    ):
        super().attach_storage_backend(
            storage_backend=storage_backend,
            prefetch_threshold=prefetch_threshold,
            model_name=model_name,
            storage_backend_extra_config=storage_backend_extra_config,
        )

        for entry in host_pools or []:
            self.storage_backend.register_mem_host_pool_v2(entry.host_pool, entry.name)

    def register_host_pool_entry(self, entry: PoolEntry) -> None:
        if not isinstance(self.mem_pool_host, HostPoolGroup):
            raise TypeError("Dynamic HiCache sidecars require HostPoolGroup.")
        self.mem_pool_host.add_entry(entry)
        if not entry.is_primary_index_anchor:
            self.extra_host_mem_release_queues.setdefault(entry.name, Queue())
            self._t38c_extra_host_mem_release_tokens.setdefault(entry.name, Queue())
        if self.enable_storage and self.storage_backend is not None:
            self.storage_backend.register_mem_host_pool_v2(entry.host_pool, entry.name)

    @staticmethod
    def parse_storage_backend_extra_config(
        storage_backend_extra_config: Optional[str],
    ) -> tuple[dict, int, float, float, bool]:
        extra_config = {}
        if storage_backend_extra_config:
            if storage_backend_extra_config.startswith("@"):
                path = storage_backend_extra_config[1:]
                ext = os.path.splitext(path)[1].lower()
                with open(path, "rb" if ext == ".toml" else "r") as f:
                    if ext == ".json":
                        extra_config = json.load(f)
                    elif ext == ".toml":
                        import tomllib

                        extra_config = tomllib.load(f)
                    elif ext in (".yaml", ".yml"):
                        import yaml

                        extra_config = yaml.safe_load(f)
                    else:
                        raise ValueError(
                            f"Unsupported config file {path} (config format: {ext})"
                        )
            else:
                extra_config = json.loads(storage_backend_extra_config)

        prefetch_threshold = extra_config.pop("prefetch_threshold", 256)
        prefetch_timeout_base = extra_config.pop("prefetch_timeout_base", 1)
        prefetch_timeout_per_ki_token = extra_config.pop(
            "prefetch_timeout_per_ki_token", 0.25
        )
        hicache_storage_pass_prefix_keys = extra_config.pop(
            "hicache_storage_pass_prefix_keys", False
        )

        if not isinstance(prefetch_threshold, int):
            raise ValueError(
                f"prefetch_threshold must be int, got {type(prefetch_threshold).__name__}"
            )
        if not isinstance(prefetch_timeout_base, (int, float)):
            raise ValueError(
                f"prefetch_timeout_base must be number, got {type(prefetch_timeout_base).__name__}"
            )
        if not isinstance(prefetch_timeout_per_ki_token, (int, float)):
            raise ValueError(
                "prefetch_timeout_per_ki_token must be number, got "
                f"{type(prefetch_timeout_per_ki_token).__name__}"
            )
        if not isinstance(hicache_storage_pass_prefix_keys, bool):
            raise ValueError(
                "hicache_storage_pass_prefix_keys must be bool, got "
                f"{type(hicache_storage_pass_prefix_keys).__name__}"
            )

        return (
            extra_config,
            prefetch_threshold,
            float(prefetch_timeout_base),
            float(prefetch_timeout_per_ki_token),
            hicache_storage_pass_prefix_keys,
        )

    def clear_storage_backend(self) -> bool:
        if not self.enable_storage:
            logger.warning("Hierarchical cache storage backend is not enabled.")
            return False
        if not hasattr(self.storage_backend, "clear"):
            logger.warning(
                "Storage backend %s does not support clear operation.",
                type(self.storage_backend).__name__,
            )
            return False
        self.storage_backend.clear()
        return True

    def _init_extra_host_mem_release_queues(self) -> None:
        self.extra_host_mem_release_queues = {}
        self._t38c_extra_host_mem_release_tokens = {}
        entries = getattr(self.mem_pool_host, "entries", None) or []
        anchor_entry = getattr(self.mem_pool_host, "anchor_entry", None)
        for entry in entries:
            if entry is anchor_entry or entry.is_primary_index_anchor:
                continue
            self.extra_host_mem_release_queues[entry.name] = Queue()
            self._t38c_extra_host_mem_release_tokens[entry.name] = Queue()

    def _append_host_mem_release_pages(
        self,
        release_queue: Queue,
        host_indices: torch.Tensor,
        page_size: int,
        pool: PoolName = PoolName.KV,
        trace_context: Optional[dict] = None,
    ) -> None:
        if host_indices.numel() == 0:
            return
        pool_label = getattr(pool, "value", pool)
        token_queue = (
            self._t38c_host_mem_release_tokens
            if pool_label == PoolName.KV.value
            else self._t38c_extra_host_mem_release_tokens.setdefault(pool, Queue())
        )
        for page in host_indices.split(page_size):
            with self._t38c_release_handoff_lock:
                release_queue.put(page)
                token = INERT_RELEASE_TOKEN
                if durable_trace_enabled():
                    digest = _t38c_slot_digest(pool, [page])
                    registered_token = remember_slot_context(
                        getattr(pool, "value", pool), "host", digest, trace_context
                    )
                    if registered_token is not None:
                        token = registered_token
                    # The real page and its exact trace token are published
                    # while the controller-owned handoff lock is held.
                token_queue.put(token)
            _t38c_durable_log(
                {
                    "evt": "residency_release_enqueued",
                    "trace_context": trace_context,
                    "pool": getattr(pool, "value", pool),
                    "tier": "host",
                    "slot_count": int(page.numel()),
                    "slot_digest": _t38c_slot_digest(pool, [page]),
                    "result": "enqueued",
                    "reason": "queued_host_release",
                }
            )

    def append_host_mem_release(
        self,
        host_indices: Optional[torch.Tensor] = None,
        extra_pools: Optional[list[PoolTransfer]] = None,
        trace_context: Optional[dict] = None,
    ):
        if trace_context is None:
            trace_context = next(
                (
                    getattr(transfer, "_t38c_trace_context", None)
                    for transfer in extra_pools or []
                    if getattr(transfer, "_t38c_trace_context", None) is not None
                ),
                None,
            )
        trace_context = dict(trace_context) if trace_context else None
        if host_indices is not None:
            self._append_host_mem_release_pages(
                self.host_mem_release_queue,
                host_indices,
                self.mem_pool_host.page_size,
                PoolName.KV,
                trace_context,
            )
        for transfer in extra_pools or []:
            if transfer.host_indices is None or transfer.host_indices.numel() == 0:
                continue
            entry = self.mem_pool_host.entry_map.get(transfer.name)
            if (
                entry is None
                or entry.is_primary_index_anchor
                or transfer.indices_from_pool is not None
            ):
                continue
            release_queue = self.extra_host_mem_release_queues.get(transfer.name)
            if release_queue is None:
                continue
            self._append_host_mem_release_pages(
                release_queue,
                transfer.host_indices,
                entry.host_pool.page_size,
                transfer.name,
                getattr(transfer, "_t38c_trace_context", trace_context),
            )

    def _t38c_pop_host_mem_release_token(self, pool) -> Optional[tuple]:
        token_queue = self._t38c_token_queue(pool)
        if token_queue is None:
            return None
        with self._t38c_release_handoff_lock:
            if token_queue.empty():
                return None
            return token_queue.get()

    def _t38c_token_queue(self, pool) -> Optional[Queue]:
        if pool == PoolName.KV or getattr(pool, "value", pool) == PoolName.KV.value:
            return self._t38c_host_mem_release_tokens
        return self._t38c_extra_host_mem_release_tokens.get(pool) or (
            self._t38c_extra_host_mem_release_tokens.get(getattr(pool, "value", pool))
        )

    def _t38c_pop_host_mem_release_pair(self, release_queue: Queue, pool):
        """Pop a release page and its exact token as one trace-only handoff."""
        token_queue = self._t38c_token_queue(pool)
        if token_queue is None:
            return None
        with self._t38c_release_handoff_lock:
            # A page without metadata is never completed by digest. Leave it
            # queued until its producer has published the paired metadata.
            if release_queue.empty() or token_queue.empty():
                return None
            return release_queue.get(), token_queue.get()

    def _t38c_rank_topology(self) -> list[str]:
        """Capture the authoritative TP rank set from initialized state."""
        if torch.distributed.is_available() and torch.distributed.is_initialized():
            world_size = torch.distributed.get_world_size(group=self.tp_group)
            if hasattr(torch.distributed, "get_process_group_ranks"):
                ranks = torch.distributed.get_process_group_ranks(self.tp_group)
            else:
                ranks = list(range(world_size))
            if world_size == 1:
                ranks = [torch.distributed.get_rank(group=self.tp_group)]
            return sorted(str(rank) for rank in ranks)
        return [str(os.environ.get("RANK", "0"))]

    def _t38c_retire_host_mem_release_tokens(self, session_id) -> None:
        """Retire queued tokens without changing the real release FIFO."""
        session_id = str(session_id)
        with self._t38c_release_handoff_lock:
            queues = [self._t38c_host_mem_release_tokens]
            queues.extend(self._t38c_extra_host_mem_release_tokens.values())
            for token_queue in queues:
                with token_queue.mutex:
                    token_queue.queue = deque(
                        INERT_RELEASE_TOKEN
                        if token is not None
                        and len(token) > 1
                        and token[1] == session_id
                        else token
                        for token in token_queue.queue
                    )

    def _t38c_reset_release_handoff(self) -> None:
        with self._t38c_release_handoff_lock:
            queues = [self._t38c_host_mem_release_tokens]
            queues.extend(self._t38c_extra_host_mem_release_tokens.values())
            for token_queue in queues:
                with token_queue.mutex:
                    token_queue.queue.clear()

    def reset(self):
        super().reset()
        self._t38c_reset_release_handoff()
        if self.enable_storage:
            self.host_mem_release_queue.queue.clear()
            for release_queue in self.extra_host_mem_release_queues.values():
                release_queue.queue.clear()
            self.prefetch_tokens_occupied = 0

    def write(
        self,
        device_indices: torch.Tensor,
        priority: Optional[int] = None,
        node_id: int = -1,
        extra_pools: Optional[list[PoolTransfer]] = None,
    ) -> Optional[torch.Tensor]:
        # D->H write-back staging: may use the P3 write-back reserve.
        alloc = getattr(self.mem_pool_host, "alloc_writeback", self.mem_pool_host.alloc)
        host_indices = alloc(len(device_indices))
        if host_indices is None:
            return None
        pool_transfers = self.mem_pool_host.resolve_host_transfers(
            extra_pools,
            primary_device_indices=device_indices,
            primary_host_indices=host_indices,
            writeback=True,
        )
        if pool_transfers is None and extra_pools:
            self.mem_pool_host.free(host_indices)
            callback = getattr(self, "host_allocability_change_fn", None)
            if callback is not None:
                callback(PoolName.KV.value, "direct_free", len(host_indices))
            return None

        self.write_queue.append(
            CacheOperation(
                host_indices,
                device_indices,
                node_id,
                priority,
                pool_transfers=pool_transfers or None,
            )
        )
        self.start_writing()
        return host_indices

    def _move_op_indices(
        self, op: CacheOperation
    ) -> tuple[torch.Tensor, torch.Tensor, Optional[list[PoolTransfer]]]:
        return self.move_hybrid_indices(op)

    def _move_write_operation(
        self, op: CacheOperation
    ) -> tuple[torch.Tensor, torch.Tensor, Optional[list[PoolTransfer]]]:
        host_group = self.mem_pool_host
        if self.io_backend != "kernel" or host_group.layout != "page_first":
            return self.move_hybrid_indices(op)
        if not getattr(host_group, "supports_per_pool_backup_indices", False):
            if not getattr(host_group, "can_use_write_back_jit", False):
                return self.move_hybrid_indices(op)
            return op.host_indices, op.device_indices, op.pool_transfers

        def move_for_pool(host_pool, host_indices, device_indices):
            if getattr(host_pool, "can_use_write_back_jit", False):
                if host_indices.is_cuda:
                    host_indices = host_indices.cpu()
                return host_indices, device_indices
            return self.move_indices(host_indices, device_indices)

        host_indices, device_indices = move_for_pool(
            host_group.anchor_entry.host_pool,
            op.host_indices,
            op.device_indices,
        )
        pool_transfers = []
        for transfer in op.pool_transfers or []:
            entry = host_group.entry_map[transfer.name]
            transfer_host_indices, transfer_device_indices = move_for_pool(
                entry.host_pool,
                transfer.host_indices,
                transfer.device_indices,
            )
            pool_transfers.append(
                replace(
                    transfer,
                    host_indices=transfer_host_indices,
                    device_indices=transfer_device_indices,
                )
            )
        return host_indices, device_indices, pool_transfers or None

    def _l2_transfers(
        self,
        host_indices: torch.Tensor,
        device_indices: torch.Tensor,
        pool_transfers: Optional[list[PoolTransfer]] = None,
    ) -> list[L2Transfer]:
        anchor = self.mem_pool_host.anchor_entry
        transfers = []
        if host_indices.numel() > 0:
            transfers.append(
                L2Transfer(
                    host_pool=anchor.host_pool,
                    device_pool=anchor.device_pool,
                    host_indices=host_indices,
                    device_indices=device_indices,
                    layer_mapper=anchor.layer_mapper,
                )
            )
        for pool_transfer in pool_transfers or []:
            if (
                pool_transfer.host_indices is None
                or pool_transfer.device_indices is None
            ):
                raise ValueError(f"Unresolved L2 transfer for {pool_transfer.name}.")
            entry = self.mem_pool_host.entry_map[pool_transfer.name]
            transfers.append(
                L2Transfer(
                    host_pool=entry.host_pool,
                    device_pool=entry.device_pool,
                    host_indices=pool_transfer.host_indices,
                    device_indices=pool_transfer.device_indices,
                    layer_mapper=entry.layer_mapper,
                )
            )
        return transfers

    def _l2_load_transfers(
        self,
        host_indices: torch.Tensor,
        device_indices: torch.Tensor,
        pool_transfers: Optional[list[PoolTransfer]] = None,
    ) -> list[L2Transfer]:
        transfers = self._l2_transfers(host_indices, device_indices, pool_transfers)
        transfers_by_entry = {
            (id(t.host_pool), id(t.device_pool)): t for t in transfers
        }
        for entry in self.mem_pool_host.entry_map.values():
            target_transfer = transfers_by_entry.get(
                (id(entry.host_pool), id(entry.device_pool))
            )
            if target_transfer is None or target_transfer.layer_mapper is None:
                continue
            for depth, draft_device_pool in enumerate(entry.packed_draft_device_pools):
                draft_host_layer = target_transfer.layer_mapper(self.layer_num + depth)
                if draft_host_layer is None:
                    continue

                def draft_layer_mapper(
                    layer_id: int,
                    *,
                    expected_layer_id: int = depth,
                    host_layer_id: int = draft_host_layer,
                ) -> Optional[int]:
                    if layer_id == expected_layer_id:
                        return host_layer_id
                    return None

                transfers.append(
                    L2Transfer(
                        host_pool=target_transfer.host_pool,
                        device_pool=draft_device_pool,
                        host_indices=target_transfer.host_indices,
                        device_indices=target_transfer.device_indices,
                        layer_mapper=draft_layer_mapper,
                        is_draft=True,
                    )
                )
        return transfers

    def _num_tokens_by_pool(self, op: CacheOperation) -> dict[str, int]:
        """Per-pool token counts for a merged transfer op (anchor + extra
        pools), shared by D->H write and H->D load acks; sidecar transfers
        reusing another pool's indices are excluded."""
        counts = {self.mem_pool_host.anchor_entry.name.value: len(op.device_indices)}
        for transfer in op.pool_transfers or []:
            if transfer.indices_from_pool is not None or transfer.host_indices is None:
                continue
            name = transfer.name.value
            counts[name] = counts.get(name, 0) + len(transfer.host_indices)
        return counts

    def _transfer_num_bytes(self, op: CacheOperation) -> int:
        """Total bytes moved by a merged transfer op across all pools.

        Sidecar transfers riding another pool's indices are included here but
        excluded from the per-pool token counts.
        """
        kv_tokens = len(op.device_indices)
        num_bytes = kv_tokens * self.mem_pool_host.anchor_entry.host_pool.size_per_token
        # Slot counts of the pools sidecars can ride on.
        source_len = {self.mem_pool_host.anchor_entry.name: kv_tokens}
        for t in op.pool_transfers or []:
            if t.indices_from_pool is None and t.host_indices is not None:
                source_len[t.name] = len(t.host_indices)
        for t in op.pool_transfers or []:
            entry = self.mem_pool_host.entry_map.get(t.name)
            if entry is None:
                continue
            if t.indices_from_pool is not None:
                num_slots = source_len.get(t.indices_from_pool, 0)
            else:
                num_slots = len(t.host_indices) if t.host_indices is not None else 0
            num_bytes += num_slots * entry.host_pool.size_per_token
        return num_bytes

    def load(
        self,
        host_indices: torch.Tensor,
        priority: Optional[int] = None,
        node_id: int = -1,
        extra_pools: Optional[list[PoolTransfer]] = None,
    ) -> Optional[torch.Tensor]:
        need_load_kv = host_indices.numel() > 0

        full_allocator = getattr(
            self.mem_pool_device_allocator,
            "full_attn_allocator",
            self.mem_pool_device_allocator,
        )
        if not need_load_kv:
            device_indices = torch.empty((0,), dtype=torch.int64, device=self.device)
        else:
            device_indices = full_allocator.alloc(len(host_indices))
            if device_indices is None:
                return None

        pool_transfers = self._resolve_device_transfers(
            extra_pools,
            kv_device_indices=device_indices,
            kv_host_indices=host_indices,
        )
        if pool_transfers is None and extra_pools:
            if need_load_kv:
                full_allocator.free(device_indices)
            return None

        self.load_queue.append(
            CacheOperation(
                host_indices,
                device_indices,
                node_id,
                priority,
                pool_transfers=pool_transfers or None,
            )
        )
        return device_indices

    def prefetch(
        self,
        request_id: str,
        new_input_tokens: List[int],
        last_hash: Optional[str] = None,
        prefix_keys: Optional[List[str]] = None,
        extra_pools: Optional[list[PoolTransfer]] = None,
        trace_context: Optional[dict] = None,
        telemetry_enabled: bool = False,
        session_generation: Optional[int] = None,
        prefetch_attempt_id: Optional[str] = None,
        matched_prefix_l3_proof: Optional[dict] = None,
        matched_prefix_tokens: Optional[int] = None,
    ) -> PrefetchOperation:
        operation = PrefetchOperation(
            request_id,
            new_input_tokens,
            last_hash,
            prefix_keys=prefix_keys,
            pool_transfers=extra_pools,
            trace_context=trace_context,
        )
        operation.telemetry_enabled = telemetry_enabled
        operation.telemetry_session_generation = (
            session_generation if telemetry_enabled else None
        )
        operation.prefetch_attempt_id = prefetch_attempt_id
        operation.matched_prefix_l3_proof = matched_prefix_l3_proof
        operation.stats_matched_prefix_tokens = matched_prefix_tokens
        for transfer in extra_pools or []:
            transfer._t38c_trace_context = operation.trace_context
        if telemetry_enabled:
            # This is the controller-owned acceptance/publication seam.  Keep
            # the value immutable after this point: workers only observe it.
            operation.prefetch_issue_mono_ns = time.monotonic_ns()
        self.prefetch_queue.put(operation)
        return operation

    def write_storage(
        self,
        host_indices: torch.Tensor,
        token_ids: List[int],
        hash_value: Optional[List[str]] = None,
        prefix_keys: Optional[List[str]] = None,
        extra_pools: Optional[list[PoolTransfer]] = None,
        node_id: Optional[Any] = None,
        trace_context: Optional[dict] = None,
    ) -> int:
        operation = StorageOperation(
            host_indices,
            token_ids,
            hash_value=hash_value,
            prefix_keys=prefix_keys,
            pool_transfers=extra_pools,
            trace_context=trace_context,
        )
        operation.node_id = node_id
        operation.trace_id = f"storage-{operation.id}"
        operation._t38c_expected_rank_set = list(self._t38c_expected_rank_set)
        for transfer in extra_pools or []:
            transfer._t38c_operation_id = operation.id
            transfer._t38c_attempt_id = operation.trace_id
            transfer._t38c_node_id = str(node_id) if node_id is not None else ""
            transfer._t38c_final_kv_hash = (
                hash_value[-1] if hash_value else ""
            )
            if transfer.name == PoolName.MAMBA:
                transfer._t38c_expected_rank_set = list(
                    self._t38c_expected_rank_set
                )
            transfer._t38c_trace_context = operation.trace_context
        self.backup_queue.put(operation)
        return operation.id

    def _storage_hit_query(self, operation) -> tuple[list[str], int]:
        if getattr(operation, "telemetry_enabled", False):
            operation.storage_query_start_mono_ns = time.monotonic_ns()
        _p2a_probe = begin_storage_query_probe()
        hash_value = self.get_hash_str(
            operation.token_ids, operation.last_hash, page_size=self.page_size
        )
        operation.all_hash_values = hash_value

        extra_info = HiCacheStorageExtraInfo(
            prefix_keys=operation.prefix_keys.copy() if operation.prefix_keys else None,
            extra_info={
                "operation_id": operation.id,
                "attempt_id": getattr(operation, "trace_id", f"prefetch-{operation.id}"),
                "node_id": getattr(operation, "node_id", None),
                "final_kv_hash": hash_value[-1] if hash_value else "",
                "trace_context": getattr(operation, "trace_context", None),
            },
        )
        if operation.pool_transfers:
            # Establish the KV frontier before asking a trailing sidecar for
            # its boundary.  The query can contain newly appended turn
            # tokens that are not in storage; those tokens must not become
            # the sidecar's trailing window and reject an otherwise complete
            # historical KV prefix.
            if _p2a_probe is not None:
                _p2a_backend_t0 = time.monotonic_ns()
            kv_hit_pages = self.storage_backend.batch_exists(hash_value, extra_info)
            if _p2a_probe is not None:
                _p2a_probe.note_backend_lookup(_p2a_backend_t0)
            kv_hit_pages = max(0, min(kv_hit_pages, len(hash_value)))
            query_hashes = hash_value[:kv_hit_pages]
            query_transfers = self._align_storage_query_transfers(
                operation.pool_transfers, hash_value, kv_hit_pages
            )
            for transfer in query_transfers:
                transfer._t38c_operation_id = operation.id
                transfer._t38c_attempt_id = getattr(
                    operation, "trace_id", f"prefetch-{operation.id}"
                )
                transfer._t38c_node_id = str(
                    getattr(operation, "node_id", "") or ""
                )
                transfer._t38c_final_kv_hash = (
                    hash_value[-1] if hash_value else ""
                )
                transfer._t38c_trace_context = getattr(
                    operation, "trace_context", None
                )
            if _p2a_probe is not None:
                _p2a_backend_t0 = time.monotonic_ns()
            hit_result = self.storage_backend.batch_exists_v2(
                query_hashes, query_transfers, extra_info
            )
            if _p2a_probe is not None:
                _p2a_probe.note_backend_lookup(_p2a_backend_t0)
        else:
            if _p2a_probe is not None:
                _p2a_backend_t0 = time.monotonic_ns()
            kv_hit_count = self.storage_backend.batch_exists(hash_value, extra_info)
            if _p2a_probe is not None:
                _p2a_probe.note_backend_lookup(_p2a_backend_t0)
            hit_result = PoolTransferResult(
                kv_hit_pages=kv_hit_count, extra_pool_hit_pages={}
            )

        kv_hit_pages = hit_result.kv_hit_pages
        if getattr(operation, "telemetry_enabled", False):
            operation.storage_query_end_mono_ns = time.monotonic_ns()
        operation.pool_storage_result.update_kv_hit_pages(kv_hit_pages)
        try:
            _t38c_log({"evt": "pc_storage_query",
                       "rid": operation.request_id,
                       "keys": [k for k in hash_value[:8]],
                       "query_suffix_len": len(hash_value),
                       "kv_hit_pages": int(kv_hit_pages),
                       "storage_hit_count": int(kv_hit_pages) * self.page_size,
                       "sidecar_hits": {getattr(k, "value", k): int(v)
                                         for k, v in hit_result.extra_pool_hit_pages.items()}})
        except Exception:
            pass

        if _p2a_probe is not None:
            _p2a_probe.emit(
                operation,
                query_len=len(hash_value),
                kv_hit_pages=int(kv_hit_pages),
            )

        return (
            hash_value[:kv_hit_pages],
            kv_hit_pages * self.page_size,
        )

    def _trailing_transfer_pages(self, transfer: PoolTransfer) -> int:
        """Return the sidecar window size, independent of query length.

        A prefetch transfer's host buffer describes the sidecar pages that
        will actually be restored.  Prefer that size over ``transfer.keys``:
        the latter may still describe the full request, including tokens past
        the KV hit frontier.  Keep the key-count fallback for storage query
        callers that do not carry host staging indices.
        """
        host_indices = transfer.host_indices
        if host_indices is not None:
            try:
                slots = int(host_indices.numel())
            except AttributeError:
                slots = len(host_indices)
            entry = getattr(self.mem_pool_host, "entry_map", {}).get(transfer.name)
            page_size = (
                getattr(entry.host_pool, "page_size", self.page_size)
                if entry is not None
                else self.page_size
            ) or 1
            if slots > 0 and slots % page_size == 0:
                return max(1, slots // page_size)
        return max(1, len(transfer.keys) if transfer.keys else 1)

    def _align_storage_query_transfers(
        self,
        transfers: list[PoolTransfer],
        all_hashes: list[str],
        kv_hit_pages: int,
    ) -> list[PoolTransfer]:
        """Align trailing sidecar keys to the actual KV hit frontier."""
        aligned = []
        for transfer in transfers:
            if transfer.hit_policy != PoolHitPolicy.TRAILING_PAGES:
                aligned.append(transfer)
                continue
            trailing = self._trailing_transfer_pages(transfer)
            keys = all_hashes[max(0, kv_hit_pages - trailing) : kv_hit_pages]
            aligned.append(replace(transfer, keys=keys))
        return aligned

    def move_hybrid_indices(
        self, operation: CacheOperation
    ) -> tuple[torch.Tensor, torch.Tensor, Optional[list[PoolTransfer]]]:
        host_indices, device_indices = self.move_indices(
            operation.host_indices, operation.device_indices
        )
        resolved_pool_transfers = None
        if operation.pool_transfers:
            resolved_pool_transfers = []
            for transfer in operation.pool_transfers:
                transfer_host_indices, transfer_device_indices = self.move_indices(
                    transfer.host_indices, transfer.device_indices
                )
                # Keep the original PoolTransfer unchanged because tree-owned
                # transfers may still reference radix-tree host state. The
                # controller only needs a normalized execution-time copy.
                resolved_pool_transfers.append(
                    PoolTransfer(
                        name=transfer.name,
                        host_indices=transfer_host_indices,
                        device_indices=transfer_device_indices,
                        keys=transfer.keys,
                        hit_policy=transfer.hit_policy,
                        indices_from_pool=transfer.indices_from_pool,
                    )
                )
        return host_indices, device_indices, resolved_pool_transfers

    def _page_transfer(self, operation: PrefetchOperation) -> int:
        # KV pools and KV-derived pools first — determines actual completed page count
        kv_completed_pages = super()._page_transfer(operation)

        # Read non-KV derived sidecar pool, e.g. SWA, Mamba.
        self._page_transfer_sidecar(operation, kv_completed_pages)
        # Base contract: return the completed KV page count (missing return
        # used to yield None, killing the IO thread's arithmetics — I7).
        return kv_completed_pages

    def _page_transfer_sidecar(
        self, operation: PrefetchOperation, kv_completed_pages: int
    ) -> None:
        if operation.pool_transfers is None:
            return

        # Extra pools only after KV fully completes. If KV terminated early
        # (IO failure, timeout, TP mismatch), skip extra IO entirely to avoid
        # data misalignment.
        pool_hits: dict[str, int] = {}
        if not operation.is_terminated() and kv_completed_pages == len(
            operation.hash_value
        ):
            # KV-derived sidecar pools are handled in CacheController._page_transfer_kv_batch.
            # Only handle non-KV-derived sidecar pools here.
            transfers_nonkv = [
                transfer
                for transfer in operation.pool_transfers
                if transfer.indices_from_pool != PoolName.KV
            ]
            self._sync_trailing_keys(
                transfers_nonkv, operation.hash_value, kv_completed_pages
            )
            self._resolve_sidecar_nonkv_derived_pool_transfers(operation)
            results = self.storage_backend.batch_get_v2(transfers_nonkv)
            pool_hits = count_pool_hits(results)
            try:
                _t38c_log({"evt": "pc_get_v2", "phase": "sidecar",
                           "rid": operation.request_id,
                           "sidecar": [getattr(t.name, "value", t.name) for t in transfers_nonkv],
                           "n_keys": sum(len(t.keys or []) for t in transfers_nonkv),
                           "hit_pages": {getattr(k, "value", k): int(v)
                                         for k, v in pool_hits.items()}})
            except Exception:
                pass
        # Emit PrefetchAck to prefetch_sync_queue, even the operation has been canceled by the
        # scheduler thread.  The prefetch sync thread expects the same number of PrefetchAck objects
        # to perform all_reduce.
        self.prefetch_sync_queue.put(
            PrefetchAck(
                rid=operation.request_id,
                operation=operation,
                pool_hits=pool_hits,
            )
        )
        return

    def _page_backup(self, operation):
        # MLA KV is replicated across TP ranks and should still be written only
        # by TP0. Rank-sharded sidecars still need every TP rank.
        backup_transfers = [
            transfer
            for transfer in operation.pool_transfers or []
            if self.should_backup(transfer)
        ]
        has_sidecar = any(bool(transfer.keys) for transfer in backup_transfers)
        has_kv = bool(operation.hash_value) and not self.backup_skip
        group_api = all(
            callable(getattr(self.storage_backend, method, None))
            for method in ("open_group", "commit_group", "abort_group")
        )
        group_id = None
        committed = False
        if group_api and (has_kv or has_sidecar):
            group_id = self.storage_backend.open_group()
            operation.group_id = group_id

        try:
            sidecar_ok = True
            if backup_transfers:
                self._resolve_sidecar_kv_derived_pool_transfers(operation)
                self._resolve_sidecar_nonkv_derived_pool_transfers(operation)
                results = (
                    self.storage_backend.batch_set_v2(
                        backup_transfers, group_id=group_id
                    )
                    if group_id is not None
                    else self.storage_backend.batch_set_v2(backup_transfers)
                )
                operation.pool_storage_result.update_extra_pool_hit_pages(
                    count_pool_hits(results)
                )
                for transfer in backup_transfers:
                    result = results.get(transfer.name)
                    if result is None:
                        result = results.get(transfer.name.value)
                    expected = len(transfer.keys or [])
                    if expected == 0 and transfer.host_indices is not None:
                        expected = int(transfer.host_indices.numel())
                    sidecar_ok = sidecar_ok and (
                        isinstance(result, (list, tuple))
                        and len(result) == expected
                        and all(bool(ok) for ok in result)
                    )
                if not sidecar_ok:
                    return False

            kv_ok = True
            if has_kv:
                previous_context = getattr(
                    self.storage_backend, "_t38c_durable_context", None
                )
                try:
                    self.storage_backend._t38c_durable_context = {
                        **(operation.trace_context or {}),
                        "operation_id": operation.id,
                        "attempt_id": getattr(
                            operation, "trace_id", f"storage-{operation.id}"
                        ),
                        "node_id": str(getattr(operation, "node_id", "") or ""),
                        "final_kv_hash": operation.hash_value[-1]
                        if operation.hash_value
                        else "",
                        "pool": "kv",
                    }
                except Exception:
                    previous_context = None
                try:
                    kv_ok = super()._page_backup(operation)
                finally:
                    try:
                        if previous_context is None:
                            del self.storage_backend._t38c_durable_context
                        else:
                            self.storage_backend._t38c_durable_context = previous_context
                    except Exception:
                        pass
            elif self.backup_skip:
                operation.completed_tokens = (
                    len(operation.hash_value) * self.page_size if has_sidecar else 0
                )

            if not kv_ok:
                return False
            if group_id is not None:
                committed = bool(self.storage_backend.commit_group(group_id))
                return committed
            return sidecar_ok and (not has_kv or kv_ok)
        except Exception:
            return False
        finally:
            if group_id is not None and not committed:
                self.storage_backend.abort_group(group_id)
            operation.group_id = None

    def should_backup(self, transfer: PoolTransfer) -> bool:
        if not self.backup_skip:
            return True

        # Kimi-K3 Mamba/KDA state is TP-sharded even when the primary MLA KV
        # pool is replicated.
        if transfer.name == PoolName.MAMBA:
            return True

        # Mooncake gives MHA draft and draft-SWA objects rank-specific keys.
        # MLA/DeepSeek-V4 draft pools remain TP0-only.
        if self.storage_backend_type == "mooncake" and transfer.name in (
            PoolName.DRAFT,
            PoolName.DRAFT_SWA,
        ):
            entry = self.mem_pool_host.entry_map.get(transfer.name)
            return entry is not None and isinstance(
                entry.host_pool, MHATokenToKVPoolHost
            )

        return False

    def backup_thread_func(self):
        """Back up rank-sharded sidecars on every TP rank.

        The base implementation skips the entire operation on non-zero MLA TP
        ranks. That optimization is valid for replicated MLA KV, but not for
        hybrid rank-sharded pools such as Kimi-K3 Mamba state.
        """
        while not self.storage_stop_event.is_set():
            try:
                operation = self.backup_queue.get(block=True, timeout=1)
                if operation is None:
                    continue
                if not self._page_backup(operation):
                    continue
                transfers = operation.pool_transfers or []
                mamba_transfers = [
                    transfer
                    for transfer in transfers
                    if transfer.name == PoolName.MAMBA
                ]
                mamba_keys = [
                    key
                    for transfer in mamba_transfers
                    for key in (transfer.keys or [])
                ]
                mamba_key_set_digest, mamba_key_count = ordered_key_set_digest(
                    mamba_keys
                )
                mamba_expected_pages = mamba_key_count
                mamba_succeeded_pages = operation.pool_storage_result.extra_pool_hit_pages.get(
                    PoolName.MAMBA,
                    operation.pool_storage_result.extra_pool_hit_pages.get(
                        PoolName.MAMBA.value, 0
                    ),
                )
                expected_rank_set = getattr(
                    operation, "_t38c_expected_rank_set",
                    self._t38c_expected_rank_set,
                )
                if expected_rank_set is None:
                    expected_rank_set = next(
                        (
                            getattr(transfer, "_t38c_expected_rank_set", None)
                            for transfer in mamba_transfers
                            if getattr(transfer, "_t38c_expected_rank_set", None)
                            is not None
                        ),
                        None,
                    )
                expected_rank_set = (
                    sorted(str(rank) for rank in expected_rank_set)
                    if expected_rank_set
                    else list(self._t38c_expected_rank_set)
                )
                observed_ack_rank_set = [
                    str(
                        torch.distributed.get_rank(group=self.tp_group)
                        if torch.distributed.is_available()
                        and torch.distributed.is_initialized()
                        else os.environ.get("RANK", "0")
                    )
                ]
                _t38c_durable_log(
                    {
                        "evt": "backup_ack_enqueue",
                        "trace_context": getattr(
                            operation, "trace_context", None
                        ),
                        "operation_id": operation.id,
                        "attempt_id": getattr(
                            operation, "trace_id", f"storage-{operation.id}"
                        ),
                        "node_id": str(getattr(operation, "node_id", "") or ""),
                        "final_kv_hash": (
                            operation.hash_value[-1]
                            if operation.hash_value
                            else ""
                        ),
                        "kv_transfer": bool(operation.hash_value),
                        "mamba_transfer": any(
                            transfer.name == PoolName.MAMBA for transfer in transfers
                        ),
                        "kv_durable": operation.completed_tokens
                        >= len(operation.hash_value) * self.page_size,
                        "mamba_durable": mamba_key_count > 0
                        and mamba_succeeded_pages == mamba_expected_pages,
                        "mamba_expected_pages": mamba_expected_pages,
                        "mamba_succeeded_pages": mamba_succeeded_pages,
                        "mamba_key_count": mamba_key_count,
                        "mamba_key_set_digest": mamba_key_set_digest,
                        "expected_rank_set": expected_rank_set,
                        "observed_ack_rank_set": observed_ack_rank_set,
                        "observed_ack_rank_count": len(observed_ack_rank_set),
                        "rank_set_unavailable": not expected_rank_set,
                        "operation": operation.id,
                        "attempt": getattr(
                            operation, "trace_id", f"storage-{operation.id}"
                        ),
                        "completed_tokens": int(operation.completed_tokens),
                        "result": "complete"
                        if operation.completed_tokens
                        >= len(operation.hash_value) * self.page_size
                        else "partial",
                    }
                )
                self.ack_backup_queue.put(operation)
            except Empty:
                continue

    def _resolve_sidecar_kv_derived_pool_transfers(self, operation):
        for transfer in operation.pool_transfers:
            if transfer.indices_from_pool == PoolName.KV:
                transfer.host_indices = operation.host_indices
                if transfer.keys is None:
                    transfer.keys = operation.hash_value

    def _resolve_sidecar_nonkv_derived_pool_transfers(self, operation):
        for transfer in operation.pool_transfers:
            if transfer.indices_from_pool is None:
                continue
            if transfer.indices_from_pool != PoolName.KV:
                source = next(
                    (
                        t
                        for t in operation.pool_transfers
                        if t.indices_from_pool is None
                        and t.name == transfer.indices_from_pool
                    ),
                    None,
                )
                if source is None:
                    raise AssertionError(
                        "Storage sidecar derived pool source missing: "
                        f"{transfer.name} from {transfer.indices_from_pool}."
                    )
                transfer.host_indices = source.host_indices
                if transfer.keys is None:
                    transfer.keys = source.keys
            else:
                pass

    def _sync_trailing_keys(
        self,
        pool_transfers: list[PoolTransfer],
        all_hashes: list[str],
        kv_hit_pages: int,
    ) -> None:
        """Re-align trailing-page sidecar keys after KV hit truncation.

        When the storage hit is shorter than the original target prefix, each
        pool transfer's keys must be updated to the last N hashes of the actual
        hit range instead of the last N hashes of the original target range.
        For mamba (N=1) this is just the last hit page hash; for SWA (N>1) it
        is a sliding window of the last N hit pages.
        """
        for transfer in pool_transfers:
            if transfer.hit_policy != PoolHitPolicy.TRAILING_PAGES:
                continue
            trailing_n = len(transfer.keys) if transfer.keys else 1
            transfer.keys = all_hashes[max(0, kv_hit_pages - trailing_n) : kv_hit_pages]
            if transfer.host_indices is None:
                continue
            entry = self.mem_pool_host.entry_map.get(transfer.name)
            pool_page_size = (
                entry.host_pool.page_size if entry is not None else self.page_size
            )
            needed = len(transfer.keys) * pool_page_size
            if transfer.host_indices.numel() > needed:
                # The hit undershot the pre-allocated window buffer. Backends
                # fetch keys zipped against the buffer head, so shrink the
                # transfer to match and release the tail now — otherwise the
                # length mismatch makes batch_get_v2 fetch nothing and the
                # whole window is silently lost downstream.
                self.append_host_mem_release(
                    extra_pools=[
                        PoolTransfer(
                            name=transfer.name,
                            host_indices=transfer.host_indices[needed:],
                        )
                    ]
                )
                transfer.host_indices = transfer.host_indices[:needed]

    def _resolve_device_transfers(
        self,
        extra_pools: Optional[list[PoolTransfer]],
        kv_device_indices: Optional[torch.Tensor] = None,
        kv_host_indices: Optional[torch.Tensor] = None,
    ) -> Optional[list[PoolTransfer]]:
        """Allocate unresolved side-pool device indices atomically."""
        if not extra_pools:
            return None
        newly_allocated: list[tuple[PoolTransfer, Callable, torch.Tensor]] = []
        derived_transfers: list[PoolTransfer] = []

        def rollback_allocated() -> None:
            for prev_pool, prev_free_fn, prev_indices in newly_allocated:
                prev_free_fn(prev_indices)
                prev_pool.device_indices = None

        for pool in extra_pools:
            if pool.indices_from_pool is not None:
                derived_transfers.append(pool)
                continue
            entry = self.mem_pool_host.entry_map.get(pool.name)
            if entry is None:
                continue
            if pool.device_indices is not None or pool.host_indices is None:
                continue
            # device_alloc_fn / device_free_fn override entry.device_pool's
            # methods for pools whose device_pool is a raw KV pool (layout)
            # rather than an allocator (e.g. SWA).
            alloc_fn = entry.device_alloc_fn or entry.device_pool.alloc
            free_fn = entry.device_free_fn or entry.device_pool.free
            evict_fn = entry.device_evict_fn
            size = len(pool.host_indices)
            indices = alloc_fn(size)
            if indices is None and evict_fn:
                evict_fn(size)
                indices = alloc_fn(size)
            if indices is None:
                # Atomic rollback: free everything we successfully allocated.
                rollback_allocated()
                return None
            pool.device_indices = indices
            newly_allocated.append((pool, free_fn, indices))

        # Assign indices to deferred pools from their source.
        for pool in derived_transfers:
            if pool.indices_from_pool == PoolName.KV:
                pool.host_indices = kv_host_indices
                pool.device_indices = kv_device_indices
                continue

            source = next(
                (
                    transfer
                    for transfer in extra_pools
                    if transfer.indices_from_pool is None
                    and transfer.name == pool.indices_from_pool
                ),
                None,
            )
            if source is None:
                rollback_allocated()
                return None
            pool.host_indices = source.host_indices
            pool.device_indices = source.device_indices
        return extra_pools

    def _reduce_prefetch_ack(self, ack: PrefetchAck) -> None:
        # Handle KV-derived pool.
        super()._reduce_prefetch_ack(ack)

        # Handle other sidecar pools, e.g. SWA, Mamba.
        if ack.pool_hits is not None:
            # "for ... in PoolName" ensures the same order across all ranks.
            # On prefetch failure, pool_hits may be empty dict.
            packed = torch.tensor(
                [ack.pool_hits.get(pool.value, 0) for pool in PoolName],
                dtype=torch.int,
            )
            self._all_reduce(
                packed,
                torch.distributed.ReduceOp.MIN,
                self.prefetch_completion_sync_groups,
            )
            for i, pool in enumerate(PoolName):
                ack.pool_hits[pool.value] = packed[i].item()
