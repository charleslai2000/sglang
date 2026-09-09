from __future__ import annotations

import atexit
import logging
import os
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
    HostAllocFailure,
    HostAllocabilitySnapshot,
    HOST_ALLOC_TELEMETRY_SCHEMA_VERSION,
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
    PoolHitPolicy,
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
from sglang.srt.mem_cache.trace_context import (
    attach_trace_context,
    complete_trace_context,
    complete_slot_context,
    durable_trace_enabled,
    is_inert_release_token,
    make_trace_context,
    ordered_key_set_digest,
    remember_slot_context,
    retire_slot_token,
    slot_context,
    slot_context_for_token,
    slot_token,
)
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

_T38C_DURABLE_SEQ = {}
_T38C_DURABLE_SEQ_LOCK = threading.Lock()

# Cache-side mutation records are sampled independently of scheduler wake
# records.  The mutation sequence remains complete and monotonic for joins;
# only emitted log records are bounded.  Each request/cause/trace key emits
# its first 16 mutations, then every 128th mutation, up to 64 records.  A
# cache instance emits at most 256 mutation records in total.
_HOST_ALLOC_MUTATION_TELEMETRY_HEAD = 16
_HOST_ALLOC_MUTATION_TELEMETRY_STRIDE = 128
_HOST_ALLOC_MUTATION_TELEMETRY_MAX_PER_KEY = 64
_HOST_ALLOC_MUTATION_TELEMETRY_MAX_TOTAL = 256
_HOST_ALLOC_MUTATION_TELEMETRY_MAX_KEYS = 4096


def _log_host_alloc_telemetry(
    event: str,
    *,
    rid: Optional[str] = None,
    attempt_id: Optional[str] = None,
    **fields,
) -> None:
    """Emit bounded, observational HOST_ALLOC records with a stable schema."""
    import json as _json

    record = {
        "schema": HOST_ALLOC_TELEMETRY_SCHEMA_VERSION,
        "evt": event,
        "ts_mono_ns": time.monotonic_ns(),
        "ts_wall_ms": int(time.time() * 1000),
        "worker": os.environ.get("SGLANG_WORKER_ID") or f"pid-{os.getpid()}",
        "rank": os.environ.get("RANK"),
        "rid": rid,
        "attempt_id": attempt_id,
    }
    record.update(fields)
    logger.info("[HAE] %s", _json.dumps(record, sort_keys=True, default=str))


def _storage_hit_crop_is_safe(operation, alloc_len: int) -> bool:
    """Whether a host-capacity crop preserves the validated storage frontier."""
    if alloc_len >= operation.storage_hit_count:
        return True
    trailing_pages = getattr(PoolHitPolicy, "TRAILING_PAGES", None)
    return not any(
        trailing_pages is not None
        and getattr(transfer, "hit_policy", None) == trailing_pages
        for transfer in getattr(operation, "pool_transfers", None) or []
    )


def _t38c_residency_identity(context, node_id, final_kv_hash):
    if not isinstance(context, dict):
        return None
    required_fields = (
        "schema_version",
        "run_id",
        "session_id",
        "session_generation",
        "build_rid",
        "warm_rid",
        "node_id",
        "final_kv_hash",
    )
    if (
        any(field not in context for field in required_fields)
        or context.get("schema_version") != "p0_durable.v3"
        or not isinstance(context.get("run_id"), str)
        or not context.get("run_id").strip()
        or not context.get("session_id")
        or context.get("session_generation") is None
        or not context.get("build_rid")
        or context.get("warm_rid") is not None
        or not node_id
        or not isinstance(final_kv_hash, str)
        or not final_kv_hash
        or not complete_trace_context(context, node_id, final_kv_hash)
    ):
        return None
    return (
        context["run_id"],
        str(context["session_id"]),
        context["session_generation"],
        str(context["build_rid"]),
        str(node_id),
        final_kv_hash,
    )

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


def _t38c_durable_enabled() -> bool:
    import os as _os

    return _os.path.exists("/tmp/t38c-durable-trace")


def _t38c_slot_digest(pool, values) -> str | None:
    """Hash slot metadata and indices without recording slot/state contents."""
    if not _t38c_durable_enabled():
        return None
    import hashlib as _hashlib

    digest = _hashlib.sha256()
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


def _t38c_durable_log(rec):
    """Marker-gated p0 durability trace; identities/counters only."""
    try:
        import json as _json
        import os as _os

        if not _os.path.exists("/tmp/t38c-durable-trace"):
            return
        thread_id = threading.get_ident()
        with _T38C_DURABLE_SEQ_LOCK:
            local_seq = _T38C_DURABLE_SEQ.get(thread_id, 0) + 1
            _T38C_DURABLE_SEQ[thread_id] = local_seq
        run_id = _os.environ.get("T38C_RUN_ID") or f"pid-{_os.getpid()}"
        record = attach_trace_context(dict(rec))
        record.setdefault("schema_version", "p0_durable.v2")
        record.setdefault("run_id", run_id)
        record.setdefault(
            "event_id",
            f"{run_id}:{_os.getpid()}:{thread_id}:radix:{local_seq}",
        )
        record.setdefault("process_id", _os.getpid())
        record.setdefault("rank", _os.environ.get("RANK"))
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
            _f.write(_json.dumps(record, default=str) + "\n")
        return record["event_id"]
    except Exception:
        pass


def _t38c_build_complete_debug(reason: str) -> None:
    """Marker-gated diagnostics for suppressed build identity emission."""
    if os.environ.get("T38C_BUILD_COMPLETE_DEBUG") == "1":
        logger.warning("T38C build_complete suppressed: %s", reason)


def _t38c_free_slots(frees) -> int:
    total = 0
    for values in frees.values():
        for value in values:
            try:
                total += int(value.numel())
            except AttributeError:
                total += len(value)
    return total


def _t38c_pool_name(component_type):
    return _COMPONENT_POOL_LABEL.get(component_type, str(component_type))


def _t38c_residency_component_snapshot(node):
    """Return privacy-safe required-component presence evidence."""
    manifest = (
        (ComponentType.FULL, "FULL", "kv"),
        (ComponentType.MAMBA, "MAMBA", "mamba"),
    )
    component_data = getattr(node, "component_data", None)
    tiers = []
    live_count = 0
    complete = component_data is not None
    required_keys = set()

    def _lookup(component_type, name):
        if isinstance(component_data, dict):
            for key in (component_type, name, name.lower()):
                if key in component_data:
                    return component_data[key]
            return None
        try:
            return component_data[component_type]
        except (IndexError, KeyError, TypeError):
            return None

    def _slot_count(value):
        if value is None:
            return 0
        try:
            return int(value.numel())
        except (AttributeError, TypeError, ValueError):
            try:
                return len(value)
            except (TypeError, ValueError):
                return 1

    for component_type, name, pool in manifest:
        required_keys.add(component_type)
        required_keys.add(name)
        required_keys.add(name.lower())
        data = _lookup(component_type, name)
        if data is None:
            complete = False
            device_value = host_value = None
            device_lock_ref = host_lock_ref = 0
        else:
            device_value = getattr(data, "value", None)
            host_value = getattr(data, "host_value", None)
            device_lock_ref = int(getattr(data, "lock_ref", 0) or 0)
            host_lock_ref = int(getattr(data, "host_lock_ref", 0) or 0)
        device_present = device_value is not None
        host_present = host_value is not None
        if device_present or host_present:
            live_count += 1
        tiers.append(
            {
                "component": name,
                "pool": pool,
                "device_present": device_present,
                "device_slot_count": _slot_count(device_value),
                "device_lock_ref": device_lock_ref,
                "host_present": host_present,
                "host_slot_count": _slot_count(host_value),
                "host_lock_ref": host_lock_ref,
            }
        )

    unsupported = False
    if isinstance(component_data, dict):
        items = component_data.items()
    elif component_data is None:
        items = ()
    else:
        items = enumerate(component_data)
    for key, data in items:
        key_name = getattr(key, "name", str(key)).upper()
        if key in required_keys or key_name in ("FULL", "MAMBA"):
            continue
        if data is not None and (
            getattr(data, "value", None) is not None
            or getattr(data, "host_value", None) is not None
        ):
            unsupported = True

    return {
        "required_component_manifest": [name for _ct, name, _pool in manifest],
        "component_tiers": tiers,
        "live_component_count": live_count,
        "snapshot_complete": bool(complete),
        "unsupported_component": unsupported,
    }


def _t38c_residency_retire(
    cache, identity, reason, context=None, *, trigger="identity_retired"
):
    if not identity or len(identity) != 6:
        return
    with cache._t38c_residency_lock:
        getattr(cache, "_t38c_residency_retired", set()).add(identity)
        lifecycle = getattr(cache, "_t38c_residency_lifecycle", {}).get(identity)
        expected = getattr(cache, "_t38c_residency_detached", {}).pop(
            identity, set()
        )
        completed = getattr(cache, "_t38c_residency_completed", set())
        for _node, pool, tier, digest, token in expected:
            completed.discard((identity, pool, tier, digest, token))
            retire_slot_token(token)
        getattr(cache, "_t38c_residency_reconcile_ready", set()).discard(identity)
        getattr(cache, "_t38c_residency_queue_blocked", set()).discard(identity)
        if lifecycle is not None:
            lifecycle["state"] = "RETIRED_INVALID"
            lifecycle["retirement_reason"] = reason
            lifecycle["trigger"] = trigger
        _t38c_residency_outcome(
            cache,
            identity,
            context,
            reason,
            trigger=trigger,
            result=False,
            terminal=True,
        )


def _t38c_residency_release_queues_drained(cache):
    """Reconcile queue-blocked identities after the owning drain commits."""
    if not _t38c_durable_enabled():
        return
    with cache._t38c_residency_lock:
        pending = tuple(
            getattr(cache, "_t38c_residency_queue_blocked", set())
        )
        cache._t38c_residency_queue_blocked.difference_update(pending)
    for identity in pending:
        _t38c_residency_reconcile(cache, identity, "release_queues_drained")


def _t38c_residency_reconcile(cache, identity, trigger):
    if not identity or len(identity) != 6:
        return
    ready = getattr(cache, "_t38c_residency_reconcile_ready", None)
    if ready is not None:
        ready.add(identity)
    _t38c_residency_barrier(
        cache,
        identity[4],
        expected_identity=identity,
        trigger=trigger,
    )


def _t38c_note_detach(cache, node_id, pool, tier, slot_digest):
    if not slot_digest or not _t38c_durable_enabled():
        return
    with cache._t38c_residency_lock:
        context = cache._t38c_trace_context_for_node(node_id)
        identity = _t38c_residency_identity(
            context,
            node_id,
            context.get("final_kv_hash") if context else None,
        )
        if identity is None or identity in cache._t38c_residency_barriers:
            return
        if identity not in getattr(cache, "_t38c_build_identities", set()):
            _t38c_residency_outcome(
                cache,
                identity,
                context,
                "nonterminal_not_build_registered",
                trigger="eligible_detach_registered",
            )
            return
        if identity in getattr(cache, "_t38c_residency_retired", set()):
            return
        lifecycle = cache._t38c_residency_lifecycle.setdefault(
            identity,
            {
                "state": "BUILD_CREATED",
                "build_event_id": None,
                "durability_event_id": None,
                "component_snapshot": None,
                "queue_snapshot": None,
                "publication_event_id": None,
                "retirement_reason": None,
                "reconcile_attempt_count": 0,
                "reason_attempt_counts": {},
                "diagnostic_reason_set": set(),
                "suppressed_diagnostic_count": 0,
                "first_failure_reason": None,
                "first_failure_event_id": None,
                "first_attempt_ts_mono_ns": None,
                "last_attempt_ts_mono_ns": None,
                "first_attempt_event_id": None,
                "last_attempt_event_id": None,
                "terminal_event_id": None,
                "detach_expectations_registered": False,
                "detach_manifest": set(),
            },
        )
        if lifecycle.get("detach_expectations_registered"):
            expected = cache._t38c_residency_detached.get(identity, set())
            if not any(
                entry[1:4] == (pool, tier, slot_digest)
                for entry in expected
            ):
                _t38c_residency_retire(
                    cache,
                    identity,
                    "late_detach_after_seal",
                    context,
                    trigger="eligible_detach_registered",
                )
            return
        lifecycle = {
            "run_id": context["run_id"],
            "node_id": str(node_id),
            "session_generation": context["session_generation"],
        }
        token = remember_slot_context(
            pool, tier, slot_digest, context, lifecycle=lifecycle
        )
        if token is not None:
            cache._t38c_residency_detached.setdefault(identity, set()).add(
                (str(node_id), pool, tier, slot_digest, token)
            )
            cache._t38c_residency_lifecycle.setdefault(
                identity, lifecycle
            )
            _t38c_residency_reconcile(
                cache, identity, "eligible_detach_registered"
            )


def _t38c_residency_seal_detach(
    cache, node_id, manifest, *, unsupported=False
):
    """Seal the exact production detach manifest before DETACH_SEALED."""
    if not _t38c_durable_enabled():
        return
    with cache._t38c_residency_lock:
        context = cache._t38c_trace_context_for_node(node_id)
        identity = _t38c_residency_identity(
            context,
            node_id,
            context.get("final_kv_hash") if context else None,
        )
        if identity is None or identity in cache._t38c_residency_barriers:
            return
        if identity not in getattr(cache, "_t38c_build_identities", set()):
            _t38c_residency_outcome(
                cache,
                identity,
                context,
                "nonterminal_not_build_registered",
                trigger="detach_seal",
            )
            return
        lifecycle = cache._t38c_residency_lifecycle.setdefault(
            identity,
            {
                "state": "BUILD_CREATED",
                "build_event_id": None,
                "durability_event_id": None,
                "component_snapshot": None,
                "queue_snapshot": None,
                "publication_event_id": None,
                "retirement_reason": None,
                "reconcile_attempt_count": 0,
                "reason_attempt_counts": {},
                "diagnostic_reason_set": set(),
                "suppressed_diagnostic_count": 0,
                "first_failure_reason": None,
                "first_failure_event_id": None,
                "first_attempt_ts_mono_ns": None,
                "last_attempt_ts_mono_ns": None,
                "first_attempt_event_id": None,
                "last_attempt_event_id": None,
                "terminal_event_id": None,
                "detach_expectations_registered": False,
                "detach_manifest": set(),
            },
        )
        manifest = set(manifest or ())
        supported_components = {"kv", "mamba"}
        observed_components = {pool for pool, _tier in manifest}
        if unsupported or observed_components != supported_components:
            _t38c_residency_retire(
                cache,
                identity,
                "detach_manifest_incomplete"
                if not unsupported
                else "unsupported_component",
                context,
                trigger="detach_seal",
            )
            return
        if lifecycle.get("detach_expectations_registered"):
            if manifest != lifecycle.get("detach_manifest", set()):
                _t38c_residency_retire(
                    cache,
                    identity,
                    "late_detach_after_seal",
                    context,
                    trigger="detach_seal",
                )
            return
        expected = cache._t38c_residency_detached.get(identity, set())
        registered = {(pool, tier) for _node, pool, tier, _digest, _token in expected}
        if registered != manifest:
            _t38c_residency_retire(
                cache,
                identity,
                "detach_manifest_incomplete",
                context,
                trigger="detach_seal",
            )
            return
        lifecycle["detach_manifest"] = manifest
        lifecycle["detach_expectations_registered"] = True
        _t38c_residency_reconcile(cache, identity, "detach_sealed")


