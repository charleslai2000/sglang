ENTRY: ACCEPT

# G1 restart-rebuild Pattern Intake — ExtentFileBackend durable metadata

```yaml
schema_version: 1.0.0-proposed
task_id: G1-RESTART-REBUILD-DESIGN-GATE-REPAIR-20260912 (continuation of
  G1-RESTART-REBUILD-DESIGN-GATE-20260912)
epoch: G1-20260912 (matches `run_epoch` in .memory/phase2-hicache-design/authority.yaml)
author_role: architect (design authority author; design artifacts only)
repair_revision: R3 (R1 responded to G1-GATE-INDEPENDENT-REVIEW-01.md; R2 responded to
  G1-GATE-INDEPENDENT-REREVIEW-01.md; R3 responds to G1-GATE-INDEPENDENT-REREVIEW-R2-01.md:
  NEW-11 wal_floor/rotation rule, NEW-12 traceability, the unified-generation hardening, and the
  minor residuals)
intake_revision: accepted package (USER-RULING-20260912-G1); this write-back changed only the
  bundle (no product/test/source file)
inspected_revision: sglang-3090-24g-opt @ HEAD 4f41f5bab562b99562f30c67540eb05344d13637 plus an
  explicitly declared dirty worktree (A-01): extent sources are clean at HEAD; the dirty files whose
  anchors are cited are python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py
  (sha256 64e933f490884b74f0d38655a8f5a75157bab530dd0ea0688323c9780f1ce4d5, +34 lines) and
  python/sglang/srt/managers/cache_controller.py
  (sha256 a41e623a2d6e462720d6584af992da290ba54e0cb3766df794117b87678b656f, +2 lines); HEAD and
  worktree anchors are given in the contract §0.1
authority_manifest: .memory/phase2-hicache-design/authority.yaml (orchestrator-owned run authority
  manifest; owner orchestrator). It records authority only and does not approve this intake; the
  orchestrator repins the post-ruling digests; verify pins before any gate movement.
authorized_write_paths: [.memory/phase2-hicache-design/work/G1-bundle/,
  python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py,
  python/sglang/srt/mem_cache/storage/extent/extent_allocator.py,
  python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py,
  python/sglang/srt/managers/cache_controller.py,
  test/registered/unit/mem_cache/test_extent_file_backend_unit.py,
  test/registered/hicache/test_hicache_spec_file_storage.py,
  python/sglang/test/hicache_spec_storage_common.py]   # this write-back wrote only the bundle
authorized_product_paths: [python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py,
  python/sglang/srt/mem_cache/storage/extent/extent_allocator.py,
  python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py,
  python/sglang/srt/managers/cache_controller.py]   # IMPLEMENTATION AUTHORIZED under USER-RULING-20260912-G1
authorized_test_paths: [test/registered/unit/mem_cache/test_extent_file_backend_unit.py,
  test/registered/hicache/test_hicache_spec_file_storage.py,
  python/sglang/test/hicache_spec_storage_common.py]   # IMPLEMENTATION AUTHORIZED under USER-RULING-20260912-G1
design_target_product_paths: [python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py,
  python/sglang/srt/mem_cache/storage/extent/extent_allocator.py,
  python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py,
  python/sglang/srt/managers/cache_controller.py]
design_target_test_paths: [test/registered/unit/mem_cache/test_extent_file_backend_unit.py,
  test/registered/hicache/test_hicache_spec_file_storage.py,
  python/sglang/test/hicache_spec_storage_common.py]
excluded_domains: [storage/ repo edits, data-file format change, data-file scan,
  distributed/Raft/placement/migration, lifecycle ownership, scheduler authority, benchmark/tuning
  claims, second authority/truth source, AGENTS.md or gate-contract edits]
  # product/test edits ARE authorized for the design-target paths under USER-RULING-20260912-G1;
  # all other domains above remain excluded.
classification: NOVEL_MECHANISM
novel_declaration: .memory/phase2-hicache-design/work/G1-bundle/G1-RESTART-REBUILD-NOVEL-MECHANISM-01.md
contract_path: .memory/phase2-hicache-design/work/G1-bundle/G1-CRASH-CONSISTENCY-CONTRACT-01.md
status: complete   # template-valid (complete|blocked); blocking gaps resolved by USER-RULING-20260912-G1 + independent review; NOT self-approved
implementation_authorized: true
acceptance_decision_id: USER-RULING-20260912-G1
```

> **Self-approval boundary.** This artifact records no local PASS, no coverage claim, and no
> self-approval. `USER-RULING-20260912-G1` (2026-09-12) decided D1=(b), D3=(a), D7=(a), the
> non-blocking defaults D2=(a)/D4=(b)/D6=(a), and ACCEPTED the novel declaration
> `NM-EXTENT-RESTART-REBUILD-01` (scope: the frozen mechanism only); the acceptance basis is the
> user ruling plus the independent review `G1-GATE-INDEPENDENT-REREVIEW-R3-01.md`
> (ACCEPT-WITH-CONDITIONS; N-1..N-4 applied). Status is `complete`; implementation is authorized
> for the design-target product/test paths in the header.

---

## 1. Scope and authority

**Goal and acceptance criteria.** Author the G1 restart-rebuild Design Gate package for the sglang
HiCache L3 `ExtentFileBackend`, conforming to the storage Pattern Intake + Novel Mechanism gate.
Acceptance of the *authoring task* = the three design artifacts exist, are internally consistent,
use every required template section, disposition every relevant recon corpus ID, declare novelty
with a complete failure model/oracle/reversibility, and are ready for orchestrator + independent
reviewer. Acceptance of the *design gate* is a separate authority decision (§9/§12) and is not
claimed here.

**Exact write scope.** This write-back edited only the three design files under
`.memory/phase2-hicache-design/work/G1-bundle/` (plus status lines in the repair response). Under
`USER-RULING-20260912-G1` the design's implementation is now authorized for the `design_target_*`
product/test paths in the header (`implementation_authorized: true`); that implementation is a
separate task and is not performed here.

**Explicit non-goals.** No product/test/source edit; no `storage/` edit; no data-file format
change; no data-file scan; no new lifecycle/scheduler/watermark/distributed authority; no second
truth source; no benchmark/tuning claim; no gate-contract or AGENTS.md edit.

**Pinned authority paths, anchors, revisions, status.**

| authority | anchor / revision | status |
|---|---|---|
| frozen design boundary | dispatch `G1-RESTART-REBUILD-DESIGN-GATE-20260912` | AUTHORITY (binding) |
| gate contract | `storage/review/gates/pattern-intake/{README,intake-template,novel-mechanism-template,traceability-schema}.md` @ corpus revision | AUTHORITY (format) |
| target recon | `.memory/phase2-hicache-design/work/G1-TARGET-RECON-20260912.md` | OBSERVED source anchors |
| corpus recon | `.memory/phase2-hicache-design/work/G1-CORPUS-RECON-20260912.md` | OBSERVED search record |
| pattern corpus | `nerun-dev/storage` @ `1953397436683219e543e19dff89560d07fa3c6f` (E436); `pattern/`+`testing/` verified unchanged at later HEAD `eb976d4fb8cf…` | EVIDENCE (not authority, not local coverage) |
| sglang target | `sglang-3090-24g-opt` @ HEAD `4f41f5bab5` plus the declared dirty worktree of §0.1 (extent sources clean at HEAD) | OBSERVED |

**Affected owners/components/interfaces/state.** `ExtentFileBackend` (constructor/open, write ACK
path, GC, `clear`, `close`), `ExtentAllocator` (event surface only; stays filesystem-free), the
hybrid controller's existing operation-context plumbing (now also the durable group-id home),
`managers/cache_controller.py` (`StorageOperation` identity), and two persistence files. The RAM
index stays the derived materialization of durable metadata; no ownership moves. Dirty blast-radius
files: `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`,
`python/sglang/srt/managers/cache_controller.py` (A-01).

**Affected invariants (one atomic ID each):** `NM-INV-01` … `NM-INV-20` (novel declaration §5,
mapped in §8; `NM-INV-16..18` are REPAIR R1 additions for D-01/D-02/D-03, `NM-INV-19` is the
REPAIR R2/R3 generation-bump invariant, and `NM-INV-20` is the D1 data-before-commit hard
invariant added by `USER-RULING-20260912-G1`).

