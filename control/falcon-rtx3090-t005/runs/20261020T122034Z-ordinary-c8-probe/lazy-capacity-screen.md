# Lazy Mamba capacity screen — 2026-10-20

## Setup / identity
- Frozen B0 remains unchanged; no baseline reconstruction or Runtime source edit. SHA256 inventories for relevant Runtime/configurator, model helper, bootstrap, and SM86 binary before/after the first Lazy probe and subsequent pairs matched byte-for-byte. Full inventories are in each run directory.
- Reused B0 launcher and Falcon revision, same process env/GPU, HiCache off, 64 input/256 greedy output direct generation, `mem_fraction_static=.90`, explicit `max_mamba_cache_size=83`, context 8192, overlap on, full Decode Graph, Prefill Graph disabled. Lazy arm changes only `--mamba-radix-cache-strategy extra_buffer` to `extra_buffer_lazy`; other launches restart the server.
- GPU lock `/tmp/f1-r16b-gpu-exclusive.lock` was acquired and held for each launch/measurement. No other SGLang/NSys/HiCache systemd service was running; no process needed killing. Per-run after-files show port closed, GPU reset to 1 MiB and 0%.

## Failure retained
- First probe wrote no timed rows because its temporary output directory was absent (`FileNotFoundError`); retained as `lazy-quick-server.log`. Corrected by creating the directory; retry completed.
- The first attempted two-pair wrapper completed its first pair and second Lazy arm but exited 1 in its final aggregator because its expected `control-r3` path did not exist. Both measured run directories remain intact. The missing third control and lazy fourth measurement were then run in an explicit C32-only pair. No failed process or service remains.

## Capacity and memory
- B0 `extra_buffer`: 83 slots / 5 state slots per request => max-running capped at 16; Mamba state allocation ≈10.90 GiB, BF16 KV=45,736 tokens (K and V ≈0.96 GiB each), Graphs to batch16, post-graph free ≈1.56 GiB.
- `extra_buffer_lazy`: 83 / 4 => max-running and Graph cap 20. Mamba allocation unchanged (conv 0.07 + SSM 10.83 GiB), KV remains 45,736 tokens, post-graph free ≈1.55 GiB. Captures batch20 then 16/12/8/4/2/1. This exposes more concurrency from the existing state allocation; it neither frees additional slots nor increases KV capacity.
- Repeated server logs show actual Decode batches up to 20 (Lazy) vs 16 (default); no OOM/CUDA errors and every client request completed. C32 exercised 128 requests per wave; this is not Batch32 execution.

## Client throughput and tails
Fixed-shape C=32, 128 requests/wave, 32,768 output tokens. Three fresh-process Lazy/control pairs (pair1/r1, pair2/r2, pair3/r3-r4; exact raw JSON in named subdirectories):

| Pair | Lazy TPS | Default TPS | Lazy client P95 | Default client P95 | success |
|---|---:|---:|---:|---:|---:|
| 1 `lazy-paired-20261020T140414Z` | 737.69 | 729.07 | 13.325 s | 11.324 s | 128/128 each |
| 2 `lazy-matched-ab/control-r2` vs `lazy-r3` | 734.69 | 730.75 | 13.405 s | 11.266 s | 128/128 each |
| 3 `lazy-matched-ab/control-r3` vs `lazy-r4` | 743.69 | 736.26 | 13.199 s | 11.173 s | 128/128 each |

Pair setup differs slightly in harness details: pairs 1–2 used the same input protocol with no explicit generation seed; pair 3 enables output token capture and fixed seed 424242; pair 2 includes C16/C24 too. Across three C32 pairs, mean Lazy TPS=738.69, control=732.03, paired differences +8.62/+3.94/+7.43 TPS (about +1.18/+0.54/+1.01%, mean +0.91%). Lazy P95 is worse by +2.001/+2.139/+2.026 s in all three. This is a small saturation throughput change accompanied by a reproducible tail-latency regression; not sufficient to ACCEPT the configuration.
- Pair 2 C16/C24/C32 Lazy TPS 714.75/754.51/734.69 vs control 721.19/731.73/730.75. Pair 1 includes C16/C24 but does not establish a general winner.

