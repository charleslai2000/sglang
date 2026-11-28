# T011 Attention Review — existing evidence only

**Status:** desk review only. No T011 experiment was started, no GPU workload was run, and no production source was changed for this review. This document consolidates the already-delivered T010 hardware profile, the existing Nsight Systems trace, and the frozen-source call paths. It does not propose an optimization.

**Source identity:** T010 report records production source `a76206a5fbd65b81ddbb470ac8088a46cf78697a` (abbreviated `a76206a5fb`); analysis baseline commit `c102ccbc5c`. The trace reviewed is `/data/sglang-hicache/gemma4/runs/20261127T-t010-hwprof/nsys/gemma4.sqlite`.

## 1. Completed GPU hardware profiling report

The complete delivered report is [`T010-GPU-HARDWARE-PROFILING-20261127.md`](T010-GPU-HARDWARE-PROFILING-20261127.md). Its findings are reproduced here in compact form; the T010 report remains authoritative for methodology, caveats, run manifests, and reproduction commands.

### Instrumentation and workload

The capture reused CUDA Profiler API markers, scheduler NVTX ranges, Nsight Systems 2025.1.3 GPU sampling and kernel timeline, and the existing DeviceTimer/FPM measurements. Production configuration: Gemma4 E4B NVFP4/GPTQ weights, `fp8_e5m2` KV, Triton attention, decode CUDA graphs up to batch 32, max-running 32, chunked prefill 4096, HiCache Full 8 GiB + Extent, and `--mem-fraction-static .94`. Seven profiled phases covered extend 1024/1280/4096, 32K chunked prefill, and decode batches 8/16/32. The capture contains 101,913 kernel launches, 39.2 s GPU activity and 10.92 s kernel busy.

### Existing benchmark context (definitions retained from T010)

| Workload | Result |
|---|---:|
| Short-context rotating C32, 1024 input + 256 output, 90 s | 819.20 output TPS; 3.20 req/s |
| Same workload, fully cached, 60 s | 1,774.92 output TPS; 6.93 req/s |
| Original C-8, L1 only, 800 requests | 643.77 output TPS; 318.12 s; 97.95% GPU duty |
| Original C-8, three tiers, same payload multiset | 594.23 output TPS; 344.65 s; 90.69% duty |
| Long-context L1 only | 78.66 output TPS; 1,874.54 s |
| Long-context three tiers | 112.51 output TPS; 1,310.62 s |

### GPU utilization by shape

| Forward shape | Span / kernel busy | SM active | SM issue | Tensor active | DRAM read | GPU active |
|---|---:|---:|---:|---:|---:|---:|
| Extend 1024 tokens (three spans) | 151–154 / 114–115 ms | 69–71% | 12.2–12.4% | 37.9–38.6% | 45.8–46.5% | 75–77% |
| Extend 1280 | 162 / 151.5 ms | 87.9% | 15.3% | 47.6% | 57.0% | 94.2% |
| Extend 4096 | 577 / 572–574 ms | 96.6–96.8% | 14.9–15.0% | 45.6–45.8% | 62.5–62.6% | 99.4–99.5% |
| Chunked 32K (8×4096) | 5665 / 5653 ms | 96.6% | 19.5% | 42.4% | 41.5% | 99.9% |
| Decode b8 | 56.5 / 56.0 ms | 61.6% | 13.9% | 5.8% | 49.9% | 100% |
| Decode b16 | 89.0 / 88.4 ms | 65.2% | 10.9% | 12.4% | 51.1% | 99.9% |
| Decode b32 | 115.8 / 115.2 ms | 68.0% | 11.5% | 16.6% | 49.4% | 99.9% |

The profile's operator budget attributed 47.0% of production C-8 kernel busy time to attention (extend `_fwd_kernel` 26.8%, decode `_fwd_grouped_kernel_stage1` 19.8%, stage 2 0.4%). In the seven-shape capture, reported shares were `_fwd_kernel` 40.4% (4.414 s/924 calls), `_fwd_grouped_kernel_stage1` 0.5% (53 ms/2,688 calls), and `_fwd_kernel_stage2` 0.04% (not in top rows; 6.95 ms total when summed from the per-grid rows below). These are different capture mixes and are not directly comparable.