**Observed facts.** See the contract §0 and the target recon. Key observed facts: no header/magic/
version/checksum in the data file; all allocator state is RAM-only; no `fsync`/`fdatasync`
anywhere; `ExtentRef` is `extent_id,offset,length,generation`; sidecars are separate extents
committed before KV with no on-disk group marker; `test_crash_reopen_all_cold` asserts the old cold
semantics; the E2E mixin asserts a warm post-restart prefix.

**Assumptions/proposals.** All design shapes are proposals (file names, framing, group commit,
group id, hook surface). "G1 introduces the first fsync" is a proposal grounded in the observed
absence of any sync call.

**Known authority/applicability gaps.** RESOLVED by `USER-RULING-20260912-G1` (2026-09-12): D1=(b),
D3=(a), D7=(a) decided; D2=(a), D4=(b), D5=(a), D6=(a) accepted as non-blocking defaults; the
novel declaration accepted with the frozen scope. Remaining non-blocking gaps: the E2E red/green
was not executed in this design-only pass, and the corpus has no exact closed-prefix
reconstruction row. The orchestrator repins the new digests in
`.memory/phase2-hicache-design/authority.yaml`.

---

## 2. Corpus search record

```yaml
pattern_corpus_revision: 1953397436683219e543e19dff89560d07fa3c6f (E436); pattern/ + testing/
  verified byte-identical at review HEAD 1870ada (git diff --stat 1953397..1870ada -- pattern
  testing empty)
testing_corpus_revision: canonical reports under .memory/storage-test-corpus/ and testing/mining/
  as recorded by G1-CORPUS-RECON-20260912.md; no separate commit recorded by that recon
searched_at: 2026-09-12 (recon executed by G1-TARGET-RECON-20260912 / G1-CORPUS-RECON-20260912;
  this author re-verified the two novelty facts and the cited anchors by direct read)
taxonomy_families: [manifest/checkpoint, WAL durability boundary, restart replay/recovery prefix,
  torn-write/truncation/corruption, generation/fencing/fail-closed, GC/invalidation/tombstone,
  atomic groups/all-or-nothing, harness/test methodology, correctness-vs-benchmark separation,
  deferred distributed]
query_terms: [manifest, checkpoint, superblock, WAL, journal, replay, recovery prefix, restart,
  reopen, torn tail, truncation, corruption, checksum, crc, generation, fencing, fail-closed,
  salvage, tombstone, invalidation, GC, eviction, watermark, group commit, fsync, fdatasync,
  durable ACK, all-or-nothing, atomic group, barrier, sidecar, in-memory index, persistent index,
  sparse file, single writer, idempotent replay, epoch, run id, write-ahead invalidation,
  clobber, reuse, truncate-to-verified]
files_inspected: [storage/pattern/{README,taxonomy,nerun-mapping,anti-patterns,bug-derived,
  foundationdb,rocksdb,tikv}.md, storage/testing/{README,nerun-test-catalog,nerun-benchmark-catalog}.md,
  storage/testing/mining/*, storage/review/gates/pattern-intake/{README,intake-template,
  novel-mechanism-template,traceability-schema}.md (per the recon record; this author directly
  re-read the gate templates and the corpus cards cited in §3-§6)]
id_ranges_inspected: [FDB-IMP-02..20, RP-RDB-001..045, TKV-CODE-004..033, TKV-ANTI-034..037,
  FAIL-ANTI-037, FDB-TST-01..09, TKV-HARNESS-044/045/048, FDB-C08..C22, RDB-C01..C39,
  TIKV-004/C11..C39, RE-046..RE-061, FAIL-041..045, BENCH-062/063]
accepted_gate_packets_inspected: [storage/review/gates/pattern-intake/README.md (contract
  1.0.0-proposed, status PROPOSED), intake-template.md, novel-mechanism-template.md,
  traceability-schema.md]
search_limitations: [corpus cards are source-level evidence, not local coverage; the "sidecar"
  term is absent from the whole corpus; no data-file-scan analogue exists; CockroachDB/distributed
  rows deferred; the recon did not run the E2E extent test; no local runtime evidence is produced
  by a design-only task; the run authority manifest now exists
  (.memory/phase2-hicache-design/authority.yaml) and its pins are repinned to R3; no card
  covers write-ahead slot invalidation before a clobbering payload write or a run-scoped durable
  group id]
```

**How the search covered the required dimensions.** Positive mechanisms: sections A/B (manifest,
checkpoint, WAL, replay, group commit, recovery prefix), D (GC recoverability), E (atomic groups).
Negative forms and historical hazards: section F (anti-patterns and bug-derived) plus the
bug-derived cards cited in §5. Harness patterns: section G and §6. Correctness cases: the testing
corpus rows in §6. Benchmark methodology: kept separate in §6/§7 (BENCH-062/063). Deferred domains:
§7 (distributed/CockroachDB, timing-dependent TiKV rows, missing C5 coverage).

**Three novelty facts re-verified directly.** (1) A content search of `storage/pattern/` and
`storage/testing/` for `sidecar` returns **no matches**; the KV+Mamba sidecar atomic group has no
source card. (2) No card covers persisting an in-RAM index over a payload-only sparse data file:
the nearest cards assume record framing/headers or an existing durable index (FDB-IMP-11,
RP-RDB-012/017, TKV-CODE-024/029). (3) No card covers write-ahead slot invalidation before a
clobbering payload write (D-01) or a durable run-scoped group id (D-03). All are recorded in the
novel declaration §2.

---

## 3. Relevant pattern decisions

One row per relevant stable ID. Trace rows are `TR-RR-*` (§8). `authority_state` is `existing`
(the card already exists in the corpus) or `proposed` (this intake proposes the local adoption);
no card is accepted local authority.

