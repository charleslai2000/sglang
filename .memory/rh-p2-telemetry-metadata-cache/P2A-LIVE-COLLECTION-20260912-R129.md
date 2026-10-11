# P2-A live collection — Q1/Q2/Q3 on the R128 probe build (R129)

- task_id: `R129` (P2-A live collection)
- role: `tester` (private, independent verification)
- status: **done**
- ENTRY: `ACCEPT`

## 1. Contract hash re-verification (required first step)

| contract | expected sha256 | actual sha256 | match |
|---|---|---|---|
| `work/P2A-COLLECTION-CONTRACT-20260912.md` | `1b9c296990d309f8a557f6c57aff57f1c9886b016cc0ab79c95f696b98fe3b26` | `1b9c296990d309f8a557f6c57aff57f1c9886b016cc0ab79c95f696b98fe3b26` | **yes** |
| `work/P2A-MEASUREMENT-CONTRACT-20260912.md` | `c05517088fab98424badcdda3ddd094cfbc698aacbc4d0a082e5c27a43b1096a` | `c05517088fab98424badcdda3ddd094cfbc698aacbc4d0a082e5c27a43b1096a` | **yes** |

Both hashes matched at start; collection proceeded.

## 2. Environment / provenance (read-only; no restart, no signal)

| item | value |
|---|---|
| server base | `http://127.0.0.1:30000` (health 200 at start) |
| server PID | `616394` (`python -B -m sglang.launch_server`) |
| scheduler PID | `617035` (`sglang::scheduler`) |
| detokenizer PID | `617036` |
| probe | `SGLANG_P2A_TIMING_PROBE=1` (frozen R128 probe) |
| model | `/mnt/data/models/qwen35-gptq` |
| server log | `/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-p2a.log` |
| repo HEAD | `4f41f5bab562b99562f30c67540eb05344d13637` |
| `run_id` / `process_id` / `profile_id` | `run-617035-40503286897536` / `617035` / `profile-97ee3d5d3bfdca6237dc746e` |
| `deployment_manifest_digest` | `262a9362e345df15d93049301d2b0e60990ba65d80c3bbc5209fb4cdab140e2d` |

**R128 build binding re-verified against the R128 freeze** (`work/R128-profile/P0-C-3090-PROFILE-REFREEZE-20260912.md`). All four producer files match byte-for-byte:

| producer | actual sha256 | R128 expected | match |
|---|---|---|---|
| `managers/scheduler.py` | `e58ca012c48c1f42d01c1df06e4d9680a9dbdf3d0f8b960ec49040841b65b853` | same | yes |
| `mem_cache/unified_radix_cache.py` | `212c3a8ffa63f41a0594ab72efed44698c8062bf745190c63919108f0b6e067f` | same | yes |
| `mem_cache/hybrid_cache/hybrid_cache_controller.py` | `64e933f490884b74f0d38655a8f5a75157bab530dd0ea0688323c9780f1ce4d5` | same | yes |
| `mem_cache/p2a_timing_probe.py` | `96d077b840d66e1d999a1e8f8308c9fc4169458f33da438f776e445032300804` | same | yes |

## 3. Workload actually run

Public HTTP only (`/v1/tokenize` + `/v1/completions`); no product import, no
server control, no `/flush_cache`, no `/close_session`, no restart, no new
instrumentation.

| field | value |
|---|---|
| driver | `work/R129-bundle/driver129.py` (sha `067904d0…af2f6`; run-1 executed the pre-supplement revision `8c41aba6…b999`) |
| N sessions | **8** (>=4) |
| TURNS | **6** (>=5) |
| session history tokens | **6,025 / 7,421 / 8,584 / 9,724 / 10,918 / 11,949 / 6,949 / 9,344** (all in 6k–12k; unique per-session marker) |
| distinct history tokens | **70,914** (> device KV pool 65,536 → device eviction) |
| pressure tokens | 6 fill (~12.1k each) + 5 inter-round (~12.2k each) ≈ **73k** distinct; combined working set ≈144k > host pool 131,072 → host eviction |
| total requests | **59** (8 COLD prime + 40 warm + 11 pressure); all HTTP **200**; 0 non-200; 0 budget-skips |
| total prompt tokens | 724,929 |
| duration | **514.0 s (8.57 min)** |
| HTTP count | **60** (59 completions + 1 tokenize) + 1 dry-run tokenize; budget was 200 |
| shape | turn 1 COLD full history; turns 2..6 warm re-send full history + novel delta; pressure between rounds |

