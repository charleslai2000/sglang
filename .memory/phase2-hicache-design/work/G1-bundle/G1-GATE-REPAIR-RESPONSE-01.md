ENTRY: ACCEPT

# G1 gate — repair response 01 (REPAIR R1) + R2 addendum (REPAIR R2) + R3 addendum (REPAIR R3)

```yaml
schema_version: 1.0.0-proposed
task_id: G1-RESTART-REBUILD-DESIGN-GATE-REPAIR-20260912 (continuation of
  G1-RESTART-REBUILD-DESIGN-GATE-20260912)
responds_to: G1-GATE-INDEPENDENT-REVIEW-01.md (verdict BLOCKED; D-01..D-11, A-01, A-02, W1..W5)
  for R1; G1-GATE-INDEPENDENT-REREVIEW-01.md (NEW-1..NEW-10, section 0.2, W5) for R2;
  G1-GATE-INDEPENDENT-REREVIEW-R2-01.md (NEW-11, NEW-12, hardening, minor residuals) for R3
repair_revision: R3 (R1 sections 1-6 retained; R2 appended as sections 7-12; R3 appended as
  sections 13-17)
design_only: true
product_test_storage_files_modified: none
classification: NOVEL_MECHANISM (unchanged)
novel_status: accepted:USER-RULING-20260912-G1 (not self-approved)
intake_status: complete
user_ruling: USER-RULING-20260912-G1 (2026-09-12; D1=(b), D3=(a), D7=(a) decided; defaults
  D2=(a), D4=(b), D5=(a), D6=(a) accepted; novel declaration NM-EXTENT-RESTART-REBUILD-01
  accepted with frozen scope only; implementation authorized for the design-target paths)
```

This file is the consolidated mapping required by the repair dispatch. Per-artifact Appendix A
tables repeat the subset relevant to each artifact.

## 1. Defect-response table

| review id | sev | status | exact textual fix (artifact / section) |
|---|---|---|---|
| D-01 | blocker | **fixed** | contract §4.3 (new steps 1-2 write-ahead invalidation; no-clobber rule; removed the false "orphan payload ... harmless" claim), §7, §8, §9, §10; novel `NM-INV-16` + `NM-F-15/16`; intake §3 hazard rows, §7 gap, §8 rows/`TR-NEG-16` |
| D-02 | blocker | **fixed** | contract §4.3 ("D-02 tail repair"), §5 (replay `ftruncate(last_valid_offset)` + `fdatasync` before any append); the R1 "or rotate/abandon" alternative is **withdrawn in R2** (NEW-2) in favour of in-place repair only; novel `NM-INV-17` + `NM-F-17`; intake §3 TKV-CODE-026 row, §5 tail analogue, §7 `NM-INV-17` |
| D-03 | blocker | **fixed (design) / needs-decision** | contract §4.0 new `(namespace_epoch, group_seq)`, `(0,0)` reserved, epoch-scoped completion, per-run re-mint persisted in manifest; §3 payload `namespace_epoch`; §9 group identity; §15 decision **D7**; novel `NM-INV-18` + `NM-F-18/19` + §4 ownership/identity row + §11 `NM-R-04`; intake §1 gap, §7 gap, §8 row |
| D-04 | major | **fixed** | contract §6: `checkpoint()` holds `_write_gate` exclusively through unlink; alternate safe rule "unlink only segments with `max_seq <= checkpoint_lsn`"; crash-window note updated; `NM-INV-11` |
| D-05 | major | **fixed** | contract §5 derive+cross-check: replay maintains an `expected` fold from the checkpoint and applies the same transitions; derived bookkeeping is compared to the **post-replay fold**, exact equality, not raw checkpoint values |
| D-06 | major | **fixed** | contract §4.3 lead-in + §11: `_write_gate` is the leader **sequencer**; group formation happens under it; only the leader plans/pwrites/applies; followers submit and wait; D-01 ordering preserved across the whole group |
| D-07 | major | **fixed** | contract §4.3 "D-07 (failed group)": RAM drops applied only after their `DROP_SLOT` is durable; on later failure no new entries install and the durable drops remain; `NM-F-05/11` wording changed from "index unchanged" to "durable prefix" |
| D-08 | major | **fixed** | contract §4.3 "D-08": grouped KV/sidecar entries are not installed/visible until `GROUP_COMMIT` is durable; on failure they are discarded and the operation fails; `NM-INV-08` extended to the live process; novel `NM-F-10` |
| D-09 | minor | **fixed** | contract §3.1 full 13-value component enum (`DEEPSEEK_V4_*`, `DRAFT_*`) with `OTHER=255` reserved, derived from `PoolName` value not key-suffix parsing |
| D-10 | minor | **fixed** | intake header `status: blocked`; intake §3 adds the RP-RDB-036 disposition row; contract §12.1 #3 no longer asserts a D6 outcome (defers to decision D6) |
| D-11 | minor | **fixed** | contract §4.2 explicit frame layout with CRC at bytes 22-25 and checksummed range `header[0..22)` |
| A-01 | major | **fixed** | contract §0.1 new "Inspected revision" section with per-file worktree digests (`hybrid_cache_controller.py` `64e933f4…`, `cache_controller.py` `a41e623a…`) and a corrected HEAD-vs-worktree anchor table; `_t38c_operation_id` corrected to **set in hybrid** HEAD `:837`/`:880` and **read in backend** `extent_file_backend.py:989`/`:1012`; `mem_cache/hybrid_cache/…` added to the dirty/blast-radius set (contract §13, intake header/§1); novel §1/§7/§9 |
| A-02 | minor | **fixed** | intake §3 anchors tightened: `RP-RDB-014 :311-332`, `RP-RDB-017 :380-401`, `RP-RDB-034 :780-801`, `FDB-IMP-19 :370-388`; open decision cited at `testing/rocksdb/crash-matrix.md:8-9` (and `restart-recovery.md:8-9`) in contract §15 D1 and intake §7 |

