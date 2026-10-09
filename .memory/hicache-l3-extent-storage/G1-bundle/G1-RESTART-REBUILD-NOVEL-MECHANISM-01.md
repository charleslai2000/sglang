ENTRY: ACCEPT

# Novel Mechanism declaration — ExtentFileBackend durable metadata restart rebuild (REPAIR R3)

```yaml
schema_version: 1.0.0-proposed
task_id: G1-RESTART-REBUILD-DESIGN-GATE-REPAIR-20260912 (continuation of
  G1-RESTART-REBUILD-DESIGN-GATE-20260912)
epoch: G1-20260912 (matches `run_epoch` in .memory/phase2-hicache-design/authority.yaml)
mechanism_id: NM-EXTENT-RESTART-REBUILD-01
repair_revision: R3 (R1 responded to G1-GATE-INDEPENDENT-REVIEW-01.md; R2 responded to
  G1-GATE-INDEPENDENT-REREVIEW-01.md; R3 responds to G1-GATE-INDEPENDENT-REREVIEW-R2-01.md:
  NEW-11 wal_floor/rotation rule, NEW-12 traceability, the unified-generation hardening, and the
  minor residuals)
title: Manifest + append-only metadata WAL rebuild of a RAM extent index over a payload-only
  sparse data file, with write-ahead slot invalidation and a durable run-scoped KV+sidecar group
proposer_role: architect (design authority author)
intake_path: .memory/phase2-hicache-design/work/G1-bundle/G1-RESTART-REBUILD-PATTERN-INTAKE-01.md
authority_manifest: .memory/phase2-hicache-design/authority.yaml (orchestrator-owned run authority
  manifest; owner orchestrator). It records authority only: it does not approve this design. The
  orchestrator repins the post-ruling digests; verify pins before any gate movement.
status: accepted:USER-RULING-20260912-G1
acceptance_decision_id: USER-RULING-20260912-G1
decided_by: user
decided_on: 2026-09-12
acceptance_basis: G1-GATE-INDEPENDENT-REREVIEW-R3-01.md (ACCEPT-WITH-CONDITIONS; N-1..N-4 applied)
required_decision_owner: orchestrator + independent G1 reviewer (satisfied by the user ruling)
```

This declaration is an evidence artifact consumed by the existing G1 gate. It does not approve
itself. **`USER-RULING-20260912-G1` (2026-09-12) ACCEPTED `NM-EXTENT-RESTART-REBUILD-01`** with the
frozen scope recorded in §12; the acceptance is the user ruling plus the independent review. Defect
mapping is in Appendix A.

---

## 1. Scope and classification

**Problem the mechanism addresses.** `ExtentFileBackend` stores page payloads in one preallocated
sparse file with **no header and no metadata**, while the authoritative `key -> ExtentRef` index,
per-slot generations, cursors, accounting, and LRU order live only in RAM
(`extent_allocator.py:113-130`). A restart therefore starts cold even though the bytes survive
(`extent_file_backend.py:17-20`). The E2E restart oracle
`TestHiCacheSpecExtentStorage`/mixin asserts post-restart storage hits, so the extent variant is
expected RED today. G1 must rebuild the RAM index from durable metadata without scanning the data
file.

**Exact components/interfaces/state touched.**

* `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py` — constructor/open, write
  ACK path (`_write_pages:1124-1160`, `batch_set_v1:598-667`, `batch_set_v2:963-1049`),
  `_gc_evict:1164-1187`, `clear:1189-1195`, `close:1209-1212`.
* `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py` — event surface of
  `plan:172-213` (now accepts `pending_drops`), `commit:215-240`, `evict_slot_lru:244-256`,
  `clear:258-284`, `_drop_slot:288-333` (allocator stays filesystem-free).
* the hybrid controller's operation context (`_t38c_durable_context` HEAD `:1100-1116`, worktree
  `:1138`; `_t38c_operation_id` set HEAD `:837`/`:880`, worktree `:851`/`:899`; read in the
  backend `batch_set_v2` HEAD/worktree `extent_file_backend.py:989`,`:1012`) — but **not** used as
  the durable group id (D-03); a new durable `(namespace_epoch, group_seq)` is minted by the
  **backend** (NEW-9), via `open_group()`/`commit_group()`.
* new persisted state: `hicache.meta{config_suffix}.manifest`,
  `hicache.meta{config_suffix}.wal.<gen>`, `...wal.current`, `...lock`.

**Trust/capability/dependency boundaries changed.** The backend gains a durable metadata namespace
and a new `fdatasync` boundary (the first fsync in the backend). No new scheduler, admission,
lifecycle, or distributed capability is added. The only new synchronization primitive is
`_write_gate`, a local writer sequencer (`self._lock` already exists at
`extent_file_backend.py:348`; `_write_gate` does not exist at HEAD); no queue/worker/thread is
added and no lock becomes an authority. Lock order is one-way `_write_gate -> _lock` (§7).

**Persistent and transient state introduced.** Persistent: the manifest checkpoint (including
`namespace_epoch`) and the WAL. Transient: the `_write_gate` sequencer, group-commit staging
buffers, and the mapped group id. No payload/authority is moved into the metadata.

**Novelty criteria triggered.** (i) no searched corpus card adequately covers the mechanism: the
data file is payload-only with no per-record framing, the index/allocator state (generations,
cursors, slot accounting) is the recovery target, write-ahead slot invalidation before clobber is
not covered, and the KV+Mamba sidecar relation has **no source card at all**; (ii) a material
composition of known patterns that introduces a new persistence format, ordering point, durability
boundary, and cross-pool failure mode; (iii) an intentional new `fdatasync` boundary where today
there is none; (iv) a relevant missing corpus range needed for the safety claim.

**Claims expressly not made.** No code is changed by this declaration; no local PASS, coverage, or
benchmark result is claimed; corpus cards are evidence not authority; extraction of the
`min`-folded shortfall as a correctness proof is not claimed. The mechanism is now ACCEPTED
(`USER-RULING-20260912-G1`) and D7 is DECIDED (a); see §5/§12 and contract §15.

**OBSERVED vs AUTHORITY vs PROPOSAL vs GAP.** All source anchors and corpus facts above are
OBSERVED. The frozen design boundary and the gate contract are AUTHORITY. Every design shape is
PROPOSAL. D1–D7 in the contract §15 and the missing exact corpus analogue are GAPs.

---

## 2. Corpus search evidence

