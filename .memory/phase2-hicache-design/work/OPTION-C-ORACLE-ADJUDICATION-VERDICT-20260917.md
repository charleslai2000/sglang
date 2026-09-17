# Option-C oracle anomalies — independent adjudication (2026-09-17)

Reviewer-deep adjudication, CPU-only, repo read-only. **All four anomalies are
ORACLE ARTIFACTS (class A). No REAL defect was found in Option-C.**

This is the durable-blocker decision: Option-C is cleared to enter the final
production candidate, subject to the single final campaign (R4).

## Verdicts

**A1 — `oracle_generation` GEN-6 `no-permanent-pinning` -> ARTIFACT**
The check is `tail_ok = any(churn[-200:])`, i.e. it fails if the last 200 of 1200
writes all fail. In the fixture the file reaches 100% live utilisation with GC off,
so `plan_relocation` has no non-victim tail and the product correctly fails closed
(documented backpressure, REVIEW-PROTOCOL A3 / commit 63f7eff612). Deterministic
`successes=11/1200`. With reclamation headroom the same 1200 writes all pass
(`max_size=48Ki` -> 1200/1200). The frozen control "passes" only by deleting live
data. The success counter is therefore unrelated to pinning.

**A2 — `oracle_crash_matrix` CP1 `refs-reachable-bytes-exact` -> ARTIFACT**
`rec["bytes_ok"] = rec["sha256"] == info["sha256"]`, where `info` (the expected
sha) is captured at oracle_crash_matrix.py:79-87 **before** the trigger at :92,
while `data` is read after the cut. The cut restores only the WAL
(`restore_full_wal()` :307-310 truncates the WAL segment; the data file is left at
end-of-trigger), so the trigger's own later pwrite is visible under a pre-trigger
index. **Orchestrator-verified**: the `pre[]` snapshot loop (line 79) precedes the
trigger (line 92), and the only restore is WAL-only. Reproduced by the reviewer:
oracle-style (no data restore) -> `corrupted=['H_…','a_…']`; physically-correct
(data restored) -> `corrupted=[]`. The frame order `SET, BATCH_COMMIT, DROP_SLOT`
confirms the relocation commit precedes the drop.

**A3 — `oracle_no_capacity` `full/fragmented:victim-selected` INVALID -> ARTIFACT**
The oracle early-returns INVALID when `obs["victims"]` is empty
(oracle_no_capacity.py:59-60). In `build_nocapacity_scenario` all four cursors hold
16000 B (384 B free) and all 64 keys are live; relocation is infeasible **by
construction**, so the candidate can only fail closed. The oracle's early return
discards exactly the fail-closed evidence its own A2/A3 row wants. Direct checks of
the fail-closed invariants pass: index unchanged, generations unchanged,
0 lost / 0 corrupted of 64. The frozen control instead returned True and dropped 16
live refs — the candidate is strictly better, yet was recorded INVALID.

**A4 — `oracle_payload_bytes` `v1:victim-selected` INVALID -> ARTIFACT**
`build_v1_scenario` fills every slot with 40*1600 = 16000 live bytes in a 64000 B
file; the 41st page wraps into a slot with only 384 B of non-victim room ->
infeasible -> fail closed -> same empty-victim early return. The v1 surface itself
works (frozen control: `v1:victim-selected PASS victims=[0]`; reviewer's reachable
v1 case: victims `[0]`, `moved_non_victim: True`, bytes exact).

## New observations NOT reported by the oracles

* **N-1 (operational).** Once the extent file is genuinely full with GC disabled, the
  write path is permanently refused: relocation cannot use dead space and there is no
  fallback, so `batch_set`/`batch_set_v1` never recover without external space. This is
  contract-consistent (A3 fail-closed) and strictly safer than the frozen path, but it
  is unbounded backpressure with no telemetry or escalation. Owner decision + metric
  recommended. (Already registered as a post-launch capacity-operations item.)
* **N-2 (low).** `plan_relocation` counts only free tail at `_cursors`; dead holes
  behind a cursor are never reused, so backpressure triggers earlier than necessary.
  Conservative limitation, not a regression.
* **N-3 (perf).** `_relocate_reclaim_victims_locked` does synchronous
  `_pread_full` + `_pwritev` + `fdatasync` while holding the backend `_lock`,
  serializing readers. Lock order is consistent (no inversion).
* **N-4 (method gap).** The crash matrix never models data-file power loss, so its
  CP2/CP3 PASS is not probative for relocated destination bytes surviving a real
  crash. Not a demonstrated product defect — Option-C's WAL-fsync/data-pwrite ordering
  matches the existing write path — but the crash-matrix evidence is weaker than it
  looks. The reviewer's proposed per-cut data-file snapshot run is the one experiment
  that would close it; not required by the owner and not run.

## Not determined
* v1 relocation with mixed component lengths / multi-page v1 batches.
* A multi-victim (>1 per trigger) path: no reachable trigger in 900 randomized trials
  with the 4-slot fixture, so "multi-victim <=1 bump" is empirically, not statically,
  validated.

## Consequence for the main line
No product code change is required by this adjudication. Option-C may proceed to the
final production candidate. The single final campaign (owner R4) remains the gate:
Gate A/F1/F2 + native 128K Gate-B on the production-commit binary + short canary.
N-1 is a launch-operations item, not a blocker; N-4 is a known evidence limitation.
