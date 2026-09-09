# Copyright 2023-2024 SGLang Team
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""A scheduler that manages a tensor parallel GPU worker."""

import dataclasses
import faulthandler
import logging
import os
import signal
import sys
import time
from array import array
from collections import deque
from contextlib import contextmanager, nullcontext
from functools import partial
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional, Set, Tuple, Union

from sglang.srt.runtime_context import (
    attention_backends,
    get_device,
    get_disagg,
    get_exec,
    get_lora,
    get_memory,
    get_mm,
    get_model,
    get_observability,
    get_parallel,
    get_schedule,
    get_serving,
    get_spec,
)

from sglang.srt.utils.common import suppress_noisy_warnings  # isort: skip

suppress_noisy_warnings()

import psutil  # isort: skip
import setproctitle
import torch
import torch.distributed
from torch.distributed import barrier

if TYPE_CHECKING:
    from torch.cuda import Stream as CudaStream

try:
    from sglang.kernels.ops.mamba.triton_ops import (
        initialize_mamba_selective_state_update_backend,
    )
except ImportError:
    initialize_mamba_selective_state_update_backend = None
from sglang.srt.beam_search.coordinator import BeamCoordinator
from sglang.srt.configs.model_config import (
    ModelConfig,
    ModelImpl,
    is_deepseek_v4,
    is_minimax_sparse,
)
from sglang.srt.constrained.grammar_manager import GrammarManager
from sglang.srt.debug_utils.pr_fix_toggle import maybe_revert_pr_fix
from sglang.srt.disaggregation.decode import (
    DecodePreallocQueue,
    DecodeTransferQueue,
    SchedulerDisaggregationDecodeMixin,
)
from sglang.srt.disaggregation.decode_kvcache_offload_manager import (
    DecodeKVCacheOffloadManager,
)
from sglang.srt.disaggregation.encoder.receiver import create_mm_receiver
from sglang.srt.disaggregation.prefill import (
    PrefillBootstrapQueue,
    SchedulerDisaggregationPrefillMixin,
    maybe_release_metadata_buffer,
)
from sglang.srt.disaggregation.utils import (
    DisaggregationMode,
    MetadataBuffers,
    ReqToMetadataIdxAllocator,
    TransferBackend,
    get_dsa_seed_metadata_dim,
    prepare_abort,
    unified_memory_disagg_move_gate,
)
from sglang.srt.distributed import get_pp_group, get_world_group
from sglang.srt.distributed.parallel_state import get_tp_group
from sglang.srt.distributed.parallel_state_wrapper import ParallelState
from sglang.srt.dllm.mixin.scheduler import SchedulerDllmMixin
from sglang.srt.environ import envs, exportable_env_vars
from sglang.srt.eplb.expert_distribution import get_global_expert_distribution_recorder
from sglang.srt.hardware_backend.mlx.runtime import use_mlx
from sglang.srt.layers.dp_attention import compute_dp_attention_world_info
from sglang.srt.layers.moe import initialize_moe_config
from sglang.srt.layers.quantization.fp4_utils import initialize_fp4_gemm_config
from sglang.srt.layers.quantization.fp8_utils import initialize_fp8_gemm_config
from sglang.srt.layers.quantization.unquant import initialize_bf16_gemm_config
from sglang.srt.lora.lora_drainer import LoRADrainer
from sglang.srt.lora.lora_overlap_loader import LoRAOverlapLoader
from sglang.srt.managers.disagg_service import maybe_create_ascend_config_store
from sglang.srt.managers.hisparse_coordinator import HiSparseCoordinator
from sglang.srt.managers.io_struct import (
    AbortReq,
    ActiveRanksOutput,
    AddExternalCorpusReqInput,
    AddExternalCorpusReqOutput,
    AttachHiCacheStorageReqInput,
    AttachHiCacheStorageReqOutput,
    BatchTokenizedEmbeddingReqInput,
    BatchTokenizedGenerateReqInput,
    CheckWeightsReqInput,
    ClearHiCacheReqInput,
    ClearHiCacheReqOutput,
    CloseSessionReqInput,
    ConfigureLoggingReq,
    ContinueGenerationReqInput,
    DestroyWeightsUpdateGroupReqInput,
    DetachHiCacheStorageReqInput,
    DetachHiCacheStorageReqOutput,
    DumperControlReqInput,
    DumperControlReqOutput,
    ExpertDistributionReq,
    ExpertDistributionReqOutput,
    ExpertDistributionReqType,
    FinishReasonDict,
    FlushCacheReqInput,
    FreezeGCReq,
    GetInternalStateReq,
    GetInternalStateReqOutput,
    GetWeightsByNameReqInput,
    HealthCheckOutput,
    InitWeightsSendGroupForRemoteInstanceReqInput,
    InitWeightsSendGroupForRemoteInstanceReqOutput,
    InitWeightsUpdateGroupReqInput,
    ListExternalCorporaReqInput,
    ListExternalCorporaReqOutput,
    LoadLoRAAdapterFromTensorsReqInput,
    LoadLoRAAdapterFromTensorsReqOutput,
    LoadLoRAAdapterReqInput,
    LoadLoRAAdapterReqOutput,
    OpenSessionReqInput,
    PauseGenerationReqInput,
    ProfileReq,
    ReleaseMemoryOccupationReqInput,
    RemoveExternalCorpusReqInput,
    RemoveExternalCorpusReqOutput,
    ResumeMemoryOccupationReqInput,
    RpcReqInput,
    RpcReqOutput,
    ScaleElasticEPReqInput,
    ScaleElasticEPReqOutput,
    SendWeightsToRemoteInstanceReqInput,
    SendWeightsToRemoteInstanceReqOutput,
    SetInternalStateReq,
    SetInternalStateReqOutput,
    ShutdownReq,
    SlowDownReqInput,
    SlowDownReqOutput,
    TokenizedEmbeddingReqInput,
    TokenizedGenerateReqInput,
    UnloadLoRAAdapterReqInput,
    UnloadLoRAAdapterReqOutput,
    UpdateWeightFromDiskReqInput,
    UpdateWeightsFromDistributedReqInput,
    UpdateWeightsFromIPCReqInput,
    UpdateWeightsFromTensorReqInput,
    UpdateWeightVersionReqInput,
    UpdateWeightVersionReqOutput,
    sock_send,
)
from sglang.srt.managers.load_snapshot import create_load_snapshot_writer
from sglang.srt.managers.min_free_slots_delayer import (
    MinFreeSlotsDelayer,
    resolve_min_free_slots,
)
from sglang.srt.managers.multimodal_processor import get_mm_processor, import_processors
from sglang.srt.managers.overlap_utils import (
    RelayPayload,
    decide_needs_confidence_relay,
    decide_needs_cpu_seq_lens,
    resolve_forward_inputs,
)
from sglang.srt.managers.prefill_delayer import (
    PrefillDelayer,
    PrefillDelayerSinglePassExecutor,
    RecentPrefillBatchSizeTracker,
)
from sglang.srt.managers.rust_server import RustServer
from sglang.srt.managers.schedule_batch import (
    FINISH_ABORT,
    MultimodalInputs,
    NextBatchPlan,
    Req,
    ScheduleBatch,
    retract_all,
)
from sglang.srt.managers.schedule_policy import (
    AddReqResult,
    CLIP_MAX_NEW_TOKENS,
    PrefillAdder,
    SchedulePolicy,
    available_and_evictable_tokens,
    device_charge,
    device_locked_tokens,
    prefill_deny_snapshot,
)
from sglang.srt.managers.scheduler_components.batch_result_processor import (
    SchedulerBatchResultProcessor,
)
from sglang.srt.managers.scheduler_components.hicache_restore import (
    FrontierAnchorInfo,
    HostAllocFailure,
    HostAllocWaitCursor,
    HostAllocWakeArbiter,
    HOST_ALLOC_TELEMETRY_SCHEMA_VERSION,
    HiCachePrefetchOrigin,
    HiCachePrefetchIssueStatus,
    PrefetchIssueResult,
    RestoreDecision,
    RestoreEvent,
    RestoreState,
    RestoreWaitReason,
    capacity_wake_applies,
    demand_restore_available,
    next_restore,
    no_material_fast_forward,
    promotion_budget_fits,
    promotion_wait_blocked,
    short_tail_recompute_allowed,
    too_short_wait_armed,
    wait_clock_next,
    wait_reason_for,
)
from sglang.srt.managers.scheduler_components.ready_horizon import (
    CausalEpochs,
    DeclineReason,
    NegativeCacheEntry,
    ReadyHorizonPolicy,
    ReadyHorizonView,
)
from sglang.srt.managers.scheduler_components.dp_attn import SchedulerDPAttnAdapter
from sglang.srt.managers.scheduler_components.flush_wrapper import SchedulerFlushWrapper
from sglang.srt.managers.scheduler_components.idle_sleeper import (
    IdleSleeper,
    RustServerIdleSleeper,
)
from sglang.srt.managers.scheduler_components.invariant_checker import (
    SchedulerInvariantChecker,
    create_scheduler_watchdog,
)
from sglang.srt.managers.scheduler_components.ipc_channels import SchedulerIpcChannels
from sglang.srt.managers.scheduler_components.kv_events_publisher import (
    SchedulerKvEventsPublisher,
)
from sglang.srt.managers.scheduler_components.load_inquirer import SchedulerLoadInquirer
from sglang.srt.managers.scheduler_components.load_publisher import (
    SchedulerLoadPublisher,
)
from sglang.srt.managers.scheduler_components.logprob_result_processor import (
    SchedulerLogprobResultProcessor,
)
from sglang.srt.managers.scheduler_components.memory_usage import (
    build_memory_usage,
    combine_graph_memory_usage,
)
from sglang.srt.managers.scheduler_components.metrics_reporter import (
    RECORD_STEP_TIME,
    PrefillStats,
    SchedulerMetricsReporter,
)
from sglang.srt.managers.scheduler_components.new_token_ratio_tracker import (
    NewTokenRatioTracker,
)
from sglang.srt.managers.scheduler_components.output_streamer import (
    SchedulerOutputStreamer,
)
from sglang.srt.managers.scheduler_components.pool_stats_observer import (
    SchedulerPoolStatsObserver,
)
from sglang.srt.managers.scheduler_components.profiler_manager import (
    SchedulerProfilerManager,
)
from sglang.srt.managers.scheduler_components.recv_skipper import (
    SchedulerRecvSkipper,
)
from sglang.srt.managers.scheduler_components.request_receiver import (
    SchedulerRequestReceiver,
)
from sglang.srt.managers.scheduler_components.weight_updater import (
    SchedulerWeightUpdaterManager,
)
from sglang.srt.managers.scheduler_input_blocker import SchedulerInputBlocker
from sglang.srt.managers.scheduler_pp_mixin import SchedulerPPMixin
from sglang.srt.managers.utils import (
    EmbeddingBatchResult,
    GenerationBatchResult,
    is_health_check_generate_req,
    validate_input_length,
)
from sglang.srt.mem_cache import kv_cache_builder
from sglang.srt.mem_cache.common import (
    maybe_cache_unfinished_req,
    release_kv_cache,
    retraction_discard,
)
from sglang.srt.model_executor.forward_batch_info import PPProxyTensors
from sglang.srt.model_loader.utils import get_resolved_model_impl
from sglang.srt.multiplex.multiplexing_mixin import SchedulerMultiplexMixin
from sglang.srt.observability.metrics_collector import SchedulerMetricsCollector
from sglang.srt.observability.req_time_stats import (
    flush_trace_batch,
    set_schedule_time_batch,
    set_time_batch,
)
from sglang.srt.observability.startup_time import build_scheduler_startup_time
from sglang.srt.observability.trace import process_tracing_init, trace_set_thread_info
from sglang.srt.parser.reasoning_parser import ReasoningParser
from sglang.srt.platforms import current_platform
from sglang.srt.plugins import load_plugins
from sglang.srt.runtime_context import get_context, publish
from sglang.srt.sampling.sampling_batch_info import SamplingBatchInfo
from sglang.srt.sampling.sampling_params import TOP_K_ALL
from sglang.srt.server_args import PortArgs, ServerArgs, compute_world_size
from sglang.srt.session.session_controller import SessionController
from sglang.srt.speculative.base_spec_worker import BaseSpecWorker
from sglang.srt.speculative.dflash_utils import validate_dflash_request
from sglang.srt.speculative.eagle_utils import get_draft_recurrent_hidden_state_spec
from sglang.srt.speculative.spec_info import SpeculativeAlgorithm
from sglang.srt.utils import (
    DynamicGradMode,
    configure_gc_logger,
    configure_logger,
    freeze_gc,
    get_available_gpu_memory,
    get_bool_env_var,
    get_int_env_var,
    is_cuda,
    is_hip,
    is_mps,
    kill_itself_when_parent_died,
    rank_consensus_checker,
    require_mlp_sync,
    set_gpu_proc_affinity,
    set_random_seed,
    suppress_other_loggers,
    triton_load_watch,
)
from sglang.srt.utils.common import is_npu
from sglang.srt.utils.hf_transformers_utils import (
    get_processor,
    get_tokenizer,
    get_tokenizer_from_processor,
    resolve_image_processor_backend,
)
from sglang.srt.utils.msgspec_utils import msgspec_to_builtins
from sglang.srt.utils.numa_utils import get_numa_node_if_available, numa_bind_to_node
from sglang.srt.utils.nvtx_utils import scheduler_nvtx_method
from sglang.srt.utils.torch_memory_saver_adapter import TorchMemorySaverAdapter
from sglang.srt.utils.weight_versions import (
    compute_weight_version_spans,
    record_weight_version_events,
)
from sglang.utils import TypeBasedDispatcher, get_exception_traceback

if is_mps():
    CudaStreamContext = nullcontext
    from sglang.srt.hardware_backend.mlx.scheduler_mixin import SchedulerMlxOverlapMixin
else:
    from torch.cuda import StreamContext as CudaStreamContext

    class SchedulerMlxOverlapMixin:
        pass


logger = logging.getLogger(__name__)


# [P2A] Per-pass admission traces (bif transitions, admission positions,
# no_token detail) are debug-only: they fire per scheduler pass and would
# otherwise flood the log (2358+ lines in 3 minutes during an idle spin).
# Gate on /tmp/t38c-on, the same file gate as the t38c probe: touch the file
# to enable, remove it to disable (no restart needed).
def _p2a_trace(fmt, *args):
    if os.path.exists("/tmp/t38c-on"):
        logger.info(fmt, *args)


def _log_host_alloc_telemetry(
    event: str,
    *,
    worker: str,
    rank,
    rid: Optional[str] = None,
    attempt_id: Optional[str] = None,
    cache_instance_id=None,
    trace_context=None,
    **fields,
) -> None:
    """Emit bounded, request-correlated HOST_ALLOC observability records."""
    import json as _json

    if event == "restore_host_alloc_wake_decision":
        decision = fields.get("decision")
        key = (rid, attempt_id)
        signature = (
            decision,
            fields.get("generation_vector_id"),
            tuple(sorted(fields.get("current_generations", {}).items())),
        )
        last = _HOST_ALLOC_WAKE_TELEMETRY_LAST.get(key)
        if signature == last:
            return
        _HOST_ALLOC_WAKE_TELEMETRY_LAST[key] = signature
        if decision != "grant":
            count = _HOST_ALLOC_WAKE_TELEMETRY_HOLDS.get(key, 0) + 1
            _HOST_ALLOC_WAKE_TELEMETRY_HOLDS[key] = count
            if count > 64:
                return
        if len(_HOST_ALLOC_WAKE_TELEMETRY_LAST) > 4096:
            _HOST_ALLOC_WAKE_TELEMETRY_LAST.clear()
            _HOST_ALLOC_WAKE_TELEMETRY_HOLDS.clear()

    record = {
        "schema": HOST_ALLOC_TELEMETRY_SCHEMA_VERSION,
        "evt": event,
        "ts_mono_ns": time.monotonic_ns(),
        "ts_wall_ms": int(time.time() * 1000),
        "worker": worker,
        "rank": rank,
        "rid": rid,
        "attempt_id": attempt_id,
        "cache_instance_id": cache_instance_id,
        "trace_context": trace_context,
    }
    record.update(fields)
    logger.info("[HAE] %s", _json.dumps(record, sort_keys=True, default=str))


_HOST_ALLOC_WAKE_TELEMETRY_LAST = {}
_HOST_ALLOC_WAKE_TELEMETRY_HOLDS = {}


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


def policy_epoch_value(policy, epochs, reason) -> int:
    """The cursor of the causal epoch a decline reason subscribes to
    (M3, user adjudication subscription table: NO_L3 -> l3_publish,
    NO_HEADROOM -> host_release, SPEC_BUDGET -> spec_budget). The negative
    cache records this value at the decline; re-eligibility compares the
    current value against it."""
    return getattr(epochs, policy.subscribed_epoch(reason))


def _prewarm_hccl_group(device, group, device_module):
    warmup_tensor = torch.zeros(1, dtype=torch.int32, device=device)
    torch.distributed.all_reduce(warmup_tensor, group=group)
    device_module.synchronize()


# Test retract decode for debugging purposes
TEST_RETRACT = envs.SGLANG_TEST_RETRACT.get()
TEST_RETRACT_INTERVAL = envs.SGLANG_TEST_RETRACT_INTERVAL.get()
TEST_RETRACT_NO_PREFILL_BS = envs.SGLANG_TEST_RETRACT_NO_PREFILL_BS.get()


STEP_MAX_US = 2_000_000

# Min wall-clock between load publishes on the stalled no-batch path, which
# spins on_idle without sleeping. Bounds the O(queue) get_loads for both the
# DP-balancing writer and the router-facing socket.
LOAD_STALL_REFRESH_S = 0.05


def _accumulate_decode_moment(
    totals: list[float],
    batch_size: int,
    step_us: int,
    generated: int,
) -> None:
    if batch_size <= 0 or step_us <= 0:
        return
    b = float(batch_size)
    t = float(step_us)
    g = float(generated)
    totals[0] += 1.0
    totals[1] += b
    totals[2] += t
    totals[3] += b * b
    totals[4] += b * t
    totals[5] += g


_is_npu = is_npu()
_is_hip = is_hip()


class Scheduler(
    SchedulerDisaggregationDecodeMixin,
    SchedulerDisaggregationPrefillMixin,
    SchedulerMultiplexMixin,
    SchedulerPPMixin,
    SchedulerDllmMixin,
    SchedulerMlxOverlapMixin,
):
    """A scheduler that manages a tensor parallel GPU worker."""

    # Class-level default so on_idle's stall gate works even if a fork
    # overrides init_load_publisher (which would otherwise not set it).
    _last_stall_publish_ts: float = float("-inf")

    def __init__(
        self,
        server_args: ServerArgs,
        port_args: PortArgs,
        gpu_id: int,
        tp_rank: int,
        moe_ep_rank: int,
        pp_rank: int,
        attn_cp_rank: int,
        moe_dp_rank: int,
        dp_rank: Optional[int],
    ):
        # NOTE: KEEP THE FOLLOWING CODE STYLE for this function:
        # Keep __init__ as an orchestrator: sequence init_* and maybe_init_* calls
        # with minimal glue. Move substantial component-specific logic into
        # dedicated methods instead of adding inline blocks here.
        self.init_startup_timing_begin()
        self.is_initializing = True
        # init_soft_watchdog starts a daemon thread that reads these on its first tick.
        self.forward_ct: int = 0
        self.cur_batch_for_debug: Optional[ScheduleBatch] = None
        self.init_soft_watchdog()

        # Parse args
        self.server_args = server_args
        self.nccl_port = port_args.nccl_port
        self.schedule_policy = get_schedule().schedule_policy
        self.enable_priority_scheduling = get_schedule().enable_priority_scheduling
        self.abort_on_priority_when_disabled = (
            get_schedule().abort_on_priority_when_disabled
        )
        self.schedule_low_priority_values_first = (
            get_schedule().schedule_low_priority_values_first
        )
        self.priority_scheduling_preemption_threshold = (
            get_schedule().priority_scheduling_preemption_threshold
        )
        self.enable_lora = get_lora().enable_lora
        self.enable_lora_overlap_loading = get_lora().enable_lora_overlap_loading
        self.max_loras_per_batch = get_lora().max_loras_per_batch
        self.enable_overlap = (
            not get_schedule().disable_overlap_schedule and not use_mlx()
        )
        self.enable_overlap_mlx = (
            not get_schedule().disable_overlap_schedule and use_mlx()
        )
        self.enable_pdmux = get_disagg().enable_pdmux
        self.skip_tokenizer_init = get_serving().skip_tokenizer_init
        self.stream_interval = get_serving().stream_interval
        self.spec_algorithm = SpeculativeAlgorithm.from_string(
            get_spec().speculative_algorithm
        )
        self.page_size = get_schedule().page_size
        self.enable_hierarchical_cache = get_memory().enable_hierarchical_cache
        self.enable_session_radix_cache = get_memory().enable_session_radix_cache
        self.enable_hicache_storage = get_memory().hicache_storage_backend is not None
        # P3 Ready Horizon (M1): wake re-issues classify as demand restores
        # only under this flag; off keeps the pre-P3 wiring (T15
        # BACKUP_PENDING-only classification), byte for byte.
        self.enable_ready_horizon = server_args.enable_ready_horizon
        # [P2A] Throttle for the aggregated admission-deny summary line.
        self._last_deny_stats_ts = 0.0
        self.enable_decode_hicache = (
            get_disagg().disaggregation_decode_enable_radix_cache
            and self.enable_hierarchical_cache
        )
        self.max_recv_per_poll = envs.SGLANG_SCHEDULER_MAX_RECV_PER_POLL.get()
        self.max_new_tokens_limit = envs.SGLANG_MAX_NEW_TOKENS_LIMIT.get()
        self.enable_hisparse = get_memory().enable_hisparse
        self.enable_dp_attention = get_parallel().enable_dp_attention
        self.enable_unified_memory = get_memory().enable_unified_memory

        # Distributed rank info
        attn_tp_rank, attn_tp_size, attn_dp_rank, attn_dp_size = (
            compute_dp_attention_world_info(
                get_parallel().enable_dp_attention,
                tp_rank,
                get_parallel().tp_size,
                get_parallel().dp_size,
                get_parallel().attn_cp_size,
            )
        )
        self.ps = ParallelState(
            tp_rank=tp_rank,
            tp_size=get_parallel().tp_size,
            pp_rank=pp_rank,
            pp_size=get_parallel().pp_size,
            dp_rank=dp_rank,
            dp_size=get_parallel().dp_size,
            attn_tp_rank=attn_tp_rank,
            attn_tp_size=attn_tp_size,
            attn_cp_rank=attn_cp_rank,
            attn_cp_size=get_parallel().attn_cp_size,
            attn_dcp_rank=tp_rank % get_parallel().dcp_size,
            attn_dcp_size=get_parallel().dcp_size,
            attn_dp_rank=attn_dp_rank,
            attn_dp_size=attn_dp_size,
            moe_ep_rank=moe_ep_rank,
            moe_ep_size=get_parallel().ep_size,
            moe_dp_rank=moe_dp_rank,
            moe_dp_size=get_parallel().moe_dp_size,
            gpu_id=gpu_id,
        )

        # Init model configs
        self.init_model_config()

        # Init metrics stats
        self.init_metrics_collector(tp_rank, pp_rank, dp_rank)

        # Init inter-process communication
        self.init_ipc_channels(port_args)
        self.init_idle_sleeper()

        # Init ZBAL, switch allocator should before any torch alloc action
        self.init_zbal_on_npu()

        # Init PD-multiplexing context
        if self.enable_pdmux:
            self.init_pdmux()

        # Init tokenizer
        self.init_tokenizer()

        # Init moe config and GEMM config (FP8 GEMM, etc.)
        self.init_moe_gemm_config()

        # Init mamba backend
        self.init_mamba_backend()

        # Must precede init_model_worker: revert targets like _init_pools run during it,
        # so patching them afterwards is a no-op.
        maybe_revert_pr_fix()

        # Launch a model worker and draft model worker if using speculative decoding
        self.init_model_worker()

        if (t := envs.SGLANG_TEST_STUCK_SCHEDULER_INIT.get()) > 0:
            time.sleep(t)

        # Init cache and memory pool
        result = kv_cache_builder.build_kv_cache(
            server_args=self.server_args,
            model_config=self.model_config,
            tp_worker=self.tp_worker,
            page_size=self.page_size,
            spec_algorithm=self.spec_algorithm,
            attn_tp_cpu_group=self.attn_tp_cpu_group,
            tp_cpu_group=self.tp_cpu_group,
            attn_cp_cpu_group=self.attn_cp_cpu_group,
            enable_metrics=get_observability().enable_metrics,
            enable_kv_cache_events=bool(
                get_observability().kv_events_config
                and self.ps.pp_rank == 0
                and self.ps.attn_tp_rank == 0
                and self.ps.attn_cp_rank == 0
            ),
            ps=self.ps,
            tp_group=self.tp_group,
            pp_group=self.pp_group,
            enable_hierarchical_cache=self.enable_hierarchical_cache,
            hicache_draft_plan=(
                self.draft_worker.hicache_draft_plan
                if self.draft_worker is not None
                else None
            ),
        )
        self.is_hybrid_swa = result.is_hybrid_swa
        self.is_hybrid_ssm = result.is_hybrid_ssm
        self.sliding_window_size = result.sliding_window_size
        self.full_tokens_per_layer = result.full_tokens_per_layer
        self.swa_tokens_per_layer = result.swa_tokens_per_layer
        self.req_to_token_pool = result.req_to_token_pool
        self.token_to_kv_pool_allocator = result.token_to_kv_pool_allocator
        self.disable_radix_cache = result.disable_radix_cache
        self.tree_cache = result.tree_cache
        self.emit_metrics_constants()
        self.maybe_init_hccl_dp_prewarm()

        if (c := self.tp_worker.model_runner.canary_manager) is not None:
            c.attach_radix_cache(self.tree_cache)

        self.init_hisparse_coordinator()

        if (
            get_disagg().disaggregation_mode == "decode"
            and get_disagg().disaggregation_decode_enable_offload_kvcache
        ):
            self.decode_offload_manager = DecodeKVCacheOffloadManager(
                req_to_token_pool=self.req_to_token_pool,
                token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
                tp_group=(
                    self.attn_tp_cpu_group
                    if self.enable_dp_attention
                    else self.tp_cpu_group
                ),
                tree_cache=self.tree_cache,
            )
        else:
            self.decode_offload_manager = None

        # Init running status
        self.init_running_status()

        # Init chunked prefill
        self.init_chunked_prefill()

        # Init diffusion LLM
        self.init_diffusion_llm()

        self.init_metrics_reporter(tp_rank, pp_rank, dp_rank)

        # Init schedule policy and new token estimation
        self.init_schedule_policy()

        # P3 Ready Horizon v0 (3.2): the READY_HOST pool maintenance policy
        # (constructed unconditionally; the per-pass maintenance pass is
        # gated on enable_ready_horizon).
        self.init_ready_horizon()

        # Init watchdog, memory saver, input blocker and recv skipper
        self.init_watch_dog_memory_saver_input_blocker()

        # Init profiler
        self.init_profiler()

        # Start the embedded Rust frontend (rank 0). Must precede
        # init_disaggregation: on PD prefill the rust api listener also serves
        # the KV bootstrap registry, and the KVManagers built there register to
        # it synchronously. (The listener is bound synchronously inside launch,
        # so the registry is accepting once this returns.) Must also precede
        # the request receiver, which reads self.recv_from_tokenizer to pick
        # its ingress transport.
        self.maybe_init_rust_server()

        # Init prefill-decodedisaggregation
        self.init_disaggregation()

        # Init overlap schedule
        self.init_overlap()

        # Init Ngram Embedding
        self.maybe_init_ngram_embedding()

        # Init prefill kv split size when deterministic inference is enabled with various attention backends
        self.init_deterministic_inference_config()

        self.init_weight_updater()

        # Init request dispatcher
        self.init_request_dispatcher()

        # Init LoRA drainer for fair scheduling
        self.init_lora_drainer()

        # Init LoRA overlap loader
        self.init_lora_overlap_loader()

        # Init the grammar backend for constrained generation
        self.init_grammar_manager()

        self.maybe_init_scripted_scheduler_hook()

        self.init_request_receiver()

        self.init_dp_attn_adapter()

        self.init_pool_stats_observer()

        self.init_invariant_checker()

        self.init_kv_events_publisher()

        self.init_load_publisher()

        self.init_load_inquirer()

        self.init_output_streamer()

        self.init_batch_result_processor()

        self.init_rank_consensus_checker()

        self.is_initializing = False
        self.init_startup_timing_summary()

    def init_startup_timing_begin(self) -> None:
        self.scheduler_startup_begin = time.perf_counter()

    def init_startup_timing_summary(self) -> None:
        self.startup_time = build_scheduler_startup_time(
            target_load_weight=self.tp_worker.weight_load_time,
            draft_load_weight=(
                0.0 if self.draft_worker is None else self.draft_worker.weight_load_time
            ),
            kv_cache_allocation=self.kv_cache_allocation_time,
            scheduler_e2e=time.perf_counter() - self.scheduler_startup_begin,
            target_cuda_graph=self.tp_worker.graph_time_usage,
            draft_cuda_graph=(
                None
                if self.draft_worker is None
                else self.draft_worker.graph_time_usage
            ),
        )

    def maybe_init_hccl_dp_prewarm(self) -> None:
        if not (
            _is_npu
            and is_deepseek_v4(self.tp_worker.model_runner.model_config.hf_config)
        ):
            return

        rank = (
            self.ps.dp_rank
            if self.ps.dp_rank is not None
            else self.tp_group.rank_in_group
        )
        logger.info("HCCL DP prewarm start: rank=%s", rank)
        _prewarm_hccl_group(
            device=self.tp_group.device,
            group=self.tp_group.device_group,
            device_module=self.tp_group.device_module,
        )
        logger.info("HCCL DP prewarm done: rank=%s", rank)

    def init_zbal_on_npu(self):
        if _is_npu:
            from sglang.srt.hardware_backend.npu.utils import init_zbal

            if self.ps.pp_size > 1:
                logger.error("only zbal mix mode support pp_size > 1!")
            init_zbal(
                self.ps.tp_size, self.ps.gpu_id, self.ps.tp_rank
            )  # only switch allocator if is mix mode

    def init_model_config(self):
        self.model_config = ModelConfig.from_server_args(self.server_args)
        if _is_npu:
            # make sure the page size is not larger than block_size and chunked_prefill_size on NPU backend
            # the npu backend request the defined page size to be no larger than block_size and chunked_prefill_size
            from sglang.srt.dllm.config import DllmConfig

            self.dllm_config = (  # For diffusion LLM
                DllmConfig.from_server_args(self.server_args)
                if get_exec().dllm.dllm_algorithm is not None
                else None
            )

    def init_metrics_collector(
        self, tp_rank: int, pp_rank: int, dp_rank: Optional[int]
    ) -> None:
        self.metrics_collector_context = SchedulerMetricsCollector.init_new(
            server_args=self.server_args,
            ps=self.ps,
            tp_rank=tp_rank,
            pp_rank=pp_rank,
            dp_rank=dp_rank,
            enable_priority_scheduling=self.enable_priority_scheduling,
            enable_lora=self.enable_lora,
            enable_hierarchical_cache=self.enable_hierarchical_cache,
        )
        self.metrics_collector = self.metrics_collector_context.collector

    def init_ipc_channels(self, port_args: PortArgs):
        is_rank_zero = (
            self.ps.pp_rank == 0
            and self.ps.attn_tp_rank == 0
            and self.ps.attn_cp_rank == 0
        )
        self.ipc_channels = SchedulerIpcChannels.create(
            port_args=port_args,
            is_rank_zero=is_rank_zero,
            # The snapshot taken at construction, not a second bag read: this
            # scheduler gates its tokenizer init on the same value, and the two
            # must not be able to disagree.
            skip_tokenizer_init=self.skip_tokenizer_init,
            metrics_enabled=get_observability().enable_metrics
            and (
                self.ps.attn_tp_rank == 0
                or get_observability().enable_metrics_for_all_schedulers
            ),
            enable_scripted_runtime=envs.SGLANG_TEST_SCRIPTED_RUNTIME.get(),
        )

        self.load_snapshot_writer = None
        self.recv_from_tokenizer = None

        if not is_rank_zero:
            return

        self.recv_from_tokenizer = self.ipc_channels.recv_from_tokenizer
        dp_rank = self.ps.dp_rank if self.ps.dp_rank is not None else 0
        try:
            self.load_snapshot_writer = create_load_snapshot_writer(
                port_args,
                self.ps.dp_size,
                dp_rank,
                publish_interval=get_observability().load_snapshot_publish_interval,
            )
        except Exception as e:
            logger.warning("load snapshot writer init failed: %s", e)

    def init_idle_sleeper(self) -> None:
        if (
            self.ps.pp_rank == 0
            and self.ps.attn_tp_rank == 0
            and self.ps.attn_cp_rank == 0
            and get_device().sleep_on_idle
        ):
            self.idle_sleeper = IdleSleeper(
                sockets=[
                    self.ipc_channels.recv_from_tokenizer,
                    self.ipc_channels.recv_from_rpc,
                ],
            )
        else:
            self.idle_sleeper = None

    def publish_load_snapshot(self, force: bool = False):
        """Returns the LoadSnapshot it published, or None when disabled,
        throttled, or failed — so co-located sinks (the router-facing load
        publisher) can reuse it instead of walking the queues again."""
        writer = self.load_snapshot_writer
        if writer is None:
            return None
        if not force:
            writer.publish_counter += 1
            if writer.publish_counter < writer.publish_interval:
                return None
        writer.publish_counter = 0
        try:
            load = self.load_inquirer.get_loads()
            writer.write(load)
            return load
        except Exception as e:
            logger.warning("load snapshot publish failed: %s", e)
            return None

    def init_tokenizer(self):
        server_args = self.server_args
        self.is_generation = self.model_config.is_generation

        if self.skip_tokenizer_init:
            self.tokenizer = self.processor = None
        else:
            if self.model_config.is_multimodal:
                self.processor = get_processor(
                    get_serving().tokenizer_path,
                    tokenizer_mode=get_serving().tokenizer_mode,
                    trust_remote_code=get_model().trust_remote_code,
                    revision=get_model().revision,
                    image_processor_backend=resolve_image_processor_backend(get_mm()),
                    tokenizer_backend=get_serving().tokenizer_backend,
                    model_name=get_model().model_path,
                )
                self.tokenizer = get_tokenizer_from_processor(self.processor)
            else:
                self.tokenizer = get_tokenizer(
                    get_serving().tokenizer_path,
                    tokenizer_mode=get_serving().tokenizer_mode,
                    trust_remote_code=get_model().trust_remote_code,
                    revision=get_model().revision,
                    tokenizer_backend=get_serving().tokenizer_backend,
                )

        # Load multimodal processor for M-RoPE fallback computation.
        self._mm_processor = None
        if (
            self.model_config.is_multimodal
            and self.processor is not None
            and not get_disagg().language_model_only
        ):
            try:
                import_processors("sglang.srt.multimodal.processors")
                self._mm_processor = get_mm_processor(
                    self.model_config.hf_config,
                    server_args,
                    self.processor,
                    "default",
                    skip_mm_pool=True,
                )
            except Exception:
                logger.warning(
                    "Failed to load multimodal processor in scheduler; "
                    "M-RoPE fallback will not be available."
                )

        if get_serving().reasoning_parser and self.tokenizer:
            reasoning_parser = ReasoningParser(
                model_type=get_serving().reasoning_parser,
                stream_reasoning=False,
                tokenizer=self.tokenizer,
            )
            think_end_ids = self.tokenizer.encode(
                reasoning_parser.detector.think_end_token, add_special_tokens=False
            )
            if think_end_ids:
                self.model_config.think_end_ids = think_end_ids
            else:
                logger.warning(
                    "Reasoning parser think_end_token %r could not be encoded; "
                    "grammar-gated reasoning is disabled.",
                    reasoning_parser.detector.think_end_token,
                )

    def init_mamba_backend(self) -> None:
        if initialize_mamba_selective_state_update_backend is not None:
            initialize_mamba_selective_state_update_backend(self.server_args)

    def init_moe_gemm_config(self):
        # For the MM models, check the text_config for MoE settings
        config_to_check = getattr(
            self.model_config.hf_config, "text_config", self.model_config.hf_config
        )

        # Different MoE architectures expose the per-token expert count under
        # different attribute names (e.g. Gemma4 uses ``top_k_experts``,
        # LongCat-2.0 uses ``moe_topk``).
        moe_topk_attrs = (
            "num_experts_per_tok",
            "num_experts_per_token",
            "top_k_experts",
            "moe_top_k",
            "moe_topk",
        )
        if any(hasattr(config_to_check, attr) for attr in moe_topk_attrs):
            initialize_moe_config()

        # Initialize GEMM-related configuration for FP8 and FP4 backends.
        initialize_fp8_gemm_config()
        initialize_fp4_gemm_config()
        initialize_bf16_gemm_config(self.server_args)

        # This must be called after initialize_moe_config
        self.require_mlp_sync = require_mlp_sync()

    def init_tp_model_worker(self):
        worker_kwargs = dict(
            server_args=self.server_args,
            gpu_id=self.ps.gpu_id,
            ps=self.ps,
            nccl_port=self.nccl_port,
        )

        # FIXME: move tp worker's init logic outside of the scheduler.
        if use_mlx():
            from sglang.srt.hardware_backend.mlx.tp_worker import MlxTpModelWorker

            self.tp_worker = MlxTpModelWorker(**worker_kwargs)
        else:
            from sglang.srt.managers.tp_worker import TpModelWorker

            self.tp_worker = TpModelWorker(**worker_kwargs)

    def maybe_init_draft_worker(self):
        if self.spec_algorithm.is_none():
            self.draft_worker = None
            self.external_corpus_manager = None
            return

        # Launch a draft worker for speculative decoding. It builds its draft
        # from this process's own config: what differs for the draft — the
        # target's context length, the draft load format, its attention backend
        # — is resolved per runner, not on a config copy.
        draft_worker_kwargs = dict(
            server_args=self.server_args,
            gpu_id=self.ps.gpu_id,
            ps=self.ps,
            nccl_port=self.nccl_port,
            target_worker=self.tp_worker,
        )

        DraftWorkerClass = self.spec_algorithm.create_worker(self.server_args)
        self.draft_worker = DraftWorkerClass(**draft_worker_kwargs)

        if self.spec_algorithm.is_ngram():
            from sglang.srt.speculative.external_corpus_manager import (
                ExternalCorpusManager,
            )

            self.external_corpus_manager = ExternalCorpusManager(
                self.draft_worker,
                self.ipc_channels.send_to_tokenizer.send_output,
            )
        else:
            self.external_corpus_manager = None

    def init_target_memory_pool(self):
        """Allocate target KV cache pools if they have not been allocated yet."""
        if (
            self.tp_worker.model_runner.memory_pool_config is not None
            and self.tp_worker.model_runner.req_to_token_pool is not None
            and self.tp_worker.model_runner.token_to_kv_pool_allocator is not None
        ):
            return
        preloaded_weights_bytes = self.tp_worker.preloaded_weights_bytes
        if self.draft_worker is not None:
            preloaded_weights_bytes += self.draft_worker.preloaded_weights_bytes
        self.tp_worker.model_runner.account_preloaded_weights(preloaded_weights_bytes)
        self.tp_worker.alloc_memory_pool()

    def init_memory_pools(self):
        """Allocate KV cache pools for target and draft workers."""
        self.init_target_memory_pool()
        # Lands the retraction backend on the disagg bag before the draft
        # worker's HiCache plan reads it.
        kv_cache_builder.resolve_decode_retraction_backup(tp_worker=self.tp_worker)
        if self.draft_worker is not None:
            pool, allocator = self.tp_worker.get_memory_pool()
            self.draft_worker.alloc_memory_pool(
                memory_pool_config=self.tp_worker.model_runner.memory_pool_config,
                req_to_token_pool=pool,
                token_to_kv_pool_allocator=allocator,
            )
            self.draft_worker.init_hicache_draft_plan()

    def init_all_attention_backends(self):
        """Initialize attention backends for all workers."""
        self.tp_worker.init_attention_backends()
        if self.draft_worker is not None:
            self.draft_worker.init_attention_backends()

    def init_all_cuda_graphs(self):
        """Capture cuda graphs for all workers."""
        self.tp_worker.init_cuda_graphs()
        if self.draft_worker is not None:
            self.draft_worker.init_cuda_graphs()

    def init_model_worker(self):
        # Load model weights.
        self.init_tp_model_worker()
        if self.server_args.is_startup_weight_load_overlap:
            self.tp_worker.start_startup_weight_load()
        self.maybe_init_draft_worker()

        # Prepare KV cache pools for all workers
        tic = time.perf_counter()
        self.init_memory_pools()
        self.kv_cache_allocation_time = time.perf_counter() - tic

        self.init_all_attention_backends()
        self.init_all_cuda_graphs()

        model_runner = self.tp_worker.model_runner
        if model_runner.token_to_kv_pool.post_capture_active:
            tic = time.perf_counter()
            model_runner.post_capture_resize_kv_pool()
            self.kv_cache_allocation_time += time.perf_counter() - tic

        if self.server_args.is_startup_weight_load_overlap:
            self.tp_worker.finalize_startup_weight_load()

        if (
            get_exec().moe.elastic_ep_backend is not None
            and get_exec().moe.ep_join_mode == "recover"
        ):
            model_runner.post_capture_elastic_ep_recover()

        # Dispatch the model worker
        if self.spec_algorithm.is_none():
            self.model_worker = self.tp_worker
        else:
            self.model_worker = self.draft_worker

        # Get token and memory info from the model worker
        (
            self.max_total_num_tokens,
            self.max_prefill_tokens,
            self.max_running_requests,
            self.max_queued_requests,
            self.max_req_len,
            self.max_req_input_len,
            self.random_seed,
            self.device,
            self.forward_stream,
            _,
            _,
            _,
        ) = self.tp_worker.get_worker_info()
        # DFlash auto-enables the legacy formula; other workloads opt in via
        # --min-free-slots-delay. Built independently of the prefill delayer.
        self.min_free_slots_delayer: Optional[MinFreeSlotsDelayer] = None
        min_free_slots = resolve_min_free_slots(
            get_schedule().min_free_slots_delay,
            self.max_running_requests,
            is_dflash_family=self.spec_algorithm.is_dflash_family(),
        )
        if min_free_slots is not None:
            self.min_free_slots_delayer = MinFreeSlotsDelayer(
                min_free_slots=min_free_slots
            )
        if not get_parallel().pp_max_micro_batch_size:
            get_context().override(
                "scheduler.pp_max_micro_batch_size_default",
                pp_max_micro_batch_size=max(
                    self.max_running_requests // self.ps.pp_size, 1
                ),
            )

        self.tp_group = get_tp_group()
        self.tp_cpu_group = self.tp_group.cpu_group
        self.attn_tp_group = get_parallel().attn_tp_group
        self.attn_tp_cpu_group = self.attn_tp_group.cpu_group
        self.attn_cp_group = get_parallel().attn_cp_group
        self.attn_cp_cpu_group = self.attn_cp_group.cpu_group
        self.pp_group = get_pp_group()
        self.world_group = get_world_group()

        # NOTE: dp_tp_* are request/data-plane coordination groups (not tensor collectives).
        # When DP attention is enabled, scope to the attention-TP group; otherwise use
        # the base TP group. Entry rank is the local rank 0 in that group.
        # Use the CPU (gloo) group to broadcast VLM Python objects and avoid CUDA
        # stream/device coupling (#11910).
        self.dp_tp_group = (
            self.attn_tp_group if self.enable_dp_attention else self.tp_group
        )
        self.dp_tp_cpu_group = self.dp_tp_group.cpu_group

        # TODO(Jialin): Migrate pad_input_ids implementations to return array.
        self.pad_input_ids_func = self.tp_worker.get_pad_input_ids_func()
        set_random_seed(self.random_seed)

        # Print debug info
        self.startup_available_gpu_memory_gb = get_available_gpu_memory(
            self.device, self.ps.gpu_id, empty_cache=False
        )
        if self.ps.tp_rank == 0:
            logger.info(
                f"max_total_num_tokens={self.max_total_num_tokens}, "
                f"chunked_prefill_size={get_schedule().chunked_prefill_size}, "
                f"max_prefill_tokens={self.max_prefill_tokens}, "
                f"max_running_requests={self.max_running_requests}, "
                f"context_len={self.model_config.context_len}, "
                f"{'available_cpu_mem' if self.device == 'cpu' else 'available_gpu_mem'}="
                f"{self.startup_available_gpu_memory_gb:.2f} GB"
            )

    def emit_metrics_constants(self) -> None:
        if not get_observability().enable_metrics:
            return

        self.metrics_collector.emit_constants(
            max_total_num_tokens=self.max_total_num_tokens,
            max_total_num_tokens_swa=self.swa_tokens_per_layer,
            weight_memory_usage_gb=self.tp_worker.model_runner.weight_load_mem_usage,
            kv_cache_memory_usage_gb=(
                self.token_to_kv_pool_allocator.get_kvcache().mem_usage
            ),
            graph_memory_usage_gb=combine_graph_memory_usage(
                self.tp_worker.graph_memory_usage,
                (
                    None
                    if self.draft_worker is None
                    else self.draft_worker.graph_memory_usage
                ),
            ),
            # TODO: max_running_requests_under_SLO has no setter — dead chain.
            max_running_requests_under_SLO=None,
            page_size=self.page_size,
            num_pages=self.max_total_num_tokens // self.page_size,
            context_len=self.model_config.context_len,
            startup_available_gpu_memory_gb=self.startup_available_gpu_memory_gb,
        )

    def init_hisparse_coordinator(self) -> None:
        self.hisparse_coordinator: Optional[HiSparseCoordinator] = None
        if not self.enable_hisparse:
            return

        # Coordinator was created inside ModelRunner.initialize() before CUDA graph capture.
        self.hisparse_coordinator = self.tp_worker.model_runner.hisparse_coordinator
        self.hisparse_coordinator.set_decode_producer_stream(self.forward_stream)

    def init_running_status(self):
        # Set by the ShutdownReq handler to break the event loop for graceful shutdown.
        self.gracefully_exit = False
        self.waiting_queue: List[Req] = []
        self._host_alloc_wake_arbiter = HostAllocWakeArbiter()
        self._host_alloc_attempt_seq = 0
        # The running decoding batch for continuous batching
        self.running_batch: ScheduleBatch = ScheduleBatch(reqs=[], batch_is_full=False)
        # The current forward batch
        self.cur_batch_for_debug: Optional[ScheduleBatch] = None
        # The last forward batch
        self.last_batch: Optional[ScheduleBatch] = None
        self.forward_ct = 0
        self.return_health_check_ipcs: Deque[Optional[str]] = deque()
        self.flush_wrapper = SchedulerFlushWrapper(
            flush_cache=self.flush_cache,
            is_fully_idle=self.is_fully_idle,
            ipc_channels=self.ipc_channels,
        )
        self._last_logged_elastic_radix_namespace: Optional[str] = None
        self.session_controller = SessionController(self.tree_cache)
        self.forward_sleep_time = None
        self._engine_paused = False

    def init_chunked_prefill(self):
        self.chunked_prefill_size = get_schedule().chunked_prefill_size
        self.prefill_decode_interval = get_schedule().prefill_decode_interval
        self._prefill_decode_interval_remaining = 0
        uses_transformers_backend = (
            get_resolved_model_impl(self.model_config) == ModelImpl.TRANSFORMERS
        )
        if (
            self.chunked_prefill_size is not None
            and self.chunked_prefill_size > 0
            and self.model_config.is_multimodal
            and uses_transformers_backend
        ):
            logger.warning(
                "Chunked prefill is disabled for multimodal models with the "
                "Transformers backend to avoid partial multimodal chunk mismatches."
            )
            self.chunked_prefill_size = None
        elif self.chunked_prefill_size is not None and self.chunked_prefill_size <= 0:
            self.chunked_prefill_size = None
        self.chunked_req = None
        self._pending_chunked_abort_req = None
        self.is_mixed_chunk = (
            self.chunked_prefill_size is not None and get_schedule().enable_mixed_chunk
        )

        # Init the dynamic chunking predictor for PP
        self.enable_dynamic_chunking = (
            get_schedule().enable_dynamic_chunking and self.ps.pp_size > 1
        )
        if self.enable_dynamic_chunking:
            try:
                self.profile_and_init_predictor()
            except Exception as e:
                logger.warning(
                    f"[PP Dynamic Chunk] Failed to profile prefill latency: {e}. "
                    "Dynamic chunking will be disabled."
                )
                self.enable_dynamic_chunking = False

    def _should_defer_prefill(self) -> bool:
        if self._prefill_decode_interval_remaining == 0:
            return False

        self._prefill_decode_interval_remaining -= 1
        return True

    def _arm_prefill_decode_interval(self, batch: Optional[ScheduleBatch]) -> None:
        if self.prefill_decode_interval == 0 or batch is None:
            return

        # DP attention synchronizes this flag across ranks. This keeps every
        # rank on the same prefill/decode cadence even when only one rank has
        # local prefill work. Non-DP scheduling can use the local mode directly.
        is_extend = (
            batch.is_extend_in_batch
            if self.require_mlp_sync
            else batch.forward_mode.is_extend()
        )
        if is_extend:
            self._prefill_decode_interval_remaining = self.prefill_decode_interval

    def init_metrics_reporter(
        self, tp_rank: int, pp_rank: int, dp_rank: Optional[int]
    ) -> None:
        # Override point for deployments that need a specialized reporter.
        self.metrics_reporter = SchedulerMetricsReporter(
            scheduler=self,
            tp_rank=tp_rank,
            pp_rank=pp_rank,
            dp_rank=dp_rank,
            metrics_collector_context=self.metrics_collector_context,
            metrics_collector=self.metrics_collector,
        )

    def init_ready_horizon(self) -> None:
        """P3 Ready Horizon v0 (3.2): construct the ready-pool policy and
        its causal-epoch refill tracking (M3, user adjudication: per-rid
        causal negative-cache; the four causal epochs are compared each
        pass). The watermark is token-based (ledger 2026-09-01 adjudication
        #1): watermarks and the write-back reserve are expressed as KV-host
        token targets -- a fixed request count is not a stable resource
        target when state length varies. Count mode is the legacy
        fallback selected by the explicit *_count server_args."""
        state_p95 = self.server_args.ready_horizon_state_p95_tokens
        self.ready_horizon_state_p95_tokens = state_p95
        self.ready_horizon_reserve_tokens = (
            self.server_args.hicache_writeback_reserve_state_tokens
            or state_p95
        )
        self.ready_horizon_margin_tokens = (
            self.server_args.ready_horizon_margin_state_tokens
            or 0
        )
        low_count = self.server_args.ready_host_watermark_low_count
        high_count = self.server_args.ready_host_watermark_high_count
        if low_count is not None and high_count is not None:
            # Legacy count mode (explicit opt-in): the pre-token-semantics
            # request-count watermarks stand as configured.
            self.ready_horizon_token_mode = False
            watermark_low = low_count
            watermark_high = high_count
        else:
            self.ready_horizon_token_mode = True
            low = self.server_args.ready_host_watermark_low
            high = self.server_args.ready_host_watermark_high
            watermark_low = low if state_p95 == 0 else state_p95
            watermark_high = high if state_p95 == 0 else 2 * state_p95
        self.ready_horizon = ReadyHorizonPolicy(
            frontier_n=self.server_args.ready_horizon_frontier_n,
            watermark_low=watermark_low,
            watermark_high=watermark_high,
            token_mode=self.ready_horizon_token_mode,
        )
        self._ready_horizon_epoch_prev: Optional[CausalEpochs] = None
        self._ready_horizon_last_refill_ts = 0.0
        self._ready_horizon_last_log: Optional[tuple] = None
        # Fix A (P1): monotonic host-capacity release counter for the
        # NO_HEADROOM subscription. Bumped on every ~pool.available_size()
        # growth observed by the epoch snapshot (genuine host-capacity
        # releasing event: host residency freed, ready eviction, working-
        # state release). The counter never recedes when the working set
        # re-consumes the freed pages, so a NO_HEADROOM park clears exactly
        # once per release -- the transient-level subscription (available
        # flips 0->100->0 and can never sustain past the decline cursor
        # under a full working set) is the B-run permanent-freeze root
        # cause.
        self._ready_host_release_epoch = 0
        # Ground truth for the growth test: the last observed available
        # level. A level that INCREASED since the last snapshot is by
        # construction a release (only free() raises the free count); the
        # refill's own traffic only ever lowers it, so it can never
        # self-trigger.
        self._ready_host_release_last_level: Optional[int] = None
        # P3 M3 (user adjudication): per-rid causal negative-cache
        # (rid -> NegativeCacheEntry). A staged request that declined
        # parks here with its subscribed epoch's cursor; it is not re-
        # eligible until that epoch advances (or the request identity
        # changes, or the safety fuse expires). Deterministic L3 misses
        # are not transient -- the revoke frees the budget and would
        # re-arm the next pass without the park.
        self._ready_horizon_negatives: dict = {}
        self._rh_request_enqueue_seq = 0
        self._rh_pass_seq = 0

    def init_schedule_policy(self):
        # Init schedule policy and new token estimation
        self.policy = SchedulePolicy(
            self.schedule_policy,
            self.tree_cache,
            self.enable_hierarchical_cache,
            self.enable_priority_scheduling,
            self.schedule_low_priority_values_first,
        )
        self.prefill_delayer: Optional[PrefillDelayer] = None
        self.prefill_bs_tracker = RecentPrefillBatchSizeTracker(
            window_size=envs.SGLANG_PREFILL_DELAYER_MAX_PREFILL_BS_WINDOW_SIZE.get()
        )
        self.max_prefill_bs: int = 0
        if get_schedule().enable_prefill_delayer:
            if get_disagg().disaggregation_mode == "decode":
                logger.info(
                    "Ignoring --enable-prefill-delayer on decode engine "
                    "(no prefill scheduling path; delayer would be a no-op)."
                )
            else:
                self.prefill_delayer = PrefillDelayer(
                    dp_size=self.ps.dp_size,
                    attn_tp_size=self.ps.attn_tp_size,
                    cpu_group=self.tp_cpu_group,
                    device_group=self.tp_group.device_group,
                    server_args=self.server_args,
                    metrics_collector=(
                        self.metrics_collector
                        if self.metrics_reporter.enable_metrics
                        else None
                    ),
                    max_delay_passes=get_schedule().prefill_delayer_max_delay_passes,
                    token_usage_low_watermark=get_schedule().prefill_delayer_token_usage_low_watermark,
                    device=self.tp_group.device,
                    debug_log_enabled=self.ps.attn_tp_rank == 0,
                )

        # NOTE: preemption is enabled by default for priority scheduling.
        self.enable_priority_preemption = (
            self.enable_priority_scheduling
            and not get_schedule().disable_priority_preemption
        )

        self.new_token_ratio_tracker = NewTokenRatioTracker.from_config()

    def init_soft_watchdog(self):
        if (x := get_device().soft_watchdog_timeout) is not None:
            self.soft_watchdog = create_scheduler_watchdog(
                self, watchdog_timeout=x, soft=True
            )

    def init_watch_dog_memory_saver_input_blocker(self):
        # Start watchdog thread
        self.watchdog = create_scheduler_watchdog(
            self, watchdog_timeout=get_device().watchdog_timeout
        )

        # Init memory saver, profiler and metric stats
        self.memory_saver_adapter = TorchMemorySaverAdapter.create(
            enable=get_exec().features.enable_memory_saver
        )

        # Init recv skipper and input blocker
        self.recv_skipper = SchedulerRecvSkipper.maybe_create()
        self.input_blocker = (
            SchedulerInputBlocker(noop=self.ps.attn_tp_rank != 0)
            if get_bool_env_var("SGLANG_ENABLE_COLOCATED_BATCH_GEN")
            else None
        )

        # Configure GC logger
        if envs.SGLANG_LOG_GC.get():
            configure_gc_logger()

    def init_disaggregation(self):
        self.mm_receiver = None
        self.disagg_prefill_bootstrap_queue = None
        self.disagg_prefill_inflight_queue = None
        self.disagg_decode_prealloc_queue = None
        self.disagg_decode_transfer_queue = None

        self.disaggregation_mode = DisaggregationMode(get_disagg().disaggregation_mode)
        self.transfer_backend = TransferBackend(
            get_disagg().disaggregation_transfer_backend
        )

        # In rust-server mode the KV bootstrap registry is already serving on
        # the rust api listener (maybe_init_rust_server runs before this
        # method — the PrefillBootstrapQueue's KVManager below registers to it
        # synchronously, and a failed registration only retries ~60s then logs,
        # leaving every PD request unroutable). Only the ascend config store,
        # which start_disagg_service would otherwise create, is left to do.
        if (
            self.disaggregation_mode == DisaggregationMode.PREFILL
            and self._hosts_rust_server()
        ):
            maybe_create_ascend_config_store(
                transfer_backend=self.transfer_backend,
            )

        draft_token_to_kv_pool = (
            self.draft_worker.primary_draft_kv_pool
            if self.draft_worker is not None
            else None
        )

        if self.spec_algorithm.carries_draft_hidden_states():
            # `draft_runner` aliases `draft_runner_list[0]` in the multi-layer
            # worker, so a single accessor covers both shapes.
            draft_runner = self.draft_worker.draft_worker.draft_runner
            disagg_hidden_size, disagg_hidden_states_dtype = (
                get_draft_recurrent_hidden_state_spec(draft_runner)
            )
        else:
            disagg_hidden_size = 16  # minimal padding size for RDMA
            disagg_hidden_states_dtype = torch.float32

        # The PD metadata wire schema must match on P and D even when only D
        # enables spec decoding; a seedless prefill writes the invalid sentinel.
        output_dsa_topk_indices_dim = get_dsa_seed_metadata_dim(
            self.model_config.hf_config
        )

        if (
            self.disaggregation_mode == DisaggregationMode.DECODE
        ):  # *8 headroom for MiniMax-M3; *2 for other models.
            buffer_multiplier = (
                8 if is_minimax_sparse(self.model_config.hf_config) else 2
            )
            buffer_size = (self.req_to_token_pool.size) * buffer_multiplier
            self.req_to_metadata_buffer_idx_allocator = ReqToMetadataIdxAllocator(
                buffer_size
            )
            self.disagg_metadata_buffers = MetadataBuffers(
                buffer_size,
                hidden_size=disagg_hidden_size,
                hidden_states_dtype=disagg_hidden_states_dtype,
                custom_mem_pool=self.token_to_kv_pool_allocator.get_kvcache().maybe_get_custom_mem_pool(),
                output_dsa_topk_indices_dim=output_dsa_topk_indices_dim,
            )

            # The decode requests polling kv cache
            self.disagg_decode_transfer_queue = DecodeTransferQueue(
                gloo_group=self.attn_tp_cpu_group,
                req_to_metadata_buffer_idx_allocator=self.req_to_metadata_buffer_idx_allocator,
                tp_rank=self.ps.tp_rank,
                metadata_buffers=self.disagg_metadata_buffers,
                scheduler=self,
                tree_cache=self.tree_cache,
            )

            # The decode requests pending for pre-allocation
            self.disagg_decode_prealloc_queue = DecodePreallocQueue(
                req_to_token_pool=self.req_to_token_pool,
                token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
                draft_token_to_kv_pool=draft_token_to_kv_pool,
                req_to_metadata_buffer_idx_allocator=self.req_to_metadata_buffer_idx_allocator,
                metadata_buffers=self.disagg_metadata_buffers,
                scheduler=self,
                transfer_queue=self.disagg_decode_transfer_queue,
                tree_cache=self.tree_cache,
                gloo_group=self.attn_tp_cpu_group,
                tp_rank=self.ps.tp_rank,
                tp_size=self.ps.tp_size,
                dp_size=get_parallel().dp_size,
                gpu_id=self.ps.gpu_id,
                bootstrap_port=get_disagg().disaggregation_bootstrap_port,
                max_total_num_tokens=self.max_total_num_tokens,
                pp_rank=self.ps.pp_rank,
                num_reserved_decode_tokens=get_disagg().num_reserved_decode_tokens,
                transfer_backend=self.transfer_backend,
            )

        elif self.disaggregation_mode == DisaggregationMode.PREFILL:
            # *2 for the headroom.
            buffer_size = self.max_running_requests * 2
            self.req_to_metadata_buffer_idx_allocator = ReqToMetadataIdxAllocator(
                buffer_size
            )
            self.disagg_metadata_buffers = MetadataBuffers(
                buffer_size,
                hidden_size=disagg_hidden_size,
                hidden_states_dtype=disagg_hidden_states_dtype,
                custom_mem_pool=self.token_to_kv_pool_allocator.get_kvcache().maybe_get_custom_mem_pool(),
                output_dsa_topk_indices_dim=output_dsa_topk_indices_dim,
            )

            self.disagg_prefill_bootstrap_queue = PrefillBootstrapQueue(
                token_to_kv_pool=self.token_to_kv_pool_allocator.get_kvcache(),
                draft_token_to_kv_pool=draft_token_to_kv_pool,
                req_to_metadata_buffer_idx_allocator=self.req_to_metadata_buffer_idx_allocator,
                metadata_buffers=self.disagg_metadata_buffers,
                tp_rank=self.ps.tp_rank,
                tp_size=self.ps.tp_size,
                gpu_id=self.ps.gpu_id,
                bootstrap_port=get_disagg().disaggregation_bootstrap_port,
                gloo_group=self.attn_tp_cpu_group,
                max_total_num_tokens=self.max_total_num_tokens,
                scheduler=self,
                pp_rank=self.ps.pp_rank,
                pp_size=self.ps.pp_size,
                transfer_backend=self.transfer_backend,
            )
            # The prefill requests that are in the middle of kv sending
            self.disagg_prefill_inflight_queue: List[Req] = []
            # Requests with a sent chunk that are not yet on the inflight queue.
            self.disagg_prefill_pending_chunk_rids: Set[str] = set()

            self.enable_staging = envs.SGLANG_DISAGG_STAGING_BUFFER.get()

        if (
            self.enable_unified_memory
            and self.disaggregation_mode != DisaggregationMode.NULL
        ):
            self.token_to_kv_pool_allocator.set_disagg_move_gate(
                unified_memory_disagg_move_gate(self)
            )

        # Init mm receiver for EPD disaggregation mode
        if get_disagg().language_only and get_disagg().encoder_transfer_backend in [
            "zmq_to_scheduler",
            "mooncake",
        ]:
            self.mm_receiver = create_mm_receiver(
                self.server_args,
                dtype=self.model_config.dtype,
                hf_config=self.model_config.hf_config,
                pp_rank=self.ps.pp_rank,
                tp_rank=self.ps.tp_rank,
                tp_group=self.tp_group,
                scheduler=self,
            )

    def init_overlap(self):
        self.device_module = torch.get_device_module(self.device)

        # FutureMap is always-on: input_ids relay used in both modes.
        # Workers without the spec_v2_attn_backends override fall back to
        # target-only so the helper still produces a safe decision (no
        # accidental opt-out for unaudited shapes).
        if self.draft_worker is not None:
            attn_backends = getattr(
                self.draft_worker,
                "spec_v2_attn_backends",
                (self.tp_worker.model_runner.attn_backend,),
            )
        else:
            attn_backends = (self.tp_worker.model_runner.attn_backend,)
        needs_cpu_seq_lens = decide_needs_cpu_seq_lens(attn_backends)
        needs_confidence_relay = decide_needs_confidence_relay()
        self.future_map = self.spec_algorithm.create_future_map(
            self.device,
            self.req_to_token_pool,
            needs_cpu_seq_lens=needs_cpu_seq_lens,
            needs_confidence_relay=needs_confidence_relay,
        )

        self._confidence_budget_prepare = None
        if (
            needs_confidence_relay
            and self.enable_overlap
            and self.draft_worker is not None
        ):
            self._confidence_budget_prepare = (
                self.draft_worker.get_confidence_budget_prepare()
            )

        if use_mlx():
            # MLX uses its own overlap loop and does not create CUDA streams,
            # but the normal non-overlap scheduler path still relays decode
            # input IDs through FutureMap.
            self.result_queue: Deque = deque()
            return

        # forward_stream_ctx / copy_stream are also used by PP (non-overlap)
        # via scheduler_pp_mixin; init unconditionally to match main.
        self.forward_stream_ctx: CudaStreamContext = self.device_module.stream(
            self.forward_stream
        )
        self.copy_stream: CudaStream = self.device_module.Stream()
        self.copy_stream_ctx: CudaStreamContext = self.device_module.stream(
            self.copy_stream
        )

        if not self.enable_overlap:
            return

        self.batch_record_buf = [None] * 2
        self.batch_record_ct = 0

    def maybe_init_ngram_embedding(self):
        self.ngram_embedding_manager = (
            self.tp_worker.model_runner.ngram_embedding_manager
        )
        self.use_ngram_embedding = self.tp_worker.model_config.use_ngram_embedding
        if self.use_ngram_embedding:
            self.token_table = self.tp_worker.model_runner.ngram_embedding_manager.table
            hf_config = self.tp_worker.model_config.hf_config
            self.ngram_embedding_n = hf_config.ngram_embedding_n
            self.ngram_embedding_k = hf_config.ngram_embedding_k

    def init_deterministic_inference_config(self):
        """Initialize deterministic inference configuration for different attention backends."""
        if not get_exec().deterministic.enable_deterministic_inference:
            self.truncation_align_size = None
            return

        backend_sizes = {
            "flashinfer": ("SGLANG_FLASHINFER_PREFILL_SPLIT_TILE_SIZE", 4096),
            "triton": ("SGLANG_TRITON_PREFILL_TRUNCATION_ALIGN_SIZE", 4096),
        }
        # Both entries are prefill knobs (SPLIT_TILE / PREFILL_TRUNCATION):
        # the prefill half decides.
        prefill_backend, _ = attention_backends()
        env_var, default_size = backend_sizes.get(prefill_backend, (None, None))
        self.truncation_align_size = (
            get_int_env_var(env_var, default_size) if env_var else None
        )

    def init_request_dispatcher(self):
        self._request_dispatcher = TypeBasedDispatcher(
            [
                (TokenizedGenerateReqInput, self.handle_generate_request),
                (TokenizedEmbeddingReqInput, self.handle_embedding_request),
                (BatchTokenizedGenerateReqInput, self.handle_batch_generate_request),
                (BatchTokenizedEmbeddingReqInput, self.handle_batch_embedding_request),
                (FlushCacheReqInput, self.flush_wrapper.handle),
                (ClearHiCacheReqInput, self.clear_hicache_storage_wrapped),
                (AttachHiCacheStorageReqInput, self.attach_hicache_storage_wrapped),
                (DetachHiCacheStorageReqInput, self.detach_hicache_storage_wrapped),
                (AbortReq, self.abort_request),
                (OpenSessionReqInput, self.open_session),
                (CloseSessionReqInput, self.close_session),
                (
                    UpdateWeightFromDiskReqInput,
                    self.weight_updater.update_weights_from_disk,
                ),
                (
                    InitWeightsUpdateGroupReqInput,
                    self.weight_updater.init_weights_update_group,
                ),
                (
                    DestroyWeightsUpdateGroupReqInput,
                    self.weight_updater.destroy_weights_update_group,
                ),
                (
                    InitWeightsSendGroupForRemoteInstanceReqInput,
                    self.init_weights_send_group_for_remote_instance,
                ),
                (
                    SendWeightsToRemoteInstanceReqInput,
                    self.send_weights_to_remote_instance,
                ),
                (
                    UpdateWeightsFromDistributedReqInput,
                    self.weight_updater.update_weights_from_distributed,
                ),
                (
                    UpdateWeightsFromTensorReqInput,
                    self.weight_updater.update_weights_from_tensor,
                ),
                (
                    UpdateWeightsFromIPCReqInput,
                    self.weight_updater.update_weights_from_ipc,
                ),
                (
                    UpdateWeightVersionReqInput,
                    self.handle_update_weight_version,
                ),
                (
                    GetWeightsByNameReqInput,
                    self.weight_updater.get_weights_by_name,
                ),
                (
                    ReleaseMemoryOccupationReqInput,
                    self.weight_updater.release_memory_occupation,
                ),
                (
                    ResumeMemoryOccupationReqInput,
                    self.weight_updater.resume_memory_occupation,
                ),
                (
                    CheckWeightsReqInput,
                    self.weight_updater.check_weights,
                ),
                (SlowDownReqInput, self.slow_down),
                (
                    ProfileReq,
                    lambda req: self.profiler_manager._profile(req),
                ),
                (FreezeGCReq, self.handle_freeze_gc),
                (ShutdownReq, self.handle_shutdown),
                (GetInternalStateReq, self.get_internal_state),
                (SetInternalStateReq, self.set_internal_state),
                (RpcReqInput, self.handle_rpc_request),
                (ExpertDistributionReq, self.expert_distribution_handle),
                (LoadLoRAAdapterReqInput, self.load_lora_adapter),
                (
                    LoadLoRAAdapterFromTensorsReqInput,
                    self.load_lora_adapter_from_tensors,
                ),
                (UnloadLoRAAdapterReqInput, self.unload_lora_adapter),
                (PauseGenerationReqInput, self.pause_generation),
                (ContinueGenerationReqInput, self.continue_generation),
                (ConfigureLoggingReq, self.configure_logging),
                (ScaleElasticEPReqInput, self.handle_scale_elastic_ep),
                (DumperControlReqInput, self.handle_dumper_control),
                (AddExternalCorpusReqInput, self.add_external_corpus),
                (
                    RemoveExternalCorpusReqInput,
                    self.remove_external_corpus,
                ),
                (
                    ListExternalCorporaReqInput,
                    self.list_external_corpora,
                ),
            ]
        )

    def _abort_on_running_timeout(self, running_batch: ScheduleBatch):
        # NOTE: this should be called before a batch is launched.
        timeout_s = envs.SGLANG_REQ_RUNNING_TIMEOUT.get()
        if timeout_s <= 0:
            return
        if running_batch.is_empty():
            return

        deadline = time.perf_counter() - timeout_s
        for req in running_batch.reqs:
            if not req.finished() and 0 < req.time_stats.forward_entry_time < deadline:
                req.to_finish = FINISH_ABORT(
                    "Request running timeout reached.", HTTPStatus.SERVICE_UNAVAILABLE
                )

    def get_init_info(self) -> Dict[str, Any]:
        """Return scheduler initialization info for handshake.

        This method provides the initialization info needed by the tokenizer manager
        and other components to verify the scheduler is ready.
        """
        result_dict = {
            "status": "ready",
            "max_total_num_tokens": self.max_total_num_tokens,
            "max_req_input_len": self.max_req_input_len,
            "startup_time": self.startup_time,
        }

        return result_dict

    def release_host_resources(self) -> None:
        # Release pinned host buffers in userspace on graceful shutdown; see
        # HostKVCache.destroy. Called from run_scheduler_process's finally.
        if self.hisparse_coordinator is not None:
            self.hisparse_coordinator.destroy()
        self.tree_cache.release_host_resources()
        if self.decode_offload_manager is not None:
            self.decode_offload_manager.release_host_resources()

        rank_consensus_checker.shutdown()

    def run_event_loop(self) -> None:
        """Run the scheduler's event loop.

        Sets up the schedule stream and dispatches to the appropriate event loop.
        The event loop blocks until shutdown.
        """
        # Engine init (graph capture, warmups) is done; from here on any
        # Triton kernel device-load is a lazy first-use at serving time.
        triton_load_watch.install()
        triton_load_watch.mark_serving_started()

        if use_mlx():
            # MLX overlap uses mx.async_eval for CPU/GPU overlap,
            # not PyTorch MPS streams.
            dispatch_event_loop(self)
            return

        self.schedule_stream = self.device_module.Stream(priority=0)
        if self.device == "cpu":
            self.schedule_stream.synchronize = lambda: None  # No-op for CPU
        elif is_cuda() or _is_hip:
            # CUDA/HIP streams come from a fixed round-robin pool. Redraw if this
            # stream aliases forward_stream, which would eliminate scheduler
            # overlap. Only CUDA/HIP streams expose a ``cuda_stream`` handle;
            # other accelerators (e.g. NPU/XPU) skip the alias check.
            _redraws = 0
            while (
                self.schedule_stream.cuda_stream == self.forward_stream.cuda_stream
                and _redraws < 64
            ):
                self.schedule_stream = self.device_module.Stream(priority=0)
                _redraws += 1
        # The global WAR barrier fences the scheduler's next shared-buffer write
        # on the previous forward's read of the unified memory pool.
        self._war_barrier_enabled = is_cuda() or envs.SGLANG_ENABLE_WAR_BARRIER.get()
        with self.device_module.StreamContext(self.schedule_stream):
            dispatch_event_loop(self)

    def _apply_war_barrier(self):
        # WAR: keep later schedule_stream writes behind this forward's shared reads.
        # Clearing matters: a phase that skips the publish then falls back to coarse.
        if not self._war_barrier_enabled:
            return
        runner = self.model_worker.last_shared_read_runner
        ev = runner.shared_read_done_event
        runner.shared_read_done_event = None
        if ev is not None and not envs.SGLANG_FORCE_COARSE_WAR_BARRIER.get():
            self.schedule_stream.wait_event(ev)
        else:
            self.schedule_stream.wait_stream(self.forward_stream)

    @DynamicGradMode()
    def event_loop_normal(self):
        """A normal scheduler loop."""
        while True:
            if self.gracefully_exit:
                break

            # Receive requests
            recv_reqs = self.request_receiver.recv_requests()
            self.process_input_requests(recv_reqs)
            if self._engine_paused:
                continue

            # Get the next batch to run
            plan = self.get_next_batch_to_run(
                running_batch=self.running_batch, last_batch=self.last_batch
            )
            self.running_batch = plan.running_batch
            batch = plan.batch_to_run
            self.cur_batch_for_debug = batch

            # Launch the current batch
            if batch:
                result = self.run_batch(batch)
                self.process_batch_result(batch, result)
            else:
                # When the server is idle, do self-check and re-init some states.
                self._sched_idled = True
                self.on_idle()

            # Update last_batch
            self.last_batch = batch
            if envs.SGLANG_ENABLE_STRICT_MEM_CHECK_DURING_BUSY.get():
                self.invariant_checker.self_check_during_busy()

    @DynamicGradMode()
    def event_loop_overlap(self):
        """A scheduler loop that overlaps the CPU processing and GPU computation."""
        self.result_queue: Deque[
            Tuple[ScheduleBatch, Union[GenerationBatchResult, EmbeddingBatchResult]]
        ] = deque()

        def pop_and_process():
            # Process the results of the last batch
            tmp_batch, tmp_result = self.result_queue.popleft()
            self.process_batch_result(tmp_batch, tmp_result)

        while True:
            if self.gracefully_exit:
                break

            # Receive requests
            recv_reqs = self.request_receiver.recv_requests()
            self.process_input_requests(recv_reqs)
            if self._engine_paused:
                continue

            # Get the next batch to run
            plan = self.get_next_batch_to_run(
                running_batch=self.running_batch, last_batch=self.last_batch
            )
            self.running_batch = plan.running_batch
            batch = plan.batch_to_run
            self.cur_batch_for_debug = batch
            disable_overlap_for_batch = self.is_disable_overlap_for_batch(
                batch, last_batch=self.last_batch
            )

            # If we do not need to overlap the current batch with the last batch,
            # we can process the last batch immediately.
            if disable_overlap_for_batch:
                pop_and_process()
                # Opportunistic flush at the disable_overlap sync boundary:
                # forward_stream is idle (prev forward drained, next not launched),
                # so `_flush`'s non-urgent guard compacts freely. Sync-free, best-effort.
                if self.enable_unified_memory:
                    try:
                        self.token_to_kv_pool_allocator.flush_opportunistic()
                    except Exception:
                        pass

            # Launch the current batch
            if batch:
                batch_result = self.run_batch(batch)
                # Fence result processing behind this forward's shared reads.
                self._apply_war_barrier()
                self.result_queue.append((batch.copy(), batch_result))
            else:
                batch_result = None
                self._sched_idled = True

            # Process the last batch
            if self.last_batch:
                if not disable_overlap_for_batch:
                    pop_and_process()
            elif batch is None:
                # When the server is idle, do self-check and re-init some states
                self.on_idle()

            # Run sample of the current batch
            # It depends on the result of the last batch (e.g., grammar), so we run it after the last batch is processed.
            if self.is_generation:
                self.launch_batch_sample_if_needed(batch_result, batch)

            # Update last_batch
            self.last_batch = batch

            if envs.SGLANG_ENABLE_STRICT_MEM_CHECK_DURING_BUSY.get():
                self.invariant_checker.self_check_during_busy()

    def is_disable_overlap_for_batch(
        self, batch: ScheduleBatch, last_batch: Optional[ScheduleBatch]
    ) -> bool:
        # For two consecutive prefill batches, we disable overlap to improve the TTFT of the first batch.
        # This might slightly hurt the throughput, so we use an environment variable to control it.
        # In DP attention mode, use the globally synchronized is_extend_in_batch
        # so all DP ranks make the same overlap decision (avoiding deadlock).
        # In non-DP mode, use the local forward_mode directly.
        if self.require_mlp_sync:
            is_extend = lambda b: b and b.is_extend_in_batch
        else:
            is_extend = lambda b: b and b.forward_mode.is_extend()

        batch_is_extend = is_extend(batch)
        last_batch_is_extend = is_extend(last_batch)

        disable_overlap_for_batch = (
            envs.SGLANG_DISABLE_CONSECUTIVE_PREFILL_OVERLAP.get()
            and batch_is_extend
            and last_batch_is_extend
        )

        # Sync so the FSM advance lands before the next batch's bitmask. Permanent
        # path for host-draft algorithms, not a pending migration.
        need_grammar_sync = (
            batch
            and not batch.spec_algorithm.is_none()
            and batch.grammar_needs_sync()
            and batch.forward_mode.is_decode()
            and len(self.result_queue) > 0
        )

        # Algorithms that support grammar overlap advance the FSM inside verify()
        # via the grammar barrier (overlapping the target forward), which resolves
        # whatever result is still pending in the queue — including the
        # extend->decode boundary — so no grammar-specific overlap disable is needed.
        return disable_overlap_for_batch or need_grammar_sync

    def _advance_pending_grammar(self):
        """Grammar barrier (spec-v2 overlap): advance the FSM over any not-yet
        -processed decode result still in the queue, so a following verify()'s
        bitmask sees the previous batch's committed tokens. Invoked mid-worker
        (before generate_token_bitmask) so the CPU advance overlaps the target
        verify forward. Idempotent; no-op when the queue is empty or has no grammar.
        """
        for prev_batch, prev_result in self.result_queue:
            self.batch_result_processor.advance_grammar_fsm(prev_result, prev_batch)

    @scheduler_nvtx_method("scheduler.process_input_requests")
    def process_input_requests(self, recv_reqs: List):
        now = time.monotonic()
        self.session_controller.maybe_reap(now)
        if get_mm().mm_feature_transport == "cuda_vmm":
            for recv_req in recv_reqs:
                self._materialize_cuda_vmm_inputs(recv_req)

        for recv_req in recv_reqs:
            # Skip health check when server is busy — ongoing requests already carry health info.
            if is_health_check_generate_req(recv_req) and not self.is_fully_idle(
                for_health_check=True
            ):
                self.return_health_check_ipcs.append(
                    getattr(recv_req, "http_worker_ipc", None)
                )
                continue

            output = self._request_dispatcher(recv_req)
            if output is not None:
                if self.rust_server is not None:
                    # Embedded Rust server: every control-request response goes
                    # back through the egress ring (the zmq tokenizer socket is
                    # not consumed); the Rust api_server shapes it per-endpoint.
                    self.rust_server.push_control_output(recv_req, output)
                elif isinstance(output, RpcReqOutput):
                    if self.ipc_channels.recv_from_rpc is not None:
                        sock_send(self.ipc_channels.recv_from_rpc, output)
                else:
                    self.ipc_channels.send_to_tokenizer.send_output(output, recv_req)

        self.flush_wrapper.check_pending()
        if self.external_corpus_manager is not None:
            self.external_corpus_manager.check_pending_load()

    def _materialize_cuda_vmm_inputs(self, recv_req):
        """Release VMM slices before request handling can reject the request."""
        if isinstance(
            recv_req, (TokenizedGenerateReqInput, TokenizedEmbeddingReqInput)
        ):
            tokenized_reqs = (recv_req,)
        elif isinstance(
            recv_req,
            (BatchTokenizedGenerateReqInput, BatchTokenizedEmbeddingReqInput),
        ):
            tokenized_reqs = recv_req
        else:
            return

        for tokenized_req in tokenized_reqs:
            if tokenized_req.mm_inputs is not None and not isinstance(
                tokenized_req.mm_inputs, MultimodalInputs
            ):
                tokenized_req.mm_inputs = MultimodalInputs.from_processor_output(
                    tokenized_req.mm_inputs
                )

    def init_profiler(self) -> None:
        self.profiler_manager = SchedulerProfilerManager(
            ps=self.ps,
            dp_tp_cpu_group=self.dp_tp_cpu_group,
            get_forward_ct=lambda: self.forward_ct,
        )

    def init_weight_updater(self) -> None:
        self.weight_updater = SchedulerWeightUpdaterManager(
            tp_worker=self.tp_worker,
            draft_worker=self.draft_worker,
            tp_cpu_group=self.tp_cpu_group,
            memory_saver_adapter=self.memory_saver_adapter,
            flush_cache=self.flush_cache,
            is_fully_idle=self.is_fully_idle,
            scheduler=self,
            metrics_collector=self.metrics_collector,
        )

    def init_lora_drainer(self) -> None:
        if get_lora().lora_drain_wait_threshold > 0.0:
            self.lora_drainer = LoRADrainer(
                get_lora().max_loras_per_batch,
                get_lora().lora_drain_wait_threshold,
            )
        else:
            self.lora_drainer = None

    def init_lora_overlap_loader(self) -> None:
        if self.enable_lora_overlap_loading:
            self.lora_overlap_loader = LoRAOverlapLoader(
                self.tp_worker.model_runner.lora_manager
            )

    def init_grammar_manager(self) -> None:
        self.grammar_manager = GrammarManager(self)

    def maybe_init_scripted_scheduler_hook(self) -> None:
        if envs.SGLANG_TEST_SCRIPTED_RUNTIME.get():
            from sglang.test.scripted_runtime.scheduler_hook import (
                ScriptedSchedulerHook,
            )

            self.scripted_scheduler_hook = ScriptedSchedulerHook(
                scheduler=self,
                tokenizer_recv_proxy=self.ipc_channels.recv_from_tokenizer,
            )
        else:
            self.scripted_scheduler_hook = None

    def _hosts_rust_server(self) -> bool:
        """Whether this scheduler rank embeds the Rust server (rank 0 only) —
        and with it the server-process duties a Python ``TokenizerManager``
        would otherwise own (e.g. serving the PD KV bootstrap registry)."""
        return envs.SGLANG_RUST_SERVER.get() and (
            self.ps.pp_rank == 0
            and self.ps.attn_tp_rank == 0
            and self.ps.attn_cp_rank == 0
        )

    def maybe_init_rust_server(self) -> None:
        """Start the embedded Rust server (rank 0) if ``SGLANG_RUST_SERVER`` is
        set, and point the ingress receiver at it. All the plumbing lives in
        ``RustServer`` (scheduler_components/rust_scheduler.py)."""

        if not self._hosts_rust_server():
            # Always define the attribute: init_output_streamer and the
            # process_input_requests hook read self.rust_server unconditionally.
            self.rust_server = None
            return

        rust_server = RustServer.launch(self)
        self.rust_server = rust_server
        # The rust server *is* the ingress source: SchedulerRequestReceiver
        # drains its request ring (rust_server_mode) instead of a zmq socket.
        self.recv_from_tokenizer = rust_server
        # Park the idle loop on the request ring within the rank-0 rust-server
        self.idle_sleeper = RustServerIdleSleeper(rust_server)

    def init_request_receiver(self) -> None:
        self.request_receiver = SchedulerRequestReceiver(
            recv_from_tokenizer=self.recv_from_tokenizer,
            recv_from_rpc=self.ipc_channels.recv_from_rpc,
            recv_skipper=self.recv_skipper,
            input_blocker=self.input_blocker,
            mm_receiver=self.mm_receiver,
            ps=self.ps,
            tp_group=self.tp_group,
            tp_cpu_group=self.tp_cpu_group,
            attn_tp_group=self.attn_tp_group,
            attn_tp_cpu_group=self.attn_tp_cpu_group,
            attn_cp_group=self.attn_cp_group,
            attn_cp_cpu_group=self.attn_cp_cpu_group,
            world_group=self.world_group,
            server_args=self.server_args,
            model_config=self.model_config,
            max_recv_per_poll=self.max_recv_per_poll,
            stream_output=lambda *a, **kw: self.output_streamer.stream_output(*a, **kw),
            get_last_batch=lambda: self.last_batch,
            scripted_scheduler_hook=self.scripted_scheduler_hook,
        )

    def init_dp_attn_adapter(self) -> None:
        # Spec workers have no .model_runner of their own; the prefill graph
        # runner that votes belongs to the target model.
        target_worker = (
            self.tp_worker.target_worker
            if isinstance(self.tp_worker, BaseSpecWorker)
            else self.tp_worker
        )
        self.dp_attn_adapter = SchedulerDPAttnAdapter(
            model_runner=target_worker.model_runner,
            tp_group=self.tp_group,
            req_to_token_pool=self.req_to_token_pool,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            tree_cache=self.tree_cache,
            offload_tags=self.weight_updater.offload_tags,
            ps=self.ps,
            model_config=self.model_config,
            enable_overlap=self.enable_overlap,
            spec_algorithm=self.spec_algorithm,
            get_require_mlp_sync=lambda: self.require_mlp_sync,
        )

    def init_pool_stats_observer(self) -> None:
        self.pool_stats_observer = SchedulerPoolStatsObserver(
            tree_cache=self.tree_cache,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            req_to_token_pool=self.req_to_token_pool,
            session_controller=self.session_controller,
            hisparse_coordinator=self.hisparse_coordinator,
            is_hybrid_swa=self.is_hybrid_swa,
            is_hybrid_ssm=self.is_hybrid_ssm,
            enable_hisparse=self.enable_hisparse,
            full_tokens_per_layer=self.full_tokens_per_layer,
            swa_tokens_per_layer=self.swa_tokens_per_layer,
            max_total_num_tokens=self.max_total_num_tokens
            * get_parallel().attn_dcp_size,
            get_last_batch=lambda: self.last_batch,
            get_running_batch=lambda: self.running_batch,
        )

    def init_invariant_checker(self) -> None:
        self.invariant_checker = SchedulerInvariantChecker(
            is_hybrid_swa=self.is_hybrid_swa,
            is_hybrid_ssm=self.is_hybrid_ssm,
            disaggregation_mode=self.disaggregation_mode,
            page_size=self.page_size,
            full_tokens_per_layer=self.full_tokens_per_layer,
            swa_tokens_per_layer=self.swa_tokens_per_layer,
            max_total_num_tokens=self.max_total_num_tokens,
            tree_cache=self.tree_cache,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            req_to_token_pool=self.req_to_token_pool,
            pool_stats_observer=self.pool_stats_observer,
            get_last_batch=lambda: self.last_batch,
            get_running_batch=lambda: self.running_batch,
        )

    def init_rank_consensus_checker(self) -> None:
        groups = []
        if self.attn_cp_group is not None and self.attn_tp_group is not None:
            groups += [self.attn_cp_group, self.attn_tp_group]
        else:
            groups += [self.tp_group]
        if self.pp_group is not None:
            groups += [self.pp_group]
        rank_consensus_checker.configure(groups)

    def init_kv_events_publisher(self) -> None:
        self.kv_events_publisher = SchedulerKvEventsPublisher(
            kv_events_config=get_observability().kv_events_config,
            ps=self.ps,
            attn_tp_rank=self.ps.attn_tp_rank,
            attn_cp_rank=self.ps.attn_cp_rank,
            attn_dp_rank=self.ps.attn_dp_rank,
            dp_rank=self.ps.dp_rank,
            tree_cache=self.tree_cache,
            send_metrics_from_scheduler=self.ipc_channels.send_metrics_from_scheduler,
            max_running_requests=self.max_running_requests,
            max_total_num_tokens=self.max_total_num_tokens,
            get_stats=lambda: self.metrics_reporter.stats,
        )

    def init_load_publisher(self) -> None:
        # Router-facing load reporting; rank gating and no-op fallback live
        # inside the component. Same interval as the DP-balancing writer so
        # the two fire in phase and the load sink always reuses that snapshot
        # instead of walking the queues itself.
        self.load_publisher = SchedulerLoadPublisher(
            kv_events_config=get_observability().kv_events_config,
            ps=self.ps,
            load_publish_endpoint=get_observability().load_publish_endpoint,
            publish_interval=get_observability().load_snapshot_publish_interval,
        )

    def init_load_inquirer(self) -> None:
        self.total_prefill_uncached_tokens = 0
        self.total_prefill_busy_us = 0
        self.decode_moment_totals: list[float] = [0.0] * 6
        self._prev_step: Optional[Tuple[int, float, bool]] = None
        self._sched_idled = False
        self.load_inquirer = SchedulerLoadInquirer(
            disaggregation_mode=self.disaggregation_mode,
            ps=self.ps,
            server_args=self.server_args,
            max_total_num_tokens=self.max_total_num_tokens,
            max_running_requests=self.max_running_requests,
            pool_stats_observer=self.pool_stats_observer,
            tp_worker=self.tp_worker,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            spec_algorithm=self.spec_algorithm,
            get_running_batch=lambda: self.running_batch,
            get_waiting_queue=lambda: self.waiting_queue,
            waiting_queue_prefix_matched=lambda: self.policy.waiting_queue_prefix_matched(
                self.waiting_queue
            ),
            get_recent_cache_hit_rate=lambda: self.metrics_reporter.recent_cache_hit_rate,
            get_stats=lambda: self.metrics_reporter.stats,
            get_chunked_req=lambda: self.chunked_req,
            get_disagg_prefill_bootstrap_queue=lambda: self.disagg_prefill_bootstrap_queue,
            get_disagg_prefill_inflight_queue=lambda: self.disagg_prefill_inflight_queue,
            get_disagg_decode_prealloc_queue=lambda: self.disagg_decode_prealloc_queue,
            get_disagg_decode_transfer_queue=lambda: self.disagg_decode_transfer_queue,
            get_spec_total_num_accept_tokens=lambda: self.metrics_reporter.spec_total_num_accept_tokens,
            get_spec_total_num_forward_ct=lambda: self.metrics_reporter.spec_total_num_forward_ct,
            get_total_prefill_uncached_tokens=lambda: self.total_prefill_uncached_tokens,
            get_total_prefill_busy_us=lambda: self.total_prefill_busy_us,
            get_decode_moment_totals=lambda: self.decode_moment_totals,
        )

    def init_output_streamer(self) -> None:
        self.output_streamer = self.get_output_streamer_class()(
            send_to_detokenizer=self.ipc_channels.send_to_detokenizer,
            tree_cache=self.tree_cache,
            ps=self.ps,
            server_args=self.server_args,
            is_generation=self.is_generation,
            spec_algorithm=self.spec_algorithm,
            disaggregation_mode=self.disaggregation_mode,
            enable_hicache_storage=lambda: self.enable_hicache_storage,
            rust_server=self.rust_server,
        )

    def get_output_streamer_class(self) -> type[SchedulerOutputStreamer]:
        return SchedulerOutputStreamer

    def init_beam_coordinator(self) -> None:
        self.beam_coordinator = BeamCoordinator(
            model_config=self.model_config,
            spec_algorithm=self.spec_algorithm,
            dllm_enabled=self.dllm_config is not None,
            max_req_len=self.max_req_len,
            req_to_token_pool=self.req_to_token_pool,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            tree_cache=self.tree_cache,
            future_map=self.future_map,
        )

    def init_batch_result_processor(self) -> None:
        self.init_beam_coordinator()
        self.batch_result_processor = SchedulerBatchResultProcessor(
            is_generation=self.is_generation,
            disaggregation_mode=self.disaggregation_mode,
            enable_overlap=self.enable_overlap,
            enable_overlap_mlx=self.enable_overlap_mlx,
            model_config=self.model_config,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            tree_cache=self.tree_cache,
            hisparse_coordinator=self.hisparse_coordinator,
            req_to_token_pool=self.req_to_token_pool,
            decode_offload_manager=self.decode_offload_manager,
            metrics_collector=self.metrics_collector,
            metrics_reporter=self.metrics_reporter,
            draft_worker=self.draft_worker,
            model_worker=self.model_worker,
            logprob_result_processor=SchedulerLogprobResultProcessor(
                model_config=self.model_config
            ),
            output_streamer=self.output_streamer,
            beam_coordinator=self.beam_coordinator,
            abort_request=self.abort_request,
        )

    def init_req_max_new_tokens(self, req):
        input_len = len(req.origin_input_ids)
        max_new_tokens = (
            req.sampling_params.max_new_tokens
            if req.sampling_params.max_new_tokens is not None
            else 1 << 30
        )
        if self.max_new_tokens_limit is not None and self.max_new_tokens_limit > 0:
            if max_new_tokens > self.max_new_tokens_limit:
                logger.warning(
                    f"Capping max_new_tokens of request {req.rid} to "
                    f"SGLANG_MAX_NEW_TOKENS_LIMIT={self.max_new_tokens_limit} "
                    f"(requested: {req.sampling_params.max_new_tokens})."
                )
            max_new_tokens = min(max_new_tokens, self.max_new_tokens_limit)

        # Keep this bound consistent with PrefillAdder's admission budget:
        # ceil_page(input_len) + max_new_tokens + page_size must be strictly
        # smaller than max_total_num_tokens. Otherwise a request can be accepted
        # into the waiting queue but can never be scheduled, blocking the queue
        # and eventually making health checks fail.
        paged_input_len = -(-input_len // self.page_size) * self.page_size
        req.sampling_params.max_new_tokens = max(
            0,
            min(
                max_new_tokens,
                self.max_req_len - input_len - 1,
                self.max_total_num_tokens * get_parallel().attn_dcp_size
                - paged_input_len
                - self.page_size
                - 1,
            ),
        )
        # Clipping above can push max_new_tokens below min_new_tokens, which
        # would suppress EOS for the whole generation. Restore the invariant.
        if req.sampling_params.min_new_tokens > req.sampling_params.max_new_tokens:
            req.sampling_params.min_new_tokens = req.sampling_params.max_new_tokens

    def _process_and_broadcast_mm_inputs(
        self,
        raw_mm_inputs,
    ):
        """Materialize MultimodalInputs once on the entry rank and broadcast to others.

        Entry rank:
        - constructs MultimodalInputs.from_processor_output() once
        - broadcasts to other ranks in self.cpu_group (if world_size > 1)

        Non-entry ranks:
        - receive the object via broadcast (if world_size > 1)
        - otherwise (single-rank / no group) fall back to local from_processor_output

        Returns:
            MultimodalInputs | None
        """
        if raw_mm_inputs is None:
            return None

        group_world_size = 1
        try:
            if (
                torch.distributed.is_available()
                and torch.distributed.is_initialized()
                and self.dp_tp_cpu_group is not None
            ):
                group_world_size = torch.distributed.get_world_size(
                    group=self.dp_tp_cpu_group
                )
        except Exception as e:
            logger.warning(
                f"Failed to get world size in mm_inputs handling with {e}, fallback to 1."
            )

        # In case tp size > 1, all the Scheduler TP ranks runs the duplicated computing
        # process in CPU which occupies the main thread CPU cycle. This computing logic
        # merely needs to be run on TP0 and be broadcast to other TP ranks.
        # Since the Scheduler is single-threaded, any large CPU cost will impact
        # handling of other messages. For example, CPU hits 99.9% can significantly
        # increase the CUDA kernel launch time.
        if self.dp_tp_group.rank_in_group == 0:
            # Only the entry rank materializes once from dict.
            image_inputs = MultimodalInputs.from_processor_output(raw_mm_inputs)
            # Broadcast to other TP ranks (use src=0 within the group).
            if group_world_size > 1:
                obj_list = [image_inputs]
                torch.distributed.broadcast_object_list(
                    obj_list,
                    src=self.dp_tp_group.first_rank,
                    group=self.dp_tp_cpu_group,
                )
                image_inputs = obj_list[0]
        else:
            # Non-entry ranks: receive if group size > 1; otherwise materialize locally.
            if group_world_size > 1:
                obj_list = [None]
                torch.distributed.broadcast_object_list(
                    obj_list,
                    src=self.dp_tp_group.first_rank,
                    group=self.dp_tp_cpu_group,
                )
                image_inputs = obj_list[0]
            else:
                image_inputs = MultimodalInputs.from_processor_output(raw_mm_inputs)

        return image_inputs

    def _get_multimodal_inputs(self, mm_inputs):
        if isinstance(mm_inputs, MultimodalInputs):
            return mm_inputs

        if get_mm().enable_broadcast_mm_inputs_process:
            return self._process_and_broadcast_mm_inputs(mm_inputs)
        return MultimodalInputs.from_processor_output(mm_inputs)

    @staticmethod
    def _try_apply_padded_mm_input_ids(recv_req, req, image_inputs) -> bool:
        """setup origin_input_ids with trying to reuse existing MultimodalInputs.padded_input_ids first,
        if absent, call pad_input_ids_func"""
        padded_input_ids = image_inputs.padded_input_ids
        if padded_input_ids is None or recv_req.input_ids is None:
            return False

        recv_input_len = len(recv_req.input_ids)
        if len(padded_input_ids) != recv_input_len:
            return False

        prefix_len = len(req.origin_input_ids) - recv_input_len
        if prefix_len < 0:
            return False

        padded_input_ids = array("q", padded_input_ids)
        if prefix_len == 0:
            req.origin_input_ids = padded_input_ids
        else:
            req.origin_input_ids = req.origin_input_ids[:prefix_len] + padded_input_ids
        return True

    def _maybe_compute_mrope_positions(self, req) -> None:
        """Compute M-RoPE positions when they are missing (e.g. gRPC preprocessed path)."""
        if self._mm_processor is None:
            return
        mm = req.multimodal_inputs
        if mm is None or mm.mrope_positions is not None:
            return

        mrope_positions, mrope_position_delta = (
            self._mm_processor.compute_mrope_positions(
                req.origin_input_ids, mm.mm_items
            )
        )
        if mrope_positions is not None:
            mm.mrope_positions = mrope_positions
            mm.mrope_position_delta = mrope_position_delta

    def _maybe_namespace_elastic_radix_cache(self, req: Req) -> None:
        if (
            get_exec().moe.elastic_ep_backend is None
            or self.disable_radix_cache
            or not self.tree_cache.is_tree_cache()
        ):
            return

        from sglang.srt.elastic_ep.elastic_ep import ElasticEPStateManager

        inst = ElasticEPStateManager.instance()
        if inst is None:
            return

        namespace = f"elastic_ep_size={ElasticEPStateManager.get_effective_ep_size()}"
        if req.extra_key:
            req.extra_key = f"{req.extra_key}|{namespace}"
        else:
            req.extra_key = namespace

        if self._last_logged_elastic_radix_namespace != namespace:
            self._last_logged_elastic_radix_namespace = namespace
            logger.debug(
                "[Elastic EP][scale] radix cache namespace is now %s",
                namespace,
            )

    def _maybe_clear_mm_inputs(self, batch: ScheduleBatch) -> None:
        for req in batch.reqs:
            if not req.finished() or not (mm_inputs := req.multimodal_inputs):
                continue
            # For session requests, keep mm_inputs for the next request
            if req.session:
                continue
            # For non-session requests, clear features and mm_inputs
            mm_inputs.release_features()
            req.multimodal_inputs = None

    def handle_generate_request(
        self,
        recv_req: TokenizedGenerateReqInput,
    ):
        # Route: normal request / session request / session-not-found
        session_id = (
            recv_req.session_params.id if recv_req.session_params is not None else None
        )
        # Radix-native sessions use only the top-level session_id.
        radix_native_session = (
            recv_req.session_id is not None and self.enable_session_radix_cache
        )

        if session_id is None or radix_native_session:
            # Normal non-session request, or a radix-native session request
            if recv_req.input_embeds is not None:
                # Generate fake input_ids based on the length of input_embeds
                seq_length = len(recv_req.input_embeds)
                recv_req.input_ids = array("q", [1]) * seq_length

            if recv_req.bootstrap_port is None:
                # Use default bootstrap port
                recv_req.bootstrap_port = get_disagg().disaggregation_bootstrap_port

            is_beam = BeamCoordinator.request_beam_width(recv_req) > 1
            req = Req(
                recv_req.rid,
                recv_req.input_text,
                recv_req.input_ids,
                recv_req.sampling_params,
                return_logprob=recv_req.return_logprob,
                top_logprobs_num=recv_req.top_logprobs_num,
                token_ids_logprob=recv_req.token_ids_logprob,
                return_sampling_mask=recv_req.return_sampling_mask,
                return_flat_raw_top_logprobs=recv_req.return_flat_raw_top_logprobs,
                stream=recv_req.stream,
                lora_id=recv_req.lora_id,
                session_id=recv_req.session_id,
                input_embeds=recv_req.input_embeds,
                positional_embed_overrides=recv_req.positional_embed_overrides,
                token_type_ids=recv_req.token_type_ids,
                custom_logit_processor=recv_req.custom_logit_processor,
                require_reasoning=recv_req.require_reasoning,
                return_hidden_states=recv_req.return_hidden_states,
                return_routed_experts=recv_req.return_routed_experts,
                routed_experts_start_len=recv_req.routed_experts_start_len,
                return_indexer_topk=recv_req.return_indexer_topk,
                eos_token_ids=self.model_config.hf_eos_token_id,
                bootstrap_host=recv_req.bootstrap_host,
                bootstrap_port=recv_req.bootstrap_port,
                bootstrap_room=recv_req.bootstrap_room,
                disagg_mode=self.disaggregation_mode,
                routed_dp_rank=recv_req.routed_dp_rank,
                disagg_prefill_dp_rank=recv_req.disagg_prefill_dp_rank,
                vocab_size=self.model_config.vocab_size,
                priority=recv_req.priority,
                metrics_collector=(
                    self.metrics_collector
                    if self.metrics_reporter.enable_metrics
                    else None
                ),
                routing_key=recv_req.routing_key,
                extra_key=recv_req.extra_key,
                cache_salt=recv_req.cache_salt,
                http_worker_ipc=recv_req.http_worker_ipc,
                dllm_config=self.dllm_config,
                time_stats=recv_req.time_stats,
                multi_item_delimiter_indices=recv_req.multi_item_delimiter_indices,
            )
            req.tokenizer = self.tokenizer

            if radix_native_session:
                req.session_generation = self.tree_cache.ensure_session_generation(
                    recv_req.session_id
                )

            if is_beam:
                error_msg = self.beam_coordinator.validate_and_init(req, recv_req)
                if error_msg:
                    logger.error(error_msg)
                    prepare_abort(req, error_msg, status_code=HTTPStatus.BAD_REQUEST)
                    self.output_streamer.stream_output([req], req.return_logprob)
                    return

            if self.disaggregation_mode != DisaggregationMode.NULL:
                # Invalid request for disaggregated mode
                if (
                    recv_req.bootstrap_room is None
                    and self.transfer_backend != TransferBackend.FAKE
                ):
                    error_msg = (
                        f"Invalid request: Disaggregated request received without "
                        f"bootstrap room id. {req.rid=}"
                    )
                    logger.error(error_msg)
                    if not envs.SGLANG_RUST_SERVER.get():
                        recv_req.time_stats.trace_ctx.abort(
                            abort_info={"reason": error_msg}
                        )
                    prepare_abort(req, error_msg, status_code=HTTPStatus.BAD_REQUEST)
                    self.output_streamer.stream_output([req], req.return_logprob)
                    return

        elif (
            session_id in self.session_controller
            and not self.session_controller.get(session_id).close_on_finish
        ):
            # Session exists and is not closing: create request from session
            session = self.session_controller.get(session_id)
            req = session.create_req(
                recv_req,
                self.tokenizer,
                self.model_config.vocab_size,
                eos_token_ids=self.model_config.hf_eos_token_id,
            )
            if self.enable_session_radix_cache:
                req.session_generation = self.tree_cache.ensure_session_generation(
                    session_id
                )
            # TODO: set trace context
            if self.metrics_reporter.enable_metrics:
                req.time_stats.set_metrics_collector(self.metrics_collector)
            if isinstance(req.finished_reason, FINISH_ABORT):
                self.init_req_max_new_tokens(req)
                self._add_request_to_queue(req)
                return

        else:
            # Session not found, or session is closing
            if session_id in self.session_controller:
                error_msg = (
                    f"Invalid request: close was requested for session {session_id}"
                )
            else:
                error_msg = f"Invalid request: session id {session_id} does not exist"
            req = Req(
                recv_req.rid,
                recv_req.input_text,
                recv_req.input_ids,
                recv_req.sampling_params,
                vocab_size=self.model_config.vocab_size,
                http_worker_ipc=recv_req.http_worker_ipc,
            )
            req.tokenizer = self.tokenizer
            req.set_finish_with_abort(error_msg)
            self.init_req_max_new_tokens(req)
            self._add_request_to_queue(req)
            return

        self._maybe_namespace_elastic_radix_cache(req)

        if self.spec_algorithm.is_dflash_family():
            error_msg = validate_dflash_request(req, self.enable_overlap)
            if error_msg is not None:
                req.set_finish_with_abort(error_msg)
                self.init_req_max_new_tokens(req)
                self._add_request_to_queue(req)
                return

        if (
            req.return_sampling_mask
            and self.disaggregation_mode != DisaggregationMode.NULL
            and not self.disagg_metadata_buffers.enable_sampling_mask
        ):
            error_msg = (
                "return_sampling_mask with disaggregation requires "
                "SGLANG_DISAGGREGATION_SAMPLING_MASK_MAX_TOKENS > 0."
            )
            req.set_finish_with_abort(error_msg)
            self.init_req_max_new_tokens(req)
            self._add_request_to_queue(req)
            return

        if req.return_sampling_mask and req.sampling_params.top_k == TOP_K_ALL:
            error_msg = (
                "return_sampling_mask requires finite top_k; top_p-only sampling "
                "is valid but can return huge masks in the tail, blowing up "
                "metadata, so we need a safety cap."
            )
            req.set_finish_with_abort(error_msg)
            self.init_req_max_new_tokens(req)
            self._add_request_to_queue(req)
            return

        if req.return_sampling_mask and not self.spec_algorithm.is_none():
            # Spec workers do not emit one sampling support per accepted token, so
            # the returned mask would not align 1:1 with generated tokens. Reject
            # the combination instead of silently returning a misaligned mask.
            error_msg = (
                "return_sampling_mask is not supported with speculative decoding."
            )
            req.set_finish_with_abort(error_msg)
            self.init_req_max_new_tokens(req)
            self._add_request_to_queue(req)
            return

        if req.return_sampling_mask and get_exec().kernel.sampling_backend == "ascend":
            # The ascend backend samples from logits directly and never builds the
            # top-k/top-p support, so it cannot produce a sampling mask.
            error_msg = (
                "return_sampling_mask is not supported with the ascend "
                "sampling backend."
            )
            req.set_finish_with_abort(error_msg)
            self.init_req_max_new_tokens(req)
            self._add_request_to_queue(req)
            return

        # Handle multimodal inputs
        if recv_req.mm_inputs is not None:
            image_inputs = self._get_multimodal_inputs(recv_req.mm_inputs)

            SessionController.adjust_mm_offsets(recv_req, req, image_inputs)

            # The following steps are already fast, execute locally on each rank.
            # Expand a single image token into multiple dummy tokens for receiving image embeddings.
            # The pad function is model-specific and can be None for some backends.
            if (
                not self._try_apply_padded_mm_input_ids(recv_req, req, image_inputs)
                and self.pad_input_ids_func
            ):
                req.origin_input_ids = array(
                    "q", self.pad_input_ids_func(req.origin_input_ids, image_inputs)
                )
            req.extend_image_inputs(image_inputs)
            self._maybe_compute_mrope_positions(req)

            if len(req.origin_input_ids) >= self.max_req_input_len:
                req.set_finish_with_abort(
                    error_msg=(
                        "Multimodal prompt is too long after expanding multimodal tokens. "
                        f"After expanding {len(req.origin_input_ids_unpadded)=} => {len(req.origin_input_ids)} >= {self.max_req_input_len}."
                    )
                )
                self.init_req_max_new_tokens(req)
                self._add_request_to_queue(req)
                return

        # initialize before returning
        self.init_req_max_new_tokens(req)

        # Validate prompt length
        error_msg = validate_input_length(
            req,
            self.max_req_input_len,
            get_serving().allow_auto_truncate,
        )
        if error_msg:
            req.set_finish_with_abort(error_msg)
            self._add_request_to_queue(req)
            return

        if not recv_req.return_logprob and recv_req.logprob_start_len != -1:
            # When return_logprob is False, logprob_start_len should be ignored
            recv_req.logprob_start_len = -1

        if recv_req.logprob_start_len == -1:
            if recv_req.return_logprob and recv_req.token_ids_logprob is None:
                # If logprob is required but neither token_ids_logprob nor logprob_start_len is
                # set, return the logprobs for output tokens by default
                req.logprob_start_len = len(req.origin_input_ids)
            elif req.is_prefill_only:
                # For prefill-only requests with logprob_start_len == -1, set logprob_start_len
                # beyond input sequence to skip input logprob computation entirely
                req.logprob_start_len = len(req.origin_input_ids)
            else:
                # If return_logprob is False, only the last token requires logprob computation
                req.logprob_start_len = -1
        else:
            req.logprob_start_len = recv_req.logprob_start_len

        if req.logprob_start_len > len(req.origin_input_ids):
            error_msg = f"{req.logprob_start_len=} is higher than the number of input tokens {len(req.origin_input_ids)=}. Please use a smaller logprob_start_len."
            req.logprob_start_len = -1
            req.set_finish_with_abort(error_msg)
            self._add_request_to_queue(req)
            return

        if (
            get_device().mlx_enable_sampling
            and req.return_logprob
            and 0 <= req.logprob_start_len < len(req.origin_input_ids)
        ):
            # The MLX sampling path computes output logprobs only; the
            # prefill result carries no input_token_logprobs, so letting
            # this through would crash output processing.
            error_msg = (
                "Prompt input logprobs (logprob_start_len) are not supported "
                "on the MLX sampling path; omit logprob_start_len to get "
                "output logprobs."
            )
            req.logprob_start_len = -1
            req.set_finish_with_abort(error_msg)
            self._add_request_to_queue(req)
            return

        if recv_req.return_routed_experts:
            error_msg = None
            if recv_req.routed_experts_start_len < 0:
                error_msg = (
                    f"{recv_req.routed_experts_start_len=} is lower than 0. "
                    "Please use a non-negative routed_experts_start_len."
                )

            if recv_req.routed_experts_start_len > len(req.origin_input_ids):
                error_msg = (
                    f"{recv_req.routed_experts_start_len=} is higher than the "
                    f"number of input tokens {len(req.origin_input_ids)=}. Please "
                    f"use a smaller routed_experts_start_len."
                )

            if error_msg is not None:
                req.routed_experts_start_len = 0
                req.set_finish_with_abort(error_msg)
                self._add_request_to_queue(req)
                return

        added_to_grammar_queue = self.grammar_manager.process_req_with_grammar(req)
        if not added_to_grammar_queue:
            self._add_request_to_queue(req)

    def handle_batch_generate_request(
        self,
        recv_req: BatchTokenizedGenerateReqInput,
    ):
        """Handle optimized batch generate request."""
        logger.debug(f"Processing batch generate request with {len(recv_req)} requests")

        # Process each request in the batch
        for tokenized_req in recv_req:
            self.handle_generate_request(tokenized_req)

    def _claim_prefetch(self, req: Req, origin: HiCachePrefetchOrigin):
        active_attempt_id = getattr(req, "hicache_prefetch_active_attempt_id", None)
        if active_attempt_id is not None:
            return None
        sequence = getattr(req, "hicache_prefetch_attempt_seq", 0) + 1
        attempt_id = f"{req.rid}:prefetch:{sequence}"
        req.hicache_prefetch_attempt_seq = sequence
        req.hicache_prefetch_active_attempt_id = attempt_id
        req.hicache_prefetch_active_origin = origin
        return attempt_id

    def _release_prefetch_claim(
        self, req: Req, attempt_id: Optional[str], terminal_reason: str
    ) -> bool:
        active_attempt_id = getattr(req, "hicache_prefetch_active_attempt_id", None)
        if active_attempt_id != attempt_id:
            logger.info(
                "[P3] evt=prefetch_claim_release_stale rid=%s expected=%s active=%s reason=%s",
                req.rid,
                attempt_id,
                active_attempt_id,
                terminal_reason,
            )
            return False
        if active_attempt_id is None:
            return False
        req.hicache_prefetch_last_attempt_id = active_attempt_id
        req.hicache_prefetch_last_origin = getattr(
            req, "hicache_prefetch_active_origin", None
        )
        req.hicache_prefetch_active_attempt_id = None
        req.hicache_prefetch_active_origin = None
        return True

    @staticmethod
    def _prefetch_state_name(state) -> str:
        return state.name if state is not None else "null"

    def _prefetch_result(
        self,
        req: Req,
        status: HiCachePrefetchIssueStatus,
        origin: HiCachePrefetchOrigin,
        reason: str,
        state_before: str,
        attempt_id: Optional[str] = None,
    ) -> PrefetchIssueResult:
        return PrefetchIssueResult(
            status=status,
            attempt_id=(
                attempt_id
                if attempt_id is not None
                else getattr(req, "hicache_prefetch_active_attempt_id", None)
            ),
            origin=origin,
            reason=reason,
            state_before=state_before,
            state_after=self._prefetch_state_name(
                getattr(req, "hicache_restore_state", None)
            ),
        )

    def _prefetch_kvcache(
        self,
        req: Req,
        *,
        origin: HiCachePrefetchOrigin,
        demand_restore: bool = False,
    ) -> PrefetchIssueResult:
        attempt_id = self._claim_prefetch(req, origin)
        if attempt_id is None:
            active_origin = getattr(
                req, "hicache_prefetch_active_origin", None
            ) or origin
            state = self._prefetch_state_name(
                getattr(req, "hicache_restore_state", None)
            )
            return PrefetchIssueResult(
                HiCachePrefetchIssueStatus.SKIPPED_ACTIVE,
                getattr(req, "hicache_prefetch_active_attempt_id", None),
                active_origin,
                "active_attempt",
                state,
                state,
            )
        try:
            result = self._prefetch_kvcache_impl(
                req, origin=origin, demand_restore=demand_restore
            )
        except Exception:
            self._release_prefetch_claim(req, attempt_id, "exception")
            raise
        result_status = (
            result.status
            if isinstance(result, PrefetchIssueResult)
            else result
        )
        if result_status is HiCachePrefetchIssueStatus.ISSUED:
            return result
        self._release_prefetch_claim(
            req,
            attempt_id,
            result.reason if isinstance(result, PrefetchIssueResult) else "declined",
        )
        return result

    def _prefetch_kvcache_impl(
        self,
        req: Req,
        *,
        origin: HiCachePrefetchOrigin,
        demand_restore: bool = False,
    ) -> PrefetchIssueResult:
        state_before_value = getattr(req, "hicache_restore_state", None)
        state_before = (
            state_before_value.name if state_before_value is not None else "null"
        )

        def result(status, reason):
            state_after_value = getattr(req, "hicache_restore_state", None)
            return PrefetchIssueResult(
                status=status,
                attempt_id=getattr(
                    req, "hicache_prefetch_active_attempt_id", None
                ),
                origin=origin,
                reason=reason,
                state_before=state_before,
                state_after=(
                    state_after_value.name
                    if state_after_value is not None
                    else "null"
                ),
            )

        try:
            _t38c_log({"evt": "pc_prefetch_enter", "phase": "entry",
                       "rid": req.rid,
                       "attempt_id": req.hicache_prefetch_active_attempt_id,
                       "origin": origin.name,
                       "l3_enabled": bool(self.enable_hicache_storage)})
        except Exception:
            pass
        if self.enable_hicache_storage:
            req.init_next_round_input(self.tree_cache, cow_mamba=False)
            tree_cache = self.tree_cache
            buffer_mode = self.server_args.hicache_host_memory_mode == "buffer_only"
            last_host_node = req.last_host_node
            # Buffer mode host-backups nothing, so match_prefix anchors at
            # root; re-anchor on the deepest device node. The anchor is only
            # read for hash/extra-key context here (never locked), so a device
            # node serves. Cache mode keeps the is_backuped gate below: its
            # write-through prefix is contiguous from root, so an unbacked
            # anchor means a guaranteed storage miss.
            if (
                buffer_mode
                and tree_cache.is_root(last_host_node)
                and not tree_cache.is_root(req.last_node)
            ):
                last_host_node = req.last_node

            try:
                _t38c_matched_len = len(req.prefix_indices) + req.host_hit_length
                _t38c_match_end = req._compute_max_prefix_len(
                    len(req.full_untruncated_fill_ids)
                )
                _t38c_anchor_hash = tree_cache.get_last_hash_value(last_host_node)
                _t38c_log({"evt": "pc_prefetch_enter", "phase": "gate",
                           "rid": req.rid,
                           "matched_len": _t38c_matched_len,
                           "match_end": _t38c_match_end,
                           "suffix_len": max(0, _t38c_match_end - _t38c_matched_len),
                           "anchor": {
                               "is_root": bool(tree_cache.is_root(last_host_node)),
                               "is_backuped": bool(tree_cache.is_backuped(last_host_node)),
                               "last_hash": _t38c_anchor_hash or "",
                           },
                           "buffer_mode": buffer_mode,
                           "gate_pass": bool(
                               tree_cache.prefetch_gate_ok(
                                   last_host_node, buffer_mode
                               )
                           )})
            except Exception:
                pass

            if tree_cache.prefetch_gate_ok(last_host_node, buffer_mode):
                matched_len = len(req.prefix_indices) + req.host_hit_length
                match_end = req._compute_max_prefix_len(
                    len(req.full_untruncated_fill_ids)
                )
                new_input_tokens = req.full_untruncated_fill_ids[matched_len:match_end]
                prefix_keys = (
                    tree_cache.get_prefix_hash_values(last_host_node)
                    if tree_cache.hicache_storage_pass_prefix_keys
                    else None
                )
                outcome = tree_cache.prefetch_from_storage(
                    req.rid,
                    last_host_node,
                    new_input_tokens,
                    tree_cache.get_last_hash_value(last_host_node),
                    prefix_keys,
                    matched_prefix_tokens=req.full_untruncated_fill_ids[:matched_len],
                    demand_restore=demand_restore,
                    host_alloc_attempt_id=getattr(
                        req, "hicache_host_alloc_attempt_id", None
                    ),
                    prefetch_attempt_id=getattr(
                        req, "hicache_prefetch_active_attempt_id", None
                    ),
                )
                # P2-1 M1b: feed the issue outcome into the restore state
                # machine (T1 issued / T2-T4 declines). declined_too_short
                # only enters WAIT[REVALIDATE] when the prompt can ever
                # qualify for a storage prefetch -- a can-never-qualify
                # decline is terminal (plain recompute), and re-issuing it
                # per pass is the capacity loop.
                if outcome == "issued":
                    self._apply_restore_event(req, RestoreEvent.PREFETCH_ISSUED)
                    return result(HiCachePrefetchIssueStatus.ISSUED, "issued")
                elif outcome == "declined_rate_limited":
                    self._apply_restore_event(req, RestoreEvent.DENIED_RATE)
                elif outcome == "forfeited_alloc_failed":
                    self._apply_restore_event(req, RestoreEvent.DENIED_ALLOC)
                    self._capture_host_alloc_wait(req)
                elif outcome == "revoked_alloc_failed":
                    self._apply_restore_event(req, RestoreEvent.DENIED_ALLOC)
                elif outcome == "declined_too_short":
                    # WAIT[REVALIDATE] is the device-match-decay bet, whose
                    # only re-issue source is the paced retry (step 2 below,
                    # gated on the poll interval). With the poll disabled
                    # (M2 default 0) the wait has no wake path and idles
                    # out the full T13 clock (e13 K=1 t5 60s): the first
                    # decline is then terminal, and the request recomputes
                    # immediately (no restore intent is armed).
                    short_tail = short_tail_recompute_allowed(
                        device_prefix_tokens=len(req.prefix_indices),
                        host_hit_tokens=req.host_hit_length,
                        suffix_tokens=max(0, match_end - matched_len),
                        page_size=self.page_size,
                        prefetch_threshold=tree_cache.prefetch_threshold,
                    )
                    if short_tail:
                        # The L1/L2 prefix is already resident; no storage
                        # event can make the current match longer. Consume
                        # the marker set by prefetch_from_storage so the
                        # paced retry cannot re-enter REVALIDATE, then use
                        # the state machine's immediate tail-admit path.
                        tree_cache.pop_storage_prefetch_miss(req.rid)
                        decision = self._apply_restore_event(
                            req,
                            RestoreEvent.DENIED_SHORT,
                            short_tail_recompute=True,
                        )
                        if decision is RestoreDecision.ADMIT_RECOMPUTE:
                            self._log_restore_recompute(req, "too_short_resident_tail")
                    elif self._restore_potential_for(req) and too_short_wait_armed(
                        get_memory().hicache_storage_prefetch_retry_poll_interval
                    ):
                        self._apply_restore_event(req, RestoreEvent.DENIED_SHORT)
            else:
                # Gate skip: the anchor is not a storage anchor yet. Cache
                # mode registers a frontier wait (M2 T5) and marks
                # WAIT[FRONTIER]; buffer mode reads by hash, never by anchor
                # backup, so a skip there is final and the request recomputes.
                # A prompt too short to ever qualify for a storage prefetch
                # skips the wait too: no restore intent, and the frontier
                # can never turn it into a restore (T13 would only delay the
                # recompute).
                if not buffer_mode and self.tree_cache.prompt_can_qualify_for_prefetch(
                    len(req.full_untruncated_fill_ids), req.host_hit_length
                ):
                    # phase2-peranchor no-material fast-forward: the anchor is
                    # not gate-ok (not root / not L3-durable / not backuped).
                    # If it has NO recoverable material at all AND nothing in
                    # flight can ever make it durable (no pending write ack, no
                    # deferred-ACK descendant for the P3 reconcile, no in-flight
                    # restore), the frontier wait is zero-expectation and would
                    # only idle out the full 60s T13 (the 9d8b5428 shape).
                    # Recompute forward immediately. This is distinct from
                    # prompt_can_qualify_for_prefetch (suffix-geometry): a
                    # candidate can qualify yet still have no material to wait
                    # on. Any in-flight producer / deferred descendant keeps the
                    # normal P3 reconcile + frontier wait path.
                    if self._no_material_fast_forward_for(req, last_host_node):
                        self._log_restore_recompute(req, "no_material")
                        return result(
                            HiCachePrefetchIssueStatus.SKIPPED_STATE,
                            "no_material",
                        )
                    self._apply_restore_event(req, RestoreEvent.GATE_SKIP_FRONTIER)
                    tree_cache.register_frontier_waiter(req.rid, last_host_node)
                    logger.info(
                        "[P2A] ts_ms=%d evt=frontier_wait rid=%s node=%s",
                        int(time.time() * 1000),
                        req.rid,
                        last_host_node,
                    )
                return result(HiCachePrefetchIssueStatus.HELD, "frontier")
            return result(HiCachePrefetchIssueStatus.HELD, outcome)
        return result(HiCachePrefetchIssueStatus.SKIPPED_STATE, "storage_disabled")

    def _host_alloc_snapshot_for_req(self, req):
        cursor = getattr(req, "hicache_host_alloc_wait_cursor", None)
        pools = {"kv"}
        if cursor is not None:
            pools.update(str(pool) for pool in cursor.blocked_domains)
            pools.update(str(pool) for pool in cursor.required_aux_units)
        snapshot_fn = getattr(self.tree_cache, "host_allocability_snapshot", None)
        if snapshot_fn is None:
            return cursor.snapshot if cursor is not None else None
        return snapshot_fn(sorted(pools))

    def _host_alloc_telemetry_identity(self):
        parallel_state = getattr(self, "ps", None)
        return (
            f"scheduler-pid-{os.getpid()}",
            getattr(parallel_state, "tp_rank", os.environ.get("RANK")),
        )

    @staticmethod
    def _host_alloc_trace_context(req):
        context = getattr(req, "trace_context", None)
        if context is None:
            context = getattr(getattr(req, "time_stats", None), "trace_ctx", None)
        if context is None or isinstance(context, (str, int, float, bool, dict, list)):
            return context
        return str(context)

    @staticmethod
    def _host_alloc_generation_vector_id(vector) -> Optional[str]:
        if vector is None:
            return None
        instance_id, generations = vector
        return f"{instance_id}:" + ",".join(
            f"{pool}={generation}" for pool, generation in generations
        )

    def _host_alloc_wait_eligible(self, req) -> bool:
        cursor = getattr(req, "hicache_host_alloc_wait_cursor", None)
        if cursor is None:
            return False
        current = self._host_alloc_snapshot_for_req(req)
        if current is None or current.cache_instance_id != cursor.snapshot.cache_instance_id:
            return False
        return all(
            current.generation_by_pool.get(pool, 0)
            > cursor.snapshot.generation_by_pool.get(pool, 0)
            for pool in cursor.blocked_domains
        )

    def _host_alloc_generation_vector_for_req(self, req):
        cursor = req.hicache_host_alloc_wait_cursor
        current = self._host_alloc_snapshot_for_req(req)
        return (
            current.cache_instance_id,
            tuple(
                sorted(
                    (str(pool), current.generation_by_pool.get(pool, 0))
                    for pool in cursor.blocked_domains
                )
            ),
        )

    def _host_alloc_global_generation_vector(self):
        snapshot_fn = getattr(self.tree_cache, "host_allocability_snapshot", None)
        if snapshot_fn is None:
            return None
        return snapshot_fn().generation_vector()

    def _host_alloc_global_snapshot(self):
        snapshot_fn = getattr(self.tree_cache, "host_allocability_snapshot", None)
        return snapshot_fn() if snapshot_fn is not None else None

    def _capture_host_alloc_wait(
        self, req, failure: Optional[HostAllocFailure] = None
    ) -> None:
        if failure is None:
            pop_failure = getattr(self.tree_cache, "pop_host_alloc_failure", None)
            failure = pop_failure(req.rid) if pop_failure is not None else None
        if failure is None:
            snapshot = self._host_alloc_snapshot_for_req(req)
            if snapshot is None:
                return
            failure = HostAllocFailure(
                requested_primary_tokens=0,
                required_aux_units={},
                failed_domains=frozenset({"kv"}),
                positive_hit_tokens=0,
                sidecar_hit_pages={},
                allocability_snapshot=snapshot,
            )
        if not hasattr(self, "_host_alloc_wake_arbiter"):
            self._host_alloc_wake_arbiter = HostAllocWakeArbiter()
        arbiter = self._host_alloc_wake_arbiter
        if getattr(req, "hicache_host_alloc_attempt_id", None) is not None:
            req.hicache_host_alloc_last_attempt_id = req.hicache_host_alloc_attempt_id
            attempt_snapshot = self._host_alloc_global_snapshot()
            sequence = arbiter.record_attempt_result(
                req.rid,
                attempt_snapshot or failure.allocability_snapshot,
            )
            req.hicache_host_alloc_attempt_id = None
        else:
            sequence = arbiter.enqueue(req.rid)
        req.hicache_host_alloc_wait_cursor = HostAllocWaitCursor(
            snapshot=failure.allocability_snapshot,
            blocked_domains=failure.failed_domains or frozenset({"kv"}),
            requested_primary_tokens=failure.requested_primary_tokens,
            required_aux_units=failure.required_aux_units,
            fifo_sequence=sequence,
        )
        worker, rank = self._host_alloc_telemetry_identity()
        wait_started_mono_ns = int(
            getattr(req, "hicache_restore_state_ts", time.perf_counter()) * 1e9
        )
        timeout_s = getattr(
            getattr(self, "server_args", None),
            "hicache_restore_wait_timeout_s",
            0,
        )
        deadline_mono_ns = (
            wait_started_mono_ns + int(timeout_s * 1e9) if timeout_s > 0 else None
        )
        _log_host_alloc_telemetry(
            "restore_host_alloc_wait",
            worker=worker,
            rank=rank,
            rid=req.rid,
            attempt_id=getattr(req, "hicache_host_alloc_last_attempt_id", None),
            cache_instance_id=failure.allocability_snapshot.cache_instance_id,
            trace_context=self._host_alloc_trace_context(req),
            state="WAIT_CAPACITY",
            reason="HOST_ALLOC",
            positive_hit_tokens=int(failure.positive_hit_tokens),
            sidecar_hit_pages=dict(failure.sidecar_hit_pages),
            requested_primary_tokens=int(failure.requested_primary_tokens),
            required_aux_units=dict(failure.required_aux_units),
            blocked_domains=sorted(map(str, failure.failed_domains)),
            captured_generations=dict(failure.allocability_snapshot.generation_by_pool),
            current_generations=dict(failure.allocability_snapshot.generation_by_pool),
            free_units=dict(failure.allocability_snapshot.free_units_by_pool),
            evictable_units=dict(failure.allocability_snapshot.evictable_units_by_pool),
            prefetch_reservation_held=False,
            fifo_sequence=sequence,
            wait_started_mono_ns=wait_started_mono_ns,
            deadline_mono_ns=deadline_mono_ns,
            retry_grant=False,
            retry_skip=False,
            retry_outcome="parked",
        )

    def _remove_host_alloc_waiter(self, rid: str) -> None:
        arbiter = getattr(self, "_host_alloc_wake_arbiter", None)
        if arbiter is not None:
            arbiter.remove(rid)

    def _select_host_alloc_waiter(self) -> Optional[str]:
        if not hasattr(self, "_host_alloc_wake_arbiter"):
            self._host_alloc_wake_arbiter = HostAllocWakeArbiter()
        arbiter = self._host_alloc_wake_arbiter
        requests = {req.rid: req for req in self.waiting_queue}
        for rid in arbiter.ordered_rids():
            req = requests.get(rid)
            if req is None or req.hicache_restore_state is not RestoreState.WAIT_CAPACITY:
                self._remove_host_alloc_waiter(rid)
        if not requests:
            return None
        controller = getattr(self.tree_cache, "cache_controller", None)
        if controller is None or controller.prefetch_rate_limited():
            return None
        timeout_s = self.server_args.hicache_restore_wait_timeout_s
        now = time.perf_counter()
        return arbiter.choose(
            lambda rid: (
                requests[rid].hicache_restore_wait_reason is RestoreWaitReason.HOST_ALLOC
                and self._host_alloc_wait_eligible(requests[rid])
                and (
                    timeout_s <= 0
                    or now
                    - getattr(requests[rid], "hicache_restore_state_ts", now)
                    <= timeout_s
                )
            ),
            lambda rid: self._host_alloc_global_generation_vector()
            or self._host_alloc_generation_vector_for_req(requests[rid]),
        )

    def _host_alloc_skip_decision(self, req) -> str:
        controller = getattr(self.tree_cache, "cache_controller", None)
        if controller is None or controller.prefetch_rate_limited():
            return "hold_budget"
        if not self._host_alloc_wait_eligible(req):
            return "hold_no_generation"
        return "hold_global_grant_used"

    def _reconcile_restore_states(self):
        """Per-pass restore-state reconciliation (P2-1 M1b/M2; evolved from
        _retry_missed_storage_prefetches). Feeds terminal prefetch outcomes
        into the request state machine (T8 finalize / T9 miss revoke / T10
        terminated revoke), consumes M2 frontier wakes (T12), re-issues
        prefetches for WAIT requests whose capacity predicate now passes
        (T11), and degrades timed-out waits to recompute (T13)."""
        if not self.waiting_queue:
            arbiter = getattr(self, "_host_alloc_wake_arbiter", None)
            for rid in arbiter.ordered_rids() if arbiter is not None else ():
                self._remove_host_alloc_waiter(rid)
            return

        # 1) Terminal outcomes recorded by the drain this pass (same thread).
        for req in self.waiting_queue:
            self._feed_restore_terminal(req)

        # 2) Legacy paced retry (REVALIDATE fallback when interval > 0).
        interval = get_memory().hicache_storage_prefetch_retry_poll_interval
        if interval > 0:
            max_attempts = get_memory().hicache_storage_prefetch_retry_max_attempts
            for req in self.waiting_queue:
                if self.tree_cache.pop_storage_prefetch_miss(req.rid):
                    req.storage_prefetch_retry_pending = True
                    req.storage_prefetch_retry_wait_polls = 0
                if (
                    not req.storage_prefetch_retry_pending
                    or req.storage_prefetch_retry_attempts >= max_attempts
                ):
                    continue
                req.storage_prefetch_retry_wait_polls += 1
                if req.storage_prefetch_retry_wait_polls <= interval:
                    continue
                req.storage_prefetch_retry_pending = False
                req.storage_prefetch_retry_attempts += 1
                logger.debug(
                    "HiCache storage prefetch retry req=%s attempt=%d",
                    req.rid,
                    req.storage_prefetch_retry_attempts,
                )
                self._prefetch_kvcache(req, origin=HiCachePrefetchOrigin.DEMAND_RETRY)

        # 3) M2: frontier-ACK wakes (T12). The ack drain moved the waiter
        # into the ready set earlier in this same event pass.
        for req in self.waiting_queue:
            if not self.tree_cache.pop_frontier_ready(req.rid):
                continue
            if req.hicache_restore_state is not RestoreState.WAIT_CAPACITY:
                self.tree_cache.discard_frontier_waiter(req.rid)
                continue  # state changed since the wake (e.g. timed out)
            was_backup_pending = (
                req.hicache_restore_wait_reason is RestoreWaitReason.BACKUP_PENDING
            )
            if was_backup_pending and not self._restore_backup_wake_ready(req):
                # A T12 wake for a still-parked backup wait: the chain's
                # durable frontier has not crossed the request's end (or
                # the demand ticket pool is full). Consume the wake and
                # hold the re-issue -- the per-pass T11 predicate re-checks
                # the frontier, so the request is not lost, and the parked
                # span stays armed.
                continue
            self.tree_cache.discard_frontier_waiter(req.rid)
            decision = self._apply_restore_event(req, RestoreEvent.FRONTIER_READY)
            if decision is RestoreDecision.RETRY_PREFETCH:
                logger.info(
                    "[P2A] ts_ms=%d evt=restore_retry rid=%s cause=frontier",
                    int(time.time() * 1000),
                    req.rid,
                )
                self._prefetch_kvcache(
                    req,
                    origin=HiCachePrefetchOrigin.DEMAND_RETRY,
                    demand_restore=self.enable_ready_horizon or was_backup_pending,
                )
                if req.hicache_restore_state is RestoreState.NONE:
                    # The wake re-issue was declined too-short: terminal
                    # (T4 on the re-issue leg), released to recompute now
                    # instead of idling out the T13 clock.
                    self._log_restore_recompute(req, "too_short")

        # 4) M1: WAIT timeout (T13) and per-pass capacity wakes (T11).
        timeout_s = self.server_args.hicache_restore_wait_timeout_s
        now = time.perf_counter()
        if not hasattr(self, "_host_alloc_attempt_seq"):
            self._host_alloc_attempt_seq = 0
        host_alloc_grant = self._select_host_alloc_waiter()
        for req in self.waiting_queue:
            if req.hicache_restore_state is not RestoreState.WAIT_CAPACITY:
                continue
            if timeout_s > 0 and now - req.hicache_restore_state_ts > timeout_s:
                self.tree_cache.discard_frontier_waiter(req.rid)
                decision = self._apply_restore_event(req, RestoreEvent.TIMEOUT)
                if decision is RestoreDecision.ADMIT_RECOMPUTE:
                    self._log_restore_recompute(req, "timeout")
                continue
            if not capacity_wake_applies(req.hicache_restore_wait_reason):
                # REVALIDATE is not testable by the capacity predicate:
                # re-issuing would be declined identically every pass. It
                # leaves only via the paced retry or the T13 timeout.
                continue
            if req.hicache_restore_wait_reason is RestoreWaitReason.HOST_ALLOC:
                worker, rank = self._host_alloc_telemetry_identity()
                cursor = getattr(req, "hicache_host_alloc_wait_cursor", None)
                current = self._host_alloc_snapshot_for_req(req)
                current_generations = (
                    dict(current.generation_by_pool) if current is not None else {}
                )
                captured_generations = (
                    dict(cursor.snapshot.generation_by_pool) if cursor else {}
                )
                vector = (
                    current.generation_vector() if current is not None else None
                )
                if req.rid != host_alloc_grant:
                    decision_name = self._host_alloc_skip_decision(req)
                    _log_host_alloc_telemetry(
                        "restore_host_alloc_wake_decision",
                        worker=worker,
                        rank=rank,
                        rid=req.rid,
                        attempt_id=getattr(
                            req, "hicache_host_alloc_attempt_id", None
                        ),
                        cache_instance_id=(
                            current.cache_instance_id if current is not None else None
                        ),
                        trace_context=self._host_alloc_trace_context(req),
                        decision=decision_name,
                        captured_generations=captured_generations,
                        current_generations=current_generations,
                        blocked_domains=sorted(
                            map(str, cursor.blocked_domains)
                        )
                        if cursor
                        else [],
                        required_aux_units=(
                            dict(cursor.required_aux_units) if cursor else {}
                        ),
                        requested_primary_tokens=(
                            int(cursor.requested_primary_tokens) if cursor else 0
                        ),
                        fifo_sequence=cursor.fifo_sequence if cursor else None,
                        generation_vector_id=self._host_alloc_generation_vector_id(
                            vector
                        ),
                        global_grant_used=decision_name == "hold_global_grant_used",
                        budget_available=decision_name != "hold_budget",
                        free_units=(
                            dict(current.free_units_by_pool) if current is not None else {}
                        ),
                        evictable_units=(
                            dict(current.evictable_units_by_pool)
                            if current is not None
                            else {}
                        ),
                        retry_grant=False,
                        retry_skip=decision_name != "grant",
                        retry_outcome=decision_name,
                    )
                    continue
                _log_host_alloc_telemetry(
                    "restore_host_alloc_wake_decision",
                    worker=worker,
                    rank=rank,
                    rid=req.rid,
                    attempt_id=getattr(req, "hicache_host_alloc_attempt_id", None),
                    cache_instance_id=(
                        current.cache_instance_id if current is not None else None
                    ),
                    trace_context=self._host_alloc_trace_context(req),
                    decision="grant",
                    captured_generations=captured_generations,
                    current_generations=current_generations,
                    blocked_domains=sorted(map(str, cursor.blocked_domains))
                    if cursor
                    else [],
                    required_aux_units=(
                        dict(cursor.required_aux_units) if cursor else {}
                    ),
                    requested_primary_tokens=(
                        int(cursor.requested_primary_tokens) if cursor else 0
                    ),
                    fifo_sequence=cursor.fifo_sequence if cursor else None,
                    generation_vector_id=self._host_alloc_generation_vector_id(vector),
                    global_grant_used=True,
                    budget_available=True,
                    free_units=(
                        dict(current.free_units_by_pool) if current is not None else {}
                    ),
                    evictable_units=(
                        dict(current.evictable_units_by_pool)
                        if current is not None
                        else {}
                    ),
                    retry_grant=True,
                    retry_skip=False,
                    retry_outcome="grant",
                )
            if not self._restore_wait_capacity_fits(req):
                continue
            # Captured before _apply_restore_event clears the reason: a
            # BACKUP_PENDING wake re-issues with its DEMAND_RESTORE ticket
            # (past the speculative PREFETCH_BUDGET only).
            was_backup_pending = (
                req.hicache_restore_wait_reason is RestoreWaitReason.BACKUP_PENDING
            )
            if req.hicache_restore_wait_reason in (
                RestoreWaitReason.FRONTIER,
                RestoreWaitReason.BACKUP_PENDING,
            ):
                self.tree_cache.discard_frontier_waiter(req.rid)
            decision = self._apply_restore_event(
                req, RestoreEvent.CAPACITY_FITS, capacity_fits=True
            )
            if decision is RestoreDecision.RETRY_PREFETCH:
                self._host_alloc_attempt_seq += 1
                req.hicache_host_alloc_attempt_id = (
                    f"{req.rid}:{self._host_alloc_attempt_seq}"
                )
                req.hicache_host_alloc_attempt_snapshot = (
                    self._host_alloc_snapshot_for_req(req)
                )
                logger.info(
                    "[P2A] ts_ms=%d evt=restore_retry rid=%s cause=capacity attempt_id=%s",
                    int(time.time() * 1000),
                    req.rid,
                    req.hicache_host_alloc_attempt_id,
                )
                self._prefetch_kvcache(
                    req,
                    origin=HiCachePrefetchOrigin.DEMAND_RETRY,
                    demand_restore=self.enable_ready_horizon or was_backup_pending,
                )
                if req.hicache_restore_state is RestoreState.NONE:
                    # Same terminal rule as the T12 wake leg: a capacity
                    # wake whose re-issued prefetch is declined too-short
                    # releases the request to recompute immediately.
                    self._log_restore_recompute(req, "too_short")

    def _feed_restore_terminal(self, req) -> None:
        """Consume a terminal prefetch outcome (finalize T8 / revoke T9/T10)
        recorded by the drain into the request's restore state machine."""
        terminal = self.tree_cache.pop_storage_prefetch_terminal(req.rid)
        if terminal is None:
            return
        if isinstance(terminal, tuple):
            terminal_attempt_id, outcome = terminal
        else:
            # Legacy test doubles may still provide an uncorrelated outcome.
            # Real cache terminals always carry the attempt ID.
            terminal_attempt_id, outcome = None, terminal
        active_attempt_id = getattr(req, "hicache_prefetch_active_attempt_id", None)
        if terminal_attempt_id is not None and terminal_attempt_id != active_attempt_id:
            logger.warning(
                "[P3] evt=prefetch_terminal_stale rid=%s terminal_attempt_id=%s active_attempt_id=%s",
                req.rid,
                terminal_attempt_id,
                active_attempt_id,
            )
            return
        if outcome == "finalized":
            event, genuine_miss = RestoreEvent.FINALIZED, False
        elif outcome == "revoked_terminated":
            event, genuine_miss = RestoreEvent.REVOKED_TERMINATED, False
        elif outcome == "revoked_backup_pending":
            event, genuine_miss = RestoreEvent.BACKUP_PENDING, False
        elif outcome == "revoked_alloc_failed":
            event, genuine_miss = RestoreEvent.DENIED_ALLOC, False
        else:  # "revoked_miss"
            event, genuine_miss = RestoreEvent.REVOKED_MISS, True
        if event is RestoreEvent.REVOKED_MISS and genuine_miss:
            # P1 sticky-miss evidence (phase2-peranchor): record the ANCHOR's
            # per-anchor storage_version at which this request's prefix was
            # proven L3-missing, plus the anchor node and the identity
            # (session generation). The admission re-arm (T6) refuses to
            # re-enter WAIT while that SAME anchor's version is unchanged and
            # the generation matches -- the same-probe restore churn gate.
            # Only THIS anchor's substantive durability change (or a
            # generation/prefix/anchor change) overrides the miss: an
            # unrelated chain's write ack bumps only the global diagnostic
            # counter and never re-arms. `anchor` is the deepest durable
            # ancestor the miss probe covered (the request's last_host_node /
            # the restore target anchor it was revoked on); `anchor_version`
            # is defensive when the anchor is gone (self-heal to re-match).
            anchor = getattr(req, "last_host_node", None)
            req.hicache_restore_miss_epoch = self._anchor_version_or_zero(anchor)
            req.hicache_restore_miss_anchor = anchor
            req.hicache_restore_miss_generation = getattr(
                req, "session_generation", None
            )
        failure = (
            self.tree_cache.pop_host_alloc_failure(req.rid)
            if event is RestoreEvent.DENIED_ALLOC
            else None
        )
        restore_state_before = self._prefetch_state_name(
            getattr(req, "hicache_restore_state", None)
        )
        attempt_id = getattr(req, "hicache_prefetch_active_attempt_id", None)
        attempt_origin = getattr(req, "hicache_prefetch_active_origin", None)
        self._apply_restore_event(req, event, genuine_miss=genuine_miss)
        if event is RestoreEvent.DENIED_ALLOC:
            self._capture_host_alloc_wait(req, failure)
        if terminal_attempt_id is not None:
            self._release_prefetch_claim(
                req, terminal_attempt_id, outcome
            )
        if event is RestoreEvent.FINALIZED:
            last_origin = getattr(req, "hicache_prefetch_last_origin", None)
            staged_tokens = getattr(
                self.tree_cache, "peek_prefetch_loaded_tokens", lambda _rid: None
            )(req.rid)
            completion = getattr(
                self.tree_cache,
                "pop_storage_prefetch_completion",
                lambda _rid: None,
            )(req.rid) or {}
            logger.info(
                "[P3] ts_ns=%d evt=ready_host schema=rh_ready_host.v1 rid=%s "
                "attempt_id=%s issue_origin=%s completed_kv_tokens=%s "
                "required_aux_pools=%s completed_aux_units=%s "
                "restore_state_before=%s restore_state_after=%s "
                "finalize_result=%s ready_monotonic_ns=%d",
                time.monotonic_ns(),
                req.rid,
                attempt_id
                or getattr(req, "hicache_prefetch_last_attempt_id", None),
                (attempt_origin or last_origin).name
                if (attempt_origin or last_origin) is not None
                else "null",
                completion.get("completed_kv_tokens", staged_tokens),
                completion.get("required_aux_pools"),
                completion.get("completed_aux_units"),
                restore_state_before,
                req.hicache_restore_state.name
                if req.hicache_restore_state is not None
                else "null",
                completion.get("finalize_result", "null"),
                time.monotonic_ns(),
            )
        if (
            event is RestoreEvent.REVOKED_MISS
            and genuine_miss
            and self.enable_ready_horizon
        ):
            # P3 M3 (user adjudication) + phase2-peranchor: a deterministic
            # miss means the full requested prefix is not in L3. The ready
            # horizon records the NO_L3 negative-cache park keyed on the
            # ANCHOR's per-anchor storage_version (not the global l3_publish
            # diagnostic counter) so this NONE request is not re-probed next
            # pass -- the miss is not transient and its revoke just released
            # the budget (the e7 spin arm). Only THAT anchor's substantive
            # durability change, an identity change (prefix/generation/anchor),
            # or the fuse expiry clears it; an unrelated chain's write ack
            # does not.
            anchor = getattr(req, "last_host_node", None)
            self._ready_horizon_negatives[req.rid] = NegativeCacheEntry(
                reason=DeclineReason.NO_L3,
                epoch_cursor=self._anchor_version_or_zero(anchor),
                fuse_expiry=time.perf_counter()
                + self.ready_horizon.safety_fuse_s,
                prefix_len=(
                    len(req.full_untruncated_fill_ids)
                    if req.full_untruncated_fill_ids is not None
                    else 0
                ),
                generation=getattr(req, "session_generation", None),
                anchor=anchor,
            )
        if event is RestoreEvent.BACKUP_PENDING:
            # The lookup found the chain mid-backup: park on the M2 frontier
            # wait, keyed by the anchor (the parked span is stored in the
            # cache at the revoke). Registering also requests the chain's
            # persistence (write_backup_storage), so the wait is
            # self-arming; the per-pass wake predicate (_restore_backup_wake_ready
            # -- durable frontier crossed the request end plus a free
            # DEMAND_RESTORE ticket) then wakes the request for one
            # re-lookup into the full chain instead of the per-pass
            # re-issue loop. Bounded by the T13 timeout.
            if (
                req.hicache_restore_state is RestoreState.WAIT_CAPACITY
                and req.last_host_node is not None
            ):
                self.tree_cache.register_frontier_waiter(
                    req.rid, req.last_host_node
                )
        if event is RestoreEvent.REVOKED_MISS:
            self._log_restore_recompute(req, "miss")
        elif req.hicache_restore_state is RestoreState.READY:
            logger.info(
                "[P2A] ts_ms=%d evt=restore_ready rid=%s",
                int(time.time() * 1000),
                req.rid,
            )

    def _final_storage_survivability(self, req) -> str:
        """[P3] Coarse storage-survivability label at a recompute release:
        which tier still holds part of the request's KV once it falls back
        to recompute. L3 durability (written+acked or restored) or a partial
        host-tree prefix survives; a full-tree miss leaves none. Drives the
        16-way NEVER_BACKED differential (NEVER / PARTIAL / FULL_THEN_LOST /
        Z3 / recycle / other)."""
        tc = self.tree_cache
        anchor = getattr(req, "last_host_node", None)
        if anchor is not None and tc.node_exists(anchor):
            if tc.is_l3_durable(anchor):
                return "l3"
            return "host"
        return "none"

    def _log_restore_recompute(self, req, cause) -> None:
        logger.info(
            "[P2A] ts_ms=%d evt=restore_recompute rid=%s cause=%s "
            "final_storage_survivability=%s",
            int(time.time() * 1000),
            req.rid,
            cause,
            self._final_storage_survivability(req),
        )

    def _apply_restore_event(
        self,
        req,
        event,
        *,
        capacity_fits: bool = False,
        genuine_miss: bool = False,
        rearm_allowed: bool = True,
        short_tail_recompute: bool = False,
    ) -> RestoreDecision:
        """Feed a restore event into the request's state machine and apply
        the transition (Req fields only; the decision is returned for the
        caller to execute). Scheduler thread only -- the drain, the
        reconciliation and the admission loop all run on it, so there is no
        concurrent write."""
        prev_state = req.hicache_restore_state
        next_state, decision = next_restore(
            req.hicache_restore_state,
            event,
            capacity_fits=capacity_fits,
            genuine_miss=genuine_miss,
            rearm_allowed=rearm_allowed,
            short_tail_recompute=short_tail_recompute,
        )
        if next_state is req.hicache_restore_state and decision is RestoreDecision.NONE:
            return decision
        if (
            prev_state is RestoreState.WAIT_CAPACITY
            and req.hicache_restore_wait_reason is RestoreWaitReason.HOST_ALLOC
        ):
            if not (
                next_state is RestoreState.WAIT_CAPACITY
                and wait_reason_for(event, genuine_miss=genuine_miss)
                is RestoreWaitReason.HOST_ALLOC
            ):
                self._remove_host_alloc_waiter(req.rid)
                req.hicache_host_alloc_wait_cursor = None
        req.hicache_restore_state = next_state
        if next_state is RestoreState.WAIT_CAPACITY:
            req.hicache_restore_wait_reason = wait_reason_for(
                event, genuine_miss=genuine_miss
            )
        else:
            req.hicache_restore_wait_reason = None
        if next_state is not RestoreState.MISS_RECOMPUTE:
            # P1: leaving the sticky-miss state (a re-arm override, an
            # abort, a forward READY, or a re-issued restore) drops the
            # negative evidence -- the miss no longer binds the request.
            req.hicache_restore_miss_epoch = None
            req.hicache_restore_miss_generation = None
            req.hicache_restore_miss_anchor = None
        # The wait clock is armed at the first WAIT entry of the episode and
        # never re-armed by a re-decline: re-arming was what let the
        # capacity loop evade the T13 timeout (state_ts reset every pass).
        req.hicache_restore_state_ts = wait_clock_next(
            prev_state, next_state, req.hicache_restore_state_ts, time.perf_counter()
        )
        logger.info(
            "[P2A] ts_ms=%d evt=restore_state rid=%s state=%s reason=%s",
            int(time.time() * 1000),
            req.rid,
            next_state.name,
            req.hicache_restore_wait_reason.name
            if req.hicache_restore_wait_reason is not None
            else "none",
        )
        return decision

    def _emit_rh_decision(
        self,
        view,
        *,
        rank,
        frontier_n,
        decision,
        reason,
        epochs,
        headroom,
        reserve_floor,
        physical_limit,
        physical_used,
        speculative_limit,
        speculative_used,
        negative_entry,
        issue_origin,
        attempt_id,
        force=False,
    ) -> None:
        req = view.req
        field = lambda value: "null" if value is None else value
        state_before = self._prefetch_state_name(view.state)
        wait_reason = view.wait_reason.name if view.wait_reason is not None else None
        fingerprint = (
            rank,
            frontier_n,
            state_before,
            wait_reason,
            bool(view.staging_eligible),
            negative_entry.reason.name if negative_entry is not None else None,
            negative_entry.epoch_cursor if negative_entry is not None else None,
            (
                epochs.l3_publish,
                epochs.host_headroom,
                epochs.host_release,
                epochs.spec_budget,
                epochs.waiting_frontier,
            ),
            headroom,
            reserve_floor,
            physical_limit,
            physical_used,
            speculative_limit,
            speculative_used,
            decision,
            reason,
        )
        previous = getattr(req, "hicache_last_rh_decision_fingerprint", None)
        if not force and previous == fingerprint:
            return
        pass_seq = getattr(self, "_rh_pass_seq", 0)
        decision_id = f"{req.rid}:rh:{pass_seq}"
        req.hicache_last_rh_decision_id = decision_id
        req.hicache_last_rh_decision_fingerprint = fingerprint
        logger.info(
            "[P3] ts_ns=%d evt=rh_preadmission_decision schema=rh_preadmission.v1 "
            "rid=%s request_enqueue_seq=%s rh_pass_seq=%d decision_id=%s "
            "fingerprint=%s frontier_rank=%d frontier_n=%d "
            "restore_state_before=%s wait_reason_before=%s "
            "active_prefetch_attempt_id=%s staging_eligible=%s "
            "restore_potential=%s negative_cache_blocked=%s negative_cursor=%s "
            "causal_epoch=%s headroom_tokens=%s reserve_floor_tokens=%s "
            "physical_budget_limit_tokens=%s physical_budget_used_tokens=%s "
            "speculative_budget_limit_tokens=%s speculative_budget_used_tokens=%s "
            "decision=%s reason=%s issue_origin=%s attempt_id=%s",
            time.monotonic_ns(),
            req.rid,
            field(getattr(req, "hicache_request_enqueue_seq", None)),
            pass_seq,
            decision_id,
            repr(fingerprint)[:160],
            rank,
            frontier_n,
            state_before,
            wait_reason or "null",
            field(getattr(req, "hicache_prefetch_active_attempt_id", None)),
            bool(view.staging_eligible),
            bool(view.staging_eligible),
            negative_entry is not None,
            field(negative_entry.epoch_cursor if negative_entry is not None else None),
            repr(epochs),
            headroom,
            reserve_floor,
            field(physical_limit),
            field(physical_used),
            field(speculative_limit),
            field(speculative_used),
            decision,
            reason,
            issue_origin.name if issue_origin is not None else "null",
            field(attempt_id),
        )

    def _ready_horizon_pass(self) -> None:
        """P3 Ready Horizon v0 (3.2): maintain the READY_HOST pool.

        Runs after _reconcile_restore_states each prefill pass. The refill
        check is event-driven (M3, user adjudication): it runs only on a
        causal-epoch event -- L3 durable/publish advanced, host pages
        released, speculative budget released, or the frontier composition
        changed -- or the low-frequency safety reconciliation, never at
        pass rate (e7: the non-directional signature self-sustained a miss
        issue->revoke spin at ~141/s). Each staging issue delegates to
        _prefetch_kvcache; a decline parks the rid in the causal
        negative-cache (its subscribed epoch's cursor), so the rid is not
        re-eligible until that epoch advances (or identity changes). The
        refill's own traffic is not an event. Speculative staging never
        evicts (M2): headroom or budget exhaustion declines silently."""
        if not self.enable_ready_horizon:
            return
        self._rh_pass_seq = getattr(self, "_rh_pass_seq", 0) + 1
        cc = self.tree_cache.cache_controller
        if cc is None:
            return
        policy = self.ready_horizon
        frontier_reqs = policy.frontier(self.waiting_queue)
        views = self._ready_horizon_views(frontier_reqs)
        now = time.perf_counter()
        epochs = self._ready_horizon_epochs(frontier_reqs, views, cc)
        event = policy.epoch_event(self._ready_horizon_epoch_prev, epochs)
        # The snapshot tracks the previous pass, not the last check: a
        # release that merely returns a counter to its pre-issue value
        # must still be visible as an event (the e7 spin's second leg).
        self._ready_horizon_epoch_prev = epochs
        if not policy.should_refill(
            event=event,
            last_refill_ts=self._ready_horizon_last_refill_ts,
            now=now,
        ):
            return
        self._ready_horizon_last_refill_ts = now

        frontier_rids = {r.rid for r in frontier_reqs}
        self._ready_horizon_negatives = {
            rid: entry
            for rid, entry in self._ready_horizon_negatives.items()
            if rid in frontier_rids
        }
        headroom = self._ready_host_headroom(cc, views)
        plan = policy.refill_plan(
            views,
            tree=self.tree_cache,
            cc=cc,
            host_headroom=headroom,
            negatives=self._ready_horizon_negatives,
            epochs=epochs,
            now=now,
            reserve_floor=self._ready_reserve_floor_tokens(cc),
        )
        decline_reasons = dict(plan.declines)
        issue_rids = {view.rid for view in plan.to_issue}
        candidate_rids = {view.rid for view in plan.candidates}
        reserve_floor = self._ready_reserve_floor_tokens(cc)
        physical_limit = getattr(cc, "prefetch_capacity_limit", None)
        physical_used = getattr(cc, "prefetch_tokens_occupied", None)
        speculative_limit = getattr(
            cc, "prefetch_speculative_capacity_limit", None
        )
        speculative_used = getattr(cc, "inflight_speculative_tokens", None)
        for rank, view in enumerate(frontier_reqs, start=1):
            entry = self._ready_horizon_negatives.get(view.rid)
            if view.rid in issue_rids:
                decision, reason = "issue", "issued"
            elif view.rid in decline_reasons:
                decision, reason = "hold", "reserve_floor"
            elif entry is not None:
                decision, reason = "exclude", "negative_cache"
            elif not view.staging_eligible:
                decision, reason = "exclude", "no_restore_potential"
            elif view.state not in (
                RestoreState.NONE,
                RestoreState.MISS_RECOMPUTE,
                RestoreState.WAIT_CAPACITY,
            ):
                decision, reason = "exclude", "state_funnel"
            elif cc.prefetch_rate_limited():
                decision, reason = "hold", "physical_budget"
            elif cc.prefetch_speculative_rate_limited():
                decision, reason = "hold", "speculative_budget"
            elif view.rid not in candidate_rids:
                decision, reason = "hold", "outside_watermark"
            else:
                decision, reason = "hold", "state_funnel"
            self._emit_rh_decision(
                view,
                rank=rank,
                frontier_n=len(frontier_reqs),
                decision=decision,
                reason=reason,
                epochs=epochs,
                headroom=headroom,
                reserve_floor=reserve_floor,
                physical_limit=physical_limit,
                physical_used=physical_used,
                speculative_limit=speculative_limit,
                speculative_used=speculative_used,
                negative_entry=entry,
                issue_origin=(
                    HiCachePrefetchOrigin.READY_HORIZON
                    if decision == "issue"
                    else None
                ),
                attempt_id=(
                    getattr(view.req, "hicache_prefetch_active_attempt_id", None)
                    if decision == "issue"
                    else None
                ),
                force=decision == "issue",
            )
        # Record the headroom-gate declines (NO_HEADROOM): none of these
        # can stage until host pages free.
        for rid, reason in plan.declines:
            view = self._ready_horizon_view_for(views, rid)
            if view is not None:
                self._park_ready_decline(rid, view, reason, epochs, now)
        for view in plan.to_issue:
            req = view.req
            result = self._prefetch_kvcache(
                req, origin=HiCachePrefetchOrigin.READY_HORIZON
            )
            state = req.hicache_restore_state
            result_status = (
                result.status
                if isinstance(result, PrefetchIssueResult)
                else result
            )
            issued = result_status is HiCachePrefetchIssueStatus.ISSUED
            result_name = (
                result_status.name.lower()
                if isinstance(result_status, HiCachePrefetchIssueStatus)
                else "issued" if issued else "declined"
            )
            logger.info(
                "[P3] ts_ns=%d evt=ready_stage schema=rh_stage.v2 rid=%s "
                "decision_id=%s attempt_id=%s issue_origin=%s demand_restore=%s "
                "restore_state_before=%s restore_state_after=%s result=%s "
                "reason=%s frontier_rank=%d headroom_tokens=%s "
                "reserve_floor_tokens=%s physical_budget_used_tokens=%s "
                "speculative_budget_used_tokens=%s",
                time.monotonic_ns(),
                req.rid,
                getattr(req, "hicache_last_rh_decision_id", None),
                (
                    result.attempt_id
                    if isinstance(result, PrefetchIssueResult)
                    else getattr(req, "hicache_prefetch_active_attempt_id", None)
                    or getattr(req, "hicache_prefetch_last_attempt_id", None)
                ),
                HiCachePrefetchOrigin.READY_HORIZON.name,
                False,
                result.state_before if isinstance(result, PrefetchIssueResult) else "null",
                result.state_after if isinstance(result, PrefetchIssueResult) else (
                    state.name if state is not None else "null"
                ),
                result_name,
                result.reason if isinstance(result, PrefetchIssueResult) else "issued" if issued else "declined",
                next((i for i, candidate in enumerate(frontier_reqs, 1) if candidate.rid == req.rid), 0),
                headroom,
                reserve_floor,
                physical_used,
                speculative_used,
            )
            if not issued:
                # A synchronous decline: the horizon cannot stage this rid
                # until the causal epoch that resolves the decline
                # advances. The budget rate-limit is the testable one.
                if cc.prefetch_rate_limited() or cc.prefetch_speculative_rate_limited():
                    self._park_ready_decline(
                        req.rid, view, DeclineReason.SPEC_BUDGET, epochs, now
                    )
            elif cc.prefetch_rate_limited() or cc.prefetch_speculative_rate_limited():
                # The issue just exhausted an inflight budget: every
                # remaining candidate would decline identically (the e7
                # attempt-only spinner class), so park the un-tried tail
                # (SPEC_BUDGET) until a budget-release epoch.
                for rest in plan.candidates:
                    if rest.rid in plan.to_issue or rest.rid == req.rid:
                        continue
                    self._park_ready_decline(
                        rest.rid, rest, DeclineReason.SPEC_BUDGET, epochs, now
                    )
                break

        if (plan.ready_count, plan.ready_tokens) != self._ready_horizon_last_log:
            logger.info(
                "[P3] ts_ms=%d evt=ready_pool size=%d tokens=%d watermark=[%s]",
                int(time.time() * 1000),
                plan.ready_count,
                plan.ready_tokens,
                policy.describe_watermarks(),
            )
            self._ready_horizon_last_log = (plan.ready_count, plan.ready_tokens)

    def _park_ready_decline(
        self, rid: str, view, reason, epochs, now
    ) -> None:
        """Record a staging decline in the per-rid causal negative-cache:
        the subscribed epoch's cursor at the decline, the request identity
        fingerprint, and the safety-fuse expiry (the anomalous repeat-fail
        bound). The rid is not re-eligible until the subscribed epoch
        advances or the identity changes (or the fuse expires)."""
        anchor = getattr(getattr(view, "req", None), "last_host_node", None)
        cursor = policy_epoch_value(self.ready_horizon, epochs, reason)
        if reason is DeclineReason.NO_L3:
            # phase2-peranchor: the NO_L3 negative cache subscribes to the
            # ANCHOR's per-anchor storage_version, not the global l3_publish
            # diagnostic counter -- an unrelated chain's durability event
            # must not clear the park.
            cursor = self._anchor_version_or_zero(anchor)
        entry = NegativeCacheEntry(
            reason=reason,
            epoch_cursor=cursor,
            fuse_expiry=now + self.ready_horizon.safety_fuse_s,
            prefix_len=view.prefix_len,
            generation=view.generation,
            anchor=anchor,
        )
        self._ready_horizon_negatives[rid] = entry

    def _ready_horizon_view_for(self, views, rid):
        for view in views:
            if view.rid == rid:
                return view
        return None

    def _ready_horizon_views(self, frontier_reqs) -> list:
        """Frozen per-request frontier views for the ready-pool policy
        (M6: the staged marker is the finalize-written, admission-consumed
        residency count; the full-prefix gate is resident-material-present
        (marker > 0))."""
        buffer_mode = self.server_args.hicache_host_memory_mode == "buffer_only"
        views = []
        for req in frontier_reqs:
            staged = (
                self.tree_cache.staged_prefetch_tokens(req.rid)
                if buffer_mode
                else self.tree_cache.peek_prefetch_loaded_tokens(req.rid)
            )
            generation = getattr(req, "session_generation", None)
            views.append(
                ReadyHorizonView(
                    req=req,
                    rid=req.rid,
                    state=req.hicache_restore_state,
                    wait_reason=req.hicache_restore_wait_reason,
                    staged_tokens=staged,
                    # the finalize writes the marker (> 0) on a full restore
                    full_prefix=staged > 0,
                    host_hit_length=req.host_hit_length,
                    staging_eligible=self._restore_potential_for(req),
                    prefix_len=len(req.full_untruncated_fill_ids) if req.full_untruncated_fill_ids is not None else 0,
                    generation=generation,
                )
            )
        return views

    def _ready_horizon_epochs(self, frontier_reqs, views, cc) -> CausalEpochs:
        """The five causal-epoch snapshot values (M3, user adjudication +
        Fix A). The running batch size is deliberately absent: it flips
        every pass under an 8-agent workload (the e7 gate breakdown) and a
        freed GPU slot surfaces through the frontier or headroom epochs.
        Per-request restore states are absent too: a candidate's denied
        WAIT transition must not re-arm the check (the per-pass poll M3
        forbids). The l3_publish epoch comes from the tree's monotonic
        durability counter; host_headroom from the host pool's free pages;
        host_release (Fix A) from the monotonic release counter, bumped
        when the observed available level GREW since the last snapshot --
        by construction a release (only free() raises the free count; the
        refill's own traffic only ever lowers it, so it can never
        self-trigger); spec_budget from the speculative inflight counter
        (released = it drops); waiting_frontier from the frontier
        composition."""
        host_release = self._ready_host_release_epoch
        last_level = self._ready_host_release_last_level
        available = cc.mem_pool_host.available_size()
        if last_level is not None and available > last_level:
            host_release += 1
        self._ready_host_release_epoch = host_release
        self._ready_host_release_last_level = available
        return CausalEpochs(
            l3_publish=self.tree_cache.l3_publish_epoch(),
            host_headroom=available,
            host_release=host_release,
            spec_budget=cc.inflight_speculative_tokens,
            waiting_frontier=tuple(r.rid for r in frontier_reqs),
        )

    def _ready_host_headroom(self, cc, views) -> int:
        """Host headroom for the READY pool (M1): the pool capacity not
        committed to the active/warm working set. The working set is the
        pool usage minus the ready horizon's own resident footprint, so
        the headroom equals the free pages plus the READY footprint; the
        refill gate then charges the resident footprint and in-flight
        staging against the free pages -- the same pages the staging alloc
        consumes (M2: speculative staging eats free headroom only). The P3
        write-back reserve floor is applied in refill_plan (reserve +
        margin kept free after the stage), not here."""
        pool = cc.mem_pool_host
        return pool.available_size() + self.ready_horizon.ready_resident_tokens(
            views
        )

    def _ready_reserve_floor_tokens(self, cc) -> int:
        """P3 write-back admission: the frozen host tokens a stage must
        leave free (writeback reserve + safety margin), in the anchor
        pool's token space. Token mode (ledger adjudication #2) reserves by
        state KV tokens directly; the legacy GB path converts lazily from
        the byte server_args because the host pool attach happens after the
        policy construction."""
        pool = cc.mem_pool_host if cc is not None else None
        if pool is None:
            return 0
        if self.ready_horizon_token_mode:
            return (
                self.ready_horizon_reserve_tokens
                + self.ready_horizon_margin_tokens
            )
        anchor = getattr(pool, "anchor_entry", None)
        anchor = anchor.host_pool if anchor is not None else pool
        reserve = 0
        getter = getattr(anchor, "writeback_reserve", None)
        if getter is not None:
            reserve = getter()
        margin_gb = self.server_args.ready_horizon_safety_margin_gb
        if margin_gb > 0:
            bytes_per_token = getattr(
                anchor, "size_per_token", getattr(anchor, "size", 1) or 1
            )
            reserve += int(margin_gb * 1e9 // bytes_per_token)
        return reserve

    def _hicache_capacity_stats(
        self, views, cc
    ) -> dict:
        """P3 token/capacity model gauge values (ledger 2026-09-01
        adjudication #3): kv_pool / writeback_reserve / ready_resident /
        working / spec_inflight / usable (pool - reserve - margin) KV-host
        token counts, plus per-pool usable (kv, mamba) and READY_state_max.
        Published to the metrics channel via SchedulerStats; no GB guessing."""

        def _pool_tokens(pool, name):
            return (
                pool.logical_size
                if getattr(pool, "logical_size", None) is not None
                else pool.size
            )

        pool = cc.mem_pool_host if cc is not None else None
        if pool is None or not hasattr(pool, "anchor_entry"):
            return {
                "kv_pool_tokens": 0,
                "writeback_reserve_tokens": 0,
                "ready_resident_tokens": 0,
                "working_tokens": 0,
                "spec_inflight_tokens": 0,
                "usable_tokens": 0,
                "kv_host_usable_tokens": 0,
                "mamba_host_usable_tokens": 0,
                "ready_state_max_tokens": 0,
            }
        anchor = pool.anchor_entry.host_pool
        kv_pool = _pool_tokens(anchor, "kv")
        reserve = getattr(anchor, "writeback_reserve", lambda: 0)()
        margin = getattr(anchor, "writeback_margin", lambda: 0)()
        ready_resident = self.ready_horizon.ready_resident_tokens(views)
        used = kv_pool - anchor.available_size()
        working = max(0, used - ready_resident)
        spec_inflight = getattr(cc, "inflight_speculative_tokens", 0) or 0
        usable = kv_pool - reserve - margin

        kv_usable = 0
        mamba_usable = 0
        for entry in pool.entries:
            entry_pool = entry.host_pool
            entry_reserve = getattr(
                entry_pool, "writeback_reserve", lambda: 0
            )()
            entry_margin = getattr(entry_pool, "writeback_margin", lambda: 0)()
            entry_usable = _pool_tokens(entry_pool, entry.name.value) - (
                entry_reserve + entry_margin
            )
            if getattr(entry.name, "value", entry.name) == "kv":
                kv_usable = entry_usable
            elif getattr(entry.name, "value", entry.name) == "mamba":
                mamba_usable = entry_usable

        ready_max = 0
        for view in views:
            if self.ready_horizon._is_ready_resident(view):
                ready_max = max(ready_max, view.staged_tokens)
        return {
            "kv_pool_tokens": kv_pool,
            "writeback_reserve_tokens": reserve,
            "ready_resident_tokens": ready_resident,
            "working_tokens": working,
            "spec_inflight_tokens": spec_inflight,
            "usable_tokens": usable,
            "kv_host_usable_tokens": kv_usable,
            "mamba_host_usable_tokens": mamba_usable,
            "ready_state_max_tokens": ready_max,
        }

    def _restore_backup_wake_ready(self, req) -> bool:
        """The T15 backup-completion wake condition (P2-IO R2): the
        parked request's chain durable frontier has crossed the request's
        end (backup_wait_ready, re-read every pass -- the ACK drain
        advances it, so the wake is ACK-driven) and a DEMAND_RESTORE
        ticket is free (bounded concurrency for a backup-complete wake
        batch; the re-issue bypasses only the speculative PREFETCH_BUDGET,
        every other gate still applies)."""
        anchor = req.last_host_node
        if anchor is None:
            return False
        return (
            self.tree_cache.backup_wait_ready(req.rid)
            and demand_restore_available(self.tree_cache.demand_restore_inflight())
        )

    def _restore_wait_capacity_fits(self, req) -> bool:
        """Per-pass WAIT wake predicate (design §2.3): device capacity for
        the incremental charge (same formula as the admission gates, minus
        the adder's running offsets -- strictly permissive, never stricter),
        the host prefetch budget, and for FRONTIER waiters the anchor
        fallback (persisted, or deleted and re-matchable). The admission
        gates stay authoritative: a too-permissive wake only costs a
        re-issued prefetch."""
        if req.hicache_restore_wait_reason is RestoreWaitReason.FRONTIER:
            anchor = req.last_host_node
            if anchor is None:
                return False
            # L3-readiness only: the host copy commits at D->H submission,
            # before the L3 write, and a wake there re-issues the prefetch
            # into an empty L3 (the M2 premature wake that kept
            # frontier_wake at zero). The predicate mirrors the ACK wake.
            return self.tree_cache.frontier_anchor_ready(anchor)
        if req.hicache_restore_wait_reason is RestoreWaitReason.BACKUP_PENDING:
            # The wait ends when the chain's durable frontier crosses the
            # request's end AND a DEMAND_RESTORE ticket is free: the wake
            # re-issues one prefetch that re-looks-up into the full chain.
            # The frontier advances only on ACK drains (re-read every
            # pass), so the wake is ACK-driven, not a poll; a failed
            # write that never crosses the frontier leaves the request to
            # the T13 timeout (bounded).
            return self._restore_backup_wake_ready(req)
        if req.hicache_restore_wait_reason is RestoreWaitReason.HOST_ALLOC:
            cc = self.tree_cache.cache_controller
            if cc is None or req.full_untruncated_fill_ids is None:
                return False
            if cc.prefetch_rate_limited():
                return False
            # Generation admission is handled by the FIFO arbiter.  Do not
            # require the complete span to be already free: the authoritative
            # retry must be allowed to run alloc -> evict_host -> alloc.
            return True
        cc = self.tree_cache.cache_controller
        if cc is not None and cc.prefetch_rate_limited():
            return False
        if req.hicache_restore_wait_reason is RestoreWaitReason.PREFETCH_BUDGET:
            # A budget wake only re-issues the L3->host prefetch, whose
            # capacity gate is the host prefetch limiter above. Device
            # admission remains authoritative after the restore reaches
            # READY; requiring its charge here strands this waiter while an
            # unrelated running request still occupies the device.
            return True
        # too_short churn (independent P, defense-in-depth): a DEVICE_QUOTA
        # waiter whose current restore suffix is already sub-threshold AND
        # can never grow back above it (the can-never-qualify prompt -- the
        # theoretical-max suffix is sub-threshold too) must not be woken by
        # the capacity predicate. Waking re-issues an inevitably
        # declined_too_short prefetch (granted=0) and re-parks on the next
        # pass's capacity check -- the tight wake->re-issue->declined->re-WAIT
        # loop. The request is released to recompute its tail directly
        # instead (the admission main fix already keeps it out of this WAIT
        # on the forward path; this predicate is the defense for any
        # DEVICE_QUOTA waiter that entered before the fix). REVALIDATE /
        # device-match-decay semantics are untouched: a prompt that CAN grow
        # its suffix above the threshold keeps its capacity wake.
        if req.hicache_restore_wait_reason is RestoreWaitReason.DEVICE_QUOTA:
            if req.full_untruncated_fill_ids is not None:
                if not (
                    self.tree_cache.prompt_can_qualify_for_prefetch(
                        len(req.full_untruncated_fill_ids), req.host_hit_length
                    )
                ):
                    return False
                # P4 gate (no-heuristic): the CURRENT actually-prefetchable
                # suffix must also clear the threshold. The can-never-qualify
                # gate above uses the theoretical-max suffix
                # (prompt_len - host_hit_length, after the device match has
                # fully decayed); a REVALIDATE-bet / never-case-residue
                # waiter passes it (max suffix >= threshold) yet its current
                # suffix (match_end - (prefix match + host match)) is still
                # sub-threshold. Capacity-waking such a waiter re-issues an
                # inevitably declined_too_short prefetch every pass (the
                # tight wake->re-issue->declined->re-WAIT loop); capacity
                # release does not change that result, so capacity is not a
                # wake source for it. Its only legal re-trigger is the
                # current suffix growing past the threshold (device match
                # decay, observed on the fresh-geometry re-entry after the
                # bounded T13 recompute) or the T13 fallback recompute
                # itself. REVALIDATE-bet restore potential is untouched
                # (has_restore_potential is not modified) -- only the
                # capacity wake is suppressed. population A (current suffix
                # already qualifies) is not held.
                if self._current_prefetch_suffix_lt_threshold(req):
                    return False
        # P2-1c promotion-budget item (design §3.4): a DEVICE_QUOTA waiter
        # whose next step is a FULL-KV promotion (host material ready) must
        # not wake while the device promotion budget cannot hold it --
        # waking re-issues prefetch -> finalize -> admission -> re-deny,
        # burning a full prefetch cycle per wake. host_hit_length == 0
        # waiters (T6 sources whose material is still staging) are not
        # budgeted: their next step is the unrestricted L3->H prefetch. The
        # predicate re-reads every pass, so a reservation release is visible
        # the same pass (drain runs before this reconciliation).
        if promotion_wait_blocked(
            req.hicache_restore_wait_reason,
            req.host_hit_length,
            promotion_budget_fits(
                device_locked_tokens(
                    self.tree_cache.token_to_kv_pool_allocator, self.tree_cache
                ),
                self.tree_cache.inflight_promotion_reserved,
                req.host_hit_length,
                self.tree_cache.token_to_kv_pool_allocator.size_full,
                self.server_args.hicache_promotion_margin_tokens,
            ),
        ):
            return False
        max_new = min(
            max(req.sampling_params.max_new_tokens - len(req.output_ids), 0),
            CLIP_MAX_NEW_TOKENS,
        )
        charge = device_charge(
            len(req.full_untruncated_fill_ids),
            len(req.prefix_indices),
            max_new,
            self.page_size,
        )
        return charge < available_and_evictable_tokens(
            self.req_to_token_pool, self.tree_cache
        )

    def _current_prefetch_suffix_lt_threshold(self, req) -> bool:
        """P4 gate (no-heuristic): whether the CURRENT actually-prefetchable
        suffix is below prefetch_threshold (page_size aligned).

        Same geometry as prompt_can_qualify_for_prefetch but on the CURRENT
        match (match_end - (len(prefix_indices) + host_hit_length)) rather
        than the theoretical max (prompt_len - host_hit_length): the current
        suffix is exactly the span prefetch_from_storage would re-issue
        (new_input_tokens = fill_ids[matched_len:match_end]). A sub-threshold
        current suffix means the re-issue is inevitably declined_too_short,
        so capacity is not a legal wake source for this waiter (its
        re-trigger is current-suffix growth past threshold via device match
        decay -- observed on the fresh-geometry re-entry after the bounded
        T13 recompute -- or the T13 fallback recompute itself)."""
        matched_len = len(req.prefix_indices) + req.host_hit_length
        match_end = req._compute_max_prefix_len(len(req.full_untruncated_fill_ids))
        current_suffix = max(0, match_end - matched_len)
        return (
            current_suffix // self.page_size * self.page_size
            < self.tree_cache.prefetch_threshold
        )

    def _restore_potential_for(self, req) -> bool:
        """Design §2.5-1 restore potential plus the can-never-qualify prompt
        gate; the shared entry condition for T4/T5/T6 (a quota or gate
        denial only becomes a WAIT when restore material exists)."""
        return self.tree_cache.has_restore_potential(
            req.rid,
            req.last_host_node,
            req.host_hit_length,
            len(req.full_untruncated_fill_ids),
        )

    def _no_material_fast_forward_for(self, req, anchor) -> bool:
        """phase2-peranchor: whether the FRONTIER waiter's anchor has NO
        recoverable material and nothing in flight can make it durable, so
        the frontier wait is zero-expectation and the request should
        ADMIT_RECOMPUTE immediately instead of idling out the full 60s T13.

        Assembles the 5 no-material facts (host / storage / pending-ACK /
        deferred-descendant / restorable-epoch-change) into a
        FrontierAnchorInfo and delegates to the pure
        no_material_fast_forward predicate. The judgment is deliberately NOT
        "storage_hit == 0 => recompute": each fact is checked on its own, and
        the presence of ANY in-flight producer or deferred descendant keeps
        the P3 reconcile + frontier wait path (never fast-forwards).

        phase2-p0fix Q1: before judging, resolve the anchor to its deepest
        durable ancestor (the most rootward L3-durable node on the anchor's
        parent chain). A request's suffix is served from a page range under
        the anchor; when the host prefix was split by an L3 write ack
        (D->H commit), the shallow anchor can be non-durable while a deeper
        ancestor's pages ARE durable. Judging on the shallow node's missing
        storage facts would mis-forward a request that could restore from the
        deeper durable pages. The storage facts (2-5) are evaluated on the
        resolved judgment anchor; host material (fact 1) is unchanged. When no
        durable ancestor exists (a pure device chain with no L3 content, root
        storage_persisted defaults False), no-material holds and the request
        forwards immediately -- the fast-forward main benefit is preserved.
        """
        tc = self.tree_cache
        # 1) Host material: host copy / host hit present for the candidate.
        host_material = bool(getattr(req, "host_hit_length", 0) > 0)
        # Q1: resolve the deepest durable ancestor before judging. Falls back
        # to the original anchor when the proxy is absent (e.g. test stubs).
        durable_ancestor = None
        if anchor is not None:
            dda = getattr(tc, "deepest_durable_ancestor", None)
            if callable(dda):
                try:
                    durable_ancestor = dda(anchor)
                except Exception:
                    durable_ancestor = None
        judgment_anchor = (
            durable_ancestor if durable_ancestor is not None else anchor
        )
        # 2) Storage material: the resolved anchor is durable (a durable
        #    ancestor was found), or the original anchor is the root (a root
        #    anchor is always prefetch-issuable -- never a no-material
        #    dead-end). A pure device chain resolves to no durable ancestor
        #    (None) -> no-material holds -> forward (main benefit preserved).
        storage_material = durable_ancestor is not None
        if judgment_anchor is not None:
            node_exists = getattr(tc, "node_exists", None)
            if callable(node_exists) and node_exists(judgment_anchor):
                is_l3 = getattr(tc, "is_l3_durable", None)
                if callable(is_l3) and is_l3(judgment_anchor):
                    storage_material = True
                is_root = getattr(tc, "is_root", None)
                if callable(is_root) and is_root(judgment_anchor):
                    storage_material = True
        # 3) Pending durable ACK: an L3 write for the resolved anchor's chain
        #    is in flight (ongoing_backup), OR the node is already marked
        #    storage_written (a submitted write whose ack could promote it).
        pending_durable_ack = False
        if judgment_anchor is not None:
            node_exists = getattr(tc, "node_exists", None)
            if callable(node_exists) and node_exists(judgment_anchor):
                is_sw = getattr(tc, "is_storage_written", None)
                if callable(is_sw):
                    pending_durable_ack = bool(is_sw(judgment_anchor))
        ongoing_backup = getattr(tc, "ongoing_backup", None)
        if ongoing_backup:
            for op_node, _lock in ongoing_backup.values():
                if op_node == judgment_anchor:
                    pending_durable_ack = True
                    break
        # 4) Deferred durable descendant: the resolved anchor still anchors a
        #    storage_acked && !storage_persisted node (a P3 reconcile
        #    promotion source that could make it durable).
        deferred_durable_desc = False
        if judgment_anchor is not None:
            node_exists = getattr(tc, "node_exists", None)
            if callable(node_exists) and node_exists(judgment_anchor):
                has_desc = getattr(tc, "has_acked_descendant", None)
                if callable(has_desc):
                    deferred_durable_desc = bool(has_desc(judgment_anchor))
        # 5) Restorable epoch change: a per-anchor durability event that could
        #    make a currently-unredeemable restore redeemable -- either an
        #    in-flight restore read-back (load_back) for this anchor node, or
        #    the anchor's own per-anchor version has moved at all (it has L3
        #    durability history, e.g. it was durable and just got cleared, so
        #    a re-restore may be redeemable). Both are conservative: they keep
        #    the frontier wait rather than fast-forward.
        restorable_epoch_change = False
        if judgment_anchor is not None:
            ongoing_load_back = getattr(tc, "ongoing_load_back", None)
            if ongoing_load_back and judgment_anchor in ongoing_load_back:
                restorable_epoch_change = True
            av = getattr(tc, "anchor_storage_version", None)
            if callable(av):
                try:
                    if int(av(judgment_anchor)) > 0:
                        restorable_epoch_change = True
                except Exception:
                    restorable_epoch_change = False
        return no_material_fast_forward(
            FrontierAnchorInfo(
                host_material=host_material,
                storage_material=storage_material,
                pending_durable_ack=pending_durable_ack,
                deferred_durable_desc=deferred_durable_desc,
                restorable_epoch_change=restorable_epoch_change,
            )
        )

    def _anchor_version_or_zero(self, anchor) -> int:
        """The per-anchor storage_version of `anchor` (0 when absent / the
        node is gone / no per-anchor API -- a dead anchor self-heals to a
        re-match from root, a new candidate, so its old negative evidence no
        longer binds). phase2-peranchor: the anchor-local causal signal for
        the P1 miss re-arm gate and the NO_L3 cursor; never the global
        diagnostic epoch."""
        if anchor is None:
            return 0
        fn = getattr(self.tree_cache, "anchor_storage_version", None)
        if not callable(fn):
            return 0
        try:
            return int(fn(anchor))
        except Exception:
            return 0

    def _miss_rearm_decision(self, req) -> bool:
        """T6 admission miss re-arm decision (explicit three-branch form of
        the P1 `miss_rearm_allowed` gate, phase2-p4-round2 点3).

        - no recorded miss epoch (defensive; the state should not be
          MISS_RECOMPUTE then) -> re-arm (preserves historical behavior).
        - re-anchored to a different node OR the identity (session
          generation) changed -> re-arm: the old negative evidence no longer
          applies to the new candidate / identity.
        - the SAME anchor's per-anchor storage version advanced -> re-arm
          ONLY when the anchor chain now actually holds durable L3 material
          (`_miss_rearm_durable_coverage`). A same-anchor version advance is
          the causal signal of a durability event, but clear (durable-belief
          removed) and evict-rebuild (chain cleared + rebuilt) both bump the
          version WITHOUT leaving recoverable L3 material -- re-probing
          those is a structural guaranteed miss, so they stay sticky and
          recompute forward instead of re-churning the revoked:miss loop.
        - same-anchor, version unchanged, generation unchanged -> sticky
          (not re-armed): re-probing the proven-missing prefix at the same
          anchor version must miss again.

        re-anchor/generation are judged BEFORE the material-coverage gate: a
        brand-new candidate must never be blocked by the old anchor's
        material state. No counters/TTL/thresholds (no-heuristic); the
        coverage check is a structural existence query (deepest durable
        ancestor non-None)."""
        if req.hicache_restore_miss_epoch is None:
            return True  # defensive: no record -> re-arm
        cur_anchor = getattr(req, "last_host_node", None)
        miss_anchor = req.hicache_restore_miss_anchor
        cur_gen = getattr(req, "session_generation", None)
        miss_gen = req.hicache_restore_miss_generation
        re_anchored = (
            miss_anchor is not None
            and cur_anchor is not None
            and cur_anchor != miss_anchor
        )
        generation_changed = cur_gen is not None and cur_gen != miss_gen
        if re_anchored or generation_changed:
            return True  # new candidate / identity changed: old evidence void
        if self._anchor_version_or_zero(cur_anchor) > req.hicache_restore_miss_epoch:
            # Same anchor, version advanced: re-arm only when the anchor
            # chain now actually has durable L3 material covering it
            # (P4-round2 点3: no-material same-anchor re-probe is a
            # structural guaranteed miss).
            return self._miss_rearm_durable_coverage(req)
        return False  # same anchor, version unchanged -> sticky

    def _miss_rearm_durable_coverage(self, req) -> bool:
        """P4-round2 点3 material-coverage gate: whether the request's anchor
        chain now actually holds durable L3 material (Q1
        `deepest_durable_ancestor(anchor)` non-None).

        A same-anchor version advance is the causal signal of a durability
        event, but it does NOT guarantee the event left recoverable material
        behind: clear (durable-belief removed) and evict-rebuild (chain
        cleared and rebuilt) both bump the version while leaving a pure
        device chain with no L3 content. Re-probing a no-material chain is a
        structural guaranteed miss (the revoked:miss churn the P1 sticky
        gate exists to prevent), so the re-arm stays sticky until material
        genuinely arrives -- at which point the chain re-gains a durable
        ancestor, dda becomes non-None, and the gate re-opens (point 5
        legitimate re-restore preserved). O(depth) existence check, no
        counters/TTL/thresholds. Defensive fallbacks: no anchor -> True
        (nothing to judge here; let the identity/anchor criteria decide);
        deepest_durable_ancestor proxy missing (stub / no per-anchor API) ->
        True (conservative release, preserves prior behavior)."""
        anchor = getattr(req, "last_host_node", None)
        if anchor is None:
            return True  # no anchor to judge -> release to identity/anchor
        dda = getattr(self.tree_cache, "deepest_durable_ancestor", None)
        if not callable(dda):
            return True  # stub/fallback: conservative release
        return dda(anchor) is not None

    def _cleanup_not_added_req(self, req, adder) -> None:
        """Revert matched mamba idx state when add_one_req rejected the
        request (avoid a memory leak). Only frees slots freshly allocated in
        this batch (not pre-existing from a session); session-held slots
        have their own lifecycle and freeing them here causes double-free."""
        added = len(adder.can_run_list) > 0 and req is adder.can_run_list[-1]
        if not added:
            # init_next_round_input() may stage deferred Mamba COW/clear
            # metadata before add_one_req() rejects the request.
            req.mamba_cow_src_index = None
            req.mamba_needs_clear = False
            if req.mamba_pool_idx is not None and not getattr(req, "session", None):
                self.tree_cache.req_to_token_pool.mamba_allocator.free(
                    req.mamba_pool_idx.unsqueeze(-1)
                )
                req.mamba_pool_idx = None

    def _add_request_to_queue(self, req: Req, is_retracted: bool = False):
        if not self._set_or_validate_priority(req):
            return
        if self.disaggregation_mode == DisaggregationMode.NULL:
            if self._abort_on_queued_limit(req):
                return
            self._rh_request_enqueue_seq = getattr(
                self, "_rh_request_enqueue_seq", 0
            ) + 1
            req.hicache_request_enqueue_seq = self._rh_request_enqueue_seq
            if not self.enable_ready_horizon:
                self._prefetch_kvcache(
                    req, origin=HiCachePrefetchOrigin.EAGER_RH_OFF
                )
            self.waiting_queue.append(req)
            req.time_stats.set_wait_queue_entry_time()
        elif self.disaggregation_mode == DisaggregationMode.PREFILL:
            self._prefetch_kvcache(
                req, origin=HiCachePrefetchOrigin.EAGER_DISAGG_PREFILL
            )
            self.disagg_prefill_bootstrap_queue.add(
                req, self.model_config.num_key_value_heads
            )
            req.time_stats.set_prefill_bootstrap_queue_entry_time()
        elif self.disaggregation_mode == DisaggregationMode.DECODE:
            self.disagg_decode_prealloc_queue.add(req, is_retracted=is_retracted)
            if not is_retracted:
                req.time_stats.set_decode_prealloc_queue_entry_time()
            else:
                req.time_stats.set_retract_time()
        else:
            raise ValueError(f"Invalid {self.disaggregation_mode=}")

    def _set_or_validate_priority(self, req: Req) -> bool:
        """Set the default priority value, or abort the request based on the priority scheduling mode."""
        if self.enable_priority_scheduling and req.priority is None:
            if self.schedule_low_priority_values_first:
                req.priority = sys.maxsize
            else:
                req.priority = -sys.maxsize - 1
        elif (
            not self.enable_priority_scheduling
            and req.priority is not None
            and self.abort_on_priority_when_disabled
        ):
            abort_req = _make_abort_req(
                req,
                finished_reason={
                    "type": "abort",
                    "status_code": HTTPStatus.SERVICE_UNAVAILABLE,
                    "message": "Using priority is disabled for this server. Please send a new request without a priority.",
                },
            )
            req.time_stats.trace_ctx.abort(abort_info=abort_req.finished_reason)
            self.ipc_channels.send_to_tokenizer.send_output(abort_req, req)
            return False
        return True

    def _abort_on_queued_limit(self, recv_req: Req) -> bool:
        """Abort an incoming or existing request if the waiting queue is full. Returns True if the incoming request is aborted."""
        if (
            self.max_queued_requests is None
            or len(self.waiting_queue) + 1 <= self.max_queued_requests
        ):
            return False

        # Reject the incoming request by default.
        req_to_abort = recv_req
        message = "The request queue is full."
        if self.enable_priority_scheduling:
            # With priority scheduling, consider aboritng an existing request based on the priority.
            # direction = 1  => smaller number = higher priority; -1 => larger number = higher priority.
            # max(...) + (direction * priority, queue_time_start) picks the least-preferred request.
            # Tie: later queue_time_start (newer) is evicted first. Preempt only if strictly better.
            direction = 1 if self.schedule_low_priority_values_first else -1
            key_fn = lambda item: (
                direction * item[1].priority,
                item[1].time_stats.wait_queue_entry_time,
            )
            idx, candidate_req = max(enumerate(self.waiting_queue), key=key_fn)
            abort_existing_req = (
                direction * recv_req.priority < direction * candidate_req.priority
            )
            if abort_existing_req:
                if self.enable_hicache_storage:
                    # Release prefetch events associated with the request
                    self.tree_cache.release_aborted_request(candidate_req.rid)
                    self._release_prefetch_claim(
                        candidate_req,
                        getattr(candidate_req, "hicache_prefetch_active_attempt_id", None),
                        "queued_priority_abort",
                    )
                self._remove_host_alloc_waiter(candidate_req.rid)
                self.waiting_queue.pop(idx)
                self.beam_coordinator.retire_group(candidate_req)
                req_to_abort = candidate_req
                message = "The request is aborted by a higher priority request."

        self.ipc_channels.send_to_tokenizer.send_output(
            _make_abort_req(
                req_to_abort,
                finished_reason={
                    "type": "abort",
                    "status_code": HTTPStatus.SERVICE_UNAVAILABLE,
                    "message": message,
                },
            ),
            req_to_abort,
        )
        req_to_abort.time_stats.trace_ctx.abort(abort_info={"reason": message})
        return req_to_abort.rid == recv_req.rid

    def _abort_on_waiting_timeout(self):
        if (timeout_s := envs.SGLANG_REQ_WAITING_TIMEOUT.get()) <= 0:
            return

        deleted_reqs = set()
        deadline = time.perf_counter() - timeout_s
        for req in self.waiting_queue:
            entry_time = req.time_stats.wait_queue_entry_time
            if 0 < entry_time < deadline:
                if self.enable_hicache_storage:
                    # Release prefetch events associated with the request
                    self.tree_cache.release_aborted_request(req.rid)
                    self._release_prefetch_claim(
                        req,
                        getattr(req, "hicache_prefetch_active_attempt_id", None),
                        "queued_abort",
                    )
                self._remove_host_alloc_waiter(req.rid)
                self.ipc_channels.send_to_tokenizer.send_output(
                    _make_abort_req(
                        req,
                        finished_reason={
                            "type": "abort",
                            "status_code": HTTPStatus.SERVICE_UNAVAILABLE,
                            "message": "Request waiting timeout reached.",
                        },
                    ),
                    req,
                )
                deleted_reqs.add(req)
                self.beam_coordinator.retire_group(req)

        if deleted_reqs:
            self.waiting_queue = [
                req for req in self.waiting_queue if req not in deleted_reqs
            ]

    def handle_embedding_request(
        self,
        recv_req: TokenizedEmbeddingReqInput,
    ):
        req = Req(
            recv_req.rid,
            recv_req.input_text,
            recv_req.input_ids,
            recv_req.sampling_params,
            positional_embed_overrides=recv_req.positional_embed_overrides,
            token_type_ids=recv_req.token_type_ids,
            routed_dp_rank=recv_req.routed_dp_rank,
            priority=recv_req.priority,
            dimensions=recv_req.dimensions,
            lora_id=recv_req.lora_id,
            http_worker_ipc=recv_req.http_worker_ipc,
            time_stats=recv_req.time_stats,
            return_pooled_hidden_states=recv_req.return_pooled_hidden_states,
            multi_item_delimiter_indices=recv_req.multi_item_delimiter_indices,
        )
        req.tokenizer = self.tokenizer
        self._maybe_namespace_elastic_radix_cache(req)

        # Handle multimodal inputs
        if recv_req.mm_inputs is not None:
            image_inputs = self._get_multimodal_inputs(recv_req.mm_inputs)
            # Expand a single image token into multiple dummy tokens for receiving image embeddings
            # The `pad_input_ids_func` is model-specific and may be None for
            # embedding models or models not requiring special padding.
            # If None, `req.origin_input_ids` is expected to be correctly populated already.
            if (
                not self._try_apply_padded_mm_input_ids(recv_req, req, image_inputs)
                and self.pad_input_ids_func
            ):
                # See companion call site above for the array.array wrap rationale.
                req.origin_input_ids = array(
                    "q", self.pad_input_ids_func(req.origin_input_ids, image_inputs)
                )

            req.extend_image_inputs(image_inputs)
            self._maybe_compute_mrope_positions(req)

            if len(req.origin_input_ids) >= self.max_req_input_len:
                req.set_finish_with_abort(
                    error_msg=(
                        "Multimodal prompt is too long after expanding multimodal tokens. "
                        f"After expanding {len(req.origin_input_ids_unpadded)=} => {len(req.origin_input_ids)} >= {self.max_req_input_len}."
                    )
                )
                self._add_request_to_queue(req)
                return

        # Validate prompts length
        error_msg = validate_input_length(
            req,
            self.max_req_input_len,
            get_serving().allow_auto_truncate,
        )
        if error_msg:
            self._add_request_to_queue(req)
            return

        # Copy more attributes
        req.logprob_start_len = -1
        self._add_request_to_queue(req)

    def handle_batch_embedding_request(
        self,
        recv_req: BatchTokenizedEmbeddingReqInput,
    ):
        """Handle optimized batch embedding request."""
        logger.debug(
            f"Processing batch embedding request with {len(recv_req)} requests"
        )

        # Process each request in the batch
        for tokenized_req in recv_req:
            self.handle_embedding_request(tokenized_req)

    def stash_chunked_request(self, req: Req):
        maybe_cache_unfinished_req(req, self.tree_cache, chunked=True)

    def process_pending_chunked_abort(self) -> None:
        """Abort an in-flight chunked-prefill request once it is safe to do so.

        ``abort_request`` only records the target in ``_pending_chunked_abort_req``
        (tearing it down mid-iteration is unsafe). Clearing ``chunked_req`` here at
        the top of the scheduling step stops the next chunk from launching; the
        chunk already launched is drained when its result is resolved. Under overlap
        the result lands a step later, so the batch-result processors keep
        ``inflight_middle_chunks`` accounting intact and skip the aborted chunk:
        ``process_batch_result_disagg_prefill`` via its ``is_aborted`` drop, and
        ``process_batch_result_prefill`` via its chunked branch (the finished req
        is excluded from streaming and its logprob offset is still accounted).
        Mirrors ``handle_bootstrap_failure``.
        """
        req = self._pending_chunked_abort_req
        if req is None:
            return
        if self.chunked_req is not req:
            # Already past chunked prefill; the running-batch abort path handles
            # it. Drop the marker once the request is actually gone.
            if req.finished() or req.req_pool_idx is None:
                self._pending_chunked_abort_req = None
            return

        prepare_abort(req, "Aborted")
        req.time_stats.trace_ctx.abort(abort_info={"reason": "Aborted"})
        req.to_finish = None
        if self.disaggregation_mode == DisaggregationMode.PREFILL:
            self.clear_pending_chunk_send(req)
            req.disagg_kv_sender.abort()
            maybe_release_metadata_buffer(
                req, self.req_to_metadata_buffer_idx_allocator
            )
            req.pending_bootstrap = False
        if self.enable_hicache_storage:
            self.tree_cache.release_aborted_request(req.rid)
            self._release_prefetch_claim(
                req,
                getattr(req, "hicache_prefetch_active_attempt_id", None),
                "chunked_abort",
            )
        release_kv_cache(req, self.tree_cache, is_insert=False)

        self.chunked_req = None
        self._pending_chunked_abort_req = None
        self.ipc_channels.send_to_tokenizer.send_output(_make_abort_req(req), req)
        logger.debug(f"Abort chunked prefill request. {req.rid=}")

    def _build_hisparse_decode_batch(self, reqs):
        """Build a ScheduleBatch for hisparse requests transitioning from staging to decode."""
        device = self.device

        batch = ScheduleBatch.init_new(
            reqs=reqs,
            req_to_token_pool=self.req_to_token_pool,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            tree_cache=self.tree_cache,
            model_config=self.model_config,
            enable_overlap=self.enable_overlap,
            spec_algorithm=self.spec_algorithm,
        )

        req_pool_indices = [r.req_pool_idx for r in reqs]
        batch.req_pool_indices = torch.tensor(
            req_pool_indices, dtype=torch.int64, device=device
        )
        batch.req_pool_indices_cpu = torch.tensor(req_pool_indices, dtype=torch.int64)
        seq_lens = [len(r.origin_input_ids) + len(r.output_ids) - 1 for r in reqs]
        batch.seq_lens = torch.tensor(seq_lens, dtype=torch.int64, device=device)
        batch.seq_lens_cpu = torch.tensor(seq_lens, dtype=torch.int64)
        batch.orig_seq_lens = torch.tensor(seq_lens, dtype=torch.int32, device=device)
        batch.seq_lens_sum = sum(seq_lens)
        # Stash last token into relay; resolve_forward_inputs will gather.
        last_tokens = torch.tensor(
            [r.output_ids[-1] for r in reqs], dtype=torch.int64, device=device
        )
        self.future_map.stash(
            batch.req_pool_indices, RelayPayload(bonus_tokens=last_tokens)
        )
        batch.input_ids = None

        if batch.return_logprob:
            batch.top_logprobs_nums = [r.logprob.top_logprobs_num for r in reqs]
            batch.token_ids_logprobs = [list(r.origin_input_ids) for r in reqs]

        batch.sampling_info = SamplingBatchInfo.from_schedule_batch(
            batch, self.model_config.vocab_size
        )
        # todo hisparse, maybe other info to contain for the new batch
        return batch

    @scheduler_nvtx_method("scheduler.get_next_batch_to_run")
    def get_next_batch_to_run(
        self, running_batch: ScheduleBatch, last_batch: Optional[ScheduleBatch]
    ) -> NextBatchPlan:
        self.process_pending_chunked_abort()

        if self.enable_fpm:
            self._fpm_batch_t0 = time.monotonic()
        self._abort_on_waiting_timeout()
        self._abort_on_running_timeout(running_batch)
        if self.dllm_config is not None:
            self.dllm_manager.filter_finished_reqs()

        # Merge the prefill batch into the running batch
        chunked_req_to_exclude = set()

        if self.dllm_config is not None and self.dllm_manager.any_staging_reqs():
            chunked_req_to_exclude.update(self.dllm_manager.staging_queue)
            for req in self.dllm_manager.staging_queue:
                if self.dllm_config.first_done_first_out_mode:
                    if not req.dllm_incomplete_ids:
                        self.stash_chunked_request(req)
                        self.req_to_token_pool.free(req)
                    # Otherwise, keep req slot/KV for reuse.
                else:
                    self.stash_chunked_request(req)

        if self.chunked_req is not None:
            # Move the chunked request out of the batch so that we can merge
            # only finished requests to running_batch.
            chunked_req_to_exclude.add(self.chunked_req)

            # Stash (cache) the previous chunk only when it produced new KV
            # beyond what is already cached. A parked chunk (add_chunked_req
            # hybrid-SWA early-return) leaves extend_range.end ==
            # len(prefix_indices), so there is nothing new to cache and
            # stashing would be a no-op.
            if self.chunked_req.extend_range.end > len(self.chunked_req.prefix_indices):
                self.stash_chunked_request(self.chunked_req)

        # HiSparse has its own prefill-to-decode transition; skip last_batch merge.
        if self.enable_hisparse:
            ready_reqs = self.hisparse_coordinator.collect_ready_reqs()
            if len(ready_reqs) > 0:
                new_batch = self._build_hisparse_decode_batch(ready_reqs)
                if running_batch.is_empty():
                    running_batch = new_batch
                else:
                    running_batch.merge_batch(new_batch)
                running_batch.hisparse_coordinator = self.hisparse_coordinator
            # Reset batch_is_full so the scheduler can schedule more prefills.
            running_batch.batch_is_full = False

        if (
            not self.enable_hisparse
            and last_batch
            and last_batch.forward_mode.is_extend()
        ):
            if last_batch.chunked_req is not None:
                # In the context pipeline parallelism, after the last chunk, the current microbatch still track outdated chunked_req.
                # We need to discard it.
                chunked_req_to_exclude.add(last_batch.chunked_req)

            if self.dllm_config is not None and last_batch.reqs:
                chunked_req_to_exclude.update(last_batch.reqs)

            # Filter batch
            last_bs = last_batch.batch_size()
            last_batch.filter_batch(chunked_req_to_exclude=list(chunked_req_to_exclude))
            if last_batch.batch_size() < last_bs:
                running_batch.batch_is_full = False

            # Merge the new batch into the running batch.
            if not last_batch.is_empty():
                if running_batch.is_empty():
                    running_batch = last_batch
                else:
                    # Merge running_batch with prefill batch
                    running_batch.merge_batch(last_batch)

        # For prefill-only batch, filter out finished requests since they
        # won't go through the decode step. This keeps running_batch accurate
        # for load reporting (num_running_reqs via /v1/loads).
        # Runs outside the last_batch block so stale requests are cleaned
        # even when no new batches arrive (e.g. traffic stops).
        if running_batch.is_prefill_only:
            running_batch.filter_batch()
            if running_batch.is_empty():
                running_batch.batch_is_full = False

        if self.dllm_config is not None:
            new_batch = self.get_new_batch_dllm(running_batch)
        elif self._should_defer_prefill():
            new_batch = None
        else:
            prefill_plan = self.get_new_batch_prefill(running_batch)
            new_batch = prefill_plan.batch_to_run
            running_batch = prefill_plan.running_batch

        need_mlp_sync = self.require_mlp_sync
        if (
            need_mlp_sync
            and not self.spec_algorithm.is_none()
            and not get_spec().speculative_skip_dp_mlp_sync
        ):
            # NOTE: This branch makes sure prefill and decode batches will not be mixed when spec and dp-attn is enabled.
            # Before merging the new batch into running batch:
            # 1. All new batches are none -> need_mlp_sync remains true (sync is needed for decode batch).
            # 2. All new batches are some (prefill / idle) -> we do not need prepare mlp sync one more time.
            new_batch = self.dp_attn_adapter.maybe_prepare_mlp_sync_batch(new_batch)
            need_mlp_sync = new_batch is None

        if new_batch is not None:
            # Run prefill first if possible
            ret = new_batch
        else:
            # Run decode (skip for prefill-only batches)
            if not running_batch.is_empty() and not running_batch.is_prefill_only:
                running_batch = self.update_running_batch(running_batch)
                ret = running_batch if not running_batch.is_empty() else None
            else:
                ret = None

        # Handle DP attention and log stats
        ret = self.dp_attn_adapter.maybe_prepare_mlp_sync_batch(
            ret, need_sync=need_mlp_sync
        )
        # Decode->extend conversion keeps a heterogeneous dp step replayable.
        converted = self.dp_attn_adapter.maybe_convert_decode_to_extend(ret)
        if converted is running_batch and converted.forward_mode.is_extend():
            # The converted batch re-enters via the last_batch extend-merge
            # next iteration; empty running_batch or it merges with itself.
            running_batch = ScheduleBatch(
                reqs=[], batch_is_full=running_batch.batch_is_full
            )
        ret = converted
        self._arm_prefill_decode_interval(ret)

        # Handle ngram embedding
        ret = self.ngram_embedding_manager.prepare_for_forward(
            ret, chunked_req=self.chunked_req
        )

        if ret:
            set_schedule_time_batch(ret)
            if self.enable_fpm:
                ret.fpm_start_time = self._fpm_batch_t0

        return NextBatchPlan(batch_to_run=ret, running_batch=running_batch)

    def get_num_allocatable_reqs(
        self,
        running_bs: int,
        beam_width: Optional[int] = None,
        running_batch: Optional[ScheduleBatch] = None,
    ) -> int:
        pp_budget = get_parallel().pp_max_micro_batch_size - running_bs
        available = self.req_to_token_pool.available_size()

        active_batch = running_batch or self.running_batch
        available = max(
            available - self.beam_coordinator.pending_member_rows(active_batch), 0
        )
        res = min(pp_budget, available)
        if beam_width is not None:
            # A beam candidate owns beam_width rows once decoding.
            res = min(res, available // beam_width)

        return res

    def get_new_batch_prefill(self, running_batch: ScheduleBatch) -> NextBatchPlan:
        prefill_delayer_single_pass = None
        if self.prefill_delayer:
            # Get max usage across all pools for prefill delay decision
            max_pool_usage = (
                self.pool_stats_observer.get_pool_stats().get_max_pool_usage()
            )
            prefill_delayer_single_pass = PrefillDelayerSinglePassExecutor(
                self.prefill_delayer, token_usage=max_pool_usage
            )

        ret, running_batch = self._get_new_batch_prefill_raw(
            prefill_delayer_single_pass=prefill_delayer_single_pass,
            running_batch=running_batch,
        )

        if self.prefill_delayer:
            observed_prefill_bs = prefill_delayer_single_pass.finalize(
                actual_prefill_bs=ret.batch_size() if ret is not None else 0
            )
            if observed_prefill_bs > 0:
                self.max_prefill_bs = self.prefill_bs_tracker.observe_attempt(
                    observed_prefill_bs
                )

        return NextBatchPlan(batch_to_run=ret, running_batch=running_batch)

    def _get_new_batch_prefill_raw(
        self,
        prefill_delayer_single_pass: Optional[PrefillDelayerSinglePassExecutor],
        running_batch: ScheduleBatch,
    ) -> Tuple[Optional[ScheduleBatch], ScheduleBatch]:
        # Check if the grammar is ready in the grammar queue
        if self.grammar_manager.has_waiting_grammars():
            ready_grammar_requests = self.grammar_manager.get_ready_grammar_requests()
            for req in ready_grammar_requests:
                self._add_request_to_queue(req)

        if self.enable_hierarchical_cache or get_memory().enable_flexkv:
            self.tree_cache.check_hicache_events()
            if self.enable_hicache_storage:
                self._reconcile_restore_states()
                # P3 Ready Horizon v0 (3.2): maintain the READY_HOST pool
                # after the restore reconciliation (event-driven, M3).
                self._ready_horizon_pass()

        # [P2A] Periodic aggregate of admission-deny reasons; per-attempt
        # denies are counters in schedule_policy, not log lines.
        deny_now = time.time()
        if deny_now - self._last_deny_stats_ts >= 30.0:
            self._last_deny_stats_ts = deny_now
            deny_stats = prefill_deny_snapshot()
            if deny_stats:
                logger.info(
                    "[P2A] ts_ms=%d evt=prefill_deny_summary reasons=%s",
                    int(deny_now * 1000),
                    deny_stats,
                )

        # Reset batch_is_full to retry admission with a prefill adder.
        if running_batch.batch_is_full:
            _p2a_trace("[P2A] ts_ms=%d evt=bif_reset", int(time.time() * 1000))
        running_batch.batch_is_full = False

        if (
            running_batch.batch_is_full or len(self.waiting_queue) == 0
        ) and self.chunked_req is None:
            return None, running_batch

        running_bs = len(running_batch.reqs)
        # Skipped during a chunked prefill: that pass must proceed regardless.
        if (
            self.min_free_slots_delayer is not None
            and self.chunked_req is None
            and self.min_free_slots_delayer.should_delay(
                running_bs=running_bs,
                num_allocatable_reqs=self.get_num_allocatable_reqs(
                    running_bs, running_batch=running_batch
                ),
            )
        ):
            return None, running_batch

        # Ignore the check if self.chunked_req is not None.
        # In the non-PP case, when self.chunked_req is not None, num_allocatable_reqs should always be greater than 0,
        # as the space for the chunked requests has just been released.
        # In PP case, chunked requests (or dllm requests) can start in one microbatch and end in another microbatch, so the max_running_requests per microbatch should not be strict.
        # Instead, we should always allow chunked requests to be added, otherwise, there will be a memory leak.
        if (
            self.get_num_allocatable_reqs(running_bs, running_batch=running_batch) <= 0
            and self.chunked_req is None
            and not self.enable_priority_preemption
        ):
            running_batch.batch_is_full = True
            _p2a_trace("[P2A] ts_ms=%d evt=bif_set reason=allocatable", int(time.time() * 1000))
            return None, running_batch

        # Get priority queue
        self.policy.calc_priority(self.waiting_queue, running_batch)

        if TEST_RETRACT and running_bs > TEST_RETRACT_NO_PREFILL_BS:
            # If we are testing retraction and the running batch size exceeds
            # TEST_RETRACT_NO_PREFILL_BS, we skip the prefill to keep the requests
            # in the waiting queue.
            return None, running_batch

        if self.enable_ready_horizon:
            # M4 READY-first: stable partition, explicit priority > READY
            # > base policy; off = the calc_priority order unchanged.
            self.waiting_queue = self.ready_horizon.partition_ready_first(
                self.waiting_queue,
                tree=self.tree_cache,
                buffer_mode=self.server_args.hicache_host_memory_mode == "buffer_only",
                priority=self.enable_priority_scheduling,
            )

        # Determine chunked_prefill_size for this batch
        chunked_prefill_size = self.chunked_prefill_size
        if self.chunked_req is not None and self.enable_dynamic_chunking:
            history_len = len(self.chunked_req.prefix_indices)
            dynamic_size = self.predict_next_chunk_size(history_len)
            if dynamic_size is not None:
                chunked_prefill_size = dynamic_size

        # Prefill policy
        # Get BLOCK_M from the backend for tile-budget admission logic
        attn_backend = self.tp_worker.model_runner.attn_backend
        if hasattr(attn_backend, "extend_attention_block_m"):
            prefill_tile_block_m = attn_backend.extend_attention_block_m
        else:
            prefill_tile_block_m = 64  # Fallback for non-Triton backends

        adder = PrefillAdder(
            self.page_size,
            self.tree_cache,
            self.token_to_kv_pool_allocator,
            running_batch,
            self.new_token_ratio_tracker.current,
            self.max_prefill_tokens,
            chunked_prefill_size,
            running_bs if self.is_mixed_chunk else 0,
            self.priority_scheduling_preemption_threshold,
            max_prefill_bs=int(self.max_prefill_bs),
            max_running_requests=self.max_running_requests,
            prefill_max_requests=get_schedule().prefill_max_requests,
            prefill_delayer_single_pass=prefill_delayer_single_pass,
            dllm_config=self.dllm_config,
            waiting_queue_len=len(self.waiting_queue),
            prefill_tile_block_m=prefill_tile_block_m,
        )

        if self.chunked_req is not None:
            self.chunked_req.init_next_round_input()
            self.chunked_req = adder.add_chunked_req(self.chunked_req)

        if self.enable_lora:
            running_loras = {
                req.lora_id for req in running_batch.reqs if not req.finished()
            }
            # Account for LoRAs that are already loaded in the adder, such as chunked requests
            running_loras.update(req.lora_id for req in adder.can_run_list)

            if self.lora_drainer:
                self.lora_drainer.update_draining_state(
                    self.waiting_queue,
                    running_batch.reqs,
                )

        mamba_allocator = getattr(self.req_to_token_pool, "mamba_allocator", None)
        if mamba_allocator is not None:
            mamba_allocator.alloc_group_begin(len(self.waiting_queue))
        # Get requests from the waiting queue to a new prefill batch
        for req in self.waiting_queue:
            if self.enable_lora and not self._can_schedule_lora_req(req, running_loras):
                continue

            running_bs = len(running_batch.reqs)
            _p2a_trace("[P2A] ts_ms=%d evt=admission rid=%s pos=%d qlen=%d running_bs=%d can_run=%d", int(time.time() * 1000), req.rid, self.waiting_queue.index(req), len(self.waiting_queue), running_bs, len(adder.can_run_list))
            candidate_beam_width = (
                req.beam_group.beam_width if req.beam_group is not None else None
            )
            if len(adder.can_run_list) >= self.get_num_allocatable_reqs(
                running_bs,
                candidate_beam_width,
                running_batch=running_batch,
            ):
                running_batch.batch_is_full = True
                _p2a_trace("[P2A] ts_ms=%d evt=bif_set reason=can_run rid=%s", int(time.time() * 1000), req.rid)
            if self.disaggregation_mode == DisaggregationMode.PREFILL:
                # In prefill mode, prealloc queue and transfer queue can also take memory,
                # so we need to check if the available size for the actual available size.
                if len(adder.can_run_list) >= self.req_to_token_pool.available_size():
                    running_batch.batch_is_full = True
                    _p2a_trace("[P2A] ts_ms=%d evt=bif_set reason=disagg rid=%s", int(time.time() * 1000), req.rid)

            if running_batch.batch_is_full:
                if (
                    not self.enable_priority_preemption
                    or not adder.preempt_to_schedule(req, self.server_args)
                ):
                    break

            if self.enable_hicache_storage:
                prefetch_done = self.tree_cache.check_prefetch_progress(req.rid)
                if not prefetch_done:
                    # skip staging requests that are ongoing prefetch
                    continue
                # P2-1 M1b: consume a terminal prefetch outcome recorded by
                # the drain or by check_prefetch_progress itself (finalize /
                # revoke) before the WAIT skip below.
                self._feed_restore_terminal(req)
                if req.hicache_restore_state is RestoreState.WAIT_CAPACITY:
                    # Restore intent denied for capacity: keep waiting for a
                    # wake (T11/T12) instead of admitting into a full
                    # recompute; bounded by the WAIT timeout (T13).
                    continue
                # Pop the number of tokens loaded from storage (L3 hits)
                loaded_tokens = self.tree_cache.pop_prefetch_loaded_tokens(req.rid)
                if loaded_tokens > 0:
                    req.storage_hit_length = loaded_tokens
                    # [P2A] restore "satisfied": the issued prefetch's
                    # requested span is served from the restored KV this
                    # admission (loaded_tokens > 0), not merely IO-complete
                    # to host. This is the issued->satisfied service marker
                    # for the B_ep/B_fin per-finish windows (metric_compare
                    # pairs it against the last prefetch_issued of the same
                    # rid). The write-back reserve fix (writeback consumes
                    # the reserve) is what lets a chain persist to L3 so a
                    # later episode can satisfy at all.
                    logger.info(
                        "[P2A] ts_ms=%d evt=restore_success rid=%s n_tokens=%d",
                        int(time.time() * 1000),
                        req.rid,
                        loaded_tokens,
                    )
            req.init_next_round_input(self.tree_cache)
            if (
                self.enable_hicache_storage
                and self.server_args.hicache_host_memory_mode == "buffer_only"
            ):
                # Buffer mode: surface a staged prefetch as the request's host
                # hit (consumed through init_load_back) plus its SWA window,
                # which consumption allocates and the request lock pins —
                # uncharged, the batch alloc can OOM. Set AFTER
                # init_next_round_input (which recomputes host_hit). Mamba
                # (fenced in init_hicache) will need the same charge via
                # mamba_host_hit_length.
                held_tokens = self.tree_cache.staged_prefetch_tokens(req.rid)
                if held_tokens > 0:
                    req.host_hit_length = held_tokens
                    req.swa_host_hit_length = (
                        self.tree_cache.staged_prefetch_swa_tokens(req.rid)
                    )
            res = adder.add_one_req(
                req,
                has_chunked_req=(self.chunked_req is not None),
                truncation_align_size=self.truncation_align_size,
            )
            if res == AddReqResult.CONTINUE:
                origin = getattr(req, "hicache_prefetch_last_origin", None)
                logger.info(
                    "[P3] ts_ns=%d evt=admission.v2 schema=rh_admission.v2 "
                    "rid=%s rh_decision_id=%s hicache_prefetch_attempt_id=%s "
                    "hicache_prefetch_origin=%s ready_host_observed=%s "
                    "admission_monotonic_ns=%d can_run=%s",
                    time.monotonic_ns(),
                    req.rid,
                    getattr(req, "hicache_last_rh_decision_id", None),
                    getattr(req, "hicache_prefetch_last_attempt_id", None),
                    origin.name if origin is not None else "null",
                    (
                        "true"
                        if req.hicache_restore_state is RestoreState.READY
                        else "null"
                    ),
                    time.monotonic_ns(),
                    "true",
                )

            if self.enable_lora:
                running_loras.add(req.lora_id)

            if res != AddReqResult.CONTINUE:
                if res == AddReqResult.NO_TOKEN:
                    if self.enable_hicache_storage and self._restore_potential_for(req):
                        # P2-1 M1b (T6): quota deny with restore material:
                        # mark WAIT[DEVICE_QUOTA] and keep scanning (no
                        # batch_is_full -- the request is not admitted and
                        # does not stall the queue behind it; the WAIT skip
                        # above holds it until a T11 wake).
                        #
                        # P1 restore re-arm churn gate (phase2-peranchor): a
                        # request parked in MISS_RECOMPUTE (proven L3-missing
                        # this episode) MUST NOT re-enter WAIT[DEVICE_QUOTA]
                        # while the ANCHOR's per-anchor storage version is
                        # unchanged and the generation matches -- re-arming
                        # would re-probe the same missing prefix and miss
                        # again (the ~13ms WAIT -> RESTORING -> revoked:miss
                        # -> ADMISSION_DENY -> WAIT churn). Only THIS anchor's
                        # substantive durability change (write ack promotion /
                        # restore read-back / durable-belief clear), a change
                        # of the anchor itself (re-anchored to a different
                        # node / deleted-anchor self-heal to a new candidate),
                        # or a generation change overrides the sticky miss
                        # (re-armable -- this candidate's L3 coverage may
                        # really cover the prefix now). An unrelated chain's
                        # write ack advances only the global diagnostic
                        # counter and never re-arms.
                        #
                        # P4-round2 (点3): same-anchor version advance is the
                        # causal signal of a durability event, but clear
                        # (durable-belief removed) and evict-rebuild both bump
                        # the version WITHOUT leaving recoverable L3 material
                        # -- re-probing those is a structural guaranteed miss
                        # (the revoked:miss churn). The same-anchor re-arm
                        # therefore additionally requires the anchor chain to
                        # now actually hold durable L3 material
                        # (_miss_rearm_durable_coverage, O(depth) structural
                        # existence check -- no counters/TTL). Re-anchor and
                        # generation change keep re-arming unconditionally.
                        miss_rearm = self._miss_rearm_decision(req)
                        self._apply_restore_event(
                            req,
                            RestoreEvent.ADMISSION_DENY,
                            rearm_allowed=miss_rearm,
                        )
                        self._cleanup_not_added_req(req, adder)
                        continue
                    _p2a_trace("[P2A] ts_ms=%d evt=no_token rid=%s res=%s can_run=%d", int(time.time() * 1000), req.rid, res, len(adder.can_run_list))
                    if self.enable_hierarchical_cache:
                        # Set batch_is_full after making sure there are requests that can be served
                        running_batch.batch_is_full = len(adder.can_run_list) > 0 or (
                            not running_batch.is_empty()
                        )
                        _p2a_trace("[P2A] ts_ms=%d evt=bif_set reason=no_token_hicache rid=%s", int(time.time() * 1000), req.rid)
                    else:
                        running_batch.batch_is_full = True
                        _p2a_trace("[P2A] ts_ms=%d evt=bif_set reason=no_token rid=%s", int(time.time() * 1000), req.rid)
                elif res == AddReqResult.RESTORE_DENIED:
                    # P2-1 M1b (T7): host material exists but the device
                    # quota for load-back was transiently unavailable: mark
                    # WAIT[DEVICE_QUOTA] and keep scanning (design C4).
                    logger.info(
                        "[P2A] ts_ms=%d evt=restore_loadback_fail rid=%s",
                        int(time.time() * 1000),
                        req.rid,
                    )
                    self._apply_restore_event(req, RestoreEvent.LOAD_BACK_FAIL)
                    self._cleanup_not_added_req(req, adder)
                    continue
                self._cleanup_not_added_req(req, adder)
                break

        if mamba_allocator is not None:
            mamba_allocator.alloc_group_end()

        # Update waiting queue
        can_run_list: List[Req] = adder.can_run_list
        if len(can_run_list) == 0:
            return None, running_batch

        can_run_set = set(can_run_list)
        self.waiting_queue = [x for x in self.waiting_queue if x not in can_run_set]
        if adder.preempt_list:
            for req in adder.preempt_list:
                self._add_request_to_queue(req)

        if adder.new_chunked_req is not None:
            # Update chunked prefill
            assert self.chunked_req is None
            self.chunked_req = adder.new_chunked_req

        if self.chunked_req is not None:
            self.chunked_req.inflight_middle_chunks += 1

        set_time_batch(can_run_list, "set_forward_entry_time")

        # Create a new batch
        new_batch = ScheduleBatch.init_new(
            can_run_list,
            self.req_to_token_pool,
            self.token_to_kv_pool_allocator,
            self.tree_cache,
            self.model_config,
            self.enable_overlap,
            self.spec_algorithm,
            chunked_req=self.chunked_req,
        )

        new_batch.contains_last_prefill_chunk = (
            self.chunked_req is None or len(can_run_list) != 1
        )

        if self.enable_hierarchical_cache:
            # todo (zhiqiang): disable cuda graph execution if hicache loading triggered
            new_batch.hicache_consumer_index = (
                self.tree_cache.ready_to_load_host_cache()
            )

        new_batch.prepare_for_extend()

        if self.tp_worker.model_runner.prefill_aware_swa:
            for req in can_run_list:
                req.swa_evict_floor = req.extend_range.end

        # Record prefill stats for logging after forward.
        new_batch.prefill_stats = PrefillStats.from_adder(
            adder,
            running_batch.reqs,
            self.enable_priority_scheduling,
            num_pending_tokens=self.load_inquirer._get_num_pending_tokens(
                chunk_deduct=(
                    self.chunked_req.extend_range.length
                    if self.chunked_req is not None
                    else 0
                ),
            ),
        )

        # Mixed-style chunked prefill
        if (
            self.is_mixed_chunk
            and not running_batch.is_empty()
            and not (new_batch.return_logprob or running_batch.return_logprob)
            # mix_with_running cats input_ids but not input_embeds — shapes would mismatch
            and new_batch.input_embeds is None
            # Beam member rows are not supported inside a mixed extend batch.
            and all(r.beam_group is None for r in running_batch.reqs)
        ):
            # TODO (lianmin): support return_logprob + mixed chunked prefill
            running_batch.filter_batch()
            if not running_batch.is_empty():
                running_batch.prepare_for_decode()
                new_batch.mix_with_running(running_batch)
                new_batch.decoding_reqs = running_batch.reqs
            running_batch = ScheduleBatch(
                reqs=[], batch_is_full=running_batch.batch_is_full
            )
        else:
            new_batch.decoding_reqs = None

        return new_batch, running_batch

    def _can_schedule_lora_req(
        self, req: Req, running_loras: set[Optional[str]]
    ) -> bool:
        """
        Check if a LoRA request can be scheduled.

        This method checks two conditions:
        1. The drainer allows scheduling (based on draining state)
        2. The LoRA adapter can be loaded (either already running or can be added)
        """
        if self.lora_drainer and not self.lora_drainer.can_schedule(req):
            return False

        if req.lora_id in running_loras:
            return True

        if self.enable_lora_overlap_loading:
            # For overlapping loading of LoRA weights with computation, we will load each
            # adapter one at a time, as opposed to loading them in one batch
            return self.lora_overlap_loader.try_overlap_load_lora(
                req.lora_id, running_loras
            )
        else:
            new_lora_set = {req.lora_id} | running_loras
            return self.tp_worker.model_runner.lora_manager.validate_lora_batch(
                new_lora_set
            )

    def update_running_batch(self, batch: ScheduleBatch) -> Optional[ScheduleBatch]:
        """Update the current running decoding batch."""
        initial_bs = batch.batch_size()

        batch.filter_batch()
        if batch.is_empty():
            batch.batch_is_full = False
            return batch

        # Check if decode out of memory
        if (kv_full_retract_flag := not batch.check_decode_mem()) or (
            TEST_RETRACT and self.forward_ct % TEST_RETRACT_INTERVAL == 0
        ):
            old_available_tokens = self.token_to_kv_pool_allocator.available_size()
            old_ratio = self.new_token_ratio_tracker.current
            mamba_allocator = getattr(
                self.tree_cache.req_to_token_pool, "mamba_allocator", None
            )
            old_mamba_available = (
                mamba_allocator.available_size()
                if mamba_allocator is not None
                else None
            )
            retracted_reqs, new_token_ratio, reqs_to_abort = batch.retract_decode()
            new_available_tokens = self.token_to_kv_pool_allocator.available_size()
            new_token_gained = new_available_tokens - old_available_tokens
            mamba_num_gained = (
                mamba_allocator.available_size() - old_mamba_available
                if mamba_allocator is not None
                else None
            )

            self.metrics_reporter.num_retracted_reqs = len(retracted_reqs)
            if self.metrics_reporter.enable_metrics and len(retracted_reqs) > 0:
                self.metrics_reporter.metrics_collector.increment_retracted_reqs(
                    num_retracted_reqs=len(retracted_reqs),
                    num_retracted_input_tokens=sum(
                        len(r.origin_input_ids) for r in retracted_reqs
                    ),
                    num_retracted_output_tokens=sum(
                        len(r.output_ids) for r in retracted_reqs
                    ),
                )
            self.new_token_ratio_tracker.current = new_token_ratio
            for req in reqs_to_abort:
                abort_reason: FINISH_ABORT = req.to_finish
                self.ipc_channels.send_to_tokenizer.send_output(
                    _make_abort_req(req, finished_reason=abort_reason.to_json()),
                    req,
                )
            for req in reqs_to_abort:
                # Member rows were freed inside retract_decode; the group only
                # has to leave the live set.
                self.beam_coordinator.retire_group(req)

            msg_prefix = (
                "KV cache pool is full. Retract requests. "
                if kv_full_retract_flag
                else "Testing retraction. "
            )
            msg_details = f"#retracted_reqs: {len(retracted_reqs)}, #new_tokens_gained: {new_token_gained}"
            if mamba_num_gained is not None:
                msg_details += f", #mamba_num_gained: {mamba_num_gained}"
            if kv_full_retract_flag:
                msg_details += (
                    f", #new_token_ratio: {old_ratio:.4f} -> {new_token_ratio:.4f}"
                )
            logger.warning(msg_prefix + msg_details)

            for req in retracted_reqs:
                self._add_request_to_queue(req, is_retracted=True)
        else:
            self.new_token_ratio_tracker.decay_step()

        if batch.batch_size() < initial_bs:
            batch.batch_is_full = False

        if batch.is_empty():
            return batch

        # Update batch tensors
        batch.prepare_for_decode()
        return batch

    def record_batch_in_overlap(self, batch: ScheduleBatch):
        # FIXME(lsyin): hacky way to keep a reference to avoid GPU tensors being freed by torch GC
        # NOTE: More Reliable: record all tensors into the forward stream
        # NOTE: - for all future tensors, we shall always read from future map
        #       - for all non-future tensors (produced only by schedule stream),
        #       we shall keep its reference not being release during all the forwarding pass
        # Snapshot all fields: spec V2 rebinds seq_lens / spec_info mid-forward.
        attr_snapshot = [
            getattr(batch, f.name, None) for f in dataclasses.fields(batch)
        ]
        self.batch_record_ct = (self.batch_record_ct + 1) % 2
        # List (not tuple) so that workers can register additional refs via
        # GenerationBatchResult.extra_keep_alive_refs after forward returns.
        self.batch_record_buf[self.batch_record_ct] = [batch, attr_snapshot]

    @contextmanager
    def _forward_isolation(self, batch: ScheduleBatch, *, overlap: bool):
        """Make SB transactional across one forward (overlap and non-overlap).

        1. Snapshot SB fields so V2's mid-forward mutations (forward_mode /
           input_ids / seq_lens / spec_info / ...) can be undone. V1 / non-spec
           only need sampling_info restored - V1 carries spec_info forward as
           next-iter draft input.
        2. Substitute sampling_info with a forward-only copy (orchestrator=None,
           shares the pre-accumulated penalty buffer) so V2's multiple init_new
           calls don't double-accumulate penalties.
        3. (overlap=True only) Pin (batch, snapshot) into batch_record_buf
           for 2 iters so GPU tensors in the snapshot survive the caching
           allocator past the forward stream. Must run AFTER the sampling_info
           swap so the forward-only copy gets pinned. The non-overlap (sync) path
           runs on a single stream and doesn't allocate batch_record_buf, so it
           passes overlap=False.
        """
        # 1. snapshot
        snapshot_v2_full = not batch.spec_algorithm.is_none()
        sched_snapshot = (
            {f.name: getattr(batch, f.name) for f in dataclasses.fields(batch)}
            if snapshot_v2_full
            else None
        )
        sched_sampling_info = batch.sampling_info

        # 2. sampling_info substitute
        if sched_sampling_info is not None:
            batch.sampling_info = sched_sampling_info.copy_for_forward()

        # 3. pin for 2-iter tensor lifetime (overlap path only)
        if overlap:
            self.record_batch_in_overlap(batch)

        try:
            yield
        finally:
            if snapshot_v2_full:
                for name, value in sched_snapshot.items():
                    setattr(batch, name, value)
            else:
                batch.sampling_info = sched_sampling_info

    @scheduler_nvtx_method("scheduler.run_batch")
    def run_batch(
        self,
        batch: ScheduleBatch,
        pp_proxy_tensors: Optional[PPProxyTensors] = None,
    ) -> Union[GenerationBatchResult, EmbeddingBatchResult]:
        """Run a batch."""
        self.forward_ct += 1
        batch.forward_iter = self.forward_ct
        batch.launch_ts = time.monotonic()
        batch.after_idle_gap = self._sched_idled
        self._sched_idled = False
        try:
            _b15_log({"evt": "pa_batch",
                      "step_kind": ("decode" if batch.forward_mode.is_decode()
                                    else "prefill" if batch.forward_mode.is_extend()
                                    else "other"),
                      "batch_size": len(batch.reqs),
                      "forward_iter": self.forward_ct,
                      "consumer_index": int(batch.hicache_consumer_index)})
        except Exception:
            pass

        if self.scripted_scheduler_hook is not None:
            self.scripted_scheduler_hook.on_run_batch(batch)

        # Whether to run the profiler
        self.profiler_manager._profile_batch_predicate(batch)
        if self.forward_sleep_time is not None:
            logger.info(f"Scheduler.run_batch sleep {self.forward_sleep_time}s")
            time.sleep(self.forward_sleep_time)

        # Place holder handling for pd-disagg decode event loop
        if batch.forward_mode.is_prebuilt():
            return self._run_batch_prebuilt(batch)

        # PD prefill: early-send cached prefix KV, overlapping the suffix forward.
        if self.disaggregation_mode == DisaggregationMode.PREFILL:
            for req in batch.reqs:
                self.maybe_send_cached_prefix_chunk(req)

        # Run forward
        if self.is_generation:
            if self.enable_overlap:
                # Self-gates on batch.spec_info.future_indices; non-spec_v2
                # no-ops (ForwardBatch.init_new lazily computes the sum).
                self.future_map.resolve_seq_lens_cpu(batch)
                if self._confidence_budget_prepare is not None:
                    self._confidence_budget_prepare(batch, self.future_map)

                with self.forward_stream_ctx:
                    self.forward_stream.wait_stream(self.schedule_stream)
                    # resolve consumes SB staging (prefill_input_ids_cpu /
                    # mix_running_indices). Run OUTSIDE isolation so the
                    # snapshot captures the post-consume state — restoring
                    # post-forward must not un-consume staging.
                    resolve_forward_inputs(batch, self.future_map)

                    with self._forward_isolation(batch, overlap=True):
                        future_indices = batch.req_pool_indices

                        # Spec_v2 fires on_publish mid-worker (between verify and
                        # draft_extend) so schedule prep can overlap with draft_extend.
                        # Non-spec has no later work — scheduler publishes after return.
                        fwd_kwargs = {}
                        if not batch.spec_algorithm.is_none():
                            fwd_kwargs["on_publish"] = partial(
                                self.future_map.publish, future_indices
                            )
                            # Grammar-overlap-capable workers advance the grammar FSM
                            # inside verify() before building the bitmask; hand them the
                            # barrier that resolves the previous batch's committed
                            # tokens (overlapping the target forward).
                            if batch.spec_algorithm.supports_grammar_overlap():
                                fwd_kwargs["grammar_barrier"] = (
                                    self._advance_pending_grammar
                                )

                        # FIXME: pp is not compatible with overlap
                        batch_result = self.model_worker.forward_batch_generation(
                            batch, **fwd_kwargs
                        )
                        if batch.spec_algorithm.is_none():
                            self.future_map.publish(future_indices, batch.seq_lens + 1)
                        # Park any refs the worker wants kept alive 2 iters
                        # (cross-stream tensor lifetime; pinned in the same
                        # ring slot as the SB attr snapshot).
                        if batch_result.extra_keep_alive_refs:
                            self.batch_record_buf[self.batch_record_ct].extend(
                                batch_result.extra_keep_alive_refs
                            )
                        if self.enable_unified_memory:
                            # Record a `forward_done` event after the forward (before
                            # copy_to_cpu); lazy-compaction `_flush` gates src reuse on
                            # it. Only the unified pool's allocator exposes these hooks.
                            allocator = self.token_to_kv_pool_allocator
                            forward_done = self.device_module.Event()
                            forward_done.record(stream=self.forward_stream)
                            allocator.set_latest_forward_done_event(forward_done)
                            # Write-set classification: hand the allocator this
                            # forward's virtual out_cache_loc as a tensor ref (no GPU work).
                            allocator.set_inflight_forward(
                                forward_done,
                                batch.out_cache_loc,
                            )
                        # FIXME(lsyin): maybe move this to forward_batch_generation
                        batch_result.copy_done = self.device_module.Event()
                        if batch_result.delay_sample_func is None:
                            self._relay_forward_payload(
                                batch, future_indices, batch_result
                            )
                            if _is_hip:
                                # Cross-stream sync costs more than the tiny D2H it
                                # overlaps.
                                batch_result.copy_to_cpu(
                                    return_logprob=batch.return_logprob,
                                    return_hidden_states=batch.return_hidden_states,
                                )
                            else:
                                # Result D2H on copy_stream overlaps the next forward
                                # instead of serializing on forward_stream; it's a leaf
                                # gated by copy_done, so nothing on forward_stream waits.
                                self.copy_stream.wait_stream(self.forward_stream)
                                with self.copy_stream_ctx:
                                    batch_result.copy_to_cpu(
                                        return_logprob=batch.return_logprob,
                                        return_hidden_states=batch.return_hidden_states,
                                    )
                        else:
                            batch_result.future_indices = future_indices

                # Next-iter input_ids relayed via future_map.
                batch.input_ids = None

                if not batch.spec_algorithm.is_none():
                    batch.spec_info = batch_result.next_draft_input
                    batch.spec_info.future_dsa_topk_indices_available = (
                        batch.spec_info.dsa_topk_indices is not None
                    )
                    batch.spec_info.future_indices = future_indices
            elif self.enable_pdmux and batch.forward_mode.is_split_prefill():
                resolve_forward_inputs(batch, self.future_map)
                batch_result = self.tp_worker.forward_batch_split_prefill(batch)
                self._relay_forward_payload(batch, batch.req_pool_indices, batch_result)
                batch.input_ids = None
                self._copy_auxiliary_output_to_cpu(batch, batch_result)
            elif not batch.spec_algorithm.is_none():
                # Non-overlap: drive the V2 worker synchronously (no
                # future_map relay / on_publish).
                resolve_forward_inputs(batch, self.future_map)
                with self._forward_isolation(batch, overlap=False):
                    batch_result = self.model_worker.forward_batch_generation(batch)
                # The isolation restore reverted the worker's in-forward SB edits;
                # re-apply what must carry to the next iter.
                batch.spec_info = batch_result.next_draft_input
                if batch_result.new_seq_lens is not None:
                    batch.seq_lens = batch_result.new_seq_lens
                    if batch.seq_lens_cpu is not None:
                        batch.seq_lens_cpu = batch_result.new_seq_lens.to("cpu")
                        batch.seq_lens_sum = int(batch.seq_lens_cpu.sum())
                batch.input_ids = None  # rebuilt next iter from draft_token
                self.update_cache_from_scheduler(batch, batch_result)
                # Sync D2H so the result processor can read CPU tensors.
                batch_result.copy_done = self.device_module.Event()
                batch_result.copy_to_cpu(
                    return_logprob=batch.return_logprob,
                    return_hidden_states=batch.return_hidden_states,
                )
            else:
                kwargs = (
                    {"pp_proxy_tensors": pp_proxy_tensors}
                    if self.spec_algorithm.is_none()
                    else {}
                )
                resolve_forward_inputs(batch, self.future_map)
                batch_result = self.model_worker.forward_batch_generation(
                    batch, **kwargs
                )
                if batch_result.has_sampled_token_ids:
                    # Non-spec: relay via future_map, gathered next iter.
                    self._relay_forward_payload(
                        batch, batch.req_pool_indices, batch_result
                    )
                    batch.input_ids = None
                self.update_cache_from_scheduler(batch, batch_result)
                self._copy_auxiliary_output_to_cpu(batch, batch_result)

            # These 2 values are needed for processing the output, but the values can be
            # modified by overlap schedule. So we have to copy them here so that
            # we can use the correct values in output processing.
            if batch.return_logprob or batch.return_hidden_states:
                batch_result.extend_input_len_per_req = [
                    req.extend_range.length if req.extend_range is not None else 0
                    for req in batch.reqs
                ]
            else:
                batch_result.extend_input_len_per_req = None

            if batch.return_logprob:
                batch_result.extend_logprob_start_len_per_req = (
                    batch.extend_logprob_start_lens
                )
            else:
                batch_result.extend_logprob_start_len_per_req = None

            ret = batch_result
        else:  # embedding or reward model
            if self.enable_overlap:
                self.record_batch_in_overlap(batch)
                with self.forward_stream_ctx:
                    self.forward_stream.wait_stream(self.schedule_stream)
                    resolve_forward_inputs(batch, self.future_map)
                    pooler_output, can_run_cuda_graph = (
                        self.tp_worker.forward_batch_embedding(batch)
                    )
                    ret = EmbeddingBatchResult(
                        embeddings=pooler_output.embeddings,
                        pooled_hidden_states=pooler_output.pooled_hidden_states,
                        can_run_cuda_graph=can_run_cuda_graph,
                    )
                    ret.copy_to_cpu()
            else:
                resolve_forward_inputs(batch, self.future_map)
                pooler_output, can_run_cuda_graph = (
                    self.tp_worker.forward_batch_embedding(batch)
                )
                ret = EmbeddingBatchResult(
                    embeddings=pooler_output.embeddings,
                    pooled_hidden_states=pooler_output.pooled_hidden_states,
                    can_run_cuda_graph=can_run_cuda_graph,
                )

        self._maybe_report_active_ranks()

        return ret

    def _maybe_report_active_ranks(self) -> None:
        if not (
            self.enable_dp_attention and get_exec().moe.elastic_ep_backend is not None
        ):
            return
        from sglang.srt.elastic_ep.elastic_ep import ElasticEPStateManager

        inst = ElasticEPStateManager.instance()
        if inst is not None and inst.active_ranks_cpu is not None:
            self.ipc_channels.send_to_tokenizer.send_output(
                ActiveRanksOutput(
                    status=[bool(x) for x in inst.active_ranks_cpu.tolist()]
                )
            )
        else:
            logger.debug("[Elastic EP] active rank state is unavailable")
            return

        model_runner = self.tp_worker.model_runner
        pending = model_runner._pending_elastic_scale_update
        if pending is not None:
            self.ipc_channels.send_to_tokenizer.send_output(pending)
            model_runner._pending_elastic_scale_update = None

    def _relay_forward_payload(
        self,
        batch: ScheduleBatch,
        future_indices: torch.Tensor,
        batch_result: GenerationBatchResult,
    ) -> None:
        """Stash this iter's relay payload for next iter's resolve_forward_inputs."""
        if self.spec_algorithm.is_ngram():
            if batch_result.next_draft_input is not None:
                payload = RelayPayload.from_ngram(batch_result.next_draft_input)
                self.future_map.stash(future_indices, payload)
            return
        if batch_result.next_draft_input is not None:
            payload = RelayPayload.from_draft_input(batch_result.next_draft_input)
        elif batch_result.has_sampled_token_ids:
            payload = RelayPayload(bonus_tokens=batch_result.next_token_ids)
        else:
            return
        if batch.beam_tail is not None:
            # The worker sliced the tail off before sampling, so sampled tokens
            # cover only the reqs-aligned rows; the coordinator relays the rest.
            future_indices = future_indices[: batch.beam_tail.num_base_rows]
        self.future_map.stash(future_indices, payload)
        self.beam_coordinator.maybe_select_and_relay(
            batch, batch_result, chunked_req=self.chunked_req
        )

    def _copy_auxiliary_output_to_cpu(
        self,
        batch: ScheduleBatch,
        result: GenerationBatchResult,
    ) -> None:
        logits_output = result.logits_output
        if (
            logits_output is None
            or logits_output.auxiliary_device_output is None
            or result.auxiliary_host_output is not None
        ):
            return
        # PP transports the device output to the first rank before copying it.
        if self.ps.pp_size > 1:
            return
        if result.copy_done is not None:
            raise RuntimeError(
                "generation result has an uncopied auxiliary output after its "
                "device-to-host copy was scheduled"
            )
        result.copy_done = self.device_module.Event()
        result.copy_to_cpu(
            return_logprob=batch.return_logprob,
            return_hidden_states=batch.return_hidden_states,
        )

    def launch_batch_sample_if_needed(
        self, batch_result: GenerationBatchResult, cur_batch: ScheduleBatch
    ) -> Union[GenerationBatchResult]:
        # TODO(lsyin): make the delayed sample a default behavior after
        # unifying the forward_batch_generation interface (related to spec V2).
        if batch_result is None or batch_result.delay_sample_func is None:
            return

        with self.forward_stream_ctx:
            self.forward_stream.wait_stream(self.schedule_stream)
            _batch_result = batch_result.delay_sample_func()
            assert _batch_result is batch_result
            # Delay-sample is non-spec only; relays the sampled bonus tokens.
            self._relay_forward_payload(
                cur_batch, batch_result.future_indices, batch_result
            )

        # Run device-to-host copy on a separate stream to avoid blocking the
        # forward stream. The copy waits for the sampled result and can overlap
        # with subsequent forward computation.
        self.copy_stream.wait_stream(self.forward_stream)
        with self.copy_stream_ctx:
            batch_result.copy_to_cpu(
                return_logprob=cur_batch.return_logprob,
                return_hidden_states=cur_batch.return_hidden_states,
            )

        # Release the closure and large GPU tensors that are no longer needed.
        # The delay_sample_func closure captures forward_batch (which holds
        # sampling_info with vocab_mask) and logits_output (which holds
        # next_token_logits). Without clearing these, they stay alive via
        # batch_result in result_queue and batch_record_buf until the next
        # iteration, causing a steady VRAM leak with structured output.
        batch_result.delay_sample_func = None
        if batch_result.logits_output is not None:
            batch_result.logits_output.next_token_logits = None

    @scheduler_nvtx_method("scheduler.process_batch_result")
    def process_batch_result(
        self,
        batch: ScheduleBatch,
        result: Union[GenerationBatchResult, EmbeddingBatchResult],
    ):
        # Flush async trace ops here: in overlap mode this CPU work runs while
        # the next batch's GPU forward is in flight, giving free overlap.
        flush_trace_batch(batch.reqs)
        snapshot = self.publish_load_snapshot(force=batch.forward_mode.is_extend())
        # Router-facing gauge on the dedicated PUB socket, reusing the
        # snapshot above rather than walking the queues again.
        self.load_publisher.publish_load_stat(
            self.load_inquirer.get_loads,
            force=batch.forward_mode.is_extend(),
            snapshot=snapshot,
        )

        if batch.forward_mode.is_decode():
            self.batch_result_processor.process_batch_result_decode(batch, result)
        elif batch.forward_mode.is_extend():
            if batch.is_dllm():
                self.process_batch_result_dllm(batch, result)
            elif self.disaggregation_mode == DisaggregationMode.PREFILL:
                self.process_batch_result_disagg_prefill(batch, result)
            else:
                self.batch_result_processor.process_batch_result_prefill(batch, result)
        elif batch.forward_mode.is_prebuilt():
            self.batch_result_processor.process_batch_result_prebuilt(batch)
        elif batch.forward_mode.is_idle():
            self.batch_result_processor.process_batch_result_idle(batch, result)

        self._record_step_counters(batch, result)

        self.metrics_reporter.log_batch_result_stats(batch, result)

        # Emit forward pass metrics (every iteration when enabled)
        if self.enable_fpm:
            self.metrics_reporter._emit_forward_pass_metrics(batch, result)

        self._maybe_clear_mm_inputs(batch)
        self.maybe_send_health_check_signal()
        self.metrics_reporter.update_device_timer()

    def _record_step_counters(
        self, batch: ScheduleBatch, result: GenerationBatchResult
    ) -> None:
        mode = batch.forward_mode
        is_prefill = mode.is_extend_without_speculative()
        if not (is_prefill or mode.is_decode() or mode.is_target_verify()):
            return
        if all(is_health_check_generate_req(req) for req in batch.reqs):
            return
        prev = self._prev_step
        self._prev_step = (batch.forward_iter, batch.launch_ts, is_prefill)
        # An idle pass keeps forward_iter contiguous (forward_ct advances in run_batch).
        if prev is None or batch.after_idle_gap:
            return
        prev_iter, prev_ts, prev_is_prefill = prev
        if prev_iter + 1 != batch.forward_iter or prev_is_prefill != is_prefill:
            return
        step_us = int((batch.launch_ts - prev_ts) * 1e6)
        if not 0 < step_us < STEP_MAX_US:
            return
        if is_prefill:
            self.total_prefill_busy_us += step_us
            self.total_prefill_uncached_tokens += batch.extend_num_tokens
        else:
            batch_size = len(batch.reqs)
            _accumulate_decode_moment(
                self.decode_moment_totals,
                batch_size,
                step_us,
                batch_size + result.num_correct_drafts,
            )

    def maybe_send_health_check_signal(self):
        if self.return_health_check_ipcs:
            # Return some signal for the health check.
            # This is used to prevent the health check signal being blocked by long context prefill.
            # However, one minor issue is that this code path does not check the status of detokenizer manager.
            self.ipc_channels.send_to_tokenizer.send_output(
                HealthCheckOutput(
                    http_worker_ipc=self.return_health_check_ipcs.popleft()
                )
            )

    def add_external_corpus(
        self, recv_req: AddExternalCorpusReqInput
    ) -> Optional[AddExternalCorpusReqOutput]:
        if self.external_corpus_manager is None:
            return AddExternalCorpusReqOutput(
                success=False,
                message="Ngram speculative decoding is not enabled.",
            )
        return self.external_corpus_manager.add(recv_req)

    def remove_external_corpus(
        self, recv_req: RemoveExternalCorpusReqInput
    ) -> RemoveExternalCorpusReqOutput:
        if self.external_corpus_manager is None:
            return RemoveExternalCorpusReqOutput(
                success=False,
                message="Ngram speculative decoding is not enabled.",
            )
        return self.external_corpus_manager.remove(recv_req)

    def list_external_corpora(
        self, recv_req: ListExternalCorporaReqInput
    ) -> ListExternalCorporaReqOutput:
        if self.external_corpus_manager is None:
            return ListExternalCorporaReqOutput(
                success=False,
                message="Ngram speculative decoding is not enabled.",
            )
        return self.external_corpus_manager.list(recv_req)

    def clear_hicache_storage_wrapped(self, recv_req: ClearHiCacheReqInput):
        if self.enable_hierarchical_cache:
            self.tree_cache.clear_storage_backend()
            logger.info("Hierarchical cache cleared successfully!")
            if_success = True
        else:
            logging.warning("Hierarchical cache is not enabled.")
            if_success = False
        return ClearHiCacheReqOutput(success=if_success)

    def on_idle(self):
        """Idle housekeeping: guard, check, metrics, reset, sleep."""
        # Flush any health-check signal deferred while the engine was busy.
        self.maybe_send_health_check_signal()

        # Publish before the fully-idle gate: a no-batch-but-not-idle stall
        # (queues parked under KV pressure / disagg transfer) has no
        # process_batch_result to publish the growing gauge, and gating here
        # froze /get_loads, DP balancing, and the LoadStat for the stall. This
        # path spins without sleeping, so a wall-clock floor bounds the
        # O(queue) get_loads for both sinks; the fully-idle publish runs
        # post-flush below.
        if not self.is_fully_idle():
            now = time.monotonic()
            if now - self._last_stall_publish_ts >= LOAD_STALL_REFRESH_S:
                self._last_stall_publish_ts = now
                snapshot = self.publish_load_snapshot(force=True)
                self.load_publisher.publish_load_stat(
                    self.load_inquirer.get_loads, force=True, snapshot=snapshot
                )
            return

        if self.enable_unified_memory:
            try:
                self.token_to_kv_pool_allocator.flush_opportunistic()
            except Exception:
                pass

        # memory leak check (skipped for hisparse — pool counters intentionally
        # diverge during host-backup, see _get_swa_token_info clamp).
        # Also skipped while deferred KV releases are pending: they hold pages out
        # of the allocator by design, so the pool is transiently below `total` and
        # would trip the idle leak invariant. Resumes once the holds resolve.
        deferred_pending = (
            self.disaggregation_mode == DisaggregationMode.DECODE
            and self.disagg_decode_transfer_queue.has_pending_deferred_releases()
        )
        if not self.enable_hisparse and not deferred_pending:
            has_leak, messages = self.invariant_checker._check_all_pools(
                self.pool_stats_observer.get_pool_stats(),
            )
            if has_leak:
                self.invariant_checker._report_leak("pool", "\n".join(messages))
            self.invariant_checker._check_req_pool()

        # tree cache sanity check
        self.invariant_checker._check_tree_cache()

        # metrics every 30s
        self.metrics_reporter._maybe_log_idle_metrics()

        # kv event publishing
        self.kv_events_publisher.publish_kv_events()

        # reset token ratio
        self.new_token_ratio_tracker.reset()

        # Fully-idle publish, post-flush so the gauge reflects compacted KV.
        # Forced (immediate) so the busy->idle transition is never delayed.
        snapshot = self.publish_load_snapshot(force=True)
        self.load_publisher.publish_load_stat(
            self.load_inquirer.get_loads, force=True, snapshot=snapshot
        )

        # sleep until next event
        self.maybe_sleep_on_idle()

    def is_fully_idle(self, for_health_check=False) -> bool:
        # Health check piggybacks on running requests in process_output.
        # Only running_batch + waiting_queue guarantee active GPU processing;
        # disagg queues (bootstrap/prealloc/transfer) may have items without
        # any request actually running on GPU — e.g. stuck handshake, full
        # KV cache, or stalled transfer — so they can't carry health info.
        # Batch running status
        idle = (
            self.running_batch.is_empty()
            and self.chunked_req is None
            and not self.dllm_manager.any_staging_reqs()
            and (self.last_batch is None or self.last_batch.is_empty())
            and (not self.enable_overlap or len(self.result_queue) == 0)
            and self._pp_microbatches_drained()
        )

        # Waiting queues: waiting + bootstrapping + preallocation + kv transfer (decode)
        idle &= len(self.waiting_queue) == 0

        if (
            for_health_check
            and not self._engine_paused
            and self.disaggregation_mode == DisaggregationMode.DECODE
            and self.disagg_decode_prealloc_queue is not None
        ):
            idle &= len(self.disagg_decode_prealloc_queue.retracted_queue) == 0

        if not for_health_check:
            # Grammar queue and prefill inflight queue may not produce batch
            # results instantly, but they still indicate the server is not idle.
            idle &= len(self.grammar_manager.grammar_queue) == 0
            if self.disaggregation_mode == DisaggregationMode.PREFILL:
                idle &= len(self.disagg_prefill_inflight_queue) == 0
                idle &= len(self.disagg_prefill_bootstrap_queue.queue) == 0

            if self.disaggregation_mode == DisaggregationMode.DECODE:
                idle &= len(self.disagg_decode_prealloc_queue.queue) == 0
                idle &= len(self.disagg_decode_prealloc_queue.retracted_queue) == 0
                idle &= len(self.disagg_decode_transfer_queue.queue) == 0
                if self.decode_offload_manager is not None:
                    idle &= len(self.decode_offload_manager.ongoing_offload) == 0

            # HiSparse: staging requests transitioning prefill -> decode
            if self.enable_hisparse:
                idle &= not self.hisparse_coordinator.has_ongoing_staging()

            # HiCache: in-flight async ops (GPU↔Host↔L3) must drain before
            # destructive operations like attach/detach/flush_cache.
            if self.enable_hierarchical_cache:
                tc = self.tree_cache
                idle &= len(tc.ongoing_write_through) == 0
                idle &= len(tc.ongoing_load_back) == 0
                if tc.enable_storage:
                    idle &= len(tc.ongoing_prefetch) == 0
                    idle &= len(tc.ongoing_backup) == 0
                    if self.server_args.hicache_host_memory_mode == "buffer_only":
                        # Queued writes, staged prefetches, and in-flight
                        # storage writes still hold host staging
                        # (buffer-mode unified tree only).
                        idle &= tc.buffer_pipeline.is_idle()

        return idle

    def _pp_microbatches_drained(self) -> bool:
        if self.ps.pp_size == 1:
            return True
        return all(x.is_empty() for x in self.running_mbs) and all(
            mb is None or mb.is_empty() for mb in self.mbs
        )

    def attach_hicache_storage_wrapped(
        self, recv_req: AttachHiCacheStorageReqInput
    ) -> AttachHiCacheStorageReqOutput:
        if not self.enable_hierarchical_cache:
            return AttachHiCacheStorageReqOutput(
                success=False, message="Hierarchical cache is not enabled."
            )

        if not self.is_fully_idle():
            return AttachHiCacheStorageReqOutput(
                success=False,
                message=(
                    "Reject attach: scheduler is not idle. "
                    f"#queue-req={len(self.waiting_queue)} "
                    f"#running-req={len(self.running_batch.reqs)}"
                ),
            )

        if not hasattr(self.tree_cache, "attach_storage_backend"):
            return AttachHiCacheStorageReqOutput(
                success=False,
                message="Current tree_cache implementation does not support dynamic attach.",
            )

        try:
            ok, msg = self.tree_cache.attach_storage_backend(
                storage_backend=recv_req.hicache_storage_backend,
                storage_backend_extra_config_json=recv_req.hicache_storage_backend_extra_config_json,
                served_model_name=get_serving().served_model_name,
                hicache_storage_prefetch_policy=recv_req.hicache_storage_prefetch_policy,
                hicache_write_policy=recv_req.hicache_write_policy,
            )
        except Exception as e:
            logger.exception("Attach HiCache storage backend failed with exception.")
            return AttachHiCacheStorageReqOutput(success=False, message=str(e))
        if ok:
            self.enable_hicache_storage = True
            hicache_fields = {
                "hicache_storage_backend": recv_req.hicache_storage_backend
            }
            if recv_req.hicache_storage_backend_extra_config_json is not None:
                hicache_fields["hicache_storage_backend_extra_config"] = (
                    recv_req.hicache_storage_backend_extra_config_json
                )
            if recv_req.hicache_storage_prefetch_policy is not None:
                hicache_fields["hicache_storage_prefetch_policy"] = (
                    recv_req.hicache_storage_prefetch_policy
                )
            if recv_req.hicache_write_policy is not None:
                hicache_fields["hicache_write_policy"] = recv_req.hicache_write_policy
            get_context().override("scheduler.attach_hicache", **hicache_fields)
            logger.info(
                f"Attached HiCache storage backend: {recv_req.hicache_storage_backend}"
            )
        return AttachHiCacheStorageReqOutput(success=ok, message=msg)

    def detach_hicache_storage_wrapped(
        self, recv_req: DetachHiCacheStorageReqInput
    ) -> DetachHiCacheStorageReqOutput:
        if not self.enable_hierarchical_cache:
            return DetachHiCacheStorageReqOutput(
                success=False, message="Hierarchical cache is not enabled."
            )

        if not self.is_fully_idle():
            return DetachHiCacheStorageReqOutput(
                success=False,
                message=(
                    "Reject detach: scheduler is not idle. "
                    f"#queue-req={len(self.waiting_queue)} "
                    f"#running-req={len(self.running_batch.reqs)}"
                ),
            )

        if not hasattr(self.tree_cache, "detach_storage_backend"):
            return DetachHiCacheStorageReqOutput(
                success=False,
                message="Current tree_cache implementation does not support dynamic detach.",
            )

        # Idempotent detach: even if scheduler thinks storage is disabled, we still
        # attempt best-effort cleanup in tree_cache (it may have leftover state).
        try:
            ok, msg = self.tree_cache.detach_storage_backend()
        except Exception as e:
            logger.exception("Detach HiCache storage backend failed with exception.")
            return DetachHiCacheStorageReqOutput(success=False, message=str(e))

        if ok or (not self.enable_hicache_storage):
            # Treat "already disabled / nothing to do" as success for idempotence.
            self.enable_hicache_storage = False
            get_context().override(
                "scheduler.detach_hicache",
                hicache_storage_backend=None,
                hicache_storage_backend_extra_config=None,
            )
            logger.info("Detached HiCache storage backend.")
            return DetachHiCacheStorageReqOutput(
                success=True, message=msg or "HiCache storage backend is detached."
            )

        return DetachHiCacheStorageReqOutput(success=False, message=msg)

    def flush_cache(self, empty_cache: bool = True):
        """Flush memory pools (e.g., KV cache, Mamba cache) and optionally empty device allocator cache."""
        if self.is_fully_idle():
            self.cur_batch_for_debug = None
            self.last_batch = None
            self.tree_cache.reset()
            self.req_to_token_pool.clear()
            self.token_to_kv_pool_allocator.clear()
            self.req_to_token_pool.reset_aux_cache_allocator()
            self.grammar_manager.clear()
            self.metrics_reporter.reset_metrics()

            if self.draft_worker:
                self.draft_worker.clear_cache_pool()

            if empty_cache:
                current_platform.empty_cache()
            # Per-DP-group leader logs once: ranks within a DP group are
            # state-synchronous, but DP groups may diverge.
            if self.metrics_reporter.is_stats_logging_rank:
                logger.info("Cache flushed successfully!")
            success = True
        else:
            logging.warning(
                f"Cache not flushed because there are pending requests. "
                f"#queue-req: {len(self.waiting_queue)}, "
                f"#running-req: {len(self.running_batch.reqs)}"
            )
            success = False
        return success

    def get_internal_state(self, recv_req: GetInternalStateReq):
        # Resolved config (pristine server_args + post-publish overrides) so a
        # readback reflects values changed via /set_internal_state, not startup.
        ret = get_context().resolved_server_args_dict()
        ret["world_size"] = compute_world_size(
            enable_dp_attention=get_parallel().enable_dp_attention,
            dp_size=get_parallel().dp_size,
            tp_size=get_parallel().tp_size,
            pp_size=get_parallel().pp_size,
        )
        ret["last_gen_throughput"] = self.metrics_reporter.last_gen_throughput
        draft_graph_memory_usage = (
            None if self.draft_worker is None else self.draft_worker.graph_memory_usage
        )
        ret["memory_usage"] = build_memory_usage(
            weight_gb=self.tp_worker.model_runner.weight_load_mem_usage,
            kv_cache_gb=self.token_to_kv_pool_allocator.get_kvcache().mem_usage,
            startup_available_gb=self.startup_available_gpu_memory_gb,
            token_capacity=self.max_total_num_tokens,
            token_capacity_swa=self.swa_tokens_per_layer,
            target_graph_memory_usage=self.tp_worker.graph_memory_usage,
            draft_graph_memory_usage=draft_graph_memory_usage,
        )
        ret["startup_time"] = self.startup_time
        ret["effective_max_running_requests_per_dp"] = self.max_running_requests

        if get_exec().moe.elastic_ep_backend is not None:
            from sglang.srt.elastic_ep.elastic_ep import ElasticEPStateManager

            ret["is_scaling_elastic_ep"] = ElasticEPStateManager.is_scaling()
            ret["effective_ep_size"] = ElasticEPStateManager.get_effective_ep_size()
            ret["pending_ep_size"] = ElasticEPStateManager.get_pending_ep_size()
            ret["scale_phase"] = ElasticEPStateManager.get_scale_phase()
            ret["elastic_ep_last_error"] = ElasticEPStateManager.get_last_error()

        if (
            not self.spec_algorithm.is_none()
            and self.metrics_reporter.spec_total_num_forward_ct > 0
        ):
            ret["avg_spec_accept_length"] = (
                self.metrics_reporter.spec_total_num_accept_tokens
                / self.metrics_reporter.spec_total_num_forward_ct
            )

        if RECORD_STEP_TIME:
            ret["step_time_dict"] = self.metrics_reporter.step_time_dict

        if self.spec_algorithm.is_dspark() and self.draft_worker is not None:
            info_record = self.draft_worker.dump_info_records()
            if info_record is not None:
                ret["dspark_info_record"] = info_record

        if envs.SGLANG_EXPOSE_OWN_ENV_VARS.get():
            ret["env_vars"] = exportable_env_vars()

        # A bound signal handler is not msgpack-serializable, and no reader
        # consumes it.
        ret.pop("custom_sigquit_handler", None)

        return GetInternalStateReqOutput(internal_state=msgspec_to_builtins(ret))

    def set_internal_state(self, recv_req: SetInternalStateReq):
        server_args_dict = recv_req.server_args
        args_allow_update = set(
            [
                "pp_max_micro_batch_size",
                "speculative_accept_threshold_single",
                "speculative_accept_threshold_acc",
                "dspark_force_budget_frac",
                "dspark_clear_info_records",
            ]
        )

        if_success = True
        for k, v in server_args_dict.items():
            if k not in args_allow_update:
                logging.warning(f"Updating {k} is not supported.")
                if_success = False
                break
            elif k == "pp_max_micro_batch_size" and (
                v > self.max_running_requests // self.ps.pp_size or v < 1
            ):
                logging.warning(
                    f"Updating {k} to {v} is rejected because it is out of the valid range [1, {self.max_running_requests // self.ps.pp_size}]."
                )
                if_success = False
                break
            elif k == "dspark_force_budget_frac":
                if not self.spec_algorithm.is_dspark() or not hasattr(
                    self.draft_worker, "set_dspark_forced_budget_frac"
                ):
                    logging.warning(
                        "dspark_force_budget_frac requires a DSpark draft worker."
                    )
                    if_success = False
                    break
                if v is not None and not (0.0 < float(v) <= 1.0):
                    logging.warning(
                        f"dspark_force_budget_frac must be in (0, 1] or null, got {v}."
                    )
                    if_success = False
                    break
            elif k == "dspark_clear_info_records":
                if not self.spec_algorithm.is_dspark() or not hasattr(
                    self.draft_worker, "clear_info_records"
                ):
                    logging.warning(
                        "dspark_clear_info_records requires a DSpark draft worker."
                    )
                    if_success = False
                    break

        if if_success:
            if (
                not self.spec_algorithm.is_none()
                and self.metrics_reporter.spec_total_num_forward_ct > 0
            ):
                avg_spec_accept_length = (
                    self.metrics_reporter.spec_total_num_accept_tokens
                    / self.metrics_reporter.spec_total_num_forward_ct
                )
                logger.info(f"{avg_spec_accept_length=}")
            self.metrics_reporter.spec_total_num_accept_tokens = (
                self.metrics_reporter.spec_total_num_forward_ct
            ) = 0
            # DSpark control keys are worker commands, not server args; route
            # them to the draft worker and keep them out of the override.
            remaining = dict(server_args_dict)
            frac = remaining.pop("dspark_force_budget_frac", None)
            if "dspark_force_budget_frac" in server_args_dict:
                self.draft_worker.set_dspark_forced_budget_frac(
                    None if frac is None else float(frac)
                )
            if remaining.pop("dspark_clear_info_records", None):
                self.draft_worker.clear_info_records()
            if remaining:
                get_context().override(source="update_server_args", **remaining)
            logger.info(f"Config updated via context override: {remaining}")

        return SetInternalStateReqOutput(updated=if_success)

    def save_remote_model(self, **kwargs):
        self.weight_updater.save_remote_model(kwargs)

    def save_sharded_model(self, **kwargs):
        self.weight_updater.save_sharded_model(kwargs)

    def handle_rpc_request(self, recv_req: RpcReqInput):
        # Handle RPC requests
        logger.info(
            f"handle_rpc_request: {recv_req.method}, param: {recv_req.parameters}"
        )

        success = True
        exec = None
        try:
            func = getattr(self, recv_req.method)
            if recv_req.parameters is not None:
                func(**recv_req.parameters)
            else:
                func()
        except Exception as e:
            success = False
            exec = e
            logger.error(f"Failed to call rpc {recv_req.method}: {str(e)}")

        barrier(group=self.tp_group.cpu_group)
        return RpcReqOutput(success=success, message="" if not exec else str(exec))

    def handle_update_weight_version(
        self, recv_req: UpdateWeightVersionReqInput
    ) -> UpdateWeightVersionReqOutput:
        self.record_weight_version_change(new_version=recv_req.new_version)
        return UpdateWeightVersionReqOutput()

    def record_weight_version_change(self, new_version: Optional[str]) -> None:
        if new_version is None or new_version == get_serving().weight_version:
            return

        old_version = get_serving().weight_version
        get_context().override("scheduler.weight_version", weight_version=new_version)

        live_reqs = {
            *self.collect_inflight_reqs(),
            *self.waiting_queue,
            *([self.chunked_req] if self.chunked_req is not None else []),
        }
        if self.hisparse_coordinator is not None:
            live_reqs.update(
                act.req for act in self.hisparse_coordinator.ack_staging_queue
            )
        num_recorded = record_weight_version_events(live_reqs, old_version=old_version)
        logger.info(
            f"Weight version changed. {old_version=} {new_version=} {num_recorded=}"
        )

    def collect_inflight_reqs(self) -> Set[Req]:
        if self.ps.pp_size == 1:
            inflight_batches = [self.running_batch, self.last_batch]
        else:
            inflight_batches = [*self.running_mbs, *self.mbs]
        return {
            req for batch in inflight_batches if batch is not None for req in batch.reqs
        }

    def abort_request(self, recv_req: AbortReq):
        if (chunked_req := self.chunked_req) is not None:
            if recv_req.abort_all or chunked_req.rid.startswith(recv_req.rid):
                self._pending_chunked_abort_req = chunked_req

        # todo hisparse, release resources for abort requests in hisparse coordinator
        # Abort requests still waiting for encoder embeddings (EPD language-only)
        if self.mm_receiver is not None:
            self.mm_receiver.abort_waiting_requests(recv_req)

        # Delete requests in the waiting queue
        to_del = []
        for i, req in enumerate(self.waiting_queue):
            if recv_req.abort_all or req.rid.startswith(recv_req.rid):
                to_del.append(i)

        # Sort in reverse order to avoid index issues when deleting
        for i in reversed(to_del):
            # Abort method 1: directly pop from the queue
            # This only works for requests that have not started anything.
            # We still need to send something back to TokenizerManager to clean up the state.
            req = self.waiting_queue.pop(i)
            self._remove_host_alloc_waiter(req.rid)
            self.beam_coordinator.retire_group(req)
            if self.enable_hicache_storage:
                # to release prefetch events associated with the request
                self.tree_cache.release_aborted_request(req.rid)
                self._release_prefetch_claim(
                    req,
                    getattr(req, "hicache_prefetch_active_attempt_id", None),
                    "abort",
                )
            self.ipc_channels.send_to_tokenizer.send_output(_make_abort_req(req), req)
            # For disaggregation decode mode, the request in the waiting queue has KV cache allocated.
            if self.disaggregation_mode == DisaggregationMode.DECODE:
                release_kv_cache(req, self.tree_cache)
            # For disaggregation prefill mode, free the metadata buffer index
            if self.disaggregation_mode == DisaggregationMode.PREFILL:
                bootstrap_pending = req.pending_bootstrap
                maybe_release_metadata_buffer(
                    req, self.req_to_metadata_buffer_idx_allocator
                )
                if (
                    bootstrap_pending
                    and hasattr(req, "disagg_kv_sender")
                    and req.disagg_kv_sender is not None
                ):
                    if hasattr(req.disagg_kv_sender, "abort"):
                        req.disagg_kv_sender.abort()

            # For mamba radix cache
            if (
                req.mamba_pool_idx is not None
                and self.disaggregation_mode != DisaggregationMode.DECODE
            ):
                release_kv_cache(req, self.tree_cache, is_insert=False)
            logger.debug(f"Abort queued request. {req.rid=}")

        if self.dllm_config is not None:
            for req in self.dllm_manager.pop_aborted_reqs(
                recv_req.abort_all, recv_req.rid
            ):
                if self.enable_hicache_storage:
                    self.tree_cache.release_aborted_request(req.rid)
                    self._release_prefetch_claim(
                        req,
                        getattr(req, "hicache_prefetch_active_attempt_id", None),
                        "abort",
                    )
                self.ipc_channels.send_to_tokenizer.send_output(
                    _make_abort_req(req), req
                )
                if (
                    req.req_pool_idx is not None
                    or getattr(req, "mamba_pool_idx", None) is not None
                ):
                    release_kv_cache(req, self.tree_cache, is_insert=False)
                logger.debug(f"Abort dLLM queued request. {req.rid=}")

        # Delete the requests in the grammar queue
        # Abort method 2: call `set_finish_with_abort`
        # The request will still run one prefill forward pass.
        # In this case, we change the input_ids to be only one token to make this prefill cheap.
        self.grammar_manager.abort_requests(recv_req)

        # Delete requests not in the waiting queue when PD disaggregation is enabled
        if self.disaggregation_mode == DisaggregationMode.PREFILL:
            # Abort requests that have not yet been bootstrapped
            for req in self.disagg_prefill_bootstrap_queue.queue:
                if recv_req.abort_all or req.rid.startswith(recv_req.rid):
                    logger.debug(f"Abort bootstrap queue request. {req.rid=}")
                    if self.enable_hicache_storage:
                        self.tree_cache.release_aborted_request(req.rid)
                        self._release_prefetch_claim(
                            req,
                            getattr(req, "hicache_prefetch_active_attempt_id", None),
                            "abort",
                        )

                    if hasattr(req.disagg_kv_sender, "abort"):
                        req.disagg_kv_sender.abort()
                    if self.ps.pp_size > 1:
                        prepare_abort(req, "Aborted by AbortReq.")

            # Abort in-flight requests
            for req in self.disagg_prefill_inflight_queue:
                if recv_req.abort_all or req.rid.startswith(recv_req.rid):
                    logger.debug(f"Abort inflight queue request. {req.rid=}")
                    if hasattr(req.disagg_kv_sender, "abort"):
                        req.disagg_kv_sender.abort()

        elif self.disaggregation_mode == DisaggregationMode.DECODE:
            # Abort requests that have not yet finished preallocation
            for decode_req in self.disagg_decode_prealloc_queue.queue:
                if recv_req.abort_all or decode_req.req.rid.startswith(recv_req.rid):
                    logger.debug(f"Abort prealloc queue request. {decode_req.req.rid=}")
                    decode_req.kv_receiver.abort()
                    if self.ps.pp_size > 1:
                        prepare_abort(decode_req.req, "Aborted by AbortReq.")

            # Abort requests waiting for kvcache to release tree cache
            for decode_req in self.disagg_decode_transfer_queue.queue:
                if recv_req.abort_all or decode_req.req.rid.startswith(recv_req.rid):
                    logger.debug(f"Abort transfer queue request. {decode_req.req.rid=}")
                    receiver = decode_req.kv_receiver
                    receiver.abort()
                    # Arm drain-ack accounting once the ABORT is sent, so acks
                    # arriving before this req is deferred (e.g. during the next
                    # forward step) are captured. A fresh set also drops stale acks
                    # from a prior request that reused this bootstrap_room. A
                    # redundant abort only re-wipes -- holds longer, never releases
                    # early -- so no transition guard is needed.
                    if (
                        receiver.kv_mgr.enable_deferred_decode_kv_release
                        and receiver.abort_notified
                    ):
                        receiver.kv_mgr.register_deferred_abort_room(
                            decode_req.req.bootstrap_room
                        )

            # Abort requests whose KV is already backed up for retraction.
            if self.disagg_decode_prealloc_queue.retracted_queue:
                remaining_retracted = []
                for decode_req in self.disagg_decode_prealloc_queue.retracted_queue:
                    if recv_req.abort_all or decode_req.rid.startswith(recv_req.rid):
                        retraction_discard(
                            decode_req,
                            self.tree_cache,
                            get_disagg().disaggregation_decode_retraction_backup,
                        )
                        self.ipc_channels.send_to_tokenizer.send_output(
                            _make_abort_req(decode_req), decode_req
                        )
                    else:
                        remaining_retracted.append(decode_req)
                self.disagg_decode_prealloc_queue.retracted_queue = remaining_retracted

        # Delete requests in the running batch
        for req in self.collect_inflight_reqs():
            if not req.finished() and (
                recv_req.abort_all or req.rid.startswith(recv_req.rid)
            ):
                # Abort method 3: set `to_finish`
                # The request will still run one decode forward pass.
                # Then we reuse all existing code to clean up the KV cache allocation.
                logger.debug(f"Abort running request. {req.rid=}")
                req.to_finish = FINISH_ABORT()

    def _pause_engine(self) -> Tuple[List[Req], int]:
        raise NotImplementedError()

    def pause_generation(self, recv_req: PauseGenerationReqInput):
        assert recv_req.mode in ("in_place", "retract")
        self._engine_paused = True

        if recv_req.mode == "in_place":
            # In-place pause: just set the flag and return immediately.
            # All scheduler state (running_batch, last_batch, chunked_req,
            # result_queue) is left untouched. On resume, the normal event
            # loop (get_next_batch_to_run) handles last_batch merge,
            # chunked_req cleanup, and overlap result processing through
            # the standard code paths. This avoids duplicating batch
            # manipulation logic and the accounting bugs that come with it.
            return

        if self.enable_overlap and self.last_batch:
            # Process the results of the last batch
            tmp_batch, tmp_result = self.result_queue.popleft()
            self.process_batch_result(tmp_batch, tmp_result)

        retract_reqs = [r for r in self.running_batch.reqs if not r.finished()]
        if (
            self.last_batch is not None
            and self.last_batch.forward_mode.is_extend()
            # Skip merge for disagg prefill: completed prefill requests are
            # already in disagg_prefill_inflight_queue. Merging them into
            # running_batch leaks them, since the prefill event loop never
            # calls update_running_batch to clean them up.
            and self.disaggregation_mode != DisaggregationMode.PREFILL
        ):
            retract_reqs += [r for r in self.last_batch.reqs if not r.finished()]

        if (
            self.chunked_req is not None
            and not self.chunked_req.finished()
            and self.chunked_req not in retract_reqs
            and self.disaggregation_mode != DisaggregationMode.PREFILL
        ):
            retract_reqs.append(self.chunked_req)

        self.last_batch = None
        self.cur_batch_for_debug = None

        if retract_reqs:
            # Decode-side retract always rebootstraps (recomputes the KV from
            # the prefill), so skip the device->host KV offload that release_req
            # would otherwise do; the offloaded copy would be immediately
            # discarded. Non-decode modes ignore offload_kv (they never offload).
            retract_all(
                reqs=retract_reqs,
                req_to_token_pool=self.req_to_token_pool,
                token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
                tree_cache=self.tree_cache,
                hisparse_coordinator=self.hisparse_coordinator,
                offload_kv=False,
            )
        self.running_batch.reqs = []
        for req in retract_reqs:
            if self.disaggregation_mode == DisaggregationMode.DECODE:
                if req.output_ids:
                    req.pd_rebootstrap_forced_output_id = req.output_ids.pop()
                req.pd_rebootstrap_in_progress = True
                req.time_stats.set_retract_time()
                self.disagg_decode_prealloc_queue.hold_rebootstrap(req)
            else:
                self._add_request_to_queue(req)
        self.running_batch.batch_is_full = False
        # In disagg-PREFILL, keep a live mid-chunk chunked_req rather than retract it:
        # freeing its KV under a live disagg KV-sender crashes pop_bootstrapped or
        # sends freed/reused KV to decode. Kept, it resumes prefill after the pause.
        # TODO(disagg-prefill-retract): tear the sender down (abort + release metadata
        # buffer + reset pending_bootstrap) before freeing KV, then retract for real.
        # Until then a weight-update pause leaves stale-weight prefix KV (off-policy).
        if self.disaggregation_mode != DisaggregationMode.PREFILL:
            self.chunked_req = None

        # Surface the paused state to dashboards immediately. The scheduler
        # event loop short-circuits before reaching ``on_idle`` while paused,
        # so without this hop ``gen_throughput`` retains its last non-zero
        # value and KV events are not flushed for the entire pause window
        # (e.g. across a weight update). Zero the gauge, force a one-shot
        # idle log by resetting the rate-limit timestamp, and flush pending
        # KV events.
        self.metrics_reporter.last_gen_throughput = 0.0
        if self.metrics_reporter.current_scheduler_metrics_enabled:
            self.metrics_reporter.metrics_collector.last_log_time = 0.0
            self.metrics_reporter._maybe_log_idle_metrics()
        self.kv_events_publisher.publish_kv_events()

    def continue_generation(self, recv_req: ContinueGenerationReqInput):
        if recv_req.torch_empty_cache:
            before_mb = torch.cuda.memory_reserved() / (1024 * 1024)
            torch.cuda.empty_cache()
            after_mb = torch.cuda.memory_reserved() / (1024 * 1024)
            logger.info(
                f"[continue_generation] torch.cuda.empty_cache() called: "
                f"reserved {before_mb:.1f} MB -> {after_mb:.1f} MB "
                f"(freed {before_mb - after_mb:.1f} MB)"
            )
        # Enqueue any rebootstrap requests that were staged during a
        # retract-mode pause. Deferring until resume keeps the preallocation
        # queue empty during the pause window (so an intervening weight update
        # can flush the cache) and recomputes the prefix KV under the updated
        # weights.
        if (
            self.disaggregation_mode == DisaggregationMode.DECODE
            and self.disagg_decode_prealloc_queue is not None
        ):
            self.disagg_decode_prealloc_queue.enqueue_held_rebootstrap()
        self._engine_paused = False

    def handle_scale_elastic_ep(
        self, recv_req: ScaleElasticEPReqInput
    ) -> ScaleElasticEPReqOutput:
        """Begin a pending elastic EP scale-up request."""
        from sglang.srt.elastic_ep.elastic_ep import ElasticEPStateManager

        old_ep_size = ElasticEPStateManager.get_effective_ep_size()
        new_ep_size = recv_req.new_ep_size
        max_ep_size = get_parallel().max_ep_size or old_ep_size

        logger.debug(
            "[Elastic EP][scale] request received: new_ep_size=%d "
            "old_ep_size=%d max_ep_size=%d",
            new_ep_size,
            old_ep_size,
            max_ep_size,
        )

        if new_ep_size <= old_ep_size:
            return ScaleElasticEPReqOutput(
                success=False,
                message=(
                    f"new_ep_size ({new_ep_size}) must be greater than current "
                    f"effective_ep_size ({old_ep_size})."
                ),
                old_ep_size=old_ep_size,
                new_ep_size=new_ep_size,
            )
        if new_ep_size > max_ep_size:
            return ScaleElasticEPReqOutput(
                success=False,
                message=(
                    f"new_ep_size ({new_ep_size}) exceeds --max-ep-size "
                    f"({max_ep_size}). Restart with a larger --max-ep-size."
                ),
                old_ep_size=old_ep_size,
                new_ep_size=new_ep_size,
            )
        if ElasticEPStateManager.is_scaling():
            return ScaleElasticEPReqOutput(
                success=False,
                message=(
                    "A previous scale operation has not completed yet. Wait until "
                    "all pending ranks have joined before issuing another scale."
                ),
                old_ep_size=old_ep_size,
                new_ep_size=new_ep_size,
                pending_ep_size=ElasticEPStateManager.get_pending_ep_size(),
                scale_phase=ElasticEPStateManager.get_scale_phase(),
            )

        if not ElasticEPStateManager.request_scale(new_ep_size):
            return ScaleElasticEPReqOutput(
                success=False,
                message=(
                    "Failed to queue elastic EP scale: no elastic state or "
                    "scale already pending."
                ),
                old_ep_size=old_ep_size,
                new_ep_size=new_ep_size,
                pending_ep_size=ElasticEPStateManager.get_pending_ep_size(),
                scale_phase=ElasticEPStateManager.get_scale_phase(),
            )
        if (eplb_manager := self.tp_worker.model_runner.eplb_manager) is not None:
            eplb_manager.disable_rebalance("elastic EP scale-up is pending")
        logger.debug(
            "[Elastic EP][scale] scale requested: target_ep_size=%d; "
            "waiting for a joining cohort",
            new_ep_size,
        )

        return ScaleElasticEPReqOutput(
            success=True,
            message=f"Scaling initiated from {old_ep_size} to {new_ep_size}",
            old_ep_size=old_ep_size,
            new_ep_size=new_ep_size,
            pending_ep_size=ElasticEPStateManager.get_pending_ep_size(),
            scale_phase=ElasticEPStateManager.get_scale_phase(),
        )

    def load_lora_adapter(
        self, recv_req: LoadLoRAAdapterReqInput
    ) -> LoadLoRAAdapterReqOutput:
        """In-place loading a new lora adapter from disk or huggingface."""

        result = self.tp_worker.load_lora_adapter(recv_req)
        return result

    def load_lora_adapter_from_tensors(
        self, recv_req: LoadLoRAAdapterFromTensorsReqInput
    ) -> LoadLoRAAdapterFromTensorsReqOutput:
        """In-place loading a new lora adapter from serialized tensors."""

        result = self.tp_worker.load_lora_adapter_from_tensors(recv_req)
        return result

    def unload_lora_adapter(
        self, recv_req: UnloadLoRAAdapterReqInput
    ) -> UnloadLoRAAdapterReqOutput:
        """Unload the lora adapter."""

        result = self.tp_worker.unload_lora_adapter(recv_req)
        return result

    def init_weights_send_group_for_remote_instance(
        self, recv_req: InitWeightsSendGroupForRemoteInstanceReqInput
    ):
        """Init the seed and client instance communication group."""
        success, message = self.tp_worker.init_weights_send_group_for_remote_instance(
            recv_req
        )
        return InitWeightsSendGroupForRemoteInstanceReqOutput(
            success=success, message=message
        )

    def send_weights_to_remote_instance(
        self, recv_req: SendWeightsToRemoteInstanceReqInput
    ):
        """Send the seed instance weights to the destination instance."""
        success, message = self.tp_worker.send_weights_to_remote_instance(recv_req)
        return SendWeightsToRemoteInstanceReqOutput(success=success, message=message)

    def slow_down(self, recv_req: SlowDownReqInput):
        t = recv_req.forward_sleep_time
        if t is not None and t <= 0:
            t = None
        self.forward_sleep_time = t
        return SlowDownReqOutput()

    def expert_distribution_handle(self, recv_req: ExpertDistributionReq):
        action = recv_req.action
        if action == ExpertDistributionReqType.START_RECORD:
            get_global_expert_distribution_recorder().start_record()
        elif action == ExpertDistributionReqType.STOP_RECORD:
            get_global_expert_distribution_recorder().stop_record()
        elif action == ExpertDistributionReqType.DUMP_RECORD:
            get_global_expert_distribution_recorder().dump_record()
        else:
            raise ValueError(f"Unrecognized ExpertDistributionReq value: {recv_req=}")
        return ExpertDistributionReqOutput()

    def open_session(self, recv_req: OpenSessionReqInput):
        output = self.session_controller.open(recv_req)
        if output.success and self.enable_session_radix_cache:
            self.tree_cache.open_radix_session(recv_req.session_id)
        if self.ps.pp_rank == 0 and self.ps.tp_rank == 0 and self.ps.attn_cp_rank == 0:
            return output
        return None

    def close_session(self, recv_req: CloseSessionReqInput):
        if self.enable_session_radix_cache:
            self.tree_cache.release_radix_session(recv_req.session_id)
        if (
            recv_req.session_id in self.session_controller
            or not self.enable_session_radix_cache
        ):
            self.session_controller.close(recv_req)

    def maybe_sleep_on_idle(self):
        if self.idle_sleeper is not None:
            self.idle_sleeper.maybe_sleep()

    def handle_freeze_gc(self, recv_req: FreezeGCReq):
        """Handle freeze_gc request: freeze scheduler's GC and forward to detokenizer."""
        freeze_gc("Scheduler")
        self.ipc_channels.send_to_detokenizer.send_output(recv_req, recv_req)
        return None

    def handle_shutdown(self, recv_req: ShutdownReq):
        # Break the event loop; the finally in run_scheduler_process releases resources.
        self.gracefully_exit = True
        return None

    def configure_logging(self, recv_req: ConfigureLoggingReq):
        if recv_req.log_level is not None:
            logging.getLogger().setLevel(recv_req.log_level.upper())
        self.ipc_channels.send_to_detokenizer.send_output(recv_req, recv_req)

    def handle_dumper_control(self, recv_req: DumperControlReqInput):
        from sglang.srt.debug_utils.dumper import dumper

        try:
            response: list = []
            if (
                not torch.distributed.is_initialized()
                or torch.distributed.get_rank() == 0
            ):
                response = dumper._http_manager.handle_request(
                    method=recv_req.method, body=recv_req.body
                )
            self.ipc_channels.send_to_tokenizer.send_output(
                DumperControlReqOutput(success=True, response=response), recv_req
            )
        except Exception as e:
            print(f"[Scheduler] handle_dumper_control error: {e}", flush=True)
            self.ipc_channels.send_to_tokenizer.send_output(
                DumperControlReqOutput(success=False, response=[], error=str(e)),
                recv_req,
            )

    # placeholder for override
    def update_cache_from_scheduler(
        self, schedule_batch: ScheduleBatch, batch_result: GenerationBatchResult
    ):
        pass


def dispatch_event_loop(scheduler: Scheduler):
    # The live PP property asserts before torch.distributed init (MLX stub).
    disaggregation_mode: DisaggregationMode = scheduler.disaggregation_mode
    if disaggregation_mode == DisaggregationMode.NULL:
        if scheduler.enable_pdmux:
            scheduler.event_loop_pdmux()
        elif get_parallel().pp_size > 1:
            scheduler.event_loop_pp()
        elif scheduler.enable_overlap_mlx:
            scheduler.event_loop_overlap_mlx()
        elif scheduler.enable_overlap:
            scheduler.event_loop_overlap()
        else:
            scheduler.event_loop_normal()
    elif disaggregation_mode == DisaggregationMode.PREFILL:
        if get_parallel().pp_size > 1:
            scheduler.event_loop_pp_disagg_prefill()
        elif scheduler.enable_overlap:
            scheduler.event_loop_overlap_disagg_prefill()
        else:
            scheduler.event_loop_normal_disagg_prefill()
    elif disaggregation_mode == DisaggregationMode.DECODE:
        if get_parallel().pp_size > 1:
            scheduler.event_loop_pp_disagg_decode()
        elif scheduler.enable_overlap:
            scheduler.event_loop_overlap_disagg_decode()
        else:
            scheduler.event_loop_normal_disagg_decode()


def configure_scheduler_process(
    server_args: ServerArgs,
    gpu_id: int,
    tp_rank: int,
    attn_cp_rank: int,
    moe_dp_rank: int,
    moe_ep_rank: int,
    pp_rank: int,
    dp_rank: Optional[int],
    display_tp_rank: Optional[int] = None,
    display_dp_rank: Optional[int] = None,
    display_moe_ep_rank: Optional[int] = None,
) -> Optional[int]:
    """Configure scheduler worker logging and process title.

    display_* ranks are cosmetic; runtime ranks stay local.
    """
    kill_itself_when_parent_died()

    # Generate the logger prefix
    if dp_rank is None and "SGLANG_DP_RANK" in os.environ:
        # [For Router] if env var "SGLANG_DP_RANK" exist, set dp_rank to the value of the env var
        dp_rank = int(os.environ["SGLANG_DP_RANK"])

    shown_dp = display_dp_rank if display_dp_rank is not None else dp_rank
    shown_tp = display_tp_rank if display_tp_rank is not None else tp_rank
    shown_moe_ep = (
        display_moe_ep_rank if display_moe_ep_rank is not None else moe_ep_rank
    )

    prefix = ""
    if shown_dp is not None:
        prefix += f" DP{shown_dp}"
    if get_parallel().pp_size > 1:
        prefix += f" PP{pp_rank}"
    if get_parallel().attn_cp_size > 1:
        prefix += f" ATTN_CP{attn_cp_rank}"
    if get_parallel().moe_dp_size > 1:
        prefix += f" MOE_DP{moe_dp_rank}"
    if get_parallel().tp_size > 1:
        prefix += f" TP{shown_tp}"
    if get_parallel().ep_size > 1:
        prefix += f" EP{shown_moe_ep}"

    # Config the process
    setproctitle.setproctitle(f"sglang::scheduler{prefix.replace(' ', '_')}")
    faulthandler.enable()

    # Configure the logger
    configure_logger(server_args, prefix=prefix)
    suppress_other_loggers()

    # Set cpu affinity to this gpu process
    if envs.SGLANG_SET_CPU_AFFINITY.get():
        set_gpu_proc_affinity(
            get_parallel().pp_size,
            get_parallel().tp_size,
            get_parallel().nnodes,
            gpu_id,
        )
    if not envs.SGLANG_NUMA_BIND_V2.get():
        numa_node = get_numa_node_if_available(server_args, gpu_id)
        if numa_node is not None:
            numa_bind_to_node(numa_node)

    return dp_rank


def run_scheduler_process(
    server_args: ServerArgs,
    port_args: PortArgs,
    gpu_id: int,
    tp_rank: int,
    attn_cp_rank: int,
    moe_dp_rank: int,
    moe_ep_rank: int,
    pp_rank: int,
    dp_rank: Optional[int],
    pipe_writer,
    display_tp_rank: Optional[int] = None,
    display_dp_rank: Optional[int] = None,
    display_moe_ep_rank: Optional[int] = None,
):
    # Load plugins so hooks can override Scheduler and its dependencies.
    load_plugins()
    # Publish before anything in this process reads configuration.
    publish(server_args, role="scheduler")
    dp_rank = configure_scheduler_process(
        server_args,
        gpu_id,
        tp_rank,
        attn_cp_rank,
        moe_dp_rank,
        moe_ep_rank,
        pp_rank,
        dp_rank,
        display_tp_rank=display_tp_rank,
        display_dp_rank=display_dp_rank,
        display_moe_ep_rank=display_moe_ep_rank,
    )
    parent_process = psutil.Process().parent()

    # Set up tracing
    if get_observability().enable_trace:
        process_tracing_init(
            get_observability().otlp_traces_endpoint,
            "sglang",
            trace_modules=get_observability().trace_modules,
        )
        thread_label = "Scheduler"
        if get_disagg().disaggregation_mode == "prefill":
            thread_label = "Prefill Scheduler"
        elif get_disagg().disaggregation_mode == "decode":
            thread_label = "Decode Scheduler"
        trace_set_thread_info(thread_label, tp_rank, dp_rank, pp_rank)

    # Create a scheduler and run the event loop
    scheduler = None
    try:
        scheduler = Scheduler(
            server_args,
            port_args,
            gpu_id,
            tp_rank,
            moe_ep_rank,
            pp_rank,
            attn_cp_rank,
            moe_dp_rank,
            dp_rank,
        )

        # Send initialization info back to the parent process
        pipe_writer.send(scheduler.get_init_info())

        # Run the event loop (blocks until a ShutdownReq sets gracefully_exit)
        scheduler.run_event_loop()

    except Exception:
        traceback = get_exception_traceback()
        logger.error(f"Scheduler hit an exception: {traceback}")
        parent_process.send_signal(signal.SIGQUIT)
        # Opt-in: SIGKILL the pgroup so sibling ranks don't spew thousands
        # of NCCL/TCPStore tracebacks before they finally die.
        if envs.SGLANG_KILLPG_ON_SCHEDULER_EXCEPTION.get():
            try:
                os.killpg(os.getpgrp(), signal.SIGKILL)
            except Exception:
                pass
    finally:
        if scheduler is not None:
            # FPM has a background ZMQ publisher thread that needs explicit
            # teardown to flush queued metrics and close the socket cleanly.
            scheduler.metrics_reporter._shutdown_fpm()
            # Graceful path only: on the exception path the GPU may be wedged
            # and the synchronize() in destroy() could itself hang.
            if scheduler.gracefully_exit:
                scheduler.release_host_resources()


def _make_abort_req(
    req: Req, finished_reason: Optional[FinishReasonDict] = None
) -> AbortReq:
    return AbortReq(
        rid=req.rid,
        finished_reason=finished_reason,
        weight_versions=compute_weight_version_spans(
            req.weight_version_events,
            current_version=get_serving().weight_version,
            num_output_tokens=len(req.output_ids),
        ),
    )
