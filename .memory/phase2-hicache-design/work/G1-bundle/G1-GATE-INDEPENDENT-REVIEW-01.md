# G1 gate — independent adversarial review (reviewer-deep), 2026-09-12

Task: `G1-GATE-INDEPENDENT-REVIEW-20260912` (read-only; no artifact modified).
Target `sglang-3090-24g-opt` @ HEAD `4f41f5bab562b99562f30c67540eb05344d13637`.
Corpus `pattern/`+`testing/` verified byte-identical across `1953397`, `eb976d4`,
and current HEAD `1870ada`.

Reviewed revisions (sha256):
* intake `5a2db7c8b6662746dcb2d195c945612c6b38275af536fc78ada1983b6d1189a5`
* novel `72acb638a8ab6c34e53bd263f3612a271e2d7899c2702bf39582e0b93b4b6cbe`
* contract `211e9e2f8d6162c3afcb915df59e7b49f8ea2fb49b08991971ef7d4ec33962cc`

## VERDICT: BLOCKED (not safe to freeze as authority)

Three genuine crash-consistency holes remain: a reused/evicted-slot overwrite
before its invalidation is durable (reader-visible corruption); a tolerated torn
tail that is never truncated (store can become unrecoverable on the next restart);
and a group id that is a per-process counter reused as a durable id (partial
KV+sidecar groups can validate across restart).

## Defects

| id | sev | location | issue | evidence | required correction |
|---|---|---|---|---|---|
| D-01 | blocker | contract §4.3 steps 1-6, §8, §11; NM-INV-04/06/07; NM-F-03/11 | "data pwrite -> WAL -> fsync" overwrites live slots before their invalidation is durable, and the index lock is released (step 4) before the drop/generation bump (step 6) -> circular-reuse and GC-evicted slots can serve clobbered bytes; crash restores durable metadata for a key whose bytes were overwritten. §4.3 "orphan payload ... harmless" is false for reused slots. | `extent_file_backend.py:1153-1157`; `extent_allocator.py:223-226,180-181,288-303` | Write-ahead the durable invalidation: append+fsync `DROP_SLOT`+generation before the data pwrite clobbers any evicted/`passed` slot, or never reuse a live-durable slot before its drop is durable; do not expose reused slots to readers until the gen bump is applied; restate the failure model + add the crash/race oracle. |
| D-02 | blocker | contract §5; NM-INV-09; intake §3 TKV-CODE-026 | tolerated torn tail is recorded but never truncated/synced; resuming appends makes the partial frame interior corruption -> next restart fails closed (or seq gap) = single tolerated tail can make the store unrecoverable. | contract §5; `pattern/tikv.md:560-573` (TKV-CODE-026 requires truncate-to-verified + sync) | `ftruncate` active segment to last verified offset + `fsync` (or rotate to fresh segment) before resuming appends; add kill->reopen->write->kill->reopen oracle. |
| D-03 | blocker | contract §9; novel §4; NM-INV-08 | group id = `operation.id` = `StorageOperation.counter`, a per-process class counter reset to 0 at process start, promoted to durable `group_id` with `0=ungrouped`. (a) ids repeat across restarts while WAL persists -> `GROUP_COMMIT(G)` from run N validates an incomplete group with same G in run N+1; (b) first op id 0 is misclassified ungrouped. "No new identity is invented" is the defect. | `cache_controller.py:259,283-284`; contract §3:161, §9:416-419 | Mint a durable WAL-global unique group id (namespace epoch/run-id + per-run sequence), reserve 0; surface as an authority decision (changes the hybrid identity contract). |
| D-04 | major | contract §6 steps 1/5/6 + crash-window note | step 6 unlinks `.wal.<gen>` yet the crash-window note says records `seq > L` may be in the old segment -> if writers resume after step 1 and before step 5, unlinking gen loses ACKed writes; quiesce-barrier role never defined. | contract §6 | hold writers through step 6, or unlink only segments with `max_seq <= checkpoint_lsn`; define the barrier. |
| D-05 | major | contract §5 "derive + cross-check" | comparing post-replay bookkeeping against raw checkpoint values is wrong once WAL `> checkpoint_lsn` is folded in -> spurious fail-closed or re-interpretation. | contract §5 | compare against the post-replay derived fold. |
| D-06 | major | contract §11 vs §4.4 | `_write_gate` ("only writer at a time") unreconciled with group commit ("multiple writers share one fsync"): held -> no group; released -> undefined plan/pwrite ordering, worsens D-01. | contract §11/§4.4 | define exact concurrency/grouping contract incl. follower join without breaking reuse ordering. |
| D-07 | major | contract §8; NM-F-05/11 | "index unchanged" on failed group is false: `_gc_evict` mutates at step 1 and `plan` `passed` drops are known pre-failure; failed pwrite/fsync leaves RAM drops with no durable `DROP_SLOT` -> evicted keys reappear after reopen. | `extent_file_backend.py:1136-1137,1185`; `extent_allocator.py:244-256,288-303` | journal+fsync evictions before RAM mutation and roll back on failure, or apply RAM drops only after group durable; fix NM-F-05/11 wording. |
| D-08 | major | contract §9 | recovery gates grouped entries on `GROUP_COMMIT`, but live process installs KV entries at batch commit before `GROUP_COMMIT`; if `GROUP_COMMIT` fails, live process can serve a non-durably-complete group. | contract §4.3 step 6; §9; `cache_controller.py:1398-1407,1421` | define in-process rollback/no-serve on `GROUP_COMMIT` failure, or defer KV index install until group commit. |
| D-09 | minor | contract §3 component enum | enum has 6 values; `PoolName` has 13 (`DEEPSEEK_V4_*`, `DRAFT_INDEXER`, `DRAFT_SWA` -> `OTHER=255`); "does not silently rely on string-suffix parsing" holds only for 5 pools. | `hicache_storage.py:63-82` | extend enum or state the lossy mapping and why safe. |
| D-10 | minor | intake header/§12; §3 vs §6/§8 | intake `status: proposed` is not template-valid (`complete\|blocked`); with non-empty `blocking_gaps` should be `blocked`. `RP-RDB-036` cited in §6/§8 with no §3 disposition row. D6 listed open yet §12.1 #3 fixes its outcome. | `intake-template.md:19`; intake §3/§6/§8/§12.1/§15 | set `status: blocked`; add §3 row or NOT_ADOPTED justification; do not assert D6 before decided. |
| D-11 | minor | contract §4.2 frame CRC | listed header 26 bytes, crc at 22-25, but CRC range written `header[0..24) || payload` overlaps crc field (manifest header correctly `[0..12)`). | contract §4.2/§3 | fix to `header[0..22)` or correct layout. |