```yaml
pattern_corpus_revision: 1953397436683219e543e19dff89560d07fa3c6f (E436); pattern/ +
  testing/ verified unchanged at review HEAD 1870ada (diff --stat 1953397..1870ada empty)
testing_corpus_revision: recon-recorded canonical reports under .memory/storage-test-corpus/ and
  testing/mining/; no separate commit recorded by the G1 corpus recon (treated as evidence)
taxonomy_families: [manifest/checkpoint, WAL durability boundary, restart replay, torn-write/
  truncation/corruption, generation/fencing/fail-closed, GC/invalidation/tombstone, atomic groups/
  all-or-nothing, harness/test methodology, benchmark separation, deferred distributed]
files_and_id_ranges: as recorded in G1-CORPUS-RECON-20260912.md tables A-G; pattern/{README,
  taxonomy,nerun-mapping,anti-patterns,bug-derived,foundationdb,rocksdb,tikv}.md;
  testing/{README,nerun-test-catalog,nerun-benchmark-catalog}.md; testing/mining/*;
  ids FDB-IMP-02..20, RP-RDB-001..045, TKV-CODE-004..033, TKV-ANTI-034..037, FAIL-ANTI-037,
  FDB-TST-01..09, TKV-HARNESS-044/045/048, FDB-C08..C22, RDB-C01..C39, TIKV-004..C39,
  RE-046..RE-061, FAIL-041..045, BENCH-062/063
query_terms: [manifest, checkpoint, superblock, WAL, journal, replay, recovery prefix, torn tail,
  truncation, corruption, checksum, generation, fencing, fail-closed, salvage, tombstone,
  invalidation, GC, group commit, fsync, durable ACK, all-or-nothing, atomic group, sidecar,
  epoch, run id, in-memory index, persistent index, sparse file, restart, reopen]
gate_and_design_anchors: [storage/review/gates/pattern-intake/README.md,
  intake-template.md, novel-mechanism-template.md, traceability-schema.md;
  frozen G1 design boundary; G1-TARGET-RECON-20260912.md; G1-CORPUS-RECON-20260912.md;
  G1-GATE-INDEPENDENT-REVIEW-01.md]
search_limitations: [corpus cards are source-level evidence, not local coverage; no data-file-scan
  analogue exists; the "sidecar" term is absent from the corpus; write-ahead invalidation before
  clobber and a run-scoped durable group id have no source card; CockroachDB/distributed rows
  deferred; the recon did not execute the E2E red/green]
```

**Why this search is sufficient.** The G1 corpus recon searched the complete in-scope corpus by the
positive mechanisms, the anti-patterns and bug-derived hazards, the harness methodology, and the
deferred/missing ranges. Three independently verified facts confirm novelty rather than omission
(verified directly by this author, not merely quoted):

1. **`"sidecar"` is absent from the entire pattern corpus** (`storage/pattern/` and
   `storage/testing/` content search returns no matches). The KV+Mamba sidecar atomic group has no
   source card.
2. **No source card covers persisting an in-RAM index over a payload-only sparse extent file.** The
   nearest cards (FDB-IMP-11, RP-RDB-012/017, TKV-CODE-024/029) assume record framing/headers or an
   existing durable index.
3. **No source card covers write-ahead slot invalidation before a clobbering payload write** (the
   D-01 boundary) or a durable run-scoped group id that survives restart (the D-03 boundary).

A consequential limitation is recorded as a gap, not as novelty by itself: no exact closed-prefix
reconstruction corpus row exists (`nerun-test-catalog.md:13`).

---

## 3. Why known patterns do not fit

| nearest_pattern_id | useful_property | required_local_property | precise_mismatch | consequence_of_adoption | disposition |
|---|---|---|---|---|---|
| FDB-IMP-11 | materialize to persistent state, commit a durable version, then evict memory | the manifest checkpoint is the durable materialization; memory may be dropped only after it is durable | source assumes a persistent spill record format with recovery metadata; local data file has **no framing/header** and must never be scanned | adopting it literally would require a data-file format change / scan, violating the frozen boundary | partial-reuse (ordering) |
| RP-RDB-012 | WAL-first, memtable-second, publish-last; never publish a partial batch | WAL is the visibility record; only index after durable WAL; all-or-nothing batch | source has a WAL with an existing durable index/memtable; local index is the thing being reconstructed and the data file is payload-only | would import a commit protocol whose recovery base does not exist locally | partial-reuse (ordering) |
| RP-RDB-017 | separate physical sync, in-memory mark-synced, and manifest update | distinct ACK, WAL-synced, and checkpoint-durable milestones | source's WAL/manifest already exist; local side has none and introduces them with a new fsync boundary | would hide that G1 defines a **new** durability primitive | partial-reuse (milestones) |
| RP-RDB-010 / RP-RDB-014 | one shared durable append per bounded group | group commit of the new metadata WAL, bounded group size, no ACK before group fsync | source groups DB writes with an existing WAL/memtable; local durability primitive and recovery are new | would understate the new ordering point | partial-reuse (grouping) |
| TKV-CODE-024 | persist a durable discriminator before exposing a rotated file | WAL segment header + `.wal.current` publication before reachability | source is a pipe-log with headers; local data file has no header and metadata is sibling files | would require a segment/header concept the data file does not have | partial-reuse (publication order) |
| TKV-CODE-026 | corruption policy explicit: fail, tolerate tail, or truncate to verified | tolerate tail then `ftruncate`+fsync before resuming appends | source already has a reader `valid_offset` and truncation; local must add the repair as a new obligation | without the repair a tolerated tail becomes interior corruption (D-02) | partial-reuse (policy) |
| TKV-CODE-029 | exclusive directory lock as single-writer authority | per-`config_suffix` metadata fence before mutate | source fences an engine directory; local must fence a metadata namespace that did not previously exist | otherwise a second opener could interleave manifest/WAL writes | partial-reuse (fencing) |
| TKV-CODE-014 / TKV-CODE-023 | match by exact identity; retire stale; refresh and retry | generation/batch/group identity is exact and durable | source identities (`term,index`) are durable raft terms; local group id must become durable and run-scoped (D-03) | a per-process id reused as a durable id lets a cross-run commit validate an orphan group | partial-reuse (identity discipline) |
| RP-RDB-019 / RP-RDB-020 | commit a related group behind a barrier, or roll all back | KV + sidecar group all-or-nothing across restart **and in the live process** | source has a manifest/version-set atomic install; local has no on-disk group marker and the sidecar concept is absent | shipping source group semantics without a local durable group id would validate partial groups across restart | partial-reuse (barrier idea) |
| RP-RDB-034 | inject I/O failure and corruption at the file boundary | the new WAL/manifest fault injection | none material beyond adding new files | n/a | partial-reuse (methodology) |
| FDB-IMP-20 | prefer restart-and-replay over in-place rollback | restart = load checkpoint -> replay WAL -> rebuild | source replays a log onto a durable store; local replay **rebuilds the index and allocator bookkeeping** | confirms the strategy but supplies no local format | partial-reuse (strategy) |
| RP-RDB-008 | anti-pattern: blocking I/O under the global logical-state lock | `fdatasync(WAL)` outside the index lock | local write path currently holds `self._lock` across plan->commit | doing fsync inside the existing lock would be the documented hazard | reject (prohibited) |
| RP-RDB-016 | anti-pattern: promise durability with no path | never claim durable before the WAL fsync returns | local new ACK must not overclaim (esp. power-loss data durability, D2) | importing "ACK == pwrite" would repeat the anti-pattern | reject (prohibited) |