No review id is rejected. No applicable finding was silently dropped.

## 2. Unsafe-crash-window response (W1..W5)

| window | resolution | where |
|---|---|---|
| W1 5a (crash before fsync, reuse clobber) | `DROP_SLOT`+`fdatasync` and the RAM drop precede the pwrite; a crash before the fsync leaves the old entry valid and unclobbered (no pwrite yet); after the fsync recovery drops it; no false ACK. Oracle `NM-F-15`. | contract §4.3 step 2, §4.3 consequences, §12; novel `NM-F-15` |
| W1 5b (no crash, concurrent reader) | RAM invalidation (index removal + generation bump) is applied **before** the pwrite; a reader that snapshotted the old ref fails `verify` under `_lock` and its bytes are discarded. Oracle `NM-F-16`. | contract §4.3 step 2 + consequence bullet; novel `NM-F-16` |
| W2 (tolerated tail then append) | On replay the active segment is `ftruncate`d **in place** to the last verified offset and `fdatasync`ed **before any append**; rotate/abandon is withdrawn (R2-NEW-2); next `seq = last_valid_seq+1`. Oracle `NM-F-17` (kill->reopen->write->kill->reopen). | contract §4.3 "D-02", §5; novel `NM-INV-17`/`NM-F-17` |
| W3 (cross-run group-id reuse) | Per-run `namespace_epoch` + `group_seq`; `GROUP_COMMIT(E,S)` only completes same-epoch entries; a prior-run incomplete group is discarded. Oracle `NM-F-18`. | contract §4.0/§9; novel `NM-INV-18`/`NM-F-18`; decision D7 |
| W4 (first op id 0 = ungrouped) | `(0,0)` is reserved; a real group always has a non-zero epoch and `seq >= 1`. Oracle `NM-F-19`. | contract §4.0; novel `NM-F-19` |
| W5 (orphan newer segment, partial header) | Segment enumeration is explicit from `.wal.current`; an orphan/newer segment with an invalid/partial header is never treated as active and is reported; if referenced it fails closed. Oracle `NM-F-20`. | contract §5 table + §16 R7; novel `NM-F-20` |

## 3. Exact durable-ACK ordering after D-01/D-07 (short pseudocode)

> Historical R1 pseudocode. It is superseded for generation and commit semantics by the R2 final
> pseudocode in §8 (NEW-1 formula, NEW-4 install-only `commit_install`); the durable-ACK ordering
> itself is unchanged.