| pattern_id | class | source_anchor | local_invariant_ids | disposition | adopted_shape_or_mismatch | authority_state | differences_and_limits | rationale | trace_row_ids |
|---|---|---|---|---|---|---|---|---|---|
| FDB-IMP-04 | implementation | pattern/foundationdb.md:70-87 | NM-INV-01,02,14 | ADOPT | constructor publishes the allocator only after load+replay completes | existing | local recovery is a single-process rebuild, not role recruitment | "index rebuilt before authoritative service" is exactly the load-before-serve rule | TR-RR-01 |
| FDB-IMP-05 | implementation | pattern/foundationdb.md:90-107 | NM-INV-11 | ADOPT | ordered close: quiesce writers -> checkpoint -> close metadata fds -> close data fd | existing | no actor/file-handle frontier; local is one fd set | gives a quiescent checkpoint boundary and a deterministic close order | TR-RR-11 |
| FDB-IMP-09 | implementation | pattern/foundationdb.md:170-187 | NM-INV-09 | ADOPT | WAL frames carry length/checksum; recovery scans to end and discards an incomplete final frame | existing | local scans the WAL, never the data file | converts byte-prefix durability into record-prefix recovery | TR-RR-09 |
| FDB-IMP-10 | implementation | pattern/foundationdb.md:190-207 | NM-INV-07,11 | ADOPT | persist `checkpoint_lsn` (logical watermark) before unlinking covered WAL segments | existing | local watermark is a single checkpoint lsn, not per-view pop | physical reclaim follows durable logical progress | TR-RR-11 |
| FDB-IMP-11 | implementation | pattern/foundationdb.md:210-227 | NM-INV-10,11 | ADOPT | materialize checkpoint -> fsync+rename -> only then rotate/unlink old WAL | existing | local spill is a compact index snapshot, not a payload spill | durable materialization before eviction/reclaim | TR-RR-10 |
| FDB-IMP-12 | implementation | pattern/foundationdb.md:230-247 | NM-INV-03 | ADOPT | reply durable only after the WAL append+sync completes | existing | no quorum; single fsync | central "ack at the durable point" rule | TR-RR-03 |
| FDB-IMP-13 | implementation | pattern/foundationdb.md:250-267 | NM-INV-03 | NOT_ADOPTED | quorum-minus-anti-quorum committed version is not imported | existing | the backend is a single-process single-writer store; there is no replica set | concrete mismatch: no quorum exists to compute | NONE |
| FDB-IMP-15 | implementation | pattern/foundationdb.md:290-307 | NM-INV-11 | ADAPT | retain old WAL generations until the checkpoint's `checkpoint_lsn` passes them; unlink only then | existing | local "consumers" are the manifest itself, not recovery/backup frontiers | same retention shape with one consumer | TR-RR-11 |
| FDB-IMP-18 | implementation | pattern/foundationdb.md:350-367 | NM-INV-09,14 | ADAPT | version-ordered bounded apply; checksum/protocol error fails validation | existing | local ordering is a single gap-free WAL seq, not multi-version MVCC | gives bounded, ordered replay that fails closed on protocol error | TR-RR-09 |
| FDB-IMP-19 | implementation | pattern/foundationdb.md:370-388 | NM-INV-03,05,10 | ADOPT | stage writes -> mark durable version -> await commit -> publish under lock | existing | local publish is the manifest rename / index install | separates durable marker from publication | TR-RR-03 |
| FDB-IMP-20 | implementation | pattern/foundationdb.md:390-407 | NM-INV-01,14 | ADOPT | restart = reboot + reopen + replay instead of in-place rollback | existing | local replay rebuilds the index rather than rolling forward a store | simplest testable recovery strategy | TR-RR-01 |
| RP-RDB-001 | implementation | pattern/rocksdb.md:10-30 | NM-INV-11 | ADOPT | numbered teardown: stop writers, drain, close WAL/manifest, then data | existing | local fd set is small and single-process | ordered teardown prevents a torn checkpoint | TR-RR-11 |
| RP-RDB-002 | implementation | pattern/rocksdb.md:33-53 | NM-INV-11 | ADOPT | checkpoint only from a quiescent write state | existing | local quiescence is the writer-serialization gate | required for a consistent checkpoint snapshot | TR-RR-11 |
| RP-RDB-007 | implementation | pattern/rocksdb.md:148-168 | NM-INV-12 | ADAPT | narrow WAL serialization separate from index state; documented lock scope | existing | local locks are `_write_gate` + `_lock`, not DB internals | keeps fsync off the logical index lock | TR-RR-12 |
| RP-RDB-010 | implementation | pattern/rocksdb.md:219-239 | NM-INV-03,12 | ADOPT | bounded group commit; one leader performs the shared durable append | existing | local group members are extent metadata writes, not DB writes | one fsync amortizes many metadata ACKs | TR-RR-03 |
| RP-RDB-011 | implementation | pattern/rocksdb.md:242-262 | NM-INV-03,12 | ADOPT | compatibility predicate before a writer joins a group | existing | local predicate is namespace/segment/sync-requirement/bound | prevents a no-fsync promise from joining a group that cannot honor it | TR-RR-03 |
| RP-RDB-012 | implementation | pattern/rocksdb.md:265-285 | NM-INV-03,05 | ADOPT | preprocess -> reserve seq -> WAL write/sync -> apply -> publish last seq | existing | local publish is the RAM index install after fsync | visibility follows durable completion | TR-RR-03 |
| RP-RDB-014 | implementation | pattern/rocksdb.md:311-332 | NM-INV-12 | ADAPT | global max group bytes; bounded group growth | existing | local bound is `max_group_bytes`/`max_group_records` | bounds latency and memory without a tuning claim | TR-RR-12 |
| RP-RDB-015 | implementation | pattern/rocksdb.md:334-354 | NM-INV-05,11 | ADOPT | capture pre-write WAL size; scoped truncation of exactly that append on failure | existing | local failure is fsync/short-append, not memtable insert | prevents a WAL tail from claiming a failed write | TR-RR-05 |
| RP-RDB-017 | implementation | pattern/rocksdb.md:380-401 | NM-INV-03,10 | ADOPT | separate physical sync, in-memory mark-synced, and manifest update | existing | local milestones are WAL-synced vs checkpoint-durable | names each durability milestone explicitly | TR-RR-10 |
| RP-RDB-019 | implementation | pattern/rocksdb.md:426-446 | NM-INV-08 | ADOPT | commit a related group behind a barrier; all-or-nothing install or rollback | existing | local group is KV+sidecar members keyed by one group id | prevents a partial group from becoming visible/recoverable | TR-RR-08 |
| RP-RDB-020 | implementation | pattern/rocksdb.md:449-469 | NM-INV-05,11 | ADOPT | retryable error rolls back ALL pending members | existing | local rollback is WAL truncation + no index install | keeps a failed group from leaving partial state | TR-RR-05 |
| RP-RDB-021 | implementation | pattern/rocksdb.md:472-492 | NM-INV-12 | ADOPT | every wait predicate includes an error/cancel escape | existing | local waiter is a group-commit follower with a bounded leader result | prevents a recovery/commit hang | TR-RR-12 |
| RP-RDB-022 | implementation | pattern/rocksdb.md:497-517 | NM-INV-07 | ADAPT | retain/journal the drop before it becomes unrecoverable; clear drains refs | existing | local queue is the WAL, not a flush scheduler; drops are journaled, not enqueued | makes invalidation durable without a new queue authority | TR-RR-07 |
| RP-RDB-023 | bug-derived | pattern/rocksdb.md:520-540 | NM-INV-07 | ADOPT | exercise invalidation/drop against in-flight work and assert no hang/crash | existing | local test = drop/evict then crash/reopen | required negative shape for GC recoverability | TR-NEG-07 |
| RP-RDB-027 | implementation | pattern/rocksdb.md:612-632 | NM-INV-07 | NOT_ADOPTED | compaction input-overlap rejection is not imported | existing | the extent backend has no compaction/rewrite path | concrete mismatch: no compaction exists to race | NONE |
| RP-RDB-029 | implementation | pattern/rocksdb.md:658-678 | NM-INV-11 | ADOPT | obsolete-file GC by reachability+protection, not age | existing | local reachability = "manifest checkpoint_lsn covers the segment" | prevents premature WAL unlink | TR-RR-11 |
| RP-RDB-031 | implementation | pattern/rocksdb.md:706-726 | NM-INV-09,12 | ADAPT | rebuild/recovery wait includes error and cancellation escape | existing | local recovery is synchronous with typed errors | prevents an indefinite recovery wait | TR-RR-12 |
| RP-RDB-032 | implementation | pattern/rocksdb.md:729-749 | NM-INV-12,13 | ADOPT | non-batch barriers join the same writer order | existing | local barrier is the checkpoint/fsync boundary | orders control ops with data ops | TR-RR-12 |
| RP-RDB-034 | harness | pattern/rocksdb.md:780-801 | NM-F-05,11 | ADOPT | inject both IO failure and checksum corruption at the file boundary | existing | local fault layer wraps WAL/manifest file ops | gives real corruption/failure coverage | TR-NEG-05 |
| RP-RDB-036 | harness | pattern/rocksdb.md:826-846 | NM-INV-16,17; NM-F-11,13 | ADAPT | sync points as a dependency DAG for rare interleavings | existing | methodology only; local scheduling points are the invalidation fsync, reuse pwrite, tail repair, and WAL append/fsync/rename/rotate | deterministically exercises W1/W2 reuse, torn-tail, and race/fault interleavings | TR-NEG-16, TR-RR-12 |
| RP-RDB-035 | bug-derived | pattern/rocksdb.md:803-823 | NM-INV-12 | ADAPT | double-check state if the sync boundary advanced during a read/wait | existing | local analogue: re-check index/slot state after the fsync wait | closes the fsync-vs-index-visibility race | TR-NEG-12 |
| RP-RDB-039 | bug-derived | pattern/rocksdb.md:895-915 | NM-INV-14 | ADOPT | persist the soak oracle across crash/restart | existing | local oracle is the recovered key/byte set | makes soak results meaningful across kills | TR-RR-14 |
| RP-RDB-041 | harness | pattern/rocksdb.md:941-961 | NM-INV-03,12 | ADOPT | separate correctness from performance results | existing | local correctness evidence is kill/reopen; benchmark is P2C | prevents a benchmark from satisfying a correctness row | TR-NEG-15 |
| TKV-CODE-004 | implementation | pattern/tikv.md:76-95 | NM-INV-13 | ADAPT | registry replacement immediately closes the displaced owner | existing | local analogue is the second-opener fence, not an actor registry | single-writer ownership without a registry | TR-RR-13 |
| TKV-CODE-006 | implementation | pattern/tikv.md:120-139 | NM-INV-13 | ADOPT | one lifecycle owner for the metadata namespace; refuse a second opener | existing | local owner is the backend instance + lock file | prevents split-brain writers | TR-RR-13 |
| TKV-CODE-012 | implementation | pattern/tikv.md:252-271 | NM-INV-05,12 | ADOPT | coalesce adjacent payloads; flush before a control boundary | existing | local coalescing is group commit of small metadata frames | bounds group overhead without merging semantics | TR-RR-12 |
| TKV-CODE-013 | implementation | pattern/tikv.md:274-293 | NM-INV-12 | ADAPT | yield/bound work on count/bytes/time with a retained continuation | existing | local group trigger is fill/time-bounded, not a worker loop | bounds group-commit latency | TR-RR-12 |
| TKV-CODE-014 | implementation | pattern/tikv.md:296-315 | NM-INV-05,06 | ADOPT | match by exact (identity, index); retire stale; impossible order fails | existing | local identity is `batch_id`/`seq`; impossible generation fails closed | catches reordered/duplicate/impossible metadata | TR-RR-06 |
| TKV-CODE-015 | implementation | pattern/tikv.md:318-337 | NM-INV-05,08 | ADOPT | write durable progress in the same commit unit as the mutation | existing | local progress markers are `BATCH_COMMIT`/`GROUP_COMMIT` frames | replay-safe progress without a separate store | TR-RR-05 |
| TKV-CODE-016 | implementation | pattern/tikv.md:340-359 | NM-INV-11 | ADOPT | replay-safe order for external artifacts vs metadata vs callbacks | existing | no external SSTs; the analogue is manifest/checkpoint ordering | prevents deleting the only replay source early | TR-RR-11 |
| TKV-CODE-017 | implementation | pattern/tikv.md:362-381 | NM-INV-11 | ADOPT | on close/destruction drain and answer waiters with explicit errors | existing | local close drains the writer gate and fails unflushed groups | no silent loss at teardown | TR-RR-11 |
| TKV-CODE-018 | implementation | pattern/tikv.md:384-403 | NM-INV-12 | ADOPT | async results route back to the lifecycle owner | existing | local results return to the writer that joined the group | keeps completion ownership single | TR-RR-12 |
| TKV-CODE-020 | implementation | pattern/tikv.md:428-447 | NM-INV-12 | ADOPT | one group leader performs the physical append+sync | existing | local group leader is the writer that wins the group mutex | one physical append/fsync per group | TR-RR-12 |
| TKV-CODE-021 | bug-derived | pattern/tikv.md:450-469 | NM-INV-07,12 | ADOPT | an empty explicit sync still syncs | existing | local analogue: `clear()`/checkpoint fsync even with no data write | prevents a no-op path from skipping durability | TR-RR-07 |
| TKV-CODE-022 | implementation | pattern/tikv.md:472-491 | NM-INV-11,12 | ADOPT | on no-space: truncate the partial append, rotate, bounded retry | existing | local rotation is segment generation + `.wal.current` | bounded recovery from a partial append | TR-RR-11 |
| TKV-CODE-023 | bug-derived | pattern/tikv.md:494-513 | NM-INV-02,06 | ADOPT | stale-index fallback: refresh from the logical index, retry, else original error | existing | local stale ref is a generation miss, never a fabricated entry | preserves single-truth semantics on stale data | TR-RR-02 |
| TKV-CODE-024 | implementation | pattern/tikv.md:516-535 | NM-INV-10,11 | ADAPT | write+fsync the durable discriminator, fsync the directory, then publish | existing | local discriminator is the WAL segment header + `.wal.current`; there is no data-file header | orders durable discoverability before reachability | TR-RR-10 |
| TKV-CODE-025 | implementation | pattern/tikv.md:538-557 | NM-INV-14 | ADAPT | deterministic serialized reducer for recovery | existing | local replay is single-threaded; parallel replay is NOT imported | keeps determinism without adding concurrency | TR-RR-14 |
| TKV-CODE-026 | implementation | pattern/tikv.md:560-579 | NM-INV-09 | ADOPT | explicit corruption policy: fail, tolerate tail, or truncate to the verified offset | existing | local policy tolerates only the final active-segment tail; interior fails closed | makes recovery policy a contract | TR-RR-09 |
| TKV-CODE-027 | implementation | pattern/tikv.md:582-601 | NM-INV-02,14 | ADOPT | detect logical holes during replay; report, do not repair | existing | local hole detection = WAL seq gap / checkpoint-vs-replay mismatch | catches silent history holes | TR-RR-02 |
| TKV-CODE-028 | implementation | pattern/tikv.md:604-623 | NM-INV-10,11 | ADAPT | distinguish live append vs rewritten/compacted vs atomic groups | existing | local distinguishes WAL append vs checkpoint snapshot vs commit groups | gives a recoverable classification without compaction | TR-RR-10 |
| TKV-CODE-029 | implementation | pattern/tikv.md:626-645 | NM-INV-13 | ADOPT | exclusive directory/namespace lock for the engine lifetime | existing | local lock is `hicache.meta{sfx}.lock` for the metadata namespace | single-writer fencing before mutate | TR-RR-13 |
| TKV-CODE-005 | implementation | pattern/tikv.md:98-117 | NM-INV-13 | ADAPT | transactional registration of owner+resource; rollback on partial failure | existing | local analogue is manifest/WAL init + lock acquisition with rollback of partial files | prevents a half-initialized namespace | TR-RR-13 |
| FDB-IMP-02 | implementation | pattern/foundationdb.md:30-47 | NM-INV-14 | ADAPT | explicit draining/terminal state machine for re-entrant recovery cleanup | existing | local recovery is a straight-line typed path, not a state machine; only the idempotence property is used | avoids importing a drain state machine the local scope does not need | TR-RR-14 |
| FDB-IMP-07 | implementation | pattern/foundationdb.md:130-147 | NM-INV-14 | NOT_ADOPTED | worker-produces/callback-on-authoritative-thread is not imported | existing | the backend has no worker pool; replay runs on the opening thread | concrete mismatch: no worker/thread exists | NONE |
| FDB-IMP-17 | implementation | pattern/foundationdb.md:330-347 | NM-INV-05 | ADAPT | normalize/copy mutations before mutating shared state | existing | local stage-then-publish of WAL frames/batch members | prevents a half-applied batch in shared state | TR-RR-05 |
| FDB-IMP-14 | implementation | pattern/foundationdb.md:270-287 | NM-INV-07,08 | ADAPT | physical safe reclaim = min across logical views | existing | local analogue = min-fold sidecar frontier and "checkpoint must cover the segment" | prevents reclaim below a slower consumer | TR-RR-07 |
| RP-RDB-004 | implementation | pattern/rocksdb.md:79-99 | NM-INV-13 | NOT_ADOPTED | CF-handle owner-ref lifetime is not imported | existing | no CF handle / borrowed view exists locally | concrete mismatch: no handle hierarchy | NONE |
| RP-RDB-009 | implementation | pattern/rocksdb.md:196-216 | NM-INV-05 | ADOPT | encode ordered mutations into one owned rep; apply at one boundary | existing | local rep is a `SET` batch + `BATCH_COMMIT` | bounds the atomic unit explicitly | TR-RR-05 |
| FDB-TST-01..03,06..08 | harness | pattern/foundationdb.md:532-709 | NM-INV-14 | ADAPT | deterministic RNG/event loop, buggify determinism, serial shuffle, explicit registration | existing | methodology only; local harness must be deterministic and reproducible | evidence shape for crash/race tests | TR-RR-14 |
| FDB-TST-04/05 | harness | pattern/foundationdb.md:532-709 | NM-F-02,04 | ADAPT | model kill/fault/disk/reboot separately | existing | local must separate process kill vs torn file vs corruption | separates crash classes for provenance | TR-NEG-04 |
| FDB-TST-09 | harness | pattern/foundationdb.md:532-709 | NM-F-13 | ADAPT | lifecycle/state matrix | existing | local matrix = checkpoint/rotation windows × kill points | covers windows, not only the happy path | TR-NEG-13 |
| TKV-HARNESS-044 | harness | pattern/tikv.md:958-977 | NM-INV-12 | ADAPT | write-barrier grouping with a held leader | existing | local group-commit leader barrier | reproduces the group ordering deterministically | TR-RR-12 |
| TKV-HARNESS-045 | harness | pattern/tikv.md:980-999 | NM-F-02,05,11 | ADOPT | fault matrix with restart and post-recovery index assertions | existing | local post-recovery assertions on the rebuilt index | asserts invariants after reopen, not just at error | TR-NEG-02 |
| TKV-HARNESS-048 | harness | pattern/tikv.md:1046-1065 | NM-INV-05 | ADOPT | assert input immutability after a failed batch operation | existing | local failed-batch group leaves no index mutation | negative shape for all-or-nothing | TR-NEG-05 |
| FAIL-CODE-030..033 | harness | pattern/tikv.md:648-733 | NM-F-14 | ADAPT | scenario mutex+RAII, counted actions, pause/unpause, faults at semantic boundaries | existing | methodology only; local fails at the WAL/manifest file boundary | deterministic fault scheduling shape | TR-RR-14 |
| RP-RDB-033 | harness | pattern/rocksdb.md:757-777 | NM-F-03,04 | ADOPT | fault env drops bytes after the last modeled sync; exposes the exact durable prefix | existing | local analogue drops bytes after the last `fdatasync` | exact durable-prefix oracle | TR-NEG-03 |
| BENCH-062/063 | benchmark | nerun-benchmark-catalog.md:6-19 | NM-INV-12 (perf only) | NOT_ADOPTED | benchmark methodology is P2C; no correctness/tuning claim here | existing | throughput cannot satisfy any correctness row | preserves correctness/benchmark separation | TR-NEG-15 |

