# Gate B PASS + F1 root cause located — state of play 2026-09-16 23:40Z

Cutoff 09:00 (2026-09-17). Owner's GREEN = exactly three: native 64K/128K perf, L3 restore correct hit,
restart recovery.

## 1. Gate B (native write-path A/B) — **PASS**, uncontaminated

Run `phase9-native-ab-20260916` (tester) finished; `REPORT.md` present. Verified against raw
`run/*/ctx*/cell.json` by the orchestrator, not just the summary.

| ctx | arm | aggregate | steady_all | plateau | gap (ms) | 100-290ms stalls | GPU util |
|---|---|---:|---:|---:|---:|---:|---:|
| 64K | L1-hot | 143.49 | 142.4 | 145.1 | 0.140 | 0 / 0.00 | 100.0 |
| 64K | Python (A) | 130.80 | 140.3 | 143.7 | 0.209 | 0 / 0.00 | 89.6 |
| 64K | **Native (B)** | 132.81 | 141.0 | 144.6 | 0.217 | 0 / 0.00 | 96.0 |
| 128K | L1-hot | 123.29 | 122.8 | 124.0 | 0.093 | 0 / 0.00 | 97.9 |
| 128K | Python (A) | 75.88 | 94.8 | 96.5 | **8.894** | **193 / 35.14 s** | **58.4** |
| 128K | **Native (B)** | 114.96 | 120.5 | 124.2 | **0.124** | **0 / 0.00** | **94.4** |

Ratios vs context-matched L1-hot: 64K agg 0.926 / plateau 0.997; 128K agg 0.932 / plateau 1.001 —
all >= 0.85. Absolute refs also met (64K >= 120.4 -> 132.81; 128K >= 104.2 -> 114.96).
Native 128K gap 0.124 ms vs Python 8.894 ms; stalls 0 vs 193.

**Contamination check (orchestrator):** every cell burst ended before the next lock owner took over —
last Native 128K burst ended 23:11:26Z, GGUF control acquired 23:12:04Z. **No cell overlapped another
owner.** Ratios are trustworthy.

Caveats reported, accepted as-is: (1) 128K write volume differs 24.32 GB (Native) vs 29.76 GB (Python),
−18%, so the stall reduction is *partially* confounded (but 0 stalls / 0.124 ms gap is not explained by
18%); 64K volumes identical at 10.648 GB. (2) v1.1's Python path no longer collapses at 64K (plateau
0.990) unlike v1 (73.5%) — the collapse is now 128K-only. (3) A/B cells restored from the **host** tier
(`tier_max.storage == 0`); a storage-tier *restore* was NOT exercised by the A/B workload -> Gate A's job.

Phase 0.1 no-regression: arm A 115 passed; arm B 111 passed + 4 known mock-shape failures. Phase 0.2 NEW
arm-B `DROP_SLOT`-before-reuse crash oracle: ordered -> old key MISS + stale ref fails `verify`; inverted
negative control -> old key present serving NEW bytes (corruption) => the positive assertion is sensitive
to ordering. **The DROP_SLOT BLOCKING-FOR-MERGE item now has real behavioural evidence, not code reading.**

## 2. F1 root cause — **LOCATED**, layer (A) storage false negative

Report: `/tmp/opencode/f1-restore-miss-20260916/F1-ROOT-CAUSE-REPORT-20260916.md`.

Trace order `storage key -> config_suffix -> namespace/epoch -> batch_exists* -> generation -> extent/ref
-> admission`: every stage TRUE until **`batch_exists`**. First true->false = presence of the FIRST queried
page key. `ExtentFileBackend.batch_exists` returns "number of consecutive existing keys **from the start**"
(first-absent index) and `_storage_hit_query` **breaks immediately** when it is short, so one absent head
page turns a 23,165/23,182-present chain into `storage_hit=0 miss_reason=miss`.

Mechanism: shared prompt-head pages are **write-once** (WAL `seq=1` writes only page 0 into slot 0; pages
1-2 `seq=4`; page 3 is written twice, `seq=29` then `seq=3735`). Later traffic matches the head in L1/L2
and never re-writes it, so the allocator's circular cursor wrap (`_plan_pure` -> `passed` -> `apply_drops`)
permanently destroys it when it recycles the oldest slot. Arithmetic closes exactly:
pre-restart runtime `storage_hit=23168` − post-drop replayed membership `23165` = **3 = pages 0,1,2**.
Offline execution of the frozen predicate: window from page 0 -> **0 hits**; same window from page 3 ->
**23165 hits**.