```text
WRITE (leader holds _write_gate; group members handled in arrival order):
  1  under _lock: select_gc_victims() [PURE]; plan(pending_drops) -> refs, reused[]
  2  if reused != {}:
         append DROP_SLOT(slot, pending_gen[slot]) for each reused slot
         fdatasync(WAL)                        # invalidation durable, BEFORE clobber
         under _lock: apply RAM drops (remove keys, gen=pending_gen, cursor=0, bytes=0)
  3  pwritev data bytes for all members        # safe: every clobbered slot invalidated
  4  append SET... + BATCH_COMMIT (+ GROUP_COMMIT if grouped)
  5  fdatasync(WAL)                            # data-plan durable
  6  under _lock: install entries             # grouped members only after (5)
  7  return ACK; release _write_gate
```

Failure at (3)/(5): no new entries install and no ACK; durable `DROP_SLOT`s from (2) stay in
effect (the index equals the durable prefix). Failure of `GROUP_COMMIT` at (4)/(5): staged grouped
members are discarded, nothing visible, operation fails.

Cost bound: one fsync on a reuse-free write; two fsyncs only when a slot is reused/evicted; each
fsync is shared across the bounded group-commit group.

## 4. New / changed open decisions requiring user or orchestrator authority

| id | decision | owner | gate consequence |
|---|---|---|---|
| **D7 (NEW, from D-03)** | durable group-id identity/epoch: per-run random `namespace_epoch` + `group_seq` with `(0,0)` reserved (proposed) vs a persisted monotonic `run_seq` vs another hybrid identity contract | user + orchestrator | **BLOCKED** until decided; changes the hybrid KV+sidecar identity contract |
| D1 | allowed post-crash recovered prefix | user + orchestrator | BLOCKED |
| D3 | fail-closed vs salvage for corrupt manifest/WAL | user + orchestrator | BLOCKED |
| D2 | power-loss vs process-crash data durability | user/orchestrator (if a power-loss claim is made) | non_blocking for the kill/reopen claim |
| D4 | sidecar ACK semantics | user/orchestrator | non_blocking; D-08 default assumes deferred visibility |
| D6 | metadata IO accounting | user/orchestrator | non_blocking; re-dispositioned tests must not assert it first |

## 5. Review findings believed factually wrong

None rejected. One clarification (not a dispute): the review's A-01 text gives `_t38c_operation_id`
set lines as "around 851/899"; those are the dirty-worktree lines, while HEAD is `:837`/`:880`.
Both are recorded in contract §0.1 so either revision can be audited. The substantive correction
(the read is in the backend `batch_set_v2`, not in the hybrid file) is accepted and applied.

## 6. Boundary

REPAIR R1 is a design-only proposal. It does not approve implementation, the novel mechanism,
D1/D3/D7 (or D2/D4/D6), repin, tests, evidence, coverage, commit, or merge. It must be re-reviewed
by an independent reviewer before any acceptance.

---

## 7. R2 defect-response table (re-review NEW-1..NEW-10, §0.2, W5)

