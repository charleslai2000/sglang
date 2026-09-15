# E-phase closure — extent + RAM-index L3 restored and measured

```yaml
schema: phase2-hicache-e-closure-1
artifact_id: E-PHASE-CLOSURE-20260912
task_id: PHASE2-E-CLOSURE-20260912
role: orchestrator
repo: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
head: 4f41f5bab562b99562f30c67540eb05344d13637
verdict: VERIFIED (E0 audit, E1 freeze, E2 deployment, E3 unit, E4 measured)
```

This closes the user-directed phase E0->E4 and answers the three required
questions. It binds every artifact by content sha256 and records the accepted
limits explicitly. No fabricated PASS: E3-live sidecar/restart checks are
unit-covered (stated), and G1 remains an open user decision.

## Q1 — Why R129 fell back to the 3M-small-file path

**Deployment selection, not a missing capability.** The launch profile's argv
contains `--hicache-storage-backend file` (`launch-r112.sh`), which the registry
maps to `HiCacheFile` (`backend_factory.py:197-199`); the live log confirms
`Creating storage backend 'file' (...HiCacheFile)`. `HiCacheFile` then:

1. uses `SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=$D/l3` (`hicache_storage.py:373`);
2. builds its metadata cache only if
   `SGLANG_HICACHE_FILE_BACKEND_ENABLE_METADATA_CACHE` is true —
   **default False** (`environ.py:697`), so `metadata_cache=None`
   (`hicache_storage.py:423`);
3. therefore takes the `os.scandir(self.file_path)` branch on **every** query
   (`hicache_storage.py:589-606`), enumerating **3,314,758 files / 133 GB**;
4. stores one `.bin` per key, and with `page_size = 1` every token page is its
   own file — hence the "3M small files" pathology.

Measured consequence (R129): Q3 storage query p50 **17.777 s**, p99 22.278 s,
`backend_lookup` ~100 % of the stage. This is recorded as a **legacy FileBackend
scalability failure, not a production baseline and not a Ready-Horizon defect.**

## Q2 — What `ExtentFileBackend` still lacks for production L3

Already complete: the full `HiCacheStorage` surface, a RAM-authoritative
`ExtentAllocator` index (dict + generation check), no `os.scandir`/`os.listdir`
anywhere, O(1)/batch lookup, generation invalidation, write-ACK atomic
visibility (`plan` -> pwrite -> `commit`), preallocated sparse extent file,
batched `preadv`/`pwritev`, lazy watermark GC, fail-closed malformed/stale
handling.

Remaining gaps, honestly:

| Id | Gap | Status |
| --- | --- | --- |
| G1 | **No metadata persistence / restart rebuild.** Restart starts cold; the on-disk bytes survive but are unreachable. | **OPEN — explicit user decision.** Not required for this phase; any fix is a NON-EXEMPT product change needing a full Pattern Intake + Novel Mechanism gate. |
| G2 | Default sizing (`extent` 64 MiB, `file_size` 64 GiB, `storage_dir=/tmp/hicache`) is wrong for a 133 GB workload. | **ADDRESSED** by E2 deployment config (256 G file, 64 M extent, 200 G max, 20 G min-free, new dir). |
| G3 | `get_stats()` deliberately returns `None`; counters only via `stats_snapshot()`. | Observability limitation; no engine metrics without a probe. |
| G4 | One data file per rank/`config_suffix`. | Fine for the frozen TP=1 profile; a multi-rank topology gets one file per rank. |
| G5 | No on-disk integrity verification. | Accepted under cache semantics (read mismatch -> miss). |

## Q3 — Measured improvement once extent + RAM index is restored

Same profile, same driver, only the backend selection changed
(`file` -> `extent`). Same workload shape (N=8 sessions, TURNS=6, 59 requests).

| Metric | R129 legacy | E4a extent (cold-ish) | E4b extent (warm) |
| --- | --- | --- | --- |
| Storage query Q3 p50 | 17.777 s | **2.616 ms** | 7.329 ms |
| Q3 miss-path p50 | — | **2.392 ms** | 8.082 ms |
| L3 -> L2 stage Q2 p50 | 16.567 s (n=1) | 304 ms (n=2) | 445 ms (n=32) |
| Admission Q1 p50 | 1.694 s | 1.009 s | 590 ms |
| Wall clock (59 req) | 514 s | 47.3 s | 19.1 s |
| Bad requests | 0 | 0 | 0 |
| L3 layout | 3,314,758 files / 133 GB | 1 sparse file, ~11 GB live | same |

**Query improvement: ~6,796x (p50 overall) / ~7,430x (p50 miss path).**
**L3 stage: ~37-54x faster p50. Wall clock: ~10.9x colder / ~26.9x warm.**
L3 was genuinely exercised: 403 extent writes, 48 positive-hit queries,
247,168 pages staged, 33 restore_success.

## Artifact manifest (content sha256)

| Artifact | sha256 |
| --- | --- |
| `work/E0-BACKEND-IDENTITY-AUDIT-20260912.md` | `e3a610b07466cadf42d38dc3506be24528d863bc659feb61eed6b4719e61e341` |
| `work/E1-EXTENT-L3-ARCHITECTURE-FREEZE-20260912.md` | `156c71402e094c1d5d99fd675f026ab692df94fca997e3afea4141a2c3e8ceed` |
| `work/E2-EXTENT-DEPLOYMENT-20260912.md` | `0613d99a62fccfa9f14c4d7fa2c2f41d2f67d524a5838c0c5ac1ad4ffc581c72` |
| `work/E4-EXTENT-PERFORMANCE-20260912.md` | `056700644ef352900ad06bc4e3889eb9b786aa3415421a5a2410b94c0c01754a` |
| `launch-e-20260912.sh` | `d24195b9a66c832226d8956ac6c79c168fbc92c4b67de44c0e1485847ab3c651` |
| E3 unit log `/mnt/data/nerun-dev/e3/e3-extent-unit.log` | `90110253c66b3f064d9c947cb785b7da2b0eadd404a4dca7711472086b850a6e` |
| E4a window `/mnt/data/nerun-dev/e4/window-e4.log` | `a44f2417a0674b0cc239bcdd2d28a029f71285348b04328adb576ddac2219edf` |
| E4b window `/mnt/data/nerun-dev/e4/window-e4b.log` | `3eea39822609ff547e490647f5097d3649f7b4be2f68398f1287ecd2d392a1ac` |
| `extracted-e4.json` | `d55e0429e95eb5a8488fb1664c0b25f8a3964339201a36ac776ce81b627314c2` |
| `extracted-e4b.json` | `eb1323e56eb9ab5e27dac9270c12e9cec65bbc751c8a2e74333c05d92d0f1a65` |

## Accepted limits / non-claims

- E4a Q2 n=2 is thin; E4b Q2 n=32 is the stronger stage sample but is warm.
- E4b is a warm repeat (not an independent restart); no cold-restart live run
  was performed (G1).
- Sidecar component-key isolation and restart-cold were verified by the CPU
  unit suite, not re-created live.
- Server was stopped and the GPU lock released after E4.

Status: E-phase **VERIFIED**; G1 (restart rebuild) is the only open
architecture decision and requires user authority.