Other reported context: KV pool 12.25 GB, weights 9.48 GB, decode graph pool 0.178 GB; the trace's seven-shape capture recorded 9.36 GB H2D and negligible D2H (capture used long-context restores). In the production C-8 trace, D2H was 7.58 GB and H2D negligible. GPU clock was 1.54–1.83 GHz in active spans. NCU per-kernel pipe/occupancy/stall/cache/DRAM-byte/power counters were **not collected**: scheduler replay failed for both Marlin and attention, and NVTX filters did not match. The report explicitly cautions that sampled utilization is not a per-kernel roofline diagnosis.

## 2. Full vs SWA Attention: trace evidence and limits

### What the trace actually identifies

The SQLite kernel table identifies kernel names, launch grids, counts and durations, but this capture has no Full/SWA layer identity attached to each kernel launch. The profiler's reliable structural attribution is:

* Extend `_fwd_kernel`: `gridZ` tracks query tiles, and `gridX`/`gridY` carry request/head axes. In the controlled T010 phases the analysis maps gridZ 16/20/64 to 1024/1280/4096 query tokens. The kernel itself runs for Full and SWA layers; the shared symbol does not encode layer type.
* Decode `_fwd_grouped_kernel_stage1`: split-KV stage 1; `gridX` varies with KV splits and `gridY=2` is the grouped-head tile count. Decode stage 2 is `_fwd_kernel_stage2`.
* No separate Full/SWA dispatch kernel symbol is present. Thus these rows cannot be reliably separated into Full and SWA costs from this trace alone. Kernel time divided by 2,688 launches or inferred model layer counts would not provide measured per-layer-type cost.

The exact aggregate rows available in the seven-shape trace (times are summed GPU kernel durations; grid values shown are `(X,Y,Z)`):

| Kernel | Grid | Calls | Total GPU ms | Mean us/call |
|---|---:|---:|---:|---:|
| Extend `_fwd_kernel` | (1,8,128) | 63 | 2708.544 | 42,993 |
| Extend `_fwd_kernel` | (1,8,64) | 315 | 878.691 | 2,789 |
| Extend `_fwd_kernel` | (4,8,16) | 140 | 323.968 | 2,314 |
| Extend `_fwd_kernel` | (4,8,32) | 28 | 130.398 | 4,657 |
| Extend `_fwd_kernel` | (3,8,16) | 70 | 119.222 | 1,703 |
| Extend `_fwd_kernel` | (1,8,16) | 140 | 82.784 | 591 |
| Extend `_fwd_kernel` | (3,8,32) | 14 | 47.860 | 3,419 |
| Extend `_fwd_kernel` | (2,8,16) | 35 | 40.034 | 1,144 |
| Extend `_fwd_kernel` | (1,8,32) | 28 | 28.359 | 1,013 |
| Extend `_fwd_kernel` | (1,8,20) | 35 | 26.468 | 756 |
| Extend `_fwd_kernel` | (2,8,32) | 7 | 15.068 | 2,153 |
| Extend `_fwd_kernel` | (1,8,40) | 7 | 11.155 | 1,594 |
| Decode stage 1 `_fwd_grouped_kernel_stage1` | (1,2,8) | 756 | 26.409 | 34.9 |
| Decode stage 1 | (12,2,8) | 630 | 10.514 | 16.7 |
| Decode stage 1 | (4,2,8) | 546 | 6.042 | 11.1 |
| Decode stage 1 | (16,2,8) | 210 | 4.032 | 19.2 |
| Decode stage 1 | (8,2,8) | 294 | 3.960 | 13.5 |
| Decode stage 1 | (32,2,8) | 84 | 0.611 | 7.3 |
| Decode stage 1 | (24,2,8) | 84 | 0.608 | 7.2 |
| Decode stage 1 | (2,2,8) | 84 | 0.427 | 5.1 |

The extend grid rows include multiple controlled phases and cannot be relabeled individually as Full or SWA from the SQL data. The Full/SWA-separated measured latency requested is therefore **not available in the existing trace**; the per-shape aggregate measurements above are the supported result. T010's production C-8 operator totals are additionally available, but are likewise not Full/SWA split.

### Model dispatch and call shapes from frozen source

