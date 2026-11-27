# Gemma4 / RTX 3090 GPU hardware profiling — 2026-11-27

Frozen source **`a76206a5fb`** (branch `3090-24g-hicache`, clean worktree). T010 was frozen at this
SHA and this report changes **no** production compute code: it only adds measurement drivers,
a capture wrapper and analysis scripts under `control/` and the run directory.

Scope: hardware-resource utilisation of the real forward shapes, to let the architect choose an
optimisation target. T010's tier result is preserved as delivered (+43% TPS three-tier vs L1-only);
anchor restore, eviction algorithms and L3 capacity work are **not** touched here.

---

## 1. What was measured, with which instrument

Reused, not rebuilt:

| Instrument | Reused from | Used for |
|---|---|---|
| CUDA Profiler API markers (`/start_profile`, `/stop_profile`) | `control/falcon-h1-3090-hicache-perf/runs/R17-…/ncu_marker_capture.py` | bounding each measured phase to the post-warmup steady state |
| `scheduler.run_batch` NVTX spans | `SGLANG_ENABLE_NVTX_SCHEDULER=1` (T007/T009 wrappers) | forward boundaries |
| Nsight Systems 2025.1.3 with per-GPU sampling metrics | `control/queued-prefetch-host-ready`, T007 R17 procedure | kernel table + `SMs Active`, `SM Issue`, `Tensor Active`, `DRAM Read/Write %peak`, `GPU Active`, `GPC clock`, PCIe memcpy |
| DeviceTimer / FPM duty numbers | T007/T009/T010 wrappers | load-level duty cross-checks |
| Nsight Compute 2025.2.1 | `control/falcon-h1-3090-cupti-forward` recipe | attempted per-kernel counters — **failed, see §7** |

Measurement driver: `runs/20261127T-t010-hwprof/hw_capture.py` (adapted from the R17 marker script)
plus `run_ncu_capture.sh`, `analyze_hw.py`, `analyze_hw2.py`.
Production config held fixed: Gemma4 E4B NVFP4/GPTQ weights, `fp8_e5m2` KV, triton attention,
decode CUDA graph bs≤32, max-running 32, chunked prefill 4096, HiCache Full 8 GiB + Extent,
`write_back` + `wait_complete`, prefill graph disabled, `--mem-fraction-static .94`.

## 2. Representative loads (existing records, not re-run)

| Cell | Workload | Throughput | GPU duty | Evidence |
|---|---|---|---|---|
| A — short ctx, rotating | 1024 in / 256 out, C32 steady, 90 s | **819.20 output TPS** (3.20 req/s, p50 9.20 s) | — | `T007-SYNC-PYTHON-AND-STEADY-C32-20261126.md` |
| A — short ctx, fully cached | same, 60 s | **1,774.92 output TPS** (6.93 req/s, p50 4.68 s) | — | same |
| B — original C-8, L1 only | 40×20, 800 req, 1024/256 | **643.77 TPS**, 318.12 s | 97.95% | `20261125T-t007-r3-l1only-c8-r2` |
| B — original C-8, three tiers | identical payload multiset | **594.23 TPS**, 344.65 s, 552 graph replays | 90.69% | `20261126T-t009-pcg-c8-r10` |
| C — long ctx, L1 only | 96×6×5000, 256 out, ≈36.5K final ctx | **78.66 TPS**, 1874.54 s | 99.54% | `20261126T-t010-l1-only-longctx-r1` |
| C — long ctx, three tiers | same 10,448,641 prompt tokens | **112.51 TPS**, 1310.62 s | 93.36% | `20261126T-t010-l3-longctx-r1` |

The B rows are the same request multiset (verified by the payload-hash log), so the 7.7% drop is
the measured cost of serving through the host/Extent tiers, not a workload difference.

## 3. GPU resource utilisation by real forward shape

