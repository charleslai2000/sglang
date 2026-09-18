# MAMBA-SWEEP-EVIDENCE-ASSESS-20260918

Status: DONE
Role: domain-analyzer (read-only evidence assessment; no service/GPU/process action)

## Task

Determine whether the mamba-pool sweep evidence already captured on disk is sufficient to pick
`max_mamba_cache_size` (candidates 48 / 56 / 64) for production, **without re-running** the sweep.
The sweep was aborted by a higher-priority production restore. Required: inventory the preserved
evidence, tabulate per-cell metrics with sources, compare cells, and decide whether the size is
already determinable (recommend a size, or name the exact missing measurement). Also record the
cell launch parameters and any KV-pool trade evidence.

## Scope

- Read-only analysis of `/tmp/opencode/mamba-sweep-20260918/**`, `/tmp/opencode/mam_metrics{1,2,3}.txt`,
  `/tmp/opencode/prod-service-20260917/logs/prod-20260917T211800Z-1653969/**` (production baseline),
  and read-only inspection of the frozen tree `/opt/sglang/local-prod-v1.2.1-candidate/src` to
  interpret metric semantics.
- Not in scope: architecture/implementation design, any config edit, any process signal, any GPU
  action, any benchmark/server launch, any git mutation. Only this artifact is written.
- Domain-analyzer authority: clarify terminology, actors, use cases, business rules, invariants,
  edge cases, semantic boundaries. I do not design software or implement code.

## Result

**IS THE ANSWER ALREADY DETERMINABLE?  NO.**

The preserved evidence does **not** contain a completed measurement of the production failure mode,
and the one completed 48-vs-56 pair does not show suppression. Three concrete reasons:

1. **The production tail was a mamba *host/L2* pool exhaustion (`WAIT_CAPACITY reason=HOST_ALLOC`,
   `failed_domains=["mamba"]`), but neither completed sweep cell reproduced it.** In the production
   run there were exactly **42** `state=WAIT_CAPACITY reason=HOST_ALLOC` entries and **42**
   `restore_host_alloc_retry_result` records with `"failed_domains": ["mamba"]` (free_before=0,
   required≈3436–3556 tokens), each parked for a full **60 s** (T13 clock). In the two completed
   sweep cells the 117+117 `WAIT_CAPACITY` entries are **all `reason=FRONTIER`** (an ordering/ACK
   wait), and there are **zero** `HOST_ALLOC`/`failed_domains`/`aux_alloc_failed` records. The sweep
   therefore did **not** exercise the mechanism the fix is supposed to address, at either size.