**Why composition of the nearest known patterns is insufficient.** The nearest positive cards
provide *discipline* (frame records, order create->durable->publish, group one fsync, publish
durable progress before eviction, reboot-and-replay, fence the namespace). None provides the local
recovery **base** (no durable index, no framing, no data-file header, no on-disk sidecar group),
nor the two repair-specific obligations: write-ahead invalidation before clobber, and a durable
run-scoped group id. Those remain new authority/failure boundaries that the declaration states.

---

## 4. Proposed boundary and ownership

```text
hybrid/cache_controller
   | open_group() -> backend mints durable (namespace_epoch, group_seq) under the writer sequencer
   | sidecar transfers + KV write
   v
ExtentFileBackend  (owns ALL metadata IO; allocator stays filesystem-free)
   |  owns group_seq allocation + GROUP_COMMIT (NEW-9; sole minting owner)
   |  invalidation: DROP_SLOT + fdatasync  (before any clobber)
   |  data pwrite ---> payload bytes in hicache.data{sfx} (never a truth source)
   |  WAL append  ---> hicache.meta{sfx}.wal.<gen>   (single durable metadata truth)
   v
group-commit leader fsync (bounded group; followers wait)  ---> ACK
   |
   v
ExtentAllocator (RAM derived working set; rebuilt on restart from durable metadata)
```

| concern | existing owner | proposed owner | allowed capability | prohibited capability | authority decision needed |
|---|---|---|---|---|---|
| durable metadata truth | none (RAM only) | backend metadata subsystem (new) | own manifest/WAL/lock and their fsync | become a scheduler/lifecycle/watermark authority | G1 acceptance; D3 |
| payload bytes | backend `hicache.data*` | unchanged | payload only; guard by dev/ino | store/carry metadata or be scanned | none |
| RAM index / generations / accounting | `ExtentAllocator` | unchanged (derived) | be rebuilt from metadata; be discarded on restart | be an independent truth that overrides durable metadata | none; `NM-INV-02` |
| write ordering (invalidation before clobber) | implicit RAM mutation | writer sequencer + WAL | fsync `DROP_SLOT` before clobber; apply RAM drop before pwrite | clobber a live durable slot before its drop is durable | none (required by D-01) |
| sidecar/KV group identity | `operation.id` (per-process counter today) | **new durable `(namespace_epoch, group_seq)`** | tag members, gate visibility on `GROUP_COMMIT` | reuse `operation.id` or `(0,0)` for a real group | **D7 RULED (a): 128-bit CSPRNG `namespace_epoch` + per-run `group_seq`** |
| single-writer authority | in-process `self._lock` | plus `fcntl.flock(LOCK_EX)` metadata fence per `config_suffix` (NEW-6) | refuse a second opener; kernel auto-releases on death | weaken the existing allocator lock or use a non-auto-released fence | none |
| oracle/evidence | engine test oracles | unchanged | observe recovered keys/bytes | become product truth | none |

**Authoritative / derived / cached / test-only.** Authoritative: the durable manifest+WAL for
recovery. Derived: the RAM index/allocator after restart. Cached/policy: `_recency` order. Test-only:
fault-injection hooks, kill harnesses, recovered-set assertions. No second commit/lifecycle/
watermark/oracle truth is created (`NM-INV-02`).

---

## 5. Atomic invariants

Each row is one falsifiable obligation. All rows carry
`acceptance_state = accepted:USER-RULING-20260912-G1` (2026-09-12); acceptance is also recorded in
§12. Rows `NM-INV-16..18` are added by REPAIR R1; `NM-INV-19` is added by REPAIR R2 and updated to
the mandated unified generation form by REPAIR R3; `NM-INV-20` is added by the D1 authority-ruling
write-back (`USER-RULING-20260912-G1`).