Source: `runs/20261127T-t010-hwprof/nsys/gemma4.sqlite` — one capture, 7 phases (extend 1024,
extend 1280, extend 4096, 32K chunked prefill, decode b8/b16/b32; 101,913 kernel launches, 39.2 s of
GPU activity, 10.92 s kernel busy). A *span* is a contiguous GPU-active window (a gap > 1 ms starts
a new span). Shapes are identified from `_fwd_kernel` `gridZ` (= tokens/64 for extend: 16 → 1024,
20 → 1280, 64 → 4096) and from the decode-attention `_fwd_grouped_kernel_stage1` count; the raw
per-span table is `hw_spans.json`, the identification query is in `analyze_hw.py`.

### 3.1 Extend (prefill) by token count

| Shape | span (ms) | kernel busy (ms) | busy/dur | SMs Active | SM Issue | Tensor Active | DRAM read %peak | DRAM write %peak | Warps in flight | GPU Active | GPC clock |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1024 tok | 154.1 | 115.1 | 74.7% | 69.4% | 12.3% | 38.1% | 45.8% | 13.6% | 15.3% | 75.3% | 1.73 GHz |
| 1024 tok (repeat 1) | 153.2 | 114.1 | 74.5% | 69.2% | 12.2% | 37.9% | 45.8% | 13.7% | 15.2% | 75.1% | 1.77 GHz |
| 1024 tok (repeat 2) | 151.4 | 114.8 | 75.8% | 70.5% | 12.4% | 38.6% | 46.5% | 13.8% | 15.5% | 76.5% | 1.75 GHz |
| 1280 tok | 162.0 | 151.5 | 93.5% | 87.9% | 15.3% | 47.6% | 57.0% | 17.4% | 19.2% | 94.2% | 1.66 GHz |
| 4096 tok | 577.1 | 572.4 | 99.2% | 96.6% | 14.9% | 45.6% | 62.5% | 22.6% | 20.4% | 99.4% | 1.59 GHz |
| 4096 tok (repeat) | 577.6 | 573.5 | 99.3% | 96.8% | 15.0% | 45.8% | 62.6% | 22.6% | 20.5% | 99.5% | 1.58 GHz |
| 1024 tok, batched ×8 | 842.9 | 837.4 | 99.3% | 96.3% | 16.8% | 53.5% | 67.8% | 17.2% | 20.8% | 99.7% | 1.57 GHz |
| 1024 tok, batched ×16 | 1812.3 | 1804.2 | 99.6% | 96.8% | 17.0% | 54.4% | 68.0% | 17.3% | 21.1% | 99.8% | 1.54 GHz |
| 1024 tok, batched (dec32 phase) | 240.2 | 236.1 | 98.3% | 94.4% | 16.8% | 53.5% | 65.7% | 17.4% | 20.5% | 98.7% | 1.59 GHz |

Single-request extend 1024 is the only shape with visible headroom inside its own span
(74.7% duty; 25% of the span is host-side launch/setup gap), and it also has the lowest
`SMs Active` of the extend family.

### 3.2 Long-context extend (32K prompt, chunk = 4096, 8 chunks in one span)

| Shape | span (ms) | kernel busy (ms) | busy/dur | SMs Active | SM Issue | Tensor Active | DRAM read %peak | DRAM write %peak | Warps in flight | GPU Active | GPC clock |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 32768 tok, 8×4096 chunks | 5665.0 | 5653.4 | 99.8% | 96.6% | 19.5% | 42.4% | 41.5% | 16.2% | 19.3% | 99.9% | 1.62 GHz |

### 3.3 Decode by batch size (production CUDA-graph batches)

