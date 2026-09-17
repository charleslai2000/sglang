# F1 Option A — bound proof came back NEGATIVE; the pre-approved path is closed by its own gate

2026-09-17 00:31Z. Cutoff 09:00 (~8.5 h). Owner ruling honoured: **no source change was made**, STEP 2
never started, GPU untouched.

## 1. Result

`f1-optionA-anchorrun-20260916` (coder): **UNAVAILABLE** — the anchor run is **NOT structurally bounded**.
Per the owner's gate ("if it grows with session prefix/context: STOP Option A, implement nothing"), the
work stopped before any edit. Authoritative tree: **none**; changed-file list vs frozen: **empty**;
frozen tree verified unmodified (`find ... -newermt '2026-09-17 00:00'` = 0).

## 2. Mechanism (why those pages are never rewritten) — cited

* `build_storage_backup_spec` (`unified_tree_core.py:2062-2087`) writes **only the target node's own
  pages**; ancestors appear solely as `prefix_keys` metadata, never bytes.
* `collect_storage_gap` (`:2089-2109`) collects only `not node.storage_written` and **stops at the first
  `storage_persisted` node**; `mark_storage_written` (`:2111-2113`) is the dedupe guard, so **once written
  a node is never re-collected**.
* Matched **L1/L2** pages are excluded from the backup span (`unified_radix_cache:1095-1109, 1985-2010`).
* The only path that re-enables a write is **delete-then-reinsert**
  (`drop_subtree_no_host` / `drop_device_leaf_to_miss`, invoked `unified_radix_cache:3125-3191`);
  demotion/hollowing keeps `storage_written`.

=> A page is **write-once** exactly while it stays continuously matched. The "anchor run" is therefore the
**continuously-resident leading prefix**, and there is no periodic re-entry mechanism to bound it.

## 3. The bound: O(context), not a constant

Executable demo on a real `UnifiedRadixCache`/`UnifiedTreeCore` + real `ExtentFileBackend` + real
`batch_exists` (`bound_demo.json`):

| chain pages | leading never-rewritten run | fraction of chain | `batch_exists` from page 0 after head-slot recycle |
|---:|---:|---:|---:|
| 6 | 6 | 1.0 | 0 |
| 12 | 12 | 1.0 | 0 |
| 24 | 24 | 1.0 | 0 |
| 48 | 48 | 1.0 | 0 |

Linear, unbounded in the model's terms. For the owner's stated scenario (a **64K→128K reused** session whose
prefix stays resident) the run is the **whole prefix** => refreshing "every anchor page" is **O(context)**
and is forbidden by the owner's rule.

## 4. Empirical counter-data, and why it does NOT bound the run

Preserved WAL write-count history (`analyze_wal.log`):
`write-once prefix length from page0: 3`; pages 0,1,2 written once (`seq 1`, `seq 4`), **pages 3..23167 all
written twice**; histogram `{1: 3, 2: 23165}`; `total pages with >=1 write: 23168 of 23183`.

So the incident's run was only **3 pages**. This does **not** refute the O(context) conclusion: those 3
pages are the depth that stayed *continuously matched*, and pages 3+ were written twice precisely because
they were evicted and re-inserted (the round-2 re-entry at `seq 3735-3784`). Run size is set by the
**continuously-resident prefix depth**, which for a reused long session is large (device pool 65536 tokens;
host tier measured in GB) — i.e. capacity/workload-dependent, **not** a structural constant.

Honest characterisation: the *structural* answer is unbounded; the *observed* instance happened to be 3.
The owner's rule is about structural boundedness, so the negative result stands.

## 5. Consequence — an owner decision is genuinely required

* **Option A (write-side anchor refresh): CLOSED** by its own bound gate. Not implemented.
* **Option B (head-aware recycling / permanent pinning): excluded by the owner** ("not permanent
  pinning") and it has the pin-accumulation problem (slot-granular => pins the whole 64 MiB slot; unique
  heads accumulate until live data must itself be evicted, which is not a correctness fix).
* **Option C (owner pre-named fallback) — live-ref relocation/compaction on extent-slot reclaim:** move
  the live refs out of a slot *before* the slot generation bump, inside the existing group-commit
  ordering. This is the principled fix and, notably, its cost is **bounded by the slot size (<= 64 MiB)
  per reclaim event, not by chain length** — i.e. structurally bounded, unlike A. It is a **new mechanism**
  touching the allocator's reclaim path, ref rewriting, generation accounting and durability ordering, so
  per the owner it needs **fresh authorization/design**, plus its own durability review.

## 6. State

* F1 = still **OPEN**; Gate A = still blocked (last run stands as **VALID INVALID / pre-fix baseline** only).
* GPU **0 % / 1-4 MiB**, no servers, ports 30000/30164/30199 free, canonical lock `free` (untouched).
* Nothing dispatched on the basis of this result; awaiting the owner's decision on Option C vs
  `PRODUCTION BLOCKED`.