| invariant_id | falsifiable normative statement | authority_owner | acceptance_state | normal_observation | failure_observation |
|---|---|---|---|---|---|
| `NM-INV-01` | On restart the backend rebuilds the authoritative RAM index solely from the manifest checkpoint and WAL; it performs no payload read, no directory-traversal key discovery, and no size-probe key discovery over `hicache.data{sfx}`. | G1 | accepted:USER-RULING-20260912-G1 | keys resolve exactly as before crash; data `preads` unchanged across reopen | a key recovered only by scanning data bytes, or a data read performed to discover keys |
| `NM-INV-02` | The RAM index after replay equals the deterministic fold of `(manifest, WAL)`; checkpoint, replay, and derived accounting never disagree, and any disagreement fails closed. | G1 | accepted:USER-RULING-20260912-G1 | reopen serves the same index and accounting | any silent reconciliation in favor of one source, or a second truth surviving a restart |
| `NM-INV-03` | A success ACK from `set`/`batch_set`/`batch_set_v1`/`batch_set_v2` is returned only after the corresponding WAL frame(s) have been appended and `fdatasync` has returned success. | G1 | accepted:USER-RULING-20260912-G1 | ACK implies WAL durability | ACK before `fdatasync`, or ACK after a failed fsync |
| `NM-INV-04` | After reopening, every operation that returned a true ACK and was not superseded by a later durable operation or a durable invalidation is present and byte-identical; the recovered set is a legal prefix of the durable operation history. | G1 | accepted:USER-RULING-20260912-G1 | all ACKed keys present and byte-identical | an ACKed, non-superseded, non-durably-invalidated key missing after reopen |
| `NM-INV-05` | A write batch becomes visible only in full: its entries are indexed only if its `BATCH_COMMIT` is durable; a partial batch is never indexed. | G1 | accepted:USER-RULING-20260912-G1 | batch all-present or all-absent | a subset of a batch's keys visible |
| `NM-INV-06` | Slot generations are persisted, restored, and strictly monotonic across restart and `clear`; any `DROP_SLOT` that would decrease a generation, or any ref whose generation differs from the restored slot generation, is resolved as a miss or a fail-closed error. | G1 | accepted:USER-RULING-20260912-G1 | stale refs miss exactly as today | a stale ref reads reused bytes, or a generation decreases |
| `NM-INV-07` | GC, LRU/watermark eviction, `_drop_slot`, and `clear` are durable: a key invalidated before a crash is absent after reopen, and its slot's generation bump survives. | G1 | accepted:USER-RULING-20260912-G1 | evicted/cleared keys stay absent | a dropped/cleared key reappears after reopen |
| `NM-INV-08` | KV and sidecar payloads for one logical hash form one atomic group: **in the live process and after restart**, either the complete group is visible/served or no member is; an incomplete group is never served and is never stitched by `batch_exists_v2`. | G1 | accepted:USER-RULING-20260912-G1 | grouped write visible only after `GROUP_COMMIT` is durable; recovered complete | a durable sidecar without its KV (or a stitched partial group) served live or after reopen |
| `NM-INV-09` | A short/torn **final** frame of the active WAL segment is tolerantly discarded to the last fully valid record; any interior malformed/checksum/version/sequence error fails closed; no partial record is ever indexed. | G1 | accepted:USER-RULING-20260912-G1 | tail loss tolerated; prefix recovered | an indexed partial record, or a fail-open on interior corruption |
| `NM-INV-10` | The manifest is versioned and integrity-checked (CRC over `header[0..12)`) and is published atomically (tmp -> fsync -> rename -> fsync dir); unknown/newer version or failed integrity check fails closed. | G1 | accepted:USER-RULING-20260912-G1 | atomic publish; known version accepted | a torn/older/newer manifest silently accepted |
| `NM-INV-11` | Checkpoint creation and WAL rotation/truncation are ordered so a crash at any step leaves a recoverable `(manifest, WAL)` combination with no lost durable record: `checkpoint()` holds `_write_gate` exclusively through rotation+unlink; segments are unlinked **exactly** when their generation is strictly below the published `wal_floor` (under the exclusive barrier this is provably identical to `max_seq <= checkpoint_lsn`); a crash in the manifest-published/rotation-pending window (`wal_floor == G_active+1`) promotes without loss. | G1 | accepted:USER-RULING-20260912-G1 | every kill point reopens to a consistent prefix | a crash window loses a durable record or yields an unusable combination |
| `NM-INV-12` | Metadata `fdatasync` never runs while holding the logical index lock; group-commit groups are bounded; WAL and replay memory are bounded; no fsync path busy-waits or blocks unrelated logical work. | G1 | accepted:USER-RULING-20260912-G1 | readers proceed during fsync; bounded groups/WAL | fsync under the index lock, unbounded group/WAL, or spin |
| `NM-INV-13` | A single backend instance owns a `config_suffix` metadata namespace; a second concurrent opener cannot interleave manifest/WAL writes; WAL `seq` is gap-free and single-writer. | G1 | accepted:USER-RULING-20260912-G1 | typed refusal for the second opener; monotonic seq | two writers appending/rotating the same WAL, or a seq gap |
| `NM-INV-14` | Replay is deterministic and idempotent: the same durable metadata yields the same index independent of directory enumeration order, thread scheduling, and wall-clock, and repeated kill/reopen converges. | G1 | accepted:USER-RULING-20260912-G1 | identical reopen result across runs | order-dependent or divergent replay |
| `NM-INV-15` | The mechanism is reversible: disabling the metadata gate or removing the metadata files restores cold-start behavior and the data file remains valid and unmodified in format. | G1 | accepted:USER-RULING-20260912-G1 | gate-off reopen is cold; data file unchanged | a data-file format dependency or an unremovable metadata requirement |
| `NM-INV-16` | **No data `pwrite` clobbers a slot that currently backs a durable live entry until that slot's `DROP_SLOT` and new generation are durable and the RAM generation bump/index removal is applied; a concurrent reader's `verify` never passes against clobbered bytes.** | G1 | accepted:USER-RULING-20260912-G1 | reusing/evicting a slot is preceded by a durable `DROP_SLOT`+fsync and a RAM drop; readers miss the old key | a clobbered slot still recoverable as valid, or a reader serving clobbered bytes |
| `NM-INV-17` | **A tolerated torn final WAL frame is `ftruncate`d in place to the last verified offset and `fsync`ed before any further append; there is no rotate-and-abandon path; the next append's `seq` continues from the last valid frame.** | G1 | accepted:USER-RULING-20260912-G1 | reopen repairs the tail in place; subsequent appends are well-framed | a later append after a partial frame, a torn frame left in a non-active segment, or an interior-corruption failure after a tolerated tail |
| `NM-INV-18` | **A durable group is identified by a WAL-global `(namespace_epoch, group_seq)` with `(0,0)` reserved as ungrouped; a `GROUP_COMMIT` from one epoch can never complete a group from another epoch, so an incomplete group from a prior run is always discarded.** | G1 | accepted:USER-RULING-20260912-G1 | groups complete only within their run; prior-run incomplete groups dropped | a cross-run commit validating an orphan group, or a real group using `(0,0)` |
| `NM-INV-19` | **Each slot generation is bumped exactly once per reuse/eviction using the single unified form `pending_gen[s] = _generations[s] + max(passed.count(s), 1 if s in pending_drops else 0)` and `ref.gen = pending_gen[slot]` (a slot in both `passed` and `pending_drops` is bumped once, not twice); `apply_drops` sets `_generations[s] = pending_gen[s]`, and `commit_install` (all-or-nothing) never re-runs a drop or re-derives a generation.** | G1 | accepted:USER-RULING-20260912-G1 | a reused/GC-victim slot's installed ref generation equals the restored generation and no entry is born stale | a double bump, a GC victim born at the old generation, or a D-05 fold mismatch |
| `NM-INV-20` | **The extent data write for a committed unit completes to the kernel/page-cache before the WAL `GROUP_COMMIT` (or `BATCH_COMMIT` for an ungrouped write) becomes durable and before any upper-layer ACK; the interleaving `WAL durable -> ACK -> data write not yet complete` is FORBIDDEN. This is SIGKILL/process-crash durability only; power-loss durability of payload bytes is not claimed.** | G1 | accepted:USER-RULING-20260912-G1 | a returned ACK implies the unit's data bytes are in the kernel/page-cache and its commit record is durable | a commit/ACK observed while the unit's data write has not completed; a SIGKILL then exposes missing/torn payload for an ACKed unit |

Compound statements are split; no row bundles independent obligations.

---

## 6. Failure model and oracle