| review id | sev | status | exact textual fix (artifact / section) |
|---|---|---|---|
| NEW-1 | major | **fixed** (superseded by R3 unified form in §13/§14) | contract §4.3 step-1 NEW-1 formula (`base[s] = pending_gen[s] if s in pending_drops else _generations[s]`; `ref.gen = base[s]+passed.count(s)`; `pending_gen[s] = _generations[s]+(passed.count(s) if s in passed else 1)`; `DROP_SLOT.new_gen == pending_gen[s]`), §7 NEW-1 paragraph, §8 `plan` row; novel `NM-INV-19`, `NM-F-21`. §4.3 step 1, §7, §8 now state the same formula. |
| NEW-2 | major | **fixed (option (a))** | contract §4.3 "D-02" deletes rotate-and-abandon and mandates in-place `ftruncate(active_fd, last_valid_offset)` + `fdatasync`; §5 replay and tolerated-vs-fail-closed table; novel `NM-INV-17`/`NM-F-17` reworded. Chosen because it is the only option that leaves no torn frame in a non-active segment (option (b) and (c) leave probabilistic/interior-corruption windows; see §9). |
| NEW-3 | major | **fixed** | contract §5 derive+cross-check: the `expected` fold applies a `SET` only when its batch is complete **and**, if grouped, its group is COMPLETE — identical to the install predicate; a staged-but-discarded `SET` is never folded (otherwise a valid WAL ending in an incomplete group spuriously FAILS CLOSED). |
| NEW-4 | moderate | **fixed** | contract §4.3 "NEW-4" + step 6 install-only; §8; §10 hook rows: `ExtentAllocator.plan` (pure) -> `apply_drops(drop_events)` (bump+remove, once, after the D-02 fsync) -> `commit_install(keys, refs)` (install-only). Old `commit(keys, refs, passed)` retained as the gate-off composition shim. Prevents the double generation bump at `extent_allocator.py:223-226` vs `:234`. novel `NM-F-21`. |
| NEW-5 | moderate | **fixed** | contract §4.3 CLEAR note, §6 `CLEAR` paragraph, §8 clear row, §10 clear row: `clear()`/detach/reset acquire `_write_gate` before appending `CLEAR`; `clear()` is quiescent-only and `CLEAR` can never land between a group's `BATCH_COMMIT` and `GROUP_COMMIT`. |
| NEW-6 | hygiene | **fixed** | contract §2 fence rule: `fcntl.flock(fd, LOCK_EX)` (with `LOCK_NB` -> typed `FenceError`, kernel auto-release on death, leftover zero-length lock file is safe and reused). The `O_CREAT|O_EXCL` alternative is dropped (not auto-released -> stale-lock hazard). novel §4 single-writer row. |
| NEW-7 | hygiene | **fixed** | intake §3: the duplicated RP-RDB-036 row (former lines 203 and 241) merged into one row covering `NM-INV-16,17; NM-F-11,13`, ADAPT, `TR-NEG-16, TR-RR-12`. |
| NEW-8 | hygiene | **fixed** | novel `NM-F-15` boundary reworded: kill points are step 3 (data pwrite), step 4 (WAL append), step 5 (data-plan fsync) — i.e. **after** the step-2 invalidation `fdatasync` has made `DROP_SLOT(K)` durable; expectation is "K absent" (or present-and-unclobbered only if the kill landed before step 2). |
| NEW-9 | hygiene | **fixed** | contract §9 and novel §4/§7: the **backend** is the sole owner/allotor of `group_seq` via `open_group()`/`commit_group()` under the `_write_gate` writer sequencer; the hybrid controller never mints an id and never reuses `operation.id`. Contract §9 and novel §4 now agree. |
| NEW-10 | hygiene | **rejected-with-reason (factually wrong)** | `os.open` is at `extent_file_backend.py:368` and `os.ftruncate` at `:370` at HEAD `4f41f5ba…` **and** in the clean worktree (grep both). The re-review's "`os.open` at 369 / `os.ftruncate` at 371" is off by one; the existing `:368-370` range was correct. Contract §0 now cites the two explicit anchors \(:368`, `:370`. No artifact change was required for correctness; the citation was made explicit. |
| §0.2 | hygiene | **fixed** | contract §0.2 replaced: the `_component_key` `bytes`/`str` claim is refuted (`PoolName.__str__` returns `self.value` at `hicache_storage.py:84-85`; `f"{key}.{pool_name}"` is `str`; `_storage_key` returns `str` at `:383-389`), so it is withdrawn; the semicolon multi-statement patch-block claim has no file/anchor/oracle in the bundle and is withdrawn. No open implementation-phase item remains. |
| W5 | hygiene | **fixed** | contract §5 recovery enumeration rule: no directory traversal — recovery reads the manifest floor `wal_floor` and `.wal.current` (`G_active`) and opens the contiguous exactly-named range `[wal_floor, G_active]`; every in-range generation must exist with a valid header (missing/malformed -> FAIL CLOSED); at most one bounded `stat` of `G_active+1` to report (never trust) an orphan with an invalid header; unreferenced generations `> G_active+1` are inert. §3 manifest gains `wal_floor`/`wal_active_gen`; §6 checkpoint computes/publishes the floor (the unlink set is exactly the segments strictly below it); novel `NM-F-20`. |

No review id other than NEW-10 is rejected; NEW-10 is rejected only as a factual anchor claim, and the
artifact still cites the anchor explicitly. No applicable finding was silently dropped.

## 8. R2 final `plan` / `commit` pseudocode (generation + drop)

