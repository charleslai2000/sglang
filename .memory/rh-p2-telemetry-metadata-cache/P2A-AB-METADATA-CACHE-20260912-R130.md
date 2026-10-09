# P2-A R130 metadata-cache A/B — SUPERSEDED / BLOCKED (no valid A/B produced)

- task_id: `R130` (P2-A follow-up single-variable metadata-cache A/B)
- role: `tester` (private, independent verification)
- status: **blocked**
- ENTRY: `ACCEPT`
- outcome: the R130 live A/B is **SUPERSEDED by a user redirect** and the
  orchestrator is running a quarantine that SIGKILLs any legacy-l3 file-backend
  server. A valid A/B was **not** produced. Partial evidence is preserved and
  reported below, fail-closed.

## 0. One-line summary

The GPU was not free on arrival (a parallel E-track benchmark/server held the
`3090.lock`), and before the R130 A/B could be completed the user redirected the
program away from the legacy FileBackend and the orchestrator intervened. The
R130 server reached health twice but was externally killed each time (the second
kill is the orchestrator's documented quarantine); the workload that did run was
destroyed (3/59 HTTP 200). Consequently there is **no valid R130 Q1/Q2/Q3 A/B**.
I stopped all launches and did not fight the quarantine.

## 1. Contract hash re-verification (required first step)

| contract | expected sha256 | actual sha256 | match |
|---|---|---|---|
| `work/P2A-AB-METADATA-CACHE-CONTRACT-20260912.md` | `7b319b1bf7446d4772a50dd0888db1bce8c7c64babeb679dc5b283dfaaab2bb8` | `7b319b1bf7446d4772a50dd0888db1bce8c7c64babeb679dc5b283dfaaab2bb8` | **yes** |

The hash matched before any launch; the contract was followed until the
supersession was discovered.

## 2. Why this is blocked — supersession evidence (control plane, read-only)

While the server was loading, the orchestrator's control plane was updated. From
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/ledger.md`:

- **L2916–2930 — USER REDIRECT:** "STOP legacy FileBackend optimization; restore
  extent + RAM index". Explicitly: *"do NOT declare the problem solved by merely
  setting `SGLANG_HICACHE_FILE_BACKEND_ENABLE_METADATA_CACHE=1`"*. Action:
  "R130 live metadata-cache A/B is **SUPERSEDED/STOPPED**".
- **L2998–3002:** a STOP DIRECTIVE was sent to this tester subagent; "partial
  `work/R130-bundle/` evidence is preserved".
- **L3135–3148:** "R130 relaunch incident (3rd occurrence), quarantined" — a
  bounded 40-minute quarantine `/mnt/data/nerun-dev/tmp/r130-quarantine.sh`
  (`r130-quarantine.log`) SIGKILLs processes that are both
  `sglang.launch_server --hicache-storage-backend file` **and** have
  `SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR` ending `/l3`.
- Baseline re-designation: **E4a (extent + RAM index) is the new L3 baseline**;
  R129 legacy FileBackend figures are permanently marked scalability-failure
  evidence and excluded from production comparison.

This invocation's dispatch was the original R130 contract and did not itself
carry the stop directive; on discovering the control-plane supersession I stopped
all launches, did not relaunch again, and left the quarantine untouched.

## 3. GPU lock handling

- The lock was **not free** on arrival: `scripts/g2_gpu_benchmark.py`
  (PID 652227, unrelated task) then an E-track extent server held
  `/mnt/data/gpu/3090.lock`. Our launch script correctly waited on
  `flock -w 300 9` (never stole the lock, never killed the other workload).
- The R130 server was acquired **only via the frozen launch script**
  (`exec 9>/mnt/data/gpu/3090.lock; flock -w 300 9`). Confirmed the new server
  owned fd 9: `/proc/726289/fd/9 -> /mnt/data/gpu/3090.lock`; `fuser` listed
  only `726289` as lock holder.
- Server identity verified: PID `726289`
  (`python -B -m sglang.launch_server`), children helper `726641`,
  scheduler `726642`, detokenizer `726643`; `CUDA_VISIBLE_DEVICES` =
  `GPU-2e3ed202-3655-d919-0a64-259209bc6587`; target GPU held by 726289.
- argv = **59 tokens, byte-identical** to the R117/R129 freeze
  (`work/R117-profile/profile.json` `launch.argv`). Env toggle confirmed live:
  `SGLANG_HICACHE_FILE_BACKEND_ENABLE_METADATA_CACHE=1`,
  `SGLANG_P2A_TIMING_PROBE=1`, storage dir `.../l3`,
  `MAX_SIZE=200G`, `MIN_FREE_SPACE=20G`; `SGLANG_HICACHE_FILE_BACKEND_METADATA_TTL`
  unset → **effective TTL = 5.0 s**.
- After the orchestrator's SIGKILL, **no R130 process remains**. The lock is now
  held by the current P2-B0 extent server (PID `740195`) — not by R130.

## 4. Init / metadata-scan cost accounting (recorded, not hidden)

Real values from the three frozen file-backend launches (all `l3`,
`max_size=200G`, `min_free=20G`). The evictor scan runs in **both** arms; the
metadata pre-scan (`_scan_existing_files_to_metadata_cache`,
`hicache_storage.py:457`, `os.listdir` + suffix classify) runs **only** when the
cache is enabled.

| arm | lock_acquired | backend created | eviction enabled (evictor scan done) | fired up | health 200 | lock→health | create→evict.enabled | entries | existing bytes |
|---|---|---|---|---|---|---|---|---|---|
| **R129** (cache OFF) | 08:04:34 | 08:05:30 | 08:06:24 | 08:06:34 | 08:06:39 | **125 s** | **54 s** | 3,086,735 | 131,420,078,080 |
| R130 attempt-1 (cache ON) | 08:54:31 | 08:55:23 | 08:56:32 | 08:56:40 | 08:56:52 | **141 s** | **69 s** | 3,314,758 | 142,056,325,120 |
| R130 attempt-2 (cache ON) | 09:07:30 | 09:08:23 | 09:09:48 | 09:09:59 | 09:10:07 | **157 s** | **85 s** | 3,314,758 | 142,056,325,120 |

Reading: the ~54–85 s `create→eviction-enabled` window is dominated by the
evictor scan (`lru_file_evictor.py:298`: `os.listdir` + one `os.stat` per file +
sort) in both arms. The metadata pre-scan adds a variable ~15–31 s (the dir also
grew +228,023 files, ≈ +4 s of evictor stat cost by linear scaling). The metadata
scan is pure `listdir` + Python suffix classification + 3.31 M
`MetadataCache.add` (lock+dict) calls.

Independent CPU-only corroboration (separate coder, `work/R130-correctness/`,
real `l3/`, 3,314,758 entries): `os.listdir` = **3.687 s**;
`os.scandir`+classify = **4.70 s**; `os.path.exists` = **5.22 µs/key**;
`MetadataCache.contains` hot = **0.51 µs/key**, revalidate = **6.0 µs/key**.

Effective TTL: **5.0 s** (`environ.py:699`). Note `MetadataCache.add()` does
**not** refresh the timestamp and `contains()` does not refresh on hit, so TTL is
measured from first insertion (R130-correctness observation, `test_add_does_not_refresh_timestamp`).

## 5. The live workload run — INVALID (preserved as evidence)

- Driver: frozen `work/R129-bundle/driver129.py` `--run`, same defaults
  (N=8, TURNS=6, N_PRESSURE=6, same HIST_TARGETS), run dir
  `work/R130-bundle/run-20260912-091027/`.
- Outcome: **3 HTTP 200 / 56 HTTP `000`** (`http_bad=56`), run ended in 19.0 s.
  The server was SIGTERM'd at `09:10:31` (24 s after health) while serving the
  first cold request, and again at `09:10:41`; it exited at ~09:10:46. The
  orchestrator ledger records this as a deliberate SIGKILL (quarantine). The
  56 failures are **external interference, not a product defect**.

Partial markers in the measured window (`l3`-slice
`/mnt/data/nerun-dev/r130/window-754-41749.log`): M1=4, M2=4, M3=3,
admission.v2=3, ready_host=3. The extractor (`extract129.py`, same joins/buckets)
was run to `R130-bundle/extracted-partial.json`.

| metric (partial, n=3) | p50 | p95 | p99 | max | min |
|---|---|---|---|---|---|
| Q1 `admission−enqueue` | 5.840 s | 6.652 s | 6.725 s | 6.743 s | 5.003 s |
| Q2 `ready−issue` | 5.837 s | 6.650 s | 6.722 s | 6.740 s | 4.999 s |
| Q3 `storage_hit_query` | 1.348 s | 1.520 s | 1.535 s | 1.539 s | 1.024 s |
| Q3 `backend_lookup_ns` | 1.345 s | 1.517 s | 1.534 s | 1.537 s | 1.021 s |

**These numbers are NOT a valid A/B** (3 cold-only samples, 56/59 requests
failed, superseded run). They are retained only as diagnostic evidence.

### 5a. Methodological finding (important, and it invalidates "cold" semantics)

`driver129.py` derives prompt text deterministically from fixed seeds
(`make_text(0x1000+i*7, …)`, deltas `0x5000+i*131+t`); only the session/rid
nonce changes. Therefore the R130 "cold" prompts are **byte-identical to R129's**
and their pages were already in `l3` from the R129 run. This matches the observed
`existing=142,056,325,120 B (3,314,758 entries)` at R130 startup
(+228,023 files vs R129 startup, i.e. R129's own writes) and the orchestrator's
verification that `l3` was unmodified by R130 (newest mtime 08:20:47). So the
partial `kv_hit_pages` values (6016 / 7360 / 8576) are **hits on pre-existing
R129 data, not a live (a) "new write immediately queryable" proof**. A genuine
(a) live test would need a fresh, never-before-seen prefix.

## 6. Correctness

- **(a) new write immediately queryable — NOT proven live.** The R130 driver
  reuses R129 content, so no new-prefix write-and-query was exercised (see §5a).
- **(b) no false hit after eviction/GC — proven offline.** `work/R130-correctness/`
  (separate coder; superseded but retained): **23 tests, 0 failures, exit 0**;
  forced LRU eviction drops the stem via `on_evict`, TTL expiry fails closed then
  revalidates via `os.path.exists`, out-of-band delete is healed by `get()`
  `FileNotFound`, `clear()` empties files+index. No live eviction was triggered
  before the kill, so the live answer is "not observed".
- **(c) restart rebuild — proven offline; live NOT performed.** The server was
  killed before the planned restart test. Offline test
  `test_c_restart_rebuild_indexes_exact_stems` constructs the backend twice and
  confirms the index equals the expected matching-stem set.

## 7. TTL attribution of the partial Q3 residual

Mechanism (source-read + offline): with `metadata_cache` enabled and TTL = 5.0 s,
`_collect_existing_component_keys` replaces the O(#L3-files) `os.scandir` with
O(query_len) `MetadataCache.contains`; but because `add()` never refreshes the
timestamp, any key older than 5 s fails `contains`, is deleted, and is
revalidated with one `os.path.exists` (then re-added). So the residual is
**per-key TTL revalidation**, not a full RAM index and not a directory scan.

Partial live observation: 3 queries with `query_len` 6024/7420/8583 took
1.02/1.35/1.54 s (≈ 170 µs/key) — while the offline microbench predicts only
~6 µs/key for revalidation and ~0.5 µs/key hot. The live ~170 µs/key is **not
explained by the microbench**; a valid run is required to attribute it (likely
live IO/concurrency, not the scandir). I do **not** claim Q3 reached sub-ms.

## 8. Gate verdicts (fail-closed)

| gate | verdict |
|---|---|
| Q3 `storage_hit_query` < 1 ms (ideal <100 µs) | **NOT ESTABLISHED.** Partial p50 1.348 s (~13× better than R129's 17.777 s, but >1 s). |
| Q2 L3→L2 stage drops markedly | **NOT ESTABLISHED.** Partial n=3 only, invalid run. |
| No regression (same/better completed, all 200, restore correctness) | **FAIL (external):** 3/200 of 59; 56 `000`. Cause = orchestrator quarantine, not product. |
| Metadata build/init cost recorded separately | **DONE** (§4). |
| A/B valid | **ABSENT** (superseded). |

## 9. Answer to the posed final question

**Cannot be answered from R130.** Partial evidence is consistent with the
full-directory scan having been eliminated (cold-query Q3 fell from R129's
12.4–22.6 s to 1.0–1.5 s), but Q3 is **not sub-ms**, and no valid Q2 was
obtained, so the "17.8 s metadata-scan bottleneck" question is answered only at
the level of: the scandir is gone; a ~1 s (not sub-ms) per-query residual
remains in the metadata path. The user redirect (§2) has already ruled the
legacy FileBackend (including this metadata-cache lever) out of the production
path: **do not declare the problem solved by enabling the metadata cache**. The
current frontier is the extent + RAM-index track (E4a baseline, P2-B0).

## 10. Artifacts (bundle `work/R130-bundle/`)

| file | content |
|---|---|
| `run-context-prelaunch.txt` | pre-launch identity + contention notes |
| `lock-wait.log` | lock wait + relaunch trace |
| `attempt1-killed-at-0856.log` (+`.sha256`) | attempt-1 full server log (health then killed) |
| `run-partial-killed-at-0910.log` (+`.sha256`) | attempt-2 full server log (health, 3 requests, killed) |
| `run-20260912-091027/` | driver `state.jsonl` + `requests.jsonl` (3×200, 56×000) |
| `driver-run.out` | driver console |
| `extracted-partial.json` | partial Q1/Q2/Q3 extraction (invalid A/B) |
| `run-context-pre.txt` | pre/post line counts + wall times |
| `/mnt/data/nerun-dev/r130/window-754-41749.log` (+ window.sha256) | measured partial window bytes (outside workspace per AGENTS #10) |

Companion (separate coder, retained superseded): `work/R130-correctness/`
(`_r130_results.json`, 23/23 tests OK; microbench over real `l3`).

## 11. Follow-ups / open issues for the orchestrator

1. **R130 is closed by supersession** — do not expect R130 A/B numbers; plan.md
   already marks it STOPPED and P2-B0/E4a is the frontier.
2. If any metadata-cache evidence is ever wanted, it must be run under the new
   architecture decision and with a **fresh nonce-independent prompt set** so
   "cold" is genuinely new (driver reuses deterministic seeds).
3. Live `(a)`/`(c)` for the legacy path remain unexecuted; `(b)` is proven
   offline only.
4. The ~1 s live per-query residual vs ~6 µs/key offline is unexplained and
   should not be attributed without a valid run.
5. The quarantine window (`r130-quarantine.sh 2400`, started 09:10:46, ends
   ~09:50:46) is orchestrator-owned; I left it untouched.
