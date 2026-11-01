# RTX3090 Gemma4 G1 performance closure — evidence index

## Frozen disposition

- Performance diagnostics: **MEASURED; diagnostic stage closed**.
- G1 numerical/quality acceptance: **FAILED / NOT ACCEPTED**, unchanged.
- Online TPOT vs GPU-time difference: **specific causal attribution NOT ESTABLISHED**.
- Exit 137: **UNKNOWN** (per the one-time read-only log check; do not infer OOM).
- Independent 32 × 32K context-capacity test: **NOT TESTED**.
- Cache-hit Prefill at actual batch 16/24/32: **NOT TESTED**; 16K chunk OOM run excluded. No retry.

## Source reports and raw archives

### 1K/4K/8K standalone Prefill

- Report/method: `PREFILL-SIZE-MEASUREMENTS-20261101.md`.
- Analyzer: `summarize_prefill_sizes.py`; collector: `prefill_sizes_gpu.py`; locked wrapper: `measure_prefill_sizes_gpu.sh`.
- Raw run: `/data/sglang-hicache/gemma4/runs/20261101T-prefill-sizes/`.
- Inputs: exact RIDs `radix8k-perf-g1-prefill-n1024-222199_0`, `...n4096...`, `...n8192...`; each response has exact prompt length, `cached_tokens=0`, one output token. `prefill-sizes.json` → matching `RADIX8K_GPU_FORWARD category=extend` entry in `nsys-launch.log` → CUDA Event elapsed. Separate `category=decode` event is excluded.
- Reproducibility hashes (`SHA256SUMS` in archive): `profile.nsys-rep` `13bb48e76fee983965e25e77f5a8aebccc04be33b9bf58799a16f5a3d58a84e9`; `profile.sqlite` `09321e701eefc0c53fcedaa86bbe95bbcbda88b5055b4dfe2081bb7df6791dfd`; `prefill-sizes.json` `99a4c97726922ce06e4afe8412b914cf62aa034c1f251bb79f10d96e981163e1`; `gpu-samples.csv` `066f3d96974cfb7c274b9f9a62164433c832ee8bf8934b72b94278c1e83a49f7`; `nsys-launch.log` `d9ef0b9bd0318fb2bac8a2fa3214525680b8c62b4f5e5216ce485f748f369206`. All were independently recalculated and matched.

### Decode c16/c24/c32 and online service baseline

- Combined interpretation/results: `G1-PERFORMANCE-CONVERGENCE-20261101.md`.
- Reproducible join: `analyze_same_run_graph_timeline.py`; outputs `same-run-decode-timeline-b16/b24/b32.json`.
- For each batch, raw source directory is `/data/sglang-hicache/gemma4/runs/<timestamp>-radix8k-profiler-decode-cN/`:
  - c16 `20261031T170655Z`, c24 `20261031T170859Z`, c32 `20261031T171035Z`.
  - Linkage is SQLite `NVTX_EVENTS` → same-thread `CUPTI_ACTIVITY_KIND_RUNTIME` `cudaGraphLaunch` correlation ID → `CUPTI_ACTIVITY_KIND_GRAPH_TRACE`; each reproduces 256/256 steps with complete per-step RID sets.
  - Input artifacts: `profile.nsys-rep`, `profile.sqlite`, `profile-decode-cN.json`, `nsys-launch.log`, `gpu-samples.csv`; derived `same-run-decode-timeline-bN.json`. The archive `sqlite` SHA-256s are c16 `f438849b66b017102491ef29e7161638649769690232e5171c8d2a6764e00202`, c24 `530add20465a371bd22a456c31306ce07a7d536e37266944edf758b5963f5b6e`, c32 `6cd9597b4a9068619fab5e7c159524eeaf2d59f7a1579269e5f5dc1592869ac6`; each run directory also retains the raw `.nsys-rep` and matching derived join JSON.
- Accepted no-Profiler service baseline: `/data/sglang-hicache/gemma4/runs/20261031T145717Z-radix8k-prefix-benchmark/records.json` and `server.log`; 48/72/96 measured requests for c16/c24/c32. Raw `records.json` was independently replayed: TPOT P50/P95 (ms) c16 `17.117/21.113`, c24 `25.597/32.383`, c32 `31.000/40.523`; TTFT P50/P95 (s) c16 `1.832/2.682`, c24 `2.544/4.092`, c32 `3.250/5.483`. These exact raw order-statistic values may differ slightly from earlier rounded/report values. `records.json` SHA-256 `c6a3498a03e8547a4ad215f3c09e43451e771a477b47cec038ce3c5acdb3022e`; `server.log` SHA-256 `e21d39edf87b7082eac100d4241849879e353a25c91d97ed62b7ba9ee9ca6351`.

### Cohort Prefill and capacity evidence

- RID-labeled target-window Prefill step and request metadata is in each c16/c24/c32 Decode profiler SQLite and `profile-decode-cN.json`; exact counts and scope limitation are recorded in `G1-PERFORMANCE-CONVERGENCE-20261101.md`.
- c16 batch8 Prefill source archive: `/data/sglang-hicache/gemma4/runs/20261031T172407Z-radix8k-profiler-prefill-c16/`; batch2 source: `/data/sglang-hicache/gemma4/runs/20261031T165207Z-radix8k-profiler-prefill-c16/`.
- The 32×32K independent-context capacity scenario was not run; do not infer it from 32 concurrent 8K requests or Decode batch 32.

## Resource/working-tree closure

At closure, process/listener checks found no SGLang service, Scheduler, or `nsys profile` process and nothing bound to port 31371. `nvidia-smi` showed 1 MiB / 0% GPU. Exclusive lock has no holder. G1-scoped changes were pushed at commit `15784316b79230d8153b94ef58f0afd1fbeb1477`; remote branch SHA was verified equal. Unrelated dirty paths remain untouched.