| case_id | preconditions | fault/concurrency/crash boundary | unsafe outcome | expected API result | expected durable truth | expected derived/transient state | recovery/fail-safe action | observables | Test Corpus analogue |
|---|---|---|---|---|---|---|---|---|---|
| `NM-F-01` | N keys written, graceful `close()` | clean reopen | none | reopen succeeds | manifest+WAL consistent | rebuilt index = pre-close index | load checkpoint -> replay -> rebuild | key set + bytes + accounting equal; no data read | RDB-C39 |
| `NM-F-02` | keys ACKed | real `SIGKILL` of the process | lost ACKed keys | new process starts | WAL-durable records survive | rebuilt index includes all durable ACKed ops | load -> replay -> rebuild | every ACKed, non-invalidated key present | FDB-C08/C09, RE-050 |
| `NM-F-03` | write in flight on a fresh slot | kill between data `pwrite` and WAL `fdatasync` | metadata referencing unwritten bytes | the interrupted call returned no ACK | no WAL frame for it | no index entry | orphan payload ignored; no scan | no key/accounting; index consistent | RE-056 |
| `NM-F-04` | WAL active segment | kill mid-append (short final frame) | indexing a partial record | reopen succeeds with tail discarded | valid prefix of WAL | last valid frame state | stop at last valid frame; **truncate+fsync before append** (`NM-INV-17`) | recovered prefix + repaired tail | FDB-IMP-09, TKV-CODE-026, RE-051 |
| `NM-F-05` | WAL segment | interior byte flip / bad magic/length/type / seq gap | fail-open on corruption | typed recovery error; no backend published | no partial truth | none published | fail closed | typed error + no serve | RDB-C39, RE-049 |
| `NM-F-06` | manifest present | corrupt crc / unknown version / geometry or dev/ino mismatch (committed region) | silently downgrade/cold | typed recovery error | none published | none | fail closed (D3(a) RULED; never truncate/salvage/serve, never silently cold-start) | typed error | RDB-C39 |
| `NM-F-07` | restored generations | `DROP_SLOT` decreases a generation; reused-slot `SET` below restored generation | stale ref reads reused bytes | typed recovery error | generations monotonic | none published | fail closed | typed error | TKV-CODE-014 |
| `NM-F-08` | slots full / watermark pressure | LRU or watermark eviction, then kill | resurrection of an evicted key | reopen succeeds | eviction durable | evicted keys absent; generations preserved | replay `DROP_SLOT` | evicted keys absent; generation values match | FDB-IMP-14, RP-RDB-022/023 |
| `NM-F-09` | `clear()` called | kill during/around clear | half-cleared state | clear ACK only after durable CLEAR | either pre- or fully-cleared | index/accounting clear; generations kept | replay CLEAR | consistent set; monotonic generations | TKV-CODE-027 |
| `NM-F-10` | hybrid operation with sidecars + KV | kill between sidecar durability and `GROUP_COMMIT` | partial group served/stitched | KV ACK only after `GROUP_COMMIT`; sidecar may be dropped | no durable complete-group marker | incomplete group members discarded | drop incomplete group | `batch_exists_v2` min-fold correct; no stitched sibling | RP-RDB-019/020 |
| `NM-F-11` | group-commit writer (reuse/evict group included) | injected `fdatasync` failure / short append | false success | no group member ACKed | WAL truncated to the post-drop boundary — the byte immediately after the last durable `DROP_SLOT` of the group (`post_drop_offset`), or `pre_group_offset` only when the group emitted no `DROP_SLOT`; durable `DROP_SLOT`s retained | index reflects the durable prefix; no new entries installed | roll back the group's new entries; return failure | no ACK; durable prefix consistent | RP-RDB-015/020, TKV-CODE-022 |
| `NM-F-12` | metadata namespace free | second concurrent opener | interleaved metadata writes | typed fence refusal | one writer | single writer | refuse second opener | typed refusal | TKV-CODE-029 |
| `NM-F-13` | checkpoint/rotation in progress | kill before/after manifest publish, before/after `.wal.current` replace, before/after WAL unlink — **including the manifest-published/rotation-pending window (`wal_floor == G_active+1`)** | lost durable records | reopen succeeds | recoverable combination | consistent prefix | resume from last valid manifest+segments; the pending-rotation window promotes `G_active := wal_floor` (no loss under the exclusive barrier) | all durable records present | FDB-IMP-11/15, TKV-CODE-024 |
| `NM-F-14` | bounded soak loop | repeated write/kill/reopen | divergence/unbounded growth | reopen converges | durable records intact | bounded index/WAL/replay memory | idempotent replay | convergence + bounded resources | RP-RDB-039, TKV-HARNESS-045 |
| `NM-F-15` | W1 5a: a live slot K is reused/evicted by a new write | kill at step 3 (data pwrite), step 4 (WAL append), or step 5 (data-plan fsync) — i.e. only **after** the step-2 invalidation `fdatasync` has made `DROP_SLOT(K)` durable (NEW-8) | reopen serves clobbered bytes for K | the interrupted call returned no ACK | `DROP_SLOT(K)` is durable; the old key is absent | index never maps K to clobbered bytes | replay applies the durable prefix | K absent (drop durable) or present-and-unclobbered if the kill landed before step 2; never corrupt | D-01 |
| `NM-F-16` | W1 5b: a live slot K is reused/evicted while a reader holds its ref | no crash; concurrent reader preads during/after the clobber | reader serves clobbered bytes | reader returns miss for K | `DROP_SLOT` durable + RAM drop applied before pwrite | reader's `verify` fails; bytes discarded | RAM drop before pwrite; re-verify under lock | reader miss; no hit on a stale generation | D-01 |
| `NM-F-17` | W2: crash mid-append, reopen tolerates tail, then write, then crash again | repeated crash with a partial tail | tolerated tail becomes interior corruption | both reopens succeed | WAL repaired in place to last verified offset before any append | seq continuity restored | `ftruncate`+`fdatasync` in place before append; **no rotate/abandon** (NEW-2) | second reopen succeeds; the torn frame is gone from disk; no interior-corruption failure | D-02, TKV-CODE-026 |
| `NM-F-18` | W3: run 1 incomplete group epoch E; restart mints E'; later op reuses `group_seq` | run-scoped id reused across runs | run-1 orphan group validated by a run-2 commit | group not visible | prior-epoch incomplete group discarded | staged members dropped | epoch-scoped completion | no cross-run completion | D-03 |
| `NM-F-19` | W4: the first operation of a run | id 0 misclassified as ungrouped | a real group never gated | operation gets `(E,1)`, grouped normally | group gated | correct staging | reserve `(0,0)` only for ungrouped | first op still all-or-nothing | D-03 |
| `NM-F-20` | W5: orphan newer segment with a partial header | crash during rotation before `.wal.current` replace | partial-header segment treated as active, or an in-range segment silently skipped | typed report; not validated | active segment from `.wal.current`; resolved range `[wal_floor, G_active]` fully present (`wal_floor == G_active+1` promotes; `wal_floor > G_active+1` FAIL CLOSED) | orphan ignored/reported; the pending-rotation `wal_floor` segment is repaired (`O_TRUNC`+header+fsync); missing in-range -> FAIL CLOSED | explicit named-range enumeration (no listdir) + header validation + one bounded orphan `stat` | orphan never trusted as-is; no durable segment silently skipped | D-02/W5 |
| `NM-F-21` | W6: a plan reuses/evicts slot S (S in `passed` and/or a GC victim not in `passed`) | no crash; a normal write path with the metadata gate on | an entry born at a stale generation (double-bumped or GC victim unbumped) | write ACKs | installed `ref.gen == pending_gen[S]`; `_generations[S] == pending_gen[S]` | index generation matches the restored/dropped generation exactly | NEW-1 unified formula + NEW-4 all-or-nothing install-only `commit_install` | replan/replay yields identical refs; no immediate miss on the just-written key; overlap never double-bumps | NEW-1/NEW-4 |
| `NM-F-22` | D1: a fresh (reuse-free) or reuse group is written and ACKed | order/fault injection at the data `pwritev` (step 3), WAL `fdatasync` (step 5), and ACK (step 7) boundaries (RP-RDB-036 sync DAG); optional SIGKILL after ACK | the unit is committed/ACKed while its extent data write has not completed to the kernel/page-cache, so a SIGKILL can expose missing/torn payload for an ACKed unit | ACK only after the data write has completed and the commit is durable | the data write completes before `GROUP_COMMIT`/`BATCH_COMMIT` durability and before the ACK; the forbidden interleaving never occurs | none installed before both conditions hold | abort/reject the ordering; never ACK the forbidden interleaving; SIGKILL reopen serves byte-identical ACKed payload | ordering transcript; SIGKILL reopen byte-identity | D1, `NM-INV-20` |

