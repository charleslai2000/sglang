#!/usr/bin/env python3
"""Isolated Gemma4 real CUDA Graph Decode Forward timer, adapted from T002 offline harness."""

from __future__ import annotations
import argparse, hashlib, json, os, pathlib, sys
from array import array

ROOT = pathlib.Path(__file__).resolve().parents[4]
for finder in list(sys.meta_path):
    if type(finder).__module__.startswith("__editable___sglang_"):
        sys.meta_path.remove(finder)
sys.path[:0] = [
    "/data/sglang-hicache/gemma4/aot-sm86-build",
    str(ROOT / "python"),
    "/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages",
    str(ROOT / "python/sglang/kernels/aot/python"),
]
import torch

MODEL = "/data/sglang-hicache/gemma4/model"
REVISION = "6cd26aaa2357fb2bad8c51699a7558a4d1a965bb"
MODEL_SHA = "19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d"


def sha(v):
    return hashlib.sha256(json.dumps(v, separators=(",", ":")).encode()).hexdigest()


def init_runner():
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
        revision=REVISION,
        trust_remote_code=True,
        tp_size=1,
        device="cuda",
        base_gpu_id=0,
        context_length=8192,
        max_total_tokens=32768,
        max_running_requests=16,
        mem_fraction_static=0.90,
        disable_radix_cache=True,
        kv_cache_dtype="bf16",
        attention_backend="triton",
        enable_forward_pass_metrics=False,
        cuda_graph_config={
            "decode": {"backend": "full", "max_bs": 16, "bs": [1, 2, 4, 8, 12, 16]},
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
    from sglang.kernels.ops.mamba.triton_ops import (
        initialize_mamba_selective_state_update_backend,
    )

    initialize_mamba_selective_state_update_backend(args)
    mc = ModelConfig.from_server_args(args)
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
        gpu_id=0,
    )
    runner = ModelRunner(
        model_config=mc,
        mem_fraction_static=0.90,
        gpu_id=0,
        ps=ps,
        nccl_port=PortArgs.init_new(args).nccl_port,
        server_args=args,
    )
    from sglang.srt.mem_cache.memory_pool import HybridReqToTokenPool

    runner.alloc_memory_pool()
    if not isinstance(runner.req_to_token_pool, HybridReqToTokenPool):
        raise RuntimeError("expected production HybridReqToTokenPool")
    runner.init_attention_backends()
    runner.init_cuda_graphs()
    return runner, args, cfg


class Cache:
    def __init__(self, r, c):
        self.req_to_token_pool = r.req_to_token_pool
        self.token_to_kv_pool_allocator = r.token_to_kv_pool_allocator
        self.page_size = c.page_size
        self.device = r.device

    def supports_mamba(self):
        return True

    def supports_swa(self):
        return True

    def is_chunk_cache(self):
        return True

    def is_tree_cache(self):
        return False

    def swa_reprefill_tail_tokens(self):
        return 0

    def get_mamba_state_indices(self, req_pool_indices):
        return self.req_to_token_pool.get_mamba_state_indices(req_pool_indices)

    def evict(self, p):
        return None

    def evict_for_alloc(self, p):
        return None

    def match_prefix(self, p):
        from sglang.srt.mem_cache.base_prefix_cache import MatchResult

        return MatchResult(
            torch.empty((0,), dtype=torch.int64, device=self.device), None, None, None
        )

    def insert(self, p):
        from sglang.srt.mem_cache.base_prefix_cache import InsertResult

        return InsertResult(prefix_len=0)

    def _insert_helper(self, *args, **kwargs):
        return None

    def retract_finished(self, *args, **kwargs):
        return None

    def cache_finished_req(self, r, is_insert=True, *, kv_len_to_handle):
        self.token_to_kv_pool_allocator.free(
            self.req_to_token_pool.req_to_token[
                r.req_pool_idx, r.cache_protected_len : kv_len_to_handle
            ]
        )

    def cache_unfinished_req(self, r, chunked=False):
        r.prefix_indices = self.req_to_token_pool.req_to_token[
            r.req_pool_idx, : r.extend_range.end
        ].to(dtype=torch.int64, copy=True)

    def inc_lock_ref(self, n):
        return None

    def dec_lock_ref(self, n, params=None):
        return None

    def protected_size(self):
        return 0

    def available_and_evictable_str(self):
        return "offline"

    def pretty_print(self):
        return None

    def reset(self):
        pass


