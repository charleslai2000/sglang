# T014 — GPU Hardware Profiling of the Frozen C-8 Deployment

| | |
| --- | --- |
| Commit under test | `ed6cec9299cb0913286e7a19bbe176ec4e259955` (`3090-24g-hicache`), **unmodified** |
| Task scope | measurement only — no serving-path change, no new telemetry, no re-certification |
| Arms | **A = Marlin + Triton**, **B = Humming W4A16 + FA2 ragged extend** |
| Model | `/data/sglang-hicache/gemma4/model` (unchanged checkpoint, KV dtype `fp8_e5m2`) |
| GPU | NVIDIA GeForce RTX 3090 24 576 MiB, driver 580.178.04, SM max 2 100 MHz, power limit 350 W |
| Tools | Nsight Compute 2025.2.1 (CUPTI **ApplicationReplay**), Nsight Systems 2025.1.3 (CUDA + NVTX), NVML |
| Artefacts | `runs/20261128T-t014-ncu/`, `runs/20261128T-t014-nsys/` under `/data/sglang-hicache/gemma4/` |

## 1. What was measured and with which instrument

| Group | Instrument | Boundary | Status |
| --- | --- | --- | --- |
| 1 SM active/throughput/issue/occupancy | NCU ApplicationReplay, per-kernel | `cudaProfilerStart/Stop` around **one** production Forward | collected |
| 2 Tensor/FP16/FP32/INT/LSU/SFU pipes | NCU per-kernel (+ instruction-pipe supplement) | same | collected (`FP32-heavy` not exposed by this NCU section set) |
| 3 DRAM read/write GB/s + % peak | NCU per-kernel % + nsys CUPTI memcpy | same | per-kernel **% of peak** collected; per-kernel byte totals excluded (see §8) |
| 4 L1/L2 hit rate + throughput | NCU per-kernel | same | collected |
| 5 Warp stalls, registers, shared memory | NCU per-kernel (WarpStateStats/LaunchStats) | same | collected |
| 6 Peak VRAM, PCIe, clocks, power | NVML sampling + nsys memcpy | bounded 45 s service window | collected (whole-GPU, sampled) |
| 7 Attention/GEMM/other kernel time share | nsys kernel table | same window | collected, split by layer type and by runtime |

Deliberately **not** attempted: NCU kernel-replay inside the scheduler process — that
is the mode T010 already showed to be impossible on this stack. ApplicationReplay on
a standalone driver replaces it, so every NCU number below comes from a process that
runs the production `ModelRunner`, pools, quantisation scheme, attention backend and
CUDA graphs for a *single* Forward, not from the service.

## 2. Arms and what differs

| | W4A16 GEMM | Extend attention | Decode attention |
| --- | --- | --- | --- |
| A | Marlin `device::Marlin<…>` (frozen default) | Triton `_fwd_kernel` | grouped Triton decode, Full CUDA Graph |
| B | Humming `humming<MmaOpClass, …>` (`SGLANG_CTWNA16_HUMMING=1`) | FA2 ragged extend (`SGLANG_FA2_RAGGED_EXTEND=1`) for eligible Full layers, Triton otherwise | identical to A |

Everything else is held fixed: same checkpoint, same `kv_cache_dtype=fp8_e5m2`, same
CUDA-graph buckets, same attention backend (`triton`), same request shapes, and a
**pinned KV capacity of 1 300 000 full-pool tokens with a 65 536-token SWA pool in
every single cell** — verified per cell (`pool_full=1300000 pool_swa=65536
clamped=False`). The serving value under the frozen C-8 argv is 1 443 628 + 65 536;
the pin sits below the memory-derived value of every configuration (which differs
between arms and shrinks further under profiler instrumentation) so that both arms
and all shapes run the identical pool.

## 3. Shapes

| Cell | Shape | How it is produced |
| --- | --- | --- |
| P1024 / P4096 | prefill | one Extend of 1 024 / 4 096 tokens (production chunk size 4 096), eager |
| E16K+1024 | long-prefix Extend | real chunked prefill to 16 384 tokens, then an Extend of 1 024 tokens that attends over the resident prefix (FA2's actual target shape) |
| D8 / D16 / D32 | decode | captured production **Full CUDA Graph** replayed at batch 8/16/32 over one shared 8 192-token context (the C-8 shared-prompt workload) |

NCU profiles at most 120 matching launches per pass (200 for the FA2 prefix cell),
taken in launch order; per-class values are duration-weighted over the profiled
launches and the instance count is always shown, so coverage is auditable. Time
shares in §6 come from nsys, which sees *every* launch, not from these subsets.

## 4. Unified hardware-utilisation table

Forward-level columns are the profiled-launch-time weighted average over the kernel
classes present in that cell; `n.c.` = not collected by the sections used (see §8).