**Why the oracle does not become a second truth.** The oracle is the served key set/bytes plus the
on-disk metadata content read back through the real constructor, compared against the pre-crash
authoritative state captured by the already-authoritative engine path. Test model state, replay
counters, timings, and the WAL itself are diagnostics used to explain a mismatch; they never decide
correctness. Correctness evidence is produced by real kill/reopen, not an in-process mock; faults
enter at the file boundary the production code uses. Benchmark rows are separate (RP-RDB-041/045).

---

## 7. Interfaces and dependencies

* **Proposed interfaces/typed outcomes.** A backend-local metadata subsystem
  (`load_manifest`, `replay_wal`, `append_frame`, `checkpoint`, `rotate`, `close`); a durable group
  id `(namespace_epoch, group_seq)` with `(0,0)` reserved; the **backend** owns allocation via
  `open_group()`/`commit_group()` (NEW-9), so `group_seq` shares the writer-sequencer order that
  controls the WAL; typed recovery errors
  (`MetadataCorruptError`, `MetadataVersionError`, `GenerationError`, `FenceError`).
  `_write_pages`/`batch_set_v1`/`batch_set_v2` keep their bool/`List[bool]`/per-pool results; only
  durability and group visibility change. `ExtentAllocator.plan` accepts `pending_drops` and returns
  `drop_events`; `apply_drops` (bump+remove, once) and `commit_install` (install-only) are split
  (NEW-4), with the old `commit` retained as a gate-off composition shim.
* **Call/data/dependency direction.** `hybrid/cache_controller -> allocate durable group id ->
  backend write API -> (invalidation DROP_SLOT+fsync | data pwrite | WAL append | group fsync) ->
  commit`. Constructor: `open -> load -> replay -> allocator -> serve`. Close/detach: `checkpoint ->
  rotate -> fsync(dir) -> close`. No reverse dependency from metadata to the data file; no allocator
  filesystem IO.
* **Ordering/synchronization/admission/resource bounds.** Writer sequencer (`_write_gate`) held by
  the group leader; index lock only for short allocator sections; group commit bounded by
  `max_group_bytes`/`max_group_records`; WAL growth bounded by a checkpoint trigger; replay bounded
  by `checkpoint_lsn` and the manifest/entry count. `_write_gate` is a **G1-introduced primitive**
  (not present at HEAD, where the backend's only lock is `self._lock`,
  `extent_file_backend.py:348`); the mandated lock order is `_write_gate -> _lock` (one-way), and
  `checkpoint()`/`clear()` hold `_write_gate` exclusively (checkpoint through rotation+unlink,
  NEW-11). No admission authority is added.
* **Cancellation/deadline/lifecycle boundaries.** Group followers wait on a bounded leader result,
  not an unbounded/spinning wait; `close`/detach is the quiescent checkpoint boundary. Lifecycle
  remains owned by the existing controller/C2-C5 boundaries.
* **Persistence/recovery/compatibility/mixed-version.** New sibling files; data file unchanged;
  manifest/WAL `format_version` gates compatibility; old binary ignores metadata and is cold; new
  binary with no metadata starts cold. Unknown/newer version: fail closed (D3 may alter).
* **Technology/library assumptions.** Buffered Python `os.pwritev`/`os.preadv` as today, plus
  `os.fdatasync`/`os.fsync`, `os.ftruncate` (tail repair), and a CRC32C implementation to pin
  (pure-Python fallback acceptable; performance is P2C).
* **Timely/local vs distributed.** Local single-process, single-node only. No Raft/placement/
  migration/ownership/network semantics.

---

## 8. Alternatives and structural trade-offs

| alternative | pattern IDs | invariant fit | failure behavior | operational cost | reason selected/rejected |
|---|---|---|---|---|---|
| (A) do nothing / keep cold restart | none | fails `NM-INV-01/04`; E2E oracle stays RED | no new risk | zero | rejected: does not meet the frozen boundary or the acceptance oracle |
| (B) header/superblock + in-file metadata | TKV-CODE-024, FDB-IMP-09 | could fit, but violates "data files store payload only" and risks the exact-range IO/layout | a first-block write could interact with sparse layout/O_DIRECT | medium | rejected: frozen boundary forbids metadata in the payload file |
| (C) directory-traversal reconstruction | RP-RDB-029 | violates "no filesystem traversal"/no data scan | wrong/slow recovery; scan cost scales with data | high | rejected: frozen boundary forbids scanning |
| (D) single WAL, no rotation, truncate prefix after checkpoint | RP-RDB-017/035 | fits correctness if truncation is scoped exactly; riskier crash windows | a crash mid-truncate must be provably recoverable | lower complexity, higher risk | partially selected as a simpler variant; default is two-segment rotation |
| (E) manifest + append-only WAL + write-ahead invalidation + run-scoped KV+sidecar group (proposed) | FDB-IMP-09/11/20, RP-RDB-010/012/015/017/019, TKV-CODE-024/026/029 | satisfies `NM-INV-01..18` | explicit torn-tail repair; reuse invalidation durable before clobber; group rollback | up to two fsyncs on reuse; new group-id contract (D7) | **selected** |
| (F) two independent WALs (KV vs sidecar) with no group marker | none | fails `NM-INV-08` | partial group after restart | low | rejected |
| (G) rely on `min`-fold query as the sole all-or-nothing mechanism | RP-RDB-019 (idea only) | masks reads but does not make the relation durable | durable partial group state persists | none | rejected: the relation must survive restart and cover the live process |
| (H) reuse `operation.id` as the durable group id | TKV-CODE-014 (cautionary) | fails `NM-INV-18` (cross-run reuse) | orphan groups validated; first op misclassified | none | rejected: D-03 |
| (I) external database/kv store for metadata | none | adds a heavy dependency and a durability authority | new op surface | high | rejected: out of scope; second authority |