---

## 4. Anti-pattern prohibitions

Every applicable anti-pattern maps to a static audit and/or a negative test. `NOT_ADOPTED` is not
used for an applicable anti-pattern.

| pattern_id | violated_local_invariant | prohibited_local_shape_or_capability | detection_method | negative_or_regression_test_ids | disposition |
|---|---|---|---|---|---|
| RP-RDB-003 | NM-INV-02,08 | a borrowed sidecar member view outliving its group/owner; serving a member without its group | static lifetime/ownership audit of group membership | NM-F-10 | prohibited |
| RP-RDB-008 | NM-INV-12 | `fdatasync`/blocking IO while holding the global logical index lock; unbounded wait under the lock | static call-path audit: `fdatasync` sites must be outside `self._lock` | NM-F-11, NM-F-12 | prohibited |
| RP-RDB-016 | NM-INV-03 | a success ACK with `sync`/durability promised but no `fdatasync` performed on that path (including any `fdatasync`-disabled mode) | static audit of every return-True site | NM-F-03, NM-F-11 | prohibited |
| RP-RDB-045 | NM-INV-03,12 | throughput/latency used as a correctness or durability oracle | artifact classification audit | TR-NEG-15 | prohibited |
| TKV-ANTI-034 | NM-INV-11 | magic-number sentinel as the shutdown/checkpoint signal instead of an explicit close/checkpoint | static control-flow audit | NM-F-13 | prohibited |
| TKV-ANTI-035 | NM-INV-12 | effectively unbounded WAL/group/replay memory; a `payload_len` trusted without a bound | static bound audit + oversized-frame test | NM-F-05, NM-F-14 | prohibited |
| TKV-ANTI-036 | NM-INV-03,04 | silent terminal success after a failed/partial recovery or a discarded group | forced-failure recovery test + code audit | NM-F-05, NM-F-11 | prohibited |
| FAIL-ANTI-037 | NM-INV-12 | busy-wait/spin/sleep used as a durable-ACK or recovery proof/mechanism | static call audit | NM-F-11, NM-F-14 | prohibited |