> **Historical (R2).** Superseded by the R3 mandated unified generation form in §13/§14: the
> primary/disjointness split below is replaced by
> `pending_gen[s] = _generations[s] + max(passed.count(s), 1 if s in pending_drops else 0)` and
> `ref.gen = pending_gen[slot]`. Retained as the R2 record only.

```text
# plan (PURE; no mutation)
g = _generations
pending_drops = {slot: pending_gen[slot] for slot in gc_victims}     # policy-selected evictions
for each member key m in arrival order:
    s = cursor.next_slot()
    if s in passed: passed[s] += 1                                  # wrap within this plan
    passed.setdefault(s, ...) ; reuse list
    base[s]      = pending_drops[s] if s in pending_drops else g[s]
    ref[m].gen   = base[s] + passed.count(s)
    pending_gen[s] = g[s] + (passed.count(s) if s in passed else 1)
    drop_events.add((s, pending_gen[s]))                            # == DROP_SLOT.new_gen
return refs, passed, drop_events

# step 2 (once, after the invalidation fdatasync)
append DROP_SLOT(s, ng) for (s, ng) in drop_events
fdatasync(WAL)                                                      # (i) invalidation durable
apply_drops(drop_events):  for (s, ng): remove slot keys; g[s] = ng; cursor[s]=0; bytes[s]=0

# step 6 (once, after the data-plan fdatasync)
commit_install(keys, refs):  for (k, r): unlink old ref accounting; _index[k]=r;
                             _slot_keys/_slot_bytes/cursor/recency updated; _next_slot set
# commit_install MUST NOT call _drop_slot and MUST NOT read/re-apply `passed`
```

Invariant: for every installed key, `_index[key].gen == _generations[slot]` (NEW-1/NEW-4;
`NM-INV-19`, `NM-F-21`). A GC victim bumps `g[s] -> g[s]+1` even when `passed.count(s) == 0`.

## 9. Chosen NEW-2 resolution and torn-tail/rotation rule

**Chosen: option (a) — in-place repair.** On replay, if the final frame of the ACTIVE segment is
short/truncated/CRC-bad: stop at the last fully valid frame, then
`ftruncate(active_fd, last_valid_offset)` followed by `fdatasync(active_fd)`, then open the active
segment in append mode at that repaired offset. There is **no rotate-and-abandon**.

Rejected alternatives:

* (b) `ftruncate+fdatasync(old_fd)` before publishing a new segment: correct but more moving parts
  (two files, publication ordering, plus the enumeration/orphan rules) for no additional safety
  over (a).
* (c) tolerate the final frame of **any** segment whose successor begins at `expected base_lsn`:
  leaves a torn frame in a non-active segment; the next restart classifies it as interior
  corruption -> FAIL CLOSED. Rejected as unsound.

Consequence: the torn frame never survives on disk, so `NM-F-17` (kill -> reopen -> write -> kill ->
reopen) is a real oracle: the second reopen must see a clean, well-framed WAL and no
interior-corruption failure.

## 10. Factually-wrong review finding (with evidence)

**NEW-10 — rejected.** The re-review claims `os.open`/`os.ftruncate` are at lines 369/371.
Observed facts (grep of the file at HEAD `4f41f5bab562b99562f30c67540eb05344d13637` and of the
clean worktree, extent sources unmodified):

```text
extent_file_backend.py:368:        self._fd = os.open(self._data_path, os.O_CREAT | os.O_RDWR, 0o644)
extent_file_backend.py:370:        os.ftruncate(self._fd, self._file_size)
```

The pre-existing `:368-370` anchor was correct; the reviewer's 369/371 is off by one. Contract §0
now cites `:368` and `:370` as two explicit anchors so the point is unambiguous. No other finding
was factually wrong; all others were verified and fixed.

## 11. R2 boundary

REPAIR R2 is a design-only proposal, like R1. It does not approve implementation, the novel
mechanism, D1/D3/D7 (or D2/D4/D6), repin, tests, evidence, coverage, commit, or merge, and it does
not self-approve. It requires an independent re-review. Gate status remains **BLOCKED** on D7, D1,
and D3.

## 12. R2 delivered artifact digests

Paths are relative to this bundle directory
`.memory/phase2-hicache-design/work/G1-bundle/`.

