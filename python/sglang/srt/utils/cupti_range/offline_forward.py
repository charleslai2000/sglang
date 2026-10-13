"""Isolated deterministic Falcon Forward CUPTI harness.

Uses the production ModelRunner, HybridReqToTokenPool, request allocation,
ScheduleBatch and ForwardBatch. No Scheduler service or online instrumentation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
from array import array

ROOT = pathlib.Path(__file__).resolve().parents[5]
# The installed editable finder in this shared venv targets the sibling opt
# worktree. Remove it in this process only and select this authorized mainline
# plus the previously validated SM86 overlay explicitly.
for _finder in list(sys.meta_path):
    if type(_finder).__module__.startswith("__editable___sglang_"):
        sys.meta_path.remove(_finder)
for _path in (
    str(ROOT / "python"),
    "/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages",
    "/tmp/f1-r3-kernel-overlay",
    str(ROOT / "python/sglang/kernels/aot/python"),
):
    if _path in sys.path:
        sys.path.remove(_path)
# sgl_kernel must resolve from the SM86 overlay; sglang from this checkout.
sys.path[:0] = ["/tmp/t002-sm86-overlay-root", str(ROOT / "python"),
                "/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages",
                str(ROOT / "python/sglang/kernels/aot/python")]
import torch

MODEL = "/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4"
REVISION = "52036ae497a2c0c253e17f98cc8652f2f7082ae3"
FIXTURE = ROOT / "control/falcon-h1-3090-hicache-perf/runs/R17-20261012T0100Z/provenance-20c837f1/workload.json"

class OfflineChunkCache:
    """Production no-prefix-cache trait used by one_batch, with hybrid pool intact."""
    def __init__(self, pool, allocator, page_size, device):
        from sglang.srt.mem_cache.base_prefix_cache import MatchResult
        self.req_to_token_pool=pool; self.token_to_kv_pool_allocator=allocator
        self.page_size=page_size; self.device=device; self.MatchResult=MatchResult
    def supports_mamba(self): return False
    def supports_swa(self): return False
    def is_chunk_cache(self): return True
    def is_tree_cache(self): return False
    def swa_reprefill_tail_tokens(self): return 0
    def evict(self, params): return None
    def evict_for_alloc(self, params): return None
    def match_prefix(self, params):
        return self.MatchResult(torch.empty((0,),dtype=torch.int64,device=self.device),None,None,None)
    def insert(self, params):
        from sglang.srt.mem_cache.base_prefix_cache import InsertResult
        return InsertResult(prefix_len=0)
    def cache_finished_req(self, req, is_insert=True, *, kv_len_to_handle):
        indices=self.req_to_token_pool.req_to_token[req.req_pool_idx,req.cache_protected_len:kv_len_to_handle]
        self.token_to_kv_pool_allocator.free(indices)
    def cache_unfinished_req(self, req, chunked=False):
        req.prefix_indices=self.req_to_token_pool.req_to_token[req.req_pool_idx,:req.extend_range.end].to(dtype=torch.int64,copy=True)
    def inc_lock_ref(self,node): return None
    def dec_lock_ref(self,node,params=None): return None
    def protected_size(self): return 0
    def available_and_evictable_str(self):
        return f"free_tokens={self.token_to_kv_pool_allocator.available_size()}"
    def pretty_print(self): return None
    def reset(self): pass


def _fixture(length,batch):
    workload=json.loads(FIXTURE.read_text())
    candidates=[r["prompt_token_ids"] for r in workload["workload"]]
    if not candidates: raise RuntimeError("frozen R17 workload contains no token fixture")
    rows=[]
    for i in range(batch):
        source=list(candidates[i % len(candidates)])
        if not source: raise RuntimeError("empty frozen prompt token fixture")
        # Deterministically tile archived valid model token IDs to the requested
        # context. The exact derived sequence and SHA are emitted per run.
        repeats=(length+len(source)-1)//len(source)
        rows.append((source*repeats)[:length])
    if any(t<0 or t>=131072 for row in rows for t in row): raise ValueError("fixture token outside frozen vocab range")
    sha=hashlib.sha256(json.dumps(rows,separators=(",",":")).encode()).hexdigest()
    return rows,sha


def _init_runner(device=0, graph_bs=1):
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
    from sglang.srt.mem_cache.memory_pool import HybridReqToTokenPool
    from sglang.srt.utils.hf_transformers_utils import get_tokenizer
    args=ServerArgs(model_path=MODEL,tokenizer_path=MODEL,revision=REVISION,trust_remote_code=True,
        tp_size=1,device="cuda",base_gpu_id=device,context_length=8192,max_total_tokens=16384,
        max_running_requests=16,mem_fraction_static=0.90,disable_radix_cache=True,
        enable_forward_pass_metrics=False,
        cuda_graph_config={"decode":{"backend":"full","max_bs":graph_bs,"bs":[graph_bs]},
                           "prefill":{"backend":"disabled"}})
    args.resolve_once(); cfg=resolving_view(args); _set_envs_and_config(args); publish(args,role="scheduler")
    initialize_moe_config(); initialize_fp8_gemm_config(); initialize_fp4_gemm_config()
    from sglang.kernels.ops.mamba.triton_ops import initialize_mamba_selective_state_update_backend
    initialize_mamba_selective_state_update_backend(args)
    model_cfg=ModelConfig.from_server_args(args)
    atp,atps,adp,adps=compute_dp_attention_world_info(cfg.enable_dp_attention,0,1,cfg.dp_size,cfg.attn_cp_size)
    ps=ParallelState(tp_rank=0,tp_size=1,pp_rank=0,pp_size=1,dp_rank=None,dp_size=cfg.dp_size,
        attn_tp_rank=atp,attn_tp_size=atps,attn_cp_rank=0,attn_cp_size=cfg.attn_cp_size,
        attn_dcp_rank=0,attn_dcp_size=cfg.dcp_size,attn_dp_rank=adp,attn_dp_size=adps,
        moe_ep_rank=0,moe_ep_size=cfg.ep_size,moe_dp_rank=None,moe_dp_size=cfg.moe_dp_size,gpu_id=device)
    runner=ModelRunner(model_config=model_cfg,mem_fraction_static=cfg.mem_fraction_static,gpu_id=device,ps=ps,
        nccl_port=PortArgs.init_new(args).nccl_port,server_args=args)
    runner.alloc_memory_pool(); runner.init_attention_backends(); runner.init_cuda_graphs()
    if not isinstance(runner.req_to_token_pool,HybridReqToTokenPool): raise RuntimeError("expected production HybridReqToTokenPool")
    tok=get_tokenizer(cfg.tokenizer_path,tokenizer_mode=cfg.tokenizer_mode,trust_remote_code=cfg.trust_remote_code)
    return runner,tok,args,cfg


def _request(i,ids,out_len):
    from sglang.srt.managers.schedule_batch import Req
    from sglang.srt.sampling.sampling_params import SamplingParams
    req=Req(rid=f"t002-{i}",origin_input_text="",origin_input_ids=array("q",ids),
        sampling_params=SamplingParams(temperature=0,top_p=1,max_new_tokens=out_len))
    req.full_untruncated_fill_ids=req.origin_input_ids; req.logprob_start_len=-1
    req.set_extend_range(0,len(ids)); return req


def _new_batch(reqs,runner,cfg):
    from sglang.srt.managers.schedule_batch import ScheduleBatch
    from sglang.srt.speculative.spec_info import SpeculativeAlgorithm
    cache=OfflineChunkCache(runner.req_to_token_pool,runner.token_to_kv_pool_allocator,cfg.page_size,runner.device)
    batch=ScheduleBatch.init_new(reqs=reqs,req_to_token_pool=runner.req_to_token_pool,
        token_to_kv_pool_allocator=runner.token_to_kv_pool_allocator,tree_cache=cache,
        model_config=runner.model_config,enable_overlap=False,spec_algorithm=SpeculativeAlgorithm.NONE)
    return batch,cache


def _prepare_prefill(batch,runner):
    batch.prepare_for_extend()
    if batch.prefill_input_ids_cpu is not None:
        batch.input_ids=batch.prefill_input_ids_cpu.to(batch.device,non_blocking=True); batch.prefill_input_ids_cpu=None
    from sglang.srt.model_executor.forward_batch_info import ForwardBatch
    return ForwardBatch.init_new(batch,runner,return_hidden_states_before_norm=False)

def _prefill(batch,runner):
    fb=_prepare_prefill(batch,runner)
    return fb,runner.forward(fb).logits_output


def _decode_prepare(batch,runner,next_ids):
    batch.input_ids=next_ids.to(torch.int64); batch.prepare_for_decode()
    from sglang.srt.model_executor.forward_batch_info import ForwardBatch
    return ForwardBatch.init_new(batch,runner,return_hidden_states_before_norm=False)

def _decode(batch,runner,next_ids):
    fb=_decode_prepare(batch,runner,next_ids)
    return fb,runner.forward(fb).logits_output


def _free(batch,runner,cache):
    from sglang.srt.mem_cache.common import release_kv_cache
    torch.cuda.synchronize()
    for req in batch.reqs:
        if req.req_pool_idx is not None:
            release_kv_cache(req,cache,is_insert=False)


def _profile_forward(prof,runner,invoke,*,label,iteration,stage,batch,tokens,graph):
    # Arm/Start only after all request/state prep. For graph decode, arm in the
    # backend seam so CUPTI's launch filtering includes the actual replay.
    if graph != "CUDA_GRAPH":
        prof.arm_window()
    stream=torch.cuda.current_stream(runner.device)
    start,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
    start.record(stream)
    if graph != "CUDA_GRAPH":
        prof.begin(label,iteration,stage,batch,tokens,graph)
    value=invoke()
    end.record(stream)
    if graph != "CUDA_GRAPH":
        prof.end()
    else:
        torch.cuda.synchronize(runner.device)
    end.synchronize()
    elapsed=start.elapsed_time(end)
    result=prof.finalize()
    if result.get("dropped")!=0 or result.get("passes")!=1 or result.get("expected_range_count")!=1:
        raise RuntimeError(f"invalid CUPTI range integrity: {result}")
    # CUPTI includes an implicit root range (with NaN counters) alongside the
    # one explicitly pushed UserRange; validate the exact named range only.
    range_rows=result.get("ranges",[])
    matched=[r for r in range_rows if r.get("name","").startswith(f"range={label};")]
    matched=[r for r in matched if all(
        torch.isfinite(torch.tensor(r.get(k,float('nan')))).item()
        for k in ("gpu__time_duration.avg","dram__bytes_read.sum","dram__bytes_write.sum")
    )]
    if len(matched)!=1:
        raise RuntimeError(f"expected exactly one populated target CUPTI UserRange, found {matched}: {result}")
    row=matched[0]
    row["passes"]=result.get("passes"); row["dropped"]=result.get("dropped")
    row["expected_range_count"]=result.get("expected_range_count")
    if not all(torch.isfinite(torch.tensor(row.get(k,float('nan')))).item() for k in ("gpu__time_duration.avg","dram__bytes_read.sum","dram__bytes_write.sum")):
        raise RuntimeError(f"target CUPTI range has invalid counters: {row}")
    row.update({"gpu_event_ms":elapsed,"iteration_id":iteration,"stage":stage,"batch":batch,"tokens":tokens,"graph":graph})
    row["dram_gbps"]=(row["dram__bytes_read.sum"]+row["dram__bytes_write.sum"])/(elapsed*1e6)
    return value,row


def main():
    p=argparse.ArgumentParser(); p.add_argument("--stage",choices=("decode","prefill"),required=True)
    p.add_argument("--batch",type=int,default=1); p.add_argument("--input-len",type=int,default=1024)
    p.add_argument("--repeat",type=int,default=1); p.add_argument("--output",required=True)
    p.add_argument("--extension",action="store_true",help="include extension metrics (may require multiple passes)")
    a=p.parse_args()
    if a.batch not in (1,2,4,8,16): raise ValueError("unsupported batch")
    if a.repeat != 1:
        raise ValueError("each independent CUPTI trial must run in its own process; use --repeat 1")
    rows,fixture_sha=_fixture(a.input_len,a.batch)
    torch.cuda.set_device(0)
    os.environ["SGLANG_T002_CUPTI"]="1"
    from sglang.srt.utils import cupti_range as prof
    runner,tokenizer,args,cfg=_init_runner(0,a.batch)
    results=[]
    try:
        # Graphs have already been captured by the production ModelRunner path.
        # Independent state starts from cleared production pools for each repeat.
        for rep in range(a.repeat):
            runner.req_to_token_pool.clear(); runner.token_to_kv_pool_allocator.clear()
            reqs=[_request(i,ids,4) for i,ids in enumerate(rows)]
            batch,cache=_new_batch(reqs,runner,cfg)
            with torch.inference_mode():
                _,prefill_logits=_prefill(batch,runner)
                torch.cuda.synchronize(runner.device)
                prefill_argmax=prefill_logits.next_token_logits.argmax(dim=-1)
                if a.stage=="prefill":
                    # Rebuild identical initial pool/request state, then capture
                    # the only measured Extend invocation in this state.
                    runner.req_to_token_pool.clear(); runner.token_to_kv_pool_allocator.clear()
                    reqs=[_request(i,ids,4) for i,ids in enumerate(rows)]
                    pb,pcache=_new_batch(reqs,runner,cfg)
                    pfb=_prepare_prefill(pb,runner)
                    prof.enable()
                    def call_prefill():
                        return pfb,runner.forward(pfb).logits_output
                    (_,logits),record=_profile_forward(prof,runner,call_prefill,
                        label=f"falcon-prefill-b{a.batch}-t{a.input_len}-r{rep}",iteration=rep,
                        stage="prefill",batch=a.batch,tokens=a.input_len*a.batch,graph="EAGER_EXTEND")
                    # Compare against the unprofiled deterministic warmup output.
                    logits_delta=(logits.next_token_logits-prefill_logits.next_token_logits).abs()
                    logits_max_abs=float(logits_delta.max().item())
                    if not torch.equal(logits.next_token_logits,prefill_logits.next_token_logits):
                        if not torch.equal(logits.next_token_logits.argmax(dim=-1),prefill_logits.next_token_logits.argmax(dim=-1)):
                            raise RuntimeError("profiled prefill argmax differs from deterministic unprofiled warmup")
                    check=logits.next_token_logits.argmax(dim=-1)
                    record["fixture_sha256"]=fixture_sha; record["output_argmax"]=check.cpu().tolist()
                    record["actual_batch"]=len(pb.reqs); record["graph_identity"]="EAGER_EXTEND"
                    record["unprofiled_logits_exact_match"]=bool(torch.equal(logits.next_token_logits,prefill_logits.next_token_logits))
                    record["unprofiled_logits_max_abs_diff"]=logits_max_abs
                    results.append(record); _free(pb,runner,pcache); continue
                # Retain real KV and Mamba state produced by real prefill.
                next_ids=prefill_argmax
                graph_runner=runner.decode_cuda_graph_runner
                fb,decode_logits=_decode(batch,runner,next_ids)
                key=getattr(graph_runner,"_replay_graph_key",None)
                if key is None: raise RuntimeError("Decode used no CUDA Graph identity")
                graph=repr(key)
                if getattr(key,"size",None)!=a.batch: raise RuntimeError(f"Graph key {key!r} does not match actual batch {a.batch}")
                # Graph warmup/capture is already complete; restore the exact
                # prefill state once more by rebuilding, to establish repeat input.
                torch.cuda.synchronize(runner.device)
                _free(batch,runner,cache)
                runner.req_to_token_pool.clear(); runner.token_to_kv_pool_allocator.clear()
                reqs=[_request(i,ids,4) for i,ids in enumerate(rows)]
                batch,cache=_new_batch(reqs,runner,cfg)
                _,prefill_logits=_prefill(batch,runner)
                torch.cuda.synchronize(runner.device)
                next_ids=prefill_logits.next_token_logits.argmax(dim=-1)
                fb=_decode_prepare(batch,runner,next_ids)
                label=f"falcon-decode-b{a.batch}-r{rep}"
                fb.t002_cupti_ranges=prof
                fb.t002_cupti_metadata=(label,rep,"decode",a.batch,1)
                fb.t002_cupti_expected_graph=graph
                graph_events=(torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True))
                fb.t002_cupti_event_pair=graph_events
                fb.t002_cupti_finalize_after=True
                prof.enable()
                logits,record=_profile_forward(prof,runner,lambda: runner.forward(fb).logits_output,
                    label=label,iteration=rep,stage="decode",batch=a.batch,tokens=1,graph="CUDA_GRAPH")
                # Graph backend records the measured events after CUPTI arm and
                # directly around graph replay, excluding host-side profiler setup.
                graph_events[1].synchronize()
                elapsed=graph_events[0].elapsed_time(graph_events[1])
                record["gpu_event_ms"]=elapsed
                key_after=getattr(graph_runner,"_replay_graph_key",None)
                if repr(key_after)!=graph: raise RuntimeError("Graph identity changed during measured replay")
                predicted=logits.next_token_logits.argmax(dim=-1)
                logits_delta=(logits.next_token_logits-decode_logits.next_token_logits).abs()
                logits_max_abs=float(logits_delta.max().item())
                if not torch.equal(logits.next_token_logits,decode_logits.next_token_logits):
                    if not torch.equal(logits.next_token_logits.argmax(dim=-1),decode_logits.next_token_logits.argmax(dim=-1)):
                        raise RuntimeError("profiled decode argmax differs from deterministic unprofiled replay")
                record["fixture_sha256"]=fixture_sha; record["output_argmax"]=predicted.cpu().tolist()
                record["actual_batch"]=len(batch.reqs)
                record["mamba_pool_index"]=[int(r.mamba_pool_idx) for r in batch.reqs]
                record["unprofiled_logits_exact_match"]=bool(torch.equal(logits.next_token_logits,decode_logits.next_token_logits))
                record["unprofiled_logits_max_abs_diff"]=logits_max_abs
                record["graph_identity"]=graph; results.append(record)
                _free(batch,runner,cache)
        pathlib.Path(a.output).write_text(json.dumps({"model":MODEL,"revision":REVISION,"stage":a.stage,
            "batch":a.batch,"input_len":a.input_len,"fixture_sha256":fixture_sha,"repeats":results},indent=2)+"\n")
    finally:
        prof.disable()

if __name__=="__main__": main()