| Shape | span (ms) | kernel busy (ms) | busy/dur | SMs Active | SM Issue | Tensor Active | DRAM read %peak | DRAM write %peak | Warps in flight | GPU Active | GPC clock |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| decode b8 | 56.5 | 56.0 | 99.2% | 61.6% | 13.9% | 5.8% | 49.9% | 1.0% | 19.3% | 100.0% | 1.69 GHz |
| decode b16 | 89.0 | 88.4 | 99.3% | 65.2% | 10.9% | 12.4% | 51.1% | 1.1% | 8.8% | 99.9% | 1.83 GHz |
| decode b32 | 115.8 | 115.2 | 99.5% | 68.0% | 11.5% | 16.6% | 49.4% | 1.8% | 10.1% | 99.9% | 1.81 GHz |
| decode step (smaller batch) | 36.8 | 36.6 | 99.5% | 46.9% | 9.5% | 4.2% | 36.9% | 0.8% | 13.3% | 99.9% | 1.83 GHz |
| decode step (smaller batch) | 26.6 | 26.1 | 98.2% | 63.5% | 11.4% | 12.6% | 47.3% | 1.2% | 9.0% | 98.4% | 1.65 GHz |
| decode step (smaller batch) | 20.1 | 19.7 | 97.8% | 66.0% | 12.3% | 16.9% | 45.7% | 2.1% | 10.3% | 97.7% | 1.60 GHz |

Batch size moves decode from 5.8% → 16.6% `Tensor Active` and 61.6% → 68.0% `SMs Active` while
`DRAM read` stays ~49–51% of peak: decode is memory-traffic dominated at every batch size measured,
and the SM cost per step grows sub-linearly with batch (56.5 → 115.8 ms for 8 → 32).

### 3.4 Class averages

| Class | spans | kernel busy (s) | duty | SMs Active | SM Issue | Tensor Active | DRAM read | DRAM write | Warps in flight | GPU Active |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Extend, short ctx | 9 | 4.13 | 90.5% | 86.4% | 14.7% | 46.1% | 58.0% | 17.3% | 18.7% | 90.9% |
| Extend, 32K ctx | 1 | 5.65 | 99.8% | 96.6% | 19.5% | 42.4% | 41.5% | 16.2% | 19.3% | 99.9% |
| Decode (b8…b32) | 6 | 0.34 | 98.9% | 61.9% | 11.6% | 11.4% | 46.7% | 1.3% | 11.8% | 99.3% |

### 3.5 Idle windows inside the capture (for contrast)

6 spans of 294–303 ms carried only 17–26 ms of kernel work: `SMs Active` 4.0–5.2%, `SM Issue`
1.1–1.2%, `GPU Active` 6.4–9.3%. The device idles completely between batches, and the clock stays
at its boosted value in every active span — nothing here is clock- or power-throttled.

## 4. Operator-level budget

### 4.1 Production C-8 window (T007/T009 profile r7, 120.06 s window, 99.81 s kernel busy, 83.1% duty)

| Rank | Kernel | GPU ms | Share of busy | Calls | Interpretation |
|---:|---|---:|---:|---:|---|
| 1 | `_fwd_kernel` (extend attention, triton) | 26,782 | 26.8% | 5,376 | prefill attention |
| 2 | `Marlin<bf16,…,256,4>` (W4A16 GEMM) | 24,794 | 24.8% | 43,984 | dense/MoE projection |
| 3 | `_fwd_grouped_kernel_stage1` (decode attention split) | 19,738 | 19.8% | 85,439 | decode attention |
| 4 | `Marlin<bf16,…,256,2>` (W4A16 GEMM) | 17,324 | 17.4% | 514,670 | small-M projection |
| 5 | `ampere_bf16_s16816gemm_bf16_128x64…` (CUTLASS) | 3,199 | 3.2% | 2,034 | PLE / big GEMM |
| 6 | flashinfer `RMSNormKernel` | 1,534 | 1.5% | 365,423 | norms |
| 7 | `act_and_mul_kernel` (gelu·mul) | 1,189 | 1.2% | 90,815 | MLP activation |
| 8 | `vectorized_elementwise_kernel(add)` | 790 | 0.8% | 183,793 | residual add |
| 9 | flashinfer `FusedAddRMSNormKernel` | 656 | 0.7% | 90,815 | fused add+norm |
| 10 | `_gemma_qkv_rmsnorm_kernel` | 397 | 0.4% | 90,816 | QK-norm |
| 11 | `_fwd_kernel_stage2` | 393 | 0.4% | 85,439 | decode attention reduce |
| 12 | `fused_rope_kernel` (256 + 512) | 383 | 0.4% | 90,816 | RoPE |
| — | everything else (softcap/argmax/copies…) | ~2,700 | 2.7% | — | sampler, logits |

