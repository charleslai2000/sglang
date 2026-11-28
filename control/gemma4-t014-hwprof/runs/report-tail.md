## 5. What the counters say, group by group

### 5.1 SM and scheduling (group 1)

Prefill is a dense, well-fed workload: the Marlin GEMMs run at **82.6 % SM
throughput / 83.5 % tensor-pipe** (P4096) and Humming at **87.9 % / 89.0 %**. Both
arms sit at ~18.7 % *achieved occupancy*, which is not a stall symptom here — the
GEMM kernel is register-heavy (255 registers/thread) and the tensor pipe is the
binding resource (stall reason #1 for both arms is `math_pipe_throttle`), so more
resident warps would not add throughput.

Decode is the opposite regime. At D32 the GEMM class runs at **21.2 % SM / 26.1 %
tensor (A)** and **34.6 % / 42.5 % (B)**; issue-active is 18.8 % vs 30.0 %. This is
the hardware signature of the T012 decode win, measured on the same 48 profiled GEMM
launches: A's decode GEMM spends **20.0 % of its issue slots on `barrier`** — the
Marlin split-K reduction — while B's dominant stall is `math_pipe_throttle` at 1.4 %.
(Absolute kernel durations are taken from nsys, not from NCU's duration column; see
§8.)

### 5.2 Compute pipes (group 2)

Tensor-pipe utilisation tracks the GEMM story exactly: P4096 51.9 % (A) → 54.8 % (B)
in the main table, and per class 83.5 % → 89.0 %. IMMA (integer tensor) is 0 in both
arms — the W4A16 weights are unpacked to BF16 and multiplied on HMMA, so no INT
tensor work exists at this layer. FP64 is 0 everywhere.

The instruction-pipe supplement shows the memory-side pipelines:

| class (P4096) | LSU % | SFU/XU % | TEX % | ADU % |
| --- | ---: | ---: | ---: | ---: |
| Marlin GEMM (A) | 16.0 | 0.1 | 0.0 | 0.9 |
| Humming GEMM (B) | 12.4 | 0.0 | 0.0 | 0.7 |
| Extend attention (both) | 15.9 / 16.2 | 0.5 / 0.6 | 0.0 | 1.0 |
| Decode attention (D32) | 42.0 / 42.1 | 1.7 / 1.7 | 0.0 | 2.4 |

Decode attention is the only place where LSU pressure (42 %) approaches a real
limit; the GEMMs are tensor-pipe bound, not LSU bound.

### 5.3 DRAM (group 3)

Per-kernel **% of DRAM peak** is available and differs sharply between arms on the
same shape:

| | P4096 DRAM read % of peak | P4096 L2 hit rate | D32 DRAM read % of peak |
| --- | ---: | ---: | ---: |
| A (Marlin) | 78.8 | 16.5 % | 24.2 |
| B (Humming) | 12.6 | 82.7 % | 40.3 |

The prefill difference is large and reproducible across the collected cells: the
Marlin GEMM streams weight tiles from DRAM (L2 hit 16.5 %, DRAM read near peak),
whereas Humming's larger tile shapes (`Shape<0, 20480, 2560>` etc.) reuse the same
weight bytes across the 4 096-token M dimension out of L2 (82.7 % hit, 12.6 % of
DRAM peak). At decode the relation inverts: at M=32 Humming reads weights once per
launch and runs at 40.3 % of DRAM peak versus Marlin's 24.2 % (and 214.6 GB/s vs
155.9 GB/s of measured bandwidth), because Marlin's split-K re-reads.

Measured **total** DRAM bandwidth in the profiled launches: P1024 649 GB/s (A) vs
313 GB/s (B), P4096 746 vs 393 GB/s, D32 156 vs 215 GB/s. The 3090's theoretical
peak is 936 GB/s, so prefill-A is at ~80 % of peak DRAM while prefill-B has ~2×
headroom.

### 5.4 L1 / L2 (group 4)

L1TEX hit rate is low in both arms and in every shape (5–12 %), which is expected:
the GEMMs bypass L1 through `ldg`-style streaming loads and only attention and the
small elementwise kernels get L1 reuse. L2 is where the arms separate, as above
(prefill 37.3 % → 76.2 %; decode 71.3 % → 68.6 %; long-prefix extend 60.3 % →
82.5 %). L2 throughput is 44.0 % (A) / 39.1 % (B) at P4096 and 21.8 % / 26.9 % at
D32 — nowhere near the L2 limit, i.e. the prefill GEMM limit is DRAM-side for A and
tensor-side for B.

### 5.5 Warps, registers, shared memory (group 5)

Per kernel class (the Forward-level rows in §4 are time-weighted across classes):

