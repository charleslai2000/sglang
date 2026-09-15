# P2-A follow-up A/B contract (FROZEN) — single-variable metadata-cache experiment

- task_id: `P2A-AB-METADATA-CACHE-20260912` (R130)
- epoch: 2026-09-12
- authority: user-approved follow-up after **P2-A = PASS/CLOSED** (root cause
  confirmed: per-query full-directory scan).
- baseline to compare: **R129** (`work/P2A-LIVE-COLLECTION-20260912-R129.md`
  `f3e32ee5…db17a`; verification `work/R129-bundle/P2A-ORCHESTRATOR-VERIFICATION.md`
  `23a7a5fd…1b21`).

## The single changed variable

```
SGLANG_HICACHE_FILE_BACKEND_ENABLE_METADATA_CACHE=1     # was unset (default False)
```

Everything else stays R129: same source (probe build `e58ca012…` scheduler +
`96d077b8…` probe), same L3 dataset/dir
`/mnt/data/neuron/sglang-3090-r112-20260911/l3`, same `launch-r112.sh`
(`2259d406…8caaa3`), same argv/profile, same telemetry (`SGLANG_P2A_TIMING_PROBE=1`),
same workload driver + params. P0-C re-frozen for the new process. GPU acquired
via `flock` and released immediately after.

**Recorded sub-variable (NOT changed):** `SGLANG_HICACHE_FILE_BACKEND_METADATA_TTL`
defaults to **5.0 s** (`environ.py:699`). The report MUST state the effective TTL
and attribute any residual cost to TTL-driven per-key revalidation vs a full RAM
index, rather than assuming "RAM lookup". Do NOT change the TTL in this arm.

## Gates (user-mandated)

1. **Q3**: `storage_hit_query` span p50/p95/p99 falls from seconds to **<1 ms**
   (ideal <100 µs); `backend_lookup_ns` share collapses. Bands: <100 µs ignore,
   100 µs–1 ms observe, >=1 ms candidate (architecture if disk/sync wait).
2. **Q2**: L3->L2 stage drops markedly and is no longer query-dominated.
3. **No regression**: same completed-request count (or better), HTTP 200 on all,
   no errors, restore correctness intact (`kv_fetched==D_req` where exercised,
   `durable-prefix recompute==0`, `hybrid_discard==0`).
4. **Metadata-cache build/init cost recorded separately** — do NOT hide the
   startup scan. Report: launch->health wall, and the metadata pre-scan cost
   (`_scan_existing_files_to_metadata_cache`, `hicache_storage.py:457`) vs the
   evictor scan (`lru_file_evictor.py:298`), e.g. via launch->health delta vs
   R129 and/or an isolated stdlib timing of `os.listdir`+suffix classification
   over the same dir.
5. **Correctness (critical — must not become "fast but stale")**:
   - (a) a new write is immediately queryable;
   - (b) after generation invalidation / lazy GC an old key is NOT falsely hit;
   - (c) after restart the cache rebuilds correctly.

## Execution

1. Acquire GPU ONLY via the launch script's flock
   (`exec 9>/mnt/data/gpu/3090.lock; flock -w 300 9`). Confirm the new server owns
   fd 9 before running. No parallel GPU work.
2. Start the server with the single variable set, to a NEW log
   `sglang-server-p2a-metacache.log` (never overwrite r112/r124/p2a logs):
   `SGLANG_HICACHE_FILE_BACKEND_ENABLE_METADATA_CACHE=1 SGLANG_P2A_TIMING_PROBE=1
    setsid nohup bash /mnt/data/neuron/sglang-3090-r112-20260911/launch-r112.sh
    > <new log> 2>&1 &`
3. Capture new PIDs, argv sha (expect 59 tokens, identical), health, provenance
   markers; write the P0-C re-freeze for this process (record the env toggle).
4. Run the SAME R129 workload: `R130_OUT=… R129_SERVER_LOG=<new log>
   python3 work/R129-bundle/driver129.py --run` with the same R129_* defaults
   (N=8, TURNS=6, N_PRESSURE=6, same HIST_TARGETS). Same request count (59).
5. Correctness:
   - live (a): after a COLD prime writes pages, an immediate subsequent query for
     the same prefix reports `kv_hit_pages > 0`; record the exact `pc_storage_query`
     / M3 lines.
   - live (c): restart the server once (cache ON), then query a prefix written
     before the restart and confirm it still hits; record the init-scan cost.
   - (b): covered by the offline correctness tests
     (`work/R130-correctness/`), plus any live eviction evidence available; if
     eviction does not trigger live, say so and rely on the offline proof.
6. Extract Q1/Q2/Q3 exactly as in R129 (monotonic only, same joins/buckets) and
   compare against R129. Fail closed on missing marks.
7. **Release the GPU**: stop the server (targeted SIGTERM) after the run + restart
   test; confirm the lock is FREE.

## Deliverables

- `work/R130-bundle/` (driver out, per-run dirs, extracted tables, sha256sums,
  new-log slice) and report `work/P2A-AB-METADATA-CACHE-20260912-R130.md`:
  A/B table (R129 vs R130) for Q1/Q2/Q3, gate verdicts, TTL attribution,
  init-cost accounting, correctness results, provenance + hashes.
- `work/R130-correctness/` (offline, NO GPU): stdlib unit tests + microbenchmark
  proving (a)/(b)/(c) and the per-key-vs-scandir cost, so the TTL lever is
  quantified without another GPU run.

## Constraints

- ONE live variable only; no source change; no profile/argv change; no new
  instrumentation beyond the frozen probe; no `/flush_cache`; no `/close_session`.
- <= 250 HTTP, <= 60 min live. Do not modify R121-R129 artifacts.
- GPU held only for the active run; release on completion.