---

## 9. Reversibility and migration

```yaml
reversible_seam: backend-local metadata subsystem behind the existing ExtentFileBackend
  read/write/lifecycle API.
persistent_format_change: adds sibling manifest/WAL/lock files; the data file format is unchanged
  (payload-only, no header). The manifest gains `namespace_epoch`; the WAL frame gains a group
  epoch and the 22-byte CRC range.
forward_migration: on first open with no metadata, initialize empty metadata (fresh namespace_epoch)
  and start cold; no scan and no data rewrite. For a pre-existing NON-EMPTY data file with no
  metadata this cold start is governed by D1(b) (RULED, USER-RULING-20260912-G1): no committed
  WAL-durable ACK exists, so the cold start stands; D3(a) fail-closed applies only to
  committed-region corruption.
rollback: disable/remove the metadata hooks -> reopen ignores metadata and starts cold as today;
  the data file remains valid. Safe point: any restart.
mixed_state_behavior: old binary ignores unknown sibling files and is cold; new binary without
  metadata starts cold (cold start under D1(b) for a non-empty pre-existing data file, as above);
  unknown/newer manifest version or committed corruption -> fail closed (D3(a), RULED).
data_rewrite_required: false
capability_removal_proof: static audit that removing the hooks restores the
  test_crash_reopen_all_cold behavior; no read/write path depends on metadata files.
blast_radius: extent_file_backend.py; extent_allocator.py event surface;
  mem_cache/hybrid_cache/hybrid_cache_controller.py; managers/cache_controller.py; the extent unit
  tests; test_hicache_spec_file_storage.py.
expiry_or_revisit_trigger: any data-file format change, new pool/component, distributed use, or
  power-loss durability claim.
```

Rollback does **not** depend on data loss, downtime, an unbuilt migrator, or another authority. The
only reverse dependency is stale metadata for an old binary, which is harmless because the old
binary never reads it.

---

## 10. Verification plan

Map every `NM-INV-*` and `NM-F-*` to the terminal traceability schema (intake §8 and contract
§12/§15):

* **Normal and boundary:** round-trip after checkpoint/reopen; boundary sizes; `clear`; empty
  store; max slots.
* **Anti-pattern static/capability audit:** no data-file scan/traversal; no fsync under the index
  lock; no unbounded group/WAL; no second truth; no metadata-in-data-file; no benchmark-as-oracle;
  no `operation.id` group id.
* **Deterministic race/fault tests:** group-commit join/leader; `fdatasync` failure; short append;
  reuse under a concurrent reader (W1 5b); fence.
* **Crash/reopen durable observations:** real `SIGKILL` and reopen; kill at every checkpoint/
  rotation window; torn tail then append then kill (W2); reuse-clobber kill (W1 5a); cross-run
  group-id (W3); first-op id (W4); orphan segment (W5); impossible generation; GC/clear then kill;
  sidecar/KV group crash; the data-before-commit ordering (`NM-F-22`, D1(b)). All crash cases are
  process-crash (SIGKILL/restart) only and are never a power-loss durability claim (`NM-INV-20`).
* **Bounded resource soak:** repeated kill/reopen; bounded WAL/index/replay memory.
* **Benchmark methodology (separate, P2C):** fsync/group-commit throughput; never substitutes for
  correctness.
* **Re-dispositioned oracles:** `test_crash_reopen_all_cold`
  (`test_extent_file_backend_unit.py:461-488`) is split into a recovery oracle and a
  cold-on-disabled/absent fallback; the E2E `TestHiCacheSpecExtentStorage`
  (`test_hicache_spec_file_storage.py:88-158` + `hicache_spec_storage_common.py:228-272`) is the
  acceptance oracle.

The G1 verification task must independently execute the crash cases and record immutable evidence;
source methodology is not PASS evidence.

---

## 11. Risks and open decisions

| id | risk/open decision | likelihood/effect | mitigation or evidence needed | owner | gate consequence | reversibility |
|---|---|---|---|---|---|---|
| `NM-R-01` | No accepted novel declaration yet | certain / blocks admission | orchestrator accepts/rejects | orchestrator + G1 reviewer + user | **CLEARED** — ACCEPTED by `USER-RULING-20260912-G1` | reversible |
| `NM-R-02` | D1 allowed post-crash prefix | high / changes invariant strength | user/orchestrator decision | user + orchestrator | **CLEARED** — D1(b) RULED; `NM-INV-20` added | reversible |
| `NM-R-03` | D3 fail-closed vs salvage | high / changes failure behavior | user/orchestrator decision; RDB-C10 unresolved | user + orchestrator | **CLEARED** — D3(a) RULED (fail closed) | reversible |
| `NM-R-04` | **D7 group-id epoch/identity (D-03)** | high / changes hybrid identity contract | user/orchestrator decision before implementation | user + orchestrator | **CLEARED** — D7(a) RULED (CSPRNG epoch + per-run seq) | reversible (metadata versioned) |
| `NM-R-05` | D2 power-loss data durability | medium / could serve missing payload | choose WAL-only or add data `fdatasync` | G1 + P2C | **DECIDED (a)** WAL `fdatasync` only; no power-loss claim | reversible |
| `NM-R-06` | D4 sidecar ACK semantics | medium / sidecar may disappear after crash | decide; D-08 proposes deferred visibility | user/orchestrator | **DECIDED (b)** sidecar ACK deferred to `GROUP_COMMIT` | reversible |
| `NM-R-07` | D6 metadata IO accounting | low / unit-oracle wording | decide before the re-dispositioned tests assert a counter outcome | user/orchestrator | **DECIDED (a)** separate metadata counters | reversible |
| `NM-R-08` | crc32c dependency/performance unpinned | low / implementation choice | pin the checksum impl | coder/G3 | non_blocking | reversible |
| `NM-R-09` | E2E red/green not established in design | medium / acceptance unknown | run the E2E in G1 verification | tester | non_blocking for design; gates acceptance | reversible |
| `NM-R-10` | No exact corpus coverage for closed-prefix reconstruction | certain / evidence gap | local crash/reopen evidence | tester/reviewer | non_blocking for design; GAP for terminal | n/a |
| `NM-R-11` | Run authority-manifest path now exists (`.memory/phase2-hicache-design/authority.yaml`, status `pending-decisions`); authority.yaml is repinned to R3 | certain / pinning discipline | verify the R3 pins before any gate movement | orchestrator | non_blocking for design | n/a |