Layer (B) (`restore_potential=False`, `negative_cache_blocked=True`) is **strictly downstream** — the
pre-admission log shows `decision=issue reason=issued restore_potential=True` before the lookup, and the
park is armed by this very miss (`RestoreEvent.REVOKED_MISS`). `storage_generation=0` is a red herring:
global `l3_publish_epoch()`, documented diagnostic-only, never gates.

**Orchestrator independent re-verification** (frozen tree, read-only): `batch_exists` contract in
`hicache_storage.py`; the `hit_page_num < len(batch_hashes)` break and the
`host_indices[i*page_size : ...]` positional alignment in `cache_controller.py::_page_transfer` (proves a
gap-skip fix would misplace every page -> the fix must be on the durability side); `build_storage_backup_spec`
and its `prefix_keys[0]` head handle; `ExtentAllocator.lookup` generation gate. All match the report.

**Minimal fix chosen (owner-visible decision):** write-side head refresh in
`unified_tree_core.py::build_storage_backup_spec` — prepend the anchor chain head page (key + host slot +
token ids) when the matched prefix is non-empty, so the head is refreshed by ordinary traffic (16 KiB per
backup). Rejected: gap-tolerant `batch_exists` (position contract -> misplacement); head-aware recycling
(needs an unpin rule, pins accumulate, up to 64 MB/slot); `file_size >= working set` (only postpones).

## 3. Orchestrator action taken: premature Gate A stopped (disclosure)

Gate A gates were queued behind the lock and, when the GGUF chain released it at 23:33:35, a
`supervisor_gateA.sh` (pid 256185, 180-attempt loop) acquired the canonical lock and launched a server.
That run was **premature and policy-violating**:

* binding order puts Gate A **after** the F1 fix — running it unfixed can only yield INVALID;
* its script performed `clear` + `flush` on the **shared** `/data/l3/local-prod-v1.1`, forbidden by the
  frozen one-task/one-namespace policy (it unlinks the previous task's WAL);
* it held a **stale lock entry** pointing at a dead pid after the waiter was killed, plus an orphaned
  parentless server.

Stopped in order: supervisor first (prevents respawn), then the driver, then the server. Verified no
respawn (20 s), ports 30164/30000 free, GPU 0% / 4 MiB. **No `clear` had executed** — shared store mtimes
are 22:25/22:30, well before the 23:33 start.

**Evidence integrity confirmed after the action:** the preserved round-1 WAL
`pre-gate4-store/hicache.meta_..._wal.0` still hashes `b4f0498e34beeb7e881c5f98cc44d5835bbb1270fd08b1a5c9d720cc86f87835`
(+ `wal.current` `9a271f2a...`), matching the recorded identity. Nothing was destroyed.

## 4. Dispatched (both CPU-only, in parallel)

| task | owner | deliverable |
|---|---|---|
| `f1-minfix-20260916` | coder | minimal fix on a NEW candidate tree `/tmp/opencode/v1.1.2-f1fix-20260916/` + regression test that FAILS before / PASSES after + the three no-regression suites. Frozen trees untouched. |
| `final-gate-harness-20260916` | coder | corrected Gate A / Gate A-F1 / F2 harnesses in a NEW dir `phase9-gates-final-20260916/`: unique per-run store namespace (no shared clear), `sampling_seed` fix, fail-closed exit codes, storage-tier INVALID-vs-FAIL distinction, the NEW post-sweep cold-L1 F1 proof, and a genuine F2 restart (new process + new lock lifecycle + new namespace). Scripts only — no GPU run. |

## 5. Next (binding order)

`F1 minimal fix` (running) -> independent review of fix + root cause -> one GPU campaign
(`Gate A >=64K` + `Gate A-F1` proof on `64K and 128K`) -> `F2` real restart -> production verdict.

**Open decision for the owner:** the F1 fix changes `unified_tree_core.py` in the frozen production
artifact, so GREEN will require a **new frozen identity** (v1.1.2 candidate) with a new
`manifest/TREE-SHA256.txt`, launcher re-pin, and a fresh tree digest. The fix, its review, and its GPU
proof can proceed without that decision; only the final freeze/promotion needs it.

## 6. Not touched (deferred lines)

GGUF/norm fold line finished its control run and confirms the known M3/M4 degeneracy (M1 coherent:
greedy640 `loop_w4` 0.0663 / stops on EOS; M3 1.0, M4 0.965-0.994, neither stops on EOS). This is the
**deferred** line and is excluded from M1's production identity — no action taken.
