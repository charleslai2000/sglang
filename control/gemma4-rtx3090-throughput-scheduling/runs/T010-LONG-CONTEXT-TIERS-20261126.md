# T010 — long-context three-tier cache: cells, telemetry, and where the time goes

Frozen source `e3beda6088`. This round ends the T007/T009 optimisation lines: the prefill CUDA
graph stays **disabled**, and Full/SWA capacity, the 8 GiB host quota, max-running 32,
chunked-prefill 4096 and `write_back` + `wait_complete` are all untouched.

## 1. Workload (same harness, more logical sessions)

`benchmark/hicache/bench_multiturn.py`, now driven through the existing wrapper with
env-overridable bench flags (`T007_BENCH_CLIENTS/ROUNDS/REQ_LEN/OUT_LEN/RATE/MAXPAR/TAG`):

```
96 clients x 6 rounds, 5000-token turns, 256-token outputs, Poisson 8, seed 42,
--fixed-history-tokens, --max-parallel 64
final context/session = 5000 x 7 + 256 x 6 = 36.5K
working set            = 96 x 36.5K = 3.5M tokens  vs  L1 1.44M + L2 0.877M = 2.32M  (+51%)
total prompt tokens    = 10,448,641  (identical in both cells, verified from metrics)
```

No GPU capacity was shrunk to manufacture hits; the working set exceeds the two device+host tiers
by geometry. Host pool confirmed at 876,899 tokens (7.18 GB), SWA host 39,866.

## 2. Same-load cells

| | cell B — L1 only | cell A — L1+L2+L3 |
|---|---|---|
| official TPS | 78.66 | **112.51 (+43.0%)** |
| bench seconds | 1874.5 | **1310.6 (−30.1%)** |
| completed | 576/576 | 576/576 (0 failed) |
| forward duty | 99.54% | 93.36% |
| prompt tokens | 10,448,641 | 10,448,641 |
| … L1 hit | 264,759 (2.5%) | 3,438,033 (32.9%) |
| … L2 hit | 0 | 687,524 (6.6%) |
| … **L3 hit** | 0 | **0 (0.0%)** |
| … re-prefilled | 10,183,882 | 6,323,084 (60.5%) |
| extend device time | 1747.0 s | 1107.1 s (**−640 s**) |
| decode device time | 119.0 s | 116.6 s |
| eviction time | 486.4 s | 509.9 s |
| D2H backup | – | 7.34M tokens / 64.9 GB / 22.4 s |
| L3 writes | – | 3.26M tokens (7,224 extent_write) |

The tier stack is worth **+43% throughput / −30% wall** at 36.5K context, and L2 restores are
substantial and valid (687,524 tokens served from host DRAM). **L3 delivers nothing**: 522
prefetch attempts produced 436 `miss_reason=miss` revocations, 77 `PARTIAL requested=15511
granted=5000 reason=shortfall`, and 723 extent reads that never became a hit.

## 3. Where the remaining time goes (cell A, 1107 s extend)

1. **Re-prefill of 6.32M tokens is the dominant loss**, and its cause is the L3 restore contract:
   the lookup needs a contiguous durable chain from the root, so a session whose older spans were
   evicted from L2 without a completed/dedup'd L3 chain gets *no* restore at all, and the partial
   path caps at one turn (granted 5,000 of 15,511 requested). L3 holds 3.26M tokens of writes that
   are never read back.
2. **Eviction costs 510 s (46% of extend)** for 4.27M evicted tokens (1,232 eviction passes,
   0.41 ms/K-token) — the second-largest single item, and it exists only because 3.5M tokens
   churn through a 2.32M two-tier window.
3. GPU idle is small (duty 93.4%); there is no sync/launch bottleneck to chase here, which is why
   the T007/T009 line is closed rather than reopened.

## 4. Next implementation step (largest loss first)

Target the L3 restore contract, not eviction: restore the **longest durable L3 span for the
request's anchor** (walk to the deepest durable ancestor, load from there down, re-prefill only the
uncovered tail) instead of requiring the root-contiguous chain that the current lookup demands.
Expected effect: convert most of the 6.32M re-prefilled tokens back into H2D restores; at the
measured 0.17–0.18 ms/token extend cost, each 1M tokens returned to L3 saves ~175 s of extend
(~+13 TPS on this cell). Correctness must stay anchored on the same proofs the L2 path already
uses (host material + completed H2D event), with the prefill graph left disabled so the
per-layer `LayerDoneCounter` wait remains authoritative.

## 5. Reproduce

```
# cell A (three tiers)
T007_BASELINE_ARGV=runs/t007_c8_baseline_argv.txt T007_OUT=<out> T007_WINDOW_SECONDS=0 \
  T007_CHUNK=4096 T007_HICACHE_MODE=on T007_BENCH_CLIENTS=96 T007_BENCH_ROUNDS=6 \
  T007_BENCH_REQ_LEN=5000 T007_BENCH_TAG=T010-l3 bash runs/t007_c8_profile.sh
# cell B (L1 only): same with T007_HICACHE_MODE=off
# comparison table
python3 runs/t010_compare_cells.py <cellA_dir> <cellB_dir>
```