`TKV-ANTI-034` is prohibited by construction: G1 uses an explicit `close()`/checkpoint path, not a
sentinel. `TKV-ANTI-035` is prohibited by the bounded-frame/group/replay rules. All prohibited
shapes have a detection method and a negative case above.

---

## 5. Bug-derived hazards

Source symptoms are quoted from the cards; they are analogues, not local history. Local
confirmation requires a fresh tester after a fresh coder and repin.

| pattern_id | source_symptom_root_cause | local_hazard | failure_boundary | unsafe_outcome | prevention | regression_oracle | test_case_ids |
|---|---|---|---|---|---|---|---|
| RP-RDB-013 | wake-before-unlink on an intrusive writer list can create a cycle / reuse | group-commit followers woken before their node/state is consumed can miss or duplicate the ACK | group-commit join/leader transition | lost wake / duplicate ACK / hang | publish completion before wake; state re-check | every group member observes exactly one ACK; no lost/duplicate effect | NM-F-11, NM-F-12 |
| RP-RDB-018 | false "fully synced" when writes/rollover occur inside the sync window | an ACK claims durability while the WAL segment advanced/rotated mid-group | WAL append+fsync+rotation window | reopen treats dropped bytes as durable | capture the exact append boundary; fsync the boundary; re-check after rotation | no ACKed record lost after reopen; rotation windows consistent | NM-F-04, NM-F-11, NM-F-13 |
| RP-RDB-020/RP-RDB-021 | partial flush install / wait without an error escape | a failed group leaves some members indexed; a waiter hangs on a dead leader | group commit failure and recovery wait | partial visibility / indefinite wait | roll back all members; bounded wait with error escape | failed group leaves zero index mutation; no hang | NM-F-05, NM-F-11 |
| RP-RDB-023 | CF drop races a scheduled flush wait -> use-after-free/lost wakeup/hang | invalidation/eviction races an in-flight write that still references the slot | `_drop_slot`/`evict` vs in-flight plan/commit | resurrection or a stale write into a reused slot | journal the drop; writer gate serializes; generation bump before ACK | dropped key absent after reopen; generation strictly increased | NM-F-08 |
| RP-RDB-035 | concatenating two visibility layers without checking whether the boundary moved | re-indexing after fsync without re-checking the slot/generation could install a stale ref | fsync-wait vs index-visibility transition | stale ref reads reused bytes | re-check state after the durability wait | verify()/generation check rejects the stale ref | NM-F-07, NM-F-08 |
| TKV-CODE-021 | empty-write fast path bypasses `sync()` | `clear()`/checkpoint with no data write returns without fsync, so its record is not durable | `clear()`/empty-batch durability | clear lost after crash / false ACK | never skip the fsync on a durability-carrying no-op | clear is durable; reopen shows the cleared state | NM-F-09 |
| TKV-CODE-023 | stale file handle treated as a missing record without revalidation | a generation-stale ref served as a hit or fabricated as a miss for the wrong reason | stale-ref read path | wrong hit or masked corruption | refresh from the logical index first; then apply generation-miss | stale ref is a miss; refreshed ref is correct | NM-F-07 |
| TKV-CODE-026 (policy analogue) | implicit best-effort corruption handling | a torn/interior-corrupt WAL silently indexed | recovery scan | partial record indexed / data loss | explicit tolerate-tail-only policy | interior corruption fails closed; tail tolerated | NM-F-04, NM-F-05 |
| TKV-CODE-027 | "file decoded" assumed to mean history complete | a missing WAL `seq` or a checkpoint/replay gap goes undetected | replay fold | silent history hole / untracked loss | detect seq gaps and checkpoint-vs-replay disagreement; report | any gap fails closed | NM-F-05, NM-F-07 |
| TKV-CODE-014 (identity analogue) | callbacks matched by exact `(term,index)`; impossible order panics | a per-process `operation.id` reused as a durable group id lets a later run complete an orphan group, and id 0 collides with "ungrouped" | KV+sidecar group identity across restart | run-N partial group validated by run-N+1; first op never gated | durable run-scoped `(namespace_epoch, group_seq)`; reserve `(0,0)` | cross-run completion impossible; first op is a valid grouped id | NM-F-18, NM-F-19 |
| TKV-CODE-026 (tail analogue, D-02) | tolerated partial tail left in place without truncation | a tolerated torn tail becomes interior corruption after the next append | reopen->append->crash | store unrecoverable on the next restart | `ftruncate`+`fdatasync` to last verified offset before any append | kill->reopen->write->kill->reopen succeeds | NM-F-17 |
| RP-RDB-018 / D-01 analogue | false durability when a boundary moves inside the sync window | a clobbering pwrite precedes the durable invalidation of the slot | reuse/eviction vs invalidation fsync | reopen serves clobbered bytes; reader serves clobbered bytes | `DROP_SLOT`+fsync and RAM drop before any clobbering pwrite | old key either valid-and-unclobbered or durably absent; reader misses | NM-F-15, NM-F-16 |

---

## 6. Harness and Test Corpus selection

Correctness and benchmark rows are kept separate. A methodology row defines evidence shape, not a
PASS. Crash-only properties require actual kill/reopen evidence.

