from __future__ import annotations

import atexit
import logging
import threading
import time
from dataclasses import replace
from enum import Enum, auto
from queue import Queue
from typing import TYPE_CHECKING, Iterator, NamedTuple, Optional, Sequence, TypeVar

import torch

from sglang.srt.distributed.communication_tags import P2PTag
from sglang.srt.environ import envs
from sglang.srt.managers.cache_controller import CacheOperation
from sglang.srt.managers.scheduler_components.hicache_restore import (
    backup_wait_applies,
    backup_wake_applies,
    promotion_budget_fits,
)
from sglang.srt.mem_cache.base_prefix_cache import (
    BasePrefixCache,
    DecLockRefParams,
    DecLockRefResult,
    EvictParams,
    EvictResult,
    IncLockRefResult,
    InitLoadBackParams,
    InsertParams,
    InsertResult,
    MatchPrefixParams,
    MatchResult,
)
from sglang.srt.mem_cache.buffer_mode.pipeline import (
    BufferModePipeline,
    validate_buffer_only_stack,
)
from sglang.srt.mem_cache.buffer_mode.storage_existence_cache import (
    StorageExistenceCache,
)
from sglang.srt.mem_cache.common import RetractionBackup
from sglang.srt.mem_cache.hicache_storage import (
    PoolName,
    PoolTransfer,
    SidecarPoolSpec,
)
from sglang.srt.mem_cache.hybrid_cache.hybrid_cache_controller import (
    HybridCacheController,
)
from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool
from sglang.srt.mem_cache.radix_cache import RadixKey
from sglang.srt.mem_cache.swa_memory_pool import SWAKVPool
from sglang.srt.mem_cache.unified_cache.cache_action import (
    BackupKV,
    CacheAction,
    ComponentAction,
    FreeComponentDeviceSlot,
    FreeDeviceKV,
    FreeDeviceKVFullOnly,
    ReplaceWriteThroughOnNodeSplit,
)

# UnifiedTreeNode / UnifiedLRUList live on the tree core; re-exported here
# because other modules and tests import them from this module.
from sglang.srt.mem_cache.unified_cache.components import (
    BASE_COMPONENT_TYPE,
    CacheTransferPhase,
    ComponentType,
    FullComponent,
    MambaComponent,
    PrepareLoadBackResult,
    SWAComponent,
    TreeComponent,
)
from sglang.srt.mem_cache.unified_cache.session_ref_tracker import (
    UnifiedSessionRefTracker,
)
from sglang.srt.mem_cache.unified_cache.storage_attachment import StorageAttachment
from sglang.srt.mem_cache.unified_cache.tree_core_registry import create_tree_core
from sglang.srt.mem_cache.unified_cache.unified_tree_core import (  # noqa: F401
    NodeId,
    UnifiedLRUList,
    UnifiedTreeCore,
    UnifiedTreeNode,
)
from sglang.srt.observability.metrics_collector import (
    StorageMetrics,
    StorageMetricsCollector,
)
from sglang.srt.runtime_context import get_memory
from sglang.srt.session.streaming_session import StreamingSession
from sglang.srt.utils.common import ceil_align

if TYPE_CHECKING:
    from sglang.srt.managers.cache_controller import HiCacheAck
    from sglang.srt.managers.schedule_batch import Req
    from sglang.srt.mem_cache.cache_init_params import CacheInitParams
    from sglang.srt.mem_cache.hybrid_cache.hybrid_cache_controller import (
        PrefetchOperation,
    )
    from sglang.srt.mem_cache.pool_host import PoolEntry
    from sglang.srt.server_args import ServerArgs

from sglang.srt.utils.rank_consensus_checker import rank_consensus

T = TypeVar("T")

# Metric label per component, matching the host pool names used by
# hicache_backup_tokens_total and the host occupancy gauges.
_COMPONENT_POOL_LABEL = {
    ComponentType.FULL: PoolName.KV.value,
    ComponentType.SWA: PoolName.SWA.value,
    ComponentType.MAMBA: PoolName.MAMBA.value,
}


COMPONENT_REGISTRY: dict[ComponentType, type[TreeComponent]] = {
    ComponentType.FULL: FullComponent,
    ComponentType.MAMBA: MambaComponent,
    ComponentType.SWA: SWAComponent,
}


logger = logging.getLogger(__name__)

# B1.5-PROBE (T31 rebase of T23; read-only instrumentation, appends JSON lines to
# /tmp/b15-probe.log only, zero numeric-path change; removed after experiment)
def _b15_log(rec):
    try:
        import json as _json
        import time as _time
        rec["ts"] = round(_time.time(), 3)
        with open("/tmp/b15-probe.log", "a") as _f:
            _f.write(_json.dumps(rec) + "\n")
    except Exception:
        pass




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


# [P2A] Per-request L3 restore final disposition. Emitted exactly once per
# request at its terminal storage interaction (decline / revoke / finalize):
# requested = page-aligned span the request could have restored, granted =
# pages actually delivered, reason = the deny/discard cause when not a full
# restore. Low frequency by construction (per request, not per attempt).
def _log_restore_disposition(rid, disposition, requested, granted, reason):
    logger.info(
        "[P2A] ts_ms=%d evt=restore_disposition rid=%s disposition=%s "
        "requested=%d granted=%d reason=%s",
        int(time.time() * 1000),
        rid,
        disposition,
        requested,
        granted,
        reason,
    )


# [P3] Eviction disposition with durability attribution (the hollow /
# forced-drop split of the NEVER_BACKED differential): durable_frontier =
# the released device span when the chain is L3-durable at the drop (the
# L3 copy survives -- a hollow), else 0 (the KV is lost -- a forced drop).
def _log_evict_durable(
    evt, node_id, freed, is_durable, *, removal_reason
):
    logger.info(
        "[P2A] ts_ms=%d evt=%s node=%d freed=%d "
        "l3_durable_frontier=%d removal_reason=%s",
        int(time.time() * 1000),
        evt,
        node_id,
        freed,
        freed if is_durable else 0,
        removal_reason,
    )


# [P3] Storage write ACK (a node's KV confirmed in L3). Frontier attribution
# for the NEVER_BACKED / PARTIAL / FULL_THEN_LOST differential: requested =
# the operation's span, durable = the persisted frontier after the ack (0 on a
# partial, the full request span on a complete write).
def _log_restore_backup(
    operation,
    node_id,
    *,
    durable_frontier: int,
    requested_frontier: int,
):
    logger.info(
        "[P3] ts_ms=%d evt=restore_backup op=%s rid=%s node=%s "
        "l3_durable_frontier=%d requested_frontier=%d",
        int(time.time() * 1000),
        operation.id,
        getattr(operation, "request_id", "none"),
        node_id,
        durable_frontier,
        requested_frontier,
    )


class _OngoingWriteThrough(NamedTuple):
    """Tracks an in-flight D→H write-through operation."""

    node_id: NodeId
    lock_params: Optional[DecLockRefParams]
    publish_node_ids: list[NodeId]


class _OngoingLoadBack(NamedTuple):
    """Tracks an in-flight H→D load-back operation."""

    node_id: NodeId
    lock_params: DecLockRefParams
    host_lock_params: DecLockRefParams
    # P2-1c: the reservation amount this entry still covers (0 once the
    # loaded span's allocation/lock ownership transferred it out of
    # inflight_promotion_reserved). The sanity invariant is
    # inflight_promotion_reserved == sum(entry.reserved_tokens).
    reserved_tokens: int = 0


class _OngoingPrefetch(NamedTuple):
    """Tracks an in-flight storage→host prefetch operation."""

    anchor_node_id: NodeId
    prefetch_key: RadixKey
    host_indices: torch.Tensor
    operation: PrefetchOperation
    anchor_lock_params: DecLockRefParams
    comp_xfers: dict[ComponentType, list[PoolTransfer]]


class PrefetchKind(Enum):
    """The inflight-budget track a prefetch was issued on (P3 M1)."""

    SPECULATIVE = auto()  # Ready-Horizon lookahead staging; eats spec headroom only
    DEMAND = auto()  # a wake re-issue serving an admitted restore episode


class PrefetchReservation:
    """Ownership record of one prefetch's inflight-budget charge (P3 M5).

    Created at issue (cache mode, Ready Horizon on) and consumed exactly
    once by release_prefetch when the prefetch leaves ongoing_prefetch.
    `released` makes a second release a no-op, so no release path can
    double-count or leak the speculative counter."""

    __slots__ = ("tokens", "kind", "released")

    def __init__(self, tokens: int, kind: PrefetchKind):
        self.tokens = tokens
        self.kind = kind
        self.released = False