* [`python/sglang/srt/models/gemma4_causal.py`](../../../../python/sglang/srt/models/gemma4_causal.py#L295) `Gemma4Attention` selects `layer_type = config.layer_types[layer_id]`. Full layers use configured `num_attention_heads`, `num_key_value_heads`, and `head_dim`; sliding layers use `swa_num_attention_heads` / `swa_num_key_value_heads` (falling back to regular counts) and `swa_head_dim` (falling back to `head_dim`). Both instantiate `RadixAttention`; SWA passes `sliding_window_size = config.sliding_window - 1`, while Full passes `-1`.
* A model layer receives `positions`, `hidden_states`, and `ForwardBatch`; Q/K/V projections and Q/K/V RMSNorm run before RoPE. Q is always formed; non-shared layers form K/V, apply RoPE to Q/K, and call `self.attn(q,k,v,...)`. A KV-sharing layer computes Q but supplies `k=None,v=None` and sets `save_kv_cache=False`.
* [`python/sglang/srt/configs/model_config.py`](../../../../python/sglang/srt/configs/model_config.py#L2210) derives Full and SWA IDs from the checkpoint's `layer_types` (`full_attention` and `sliding_attention`).
* [`python/sglang/srt/layers/attention/triton_backend.py`](../../../../python/sglang/srt/layers/attention/triton_backend.py#L1313) `forward_extend` uses the window metadata for layers with a sliding-window size, otherwise full KV metadata, and calls the Triton extend entry point. [`forward_decode`](../../../../python/sglang/srt/layers/attention/triton_backend.py#L1812) follows the same Full/SWA metadata selection and calls the decode entry point. Both pass layer descales when present.
* Exact production dimensions and layer counts depend on the loaded model checkpoint configuration. They are not inferred here from a model name; the checked-in model implementation uses config-provided dimensions as described above.

## 3. Complete source locations for the current Attention call and kernels

The code has not been copied into this report to avoid creating a divergent duplicate of several thousand lines. These source links point to the **complete definitions**, not selected snippets, at the frozen working tree; they are the canonical full source requested for review:

1. Gemma call path and Full/SWA setup: [`Gemma4Attention.__init__` and `.forward`](../../../../python/sglang/srt/models/gemma4_causal.py#L295-L526); decoder layer selects the Full/SWA head dimension at [`Gemma4DecoderLayer.__init__`](../../../../python/sglang/srt/models/gemma4_causal.py#L553-L590).
2. Triton backend dispatch and complete `forward_extend`: [`triton_backend.py`](../../../../python/sglang/srt/layers/attention/triton_backend.py#L1313-L1490); unified extend route: [
`_forward_extend_unified`](../../../../python/sglang/srt/layers/attention/triton_backend.py#L1640-L1800); complete `forward_decode`: [`triton_backend.py`](../../../../python/sglang/srt/layers/attention/triton_backend.py#L1812-L1980).
3. Prefill/extend kernel and dispatch implementation (including `_fwd_kernel`, its launch wrapper, unified variant, metadata assembly): [`python/sglang/kernels/ops/attention/extend_attention.py`](../../../../python/sglang/kernels/ops/attention/extend_attention.py). The main kernel starts at `_fwd_kernel` (around line 304); the public `extend_attention_fwd` and `extend_attention_fwd_unified` definitions follow the kernel bodies.
4. Decode kernels and dispatch implementation (including `_fwd_kernel_stage1`, grouped-head variants, stage 2, public `decode_attention_fwd`): [`python/sglang/kernels/ops/attention/decode_attention.py`](../../../../python/sglang/kernels/ops/attention/decode_attention.py).

The above files are the complete source of the invoked Python/Triton paths, including helper kernels and launch logic. The selected backend in this production configuration is Triton, per the T010 capture manifest/report.

## 4. Shared-KV FP8 read, conversion, mapping, and transfer path

### Layer ownership and mapping

In `Gemma4Attention.__init__`, the final `num_kv_shared_layers` layers reuse KV from the nearest preceding layer of the same `layer_type`: `kv_shared_layer_index` is chosen by reverse-searching `config.layer_types` before the shared suffix. `RadixAttention.layer_id` is set to that source layer id, so the attention backend addresses the source layer's KV buffers. Shared layers still compute their own Q and attention output, but do not write new K/V. Thus reuse here is KV *ownership/read reuse*, not reuse of a previously computed attention output.

### FP8 storage and decode read

The profiled production flag is `--kv-cache-dtype=fp8_e5m2`. `configure_kv_cache_dtype` resolves it to `torch.float8_e5m2` on CUDA. The MHA pool stores FP8 cache bytes (the pool's store view may use `uint8` for indexed writes). Newly produced non-shared K/V go through `RadixAttention`'s backend cache write and `MHATokenToKVPool.set_kv_buffer`; layer scales, if present, are passed to the pool. The underlying pool converts/casts or quantizes as dictated by dtype and configured quantization method.

For a shared layer, Gemma passes `k=None,v=None`. Triton `forward_extend` then obtains the layer's key/value buffers using the mapped source `layer.layer_id`, resolves request cache locations, gathers cached K/V, and currently casts gathered tensors to query dtype when the buffer dtype differs. The attention call still receives layer descale scalars when configured; `_fwd_kernel` applies K descale in the QK scale (`sm_scale * k_scale`) and V descale to the value accumulator. For decode, the kernel reads the FP8 K/V pool directly; stage 1 uses `sm_scale * k_scale` and stage 2 multiplies the output by `v_scale`. The stored FP8 representation is therefore not an independently materialized BF16 cache copy; conversion/casting behavior is at the gather/kernel boundary according to the path and dtype.

### Address mapping and transfer

Full and SWA cache buffers have separate metadata/index domains. `forward_extend` / `forward_decode` select full or sliding-window `kv_indptr` and `kv_indices` by `layer.sliding_window_size`; for shared layers the mapped source layer id selects the owner buffer. Pool wrapper mapping then routes the owner to the underlying Full or SWA sub-pool. Shared-page buffers can be 4-D `[num_pages,page_size,heads,dim]`; `decode_attention.py::_extract_kv_strides` supplies page/token strides to the kernels. The kernel maps each logical KV index to a physical token/page and head using those strides.

Attention's GPU read path is not itself an inter-device transfer. HiCache/device-host/Extent transfers happen at cache backup or restore boundaries, outside the per-token attention kernel. T010's seven-shape trace reports H2D 9.36 GB / 1,984 ms and negligible D2H in its capture; the report attributes those H2D copies to long-context KV restores. Its production C-8 trace reports 7.58 GB D2H / 678 ms and negligible H2D. These totals are not specifically attributable to shared-KV layers and must not be described as per-layer traffic.

## 5. Source/evidence references

* Hardware report and trace inventory: [`T010-GPU-HARDWARE-PROFILING-20261127.md`](T010-GPU-HARDWARE-PROFILING-20261127.md), raw SQLite `/data/sglang-hicache/gemma4/runs/20261127T-t010-hwprof/nsys/gemma4.sqlite`.
* Gemma model call: [`python/sglang/srt/models/gemma4_causal.py`](../../../../python/sglang/srt/models/gemma4_causal.py).
* Triton backend dispatch: [`python/sglang/srt/layers/attention/triton_backend.py`](../../../../python/sglang/srt/layers/attention/triton_backend.py).
* Extend implementation: [`python/sglang/kernels/ops/attention/extend_attention.py`](../../../../python/sglang/kernels/ops/attention/extend_attention.py).
* Decode implementation: [`python/sglang/kernels/ops/attention/decode_attention.py`](../../../../python/sglang/kernels/ops/attention/decode_attention.py).
* KV dtype resolution: [`python/sglang/srt/mem_cache/kv_cache_dtype.py`](../../../../python/sglang/srt/mem_cache/kv_cache_dtype.py); cache writes and buffer views: [`python/sglang/srt/mem_cache/memory_pool.py`](../../../../python/sglang/srt/mem_cache/memory_pool.py); Full/SWA pool routing: [`python/sglang/srt/mem_cache/swa_memory_pool.py`](../../../../python/sglang/srt/mem_cache/swa_memory_pool.py).

**Unresolved by existing evidence:** per-layer Full-vs-SWA latency and shared-layer-specific H2D/D2H bytes cannot be reconstructed from this trace because it contains no per-launch layer/type identity or transfer ownership labels. No missing values are imputed in this review.
