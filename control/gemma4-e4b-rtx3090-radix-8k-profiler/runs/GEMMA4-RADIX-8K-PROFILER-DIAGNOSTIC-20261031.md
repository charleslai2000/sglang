# Gemma 4 Radix 8K Profiler Diagnosis — 2026-10-31

## Status

**Target GPU profiling evidence obtained; full diagnosis remains PARTIAL. G1 remains FAILED / NOT ACCEPTED.** No optimization, clock, math, quantization, or cache semantic change was made. CUPTI capture was started/stopped by signals handled in the CUDA-owning Scheduler process; this bypassed the earlier missing-target-window kernel limitation.

## Established evidence

- Existing accepted no-profiler baseline and exact 7,168-prefix fixture remain authoritative.
- Opt-in `RADIX8K_FWD` NVTX identity is wired to scheduler `forward_iter`, RID list, mode, actual batch, graph flag and bucket. DeviceTimer metadata was also threaded through; a reporter exception caused by passing RID metadata as Prometheus kwargs was fixed.
- Accepted c16 Prefill trace: `/data/sglang-hicache/gemma4/runs/20261031T165207Z-radix8k-profiler-prefill-c16/`. 16/16 requests returned 256 tokens with device `cached_tokens=7168`, host=0. Eight target Prefill forwards all had actual batch=2; median summed GPU kernel duration 134.686 ms (P95 135.662 ms), median enclosing NVTX span 138.533 ms.
- Follow-up c16 Prefill with `--chunked-prefill-size 8192` and `max_prefill_tokens=16384`: `/data/sglang-hicache/gemma4/runs/20261031T172407Z-radix8k-profiler-prefill-c16/`. It produced four actual batch-8 extends (two cohort waves), with 16/16 exact cache/output validations. This is the best bounded large-batch Prefill point so far; it is not a batch-16/24/32 measurement. Attempting 16,384-token chunks OOMed at 23.06 GiB process memory and was excluded.
- Accepted Decode traces: c16 `/data/sglang-hicache/gemma4/runs/20261031T170655Z-radix8k-profiler-decode-c16/`, c24 `/data/sglang-hicache/gemma4/runs/20261031T170859Z-radix8k-profiler-decode-c24/`, c32 `/data/sglang-hicache/gemma4/runs/20261031T171035Z-radix8k-profiler-decode-c32/`. Each had 256 actual graph Decode forwards at the requested batch and 16/16, 24/24, 32/32 requests respectively with `cached_tokens=7168`, host=0 and 256 outputs.
- Nsight `CUPTI_ACTIVITY_KIND_GRAPH_TRACE` execution durations are the actual replay GPU intervals; ordinary `CUPTI_ACTIVITY_KIND_KERNEL` rows undercount graph work. Graph execution duration P50/P95/mean: batch16 **12.593/13.077/12.651 ms**, batch24 **18.079/18.360/18.048 ms**, batch32 **20.419/21.187/20.492 ms** (256 executions each). Scheduler NVTX spans have substantially wider wall time (median/P95 **9.664/10.134, 14.537/15.125, 16.824/17.640 ms** for c16/c24/c32), reflecting host scheduling/queue/synchronization/overlap; do not conflate with graph device interval.
- In Prefill summed target GPU kernel time, dominant kernels by accumulated duration were Marlin W4A16 GEMM 513.6 ms and `_fwd_kernel` 496.0 ms across the eight joined forward steps; then activation 20.8 ms, RMSNorm 13.6 ms, vectorized elementwise 12.2 ms. These are aggregate kernel execution durations and may overlap; no percentage of wall time is inferred. Decode CUDA Graph aggregate ordinary kernel rows do not attribute internal kernels; graph replay duration above is authoritative for device time.
- Nsight Systems CLI 2025.2.1, bundled with Nsight Compute 2025.2.1, passed a known CUDA matmul calibration and exported 25,297 CUDA kernel events from a model trace. However installed driver 13.0 is reported unsupported; the tool uses CUDA 12.9 trace libraries.
- The c16 full-service trace in `/data/sglang-hicache/gemma4/runs/20261031T163938Z-radix8k-profiler-prefill-c16/` contains 299 forward NVTX spans (step IDs through 283), and the target client log proves cohort completion. It shows CUDA kernel records only through timestamp 67.387 s while target cohort Prefill begins around 71.567 s and Decode around 74.520 s. Thus target-period GPU kernel coverage is absent. Despite a global 7,381 apparent kernel/NVTX overlap count, the target forward spans specifically have zero fully-contained CUDA kernels; do not use aggregate overlap as target evidence. That trace is rejected for target timings.
- Correction: in the accepted signal-controlled c16/c24/c32 target traces, all 256 target Decode forwards were graph=1 and bucketed at 16/24/32 respectively. Earlier non-accepted server startup attempts resolving only through 16 do not describe these runs.
- Prefill CUDA Graph is disabled by the existing model auto-rule. This is configuration evidence, not an optimization target.

## Five requested performance issues