| corpus_id | evidence_class | invariant_ids | purpose | setup_fault_concurrency | oracle | planned_test_id_path | required_evidence | coverage_state |
|---|---|---|---|---|---|---|---|---|
| FDB-C08/C09/C10/C11/C12/C13/C20/C22; RDB-C39; RE-049/050/051 | source-level | NM-INV-04,09,11 | crash/reopen, torn tail, manifest corruption/rotation | kill at append/fsync/checkpoint; corrupt crc; truncate tail | recovered prefix exact; interior corruption rejected | extent unit + E2E crash tests | real kill/reopen logs; recovered set | planned (RE/C rows source-level only) |
| RE-054/056/059/061; FAIL-041..045 | source-level | NM-INV-05,09 | partial write, rotation header error, non-atomic visible prefix, empty sync fsync path | partial append; rotate header error; no-op sync | no index from a partial record; no-op still fsyncs | WAL fault tests | fault transcript; no-partial-index assert | planned |
| FDB-TST-01..09; FAIL-CODE-030..033 | methodology-only | NM-F-02,04,13,14 | deterministic fault/race/lifecycle matrix | deterministic RNG/scheduling; kill/fault/disk/reboot separated | reproducibility + post-recovery assertions | crash harness | reproducible transcript | planned |
| RP-RDB-033/034/036/039 | methodology-only | NM-F-03,04,05,11,13 | durable-prefix drop, IO/corruption injection, sync DAG, persistent soak oracle | drop bytes after last sync; corrupt at FS boundary | exact durable prefix; corruption typed | WAL fault/soak tests | injected-fault evidence | planned |
| RP-RDB-041 | methodology-only | NM-INV-12 | correctness vs performance separation | none | benchmark cannot satisfy a correctness row | P2C benchmark task | classification | planned |
| TKV-HARNESS-044/045/048 | methodology-only | NM-F-02,05,11 | group barrier, restart fault matrix, failed-batch immutability | held leader; restart; failed batch | post-recovery index correct; no mutation on failure | group/restart tests | fault matrix + index assert | planned |
| RDB-C01/C03/C11/C13/C14/C15/C34; RE-046..048 | source-level | NM-INV-10 | manifest/checkpoint lifecycle and reopen | kill during open/close; CRC/decode corruption | consistent reopen or typed reject | checkpoint lifecycle tests | reopen evidence | planned |
| TIKV-004/C11..C16/C23/C33/C34/C39 | source-level | NM-INV-09,11,14 | recovery/corruption/rebuild | corruption, partial recovery | deterministic rebuild; fail closed on gap | replay tests | replay transcript | planned |
| `test_crash_reopen_all_cold` (unit:461-488) | local-authority | NM-INV-04,15 | old cold oracle, MUST be re-dispositioned | close+reopen; SIGKILL | see contract §12.1 | `test_extent_file_backend_unit.py` | split recovery + fallback tests | existing; re-disposition required |
| `TestHiCacheSpecExtentStorage` (E2E:88-158) + mixin `hicache_spec_storage_common.py:228-272` | local-authority | NM-INV-04,08 | acceptance oracle: post-restart storage hits + backend identity + spec accept | real server stop/launch | `storage_cached_tokens >= input_token_len - 2*page_size`; `storage_backend == ExtentFileBackend` | `test_hicache_spec_file_storage.py` | real restart run | existing; expected RED today (recon) |
| BENCH-062/063 | benchmark | none | performance methodology only | none | n/a | P2C task | separate P2C | deferred |

---

## 7. Deferred and missing IDs

| ids_or_range | reason | affected_invariants_or_claims | consequence | current_phase | target_phase_or_task | owner | gate_disposition |
|---|---|---|---|---|---|---|---|
| FDB-C11/C16/C18, FDB-C13/C23/C34 | DISTRIBUTED-LATER / P2C | NM-INV-08 (cluster-level only) | no cluster/negative-corruption/dual-restore claim | G1 | distributed phase | corpus owner | non_blocking (local single-node scope) |
| FDB-C05, C18-C23; CRDB-1..3 | distributed phase | none claimed | no cluster-level restart claim | G1 | distributed phase | distributed owner | deferred |
| RDB-C10 best-efforts salvage | unresolved corpus decision | NM-F-06, D3 | fail-closed vs salvage for a corrupt manifest is RULED fail closed (D3(a)) | G1 | RULED D3(a) fail closed (`USER-RULING-20260912-G1`) | user + orchestrator | RESOLVED (RDB-C10 salvage superseded) |
| TIKV-009/017/018/025/026/027/033/040 | timing-dependent; need barriers | NM-F-14 | no deterministic crash/reopen oracle from these rows yet | G1 | fresh harness task | tester | non_blocking (local harness planned) |
| TiKV split-race / snapshot-install restart | upstream TODO | none claimed | restart during snapshot install out of scope | G1 | n/a | n/a | deferred |
| C5 exact corpus coverage | `MISSING exact corpus coverage` (`nerun-test-catalog.md:13`) | NM-INV-14 | no exact closed-prefix reconstruction corpus row; local evidence required | G1 | G1 verification | tester/reviewer | **GAP** (non_blocking for design; terminal needs local evidence) |
| all canonical C2/C3/C4/C5 mappings | PARTIAL/MISSING | none claimed | no local coverage may be inferred from source rows | G1 | per owner | respective owners | non_blocking; no coverage claim |
| `"sidecar"` term | absent from `pattern/*.md` | NM-INV-08 | sidecar atomic group must be composed -> novelty | G1 | novel declaration | architect/orchestrator | **GAP/BLOCKED** (drives classification) |
| named phased-shutdown API / fail-rs parked-ack | absent (`CORPUS-02-FAILPOINT-SHUTDOWN.md:126-135`) | NM-F-13 | crash-only restart lacks a first-class source primitive | G1 | fresh harness task | tester | non_blocking (local harness) |
| FDB paired-restart "allowed post-crash prefix" + RDB reopen "allowed logical prefix" | open design decisions, not corpus answers (`testing/foundationdb/restart-recovery.md:8-9`, `testing/rocksdb/crash-matrix.md:8-9`) | NM-INV-04 | the recovered-prefix boundary is unresolved | G1 | RULED D1(b) process-crash semantics (`USER-RULING-20260912-G1`) | user + orchestrator | RESOLVED |
| durable run-scoped group-id identity/epoch | no corpus card; changes the hybrid KV+sidecar identity contract | NM-INV-08, NM-INV-18 | a per-process counter cannot be a durable id; cross-run completion and id-0 collision are unsafe | G1 | RULED D7(a) CSPRNG `namespace_epoch` + per-run `group_seq` (`USER-RULING-20260912-G1`) | user + orchestrator | RESOLVED |
| write-ahead slot invalidation before clobber | no corpus card for payload-only sparse reuse | NM-INV-16 | clobbered live bytes can be served/recovered without a durable invalidation | G1 | G1 acceptance; design fixed and accepted (`USER-RULING-20260912-G1` + independent review) | architect/orchestrator | RESOLVED |
| run authority-manifest pins | path exists (`.memory/phase2-hicache-design/authority.yaml`); the orchestrator repins the new post-ruling digests | intake pinning | verify the new pins before any gate movement | G1 | orchestrator repin after the write-back | orchestrator | non_blocking for design |

---

## 8. Invariant-to-pattern-to-test mapping

Canonical columns per `traceability-schema.md` (terminal CSV is produced by the implementation gate;
here the intake mapping is populated, code/evidence/review remain `planned`).

Summary:

| invariant_id | positive_pattern_ids | negative_or_bug_ids | planned_code_boundary | test_corpus_ids | oracle | trace_status |
|---|---|---|---|---|---|---|
| NM-INV-01 | FDB-IMP-04; FDB-IMP-20 | none:reason=no-scan-analogue | `ExtentFileBackend.__init__` (254-376): load+replay before allocator publish | FDB-C08/C09; RDB-C39 | reopen rebuilds the index with no payload read/traversal | planned |
| NM-INV-02 | FDB-IMP-04; TKV-CODE-023; TKV-CODE-027 | RP-RDB-003 | checkpoint/replay/derive fold + typed recovery error | TIKV-C23/C33; RDB-C39 | checkpoint==replay==derived or typed fail-closed | planned |
| NM-INV-03 | FDB-IMP-12; RP-RDB-010/011/012; RP-RDB-017 | RP-RDB-016; RP-RDB-018 | `_write_pages`/`batch_set_v1`/`batch_set_v2` WAL append + `fdatasync` | RDB-C39; RE-061 | no ACK before `fdatasync` success | planned |
| NM-INV-04 | FDB-IMP-20; RP-RDB-039 | RP-RDB-018 | reconstructed index == durable history prefix | FDB-C08/C09/C12; RE-050 | every non-superseded durable ACKed key present | planned |
| NM-INV-05 | RP-RDB-009; RP-RDB-015; RP-RDB-020; FDB-IMP-17 | TKV-ANTI-036 | `SET`+`BATCH_COMMIT` staging | TKV-HARNESS-048; RE-056 | partial batch never indexed | planned |
| NM-INV-06 | TKV-CODE-014; TKV-CODE-023 | RP-RDB-035 | generation restore/replay/validate | TIKV-C11/C13 | monotonic generations; stale ref = miss/fail-closed | planned |
| NM-INV-07 | RP-RDB-022/023; RP-RDB-029; FDB-IMP-14 | TKV-CODE-021 | `DROP_SLOT`/`CLEAR` journaling in GC/clear | RE-050; RDB-C39 | invalidated key stays absent; generation persists | planned |
| NM-INV-08 | RP-RDB-019/020 | RP-RDB-003; RP-RDB-021 | `GROUP_COMMIT` + incomplete-group drop | E2E mixin 228-272 | no partial/stiched KV+sidecar group after reopen | planned |
| NM-INV-16 | FDB-IMP-19; RP-RDB-017; RP-RDB-022/023 | RP-RDB-018; TKV-CODE-023 | invalidation phase before any clobbering pwrite; reader re-verify | RP-RDB-036 analogue; D-01 cases | old key either valid-and-unclobbered or durably absent; no reader hit on clobbered bytes | planned |
| NM-INV-17 | TKV-CODE-026 | TKV-CODE-026 (hazard) | `ftruncate`+`fdatasync` before any append after a tolerated tail | NM-F-17; RE-051 | kill->reopen->write->kill->reopen succeeds; no interior corruption | planned |
| NM-INV-18 | TKV-CODE-014 (identity discipline); RP-RDB-019 | TKV-CODE-014 (hazard) | durable `(namespace_epoch, group_seq)`; epoch-scoped completion | E2E mixin 228-272; NM-F-18/19 | no cross-run completion; `(0,0)` reserved; first op grouped | planned |
| NM-INV-19 | FDB-IMP-19; RP-RDB-017; RP-RDB-022/023; RP-RDB-035 | TKV-CODE-014 (hazard); TKV-CODE-023 | `plan` unified generation formula (`pending_gen[s] = _generations[s] + max(passed.count(s), 1 if s in pending_drops else 0)`, `ref.gen = pending_gen[slot]`), `apply_drops` once, all-or-nothing install-only `commit_install` | NM-F-21; NM-F-07/08; RDB-C39 | each slot bumped exactly once per plan; installed `ref.gen == pending_gen[slot]`; a slot in both `passed` and `pending_drops` never double-bumps | planned |
| NM-INV-20 | FDB-IMP-12; RP-RDB-010/012; RP-RDB-017 | RP-RDB-016; RP-RDB-018 | `_write_pages`/`batch_set_v1`/`batch_set_v2`: data `pwritev` completes to the kernel/page-cache before WAL commit durability and before the ACK (D1(b)); ordering checked at the step-3/5/7 boundaries | NM-F-22; NM-F-02; NM-F-03 | a returned ACK implies the unit's data bytes are in the kernel/page-cache and its commit is durable; the forbidden `WAL durable -> ACK -> data write incomplete` interleaving never occurs | planned |
| NM-INV-09 | FDB-IMP-09; FDB-IMP-18; TKV-CODE-026 | TKV-CODE-026 (hazard) | WAL frame framing + tail policy | RE-051/054/056; RDB-C39 | final tattered frame tolerated; interior fails closed | planned |
| NM-INV-10 | FDB-IMP-11; RP-RDB-017; TKV-CODE-024/028 | TKV-ANTI-035 | manifest serialize + `fdatasync`+rename+dir-fsync; version check | RE-046..048 | atomic publish; unknown version fails closed | planned |
| NM-INV-11 | FDB-IMP-05/15; RP-RDB-001/002/029; TKV-CODE-016/022 | RP-RDB-018; TKV-ANTI-034 | checkpoint/rotate/unlink ordering; exclusive `_write_gate` through rotation+unlink | RDB-C39; RE-059; NM-F-13 | every kill window recovers a consistent prefix, including the `wal_floor == G_active+1` pending-rotation promotion (NEW-11) | planned |
| NM-INV-12 | RP-RDB-007/010/011/014/021/032; TKV-CODE-012/013/018/020 | RP-RDB-008; FAIL-ANTI-037; TKV-ANTI-035 | `_write_gate` + group commit + bounded frames | TKV-HARNESS-044; RP-RDB-036 | fsync off the index lock; bounded group/WAL; no spin | planned |
| NM-INV-13 | TKV-CODE-004/006/029; TKV-CODE-005 | none:reason=single-process-fence | manifest/WAL init + lock file | TKV-CODE-029 analogue test | second opener typed refusal | planned |
| NM-INV-14 | FDB-IMP-20; TKV-CODE-025; FDB-IMP-02 | TKV-CODE-027 | deterministic single-thread replay fold | FDB-TST-01..09; FAIL-CODE-030..033 | identical reopen result across runs; bounded memory | planned |
| NM-INV-15 | RP-RDB-041 | RP-RDB-045 | feature gate / removal seam | fallback cold test | gate-off reopen is cold; data file format unchanged | planned |

Named negative rows (trace schema §4): `TR-NEG-03` (RP-RDB-016/018 durability overclaim),
`TR-NEG-05` (RP-RDB-015/020 + TKV-ANTI-036 + RP-RDB-034/TKV-HARNESS-048 partial-batch/rollback),
`TR-NEG-07` (RP-RDB-022/023 + TKV-CODE-021 invalidation recoverability), `TR-NEG-12`
(RP-RDB-008 + RP-RDB-035 + FAIL-ANTI-037 fsync-under-lock/race/spin), `TR-NEG-13`
(TKV-ANTI-034/FDB-TST-09 checkpoint/rotation lifecycle, **including the NEW-11
`wal_floor == G_active+1` pending-rotation window, RP-RDB-018 + TKV-CODE-024**), `TR-NEG-15`
(RP-RDB-041/045 + BENCH-062/063 correctness-vs-benchmark separation), `TR-NEG-16` (RP-RDB-018 +
TKV-CODE-026 + RP-RDB-036 reuse-clobber/tail-repair interleavings for D-01/D-02, **and the
NEW-1/R3 unified-generation overlap, RP-RDB-035 + TKV-CODE-014 + TKV-CODE-023**).

---

## 9. Novel Mechanism decision

```yaml
nearest_known_patterns: [FDB-IMP-11, FDB-IMP-20, FDB-IMP-09, RP-RDB-010, RP-RDB-012, RP-RDB-014,
  RP-RDB-017, RP-RDB-019, RP-RDB-020, TKV-CODE-024, TKV-CODE-026, TKV-CODE-029, RP-RDB-016,
  RP-RDB-008]
novel_criteria_triggered:
  - no searched corpus card adequately covers persisting an in-RAM extent index (index +
    per-slot generations + cursors + accounting) over a payload-only sparse file with no header
    and no scan
  - composition of manifest/WAL/replay/group-commit/atomic-group patterns introduces a new
    persistence format, durability boundary (first fdatasync), ordering point, and cross-pool
    failure mode
  - the KV+Mamba sidecar atomic group has no source card ("sidecar" is absent from the corpus)
  - no card covers write-ahead slot invalidation before a clobbering payload write (D-01) or a
    durable run-scoped group id that survives restart (D-03); the nearest identity card
    (TKV-CODE-014) is a cautionary analogue, not a fit
  - a relevant missing corpus range (exact closed-prefix reconstruction) is needed for the
    safety claim
classification_reason: >
  NOVEL_MECHANISM. Known cards supply discipline (record framing, durable-before-publish,
  group commit, reboot-and-replay, namespace fencing, explicit corruption policy) but not the
  local recovery base: there is no durable index, no record framing, no data-file header, and no
  on-disk KV+sidecar group. Composing them still leaves the core obligations (rebuild the index
  and allocator bookkeeping, define the new fsync boundary, define the atomic group, decide
  torn-tail vs interior-corruption) without a source analogue. Three independently verified facts
  force the declaration: "sidecar" is absent from the whole pattern corpus; no card persists a RAM
  index over a payload-only sparse extent file; and no card covers write-ahead slot invalidation
  before clobber or a run-scoped durable group id. Repair R1 added `NM-INV-16..18`/`NM-F-15..20`;
  R2/R3 add `NM-INV-19`/`NM-F-21` (generation bump) and the NEW-11 pending-rotation rule; the
  authority-ruling write-back adds `NM-INV-20`/`NM-F-22` (D1 data-before-commit). The design is
  ACCEPTED under `USER-RULING-20260912-G1` (frozen scope only; see §12).
declaration_path: .memory/phase2-hicache-design/work/G1-bundle/G1-RESTART-REBUILD-NOVEL-MECHANISM-01.md
required_authority_owner: orchestrator + independent G1 reviewer (D1/D3/D7 ruled by the user)
acceptance_decision_id: USER-RULING-20260912-G1
```