## Anchor errors

| id | sev | artifact claim | actual |
|---|---|---|---|
| A-01 | major | contract §1/§9/§10 cites `_t38c_durable_context` `hybrid_cache_controller.py:1128-1150`, sidecars `:1090-1094`, KV `:1142`, attach `:305-306,315-316`; `managers/cache_controller.py:726-770,835-858,1421`; "read directly at HEAD" | these match the DIRTY worktree, not HEAD. HEAD: `_t38c_durable_context` 1100-1116, sidecar `batch_set_v2` 1060, KV `super()._page_backup` 1108, attach 292/302; `cache_controller.py` detach 724, reset 833, ack 1419. Hybrid has +34 worktree lines (P2A telemetry); managers +2. `_t38c_operation_id` read is in backend `batch_set_v2:1008-1017`, not hybrid 1012-1017. Intake §1 omits `mem_cache/hybrid_cache/…` from the dirty set (a blast-radius file). Re-pin anchors to HEAD (or declare the dirty revision+digests) and fix the `_t38c_operation_id` citation. |
| A-02 | minor | over-broad corpus ranges `RP-RDB-014 :311-354`, `RP-RDB-017 :380-425`, `RP-RDB-034 :780-823`, `FDB-IMP-19 :370-407`; crash-matrix `:5-6` | tighten to actual card extents; open decision is `crash-matrix.md:8-9`. |

## Unsafe crash windows (exact interleavings)

* **W1 (D-01).** K@slot s ACKed gen=g, bytes+SET durable. New write: (1) `_gc_evict` evicts s / `plan` lists s in `passed`; (2) pwrite clobbers K's bytes at slot s; (3) SET appended; (4) lock released; (5a) crash before fsync -> reopen restores K (gen g, no `DROP_SLOT`), `lookup(K)` hit -> serves clobbered bytes; **or** (5b) no crash: a lock-free reader after (4) sees unchanged `_index[K]`, `verify` passes -> serves clobbered bytes.
* **W2 (D-02).** Crash mid-append to active gen; reopen tolerates tail but does not truncate; process resumes appending after partial bytes; crash again -> interior malformed frame -> fail-closed forever.
* **W3 (D-03).** Run 1: sidecar durable for group id 7, crash before `GROUP_COMMIT(7)`. Run 2 counter resets; unrelated later op also id 7 completes `GROUP_COMMIT(7)` -> recovery validates run-1 orphan sidecar.
* **W4 (D-03).** First `StorageOperation` of a run has id 0 -> `group_id=0` "ungrouped" -> never gated.
* **W5 (plausible, unconfirmed).** Crash during rotation before `.wal.current` replace can leave an orphan newer segment with a partial header; recovery never states how segments are enumerated or that unreachable invalid-header segments are ignored.

## Open decisions requiring user/orchestrator authority

* D1 allowed post-crash recovered prefix; D3 fail-closed vs salvage (both block terminal acceptance).
* D2 power-loss vs process-crash data durability (only if a power-loss claim is made).
* D4 sidecar ACK semantics.
* Novel-mechanism acceptance of `NM-EXTENT-RESTART-REBUILD-01` + an authority-manifest path to pin the intake.
* **NEW:** the durable group-id identity/epoch (D-03) changes the hybrid identity contract; currently silently asserted. D5/D6 remain lower-level.

## Correctly covered (do not redo)

Intake has all 12 sections + attestation; `NOVEL_MECHANISM` justified under
README §4; declaration `proposed`/`PENDING`; no false local coverage;
`test_crash_reopen_all_cold` = re-disposition required; E2E = expected-RED
honestly labeled unverified. Observed facts accurate (no header/checksum/fsync;
RAM-only state; `ExtentRef` 4-field; `plan` generation; `clear` keeps
generations; sidecars precede KV; `min`-folded `batch_exists_v2`). Most failure
oracles real (SIGKILL; file-boundary fault injection); fresh-slot durability
ordering sound; fail-closed interior corruption, atomic manifest publish,
generation monotonicity, no-scan recovery, reversibility seam, D1/D3 surfacing
correct. Corpus search record real.

## Required follow-ups

1. repair pass for D-01/D-02/D-03 + D-04..D-08 wording + D-09..D-11 + anchor re-pin;
2. obtain D1/D3 (and D2/D4 as applicable) + a group-id-epoch decision;
3. re-pin anchors to HEAD or declare the dirty revision;
4. re-review the corrected bundle.