class UnifiedRadixCache(BasePrefixCache):
    def __init__(
        self,
        params: CacheInitParams,
    ):
        self.req_to_token_pool = params.req_to_token_pool
        self.token_to_kv_pool_allocator = params.token_to_kv_pool_allocator
        self.disable = params.disable

        if params.enable_metrics:
            self.init_metrics_collector()
        self._enable_metrics_flag = params.enable_metrics
        self.enable_storage_metrics = False
        self.storage_metrics_collector: Optional[StorageMetricsCollector] = None
        self.extra_metric_labels = None

        assert params.tree_components is not None
        self.tree_components = tuple(params.tree_components)
        self.enable_session_radix_cache = params.enable_session_radix_cache
        component_registry = COMPONENT_REGISTRY
        if params.component_registry_override:
            component_registry = {
                **COMPONENT_REGISTRY,
                **params.component_registry_override,
            }
        self.components: dict[ComponentType, TreeComponent] = {
            ct: component_registry[ct](self, params) for ct in self.tree_components
        }
        self._components_tuple: tuple[TreeComponent, ...] = tuple(
            self.components.values()
        )
        # Whether SWA is enabled.
        self.is_swa_enabled = ComponentType.SWA in params.tree_components
        # Whether Mamba is enabled.
        self.is_mamba_enabled = ComponentType.MAMBA in params.tree_components
        # Whether the mamba extra (ping-pong) buffer is enabled.
        self.enable_mamba_extra_buffer = (
            params.enable_mamba_extra_buffer if self.is_mamba_enabled else False
        )
        # SWA window size (None when SWA is not enabled).
        self._sliding_window_size = (
            params.sliding_window_size if self.is_swa_enabled else None
        )
        # The TreeCore owns the tree member-var state (structure, LRUs, sizes,
        # evictable leaves) and drives the components' tree-level hooks.
        self.tree_core = create_tree_core(
            name=envs.SGLANG_UNIFIED_RADIX_TREE_CORE_BACKEND.get(),
            params=params,
            components=self.components,
        )
        # Components execute boundary actions through the tree core.
        for component in self.components.values():
            component.tree_core = self.tree_core

        # Session ref tracking (--enable-session-radix-cache).
        self.session_refs = UnifiedSessionRefTracker(
            components=self._components_tuple,
            tree_core=self.tree_core,
            enable_session_radix_cache=self.enable_session_radix_cache,
        )

        self.sidecar_pool_specs: list[SidecarPoolSpec] = []

        # Streaming session: embedded StreamingSession with self as inner.
        # Always on -- zero overhead when no streaming session is open (the
        # try_* entries short-circuit on non-streaming reqs / real TreeNodes).
        # Dispatch methods below pre-check conditions so the session's
        # internal fall-through to self.inner.xxx never fires -- no recursion.
        self.session = StreamingSession(inner=self)

        self.tp_group = params.tp_cache_group
        self.attn_cp_group = params.attn_cp_cache_group
        self.attn_tp_group = params.attn_tp_cache_group
        self.pp_group = params.pp_cache_group
        self.tp_world_size = (
            1
            if self.tp_group is None
            else torch.distributed.get_world_size(group=self.tp_group)
        )
        self.pp_rank = params.pp_rank
        self.pp_size = params.pp_size
        self.work_list: list[torch.distributed.Work] = []

        # HiCache D↔H defaults (overridden by init_hicache)
        self.cache_controller: Optional[HybridCacheController] = None
        self.host_pool_group = None  # set by attach_hybrid_pool_to_unified_cache
        # Owns the storage backend lifecycle; built by init_hicache.
        self._storage_attachment: Optional[StorageAttachment] = None
        self.prefetch_stop_policy = "best_effort"
        self.prefetch_threshold = 256
        self.prefetch_timeout_base = 1.0
        self.prefetch_timeout_per_page = 0.25
        self.hicache_storage_pass_prefix_keys = False
        # Buffer-only host memory mode (host RAM as transient GPU↔storage
        # staging, not an L2 tier); resolved in init_hicache, which also
        # constructs the pipeline collaborator (None = cache mode).
        self.host_memory_mode = "cache"
        self.buffer_pipeline: Optional[BufferModePipeline] = None
        # Write-side dedupe: beliefs about what storage already holds, so
        # re-inserts of hot prefixes skip the redundant backup.
        self.storage_existence_cache = StorageExistenceCache()
        # Cumulative prefetch-outcome counters, exported through the
        # log_storage_metrics flow.
        self._prefetch_outcome_stats: dict[str, float] = {
            "attempts": 0,
            "issued": 0,
            "declined_too_short": 0,
            "declined_rate_limited": 0,
            "revoked_insufficient": 0,
            "revoked_full_miss": 0,
            "l3_demand_requests": 0,
            "l3_miss_tokens": 0,
            "l1l2_miss_tokens": 0,
            "l3_demand_total_tokens": 0,
            "l3_sum_rate_all": 0.0,
            "l3_sum_rate_main_weighted": 0.0,
        }

        # P2-1c promotion-admission margin (device token level). Config, not
        # runtime state: init_hicache overrides from server_args; _reset_full
        # must not clobber it.
        self.promotion_margin_tokens = 2048

        self.reset()
        logger.info(
            f"Init Unified Radix Cache. Components: {self.tree_components}. "
            f"Tree Core: {type(self.tree_core).__name__}"
        )

    def _all_reduce_attn_groups(self, tensor: torch.Tensor, op):
        reduced = False
        for group in (self.attn_cp_group, self.attn_tp_group):
            if group is not None and torch.distributed.get_world_size(group=group) > 1:
                torch.distributed.all_reduce(tensor, op=op, group=group)
                reduced = True
        if not reduced and self.tp_world_size > 1:
            torch.distributed.all_reduce(tensor, op=op, group=self.tp_group)

    def _barrier_attn_groups(self):
        waited = False
        for group in (self.attn_cp_group, self.attn_tp_group):
            if group is not None and torch.distributed.get_world_size(group=group) > 1:
                torch.distributed.barrier(group=group)
                waited = True
        if not waited and self.tp_world_size > 1:
            torch.distributed.barrier(group=self.tp_group)

    def _drain_async_work(self):
        """
        Block until all outstanding async sends are consumed, then clear.

        Called at the start of each event round, so work_list holds the sends
        accumulated since the last round. This bounds it and applies
        backpressure when a downstream PP rank lags. Scheduler thread only.
        """
        for work in self.work_list:
            work.wait()
        self.work_list.clear()

    def _all_reduce(self, data: torch.Tensor, tp_reduce_op: torch.distributed.ReduceOp):
        """
        Synchronize data across all TP and PP ranks.

        In particular, "tp_reduce_op" is performed on all TP ranks of the first PP rank,
        and then the result is propagated to all following PP ranks.

        Must be called in the scheduler thread.
        """
        if self.pp_rank == 0:
            self._all_reduce_attn_groups(data, tp_reduce_op)
        self._pp_sync(data)

    def _pp_sync(self, data: torch.Tensor) -> None:
        """
        Synchronize data across the PP pipeline, where PPn (n>0) will receive PP0's data.
        """
        if self.pp_size <= 1 or self.pp_group is None:
            return
        if self.pp_rank > 0:
            torch.distributed.recv(
                data,
                group_src=self.pp_rank - 1,
                group=self.pp_group,
                tag=P2PTag.HIRADIX_PP_SYNC,
            )
        if self.pp_rank + 1 < self.pp_size:
            copy_of_data = data.clone()
            send_work = torch.distributed.isend(
                copy_of_data,
                group_dst=self.pp_rank + 1,
                group=self.pp_group,
                tag=P2PTag.HIRADIX_PP_SYNC,
            )
            self.work_list.append(send_work)

    def reset(self) -> None:
        self._reset_full()

    def _reset_full(self) -> None:
        """Full reset: destroy entire tree and all state."""
        self.tree_core.reset()
        self.session_refs.reset()

        # Reset Controller.
        self.session.slots.clear()
        self.ongoing_write_through: dict[int, _OngoingWriteThrough] = {}
        # L3 persists deferred out of the D->H ack drain: nodes whose write
        # acked while their anchor->node chain was not yet written to L3.
        self._pending_storage_writes: list[NodeId] = []
        # Deferred persists skipped because their node was deleted before
        # the flush consumed it (observability for the stale-ref family).
        self._storage_persist_skip_count = 0
        # P0 (phase2-backupassert): storage-gap nodes that were not host-backed
        # up but whose device value was already released (host-only unbacked
        # ancestors). These legally skip the device->host backup and fall
        # through to the storage-write path (host->L3). Observability counter.
        self._storage_gap_skipped_d2h_count = 0
        # P0 (phase2-backupassert): storage-gap nodes with neither a device
        # value nor a host copy (forced-miss tombstone / hollow with no KV in
        # any tier). They have nothing to persist and are skipped as the
        # explicit invalid / un-backupable state. Observability counter.
        self._storage_gap_skipped_nokv_count = 0
        # Re-entry guard for _drain_write_through_acks (see its entry check).
        self._drain_write_through_depth = 0
        # P3 (phase2-p3-fix): deferred-ACK reconciliation re-entrancy guard
        # (see _reconcile_deferred_acked) -- write_backup_storage re-enters
        # _flush_pending_storage_writes, so the scan must run at most once
        # per outermost flush.
        self._reconcile_depth = 0
        self.ongoing_load_back: dict[int, _OngoingLoadBack] = {}
        # P2-1c promotion admission: net reservation counter (device token
        # level, "reserved counts only the not-yet-locked part"), its peak,
        # and the [P2A] event counters (design §5-8).
        self.inflight_promotion_reserved = 0
        self._promotion_inflight_peak = 0
        self._promotion_denied_count = 0
        self._promotion_denied_exact_count = 0
        self._promotion_reserve_count = 0
        self._promotion_transfer_count = 0
        self._promotion_release_count = 0
        self.enable_storage = False
        self.prefetch_loaded_tokens_by_reqid: dict[str, int] = {}
        self.ongoing_prefetch: dict[str, _OngoingPrefetch] = {}
        # P3 M5: per-rid inflight-budget ownership records; every removal
        # from ongoing_prefetch releases its reservation exactly once.
        self._prefetch_reservations: dict[str, PrefetchReservation] = {}
        # Rids whose storage prefetch resolved without a usable result;
        # popped by the scheduler to pace availability-check retries.
        self._storage_prefetch_missed_rids: set[str] = set()
        # P2-1 M2: frontier waiters keyed by their anchor node (scheduler
        # gate skip registers, the ack drain wakes, reconciliation consumes).
        self._storage_frontier_waiters: dict[NodeId, set[str]] = {}
        self._storage_frontier_ready: set[str] = set()
        # P2-IO T15: parked-backup spans per rid (anchor, requested_pages,
        # page_hashes), stored at the park and popped when the wait ends
        # (discard_frontier_waiter); the wake re-reads the chain frontier
        # from the stored anchor each scheduler pass.
        self._backup_wait_spans: dict[str, tuple[NodeId, int, list[str]]] = {}
        # P2-IO R2: rids whose re-issue holds a DEMAND_RESTORE ticket (the
        # T15 wake path past the speculative PREFETCH_BUDGET); added at the
        # demand issue, discarded when the prefetch leaves ongoing_prefetch.
        self._demand_restore_rids: set[str] = set()
        # P2-1 M1b: terminal prefetch outcome per rid ("finalized" /
        # "revoked_miss" / "revoked_terminated"), recorded by the drain and
        # consumed by the scheduler's restore-state reconciliation on the
        # same (scheduler) thread.
        self._storage_prefetch_terminal: dict[str, str] = {}
        self.ongoing_backup: dict[int, tuple[NodeId, DecLockRefParams]] = {}
        # One-shot marker for the storage-failure degradation (see
        # _handle_storage_failure); cleared together with the controller's
        # thread restart in reset().
        self._storage_failure_handled = False
        if self.buffer_pipeline is not None:
            self.buffer_pipeline.reset()

        if self.cache_controller is not None:
            self.cache_controller.reset()
            self.cache_controller.mem_pool_host.clear()
            self.enable_storage = self.cache_controller.enable_storage

        self.tree_core.kv_events.record_all_cleared()

    def init_hicache(self, server_args: ServerArgs, params: CacheInitParams) -> None:
        """Initialize HiCache infrastructure."""
        self.host_memory_mode = server_args.hicache_host_memory_mode
        self.promotion_margin_tokens = server_args.hicache_promotion_margin_tokens
        # T15 bypass gate (P2-IO): read once at init. Off restores the
        # pre-T15 baseline (partial revokes as a miss); the T15 machinery
        # stays in the tree as dead code behind _backup_park_applies.
        self.hicache_restore_backup_park = server_args.hicache_restore_backup_park
        # P3 Ready Horizon (M1): read once at init. Off keeps the pre-P3
        # single-track inflight budget byte for byte (the speculative
        # counter never grows, no reservations, wake re-issues keep their
        # T15 demand_restore semantics only).
        self.enable_ready_horizon = server_args.enable_ready_horizon
        if self.host_memory_mode == "buffer_only":
            # FULL and FULL+SWA only: Mamba has no state-handoff channel on
            # the admission-time load-back read path and is not layer-gated.
            # Lifting the fence also needs the admission charge: a staged
            # state slot is request-pinned at consumption and must ride
            # req.mamba_host_hit_length the way the SWA window does.
            supported = {ComponentType.FULL, ComponentType.SWA}
            if not set(self.tree_components) <= supported:
                raise ValueError(
                    "--hicache-host-memory-mode buffer_only supports only "
                    "FULL/SWA unified trees; got components "
                    f"{sorted(ct.name for ct in self.tree_components)}."
                )
        from sglang.srt.mem_cache.hybrid_cache.hybrid_pool_assembler import (
            attach_hybrid_pool_to_unified_cache,
        )

        self.load_cache_event = threading.Event()
        self.sidecar_pool_specs.clear()
        self.extra_metric_labels = server_args.extra_metric_labels

        # Parse storage config once, share with assembler and tree
        storage_backend = get_memory().hicache_storage_backend
        storage_extra_config = None
        storage_prefetch_threshold = 256
        prefetch_timeout_base = 1.0
        prefetch_timeout_per_ki_token = 0.25
        hicache_storage_pass_prefix_keys = False
        if storage_backend is not None:
            (
                storage_extra_config,
                storage_prefetch_threshold,
                prefetch_timeout_base,
                prefetch_timeout_per_ki_token,
                hicache_storage_pass_prefix_keys,
            ) = HybridCacheController.parse_storage_backend_extra_config(
                get_memory().hicache_storage_backend_extra_config
            )

        attach_hybrid_pool_to_unified_cache(
            self,
            params,
            server_args,
            load_cache_event=self.load_cache_event,
            storage_backend=storage_backend,
            storage_extra_config=storage_extra_config,
            storage_prefetch_threshold=storage_prefetch_threshold,
        )
        # Tag HiCache enablement on the TreeCore.
        if self.cache_controller is not None:
            self.tree_core.set_hicache_enabled()
            # P3 M1: the speculative budget share, read before any
            # attach_storage_backend computes the limit from it.
            self.cache_controller.prefetch_speculative_fraction = (
                server_args.hicache_prefetch_speculative_fraction
            )
            if self.supports_swa():
                swa = self.components[ComponentType.SWA]
                self.tree_core.has_swa_host_pool = swa._swa_kv_pool_host is not None

        if self.host_memory_mode == "buffer_only":
            swa = self.components.get(ComponentType.SWA)
            validate_buffer_only_stack(
                sidecar_pool_specs=self.sidecar_pool_specs, swa_component=swa
            )
            self.buffer_pipeline = BufferModePipeline(
                cache=self,
                max_context_len=server_args.context_length or 0,
                swa_window_pages=(
                    swa.full_window_pages
                    if swa is not None and self.tree_core.has_swa_host_pool
                    else 0
                ),
                # Leak backstop only: live queued tokens are intrinsically
                # bounded by the FULL device pool (one intent per node, stale
                # intents swept per tick), so a cap that binds on live
                # content would drop-newest and punch storage holes.
                write_backlog_cap=2 * self.token_to_kv_pool_allocator.size_full,
            )
            self.cache_controller.host_write_staged_tokens_fn = (
                lambda: self.buffer_pipeline.write_staged_tokens_
            )

        # State initialization
        self.write_through_threshold = (
            1 if get_memory().hicache_write_policy == "write_through" else 2
        )
        self.is_write_back = (
            self.cache_controller is not None
            and self.cache_controller.write_policy == "write_back"
        )
        # Pre-seed the dropped-tokens series at 0 per pool
        if self.metrics_collector is not None and self.cache_controller is not None:
            for ct in self.tree_components:
                self.metrics_collector.increment_dropped_tokens(
                    num_tokens=0,
                    reason="host_pressure",
                    pool=_COMPONENT_POOL_LABEL[ct],
                )
        self.load_back_threshold = 10
        self.prefetch_stop_policy = get_memory().hicache_storage_prefetch_policy

        # Runtime attach/detach of the L3 backend (startup, admin API, atexit).
        self._storage_attachment = StorageAttachment(self)
        atexit.register(self.shutdown)

        if storage_backend is not None:
            self._storage_attachment.apply_runtime_config(
                storage_backend=storage_backend,
                prefetch_threshold=storage_prefetch_threshold,
                prefetch_timeout_base=prefetch_timeout_base,
                prefetch_timeout_per_ki_token=prefetch_timeout_per_ki_token,
                hicache_storage_pass_prefix_keys=hicache_storage_pass_prefix_keys,
                enable_storage=self.cache_controller.enable_storage,
                enable_storage_metrics=self._enable_metrics_flag,
                extra_metric_labels=self.extra_metric_labels,
            )

    def register_sidecar_pool(
        self, spec: SidecarPoolSpec, entry: Optional[PoolEntry] = None
    ) -> None:
        if entry is not None:
            if self.cache_controller is None:
                raise RuntimeError("HiCache controller is not attached.")
            self.cache_controller.register_host_pool_entry(entry)
        self.sidecar_pool_specs.append(spec)

    def release_host_resources(self) -> None:
        if self.cache_controller is not None:
            # Graceful-exit order: drain/join the storage threads before
            # destroying the host pools they read/write; otherwise a still-
            # running backup thread touches a destroyed pool (NoneType crash).
            self.cache_controller.stop_storage_threads()
        if self.host_pool_group is not None:
            self.host_pool_group.destroy()

    @rank_consensus(
        same_params=["params"],
        same_results=["result.full_kv_hit_length", "result.swa_host_hit_length"],
    )
    def match_prefix(self, params: MatchPrefixParams) -> MatchResult:
        result = self.session.try_match_prefix(params)
        if result is not None:
            return result
        if self.disable:
            return self.tree_core.empty_match_result
        result = self.tree_core.match_prefix(params)
        # Apply the walk's actions (e.g. a pending write-through relocation on
        # a split) before the finalizers, which can evict or raise.
        self._apply_cache_actions(result.cache_actions)
        for component in self._components_tuple:
            result = component.finalize_match_result_in_cache(params, result)
        # Finalizers must not emit actions; the walk's were applied above.
        assert not result.cache_actions
        return result

    def is_chunk_cache(self) -> bool:
        return self.disable

    def insert(self, params: InsertParams) -> InsertResult:
        if self.disable:
            return InsertResult(prefix_len=0)
        # Fail fast on re-entrancy without touching the in-flight walk.
        assert not self.tree_core.has_ongoing_insert(), "re-entrant insert"
        # Pump the resumable insert, applying each step's actions at its barrier.
        try:
            step = self.tree_core.begin_insert(params)
            while True:
                self._apply_cache_actions(step.actions)
                if step.result is not None:
                    # Walk actions flow through the steps; the result is action-free.
                    assert not step.result.cache_actions
                    return step.result
                step = self.tree_core.resume_insert()
        finally:
            # Drain still-pending actions so frees reach the allocator on abort.
            self._apply_cache_actions(self.tree_core.end_insert())

    def evict(self, params: EvictParams) -> EvictResult:
        return self._evict(params)

    def evict_for_alloc(self, params: EvictParams) -> EvictResult:
        """Evict until the requested component allocations become feasible.

        ``params`` contains allocator shortfalls, not absolute eviction quotas.
        A component eviction can cascade to its peers; with a shared memory pool,
        those collateral frees can satisfy the original allocation before the
        triggering component's requested count is reached.
        """
        if self.disable:
            return EvictResult()

        request_by_type = self._evict_request_by_type(params)
        available_size_targets = {
            ct: self._component_available_size(ct) + request_cnt
            for ct, request_cnt in request_by_type.items()
            if request_cnt > 0
        }
        return self._evict(params, available_size_targets)

    @staticmethod
    def _evict_request_by_type(params: EvictParams) -> dict[ComponentType, int]:
        return {
            ComponentType.FULL: params.num_tokens,
            ComponentType.SWA: params.swa_num_tokens,
            ComponentType.MAMBA: params.mamba_num,
            ComponentType.C128: 0,
        }

    def _component_available_size(self, component_type: ComponentType) -> int:
        """Return capacity usable by the component's next allocation.

        Shared allocators expose schedulable capacity, which includes peer holes
        that an urgent allocator flush can reclaim without further eviction.
        """
        if component_type == ComponentType.FULL:
            if self.supports_swa():
                return self.token_to_kv_pool_allocator.full_available_size()
            return self.token_to_kv_pool_allocator.available_size()
        if component_type == ComponentType.SWA:
            return self.token_to_kv_pool_allocator.swa_available_size()
        if component_type == ComponentType.MAMBA:
            return self.req_to_token_pool.mamba_allocator.schedulable_available_size()
        raise ValueError(f"Unsupported cache component: {component_type}")

    def _evict(
        self,
        params: EvictParams,
        available_size_targets: Optional[dict[ComponentType, int]] = None,
    ) -> EvictResult:
        if self.disable:
            return EvictResult()
        start_time = time.perf_counter()
        _b15_evict_t0 = time.perf_counter()
        tracker = {ct: 0 for ct in self.tree_components}

        request_by_type = self._evict_request_by_type(params)
        self._evict_components(
            request_by_type,
            tracker,
            available_size_targets=available_size_targets,
        )

        if (
            self.cache_controller is not None
            and self.cache_controller.write_policy == "write_back"
        ):
            self.writing_check(write_back=True)

        # Report full-layer tokens only
        self.update_eviction_metrics(tracker[BASE_COMPONENT_TYPE], start_time)
        try:
            _b15_log({"evt": "pa_evict",
                      "ms": round((time.perf_counter() - _b15_evict_t0) * 1000, 3),
                      "requested_tokens": params.num_tokens,
                      "mamba_num": params.mamba_num})
        except Exception:
            pass
        return EvictResult(
            num_tokens_evicted=tracker[BASE_COMPONENT_TYPE],
            swa_num_tokens_evicted=tracker.get(ComponentType.SWA, 0),
            mamba_num_evicted=tracker.get(ComponentType.MAMBA, 0),
        )

    def _free_values(
        self,
        device_frees: dict[ComponentType, list[torch.Tensor]],
        host_frees: dict[ComponentType, list[torch.Tensor]],
    ) -> None:
        """Free a tree-side step's returned device and host values right away."""
        # Both drains must run even if one raises.
        try:
            self._drain_device_frees(device_frees)
        finally:
            self._drain_host_frees(host_frees)

    def _accumulate_tracker(
        self,
        tracker: dict[ComponentType, int],
        delta: dict[ComponentType, int],
    ) -> None:
        """Fold a step result's evicted delta into the running totals."""
        for ct, n in delta.items():
            tracker[ct] += n

    def _evict_device_next_node(
        self, component_type: ComponentType, tracker: dict[ComponentType, int]
    ) -> tuple[Optional[NodeId], bool]:
        """Advance the eviction walk one node, consuming its step result."""
        result = self.tree_core.evict_device_next_node(component_type, tracker)
        self._free_values(result.device_frees, result.host_frees)
        self._accumulate_tracker(tracker, result.tracker)
        return result.node_id, result.made_progress

    def _evict_device_leaf(
        self, node_id: NodeId, tracker: dict[ComponentType, int]
    ) -> Optional[BackupKV]:
        """Evict one device leaf, consuming its step result; returns the
        deferred write-back BackupKV when one must run before the demote."""
        result = self.tree_core.evict_device_leaf(node_id, self.is_write_back)
        self._free_values(result.device_frees, result.host_frees)
        self._accumulate_tracker(tracker, result.tracker)
        return result.backup_kv

    def _demote(self, node_id: NodeId, tracker: dict[ComponentType, int]) -> None:
        """Demote a backed-up node, consuming its step result."""
        result = self.tree_core.demote(node_id)
        self._free_values(result.device_frees, result.host_frees)
        self._accumulate_tracker(tracker, result.tracker)

    def _drop_subtree_no_host(
        self, node_id: NodeId, tracker: dict[ComponentType, int]
    ) -> bool:
        """Run the write-back drop fallback, consuming its step result."""
        result = self.tree_core.drop_subtree_no_host(node_id)
        self._free_values(result.device_frees, result.host_frees)
        self._accumulate_tracker(tracker, result.tracker)
        return result.is_dropped

    def _evict_device_leaf_storage_backed(
        self, node_id: NodeId, tracker: dict[ComponentType, int]
    ) -> None:
        """Hollow a device leaf whose chain is L3-durable (the D->H backup
        failed and the subtree drop was declined): free its device layers,
        keep the node and host subtree. The L3 copy is the durable backup --
        written+acked or restored (P2-1 e14)."""
        result = self.tree_core.evict_device_leaf_storage_backed(node_id)
        self._free_values(result.device_frees, result.host_frees)
        self._accumulate_tracker(tracker, result.tracker)
        _log_evict_durable(
            "hollow_evict",
            node_id,
            result.tracker.get(BASE_COMPONENT_TYPE, 0),
            self.tree_core.is_l3_durable(node_id),
            removal_reason="storage_backed",
        )

    def _drop_device_leaf_to_miss(
        self, node_id: NodeId, tracker: dict[ComponentType, int]
    ) -> None:
        """Drop an evictable device leaf to a plain miss when the D->H
        backup failed, the subtree drop was declined, and the chain is not
        L3-durable (P2-1 e15 Z3): free its device layers, keep the node and
        host subtree, and leave no hollow/restore expectation behind. The
        walker's evictable_device_leaves membership guarantees the leaf is
        unlocked (lock_ref == 0: no active request, no in-flight H->D DMA)
        and the failed backup never issued the D->H copy; the caller proved
        is_l3_durable False, so the released KV is not backed by any other
        tier -- a future access misses and recomputes. Cache persistence is
        sacrificed, never faked."""
        # is_l3_durable must be read before the detach unregisters the node.
        was_l3_durable = self.tree_core.is_l3_durable(node_id)
        result = self.tree_core.drop_device_leaf_to_miss(node_id)
        self._free_values(result.device_frees, result.host_frees)
        self._accumulate_tracker(tracker, result.tracker)
        # P2-1 e16/e17: the node is now a forced-miss plain miss (device layers
        # gone, no hollow/restore expectation). Detach it AND its host-only
        # subtree from the tree so no later ancestor drop_subtree_no_host
        # traverse sees a dead descendant (e16) and no reachable-from-root
        # membership check trips on an orphaned subtree (e17). The parent chain
        # backspaces the dropped KV, so removing the dead leaf's subtree removes
        # no durable content. drop_subtree_no_host skips any tombstone it still
        # encounters (belt-and-suspenders).
        detach_result = self.tree_core.detach_miss_dropped(node_id)
        self._free_values(detach_result.device_frees, detach_result.host_frees)
        self._accumulate_tracker(tracker, detach_result.tracker)
        _log_evict_durable(
            "forced_drop_to_miss",
            node_id,
            result.tracker.get(BASE_COMPONENT_TYPE, 0),
            was_l3_durable,
            removal_reason="no_durable_backup",
        )

    def _evict_components(
        self,
        request_by_type: dict[ComponentType, int],
        tracker: dict[ComponentType, int],
        available_size_targets: Optional[dict[ComponentType, int]] = None,
    ) -> None:
        # Buffer mode: eviction always wins over queued backup intents — a
        # destroyed victim's intent is stale-swept and the content rewrites
        # after its recompute.

        def target_reached(component_type: ComponentType) -> bool:
            if available_size_targets is None:
                return False
            target = available_size_targets.get(component_type)
            # Do not compact on every eviction step. Shared allocators include
            # drainable peer holes here and flush the peer once in alloc().
            return (
                target is not None
                and self._component_available_size(component_type) >= target
            )

        for ct in self.tree_components:
            request_cnt = request_by_type[ct]
            # A preceding component may have cascade-evicted this component or,
            # on a shared pool, released enough bytes to satisfy its allocation.
            if tracker[ct] >= request_cnt or target_reached(ct):
                continue
            self.tree_core.evict_device_start(ct, request_cnt)
            try:
                while not target_reached(ct):
                    node_id, made_progress = self._evict_device_next_node(ct, tracker)
                    if node_id is None:
                        if made_progress:
                            # Internal tombstone frees are now allocator-visible;
                            # recheck the allocation target before walking again.
                            continue
                        break
                    backup_kv = self._evict_device_leaf(node_id, tracker)
                    if backup_kv is not None:
                        # Deferred demote: run the D->H backup, demote only on success.
                        written = self._execute_and_commit_kv_backup(
                            backup_kv, write_back=True
                        )
                        freed_before_drop = dict(tracker)
                        if written > 0:
                            # Defer the L3 persist flush past the demote: its
                            # gap-fill may evict_host, and the duplicate-reclaim
                            # pass takes D-leaves, which would strip this node's
                            # just-acked host copy before _demote runs.
                            self.writing_check(write_back=True, flush_pending=False)
                            self._demote(node_id, tracker)
                        elif self._drop_subtree_no_host(node_id, tracker):
                            self._record_dropped_tokens(tracker, freed_before_drop)
                            logger.warning(
                                "write_back: KV subtree dropped without backup "
                                "due to host memory pressure, root node %d",
                                node_id,
                            )
                        elif self.tree_core.is_l3_durable(node_id):
                            # Backup and drop both blocked (host full; the
                            # subtree's host values are DMA-locked by an
                            # in-flight prefetch), but the chain's L3 copy is
                            # the durable backup -- written+acked OR restored
                            # (P2-1 e14: a chain restored from L3 is the
                            # K=32 deadlock shape) -- so hollow the leaf
                            # instead of leaving it unevictable until host
                            # space frees.
                            self._evict_device_leaf_storage_backed(
                                node_id, tracker
                            )
                        else:
                            # P2-1 e15 Z3: no tier can take over this leaf's
                            # KV (no L3 copy, subtree drop locked) -- degrade
                            # it to a plain future miss/recompute instead of
                            # leaving the walker stuck until host space
                            # frees. Liveness may sacrifice cache hits, but
                            # never fakes durability.
                            self._drop_device_leaf_to_miss(node_id, tracker)
            finally:
                self.tree_core.evict_device_end(ct)

    def _record_dropped_tokens(
        self,
        tracker: dict[ComponentType, int],
        freed_before_drop: dict[ComponentType, int],
    ) -> None:
        """Record per-pool tokens dropped without backup under host pressure."""
        if self.metrics_collector is None:
            return
        for ct, freed in tracker.items():
            dropped = freed - freed_before_drop[ct]
            if dropped > 0:
                self.metrics_collector.increment_dropped_tokens(
                    num_tokens=dropped,
                    reason="host_pressure",
                    pool=_COMPONENT_POOL_LABEL[ct],
                )

    def inc_lock_ref(
        self, node_id: NodeId, skip_lock_components: Sequence[ComponentType] = ()
    ) -> IncLockRefResult:
        result = self.session.try_inc_lock_ref(node_id)
        if result is not None:
            return result
        if self.disable:
            return IncLockRefResult()
        return self.tree_core.inc_lock_ref(node_id, skip_lock_components)

    def dec_lock_ref(
        self,
        node_id: NodeId,
        params: Optional[DecLockRefParams] = None,
        skip_swa: bool = False,
    ) -> DecLockRefResult:
        result = self.session.try_dec_lock_ref(node_id, params)
        if result is not None:
            return result
        if self.disable:
            return DecLockRefResult()
        return self.tree_core.dec_lock_ref(node_id, params, skip_swa)

    def _dec_req_lock(self, req: Req, *, skip_swa: bool = False) -> None:
        """Release the tree lock a request holds on its last_node, honoring the
        components it skipped locking so it never drops a lock it never took."""
        self.dec_lock_ref(
            req.last_node,
            DecLockRefParams(
                swa_uuid_for_lock=req.swa_uuid_for_lock,
                skip_lock_node_ids=req.skip_lock_node_ids,
            ),
            skip_swa=skip_swa,
        )

    def dec_swa_lock_only(
        self,
        node_id: NodeId,
        swa_uuid_for_lock: Optional[int] = None,
        skip_lock_node_ids: Optional[dict] = None,
    ) -> None:
        if self.disable:
            return
        result = self.tree_core.dec_swa_lock_only(
            node_id, swa_uuid_for_lock, skip_lock_node_ids
        )
        self._free_values(result.device_frees, result.host_frees)

    def inc_host_lock_ref(self, node_id: NodeId) -> IncLockRefResult:
        if self.disable:
            return IncLockRefResult()
        return self.tree_core.inc_host_lock_ref(node_id)

    def dec_host_lock_ref(
        self, node_id: NodeId, params: Optional[DecLockRefParams] = None
    ) -> DecLockRefResult:
        if self.disable:
            return DecLockRefResult()
        return self.tree_core.dec_host_lock_ref(node_id, params)

    def cache_finished_req(
        self, req: Req, is_insert: bool = True, *, kv_len_to_handle: int, **kwargs
    ) -> None:
        if self.session.try_cache_finished_req(req, is_insert=is_insert, **kwargs):
            return

        if self.disable:
            kv_indices = self.req_to_token_pool.req_to_token[
                req.req_pool_idx, :kv_len_to_handle
            ]
            self.token_to_kv_pool_allocator.free_segment(kv_indices, start_pos=0)
            for comp in self._components_tuple:
                comp.cleanup_after_caching_req(req, is_finished=True)
            return

        token_ids = (req.origin_input_ids + req.output_ids)[:kv_len_to_handle]
        kv_indices = self.req_to_token_pool.req_to_token[
            req.req_pool_idx, :kv_len_to_handle
        ]

        result = None
        insert_params = None

        if is_insert:
            insert_params = InsertParams(
                prev_prefix_len=req.cache_protected_len,
                priority=getattr(req, "priority", 0) or 0,
            )

            # components prepare insert data + return effective cache_len
            effective_cache_len = len(token_ids)
            for comp in self._components_tuple:
                cl = comp.prepare_for_caching_req(
                    req=req,
                    insert_params=insert_params,
                    token_ids_len=len(token_ids),
                    is_finished=True,
                )
                if cl is not None:
                    effective_cache_len = min(effective_cache_len, cl)

            # Truncate if needed; the tail free is deferred and batched with
            # the unaligned tail below so a shared boundary page is emitted once.
            kv_indices_full = kv_indices
            tail_free_start = None
            if effective_cache_len < len(token_ids):
                tail_free_start = max(effective_cache_len, req.cache_protected_len)
                token_ids = token_ids[:effective_cache_len]
                kv_indices = kv_indices[:effective_cache_len]

            radix_key = RadixKey(
                token_ids,
                req.extra_key,
                is_bigram=self.tree_core.is_eagle,
                cache_salt=req.cache_salt,
            ).page_aligned(self.page_size)
            page_aligned_len = len(radix_key)
            values = kv_indices[:page_aligned_len].to(dtype=torch.int64, copy=True)

            insert_params.key = radix_key
            insert_params.value = values
            result = self.insert(insert_params)

            # Free unaligned tail (+ deferred truncation tail)
            segments = [(kv_indices[page_aligned_len:], page_aligned_len)]
            if tail_free_start is not None:
                segments.append((kv_indices_full[tail_free_start:], tail_free_start))
            self.token_to_kv_pool_allocator.free_segments(segments)
        else:
            self.token_to_kv_pool_allocator.free_segment(
                kv_indices[req.cache_protected_len :],
                start_pos=req.cache_protected_len,
            )

        self._dec_req_lock(req, skip_swa=req.swa_prefix_lock_released)

        if is_insert and result is not None and result.last_device_node is not None:
            req.last_node = result.last_device_node

        # cleanup
        for comp in self._components_tuple:
            comp.cleanup_after_caching_req(
                req, is_finished=True, insert_result=result, insert_params=insert_params
            )

        if self.enable_session_radix_cache and result is not None:
            from sglang.srt.managers.schedule_batch import FINISH_ABORT

            if req.finished_reason is not None and not isinstance(
                req.finished_reason, FINISH_ABORT
            ):
                self.session_refs.register_session_ref(req)

    def cache_unfinished_req(self, req: Req, chunked: bool = False, **kwargs) -> None:
        if self.session.try_cache_unfinished_req(req, chunked=chunked, **kwargs):
            return

        token_ids = req.get_fill_ids()

        if self.disable:
            kv_indices = self.req_to_token_pool.req_to_token[
                req.req_pool_idx, : len(token_ids)
            ]
            req.prefix_indices = kv_indices.to(dtype=torch.int64, copy=True)
            return

        kv_indices_orig = self.req_to_token_pool.req_to_token[
            req.req_pool_idx, : len(token_ids)
        ]

        # components prepare insert data + return effective cache_len
        insert_params = InsertParams(
            prev_prefix_len=req.cache_protected_len,
            chunked=chunked,
            priority=getattr(req, "priority", 0) or 0,
        )
        effective_cache_len = len(token_ids)
        for comp in self._components_tuple:
            cl = comp.prepare_for_caching_req(
                req=req,
                insert_params=insert_params,
                token_ids_len=len(token_ids),
                is_finished=False,
            )
            if cl is not None:
                effective_cache_len = min(effective_cache_len, cl)

        radix_key = RadixKey(
            token_ids[:effective_cache_len],
            req.extra_key,
            is_bigram=self.tree_core.is_eagle,
            cache_salt=req.cache_salt,
        )

        if envs.SGLANG_OPT_UNIFIED_CACHE_FREE_OUT_OF_WINDOW_SLOTS.get():
            # The frontier lands a page below page_floor(pre_len + 1), which has to
            # be where the insert stops, or the leaf it creates keeps less than a
            # sliding window of live SWA and the match after the insert rejects it.
            # The insert stops at page_floor(len(radix_key)), and a bigram key is
            # one shorter than the tokens it spans, so measure the key.
            for comp in self._components_tuple:
                comp.free_out_of_window_slots(req, len(radix_key) - 1, insert_params)

        if effective_cache_len <= 0:
            req.prefix_indices = kv_indices_orig.to(dtype=torch.int64, copy=True)
            for comp in self._components_tuple:
                comp.cleanup_after_caching_req(
                    req, is_finished=False, insert_params=insert_params
                )
            return

        kv_indices = kv_indices_orig[:effective_cache_len]

        radix_key = radix_key.page_aligned(self.page_size)
        page_aligned_len = len(radix_key)
        values = kv_indices[:page_aligned_len].to(dtype=torch.int64, copy=True)

        insert_params.key = radix_key
        insert_params.value = values
        result = self.insert(insert_params)

        # Match prefix. SWA insertion retains one extra window before the
        # page-aligned boundary, so the normal match remains safe to repoint.
        match_result = self.match_prefix(MatchPrefixParams(key=radix_key, req=req))
        new_indices = match_result.device_indices
        new_last_node = match_result.last_device_node
        new_prefix_len = result.prefix_len
        assert (
            req.cache_protected_len <= len(new_indices) + self.page_size - 1
        ), f"{req.cache_protected_len=}, {len(new_indices)=}, {page_aligned_len=}"
        assert new_prefix_len <= len(
            new_indices
        ), f"{new_prefix_len=}, {len(new_indices)=}"
        self.req_to_token_pool.write(
            (req.req_pool_idx, slice(req.cache_protected_len, len(new_indices))),
            new_indices[req.cache_protected_len :],
        )

        self._dec_req_lock(req)
        # Opt-in: leave the matched-prefix mamba evictable during decode (it is
        # already COW'd to the request's own slot, never read from this node again).
        # Safe only because any future COW source is the COWing request's own
        # admission-locked last_node (recorded only if still present, locked before
        # the next alloc) -- not this evictable node. A scheduler that matched a
        # whole batch before locking would break that. Off = original full lock.
        skip_lock_components = (
            (ComponentType.MAMBA,)
            if envs.SGLANG_OPT_MAMBA_SKIP_DECODE_LOCK.get()
            else ()
        )
        lock_result = self.inc_lock_ref(
            new_last_node, skip_lock_components=skip_lock_components
        )

        # Update req fields
        if len(new_indices) < len(kv_indices_orig):
            req.prefix_indices = torch.cat(
                [new_indices, kv_indices_orig[len(new_indices) :]]
            )
        else:
            req.prefix_indices = new_indices
        req.cache_protected_len = len(new_indices)
        req.last_node = new_last_node
        req.swa_uuid_for_lock = lock_result.swa_uuid_for_lock
        # carry the skip set so this node's dec releases only what we locked
        req.skip_lock_node_ids = lock_result.skip_lock_node_ids
        # The rematch acquired a new SWA prefix lock.
        req.swa_prefix_lock_released = False

        # cleanup
        for comp in self._components_tuple:
            comp.cleanup_after_caching_req(
                req,
                is_finished=False,
                insert_result=result,
                insert_params=insert_params,
            )

    # ---- Internal Helpers ----

    def _apply_cache_actions(
        self, actions: list[CacheAction | ComponentAction]
    ) -> None:
        # Apply and consume one at a time: a spent list cannot be double-applied.
        actions.reverse()
        try:
            while actions:
                self._apply_cache_action(actions.pop())
        finally:
            actions.reverse()

    def _apply_cache_action(self, action: CacheAction | ComponentAction) -> None:
        # Component actions route to their component class; the rest are
        # cache-owned and handled here by type.
        if isinstance(action, ComponentAction):
            self.components[action.component_type].apply_component_action(action)
        elif isinstance(action, ReplaceWriteThroughOnNodeSplit):
            self._replace_pending_write_through_node(
                action.ack_id,
                action.old_node_id,
                [action.new_node_id, action.new_child_node_id],
            )
        elif isinstance(action, FreeDeviceKV):
            # tree values are page-aligned copies of a kv row: page-exact segments
            for indices in action.indices:
                self.token_to_kv_pool_allocator.free_segment(indices, start_pos=0)
        elif isinstance(action, FreeDeviceKVFullOnly):
            for indices in action.indices:
                self.token_to_kv_pool_allocator.free_full(indices)
        elif isinstance(action, BackupKV):
            self._execute_and_commit_kv_backup(action)
        else:
            raise AssertionError(f"unhandled CacheAction: {type(action).__name__}")

    def _drain_device_frees(
        self, device_frees: dict[ComponentType, list[torch.Tensor]]
    ) -> None:
        # Free per component device slots, consuming each entry as it frees.
        for ct in list(device_frees):
            self._apply_cache_action(
                FreeComponentDeviceSlot(device_frees.pop(ct), component_type=ct)
            )

    def _drain_host_frees(
        self, host_frees: dict[ComponentType, list[torch.Tensor]]
    ) -> None:
        # Free per component host-pool slots, consuming each entry as it frees.
        for ct in list(host_frees):
            self.components[ct].free_host_values(host_frees.pop(ct))

    def evict_host(
        self, num_tokens: int, component_type: ComponentType = BASE_COMPONENT_TYPE
    ) -> int:
        """Evict host resources for a specific component to free host pool space."""
        if self.host_memory_mode == "buffer_only":
            # The tree never holds host values in buffer mode, and staging
            # is operation-owned (freed at each ack): nothing is evictable.
            return 0
        result = self.tree_core.drive_host_eviction(component_type, num_tokens)
        self._free_values(result.device_frees, result.host_frees)
        return result.tracker.get(component_type, 0)

    # ---- Decode retraction ----

    def supports_retraction_backup(self) -> bool:
        if self.cache_controller is None or self.host_pool_group is None:
            return False
        if self.supports_mamba():
            return False

        kv_cache = self.token_to_kv_pool_allocator.get_kvcache()
        if isinstance(kv_cache, SWAKVPool):
            return (
                self.supports_swa()
                and {
                    PoolName.KV,
                    PoolName.SWA,
                }
                <= self.host_pool_group.entry_map.keys()
            )
        return isinstance(kv_cache, MHATokenToKVPool) and (
            PoolName.KV in self.host_pool_group.entry_map
        )

    def validate_retraction_host_capacity(self) -> None:
        if not self.supports_retraction_backup():
            raise ValueError(
                "--disaggregation-decode-retraction-backup=host_pool requires "
                "an MHA or hybrid-SWA HiCache host stack."
            )

        for spec in self.sidecar_pool_specs:
            source_size = self.host_pool_group.entry_map[
                spec.indices_from_pool
            ].host_pool.logical_size
            sidecar_size = self.host_pool_group.entry_map[
                spec.pool_name
            ].host_pool.logical_size
            if sidecar_size < source_size:
                raise ValueError(
                    "Retraction sidecar host pool is smaller than its index source: "
                    f"pool={spec.pool_name}, host_slots={sidecar_size}, "
                    f"source={spec.indices_from_pool}, source_slots={source_size}."
                )

    @staticmethod
    def _pad_retraction_indices(indices: torch.Tensor, page_size: int) -> torch.Tensor:
        aligned_len = ceil_align(len(indices), page_size)
        if aligned_len == len(indices):
            return indices
        tail = indices[-1] + torch.arange(
            1,
            aligned_len - len(indices) + 1,
            dtype=torch.int64,
            device=indices.device,
        )
        return torch.cat([indices, tail])

    def _retraction_device_transfers(
        self, req: Req
    ) -> tuple[torch.Tensor, list[PoolTransfer]]:
        num_tokens = req.seqlen - 1
        full_indices = self.req_to_token_pool.req_to_token[
            req.req_pool_idx, :num_tokens
        ].to(torch.int64)
        full_indices = self._pad_retraction_indices(full_indices, self.page_size)

        component_transfers: dict[ComponentType, list[PoolTransfer]] = {}
        if self.supports_swa():
            kv_cache = self.token_to_kv_pool_allocator.get_kvcache()
            assert self.sliding_window_size is not None
            window_start = max(0, num_tokens - self.sliding_window_size)
            window_start = window_start // self.page_size * self.page_size
            window_indices = self.req_to_token_pool.req_to_token[
                req.req_pool_idx, window_start:num_tokens
            ].to(torch.int64)
            swa_indices = kv_cache.translate_loc_from_full_to_swa(window_indices)
            assert bool(
                (swa_indices > 0).all()
            ), f"unmapped SWA window positions for request {req.rid}"
            component_transfers[ComponentType.SWA] = [
                PoolTransfer(
                    name=PoolName.SWA,
                    device_indices=self._pad_retraction_indices(
                        swa_indices, self.page_size
                    ),
                )
            ]

        kv_transfer = PoolTransfer(name=PoolName.KV, device_indices=full_indices)
        extra_transfers = [
            transfer
            for transfers in component_transfers.values()
            for transfer in transfers
        ]
        extra_transfers.extend(
            self._build_sidecar_transfers(
                CacheTransferPhase.BACKUP_HOST,
                kv_transfer,
                component_transfers,
            )
        )
        return full_indices, extra_transfers

    def _reclaim_retraction_host(self, num_tokens: int) -> int:
        if self.disable:
            return 0
        return self.evict_host(num_tokens)

    def retraction_backup(self, req: Req) -> Optional[RetractionBackup]:
        """Back up device KV to the host pool; None when it cannot fit after reclaim."""
        assert req.seqlen > 1

        device_indices, extra_transfers = self._retraction_device_transfers(req)
        # Retraction backs device KV up to the host: a D->H write-back
        # channel, so it may use the P3 write-back reserve.
        host_indices = self.host_pool_group.alloc(len(device_indices), writeback=True)
        if host_indices is None:
            self._reclaim_retraction_host(len(device_indices))
            host_indices = self.host_pool_group.alloc(
                len(device_indices), writeback=True
            )
        if host_indices is None:
            return None

        resolved = self.host_pool_group.resolve_host_transfers(
            extra_transfers or None,
            primary_device_indices=device_indices,
            primary_host_indices=host_indices,
            writeback=True,
        )
        if resolved is None and extra_transfers:
            self.host_pool_group.free(host_indices)
            return None

        backup = RetractionBackup(
            host_indices=host_indices,
            pool_transfers=[replace(x, device_indices=None) for x in resolved or []]
            or None,
        )
        operation = CacheOperation(
            host_indices,
            device_indices,
            node_id=-1,
            pool_transfers=resolved,
        )
        try:
            write_host, write_device, write_pools = (
                self.cache_controller._move_write_operation(operation)
            )
            completion = self.cache_controller.l2_transfer_engine.submit_device_to_host(
                self.cache_controller._l2_transfers(
                    write_host, write_device, write_pools
                )
            )
            completion.finish_event.synchronize()
        except Exception:
            self.retraction_discard(backup)
            raise
        return backup

    def retraction_restore(self, req: Req, backup: RetractionBackup) -> None:
        device_indices, current_transfers = self._retraction_device_transfers(req)
        assert len(backup.host_indices) == len(device_indices), (
            f"Host backup has {len(backup.host_indices)} slots, but restore has "
            f"{len(device_indices)}"
        )

        current_by_name = {transfer.name: transfer for transfer in current_transfers}
        saved_by_name = {
            transfer.name: transfer for transfer in backup.pool_transfers or []
        }
        assert current_by_name.keys() == saved_by_name.keys(), (
            f"Host backup pools {set(saved_by_name)} do not match restore pools "
            f"{set(current_by_name)}"
        )
        restored_transfers = [
            replace(
                saved,
                device_indices=current_by_name[name].device_indices,
            )
            for name, saved in saved_by_name.items()
        ]
        resolved = self.cache_controller._resolve_device_transfers(
            restored_transfers or None,
            kv_device_indices=device_indices,
            kv_host_indices=backup.host_indices,
        )
        assert resolved is not None or not restored_transfers

        operation = CacheOperation(
            backup.host_indices,
            device_indices,
            node_id=-1,
            pool_transfers=resolved,
        )
        load_host, load_device, load_pools = self.cache_controller._move_op_indices(
            operation
        )
        completion = self.cache_controller.l2_transfer_engine.submit_host_to_device(
            self.cache_controller._l2_load_transfers(
                load_host, load_device, load_pools
            ),
            layer_num=self.cache_controller.layer_num,
        )
        completion.finish_event.synchronize()
        self.retraction_discard(backup)

    def retraction_discard(self, backup: RetractionBackup) -> None:
        self.host_pool_group.free(backup.host_indices)
        self.host_pool_group.release_transfers(backup.pool_transfers)

    # ---- HiCache: Backup / LoadBack ----

    def _execute_and_commit_kv_backup(
        self, action: BackupKV, write_back: bool = False
    ) -> int:
        """Run a backup action top-down, stopping at the first failed backup."""
        if self.buffer_pipeline is not None:
            # Buffer mode bypasses the host-backup contiguity below: nothing
            # is ever host-backuped here. Contiguity comes from end-to-end
            # FIFO ordering instead (BackupKV chains are parent-before-child
            # and every pipeline stage drains in order).
            for node_id in action.node_ids:
                self.buffer_pipeline.enqueue_backup_intent(
                    self.tree_core.node_by_id(node_id)
                )
            return 0
        written = 0
        for node_id in action.node_ids:
            device_value, comp_xfers = self.tree_core.build_backup_spec(node_id)
            # Overlapping chain actions may revisit nodes with Full KV already
            # backed up. Skip only when no transfer remains.
            if device_value.numel() == 0 and not comp_xfers:
                continue
            sidecar_xfers = self._build_backup_sidecar(device_value, comp_xfers)
            host_indices = self._execute_kv_backup(
                node_id, device_value, comp_xfers, sidecar_xfers
            )
            if host_indices is None:
                return 0
            self.tree_core.commit_backup(node_id, host_indices, comp_xfers)
            lock_params = None
            if not write_back:
                lock_params = self.inc_lock_ref(node_id).to_dec_params()
            self._track_write_through_node(node_id, lock_params)
            written = len(host_indices)
        return written

    def _build_backup_sidecar(self, device_value, comp_xfers):
        """Gather sidecar transfer spec."""
        kv_xfer = PoolTransfer(name=PoolName.KV, device_indices=device_value)
        return self._build_sidecar_transfers(
            CacheTransferPhase.BACKUP_HOST, kv_xfer, comp_xfers
        )

    def _execute_kv_backup(self, node_id, device_value, comp_xfers, sidecar_xfers):
        """Execute Backup action."""
        kv_tokens = len(device_value)
        host_avail = self.cache_controller.mem_pool_host.available_size()
        if host_avail < kv_tokens:
            needed = kv_tokens - host_avail
            if self.evict_host(needed) < needed:
                # F1: ACK backlog holds host_lock_ref on finished L3 writes;
                # drain the ready ACKs once, then retry eviction exactly once.
                self.drain_storage_control_queues_local()
                if self.evict_host(needed) < needed:
                    return None
        aux_xfers = [x for xfers in comp_xfers.values() for x in xfers]
        aux_xfers.extend(sidecar_xfers)
        return self.cache_controller.write(
            device_value, node_id=node_id, extra_pools=aux_xfers or None
        )

    def _track_write_through_node(
        self,
        node_id: NodeId,
        lock_params: Optional[DecLockRefParams],
    ) -> None:
        self.tree_core.mark_write_through_pending(node_id)
        self.ongoing_write_through[node_id] = _OngoingWriteThrough(
            node_id, lock_params, [node_id]
        )

    def _replace_pending_write_through_node(
        self, ack_id: int, old_node_id: NodeId, new_node_ids: list[NodeId]
    ) -> None:
        pending = self.ongoing_write_through.get(ack_id)
        if pending is None:
            return

        lock_node_id, lock_params, publish_node_ids = pending
        updated_node_ids = []
        replaced = False
        for node_id in publish_node_ids:
            if node_id == old_node_id:
                updated_node_ids.extend(new_node_ids)
                replaced = True
            else:
                updated_node_ids.append(node_id)

        if not replaced:
            return

        self.ongoing_write_through[ack_id] = _OngoingWriteThrough(
            lock_node_id,
            lock_params,
            updated_node_ids,
        )

    def _finish_write_through_ack(self, ack_id: int) -> None:
        if self.buffer_pipeline is not None:
            self.buffer_pipeline.finish_backup_ack(ack_id)
            return

        lock_node_id, lock_params, publish_node_ids = self.ongoing_write_through.pop(
            ack_id
        )
        self.tree_core.finish_write_through(publish_node_ids, ack_id)
        if lock_params is not None:
            self.dec_lock_ref(lock_node_id, lock_params)
        if self.enable_storage:
            # Back up each fragment: after a split, lock_node only holds the
            # suffix; the prefix fragment must be persisted as well. Deferred:
            # the gap-fill wait would re-enter the running drain (unbounded
            # recursion); _flush_pending_storage_writes persists the nodes
            # once the drain returns.
            self._pending_storage_writes.extend(publish_node_ids)

    # ---- P2-1c promotion admission (H→D capacity reservation) ----

    def _device_locked_tokens(self) -> int:
        """Derived device locked token count (capacity - available -
        evictable), the promotion budget's locked term (design §3.1).

        Mirrors the scheduler-side device_locked_tokens dispatcher on the
        FULL pool: whatever the pool can neither allocate nor evict (chain
        locks, in-flight DMA, running batches). The e11 dump arithmetic
        (1033 + 10231 + 21504 = 32768) validates the derivation.
        """
        return (
            self.token_to_kv_pool_allocator.size_full
            - self._component_available_size(ComponentType.FULL)
            - self.tree_core.full_evictable_size()
        )

    def _promotion_budget_fits(self, new_restore: int) -> bool:
        """Promotion budget predicate (design §3.1):
        locked + reserved + new_restore <= capacity - margin."""
        return promotion_budget_fits(
            locked=self._device_locked_tokens(),
            reserved=self.inflight_promotion_reserved,
            new_restore=new_restore,
            capacity=self.token_to_kv_pool_allocator.size_full,
            margin=self.promotion_margin_tokens,
        )

    def _promotion_pool_observation(self) -> str:
        """P2-1c expert ④: per-pool observation suffix for the [P2A]
        promotion events -- the FULL pool (the budgeted one) plus each aux
        pool's free/evictable/locked. Feeds the hybrid two-pool evaluation;
        per-component budgets are intentionally not implemented this round.
        """
        parts = [
            f"full_free={self._component_available_size(ComponentType.FULL)}",
            f"full_evictable={self.tree_core.full_evictable_size()}",
            f"full_locked={self._device_locked_tokens()}",
        ]
        if self.is_mamba_enabled:
            mamba_alloc = self.req_to_token_pool.mamba_allocator
            mamba_free = mamba_alloc.available_size()
            mamba_evict = self.tree_core.mamba_evictable_size()
            parts += [
                f"mamba_free={mamba_free}",
                f"mamba_evictable={mamba_evict}",
                f"mamba_locked={mamba_alloc.size - mamba_free - mamba_evict}",
            ]
        if self.is_swa_enabled:
            swa_alloc = self.token_to_kv_pool_allocator
            swa_free = swa_alloc.swa_available_size()
            swa_evict = self.tree_core.swa_evictable_size()
            parts += [
                f"swa_free={swa_free}",
                f"swa_evictable={swa_evict}",
                f"swa_locked={swa_alloc.size_swa - swa_free - swa_evict}",
            ]
        return " " + " ".join(parts)

    def _release_promotion_reservation(
        self, amount: int, node_id: int, cause: str
    ) -> None:
        """Release a promotion reservation (design §3.3 E3/E4 + exception +
        finalizer paths). The counter must never go negative: on underflow
        the violation is logged, not silently swallowed, and the counter is
        clamped to 0 so a bug cannot jam the budget forever (R3).
        """
        if amount <= 0:
            return
        if self.inflight_promotion_reserved < amount:
            logger.error(
                "P2-1c promotion reservation underflow: release %d > held %d "
                "(node %d, cause=%s)",
                amount,
                self.inflight_promotion_reserved,
                node_id,
                cause,
            )
            self.inflight_promotion_reserved = 0
            return
        self.inflight_promotion_reserved -= amount
        self._promotion_release_count += 1
        logger.info(
            "[P2A] ts_ms=%d evt=promotion_release n=%d cause=%s reserved=%d%s",
            int(time.time() * 1000),
            amount,
            cause,
            self.inflight_promotion_reserved,
            self._promotion_pool_observation(),
        )

    def _transfer_promotion_reservation(self, amount: int, node_id: int) -> None:
        """Ownership transfer (expert ①): once the loaded span's allocation
        and load lock are established (post cache_controller.load + ongoing
        registration), the span sits inside the derived locked term --
        keeping it in reserved too would double-count the same tokens for
        the whole DMA window and compress all other promotions. The transfer
        is the reservation -> lock ownership handover: the counter then only
        covers reservations whose load has not started.
        """
        if amount <= 0:
            return
        if self.inflight_promotion_reserved < amount:
            logger.error(
                "P2-1c promotion reservation underflow on transfer: %d > held %d "
                "(node %d)",
                amount,
                self.inflight_promotion_reserved,
                node_id,
            )
            self.inflight_promotion_reserved = 0
            return
        self.inflight_promotion_reserved -= amount
        self._promotion_transfer_count += 1
        logger.info(
            "[P2A] ts_ms=%d evt=promotion_transfer n=%d reserved=%d%s",
            int(time.time() * 1000),
            amount,
            self.inflight_promotion_reserved,
            self._promotion_pool_observation(),
        )

    def _finalize_load_back_entry(self, entry: _OngoingLoadBack, cause: str) -> None:
        """Release a registered load-back entry's residual reservation and
        locks exactly once (expert ② finalizer: success ACK, failure, cancel,
        fatal, and shutdown all terminate here or in the pre-registration
        release paths). The caller pops the entry from ongoing_load_back
        before invoking this, so exactly-once is structural.
        """
        if entry.reserved_tokens > 0:
            self._release_promotion_reservation(
                entry.reserved_tokens, entry.node_id, cause
            )
        self.dec_lock_ref(entry.node_id, entry.lock_params)
        self.dec_host_lock_ref(entry.node_id, entry.host_lock_params)

    def _release_all_load_backs(self, cause: str) -> None:
        """Release every in-flight load-back entry (shutdown / fatal
        cleanup). Each entry is popped here, so a later ack drain finds
        nothing to release."""
        for ack_id in list(self.ongoing_load_back):
            entry = self.ongoing_load_back.pop(ack_id)
            self._finalize_load_back_entry(entry, cause=cause)

    def load_back(
        self,
        node_id: NodeId,
        mem_quota: Optional[int] = None,
        req=None,
    ) -> bool:
        """Load evicted KV data from host back to device (H→D)."""
        if self.cache_controller is None:
            return False

        # P2-1c checkpoint 1 (entry gate; design §3.2): reserve-before-lock
        # admission. The budget holds `locked + reserved + est <= capacity -
        # margin`; est is the host-only span about to be promoted (the
        # request's device prefix is already inside the derived locked term,
        # so no double/lost count here). Rejecting before any lock costs
        # nothing (no host anchor, no chain lock, no spec build) and flows
        # into the existing RESTORE_DENIED -> WAIT[DEVICE_QUOTA] path (M1b).
        # est == 0 (pure aux restore) skips the FULL-KV budget: aux pools
        # have their own budget (rem_swa_tokens).
        est = (
            req.host_hit_length
            if (req is not None and req.host_hit_length > 0)
            else 0
        )
        if est > 0 and not self._promotion_budget_fits(est):
            self._promotion_denied_count += 1
            logger.info(
                "[P2A] ts_ms=%d evt=promotion_denied rid=%s est=%d locked=%d "
                "reserved=%d margin=%d%s",
                int(time.time() * 1000),
                req.rid if req is not None else None,
                est,
                self._device_locked_tokens(),
                self.inflight_promotion_reserved,
                self.promotion_margin_tokens,
                self._promotion_pool_observation(),
            )
            return False

        host_anchor_params = self.inc_host_lock_ref(node_id).to_dec_params()

        # Lock the path before building transfers (the aux build can evict).
        result = self.inc_lock_ref(node_id)
        ancestor_lock_params = result.to_dec_params()

        # Let each component pre-allocate per-request state for the load-back;
        # the finally below lets components recover it unless the load succeeds.
        preps: dict[ComponentType, PrepareLoadBackResult] = {
            comp.component_type: comp.prepare_load_back(node_id, req=req)
            for comp in self._components_tuple
        }
        success = False
        try:
            success = self._load_back_transfers(
                node_id=node_id,
                mem_quota=mem_quota,
                req=req,
                result=result,
                ancestor_lock_params=ancestor_lock_params,
                host_anchor_params=host_anchor_params,
            )
            return success
        finally:
            for comp in self._components_tuple:
                comp.finalize_load_back(req, preps[comp.component_type], success)

    def _load_back_transfers(
        self,
        *,
        node_id: NodeId,
        mem_quota: Optional[int],
        req,
        result: IncLockRefResult,
        ancestor_lock_params: DecLockRefParams,
        host_anchor_params: DecLockRefParams,
    ) -> bool:
        # Build the KV + per-component aux transfers.
        kv_xfer, comp_xfers = self.tree_core.build_load_back_spec(node_id, req=req)
        kv_tokens = len(kv_xfer.host_indices)
        sidecar_xfers = self._build_sidecar_transfers(
            CacheTransferPhase.LOAD_BACK, kv_xfer, comp_xfers
        )

        # Skip if there is nothing to load, or if the Full-KV transfer is too
        # small / exceeds memory quota. Aux transfers should still run even
        # when the Full-KV load is skipped by thresholding. max(1, ...): an
        # entirely empty spec (e.g. foreign-pin rejection) must never report
        # success, even at load_back_threshold <= 0.
        if (kv_tokens < max(1, self.load_back_threshold) and not comp_xfers) or (
            mem_quota is not None and kv_tokens > mem_quota + result.delta
        ):
            self.dec_lock_ref(node_id, ancestor_lock_params)
            self.dec_host_lock_ref(node_id, host_anchor_params)
            return False

        # P2-1c checkpoint 2 (precise gate + reserve; design §3.2): the
        # authoritative budget check on the exact spec size, placed BEFORE
        # evict_for_alloc -- a budget rejection never starts the walker,
        # which is the mechanism that drops forced_drop (Test A' criterion).
        # kv_tokens == 0 (pure aux restore) skips the FULL-KV budget. The
        # reservation happens here, before the device load; every later exit
        # releases it exactly once (E3/E4 inline, success transfers it to
        # lock ownership, exceptions via the finally below).
        reserved_held = 0
        try:
            if kv_tokens > 0 and not self._promotion_budget_fits(kv_tokens):
                self._promotion_denied_exact_count += 1
                logger.info(
                    "[P2A] ts_ms=%d evt=promotion_denied_exact rid=%s kv=%d "
                    "locked=%d reserved=%d margin=%d%s",
                    int(time.time() * 1000),
                    req.rid if req is not None else None,
                    kv_tokens,
                    self._device_locked_tokens(),
                    self.inflight_promotion_reserved,
                    self.promotion_margin_tokens,
                    self._promotion_pool_observation(),
                )
                self.dec_lock_ref(node_id, ancestor_lock_params)
                self.dec_host_lock_ref(node_id, host_anchor_params)
                return False
            if kv_tokens > 0:
                self.inflight_promotion_reserved += kv_tokens
                self._promotion_reserve_count += 1
                if (
                    self.inflight_promotion_reserved
                    > self._promotion_inflight_peak
                ):
                    self._promotion_inflight_peak = (
                        self.inflight_promotion_reserved
                    )
                reserved_held = kv_tokens
                logger.info(
                    "[P2A] ts_ms=%d evt=promotion_reserve n=%d rid=%s reserved=%d%s",
                    int(time.time() * 1000),
                    kv_tokens,
                    req.rid if req is not None else None,
                    self.inflight_promotion_reserved,
                    self._promotion_pool_observation(),
                )

            avail = self._component_available_size(ComponentType.FULL)
            if avail < kv_tokens:
                needed = kv_tokens - avail
                self.evict_for_alloc(EvictParams(num_tokens=needed))
                if self._component_available_size(ComponentType.FULL) < kv_tokens:
                    # E3: eviction could not cover the span; the load never
                    # started, so the reservation is returned.
                    self._release_promotion_reservation(
                        reserved_held, node_id, "evict_fail"
                    )
                    reserved_held = 0
                    self.dec_lock_ref(node_id, ancestor_lock_params)
                    self.dec_host_lock_ref(node_id, host_anchor_params)
                    return False

            # Load H→D
            aux_xfers = [x for xfers in comp_xfers.values() for x in xfers]
            aux_xfers.extend(sidecar_xfers)
            device_indices = self.cache_controller.load(
                host_indices=kv_xfer.host_indices,
                node_id=node_id,
                extra_pools=aux_xfers or None,
            )

            self.dec_lock_ref(node_id, ancestor_lock_params)
            if device_indices is None:
                # E4: the load failed to allocate; the span is still free,
                # so the reservation is returned.
                self._release_promotion_reservation(
                    reserved_held, node_id, "load_fail"
                )
                reserved_held = 0
                self.dec_host_lock_ref(node_id, host_anchor_params)
                return False

            # Commit the loaded KV back onto the node + apply its emitted
            # actions.
            self._apply_cache_actions(
                self.tree_core.commit_load_back(
                    node_id, device_indices, kv_xfer, comp_xfers
                )
            )

            self.ongoing_load_back[node_id] = _OngoingLoadBack(
                node_id,
                self.inc_lock_ref(node_id).to_dec_params(),
                host_anchor_params,
                0,  # residual reservation: transferred to lock ownership below
            )
            # Ownership transfer (expert ①): the span is now allocated AND
            # locked, so the derived locked term covers it from here until
            # the ack drain; keeping the reservation until the ack would
            # double-count the same tokens for the whole DMA window. The
            # reservation counts only the not-yet-locked part from now on.
            self._transfer_promotion_reservation(reserved_held, node_id)
            reserved_held = 0
            return True
        finally:
            if reserved_held > 0:
                # Exception between the reserve and its transfer/release: the
                # load never established lock ownership, so the reservation
                # must be returned (expert ② explicit-failure path).
                self._release_promotion_reservation(
                    reserved_held, node_id, "exception"
                )

    def _build_sidecar_transfers(
        self,
        phase: CacheTransferPhase,
        kv_xfer: PoolTransfer,
        comp_xfers: dict[ComponentType, list[PoolTransfer]],
    ) -> list[PoolTransfer]:
        transfers: list[PoolTransfer] = []
        for spec in self.sidecar_pool_specs:
            if spec.indices_from_pool == PoolName.KV:
                indices_source = kv_xfer
            else:
                source_component = {
                    PoolName.SWA: ComponentType.SWA,
                    PoolName.MAMBA: ComponentType.MAMBA,
                }.get(spec.indices_from_pool)
                if source_component is None:
                    raise AssertionError(
                        f"Unsupported sidecar indices source pool "
                        f"{spec.indices_from_pool}."
                    )
                matching_sources = comp_xfers.get(source_component, ())
                if not matching_sources:
                    continue
                indices_source = matching_sources[0]
                if indices_source.name != spec.indices_from_pool:
                    raise AssertionError(
                        f"Sidecar indices source pool {spec.indices_from_pool} "
                        f"resolved to {indices_source.name} during {phase}."
                    )

            indices = (
                indices_source.device_indices
                if phase == CacheTransferPhase.BACKUP_HOST
                else indices_source.host_indices
            )
            defer_kv_sidecar = (
                phase == CacheTransferPhase.PREFETCH
                and spec.indices_from_pool == PoolName.KV
            )
            if (indices is None or len(indices) == 0) and not defer_kv_sidecar:
                continue
            transfers.append(
                PoolTransfer(
                    name=spec.pool_name,
                    keys=indices_source.keys,
                    hit_policy=spec.hit_policy,
                    indices_from_pool=spec.indices_from_pool,
                )
            )
        return transfers

    def _flush_pending_storage_writes(self) -> None:
        """Persist every node whose D->H write acked while its chain was not
        yet written to L3. The ack path only defers (see
        _finish_write_through_ack), so this runs outside any drain. Nodes
        deleted since their deferral (eviction/drop/tombstone cleanup) are
        skipped, not persisted."""
        while self._pending_storage_writes:
            node_id = self._pending_storage_writes.pop(0)
            if not self.tree_core.node_exists(node_id):
                self._skip_stale_storage_persist(node_id)
                continue
            try:
                self.write_backup_storage(node_id)
            except KeyError:
                # Backstop: the node or a gap ancestor died between the
                # existence check and the arena lookups; nothing to persist.
                self._skip_stale_storage_persist(node_id)
        # P3 (phase2-p3-fix): deferred-ACK reconciliation. A node whose L3
        # write acked while its parent chain was not persisted is left
        # deferred (storage_acked && !storage_persisted) by
        # advance_storage_persisted. If its parent chain is later cleared
        # (revoke-miss clear_storage_durable) or physically deleted
        # (eviction/tombstone), nothing re-promotes it without a fresh IO
        # -- the permanent frontier HOL (T13 60s timeout). This pass
        # rescans deferred_acked_nodes each drain and re-fills each
        # surviving node's chain from the nearest persisted ancestor / root
        # (collect_storage_gap), then re-promotes through a real write ack.
        # Idempotent: collect_storage_gap skips already-written nodes,
        # write_backup_storage skips is_storage_written / dead nodes, and
        # advance_storage_persisted returns early for persisted nodes; a
        # single pass re-fills each broken chain once. Reconciliation never
        # sets storage_persisted itself -- promotion stays a real-ack /
        # real-restore fact.
        self._reconcile_deferred_acked()

    def _reconcile_deferred_acked(self) -> None:
        """P3 A3: re-fill and re-promote every deferred-ACK node (acked but
        not persisted) whose chain is broken by a cleared / deleted parent.
        One ancestors-first sweep per outermost _flush_pending_storage_writes;
        per-node gap fill is idempotent (see _flush_pending_storage_writes).
        Re-entrancy guarded: write_backup_storage itself calls
        _flush_pending_storage_writes at its tail, so without a depth guard a
        deferred node that is not resolved in one fill (ack in flight, or an
        unfillable chain) would re-enter this scan from inside itself,
        unboundedly."""
        if getattr(self, "_reconcile_depth", 0) > 0:
            return
        self._reconcile_depth = getattr(self, "_reconcile_depth", 0) + 1
        try:
            self._reconcile_deferred_acked_inner()
        finally:
            self._reconcile_depth -= 1

    def _reconcile_deferred_acked_inner(self) -> None:
        if not self.enable_storage or self.cache_controller is None:
            return
        deferred = self.tree_core.deferred_acked_nodes()
        if not deferred:
            return
        for node_id in deferred:
            if not self.tree_core.node_exists(node_id):
                self._skip_stale_storage_persist(node_id)
                continue
            try:
                # 1) Fill any broken parent gap: re-write the nodes whose
                #    parent chain was physically deleted (tombstone / host
                #    eviction) from the nearest persisted ancestor / root.
                #    collect_storage_gap skips already-written nodes, so this
                #    is a no-op for a node whose write is already complete.
                self.write_backup_storage(node_id)
            except KeyError:
                # A gap ancestor died between the scan and the arena lookups.
                self._skip_stale_storage_persist(node_id)
                continue
            # 2) Re-run promotion on the already-acked node. Its write is
            #    real and acked; it was only deferred because the parent
            #    chain was not contiguous when the ack arrived. Now that the
            #    chain is contiguous (parent persisted, or the node re-anchored
            #    to root after its parent was deleted), re-invoking the same
            #    promotion entry the ack drain uses promotes the node and its
            #    acked descendants. This is the reverse-path repair -- it does
            #    not fabricate durability (advance_storage_persisted only
            #    promotes when the parent chain is contiguous), and it is
            #    idempotent (advance returns early for an already-persisted
            #    node). Waking frontier waiters mirrors the ack drain: a
            #    freshly promoted anchor can serve its waiters, closing the
            #    loop that the T13 timeout path used to cut short.
            promoted = self.tree_core.advance_storage_persisted(node_id)
            for promoted_id in promoted:
                self._wake_frontier_waiters(promoted_id)

    def _skip_stale_storage_persist(self, node_id: NodeId) -> None:
        """Count and log a deferred L3 persist whose node is no longer alive."""
        self._storage_persist_skip_count += 1
        logger.debug("stale L3 persist skipped: node %d no longer alive", node_id)

    def write_backup_storage(self, node_id: NodeId) -> None:
        """Persist node_id's KV chain to L3, completing ancestor gaps first.

        L3 reads only hit when every page hash from the recoverable anchor
        down to the node exists in storage. write_back evicts leaves without
        ever backing up their ancestors, so writing only the leaf would
        persist a suffix with a missing prefix. Fill the anchor->node gap:
        host-backup the unbacked gap nodes, wait out their D->H acks (their
        ack path re-enters this method per node and submits those L3 writes),
        then submit the remaining gap nodes in ancestors-first order."""
        if not self.enable_storage or self.cache_controller is None:
            return
        gap = self.tree_core.collect_storage_gap(node_id)
        # Gap nodes may have been deleted since the deferral: the arena
        # lookup below would KeyError on a dead id. Nodes deleted by this
        # loop's own D->H backups are re-filtered per iteration.
        gap = [nid for nid in gap if self.tree_core.node_exists(nid)]
        if not gap:
            return
        for nid in gap:
            if not self.tree_core.node_exists(nid):
                self._skip_stale_storage_persist(nid)
                continue
            if not self.tree_core.is_backuped(nid):
                # P0 (phase2-backupassert): a gap node may be unbacked AND
                # host-only (device value already released by an eviction /
                # hollow / forced-miss, or inserted host-only). `is_backuped`
                # alone cannot distinguish "unbacked with a device value"
                # (needs a D->H backup) from "unbacked host-only" (device
                # value gone; host copy is the only KV). Do not run the D->H
                # backup when there is no device value to copy -- the
                # _build_backup_spec assert would fire. Skip and let the
                # storage-write loop below persist the host copy to L3.
                if self.tree_core.get_component_device_value(
                    nid, BASE_COMPONENT_TYPE
                ) is None:
                    self._storage_gap_skipped_d2h_count += 1
                    continue
                self._execute_and_commit_kv_backup(BackupKV([nid]), write_back=False)
        # The D->H backups above evict_host when host space is tight; host
        # eviction deletes host-only leaves, which may be gap nodes. Re-filter
        # before the drain and L3 writes.
        gap = [nid for nid in gap if self.tree_core.node_exists(nid)]
        # Blocking, but only in the write_back path, which already blocks on
        # D->H acks in writing_check; the write_through path never has an
        # unbacked gap node. Ack completion only defers L3 persists (see
        # _finish_write_through_ack), so the drain never re-enters here.
        while any(nid in self.ongoing_write_through for nid in gap):
            self._drain_write_through_acks()
        for nid in gap:
            if not self.tree_core.node_exists(nid):
                self._skip_stale_storage_persist(nid)
                continue
            if not self.tree_core.is_backuped(nid):
                # P0 (phase2-backupassert): a gap node with neither a device
                # value nor a host copy (a forced-miss tombstone / hollow with
                # no KV in any tier) has nothing to persist. It must not be
                # written to L3 as if it carried content (would fabricate a
                # durable chain for a node that holds no KV) -- skip it as the
                # explicit invalid / un-backupable state and record the reason.
                self._storage_gap_skipped_nokv_count += 1
                continue
            if not self.tree_core.is_storage_written(nid):
                self._write_backup_storage_node(nid)
        # Nodes deferred by the acks drained above completed their D->H DMAs;
        # persist them now, before a later eviction can reclaim their host
        # copies. Their chains were either just submitted or are filled by
        # the nested calls.
        self._flush_pending_storage_writes()

    def _write_backup_storage_node(self, node_id: NodeId) -> None:
        """Submit one node's KV to L3 and register its ack entry."""
        cc = self.cache_controller
        if cc is not None and cc.storage_failure_reason is not None:
            # Storage degraded: keep the node host-only (no L3 write, no ack
            # entry); the next persist flush skips it again at this gate.
            return
        spec = self.tree_core.build_storage_backup_spec(
            node_id, self.hicache_storage_pass_prefix_keys
        )
        if spec is None:
            return

        kv_xfer = PoolTransfer(
            name=PoolName.KV,
            host_indices=spec.host_value,
            keys=spec.hash_value,
        )
        sidecar_xfers = self._build_sidecar_transfers(
            CacheTransferPhase.BACKUP_STORAGE, kv_xfer, spec.comp_xfers
        )
        aux_xfers = [x for xfers in spec.comp_xfers.values() for x in xfers]
        aux_xfers.extend(sidecar_xfers)

        # T38C-PROBE (L3 write-chain observation; log-only, gated on
        # /tmp/t38c-on). Records the write chain's full-64-hex seed and first
        # page hash so a live run can be compared byte-for-byte against the
        # read-side pc_prefetch_enter / pc_storage_query (full 64-hex). The
        # write chain is seeded by the parent's last hash
        # (compute_node_hash_values -> parent.hash_value[-1]).
        try:
            _wparent = self.tree_core.node_by_id(node_id).parent
            _wseed = (
                _wparent.get_last_hash_value()
                if _wparent is not None
                else None
            )
            _t38c_log({
                "evt": "pc_write_seed",
                "node_id": str(node_id),
                "write_seed": _wseed or "",
                "page0_hash": spec.hash_value[0] if spec.hash_value else "",
                "page1_hash": spec.hash_value[1] if len(spec.hash_value or []) > 1 else "",
                "n_pages": len(spec.hash_value or []),
            })
        except Exception:
            pass

        operation_id = self.cache_controller.write_storage(
            spec.host_value,
            spec.token_ids,
            spec.hash_value,
            spec.prefix_keys,
            extra_pools=aux_xfers or None,
            node_id=node_id,
        )
        self.ongoing_backup[operation_id] = (
            node_id,
            self.inc_host_lock_ref(node_id).to_dec_params(),
        )
        # Dedupe guard at submission: the re-entrant gap walk must not
        # resubmit a node whose write is already in flight.
        self.tree_core.mark_storage_written(node_id)

    def is_backuped(self, node_id: NodeId) -> bool:
        return self.tree_core.is_backuped(node_id)

    def prefetch_gate_ok(self, node_id: NodeId, buffer_mode: bool = False) -> bool:
        """P2-1 M2 prefetch gate: an anchor is prefetch-issuable when it is
        host-backuped (the cache-mode write-through contiguity), the root, or
        L3-durable (the durable copy the T11/T12 wake predicates rely on;
        P2-1 e14 extends it from written+acked to restored chains).
        Gate and wake must agree or every wake re-registers the wait (the
        frontier spin). Buffer mode reads by hash, never by anchor backup."""
        return (
            self.is_backuped(node_id)
            or self.is_root(node_id)
            or self.is_l3_durable(node_id)
            or (buffer_mode and self.get_last_hash_value(node_id) is not None)
        )

    def is_root(self, node_id: NodeId) -> bool:
        return self.tree_core.is_root(node_id)

    def node_exists(self, node_id: NodeId) -> bool:
        """Whether the node id still resolves in the arena (eviction/drop may
        have deleted it after a deferred reference was recorded). P2-1 M1b/M2
        guard: stale anchors are never dereferenced."""
        return self.tree_core.node_exists(node_id)

    def is_storage_persisted(self, node_id: NodeId) -> bool:
        """Whether the node is a persisted storage anchor: its L3 write acked
        and its parent chain contiguous to the root (the frontier-wake
        condition, P2-1 M2 T12)."""
        return self.tree_core.is_storage_persisted(node_id)

    def is_l3_durable(self, node_id: NodeId) -> bool:
        """Whether the node's KV is confirmed present in L3: written+ACK or
        restored successfully (P2-1 e14). The unified hollow/eviction and
        gate/wake predicate; unlike is_storage_persisted no parent-chain
        contiguity is required."""
        return self.tree_core.is_l3_durable(node_id)

    def l3_publish_epoch(self) -> int:
        """The current monotonic L3 durable/publish epoch (P3 M3): bumped
        on every durability advance (write ack promotion / restore
        read-back). The scheduler's l3_publish causal-epoch signal; a
        value that never moved means the L3 coverage a NO_L3-parked rid
        missed on is unchanged, so the park does not clear."""
        return self.tree_core.l3_publish_epoch()

    def chain_backup_frontiers(
        self,
        node_id: NodeId,
        requested_pages: int,
        page_hashes: list[str],
    ) -> tuple[int, int]:
        """The chain's backup frontiers under node_id, in request coordinates
        (0..requested_pages): durable = deepest persisted page end on the
        request branch (the acked+contiguous write frontier), target = the
        end the in-flight backup pipeline is going to reach (durable or an
        in-flight write's request block end).

        The T15 park predicate's inputs: a partial hit parks only when the
        pipeline is targeted to cover the request's end (target >=
        requested) and the durable frontier is still behind it -- the wake
        (durable >= requested) then serves one re-lookup and one full
        restore. A pipeline that stops short of the request end (chain
        growth, a dropped-without-backup tail, a sibling chain's write)
        shows target < requested and is not parked: the current restore-or-
        recompute behavior applies. An anchor evicted since the lookup is
        reported as (requested_pages, 0): nothing to wait on, and a park
        would wake immediately (backup_wait_ready self-heals a deleted
        anchor to True) -- the per-pass re-issue loop returns."""
        if not self.tree_core.node_exists(node_id):
            return requested_pages, 0
        pos = {h: i for i, h in enumerate(page_hashes)}
        durable = self.tree_core.persisted_chain_frontier(
            node_id, pos, requested_pages
        )
        target = durable
        for op_node_id, _lock_params in self.ongoing_backup.values():
            block = self.tree_core.page_block_in_request(
                op_node_id, pos, requested_pages
            )
            if block is not None:
                target = max(target, block[1])
        return durable, target

    def backup_wait_ready(self, req_id: str) -> bool:
        """Whether a parked T15 request's backup-completion wait is over:
        the chain's durable frontier has crossed the request's end
        (backup_wake_applies). Re-computed every scheduler pass; the ACK
        drain advances the frontier, so the wake is ACK-driven. An anchor
        deleted since the park self-heals to True: the re-issue re-matches
        from the root and the re-lookup decides."""
        span = self._backup_wait_spans.get(req_id)
        if span is None:
            return False
        anchor, requested_pages, page_hashes = span
        if not self.tree_core.node_exists(anchor):
            return True
        pos = {h: i for i, h in enumerate(page_hashes)}
        durable = self.tree_core.persisted_chain_frontier(
            anchor, pos, requested_pages
        )
        return backup_wake_applies(durable, requested_pages)

    def demand_restore_inflight(self) -> int:
        """In-flight DEMAND_RESTORE re-issues (the T15 wake path), for the
        bounded-concurrency gate demand_restore_available."""
        return len(self._demand_restore_rids)

    def reserve_prefetch(self, req_id: str, tokens: int, kind: PrefetchKind) -> None:
        """P3 M5: charge one issued prefetch against the inflight budgets.

        Cache mode only (buffer mode grants occupancy at hit-alloc, sized
        to the hit, and never charges the speculative counter). The
        reservation is consumed exactly once by release_prefetch; the
        speculative counter grows only for SPECULATIVE issues, so the
        Ready-Horizon-off mode (no reservations at all) never touches it."""
        assert req_id not in self._prefetch_reservations, (
            f"double reserve for {req_id}: the previous prefetch was never "
            "released (an M5 exactly-once violation)"
        )
        self._prefetch_reservations[req_id] = PrefetchReservation(tokens, kind)
        if kind is PrefetchKind.SPECULATIVE:
            cc = self.cache_controller
            cc.inflight_speculative_tokens += tokens

    def release_prefetch(self, req_id: str, reason: str) -> None:
        """P3 M5: the single exactly-once release of a prefetch's
        inflight-budget charge.

        Every ongoing_prefetch removal point -- finalize, revoke, abort,
        hybrid discard, detach -- exits through here (upstream #31445
        abort-leak guard). Idempotent: a second release or a release of an
        unreserved rid (Ready Horizon off) is a no-op. `reason` names the
        removal path at the call site. The physical counter is released by
        the existing per-site accounting; this helper owns the speculative
        counter and the `released` marker."""
        reservation = self._prefetch_reservations.get(req_id)
        if reservation is None or reservation.released:
            return
        reservation.released = True
        del self._prefetch_reservations[req_id]
        if reservation.kind is PrefetchKind.SPECULATIVE:
            cc = self.cache_controller
            cc.inflight_speculative_tokens = max(
                0, cc.inflight_speculative_tokens - reservation.tokens
            )

    def frontier_anchor_ready(self, node_id: NodeId) -> bool:
        """P2-1 M2 T11: whether a FRONTIER waiter's anchor can serve a
        re-issued prefetch. Mirrors _wake_frontier_waiters: the chain is
        L3-durable (written+acked or restored, P2-1 e14), or the anchor was
        deleted and a re-match falls back to root (self-heal, design §3.3).
        Deliberately not is_backuped: the host copy commits at D->H
        submission, before the L3 write, and a wake there re-issues the
        prefetch into an empty L3 (the M2 premature-wake bug that kept
        frontier_wake at zero)."""
        if not self.tree_core.node_exists(node_id):
            return True
        return self.tree_core.is_l3_durable(
            node_id
        ) or self.tree_core.is_root(node_id)

    def get_last_hash_value(self, node_id: NodeId) -> Optional[str]:
        return self.tree_core.get_last_hash_value(node_id)

    def get_prefix_hash_values(self, node_id: NodeId) -> list[str]:
        return self.tree_core.get_prefix_hash_values(node_id)

    def query_storage_hit_length(
        self,
        last_host_node_id: NodeId,
        new_input_tokens: list[int],
        last_hash: Optional[str] = None,
        prefix_keys: Optional[list[str]] = None,
    ) -> int:
        """Synchronously probe L3 storage for the reusable prefix length."""
        if (
            not self.enable_storage
            or self.cache_controller is None
            or self.cache_controller.prefetch_rate_limited()
            or self.cache_controller.storage_failure_reason is not None
        ):
            return 0

        extra_key, cache_salt = self.tree_core.prefetch_anchor_info(last_host_node_id)
        prefetch_key = RadixKey(
            new_input_tokens,
            extra_key=extra_key,
            is_bigram=self.tree_core.is_eagle,
            cache_salt=cache_salt,
        ).page_aligned(self.page_size)
        if len(prefetch_key) < self.prefetch_threshold:
            return 0

        from sglang.srt.mem_cache.hybrid_cache.hybrid_cache_controller import (
            PrefetchOperation,
        )

        operation = PrefetchOperation(
            "__storage_hit_query__",
            prefetch_key,
            last_hash,
            prefix_keys,
        )
        _, storage_hit_count = self.cache_controller._storage_hit_query(operation)
        storage_hit_count_tensor = torch.tensor(storage_hit_count, dtype=torch.int)
        self._all_reduce_attn_groups(
            storage_hit_count_tensor, torch.distributed.ReduceOp.MIN
        )
        storage_hit_count = storage_hit_count_tensor.item()
        storage_hit_count -= storage_hit_count % self.page_size
        return storage_hit_count

    def _prefetch_budget_denied(self, demand_restore: bool) -> bool:
        """P3 Ready Horizon (M1): the two-track inflight-budget admission.

        SPECULATIVE issues are bounded by the physical inflight budget
        (prefetch_rate_limited, all kinds) and, under Ready Horizon, by
        the speculative sub-budget. DEMAND restores are bounded by the
        physical budget only, and only under Ready Horizon -- off-mode
        keeps the pre-P3 T15 ticket semantics (demand bypasses the budget
        entirely, speculative checks the single physical track)."""
        cc = self.cache_controller
        physical_full = cc.prefetch_rate_limited()
        if demand_restore:
            return self.enable_ready_horizon and physical_full
        return physical_full or (
            self.enable_ready_horizon and cc.prefetch_speculative_rate_limited()
        )

    def prefetch_from_storage(
        self,
        req_id: str,
        last_host_node_id: NodeId,
        new_input_tokens: list[int],
        last_hash: Optional[str] = None,
        prefix_keys: Optional[list[str]] = None,
        matched_prefix_tokens: Optional[list[int]] = None,
        demand_restore: bool = False,
    ) -> Optional[str]:
        """Returns an outcome code for the P2-1 M1b state machine:
        "issued" / "declined_rate_limited" / "declined_too_short" /
        "forfeited_alloc_failed" / "skipped_no_l3" / "skipped_dup" (None
        pre-M1b semantics preserved as the skip codes).

        demand_restore marks a T15 wake re-issue (P2-IO R2): it holds a
        DEMAND_RESTORE ticket, bypassing only the speculative
        PREFETCH_BUDGET check -- every other gate (host staging alloc,
        cancellation, admission) applies as for any prefetch. The ticket
        is granted at issue and released when the prefetch leaves
        ongoing_prefetch."""
        if (
            not self.enable_storage
            or self.cache_controller is None
            or self.cache_controller.storage_failure_reason is not None
        ):
            try:
                _t38c_log({"evt": "pc_outcome", "phase": "entry",
                           "rid": req_id,
                           "outcome": "skipped_no_l3",
                           "storage_enabled": bool(self.enable_storage)})
            except Exception:
                pass
            return "skipped_no_l3"

        buffer_mode = self.host_memory_mode == "buffer_only"
        extra_key, cache_salt = self.tree_core.prefetch_anchor_info(last_host_node_id)
        prefetch_key = RadixKey(
            new_input_tokens,
            extra_key=extra_key,
            is_bigram=self.tree_core.is_eagle,
            cache_salt=cache_salt,
        ).page_aligned(self.page_size)
        prefetch_length = len(prefetch_key)
        stats = self._prefetch_outcome_stats
        if prefetch_length > 0:
            stats["attempts"] += 1
        try:
            _t38c_log({"evt": "pc_outcome", "phase": "issue", "rid": req_id,
                       "outcome": "attempt",
                       "prefetch_length": prefetch_length,
                       "prefetch_threshold": self.prefetch_threshold,
                       "suffix_len": len(new_input_tokens),
                       "counters": dict(stats)})
        except Exception:
            pass
        if prefetch_length < self.prefetch_threshold:
            if prefetch_length > 0:
                stats["declined_too_short"] += 1
            try:
                _t38c_log({"evt": "pc_outcome", "phase": "issue", "rid": req_id,
                           "outcome": "declined_too_short",
                           "counters": dict(stats)})
            except Exception:
                pass
            # A too-short/fully-matched suffix can become a full recompute if
            # the device match evicts while queued; arm the paced retry.
            self._storage_prefetch_missed_rids.add(req_id)
            _log_restore_disposition(req_id, "RECOMPUTE", prefetch_length, 0, "too_short")
            return "declined_too_short"
        if not buffer_mode and self._prefetch_budget_denied(demand_restore):
            stats["declined_rate_limited"] += 1
            try:
                _t38c_log({"evt": "pc_outcome", "phase": "issue", "rid": req_id,
                           "outcome": "declined_rate_limited", "site": "issue",
                           "counters": dict(stats)})
            except Exception:
                pass
            self._storage_prefetch_missed_rids.add(req_id)
            # The state machine parks the rid in WAIT[PREFETCH_BUDGET]
            # (T2): the T11 capacity wake re-issues when the budget frees,
            # so this decline is retryable, not a recompute (the e13
            # disposition label contradicted the observed restore_retry
            # cause=capacity wakes).
            _log_restore_disposition(req_id, "WAIT", prefetch_length, 0, "denied_rate_limit")
            return "declined_rate_limited"
        if req_id in self.ongoing_prefetch or (
            buffer_mode and self.buffer_pipeline.has_staged(req_id)
        ):
            try:
                _t38c_log({"evt": "pc_outcome", "phase": "issue", "rid": req_id,
                           "outcome": "skipped_dup",
                           "counters": dict(stats)})
            except Exception:
                pass
            # A fetch (or an unconsumed hold) already exists for this rid;
            # overwriting would leak its staging slots.
            return "skipped_dup"

        # Buffer mode holds no tree state during the fetch: buffers are
        # operation-owned, so the anchor needs no pin.
        anchor_lock_params = (
            None
            if buffer_mode
            else self.inc_host_lock_ref(last_host_node_id).to_dec_params()
        )
        comp_xfers: dict[ComponentType, list[PoolTransfer]] = {}
        alloc_failed = False
        for ct in self.tree_components:
            if ct == BASE_COMPONENT_TYPE:
                continue
            # Pre-allocate the component's prefetch host buffer so the build stays pure.
            prep = self.components[ct].prepare_prefetch(
                last_host_node_id, prefetch_tokens=len(prefetch_key)
            )
            if prep.alloc_failed:
                alloc_failed = True
                break
            if prep.host_indices is None:
                continue
            transfers = self.tree_core.build_hicache_transfers(
                ct,
                last_host_node_id,
                CacheTransferPhase.PREFETCH,
                token_ids=prefetch_key.token_ids,
                prefetch_tokens=len(prefetch_key),
                last_hash=last_hash,
                host_indices=prep.host_indices,
            )
            if transfers:
                comp_xfers[ct] = transfers
        kv_xfer = PoolTransfer(name=PoolName.KV, host_indices=None)
        sidecar_xfers = self._build_sidecar_transfers(
            CacheTransferPhase.PREFETCH, kv_xfer, comp_xfers
        )
        if alloc_failed:
            # The whole storage fetch is forfeited over one aux staging
            # alloc (e.g. a single SWA window) — count it, or write-burst
            # starvation of the aux pool reads as generic hit-rate loss.
            if (
                self.enable_storage_metrics
                and self.storage_metrics_collector is not None
            ):
                self.storage_metrics_collector.log_prefetch_aux_alloc_failed_tokens(
                    len(prefetch_key)
                )
            self.cache_controller.append_host_mem_release(
                extra_pools=[x for xfers in comp_xfers.values() for x in xfers],
            )
            if anchor_lock_params is not None:
                self.dec_host_lock_ref(last_host_node_id, anchor_lock_params)
            # Forfeited over transient staging pressure; retryable (T3
            # parks the rid in WAIT[HOST_ALLOC], woken by T11).
            self._storage_prefetch_missed_rids.add(req_id)
            _log_restore_disposition(req_id, "WAIT", prefetch_length, 0, "aux_alloc_failed")
            try:
                _t38c_log({"evt": "pc_outcome", "phase": "issue", "rid": req_id,
                           "outcome": "forfeited_alloc_failed",
                           "prefetch_length": prefetch_length,
                           "counters": dict(stats)})
            except Exception:
                pass
            return "forfeited_alloc_failed"

        aux_xfers = [x for xfers in comp_xfers.values() for x in xfers]
        aux_xfers.extend(sidecar_xfers)
        operation = self.cache_controller.prefetch(
            req_id,
            prefetch_key,
            last_hash,
            prefix_keys,
            extra_pools=aux_xfers or None,
        )
        stats["issued"] += 1
        logger.info("[P2A] ts_ms=%d evt=prefetch_issued rid=%s prefetch_length=%d", int(time.time() * 1000), req_id, prefetch_length)
        try:
            _t38c_log({"evt": "pc_outcome", "phase": "issue", "rid": req_id,
                       "outcome": "issued",
                       "prefetch_length": prefetch_length,
                       "counters": dict(stats)})
        except Exception:
            pass
        # Snapshots for the L3 miss accounting at the query outcome (the
        # hit/revoke drains): requested span and total prompt length.
        operation.stats_requested_tokens = prefetch_length
        operation.stats_total_tokens = prefetch_length + len(
            matched_prefix_tokens or []
        )
        self.ongoing_prefetch[req_id] = _OngoingPrefetch(
            last_host_node_id,
            prefetch_key,
            None,
            operation,
            anchor_lock_params,
            comp_xfers,
        )
        if demand_restore:
            # The T15 wake re-issue is issued: grant its DEMAND_RESTORE
            # ticket (the bounded-concurrency grant, anti-thundering-herd
            # for a backup-complete wake batch). Released with the prefetch
            # at each ongoing_prefetch removal point.
            self._demand_restore_rids.add(req_id)
        if buffer_mode:
            self.buffer_pipeline.set_prefix_ctx(req_id, matched_prefix_tokens)
            # Pin the just-matched anchor now: deferred to hit-alloc it is
            # often already deleted under churn (silent unlocked launch).
            # The hit-alloc call remains as an idempotent second chance.
            self.buffer_pipeline.try_lock_anchor(req_id, last_host_node_id)
        else:
            # Cache mode reserves the requested span up front; buffer mode
            # grants occupancy later at hit-alloc time, sized to the hit.
            self.cache_controller.prefetch_tokens_occupied += len(prefetch_key)
            if self.enable_ready_horizon:
                # M1/M5: classify the issue -- wake re-issues are demand
                # restores, everything else (entry issues, paced retries)
                # is speculative staging -- and record its budget charge.
                self.reserve_prefetch(
                    req_id,
                    len(prefetch_key),
                    PrefetchKind.DEMAND if demand_restore else PrefetchKind.SPECULATIVE,
                )
        return "issued"

    def _prefetch_timeout_check_linear_func(self, operation: PrefetchOperation) -> bool:
        return (
            time.monotonic() - operation.start_time
            > self.prefetch_timeout_base
            + len(operation.hash_value) * self.prefetch_timeout_per_page
        )

    def can_terminate_prefetch(self, operation: PrefetchOperation) -> bool:
        if self.prefetch_stop_policy == "best_effort":
            return True
        if self.prefetch_stop_policy == "wait_complete":
            return False
        elif self.prefetch_stop_policy == "timeout":
            return self._prefetch_timeout_check_linear_func(operation)
        else:
            return True

    @rank_consensus(same_params=True, same_results=True)
    def check_prefetch_progress(self, req_id: str) -> bool:
        if req_id not in self.ongoing_prefetch:
            return True

        _, _, _, operation, _, _ = self.ongoing_prefetch[req_id]

        # Determine whether or not we should terminate this prefetch request.  Make all
        # ranks agree on the decision.  When running with PP, PPn will follow PP0's decision.
        should_terminate = False
        if self.pp_rank == 0:
            should_terminate = operation.is_terminated() or self.can_terminate_prefetch(
                operation
            )
        should_terminate_tensor = torch.tensor(
            int(should_terminate), dtype=torch.int, device="cpu"
        )
        self._all_reduce(should_terminate_tensor, torch.distributed.ReduceOp.MAX)
        should_terminate = should_terminate_tensor.item() == 1

        if not should_terminate:
            return False

        self.cache_controller.terminate_prefetch(operation)
        if operation.host_indices is None:
            self._storage_prefetch_missed_rids.add(req_id)
            self.revoke_pending_prefetch(req_id)
        else:
            self._handle_prefetch_result(operation)
        return True

    def _handle_prefetch_result(self, operation: PrefetchOperation) -> None:
        # This function **owns**:
        # - host_indices[0 : completed_tokens]
        # - sidecar pool hits if operation.pool_transfers_done is true
        #
        # That is, when this function returns the host memory referenced must be inserted
        # into the radix tree or released to pool.
        logger.info("[P2A] ts_ms=%d evt=prefetch_finalize rid=%s completed_tokens=%d mode=%s", int(time.time() * 1000), operation.request_id, int(operation.completed_tokens or 0), self.host_memory_mode)
        try:
            _t38c_log({"evt": "pc_l3_host",
                       "rid": operation.request_id,
                       "completed_tokens": int(operation.completed_tokens or 0),
                       "requested_tokens": int(getattr(operation, "stats_requested_tokens", 0) or 0)})
        except Exception:
            pass

        req_id = operation.request_id
        completed_tokens = operation.completed_tokens
        hash_value = operation.hash_value

        (
            last_host_node_id,
            prefetch_key,
            host_indices,
            _,
            anchor_lock_params,
            comp_xfers,
        ) = self.ongoing_prefetch[req_id]

        # All PP/TP ranks will get the same `min_completed_tokens`, because `completed_tokens`
        # and `pool_hits` in their operations are same.  No need to sync cross-rank here.
        if not self._check_hybrid_prefetch_result(
            req_id,
            operation,
            completed_tokens,
            hash_value,
            host_indices,
            last_host_node_id,
            anchor_lock_params,
            prefetch_key,
        ):
            # Hybrid all-or-nothing check failed; result already discarded.
            _log_restore_disposition(
                req_id,
                "RECOMPUTE",
                operation.stats_requested_tokens or 0,
                completed_tokens,
                "hybrid_discard",
            )
            return

        requested = operation.stats_requested_tokens or 0
        if completed_tokens <= 0:
            disposition, disposition_reason = "RECOMPUTE", "miss"
        elif completed_tokens < requested:
            disposition, disposition_reason = "PARTIAL", "shortfall"
        else:
            disposition, disposition_reason = "RESTORE", "full"
        _log_restore_disposition(
            req_id, disposition, requested, completed_tokens, disposition_reason
        )

        if self.buffer_pipeline is not None:
            # No graft: release the rank-local tail beyond the synced usable
            # length, then park the bounce for admission-time consumption.
            self.record_storage_prefetch_terminal(req_id, "finalized")
            return self.buffer_pipeline.stage_completed_prefetch(
                req_id, completed_tokens, hash_value
            )

        fetched_key = prefetch_key[:completed_tokens]
        insert_result = self.tree_core.insert_host(
            last_host_node_id,
            fetched_key,
            host_indices[:completed_tokens],
            hash_value[: completed_tokens // self.page_size],
        )

        # Apply the host-insert walk's actions before the transfer commit.
        self._apply_cache_actions(insert_result.cache_actions)

        if insert_result.host_insert_dropped:
            self.cache_controller.append_host_mem_release(
                host_indices=host_indices[:completed_tokens],
                extra_pools=[x for xfers in comp_xfers.values() for x in xfers],
            )
            loaded_from_storage = 0
        else:
            commit_actions: list[CacheAction | ComponentAction] = []
            self.tree_core.commit_hicache_transfers(
                last_host_node_id,
                CacheTransferPhase.PREFETCH,
                comp_xfers,
                cache_actions=commit_actions,
                insert_result=insert_result,
                pool_storage_result=operation.pool_storage_result,
            )
            self._apply_cache_actions(commit_actions)
            # The commit emits via commit_actions only; the walk's were applied above.
            assert not insert_result.cache_actions

            # The restored span's KV is confirmed in L3 -- it was just read
            # from there -- so mark the inserted node durable like a
            # written+acked chain. Without this a restored chain never
            # qualifies for the hollow fallback or the prefetch gates
            # (P2-1 e14: the K=32 evict deadlock). A shortfall inserted
            # exactly prefetch_key[:completed_tokens], so the inserted node
            # spans precisely the durable range.
            if insert_result.inserted_host_node is not None:
                self.tree_core.mark_storage_restored(
                    insert_result.inserted_host_node
                )

            self.cache_controller.mem_pool_host.free(
                host_indices[: insert_result.prefix_len]
            )
            loaded_from_storage = completed_tokens - insert_result.prefix_len

        self.dec_host_lock_ref(last_host_node_id, anchor_lock_params)
        self.release_prefetch(req_id, "finalize")
        del self.ongoing_prefetch[req_id]
        self._demand_restore_rids.discard(req_id)
        self.cache_controller.prefetch_tokens_occupied -= len(prefetch_key)
        self.record_storage_prefetch_terminal(req_id, "finalized")

        self.prefetch_loaded_tokens_by_reqid[req_id] = loaded_from_storage
        logger.info(
            "HiCache prefetch %s req=%s completed=%d matched=%d loaded=%d occupied=%d",
            "dropped" if insert_result.host_insert_dropped else "success",
            req_id,
            completed_tokens,
            insert_result.prefix_len,
            loaded_from_storage,
            self.cache_controller.prefetch_tokens_occupied,
        )
        if self.enable_storage_metrics and self.storage_metrics_collector is not None:
            self.storage_metrics_collector.log_prefetched_tokens(loaded_from_storage)
        return

    def _check_hybrid_prefetch_result(
        self,
        req_id: str,
        operation: PrefetchOperation,
        completed_tokens: int,
        hash_value: list[str],
        host_indices: torch.Tensor,
        last_host_node_id: NodeId,
        anchor_lock_params: DecLockRefParams,
        prefetch_key: RadixKey,
    ) -> bool:
        """Decide the length of usable prefix.

        Two strategies depending on the hybrid layout:

        * DSA-style (Full attention + KV-derived ALL_PAGES sidecar such as the
          DSA / MiniMax indexer): *clamp* to the minimum fetched prefix shared by
          the Full KV pool and every sidecar. A partial prefix is still usable
          because the sidecar is page-aligned with KV and required for every page.
        * Everything else (SWA / Mamba components, mixed DeepSeekV4 stacks):
          *all-or-nothing*. Their pools only cover a window / tail and cannot be
          truncated page by page, so any shortfall discards the whole prefetch.

        Returns true if prefetch success, or false when an all-or-nothing prefetch
        was discarded (the caller should then treat the prefetch as finished).
        """
        # Sync completed tokens and per-pool hit pages across ATTN groups, taking
        # the minimum so every rank agrees on the same usable prefix length.
        #
        # Skip KV-derived pools, which do not report hits in operation.pool_storage_result.
        # Their hit lengths are stored in completed_tokens.
        pool_transfers = [
            transfer
            for transfer in operation.pool_transfers or []
            if transfer.indices_from_pool != PoolName.KV
        ]
        hit_pages = (
            operation.pool_storage_result.extra_pool_hit_pages if pool_transfers else {}
        )
        pool_hit_pages = [hit_pages.get(t.name, 0) for t in pool_transfers]
        completed_tokens = operation.completed_tokens
        # Hybrid cache state is all-or-nothing: every extra pool (SWA / Mamba / ...)
        # must cover the same fetched prefix. If any pool falls short the whole
        # prefetch result is unusable, so discard it and release everything.
        expected_tokens = len(hash_value) * self.page_size
        all_succeeded = completed_tokens == expected_tokens and all(
            transfer.keys is not None and count == len(transfer.keys)
            for transfer, count in zip(pool_transfers, pool_hit_pages)
        )
        if pool_transfers and not all_succeeded:
            # Drop the KV beliefs from the first page any pool failed to serve;
            # the next insert then re-writes that span through one FULL check,
            # restoring the missing aux pages.
            keep_pages = completed_tokens // self.page_size
            for transfer, count in zip(pool_transfers, pool_hit_pages):
                if transfer.keys is None:
                    keep_pages = 0
                elif count < len(transfer.keys):
                    # Aux transfers key the chain's trailing pages.
                    keep_pages = min(
                        keep_pages, max(0, len(hash_value) - len(transfer.keys))
                    )
            self.storage_existence_cache.invalidate_beyond(
                PoolName.KV, hash_value, keep_pages=keep_pages
            )
            # The controller's prefetch IO thread already releases the untransferred
            # tail (host_indices[completed_tokens:])
            self.cache_controller.append_host_mem_release(
                host_indices=host_indices[:completed_tokens],
                extra_pools=pool_transfers if operation.pool_transfers_done else None,
            )
            if anchor_lock_params is not None:
                self.dec_host_lock_ref(last_host_node_id, anchor_lock_params)
            if self.buffer_pipeline is not None:
                self.buffer_pipeline.pop_prefix_ctx(req_id)
                self.buffer_pipeline.release_anchor_lock(req_id)
            self.release_prefetch(req_id, "hybrid_discard")
            del self.ongoing_prefetch[req_id]
            self._demand_restore_rids.discard(req_id)
            self.cache_controller.prefetch_tokens_occupied -= (
                self._prefetch_occupied_span(prefetch_key, host_indices)
            )
            self.prefetch_loaded_tokens_by_reqid[req_id] = 0
            self.record_storage_prefetch_terminal(req_id, "finalized")
            logger.warning(
                "HiCache hybrid prefetch discarded req=%s completed=%d requested=%d "
                "kv_beliefs_kept_pages=%d",
                req_id,
                completed_tokens,
                expected_tokens,
                keep_pages,
            )
            return False
        return True

    def peek_prefetch_loaded_tokens(self, req_id: str) -> int:
        """Non-consuming view of a staged prefetch's loaded-token count
        (P3 3.2, the M6 residency marker): the tokens loaded from storage
        are physically resident in the host tree from finalize until
        admission pops them (pop_prefetch_loaded_tokens). A zero or
        missing entry means no resident material -- the request is not
        READY-pool material even if its state machine says READY."""
        return self.prefetch_loaded_tokens_by_reqid.get(req_id, 0)

    def pop_prefetch_loaded_tokens(self, req_id: str) -> int:
        # The request is being scheduled; a still-unserved miss marker, a
        # pending terminal outcome, and any frontier wait are moot now.
        self._storage_prefetch_missed_rids.discard(req_id)
        self._storage_prefetch_terminal.pop(req_id, None)
        self.discard_frontier_waiter(req_id)
        return self.prefetch_loaded_tokens_by_reqid.pop(req_id, 0)

    def pop_storage_prefetch_miss(self, req_id: str) -> bool:
        """True once per resolved storage-prefetch miss for a live request;
        the scheduler uses it to arm the paced availability-check retry."""
        if req_id in self._storage_prefetch_missed_rids:
            self._storage_prefetch_missed_rids.discard(req_id)
            return True
        return False

    # ---- P2-1 M2: frontier waiters (is_backedup gate skip + ACK wake) ----

    def register_frontier_waiter(self, req_id: str, node_id: NodeId) -> None:
        """Record a frontier wait for req_id keyed by its anchor node (the
        scheduler's gate else-branch, design T5), and request that node's
        chain persistence (write_back only writes L3 on eviction, so the
        wait itself must advance the frontier). Re-registration overwrites
        the previous key: arrival retries are idempotent. The wait ends when
        the node's L3 write ack promotes it to storage_persisted
        (_wake_frontier_waiters), when the per-pass frontier predicate passes,
        or on cleanup (discard_frontier_waiter)."""
        for existing, waiters in self._storage_frontier_waiters.items():
            if req_id in waiters:
                waiters.discard(req_id)
                if not waiters:
                    del self._storage_frontier_waiters[existing]
                break
        self._storage_frontier_waiters.setdefault(node_id, set()).add(req_id)
        # A re-registered waiter is no longer pending wakeup.
        self._storage_frontier_ready.discard(req_id)
        # The wait itself advances the storage frontier: write_back only
        # writes L3 on eviction, so without this the anchor chain would
        # never reach storage_persisted and the wait would sleep until the
        # T13 timeout (the 42ms-gap wake=0 bug). The gap fill dedupes by
        # is_backuped / is_storage_written; a deleted anchor is skipped
        # (its waiter self-heals through the re-match predicate).
        if self.tree_core.node_exists(node_id):
            self.write_backup_storage(node_id)

    def pop_frontier_ready(self, req_id: str) -> bool:
        """True once per ACK wake for a live request; the scheduler re-issues
        its prefetch (re-passes the gate, self-healing). Mirrors
        pop_storage_prefetch_miss."""
        if req_id in self._storage_frontier_ready:
            self._storage_frontier_ready.discard(req_id)
            return True
        return False

    def discard_frontier_waiter(self, req_id: str) -> None:
        """Drop a request's frontier wait (abort, state-machine exit,
        admission consumption). Idempotent. Also ends a parked T15
        backup wait: the span is popped so a later reconciliation cannot
        wake a request that left WAIT_CAPACITY (the T12 hold path re-runs
        the wake gate before discarding, keeping a still-unready park)."""
        self._storage_frontier_ready.discard(req_id)
        for existing, waiters in list(self._storage_frontier_waiters.items()):
            if req_id in waiters:
                waiters.discard(req_id)
                if not waiters:
                    del self._storage_frontier_waiters[existing]
        self._backup_wait_spans.pop(req_id, None)

    def _wake_frontier_waiters(self, node_id: NodeId) -> None:
        """Move the waiters of a freshly durable node into the ready set
        (called after advance_storage_persisted in the ack drain; the
        predicate accepts restored chains too, P2-1 e14). Set membership
        only -- zero queue consumption, zero callbacks, zero write path --
        so the F2 exactly-once ack semantics are untouched. Stale or
        un-durable nodes are skipped, never dereferenced."""
        waiters = self._storage_frontier_waiters.get(node_id)
        if not waiters:
            return
        if not self.tree_core.node_exists(node_id):
            return
        if not self.tree_core.is_l3_durable(node_id):
            return
        self._storage_frontier_ready.update(waiters)
        del self._storage_frontier_waiters[node_id]
        for req_id in waiters:
            logger.info(
                "[P2A] ts_ms=%d evt=frontier_wake rid=%s node=%s",
                int(time.time() * 1000),
                req_id,
                node_id,
            )

    def prompt_can_qualify_for_prefetch(
        self, prompt_len: int, host_hit_length: int = 0
    ) -> bool:
        """Whether a prompt can ever present a prefetchable suffix: its
        longest possible storage query (prompt beyond the host match, after
        the device match has fully decayed), page-aligned the same way
        prefetch_from_storage aligns keys. False means the query would be
        declined_too_short forever -- health checks and tiny prompts have no
        storage-restore intent to wait for."""
        max_suffix = max(0, prompt_len - host_hit_length)
        return max_suffix // self.page_size * self.page_size >= self.prefetch_threshold

    def has_restore_potential(
        self,
        req_id: str,
        anchor_node_id: NodeId,
        host_hit_length: int,
        prompt_len: Optional[int] = None,
    ) -> bool:
        """P2-1 M1b (T6): whether a quota-denied request has recoverable
        restore material (design §2.5-1): host material, an in-flight or
        registered restore intent, or an L3-queryable anchor chain. A prompt
        too short to ever qualify for a storage prefetch has no restore
        intent (declined_too_short is terminal for it).

        too_short churn (independent P): the never-case gate applies even
        when host material is present. When BOTH the current restore suffix
        and the theoretical-max suffix are below the prefetch threshold (a
        can-never-qualify prompt), no storage prefetch can ever be granted,
        so parking WAIT[DEVICE_QUOTA] would only re-issue an inevitably
        declined_too_short prefetch on every capacity wake (the tight
        wake -> re-issue -> declined -> re-WAIT loop). Host material alone
        no longer wins there -- the request recomputes its tail directly.
        The device-match-decay REVALIDATE bet is preserved: a prompt whose
        max suffix still reaches the threshold (prompt_can_qualify True)
        keeps its restore potential, because its current sub-threshold
        suffix may grow back above threshold once the device match decays."""
        if prompt_len is not None and not self.prompt_can_qualify_for_prefetch(
            prompt_len, host_hit_length
        ):
            return False
        if host_hit_length > 0:
            return True
        if req_id in self.ongoing_prefetch or req_id in self._storage_prefetch_missed_rids:
            return True
        if not self.tree_core.node_exists(anchor_node_id):
            return False
        return self.tree_core.is_backuped(anchor_node_id) or self.tree_core.is_root(
            anchor_node_id
        )

    # ---- P2-1 M1b: terminal prefetch outcomes (drain -> scheduler) ----

    def record_storage_prefetch_terminal(self, req_id: str, outcome: str) -> None:
        """Record a terminal prefetch outcome for the scheduler's
        restore-state reconciliation (same thread: the drain runs inside the
        scheduler's event pass)."""
        self._storage_prefetch_terminal[req_id] = outcome

    def pop_storage_prefetch_terminal(self, req_id: str) -> Optional[str]:
        """Consume the recorded terminal outcome once (None when absent)."""
        return self._storage_prefetch_terminal.pop(req_id, None)

    def staged_prefetch_tokens(self, req_id: str) -> int:
        """Tokens a staged buffer-mode prefetch would splice (0 = no hold);
        surfaced by the scheduler as the request's host_hit_length."""
        if self.buffer_pipeline is None:
            return 0
        return self.buffer_pipeline.staged_prefetch_tokens(req_id)

    def staged_prefetch_swa_tokens(self, req_id: str) -> int:
        """SWA device tokens consuming a staged buffer-mode prefetch will
        allocate; surfaced as the request's swa_host_hit_length."""
        if self.buffer_pipeline is None:
            return 0
        return self.buffer_pipeline.staged_prefetch_swa_tokens(req_id)

    @rank_consensus(same_params=True)
    def release_aborted_request(self, rid: str) -> None:
        self.prefetch_loaded_tokens_by_reqid.pop(rid, None)
        self._storage_prefetch_missed_rids.discard(rid)
        self._storage_prefetch_terminal.pop(rid, None)
        self.discard_frontier_waiter(rid)
        if (
            self.buffer_pipeline is not None
            and self.buffer_pipeline.release_aborted_staged(rid)
        ):
            return
        # M5: released unconditionally -- a reservation whose prefetch
        # entry is already gone would otherwise leak (the #31445 class).
        self.release_prefetch(rid, "abort")
        if rid not in self.ongoing_prefetch:
            return

        (
            last_host_node_id,
            prefetch_key,
            host_indices,
            operation,
            anchor_lock_params,
            comp_xfers,
        ) = self.ongoing_prefetch[rid]
        logger.info("[P2A] ts_ms=%d evt=prefetch_abort_cleanup rid=%s pre_alloc=%s", int(time.time() * 1000), rid, operation.host_indices is None)
        if operation.host_indices is None:
            self.cache_controller.terminate_prefetch(operation)
            self.revoke_pending_prefetch(rid)
            return

        completed_tokens, _ = self.cache_controller.terminate_prefetch(operation)
        if anchor_lock_params is not None:
            self.dec_host_lock_ref(last_host_node_id, anchor_lock_params)
        del self.ongoing_prefetch[rid]
        self._demand_restore_rids.discard(rid)
        if self.buffer_pipeline is not None:
            self.buffer_pipeline.pop_prefix_ctx(rid)
            self.buffer_pipeline.release_anchor_lock(rid)
        pool_transfers = [x for xfers in comp_xfers.values() for x in xfers]
        self.cache_controller.append_host_mem_release(
            host_indices=host_indices[:completed_tokens],
            extra_pools=pool_transfers if operation.pool_transfers_done else None,
        )
        # Buffer mode granted occupancy at hit-alloc, sized to the bounce;
        # cache mode reserved the requested span at enqueue.
        self.cache_controller.prefetch_tokens_occupied -= self._prefetch_occupied_span(
            prefetch_key, host_indices
        )

    def _invalidate_absent_from_hit_query(self, operation) -> None:
        """Drop KV beliefs beyond the folded usable cut (rank-synced): the
        next insert then re-writes the node (all pools), healing stale
        positives and aux holes at the cut through one FULL check."""
        if self.host_memory_mode != "buffer_only":
            return
        chain = operation.all_hash_values
        if chain is None:
            return
        self.storage_existence_cache.invalidate_beyond(
            PoolName.KV, chain, keep_pages=operation.storage_hit_count // self.page_size
        )

    def _account_prefetch_outcome(self, operation, revoked: bool) -> None:
        """Feed the cumulative prefetch-outcome counters at the (rank-synced)
        query outcome: T = prompt tokens, L = requested, m = L3-miss."""
        requested = operation.stats_requested_tokens
        if requested <= 0:
            return
        stats = self._prefetch_outcome_stats
        hit = max(0, min(operation.storage_hit_count, requested))
        if revoked:
            if hit > 0:
                stats["revoked_insufficient"] += 1
            else:
                stats["revoked_full_miss"] += 1
        miss = requested - hit
        total = max(operation.stats_total_tokens, requested, 1)
        stats["l3_demand_requests"] += 1
        stats["l1l2_miss_tokens"] += requested
        stats["l3_miss_tokens"] += miss
        stats["l3_demand_total_tokens"] += total
        stats["l3_sum_rate_all"] += miss / total
        stats["l3_sum_rate_main_weighted"] += (miss / requested) * total

    def prefetch_outcome_stats_snapshot(self) -> dict:
        """Cumulative counters + instantaneous occupancy, in the schema
        log_prefetch_stats consumers expect."""
        cc = self.cache_controller
        cap = max(cc.prefetch_capacity_limit, 1)
        return {
            **self._prefetch_outcome_stats,
            "occupancy_ratio": cc.prefetch_tokens_occupied / cap,
        }

    def _backup_park_applies(self, anchor_node_id: NodeId, operation) -> bool:
        """The T15 park predicate for one prefetch outcome: partial hit
        whose chain's backup pipeline is targeted to cover the request's
        end (target >= requested) while the durable frontier is still
        behind it. The frontiers come from chain_backup_frontiers; the
        outcome's page counts are in pages (the hash list is page-aligned
        with the requested span).

        Single gate of the T15 bypass (P2-IO Phase 1): off restores the
        pre-T15 baseline -- the revoke classification falls through to the
        pre-existing branches (miss / insufficient / alloc_failed) and the
        request recomputes; the scheduler-side T15 machinery is unreachable
        dead code. The flag is read once at init_hicache."""
        if not self.hicache_restore_backup_park:
            return False
        page_hashes = operation.all_hash_values
        if not page_hashes:
            return False
        requested_pages = len(page_hashes)
        durable, target = self.chain_backup_frontiers(
            anchor_node_id, requested_pages, page_hashes
        )
        return backup_wait_applies(
            operation.storage_hit_count // self.page_size,
            requested_pages,
            durable_frontier=durable,
            backup_target_frontier=target,
        )

    def _prefetch_occupied_span(self, prefetch_key, host_indices) -> int:
        """Occupancy units held by a prefetch: cache mode reserves the
        requested span at enqueue; buffer mode grants at hit-alloc, sized
        to the allocation (0 while still querying / parked)."""
        if self.host_memory_mode == "buffer_only":
            return len(host_indices) if host_indices is not None else 0
        return len(prefetch_key)

    def revoke_pending_prefetch(self, req_id: str) -> None:
        # M5: released before the pop -- a revoke for a prefetch whose
        # entry is already gone must still consume its reservation.
        self.release_prefetch(req_id, "revoke")
        info = self.ongoing_prefetch.pop(req_id, None)
        if info is None:
            return
        self._demand_restore_rids.discard(req_id)
        (
            last_host_node_id,
            prefetch_key,
            _host_indices,
            operation,
            anchor_lock_params,
            comp_xfers,
        ) = info
        if operation.is_terminated():
            revoke_reason = "terminated"
        elif self._backup_park_applies(last_host_node_id, operation):
            # Partial hit with the chain's backup pipeline targeted to cover
            # the request's end while the durable frontier is still behind
            # it: park on the backup-completion wait (T15) instead of
            # degrading to a terminal miss -- the backup completes and the
            # re-issued lookup then serves the full chain. Never on a zero
            # hit (the span may be genuinely unwritten) or a pipeline that
            # stops short of the request end (a genuine partial: the
            # current restore-or-recompute behavior applies).
            revoke_reason = "backup_pending"
            page_hashes = operation.all_hash_values
            self._backup_wait_spans[req_id] = (
                last_host_node_id,
                len(page_hashes),
                page_hashes,
            )
        elif operation.storage_hit_count == 0:
            revoke_reason = "miss"
        elif operation.storage_hit_count < self.prefetch_threshold:
            revoke_reason = "insufficient"
        else:
            revoke_reason = "alloc_failed"
        logger.info(
            "[P2A] ts_ms=%d evt=prefetch_revoke rid=%s terminated=%s "
            "storage_hit=%d requested=%d miss_reason=%s storage_generation=%d",
            int(time.time() * 1000),
            req_id,
            operation.is_terminated(),
            operation.storage_hit_count,
            operation.stats_requested_tokens,
            revoke_reason,
            self.tree_core.l3_publish_epoch(),
        )
        if operation.storage_hit_count == 0:
            # P2-1 e15 Y: the query reported no pages, so the anchor's
            # L3-durable belief is stale (chain evicted from storage or
            # never persisted). Clear it on the anchor only -- descendants'
            # flags are separate facts -- so gates/wakes/hollow stop
            # trusting the dead chain; a write ack re-sets the belief.
            self.tree_core.clear_storage_durable(last_host_node_id)
        _log_restore_disposition(
            req_id,
            "WAIT" if revoke_reason == "backup_pending" else "RECOMPUTE",
            operation.stats_requested_tokens or 0,
            operation.storage_hit_count,
            f"revoked:{revoke_reason}",
        )
        # P2-1 M1b (T9/T10) + P2-IO (T15): the scheduler distinguishes a
        # genuine miss (no wait -- recompute), a capacity-type termination
        # (retryable) and the backup-in-flight partial (park on the
        # backup-completion wait).
        terminal = (
            "revoked_terminated"
            if revoke_reason == "terminated"
            else "revoked_backup_pending"
            if revoke_reason == "backup_pending"
            else "revoked_miss"
        )
        self.record_storage_prefetch_terminal(req_id, terminal)
        self._invalidate_absent_from_hit_query(operation)
        if self.buffer_pipeline is not None:
            self.buffer_pipeline.pop_prefix_ctx(req_id)
            self.buffer_pipeline.release_anchor_lock(req_id)
        cc = self.cache_controller
        cc.append_host_mem_release(
            extra_pools=[x for xfers in comp_xfers.values() for x in xfers]
        )
        if anchor_lock_params is not None:
            self.dec_host_lock_ref(last_host_node_id, anchor_lock_params)
        # Every revoke path runs before the bounce alloc, so buffer mode
        # holds no occupancy here; post-alloc aborts go through
        # release_aborted_request instead.
        assert _host_indices is None or self.host_memory_mode != "buffer_only"
        cc.prefetch_tokens_occupied = max(
            0,
            cc.prefetch_tokens_occupied
            - self._prefetch_occupied_span(prefetch_key, _host_indices),
        )

    def _drain_storage_control_queues_impl(
        self,
        n_storage_hit: Optional[int],
        n_ack_prefetch: Optional[int],
        n_backup: Optional[int],
        n_release: Optional[int],
        extra_release_counts: Optional[dict[PoolName, int]],
        log_metrics: bool,
    ) -> None:
        cc = self.cache_controller

        def _drain_queue(q: Queue[T], n: Optional[int]) -> Iterator[T]:
            """If n is None, consume all items from the queue.
            Otherwise, consume n items from the queue.  Blocking if there are no enough n items.

            In TP, each rank consumes the a minimal number of items of all ranks.
            In PP, each rank consumes the exact number of items of PP0.  Refer to _pp_sync for more details.

            This prevents TP/PP divergence.
            """
            if n is None:
                while not q.empty():
                    item = q.get()
                    yield item
            else:
                for _ in range(n):
                    # Block when there are not enough elements.
                    # All TP/PP ranks must consume the same number of elements.
                    item = q.get()
                    yield item

        buffer_mode = self.host_memory_mode == "buffer_only"

        def _try_alloc_storage_hit(operation) -> bool:
            """Allocate the hit-sized bounce and launch the transfer.
            Returns False when staging pressure defers the allocation
            (buffer mode parks and retries; cache mode revokes)."""
            req_id = operation.request_id
            info = self.ongoing_prefetch.get(req_id)
            if info is None:
                return True  # aborted/cleaned; nothing to retry
            if operation.is_terminated():
                self.revoke_pending_prefetch(req_id)
                return True

            if buffer_mode and cc.prefetch_rate_limited():
                # Pool is load-saturated: hold the KNOWN hit until staged
                # prefetches ahead of us are consumed. The op stays in
                # ongoing_prefetch, so wait_complete keeps gating admission.
                return False
            alloc_len = operation.storage_hit_count
            host_indices = cc.mem_pool_host.alloc(alloc_len)
            if host_indices is None:
                # P3 M2: speculative staging eats free/soft-reserved host
                # headroom only -- an alloc failure declines it silently,
                # never forcing host eviction (staging must not push a
                # warm chain out of Host). Demand restores, and the
                # Ready-Horizon-off baseline (no reservation), still evict.
                reservation = self._prefetch_reservations.get(req_id)
                if reservation is None or reservation.kind is PrefetchKind.DEMAND:
                    self.evict_host(alloc_len)
                    host_indices = cc.mem_pool_host.alloc(alloc_len)
            if host_indices is None and not buffer_mode:
                # Memory-pressure fallback: a shorter page-aligned prefix.
                # (Cache mode only — buffer mode parks for the full hit.)
                available_size = cc.mem_pool_host.available_size()
                alloc_len = min(
                    operation.storage_hit_count,
                    available_size - (available_size % self.page_size),
                )
                if alloc_len >= self.prefetch_threshold:
                    host_indices = cc.mem_pool_host.alloc(alloc_len)
            if host_indices is None:
                if buffer_mode:
                    return False
                self.revoke_pending_prefetch(req_id)
                return True

            operation.storage_hit_count = alloc_len
            operation.hash_value = operation.hash_value[: alloc_len // self.page_size]
            operation.host_indices = host_indices
            self.ongoing_prefetch[req_id] = info._replace(host_indices=host_indices)
            if buffer_mode:
                cc.prefetch_tokens_occupied += alloc_len
                # IO commit: pin the anchor until consumption. Do not read
                # attributes off `operation` here — alternative cache
                # controllers may expose a narrower surface.
                self.buffer_pipeline.try_lock_anchor(req_id, info.anchor_node_id)
            cc.prefetch_buffer.put(operation)
            return True

        def _drain_and_alloc_storage_hit():
            # Parked hits first (FIFO fairness with retries; buffer only).
            if buffer_mode:
                parked = self.buffer_pipeline.pending_hit_allocs
                while parked:
                    if not _try_alloc_storage_hit(parked[0]):
                        break
                    parked.popleft()
            for operation in _drain_queue(cc.prefetch_hit_queue, n_storage_hit):
                req_id = operation.request_id
                info = self.ongoing_prefetch.get(req_id)
                if info is None:
                    # Request already aborted/cleaned up; still flush the
                    # query's absent-hash feedback.
                    self._invalidate_absent_from_hit_query(operation)
                    continue
                if operation.is_terminated():
                    # Controller-side miss termination (retryable) or an abort
                    # race (abort cleanup discards the marker).
                    self._storage_prefetch_missed_rids.add(req_id)
                    self.revoke_pending_prefetch(req_id)
                    try:
                        _t38c_log({"evt": "pc_outcome", "phase": "drain", "rid": req_id,
                                   "outcome": "terminated_revoke",
                                   "counters": dict(self._prefetch_outcome_stats)})
                    except Exception:
                        pass
                    continue
                if operation.storage_hit_count < self.prefetch_threshold:
                    # Below-threshold hit: classify + feed the L3 miss
                    # accounting, then revoke (not enough benefit).
                    self._account_prefetch_outcome(operation, revoked=True)
                    try:
                        _t38c_log({"evt": "pc_outcome", "phase": "drain", "rid": req_id,
                                   "outcome": ("revoked_insufficient" if operation.storage_hit_count > 0
                                               else "revoked_full_miss"),
                                   "storage_hit_count": int(operation.storage_hit_count),
                                   "requested_tokens": int(getattr(operation, "stats_requested_tokens", 0) or 0),
                                   "counters": dict(self._prefetch_outcome_stats)})
                    except Exception:
                        pass
                    self._storage_prefetch_missed_rids.add(req_id)
                    self.revoke_pending_prefetch(req_id)
                    continue
                self._invalidate_absent_from_hit_query(operation)
                self._account_prefetch_outcome(operation, revoked=False)
                if self._backup_park_applies(info.anchor_node_id, operation):
                    # Partial hit at or above the threshold with the chain's
                    # backup pipeline targeted to cover the request's end
                    # while the durable frontier is still behind it: park
                    # on the T15 wait instead of restoring the partial
                    # span. Each partial restore was denied at admission
                    # while the device stayed full, re-issuing the lookup
                    # per pass (the e13 retry loop); the backup-completion
                    # wake re-looks-up once and restores the full chain.
                    self._storage_prefetch_missed_rids.add(req_id)
                    self.revoke_pending_prefetch(req_id)
                    continue
                if not _try_alloc_storage_hit(operation):
                    # Counted once at first parking, not per retry tick.
                    self._prefetch_outcome_stats["declined_rate_limited"] += 1
                    try:
                        _t38c_log({"evt": "pc_outcome", "phase": "drain", "rid": req_id,
                                   "outcome": "declined_rate_limited", "site": "drain",
                                   "counters": dict(self._prefetch_outcome_stats)})
                    except Exception:
                        pass
                    self.buffer_pipeline.pending_hit_allocs.append(operation)

        def _drain_ack_prefetch():
            for ack in _drain_queue(cc.ack_prefetch_queue, n_ack_prefetch):
                operation = ack.operation
                if ack.completed_tokens is not None:
                    if operation.request_id in self.ongoing_prefetch:
                        assert operation.completed_tokens <= ack.completed_tokens
                        operation.completed_tokens = ack.completed_tokens
                if ack.pool_hits is not None:
                    if operation.request_id in self.ongoing_prefetch:
                        operation.pool_storage_result.update_extra_pool_hit_pages(
                            ack.pool_hits
                        )
                        operation.pool_transfers_done = True
                if ack.completed_req:
                    logger.info("[P2A] ts_ms=%d evt=prefetch_io_done rid=%s completed=%s", int(time.time() * 1000), operation.request_id, ack.completed_tokens)
                    if operation.request_id in self.ongoing_prefetch:
                        # check_prefetch_progress() is not called for this rid yet.
                        # Let us insert the prefetch result into the radix tree.
                        self._handle_prefetch_result(operation)
                    cc.append_host_mem_release(
                        operation.host_indices[operation.completed_tokens :],
                        (
                            operation.pool_transfers
                            if not operation.pool_transfers_done
                            else None
                        ),
                    )

        def _drain_backup():
            drained = 0
            for operation in _drain_queue(cc.ack_backup_queue, n_backup):
                drained += 1
                if buffer_mode:
                    # Storage write acked: free the staging.
                    self.buffer_pipeline.finish_storage_write_ack(operation.id)
                else:
                    entry = self.ongoing_backup.pop(operation.id, None)
                    if entry is not None:
                        node_id, lock_params = entry
                        self.dec_host_lock_ref(node_id, lock_params)
                        # [P3] restore_backup: the storage write ACK'd for
                        # this node. Frontier attribution for the NEVER/
                        # PARTIAL/FULL_THEN_LOST differential: requested =
                        # this operation's span; durable = the persisted
                        # frontier after the ack (0 if this op was partial
                        # -- then the node is not promoted below).
                        _log_restore_backup(
                            operation,
                            node_id,
                            durable_frontier=(
                                operation.completed_tokens
                                if operation.completed_tokens
                                >= len(operation.host_indices)
                                else 0
                            ),
                            requested_frontier=len(operation.host_indices),
                        )
                        if operation.completed_tokens >= len(
                            operation.host_indices
                        ):
                            # The write is durable: promote the node to a
                            # persisted anchor when its parent chain is.
                            # Promoted is every node that became persisted
                            # here, including descendants acked before
                            # their parent chain (retroactive promotion).
                            promoted = self.tree_core.advance_storage_persisted(
                                node_id
                            )
                            # P2-1 M2: a freshly persisted anchor can serve
                            # its frontier waiters. Set membership only --
                            # no queue consumption, no callbacks, no write
                            # path -- so the F2 exactly-once ack semantics
                            # are untouched.
                            for promoted_id in promoted:
                                self._wake_frontier_waiters(promoted_id)
                        else:
                            # Partial write (a page batch failed): L3 holds
                            # no durable copy, so the node must not become
                            # an anchor (hollow would release the last
                            # complete copy on its word). Clear the
                            # submission dedupe guard so the next gap fill
                            # rewrites the node; the host lock ref was
                            # released above and re-acquired on resubmit.
                            logger.warning(
                                "[P2A] partial backup ack: node %d got %d/%d "
                                "tokens; will rewrite",
                                node_id,
                                operation.completed_tokens,
                                len(operation.host_indices),
                            )
                            self.tree_core.clear_storage_written(node_id)
                if (
                    log_metrics
                    and self.enable_storage_metrics
                    and self.storage_metrics_collector is not None
                ):
                    self.storage_metrics_collector.log_backuped_tokens(
                        operation.completed_tokens
                    )
            return drained

        def _drain_release():
            host_indices_list = []
            released_tokens = 0
            for host_indices in _drain_queue(cc.host_mem_release_queue, n_release):
                host_indices_list.append(host_indices)
                released_tokens += len(host_indices)
            if host_indices_list:
                cc.mem_pool_host.free(torch.cat(host_indices_list, dim=0))
            return len(host_indices_list), released_tokens

        def _drain_extra_release():
            drained: dict[PoolName, tuple[int, int]] = {}
            if not extra_release_counts:
                return drained
            for pool_name, limit in extra_release_counts.items():
                release_queue = cc.extra_host_mem_release_queues.get(pool_name)
                if release_queue is None:
                    continue
                host_indices_list = []
                released_tokens = 0
                for host_indices in _drain_queue(release_queue, limit):
                    host_indices_list.append(host_indices)
                    released_tokens += len(host_indices)
                if host_indices_list:
                    cc.mem_pool_host.free(
                        torch.cat(host_indices_list, dim=0), pool=pool_name
                    )
                drained[pool_name] = (len(host_indices_list), released_tokens)
            return drained

        _drain_and_alloc_storage_hit()
        _drain_ack_prefetch()
        _drain_backup()
        _drain_release()
        _drain_extra_release()

    def drain_storage_control_queues(self) -> None:
        cc = self.cache_controller
        extra_release_queues = getattr(cc, "extra_host_mem_release_queues", {})
        extra_pool_names = list(extra_release_queues)
        local_qsize_list = [
            cc.prefetch_hit_queue.qsize(),
            cc.ack_prefetch_queue.qsize(),
            cc.ack_backup_queue.qsize(),
            cc.host_mem_release_queue.qsize(),
            *[
                extra_release_queues[pool_name].qsize()
                for pool_name in extra_pool_names
            ],
        ]
        qsizes = torch.tensor(
            local_qsize_list,
            dtype=torch.int,
        )
        self._all_reduce(qsizes, torch.distributed.ReduceOp.MIN)
        qsize_list = list(map(int, qsizes.tolist()))
        n_storage_hit, n_ack_prefetch, n_backup, n_release = qsize_list[:4]
        extra_release_counts = {
            pool_name: count
            for pool_name, count in zip(extra_pool_names, qsize_list[4:])
        }
        self._drain_storage_control_queues_impl(
            n_storage_hit=n_storage_hit,
            n_ack_prefetch=n_ack_prefetch,
            n_backup=n_backup,
            n_release=n_release,
            extra_release_counts=extra_release_counts,
            log_metrics=True,
        )

    def drain_storage_control_queues_local(self) -> None:
        """Drain the storage control queues without cross-rank synchronization.

        For the detach / shutdown path, where best-effort cleanup matters more than
        keeping the drained counts identical across ranks. The prefetch-hit queue is
        deliberately skipped: servicing it would allocate host pages for a prefetch
        that can no longer complete.
        """
        cc = self.cache_controller
        # The storage queues are created by the controller when the storage threads
        # start, so they are still None when a backend was never attached.
        if cc is None or cc.prefetch_hit_queue is None:
            return
        self._drain_storage_control_queues_impl(
            n_storage_hit=0,
            n_ack_prefetch=0,
            n_backup=None,
            n_release=None,
            extra_release_counts={
                name: None for name in cc.extra_host_mem_release_queues
            },
            log_metrics=False,
        )

    # ---- HiCache: Storage backend lifecycle (delegated) ----

    def attach_storage_backend(
        self,
        storage_backend: str,
        storage_backend_extra_config_json: Optional[str] = None,
        served_model_name: Optional[str] = None,
        hicache_storage_prefetch_policy: Optional[str] = None,
        hicache_write_policy: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Attach (enable) the HiCache storage backend at runtime."""
        if self._storage_attachment is None:
            return (
                False,
                "HiCache is not initialized; launch with "
                "--enable-hierarchical-cache to attach a storage backend.",
            )
        return self._storage_attachment.attach(
            storage_backend=storage_backend,
            storage_backend_extra_config_json=storage_backend_extra_config_json,
            served_model_name=served_model_name,
            hicache_storage_prefetch_policy=hicache_storage_prefetch_policy,
            hicache_write_policy=hicache_write_policy,
        )

    def detach_storage_backend(self) -> tuple[bool, str]:
        """Detach (disable) the HiCache storage backend at runtime."""
        if self._storage_attachment is None:
            return False, "HiCache storage backend is not initialized."
        return self._storage_attachment.detach()

    def shutdown(self) -> None:
        """Best-effort auto-detach of the storage backend on process shutdown."""
        # P2-1c expert ② shutdown/fatal cleanup: the ack drain will never run
        # again, so every in-flight load-back entry terminates here -- its
        # residual reservation (0 after the ownership transfer) and locks are
        # released exactly once.
        self._release_all_load_backs(cause="shutdown")
        if self._storage_attachment is not None:
            self._storage_attachment.shutdown()

    def clear_storage_backend(self) -> bool:
        if self._storage_attachment is None:
            return False
        ok = self._storage_attachment.clear()
        if ok:
            # L3 is empty now: every storage-presence belief is stale, and a
            # retained positive would skip that page's backup forever.
            self.storage_existence_cache.clear()
        return ok

    # ---- HiCache: Async Event Management ----

    def _count_ready_acks(self, ack_queue) -> int:
        ready_count = 0
        for ack in ack_queue:
            if not ack.finish_event.query():
                break
            ready_count += 1
        return ready_count

    def _sync_hicache_ready_counts(
        self,
    ) -> tuple[int, int, tuple[int, ...], tuple[PoolName, ...]]:
        cc = self.cache_controller
        if cc is None:
            write_acks = 0
            load_acks = 0
            storage_queue_sizes = ()
            extra_pool_names = ()
        else:
            write_acks = self._count_ready_acks(cc.ack_write_queue)
            load_acks = self._count_ready_acks(cc.ack_load_queue)
            extra_release_queues = getattr(cc, "extra_host_mem_release_queues", {})
            extra_pool_names = (
                tuple(extra_release_queues) if self.enable_storage else ()
            )
            storage_queue_sizes = (
                (
                    cc.prefetch_hit_queue.qsize(),
                    cc.ack_prefetch_queue.qsize(),
                    cc.ack_backup_queue.qsize(),
                    cc.host_mem_release_queue.qsize(),
                    *(extra_release_queues[name].qsize() for name in extra_pool_names),
                )
                if self.enable_storage
                else ()
            )

        # Piggybacked TP check: [digest, -digest] MIN-reduces to [min, -max],
        # equal iff reclaim victim order matched on every rank.
        digest = self.tree_core.write_back_duplicate_reclaim_digest
        ready_counts = torch.tensor(
            [
                write_acks,
                load_acks,
                *storage_queue_sizes,
                digest,
                -digest,
            ],
            dtype=torch.int64,
            device="cpu",
        )
        self._all_reduce(ready_counts, torch.distributed.ReduceOp.MIN)

        count_values = list(map(int, ready_counts.tolist()))
        assert (
            count_values[-2] == -count_values[-1]
        ), "write_back duplicate-reclaim victims diverged across TP ranks"
        return (
            count_values[0],
            count_values[1],
            tuple(count_values[2:-2]),
            extra_pool_names,
        )

    def _drain_write_through_acks(self) -> None:
        """One pass over one generation of the D->H ack queue: sync each DMA
        and ack every pending write-through entry (write_back entries
        included)."""
        cc = self.cache_controller
        if self._drain_write_through_depth:
            # Re-entered from an ack callback: the enclosing drain owns this
            # round; acking again would double-claim the same generation.
            logger.warning(
                "skipping re-entered _drain_write_through_acks; the "
                "enclosing drain owns this round"
            )
            return
        self._drain_write_through_depth += 1
        try:
            # Claim the whole generation up front so every ack is popped
            # exactly once before its callback runs; acks enqueued by the
            # callbacks wait for the next round instead of being drained
            # again here.
            batch = list(cc.ack_write_queue)
            cc.ack_write_queue.clear()
            for ack in batch:
                ack.finish_event.synchronize()
                acked = False
                for ack_id in ack.node_ids:
                    if ack_id in self.ongoing_write_through:
                        self._finish_write_through_ack(ack_id)
                        acked = True
                if acked:
                    self._log_write_ack_metrics(ack)
        finally:
            self._drain_write_through_depth -= 1

    def writing_check(
        self,
        write_back: bool = False,
        finish_count: Optional[int] = None,
        flush_pending: bool = True,
    ) -> None:
        """Poll write-through completions."""
        cc = self.cache_controller
        if cc is None:
            return

        if write_back:
            # Blocking: wait for all pending write-backs
            _b15_wc_pending = len(self.ongoing_write_through)
            _b15_wc_t0 = time.perf_counter()
            while self.ongoing_write_through:
                # No assert after the drain: the flush below may host-backup
                # gap nodes and enqueue fresh D->H entries.
                self._drain_write_through_acks()
            if flush_pending:
                # Not before a walk's pending demote: the persist gap-fill may
                # evict_host, whose duplicate-reclaim pass would steal the
                # just-acked host copy and break the demote's backuped
                # precondition (see _evict_components).
                self._flush_pending_storage_writes()
            try:
                _b15_log({"evt": "pa_writing_check",
                          "ms": round((time.perf_counter() - _b15_wc_t0) * 1000, 3),
                          "pending": _b15_wc_pending})
            except Exception:
                pass
            return

        if finish_count is None:
            # Every rank must enter the all_reduce below; ongoing_write_through can
            # diverge across ranks (e.g. write_backup returning 0 on a subset).
            finish_count = 0
            if self.pp_rank == 0:
                finish_count = self._count_ready_acks(cc.ack_write_queue)
            finish_count_tensor = torch.tensor(
                finish_count, dtype=torch.int, device="cpu"
            )
            self._all_reduce(finish_count_tensor, torch.distributed.ReduceOp.MIN)
            finish_count = finish_count_tensor.item()

        # Process completed acks
        while finish_count > 0:
            ack = cc.ack_write_queue.pop(0)
            ack.finish_event.synchronize()
            for ack_id in ack.node_ids:
                self._finish_write_through_ack(ack_id)
            self._log_write_ack_metrics(ack)
            finish_count -= 1
        # Persists deferred by the acks above run after the pop loop, never
        # from inside it (their D->H wait would steal the bounded queue).
        self._flush_pending_storage_writes()

    def _log_write_ack_metrics(self, ack: HiCacheAck) -> None:
        """Record D->H backup volume and duration for a completed write ack."""
        if self.metrics_collector is None:
            return
        for pool, num_tokens in (ack.num_tokens_by_pool or {}).items():
            if num_tokens > 0:
                self.metrics_collector.increment_backup_num_tokens(
                    num_tokens=num_tokens, pool=pool
                )
        if ack.num_bytes > 0:
            self.metrics_collector.increment_backup_num_bytes(ack.num_bytes)
        if ack.timing_enabled:
            duration_ms = ack.start_event.elapsed_time(ack.finish_event)
            self.metrics_collector.observe_backup_duration(duration_ms / 1000.0)

    def loading_check(self, finish_count: Optional[int] = None) -> None:
        """Poll load-back completions."""
        cc = self.cache_controller
        if cc is None:
            return
        if finish_count is None:
            # Every rank must enter the all_reduce below; ongoing_load_back can
            # diverge across ranks.
            finish_count = 0
            if self.pp_rank == 0:
                finish_count = self._count_ready_acks(cc.ack_load_queue)
            # Piggybacked TP check: [digest, -digest] MIN-reduces to [min, -max],
            # equal iff reclaim victim order matched on every rank.
            digest = self.tree_core.write_back_duplicate_reclaim_digest
            sync_tensor = torch.tensor(
                [finish_count, digest, -digest], dtype=torch.int64, device="cpu"
            )
            self._all_reduce(sync_tensor, torch.distributed.ReduceOp.MIN)
            finish_count = int(sync_tensor[0].item())
            assert (
                sync_tensor[1].item() == -sync_tensor[2].item()
            ), "write_back duplicate-reclaim victims diverged across TP ranks"

        while finish_count > 0:
            ack = cc.ack_load_queue.pop(0)
            try:
                _b15_log({"evt": "pb_load_done",
                          "n_tokens": ack.num_tokens,
                          "n_pending": len(cc.ack_load_queue)})
            except Exception:
                pass
            ack.finish_event.synchronize()
            for ack_id in ack.node_ids:
                if (
                    self.buffer_pipeline is not None
                    and self.buffer_pipeline.try_finish_load_back(ack_id)
                ):
                    continue
                # E5 (success ACK / cancel): pop exactly-once, then the
                # finalizer releases the entry's residual reservation and
                # locks (the reservation was transferred to lock ownership at
                # registration, so the residual is 0 -- the pop is what makes
                # release exactly-once).
                entry = self.ongoing_load_back.pop(ack_id)
                self._finalize_load_back_entry(entry, cause="ack")
                # Unpin the loaded nodes; host copies stay as reclaimable duplicates.
                self.tree_core.finish_load_back(entry.node_id)

            if self.metrics_collector is not None:
                for pool, num_tokens in (ack.num_tokens_by_pool or {}).items():
                    if num_tokens > 0:
                        self.metrics_collector.increment_load_back_num_tokens(
                            num_tokens=num_tokens, pool=pool
                        )
                if ack.num_bytes > 0:
                    self.metrics_collector.increment_load_back_num_bytes(ack.num_bytes)
                if ack.timing_enabled:
                    duration_ms = ack.start_event.elapsed_time(ack.finish_event)
                    self.metrics_collector.observe_load_back_duration(
                        duration_ms / 1000.0
                    )
            finish_count -= 1

    # ---- HiCache: Scheduler Entry Points ----

    def init_load_back(
        self,
        params: InitLoadBackParams,
    ) -> tuple[torch.Tensor, NodeId]:
        """Prepare KV cache loading from host to device.
        Returns (device_indices, last_node). Buffer mode dispatches to the
        staged-prefetch consumption (BufferModePipeline.init_load_back)."""
        try:
            _b15_log({"evt": "pa_lb_init",
                      "rid": (params.req.rid if params.req is not None else None),
                      "host_hit_length": params.host_hit_length})
        except Exception:
            pass
        if self.buffer_pipeline is not None:
            return self.buffer_pipeline.init_load_back(params)
        best_match_node_id = params.best_match_node
        mem_quota = params.mem_quota
        req = params.req
        assert req is not None
        last_best_match_device_node_id = req.last_node

        if (
            self.tree_core.is_full_device_evicted(best_match_node_id)
            or params.host_hit_length > 0
            or (
                req is not None
                and (req.swa_host_hit_length > 0 or req.mamba_host_hit_length > 0)
            )
        ):
            if self.load_back(best_match_node_id, mem_quota, req=req):
                new_indices = self.tree_core.collect_full_device_indices(
                    best_match_node_id, last_best_match_device_node_id
                )
                if new_indices.numel() == 0:
                    return (
                        self.tree_core.empty_match_result.device_indices,
                        last_best_match_device_node_id,
                    )

                logger.debug(
                    "init_load_back success: loaded %d tokens for node %d",
                    len(new_indices),
                    best_match_node_id,
                )
                return new_indices, best_match_node_id

        return (
            self.tree_core.empty_match_result.device_indices,
            last_best_match_device_node_id,
        )

    def _handle_storage_failure(self, reason: str) -> None:
        """Degrade when a storage thread died (never restart it).

        Runs once per failure on the scheduler thread: revoke every in-flight
        prefetch so no request hangs on a dead IO thread (the I7 failure
        mode), release the host lock refs of unacked storage writes, and log
        the failure once. The gates in query_storage_hit_length /
        prefetch_from_storage / _write_backup_storage_node then keep L3 off
        for the rest of the run; requests fall back to recompute.
        """
        if self._storage_failure_handled:
            return
        self._storage_failure_handled = True
        logger.error(
            "HiCache storage failure: %s. Degrading: L3 queries/prefetches/"
            "writes are disabled for the rest of this run; requests fall back "
            "to recompute.",
            reason,
        )
        for rid in list(self.ongoing_prefetch):
            self.release_aborted_request(rid)
        for node_id, lock_params in list(self.ongoing_backup.values()):
            self.dec_host_lock_ref(node_id, lock_params)
        self.ongoing_backup.clear()

    def check_hicache_events(self) -> None:
        """Called per scheduler step to poll async HiCache events."""
        cc = self.cache_controller
        if cc is not None and cc.storage_failure_reason is not None:
            self._handle_storage_failure(cc.storage_failure_reason)
        try:
            import time as _t38c_time
            _now = _t38c_time.time()
            _last = getattr(self, "_t38c_last_stats_ts", 0.0)
            if _now - _last >= 30.0:
                self._t38c_last_stats_ts = _now
                _t38c_log({"evt": "pc_stats_snapshot",
                           "counters": dict(self._prefetch_outcome_stats)})
        except Exception:
            pass
        # Reap the previous round's PP-sync sends before issuing new ones.
        self._drain_async_work()

        if self.pp_size != 1:
            finish_counts = torch.zeros(2, dtype=torch.int, device="cpu")
            if self.pp_rank == 0 and self.cache_controller is not None:
                finish_counts[0] = self._count_ready_acks(
                    self.cache_controller.ack_write_queue
                )
                finish_counts[1] = self._count_ready_acks(
                    self.cache_controller.ack_load_queue
                )
            self._all_reduce(finish_counts, torch.distributed.ReduceOp.MIN)
            write_finish_count, load_finish_count = map(int, finish_counts.tolist())
            self.writing_check(finish_count=write_finish_count)
            self.loading_check(finish_count=load_finish_count)
            if self.enable_storage:
                self.drain_storage_control_queues()
        else:
            (
                write_finish_count,
                load_finish_count,
                storage_queue_sizes,
                extra_pool_names,
            ) = self._sync_hicache_ready_counts()
            self.writing_check(finish_count=write_finish_count)
            self.loading_check(finish_count=load_finish_count)

            if self.enable_storage and storage_queue_sizes:
                n_storage_hit, n_ack_prefetch, n_backup, n_release = (
                    storage_queue_sizes[:4]
                )
                extra_release_counts = {
                    pool_name: count
                    for pool_name, count in zip(
                        extra_pool_names,
                        storage_queue_sizes[4:],
                    )
                }
                self._drain_storage_control_queues_impl(
                    n_storage_hit=n_storage_hit,
                    n_ack_prefetch=n_ack_prefetch,
                    n_backup=n_backup,
                    n_release=n_release,
                    extra_release_counts=extra_release_counts,
                    log_metrics=True,
                )
        if self.buffer_pipeline is not None:
            self.buffer_pipeline.flush_pending_writes()
        if self.enable_storage_metrics and self.storage_metrics_collector is not None:
            storage_metrics = self.cache_controller.storage_backend.get_stats()
            if storage_metrics is None:
                # Backends without native stats (e.g. file) still carry the
                # controller-side prefetch outcome counters.
                storage_metrics = StorageMetrics()
            storage_metrics.prefetch_stats = self.prefetch_outcome_stats_snapshot()
            self.storage_metrics_collector.log_storage_metrics(storage_metrics)

    def ready_to_load_host_cache(self) -> int:
        """Notify the cache controller to start the KV cache loading."""
        if self.cache_controller is not None:
            return self.cache_controller.start_loading()
        return 0

    def is_load_back_event_done(self, consumer_index: int) -> bool:
        """Return True after the local load-back event is complete.

        Mirrors ``HiRadixCache`` so the disagg decode restore state machine
        (``DecodeHiCacheTransferMixin``) can gate on load-back completion; the
        controller-level ``layer_done_counter`` event is shared across cache
        implementations, while the tree-side bookkeeping runs in
        ``loading_check``.
        """
        if consumer_index < 0 or self.cache_controller is None:
            return True

        finish_event = self.cache_controller.layer_done_counter.events[
            consumer_index
        ].finish_event
        if not finish_event.query():
            return False

        self.loading_check()
        return True

    # ---- Query / Inspection APIs ----
    # These APIs exist for compatibility with other RadixTree implementations.
    # TODO: simplify and consolidate in a future refactor.

    @property
    def sliding_window_size(self):
        return self._sliding_window_size

    def swa_reprefill_tail_tokens(self) -> int:
        """
        Only unified_kv + HiCache needs this: SWA lives in a per-request ring
        (state_slot/pos), not content-stable and never offloaded to host, so a
        reused prefix's trailing sliding window would read another request's
        stale ring slots. Re-prefilling that window rewrites this request's ring
        (what plain radix reuse does via its SWA match gate). 0 for every other
        layout.
        """
        swa = self.components.get(ComponentType.SWA)
        unified_compress_only_hicache = (
            self.cache_controller is not None
            and swa is not None
            and not self.tree_core.has_swa_host_pool
        )
        return swa.sliding_window_size if unified_compress_only_hicache else 0

    def swa_retain_floor(self, req) -> int | None:
        if not self.is_mamba_enabled or self._sliding_window_size is None:
            return None
        checkpoint = req.mamba_last_track_seqlen
        if checkpoint is None:
            return None
        return checkpoint - self._sliding_window_size

    def supports_swa(self) -> bool:
        return self.is_swa_enabled

    def supports_mamba(self) -> bool:
        return self.is_mamba_enabled

    # ---- Session radix cache API (delegates to composed UnifiedSessionRefTracker) ----

    def open_radix_session(self, session_id: str) -> Optional[int]:
        return self.session_refs.open_radix_session(session_id)

    def ensure_session_generation(self, session_id: str) -> int:
        return self.session_refs.ensure_session_generation(session_id)

    def release_radix_session(self, session_id: str) -> int:
        return self.session_refs.release_radix_session(session_id)

    # ---- Streaming session API (delegates to composed StreamingSession) ----

    def supports_streaming_session(self) -> bool:
        return True

    def release_session(self, session_id: str) -> None:
        self.session.release_session(session_id)

    def session_held_tokens(self, active_pool_idxs: Optional[set] = None) -> int:
        return self.session.session_held_tokens(active_pool_idxs)

    def session_held_full_tokens(self, active_pool_idxs: Optional[set] = None) -> int:
        return self.session.session_held_full_tokens(active_pool_idxs)

    def session_held_swa_tokens(self, active_pool_idxs: Optional[set] = None) -> int:
        return self.session.session_held_swa_tokens(active_pool_idxs)

    def session_held_req_count(self, active_pool_idxs: Optional[set] = None) -> int:
        return self.session.session_held_req_count(active_pool_idxs)

    def session_held_mamba_slots(self, active_pool_idxs: Optional[set] = None) -> int:
        return self.session.session_held_mamba_slots(active_pool_idxs)

    def evictable_size(self) -> int:
        return self.tree_core.evictable_size()

    def protected_size(self) -> int:
        return self.tree_core.protected_size()

    def full_evictable_size(self) -> int:
        return self.tree_core.full_evictable_size()

    def full_protected_size(self) -> int:
        return self.tree_core.full_protected_size()

    def swa_evictable_size(self) -> int:
        return self.tree_core.swa_evictable_size()

    def mamba_evictable_size(self) -> int:
        return self.tree_core.mamba_evictable_size()

    def swa_protected_size(self) -> int:
        return self.tree_core.swa_protected_size()

    def mamba_protected_size(self) -> int:
        return self.tree_core.mamba_protected_size()

    def total_size(self) -> tuple[int, int]:
        return self.tree_core.total_size()

    def all_values_flatten(self) -> torch.Tensor:
        return self.tree_core.all_values_flatten()

    def all_mamba_values_flatten(self) -> torch.Tensor:
        return self.tree_core.all_mamba_values_flatten()

    def available_and_evictable_str(self) -> str:
        # TODO(zhangmj): need more detailed log info for session reference.
        if self.supports_swa():
            full_available_size = self.token_to_kv_pool_allocator.full_available_size()
        else:
            full_available_size = self.token_to_kv_pool_allocator.available_size()
        full_evictable = self.tree_core.component_evictable_size(BASE_COMPONENT_TYPE)
        lines = [
            f"Available full tokens: {full_available_size + full_evictable} "
            f"(full_available_size={full_available_size} + full_evictable_size_={full_evictable})"
        ]
        for ct in self.tree_components:
            if ct == BASE_COMPONENT_TYPE:
                continue
            if ct.is_swa:
                available_size = self.token_to_kv_pool_allocator.swa_available_size()
            elif ct.is_mamba:
                available_size = self.req_to_token_pool.mamba_allocator.available_size()
            else:
                continue

            lines.append(
                f"Available {ct}: {available_size + self.tree_core.component_evictable_size(ct)} "
                f"(available_size={available_size} + component_evictable_size_={self.tree_core.component_evictable_size(ct)})"
            )
        return "\n".join(lines) + "\n"

    def sanity_check(self):
        """Verify tree invariants.

        TODO(hzh): This method has relatively high latency; simplify the
        check logic once the tree implementation stabilizes.
        """
        # Skip when streaming sessions hold tree locks: the check asserts
        # all nodes are unlocked during idle, which streaming sessions break
        # by design (they hold a first-turn lock across turns).
        if self.session.any_holding_kv():
            return

        # Pass ongoing ops as lightweight (id, node_id) pairs so the tree core
        # can resolve + validate them without reaching into Controller state.
        if self.buffer_pipeline is not None:
            ongoing_write_through = [
                (nid, entry.intent.node_id)
                for nid, entry in self.buffer_pipeline.ongoing_write_through.items()
            ]
        else:
            ongoing_write_through = [
                (nid, wt.node_id) for nid, wt in self.ongoing_write_through.items()
            ]
        ongoing_load_back = [
            (nid, lb.node_id) for nid, lb in self.ongoing_load_back.items()
        ]
        # P2-1c I2 invariant (design §3.3): the net reservation counter
        # equals the sum of the live entries' residual reservations. Runs on
        # the scheduler thread at pass boundaries, never mid-load_back, so
        # the gate->transfer window is never observed.
        reserved_sum = sum(
            lb.reserved_tokens for lb in self.ongoing_load_back.values()
        )
        assert self.inflight_promotion_reserved == reserved_sum, (
            f"P2-1c reservation invariant violated: counter="
            f"{self.inflight_promotion_reserved} != sum(live entries)="
            f"{reserved_sum}"
        )
        self.tree_core.sanity_check(ongoing_write_through, ongoing_load_back)

    def pretty_print(self) -> None:
        self.tree_core.pretty_print()

    # ---- TreeCore state delegation ----
    # The facade re-exposes tree-owned config (page_size, enable_storage, ...) so its
    # own coordination methods and external callers read them off the cache.

    # ``page_size`` keeps a setter: StreamingSession forwards assignment onto its
    # inner cache (the PrefixCacheTrait surface).
    @property
    def page_size(self):
        return self.tree_core.page_size

    @page_size.setter
    def page_size(self, value) -> None:
        self.tree_core.page_size = value

    @property
    def enable_storage(self):
        return self.tree_core.enable_storage

    @enable_storage.setter
    def enable_storage(self, value) -> None:
        self.tree_core.enable_storage = value

    @property
    def write_through_threshold(self):
        return self.tree_core.write_through_threshold

    @write_through_threshold.setter
    def write_through_threshold(self, value) -> None:
        self.tree_core.write_through_threshold = value

    @property
    def is_write_back(self):
        return self.tree_core.is_write_back

    @is_write_back.setter
    def is_write_back(self, value) -> None:
        self.tree_core.is_write_back = value

    @property
    def device(self):
        return self.tree_core.device

    @property
    def root_node(self):
        return self.tree_core.root_node

    def take_events(self):
        # Drain the KV event queue from the TreeCore.
        return self.tree_core.take_events()

    def resolve_node_handle(self, node_handle):
        """Look up the node object from its NodeId.

        TODO(Jialin): Remove after the Unified Radix Cache split.
        """
        if isinstance(node_handle, int):
            return self.tree_core.node_by_id(node_handle)
        # Internal callers (and the session sentinel / None) pass a non-int through.
        return node_handle

    def root_node_handle(self, extra_key: Optional[str] = None) -> NodeId:
        """The root's NodeId -- URC match results carry NodeIds."""
        return self.tree_core.root_node_handle(extra_key)