| | Marlin (prefill / decode) | Humming (prefill / decode) |
| --- | --- | --- |
| registers/thread | 255 / 198 | 255 / 123 |
| shared memory/block | 102 KB / 102 KB | 77 KB / 41 KB |
| dominant stall | `math_pipe_throttle` / `barrier` (20.0 %) | `math_pipe_throttle` / `math_pipe_throttle` (1.4 %) |

Marlin's 255-register, 102 KB-shared prefill kernel caps theoretical occupancy at one
to two blocks per SM; Humming needs 77 KB and reaches a higher tensor-pipe share at
the same measured occupancy. On decode the gap widens: Marlin keeps 198 registers and
102 KB of shared memory to do split-K reduction, Humming 123 registers and 41 KB.
Attention kernels sit at 184–225 registers (extend/decode), also occupancy-limited,
with `long_scoreboard` (global-memory latency) as the dominant stall — the classic
signature of KV reads that no amount of extra warps can hide.

### 5.6 Envelope: VRAM, clocks, power, PCIe (group 6, whole-GPU sampled)

| | A (tiers-triton) | B (tiers-fa2) |
| --- | ---: | ---: |
| peak VRAM (NVML max) | 24 112 MiB | 24 010 MiB |
| SM clock mean / max | 1 461 / 1 935 MHz | 1 457 / 1 890 MHz |
| memory clock mean / max | 7 877 / 9 751 MHz | 7 877 / 9 751 MHz |
| board power mean / max | 211.2 / 350.9 W | 209.7 / 350.0 W |
| temperature mean / max | 59.0 / 77 °C | 61.6 / 77 °C |
| PCIe link (NVML) | gen 1–3 × 16 | gen 1–3 × 16 |
| CUPTI memcpy HtoD / DtoH / DtoD | 0.00 / 0.067 / 0.003 GB/s | 0.00 / 0.066 / 0.11 GB/s |

Both arms run the GPU to its 350 W board limit at peaks, at ~1.46 GHz average SM clock
and 23.5 GiB of the 24 GiB device (24 112 / 24 010 MiB peak). HtoD traffic is negligible in this
workload (weights are resident; prompts are tiny), so PCIe is not a factor and the
link idles down to gen 1 between bursts. These are NVML samples of the whole device,
not per-kernel counters.

### 5.7 Kernel time share and layer-type attribution (group 7)

Bounded 45 s steady-state window of the **production C-8 three-tier HiCache stack**
(identical argv, only the two switches differ), 1.0 M kernel launches per window:

| kernel class | A share | B share |
| --- | ---: | ---: |
| Humming W4A16 GEMM | 37.86 % | 37.41 % |
| Extend attention (all runtimes) | 26.77 % | 26.36 % |
| Decode attention (grouped Triton) | 21.82 % | 22.77 % |
| cuBLAS BF16 GEMM (unquantised layers) | 4.37 % | 4.31 % |
| RMSNorm / activation / RoPE | 2.85 / 1.59 / 0.48 % | 2.83 / 1.57 / 0.47 % |
| everything else | 4.25 % | 4.27 % |

Attention is split by launch signature, not by assumption:

| full/split | A | B |
| --- | ---: | ---: |
| Full layers (head_dim 512), Triton `_fwd_kernel` | 8 706 ms / 1 722 launches / 26.21 % | 7 972 ms / 1 583 launches / 23.94 % |
| Full layers, FlashInfer `BatchPrefillWithRaggedKVCacheKernel` | — | 621 ms / 198 launches / 1.87 % |
| SWA layers (head_dim 256), Triton | 171 ms / 37 087 launches / 0.51 % | 171 ms / 36 689 launches / 0.51 % |

Three facts follow directly from the data:

1. **Full-layer extends dominate attention**, SWA layers are 0.5 % of kernel time —
   the 80 KB shared-memory tile on the head_dim-512 launch is what separates the two
   families, and the SWA family is identical in both arms.
2. **FA2 covers a minority of Full-layer extends in this workload**: 198 FlashInfer
   launches replacing Triton launches, i.e. the 128 MiB transient-prefix ceiling
   rejects most long-prefix Forwards. Where it does engage it is cheaper:
   3.1 ms/launch (FlashInfer) vs 5.0 ms/launch (Triton) for the same class.
3. Decode attention is unchanged between arms (22.8 % vs 21.8 %, inside the
   window-to-window variation of a different mix of prefill/decode Forwards), as
   designed — FA2 is an extend-only path.

## 6. Where the time goes, and what limits it

- **Prefill**: GEMM-bound on the tensor pipe for both arms; A additionally sits at
  ~80 % of DRAM peak, B at ~40 %. The hardware therefore predicts what T012
  measured: replacing Marlin with Humming removes a DRAM bottleneck and raises
  tensor-pipe utilisation (83.5 % → 89.0 %).