| artifact | sha256 |
|---|---|
| `G1-CRASH-CONSISTENCY-CONTRACT-01.md` | `a729d540a50ada09a510b83f8a24477c7ef51192859b27f243aac640a6987455` |
| `G1-RESTART-REBUILD-NOVEL-MECHANISM-01.md` | `31ae778040dbd495ccaca9d7cf6e76117bd646730a0e844288ec9a8fe399313d` |
| `G1-RESTART-REBUILD-PATTERN-INTAKE-01.md` | `37b03a07a1dce9cecd75370a55e9840ac05577cbef077970e2bdf1f86a2d25ec` |
| `G1-GATE-REPAIR-RESPONSE-01.md` (this file) | digest reported in the R2 delivery message (self-reference not embedded) |

Product/test/source scope: no file under `python/` or `test/` was modified by this repair; the
`storage/extent/` sources are clean at HEAD. The only writes are the four artifacts in this bundle
(`git status --porcelain -- .memory` shows the bundle as untracked, not part of the product tree).

---

## 13. R3 defect-response table (re-review R2-01: NEW-11, NEW-12, hardening, minor residuals)

| review id | sev | status | exact textual fix (artifact / section) |
|---|---|---|---|
| NEW-11 | moderate / correctness (sole new blocker) | **fixed (rule (a))** | Contract §6 quiesce barrier: the "release the gate after step 4" optimization is **DELETED**; `_write_gate` is held exclusively through step 6. §6 defines `wal_floor = G_active+1` at publish, the exact unlink set (generations `< wal_floor`, provably identical to `max_seq <= L` under the barrier), and the crash windows including the (4)-(5) pending-rotation window. §5 defines the resolved range: `wal_floor <= G_active` normal; `wal_floor == G_active+1` benign promotion; `wal_floor > G_active+1` fail closed. §4.4 failed-group boundary, §5 table, §16 R7, novel `NM-F-13/20` updated. `NM-INV-03/04` re-verified and unchanged; `NM-F-17..20` re-verified. |
| NEW-12 | minor / traceability | **fixed** | Contract §12 gains the `NM-F-21` oracle row after `NM-F-20`; intake §8 gains the explicit `NM-INV-19` row (positive + negative + test ids); intake Appendix B NEW-1's unsupported "by reference" claim is corrected; `every_invariant_has_pattern_and_test: true` is now genuinely supported. |
| hardening (optional) | minor | **fixed** | Contract §4.3 step 1 and §7 mandate the single unified generation form `pending_gen[s] = _generations[s] + max(passed.count(s), 1 if s in pending_drops else 0)`, `ref.gen = pending_gen[slot]`; the §4.3 "counted in the `passed` branch only" sentence and the `pending_drops ∩ passed = ∅` precondition are deleted; novel `NM-INV-19`/`NM-F-21` updated; intake `NM-INV-19` row added. |
| D1 vs §13 cold start | residual | **fixed** | Contract §13 `forward_migration` now states the pre-existing-non-empty-data-file/no-metadata cold start IS OPEN DECISION D1 (recommended D1(b)); §15 D1 consequence notes it governs §5/§13; novel §9 `forward_migration`/`mixed_state_behavior` made D1-conditional. |
| `_write_gate` is NEW | residual | **fixed** | Contract §0 OBSERVED: `_write_gate` does not exist at HEAD (only `self._lock` at `extent_file_backend.py:348`); §11 declares it G1-introduced and pins one-way lock order `_write_gate -> _lock`; novel §1/§7 state the same. |
| same-gen partial-header orphan | residual | **fixed** | Contract §5 enumeration EXCEPTION + §5 table + §6 step 5: repair in place (`os.ftruncate(fd,0)`/`O_TRUNC`, write valid header at offset 0, `fdatasync`, publish `.wal.current`) for a never-active segment at the promoted `wal_floor`; a segment named by `.wal.current` with an invalid header still fails closed. |
| `commit_install` atomicity | residual | **fixed** | Contract §4.3 step 6: install is **all-or-nothing under `_lock`**; a validation failure installs nothing, returns failure, and the backend **QUIESCES** rather than diverge from the durable WAL; a reopen re-installs the durable frames deterministically. |
| `wal_active_gen` staleness | residual | **fixed** | Contract §5 tolerated-vs-fail-closed table + §6: `wal_active_gen` is a checkpoint-time validation-only hint; a newer `.wal.current` after rotation is expected and must not be treated as corruption. |
| failed-group truncation | residual | **fixed** | Contract §4.4: exact boundary is the **post-drop offset** (immediately after the last durable `DROP_SLOT` of the group; `pre_group_offset` if none), followed by `fdatasync(WAL)`; contract `NM-F-11` updated. |