Grouped: **attention 47.0%**, **Marlin GEMM 42.2%**, norms 2.7%, activation 1.2%, RoPE 0.4%,
sampler/logits 2.0%, residual/elementwise 2.2%.

### 4.2 Seven-shape capture (whole-window shares, 10.92 s busy)

| Kernel | GPU ms | Share | Calls | regs/thread | static smem | block | grid (modal) |
|---|---:|---:|---:|---:|---:|---:|---|
| `Marlin<bf16,…,256,4>` | 5,071 | 46.4% | 7,563 | 255 | 0 | 256 | 82×… |
| `_fwd_kernel` | 4,414 | 40.4% | 924 | 149 | 0 | 256 | (1,8,64) |
| `act_and_mul_kernel` | 209 | 1.9% | 3,612 | 26 | 0 | 256 | 20,480 |
| `Marlin<…,256,2>` | 183 | 1.7% | 10,373 | 96 | 0 | 256 | 82 |
| flashinfer `RMSNormKernel` | 164 | 1.5% | 14,534 | 64 | 0 | 128 | 1,024 |
| `vectorized_elementwise(add)` | 118 | 1.1% | 7,310 | 37 | 0 | 128 | 43,008 |
| `Marlin<…,256,2>` (variant) | 97 | 0.9% | 5,060 | 150 | 0 | 256 | 82 |
| flashinfer `FusedAddRMSNormKernel` | 79 | 0.7% | 3,612 | 156 | 0 | 128 | 1,024 |
| `ampere_bf16_s16816gemm_bf16_64x64…` | 76 | 0.7% | 49 | 102 | 49,152 | 128 | 4,096 |
| `elementwise_kernel<128,4,…nocast>` | 65 | 0.6% | 6,598 | 16 | 0 | 128 | 86,016 |
| `_fwd_grouped_kernel_stage1` | 53 | 0.5% | 2,688 | 180 | 0 | 128 | (1..16,2,8) |
| `gemv2T_kernel_val` | 50 | 0.5% | 33 | 60 | 2,560 | 128 | 32,768 |
| `_gemma_qkv_rmsnorm_kernel` | 50 | 0.5% | 3,612 | 23 | 0 | 128 | 4,096 |
| `fused_rope_kernel<…256…>` | 37 | 0.3% | 3,010 | 34 | 0 | 128 | 984 |

Per-call cost: `_fwd_kernel` 4.78 ms (mean), `Marlin<256,4>` 0.671 ms, `act_and_mul` 0.058 ms,
`RMSNormKernel` 0.041 ms.

## 5. Memory, PCIe and clock

