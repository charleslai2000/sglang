# T009 — Breakable prefill CUDA graph: enablement, measurements, verdict

Date: 2026-11-26. Frozen base `1e3764c958` (production baseline **587.94** TPS, r6). All work
below keeps the Full/SWA KV capacity, the concurrency limits, the cache tiers and the scheduling
policy unchanged; no allocator code was touched.

## 1. What was enabled

The tree already carries the upstream breakable prefill graph
(`PrefillCudaGraphRunner` + `BreakableCudaGraphBackend`, segmented capture with attention metadata
recomputed out-of-graph, upstream #44220 lineage). It was simply disabled in the frozen launch.
Enablement is a launch-flag change plus three adaptations, no new runner:

```
--cuda-graph-backend-prefill breakable --cuda-graph-bs-prefill 1024 1280 1536 2048 4096
```

(`control/gemma4-rtx3090-throughput-scheduling/runs/t009_pcg_baseline_argv.txt` is the frozen
C-8 argv plus exactly these two flags.)

Bucket choice comes from the measured extend shape histogram of the frozen workload (367 logged
prefill batches, 1,013,761 new tokens):

| new tokens | 4096 | 1280 | 2048 | 3584 | 1024 | 1536 | 2560 | 3072 | 2304 | 3840 | 1 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| batches | 162 | 100 | 26 | 24 | 23 | 22 | 4 | 3 | 1 | 1 | 1 |
| seqs per batch | 4 (162), 1 (124), 2 (53), 3 (28) | | | | | | | | | | |

## 2. Adaptations required to make the existing implementation work here

1. **Capture/replay input contract (correctness).** `capture_prepare` and `load_batch` passed the
   `input_embeds` buffer *and* `input_ids` to the body. Gemma4's text body requires exactly one
   (`gemma4_causal.py:972`), so capture raised immediately. Both now use the input_ids path only,
   which matches replay eligibility: `can_replay_locally` already rejects any batch whose
   `input_embeds` is not `None`.
2. **HiCache H2D dependency (correctness, requested).** `MemoryPool.get_kv_buffer` waits per layer
   on the cache controller's `LayerDoneCounter`. Capture runs with no load in flight, so that wait
   is absent from / stale inside a captured segment: replaying a batch that is still waiting on a
   host→device copy could read KV slots before the copy lands (the in-tree
   `todo (zhiqiang): disable cuda graph execution if hicache loading triggered`). `can_run_graph`
   now returns False whenever the batch's layer-transfer consumer is set and its `finish_event` is
   not complete; eager keeps the load ordering authoritative. Replay always refreshes
   `out_cache_loc` from the live batch through `buffer_registry.fill_from`, so it reads the current
   KV mapping.
3. **Exact-bucket replay.** `load_batch` can only pad the token axis; the captured body derives
   each token's request from live `seq_lens`/`extend_start_loc`, so a padded tail belongs to no
   request. Replay now requires `num_tokens` to be one of the captured buckets. In this workload
   the high-frequency shapes are exact bucket hits, so the constraint costs no coverage and
   removes padding waste.

Capture could not fit in the 1.28 GB left by the frozen KV pool until the allocator used
`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` (allocation policy only — capacity, pool size
and concurrency unchanged).

**Correction to an earlier misreading:** a device-side assert seen during the first enablement
attempts came from my own probe payloads (`input_ids` ≈ 300k, outside the tokenizer vocabulary),
not from graph replay. With in-vocabulary ids the same shapes replay cleanly, including
multi-request batches (115 × 4-request 4096-token replays in r10).

## 3. Short-window validation (real replay vs real eager)

`t009_pcg_ab.sh`, identical 40 clients × 5 rounds C-8 shape, 200 requests, same server config
apart from the prefill backend; device timer + bench:

| | extend (device s) | decode (device s) | output tok/s | prefill batches |
|---|---|---|---|---|
| eager | 34.74 | 26.66 | 742.97 | 152 eager |
| graph (1024/1280/1536/2048) | 32.06 | 26.82 | **770.60 (+3.7%)** | 110 replay / 45 eager |

Extend device time −7.7%; decode unchanged; capture 0.42–0.44 GB, 6.6 s.

Numeric parity: a single-request 1024-token prefill replayed under the graph produced **identical
output token ids** to eager (`20261126T-t009-pcg-parity-{graph,eager}`). Concurrent probes differ
between two *eager* runs as well, so that difference is batch-composition nondeterminism, not a
graph defect.

## 4. Full C-8 acceptance runs (unchanged workload, 800 requests)

| run | buckets | capture | official TPS | duty | bench s | completed | graph / eager batches |
|---|---|---|---|---|---|---|---|
| r6 (frozen) | none | – | 587.94 | 90.57% | 348.34 | 800/800 | 0 / all |
| r9 | 1024,1280,1536,2048 | 0.44 GB | 592.02 | 90.02% | 345.93 | 800/800 | 336 / 170 |
| r10 | + 4096 | 0.71 GB | **594.23** | 90.69% | 344.65 | 800/800 | 552 / 77 |

r10 verification: exact 800-payload multiset (0 missing, 0 unexpected), 0 sanity failures, 0
scheduler exceptions, 0 OOM, no pool-invariant failure, L1 = 9,533,440 and newly-prefilled =
1,013,761 identical to the frozen baseline. Replay mix: 195 × 1280 single, 115 × 4096
multi-request, 67 × 1024 single; remaining eager shapes are 2560/2304/3328 (counts ≤ 26).

## 5. Verdict

* The graph is **real and reproducible**: +6.29 TPS (+1.07%) on the official C-8 metric at
  unchanged KV capacity, unchanged concurrency, identical tier counters, zero correctness
  findings, and a measured −7.7% extend device time on replayed shapes.
* The **≥600 gate is not met** (594.23, 0.96% short). The binding constraint is graph memory, not
  the graph mechanism: six buckets cost 0.72 GB and OOM the workload against the frozen pool
  (measured 22.85 GiB allocated / 2.5 MiB free, a 20 MiB request), five buckets cost 0.71 GB and
  leave 0.70 GB, four cost 0.44 GB. Capturing 3584 as well (24 batches, 86k tokens) would exceed
  that envelope, and the remaining eager shapes are worth ~1% of tokens each.
* Consequently the candidate is **not** withdrawn for being uneconomical — it pays for itself in
  throughput with no capacity cost — but it does not reach the goal, and per instruction it was
  not pushed to the gate by shrinking KV capacity or forcing capture. The prefill backend stays
  opt-in; the frozen default remains `disabled`.

Remaining routes to ≥600, all outside this candidate: extend-path kernel/launch fusion (the bulk
of the residual launch bubbles), or a KV-capacity trade (explicitly forbidden here), or a
graph topology that captures the 3584/4096 token axis at lower per-bucket memory.

## 6. Reproduce

```
# A/B short window
T009_PCG_BUCKETS="1024 1280 1536 2048" bash runs/t009_pcg_ab.sh graph <out>
                                       bash runs/t009_pcg_ab.sh eager <out>
# numeric parity
T009_PCG_BUCKETS="1024 1280 1536 2048" bash runs/t009_pcg_smoke.sh graph <out>
                                       bash runs/t009_pcg_smoke.sh eager <out>
# full C-8 acceptance
T007_BASELINE_ARGV=runs/t009_pcg_baseline_argv.txt T007_OUT=<out> T007_WINDOW_SECONDS=0 \
  T007_CHUNK=4096 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True bash runs/t007_c8_profile.sh
```
