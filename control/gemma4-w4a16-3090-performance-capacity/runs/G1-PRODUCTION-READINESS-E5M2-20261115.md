# G1 E5M2 production-readiness assessment — 2026-11-15

## Decision

**NO-GO for production deployment of E5M2 KV at this time.** The tested RTX 3090 candidate is operationally viable for a controlled, non-production E5M2 service: real HTTP inference, CUDA Graph Decode, Radix reuse/eviction, client cancellation, C32 8K/64K requests, and one 60-minute mixed run all completed without a model/runtime error in the accepted runs. This is **not** numerical acceptance: the already-approved numerical work remains limited, E5M2 remains NOT ACCEPTED, and BF16 KV remains the default. In addition, the tested configuration has **no HiCache L2/L3 enabled**. Therefore this assessment does not authorize production, HiCache deployment, or any business-environment change.

## Candidate / reproducibility

- Model: `/data/sglang-hicache/gemma4/model`, Gemma 4 E4B-it QAT W4A16 pack-quantized INT4 group32; model revision `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`; weights SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`. Compute is BF16 (quantized W4A16 weights); only KV uses `fp8_e5m2`—this is not an FP8-weight run.
- Service: current `3090-24g-hicache` worktree / installed SGLang environment, RTX 3090, TP1, Triton attention, `--kv-cache-dtype fp8_e5m2`, context 131,072, max-running 32, max-total-tokens 262,144, static memory fraction 0.94, chunked prefill 2,048, full CUDA Graph Decode max bs32, Radix enabled (LRU). Exact `get_server_info` evidence: `/data/sglang-hicache/gemma4/runs/20261115T-g1-prod-e5m2-eviction/server-info.json`.
- Full KV allocation: FP8 E5M2, 262,144 tokens; K and V each 1.75 GiB. SWA allocation: FP8 E5M2, 209,715 tokens; K and V each 3.50 GiB. Startup reported 2.91 GiB available GPU memory after initialization. These are pool allocations, not a promise of concurrent usable context independent of scheduler/prefill/graph overhead.
- Run entrypoint: `control/gemma4-w4a16-3090-performance-capacity/runs/run_g1_prod_e5m2.sh`; workload driver: `g1_prod_e5m2_run.py`. The active tests were bound to `/tmp/f1-r16b-gpu-exclusive.lock`; final service/port/GPU/lock state was checked after teardown.

## Measured results

### HTTP concurrency and Graph Decode

Short input (65 token prompt, 256-token greedy outputs), existing E5M2 records reused without rerunning:

| Concurrency | Successful requests / trials | Aggregate output throughput (tok/s) |
|---:|---:|---:|
| 1 | 3/3 | 89.8–116.7 |
| 4 | 8/8 | 414.3–464.4 |
| 8 | 16/16 | 791.8–856.1 |
| 16 | 32/32 | 1,377.7–1,571.2 |
| 32 | 64/64 | 1,829.8–2,205.2 |

These are short-prompt, fixed-output service numbers, not a cross-dtype speedup claim and not representative of long-prefill cost. Raw records live under `/data/sglang-hicache/gemma4/runs/20261115T-g1-prod-e5m2/bench-c{1,4,8,16,32}.json/`.

A fresh service logged successful full decode CUDA Graph capture (`Capture target decode CUDA graph end`, bs tiers through 32) and live Decode log lines explicitly show `cuda graph: True`. Actual streamed 8K requests: bs1 produced ~100 tok/s with TTFT 138 ms and TPOT 9.0 ms on the warmed request; bs32 produced ~921 tok/s, TTFT P50 1.069 s / P95 1.127 s, TPOT P50 17.35 ms. Evidence is in `/data/sglang-hicache/gemma4/runs/20261115T-g1-prod-e5m2-eviction/graph-{8k,c32-8k}/results.json`.

### Radix, cancellation, and capacity

- Reused saved 8K fixture through real E5M2 HTTP service. On a fresh process, exact repeat hit 7,167 cached tokens, partial-prefix request hit 2,048, four unrelated 7,168–8,192-token requests ran, and original prefix then re-hit 7,167. All outputs reached requested 32 tokens and retractions remained zero. Cold-prefix initially had 0 cached tokens in the fresh-process run. Evidence: `.../20261115T-g1-prod-e5m2-eviction/radix-cache/results.json`. This proves Radix reuse and successful recomputation, not a deterministic eviction of the original shared prefix: the four unrelated prompts showed large prefix overlap and the old prefix still hit afterward. Earlier run did observe a cold re-computation after eviction (`.../20261115T-g1-prod-e5m2/radix-cache/results.json`); cache eviction is best treated as exercised but not fully isolated.
- A live single-request streamed ~64K input was aborted with `/abort_request` (`abort_all=true`): HTTP 200, stream returned `finish_reason=abort`, client thread finished within the 180-second join, and the service subsequently passed follow-up requests. Evidence: `.../20261115T-g1-prod-e5m2/cancel-r2/results.json`.
- Real random-token C32 capacity: 8,192 input × 32 requests × 32 output tokens: **32/32 success**, full prefill verified, zero retractions, 38.42 s burst. 65,278 input × 32 requests × 32 output tokens: **32/32 success**, full prefill verified, zero retractions, 550.60 s burst; request latency P50/P95 309.08/550.04 s. This is an expensive, queueing-dominated stress point, not a viable latency SLO. Evidence directories: `.../20261115T-g1-prod-e5m2-eviction/c32-{8k,64k}/`.
- No 131K C32 claim is made. The full-context capability flag does not establish concurrent 131K admission; actual E5M2 C32 long-context acceptance here is limited to 65,278-token prompts.

### 60-minute stability

The accepted steady-state run used four workers, each targeting one request start per 25 seconds, deterministic mix of saved 8K prompts and 65,278-token prompts (long request every fifth iteration per worker), 64 generated tokens/request, shared E5M2 service and Radix enabled. Across the four workers it completed **576/576 requests** over 3,556.8 seconds between first and last completed response (59m16.8s; driver window 60m). The average completed-response spacing was 6.19 s due to interleaved worker schedules and completion times; the 25 s value is a per-worker pacing target, not a global rate. Mix: 460 short and 116 long requests. No request errors, no KV retractions, no model restart, and the service remained listening after the load driver ended until the planned watchdog shutdown. End-to-end latency P50/P95/max = 1.175/2.777/19.406 s (long-prefill tail is included). Output throughput averaged 10.37 tok/s over the wall interval; this intentionally paced test is a stability workload, not a throughput benchmark. GPU sample file had 4,142 valid rows and measured 22,091 MiB max / 22,088 MiB mean reported memory used. Evidence: `/data/sglang-hicache/gemma4/runs/20261115T-g1-prod-e5m2/mixed-60m-r2/results.json`, `gpu-samples.csv`, `server.log`.

The first attempt was invalidated as a stability claim: an outer 600-second tool cap terminated the driver while the server's internal 8-minute watchdog was draining, causing a second SIGTERM. The mixed client then retried in a tight loop, producing spurious connection-refused records. No model defect was attributed to that run. The 60-minute run was repeated with both limits extended; the accepted second run has zero errors and completes its full window. The mixed-load driver now rate-limits and halts on service-level exceptions.

## HiCache and operational boundary

The actual candidate runtime reports `enable_hierarchical_cache=false`, `hicache_size=0`, and no storage backend (`hicache_storage_backend=null`). HTTP `/metrics` returned 404, so no independent per-request KV pool telemetry endpoint was available. Existing tests cover GPU-resident Radix only. **HiCache host L2 / storage L3 were not enabled or tested**, so any requirement for these tiers is an explicit NO-GO until a separate authorized configuration and qualification exists.

Cancellation was verified at the HTTP stream/client level and with subsequent service requests; the workload did not independently measure allocator free-list bytes after abort. Physical pool/retraction telemetry is limited to request metadata (`num_retractions`) and sampled device memory. The candidate's 131K configured context, 262K full-token pool, 209,715 SWA pool, high graph memory reserve and multi-second 64K C32 latency mean capacity/latency limits must be enforced by the deployment layer; no production SLO or overload policy is certified here.

## Final acceptance

- Real E5M2 HTTP inference / basic cancellation: **PASS**.
- CUDA Graph Decode capture and live usage bs1–32: **PASS**.
- Short-request concurrency through c32: **PASS**.
- 8K and 64K C32 real admission / decode: **PASS (32-token output only)**; 64K C32 latency is very high.
- Radix reuse / partial hit / post-churn reuse: **PASS**; eviction isolation not fully deterministic.
- 60-minute mixed E5M2 stability: **PASS (576/576, zero errors)** for this bounded workload.
- HiCache L2/L3: **NOT TESTED / NOT ENABLED**.
- E5M2 numerical acceptance: **NOT ACCEPTED** (see `G1-E5M2-NUMERICAL-CLOSURE-NEW-20261115.md`, `G1-E5M2-GRAPH-PAIR-20261115.md`, and E5M2 GSM8K paired report).
- Production: **NO-GO**. Continue BF16 KV by default. E5M2 is suitable only for controlled non-production experimentation until numerical criteria are formally accepted, an explicitly scoped HiCache decision is resolved, and latency/capacity/operational SLOs are approved. No deployment performed.

## Suggested controlled-test configuration (not production-approved)

```bash
G1_PROD_OUT=/data/sglang-hicache/gemma4/runs/20261115T-g1-prod-e5m2-eviction \
G1_PROD_PORT=31401 G1_PROD_CONTEXT=131072 G1_PROD_MAX_RUNNING=32 \
G1_PROD_MEM_FRACTION=.94 G1_PROD_GRAPH_BS=32 \
G1_PROD_RADIX=on G1_PROD_HICACHE=off \
control/gemma4-w4a16-3090-performance-capacity/runs/run_g1_prod_e5m2.sh
```

This is only the exact tested lab candidate. Acquire `/tmp/f1-r16b-gpu-exclusive.lock` through the launcher; do not remove watchdog/cleanup behavior. Evidence root: `/data/sglang-hicache/gemma4/runs/20261115T-g1-prod-e5m2/` and `/data/sglang-hicache/gemma4/runs/20261115T-g1-prod-e5m2-eviction/`.
