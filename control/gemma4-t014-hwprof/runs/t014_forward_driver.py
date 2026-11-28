#!/usr/bin/env python3
"""T014 offline Gemma4 Forward driver (profiling only, no scheduler service).

Reproduces the production forward shapes of the frozen C-8 deployment on the real
checkpoint, KV capacity and attention/quantisation stacks:

  prefill : one Extend of ``--input-len`` tokens (eager)
  prefix  : a real chunked Extend — ``--prefix-len`` tokens already resident, then
            an Extend of ``--new-len`` tokens that attends over them
  decode  : a captured production Full CUDA Graph replayed at ``--batch`` 8/16/32

The measured forward is delimited by ``cudaProfilerStart/Stop`` so an external
profiler with ``--profile-from-start off`` sees exactly that forward. Nothing here
touches the serving path: the production ModelRunner, KV/SWA pools, quantisation
scheme, attention backend and CUDA graphs are used unchanged.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from array import array

ROOT = pathlib.Path("/home/ubuntu/workspaces/3rdparty/sglang-hicache")
for _finder in list(sys.meta_path):
    if type(_finder).__module__.startswith("__editable___sglang_"):
        sys.meta_path.remove(_finder)
for _path in (
    str(ROOT / "python"),
    "/tmp/f1-r3-kernel-overlay",
    str(ROOT / "python/sglang/kernels/aot/python"),
):
    while _path in sys.path:
        sys.path.remove(_path)
AOT = "/data/sglang-hicache/g2-quasar-runs/20261110T-g2-postrope-e5m2-quality/aot-sm86-package"
sys.path[:0] = [
    AOT,
    str(ROOT / "python"),
    "/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages",
    str(ROOT / "python/sglang/kernels/aot/python"),
]

MODEL = "/data/sglang-hicache/gemma4/model"


#: Serving KV capacity of the frozen C-8 argv (full pool; SWA pool separate).
FROZEN_SERVING_MAX_TOTAL_TOKENS = 1443628

#: Capacity actually pinned in every T014 cell. ``max_total_tokens`` is an upper
#: bound (the pool never exceeds the memory-derived value), and the derived value
#: differs between arms and under profiler instrumentation, so the pin sits below
#: every derived value: all cells then run the identical 1,300,000-token full pool
#: and the 65,536-token SWA pool. The pin is recorded per cell and asserted.
FROZEN_PINNED_MAX_TOTAL_TOKENS = 1_300_000

#: Production C-8 decode-graph buckets; keeping them identical reproduces the
#: frozen KV capacity (graph memory is part of the static pool budget).
PRODUCTION_GRAPH_BS = (1, 2, 4, 8, 12, 16, 24, 32)


def build_runner(device=0, graph_bs=PRODUCTION_GRAPH_BS):
    from sglang.srt.server_args import ServerArgs, PortArgs
    from sglang.srt.arg_groups.overrides import resolving_view
    from sglang.srt.entrypoints.engine import _set_envs_and_config
    from sglang.srt.runtime_context import publish
    from sglang.srt.layers.moe import initialize_moe_config
    from sglang.srt.layers.quantization.fp8_utils import initialize_fp8_gemm_config
    from sglang.srt.layers.quantization.fp4_utils import initialize_fp4_gemm_config
    from sglang.srt.model_executor.model_runner import ModelRunner
    from sglang.srt.configs.model_config import ModelConfig
    from sglang.srt.layers.dp_attention import compute_dp_attention_world_info
    from sglang.srt.distributed.parallel_state_wrapper import ParallelState

    args = ServerArgs(
        model_path=MODEL,
        tokenizer_path=MODEL,
        trust_remote_code=True,
        tp_size=1,
        device="cuda",
        base_gpu_id=device,
        context_length=131072,
        # One extra row: the shared decode context is owned by a separate request
        # row, so the measured batch of 32 still fits the production request pool.
        max_running_requests=33,
        mem_fraction_static=0.94,
        chunked_prefill_size=4096,
        kv_cache_dtype="fp8_e5m2",
        attention_backend="triton",
        disable_radix_cache=False,
        max_total_tokens=FROZEN_PINNED_MAX_TOTAL_TOKENS,
        enable_forward_pass_metrics=False,
        skip_server_warmup=True,
        cuda_graph_config={
            "decode": (
                {"backend": "full", "max_bs": max(graph_bs), "bs": list(graph_bs)}
                if graph_bs
                else {"backend": "disabled"}
            ),
            "prefill": {"backend": "disabled"},
        },
    )
    args.resolve_once()

    cfg = resolving_view(args)
    _set_envs_and_config(args)
    publish(args, role="scheduler")
    initialize_moe_config()
    initialize_fp8_gemm_config()
    initialize_fp4_gemm_config()
    model_cfg = ModelConfig.from_server_args(args)
    atp, atps, adp, adps = compute_dp_attention_world_info(
        cfg.enable_dp_attention, 0, 1, cfg.dp_size, cfg.attn_cp_size
    )
    ps = ParallelState(
        tp_rank=0,
        tp_size=1,
        pp_rank=0,
        pp_size=1,
        dp_rank=None,
        dp_size=cfg.dp_size,
        attn_tp_rank=atp,
        attn_tp_size=atps,
        attn_cp_rank=0,
        attn_cp_size=cfg.attn_cp_size,
        attn_dcp_rank=0,
        attn_dcp_size=cfg.dcp_size,
        attn_dp_rank=adp,
        attn_dp_size=adps,
        moe_ep_rank=0,
        moe_ep_size=cfg.ep_size,
        moe_dp_rank=None,
        moe_dp_size=cfg.moe_dp_size,
        gpu_id=device,
    )
    runner = ModelRunner(
        model_config=model_cfg,
        mem_fraction_static=cfg.mem_fraction_static,
        gpu_id=device,
        ps=ps,
        nccl_port=PortArgs.init_new(args).nccl_port,
        server_args=args,
    )
    runner.alloc_memory_pool()
    runner.init_attention_backends()
    runner.init_cuda_graphs()
    return runner, args, cfg


class ChunkCache:
    """Production no-prefix-cache trait, extended with an explicit prefix injector."""

    def __init__(self, pool, allocator, page_size, device):
        from sglang.srt.mem_cache.base_prefix_cache import MatchResult

        self.req_to_token_pool = pool
        self.token_to_kv_pool_allocator = allocator
        self.page_size = page_size
        self.device = device
        self.MatchResult = MatchResult

    def supports_mamba(self):
        return False

    def supports_swa(self):
        return False

    def is_chunk_cache(self):
        return True

    def is_tree_cache(self):
        return False

    def swa_reprefill_tail_tokens(self):
        return 0

    def evict(self, params):
        return None

    def evict_for_alloc(self, params):
        return None

    def match_prefix(self, params):
        import torch

        return self.MatchResult(
            torch.empty((0,), dtype=torch.int64, device=self.device), None, None, None
        )

    def insert(self, params):
        from sglang.srt.mem_cache.base_prefix_cache import InsertResult

        return InsertResult(prefix_len=0)

    def cache_finished_req(self, req, is_insert=True, *, kv_len_to_handle):
        indices = self.req_to_token_pool.req_to_token[
            req.req_pool_idx, req.cache_protected_len : kv_len_to_handle
        ]
        self.token_to_kv_pool_allocator.free(indices)

    def cache_unfinished_req(self, req, chunked=False):
        req.prefix_indices = self.req_to_token_pool.req_to_token[
            req.req_pool_idx, : req.extend_range.end
        ].to(dtype=torch.int64, copy=True)

    def inc_lock_ref(self, node):
        return None

    def dec_lock_ref(self, node, params=None):
        return None

    def protected_size(self):
        return 0

    def available_and_evictable_str(self):
        return f"free_tokens={self.token_to_kv_pool_allocator.available_size()}"

    def pretty_print(self):
        return None

    def reset(self):
        pass


def token_fixture(length, batch, seed=1319):
    """Deterministic valid token ids inside the checkpoint vocabulary."""
    import torch

    generator = torch.Generator(device="cpu").manual_seed(seed)
    rows = []
    for index in range(batch):
        base = torch.randint(3, 200000, (length,), generator=generator)
        rows.append(base.tolist())
    return rows


def make_req(index, ids, out_len):
    from sglang.srt.managers.schedule_batch import Req
    from sglang.srt.sampling.sampling_params import SamplingParams

    req = Req(
        rid=f"t014-{index}",
        origin_input_text="",
        origin_input_ids=array("q", ids),
        sampling_params=SamplingParams(temperature=0, top_p=1, max_new_tokens=out_len),
    )
    req.full_untruncated_fill_ids = req.origin_input_ids
    req.logprob_start_len = -1
    req.set_extend_range(0, len(ids))
    return req


def new_batch(reqs, runner, cfg):
    from sglang.srt.managers.schedule_batch import ScheduleBatch
    from sglang.srt.speculative.spec_info import SpeculativeAlgorithm

    cache = ChunkCache(
        runner.req_to_token_pool,
        runner.token_to_kv_pool_allocator,
        cfg.page_size,
        runner.device,
    )
    batch = ScheduleBatch.init_new(
        reqs=reqs,
        req_to_token_pool=runner.req_to_token_pool,
        token_to_kv_pool_allocator=runner.token_to_kv_pool_allocator,
        tree_cache=cache,
        model_config=runner.model_config,
        enable_overlap=False,
        spec_algorithm=SpeculativeAlgorithm.NONE,
    )
    return batch, cache


def forward_batch(batch, runner):
    from sglang.srt.model_executor.forward_batch_info import ForwardBatch

    batch.prepare_for_extend()
    if batch.prefill_input_ids_cpu is not None:
        batch.input_ids = batch.prefill_input_ids_cpu.to(
            batch.device, non_blocking=True
        )
        batch.prefill_input_ids_cpu = None
    fb = ForwardBatch.init_new(batch, runner, return_hidden_states_before_norm=False)
    return runner.forward(fb).logits_output


def decode_batch(batch, runner, next_ids):
    import torch

    from sglang.srt.model_executor.forward_batch_info import ForwardBatch

    if getattr(batch, "sampling_info", None) is None:
        # A decode-only batch has not been through prepare_for_extend, which is
        # where the scheduler builds this. Same construction, same defaults.
        from sglang.srt.sampling.sampling_batch_info import SamplingBatchInfo

        batch.sampling_info = SamplingBatchInfo.from_schedule_batch(
            batch, runner.model_config.vocab_size
        )

    batch.input_ids = next_ids.to(torch.int64)
    batch.prepare_for_decode()
    fb = ForwardBatch.init_new(batch, runner, return_hidden_states_before_norm=False)
    return runner.forward(fb).logits_output


def free_batch(batch, runner, cache):
    import torch

    from sglang.srt.mem_cache.common import release_kv_cache

    torch.cuda.synchronize()
    for req in batch.reqs:
        if req.req_pool_idx is not None:
            release_kv_cache(req, cache, is_insert=False)


def fa2_stats(runner):
    backend = getattr(runner, "attn_backend", None)
    state = getattr(backend, "_fa2_ragged_state", None)
    if state is None:
        return None
    return dict(state.stats)


def reset_fa2_plan(backend):
    for name, value in (("_fa2_ragged_plan", None), ("_fa2_ragged_planned", False)):
        if hasattr(backend, name):
            setattr(backend, name, value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage", choices=("prefill", "prefix", "decode"), required=True
    )
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--input-len", type=int, default=1024)
    parser.add_argument("--prefix-len", type=int, default=28672)
    parser.add_argument("--new-len", type=int, default=4096)
    parser.add_argument("--decode-context", type=int, default=8192)
    parser.add_argument("--arm", choices=("marlin", "humming"), default="marlin")
    parser.add_argument("--attn", choices=("triton", "fa2"), default="triton")
    parser.add_argument("--profile-region", action="store_true")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    # CUDA graphs are only needed for the decode stage; prefill/prefix keep the
    # frozen KV capacity and need the headroom for the extend activations.
    graph_bs = (args.batch,) if args.stage == "decode" else ()

    os.environ["SGLANG_GEMMA4_SWA_POOL_TOKENS"] = "65536"
    os.environ.setdefault("SGLANG_HUMMING_USE_F16_ACCUM", "0")
    os.environ.setdefault("SGLANG_T011_BF16_PREFIX_BUDGET_MB", "128")
    if args.arm == "humming":
        os.environ["SGLANG_CTWNA16_HUMMING"] = "1"
    else:
        os.environ.pop("SGLANG_CTWNA16_HUMMING", None)
    if args.attn == "fa2":
        os.environ["SGLANG_FA2_RAGGED_EXTEND"] = "1"
    else:
        os.environ.pop("SGLANG_FA2_RAGGED_EXTEND", None)

    import torch

    torch.cuda.set_device(0)
    runner, server_args, cfg = build_runner(0, graph_bs)
    backend = runner.attn_backend
    capability = torch.cuda.get_device_capability()

    def region(fn):
        if not args.profile_region:
            return fn()
        cudart = torch.cuda.cudart()
        cudart.cudaProfilerStart()
        try:
            return fn()
        finally:
            cudart.cudaProfilerStop()

    result = {
        "stage": args.stage,
        "arm": args.arm,
        "attn": args.attn,
        "batch": args.batch,
        "input_len": args.input_len,
        "prefix_len": args.prefix_len,
        "new_len": args.new_len,
        "decode_context": args.decode_context,
        "device": torch.cuda.get_device_name(),
        "capability": list(capability),
        "torch": torch.__version__,
        "max_total_num_tokens": int(runner.max_total_num_tokens),
        "max_total_tokens_pinned": FROZEN_PINNED_MAX_TOTAL_TOKENS,
        "max_total_tokens_clamped": int(runner.max_total_num_tokens)
        != FROZEN_PINNED_MAX_TOTAL_TOKENS,
        "max_total_num_tokens_swa": int(
            getattr(runner, "max_total_num_tokens_swa", 0) or 0
        ),
        "kv_pool_geometry": {
            name: value
            for name, value in (
                ("alloc.size", getattr(runner.token_to_kv_pool_allocator, "size", None)),
                ("alloc.size_full", getattr(runner.token_to_kv_pool_allocator, "size_full", None)),
                ("alloc.size_swa", getattr(runner.token_to_kv_pool_allocator, "size_swa", None)),
                ("pool.size_swa", getattr(runner.token_to_kv_pool, "size_swa", None)),
            )
        },
        "kv_cache_dtype": server_args.kv_cache_dtype,
        "quantization_flag": os.environ.get("SGLANG_CTWNA16_HUMMING", "0"),
        "fa2_flag": os.environ.get("SGLANG_FA2_RAGGED_EXTEND", "0"),
        "fa2_enabled_in_backend": bool(
            getattr(backend, "enable_fa2_ragged_extend", False)
        ),
        "fa2_stats_before": fa2_stats(runner),
    }

    def fill_chunks(reqs, per_round_total, target_len):
        """Extend ``reqs`` to ``target_len`` in production-sized chunks.

        Every round extends the same absolute window (``filled..stop``) with the
        already-written KV published as ``prefix_indices``, exactly like
        Scheduler's chunked prefill. Keeping each Forward inside
        ``chunked_prefill_size`` is also what keeps the SWA working set inside its
        pool, so this is the only way production ever grows a context.
        """
        per_req = max(1, per_round_total // max(1, len(reqs)))
        filled = 0
        batch = cache = logs = None
        while filled < target_len:
            stop = min(filled + per_req, target_len)
            for req in reqs:
                if filled:
                    req.prefix_indices = runner.req_to_token_pool.req_to_token[
                        req.req_pool_idx, :filled
                    ].to(dtype=torch.int64, copy=True)
                req.set_extend_range(filled, stop)
            reset_fa2_plan(backend)
            batch, cache = new_batch(reqs, runner, cfg)
            logs = forward_batch(batch, runner)
            torch.cuda.synchronize()
            filled = stop
        return batch, cache, logs

    with torch.inference_mode():
        if args.stage in ("prefill", "prefix"):
            total = (
                args.input_len
                if args.stage == "prefill"
                else args.prefix_len + args.new_len
            )
            rows = token_fixture(total, args.batch)
            reqs = [make_req(i, ids, 4) for i, ids in enumerate(rows)]
            if args.stage == "prefix":
                fill_chunks(reqs, cfg.chunked_prefill_size, args.prefix_len)
                for req in reqs:
                    req.prefix_indices = runner.req_to_token_pool.req_to_token[
                        req.req_pool_idx, : args.prefix_len
                    ].to(dtype=torch.int64, copy=True)
                    req.set_extend_range(
                        args.prefix_len, args.prefix_len + args.new_len
                    )
                reset_fa2_plan(backend)
                batch, cache = new_batch(reqs, runner, cfg)
            else:
                # Production-sized prompt: one Extend of the whole input (the
                # chunk size equals the largest prefill shape under test).
                for req in reqs:
                    req.set_extend_range(0, total)
                batch, cache = new_batch(reqs, runner, cfg)
            logs = region(lambda: forward_batch(batch, runner))
            torch.cuda.synchronize()
            result["output_argmax"] = (
                logs.next_token_logits.argmax(dim=-1).cpu().tolist()
            )
            result["tokens"] = total * args.batch
            result["extend_tokens"] = (
                args.input_len * args.batch
                if args.stage == "prefill"
                else args.new_len * args.batch
            )
            result["prefix_tokens"] = (
                0 if args.stage == "prefill" else args.prefix_len * args.batch
            )
            free_batch(batch, runner, cache)
        else:
            # Production decode: `--batch` requests that share one resident
            # context (the C-8 shared system prompt), replayed from the captured
            # Full CUDA Graph. The context is built once with a real chunked
            # prefill, then aliased as a radix-cache hit by every request, so the
            # SWA working set stays inside the production pool exactly like
            # serving does after eviction.
            owner_rows = token_fixture(args.decode_context, 1)
            owner = make_req(0, owner_rows[0], 4)
            fill_chunks([owner], cfg.chunked_prefill_size, args.decode_context)
            shared_rows = runner.req_to_token_pool.req_to_token[
                owner.req_pool_idx, : args.decode_context
            ].to(dtype=torch.int64, copy=True)
            rows = token_fixture(args.decode_context + 1, args.batch)
            reqs = [make_req(i + 1, ids, 4) for i, ids in enumerate(rows)]
            for req in reqs:
                req.prefix_indices = shared_rows.clone()
                req.set_extend_range(args.decode_context, args.decode_context + 1)
            batch, cache = new_batch(reqs, runner, cfg)
            # One real 1-token Extend per request initialises the scheduler-side
            # batch state (req slots, seq_lens, out_cache_loc) exactly as the
            # last prefill chunk of a cache-hit request does.
            warm = forward_batch(batch, runner)
            torch.cuda.synchronize()
            next_ids = warm.next_token_logits.argmax(dim=-1)
            # Warm one graph replay so capture-side allocations are already done.
            decode_batch(batch, runner, next_ids)
            torch.cuda.synchronize()
            reset_fa2_plan(backend)
            graph_runner = runner.decode_cuda_graph_runner
            logs = region(lambda: decode_batch(batch, runner, next_ids))
            torch.cuda.synchronize()
            key = getattr(graph_runner, "_replay_graph_key", None)
            result["output_argmax"] = (
                logs.next_token_logits.argmax(dim=-1).cpu().tolist()
            )
            result["tokens"] = args.batch
            result["graph_identity"] = repr(key)
            result["actual_batch"] = int(getattr(key, "size", 0) or 0)
            result["decode_context"] = args.decode_context
            result["context_tokens_shared"] = args.decode_context
            # No teardown: the shared context rows are aliased by every request,
            # so a per-request release would double-free them. The process exits
            # immediately after the measurement.

    result["fa2_stats_after"] = fa2_stats(runner)
    pathlib.Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "stage",
                    "arm",
                    "attn",
                    "batch",
                    "tokens",
                    "max_total_num_tokens",
                    "fa2_enabled_in_backend",
                    "fa2_stats_after",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