| Item | Value | Source |
|---|---|---|
| Weight memory | 9.48 GB | `sglang:weight_memory_usage_gb` |
| KV cache memory | 12.25 GB | `sglang:kv_cache_memory_usage_gb` |
| Decode graph pool | 0.178 GB | `sglang:graph_memory_usage_gb{phase="decode"}` |
| Startup available GPU memory | 1.12 GB | `sglang:startup_available_gpu_memory_gb` |
| NVML used / total at steady state | 23,066 / 24,576 MiB | `gpu-samples.csv` (C-8 acceptance r6) |
| KV pool at steady state | Full 1,439,896 tok, SWA 65,536 tok | acceptance r6 metrics |
| Torch `allocated`/`reserved`/`peak` gauges | **not exported** by this build | not available |
| H2D in 7-shape capture | 9.36 GB / 1,984 ms (3,150 ops) | nsys `CUPTI_ACTIVITY_KIND_MEMCPY` |
| D2H in 7-shape capture | ~0 GB / 0.11 ms (78 ops) | same |
| H2D in production C-8 window | ~0 GB / 1.31 ms | r7 capture |
| D2H in production C-8 window | 7.58 GB / 678 ms (30,054 ops) | r7 capture |
| D2D in production C-8 window | 0.28 GB / 15.9 ms | r7 capture |
| SM / GPC clock under load | 1.54–1.83 GHz (span means; single-request extend 1.73–1.77, 4096 extend 1.58–1.59, decode 1.60–1.83) | nsys GPU metrics |
| SM clock idle | 210 MHz, memory clock 405 MHz, 27 W | NVML `nvidia-smi` (idle sample) |
| Power under load | **not collected** | see §7 |

PCIe/compute overlap: in both captures the H2D traffic is issued as synchronous copies on the copy
engine between batches (no concurrent-copy+compute overlap was observed in the sampled timeline);
during the seven-shape run the 9.36 GB of H2D (KV restores into the device pool at long context)
is serialised against compute, which inflates the extend spans above the production duty.

## 6. What the numbers say (and do not say)

* Every active span runs at the boosted clock; nothing is power- or clock-limited in this sample.
* Extend is **not** SM-issue-limited: `SM Issue` is 12–20% while `SMs Active` is 69–97% and
  `Tensor Active` 38–54%. The GPU is busy but far from saturating any single pipeline.
* Decode is a **latency/occupancy** regime: `Compute Warps in Flight` 9–19% and `Tensor Active`
  4–17% with `DRAM read` 37–51% of peak — small-batch GEMM/GEMV traffic with little pipeline work.
* Long-context extend raises `SMs Active` to 96.6% and `GPU Active` to 99.9% while `SM Issue`
  stays ≤19.5%; its `DRAM read` is 41.5% of peak versus 62.5% for a 1024-token extend, i.e. the
  32K prompt is served by the same arithmetic pipelines with *less* relative DRAM traffic per unit
  time (the spans are simply much longer). Batched 1024-token extends, not long context, are the
  highest-DRAM class (67.8–68.0% read).
* These are utilisation readings, not a roofline verdict: without per-kernel stall/pipeline data
  (§7) the limiting resource cannot be named.

## 7. Collection limits (explicit)

Nsight Compute per-kernel counters were **attempted and failed** on this host, so the following are
**NOT COLLECTED** and must not be inferred from the utilisation percentages above:

* per-kernel Tensor/FP32/FP16/INT pipe utilisation, LSU and SFU pipe utilisation;
* per-kernel achieved occupancy and warp-issue stall reasons;
* hardware L1/L2 cache hit rate and bandwidth (distinct from HiCache L1/L2/L3 tiers);
* per-kernel DRAM read/write bytes;
* per-kernel power draw, memory clock, thermal state.

Evidence of the failures (all preserved):

| Attempt | Result |
|---|---|
| `ncu --set detailed` on 30 kernels under `--profile-from-start off` + NVTX include | `==ERROR== Failed to profile "Marlin"`, `InterprocessLockFailed` |
| after clearing `/tmp/nsight-compute-lock` | profiling starts, then `Failed to profile "Marlin" in process <scheduler>` for every filter (`Marlin`, `_fwd_kernel`), `--lane`/`--mem-fraction .80` both fail |
| `--metrics` list on a plain torch matmul as root | succeeds (18 passes) — counter access itself is fine |
| NVTX filtering (`scheduler.run_batch`, `Default@…`, push/pop and start/end forms) | `No kernels were profiled` even in a minimal nvtx.annotate repro |