The declaration is ACCEPTED by `USER-RULING-20260912-G1` (2026-09-12) on the basis of the
independent review; it is not authority in itself and does not approve any PASS or coverage.

---

## 10. Timely/distributed and phase separation

* **C2/C3/C4/C5 ownership affected and preserved.** C2 lifecycle/accounting/`Closed`, C3 bounded
  typed reads, C4 Apply/materialization, and C5 scheduling/reconstruction remain owners of truth.
  The metadata subsystem records what the existing backend did; it does not schedule, admit, or
  evict. The allocator remains the RAM working set; durable metadata is the recovery source.
* **Applicable P2C freeze decision-list IDs and disposition.** None of the P2C freeze decision-list
  ranges are touched. Group bounds and fsync throughput are correctness bounds here; tuning is P2C
  and is not frozen.
* **Correctness versus benchmark claim boundary.** Correctness = recovered key/byte set and
  typed recovery behavior via real kill/reopen. Benchmark = fsync/group throughput, separate
  (RP-RDB-041/045; BENCH-062/063 deferred).
* **Timely/local execution assumptions and E/TC invariants.** Local single-process asynchronous
  write path; no Timely scheduling authority is claimed. No E/TC invariant is changed.
* **Distributed/Raft/ownership/migration/chaos concerns.** Explicitly deferred; no cluster-level
  restart claim (FDB-C05/C18-C23, CRDB-1..3).
* **Why distributed concerns are out of scope.** The frozen boundary and the local single-node,
  single-process store define the scope; there is no replica set, placement, or ownership.
* **Cross-domain gaps requiring a fresh Task ID.** Any distributed use, data-file format change,
  new pool/component, or lifecycle-authority change requires a fresh Task ID.

---

## 11. Exemption declaration

NOT EXEMPT. This intake proposes a persistence format, a new durability boundary, a recovery
behavior, concurrency/ordering, a cross-pool failure boundary, and test-oracle changes. It is not
mechanical maintenance or non-authoritative documentation.

---

## 12. Completeness attestation

```yaml
all_relevant_ids_dispositioned: true
anti_patterns_mapped: true
bug_hazards_mapped: true
missing_and_deferred_recorded: true
every_invariant_has_pattern_and_test: true
novel_declaration_complete_or_not_required: true
methodology_not_claimed_as_result: true
no_second_authority_created: true
blocking_gaps: []   # resolved by USER-RULING-20260912-G1 (D1/D3/D7 + novel acceptance) and the
                    # independent review; remaining NON-blocking: missing exact closed-prefix
                    # corpus coverage and E2E red/green not run in this design-only pass; the
                    # orchestrator repins the post-ruling digests.
```

**Boundary:** this artifact is a design prerequisite. `USER-RULING-20260912-G1` ACCEPTED the novel
mechanism (frozen scope only), decided D1/D3/D7, and accepted the non-blocking defaults
D2/D4/D5/D6; implementation is authorized for the design-target product/test paths. This artifact
itself approves no PASS, coverage, evidence, commit, or merge; the orchestrator repins the digests.

---

## Appendix A — defect-response (review R1)

| review id | status | exact textual fix |
|---|---|---|
| D-01 | fixed | §3 negative/hazard rows; §7 and §8 `NM-INV-16` + D-01 rows; novel/contract cross-reference |
| D-02 | fixed | §3 TKV-CODE-026 tail row; §5 tail analogue; §7 `NM-INV-17` |
| D-03 | fixed (design) / needs-decision | §7 durable-group-id gap; §9 criteria + owner; contract §4.0/D7 |
| D-04 | fixed | contract §6; §8 `NM-INV-11` (via contract) |
| D-05 | fixed | contract §5 |
| D-06 | fixed | contract §11 |
| D-07 | fixed | contract §4.3; §5 RP-RDB-020 row wording unchanged in intent |
| D-08 | fixed | §8 `NM-INV-08` oracle wording (live + recovery) |
| D-09 | fixed | contract §3.1 13-value enum |
| D-10 | fixed | header `status: blocked`; §3 adds the RP-RDB-036 row; contract §12.1 no longer asserts D6 |
| D-11 | fixed | contract §4.2 CRC `header[0..22)` |
| A-01 | fixed | header `inspected_revision` with per-file digests; §1 dirty set adds hybrid/manager files; contract §0.1 anchor table |
| A-02 | fixed | §3 anchors tightened to card extents; §7 `crash-matrix.md:8-9` |

---

## Appendix B — defect-response (re-review R2: NEW-1..NEW-10, §0.2, W5)

| review id | status | exact textual fix |
|---|---|---|
| NEW-7 | fixed | the duplicated RP-RDB-036 row is merged into one row at §3 (was also duplicated later): now covers `NM-INV-16,17; NM-F-11,13`, ADAPT, `TR-NEG-16, TR-RR-12` |
| NEW-1 | fixed (R3 correction) | The R2 text claimed "§7/§8 rows reference `NM-INV-19`/`NM-F-21`"; that was **unsupported** — §8 had no `NM-INV-19` row and never mentioned `NM-F-21`. R3 adds the explicit `NM-INV-19` row to §8 and the `NM-F-21` oracle row to contract §12; §7 names the R3 repin. `every_invariant_has_pattern_and_test` is now genuinely true. |
| NEW-2 | fixed (by reference) | §3 TKV-CODE-026 row already names in-place `ftruncate`+fsync; novel `NM-INV-17`/`NM-F-17` now delete rotate/abandon |
| NEW-4 | fixed (by reference) | §7/§8 reference the split `plan`/`apply_drops`/`commit_install` |
| NEW-6 | fixed (by reference) | §3 TKV-CODE-029 row + contract §2 pin `fcntl.flock(LOCK_EX)` |
| W5 | fixed (by reference) | `NM-F-20` and contract §5 enumeration rule; no traversal |

---

## Appendix C — defect-response (re-review R2-01: NEW-11, NEW-12, hardening, minor residuals)

| review id | status | exact textual fix |
|---|---|---|
| NEW-11 | fixed (contract rule (a)) | §8 `NM-INV-11` now names the exclusive `_write_gate` hold through rotation+unlink and the `wal_floor == G_active+1` pending-rotation promotion; the existing `TR-NEG-13` checkpoint/rotation lifecycle row now also covers it (RP-RDB-018 + TKV-CODE-024). (Design detail lives in contract §5/§6; novel `NM-F-13/20`.) |
| NEW-12 | fixed | §8 gains the `NM-INV-19` row (positive + negative + test ids); Appendix B NEW-1's unsupported "by reference" claim is corrected; `NM-F-21` is now in contract §12. `every_invariant_has_pattern_and_test: true` is now supported. |
| hardening | fixed | §8 `NM-INV-19` oracle states the mandated unified generation form and that `passed`∩victim overlap never double-bumps; the existing `TR-NEG-16` row now also covers it (RP-RDB-035 + TKV-CODE-014 + TKV-CODE-023). |
| minor residuals | fixed | §1/§2/§7/§12 authority-manifest text now points at the existing `authority.yaml` (R3 pins repinned); the D1-conditional cold start is stated in novel §9 and contract §13. |

---

## Appendix D — authority-ruling write-back (`USER-RULING-20260912-G1`, 2026-09-12)

Surgical write-back of the user's binding decisions; no mechanism/invariant change beyond the one
new hard invariant.

| ruling | recorded in |
|---|---|
| Intake `status: blocked -> complete`; implementation authorized for design-target product/test paths | header, Self-approval boundary, §1, §12 |
| D1=(b) process-crash semantics + hard invariant | §1, §7, §8; `NM-INV-20` (new) + `NM-F-22` (new, in the novel/contract) |
| D3=(a) fail closed | §7 |
| D7=(a) CSPRNG epoch + per-run `group_seq` | §7 |
| D2=(a), D4=(b), D6=(a) accepted defaults | §1, §12 |
| Novel `NM-EXTENT-RESTART-REBUILD-01` ACCEPTED (frozen scope only) | §9 |
