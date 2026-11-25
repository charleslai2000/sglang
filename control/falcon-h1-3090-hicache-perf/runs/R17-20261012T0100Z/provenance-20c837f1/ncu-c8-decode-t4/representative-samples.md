# c8 Decode representative Falcon kernel evidence

Paired sources:
- NCU full scheduler capture: `falcon-scheduler.ncu-rep` → `details.txt`.
- Existing in-scheduler c8 Decode timeline: `../../profile-decode/r17-decode-TP-0-DECODE.trace.json.gz`; this is the same frozen 120-request workload/config and confirms actual graph Decode stage.

One recent Decode graph cycle in the timeline has these scheduler GPU events, in capture timestamps; duration values are CUDA timeline event durations, not profiler-free service TPS:

| Kernel | Timeline duration |
|---|---:|
| Marlin M=1 (int4) | 51.071 us |
| Mamba causal conv update | 2.976 us |
| Mamba selective scan update | 60.031 us |
| Marlin M=1 next launch | 28.832 us |

The NCU all-kernel capture in `details.txt` includes real process 259848 CUDA kernels and full per-kernel counter sections. Because its `--launch-count 48` selected heterogeneous first launches, use the report for collector validation and broad kernel-level evidence, not as a pure steady-state Marlin sample or whole Decode interval. Exact kernel filter regexes for subsequent stage runs should reuse profile identities (`sglang::device::marlin::Marlin`, `_selective_scan_update_kernel`, `causal_conv1d_update_kernel`, BF16 CUTLASS/FlashInfer names); keep reports per stage/config and document any name normalization.

## c8 profile trace validation
The Decode trace has 8,854 GPU/runtime events across timestamps 827075393857.146–827075507852.681 us. It contains 528 Marlin M=1 calls, 264 Mamba conv updates, 264 Mamba selective-scan updates, plus CUDA graph decode. The request cohort was eight simultaneous requests, each 128 generated tokens. Trace begins/ends include CPU/API activity and other event categories; use kernel events/correlation and scheduler annotations rather than `end-start` as GPU execution sum.
