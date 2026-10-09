# E4 — Performance gate: extent + RAM index vs legacy FileBackend (R129)

```yaml
schema: phase2-hicache-e4-performance-1
artifact_id: E4-EXTENT-PERFORMANCE-20260912
task_id: PHASE2-E4-20260912
role: orchestrator (live measurement)
repo: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
head: 4f41f5bab562b99562f30c67540eb05344d13637
mode: live (extent server; GPU via flock; server stopped; lock released)
classification: MEASURED
```

## 0. Setup

- Server: `launch-e-20260912.sh`
  sha256 `d24195b9a66c832226d8956ac6c79c168fbc92c4b67de44c0e1485847ab3c651`
  (only argv delta vs frozen `launch-r112.sh`: `--hicache-storage-backend
  file` -> `extent`). Same 3090 profile, same probe ON
  (`SGLANG_P2A_TIMING_PROBE=1`), same workload driver as R129
  (`driver_e4.py`, byte-identical to `driver129.py`,
  sha256 `067904d048519e45aa58eb131f26e752a675548273440670984c0873b00af2f6`),
  same extraction (`extract_e4.py`, byte-identical to `extract129.py`,
  sha256 `89df4ad5157d6039da6206711bc52deafecc03dacfe1bd728e97902ac1f5b73c`).
- Live identity from `sglang-server-e.log`:
  `Creating storage backend 'extent'
  (sglang.srt.mem_cache.storage.extent.extent_file_backend.ExtentFileBackend)`
  and `ExtentFileBackend: file=.../l3-extent/hicache.data_-mnt-data-models-qwen35-gptq_0_1
  extent=64000000 B slots=4000 max_size=200000000000 min_free=20000000000`.
- L3 layout: **one** sparse data file (apparent 256 GB, physical ~11 GB live).
  Legacy `l3/` untouched (newest mtime 08:20:47, before E4; 3,314,758 files,
  133 GB).

## 1. Workload runs

| Run | State | Requests | Bad | Wall | Window sha256 |
| --- | --- | --- | --- | --- | --- |
| R129 | legacy `file` | 59 | 0 | 514 s | (frozen) `a19fed92…8132` |
| E4a | extent, cold-ish (first after start) | 59 | 0 | 47.3 s | `a44f2417a0674b0cc239bcdd2d28a029f71285348b04328adb576ddac2219edf` |
| E4b | extent, warm (repeat) | 59 | 0 | 19.1 s | `3eea39822609ff547e490647f5097d3649f7b4be2f68398f1287ecd2d392a1ac` |

Extracted JSON: `extracted-e4.json` `d55e0429e95eb5a8488fb1664c0b25f8a3964339201a36ac776ce81b627314c2`;
`extracted-e4b.json` `eb1323e56eb9ab5e27dac9270c12e9cec65bbc751c8a2e74333c05d92d0f1a65`.

## 2. Q3 — storage query latency (the metadata query)

| | R129 legacy | E4a extent | E4b extent |
| --- | --- | --- | --- |
| Q3 n | 27 | 61 | 50 |
| p50 | **17.777 s** | **2.616 ms** | 7.329 ms |
| p95 | — | 15.017 ms | 32.665 ms |
| p99 | 22.278 s | 30.279 ms | 40.628 ms |
| max | — | 33.286 ms | 46.118 ms |
| miss-path p50 | — | 2.392 ms (n=57) | 8.082 ms (n=6) |
| hit-path p50 | 4.207 ms (n=4) | 7.258 ms (n=44) |
| kv_hit_pages split | 25 miss / 2 hit | 57 miss / 4 hit | 44 hit / 6 miss |

**p50 improvement (miss path, the dominant R129 cost):**
17,777 ms -> 2.392 ms = **~7,430x**. Overall Q3 p50 (E4a) = **~6,796x**.
E4b's higher p50 is expected: 88 % of its queries are real L3 hits that perform
actual IO, and it is a warm repeat, not an independent cold run.

## 3. Q2 — L3 -> L2 stage (ready - prefetch_issue)

| | R129 legacy | E4a extent | E4b extent |
| --- | --- | --- | --- |
| n | 1 | 2 | 32 |
| p50 | 16.567 s | 304 ms | 445 ms |
| p95 | — | 421 ms | 821 ms |
| p99 | — | 431 ms | 832 ms |

R129's Q2 stage was `~92.6 %` query time; with the query collapsed, the stage
p50 falls to 304-445 ms. (A1: Q2 samples remain thin in the cold run; E4b's
n=32 is the stronger sample.)

## 4. Q1 — admission - enqueue (lead time)

| | R129 legacy | E4a extent | E4b extent |
| --- | --- | --- | --- |
| n | 27 | 28 | 55 |
| p50 | 1.694 s | 1.009 s | 590 ms |

Q1 is not directly storage-bound (it includes queue/compute lead), so its
improvement is smaller and consistent with the storage stage no longer
monopolizing the single prefetch thread.

## 5. L3 exercise and health (proves the path was real)

- `evt=extent_write`: 403.
- `evt=storage_hit_query`: 111 total; 48 with positive `kv_hit_pages`;
  `sum(kv_hit_pages) = 247,168`.
- `restore_success` 33; `restore_retry` 14; `ready_pool` 53.
- Probe overhead (ns): M1 p50 ~3.9 us, M2 p50 ~4.2 us, M3 p50 ~1.5 us;
  `over_1ms = 0`. The probe did not distort the measurement.
- v1-write -> v2-query round trip is exercised live (extent writes followed by
  positive v2 hit queries).

## 6. Result

The legacy full-directory `os.scandir` that produced 17.8 s/query is removed;
the RAM-index query path is O(1) per key and measured at low-single-digit
milliseconds. L3 stage and wall-clock both improve by >1 order of magnitude.
No correctness regression observed (0 bad requests across both runs).

Status: **PASS** for the E4 performance gate (measured). Restart-rebuild (G1)
remains out of scope and is an explicit open decision.