## Correctness
- Token-ID output capture is supported by `/v1/completions` `return_token_ids=true` (not `/generate`). A fresh-process single-concurrency C1 exact input produced identical 256/256 greedy output IDs between Lazy and default. This verifies a narrow no-cache, single-input path only.
- First concurrent token-ID check used no explicit seed and compared request index across processes; that index is not a stable request identity under scheduler reordering. It matched 73/128 by index; both arms had the same two token streams but differing multiplicities. This is inconclusive, not a correctness failure or pass. A fixed seed was used for the third C32 pair; only 80/128 request-index streams matched, and unordered counts were 110/128 due to differing stream multiplicities. Thus concurrent exact parity remains **NOT VERIFIED**. Do not treat aggregate token matches as cache/model correctness, and do not infer the unmatched indices are necessarily value drift without a stable request-ID-to-input join.
- No long greedy, FULL KV/MAMBA state snapshot, prefix-cache reuse, Host/Storage restore or logits oracle has passed for this candidate; full T005 correctness/acceptance gate remains open.

## Device telemetry
- One-second whole-device samples for pair1: Lazy mean/max GPU utilization 66.4/100%, peak 22,878 MiB/77C, mean/max power 250/350.6W; control 68.8/100%, peak 22,776 MiB/79C, mean/max power 259/350.2W.
- Pair3 C32 intervals: 101 samples each. Both mean/max GPU utilization 47.05/100%, memory peak 22,772 vs 22,786 MiB, temperature peak 75 vs 76C, mean/max power 193.7/349.8 vs 198.0/350.4W; mean SM clock 1301 vs 1344MHz and memory clock 6802 vs 7036MHz (control vs Lazy). These are coarse whole-GPU clock/power samples, not SM active cycles, Tensor Core, DRAM bandwidth, or stall attribution. Peak GPU activity reached 100% in both arms; no proof that additional Mamba capacity moves the hardware saturation ceiling materially.

## Follow-on capacity calculation
- From boot logs: state bytes/slot ≈ `(10.83 + 0.07) GiB / 83` = 134.48 MiB; BF16 KV bytes/token ≈ `(0.96 + 0.96) GiB / 45,736` = 44.02 KiB. Thus each extra 4 slots costs ≈0.525 GiB, equivalent in byte budget to ~12,513 KV tokens (~27.4% of current pool); post-graph free would be ~1.02 GiB if all else were fixed. This is an estimate, not a safe-capacity measurement. At +8 slots the estimate leaves only ~0.50 GiB before other allocation variance, so do not test that without a tighter memory/graph reserve model.

## Conclusion / next
- Lazy reliably increases the scheduler/Graph active cap 16→20 using identical fixed Mamba/KV allocation. Across three C32 paired repeats it gives a small +0.91% average aggregate output TPS change, but every pair raises client P95 by ~2.0–2.14 seconds. This is a latency tradeoff, not an unqualified optimization win; the explicit C32 workload asks more than the 16-request base cap and Lazy admits 20, increasing queue tail. Do not ACCEPT Lazy as a production setting without a workload SLA disposition.
- Fixed-input C1 token equality is exact; concurrent token/state correctness is not fully verified, and no cache correctness gates were run. Further correctness is needed before any candidate acceptance. A candidate must not be justified solely by +0.91% throughput while ignoring P95 regression.
- Explicit ratio/pool-size increases remain untested and unsafe to raise blindly: only ~1.55 GiB remains after graph capture while KV already holds 45,736 tokens. Next, calculate measured bytes/slot and KV bytes/token from these exact logs; only consider a small, bounded slot increment if it retains graph/OOM margin and report the KV capacity loss. Decode Lock Skip was not toggled; complete shared-node lock receipt and deferred COW ownership review remains before testing.