---

# Follow-up: L3 capacity hypothesis tested and falsified

Cell A's third tier served **zero** tokens while the extent file sat at its 32 GiB `max_size`
(`du -sh l3-extent` = 33 GB) and the backend logged `extent_eviction_radix_invalidate`. The
working set evicted from L2 is ~2.6M tokens ≈ 26 GB, so the natural hypothesis was capacity:
the tier evicts itself before a session returns. Cell A2 re-ran the identical workload with the
extent tier set to **64 GiB** (`runs/t010_c8_l3_64g_argv.txt`; `file_size` = `max_size` =
68,719,476,736), everything else unchanged.

| | cell B L1 only | cell A three tiers (32 GiB L3) | cell A2 three tiers (64 GiB L3) |
|---|---|---|---|
| official TPS | 78.66 | **112.51** | 108.30 |
| bench seconds | 1874.5 | **1310.6** | 1361.6 |
| forward duty | 99.54% | 93.36% | 93.78% |
| prompt tokens | 10,448,641 | 10,448,641 | 10,448,641 |
| L1 hit | 264,759 | 3,438,033 | 3,129,659 |
| L2 hit | 0 | 687,524 | 714,896 |
| **L3 hit** | 0 | **0** | **0** |
| re-prefilled | 10,183,882 | 6,323,084 | 6,604,086 |
| extend device | 1747.0 s | 1107.1 s | 1157.3 s |
| eviction | 486.4 s | 509.9 s | 543.8 s |
| L3 writes | – | 3.26M tokens | 3.30M tokens |
| extent self-eviction | – | yes (file at max_size) | **none** (0 events) |

Verdict: **capacity is not the blocker.** Doubling the third tier removed self-eviction entirely
and still served 0 tokens from L3 — it even cost ~4 TPS through the larger extent directory's
bookkeeping. The residual behaviour is identical in both cells: 3.3M tokens are written to L3,
`prefetch_revoke ... storage_hit=0 miss_reason=miss` dominates, and the partial path grants at most
about one to two turns (`granted=5000` of 15,511; best observed `granted=10,256` of 20,767), so
~63% of prompt tokens are recomputed.

Therefore the two tiers that work are L1+L2 (+43% TPS, −30% wall versus L1-only), and the open
item is the L3 **read/durability contract**, not tier sizing: writes land (3.3M tokens, 65.9 GB of
D2H feeding them) but the lookup never turns them into a served span for a returning session.
Next step is still the anchor-based longest-durable-span restore, now with the sizing hypothesis
explicitly excluded — and it must explain why a written node's hash chain is no longer readable
after L1/L2 eviction rather than assuming it.

---

# Correction: the "L3 serves zero" reading was a counter-attribution artifact

The `l3` series in the table above is not "tokens the Extent tier delivered". Tracing it:
`sglang:hicache_prompt_tokens_total{source="l3"}` is fed from
`matched_prefix_l3_tokens`, i.e. the **match-time authority** of the radix tree
(`scheduler._final_storage_survivability` -> `tree_cache.is_l3_durable(anchor)`), and it only
becomes non-zero when the *tree node* itself is still alive and flagged durable. Tokens that come
back through a storage prefetch are staged into the host pool first and then matched as `l2`.

Two independent checks agree with that reading:

* cell A2's restore grants sum to ~830K tokens (32 x 5,000 + 21 x 10,256 + 17 x 15,512 +
  7 x 20,768 + 3 x 4,999 + 2 x 15,511), the same order as the measured `l2` total of 714,896
  (some grants hit shortfall/admission losses), and the run logged **723 `extent_read`**
  operations — the third tier is being read.
* the largest grant per request is `requested - ~one output turn`, and several are
  `requested + 1` (15,511 -> 15,512; 20,767 -> 20,768), i.e. the restore covers essentially the
  whole requested span for those requests; the `PARTIAL` label there is an off-by-one in the
  disposition comparison, not a functional shortfall.

So the correct statement of the three-tier result is:

* the tier stack (L2 host DRAM + L3 Extent, with L3 feeding restores through host staging) is
  worth **+43% TPS / −30% wall** against L1-only on the identical workload;
* `source="l3"` staying at 0 does **not** mean the third tier is idle — it means no request was
  served by a *tree-resident, durable-flagged* node, which is expected once the working set
  (3.5M tokens) exceeds L1+L2 (2.32M) and the tree keeps only the LRU window;
* the residual cost is therefore not a broken L3 path: it is 6.6M re-prefilled tokens (extend
  ~1.1 s/K-token) plus ~0.5 s/K-token of eviction, i.e. the price of a working set that is 51%
  larger than the two fast tiers, with the third tier returning a few hundred thousand tokens per
  pass.

Consequence for the next step: an anchor-based restore is still the way to convert more re-prefill
into H2D loads, but it must be justified as *widening* what one restore returns (the per-request
grant already reaches the full span when the chain is resident), not as repairing a dead tier.
Any future claim about L3 must cite `extent_read` counts and restore grants, not the `l3`
counter alone.
