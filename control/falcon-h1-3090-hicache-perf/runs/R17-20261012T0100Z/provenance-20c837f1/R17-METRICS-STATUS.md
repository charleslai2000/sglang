# R17-METRICS Status — 2026-10-11

## Scope and provenance
- Isolated branch `r17-falcon-hicache`, based on pushed baseline `6f612b0301416157e48fc5e40ac01680bc212b3c`; model `Falcon-H1-7B-Instruct-GPTQ-Int4`, revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`; RTX 3090 / GA102; SGLang `0.5.20.dev22+g9c9e7b7c7`.
- This is a status/limitations report, **not completion** of the R17-METRICS contract. Required long-context/prefill-heavy, decode-heavy, GSP multi-turn matrices, successful L2 restore, scheduler-attached NCU, complete phase records, and optimization A/B are not delivered.
- Fixed short-prompt manifest: `workload.json`, SHA256 `c9bafdb887a6bd0e21bafc14719c42769884538431a06e1a1f20754d37f46bff`; 120 requests, 45,863 input tokens, lengths 257–512, 128 output each. It is mixed/decode-capacity coverage only; not a prefill-heavy/long-context workload.

## Evidence captured
- NCU 2025.2.1 is installed. An isolated synthetic CUDA GEMM yielded real GA102 counters under sudo (`ncu-smoke-full.csv`), establishing tool/permission feasibility only. It is not Falcon evidence. Attempts to attach NCU to the actual `sglang::scheduler` worker and launch-and-suspend smoke did not yield a report; retain raw `ncu-attach-*`, `ncu-c8-decode-t1/`, `attach-smoke.*`. Do not call scheduler counters collected. No global security/policy setting was modified.
- SGLang V2 scheduler-context Torch profiles are retained in `profile-prefill/` and `profile-decode/`. Their intended scheduler-stage filtering was applied after correcting the V2 path and both contain many CUDA events (about 5,960 Prefill; 9,734 Decode including graph activity). These are diagnostic/profiled runs, not clean baselines. A separately verified unprofiled-versus-profiled perturbation estimate is not in this status artifact; no unprofiled GPU compute-time ratio is claimed.
- Device timer/forward-batch index logging was enabled in the latest Host launcher (`SGLANG_ENABLE_METRICS_DEVICE_TIMER=1`, `SGLANG_LOG_FORWARD_ITERS=1`). One additional Host c8 trial was captured as `final-c8-host-t5.json`, stdout/stderr, `final-c8-host-t5/{gpu-nvml.csv,scheduler.log}`. It completed 120/120 requests; 309.40 output tokens/s; 923.84 input tokens/s; TTFT p50/p95/p99 996.84/1189.85/1191.40 ms; TPOT 18.03/18.70/20.15 ms. Scheduler logs show decode running batch 8, queue 0, CUDA graph true; short prefill records show partial batches and queue variation. NVML samples show ~23,004 MiB used and windows up to 100% GPU utilization, 349 W and 1,920 MHz. These are time-sampled device metrics, not SM Active/compute counters.
- Host was enabled and actual runtime config captured in `host-server-info.json` (that file describes a prior run with ratio 1.0; the latest server command/log used ratio 2.0). At ratio 2.0, service metrics showed approximately 91,473 KV Host tokens capacity. Latest extra c8 run produced D→H backups of 25.82 GB and 44,070 KV + 171 Mamba tokens, and evicted 19,213 tokens. Those are aggregate write/eviction figures, **not** successful Host restore.
- In the extra c8 run, 120/120 request telemetry rows were `partial`, all 45,863 prompt tokens were newly prefilled, and L1/L2/L3 effective restored-token counts were all zero. Earlier Host c8 samples `host-cache-official-c8-t6.json` and `host-cache-capacity2-c8-t7.json` also completed 120/120 but had zero tier hits and `partial` telemetry. Therefore this short, unique-prompt workload did not exercise Host reuse; no Host benefit is inferred. One prior repeated-prefix diagnostic produced a 256-token L1 hit, but it is not a complete Host/GPU comparison and establishes no L2 restore.
- In `final-c8-host-t5.json`, run-window H→D `load_back_*` deltas are zero/absent while D→H backup metrics are nonzero. No successful H→D operation was measured; do not derive H→D bytes/duration from D→H counters. L3 is `NOT_QUALIFIED`.
- The 120-request c8 Host output throughput is comparable in scale to preceding GPU-only c8 observation (about 316.6 tok/s in a different prior matched-parameter run; 311.9 tok/s in another Host run). This is not a controlled multi-round A/B: differing time/config state and zero Host hits preclude a cache-value claim.

## Important data/config caveats
- Existing R17 `final-c*-t*` exporter-enabled c4–c24 values are incomplete repetitions and mostly initial GPU-only behavior. The initial unexported sweeps do not supply reliable request-level cache telemetry or TPOT. Neither set satisfies the full matrix contract.
- Prior `host-server-info.json` reports `hicache_ratio=1.0`, while later launch command and server log show ratio `2.0`; preserve this config distinction when grouping data. Do not silently assign that ratio-1 server-info snapshot to the ratio-2 c8 run.
- The metrics-file `hicache_request.v1` outcome may be partial; effective cache tokens are reported separately. Do not treat D→H backup as H→D restoration.

## Not delivered / acceptance
- No Falcon scheduler NCU kernel report/raw per-kernel counters; no supported-pipeline/stall/L2/PCIe kernel metric attribution.
- No full independent clean repetitions with telemetry across c1/4/8/12/16/20/24, no complete Prefill-heavy / Decode-heavy / long-context / true GSP multi-turn by GPU-only/Host/Extent and cold/warm comparison, and no per-request cold/warm cache-class latency analysis.
- No complete phase-specific batch rates/tails + queue/wait/request timeline joined to stable request IDs, nor a validated NCU/profiler perturbation estimate.
- No successful L2 restore bytes/event latency or matched-operation ACK evidence from this performance run; no L3 read/restore. L3 remains `NOT_QUALIFIED`.
- No profile-backed optimization A/B or relevant correctness regression was conducted. No optimization is proposed on the present evidence.
- Consequently this milestone remains **INCOMPLETE / NOT ACCEPTED**. Existing R16B/R16C acceptance is unchanged.

## Cleanup
- The one-shot c8 Host trial completed successfully. Service should be stopped after any explicitly requested follow-on; verify no test-owned processes, port 30160, and GPU allocations remain. This report does not assert cleanup until that final check is recorded.