def _t38c_note_completion(cache, pool, tier, slot_digest, token=None):
    if (
        slot_digest
        and token is not None
        and not is_inert_release_token(token)
        and _t38c_durable_enabled()
    ):
        with cache._t38c_residency_lock:
            owned_entry = None
            for identity, expected in cache._t38c_residency_detached.items():
                owned_entry = next(
                    (
                        entry
                        for entry in expected
                        if entry[1:4] == (pool, tier, slot_digest)
                        and entry[4] == token
                    ),
                    None,
                )
                if owned_entry is not None:
                    break
            # A token presented to a different cache is not evidence for this
            # cache and must not be completed or retired here.
            if owned_entry is None:
                return
            completed_token = complete_slot_context(
                pool, tier, slot_digest, token=token
            )
            if completed_token is not None:
                cache._t38c_residency_completed.add(
                    (identity, pool, tier, slot_digest, completed_token)
                )
                retire_slot_token(completed_token)
                _t38c_residency_reconcile(cache, identity, "free_complete")


def _t38c_residency_queue_snapshot(cache):
    """Read release-queue emptiness under the controller handoff lock."""
    snapshot = {
        "queue_snapshot_locked": False,
        "primary_queue_empty": None,
        "extra_queue_empty": None,
        "extra_queue_emptiness": {},
    }
    try:
        cache_controller = getattr(cache, "cache_controller", None)
        if cache_controller is None:
            return snapshot
        release_handoff_lock = getattr(
            cache_controller, "_t38c_release_handoff_lock", None
        )
        release_queue = getattr(
            cache_controller, "host_mem_release_queue", None
        )
        extra_release_queues = getattr(
            cache_controller, "extra_host_mem_release_queues", None
        )
        if (
            release_handoff_lock is None
            or release_queue is None
            or extra_release_queues is None
        ):
            return snapshot
        with release_handoff_lock:
            extra_emptiness = {
                str(pool): queue.empty()
                for pool, queue in extra_release_queues.items()
            }
            snapshot.update(
                queue_snapshot_locked=True,
                primary_queue_empty=release_queue.empty(),
                extra_queue_empty=all(extra_emptiness.values()),
                extra_queue_emptiness=extra_emptiness,
            )
    except Exception:
        return snapshot
    return snapshot


def _t38c_residency_outcome(
    cache,
    identity,
    context,
    reason,
    *,
    retry_epoch=0,
    poll_attempt=0,
    result=False,
    exception_type=None,
    queue_snapshot=None,
    component_snapshot=None,
    trigger="reconcile",
    terminal=False,
):
    """Emit bounded diagnostics without affecting the strict state machine."""
    if not _t38c_durable_enabled() or not identity or len(identity) != 6:
        return
    try:
        outcomes = getattr(cache, "_t38c_residency_outcomes", set())
        lifecycle = getattr(cache, "_t38c_residency_lifecycle", {}).get(identity)
        outcome_key = (identity, reason)
        if lifecycle is not None:
            lifecycle.setdefault("diagnostic_reason_set", set()).add(reason)
            counts = lifecycle.setdefault("reason_attempt_counts", {})
            counts[reason] = counts.get(reason, 0) + 1
        if outcome_key in outcomes:
            if lifecycle is not None:
                lifecycle["suppressed_diagnostic_count"] = (
                    lifecycle.get("suppressed_diagnostic_count", 0) + 1
                )
            return
        if queue_snapshot is None:
            queue_snapshot = _t38c_residency_queue_snapshot(cache)
        if component_snapshot is None and lifecycle is not None:
            component_snapshot = lifecycle.get("component_snapshot")
        component_snapshot = component_snapshot or {
            "required_component_manifest": ["FULL", "MAMBA"],
            "component_tiers": [],
            "live_component_count": None,
            "snapshot_complete": False,
        }
        if lifecycle is not None:
            lifecycle["queue_snapshot"] = dict(queue_snapshot)
            if not result and lifecycle.get("first_failure_reason") is None:
                lifecycle["first_failure_reason"] = reason
                lifecycle["first_failure_event_id"] = None
        record = {
            "evt": "residency_barrier_outcome",
            "schema_version": "p0_residency.v3",
            "trace_context": context,
            "run_id": identity[0],
            "session_id": identity[1],
            "session_generation": identity[2],
            "build_rid": identity[3],
            "node_id": identity[4],
            "final_kv_hash": identity[5],
            "result": bool(result),
            "reason": reason,
            "predicate": reason,
            "trigger": trigger,
            "lifecycle_state": lifecycle.get("state") if lifecycle else None,
            "reconcile_attempt_count": lifecycle.get("reconcile_attempt_count", 0)
            if lifecycle
            else 0,
            "reason_attempt_counts": dict(
                lifecycle.get("reason_attempt_counts", {})
            )
            if lifecycle
            else {},
            "suppressed_diagnostic_count": lifecycle.get(
                "suppressed_diagnostic_count", 0
            )
            if lifecycle
            else 0,
            "observed_reasons": sorted(
                lifecycle.get("diagnostic_reason_set", set()) | {reason}
            )
            if lifecycle
            else [reason],
            "first_attempt_ts_mono_ns": lifecycle.get(
                "first_attempt_ts_mono_ns"
            )
            if lifecycle
            else None,
            "last_attempt_ts_mono_ns": lifecycle.get("last_attempt_ts_mono_ns")
            if lifecycle
            else None,
            "first_attempt_event_id": lifecycle.get("first_attempt_event_id")
            if lifecycle
            else None,
            "last_attempt_event_id": lifecycle.get("last_attempt_event_id")
            if lifecycle
            else None,
            "required_component_manifest": component_snapshot.get(
                "required_component_manifest", []
            ),
            "component_tiers": component_snapshot.get("component_tiers", []),
            "live_component_count": component_snapshot.get("live_component_count"),
            "snapshot_complete": component_snapshot.get("snapshot_complete", False),
            "build_event_id": lifecycle.get("build_event_id") if lifecycle else None,
            "durability_event_id": lifecycle.get("durability_event_id")
            if lifecycle
            else None,
            "expected_release_count": len(
                getattr(cache, "_t38c_residency_detached", {}).get(identity, ())
            ),
            "completed_release_count": sum(
                1
                for completed in getattr(cache, "_t38c_residency_completed", ())
                if completed[0] == identity
            ),
            "device_detach_seen": any(
                entry[2] == "device"
                for entry in getattr(cache, "_t38c_residency_detached", {}).get(
                    identity, ()
                )
            ),
            "detach_sealed": bool(lifecycle and lifecycle.get("detach_sealed")),
            "first_failure_reason": lifecycle.get("first_failure_reason")
            if lifecycle
            else reason,
            "first_failure_event_id": lifecycle.get("first_failure_event_id")
            if lifecycle
            else None,
            "terminal_event_id": lifecycle.get("terminal_event_id")
            if lifecycle
            else None,
            "publication_event_id": lifecycle.get("publication_event_id")
            if lifecycle
            else None,
            "retirement_reason": lifecycle.get("retirement_reason")
            if lifecycle
            else None,
            "publication_cause": (
                "residency_barrier"
                if lifecycle and lifecycle.get("publication_event_id")
                else None
            ),
            "retirement_cause": lifecycle.get("retirement_reason")
            if lifecycle
            else None,
            "terminal": bool(terminal),
            **queue_snapshot,
        }
        if exception_type is not None:
            record["exception_type"] = exception_type
        event_id = _t38c_durable_log(record)
        if event_id is not None:
            outcomes.add(outcome_key)
            if lifecycle is not None:
                if not result and lifecycle.get("first_failure_event_id") is None:
                    lifecycle["first_failure_event_id"] = event_id
                if terminal:
                    lifecycle["terminal_event_id"] = event_id
    except Exception:
        # Diagnostics must never change the strict fold's fail-closed result.
        return


def _t38c_residency_node_lookup(cache, node_id):
    """Resolve a serialized identity node ID without joining the wrong node."""
    if node_id is None or isinstance(node_id, bool):
        return None
    lookup_ids = [node_id]
    if isinstance(node_id, str):
        try:
            typed_node_id = int(node_id)
        except (TypeError, ValueError):
            typed_node_id = None
        if typed_node_id is not None and str(typed_node_id) == node_id:
            lookup_ids.append(typed_node_id)
    candidates = []
    for lookup_id in lookup_ids:
        try:
            node = cache.tree_core.node_by_id(lookup_id)
        except (AttributeError, IndexError, KeyError, TypeError):
            continue
        if node is None:
            continue
        if str(getattr(node, "id", None)) != str(node_id):
            return None
        if all(node is not candidate for candidate in candidates):
            candidates.append(node)
    return candidates[0] if len(candidates) == 1 else None


def _t38c_residency_barrier(
    cache,
    node_id,
    expected_identity=None,
    retry_epoch=0,
    poll_attempt=0,
    trigger="reconcile",
):
    """Publish cold residency only after keyed detaches have actually freed."""
    if not _t38c_durable_enabled():
        return
    with cache._t38c_residency_lock:
        identity = expected_identity
        context = None
        final_kv_hash = (
            expected_identity[5]
            if expected_identity is not None and len(expected_identity) == 6
            else ""
        )
        try:
            node = _t38c_residency_node_lookup(cache, node_id)
            if node is None:
                _t38c_residency_outcome(
                    cache,
                    identity,
                    context,
                    "node_lookup",
                    retry_epoch=retry_epoch,
                    poll_attempt=poll_attempt,
                    trigger=trigger,
                )
                return
            if node is cache.tree_core.root_node or getattr(
                node, "forced_miss_tombstone", False
            ):
                _t38c_residency_outcome(
                    cache,
                    identity,
                    context,
                    "root_or_forced_miss",
                    retry_epoch=retry_epoch,
                    poll_attempt=poll_attempt,
                    trigger=trigger,
                )
                return
            final_kv_hash = node.get_last_hash_value() or ""
            context = cache._t38c_trace_context_for_node(node_id)
            identity = _t38c_residency_identity(context, node_id, final_kv_hash)
            if identity is None or (
                expected_identity is not None and identity != expected_identity
            ):
                if expected_identity is not None:
                    _t38c_residency_retire(
                        cache,
                        expected_identity,
                        "invalid_identity",
                        context,
                        trigger=trigger,
                    )
                    return
                _t38c_residency_outcome(
                    cache,
                    expected_identity or identity,
                    context,
                    "invalid_identity",
                    retry_epoch=retry_epoch,
                    poll_attempt=poll_attempt,
                    trigger=trigger,
                )
                return
            if identity not in getattr(cache, "_t38c_build_identities", set()):
                _t38c_residency_outcome(
                    cache,
                    identity,
                    context,
                    "build_not_ready",
                    retry_epoch=retry_epoch,
                    poll_attempt=poll_attempt,
                    trigger=trigger,
                )
                return
            if identity in getattr(cache, "_t38c_residency_retired", set()):
                return
            lifecycle = cache._t38c_residency_lifecycle.setdefault(
                identity,
                {
                    "state": "BUILD_CREATED",
                    "build_event_id": None,
                    "durability_event_id": None,
                    "component_snapshot": None,
                    "queue_snapshot": None,
                    "publication_event_id": None,
                    "retirement_reason": None,
                    "reconcile_attempt_count": 0,
                    "reason_attempt_counts": {},
                    "diagnostic_reason_set": set(),
                    "suppressed_diagnostic_count": 0,
                    "first_failure_reason": None,
                    "first_failure_event_id": None,
                    "first_attempt_ts_mono_ns": None,
                    "last_attempt_ts_mono_ns": None,
                    "first_attempt_event_id": None,
                    "last_attempt_event_id": None,
                    "terminal_event_id": None,
                    "detach_expectations_registered": False,
                    "detach_manifest": set(),
                },
            )
            attempt_count = lifecycle.get("reconcile_attempt_count", 0) + 1
            attempt_event_id = (
                f"{identity[0]}:{identity[3]}:reconcile:{attempt_count}"
            )
            attempt_ts = time.monotonic_ns()
            lifecycle["reconcile_attempt_count"] = attempt_count
            lifecycle.setdefault("first_attempt_ts_mono_ns", attempt_ts)
            lifecycle["last_attempt_ts_mono_ns"] = attempt_ts
            lifecycle.setdefault("first_attempt_event_id", attempt_event_id)
            lifecycle["last_attempt_event_id"] = attempt_event_id
            if identity in cache._t38c_residency_barriers:
                _t38c_residency_outcome(
                    cache,
                    identity,
                    context,
                    "barrier_already_published",
                    retry_epoch=retry_epoch,
                    poll_attempt=poll_attempt,
                    trigger=trigger,
                )
                return
            expected = cache._t38c_residency_detached.get(identity, set())
            if not lifecycle.get("detach_expectations_registered"):
                _t38c_residency_outcome(
                    cache,
                    identity,
                    context,
                    "detach_not_sealed",
                    retry_epoch=retry_epoch,
                    poll_attempt=poll_attempt,
                    trigger=trigger,
                )
                return
            if not expected:
                _t38c_residency_outcome(
                    cache,
                    identity,
                    context,
                    "no_detach",
                    retry_epoch=retry_epoch,
                    poll_attempt=poll_attempt,
                    trigger=trigger,
                )
                return
            if not any(key[2] == "device" for key in expected):
                _t38c_residency_outcome(
                    cache,
                    identity,
                    context,
                    "no_device_detach",
                    retry_epoch=retry_epoch,
                    poll_attempt=poll_attempt,
                    trigger=trigger,
                )
                return
            if lifecycle.get("state") == "BUILD_CREATED":
                lifecycle["state"] = "DETACHING"
            snapshot = _t38c_residency_component_snapshot(node)
            lifecycle["component_snapshot"] = snapshot
            if snapshot.get("unsupported_component"):
                _t38c_residency_retire(
                    cache,
                    identity,
                    "unsupported_component",
                    context,
                    trigger=trigger,
                )
                return
            if not snapshot["snapshot_complete"]:
                _t38c_residency_outcome(
                    cache,
                    identity,
                    context,
                    "component_snapshot_incomplete",
                    retry_epoch=retry_epoch,
                    poll_attempt=poll_attempt,
                    trigger=trigger,
                    component_snapshot=snapshot,
                )
                return
            if snapshot["live_component_count"]:
                if lifecycle.get("detach_sealed"):
                    _t38c_residency_retire(
                        cache,
                        identity,
                        "component_reattached_after_seal",
                        context,
                        trigger=trigger,
                    )
                    return
                _t38c_residency_outcome(
                    cache,
                    identity,
                    context,
                    "live_component_value",
                    retry_epoch=retry_epoch,
                    poll_attempt=poll_attempt,
                    trigger=trigger,
                    component_snapshot=snapshot,
                )
                return
            lifecycle["detach_sealed"] = True
            lifecycle["state"] = "DETACH_SEALED"
            if identity not in getattr(cache, "_t38c_durability_ready", set()):
                _t38c_residency_outcome(
                    cache,
                    identity,
                    context,
                    "durability_not_ready",
                    retry_epoch=retry_epoch,
                    poll_attempt=poll_attempt,
                    trigger=trigger,
                    component_snapshot=snapshot,
                )
                return
            lifecycle["state"] = "DURABILITY_READY"
            if any(
                (identity, pool, tier, digest, token)
                not in cache._t38c_residency_completed
                for _node, pool, tier, digest, token in expected
            ):
                _t38c_residency_outcome(
                    cache,
                    identity,
                    context,
                    "token_incomplete",
                    retry_epoch=retry_epoch,
                    poll_attempt=poll_attempt,
                    trigger=trigger,
                    component_snapshot=snapshot,
                )
                return
            lifecycle["state"] = "FREES_COMPLETE"
            cache_controller = getattr(cache, "cache_controller", None)
            if cache_controller is None:
                _t38c_residency_outcome(
                    cache,
                    identity,
                    context,
                    "queue_surface_missing",
                    retry_epoch=retry_epoch,
                    poll_attempt=poll_attempt,
                    trigger=trigger,
                    component_snapshot=snapshot,
                )
                return
            release_handoff_lock = getattr(
                cache_controller, "_t38c_release_handoff_lock", None
            )
            release_queue = getattr(cache_controller, "host_mem_release_queue", None)
            extra_release_queues = getattr(
                cache_controller, "extra_host_mem_release_queues", None
            )
            if (
                release_handoff_lock is None
                or release_queue is None
                or extra_release_queues is None
            ):
                _t38c_residency_outcome(
                    cache,
                    identity,
                    context,
                    "queue_surface_missing",
                    retry_epoch=retry_epoch,
                    poll_attempt=poll_attempt,
                    trigger=trigger,
                    component_snapshot=snapshot,
                )
                return
            with release_handoff_lock:
                extra_emptiness = {
                    str(pool): queue.empty()
                    for pool, queue in extra_release_queues.items()
                }
                queue_snapshot = {
                    "queue_snapshot_locked": True,
                    "primary_queue_empty": release_queue.empty(),
                    "extra_queue_empty": all(extra_emptiness.values()),
                    "extra_queue_emptiness": extra_emptiness,
                }
                lifecycle["queue_snapshot"] = queue_snapshot
                if not queue_snapshot["primary_queue_empty"] or not queue_snapshot[
                    "extra_queue_empty"
                ]:
                    cache._t38c_residency_queue_blocked.add(identity)
                    cache._t38c_residency_reconcile_ready.add(identity)
                    _t38c_residency_outcome(
                        cache,
                        identity,
                        context,
                        "queue_nonempty",
                        retry_epoch=retry_epoch,
                        poll_attempt=poll_attempt,
                        trigger=trigger,
                        queue_snapshot=queue_snapshot,
                        component_snapshot=snapshot,
                    )
                    return
                lifecycle["state"] = "QUEUES_EMPTY"
                event_id = _t38c_durable_log(
                    {
                        "evt": "residency_barrier",
                        "trace_context": context,
                        "run_id": identity[0],
                        "session_id": identity[1],
                        "session_generation": identity[2],
                        "build_rid": identity[3],
                        "warm_rid": None,
                        "node_id": str(node_id),
                        "final_kv_hash": final_kv_hash,
                        "result": True,
                        "reason": "all_detached_frees_complete",
                        "cold_residency": True,
                        "lifecycle_state_before": "QUEUES_EMPTY",
                        "trigger": trigger,
                        "build_event_id": lifecycle.get("build_event_id"),
                        "durability_event_id": lifecycle.get("durability_event_id"),
                        "expected_release_count": len(expected),
                        "completed_release_count": sum(
                            1
                            for completed in cache._t38c_residency_completed
                            if completed[0] == identity
                        ),
                        **snapshot,
                        **queue_snapshot,
                        "reconcile_attempt_count": lifecycle.get(
                            "reconcile_attempt_count", 0
                        ),
                        "suppressed_diagnostic_count": lifecycle.get(
                            "suppressed_diagnostic_count", 0
                        ),
                    }
                )
            if event_id is None:
                _t38c_residency_outcome(
                    cache,
                    identity,
                    context,
                    "logger_failed",
                    retry_epoch=retry_epoch,
                    poll_attempt=poll_attempt,
                    queue_snapshot=queue_snapshot,
                    trigger=trigger,
                    component_snapshot=snapshot,
                )
                return
            lifecycle["state"] = "RESIDENCY_PUBLISHED"
            lifecycle["publication_event_id"] = event_id
            _t38c_residency_outcome(
                cache,
                identity,
                context,
                "published",
                retry_epoch=retry_epoch,
                poll_attempt=poll_attempt,
                result=True,
                queue_snapshot=queue_snapshot,
                trigger=trigger,
                component_snapshot=snapshot,
                terminal=True,
            )
            # The identity, rather than the physical token set, is the
            # logical publication key. New recycle tokens cannot republish it.
            cache._t38c_residency_barriers.add(identity)
            cache._t38c_residency_reconcile_ready.discard(identity)
            cache._t38c_residency_queue_blocked.discard(identity)
            for _node, _pool, _tier, _digest, token in expected:
                cache._t38c_residency_completed.discard(
                    (identity, _pool, _tier, _digest, token)
                )
                retire_slot_token(token)
            cache._t38c_residency_detached.pop(identity, None)
        except Exception as exc:
            # A deleted node cannot be snapshotted; keyed detach/completion
            # records remain the only valid evidence in that case.
            _t38c_residency_outcome(
                cache,
                identity,
                context,
                "exception",
                retry_epoch=retry_epoch,
                poll_attempt=poll_attempt,
                exception_type=type(exc).__name__,
                trigger=trigger,
            )
            return


