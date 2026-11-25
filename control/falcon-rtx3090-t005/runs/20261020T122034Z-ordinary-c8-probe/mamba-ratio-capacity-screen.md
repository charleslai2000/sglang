# Mamba ratio / pool sizing screen — 2026-10-20

## Identity and method
- Reused frozen B0 Falcon revision, branch/HEAD and actual dirty Runtime without rebuilding B0 or changing source. Each process hashes the same runtime/configurator/cache files and SM86 DSO before/after; no drift.
- GPU lock held for every server start and C16/C24/C32 sweep. GPU/port cleanup files retained per run; final GPU 1 MiB, 0%, 36C; port 30160 closed. No SGLang/NSys/HiCache systemd service or competing GPU process existed.
- Relevant source tree includes uncommitted changes in the memory configurator, so ratios were read from actual server arguments/logs; no source edit was made.

## Threshold probing and retained failures
- The first ratio=.921 launch was based on an incorrect back-calculation and gave 46 states, 9 running requests, 160,177 KV tokens. It booted and was stopped after health check; no client workload. Preserved in `ratio84-20261020T143820Z/`.
- `.98/.99/1.00/1.05` startup probes gave 47/48/48/49 slots, 9 max-running, KV 157,084/153,991/153,991/150,898 tokens and post-graph free 1.63/1.67/1.67/1.71 GiB. Clarification: frozen B0 explicitly pins `--max-mamba-cache-size=83`, so its `.9` argument is not an auto-ratio baseline point. Automatic probes are monotonic here; the actual outputs show the ratio-to-slot slope, not a nonlinear failure. Logs retained as `ratio-0.980-k84-*` through `ratio-1.050-k87-*`.
- Ratio6.0’s first health-only run matched B0’s 83 slots, but was stopped after health and is not a throughput row (`ratio6-k84-144525/`). A separate fresh Ratio6.0 process performed the measured sweep. Ratio6.1 was health-only and also resolved to 83 slots; it is not a measured performance row. Ratio7 first health-only startup resolved 85 slots, but no benchmark; preserved under `ratio7-144844/`.
- Bench-script performs graceful SIGTERM; server logs contain the known Uvicorn cancellation traceback at shutdown after all requests completed. Client statuses and post-cleanup snapshots establish no active service, GPU context or port leakage.

## Measured pool results
| Setting | Actual states | slots/request | Max running | Mamba state allocation | BF16 KV tokens | KV K/V | post-graph free |
|---|---:|---:|---:|---:|---:|---:|---:|
| frozen B0 extra_buffer, ratio .9, `max_mamba_cache_size=83` | 83 | 5 | 16 | conv .07 + SSM 10.83 GiB | 45,736 | .96 + .96 GiB | 1.56 GiB |
| ratio6.0 auto cap | 83 | 5 | 16 | same | 45,736 | same | 1.56 GiB |
| ratio7.0 auto cap | 85 | 5 | 17 | conv .08 + SSM 11.09 GiB | 39,550 | .83 + .83 GiB | 1.64 GiB |
| ratio6.0 + Lazy | not yet tested in this ratio arm | — | — | — | — | — | — |

Because frozen B0 explicitly pins `--max-mamba-cache-size=83`, it is not a ratio-derived point. Automatic ratios `.921`→`.98`→`.99/1.0`→`1.05`→`6.0`→`7.0` yield 46→47→48→49→83→85 slots, monotonically. Ratio6 auto happens to reproduce the B0 cap while ratio7 increases it by two; the actual server logs are the basis for comparisons.

## Throughput sweep (one fresh server lifetime each, fixed 64 input / 256 greedy output, one warmup and 4C requests)
| Ratio/strategy | C16 TPS / P95 | C24 TPS / P95 | C32 TPS / P95 | requests successful |
|---|---:|---:|---:|---:|
| 6.0 + extra_buffer, actual cap16 | 713.76 / 5.930s | 732.16 / 11.230s | 730.36 / 11.308s | 64/96/128 |
| 7.0 + extra_buffer, actual cap17 | 717.40 / 5.727s | 670.75 / 12.626s | 660.14 / 12.814s | 64/96/128 |

Ratio7 allocates only two additional state slots, reduces KV capacity by 6,186 tokens (13.5%; about 0.26 GiB K/V), and nevertheless decreases C32 throughput by 70.22 TPS (-9.6%) vs Ratio6, with +1.51s P95. Scheduler logs show active batch17 for 77 steps, batch16 for 26 and smaller batches for 31 steps; no OOM and all requests succeed. Ratio6 has 116 active16 Decode steps and 18 active1. Ratio7 batch17 fails to offset the capacity redistribution cost or its observed saturation performance. This is one process/run per setting, a screening comparison, not a three-pair acceptance experiment.

## Device sampling
- One-second whole-GPU samples over full measured process lifetimes: ratio6 n=156, mean/max `utilization.gpu` 69/100%, peak memory 22,828 MiB, peak 77C, mean/max power 255.6/350.35W, mean SM clock ~1479MHz. Ratio7 n=168, 69.4/100%, 22,706 MiB, 79C, 259.7/350.13W, ~1507MHz. These include startup/idle portions; both peaks hit 100%, but this is not SM active-cycle, Tensor Core, DRAM throughput, or stall attribution.

## Decision and next
- **Reject ratio7 / implicit larger pool** for this frozen workload: it spends ~0.26 GiB on two extra Mamba state slots, loses 6,186 KV tokens, and the single measured sweep regresses C24/C32 throughput and tail despite active batch17. Do not raise ratio to chase capacity blindly.
- Preserve ratio6/default (same actual 83 slots and pool split as B0); it reproduces approximate baseline service performance within screen noise and does not change configuration capacity. No code change or candidate acceptance.
- Lazy at fixed cap gave 20 active requests and +0.91% mean C32 TPS over three pairs but repeatable +2.0s P95; not an acceptable capacity setting without an SLA decision.
- A direct Mamba pool increase via auto-ratio is coupled with KV depletion: ratio7 trades about .26 GiB KV for two slots and degrades saturated throughput. Naive pre-experiment budget estimates were wrong because B0 pins the pool size rather than auto-sizing from ratio. Use the measured monotonic ratio→slot curve above and actual startup KV/graph reserve; do not force `--max-mamba-cache-size` unless measured KV/graph budget and OOM margin justify it.
- Decode Lock Skip has not been enabled. Its shared-node refs, eviction race and COW ownership must be proven first; this screen provides no evidence to override that gate.