2. **The device availability signal named in the dispatch does not discriminate.** `cell-48` and
   `cell-56` both reach `mamba_available_min = 0.0` (the pool's *schedulable* free-slot gauge), both
   hit 0 in a similar fraction of samples (27/242 vs 22/203), and both show `mamba_used_max = 32`.
   With `max_mamba_cache_size` = 48 vs 56 the metric is dominated by radix/evictable accounting, not
   by pool size; it cannot separate the sizes.
3. **The 48→56 comparison is non-monotonic and the third point is absent.** WAIT_CAPACITY event count
   is identical (117 vs 117); p50/p95 improve slightly but **p99/max get worse** (35.94 s → 61.65 s /
   36.63 s → 63.05 s). Cell 64 produced **no completed `cell-64.json`** (three attempts all terminated
   mid-load; partial request-metrics only). No size can be recommended.

**Recommended size: none determinable from disk.**

**Exact missing measurement (narrow):** a completed cell whose load drives the **mamba host aux pool
to free=0 with `restore_host_alloc_retry_result` / `failed_domains=["mamba"]`** and a measurable
per-request TTFT tail, run at 48 and at 56 (and 64 only if 48 vs 56 stay flat). Equivalently: the
current harness must be made to reproduce the production `HOST_ALLOC` signature; without that, the
`FRONTIER`-only waits it generates cannot test a `--max-mamba-cache-size` change. A re-run should also
produce the missing completed cell 64 so the 3-point curve exists. This is **one bounded GPU window**
(one server run per size; per-cell wall time ≈ 7 min at the sweep2 harness shape).

**KV-pool trade evidence (present, relevant):** increasing `--max-mamba-cache-size` also enlarges the
mamba L2 (host) pool at the expense of the KV host pool, because `hicache_size` (32 GB) is split
proportionally to device-pool bytes (`hybrid_pool_assembler._split_hicache_size`). Measured at startup:
48 → KV host 1,509,560 tokens / 24.73 GB, mamba host **7.31 GB**; 56 → KV host 1,455,589 tokens /
23.85 GB, mamba host **8.19 GB**. So 56 buys ~+0.88 GB mamba host L2 for ~−53,971 KV host tokens
(−3.6%). This is a real trade but it is **not** the measured cause of the observed differences, and it
was never exercised along the production failure path.

## Evidence

### Cell inventory (what ran, what did not)

| Cell / run | Window (UTC) | Terminal? | Verdict |
|---|---|---|---|
| `cell-48` sweep1 `sweep-mamba48-20260917T231327Z-1726566` | 23:13:47–23:16:59 | supervisor rc=0 | **PARTIAL / INVALID for purpose** — completed 96 requests but `gen_tokens=0`, all `completion_tokens=0`, 0 WAIT_CAPACITY, restore path not exercised |
| `cell-48` sweep2 `sweep2-mamba48-20260917T231910Z-1727975` | 23:19:15–23:30:05 | supervisor rc=0 | **COMPLETE** (`cell-48.json`) |
| `cell-56` sweep2 `sweep2-mamba56-20260917T231910Z-1727975` | 23:30:57–23:40:14 | supervisor rc=0 | **COMPLETE** (`cell-56.json`; finished during this assessment) |
| `cell-64` sweep2 `sweep2-mamba64-20260917T231910Z-1727975` | 23:42:17–23:47:13 | load_rc=143 "Terminated" | **NEVER COMPLETED** — no `cell-64.json`, `load-summary.txt` 0 bytes |
| `cell-64` sweep2b `sweep2-mamba64b-20260917T234929Z-1736234` | 23:49:35 | FATAL refused | **NEVER LAUNCHED** ("GPU has a material compute holder") |
| `cell-64` sweep3 `sweep3-mamba64-20260917T235029Z-1737059` | 23:50:32–23:53:43 | load_rc=143 "Terminated" | **NEVER COMPLETED** — partial only |

- `phase0/` is **empty** (`ls /tmp/opencode/mamba-sweep-20260918/phase0` → no entries): no Phase-0
  baseline was ever written.
- `alloc-48/56/64.json` exist and all `result: PASS` (namespace allocation only, 23:13:27Z); a
  namespace allocation is **not** a measurement.
- The cell-64 attempts at 23:42–23:53 occurred **concurrently with this analysis**, driven by another
  active task; they are recorded as observed facts, not analyzed further.
- `cell-48` sweep1 is excluded from comparison because its `cell-48.json` reports `gen_tokens: 0`,
  `ttft_p95: 5.1143`, `vram_peak_mib: 23149`, and its console has **0** WAIT_CAPACITY and only
  1 `prefetch_issued` / 122 `rh_match_prepare` (vs 281 / 1249 in sweep2) — i.e. it never drove the
  restore/mamba path. (Its 96 requests ran in a 62.97 s wall.)

### Per-cell metrics (with sources)

Source paths abbreviated: `L = /tmp/opencode/mamba-sweep-20260918/phase2/logs`; `C48 = L/cell-48-sweep2-mamba48-...-1727975`;
`C48a = L/cell-48-sweep-mamba48-...-1726566`; `C56 = L/cell-56-sweep2-mamba56-...-1727975`.
JSON line numbers are `cell-48.json` / `cell-56.json`.

| Metric | cell-48 sweep2 | cell-56 sweep2 | Source |
|---|---|---|---|
| TTFT p50 / p95 / p99 / max (s) | 13.825 / 30.8447 / 35.9411 / 36.6254 | 12.5555 / 20.6471 / 61.6461 / 63.0498 | `C48/cell-48.json:16-20`; `C56/cell-56.json:16-20` |
| TTFT n | 128 | 128 | `cell-*.json:20` (`ttft_count`) |
| WAIT_CAPACITY events (count) | 117 `state=WAIT_CAPACITY`, all `reason=FRONTIER` | 117, all `reason=FRONTIER` | `C48/server.console.log`, first at line 959; `C56/server.console.log`, first at line 999; exact counts from `evt=restore_state ... state=WAIT_CAPACITY reason=FRONTIER` |
| WAIT_CAPACITY reason mix | FRONTIER 117; HOST_ALLOC 0 | FRONTIER 117; HOST_ALLOC 0 | same console files; `restore_host_alloc_retry_result` count = 0 in both |
| WAIT total time (frontier_wait→frontier_wake) | sum 129 s; p50 1 s; max 9 s (117 pairs) | sum 94 s; p50 0 s; max 46 s (117 pairs) | derived from `evt=frontier_wait`/`evt=frontier_wake` timestamps in `C48`/`C56` console (second resolution) |
| `mamba_available_tokens` min | 0.0 | 0.0 | `cell-48.json:22`; `cell-56.json:22` |
| `mamba_available_tokens==0` frequency | 27 / 242 samples | 22 / 203 samples | `cell-*.json` `samples[]` (`mamba_available_tokens`) |
| `mamba_used_tokens` max | 32 | 32 | `cell-48.json:23`; `cell-56.json:23` |
| Console `mamba usage` max | 0.67 (n=719; never 1.0) | 0.57 (n=728; never 1.0) | `mamba usage:` lines in `C48`/`C56` console |
| Aggregate gen TPS | 65.86 | 77.89 | `cell-48.json:14`; `cell-56.json:14` (`aggregate_gen_tps`) |
| Per-request gen TPS | 9.7 | 11.55 | `cell-48.json:15`; `cell-56.json:15` (`per_request_gen_tps`) |
| Wall / gen tokens | 497.51 s / 32768 | 420.708 s / 32768 | `cell-*.json:12-13` |
| `max_total_tokens` | 524288 | 524288 | `C48`/`C56` console line 673; also `prod-argv.txt` |
| KV `kv_used_max` / `kv_available_min` | 96929 / 16 | 111634 / 9 | `cell-48.json:24-25`; `cell-56.json:24-25` |
| KV utilization (console `full token usage`) | max 0.18 | max 0.21 | `full token usage:` lines in `C48`/`C56` console |
| VRAM peak (MiB) | 22995 | 23389 | `cell-48.json:26`; `cell-56.json:26` |
| OOM / request errors | 0 failed / 0 OOM text | 0 failed / 0 OOM text | `cell-*.json:6-8`; no "out of memory"/"CUDA error" in `C48`/`C56` console |
| Lazy Triton-kernel advisories | none | 3 (`_fused_sigmoid_mul_kernel` etc., "free device mem: 0.73 GiB") | `C56/server.console.log:726,821,948` |
| Mamba host L2 pool | 7.31 GB | 8.19 GB | `Allocating ... GB host memory for hierarchical Mamba cache` — `C48` console line 676; `C56` console line 676 |
| KV host pool | 1509560 tokens / 24.73 GB | 1455589 tokens / 23.85 GB | `Allocating kv hierarchical KV host pool` — `C48`/`C56` console line 675 |
| Device mamba allocation | `conv 0.05GB, ssm 2.30GB` | `conv 0.06GB, ssm 2.67GB` | `Mamba Cache is allocated` — `C48` console line 663; `C56` console line 663 |
| Post-model available GPU mem | 1.92 GB | 1.54 GB | `max_total_num_tokens=...` line — `C48`/`C56` console line 673 |

Partial cell-64 observations (request-metrics only, no `cell-64.json`; **not** comparable as a cell):
- `cell-64-sweep2` (terminated 23:47): 56 big-prompt request-metrics, e2e min/p50/p95/max =
  19.0/20.8/21.57/21.71 s; WAIT_CAPACITY text count 388; `failed_domains` 0.
- `cell-64-sweep3` (terminated 23:53): 16 big-prompt request-metrics, e2e min/p50/p95/max =
  19.46/20.52/39.81/39.81 s; WAIT_CAPACITY 186; `failed_domains` 0.
- These are truncated, different-window fragments; do not use as cell-64 data.

### Production baseline (context; source: `/tmp/opencode/prod-service-20260917/logs/prod-20260917T211800Z-1653969/`)

- Config: `--max-mamba-cache-size 48`, `--max-total-tokens 524288`, `--max-running-requests 8`,
  `--hicache-size 32` (`/tmp/opencode/mamba-sweep-20260918/phase2/prod-argv.txt`).
- 515 request events across `sglang-request-metrics-20260917_{21,22,23}.log`; e2e p50/p95/p99/max =
  **4.7 / 67.9 / 102.6 / 135.4 s**; 52 requests >60 s, 7 >100 s, 5 >120 s.
- **42** `state=WAIT_CAPACITY reason=HOST_ALLOC` entries (`server.console.log:3002` first occurrence,
  21:44:08Z); **42** `restore_host_alloc_retry_result` records with `"failed_domains": ["mamba"]`,
  mamba `free_before=0`, `required` 3436–3556 tokens, `retry_outcome="forfeited_alloc_failed"`.
- Each HOST_ALLOC episode lasted a full **60.0 s** (T13 clock); 36 unique rids; total ≈ 2465 s of
  parked time. There are **0** `frontier_wait`/`restore_retry` events in production.
- `hicache_mamba_host_usable_tokens = 142.0` in all three `/tmp/opencode/mam_metrics{1,2,3}.txt`
  snapshots (22:38, 22:56, 23:03Z), i.e. the mamba host pool's usable capacity is tiny (~142 units)
  against these restores.
- The production dispatch premise (`mamba_available_tokens==0 → WAIT_CAPACITY`) is confirmed only for
  the *state*: `mam_metrics*.txt` shows `mamba_available_tokens` 13.0 → 1.0 → 0.0 across the three
  snapshots. But the **wait reason in production is `HOST_ALLOC` (mamba host aux alloc failure), not
  a device `mamba_available_tokens==0` denial**; those are different state-machine events
  (`DENIED_ALLOC`/T3 → `RestoreWaitReason.HOST_ALLOC`, vs capacity-type events — see
  `hicache_restore.py:530-543`).

### Terminology / semantic boundaries (from the frozen tree, read-only)

- `--max-mamba-cache-size` sizes the **device** mamba SSM state pool. The metric
  `sglang:mamba_available_tokens` is `mamba_allocator.available_size()` = *schedulable* free slots,
  excluding evictable (radix-cached) slots (`pool_stats_observer.py:244-269`). It can read 0 while the
  pool still has evictable state; it is **not** by itself evidence of capacity exhaustion.
- Increasing `--max-mamba-cache-size` also increases the mamba **host (L2)** pool because the fixed
  `--hicache-size` is split proportionally to device-pool bytes
  (`hybrid_pool_assembler.py:134-148, 711-731`; `pool_host/mamba.py:41-82`). This is the plausible
  causal channel from the flag to the production `HOST_ALLOC["mamba"]` failure — but it is exactly
  the channel the completed sweep cells did not exercise.
- `WAIT_CAPACITY` is a state, not a duration; distinct reasons denote distinct mechanisms:
  `FRONTIER` (T5 ordering/ACK wait) vs `HOST_ALLOC` (T3 host aux alloc failure). Conflating them
  would be an error.
- `WAIT_CAPACITY/HOST_ALLOC` has no Ready-Horizon wake; it is retried on the paced retry / T13
  (60 s) path (`ready_horizon.py:418-440`), which explains the 60 s quantization of the production tail.

### Comparison (48 vs 56, like-for-like: sweep2, C8, rounds=16, prefix-pool 64)

- WAIT_CAPACITY count: **117 vs 117** (no change; both FRONTIER).
- WAIT total time: 129 s vs 94 s; but max single frontier wait **worse** at 56 (9 s → 46 s).
- TTFT p50 −9.2% (13.825→12.5555), p95 −33.1% (30.8447→20.6471); **p99 +71.5%** (35.9411→61.6461),
  **max +72.2%** (36.6254→63.0498).
- Aggregate TPS +18.3% (65.86→77.89); per-request TPS +19.1% (9.7→11.55).
- VRAM peak +394 MiB (22995→23389); no OOM at either size; post-model free VRAM 1.92→1.54 GB.
- Cell 64: no completed data → the 3-point curve cannot be formed.

Net: no clean, monotonic suppression of the tail at 56, and **no measurement of the production
failure mode at either size**, so the comparison cannot justify a choice.

## Defects / blockers

1. **Failure-mode mismatch (dominant).** Completed cells produced only `FRONTIER` waits; production's
   123 s tail is `HOST_ALLOC` with `failed_domains=["mamba"]`. The sweep as executed does not test the
   production failure path.
2. **Missing completed cell 64.** No `cell-64.json`; all three attempts terminated (one refused for a
   material GPU holder, two killed mid-load at 23:47 and 23:53). `load-summary.txt` 0 bytes.
3. **Cell-48 sweep1 invalid.** `gen_tokens=0`, no WAIT_CAPACITY, restore path not exercised; unusable.
4. **No Phase-0 baseline artifact** (`phase0/` empty), so no pre-sweep baseline exists on disk.
5. **Sampler granularity.** `mamba_available_tokens` samples are 2 s apart and derived from `/metrics`;
   the "hit 0" counts (27/242, 22/203) are sample-level, not event-level.
6. **Concurrent activity under me.** Cell 56 completed and cell-64 attempts started/stopped while this
   read-only assessment ran (another task also brought production up on :30000 at ~23:47). I did not
   interfere. Stable files analyzed had sha256 captured at 23:54Z:
   `cell-48.json 84fa509e…fb657c`, `cell-56.json c18bf008…9771a7`,
   `C48/server.console.log b90a1fcc…a874c6`, `C56/server.console.log c36eafe7…9839e3`.

## Remaining claims / exclusions

- I did **not** restart, stop, signal, or otherwise touch any process, service, port, or GPU; no
  benchmark or server was launched; no sweep file was edited or deleted; no git operation was performed.
- Conclusions rest only on files listed above. Where a metric was unavailable I said so; I did not infer
  values. In particular, no `cell-64.json` metrics exist.
- The single partially-run cell 48 (sweep1) is excluded from the comparison and labeled invalid.
- I did not determine whether the current production instance (restored at ~23:47 on :30000) is
  serving the sweep config; that is outside this invocation.
- Whether 64 is "still needed": yes, a completed 64 is needed **if** 48 vs 56 remain flat — and more
  fundamentally, a cell that reproduces the production `HOST_ALLOC` signature is needed first.
- Follow-on needs are reported to the orchestrator; I did not spawn agents or create IDs.

## Terminal state: DONE