Logs: `runs/20261127T-t010-hwprof/ncu-run.log`, `ncu-test.log`, `ncu-test2.log`.
Conclusion: NCU cannot serialise (kernel-replay) kernels inside this scheduler process on this
driver/GPU combination; only the CUDA Profiler API marker path starts profiling, and it then fails
on the first replay. A CPU-side sampling profiler or a per-kernel IPC harness would be needed for
those columns — that is a tooling project, not a measurement tweak, and was not started here.

Additional limits of what *was* collected:

* Extend token counts are identified structurally from `_fwd_kernel` `gridZ` (16/20/64 → 1024/1280/4096),
  which is exact. Decode batch sizes are identified by phase order plus the monotone step durations
  (56.5/89.0/115.8 ms for b8/b16/b32); the three smaller decode spans cannot be assigned a batch
  with certainty and are reported as "smaller batch". The `/start_profile` stage trigger auto-stops
  after `num_steps`, so no explicit in-timeline phase marker exists; the driver's per-phase
  `result.json` and the span composition are the boundary evidence.
* GPU sampling metrics are device-wide 1 ms-class samples averaged over each span, so a span mixes
  its dominant kernel class with the small tail; they are not per-kernel.
* Percent-of-peak DRAM figures are Nsight's %peak; converting them to GB/s requires a peak
  assumption and was deliberately not done.
* The 7-shape capture runs at production config but with tracing/sampling enabled, so its absolute
  wall times are inflated (e.g. decode steps 20–116 ms vs 14.71 ms production TPOT). Utilisation
  percentages are the usable output, not the timings.

## 8. Raw evidence and reproduction

| Path | Content |
|---|---|
| `runs/20261127T-t010-hwprof/hw_capture.py` | phase driver (server + Perf API markers), SHA-256 in `manifest.json` |
| `runs/20261127T-t010-hwprof/run_ncu_capture.sh` | NCU attempt (kept for the failure record) |
| `runs/20261127T-t010-hwprof/nsys/gemma4.nsys-rep`, `gemma4.sqlite` | the capture and its 1.0 GB export |
| `runs/20261127T-t010-hwprof/nsys-run/` | per-phase `start.txt`/`stop.txt`/`result.json`, `launch-argv.txt`, `manifest.json` |
| `runs/20261127T-t010-hwprof/analyze_hw.py`, `analyze_hw2.py` | span segmentation, classification, GPU-metric joins |
| `runs/20261127T-t010-hwprof/range_index.json`, `hw_spans.json` | machine-readable per-span table behind §3 |
| `runs/20261127T-t010-hwprof/ncu-run.log`, `ncu-test.log`, `ncu-test2.log` | NCU failure evidence |
| `/data/sglang-hicache/gemma4/runs/20261126T-t009-c8-profile-r7/` | production C-8 nsys window behind §4.1 |

Reproduce the working measurement:

```bash
OUT=/data/sglang-hicache/gemma4/runs/20261127T-t010-hwprof
sudo -n env SGLANG_ENABLE_NVTX_SCHEDULER=1 /usr/local/bin/nsys profile \
  --trace=cuda,nvtx --cuda-graph-trace=node --cuda-event-trace=false \
  --gpu-metrics-devices=0 --force-overwrite=true -o "$OUT/nsys/gemma4" \
  /home/ubuntu/venvs/sglang-3090/bin/python "$OUT/hw_capture.py" \
  --phases ext1024,ext1280,ext4096,long,dec8,dec16,dec32 --port 31410 --out "$OUT/nsys-run"
nsys export --type sqlite -o "$OUT/nsys/gemma4.sqlite" "$OUT/nsys/gemma4.nsys-rep"
cd "$OUT" && python analyze_hw2.py
```

Source SHA: `a76206a5fbd65b81ddbb470ac8088a46cf78697a`; Nsight Systems 2025.1.3.140,
Nsight Compute 2025.2.1.0, torch 2.13.0+cu129, driver as reported by `nvidia-smi` at run time.
GPU returned to 1 MiB / 0% after every run; port 31406/31409/31410 clear; no extent data left in use.