- **Decode**: tensor-pipe utilisation collapses for both arms (26 % A / 42 % B) —
  skinny M makes the GEMM latency- and DRAM-bound. Marlin's split-K reduction
  (20 % `barrier` stalls, 102 KB shared memory) is the visible cost; Humming needs
  less of both.
- **Attention**: Full-layer extend is the single largest kernel in the service window
  (26 % of GPU time, 5 ms per launch). Its limits are global-memory latency
  (`long_scoreboard`) and shared-memory footprint, not tensor throughput — which is
  exactly the space FA2 improves per launch, and why the transient-prefix ceiling,
  not the arithmetic, bounds its share.

## 7. Reproduction

```
# per-shape counters (12 cells, CUPTI ApplicationReplay)
control/gemma4-t014-hwprof/runs/run_matrix_ncu.sh
# instruction-pipe + DRAM-percentage supplement (4 cells)
control/gemma4-t014-hwprof/runs/run_supplement_ncu.sh
# FA2-attributed long-prefix cell (200-launch budget)
env T014_LAUNCH_COUNT=200 control/gemma4-t014-hwprof/runs/run_ncu.sh \
  <out> --stage prefix --prefix-len 16384 --new-len 1024 --arm humming --attn fa2 --out <json>
# bounded service window per arm (nsys + NVML)
control/gemma4-t014-hwprof/runs/run_nsys_tiers.sh triton
control/gemma4-t014-hwprof/runs/run_nsys_tiers.sh fa2
# reduction
python3 control/gemma4-t014-hwprof/runs/t014_ncu_analyze.py <cell>...
python3 control/gemma4-t014-hwprof/runs/t014_nsys_analyze.py <cell> --nvml <csv>
python3 control/gemma4-t014-hwprof/runs/t014_build_report.py
```

Raw artefacts: `/data/sglang-hicache/gemma4/runs/20261128T-t014-ncu/` (16 `.ncu-rep`
reports, per-cell JSON, `analysis/summary.json`, `analysis/tables.md`) and
`/data/sglang-hicache/gemma4/runs/20261128T-t014-nsys/` (two `.nsys-rep` + `.sqlite`
windows, `nvml-*.csv`, `nsys-analysis.json`). Two superseded cells are kept for
audit in `…/20261128T-t014-ncu/samples/`: the first one used a kernel filter that
could not match templated `Marlin<…>` names (`badregex-`), the second was taken
before the KV pool was pinned (`pinned1443-`).

## 8. Limitations and explicitly missing metrics

| Item | Why | Consequence |
| --- | --- | --- |
| Whole-GPU SM-issue / SMs-active / tensor-active / DRAM-read % from nsys GPU metrics | `nsys --gpu-metrics-devices` needs root on this driver (`ERR_NVGPUCTRPERM`); the service was not run as root | whole-GPU *utilisation* percentages are not reported; per-kernel equivalents come from NCU, clocks/power/VRAM from NVML |
| Per-kernel DRAM byte totals | NCU applies a per-report display scale to `dram__bytes*` columns; values are not comparable across reports (observed 0.45 ↔ 3 736 for the same class) | reported as DRAM **% of peak** and measured GB/s only |
| `FP32-heavy` pipe | not emitted by the section set on this GPU | `n.c.` |
| Per-kernel counters for the *service* process | NCU cannot attach to it without the T010 kernel-replay mode that already failed | service window gives kernel time shares + NVML, not counters |
| Decode cells use a shared 8 192-token context | keeps the SWA working set inside the production pool without the scheduler's eviction bookkeeping | decode attention is measured at a realistic shared-prefix length, not at tail 24 K contexts |
| Profiled-launch subsets (120/200 launches per cell) | bounds runtime (~11–22 min per cell) | per-class counters cover the first layers of each Forward; counts are printed so nothing is hidden |
| 45 s windows | bounded, per the repo workload rules | TPS in those windows (608.5 A / 617.7 B) is *not* a performance result and is not used as one |

## 9. Verdict

The hardware data explains the accepted behaviour rather than contradicting it:
Humming removes a DRAM bottleneck in prefill (DRAM read 78.8 % → 12.6 % of peak,
L2 hit 16.5 % → 82.7 %) and raises tensor-pipe utilisation (83.5 % → 89.0 %), while
on decode it avoids Marlin's split-K reduction (barrier stalls 20.0 % → 1.4 %,
registers 198 → 123). Full-layer extend attention is the largest single consumer of
GPU time (26 % of the window), its limiting factors are global-memory latency and
shared-memory footprint, and FA2 — bounded by the 128 MiB transient-prefix ceiling —
replaces only a minority of those launches although it is ~38 % cheaper per launch
when it does. No arm-specific bottleneck appears in VRAM, clocks, power or PCIe.
