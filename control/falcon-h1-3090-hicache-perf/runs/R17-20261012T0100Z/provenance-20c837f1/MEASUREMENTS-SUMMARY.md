# R17 scheduler/GPU and cache-control measurements — 2026-10-11

## Scope and provenance

- Frozen isolated worktree: `/tmp/sglang-r17`, branch `r17-falcon-hicache`, HEAD `20c837f1a3daaec47508feaecf5514dd586c636c`.
- Model: `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`, revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`; RTX 3090, TP=1.
- Fixed request set: first 40 entries of `workload.json`, 15,016 submitted prompt tokens, 128 requested output tokens/request (5,120 total). Manifest SHA256 `782e1c5fcdfb40aec6683813c66e8c30cfee4b05b9173541f4abc836cac6b4ec`.
- Scheduler metrics are existing `ForwardPassMetrics` with CUDA-event `DeviceTimer`; event interval wraps `model_runner.forward/cuda_graph.replay`. Request records are per-request API metadata/client wall clock. NVML is an independent ~1 second device-wide sample; don't equate it with scheduler event time.
- Full raw records are in `scheduler-{gpu-only|host}-c{8|16}-tN/{summary.json,request-results.json,scheduler-forward-pass.json,gpu-nvml.csv,server.log,metrics-final.prom}`. GPU-only c8 uses valid repetitions t5,t6,t7; t3,t4 are earlier failed FPM-collector wiring trials and excluded. c8 t1 is retained but excluded from the formal three-repeat summary to use the consistently sampled valid set.

## Clean scheduler/request runs

| Mode | Concurrency | n | Completed | Request window s (mean; min–max) | DeviceTimer summed forward s (mean) | Prefill compute tokens / run | Decode active forwards / run | Decode request-iterations / run | Client latency P50/P95 s (per run) | max scheduler queue wait / request s (per run) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| GPU-only | 8 | 3 | 40/40 each | 16.379; 16.366–16.405 | 16.213 | 13,601 | 648 | 5,128 | 3.263–3.271 / 3.291–3.333 | 0.279–0.280 |
| GPU-only | 16 | 3 | 40/40 each | 12.997; 12.786–13.303 | 12.834 | 13,760 | 392 | 5,128 | 4.671–4.829 / 4.786–5.149 | 1.455–1.493 |
| GPU+Host cache | 8 | 1 | 40/40 | 17.105 | 16.603 | 11,790 | 646 | 5,112 | 3.447 / 3.471 | 0.618 |
| GPU+Host cache | 16 | 1 | 40/40 | 13.491 | 12.853 | 13,760 | 390 | 5,096 | 4.964 / 5.095 | 1.754 |

Per-run request completion tokens were 128 for all requests. Service-reported `e2e_latency_s` is available in request JSON; client wall latency above is also available. `ttft_s` is null in every captured response, so no valid TTFT is reported. `queue_time_s` is API metadata, not total scheduler wait; its mean is zero in the listed run samples while per-request maxima are shown in the raw JSON. TPOT was not exported by this runner, so do not infer it from E2E latency; exact request and FPM rows remain in raw JSON.

### Derived rates (workload-level, not GPU-compute rates)

- GPU-only c8: 5,120 output tokens / mean request window = **312.6 output tok/s aggregate**; submitted 15,016 input tokens / window = **916.8 input tok/s**.
- GPU-only c16: **394.0 output tok/s**, **1,155.3 submitted input tok/s**.
- These are request-window rates for this fixed short-prompt workload. They are not Prefill/Decode kernel throughput; don't combine prompt and output tokens or infer a cache benefit from c8/c16 differences.

### Prefill and Decode event-time decomposition

| Mode/concurrency | Prefill event sum s (per run) | Decode event sum s (per run) |
|---|---|---|
| GPU-only c8 | 5.015–5.066 (mean 5.047) | 11.159–11.178 (mean 11.166) |
| GPU-only c16 | 4.937–5.407 (mean 5.123) | 7.707–7.721 (mean 7.712) |
| Host c8 (one run) | 5.098 | 11.505 |
| Host c16 (one run) | 4.943 | 7.909 |

These phase bins sum each message's forward event according to its scheduled batch mode. They do not include GPU work outside that event seam and are not union-busy measurements. The event duration can include asynchronous work ordered on the measured stream; it is not a kernel-by-kernel sum. Prefill FPM message counts vary with scheduler batching/chunking.


### 逐 run 可复算的 Phase TPS 与真实请求窗 NVML

Prefill phase TPS = 同 run FPM scheduled `sum_prefill_tokens` / 同类 batch CUDA-event 时间和；Decode active TPS = 固定请求集 5,120 completion tokens / 有 Decode requests 的 batch event 时间和。不是整机 busy TPS。区间按有效三次重复给出：

| 配置 | Prefill FPM tokens | Prefill event s (range) | Prefill event TPS (range) | Decode outputs | Decode event s (range) | Decode active TPS (range) | Request window aggregate output TPS (mean) |
|---|---:|---:|---:|---:|---:|---:|---:|
| GPU-only c8 | 13,601 | 5.015–5.066 | 2,685–2,712 | 5,120 | 11.159–11.178 | 458.05–458.82 | 312.6 |
| GPU-only c16 | 13,760 | 4.937–5.407 | 2,545–2,787 | 5,120 | 7.707–7.721 | 663.16–664.32 | 394.0 |
| GPU+Host c8 (single control) | 11,790 | 5.098 | 2,313 | 5,120 | 11.505 | 445.01 | 299.3 |
| GPU+Host c16 (single control) | 13,760 | 4.943 | 2,784 | 5,120 | 7.909 | 647.34 | 379.5 |

Actual request-window-only NVML rows were selected by each run's `wall_start_epoch_ns <= sample.wall_time_ns <= wall_end_epoch_ns`; all startup and 120-second loaded-idle samples were excluded:

| Config | Request-window samples/run | GPU util mean % (range) | Power mean W (range) | SM clock mean MHz (range) | Memory clock mean MHz (range) | Max temperature °C | Throttle reason observed |
|---|---:|---:|---:|---:|---:|---:|---|
| GPU-only c8 t5/t6/t7 | 17/16/16 | 84.6 / 98.1 / 97.3 | 320.1 / 333.4 / 332.7 | 1845.9 / 1854.4 / 1848.8 | 9501 each | 65/63/63 | blank + sw_power |
| GPU-only c16 t1/t2/t3 | 13 each | 85.8 / 92.3 / 84.5 | 299.8 / 320.8 / 297.7 | 1723.8 / 1838.1 / 1719.2 | 8801/9501/8801 | 60/61/60 | idle samples plus sw_power |
| GPU+Host c8 t1 | 17 | 95.1 | 321.8 | 1864.4 | 9501 | 63 | blank + sw_power |
| GPU+Host c16 t1 | 13 | 99.6 | 319.2 | 1816.2 | 9501 | 61 | sw_power |

NVML has ~1 s resolution, only 13–17 request-window observations per run; use as window-level device context, not kernel-level attribution. c8 t5 is an older valid sample without a captured 120-second baseline; its request-only range selection still uses exact request timestamps.

## Device-wide NVML context (per-run independent window)

| Mode/concurrency | NVML samples across run windows | GPU util mean / max % (window includes model load + 120s loaded-idle baseline + request window) | Peak memory GiB | Mean/max power W | Max temp °C | SM clock range MHz | throttle samples |
|---|---:|---:|---:|---:|---:|---:|---|
| GPU-only c8 | 73–199 | 8.8–23.9 / 100 | 22.85 | 71.6–126.1 / 348.9–349.1 | 63–65 | 210–1920 | mostly idle during baseline, `sw_power` during activity |
| GPU-only c16 | 188–195 | 7.0–7.4 / 100 | 22.85 | 65.4–67.2 / 347.9–349.4 | 61 | 210–1920 | mostly idle during baseline, `sw_power` during activity |
| Host c8 | 214 | 8.8 / 100 | 22.91 | 75.2 / 349.1 | 63 | 210–1920 | idle + `sw_power` |
| Host c16 | 211 | 7.1 / 100 | 22.91 | 71.2 / 349.2 | 61 | 210–1905 | idle + `sw_power` |

NVML means are diluted by server load/capture and 120-second idle baseline; they are not request-window means. `idle` throttle reason is expected during idle and is not evidence of load-time throttling. `sw_power` is recorded during active samples; don't infer that it caused a performance limitation from the mask alone.

## Cache status and limits

- The Host runs were deliberately retained as controls, but request-level `cached_tokens` summed to **0/40** for both runs and all `cached_tokens_details` were null. They do **not** qualify Host cache hits or Host restore.
- Host c8 FPM recorded 11,790 Prefill compute tokens versus 13,601 for c8 GPU-only, although submitted prompt tokens are 15,016 in both. `cached_tokens` is 0 for every request in both; request `cached_tokens_details` is null. FPM semantics count scheduled prefill tokens and separately report scheduled prefix-KV tokens; they do not encode a cache hit or prove prefill tokens saved. The raw c8 Host FPM has 11 prefill-class messages vs 13 in the c8 GPU-only repeats, and its summed `sum_prefill_kv_tokens` is 11,790 vs 14,395 for GPU-only; that field reports the number of prefix indices per scheduled prefill request (it is not a tier-attributed effective-hit counter). Here it is lower by 2,605 tokens, not higher; this says nothing by itself about Host/L1/L2 reuse. Request-level cache hit details are null and HiCache per-tier effective-hit counters for these windows are not available in the saved request records, so there is no basis for crediting saved prefill tokens to cache. Audit admission/prefix metadata and FPM aggregation before drawing a cache-performance conclusion.
- No R17-created target Host ACK + target device eviction + host-source restore sequence has passed yet. No L3 read-back/restore has passed. Hence no L1/L2/L3 effectiveness or latency decomposition, no cache-tier performance comparison, and no T003 result.
- Existing c8 Decode NCU report is a diagnostic first-48-launch heterogeneous sample with profiler replay; it is not a clean performance sample or a representative stage matrix. See `ncu-c8-decode-t4/SUMMARY.md`.

## Hardware cleanup

After the completed runs: RTX 3090 reported 1 MiB used / 0% utilization; no 30127/30160 service listener or SGLang/NCU compute process remained.