1. Batch-level GPU time for 1,024 new Prefill tokens following an exact 7,168-token cache hit — **MEASURED at batch 2 and batch 8 only**. Batch 2 median summed kernel duration 134.686 ms/P95 135.662 ms; the safer 8,192 chunk follow-up reached batch 8. Batch 16/24/32 Prefill remains unmeasured; 16,384-token chunks OOMed.
2. Decode GPU Forward vs online TPOT — **MEASURED, domains distinct**: graph replay device duration P50/P95 12.593/13.077, 18.079/18.360, 20.419/21.187 ms for actual batches 16/24/32. Online per-request TPOT remains the accepted service measurement in the separate performance report; scheduler NVTX wall spans (median/P95 9.664/10.134, 14.537/15.125, 16.824/17.640 ms) include host-side overlap and are not graph device durations. No per-request division of batch device time.
3. Dominant kernels — **MEASURED for Prefill**: Marlin and `_fwd_kernel` dominate aggregate execution time. Internal CUDA graph kernel attribution is unavailable from expanded ordinary-kernel rows in these captures; NCU has not yet been run.
4. Graph/eager — **MEASURED for Decode**: all 16/24/32 target forwards are `graph=1` and bucketed to requested sizes (256 each); Prefill forwards are eager (`graph=0`), consistent with auto-rule.
5. Capture gap — **RESOLVED for these runs** via `cudaProfilerApi` triggered in the CUDA-owning Scheduler process. Historical failed traces remain excluded. Nsight tool/driver version mismatch is present but did not prevent full target capture with this path.

## Invalid attempts and handling

- `/data/sglang-hicache/gemma4/runs/20261031T154735Z-radix8k-profiler-prefill-c16/`: timer-metadata/metrics reporter exception; no performance evidence.
- `/data/sglang-hicache/gemma4/runs/20261031T160200Z-radix8k-profiler-prefill-c16/`: server child detection failed; discard.
- `/data/sglang-hicache/gemma4/runs/20261031T160411Z-radix8k-profiler-prefill-c16/`: Nsight 2025.1.3 exported NVTX but no target CUDA kernel table; discard.
- `/data/sglang-hicache/gemma4/runs/20261031T160840Z-radix8k-profiler-prefill-c16/`: exact-hit cohort valid, but CUDA kernel events end before target cohort forward; reject timings.
- `/data/sglang-hicache/gemma4/runs/20261031T161318Z-radix8k-profiler-prefill-c16/`: no kernel table; discard.
- `/data/sglang-hicache/gemma4/runs/20261031T161728Z-radix8k-profiler-prefill-c16/`, `161933Z`, `162115Z`, `162311Z`: Profiler API controller/launcher experiments; no usable exported target trace; discard.
- `/data/sglang-hicache/gemma4/runs/20261031T163938Z-radix8k-profiler-prefill-c16/`: report has kernels but target cohort CUDA coverage absent; reject timing attribution.

## G1 convergence addendum — 2026-11-01

Existing same-run Decode traces were joined offline from Scheduler NVTX thread/RID/step → runtime `cudaGraphLaunch` correlation ID → CUPTI graph execution. For each c16/c24/c32 trace, 256/256 graph forwards join uniquely; preserve per-step graph replay and same-cohort request metadata without dividing batch GPU time across RIDs. Profiler request metadata yields queue, Prefill-forward, Prefill-done-from-receive and E2E timing. Prefill-forward P50/P95: c16 570.87/672.65 ms, c24 572.04/677.01 ms, c32 520.75/674.12 ms. Prefill-done-minus-request-received P50/P95: c16 1,754.74/2,681.48 ms, c24 2,414.97/4,011.70 ms, c32 3,129.32/5,364.80 ms. These profiler timings are perturbed by profiling and queueing; they are not accepted online baseline timings. The accepted no-profiler c16/c24/c32 run reports TTFT P50/P95 1.832/2.688, 2.544/4.095, 3.250/5.483 seconds and TPOT 17.117/25.597/31.000 ms from 48/72/96 requests.

Exact Prefill cohort joins from `ReqTimeStats` to unique profile NVTX steps: c16=8, c24=12, c32=16 forwards, each batch 2 with two distinct RIDs and 2,048 new tokens. RID sets exactly partition 16/24/32 accepted request records. The separate safer c16 batch8 archive has 16 requests in two batch8 forwards, not four. No Prefill batch16/24/32 measurement is established.

Independent single-request uncached size probes (chunk 8192, cache disabled, BF16 KV) have exact-RID DeviceTimer CUDA Event times: 1K 147.599 ms / 6,937.71 tok/s; 4K 490.839 ms / 8,344.90 tok/s; 8K 1,043.633 ms / 7,849.50 tok/s. Each request hit cache 0 and returned one token. NVML sampled every 100 ms recorded 23,529 MiB whole-device used, including model/KV allocations; it is not incremental Prefill peak. Nsight GPU metric sampling is unavailable due driver permission `ERR_NVGPUCTRPERM`. Methods/artifacts are in `control/gemma4-e4b-rtx3090-g1-perf-convergence/runs/PREFILL-SIZE-MEASUREMENTS-20261101.md` and `/data/sglang-hicache/gemma4/runs/20261101T-prefill-sizes/`.

Exit-137 cause remains UNKNOWN per the one-time log check. Decode graph-internal kernel expansion/NCU attribution remains unavailable; do not infer per-request GPU time. GPU/service cleaned; NVML 1 MiB / 0%, lock released. G1 remains FAILED / NOT ACCEPTED. This combined update has not been selectively committed/pushed; preserve unrelated dirty files.

## Remaining scope

- Finish offline reproducibility checks and scoped five-issue synthesis, including full-cohort timing domains and Decode/request correlation.
- Selectively stage only profiler/G1-owned files, run tests, commit/push and verify remote SHA when attributable. G1 stays FAILED / NOT ACCEPTED.
