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

---

# Final convergence round (frozen at `8b607f6756`)

## 1. Upstream mechanism audit — nothing missing

| upstream piece | status in this tree |
|---|---|
| `BreakableCudaGraphBackend` segmented capture, shared output buffer | inherited: one `_shared_output_buffer` per backend, `_alloc_full_buffer` on the largest (first) bucket, `_slice_output` per bucket; per-bucket `_outputs`/`_graphs` are views/refs, not copies |
| graph pool reuse | inherited: `get_or_create_global_graph_memory_pool()` + `set_graph_pool_id()` in `capture_session`, so every bucket (and the decode phase) carves the same pool; no per-bucket pool |
| intermediate tensor lifetime / replay-time transients | inherited as the borrow path (`runner_utils/pool.py` + `BumpArenaStub`), wired into this backend through `graph_pool_capture_scope()` / `graph_pool_replay_scope()` |
| `GraphPoolPrecarve` | no such symbol exists in this tree; the same role is played by the borrow/bump-arena path above, which is gated by `SGLANG_ENABLE_GRAPH_POOL_BORROW` (default **False**) |

The only lever that was not already exercised is that env default, so it was measured rather than
assumed:

| run | borrow | buckets | capture | official TPS | duty |
|---|---|---|---|---|---|
| r10 | off | 1024/1280/1536/2048/4096 | 0.71 GB | **594.23** | 90.69% |
| r11 | on | same | 0.71 GB | 593.52 | 90.35% |

No net gain (−0.71 TPS, inside the 0.4–0.7 TPS run-to-run spread established by r6/r8), capture
footprint unchanged. **No code was added for this item** and the default stays off.

## 2. Per-bucket economics — 3584 deliberately not added

Residual eager shapes in r10 (the best run): 2560×26, 2304×23, 3328×22, 3840×2, 3072×2,
**3584×1** → ≈210k tokens, 21% of new tokens. 3584 would cover a single batch, so adding it is
pure memory cost. Measured bucket costs: ~0.11 GB per small bucket, +0.27 GB for 4096; capture
headroom (0.70 GB left after r10) is the binding constraint, not the mechanism. Even covering the
whole residual is bounded by the measured r9→r10 slope (47% more tokens for +2.21 TPS) at roughly
+0.5–0.9 TPS, i.e. ~595 — below the 600 gate. No new kernels, no KV change.

## 3. Correctness with the graph on (`20261126T-t009-pcg-validate`)

Config: `--max-total-tokens 65536`, `--hicache-size 1`, fresh Extent, five buckets, graph on.

* **Alternating replay across buckets**: 160 graph replays spread over 1024/1280/1536/2048/4096
  with the probes sent twice in interleaved (ascending then descending) order. Cold-vs-repeat ids
  are identical for 1024/1280/4096 and differ for 1536/2048; those two compare a cold batch with a
  prefix-hit batch (extend 1 token), and the same class of difference appears between two *eager*
  runs, so it is batch-composition nondeterminism (fp8 KV + different attention tilings), not a
  replay defect. The earlier dedicated parity run is the decisive control: a replayed 1024-token
  prefill matched eager token-for-token.
* **Real L3 restore with the graph on**: target 20,000 tokens → 16 × 20k pressure requests →
  `/flush_cache` → re-request: **19,999 cached tokens restored**, one `disposition=RESTORE`, 38
  extent read/storage-hit log lines. Restore still comes from the Extent tier with capture active.
* **HiCache H2D fallback**: the guard (`can_run_graph` → eager while the batch's layer-transfer
  `finish_event` is incomplete) is in place and now logs at info (rate-limited). In this workload
  it did **not** need to fire: `wait_complete` gates admission, so the transfer is complete before
  the prefill batch runs. Recorded as a safety contract with no observed trip, not as an exercised
  path.

## 4. Verdict for this round

No further net gain is available from the prefill-graph direction at the frozen KV capacity:
mechanisms are fully inherited, borrow adds nothing, the only uncovered buckets are worth
≤0.9 TPS, and the memory envelope forbids the rest. Per the round's own stop condition:

* **Keep the `594.23` TPS opt-in result** (`r10`, five buckets, 0.71 GB capture).
* **≥600 TPS is not reached** — best measured is 594.23, 5.77 TPS (0.96%) short.
* Production default remains `--cuda-graph-backend-prefill disabled`; the enabled configuration is
  reproducible from `runs/t009_pcg_baseline_argv.txt`.
* This direction is closed. Reaching 600 needs extend-path kernel/launch fusion or a KV-capacity
  trade, both outside this task.