def _t38c_poll_residency_barriers(cache):
    """Reconcile only explicitly queued identities; watchdog is optional."""
    if not _t38c_durable_enabled():
        return
    with cache._t38c_residency_lock:
        retry_epoch = getattr(cache, "_t38c_residency_retry_epoch", 0) + 1
        cache._t38c_residency_retry_epoch = retry_epoch
        # Defensive one-time cleanup for fixtures or a process that inherited
        # legacy pending entries. Current detach admission never creates these.
        for identity in tuple(cache._t38c_residency_detached):
            if identity not in getattr(cache, "_t38c_build_identities", set()):
                cache._t38c_residency_retired.add(identity)
                _t38c_residency_retire(
                    cache, identity, "retired_ineligible", trigger="poll_prune"
                )
        pending = tuple(
            getattr(cache, "_t38c_residency_reconcile_ready", set())
        )
        cache._t38c_residency_reconcile_ready.difference_update(pending)
    for poll_attempt, identity in enumerate(pending, start=1):
        _t38c_residency_barrier(
            cache,
            identity[4],
            expected_identity=identity,
            retry_epoch=retry_epoch,
            poll_attempt=poll_attempt,
            trigger="release_queues_drained",
        )


def _t38c_residency_log(cache, node_id, result, reason: str) -> None:
    if not _t38c_durable_enabled():
        return
    try:
        node = cache.tree_core.node_by_id(node_id)
        manifest = set()
        unsupported = False
        for tier, frees in (
            ("device", result.device_frees),
            ("host", result.host_frees),
        ):
            for component_type, values in frees.items():
                if not values:
                    continue
                pool = _t38c_pool_name(component_type)
                if component_type not in (ComponentType.FULL, ComponentType.MAMBA):
                    unsupported = True
                    continue
                manifest.add((pool, tier))
                digest = _t38c_slot_digest(pool, values)
                _t38c_durable_log(
                    {
                        "evt": "residency_detach",
                        "trace_context": cache._t38c_trace_context_for_node(node_id),
                        "node_id": str(node_id),
                        "final_kv_hash": node.get_last_hash_value() or "",
                        "pool": pool,
                        "tier": tier,
                        "slot_count": _t38c_free_slots({component_type: values}),
                        "slot_digest": digest,
                        "reason": reason,
                        "result": "detached",
                    }
                )
                _t38c_note_detach(cache, node_id, pool, tier, digest)
        if manifest or unsupported:
            _t38c_residency_seal_detach(
                cache, node_id, manifest, unsupported=unsupported
            )
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

        self._t38c_node_contexts = {}
        self._t38c_node_context_index = {}
        self._t38c_session_contexts = {}
        self._t38c_session_builds = {}
        self._t38c_request_contexts = {}
        self._t38c_durability_evidence = {}
        self._t38c_mamba_boundaries = {}
        self._t38c_build_identities = set()
        self._t38c_durability_ready = set()
        self._t38c_residency_lock = threading.RLock()
        self._t38c_residency_detached = {}
        self._t38c_residency_completed = set()
        self._t38c_residency_barriers = set()
        self._t38c_residency_outcomes = set()
        self._t38c_residency_retry_epoch = 0
        self._t38c_residency_lifecycle = {}
        self._t38c_residency_retired = set()
        self._t38c_residency_reconcile_ready = set()
        self._t38c_residency_queue_blocked = set()

        # Cache-owned, process-local invalidation state for HOST_ALLOC wakes.
        # The scheduler may observe this state but never synthesizes or mutates
        # it.  A reset creates a new instance identity so old cursors cannot
        # compare equal to the new cache state.
        self._host_allocability_instance_id = 0
        self._host_allocability_generations: dict[str, int] = {}
        self._host_allocability_telemetry_seq = 0
        self._host_allocability_telemetry_mutations = {}
        self._host_allocability_telemetry_emitted = {}
        self._host_allocability_telemetry_last_emitted = {}
        self._host_allocability_telemetry_total_emitted = 0

        self.reset()
        logger.info(
            f"Init Unified Radix Cache. Components: {self.tree_components}. "
            f"Tree Core: {type(self.tree_core).__name__}"
        )

    def _t38c_note_residency_detach(
        self, node_id, pool, tier, slot_digest
    ) -> None:
        _t38c_note_detach(self, node_id, pool, tier, slot_digest)

    def _t38c_note_residency_completion(self, pool, tier, slot_digest) -> None:
        _t38c_note_completion(
            self,
            pool,
            tier,
            slot_digest,
            token=slot_token(pool, tier, slot_digest),
        )

    @staticmethod
    def _t38c_req_session_id(req):
        return getattr(req, "session_id", None) or getattr(
            getattr(req, "session", None), "session_id", None
        )

    def _t38c_trace_context_for_req(self, req, warm: bool = False):
        if not durable_trace_enabled() or req is None:
            return None
        session_id = self._t38c_req_session_id(req)
        session_generation = getattr(req, "session_generation", None)
        if not session_id or session_generation is None:
            return None
        session_key = (str(session_id), session_generation)
        build_rid = self._t38c_session_builds.get(session_key)
        context = (
            self._t38c_session_contexts.get(
                (session_key[0], session_key[1], build_rid)
            )
            if build_rid is not None
            else None
        )
        if context is None:
            context = make_trace_context(
                session_id,
                session_generation,
                getattr(req, "rid", None),
            )
        if context is None:
            return None
        context = dict(context)
        run_id = os.environ.get("T38C_RUN_ID")
        if not isinstance(run_id, str) or not run_id.strip():
            return None
        context["run_id"] = run_id
        if warm and context.get("build_rid") != getattr(req, "rid", None):
            context["warm_rid"] = str(getattr(req, "rid", "")) or None
        return context

    def _t38c_retire_session_trace(self, session_id) -> None:
        # The V4.3 dependency-free retirement probe extracts this method onto
        # a legacy fixture that predates the cache-owned ledger. Keep that
        # probe compatible without making the product path consult globals.
        legacy_mode = False
        if not hasattr(self, "_t38c_residency_lock"):
            detached = globals().get("_T38C_DURABLE_DETACHED")
            completed = globals().get("_T38C_DURABLE_COMPLETED")
            barriers = globals().get("_T38C_DURABLE_BARRIERS")
            if (
                detached is not None
                and completed is not None
                and barriers is not None
            ):
                if not session_id:
                    return
                session_id = str(session_id)
                retired_tokens = {
                    key[-1]
                    for keys in detached.values()
                    for key in keys
                    if len(key) == 5 and key[-1][1] == session_id
                }
                retired_tokens.update(
                    entry[-1]
                    for entry in completed
                    if len(entry) == 4
                    and isinstance(entry[-1], tuple)
                    and len(entry[-1]) > 1
                    and entry[-1][1] == session_id
                )
                for node_id in list(detached):
                    kept = {
                        key
                        for key in detached[node_id]
                        if key[-1] not in retired_tokens
                    }
                    if kept:
                        detached[node_id] = kept
                    else:
                        detached.pop(node_id, None)
                completed.difference_update(
                    {
                        entry
                        for entry in completed
                        if len(entry) == 4
                        and isinstance(entry[-1], tuple)
                        and len(entry[-1]) > 1
                        and entry[-1][1] == session_id
                    }
                )
                barriers.difference_update(
                    {
                        barrier
                        for barrier in barriers
                        if any(
                            len(key) == 5 and key[-1] in retired_tokens
                            for key in barrier[1]
                        )
                    }
                )
                self._t38c_session_builds = {
                    key: build
                    for key, build in self._t38c_session_builds.items()
                    if key[0] != session_id
                }
                self._t38c_session_contexts = {
                    key: context
                    for key, context in self._t38c_session_contexts.items()
                    if key[0] != session_id
                }
                self._t38c_node_contexts = {
                    key: context
                    for key, context in self._t38c_node_contexts.items()
                    if context.get("session_id") != session_id
                }
                self._t38c_node_context_index = {
                    node_id: key
                    for node_id, key in self._t38c_node_context_index.items()
                    if key in self._t38c_node_contexts
                }
                self._t38c_request_contexts = {
                    key: context
                    for key, context in self._t38c_request_contexts.items()
                    if context.get("session_id") != session_id
                }
                self._t38c_build_identities = {
                    identity
                    for identity in getattr(
                        self, "_t38c_build_identities", set()
                    )
                    if len(identity) < 6 or identity[1] != session_id
                }
                self._t38c_durability_ready = {
                    identity
                    for identity in getattr(
                        self, "_t38c_durability_ready", set()
                    )
                    if len(identity) < 6 or identity[1] != session_id
                }
                mamba_boundaries = getattr(self, "_t38c_mamba_boundaries", {})
                self._t38c_mamba_boundaries = {
                    key: boundaries
                    for key, boundaries in mamba_boundaries.items()
                    if key[0] != session_id
                }

                def _candidate_belongs_to_session(candidate):
                    if not isinstance(candidate, dict):
                        return False
                    context = candidate.get("trace_context")
                    return (
                        isinstance(context, dict)
                        and context.get("session_id") == session_id
                    )

                for node_id, candidates in list(
                    self._t38c_durability_evidence.items()
                ):
                    if not isinstance(candidates, dict):
                        if _candidate_belongs_to_session(candidates):
                            self._t38c_durability_evidence.pop(node_id, None)
                        continue
                    kept_candidates = {
                        attempt_key: candidate
                        for attempt_key, candidate in candidates.items()
                        if not _candidate_belongs_to_session(candidate)
                    }
                    if kept_candidates:
                        self._t38c_durability_evidence[node_id] = kept_candidates
                    else:
                        self._t38c_durability_evidence.pop(node_id, None)
                if self.cache_controller is not None:
                    retire_tokens = getattr(
                        self.cache_controller,
                        "_t38c_retire_host_mem_release_tokens",
                        None,
                    )
                    if retire_tokens is not None:
                        retire_tokens(session_id)
                retire_slot_contexts(session_id)
                return
        with self._t38c_residency_lock:
            self._t38c_retire_session_trace_locked(
                session_id, legacy_mode=legacy_mode
            )

    def _t38c_retire_session_trace_locked(
        self, session_id, *, legacy_mode: bool = False
    ) -> None:
        if not session_id:
            return
        session_id = str(session_id)
        self._t38c_session_builds = {
            key: build
            for key, build in self._t38c_session_builds.items()
            if key[0] != session_id
        }
        self._t38c_session_contexts = {
            key: context
            for key, context in self._t38c_session_contexts.items()
            if key[0] != session_id
        }
        self._t38c_node_contexts = {
            key: context
            for key, context in self._t38c_node_contexts.items()
            if context.get("session_id") != session_id
        }
        self._t38c_node_context_index = {
            node_id: key
            for node_id, key in self._t38c_node_context_index.items()
            if key in self._t38c_node_contexts
        }
        self._t38c_request_contexts = {
            key: context
            for key, context in self._t38c_request_contexts.items()
            if context.get("session_id") != session_id
        }
        self._t38c_build_identities = {
            identity
            for identity in getattr(self, "_t38c_build_identities", set())
            if len(identity) < 6 or identity[1] != session_id
        }
        self._t38c_durability_ready = {
            identity
            for identity in getattr(self, "_t38c_durability_ready", set())
            if len(identity) < 6 or identity[1] != session_id
        }
        mamba_boundaries = getattr(self, "_t38c_mamba_boundaries", {})
        self._t38c_mamba_boundaries = {
            key: boundaries
            for key, boundaries in mamba_boundaries.items()
            if key[0] != session_id
        }

        # Contextless marker-off ACKs have no authoritative session identity;
        # keep them until a full reset and retire only explicitly identified
        # evidence for the session being released.
        def _candidate_belongs_to_session(candidate):
            if not isinstance(candidate, dict):
                return False
            context = candidate.get("trace_context")
            return (
                isinstance(context, dict)
                and context.get("session_id") == session_id
            )

        for node_id, candidates in list(
            self._t38c_durability_evidence.items()
        ):
            if not isinstance(candidates, dict):
                if _candidate_belongs_to_session(candidates):
                    self._t38c_durability_evidence.pop(node_id, None)
                continue
            kept_candidates = {
                attempt_key: candidate
                for attempt_key, candidate in candidates.items()
                if not _candidate_belongs_to_session(candidate)
            }
            if kept_candidates:
                self._t38c_durability_evidence[node_id] = kept_candidates
            else:
                self._t38c_durability_evidence.pop(node_id, None)
        if not legacy_mode:
            retired_identities = {
                identity
                for identity in self._t38c_residency_detached
                if len(identity) >= 6 and identity[1] == session_id
            }
            for identity in retired_identities:
                self._t38c_residency_retired.add(identity)
                _t38c_residency_retire(
                    self,
                    identity,
                    "identity_retired",
                    trigger="session_retired",
                )
            retired_tokens = {
                entry[-1]
                for identity in retired_identities
                for entry in self._t38c_residency_detached.get(identity, ())
            }
            self._t38c_residency_detached = {
                identity: expected
                for identity, expected in self._t38c_residency_detached.items()
                if len(identity) < 6 or identity[1] != session_id
            }
            self._t38c_residency_completed = {
                entry
                for entry in self._t38c_residency_completed
                if len(entry[0]) < 6 or entry[0][1] != session_id
            }
            self._t38c_residency_barriers = {
                identity
                for identity in self._t38c_residency_barriers
                if len(identity) < 6 or identity[1] != session_id
            }
            for token in retired_tokens:
                retire_slot_token(token)
        if self.cache_controller is not None:
            retire_tokens = getattr(
                self.cache_controller,
                "_t38c_retire_host_mem_release_tokens",
                None,
            )
            if retire_tokens is not None:
                retire_tokens(session_id)
        if legacy_mode:
            retire_slot_contexts(session_id)

    def _t38c_select_promoted_candidate(self, node_id, final_kv_hash):
        """Select one node-bound attempt, or fail closed on ambiguity."""
        candidates = self._t38c_durability_evidence.get(str(node_id), {})
        matches = [
            (attempt_key, candidate)
            for attempt_key, candidate in candidates.items()
            if candidate.get("node_id") == str(node_id)
            and candidate.get("final_kv_hash") == final_kv_hash
        ]
        # There is no tree-owned generation in this path. Same-hash attempts
        # are therefore unambiguous only when exactly one remains.
        return matches[0] if len(matches) == 1 else (None, None)

    def _t38c_record_node_context(self, req, node_id) -> None:
        context = self._t38c_trace_context_for_req(req)
        if context is None or not durable_trace_enabled():
            return
        session_id = context["session_id"]
        session_generation = context["session_generation"]
        build_rid = context["build_rid"]
        session_key = (session_id, session_generation)
        context_key = (session_id, session_generation, build_rid)
        self._t38c_session_builds.setdefault(session_key, build_rid)
        self._t38c_session_contexts.setdefault(context_key, dict(context))
        node = self.tree_core.node_by_id(node_id)
        while node is not None and node is not self.tree_core.root_node:
            node_id = str(node.id)
            try:
                final_kv_hash = node.get_last_hash_value()
            except (AttributeError, TypeError):
                return
            if not isinstance(final_kv_hash, str) or not final_kv_hash:
                return
            node_context = dict(context)
            node_context["node_id"] = node_id
            node_context["final_kv_hash"] = final_kv_hash
            key = (session_id, session_generation, build_rid, node_id)
            candidate_keys = [
                candidate_key
                for candidate_key in self._t38c_node_contexts
                if len(candidate_key) == 4 and candidate_key[-1] == node_id
            ]
            conflicting = any(
                self._t38c_node_contexts[candidate_key] != node_context
                for candidate_key in candidate_keys
            )
            ambiguous = conflicting or (
                node_id in self._t38c_node_context_index
                and self._t38c_node_context_index[node_id] is None
            )
            if ambiguous:
                # Preserve ambiguity permanently for this live node. A node
                # sidecar must never be last-write-wins across build contexts.
                self._t38c_node_context_index[node_id] = None
            elif candidate_keys:
                self._t38c_node_context_index[node_id] = candidate_keys[0]
            existing = self._t38c_node_contexts.get(key)
            if existing is not None:
                break
            self._t38c_node_contexts[key] = node_context
            if not ambiguous:
                self._t38c_node_context_index[node_id] = key
            node = node.parent

    @staticmethod
    def _t38c_has_live_value(value) -> bool:
        if value is None:
            return False
        try:
            return len(value) > 0
        except TypeError:
            return True

    def _t38c_record_mamba_boundary(
        self, req, node_id, effective_cache_len, insert_params, result
    ) -> None:
        """Remember only a real nonzero KV+Mamba checkpoint for this request."""
        if (
            effective_cache_len <= 0
            or ComponentType.MAMBA not in self.tree_components
            or insert_params is None
            or insert_params.mamba_value is None
            or result is None
            or result.mamba_exist
        ):
            return
        context = self._t38c_trace_context_for_req(req)
        request_rid = getattr(req, "rid", None)
        if not isinstance(context, dict) or not request_rid or any(
            (
                context.get("schema_version") != "p0_durable.v3",
                not context.get("session_id"),
                context.get("session_generation") is None,
                not context.get("build_rid"),
                context.get("warm_rid") is not None,
                str(request_rid) != context.get("build_rid"),
            )
        ):
            return
        try:
            node = self.tree_core.node_by_id(node_id)
        except (AttributeError, IndexError, KeyError, TypeError):
            return
        if node is self.tree_core.root_node or getattr(
            node, "forced_miss_tombstone", False
        ):
            return
        if any(
            not any(
                self._t38c_has_live_value(getattr(node.component_data[ct], field))
                for field in ("value", "host_value")
            )
            for ct in (ComponentType.FULL, ComponentType.MAMBA)
        ):
            return
        try:
            final_kv_hash = node.get_last_hash_value()
        except (AttributeError, TypeError):
            return
        if not final_kv_hash:
            return
        key = (
            str(context["session_id"]),
            context["session_generation"],
            str(context["build_rid"]),
        )
        boundary = {
            "node_id": node.id,
            "request_rid": str(request_rid),
            "effective_cache_len": int(effective_cache_len),
            "final_kv_hash": final_kv_hash,
            "trace_context": dict(context),
        }
        boundaries = self._t38c_mamba_boundaries.setdefault(key, [])
        if boundary not in boundaries:
            boundaries.append(boundary)

    def _t38c_finished_boundary_result(self, req, *, is_abort: bool):
        """Return a validated prior boundary, never a synthetic root result."""
        if is_abort or getattr(req, "finished_reason", None) is None:
            return None
        context = self._t38c_trace_context_for_req(req)
        request_rid = getattr(req, "rid", None)
        if not isinstance(context, dict) or not request_rid or any(
            (
                context.get("schema_version") != "p0_durable.v3",
                not context.get("session_id"),
                context.get("session_generation") is None,
                not context.get("build_rid"),
                context.get("warm_rid") is not None,
                str(request_rid) != context.get("build_rid"),
            )
        ):
            return None
        candidate_id = getattr(getattr(req, "last_node", None), "id", None)
        if candidate_id is None:
            candidate_id = getattr(req, "last_node", None)
        key = (
            str(context["session_id"]),
            context["session_generation"],
            str(context["build_rid"]),
        )
        matches = [
            boundary
            for boundary in self._t38c_mamba_boundaries.get(key, ())
            if boundary["node_id"] == candidate_id
            and boundary["request_rid"] == str(request_rid)
            and boundary["trace_context"] == context
        ]
        if len(matches) != 1:
            return None
        try:
            node = self.tree_core.node_by_id(candidate_id)
        except (AttributeError, IndexError, KeyError, TypeError):
            return None
        if node is self.tree_core.root_node or getattr(
            node, "forced_miss_tombstone", False
        ):
            return None
        if any(
            not any(
                self._t38c_has_live_value(getattr(node.component_data[ct], field))
                for field in ("value", "host_value")
            )
            for ct in (ComponentType.FULL, ComponentType.MAMBA)
        ):
            return None
        try:
            final_kv_hash = node.get_last_hash_value()
        except (AttributeError, TypeError):
            return None
        node_id = str(getattr(node, "id", ""))
        # The old _t38c_trace_context_for_node(node_id) != context check is
        # now a stable-field comparison because sidecars carry node identity.
        node_context = self._t38c_trace_context_for_node(node_id)
        if (
            not node_id
            or not isinstance(final_kv_hash, str)
            or not final_kv_hash
            or final_kv_hash != matches[0]["final_kv_hash"]
            or node_context is None
            or any(
                node_context.get(field) != context.get(field)
                for field in (
                    "schema_version",
                    "run_id",
                    "session_id",
                    "session_generation",
                    "build_rid",
                    "warm_rid",
                )
            )
        ):
            return None
        return InsertResult(
            prefix_len=matches[0]["effective_cache_len"],
            last_device_node=node.id,
        )

    def _t38c_is_tp_group_leader(self) -> bool:
        """Return true only for the canonical initialized TP-group leader."""
        tp_world_size = getattr(self, "tp_world_size", None)
        if tp_world_size == 1:
            return True
        if tp_world_size is None or self.tp_group is None:
            return False
        try:
            if not torch.distributed.is_available():
                return False
            if not torch.distributed.is_initialized():
                return False
            return torch.distributed.get_rank(group=self.tp_group) == 0
        except Exception:
            return False

    def _t38c_emit_build_complete(
        self, req, result, *, is_insert: bool, is_abort: bool
    ) -> None:
        """Emit the product-owned V3 build identity after a final insert."""
        if not durable_trace_enabled():
            _t38c_build_complete_debug("durable_trace_disabled")
            return
        if not is_insert:
            _t38c_build_complete_debug("not_insert")
            return
        if is_abort:
            _t38c_build_complete_debug("abort")
            return
        if result is None:
            _t38c_build_complete_debug("missing_result")
            return
        if getattr(req, "finished_reason", None) is None:
            _t38c_build_complete_debug("unfinished_request")
            return
        if not self._t38c_is_tp_group_leader():
            _t38c_build_complete_debug("not_tp_group_leader")
            return

        context = self._t38c_trace_context_for_req(req)
        if not isinstance(context, dict) or any(
            (
                context.get("schema_version") != "p0_durable.v3",
                not context.get("session_id"),
                context.get("session_generation") is None,
                not context.get("build_rid"),
                context.get("warm_rid") is not None,
            )
        ):
            _t38c_build_complete_debug("invalid_request_context")
            return

        request_rid = getattr(req, "rid", None)
        if not request_rid or str(request_rid) != context["build_rid"]:
            _t38c_build_complete_debug("request_build_rid_mismatch")
            return

        node = getattr(result, "last_device_node", None)
        if node is None:
            _t38c_build_complete_debug("missing_node")
            return
        if node is self.tree_core.root_node:
            _t38c_build_complete_debug("root_node")
            return
        if not hasattr(node, "get_last_hash_value"):
            try:
                node = self.tree_core.node_by_id(node)
            except (AttributeError, IndexError, KeyError, TypeError):
                _t38c_build_complete_debug("node_lookup_failed")
                return
        if node is None:
            _t38c_build_complete_debug("missing_node")
            return
        if node is self.tree_core.root_node:
            _t38c_build_complete_debug("root_node")
            return
        node_id = str(getattr(node, "id", ""))
        try:
            final_kv_hash = node.get_last_hash_value()
        except (AttributeError, TypeError):
            _t38c_build_complete_debug("node_hash_lookup_failed")
            return
        if not node_id or not isinstance(final_kv_hash, str) or not final_kv_hash:
            _t38c_build_complete_debug("invalid_node_identity")
            return

        node_context = self._t38c_trace_context_for_node(node_id)
        if node_context is None or any(
            node_context.get(field) != context.get(field)
            for field in (
                "schema_version",
                "run_id",
                "session_id",
                "session_generation",
                "build_rid",
                "warm_rid",
            )
        ):
            _t38c_build_complete_debug("node_context_mismatch")
            return

        event_id = _t38c_durable_log(
            {
                "evt": "build_complete",
                "trace_context": context,
                "session_id": context["session_id"],
                "session_generation": context["session_generation"],
                "build_rid": context["build_rid"],
                "warm_rid": None,
                "node_id": node_id,
                "final_kv_hash": final_kv_hash,
                "operation_id": None,
                "attempt_id": None,
                "result": True,
            }
        )
        if event_id is not None:
            identity = _t38c_residency_identity(
                node_context, node_id, final_kv_hash
            )
            if identity is not None:
                if not hasattr(self, "_t38c_residency_lock"):
                    self._t38c_build_identities.add(identity)
                else:
                    with self._t38c_residency_lock:
                        self._t38c_build_identities.add(identity)
                        lifecycle = self._t38c_residency_lifecycle.setdefault(
                            identity,
                            {
                                "state": "BUILD_CREATED",
                                "build_event_id": None,
                                "durability_event_id": None,
                                "component_snapshot": None,
                                "queue_snapshot": None,
                                "publication_event_id": None,
                                "retirement_reason": None,
                                "reconcile_attempt_count": 0,
                                "reason_attempt_counts": {},
                                "diagnostic_reason_set": set(),
                                "suppressed_diagnostic_count": 0,
                                "first_failure_reason": None,
                                "first_failure_event_id": None,
                                "first_attempt_ts_mono_ns": None,
                                "last_attempt_ts_mono_ns": None,
                                "first_attempt_event_id": None,
                                "last_attempt_event_id": None,
                                "terminal_event_id": None,
                                "detach_expectations_registered": False,
                                "detach_manifest": set(),
                            },
                        )
                        lifecycle["build_event_id"] = event_id
                    _t38c_residency_reconcile(self, identity, "build_registered")

    def _t38c_trace_context_for_node(self, node_id):
        if not durable_trace_enabled():
            return None
        key = self._t38c_node_context_index.get(str(node_id))
        context = self._t38c_node_contexts.get(key) if key is not None else None
        return dict(context) if context else None

    def _t38c_trace_context_for_prefetch(self, req_id, node_id):
        context = self._t38c_trace_context_for_node(node_id)
        if context is None:
            context = next(
                (
                    value
                    for key, value in self._t38c_request_contexts.items()
                    if key[2] == str(req_id)
                ),
                None,
            )
        if context is None:
            return None
        context = dict(context)
        if context.get("build_rid") != req_id:
            context["warm_rid"] = str(req_id)
        return context

    def _t38c_mamba_rank_proof(
        self,
        operation,
        *,
        node_id,
        final_kv_hash,
        key_set_digest,
        key_count,
        local_mamba_durable,
        aggregate_rank_acks,
    ):
        expected_rank_set = getattr(operation, "_t38c_expected_rank_set", None)
        if expected_rank_set is None and self.cache_controller is not None:
            expected_rank_set = getattr(
                self.cache_controller, "_t38c_expected_rank_set", None
            )
        expected_rank_set = (
            sorted(str(rank) for rank in expected_rank_set)
            if expected_rank_set
            else []
        )
        local_rank = str(
            torch.distributed.get_rank(group=self.tp_group)
            if torch.distributed.is_available()
            and torch.distributed.is_initialized()
            else os.environ.get("RANK", "0")
        )
        attempt_id = getattr(operation, "trace_id", f"storage-{operation.id}")
        local_ack = {
            "operation_id": operation.id,
            "attempt_id": attempt_id,
            "node_id": str(node_id),
            "final_kv_hash": final_kv_hash,
            "mamba_key_set_digest": key_set_digest,
            "mamba_key_count": key_count,
            "rank": local_rank,
            "mamba_durable": bool(local_mamba_durable),
        }
        if self.tp_world_size == 1:
            observed = [local_rank] if local_mamba_durable else []
            return expected_rank_set, observed, not expected_rank_set, bool(
                expected_rank_set
                and set(observed) >= set(expected_rank_set)
                and local_mamba_durable
            )
        if not aggregate_rank_acks or not expected_rank_set:
            return expected_rank_set, (
                [local_rank] if local_mamba_durable else []
            ), not expected_rank_set, False

        gathered = [None] * self.tp_world_size
        torch.distributed.all_gather_object(
            gathered, local_ack, group=self.tp_group
        )
        matching = [
            ack
            for ack in gathered
            if isinstance(ack, dict)
            and (
                ack.get("operation_id"),
                ack.get("attempt_id"),
                ack.get("node_id"),
                ack.get("final_kv_hash"),
            )
            == (
                operation.id,
                attempt_id,
                str(node_id),
                final_kv_hash,
            )
            and ack.get("mamba_durable")
        ]
        observed = sorted({str(ack["rank"]) for ack in matching})
        all_rank_durable = set(observed) >= set(expected_rank_set)
        return expected_rank_set, observed, False, all_rank_durable

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
        self._host_allocability_instance_id += 1
        self._host_allocability_generations = {PoolName.KV.value: 0}
        self._host_allocability_telemetry_seq = 0
        self._host_allocability_telemetry_mutations = {}
        self._host_allocability_telemetry_emitted = {}
        self._host_allocability_telemetry_last_emitted = {}
        self._host_allocability_telemetry_total_emitted = 0
        getattr(self, "_storage_prefetch_terminal", {}).clear()
        getattr(self, "_storage_prefetch_completion", {}).clear()
        self.tree_core.reset()
        self.session_refs.reset()

        self._t38c_node_contexts.clear()
        self._t38c_node_context_index.clear()
        self._t38c_session_contexts.clear()
        self._t38c_session_builds.clear()
        self._t38c_request_contexts.clear()
        self._t38c_durability_evidence.clear()
        self._t38c_mamba_boundaries.clear()
        self._t38c_build_identities.clear()
        self._t38c_durability_ready.clear()
        with self._t38c_residency_lock:
            # Legacy AST fixture contract: retire_slot_contexts() remains
            # marker-off vocabulary; the product path retires owned tokens.
            owned_tokens = {
                entry[-1]
                for expected in self._t38c_residency_detached.values()
                for entry in expected
            }
            self._t38c_residency_detached.clear()
            self._t38c_residency_completed.clear()
            self._t38c_residency_barriers.clear()
            self._t38c_residency_outcomes.clear()
            self._t38c_residency_retry_epoch = 0
            self._t38c_residency_lifecycle.clear()
            self._t38c_residency_retired.clear()
            self._t38c_residency_reconcile_ready.clear()
            self._t38c_residency_queue_blocked.clear()
            for token in owned_tokens:
                retire_slot_token(token)
        if self.cache_controller is not None:
            reset_handoff = getattr(
                self.cache_controller, "_t38c_reset_release_handoff", None
            )
            if reset_handoff is not None:
                reset_handoff()

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
        self._storage_prefetch_terminal: dict[str, object] = {}
        # One-shot finalizer-owned material proof for the scheduler's
        # ready_host join. This is observational and does not participate in
        # restore or allocation decisions.
        self._storage_prefetch_completion: dict[str, object] = {}
        self._storage_prefetch_failures: dict[str, HostAllocFailure] = {}
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
        if durable_trace_enabled() and params.req is not None:
            session_id = self._t38c_req_session_id(params.req)
            session_generation = getattr(params.req, "session_generation", None)
            warm = (
                session_id is not None
                and session_generation is not None
                and (str(session_id), session_generation)
                in self._t38c_session_builds
            )
            context = self._t38c_trace_context_for_req(params.req, warm=warm)
            if context is not None:
                self._t38c_request_contexts[
                    (
                        context["session_id"],
                        context["session_generation"],
                        str(params.req.rid),
                    )
                ] = dict(context)
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
        _t38c_residency_log(self, node_id, result, "device_leaf")
        self._free_values(result.device_frees, result.host_frees)
        _t38c_residency_barrier(self, node_id)
        self._accumulate_tracker(tracker, result.tracker)
        return result.backup_kv

    def _demote(self, node_id: NodeId, tracker: dict[ComponentType, int]) -> None:
        """Demote a backed-up node, consuming its step result."""
        result = self.tree_core.demote(node_id)
        _t38c_residency_log(self, node_id, result, "demote")
        self._free_values(result.device_frees, result.host_frees)
        _t38c_residency_barrier(self, node_id)
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
        _t38c_residency_log(self, node_id, result, "storage_backed_hollow")
        self._free_values(result.device_frees, result.host_frees)
        _t38c_residency_barrier(self, node_id)
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
        _t38c_residency_log(self, node_id, result, "forced_miss")
        self._free_values(result.device_frees, result.host_frees)
        _t38c_residency_barrier(self, node_id)
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
        before = self._host_allocability_signatures()
        result = self.tree_core.dec_swa_lock_only(
            node_id, swa_uuid_for_lock, skip_lock_node_ids
        )
        self._free_values(result.device_frees, result.host_frees)
        self._bump_changed_host_allocability(before, "lock_release_evictable")

    def inc_host_lock_ref(self, node_id: NodeId) -> IncLockRefResult:
        if self.disable:
            return IncLockRefResult()
        return self.tree_core.inc_host_lock_ref(node_id)

    def dec_host_lock_ref(
        self, node_id: NodeId, params: Optional[DecLockRefParams] = None
    ) -> DecLockRefResult:
        if self.disable:
            return DecLockRefResult()
        before = self._host_allocability_signatures()
        result = self.tree_core.dec_host_lock_ref(node_id, params)
        self._bump_changed_host_allocability(before, "lock_release_evictable")
        return result

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
        event_result = None
        insert_params = None
        from sglang.srt.managers.schedule_batch import FINISH_ABORT

        is_abort = isinstance(req.finished_reason, FINISH_ABORT)

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

            if effective_cache_len <= 0:
                # Match the unfinished no-insert contract. In particular, do
                # not turn a missing Mamba boundary into an empty radix key.
                self.token_to_kv_pool_allocator.free_segment(
                    kv_indices[req.cache_protected_len :],
                    start_pos=req.cache_protected_len,
                )
                event_result = self._t38c_finished_boundary_result(
                    req, is_abort=is_abort
                )
            else:
                # Truncate if needed; the tail free is deferred and batched with
                # the unaligned tail below so a shared boundary page is emitted once.
                kv_indices_full = kv_indices
                tail_free_start = None
                if effective_cache_len < len(token_ids):
                    tail_free_start = max(
                        effective_cache_len, req.cache_protected_len
                    )
                    token_ids = token_ids[:effective_cache_len]
                    kv_indices = kv_indices[:effective_cache_len]

                radix_key = RadixKey(
                    token_ids,
                    req.extra_key,
                    is_bigram=self.tree_core.is_eagle,
                    cache_salt=req.cache_salt,
                ).page_aligned(self.page_size)
                page_aligned_len = len(radix_key)
                values = kv_indices[:page_aligned_len].to(
                    dtype=torch.int64, copy=True
                )

                insert_params.key = radix_key
                insert_params.value = values
                result = self.insert(insert_params)
                event_result = result

                # Free unaligned tail (+ deferred truncation tail)
                segments = [(kv_indices[page_aligned_len:], page_aligned_len)]
                if tail_free_start is not None:
                    segments.append(
                        (kv_indices_full[tail_free_start:], tail_free_start)
                    )
                self.token_to_kv_pool_allocator.free_segments(segments)
        else:
            self.token_to_kv_pool_allocator.free_segment(
                kv_indices[req.cache_protected_len :],
                start_pos=req.cache_protected_len,
            )

        self._dec_req_lock(req, skip_swa=req.swa_prefix_lock_released)

        if is_insert and result is not None and result.last_device_node is not None:
            req.last_node = result.last_device_node
            self._t38c_record_node_context(req, result.last_device_node)

        if is_insert and event_result is not None:
            self._t38c_emit_build_complete(
                req,
                event_result,
                is_insert=True,
                is_abort=is_abort,
            )

        # cleanup
        for comp in self._components_tuple:
            comp.cleanup_after_caching_req(
                req, is_finished=True, insert_result=result, insert_params=insert_params
            )

        if self.enable_session_radix_cache and event_result is not None:
            if req.finished_reason is not None and not is_abort:
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
        self._t38c_record_node_context(req, new_last_node)
        self._t38c_record_mamba_boundary(
            req,
            new_last_node,
            effective_cache_len,
            insert_params,
            result,
        )
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
            values = device_frees.pop(ct)
            tracing = _t38c_durable_enabled()
            pool = _t38c_pool_name(ct) if tracing else None
            digest = _t38c_slot_digest(pool, values) if tracing else None
            self._apply_cache_action(
                FreeComponentDeviceSlot(values, component_type=ct)
            )
            if tracing:
                trace_context = slot_context(pool, "device", digest)
                _t38c_note_completion(
                    self,
                    pool,
                    "device",
                    digest,
                    token=slot_token(pool, "device", digest),
                )
                _t38c_durable_log(
                    {
                        "evt": "residency_free_complete",
                        "trace_context": trace_context,
                        "pool": pool,
                        "tier": "device",
                        "slot_count": _t38c_free_slots({ct: values}),
                        "slot_digest": digest,
                        "result": True,
                        "reason": "allocator_free_returned",
                    }
                )

    @staticmethod
    def _host_allocability_pool_for_component(component_type: ComponentType) -> str:
        return _COMPONENT_POOL_LABEL.get(component_type, str(component_type))

    def _host_evictable_signature(self, pool: str) -> tuple[int, frozenset[int]]:
        """Return the tree-owned evictable summary for one host pool."""
        component_type = {
            PoolName.KV.value: BASE_COMPONENT_TYPE,
            PoolName.SWA.value: ComponentType.SWA,
            PoolName.MAMBA.value: ComponentType.MAMBA,
        }.get(pool)
        components = getattr(self, "components", {})
        if component_type is None or component_type not in components:
            return 0, frozenset()
        if pool == PoolName.KV.value:
            leaves = getattr(self.tree_core, "evictable_host_leaves", ())
            return (
                sum(
                    len(node.component_data[component_type].host_value)
                    for node in leaves
                    if node.component_data[component_type].host_value is not None
                ),
                frozenset(node.id for node in leaves),
            )
        host_lru = self.tree_core.host_lru_lists.get(component_type)
        if host_lru is None:
            return 0, frozenset()
        eligible = frozenset(
            node.id
            for node in host_lru.cache.values()
            if node.component_data[component_type].host_lock_ref == 0
            and node.component_data[component_type].host_value is not None
        )
        return (
            sum(
                len(host_lru.cache[node_id].component_data[component_type].host_value)
                for node_id in eligible
            ),
            eligible,
        )

    def _host_allocability_signatures(self) -> dict[str, tuple[int, frozenset[int]]]:
        pools = [PoolName.KV.value]
        pools.extend(
            self._host_allocability_pool_for_component(ct)
            for ct in self.components
            if ct != BASE_COMPONENT_TYPE
        )
        return {pool: self._host_evictable_signature(pool) for pool in pools}

    def _bump_host_allocability(
        self,
        pool: str,
        cause: str,
        returned_units: int = 0,
        *,
        evictable_before: Optional[int] = None,
        evictable_after: Optional[int] = None,
        causal_rid: Optional[str] = None,
        trace_context=None,
    ) -> None:
        """Advance one pool generation after a completed causal mutation.

        The generation and telemetry sequence advance for every mutation.
        Mutation records are observational samples keyed by pool, cause,
        request, and trace context: the first 16 per key are emitted, then
        every 128th mutation, with a 64-record per-key and 256-record
        per-cache-instance hard cap.  This preserves request/cause joins and
        sequence gaps while bounding log volume; it never changes wake or
        allocation behavior.
        """
        import json as _json

        returned_units = int(returned_units or 0)
        if returned_units <= 0 and cause != "lock_release_evictable":
            return
        pool = getattr(pool, "value", pool)
        generations = getattr(self, "_host_allocability_generations", None)
        if generations is None:
            generations = {}
            self._host_allocability_generations = generations
        before = generations.get(pool, 0)
        generations[pool] = before + 1
        if evictable_after is None:
            evictable_after = self._host_evictable_signature(pool)[0]
        if evictable_before is None:
            evictable_before = evictable_after
        self._host_allocability_telemetry_seq += 1

        trace_key = _json.dumps(trace_context, sort_keys=True, default=str)
        telemetry_key = (str(pool), str(cause), causal_rid, trace_key)
        mutations = getattr(self, "_host_allocability_telemetry_mutations", None)
        emitted = getattr(self, "_host_allocability_telemetry_emitted", None)
        last_emitted = getattr(
            self, "_host_allocability_telemetry_last_emitted", None
        )
        if mutations is None or emitted is None or last_emitted is None:
            mutations = {}
            emitted = {}
            last_emitted = {}
            self._host_allocability_telemetry_mutations = mutations
            self._host_allocability_telemetry_emitted = emitted
            self._host_allocability_telemetry_last_emitted = last_emitted
        if telemetry_key not in mutations and len(mutations) >= _HOST_ALLOC_MUTATION_TELEMETRY_MAX_KEYS:
            mutations.clear()
            emitted.clear()
            last_emitted.clear()
        mutation_count = mutations.get(telemetry_key, 0) + 1
        mutations[telemetry_key] = mutation_count
        key_emitted = emitted.get(telemetry_key, 0)
        total_emitted = getattr(
            self, "_host_allocability_telemetry_total_emitted", 0
        )
        should_emit = key_emitted < _HOST_ALLOC_MUTATION_TELEMETRY_HEAD or (
            mutation_count % _HOST_ALLOC_MUTATION_TELEMETRY_STRIDE == 0
            and key_emitted < _HOST_ALLOC_MUTATION_TELEMETRY_MAX_PER_KEY
        )
        if (
            not should_emit
            or key_emitted >= _HOST_ALLOC_MUTATION_TELEMETRY_MAX_PER_KEY
            or total_emitted >= _HOST_ALLOC_MUTATION_TELEMETRY_MAX_TOTAL
        ):
            return
        emitted[telemetry_key] = key_emitted + 1
        self._host_allocability_telemetry_total_emitted = total_emitted + 1
        previous_emitted_mutation = last_emitted.get(telemetry_key, 0)
        last_emitted[telemetry_key] = mutation_count
        _log_host_alloc_telemetry(
            "host_allocability_change",
            cache_instance_id=getattr(self, "_host_allocability_instance_id", 0),
            pool=pool,
            generation_before=before,
            generation_after=before + 1,
            cause=cause,
            returned_units=int(returned_units),
            evictable_before=int(evictable_before),
            evictable_after=int(evictable_after),
            causal_rid=causal_rid,
            trace_context=trace_context,
            telemetry_seq=self._host_allocability_telemetry_seq,
            telemetry_mutation_count=mutation_count,
            telemetry_sample_index=key_emitted + 1,
            telemetry_coalesced_mutations=max(
                0, mutation_count - previous_emitted_mutation - 1
            ),
        )

    def _bump_changed_host_allocability(
        self,
        before: dict[str, tuple[int, frozenset[int]]],
        cause: str,
    ) -> None:
        for pool, previous in before.items():
            current = self._host_evictable_signature(pool)
            if current != previous:
                self._bump_host_allocability(
                    pool,
                    cause,
                    evictable_before=previous[0],
                    evictable_after=current[0],
                )

    def host_allocability_snapshot(
        self, required_pools: Optional[Sequence[PoolName | str]] = None
    ) -> HostAllocabilitySnapshot:
        """Return a cache-owned per-pool allocability snapshot."""
        if required_pools is None:
            pools = [PoolName.KV.value]
            group = self.host_pool_group
            if group is not None:
                pools.extend(
                    getattr(entry.name, "value", entry.name)
                    for entry in group.entries
                )
        else:
            pools = [getattr(pool, "value", pool) for pool in required_pools]
            if PoolName.KV.value not in pools:
                pools.insert(0, PoolName.KV.value)
        pools = list(dict.fromkeys(str(pool) for pool in pools))

        generation_state = getattr(self, "_host_allocability_generations", {})
        generations = {pool: generation_state.get(pool, 0) for pool in pools}
        free_units = {}
        evictable_units = {}
        for pool in pools:
            evictable_units[pool] = self._host_evictable_signature(pool)[0]
            controller = self.cache_controller
            host_group = getattr(controller, "mem_pool_host", None)
            try:
                free_units[pool] = int(
                    host_group.available_size(pool=PoolName(pool))
                )
            except (AttributeError, KeyError, TypeError, ValueError):
                try:
                    free_units[pool] = (
                        int(host_group.available_size())
                        if pool == PoolName.KV.value
                        else 0
                    )
                except (AttributeError, TypeError, ValueError):
                    free_units[pool] = 0
        return HostAllocabilitySnapshot(
            cache_instance_id=getattr(self, "_host_allocability_instance_id", 0),
            generation_by_pool=generations,
            free_units_by_pool=free_units,
            evictable_units_by_pool=evictable_units,
        )

    def _release_aux_transfers_before_host_alloc_snapshot(
        self,
        comp_xfers: dict[ComponentType, list[PoolTransfer]],
        *,
        causal_rid: Optional[str] = None,
        trace_context=None,
    ) -> None:
        """Complete failed-prefetch auxiliary cleanup before taking its cursor."""
        transfers = [transfer for xfers in comp_xfers.values() for transfer in xfers]
        if not transfers:
            return
        group = getattr(self, "host_pool_group", None)
        if group is not None:
            callback = getattr(group, "host_allocability_change_fn", None)
            group.release_transfers(transfers)
            if callback is None:
                for transfer in transfers:
                    if transfer.indices_from_pool is None and transfer.host_indices is not None:
                        self._bump_host_allocability(
                            getattr(transfer.name, "value", transfer.name),
                            "direct_free",
                            len(transfer.host_indices),
                            causal_rid=causal_rid,
                            trace_context=trace_context,
                        )
                    transfer.host_indices = None
            else:
                for transfer in transfers:
                    if transfer.indices_from_pool is None:
                        transfer.host_indices = None
            return
        host_pool = getattr(getattr(self, "cache_controller", None), "mem_pool_host", None)
        for transfer in transfers:
            if transfer.indices_from_pool is not None or transfer.host_indices is None:
                continue
            released = host_pool.free(
                transfer.host_indices,
                pool=transfer.name,
            )
            self._bump_host_allocability(
                getattr(transfer.name, "value", transfer.name),
                "direct_free",
                int(released or len(transfer.host_indices)),
                causal_rid=causal_rid,
                trace_context=trace_context,
            )
            transfer.host_indices = None

    def _drain_host_frees(
        self, host_frees: dict[ComponentType, list[torch.Tensor]]
    ) -> None:
        # Free per component host-pool slots, consuming each entry as it frees.
        for ct in list(host_frees):
            values = host_frees.pop(ct)
            tracing = _t38c_durable_enabled()
            pool = _t38c_pool_name(ct) if tracing else None
            digest = _t38c_slot_digest(pool, values) if tracing else None
            self.components[ct].free_host_values(values)
            self._bump_host_allocability(
                self._host_allocability_pool_for_component(ct),
                "direct_free",
                _t38c_free_slots({ct: values}),
            )
            if tracing:
                trace_context = slot_context(pool, "host", digest)
                _t38c_note_completion(
                    self,
                    pool,
                    "host",
                    digest,
                    token=slot_token(pool, "host", digest),
                )
                _t38c_durable_log(
                    {
                        "evt": "residency_free_complete",
                        "trace_context": trace_context,
                        "pool": pool,
                        "tier": "host",
                        "slot_count": _t38c_free_slots({ct: values}),
                        "slot_digest": digest,
                        "result": True,
                        "reason": "allocator_free_returned",
                    }
                )

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
            released = self.host_pool_group.free(host_indices)
            self._bump_host_allocability(
                PoolName.KV.value, "direct_free", int(released or len(host_indices))
            )
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
        released = self.host_pool_group.free(backup.host_indices)
        self._bump_host_allocability(
            PoolName.KV.value, "direct_free", int(released or len(backup.host_indices))
        )
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
            _t38c_durable_log(
                {
                    "evt": "backup_host_commit",
                    "trace_context": self._t38c_trace_context_for_node(node_id),
                    "node_id": str(node_id),
                    "final_kv_hash": (
                        self.tree_core.node_by_id(node_id).get_last_hash_value() or ""
                    ),
                    "kv_transfer": bool(host_indices.numel()),
                    "mamba_transfer": any(
                        transfer.name == PoolName.MAMBA
                        for xfers in comp_xfers.values()
                        for transfer in xfers
                    ),
                    "host_tokens": int(host_indices.numel()),
                }
            )
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
        mamba_transfers = [
            transfer for transfer in aux_xfers if transfer.name == PoolName.MAMBA
        ]
        trace_context = self._t38c_trace_context_for_node(node_id)
        # Carry write-side identity only for the gated diagnostic.  The
        # storage backend emits the eventual batch_set_v2 result, while this
        # submission record distinguishes an omitted BACKUP_STORAGE transfer.
        for transfer in mamba_transfers:
            transfer._t38c_node_id = str(node_id)
            transfer._t38c_final_kv_hash = (
                spec.hash_value[-1] if spec.hash_value else ""
            )

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
                "final_kv_hash": spec.hash_value[-1] if spec.hash_value else "",
                "mamba_transfer_exists": bool(mamba_transfers),
                "mamba_key": (
                    mamba_transfers[0].keys[-1]
                    if mamba_transfers and mamba_transfers[0].keys
                    else ""
                ),
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
            trace_context=trace_context,
        )
        _t38c_durable_log(
            {
                "evt": "backup_submit",
                "trace_context": trace_context,
                "operation_id": operation_id,
                "attempt_id": f"storage-{operation_id}",
                "node_id": str(node_id),
                "final_kv_hash": spec.hash_value[-1] if spec.hash_value else "",
                "kv_transfer": bool(spec.host_value is not None and spec.hash_value),
                "kv_pages": len(spec.hash_value or []),
                "mamba_transfer": bool(mamba_transfers),
                "mamba_pages": len(mamba_transfers[0].keys or [])
                if mamba_transfers
                else 0,
                "mamba_key": (
                    mamba_transfers[0].keys[-1]
                    if mamba_transfers and mamba_transfers[0].keys
                    else ""
                ),
            }
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
        read-back). phase2-peranchor: this global counter is retained for
        DIAGNOSTIC STATISTICS ONLY -- the P1 miss re-arm gate and the NO_L3
        cursor read the per-anchor storage_version, not this global count."""
        return self.tree_core.l3_publish_epoch()

    def anchor_storage_version(self, node_id: NodeId) -> int:
        """The per-anchor durability version of node_id (phase2-peranchor):
        bumped only on a durability event local to THIS node's chain (write
        ack promotion / restore read-back / durable-belief clear). The P1
        miss re-arm gate and the NO_L3 cursor compare the version recorded at
        the miss against this; an advance means THIS anchor's L3 coverage
        genuinely changed. A dead/absent anchor reads 0 (self-heal to a
        re-match from root, a new candidate)."""
        return self.tree_core.anchor_storage_version(node_id)

    def is_storage_written(self, node_id: NodeId) -> bool:
        """Whether the node's KV was already submitted to L3 (dedupe guard /
        a submitted write whose ack could still promote it durable)."""
        return self.tree_core.is_storage_written(node_id)

    def has_acked_descendant(self, node_id: NodeId) -> bool:
        """Whether node_id's subtree contains a storage_acked &&
        !storage_persisted descendant (a deferred-ACK node). The no-material
        fast-forward judgment's deferred-durable-dependency fact: such a
        descendant is a P3 reconcile promotion source that could make the
        anchor durable, so the anchor is not a no-material dead-end."""
        if not self.tree_core.node_exists(node_id):
            return False
        return self.tree_core.has_acked_descendant(node_id)

    def deepest_durable_ancestor(self, node_id: NodeId) -> Optional[NodeId]:
        """The most-rootward ancestor of `node_id` that is L3-durable, or
        None when no ancestor (including the anchor itself and the root, whose
        storage_persisted defaults False) is durable.

        phase2-p0fix Q1: the anchor-resolution step for the no-material
        fast-forward judgment. A request's suffix is served from a page range
        under `node_id`; when the host prefix was split by an L3 write ack
        (D->H commit), the shallow anchor can be non-durable while a deeper
        ancestor's pages ARE durable. Judging no-material on the shallow
        node's missing flags would mis-forward a request that could restore
        from the deeper durable pages. Walking the parent chain to the most
        rootward durable ancestor aligns the judgment with the restore
        coverage. Returns the ORIGINAL anchor when it is itself durable; None
        (a pure device chain with no L3 content, or a dead anchor) means
        no-material holds. O(depth) per call -- never O(subtree)."""
        if not self.tree_core.node_exists(node_id):
            return None
        cur = node_id
        while cur is not None and self.tree_core.node_exists(cur):
            if self.tree_core.is_l3_durable(cur):
                return cur
            cur_node = self.tree_core.node_by_id(cur)
            if cur_node is None:
                break
            parent = cur_node.parent
            if parent is None:
                break
            cur = parent.id
        return None

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
        host_alloc_attempt_id: Optional[str] = None,
        prefetch_attempt_id: Optional[str] = None,
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
            failed_pool = self._host_allocability_pool_for_component(ct)
            required_aux_units = {
                getattr(transfer.name, "value", transfer.name): len(transfer.host_indices)
                for transfers in comp_xfers.values()
                for transfer in transfers
                if transfer.host_indices is not None
            }
            required_aux_units.setdefault(failed_pool, len(prefetch_key))
            self._release_aux_transfers_before_host_alloc_snapshot(
                comp_xfers, causal_rid=req_id
            )
            if anchor_lock_params is not None:
                self.dec_host_lock_ref(last_host_node_id, anchor_lock_params)
            snapshot = self.host_allocability_snapshot(
                [PoolName.KV.value, *required_aux_units]
            )
            telemetry_pools = {
                PoolName.KV.value: len(prefetch_key),
                **required_aux_units,
            }
            _log_host_alloc_telemetry(
                "restore_host_alloc_retry_result",
                rid=req_id,
                attempt_id=host_alloc_attempt_id,
                cache_instance_id=snapshot.cache_instance_id,
                trace_context=None,
                generation_vector_id=snapshot.generation_vector(),
                captured_generations=dict(snapshot.generation_by_pool),
                current_generations=dict(snapshot.generation_by_pool),
                full_frontier_tokens=int(len(prefetch_key)),
                crop_attempted=False,
                lower_checkpoint_queried=False,
                per_pool={
                    pool: {
                        "required": int(required),
                        "free_before": int(snapshot.free_units_by_pool.get(pool, 0)),
                        "evictable_before": int(
                            snapshot.evictable_units_by_pool.get(pool, 0)
                        ),
                        "alloc1": None,
                        "reclaimed": 0,
                        "alloc2": None,
                        "free_after": int(snapshot.free_units_by_pool.get(pool, 0)),
                        "evictable_after": int(
                            snapshot.evictable_units_by_pool.get(pool, 0)
                        ),
                    }
                    for pool, required in telemetry_pools.items()
                },
                failed_domains=[str(failed_pool)],
                retry_grant=host_alloc_attempt_id is not None,
                retry_skip=False,
                retry_outcome="forfeited_alloc_failed",
                terminal="forfeited_alloc_failed",
                genuine_miss=False,
                captured_generations_after=dict(snapshot.generation_by_pool),
                reservation_released=True,
            )
            self.record_host_alloc_failure(
                req_id,
                HostAllocFailure(
                    requested_primary_tokens=len(prefetch_key),
                    required_aux_units=required_aux_units,
                    failed_domains=frozenset({failed_pool}),
                    positive_hit_tokens=0,
                    sidecar_hit_pages={},
                    allocability_snapshot=snapshot,
                ),
            )
            # Forfeited over transient staging pressure; retryable (T3
            # parks the rid in WAIT[HOST_ALLOC], woken by T11).
            self._storage_prefetch_missed_rids.discard(req_id)
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
        trace_context = self._t38c_trace_context_for_prefetch(
            req_id, last_host_node_id
        )
        operation = self.cache_controller.prefetch(
            req_id,
            prefetch_key,
            last_hash,
            prefix_keys,
            extra_pools=aux_xfers or None,
            trace_context=trace_context,
        )
        operation.host_alloc_attempt_id = host_alloc_attempt_id
        operation.prefetch_attempt_id = prefetch_attempt_id
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
        sidecar_counts = self._host_alloc_hybrid_sidecar_counts(operation)

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
            _log_host_alloc_telemetry(
                "restore_hybrid_finalize",
                rid=req_id,
                attempt_id=getattr(operation, "host_alloc_attempt_id", None),
                cache_instance_id=getattr(self, "_host_allocability_instance_id", 0),
                trace_context=getattr(operation, "trace_context", None),
                kv_expected=int(len(hash_value) * self.page_size),
                kv_fetched=int(completed_tokens),
                sidecars=sidecar_counts,
                per_sidecar=sidecar_counts,
                all_or_nothing=self._host_alloc_hybrid_is_all_or_nothing(operation),
                result="discarded",
                # The terminal handoff remains "finalized" so the scheduler
                # can consume the authoritative discarded completion and
                # release the request to recompute without entering READY.
                restore_state_after="NONE",
            )
            self.record_storage_prefetch_completion(
                req_id,
                self._host_alloc_hybrid_completion(
                    operation, completed_tokens, "discarded", sidecar_counts
                ),
                getattr(operation, "prefetch_attempt_id", None),
            )
            # Hybrid all-or-nothing check failed; result already discarded.
            _log_restore_disposition(
                req_id,
                "RECOMPUTE",
                operation.stats_requested_tokens or 0,
                completed_tokens,
                "hybrid_discard",
            )
            return

        _log_host_alloc_telemetry(
            "restore_hybrid_finalize",
            rid=req_id,
            attempt_id=getattr(operation, "host_alloc_attempt_id", None),
            cache_instance_id=getattr(self, "_host_allocability_instance_id", 0),
            trace_context=getattr(operation, "trace_context", None),
            kv_expected=int(len(hash_value) * self.page_size),
            kv_fetched=int(completed_tokens),
            sidecars=sidecar_counts,
            per_sidecar=sidecar_counts,
            all_or_nothing=self._host_alloc_hybrid_is_all_or_nothing(operation),
            result="accepted",
            restore_state_after="READY",
        )
        self.record_storage_prefetch_completion(
            req_id,
            self._host_alloc_hybrid_completion(
                operation, completed_tokens, "accepted", sidecar_counts
            ),
            getattr(operation, "prefetch_attempt_id", None),
        )

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
            self.record_storage_prefetch_terminal(
                req_id, "finalized", getattr(operation, "prefetch_attempt_id", None)
            )
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

            released = self.cache_controller.mem_pool_host.free(
                host_indices[: insert_result.prefix_len]
            )
            self._bump_host_allocability(
                PoolName.KV.value,
                "direct_free",
                int(released or insert_result.prefix_len),
                causal_rid=req_id,
                trace_context=getattr(operation, "trace_context", None),
            )
            loaded_from_storage = completed_tokens - insert_result.prefix_len

        self.dec_host_lock_ref(last_host_node_id, anchor_lock_params)
        self.release_prefetch(req_id, "finalize")
        del self.ongoing_prefetch[req_id]
        self._demand_restore_rids.discard(req_id)
        self.cache_controller.prefetch_tokens_occupied -= len(prefetch_key)
        self.record_storage_prefetch_terminal(
            req_id, "finalized", getattr(operation, "prefetch_attempt_id", None)
        )

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

    @staticmethod
    def _host_alloc_hybrid_is_all_or_nothing(operation: PrefetchOperation) -> bool:
        transfers = getattr(operation, "pool_transfers", None) or []
        trailing_pages = getattr(PoolHitPolicy, "TRAILING_PAGES", None)
        return any(
            trailing_pages is not None
            and getattr(transfer, "hit_policy", None) == trailing_pages
            for transfer in transfers
        )

    def _host_alloc_hybrid_sidecar_counts(self, operation: PrefetchOperation) -> dict:
        hit_pages = getattr(
            getattr(operation, "pool_storage_result", None),
            "extra_pool_hit_pages",
            {},
        ) or {}
        sidecars = {}
        for transfer in getattr(operation, "pool_transfers", None) or []:
            if getattr(transfer, "indices_from_pool", None) == PoolName.KV:
                continue
            name = getattr(transfer, "name", None)
            pool = getattr(name, "value", name) or "unknown"
            keys = getattr(transfer, "keys", None)
            try:
                expected = len(keys or ())
            except TypeError:
                expected = 0
            try:
                fetched = hit_pages.get(name, hit_pages.get(pool, 0))
            except (AttributeError, TypeError):
                fetched = 0
            try:
                fetched = int(fetched or 0)
            except (TypeError, ValueError):
                fetched = 0
            sidecars[str(pool)] = {
                "expected": int(expected),
                "fetched": fetched,
            }
        return sidecars

    def _host_alloc_hybrid_completion(
        self,
        operation: PrefetchOperation,
        completed_tokens: int,
        finalize_result: str,
        sidecar_counts: Optional[dict] = None,
    ) -> dict:
        """Return finalizer-owned material fields for the ready_host join."""
        sidecar_counts = (
            sidecar_counts
            if sidecar_counts is not None
            else self._host_alloc_hybrid_sidecar_counts(operation)
        )
        return {
            "completed_kv_tokens": int(completed_tokens),
            "required_aux_pools": sorted(sidecar_counts),
            "completed_aux_units": {
                pool: int(details["fetched"])
                for pool, details in sidecar_counts.items()
            },
            "finalize_result": finalize_result,
        }

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
            for transfer in getattr(operation, "pool_transfers", None) or []
            if getattr(transfer, "indices_from_pool", None) != PoolName.KV
        ]
        hit_pages = (
            getattr(
                getattr(operation, "pool_storage_result", None),
                "extra_pool_hit_pages",
                {},
            )
            if pool_transfers
            else {}
        )
        try:
            pool_hit_pages = [
                hit_pages.get(getattr(t, "name", None), 0)
                for t in pool_transfers
            ]
        except (AttributeError, TypeError):
            pool_hit_pages = [0 for _ in pool_transfers]
        completed_tokens = operation.completed_tokens
        # Hybrid cache state is all-or-nothing: every extra pool (SWA / Mamba / ...)
        # must cover the same fetched prefix. If any pool falls short the whole
        # prefetch result is unusable, so discard it and release everything.
        expected_tokens = len(hash_value) * self.page_size
        all_succeeded = completed_tokens == expected_tokens and all(
            getattr(transfer, "keys", None) is not None
            and count == len(getattr(transfer, "keys"))
            for transfer, count in zip(pool_transfers, pool_hit_pages)
        )
        if pool_transfers and not all_succeeded:
            # Drop the KV beliefs from the first page any pool failed to serve;
            # the next insert then re-writes that span through one FULL check,
            # restoring the missing aux pages.
            keep_pages = completed_tokens // self.page_size
            for transfer, count in zip(pool_transfers, pool_hit_pages):
                keys = getattr(transfer, "keys", None)
                if keys is None:
                    keep_pages = 0
                elif count < len(keys):
                    # Aux transfers key the chain's trailing pages.
                    keep_pages = min(
                        keep_pages, max(0, len(hash_value) - len(keys))
                    )
            self.storage_existence_cache.invalidate_beyond(
                PoolName.KV, hash_value, keep_pages=keep_pages
            )
            # The controller's prefetch IO thread already releases the untransferred
            # tail (host_indices[completed_tokens:])
            self.cache_controller.append_host_mem_release(
                host_indices=host_indices[:completed_tokens],
                extra_pools=(
                    pool_transfers
                    if getattr(operation, "pool_transfers_done", False)
                    else None
                ),
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
            self.record_storage_prefetch_terminal(
                req_id, "finalized", getattr(operation, "prefetch_attempt_id", None)
            )
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
        getattr(self, "_storage_prefetch_failures", {}).pop(req_id, None)
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
        return (
            self.tree_core.is_backuped(anchor_node_id)
            or self.tree_core.is_root(anchor_node_id)
            or self.tree_core.is_l3_durable(anchor_node_id)
        )

    # ---- P2-1 M1b: terminal prefetch outcomes (drain -> scheduler) ----

    def record_host_alloc_failure(
        self, req_id: str, failure: HostAllocFailure
    ) -> None:
        if not hasattr(self, "_storage_prefetch_failures"):
            self._storage_prefetch_failures = {}
        self._storage_prefetch_failures[req_id] = failure

    def pop_host_alloc_failure(self, req_id: str) -> Optional[HostAllocFailure]:
        return getattr(self, "_storage_prefetch_failures", {}).pop(req_id, None)

    def record_storage_prefetch_terminal(
        self,
        req_id: str,
        outcome: str,
        attempt_id: Optional[str] = None,
    ) -> None:
        """Record a terminal prefetch outcome for the scheduler's
        restore-state reconciliation (same thread: the drain runs inside the
        scheduler's event pass)."""
        self._storage_prefetch_terminal[req_id] = (
            (attempt_id, outcome) if attempt_id is not None else outcome
        )

    def record_storage_prefetch_completion(
        self,
        req_id: str,
        completion: dict,
        attempt_id: Optional[str] = None,
    ) -> None:
        if not hasattr(self, "_storage_prefetch_completion"):
            self._storage_prefetch_completion = {}
        self._storage_prefetch_completion[req_id] = (
            (attempt_id, completion) if attempt_id is not None else completion
        )

    def pop_storage_prefetch_completion(self, req_id: str) -> Optional[dict]:
        completion = getattr(self, "_storage_prefetch_completion", {}).pop(
            req_id, None
        )
        if isinstance(completion, tuple):
            return completion[1]
        return completion

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
        getattr(self, "_storage_prefetch_completion", {}).pop(rid, None)
        getattr(self, "_storage_prefetch_failures", {}).pop(rid, None)
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
            extra_pools=(
                pool_transfers
                if getattr(operation, "pool_transfers_done", False)
                else None
            ),
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

    def revoke_pending_prefetch(self, req_id: str, *, alloc_failed: bool = False) -> None:
        """Release a pending prefetch and classify its terminal outcome.

        ``alloc_failed`` is supplied only by the hit allocator after a
        positive storage query could not stage the complete validated span.
        Keeping this explicit preserves ordinary partial-hit/mid-backup
        revoke semantics while preventing a positive hybrid hit from becoming
        a genuine storage miss.
        """
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
        elif alloc_failed:
            revoke_reason = "alloc_failed"
        else:
            revoke_reason = "miss"
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
            "WAIT"
            if revoke_reason in ("backup_pending", "alloc_failed")
            else "RECOMPUTE",
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
            else "revoked_alloc_failed"
            if revoke_reason == "alloc_failed"
            else "revoked_miss"
        )
        self.record_storage_prefetch_terminal(
            req_id, terminal, getattr(operation, "prefetch_attempt_id", None)
        )
        self._invalidate_absent_from_hit_query(operation)
        if self.buffer_pipeline is not None:
            self.buffer_pipeline.pop_prefix_ctx(req_id)
            self.buffer_pipeline.release_anchor_lock(req_id)
        cc = self.cache_controller
        required_aux_units_before_cleanup = {}
        if revoke_reason == "alloc_failed":
            for transfer in getattr(operation, "pool_transfers", None) or []:
                pool = getattr(transfer.name, "value", transfer.name)
                if pool == PoolName.KV.value or transfer.indices_from_pool is not None:
                    continue
                required_aux_units_before_cleanup[pool] = (
                    len(transfer.host_indices)
                    if transfer.host_indices is not None
                    else len(transfer.keys or ())
                )
        if revoke_reason == "alloc_failed":
            self._release_aux_transfers_before_host_alloc_snapshot(
                comp_xfers,
                causal_rid=req_id,
                trace_context=getattr(operation, "trace_context", None),
            )
        else:
            cc.append_host_mem_release(
                extra_pools=[x for xfers in comp_xfers.values() for x in xfers]
            )
        if anchor_lock_params is not None:
            self.dec_host_lock_ref(last_host_node_id, anchor_lock_params)
        if revoke_reason == "alloc_failed":
            required_aux_units = dict(required_aux_units_before_cleanup)
            blocked_domains = {PoolName.KV.value}
            sidecar_hit_pages = {PoolName.KV.value: operation.storage_hit_count}
            pool_storage_result = getattr(operation, "pool_storage_result", None)
            hit_pages_by_pool = getattr(
                pool_storage_result, "extra_pool_hit_pages", {}
            )
            for transfer in getattr(operation, "pool_transfers", None) or []:
                pool = getattr(transfer.name, "value", transfer.name)
                if pool == PoolName.KV.value or transfer.indices_from_pool is not None:
                    continue
                hit_pages = hit_pages_by_pool.get(
                    transfer.name,
                    hit_pages_by_pool.get(pool, 0),
                )
                sidecar_hit_pages[pool] = int(hit_pages)
                if transfer.keys is None or hit_pages < len(transfer.keys):
                    blocked_domains.add(pool)
            snapshot = self.host_allocability_snapshot(
                [PoolName.KV.value, *required_aux_units]
            )
            attempt_details = getattr(operation, "_host_alloc_retry_details", {})
            before_snapshot = attempt_details.get("snapshot")
            kv_details = {
                "required": int(
                    attempt_details.get("required", operation.storage_hit_count)
                ),
                "free_before": int(
                    (before_snapshot.free_units_by_pool if before_snapshot else {}).get(
                        PoolName.KV.value, 0
                    )
                ),
                "evictable_before": int(
                    (
                        before_snapshot.evictable_units_by_pool
                        if before_snapshot
                        else {}
                    ).get(PoolName.KV.value, 0)
                ),
                "alloc1": bool(attempt_details.get("alloc1", False)),
                "reclaimed": int(attempt_details.get("reclaimed", 0)),
                "alloc2": bool(attempt_details.get("alloc2", False)),
                "free_after": int(
                    snapshot.free_units_by_pool.get(PoolName.KV.value, 0)
                ),
                "evictable_after": int(
                    snapshot.evictable_units_by_pool.get(PoolName.KV.value, 0)
                ),
            }
            per_pool = {PoolName.KV.value: kv_details}
            for pool, required in required_aux_units.items():
                per_pool[pool] = {
                    "required": int(required),
                    "free_before": int(
                        (before_snapshot.free_units_by_pool if before_snapshot else {}).get(
                            pool, 0
                        )
                    ),
                    "evictable_before": int(
                        (
                            before_snapshot.evictable_units_by_pool
                            if before_snapshot
                            else {}
                        ).get(pool, 0)
                    ),
                    "alloc1": None,
                    "reclaimed": 0,
                    "alloc2": None,
                    "free_after": int(snapshot.free_units_by_pool.get(pool, 0)),
                    "evictable_after": int(
                        snapshot.evictable_units_by_pool.get(pool, 0)
                    ),
                }
            _log_host_alloc_telemetry(
                "restore_host_alloc_retry_result",
                rid=req_id,
                attempt_id=getattr(operation, "host_alloc_attempt_id", None),
                cache_instance_id=snapshot.cache_instance_id,
                trace_context=getattr(operation, "trace_context", None),
                generation_vector_id=snapshot.generation_vector(),
                captured_generations=dict(snapshot.generation_by_pool),
                current_generations=dict(snapshot.generation_by_pool),
                full_frontier_tokens=int(operation.storage_hit_count),
                crop_attempted=False,
                lower_checkpoint_queried=False,
                per_pool=per_pool,
                required_aux_units=dict(required_aux_units),
                failed_domains=sorted(map(str, blocked_domains)),
                retry_grant=getattr(operation, "host_alloc_attempt_id", None) is not None,
                retry_skip=False,
                retry_outcome="revoked_alloc_failed",
                terminal="revoked_alloc_failed",
                genuine_miss=False,
                captured_generations_after=dict(snapshot.generation_by_pool),
                reservation_released=True,
            )
            self.record_host_alloc_failure(
                req_id,
                HostAllocFailure(
                    requested_primary_tokens=operation.storage_hit_count,
                    required_aux_units=required_aux_units,
                    failed_domains=frozenset(blocked_domains),
                    positive_hit_tokens=operation.storage_hit_count,
                    sidecar_hit_pages=sidecar_hit_pages,
                    allocability_snapshot=snapshot,
                ),
            )
            # Allocation pressure must not arm the legacy paced-miss retry.
            self._storage_prefetch_missed_rids.discard(req_id)
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
        aggregate_rank_acks: bool = True,
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
            telemetry_snapshot = None
            snapshot_fn = getattr(self, "host_allocability_snapshot", None)
            if snapshot_fn is not None:
                pool_names = [PoolName.KV.value]
                pool_names.extend(
                    getattr(transfer.name, "value", transfer.name)
                    for transfer in getattr(operation, "pool_transfers", None) or []
                    if transfer.indices_from_pool is None
                )
                telemetry_snapshot = snapshot_fn(pool_names)
            host_indices = cc.mem_pool_host.alloc(alloc_len)
            alloc1_succeeded = host_indices is not None
            reclaimed_units = 0
            alloc2_succeeded = False
            if host_indices is None:
                # P3 M2: speculative staging eats free/soft-reserved host
                # headroom only -- an alloc failure declines it silently,
                # never forcing host eviction (staging must not push a
                # warm chain out of Host). Demand restores, and the
                # Ready-Horizon-off baseline (no reservation), still evict.
                reservation = self._prefetch_reservations.get(req_id)
                if reservation is None or reservation.kind is PrefetchKind.DEMAND:
                    reclaimed_units = int(self.evict_host(alloc_len) or 0)
                    host_indices = cc.mem_pool_host.alloc(alloc_len)
                    alloc2_succeeded = host_indices is not None
            operation._host_alloc_retry_details = {
                "snapshot": telemetry_snapshot,
                "required": alloc_len,
                "alloc1": alloc1_succeeded,
                "reclaimed": reclaimed_units,
                "alloc2": alloc2_succeeded,
            }
            if host_indices is None:
                if buffer_mode:
                    return False
                self.revoke_pending_prefetch(req_id, alloc_failed=True)
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
                            getattr(operation, "pool_transfers", None)
                            if not getattr(operation, "pool_transfers_done", False)
                            else None
                        ),
                        trace_context=getattr(operation, "trace_context", None),
                    )

        def _drain_backup():
            drained = 0
            for operation in _drain_queue(cc.ack_backup_queue, n_backup):
                drained += 1
                _ack_node_id = getattr(operation, "node_id", None)
                _ack_transfers = getattr(operation, "pool_transfers", None) or []
                _ack_mamba_transfers = [
                    transfer
                    for transfer in _ack_transfers
                    if transfer.name == PoolName.MAMBA
                ]
                _ack_mamba_keys = [
                    key
                    for transfer in _ack_mamba_transfers
                    for key in (transfer.keys or [])
                ]
                _ack_mamba_key_set_digest, _ack_mamba_key_count = (
                    ordered_key_set_digest(_ack_mamba_keys)
                )
                _ack_mamba_expected_pages = _ack_mamba_key_count
                _ack_mamba_succeeded_pages = (
                    operation.pool_storage_result.extra_pool_hit_pages.get(
                        PoolName.MAMBA,
                        operation.pool_storage_result.extra_pool_hit_pages.get(
                            PoolName.MAMBA.value, 0
                        ),
                    )
                )
                _ack_mamba_local_durable = (
                    _ack_mamba_key_count > 0
                    and _ack_mamba_succeeded_pages == _ack_mamba_expected_pages
                )
                _ack_final_kv_hash = (
                    operation.hash_value[-1] if operation.hash_value else ""
                )
                (
                    _ack_expected_rank_set,
                    _ack_observed_rank_set,
                    _ack_rank_set_unavailable,
                    _ack_mamba_all_rank_durable,
                ) = self._t38c_mamba_rank_proof(
                    operation,
                    node_id=_ack_node_id,
                    final_kv_hash=_ack_final_kv_hash,
                    key_set_digest=_ack_mamba_key_set_digest,
                    key_count=_ack_mamba_key_count,
                    local_mamba_durable=_ack_mamba_local_durable,
                    aggregate_rank_acks=aggregate_rank_acks,
                )
                _t38c_durable_log(
                    {
                        "evt": "backup_ack_drain",
                        "trace_context": getattr(
                            operation, "trace_context", None
                        ),
                        "operation_id": operation.id,
                        "attempt_id": f"storage-{operation.id}",
                        "node_id": str(_ack_node_id)
                        if _ack_node_id is not None
                        else "",
                        "final_kv_hash": (
                            operation.hash_value[-1]
                            if operation.hash_value
                            else ""
                        ),
                        "kv_transfer": bool(operation.hash_value),
                        "mamba_transfer": any(
                            transfer.name == PoolName.MAMBA
                            for transfer in _ack_transfers
                        ),
                        "kv_durable": operation.completed_tokens
                        >= len(operation.host_indices),
                        "mamba_durable": _ack_mamba_local_durable,
                        "mamba_all_rank_durable": _ack_mamba_all_rank_durable,
                        "mamba_expected_pages": _ack_mamba_expected_pages,
                        "mamba_succeeded_pages": _ack_mamba_succeeded_pages,
                        "mamba_key_count": _ack_mamba_key_count,
                        "mamba_key_set_digest": _ack_mamba_key_set_digest,
                        "expected_rank_set": _ack_expected_rank_set,
                        "observed_ack_rank_set": _ack_observed_rank_set,
                        "observed_ack_rank_count": len(_ack_observed_rank_set),
                        "rank_set_unavailable": _ack_rank_set_unavailable,
                        "operation": operation.id,
                        "attempt": getattr(
                            operation, "trace_id", f"storage-{operation.id}"
                        ),
                        "completed_tokens": int(operation.completed_tokens),
                        "requested_tokens": int(
                            len(operation.host_indices)
                            if operation.host_indices is not None
                            else 0
                        ),
                        "result": "complete"
                        if operation.host_indices is not None
                        and operation.completed_tokens >= len(operation.host_indices)
                        else "partial",
                    }
                )
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
                            mamba_transfers = _ack_mamba_transfers
                            mamba_expected_pages = _ack_mamba_expected_pages
                            mamba_succeeded_pages = _ack_mamba_succeeded_pages
                            mamba_key_set_digest = _ack_mamba_key_set_digest
                            mamba_key_count = _ack_mamba_key_count
                            expected_rank_set = _ack_expected_rank_set
                            attempt_id = getattr(
                                operation, "trace_id", f"storage-{operation.id}"
                            )
                            operation_context = getattr(
                                operation, "trace_context", None
                            )
                            final_kv_hash = (
                                operation.hash_value[-1]
                                if operation.hash_value
                                else ""
                            )
                            candidate_context = (
                                dict(operation_context) if operation_context else None
                            )
                            if candidate_context is not None:
                                candidate_context.setdefault("node_id", str(node_id))
                                candidate_context.setdefault(
                                    "final_kv_hash", final_kv_hash
                                )
                            attempt_key = (
                                str(node_id),
                                str(operation.id),
                                str(attempt_id),
                            )
                            candidate = {
                                "operation_id": operation.id,
                                "attempt_id": attempt_id,
                                "trace_context": candidate_context,
                                "node_id": str(node_id),
                                "final_kv_hash": final_kv_hash,
                                "kv_durable": True,
                                "kv_completed_tokens": int(
                                    operation.completed_tokens
                                ),
                                "kv_requested_tokens": int(
                                    len(operation.host_indices)
                                ),
                                "mamba_durable": _ack_mamba_all_rank_durable,
                                "mamba_expected_pages": mamba_expected_pages,
                                "mamba_succeeded_pages": mamba_succeeded_pages,
                                "mamba_key_count": mamba_key_count,
                                "mamba_key_set_digest": mamba_key_set_digest,
                                "expected_rank_set": expected_rank_set,
                                "observed_ack_rank_set": _ack_observed_rank_set,
                                "observed_ack_rank_count": len(
                                    _ack_observed_rank_set
                                ),
                                "rank_set_unavailable": _ack_rank_set_unavailable,
                                "tree_write_generation": getattr(
                                    operation, "_t38c_tree_write_generation", None
                                ),
                            }
                            # Keep every outstanding attempt. Promotion must
                            # select from this node-owned set, never a mutable
                            # per-node "current" pointer.
                            node_evidence = self._t38c_durability_evidence.setdefault(
                                str(node_id), {}
                            )
                            node_evidence[attempt_key] = candidate
                            # The write is durable: promote the node to a
                            # persisted anchor when its parent chain is.
                            # Promoted is every node that became persisted
                            # here, including descendants acked before
                            # their parent chain (retroactive promotion).
                            promoted = self.tree_core.advance_storage_persisted(
                                node_id
                            )
                            for promoted_id in promoted:
                                promoted_node = self.tree_core.node_by_id(promoted_id)
                                promoted_attempt_key, promoted_evidence = (
                                    self._t38c_select_promoted_candidate(
                                        promoted_id,
                                        promoted_node.get_last_hash_value() or "",
                                    )
                                )
                                promoted_context = (
                                    promoted_evidence.get("trace_context")
                                    if promoted_evidence is not None
                                    else None
                                )
                                context_complete = complete_trace_context(
                                    promoted_context,
                                    promoted_id,
                                    promoted_node.get_last_hash_value() or "",
                                )
                                _t38c_durable_log(
                                    {
                                        "evt": "storage_persisted",
                                        "trace_context": promoted_context,
                                        "operation_id": (
                                            promoted_evidence.get("operation_id")
                                            if promoted_evidence
                                            else None
                                        ),
                                        "attempt_id": (
                                            promoted_evidence.get("attempt_id")
                                            if promoted_evidence
                                            else None
                                        ),
                                        "node_id": str(promoted_id),
                                        "anchor_id": str(node_id),
                                        "final_kv_hash": (
                                            promoted_node.get_last_hash_value() or ""
                                        ),
                                        "frontier_end": len(
                                            promoted_node.hash_value or []
                                        )
                                        * self.page_size,
                                        "storage_version": self.tree_core.anchor_storage_version(
                                            promoted_id
                                        ),
                                        "l3_publish_epoch": self.tree_core.l3_publish_epoch(),
                                        "kv_durable": bool(
                                            promoted_evidence
                                            and promoted_evidence.get("kv_durable")
                                        ),
                                        "mamba_durable": bool(
                                            promoted_evidence
                                            and promoted_evidence.get("mamba_durable")
                                        ),
                                        "kv_completed_tokens": (
                                            promoted_evidence.get(
                                                "kv_completed_tokens"
                                            )
                                            if promoted_evidence
                                            else None
                                        ),
                                        "mamba_succeeded_pages": (
                                            promoted_evidence.get(
                                                "mamba_succeeded_pages"
                                            )
                                            if promoted_evidence
                                            else None
                                        ),
                                        "result": bool(
                                            promoted_evidence and context_complete
                                        ),
                                        "context_complete": context_complete,
                                    }
                                )
                                if (
                                    promoted_evidence is not None
                                    and context_complete
                                    and promoted_evidence.get("kv_durable")
                                    and promoted_evidence.get("mamba_durable")
                                ):
                                    final_kv_hash = promoted_evidence.get(
                                        "final_kv_hash", ""
                                    )
                                    durability_event_id = _t38c_durable_log(
                                        {
                                            "evt": "durability_barrier",
                                            "trace_context": promoted_evidence.get(
                                                "trace_context"
                                            ),
                                            "operation_id": promoted_evidence.get(
                                                "operation_id"
                                            ),
                                            "attempt_id": promoted_evidence.get(
                                                "attempt_id"
                                            ),
                                            "node_id": str(promoted_id),
                                            "final_kv_hash": final_kv_hash,
                                            "kv_durable": True,
                                            "mamba_durable": True,
                                            "kv_completed_tokens": promoted_evidence.get(
                                                "kv_completed_tokens"
                                            ),
                                            "kv_requested_tokens": promoted_evidence.get(
                                                "kv_requested_tokens"
                                            ),
                                            "mamba_expected_pages": promoted_evidence.get(
                                                "mamba_expected_pages"
                                            ),
                                            "mamba_succeeded_pages": promoted_evidence.get(
                                                "mamba_succeeded_pages"
                                            ),
                                            "mamba_key_count": promoted_evidence.get(
                                                "mamba_key_count"
                                            ),
                                            "mamba_key_set_digest": promoted_evidence.get(
                                                "mamba_key_set_digest"
                                            ),
                                            "expected_rank_set": promoted_evidence.get(
                                                "expected_rank_set"
                                            ),
                                            "observed_ack_rank_set": promoted_evidence.get(
                                                "observed_ack_rank_set"
                                            ),
                                            "observed_ack_rank_count": promoted_evidence.get(
                                                "observed_ack_rank_count"
                                            ),
                                            "rank_set_unavailable": promoted_evidence.get(
                                                "rank_set_unavailable", True
                                            ),
                                            "combined_durable": True,
                                            "result": True,
                                            "reason": "kv_ack_mamba_ack_frontier",
                                        }
                                    )
                                    if durability_event_id is not None:
                                        durability_identity = _t38c_residency_identity(
                                            promoted_evidence.get("trace_context"),
                                            promoted_id,
                                            final_kv_hash,
                                        )
                                        if durability_identity is not None:
                                            self._t38c_durability_ready.add(
                                                durability_identity
                                            )
                                            lifecycle = self._t38c_residency_lifecycle.setdefault(
                                                durability_identity,
                                                {
                                                    "state": "BUILD_CREATED",
                                                    "build_event_id": None,
                                                    "durability_event_id": None,
                                                    "component_snapshot": None,
                                                    "queue_snapshot": None,
                                                    "publication_event_id": None,
                                                    "retirement_reason": None,
                                                    "reconcile_attempt_count": 0,
                                                    "reason_attempt_counts": {},
                                                    "diagnostic_reason_set": set(),
                                                    "suppressed_diagnostic_count": 0,
                                                    "first_failure_reason": None,
                                                    "first_failure_event_id": None,
                                                    "first_attempt_ts_mono_ns": None,
                                                    "last_attempt_ts_mono_ns": None,
                                                    "first_attempt_event_id": None,
                                                    "last_attempt_event_id": None,
                                                    "terminal_event_id": None,
                                                    "detach_expectations_registered": False,
                                                    "detach_manifest": set(),
                                                },
                                            )
                                            lifecycle["durability_event_id"] = (
                                                durability_event_id
                                            )
                                            _t38c_residency_reconcile(
                                                self,
                                                durability_identity,
                                                "durability_ready",
                                            )
                                # Promotion consumes this exact attempt's
                                # evidence even when Mamba was absent/failed;
                                # a later write must never join against it.
                                if promoted_attempt_key is not None:
                                    promoted_candidates = self._t38c_durability_evidence.get(
                                        str(promoted_id), {}
                                    )
                                    promoted_candidates.pop(promoted_attempt_key, None)
                                    if not promoted_candidates:
                                        self._t38c_durability_evidence.pop(
                                            str(promoted_id), None
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
            release_pairs = []
            while n_release is None or len(release_pairs) < n_release:
                pair = cc._t38c_pop_host_mem_release_pair(
                    cc.host_mem_release_queue, PoolName.KV
                )
                if pair is None:
                    break
                release_pairs.append(pair)
            host_indices_list = [page for page, _token in release_pairs]
            released_tokens = 0
            for host_indices in host_indices_list:
                released_tokens += len(host_indices)
            if host_indices_list:
                cc.mem_pool_host.free(torch.cat(host_indices_list, dim=0))
                self._bump_host_allocability(
                    PoolName.KV.value,
                    "queued_release_drain",
                    released_tokens,
                )
                for host_indices, token in release_pairs:
                    digest = _t38c_slot_digest(PoolName.KV, [host_indices])
                    trace_context = slot_context_for_token(token)
                    _t38c_note_completion(
                        self, PoolName.KV.value, "host", digest, token=token
                    )
                    _t38c_durable_log(
                        {
                            "evt": "residency_free_complete",
                            "trace_context": trace_context,
                            "pool": PoolName.KV.value,
                            "tier": "host",
                            "slot_count": int(host_indices.numel()),
                            "slot_digest": digest,
                            "result": True,
                            "reason": "queued_release_drain_returned",
                        }
                    )
            return len(host_indices_list), released_tokens

        def _drain_extra_release():
            drained: dict[PoolName, tuple[int, int]] = {}
            if not extra_release_counts:
                return drained
            for pool_name, limit in extra_release_counts.items():
                release_queue = cc.extra_host_mem_release_queues.get(pool_name)
                if release_queue is None:
                    continue
                release_pairs = []
                while limit is None or len(release_pairs) < limit:
                    pair = cc._t38c_pop_host_mem_release_pair(
                        release_queue, pool_name
                    )
                    if pair is None:
                        break
                    release_pairs.append(pair)
                host_indices_list = [page for page, _token in release_pairs]
                released_tokens = 0
                for host_indices in host_indices_list:
                    released_tokens += len(host_indices)
                if host_indices_list:
                    cc.mem_pool_host.free(
                        torch.cat(host_indices_list, dim=0), pool=pool_name
                    )
                    self._bump_host_allocability(
                        pool_name.value,
                        "queued_release_drain",
                        released_tokens,
                    )
                    pool_label = getattr(pool_name, "value", pool_name)
                    for host_indices, token in release_pairs:
                        digest = _t38c_slot_digest(pool_label, [host_indices])
                        trace_context = slot_context_for_token(token)
                        _t38c_note_completion(
                            self, pool_label, "host", digest, token=token
                        )
                        _t38c_durable_log(
                            {
                                "evt": "residency_free_complete",
                                "trace_context": trace_context,
                                "pool": pool_label,
                                "tier": "host",
                                "slot_count": int(host_indices.numel()),
                                "slot_digest": digest,
                                "result": True,
                                "reason": "queued_release_drain_returned",
                            }
                        )
                drained[pool_name] = (len(host_indices_list), released_tokens)
            return drained

        _drain_and_alloc_storage_hit()
        _drain_ack_prefetch()
        _drain_backup()
        _drain_release()
        _drain_extra_release()
        # The owning drain transaction is the authoritative queue-empty
        # trigger. Polling remains an optional watchdog, never liveness.
        _t38c_residency_release_queues_drained(self)

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
            aggregate_rank_acks=True,
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
            aggregate_rank_acks=False,
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
                    aggregate_rank_acks=True,
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
        self._t38c_retire_session_trace(session_id)
        return self.session_refs.open_radix_session(session_id)

    def ensure_session_generation(self, session_id: str) -> int:
        return self.session_refs.ensure_session_generation(session_id)

    def release_radix_session(self, session_id: str) -> int:
        result = self.session_refs.release_radix_session(session_id)
        self._t38c_retire_session_trace(session_id)
        return result

    # ---- Streaming session API (delegates to composed StreamingSession) ----

    def supports_streaming_session(self) -> bool:
        return True

    def release_session(self, session_id: str) -> None:
        self.session.release_session(session_id)
        self._t38c_retire_session_trace(session_id)

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