def make_batch(runner, cfg, ids):
    from sglang.srt.managers.schedule_batch import Req, ScheduleBatch
    from sglang.srt.sampling.sampling_params import SamplingParams
    from sglang.srt.speculative.spec_info import SpeculativeAlgorithm

    reqs = []
    for i, row in enumerate(ids):
        q = Req(
            rid=f"gemma-b{len(ids)}-{i}",
            origin_input_text="",
            origin_input_ids=array("q", row),
            sampling_params=SamplingParams(temperature=0, top_p=1, max_new_tokens=2),
        )
        q.full_untruncated_fill_ids = q.origin_input_ids
        q.logprob_start_len = -1
        q.set_extend_range(0, len(row))
        reqs.append(q)
    cache = Cache(runner, cfg)
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--batch", type=int, choices=[1, 2, 4, 8, 16], required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    os.environ["SGLANG_T002_CUPTI"] = "0"
    torch.cuda.set_device(0)
    r, args, cfg = init_runner()
    ids = [
        [2 + ((j * 7919 + i * 104729) % 200000) for j in range(64)]
        for i in range(a.batch)
    ]
    from sglang.srt.model_executor.forward_batch_info import ForwardBatch
    from sglang.srt.mem_cache.common import release_kv_cache

    b, _ = make_batch(r, cfg, ids)
    b.prepare_for_extend()
    b.input_ids = b.prefill_input_ids_cpu.to(b.device, non_blocking=True)
    b.prefill_input_ids_cpu = None
    with torch.inference_mode():
        nextids = (
            r.forward(
                ForwardBatch.init_new(b, r, return_hidden_states_before_norm=False)
            )
            .logits_output.next_token_logits.argmax(-1)
            .to(torch.int64)
        )
        torch.cuda.synchronize()
    b.input_ids = nextids
    b.prepare_for_decode()
    fb = ForwardBatch.init_new(b, r, return_hidden_states_before_norm=False)
    gr = r.decode_cuda_graph_runner
    torch.cuda.synchronize()
    ref = r.forward(fb).logits_output.next_token_logits
    torch.cuda.synchronize()
    key = repr(gr._replay_graph_key)
    gsize = getattr(gr._replay_graph_key, "size", None)
    if gsize != a.batch:
        raise RuntimeError(f"graph key mismatch {gsize=} {a.batch=}: {key}")
    # Reinitialize identical input/state after graph setup, then measure replay only.
    for q in b.reqs:
        if q.req_pool_idx is not None:
            release_kv_cache(q, b.tree_cache, is_insert=False)
    for q in b.reqs:
        if q.req_pool_idx is not None:
            release_kv_cache(q, b.tree_cache, is_insert=False)
    b, _ = make_batch(r, cfg, ids)
    b.prepare_for_extend()
    b.input_ids = b.prefill_input_ids_cpu.to(b.device, non_blocking=True)
    b.prefill_input_ids_cpu = None
    with torch.inference_mode():
        r.forward(ForwardBatch.init_new(b, r, return_hidden_states_before_norm=False))
        torch.cuda.synchronize()
    b.input_ids = nextids
    b.prepare_for_decode()
    fb = ForwardBatch.init_new(b, r, return_hidden_states_before_norm=False)
    starts = [torch.cuda.Event(enable_timing=True) for _ in range(27)]
    ends = [torch.cuda.Event(enable_timing=True) for _ in range(27)]
    out = None
    with torch.inference_mode():
        for i in range(27):
            starts[i].record()
            out = r.forward(fb).logits_output.next_token_logits
            ends[i].record()
    torch.cuda.synchronize()
    ms = [starts[i].elapsed_time(ends[i]) for i in range(2, 27)]
    if repr(gr._replay_graph_key) != key:
        raise RuntimeError("graph changed during measured trials")
    result = {
        "batch": a.batch,
        "actual_batch": int(fb.batch_size),
        "model_revision": REVISION,
        "model_sha256": MODEL_SHA,
        "source_sha": os.environ.get("GEMMA_SOURCE_SHA"),
        "fixture_sha256": sha(ids),
        "prompt_tokens_per_req": 64,
        "forward_workload": "steady-state decode after 64-token prefill and two warmup decode replays",
        "graph_capture_bs": [1, 2, 4, 8, 12, 16],
        "kv_pool_type": type(r.req_to_token_pool).__name__,
        "graph_runner": type(gr).__name__,
        "kv_dtype": "bf16",
        "tp": 1,
        "attention": "triton",
        "graph_identity": key,
        "graph_size": gsize,
        "graph_replay": True,
        "warmup_replays": 2,
        "n": len(ms),
        "cuda_event_ms": ms,
        "p50_ms": sorted(ms)[12],
        "p95_ms": sorted(ms)[23],
        "mean_ms": sum(ms) / len(ms),
        "theoretical_aggregate_decode_tps": a.batch * 1000 / (sum(ms) / len(ms)),
        "logits_shape": list(out.shape),
    }
    pathlib.Path(a.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    try:
        from sglang.srt.distributed import destroy_distributed_environment

        destroy_distributed_environment()
    finally:
        if torch.distributed.is_initialized():
            torch.distributed.destroy_process_group()


if __name__ == "__main__":
    main()
