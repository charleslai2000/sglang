# c8 Falcon Scheduler NCU — first valid run

## Provenance / boundary
- Isolated worktree `/tmp/sglang-r17`, branch `r17-falcon-hicache`, base `20c837f1a3daaec47508feaecf5514dd586c636c`; model revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`; RTX 3090 / GA102 / CC 8.6; NCU 2025.2.1.
- Used `sudo -n ncu --set full --launch-count 48 --target-processes all -- <R17 venv python> orchestrate.py`; NCU connected to service PID 259746 and CUDA scheduler PID 259848. Stage evidence is the c8 decode scheduler timeline `profile-decode/r17-decode-TP-0-DECODE.trace.json.gz`, containing actual graph decode Marlin M=1, FlashInfer and Mamba update kernels.
- NCU was active through service boot/capture and the request window; frozen manifest requests 0–39 completed 40/40 with exactly 128 generated tokens. Due NCU replay, the c8 request batch took 202.28 s; this is **not clean throughput**. The NCU report captures first matching 48 scheduler CUDA launches after the collection became active; included launches are not all one model GEMM family, as shown by kernel identities below.
- Scheduler/source CUDA timeline independently corroborates M=1 Marlin, Mamba conv/scan and graph decode at c8; NCU captures graph-launched kernel executions. It does not make every profiled kernel phase-attributable without event-to-request timing joins.

## Artifacts
- Raw report: `falcon-scheduler.ncu-rep` (75,614,611 bytes).
- CSV raw export: `import.csv`; full decoded sections: `details.txt`; command stdout/stderr retained.
- Request outcomes: `requests.json`; service startup log: `../ncu-c8-decode-t2/server.stdout`.
- NCU `full` set offers per-kernel reports and multiple PM sampling pass groups. Inspect each kernel section and its metric units; do not average unrelated kernels or call this a GPU whole-window statistic.

## Representative observed values — kernel-level, not whole-GPU workload averages
Verified NCU sections include duration, SM throughput, DRAM throughput, L2 throughput/hit, tensor pipelines, occupancy, IPC/issue and stall sections. Selected sampled kernels from report (a kernel instance per row; heterogeneous kernels and launch shapes):

| Kernel | Duration | SM compute throughput (% peak sustained elapsed) | DRAM throughput (% peak sustained elapsed) | L2 hit rate | Tensor pipe (% peak active) | Achieved occupancy |
|---|---:|---:|---:|---:|---:|---:|
| `vectorized_elementwise_kernel<4, FillFunctor<int>>` | 2.27 us | 0.01% | 0.19% | 88.82% | 0% | 8.28% |
| another vectorized elementwise launch | 2.37 us | 0.01% | 0.19% | 92.12% | 0% | 8.56% |
| `vectorized_elementwise_kernel<4, FillFunctor<c10::BFloat16>>` | 6.62 us | 0.01% | 0.07% | 87.51% | 0% | 7.98% |
| sampled GEMM-like scheduler launch | 14.18 us | 29.79% | 8.21% | 86.82% | use trace/counter section; this launch is not asserted as Marlin | see per-kernel section |

The 14.18us row must not be labeled Marlin solely from this summary; NCU's first 48-launch sample includes setup/vector and GEMM kernels. The report details file is the source of exact kernel identity and associated counter section. GPU values such as SM throughput are per profiled kernel; NVML global utilization/clock/power/temp is a separate time-sampled window and is not yet archived for this run. L2 write hit ratio can exceed 100% in NCU's sector accounting and must not be presented as a bounded percentage; use load hit rate / definition instead.

## Scope / gaps
- **NCU c8 scheduler collection path PASS**: actual scheduler PID observed by NCU, Falcon workload requests executed, raw report imports and per-kernel hardware counter sections exist. This is not the full c8/c16 Prefill/Decode acceptance matrix.
- c8 Prefill and c16 Prefill/Decode NCU remain open. Need explicitly bound stage windows, correlate sampled scheduler kernel names against existing stage timeline, and collect separate NVML window samples.
- c8 whole GPU utilization/stall/window statistics, c8 Prefill/Decode compute-tokens / union GPU execution time / TPS, CUDA launch/graph CPU overhead, first-token-ready, scheduler queue/waits remain incomplete.
- This profile does not yield a clean performance result. Request duration under NCU is strongly perturbed and must not be compared with R17 clean benchmark rates.
