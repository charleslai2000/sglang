# Falcon R17 — targeted NCU phase counters

## Provenance / interpretation

- Frozen checkout: `/tmp/sglang-r17`, `r17-falcon-hicache`, HEAD `20c837f1a3daaec47508feaecf5514dd586c636c`; Falcon GPTQ revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`; one RTX 3090, GA102/CC 8.6.
- The earlier full c8 report at `ncu-c8-decode-t4/falcon-scheduler.ncu-rep` was imported and its **48 rows all enumerated**, but none is the Marlin/Mamba/FlashInfer representative set. Do not average those heterogeneous kernel rows. Its complete per-launch data are in `ncu-c8-decode-t4/import.csv` and `details.txt`.
- Four new reports were collected with the previously working sudo NCU launch-and-attach method; target process logs show API + scheduler child, all 40 fixed requests returned 128 tokens. NCU selection used these target function regexes and a bound of 8 matching invocations: Prefill `Marlin<__nv_bfloat16...` and `ampere_bf16_s16816gemm_bf16_128x128...`; Decode `Marlin<__nv_bfloat16...`, `causal_conv1d_update_kernel`, `_selective_scan_update_kernel`, and `ampere_bf16_s16816gemm_bf16_64x64...`.
- The phase names/identity are joined against the existing PyTorch scheduler trace: Prefill uses `profile-prefill/r17-prefill-TP-0-EXTEND.trace.json.gz`; Decode uses `profile-decode/r17-decode-TP-0-DECODE.trace.json.gz`. For c8 Decode, trace kernel grid/block examples: Marlin `[82,1,1]x[256,1,1]`, conv `[8,56,1]x[64,1,1]`, scan `[32,8,24]x[256,1,1]`, GEMMs `[105,1,1]x[128,1,1]`, `[48,1,1]x[128,1,1]`. NCU profiled launch geometry is listed in every raw CSV row. c16 has different batch geometry (e.g. conv grid `[16,56,1]`, scan `[32,16,24]`); no cross-batch extrapolation.
- These are **individual NCU kernel instances** measured under NCU replay. Never use their durations as clean Prefill/Decode service TPS. `ncu.stdout` logs include kernel export names and report paths; `manifest.json`, request outcome, UTC window, before/after GPU state and raw report are retained per run.
- NCU values use NCU's metric definitions: SM Compute Throughput and DRAM Throughput are % of peak sustained elapsed; Tensor Core is Tensor pipe cycles as % of peak sustained active; L2 throughput is % of peak sustained elapsed; load hit rate is the NCU sector-op-read hit ratio. NCU read/write values below are **decimal GB/s** from the corresponding per-kernel transferred bytes / kernel duration. GPU uses its peak-sustained reference for DRAM %. `smsp__issue_inst0...` is issue-slot-0 active % of peak sustained active, not “efficiency” (it can exceed 100% at max sampling); stall columns are average stalled warps per active issue slot, not fractions of time. The multi-pass `full` set does not expose a valid “GPU whole-window” average.

## Table A — per-kernel counters (selected representative invocations)

Each row is one reported launch; duplicate rows are different selected kernel invocations, not replicates to pool or average. Time in µs; bandwidth in decimal GB/s. Cells `LS/IMC/math/LDST/wait` are long-scoreboard / IMC-miss / math-pipe-throttle / LG-throttle / wait stalled warps per issue-active slot. Issue shows slot0-active %. The report includes remaining full-set counters.

| Stage / c | Kernel (trace-joined; launch geometry) | Time | SM % peak | Tensor % active peak | DRAM read / write GB/s | DRAM % peak | L2 % peak | L2 read hit % | Achieved occupancy % | Issue0 % | LS / IMC / math / LDST / wait |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Prefill c8 | Marlin `mlp` instance A; grid 82,1,1 block 256 | 68.768 | 30.379 | 33.070 | 0.577 / 0.043 | 68.014 | 41.767 | 32.384 | 16.731 | 91.6 | 0.480 / 0.128 / 3.642 / 0.001 / 0.902 |
| Prefill c8 | Marlin `mlp` instance B; same shape | 39.136 | 26.933 | 31.263 | 0.511 / 0.056 | 62.297 | 37.475 | 32.870 | 16.705 | 91.7 | 0.589 / 0.252 / 3.601 / 0.001 / 0.899 |
| Prefill c16 | Marlin instance A; grid 82,1,1 block 256 | 68.608 | 30.383 | 33.071 | 0.578 / 0.043 | 68.211 | 41.883 | 32.383 | 16.736 | 91.6 | 0.484 / 0.130 / 3.641 / 0.002 / 0.902 |
| Prefill c16 | Marlin instance B; same shape | 38.944 | 27.213 | 31.215 | 0.514 / 0.056 | 62.677 | 37.664 | 32.853 | 16.657 | 91.6 | 0.586 / 0.254 / 3.600 / 0.001 / 0.899 |
| Decode c8 | Marlin M=1; grid 82,1,1 block 256 | 68.416 | 30.587 | 33.112 | 0.579 / 0.042 | 68.272 | 41.989 | 32.383 | 16.739 | 91.6 | 0.482 / 0.125 / 3.631 / 0.002 / 0.902 |
| Decode c8 | Marlin M=1 second shape instance; same grid | 38.880 | 27.082 | 31.192 | 0.515 / 0.056 | 62.691 | 37.745 | 32.852 | 16.674 | 91.6 | 0.583 / 0.253 / 3.612 / 0.001 / 0.899 |
| Decode c8 | Mamba causal conv; grid 16,56,1 block 64 | 5.408 | 12.857 | 0.000 | 0.034 / 0.00045 | 3.787 | 16.668 | 76.556 | 31.152 | 86.4 | 10.544 / 1.765 / 0.629 / 0.056 / 2.347 |
| Decode c8 | Mamba selective scan; grid 32,16,24 block 256 | 78.592 | 75.575 | 0.000 | 0.042 / 0.033 | 8.167 | 62.244 | 93.534 | 93.227 | 86.2 | 0.909 / 0.229 / 1.397 / 0.003 / 1.918 |
| Decode c8 | BF16 GEMM, grid 105,1,1 block 128 | 86.240 | 27.040 | 42.509 | 0.478 / 0.026 | 55.347 | 28.664 | 19.849 | 8.815 | 91.6 | 0.418 / 0.164 / 7.456 / 0.025 / 2.089 |
| Decode c8 | BF16 GEMM, grid 48,1,1 block 128 | 41.664 | 24.934 | 44.701 | 0.456 / 0.049 | 55.383 | 27.403 | 19.868 | 8.335 | 91.9 | 0.080 / 0.204 / 7.186 / 0.021 / 2.165 |
| Decode c16 | BF16 GEMM, grid 105,1,1 block 128 | 85.728 | 27.156 | 42.448 | 0.481 / 0.026 | 55.693 | 28.836 | 19.848 | 8.754 | 91.6 | 0.393 / 0.168 / 7.461 / 0.025 / 2.089 |
| Decode c16 | Mamba causal conv, grid 16,56,1 block 64 | 5.536 | 12.717 | 0.000 | 0.033 / 0.00051 | 3.683 | 15.916 | 76.898 | 32.932 | 84.6 | 10.345 / 1.803 / 0.629 / 0.056 / 2.346 |
| Decode c16 | Mamba selective scan, grid 32,16,24 block 256 | 78.560 | 75.382 | 0.000 | 0.042 / 0.033 | 8.152 | 62.324 | 93.290 | 93.107 | 85.6 | 0.911 / 0.218 / 1.393 / 0.003 / 1.919 |
| Decode c16 | BF16 GEMM, grid 48,1,1 block 128 | 41.632 | 24.840 | 44.676 | 0.456 / 0.050 | 55.572 | 27.529 | 19.864 | 8.325 | 91.8 | 0.078 / 0.206 / 7.196 / 0.021 / 2.165 |

**Not yet kernel-covered in this targeted NCU set:** Prefill has Marlin launches, but the requested BF16 128x128 CUTLASS regex produced no exported row; report shows the eight selected rows are Marlin. Decode's selected set contains Marlin, Mamba, BF16 GEMM. Therefore treat Prefill columns as Marlin-only evidence, not the entire stage distribution. All four profiles have 8 reported kernel rows; two “Marlin” rows in Prefill carry 4 different launch counters, as shown in CSV (identical kernel name but different weights/invocation context). Representative output kernel time/counters are independently sampled, not clean TPS.

## Exact raw artifacts / rerun outputs

- Original mixed c8 report: `ncu-c8-decode-t4/{falcon-scheduler.ncu-rep,import.csv,details.txt,requests.json,SUMMARY.md}`.
- c8 Decode: `ncu-decode-c8-t8-1791702178785661008/{falcon-filtered.ncu-rep,import.csv,requests.json,manifest.json,ncu.stdout,ncu-start.utc,ncu-end.utc,nvidia-smi-before.txt,nvidia-smi-after.txt}`.
- c8 Prefill: `ncu-prefill-c8-t8-1791702700933960932/` same files.
- c16 Decode: `ncu-decode-c16-t8-1791703053064947371/` same files.
- c16 Prefill: `ncu-prefill-c16-t8-1791703591797622215/` same files.
- Every `import.csv` has one header-type row and 8 counter rows; selected kernel rows are preserved without averaging. CUDA Graph: Prefill Marlin calls in the prior stage trace are eager (`graph id 0`); c8 Decode representative graph has `graph id 8`, while c16 request run launches selected shapes/instances from its separately started service. The profile trace explicitly confirms c8 Decode uses full CUDA Graph with M=1 Marlin and Mamba conv/scan.

## Device-window status separate from kernel counters

The report's start/end clocks/perf status text is sampled before/after each NCU process, not a per-kernel counter or continuous whole GPU window. The running clean request-window NVML table is `MEASUREMENTS-SUMMARY.md`; it is 1-second device-wide monitoring, not NCU window-specific. These four profile invocations are not the clean c8/c16 throughput runs. Their request outputs are in each `requests.json`.