---

## 12. Acceptance record

```yaml
decision: ACCEPTED
decision_id: USER-RULING-20260912-G1
acceptance_decision_id: USER-RULING-20260912-G1
decided_by: user
decided_on: 2026-09-12
authority_manifest_update: NONE by this artifact; the orchestrator repins the new digests in
  .memory/phase2-hicache-design/authority.yaml
accepted_invariants: [NM-INV-01, NM-INV-02, NM-INV-03, NM-INV-04, NM-INV-05, NM-INV-06, NM-INV-07,
  NM-INV-08, NM-INV-09, NM-INV-10, NM-INV-11, NM-INV-12, NM-INV-13, NM-INV-14, NM-INV-15,
  NM-INV-16, NM-INV-17, NM-INV-18, NM-INV-19, NM-INV-20]
accepted_scope: [the frozen mechanism only: "compact manifest/checkpoint + append-only WAL ->
  restart rebuild RAM-authoritative index"; explicitly NO open-ended mechanism expansion]
conditions: [independent review G1-GATE-INDEPENDENT-REREVIEW-R3-01.md ACCEPT-WITH-CONDITIONS,
  N-1..N-4 applied; implementation authorized for the intake's design-target product/test paths;
  a fresh coder; independent crash/reopen tester; independent reviewer]
```

Only an authorized gate/orchestrator/user decision can populate an accepted record; the record
above is populated by the user ruling, not by this artifact.

---

## Appendix A — defect-response (review R1)

| review id | status | exact textual fix |
|---|---|---|
| D-01 | fixed | `NM-INV-16`; `NM-F-15/16`; §3 sidecar/identity rows; §4 ownership row "write ordering"; §8 alternative (E)/(H) |
| D-02 | fixed | `NM-INV-17`; `NM-F-17`; §3 TKV-CODE-026 row; §10 crash cases |
| D-03 | fixed (design) / needs-decision | §4 durable `(namespace_epoch, group_seq)`; §5 `NM-INV-18`; `NM-F-18/19`; D7 in §11; contract §4.0 |
| D-04 | fixed | contract §6 quiesce barrier; `NM-INV-11` extended with `max_seq <= checkpoint_lsn` |
| D-05 | fixed | contract §5 derive+cross-check (post-replay fold) |
| D-06 | fixed | contract §11 sequencer; §7 ordering |
| D-07 | fixed | `NM-F-11` wording ("durable prefix"); contract §4.3 |
| D-08 | fixed | `NM-INV-08` extended to the live process; `NM-F-10`; §4 group identity |
| D-09 | fixed | contract §3.1 13-value enum |
| D-10 | fixed | intake `status: blocked`; intrinsic to this artifact by reference |
| D-11 | fixed | contract §4.2 CRC `header[0..22)`; `NM-INV-10` manifest CRC unchanged |
| A-01 | fixed | §1 and §7 corrected HEAD/worktree anchors; `_t38c_operation_id` set/read split; §9 blast radius adds hybrid/dirty set |
| A-02 | fixed | contract/intake anchors tightened; `crash-matrix.md:8-9` |

---

## Appendix B — defect-response (re-review R2: NEW-1..NEW-10, §0.2, W5)

| review id | status | exact textual fix |
|---|---|---|
| NEW-1 | fixed | `NM-INV-19`; `NM-F-21`; §4 and §7 generation-base text reference the contract §4.3/§7 formula |
| NEW-2 | fixed (option (a)) | `NM-INV-17` and `NM-F-17` reworded: in-place `ftruncate`+`fdatasync`, no rotate/abandon |
| NEW-4 | fixed | `NM-F-21`; §7 split-API text (`plan`/`apply_drops`/`commit_install`) |
| NEW-8 | fixed | `NM-F-15` fault boundary reworded to kill points at steps 3/4/5 after the step-2 invalidation fsync; drop-durable expectation stated |
| NEW-9 | fixed | §4 and §7 backend owns `group_seq` via `open_group()`/`commit_group()` |
| W5 | fixed | `NM-F-20` conformance to the contract §5 enumeration rule; `NM-INV-19` added |
| §0.2 | not applicable to this artifact | the `bytes`/`str` and semicolon claims were contract §0.2-only and are withdrawn there |

---

## Appendix C — defect-response (re-review R2-01: NEW-11, NEW-12, hardening, minor residuals)

| review id | status | exact textual fix |
|---|---|---|
| NEW-11 | fixed (contract rule (a)) | `NM-F-13` and `NM-F-20` now carry the pending-rotation window and the resolved-range rule (`wal_floor == G_active+1` promotes; `wal_floor > G_active+1` fails closed); §7 records that `checkpoint()` holds `_write_gate` exclusively through rotation+unlink. §1/§6/§7 are consistent with contract §5/§6. `NM-INV-03/04` unchanged (still hold under the exclusive hold). |
| NEW-12 | fixed | `NM-INV-19` is the canonical invariant; `NM-F-21` is the canonical oracle and is now also in contract §12. Intake §8 gains the `NM-INV-19` row and its Appendix B claim is corrected. |
| hardening | fixed | `NM-INV-19`/`NM-F-21` now state the **unified** generation form `pending_gen[s] = _generations[s] + max(passed.count(s), 1 if s in pending_drops else 0)`, `ref.gen = pending_gen[slot]`; the contract §4.3 disjointness precondition is deleted. |
| minor residuals | fixed | §7 declares `_write_gate` G1-new with one-way lock order `_write_gate -> _lock`; §9 `forward_migration`/`mixed_state_behavior` are D1-conditional for a pre-existing non-empty data file; §11 `NM-R-11` repointed to the existing authority manifest (R3 pins repinned). |

---

### Appendix D — authority-ruling write-back (`USER-RULING-20260912-G1`, 2026-09-12)

Surgical write-back of the user's binding decisions; the mechanism is unchanged beyond the one new
hard invariant.

| ruling | recorded in |
|---|---|
| Novel `NM-EXTENT-RESTART-REBUILD-01` = ACCEPTED (frozen scope only) | header `status`/`acceptance_decision_id`, §1, §12 |
| D1=(b) process-crash semantics + hard invariant | §4 ownership row context, §10/§11, §12; `NM-INV-20` (new) + `NM-F-22` (new) |
| D3=(a) fail closed | §9, §11 `NM-R-03` |
| D7=(a) CSPRNG epoch + per-run `group_seq` | §4 ownership row, §11 `NM-R-04` |
| D2=(a), D4=(b), D6=(a) accepted defaults | §11 `NM-R-05/06/07`, §12 |

Every pre-existing `NM-INV-*`/`NM-F-*` id and the `NOVEL_MECHANISM` classification are retained;
`NM-INV-20`/`NM-F-22` are the only additions.