## 14. Chosen NEW-11 rule and the exact recovery range / unlink rule

**Chosen: rule (a) — delete the gate-release optimization.** `checkpoint()` acquires `_write_gate`
exclusively and holds it until after the WAL unlink completes (step 6), releasing only at step 7;
while it is held no writer may plan, pwrite, or append. The R2 "release after step 4" branch is
deleted, so no record with `seq > L` can exist until rotation has completed. At step 3 the manifest
publishes `checkpoint_lsn = L`, `wal_floor = G_active+1` (the generation step 5 will create) and
`wal_active_gen = G_active`; step 5 rotates to `new = G_active+1` and publishes `.wal.current`; the
normal post-checkpoint state is `wal_floor == G_active` (the rotated-to generation). The only
in-flight state is the crash window between steps 4 and 5, where `.wal.current` is still `G_active`
and `wal_floor == G_active+1`.

**Exact recovery range rule (§5):**
* `wal_floor <= G_active` → NORMAL: enumerate the contiguous named range `[wal_floor, G_active]`.
* `wal_floor == G_active + 1` → BENIGN pending-rotation: because the exclusive barrier guarantees
  no record with `seq > checkpoint_lsn` was appended, the segment below the floor is fully covered
  by the checkpoint snapshot. Promote `G_active := wal_floor`; validate `.wal.<wal_floor>` (create
  or repair its header at offset 0 if absent/partial), publish `.wal.current := wal_floor`, and
  replay `[wal_floor, wal_floor]`. No ACKed record is lost; the empty/inverted textual range
  `[wal_floor, G_active]` is exactly this state and is never an error.
* `wal_floor > G_active + 1` → FAIL CLOSED (impossible under the exclusive barrier).

**Exact unlink rule (§6 step 6):** unlink **exactly** the generations strictly below the published
`wal_floor`. Under the exclusive barrier this set is provably identical to `{ g : max_seq(g) <= L }`:
no segment `>= wal_floor` exists before step 5, none can receive `seq > L` while the gate is held,
and every segment `< wal_floor` is fully covered by `checkpoint_lsn = L`. So the two formulations
are one rule, not two alternatives; `wal_floor` and every generation at or above it are retained.

## 15. R3 delivered artifact digests

Paths are relative to this bundle directory
`.memory/phase2-hicache-design/work/G1-bundle/`. Digests are recomputed after the R3 write and are
repeated in the R3 delivery message.

| artifact | sha256 |
|---|---|
| `G1-CRASH-CONSISTENCY-CONTRACT-01.md` | `1e643efc3f345a88c401e46c3bd0aa5272b9610b13ed230ccd35def1fdd5ef13` |
| `G1-RESTART-REBUILD-NOVEL-MECHANISM-01.md` | `61e459c9cc3c40370b1f97cec99fda682788ae420baf4a163e2b388e13c4af95` |
| `G1-RESTART-REBUILD-PATTERN-INTAKE-01.md` | `783471557be9bd2daef665995b3a9777a632f25be533f49d7b21e4028c12cebd` |
| `G1-GATE-REPAIR-RESPONSE-01.md` (this file) | digest reported in the R3 delivery message (self-reference not embedded) |

## 16. R3 boundary

REPAIR R3 is a design-only proposal, like R1/R2. It does not approve implementation, the novel
mechanism, D1/D3/D7 (or D2/D4/D6), repin, tests, evidence, coverage, commit, or merge, and it does
not self-approve. It requires an independent re-review. Gate status remains **BLOCKED** on D7, D1,
and D3. The orchestrator must repin the R3 digests in `.memory/phase2-hicache-design/authority.yaml`
before any gate movement.

Product/test/source scope: no file under `python/` or `test/` was modified by this repair, and no
file under `storage/` was modified; the `storage/extent/` sources are clean at HEAD. The only writes
are the four artifacts in this bundle.