Log window measured: server log **lines 36,294–597,400** (561,107 lines), sliced
at run end. Full 69 MB window preserved at
`/mnt/data/nerun-dev/r129/window-36294-597400.log` (sha
`a19fed9298341d69430308f24352390edee1d51b97b322d06032dc308b938132`); compact
mark window in the bundle (`marks-window.log`).

## 4. Q1 — queue lead time (`admission_monotonic_ns − enqueue_mono_ns`, by rid)

- M1 `enqueue_mono_ns`: **59/59** requests (exactly one per rid; 0 duplicates).
- `admission.v2`: **27** rids joined; `admission_monotonic_ns` always later than
  the enqueue mark (0 negative); 0 duplicate `admission.v2`.
- **Q1 (n=27):**

| stat | ns | ms | s |
|---|---|---|---|
| min | 40,354,503 | 40.355 | 0.040 |
| p50 | 1,694,285,336 | 1,694.285 | 1.694 |
| p95 | 33,107,529,615.5 | 33,107.530 | 33.108 |
| p99 | 39,866,462,474.6 | 39,866.462 | 39.866 |
| max | 40,666,971,116 | 40,666.971 | 40.667 |
| mean | 6,391,669,276.3 | 6,391.669 | 6.392 |

Q1 is large because `max_running_requests=1` serializes the concurrent warm
rounds; the deepest-queued request waited ~40.7 s.

## 5. Q2 — L3→L2 stage (`ready_monotonic_ns − prefetch_issue_mono_ns`, same attempt_id)

- M2 `prefetch_issued`: **27** attempts (0 duplicate attempt_ids).
- `ready_host`: **1** completed pair.
- **Q2 (n=1): 16,567,416,651 ns = 16,567.417 ms = 16.567 s**
  (`p50 = p95 = p99 = max` for a single sample).
- Paired attempt: `r129-s0-t2-081155:prefetch:2`, `issue_origin=DEMAND_RETRY`,
  `finalize_result=accepted`, `completed_kv_tokens=1920`.
- Non-completed attempts: **26** attempts have `prefetch_issued` but no
  `ready_host` (exact ids in §8). Of these, 25 reached `evt=restore_recompute`
  and 26 `evt=prefetch_revoke` (wall-ms context only) — they did not complete,
  so no Q2 end is fabricated.

## 6. Q3 — storage metadata query cost (`exit − enter`, by caller / query_len bucket)

M3 `evt=storage_hit_query`: **27** samples. **All `caller=async_prefetch`;
`caller=sync_decode` = 0** (the PD-disaggregation decode-side
`__storage_hit_query__` path is dormant on this profile, as the measurement
contract expects). `lock_wait_ns` / `syscall_wait_ns` / `all_reduce_ns` are
`N/A` for all 27 (set of observed values = `{N/A}`), not a gap.

**Q3 all (n=27):** min 12.418 s · p50 17.777 s · p95 21.181 s · p99 22.278 s ·
max 22.613 s. Human units: p50 17,777.339 ms · p95 21,180.984 ms ·
p99 22,277.504 ms · max 22,612.547 ms.

**Backend attribution (`backend_lookup_ns`, n=27):** p50 17,773.109 ms ·
p95 21,178.057 ms · p99 22,275.451 ms · max 22,610.023 ms — i.e.
**≥99.97 % of the `_storage_hit_query` span is `batch_exists`/`batch_exists_v2`**
(the file backend's `os.scandir`/`os.path.exists` scan). The probe's own
`probe_ns` (M3) is ~1–4 µs, so this is not probe overhead.

By caller:

| caller | n | p50 (ms) | p95 (ms) | p99 (ms) | max (ms) |
|---|---|---|---|---|---|
| `async_prefetch` | 27 | 17,777.339 | 21,180.984 | 22,277.504 | 22,612.547 |
| `sync_decode` | 0 | — | — | — | — |

By `query_len` bucket:

| bucket | n | p50 (ms) | p95 (ms) | p99 (ms) | max (ms) |
|---|---|---|---|---|---|
| `<1k` | 0 | — | — | — | — |
| `1k–5k` | 8 | 19,093.470 | 22,161.527 | 22,522.343 | 22,612.547 |
| `5k–20k` | 19 | 17,500.057 | 19,425.147 | 19,553.085 | 19,585.070 |
| `>=20k` | 0 | — | — | — | — |

`kv_hit_pages`: **2 hits** (both `r129-s0-t2-081155:prefetch:1|2`, 1,920 pages)
and **25 misses** (0 pages). The hit queries were also 15.3–17.8 s, so cost is
not a function of hit/miss.

**Q3 acceptance verdict:** p99 = 22.28 s, which is **≥1 ms by >4 orders of
magnitude → optimization candidate**, and because ~99.97 % of it is the file
backend's synchronous metadata scan (`os.scandir`/`os.path.exists`) inside
`backend_lookup_ns`, with no lock/syscall/all-reduce isolation available, it is
also a **clear disk-syscall / synchronous-blocking wait → architectural
problem** (per the frozen acceptance bands). It cannot be classed as negligible
or observe-only at any bucket.

## 7. Q1-vs-Q2 coverage conclusion

**Direct per-attempt join fails (fail closed).** The single completed attempt
`r129-s0-t2-081155:prefetch:2` has **no `admission.v2` for its rid**
`r129-s0-t2-081155`, so `ready_host` cannot be subtracted from the request's
switch-in mark. **Joinable coverage samples: 0/1.**

**Distributional comparison (clearly labelled inference, not a per-request
proof):**

- Q1 p50 = **1.694 s** vs Q2 = **16.567 s** → the median queue lead is ~10×
  shorter than the L3→L2 stage.
- Q1 p95 = **33.108 s** and max = **40.667 s** exceed Q2, so only requests
  buried deep in the queue can cover the stage.
- Therefore queue lead is **not sufficient in general** to cover the L3→L2
  stage; a restoring request near the head of the queue would be exposed by
  ~16.6 s. A contract-exact per-request verdict is **not measurable from this
  window** because `admission.v2` is not emitted for prefetch-restored rids.

**Mechanistic linkage (contractual marks):** for the one completed attempt,
M3 `_storage_hit_query` = **15.345 s** (`r129-s0-t2-081155:prefetch:2`,
`kv_hit_pages=1920`) vs Q2 = **16.567 s** → the storage metadata query is
**~92.6 % of the L3→L2 stage**. So the storage query sits on the prefetch
critical path (async prefetch thread), and dominates it.

## 8. Probe overhead (`probe_ns`, per mark)

| mark | n | p50 | p95 | p99 | max | any >1 ms |
|---|---|---|---|---|---|---|
| M1 `enqueue_mono_ns` | 59 | 5.27 µs | 7.72 µs | 19.33 µs | 33.41 µs | no (0) |
| M2 `prefetch_issued` | 27 | 4.97 µs | 8.82 µs | 11.00 µs | 11.66 µs | no (0) |
| M3 `storage_hit_query` | 27 | 1.84 µs | 3.65 µs | 4.15 µs | 4.30 µs | no (0) |

No mark exceeded 1 ms; live overhead (~2–33 µs) confirms the off-line
no-op baseline. No measurement-defect flag required.

## 9. Missing / unjoinable records (fail closed — no imputation)

1. **Q1 join gap — 32 rids have M1 but no `admission.v2`** (admission.v2 is
   emitted only when `add_one_req` returns `CONTINUE`; prefetch-restoring /
   not-yet-runnable requests do not emit it):
   `r129-s0-cold-081155, r129-s1-cold-081155, r129-s2-cold-081155,
   r129-s3-cold-081155, r129-s4-cold-081155, r129-s5-cold-081155,
   r129-s6-cold-081155, r129-s7-cold-081155, r129-p0-fill-081155,
   r129-p1-fill-081155, r129-p2-fill-081155, r129-p3-fill-081155,
   r129-p4-fill-081155, r129-p5-fill-081155, r129-s0-t2-081155,
   r129-s1-t2-081155, r129-s2-t2-081155, r129-s3-t2-081155,
   r129-s4-t2-081155, r129-s5-t2-081155, r129-s6-t2-081155,
   r129-s7-t2-081155, r129-press-t2-0-081155, r129-s1-t3-081155,
   r129-s0-t3-081155, r129-s2-t3-081155, r129-s5-t3-081155,
   r129-s7-t3-081155, r129-press-t3-0-081155, r129-press-t4-0-081155,
   r129-press-t5-0-081155, r129-press-t6-0-081155`.
2. **Q2 join gap — 26 attempts have `prefetch_issued` but no `ready_host`**
   (non-completed attempts; count only, no fabricated end):
   `r129-s0-cold-081155:prefetch:1, r129-s1-cold-081155:prefetch:1,
   r129-s2-cold-081155:prefetch:1, r129-s3-cold-081155:prefetch:1,
   r129-s4-cold-081155:prefetch:1, r129-s5-cold-081155:prefetch:1,
   r129-s6-cold-081155:prefetch:1, r129-s7-cold-081155:prefetch:1,
   r129-p0-fill-081155:prefetch:1, r129-p1-fill-081155:prefetch:1,
   r129-p2-fill-081155:prefetch:1, r129-p3-fill-081155:prefetch:1,
   r129-p4-fill-081155:prefetch:1, r129-p5-fill-081155:prefetch:1,
   r129-s0-t2-081155:prefetch:1, r129-press-t2-0-081155:prefetch:1,
   r129-s1-t3-081155:prefetch:1, r129-press-t3-0-081155:prefetch:1,
   r129-s0-t4-081155:prefetch:1, r129-s2-t4-081155:prefetch:1,
   r129-press-t4-0-081155:prefetch:1, r129-s0-t5-081155:prefetch:1,
   r129-s2-t5-081155:prefetch:1, r129-press-t5-0-081155:prefetch:1,
   r129-s0-t6-081155:prefetch:1, r129-press-t6-0-081155:prefetch:1`.
   (Note the retry pair: `r129-s0-t2-081155:prefetch:1` queried L3
   `kv_hit_pages=1920` but did not complete; `:prefetch:2` completed.)
3. **Coverage join gap — 0 joinable Q1×Q2 samples** (see §7). The one Q2 rid is
   absent from the Q1 population; no other attempt completed.
4. **Integrity:** 0 duplicate M1 per rid, 0 duplicate `admission.v2` per rid,
   0 duplicate M2 attempt_id, 0 `ready_host` without a matching
   `prefetch_issued`, 0 negative Q1. No record was imputed.

## 10. Infrastructure event (not a product defect, not caused by R129)

Run 1 completed normally at log line 59,7400 (`run_end`, 59/59 HTTP 200, all
requests drained). **~16 s later the server received an external SIGTERM**
(`[2026-09-12 08:20:46] SIGTERM received. signum=None frame=None. Draining
requests and shutting down...`, log line 597400), drained 0 remaining requests,
and exited. PIDs 616394/617035/617036 no longer exist; port 30000 has no
listener. R129 sent no signal and did not restart the server.

A second, contract-compliant supplement run (aggressive eviction bursts to try
to raise the Q2 sample count) was started at 08:21:01 and **aborted immediately
with `ConnectionRefusedError`** because the server was already down; no
supplemental HTTP requests were served. This is why Q2 has n=1. Evidence:
`run2-context.txt`, `driver-run2.out`, `run-20260912-082101/state.jsonl`,
`teardown.log`.

## 11. Final answers to the three P2-A questions

1. **Is queue lead time sufficient to cover the L3→L2 stage?** — **No, not in
   general.** Q1 p50 (1.694 s) is ~10× smaller than Q2 (16.567 s); only the
   deep tail (p95 33.1 s, max 40.7 s) covers it. The direct per-request join is
   unmeasurable on this build because `admission.v2` is not emitted for
   prefetch-restored rids (fail-closed gap).
2. **How long does the L3→L2 stage actually take?** — **~16.57 s** (n=1, one
   completed `ready_host`; 26 non-completed attempts reported, not imputed).
3. **Is the storage metadata/query itself worth optimizing?** — **Yes.** Q3
   p99 = **22.28 s**, ~100 % of it the file-backend metadata scan
   (`backend_lookup_ns`); this is an optimization candidate and a clear
   disk-syscall / synchronous-blocking architectural problem. It is ~92.6 % of
   the observed L3→L2 stage.

## 12. Deliverables / integrity

- Report: this file. Bundle: `work/R129-bundle/` (driver, extraction script,
  run state/requests, console logs, compact raw mark window, teardown, sums).
- Bundle `sha256sums.txt`: **16/16 files verified OK**.
- Overflow R121–R128 artifacts were not modified; product source read-only.

Residual / follow-ups for the orchestrator (not started here):

- Q2 has n=1 and the coverage join is empty; a fresh dispatch after the server
  is restored could run a heavier eviction-burst workload (driver supports
  `R129_BURST_TURNS`/`R129_BURST_N`) to populate Q2 and to attempt the Q1×Q2
  join, provided the `admission.v2` coverage gap allows it.
- The `admission.v2`-not-emitted-on-prefetch-restore gap and the
  file-backend `batch_exists_v2` multi-second scan are product/telemetry
  findings owned elsewhere — not diagnosed or fixed here.
