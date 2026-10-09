ENTRY: ACCEPT

# G1 crash-consistency contract — ExtentFileBackend restart rebuild (REPAIR R3)

```yaml
schema_version: 1.0.0-proposed
contract_id: G1-CRASH-CONSISTENCY-CONTRACT-01
repair_revision: R3 (R1 responded to G1-GATE-INDEPENDENT-REVIEW-01.md; R2 responded to
  G1-GATE-INDEPENDENT-REREVIEW-01.md; R3 responds to G1-GATE-INDEPENDENT-REREVIEW-R2-01.md:
  NEW-11 wal_floor/rotation rule, NEW-12 traceability, the §7 unified-generation hardening, and
  the minor residuals)
task_id: G1-RESTART-REBUILD-DESIGN-GATE-REPAIR-20260912 (continuation of
  G1-RESTART-REBUILD-DESIGN-GATE-20260912)
role: architect (design authority author; design artifacts only)
inspected_revision: sglang-3090-24g-opt @ HEAD 4f41f5bab562b99562f30c67540eb05344d13637
  plus an explicitly declared dirty worktree (see §0.1). Anchor citations below are given for HEAD
  and, where they differ, for the dirty worktree.
corpus_revision: 1953397436683219e543e19dff89560d07fa3c6f (E436); pattern/+testing/ verified
  byte-identical at review HEAD 1870ada (git diff --stat 1953397..1870ada -- pattern testing empty)
design_status: accepted   # USER-RULING-20260912-G1 (2026-09-12); independent review
  # G1-GATE-INDEPENDENT-REREVIEW-R3-01.md ACCEPT-WITH-CONDITIONS (N-1..N-4 applied); not self-approved
acceptance_decision_id: USER-RULING-20260912-G1
decided_by: user
decided_on: 2026-09-12
implementation_authorized: true   # design-target product/test paths only (see intake); USER-RULING-20260912-G1
```

This document is the **precise design** (REPAIR R3; R1/R2 body retained). It is a proposal. It changes
no product or test file in this task. Corpus cards are evidence, not authority, and are never local
coverage. Repairs D-01..D-11/A-01/A-02 are mapped to exact sections in Appendix A; repairs
NEW-1..NEW-10/§0.2/W5 are mapped in Appendix B; repairs NEW-11/NEW-12 and the R3 hardening/minor
residuals are mapped in Appendix C.

---

## 0. Authority, boundary, and classification of statements

**OBSERVED (source facts, read directly):**

* The extent data file is `f"hicache.data{self.config_suffix}"` under `self._storage_dir`
  (`extent_file_backend.py:345-347`); it is created with `os.open(path, O_CREAT|O_RDWR, 0o644)`
  at `:368` and `os.ftruncate(fd, file_size)` at `:370` (NEW-10: verified at HEAD and in the
  clean worktree; the range `:368-370` was already correct, now cited as two explicit anchors).
* The file has **no header, magic, version, checksum or metadata record**; only payloads are
  written (`pwritev` at `extent_id*extent_size + first`, `:639-646`, `:1153-1157`).
* All authoritative state is RAM-only (`ExtentAllocator.__init__`, `extent_allocator.py:113-130`):
  `_index`, `_generations`, `_cursors`, `_slot_keys`, `_slot_bytes`, `_next_slot`, `_recency`.
  A fresh allocator is built on every open (`extent_file_backend.py:371`).
* **There is no `fsync`/`fdatasync` anywhere** (`grep` over `storage/extent/` matches only the
  docstring at `extent_file_backend.py:18`). The current ACK means "pwrite succeeded + index
  registration"; a crash leaves data orphaned and restart is cold
  (`extent_file_backend.py:17-20`).
* `ExtentRef` (frozen msgspec Struct) is exactly `extent_id, offset, length, generation`
  (`extent_allocator.py:99-103`); there is no `component`, key, checksum, or serialization.
* `_component_key` (`:386-389`) encodes the pool into the key (`key + "." + pool`), and
  `_storage_key` (`:383-384`) appends `config_suffix`.
* `plan` stamps `generation = _generations[slot] + passed.count(slot)` (`:209`); `_drop_slot`
  bumps the slot generation (`:303`); `clear` deliberately does **not** reset generations (`:284`).
* `_gc_evict` currently mutates RAM eviction before the data pwrite
  (`extent_file_backend.py:1164-1187`), and `plan` returns `passed` slots whose old residents are
  dropped by `commit` (`extent_allocator.py:223-226,180-181,288-303`). This is the D-01 reuse
  clobber boundary.
* KV and sidecars for one logical hash are separate index entries and separate extents; sidecars
  are committed before KV. **There is no cross-pool transaction or on-disk group marker.** (HEAD
  anchors: `hybrid_cache_controller.py` `batch_set_v2(backup_transfers)` `:1060`, `super()._page_backup`
  `:1108`. Dirty-worktree anchors: `:1094`, `:1142`; see §0.1.)
* On restart a recovered-but-sibling-missing state is reported as a shorter prefix by the existing
  `min`-folded `batch_exists_v2` (`:745-893`), never silently stitched.
* `StorageOperation.counter` is a **class counter reset to 0 at process start**; `self.id =
  StorageOperation.counter; StorageOperation.counter += 1` (`cache_controller.py:259,283-284`
  both at HEAD and in the worktree). Therefore `operation.id` is not durable or WAL-global (D-03),
  and the first op of a run has id 0 (W4).
* **`_write_gate` does not exist at HEAD.** The backend's only lock is `self._lock =
  threading.Lock()` (`extent_file_backend.py:348`); `grep` finds no `_write_gate` attribute anywhere
  in the backend. `_write_gate` is a **G1-introduced** writer-sequencer primitive (design; not
  implemented here), and the mandated lock order is `_write_gate -> _lock` (§11). (R3 minor
  residual; the re-review's parenthetical `:346` is off by two lines in the observed file.)

### 0.1 Inspected revision (A-01 repair)

The prior revision cited line numbers from the dirty worktree while claiming HEAD. Corrected
declaration:

* **Repo HEAD:** `4f41f5bab562b99562f30c67540eb05344d13637`.
* **Extent sources are clean at HEAD** (`git status --porcelain --
  python/sglang/srt/mem_cache/storage/extent/` is empty); all `extent_file_backend.py` /
  `extent_allocator.py` anchors below are HEAD-valid and worktree-valid.
* **Scope note (OBSERVED, R2):** the worktree is a shared, independently dirty tree. A
  `git status --porcelain -- python test` at R2 inspection also lists unrelated modifications
  (`managers/scheduler.py`, `managers/scheduler_components/hicache_restore.py`,
  `managers/scheduler_components/ready_horizon.py`, `mem_cache/trace_context.py`,
  `mem_cache/unified_cache/components/mamba_component.py`, `mem_cache/unified_radix_cache.py`, and
  `test/registered/unit/managers/test_hicache_host_allocability.py`) plus untracked P2A probe files.
  None is cited for an anchor, and this design changes none of them; the two anchor-cited dirty
  files are the table below, and every cited extent/backend file is clean. This note is added so
  the inspected revision is not overstated.
* **Dirty worktree files whose anchors were cited** (P2A telemetry adds lines):

| file | worktree sha256 | worktree vs HEAD delta |
|---|---|---|
| `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py` | `64e933f490884b74f0d38655a8f5a75157bab530dd0ea0688323c9780f1ce4d5` | +34 lines; HEAD anchors apply at worktree anchors minus the per-symbol offsets below |
| `python/sglang/srt/managers/cache_controller.py` | `a41e623a2d6e462720d6584af992da290ba54e0cb3766df794117b87678b656f` | +2 lines |

Corrected anchor table (HEAD first, dirty worktree in parentheses):

| symbol | HEAD anchor | dirty-worktree anchor |
|---|---|---|
| hybrid `attach_storage_backend` | `:276` (+ `register_mem_host_pool_v2` `:292`, `:302`) | `:290` |
| hybrid `batch_set_v2(backup_transfers)` (sidecars) | `:1060` | `:1094` |
| hybrid `super()._page_backup(operation)` (KV) | `:1108` | `:1142` |
| hybrid `_t38c_durable_context = trace_context` | `:1100-1116` | `:1138` |
| hybrid `_t38c_operation_id = operation.id` (SET) | `:837`, `:880` | `:851`, `:899` |
| backend `batch_set_v2` `_t38c_operation_id` (READ) | `extent_file_backend.py:989`, `:1012` | same (extent clean) |
| managers `detach_storage_backend` | `:724` | `:726` |
| managers `reset` | `:833` | `:835` |
| managers `ack_backup_queue.put(operation)` | `:1419` | `:1421` |

The long-standing error `_t38c_operation_id` "`:1012-1017` in hybrid" is corrected: the id is
**set in hybrid** (`:837`/`:880` HEAD) and **read in the backend** `batch_set_v2`
(`extent_file_backend.py:989`,`:1012`). `mem_cache/hybrid_cache/…` is added to the dirty
blast-radius set in the intake (A-01).

### 0.2 Prior-repair note disposition (review re-review §0.2)

The R1 "patch-consistency" note claimed (a) a `bytes`/`str` `_component_key` bug and (b) a
semicolon-separated multi-statement patch block. Both are **withdrawn**:

* (a) is refuted at HEAD. `PoolName.__str__` returns `self.value` (`hicache_storage.py:84-85`),
  so `f"{key}.{pool_name}"` is a `str`; `_storage_key` appends `config_suffix` and returns a `str`
  (`extent_file_backend.py:383-389`). No `bytes`/`str` defect exists. The persisted `component`
  enum is still derived from the `PoolName` value (contract §3.1), which is a design choice, not a
  bug fix.
* (b) has no file, anchor, diff, or oracle in this bundle. It is not a tracked work item.

No unexplained note remains; there is no open implementation-phase item from §0.2.

**AUTHORITY (binding inputs):**

* Frozen design boundary in `G1-RESTART-REBUILD-DESIGN-GATE-20260912`: no data-file scan at
  restart; compact persistent MANIFEST/CHECKPOINT + append-only metadata WAL; data files store
  payload only; contract minimum `key -> extent_id / offset / length / generation / component`;
  versioned + integrity-checked checkpoint; a WAL append becomes a recoverable fact only after a
  durable-write ACK; restart = load checkpoint -> replay WAL -> rebuild RAM index; torn/malformed/
  impossible-generation fail closed; GC/invalidation recoverable; KV + Mamba sidecar
  all-or-nothing identity survives restart.
* The repair dispatch `G1-RESTART-REBUILD-DESIGN-GATE-REPAIR-20260912`.
* `storage/review/gates/pattern-intake/{README.md,intake-template.md,novel-mechanism-template.md,
  traceability-schema.md}` (contract `1.0.0-proposed`).

**PROPOSAL → ACCEPTED (`USER-RULING-20260912-G1`, 2026-09-12):** every shape below (file names,
frames, hooks, ordering) was a proposal; the mechanism is now accepted by the user ruling, on the
basis of the independent review (ACCEPT-WITH-CONDITIONS). This contract does **not** approve
itself.

**DECIDED:** §15 records the user's binding decisions D1=(b), D3=(a), D7=(a) and the accepted
non-blocking defaults D2=(a), D4=(b), D6=(a) (D5=(a) dispositioned). The D1 hard invariant is
`NM-INV-20`, with failure case `NM-F-22`.

---

## 1. Authority model and truth ownership

```text
durable metadata (manifest checkpoint + append-only WAL)   <-- single durable truth
        |  deterministic load + replay
        v
RAM authoritative working set (ExtentAllocator index/generations/cursors/accounting/recency)
        |  derived materialization; may be discarded and rebuilt at any restart
        v
data file hicache.data{config_suffix} (payload bytes only; never a metadata truth source)
```

* The **data file is payload-only and is never scanned, listed, or size-probed for key discovery**.
  Its `st_dev`/`st_ino`/size are recorded in the manifest only as a *guard* (detect replacement),
  never as a key source.
* The RAM index remains the runtime authority for the live process; after restart it is a pure
  **derived** rebuild of durable metadata. The two are never allowed to disagree: a disagreement on
  load/replay is a fail-closed recovery error (`NM-INV-02`).
* No second commit/lifecycle/watermark/oracle authority is created. The manifest/WAL record what
  the allocator did; they do not schedule, admit, or evict.

---

## 2. Files, naming, and per-rank isolation

All files live in the same `self._storage_dir` as the data file and use the **same
`config_suffix` rule** already computed at `extent_file_backend.py:257-279` (model / tp / pp / cp).
This keeps the existing per-rank isolation guarantee: ranks never share metadata or an allocator.

| file | role |
|---|---|
| `hicache.data{config_suffix}` | existing payload-only sparse data file (unchanged format) |
| `hicache.meta{config_suffix}.manifest` | compact versioned + integrity-checked checkpoint (single, atomically replaced) |
| `hicache.meta{config_suffix}.wal.<gen>` | append-only metadata WAL segment `<gen>` |
| `hicache.meta{config_suffix}.wal.current` | atomic pointer to the active WAL segment generation |
| `hicache.meta{config_suffix}.lock` | exclusive single-writer fence: `fcntl.flock(fd, LOCK_EX)` on a persistent lock file (NEW-6) |

**Fence rule (NEW-6).** The fence is `fcntl.flock(fd, LOCK_EX)` (`LOCK_NB` for a typed refusal:
a second opener gets `EWOULDBLOCK` -> `FenceError`). `flock` is auto-released by the kernel when
the holding process dies, so a crash never leaves a stale lock that blocks reopen — this is why
`O_CREAT|O_EXCL` is **not** an equal alternative and is not used. The lock file itself is not
deleted on crash; leaving it is safe because its content is immaterial (the flock, not the file
existence, is the authority). Stale-lock handling = none required beyond `flock`; recovery may
truncate/reuse a leftover zero-length lock file. If `flock` is unavailable on a platform, the
design fails closed rather than substituting a non-auto-released lock.

Rationale for sibling files rather than a header inside `hicache.data*`: the frozen boundary says
data files store payload only and metadata must not depend on filesystem traversal. Sibling files
keep the data file format and all existing IO/exact-range/read-amplification behavior byte-for-byte
unchanged, keep recovery to a fixed set of `open()` calls (no traversal), and let the old binary
ignore metadata cleanly (§13).

`config_suffix` also means each TP/PP/CP rank owns a disjoint `(manifest, WAL, data)` triple; there
is no cross-rank metadata coordination and no new distributed claim.

---

## 3. Manifest / checkpoint format

Fixed little-endian framing; the whole record is length-delimited and checksummed.

```text
offset  size  field
0       4     magic = 0x484D3145 ("HM1E")
4       2     format_version            # u16, currently 1
6       2     flags
8       4     payload_len
12      4     crc32c(header[0..12) || payload)   # header bytes 0..11 inclusive
16      ...   payload (below)
```

Payload:

| field | type | note |
|---|---|---|
| `checkpoint_lsn` | u64 | highest WAL seq folded into this checkpoint (0 = empty) |
| `wal_floor` | u64 | smallest WAL segment generation that may contain a record with `seq > checkpoint_lsn` (W5 enumeration floor; segments below it are checkpoint-covered and need not exist) |
| `wal_active_gen` | u64 | active segment generation at checkpoint time (W5 validation only) |
| `extent_size` | u64 | must equal runtime `extent_size`, else fail closed |
| `file_size` | u64 | must equal runtime `file_size`, else fail closed |
| `num_slots` | u32 | must equal runtime `file_size // extent_size` |
| `data_dev` / `data_ino` | u64 each | guard against data-file replacement (0 = unknown) |
| `file_uuid` | 16 bytes | random id minted on first initialization; stable thereafter |
| `namespace_epoch` | 16 bytes | WAL-global group-id epoch minted per run and persisted (D-03/D7) |
| `next_slot` | u32 | allocator cursor |
| `generations[num_slots]` | u64 each | authoritative slot generations |
| `cursors[num_slots]` | u32 each | authoritative pack cursors |
| `slot_bytes[num_slots]` | u64 each | bookkeeping; is a *base* folded by replay (D-05) |
| `recency_order` | u32 count + keys | approximate LRU order (policy, not correctness) |
| `entries` | u32 count + records | one per live key (below) |
| `groups` | u32 count + group records | one per complete atomic group (below) |

Index entry record (this is the contract-minimum metadata):

```text
storage_key   (u16 len + bytes)
extent_id     (u32)
offset        (u32)
length        (u32/u64; page length is bounded by extent_size)
generation    (u64)
component     (u8 enum; see the 13-value table below)
group_epoch   (16 bytes; 0 = ungrouped)
group_seq     (u64; 0 = ungrouped)
```

Group record: `group_epoch (16)`, `group_seq (u64)`, `member_count (u32)`, `state (u8: COMPLETE)`.
An **incomplete** group is never written into a checkpoint: checkpoint creation resolves it by
dropping its members first, so the checkpoint contains only complete groups.

### 3.1 Component enum (D-09 repair)

`PoolName` (`hicache_storage.py:63-82`) has **13** members. The persisted enum covers all 13
explicitly, with `OTHER=255` reserved for a future/unknown pool:

| u8 | component | `PoolName` |
|---|---|---|
| 0 | KV | `KV` |
| 1 | MAMBA | `MAMBA` |
| 2 | SWA | `SWA` |
| 3 | INDEXER | `INDEXER` |
| 4 | DEEPSEEK_V4_C4 | `DEEPSEEK_V4_C4` |
| 5 | DEEPSEEK_V4_C4_INDEXER | `DEEPSEEK_V4_C4_INDEXER` |
| 6 | DEEPSEEK_V4_C128 | `DEEPSEEK_V4_C128` |
| 7 | DEEPSEEK_V4_C4_STATE | `DEEPSEEK_V4_C4_STATE` |
| 8 | DEEPSEEK_V4_C4_INDEXER_STATE | `DEEPSEEK_V4_C4_INDEXER_STATE` |
| 9 | DEEPSEEK_V4_C128_STATE | `DEEPSEEK_V4_C128_STATE` |
| 10 | DRAFT | `DRAFT` |
| 11 | DRAFT_INDEXER | `DRAFT_INDEXER` |
| 12 | DRAFT_SWA | `DRAFT_SWA` |
| 255 | OTHER | reserved; only for a future pool added without an enum bump |

`component` is derived from `PoolName`'s **value** at write time, not from parsing the storage-key
suffix; `OTHER` is lossy and is only allowed when the pool is not one of the 13, in which case the
storage key still disambiguates at runtime and recovery only needs the key. The persisted record
also carries `group_epoch`/`group_seq`, so no correctness path depends on `component` parsing.

Property: the checkpoint is a **compact superset** of the WAL up to `checkpoint_lsn`, so replay
only needs WAL records with `seq > checkpoint_lsn`.

The runtime `_index` may keep `key -> ExtentRef{extent_id, offset, length, generation}` and derive
component from the key for the hot path (see §12, decision D5). The persisted contract is the
five-tuple plus group identity; nothing about it depends on the in-RAM struct shape.

---

## 4. WAL record format and the durable-ACK boundary

### 4.0 Group identity (D-03 repair)

`operation.id` is **not** used as the durable group id. It is a per-process class counter reset at
start (`cache_controller.py:259,283-284`); reusing it would let a `GROUP_COMMIT(G)` from run N+1
validate an incomplete group with the same `G` from run N (W3), and the first op of a run has
`id=0`, which would collide with "ungrouped" (W4).

**DECIDED durable identity (D7 = (a); `USER-RULING-20260912-G1`, 2026-09-12):**

* `namespace_epoch`: 16-byte random id from a **CSPRNG**, minted at first metadata initialization,
  re-minted at each process open (clean or crash; per writer/runtime incarnation), and persisted in
  the manifest and in WAL/group metadata. It is the run's durable identity. An all-zero epoch is
  FORBIDDEN for any normal grouped operation.
* `group_seq`: a per-run `u64` monotonic counter starting at **1**, allocated under the writer
  sequencer. `group_id = (namespace_epoch, group_seq)`.
* `(epoch=0, seq=0)` is reserved as **ungrouped** (ungrouped writes carry this).
* A group is `COMPLETE` iff a durable `GROUP_COMMIT(epoch, seq, member_count)` exists with matching
  members. Recovery only completes a group whose entries carry the **same** `(epoch, seq)`.
* Cross-run safety: run N+1 mints `epoch' != epoch`; a `GROUP_COMMIT(epoch', seq')` can never match
  run-N entries, so a prior run's incomplete group is always discarded (never validated).

KV and Mamba sidecar entries use the **IDENTICAL** `(namespace_epoch, group_seq)`. This changes the
hybrid KV+sidecar identity contract; it is surfaced as **D7** in §15 and is **DECIDED (a)** by
`USER-RULING-20260912-G1`: chosen over a persisted monotonic counter because there is no
self-referential crash-safety loop, no run-count leak, and the 128-bit collision probability is
negligible. Implementation is authorized under the ruling.

### 4.1 Segment header

Each `hicache.meta{config_suffix}.wal.<gen>` begins with:
`magic (4) | format_version (2) | flags (2) | segment_generation (u64) | base_lsn (u64) | crc32c`.
`base_lsn` is the highest checkpoint lsn known when the segment was created (0 for a fresh store).
The segment header is written and fsynced **before** the segment becomes reachable from
`.wal.current` (TKV-CODE-024 analogue: durable discriminator before publication).

### 4.2 Frames (D-11 repaired)

```text
offset  0   4   magic (4)
offset  4   2   format_version (2)
offset  6   1   type (1)
offset  7   1   flags (1)
offset  8   2   reserved (2)
offset 10   4   payload_len (4)
offset 14   8   seq (u64)
offset 22   4   crc32c(header[0..22) || payload) (4)      # CRC covers bytes 0..21 only
offset 26   ... payload
```

The CRC field is at bytes 22-25; the checksummed range is `header[0..22)` (magic through `seq`),
**excluding** the CRC field itself. (Prior text said `header[0..24)`, which overlapped the CRC;
fixed.)

* `seq` is a strictly increasing, gap-free per-namespace WAL sequence (LSN) allocated by the
  single writer (`NM-INV-13`). A gap or non-monotonic `seq` is fail-closed on replay.
* `payload_len` is bounded by `wal_max_record_bytes` (proposal: `min(8 MiB, extent_size)`); a frame
  whose `payload_len` exceeds the bound is a malformed frame -> fail closed.
* `type`:

| type | payload |
|---|---|
| `SET` = 1 | `group_epoch (16)`, `group_seq (u64)`, `batch_id (u64)`, `member_index (u32)`, `member_count (u32)`, entries[(key,extent_id,offset,length,generation,component)] |
| `BATCH_COMMIT` = 2 | `batch_id (u64)`, `member_count (u32)` |
| `GROUP_COMMIT` = 3 | `group_epoch (16)`, `group_seq (u64)`, `member_count (u32)` |
| `DROP_SLOT` = 4 | `slot (u32)`, `new_generation (u64)` |
| `CLEAR` = 5 | `epoch (u64)` (a monotonic marker; generations stay monotonic) |
| `CHECKPOINT_MARK` = 6 | `checkpoint_lsn (u64)` (advisory; also derivable from the manifest) |

* A write of many pages may exceed `wal_max_record_bytes`; it then emits N `SET` frames with the
  same `batch_id`, distinct `member_index`, shared `member_count`, followed by a `BATCH_COMMIT`.
  **Recovery indexes a batch's entries only if its `BATCH_COMMIT` is durable** (all-or-nothing for
  the write batch).
* `GROUP_COMMIT` is the cross-pool (KV + sidecar) successor of the group's last member batch. It
  carries the same `(group_epoch, group_seq)` as its entries. Recovery keeps a grouped entry only
  if its `(group_epoch, group_seq)` has a durable `GROUP_COMMIT`.

### 4.3 The exact durable-ACK boundary (D-01 / D-06 / D-07 / D-08 repaired)

Today the ACK is `pwritev` success + `_allocator.commit` (`_write_pages:1124-1160`,
`batch_set_v1:625-667`). G1 replaces the ACK point. The **write-ahead invalidation rule** D-01:
*no data `pwrite` may clobber a slot that currently backs a durable live entry until that slot's
`DROP_SLOT`+new generation is durable AND the RAM generation bump/index removal is applied.*

Single writer sequencer (D-06): `_write_gate` is the **sequencer** held by the group leader; group
formation happens under it and only the leader plans/pwrites/applies. Followers submit requests and
wait for the leader's result; they never plan or pwrite independently. Thus "group commit shares
one fsync" and "only one writer touches a slot at a time" are both true.

```text
WRITE (leader holds _write_gate; group members are handled in arrival order):
1. under _lock: select_gc_victims()  [PURE, no mutation];
                 plan(pending_drops) -> (refs, passed, drop_events)   [PURE]
       * pending_drops = the set of GC-victim slots selected in this step (a slot to be evicted by
         watermark/LRU policy; it is NOT necessarily in the circular `passed` set). Each victim's
         `pending_gen[s]` is computed by the NEW-1 formula below.
       * generation (NEW-1; **unified form mandated unconditionally**, R3 hardening):
             pending_gen[s] = _generations[s] + max(passed.count(s),
                                                    1 if s in pending_drops else 0)
             ref.gen        = pending_gen[slot]     # the slot the key is placed into
             DROP_SLOT.new_gen == pending_gen[s]    # exact equality, no re-derivation
         `passed.count(s)` is the number of times this plan wraps the cursor into slot `s` (the
         existing packed guard makes it at most 1). The `max(...)` bumps any slot in `passed`,
         `pending_drops`, or **both** exactly once: overlap is tolerated and never double-counted,
         so no `pending_drops ∩ passed = ∅` precondition is needed. plan accepts pending_drops and
         computes placement/ref generations exactly as if `_drop_slot` had been applied (cursor
         reset to 0, slot empty) exactly once per dropped slot; plan stays pure.
       * drop_events = {(s, pending_gen[s]) : s in passed UNION pending_drops_slots}  (NEW-1/NEW-4)
 2. if drop_events != {} :
       append DROP_SLOT(s, ng) for every (s, ng) in drop_events    # one event per dropped slot
       fdatasync(WAL)                                   # (i) INVALIDATION DURABLE, before clobber
       under _lock: apply_drops(drop_events): remove each dropped slot's keys, set gen=ng,
         cursor=0, slot_bytes=0                          # readers can no longer verify old refs
     else: (no invalidation fsync; no RAM drop)
 3. pwritev data bytes for all members at the planned offsets
       # safe: every clobbered slot was durably invalidated and RAM-invalidated in step 2
 4. append SET...+BATCH_COMMIT for all members; append GROUP_COMMIT for a grouped operation
 5. fdatasync(WAL)                                     # (ii) DATA-PLAN DURABLE
 6. under _lock: INSTALL-ONLY commit for all members    # NEW-4: never re-run passed/_drop_slot
        * the `passed`/GC drops were already consumed in step 2; step 6 installs `_index[key]=ref`,
          updates `_slot_keys`/`_slot_bytes`, cursors, recency, and `_next_slot`
        * `commit_install` is **all-or-nothing under `_lock`**: either every member is installed and
          every installed `ref.gen == pending_gen[slot]`, or none is installed and the call raises;
          it must not leave a partial install (`NM-INV-05/19`). A validation failure here installs
          nothing, returns failure, and the backend **QUIESCES** (refuses further writes) rather
          than continue with a live index that disagrees with the durable WAL; a subsequent reopen
          deterministically re-installs the already-durable frames. (R3 minor residual.)
        * grouped members are installed only after (5) includes GROUP_COMMIT, see D-08
 7. return ACK (True / per-transfer results); release _write_gate

CLEAR (NEW-5): clear()/detach/reset acquire _write_gate before appending a CLEAR frame and
  fdatasync(WAL); while an in-flight group is mid-sequence no CLEAR may interleave, so WAL order
  always matches live RAM order. (See the clear path below.)
```

**D1 (RULED 2026-09-12, binding): process-crash semantics and the data-before-commit hard
invariant (`NM-INV-20`).** D1 = (b). For SIGKILL / process crash: every operation that completed a
WAL-durable commit AND was ACKed to the upper layer MUST be recoverable after restart. For power
loss / kernel crash: extent DATA BYTES are explicitly NOT promised on stable media — a separate,
stronger durability tier that this design does not claim. HARD INVARIANT: the extent data write
(step 3) must be completed to the kernel/page-cache BEFORE the WAL `GROUP_COMMIT` (or
`BATCH_COMMIT` for an ungrouped write) becomes durable (step 5) AND BEFORE the upper-layer ACK
(step 7). The interleaving `WAL durable -> ACK -> data write not yet complete` is FORBIDDEN.
Oracle `NM-F-22` asserts this ordering; the crash acceptance oracle tests ONLY SIGKILL/process
restart and is labelled as such — it is never packaged as power-loss durability.

Ordering direction: **invalidation durable -> RAM invalidation -> data clobber -> data-plan durable
-> RAM install -> ACK.** Consequences:

* **Crash before step 2's fsync:** no `DROP_SLOT` durable and no clobber persisted (the pwrite has
  not happened); the old entry remains valid -> recovered correctly. No false ACK (none was given).
* **Crash after step 2's fsync, before step 3:** `DROP_SLOT` durable, RAM drop applied; recovery
  drops the old keys. The new batch was never ACKed and is not indexed. Correct.
* **Crash after step 5, before step 6:** `SET`/`BATCH_COMMIT` (and `GROUP_COMMIT`) durable; recovery
  rebuilds the new entries; ACK may or may not have been returned, but a returned ACK implies
  durability. Correct.
* **Concurrent reader (W1 5b, no crash):** a reader that snapshotted an old ref before step 2's RAM
  drop preads possibly after step 3; its re-verify under `_lock` compares `_index.get(key) == ref`,
  but the key was removed in step 2 -> verify fails -> miss and the bytes are discarded. No
  clobbered bytes are ever served.
* **Cost:** one `fdatasync` on a fresh append (no reuse); **two** `fdatasync` when any slot is
  reused/evicted. Group commit still amortizes each fsync across the bounded group.

**D-07 (failed group).** RAM drops are applied only after their `DROP_SLOT` is durable (step 2).
If the data pwrite (step 3) or the data fsync (step 5) then fails, no new entries are installed and
the group is not ACKed, but the already-durable eviction/reuse drops remain in effect — the index
reflects exactly the durable prefix. This is cache degradation, not corruption, and is stated
explicitly (NM-F-05/NM-F-11 repaired; the prior "index unchanged on failure" claim is removed).

**D-08 (in-process group failure).** For a grouped operation, no KV or sidecar entry becomes
visible in the live process before its `GROUP_COMMIT` is durable (step 6 happens only after step 5
includes `GROUP_COMMIT`). If `GROUP_COMMIT` cannot be made durable, the staged group members are
discarded (no install) and the KV/operation returns failure; the live process therefore never
serves a group that recovery would consider incomplete. NM-INV-08 covers the live process and
recovery.

**NEW-4 (split `commit` API; single generation bump).** The current
`ExtentAllocator.commit` re-applies drops internally (`for slot in passed: self._drop_slot(...)`,
`extent_allocator.py:223-226`) and then installs refs (`:234`). Re-running that at step 6 would bump
each reused/GC slot generation a **second** time after step 2, so every `ref.gen` computed in
plan step 1 would be born stale and immediately miss (and the D-05 fold would mismatch). The API is
split exactly:

* `plan(key_lengths, pending_drops) -> (refs, passed, drop_events)`: **pure**; `drop_events` is the
  list of `(slot, new_generation)` for `passed` slots (and any caller-supplied GC victims), with
  `new_generation` computed by the NEW-1 formula. It does not mutate `_index`, `_generations`,
  `_cursors`, `_slot_keys`, `_slot_bytes`, or `_recency`.
* `apply_drops(drop_events)`: the **only** method that bumps generations and removes keys; called
  once in step 2, after the `DROP_SLOT` fsync. Idempotent per `(slot, new_generation)`.
* `commit_install(keys, refs)`: **install-only**. It must NOT call `_drop_slot` and must NOT read
  or re-apply `passed`. It performs exactly the `:227-240` body (unlink old ref accounting for a
  rewritten key, set `_index[key]=ref`, update `_slot_keys`/`_slot_bytes`, advance `_cursors`,
  refresh `_recency`, set `_next_slot`).

Backward-compatibility shim (proposal, behind the metadata gate off): the old `commit(keys, refs,
passed)` may remain as `apply_drops(...); commit_install(...)` so that the current unit tests and
the feature-off path are byte-equivalent. With the gate on, step 2 and step 6 call the two methods
separately. This is the exact split that keeps the generation monotonic and the fold consistent
(oracle `NM-F-21`).

**D-02 (tail repair; NEW-2 resolution = option (a)).** On replay, a torn final frame of the active
segment is tolerated only after the segment is repaired **in place**:
`ftruncate(active_fd, last_valid_offset)` then `fdatasync(active_fd)`. `next seq = last_valid_seq+1`.
The R1 alternative "rotate to a fresh segment and abandon the partial tail" is **deleted**: it left
the torn frame in a now-non-active segment that the next restart classifies as interior corruption
-> FAIL CLOSED. The sole repair path is in-place `ftruncate`+`fdatasync` (option (a), the simplest
provable choice). No append may ever follow a partial frame without this repair, and no tolerated
tail may survive in a non-active segment. See §5 and NM-F-17.

`clear()` and checkpoint carry the same fsync discipline; `batch_set_v2`'s per-transfer `True` for
grouped members implies `GROUP_COMMIT` durability. **NEW-5:** `clear()`/detach/reset take
`_write_gate` before appending `CLEAR` (they are not allowed to interleave with an in-flight
group), so `clear()` is a quiescent-only operation and `CLEAR` never lands between a group's
`BATCH_COMMIT` and its `GROUP_COMMIT`.

### 4.4 Cost bound (RP-RDB-010 / RP-RDB-012 / RP-RDB-014)

* One `fdatasync(WAL)` per **group per phase**; a reuse-free group pays one, a group that reuses or
  evicts pays two (invalidation + data-plan). Groups are bounded by `max_group_bytes` and
  `max_group_records` (both finite) under the leader sequencer (RP-RDB-010/011/012/014).
* No unbounded wait: a group closes on a bounded trigger (leader timeout / fill) and never
  busy-spins (FAIL-ANTI-037). A failed fsync/short append fails the whole group; the WAL is
  truncated to the **post-drop boundary**, not blindly to the pre-group offset: capture
  `pre_group_offset` before step 1; if step 2 appended and fsynced one or more `DROP_SLOT` frames,
  the truncation offset is the byte immediately after the last durable `DROP_SLOT` frame of this
  group (`post_drop_offset`), and every frame this group appended after it (`SET`/`BATCH_COMMIT`/
  `GROUP_COMMIT`) is removed; if step 2 emitted no frame, the boundary is `pre_group_offset`. The
  truncation is followed by `fdatasync(WAL)` before `_write_gate` is released. Because step 2 appends
  all of the group's `DROP_SLOT`s before any other frame, `post_drop_offset` is well defined and
  monotonic. Already-durable `DROP_SLOT` invalidations are never rolled back (a committed, intended
  eviction). (R3 minor residual; RP-RDB-015/020.)
* Metadata volume per write is `O(pages)` small fixed records (no payload duplication); replay
  memory is bounded by `entries` and by the manifests, not by data size.
* `fdatasync(WAL)` is issued **without** holding the logical index lock (step 2/5 run outside
  `_lock`), so a slow fsync cannot serialize readers or unrelated logical-state work (RP-RDB-008).
* Power-loss (not process-crash) durability of the **data** bytes is a separate, stronger claim
  that needs `fdatasync(data_fd)` too; see §15 decision D2 (RULED **(a) WAL `fdatasync` only**).
  The D1(b) boundary above is sufficient for the real SIGKILL/process kill/reopen oracle the E2E
  test uses; it is NOT a power-loss claim (`NM-INV-20`).

---

## 5. Restart algorithm (D-02, D-05 repaired)

```text
open(data)                       # O_CREAT|O_RDWR + ftruncate, exactly as today
acquire meta lock                # fcntl.flock(LOCK_EX) single-writer fence (NM-INV-13, NEW-6)
read .wal.current                # atomic pointer -> ACTIVE segment generation G_active (W5)
read manifest hicache.meta{sfx}.manifest (if any):   # W5: must precede enumeration
  absent:
      if a fresh empty data file / no prior metadata -> initialize metadata (file_uuid,
        namespace_epoch, empty checkpoint); start cold (NO data scan); wal_floor = G_active
      if data file existed with allocated blocks but no manifest -> cold start (D1(b) RULED: no
        committed metadata/WAL exists, so no durable fact is lost)
  present:
      verify magic / format_version / crc32c / geometry / data dev+ino guard
      any failure -> FAIL CLOSED (D3(a) RULED; committed-region corruption is never salvaged)
      checkpoint_lsn = manifest.checkpoint_lsn; wal_floor = manifest.wal_floor
resolve the active-generation range (NEW-11/R3; wal_floor is the enumeration floor, .wal.current the
active pointer):
   * wal_floor <= G_active: NORMAL; enumerate the contiguous range [wal_floor, G_active].
   * wal_floor == G_active+1: BENIGN "checkpoint published, rotation pending" (§6 crash window
     between steps 4 and 5). The §6 exclusive barrier guarantees no record with seq > checkpoint_lsn
     was appended while the gate was held, so the segment below the floor is fully covered by the
     checkpoint snapshot and there is nothing above the floor to lose. Promote: set
     G_active := wal_floor; validate/recreate hicache.meta{sfx}.wal.<wal_floor> (next bullet);
     publish .wal.current := wal_floor (fsync dir); enumerate [wal_floor, wal_floor]. This is NOT
     an error: the inverted/empty textual range [wal_floor, G_active] is exactly this state.
   * wal_floor > G_active+1: FAIL CLOSED (cannot arise under the §6 exclusive barrier).
   * manifest absent: the range is [G_active, G_active] and wal_floor := G_active. If the manifest
     is absent while any durable WAL segment exists, or if `.wal.current` is absent with any prior
     metadata present (so `G_active` cannot be resolved), recovery FAILS CLOSED and never silently
      discards durable WAL segments or cold-starts; this branch is governed by D1(b) (allowed
      recovered prefix) and D3(a) (fail-closed vs salvage), both RULED 2026-09-12 (R3 residual).
enumerate WAL segments (W5; NO directory traversal):
   * open only exactly-named paths, one per generation in the resolved contiguous range:
       for g in [wal_floor, G_active]:  open hicache.meta{sfx}.wal.<g>   (no listdir)
   * every generation in the range must exist with a valid header; a missing (ENOENT) or malformed
     in-range segment -> FAIL CLOSED (by construction no reclamation removes a segment >= wal_floor,
     so a missing in-range segment means durable records were lost)
     EXCEPTION (same-generation partial-header orphan): a segment at exactly wal_floor in the
     promoted wal_floor == old G_active+1 state was never published to .wal.current and cannot hold
     a valid frame. If it exists with a short/partial/invalid header, repair it in place instead of
     failing: `os.ftruncate(fd, 0)` (equivalently reopen `O_TRUNC`), write the valid header
     (`base_lsn = checkpoint_lsn`) at offset 0, `fdatasync`, then publish `.wal.current` (R3
     residual; §6 step 5).
   * bounded orphan probe (at most ONE stat, never a listdir): stat
     hicache.meta{sfx}.wal.<G_active+1>; if it exists with an invalid/partial header it is
     reported as an orphan and is NOT opened/trusted, unless it is exactly the promoted wal_floor of
     the pending-rotation state above (then it is repaired, never trusted as-is)
   * a segment named by .wal.current (or, in the normal non-promoted case, by the manifest) with an
     invalid header -> FAIL CLOSED
   * an unreferenced segment with generation > G_active+1 is out of the enumeration and inert
restore checkpoint state (index, generations, cursors, slot accounting, recency, groups)
mint a NEW namespace_epoch for this run; persist it (groups from prior epochs are never
completable)
replay WAL segments with any record seq > checkpoint_lsn, in ascending segment generation:
  validate segment header (magic/version/crc)
  read frames sequentially:
    - clean end of segment -> next segment
    - FINAL frame of the ACTIVE segment is short/truncated/crc-bad -> tolerate:
      stop at last fully valid frame; REPAIR IN PLACE before any further append (NEW-2 option (a)):
        ftruncate(active_fd, last_valid_offset); fdatasync(active_fd)
        # there is NO rotate-and-abandon path; the torn frame must not survive in any segment
      record the discarded tail (NOT indexed)
    - any interior/earlier frame malformed, bad crc, bad magic, bad type, duplicate/gap seq
      -> FAIL CLOSED
  apply in seq order (idempotent upsert):
    SET (pending until commit)     -> stage entries by (epoch,seq,batch_id)
    BATCH_COMMIT(batch_id)         -> mark batch complete; entries become index candidates
    GROUP_COMMIT(epoch,seq)        -> mark that (epoch,seq) complete (only same-epoch entries
                                      can be completed)
    DROP_SLOT(slot,new_gen)        -> remove slot's keys; set generation; validate new_gen >
                                      current generation else FAIL CLOSED
    CLEAR(epoch)                   -> clear index/accounting/cursors; keep generations
after replay:
  for every staged entry whose batch is not complete -> discard (write all-or-nothing)
  for every entry whose (epoch,seq)!=(0,0) and group is not COMPLETE -> discard
      (KV+sidecar all-or-nothing); record the drop
  install remaining entries into the RAM index
derive + cross-check (D-05 repaired; NEW-3):
  replay maintains an `expected` fold: start from checkpoint slot_bytes/cursors/generations and
  apply the same DROP_SLOT/CLEAR transitions during replay
  a SET contributes to the fold ONLY when its batch is complete AND (if grouped) its group is
  COMPLETE — i.e. exactly the same predicate as the install decision above; a staged-but-discarded
  SET must NOT be folded, or a valid WAL ending in an incomplete group would spuriously FAIL CLOSED
  recompute derived _slot_keys/_slot_bytes/cursors from the installed index
  compare derived against the POST-REPLAY `expected` fold (NOT the raw checkpoint values);
  exact integer/set equality; any mismatch -> FAIL CLOSED
allocate the next WAL seq = max(seen seq)+1 (or checkpoint_lsn+1)
open the active segment in append mode at the repaired offset; install-only commit for this run
publish allocator/backend; begin serving
```

**Tolerated vs fail-closed (exact):**

| condition | action |
|---|---|
| short/truncated/bad-crc **final** frame of the **active** segment | tolerate, then in-place `ftruncate`+`fdatasync` to last valid offset **before any append**; no rotate-and-abandon (D-02/NEW-2) (`NM-F-04`, `NM-F-17`) |
| bad magic/version/crc/checksum, unknown type, malformed length, interior gap/duplicate seq, interior corruption | fail closed (`NM-F-05`) |
| manifest bad magic/version/crc, geometry mismatch, data dev/ino mismatch (committed region) | fail closed (`NM-F-06`); D3(a) RULED — never auto-truncate/salvage/serve, never silently cold-start pretending durability |
| `DROP_SLOT` new_generation <= current, or a `SET` generation for a reused slot smaller than the restored generation, or generation outside `u64` monotonic range | fail closed (`NM-F-07`) |
| post-replay derived accounting != post-replay expected fold | fail closed (`NM-INV-02`) |
| `wal_floor == G_active+1` (manifest published, rotation pending) | BENIGN: promote `G_active := wal_floor`, validate/recreate its header, publish `.wal.current`; replay `[wal_floor, wal_floor]`; never an error and never data loss under the §6 exclusive barrier (`NM-F-13`; NEW-11/R3) |
| `wal_floor > G_active+1` | fail closed (impossible under the §6 exclusive barrier; a gap means the manifest floor and `.wal.current` disagree beyond the single pending-rotation step) |
| same-generation partial-header segment at the promoted `wal_floor` | repair in place: `ftruncate(fd,0)`/`O_TRUNC`, write valid header (`base_lsn = checkpoint_lsn`), `fdatasync`, publish `.wal.current`; never published active, so it cannot hold a valid frame (R3 residual) |
| manifest `wal_active_gen` differs from `.wal.current` after a completed rotation | **validation-only, not corruption.** `wal_active_gen` is a checkpoint-time hint; `.wal.current` is authoritative for `G_active`. A newer active generation is expected and must not be treated as a mismatch or as damage (R3 residual) |
| orphan/unreferenced WAL segment (W5) | never enumerated as active (W5 rule above): recovery opens the resolved contiguous named range `[wal_floor, G_active]` (manifest floor + `.wal.current`), never a listdir; each in-range generation must exist with a valid header (missing/malformed -> FAIL CLOSED, except the repaired pending-rotation case); a bounded one-`stat` probe of `G_active+1` may **report** but never trust an orphan with an invalid header; generations `> G_active+1` are inert (`NM-F-20`) |
| no metadata at all but a non-empty data file | cold start under D1(b) (RULED): no committed metadata/WAL exists, so no durable fact is lost; D3(a) fail-closed covers committed-region corruption only, never metadata absence |

Fail-closed means: the backend constructor raises a typed recovery error; the process does not
publish an allocator, does not serve reads/writes from partial state, and does not silently start
cold. The error names the file, the LSN/offset, and the failure class.

**D3 (RULED (a), `USER-RULING-20260912-G1`, 2026-09-12).** Committed manifest/WAL corruption ->
refuse to start that cache namespace (fail closed); no committed-region auto-truncation/salvage is
served, and there is no silent cold-start pretending durability is intact. The designed torn
**ACTIVE** tail/frame repair (D-02/`NM-INV-17`, `NM-F-04/17`) is unchanged and is the only
tolerated repair. Rationale to record: wrong resurrection of KV+Mamba state is far worse than a
cache miss.

Replay is deterministic and idempotent: it depends only on byte content and the single total order
`seq`, never on directory enumeration order, thread scheduling, or wall-clock (`NM-INV-14`).

---

## 6. Checkpoint creation, WAL rotation, truncation (D-04 repaired)

Checkpoint triggers (proposal): `close()` (graceful quiescent point), WAL size beyond
`wal_max_bytes`, and controller detach/reset.

**Quiesce barrier (D-04 / NEW-11).** `checkpoint()` acquires `_write_gate` **exclusively** and holds
it through step 6 (publish + rotation + unlink); it is released only at step 7. While it is held, no
writer may plan, pwrite, or append. The R2 "release the gate after step 4" optimization is
**DELETED** (R3). Releasing early would let a writer append `seq > L` into the still-active
`G_active` segment after the manifest already published `wal_floor = G_active+1`, so a crash before
rotation would reopen with an inverted range `[wal_floor, G_active]` and would not replay the
segment holding the ACKed records. With the exclusive hold, no record with `seq > L` can exist until
rotation completes.

Because `_write_gate` is held by a write group from step 1 through step 7 (§4.3), `checkpoint()`
cannot acquire it while any group is in flight; therefore `L` is the last **applied** and last
**durable** seq, and no WAL frame with `seq > L` exists at step 3. This is what makes the
`wal_floor == G_active + 1` promotion in the (4)-(5) window lossless.

`wal_floor` is the smallest segment generation that may contain a record with `seq > L`. At the
moment the manifest publishes (step 4) rotation has not happened yet, so the smallest such
generation is the one step 5 will create: `wal_floor = G_active+1` (`G_active` = the active
generation at step 1). The normal post-checkpoint state is therefore `wal_floor == G_active` (the
rotated-to generation); the only in-flight state is `wal_floor == .wal.current + 1` (the
pending-rotation window), which §5 recovery handles by promotion. `wal_floor` can never exceed
`G_active + 1`, and the recovery range is never empty.

```text
checkpoint():
  1. acquire _write_gate (exclusive); quiesce writers at a seq boundary L = last applied seq
  2. snapshot allocator (+ resolve all incomplete groups by dropping their members)
  3. serialize manifest to  hicache.meta{sfx}.manifest.tmp
       * payload includes checkpoint_lsn=L, wal_floor = G_active+1, wal_active_gen = G_active
         (W5 enumeration contract)
  4. fdatasync(tmp); rename(tmp -> .manifest); fsync(dir)          # atomic publish
  5. rotate WAL:  let new = G_active+1
       create  .wal.<new> with O_CREAT|O_TRUNC (recycle a leftover/partial-header file);
         write+fsync the segment header(base_lsn=L) at offset 0; fsync(dir)
       atomically replace  .wal.current  -> new; fsync(dir)        # publish new active
  6. unlink EXACTLY the generations strictly below the published wal_floor (== generations < new).
     Under the exclusive barrier this set is IDENTICAL to { g : max_seq(g) <= L }: no segment >=
     wal_floor exists before step 5, none can receive seq > L while the gate is held, and every
     segment < wal_floor is fully covered by checkpoint_lsn = L. The two rules are therefore one
     rule, not two alternatives.
  7. release _write_gate
```

`wal_floor` + `.wal.current` are the recovery enumeration source (W5): recovery opens the resolved
contiguous named range `[wal_floor, G_active]` (with the §5 promotion rule) and never lists a
directory. The unlink set is exactly the generations strictly below `wal_floor`; `wal_floor` and
every generation at or above it are retained. A crash between steps 4 and 6 leaves extra old
segments below `wal_floor`; they are fully covered by `checkpoint_lsn = L` and are not opened
(opening starts at `wal_floor`). `close()` and `detach/reset` use the same exclusive barrier and the
same enumeration record.

Crash windows (exclusive barrier; NEW-11):
* before (4): old manifest + old WAL are consistent; replay from the old `checkpoint_lsn`; the range
  `[old wal_floor, G_active]` is non-empty.
* between (4) and (5): the new manifest publishes `checkpoint_lsn = L` and `wal_floor = gen+1` while
  `.wal.current` still names `gen`. Recovery sees `wal_floor == G_active + 1`, the benign
  "checkpoint published, rotation pending" state of §5: because the gate was held, `gen` holds only
  records `<= L` (nothing above the floor exists), so recovery promotes `.wal.current` to `gen+1`
  (creating/repairing its header if needed) and starts appends at `L+1`. No durable record is lost;
  the inverted/empty textual range is never an error under this rule.
* between (5) and (6): `.wal.current` names `gen+1` and the manifest floor is `gen+1`, so the range
  `[gen+1, gen+1]` is normal; `gen` is below the floor, covered, and inert; unlink is idempotent.
* during (6): with the exclusive barrier, writers are quiesced; every segment that may hold
  `seq > L` is at or above `wal_floor` and is retained; only generations `< wal_floor` are unlinked.

Recovery opens the manifest, `.wal.current`, and the resolved named range only; it never lists a
directory and never scans the data file. Bounded replay: segments whose max seq is
`<= checkpoint_lsn` are skipped. `wal_active_gen` in the manifest is a checkpoint-time hint used
only for validation/diagnostics; after a completed rotation `.wal.current` is newer, which is
expected and is not corruption.

`CLEAR` is durable: `clear()` acquires `_write_gate` (NEW-5), appends a `CLEAR` frame, and fsyncs
before returning `True`; a crash around it leaves either the pre-clear state or the cleared state,
never a half-clear (`NM-F-09`). Because it requires the writer sequencer, `clear()` is
quiescent-only and cannot land between a group's `BATCH_COMMIT` and its `GROUP_COMMIT`.

---

## 7. Generations across restart

Today `_generations` is per-slot RAM only (`extent_allocator.py:124`) and is bumped only in
`_drop_slot` (`:303`). G1 persists it two ways:

* the checkpoint stores `generations[num_slots]`;
* every `_drop_slot` emits a durable `DROP_SLOT(slot, new_generation)` **before** the clobbering
  pwrite (§4.3 step 2).

On restart, generations are restored from the checkpoint and advanced by replay. Invariants:
`new_generation` is strictly greater than the restored value (a non-increase is impossible -> fail
closed); generations are monotonic across `clear`; an `ExtentRef` whose `generation` does not equal
the restored slot generation is a miss exactly as today (`lookup`/`verify`
`extent_allocator.py:138-163`), so a stale reference can never read reused bytes. This preserves
the existing generation-based invalidation while making it survive restart (`NM-INV-06`).

**NEW-1 (exact generation; unified form mandated unconditionally; R3 hardening).** The old R1
wording was wrong for a GC victim that is **not** in `passed`: it yielded `ref.gen = _generations[s]`
while step 2 set `_generations[s] = g+1` and wrote `DROP_SLOT(s, g+1)`, so the entry was born stale
and the next recovery would fail closed (`NM-F-07`). R2 patched this with a disjointness
precondition that the §4.3 prose then contradicted. R3 removes the split: the single unified form
below is mandated and needs no disjointness precondition.

```text
pending_gen[s] = _generations[s] + max(passed.count(s), 1 if s in pending_drops else 0)
ref.gen        = pending_gen[slot]          # slot is where the key is placed
DROP_SLOT.new_gen == pending_gen[s]         # exact equality with the formula, no re-derivation
drop_events    = {(s, pending_gen[s]) : s in passed UNION pending_drops}
```

`passed.count(s)` is the number of times this single plan wraps the cursor into slot `s` (the
existing `packed` guard makes it at most 1, `extent_allocator.py:195-198`). The `max(...)` bumps any
slot in `passed`, `pending_drops`, or **both** exactly once, so overlap is tolerated and never
double-counted, and each dropped slot emits exactly one `DROP_SLOT`. `apply_drops` then sets
`_generations[s] = pending_gen[s]` and the install step (`commit_install`) stores `ref.gen`
unchanged. `plan` remains pure and `pending_gen` is computed entirely from the pre-plan
`_generations` plus this plan's `passed`/`pending_drops` sets, so replaying the same plan yields the
same refs (`NM-INV-06`, `NM-INV-19`). Idempotence: `apply_drops` is keyed by `(slot, new_generation)`
and is a no-op if `_generations[s]` already equals `new_generation`.

---

## 8. GC / eviction / invalidation recoverability (D-01, D-07 repaired)

| path | today | G1 durable representation |
|---|---|---|
| `ExtentAllocator._drop_slot` (`:288-333`) | RAM remove + generation bump | emit `DROP_SLOT(slot,new_generation)` and fsync **before** the clobbering pwrite; RAM mutation only after that fsync |
| `commit` applies `passed` drops (`:223-226`) | RAM-only, and re-applied at install | **split (NEW-4):** `plan` returns `passed` + `drop_events`; `apply_drops(drop_events)` runs once in the invalidation phase (step 2) after the `DROP_SLOT` fsync; `commit_install(keys, refs)` at step 6 is install-only and must NOT call `_drop_slot` or re-read `passed` |
| `evict_slot_lru` (`:244-256`) from `select_gc_victims`/`_gc_evict` (`extent_file_backend.py:1164-1187`) | RAM-only, mutated before pwrite | selection is **pure** during planning; `DROP_SLOT` durable + fsync before RAM mutation; RAM mutation before pwrite |
| `clear` (`:258-284`) | RAM-only, generations kept | `CLEAR` frame + fsync before `clear()` returns `True`; generations kept; **clear/detach/reset take `_write_gate` (NEW-5)** |
| LRU recency (`_recency`) | RAM-only policy | checkpoint stores an approximate order; policy state need not be exact for correctness. The binding invariant is no resurrection of an invalidated key; recency may be reconstructed conservatively |

A key invalidated before a crash must not reappear after reopen, and a slot's generation bump must
persist (`NM-INV-07`). On a failed data pwrite/fsync, the already-durable eviction drops remain
applied (D-07); no new entries are installed. To keep the allocator filesystem-free (its docstring
contract, `extent_allocator.py:11-15`), the backend writes the journal; `plan`/`evict` return
events.

---

## 9. KV + sidecar atomic group (all-or-nothing across restart and in the live process; D-03, D-08)

**Group identity = the durable `(namespace_epoch, group_seq)` of §4.0**, not `operation.id`.
**NEW-9 (single allocation owner):** the **backend** is the sole allocator of `group_seq`; the
hybrid controller only *opens* and *commits* a group around an operation:

```text
hybrid/cache_controller:  gid = backend.open_group()      # allocates (namespace_epoch, group_seq)
                          ... batch_set_v2(sidecars, gid) / _write_pages(kv, gid) ...
                          ok = backend.commit_group(gid)  # durable GROUP_COMMIT or failure
```

`open_group()`/`commit_group()` run under the backend's `_write_gate`/writer sequencer, so `group_seq`
is allocated in the same single-writer order that controls the WAL and the fsync (contract §11);
novel §4 agrees. The controller never mints an id and never reuses `operation.id`. This changes the
hybrid identity contract and is **decision D7** (§15).

Ordering and representation:

```text
sidecar batch(s):  SET(group_epoch=E, group_seq=S, batch_id=b1,...) ... BATCH_COMMIT(b1)
KV batch:          SET(group_epoch=E, group_seq=S, batch_id=b2,...) ... BATCH_COMMIT(b2)
group commit:      GROUP_COMMIT(E, S, member_count=all members)   -> durable
                   only then install the group's entries and return the KV ACK
```

* Live process (D-08): grouped KV and sidecar entries are staged but **not installed/visible**
  until `GROUP_COMMIT(E,S)` is durable. On failure they are discarded and the operation returns
  failure. So the live process can never serve a group that recovery would drop.
* Recovery keeps only entries whose `(epoch,seq)` is `COMPLETE` and matches a durable
  `GROUP_COMMIT`; a run-N incomplete group can never be completed by run N+1 (`epoch' != epoch`,
  W3), and `(0,0)` is reserved for ungrouped (W4).
* The existing `batch_exists_v2` `min`-fold (`:780-893`) is fed a consistent group: it can only
  report a shorter or equal prefix, never a stitched sibling.
* Ungrouped writes carry `(0,0)` and are live once their `BATCH_COMMIT` is durable.

---

## 10. Hook points and call/ordering direction

| anchor (HEAD `4f41f5bab5`) | role today | G1 hook |
|---|---|---|
| constructor `extent_file_backend.py:254-376` | config, `open` `:368`, `ftruncate` `:370`, fresh allocator `:371` | after `open`/`ftruncate`: acquire meta lock, load manifest + replay WAL, build `ExtentAllocator` from restored state; initialize metadata when absent |
| `ExtentAllocator.plan` `extent_allocator.py:172-213` | pure placement | accepts `pending_drops`; computes `pending_gen[s]` and `ref.gen = pending_gen[slot]` by the NEW-1 **unified** formula; returns `drop_events`; still pure |
| `ExtentAllocator.commit` `:215-240` (`_drop_slot` at `:223-226`, install at `:234`) | drops + install in one call | **split (NEW-4):** `apply_drops(drop_events)` once after the D-02 `DROP_SLOT` fsync; `commit_install(keys, refs)` install-only after the data-plan fsync; grouped members after `GROUP_COMMIT`. Gate-off keeps the old `commit` as the composition shim |
| `ExtentAllocator._drop_slot` `:288-333` | RAM remove + generation bump | backend emits `DROP_SLOT` + fsync before the RAM mutation and pwrite |
| `_write_pages` `extent_file_backend.py:1124-1160` | `gc -> plan -> pwritev -> commit -> True` | steps 1-7 of §4.3 including the invalidation phase |
| `batch_set_v1` `:598-667` | same sequence under `self._lock` | same, using the sequencer |
| `batch_set_v2` `:963-1049` | per-transfer `_write_pages` | same, plus durable group id and deferred visibility |
| `_gc_evict` `:1164-1187` / `evict_slot_lru` `:244-256` | RAM eviction | split into pure selection + durable-drop application |
| `clear` `:1189-1195` / `ExtentAllocator.clear` `:258-284` | RAM clear | take `_write_gate` (NEW-5), then `CLEAR` + fsync before `True` |
| `close` `:1209-1212` | `os.close(fd)` | quiesce -> checkpoint -> close metadata fds -> close data fd |
| controller detach `cache_controller.py:724`, `reset()` `:833`; ack `:1419` (worktree `:726`,`:835`,`:1421`); hybrid attach `hybrid_cache_controller.py:276,292,302` (worktree `:290`) | lifecycle | detach/reset triggers a durable checkpoint or clean close; no second lifecycle owner |
| hybrid `_t38c_durable_context` `:1100-1116`; `batch_set_v2` `:1060`; `super()._page_backup` `:1108`; `_t38c_operation_id` set `:837`/`:880` (worktree `:1138`,`:1094`,`:1142`,`:851`/`:899`) | trace-only | replaced by the explicit durable group-id allocation of §4.0 |

Allocator stays pure/filesystem-free; backend owns all metadata IO; metadata never depends on data
file traversal.

---

## 11. Concurrency model (D-06 repaired)

* `self._lock` is the **logical-state / read-snapshot** lock (`snapshot`/`verify`/`lookup`).
* `_write_gate` is a **G1-introduced primitive**: it does not exist at HEAD, where the backend's
  only lock is `self._lock` (`extent_file_backend.py:348`). It is the **writer sequencer** held by
  the group-commit leader (and by `checkpoint()`/`clear()`). Only the leader ever runs
  `plan`/pwrite/`DROP_SLOT`/`commit`; group followers submit requests and wait. Therefore there is
  exactly one planner/pwriter at a time, and the D-01 reuse ordering is preserved across an entire
  group. It is design-only and not implemented here.
* **Lock order is `_write_gate -> _lock`**, one-way: a holder of `_write_gate` may acquire `_lock`
  for the short allocator sections; a holder of `_lock` never acquires `_write_gate`.
  `fdatasync(WAL)` runs outside `_lock` (write-path steps 2/5 hold `_write_gate` and release only
  `_lock`). This single order is the deadlock-freedom rule; no reverse acquisition exists anywhere
  in the write/checkpoint/clear paths.
* Group commit does not run two planners concurrently; it shares the fsync. Group formation is
  bounded by `max_group_bytes`/`max_group_records` and a leader timeout; no busy-wait
  (FAIL-ANTI-037). A compatibility predicate prevents a no-fsync/no-durability request from joining
  a group whose leader cannot honor it (RP-RDB-011).
* The index lock is held only for short allocator sections and released across `fdatasync`
  (RP-RDB-008).
* Single-writer fence per `config_suffix` prevents a second process from interleaving metadata
  writes (TKV-CODE-029).

---

## 12. Oracle and test plan (mapped to NM-INV / NM-F)

Correctness oracles are external to the metadata mechanism: recover through the **real constructor
and real file IO**, compare the served key set and bytes against the pre-crash authoritative state,
and assert the durable files' on-disk content. Metrics/queue state/replay counters are diagnostics,
never truth. Correctness and benchmark results are reported separately (RP-RDB-041).

Every crash case in this plan is a **process-crash (SIGKILL/restart)** case and is labelled as such;
none is a power-loss durability claim (`NM-INV-20`, D1(b)). Committed-region corruption cases
assert fail-closed (D3(a)).

| NM-F | scenario | oracle | NM-INV | analogue |
|---|---|---|---|---|
| NM-F-01 | write N keys, graceful `close()`, reopen same dir | all keys present + byte-identical; no data scan; replay deterministic | 01,03,04,09,10,14 | RDB-C39 |
| NM-F-02 | write N keys, ACKed; real `SIGKILL`; reopen | every ACKed, non-superseded, non-invalidated key present + byte-identical | 03,04,05,14 | FDB-C08/C09, RE-050 |
| NM-F-03 | kill between data `pwrite` and WAL `fdatasync` on a fresh slot | no ACK was returned; reopen has no key/accounting; no partial group | 03,05,09 | RE-056, TKV-CODE-021 |
| NM-F-04 | truncate/garble the final WAL frame | tail discarded to last valid frame; valid prefix recovered; explicit discarded-tail record | 09,17 | FDB-IMP-09, TKV-CODE-026, RE-051 |
| NM-F-05 | flip a byte in an interior WAL frame / bad magic / bad length | typed fail-closed; no allocator published; no partial index | 02,09 | RDB-C39, RE-049 |
| NM-F-06 | corrupt/version-bump manifest / geometry mismatch / data inode swap | typed fail-closed | 02,10 | RDB-C39 |
| NM-F-07 | craft `DROP_SLOT` decreasing generation, or a reused-slot `SET` generation below restored | typed fail-closed | 06 | TKV-CODE-014 |
| NM-F-08 | fill slots to force LRU/watermark GC, then kill | evicted keys absent; generations preserved; no resurrection | 07 | FDB-IMP-14, RP-RDB-022/023 |
| NM-F-09 | `clear()`, then kill during/after | either pre-clear or fully-cleared; generations monotonic; no half-clear | 07,09 | TKV-CODE-027 |
| NM-F-10 | crash between sidecar durability and `GROUP_COMMIT` | no partial KV+sidecar group served; `min`-fold never stitches | 08,16,18 | RP-RDB-019/020 |
| NM-F-11 | inject `fdatasync` failure / short WAL append on a reuse group | group not ACKed; no new entries installed; WAL truncated to the post-drop boundary (after the last durable `DROP_SLOT`, else pre-group offset) and fsynced; durable drops retained | 03,05,12 | RP-RDB-015/020, TKV-CODE-022 |
| NM-F-12 | second concurrent opener for the same `config_suffix` | typed refusal / fence; no interleaved metadata append | 13 | TKV-CODE-029 |
| NM-F-13 | kill during checkpoint/rotation windows (before/after manifest publish, before/after `.wal.current` replace, before/after unlink), **including the manifest-published/rotation-pending window `wal_floor == G_active+1`** | every window reopens to a consistent prefix; the pending-rotation window promotes (no lost records); no durable record lost | 10,11,14,17 | FDB-IMP-11/15, TKV-CODE-024 |
| NM-F-14 | bounded soak: loop write/kill/reopen K times | no unbounded growth; deterministic recovery; every non-invalidated durable key present; memory bounded | 12,14 | RP-RDB-039, TKV-HARNESS-045 |
| NM-F-15 | W1 5a: reuse/evict a live slot, kill after the clobber but before/at the WAL fsync | reopen never serves clobbered bytes for the old key; either old key valid (no clobber persisted) or old key dropped (invalidation durable); no false ACK | 03,04,06,07,16 | D-01 |
| NM-F-16 | W1 5b: reuse/evict while a concurrent reader snapshots the old ref | reader's re-verify fails; clobbered bytes are never served; no hit on a stale generation | 06,07,16 | D-01 |
| NM-F-17 | W2: kill mid-append, reopen (tolerated tail), immediately write, kill again, reopen | second reopen succeeds; tolerated tail never becomes interior corruption; seq continuity restored | 09,17 | D-02, TKV-CODE-026 |
| NM-F-18 | W3: run 1 leaves an incomplete group (epoch E); restart mints E'; a later op gets the same `group_seq`; `GROUP_COMMIT(E',S)` | run-1 orphan group is never validated; no cross-run completion | 08,18 | D-03 |
| NM-F-19 | W4: first operation of a run | it is a valid grouped id `(E,1)`, never `(0,0)`; ungrouped is reserved for `(0,0)` only | 08,18 | D-03 |
| NM-F-20 | W5: orphan newer segment with a partial header | not enumerated as active; never validated from a partial header; reported, not silently trusted; the pending-rotation `wal_floor` segment is repaired (`O_TRUNC`+header+fsync), and `wal_floor > G_active+1` fails closed | 09,11,17 | D-02/W5 |
| NM-F-21 | W6: a plan reuses/evicts slot S (S in `passed` and/or a GC victim not in `passed`); metadata gate on, no crash | installed `ref.gen == pending_gen[S]` and `_generations[S] == pending_gen[S]`; no entry born stale; no double bump when S is both `passed` and a victim; `commit_install` installs all-or-nothing | 06,19 | NEW-1/NEW-4 |
| NM-F-22 | D1: a fresh (reuse-free) or reuse group is written and ACKed; observe the data-write vs WAL-commit vs ACK ordering (step 3 vs step 5 vs step 7) | the extent data write completes to the kernel/page-cache BEFORE the WAL `GROUP_COMMIT`/`BATCH_COMMIT` is durable AND BEFORE the ACK; the interleaving `WAL durable -> ACK -> data write not yet complete` is FORBIDDEN; process-crash (SIGKILL) only, never power-loss | 03,04,20 | D1, RP-RDB-036 |

Crash cases must use real kill/reopen (subprocess `SIGKILL`, or the real server stop/launch path),
not an in-process `close()` mock. Fault injection enters at the file boundary the production code
uses (RP-RDB-034: both IO error and checksum/corruption).

### 12.1 Re-disposition of `test_crash_reopen_all_cold`

`test/registered/unit/mem_cache/test_extent_file_backend_unit.py:461-488` asserts the **old cold
semantics**: after `close()` + reopen, every key is absent, `preads==0`, `pwrites==0`, `opens==1`.
G1 changes this oracle. It must be explicitly re-dispositioned, not silently ignored:

1. Replace the positive cold assertion with `test_crash_reopen_recovers_durable_metadata`: after
   write + close/reopen (and a SIGKILL variant), keys are present and byte-identical, and the reopen
   path performs **no data-file payload read**.
2. Keep a fallback test `test_crash_reopen_cold_when_metadata_disabled_or_absent`: with the feature
   gate off (or metadata files removed), reopen is cold exactly as before. This preserves the
   removability proof (`NM-INV-15`).
3. Metadata fds use **separate metadata counters** (D6=(a), RULED 2026-09-12 via
   `USER-RULING-20260912-G1`); the re-dispositioned tests assert the separate-counter outcome and
   must not fold metadata opens/preads into the data-file `opens`/`preads` counters.

### 12.2 Acceptance oracle: `TestHiCacheSpecExtentStorage`

`test/registered/hicache/test_hicache_spec_file_storage.py:88-158` inherits the shared mixin
`python/sglang/test/hicache_spec_storage_common.py:228-272`, which performs a **real restart**
(`_restart_spec_server` = stop + launch, `:120-124`) and asserts:

* `storage_cached_tokens >= input_token_len - 2*page_size` (`:251-256`);
* `cached_tokens_details["storage_backend"] == "ExtentFileBackend"` (`:257-262`);
* spec accept length does not regress (`:263-272`).

This is the natural end-to-end acceptance oracle G1 must make green; per the recon it is expected
RED today. It exercises a real process restart (SIGKILL/stop+launch) only — it is not a power-loss
durability oracle (`NM-INV-20`). The G1 verification task must run it before and after; this
design-only pass does not.

### 12.3 G1 acceptance points (USER-RULING-20260912-G1)

These eight points are the user-required G1 acceptance criteria. They are process-crash
(SIGKILL/restart) criteria only; they are NOT power-loss durability criteria (`NM-INV-20`).

| # | acceptance point | mapped oracle / invariant |
|---|---|---|
| 1 | pre-SIGKILL ACKed + `GROUP_COMMIT` durable -> present after restart | `NM-F-02`, `NM-F-10`; `NM-INV-03`, `NM-INV-04`, `NM-INV-20` |
| 2 | uncommitted / torn active tail -> no resurrection | `NM-F-03` (uncommitted), `NM-F-04`/`NM-F-17` (torn active tail); `NM-INV-05`, `NM-INV-09`, `NM-INV-17` |
| 3 | committed corruption -> fail closed | `NM-F-05`, `NM-F-06`; `NM-INV-09`, `NM-INV-10` (D3(a)) |
| 4 | stale generation -> no resurrection | `NM-F-07`, `NM-F-08`; `NM-INV-06`, `NM-INV-07` |
| 5 | KV + Mamba group -> all-or-nothing | `NM-F-10`; `NM-INV-08` (D4(b)) |
| 6 | new process uses a new namespace epoch; no seq collision with old runs | `NM-F-18`, `NM-F-19`; `NM-INV-18` (D7(a)) |
| 7 | `TestHiCacheSpecExtentStorage` RED -> GREEN | §12.2 E2E (`test_hicache_spec_file_storage.py:88-158` + mixin); `NM-F-01`/`NM-F-02`; `NM-INV-01`, `NM-INV-04`, `NM-INV-08` |
| 8 | RAM index restart-rebuild byte/identity equivalent | `NM-F-01`; `NM-INV-01`, `NM-INV-02`, `NM-INV-14` |

Point 7 is the end-to-end acceptance oracle and is expected RED before the change; the G1
implementation/verification task must run it before and after (§12.2). Point 1's "committed" means
WAL-durable `GROUP_COMMIT`/`BATCH_COMMIT`; the data-before-commit ordering is `NM-INV-20`.

---

## 13. Reversibility and migration

```yaml
reversible_seam: a backend-local metadata subsystem (manifest + WAL + lock) behind the existing
  ExtentFileBackend write/read/lifecycle API; no public engine interface change is required to
  disable it.
persistent_format_change: adds sibling metadata files; the data file format is UNCHANGED
  (payload-only, no header). Manifest format_version and WAL format_version gate compatibility.
forward_migration: on first open with no metadata, initialize empty metadata (including a fresh
  namespace_epoch) and start cold; do not scan or rewrite the data file. When a pre-existing data
  file is non-empty (allocated blocks) and there is no metadata, this is the D1 case; D1 is RULED
  (b) (process-crash semantics, USER-RULING-20260912-G1): there is no committed WAL-durable ACK to
  recover, so the cold start stands. D3 is RULED (a): fail-closed applies only to committed-region
  corruption, never to metadata absence. (R3 residual: reconciled with §5.)
rollback: remove/disable the metadata gate -> reopen ignores metadata and starts cold exactly as
  today; the pre-existing data file remains readable by the old behavior. Safe point: any restart.
mixed_state_behavior: an old binary ignores unknown sibling files and behaves cold; a new binary
  with no metadata starts cold. New binary + committed manifest/WAL corruption or unknown/newer
  manifest format_version -> fail closed (D3(a), RULED).
data_rewrite_required: false
capability_removal_proof: static audit that removing the metadata hooks restores the
  test_crash_reopen_all_cold behavior and that no read/write path depends on metadata files.
blast_radius: python/.../storage/extent/extent_file_backend.py, extent_allocator.py (event
  surface), python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py (group id/context),
  python/sglang/srt/managers/cache_controller.py (operation identity), the extent unit tests and
  the file-storage E2E test.
expiry_or_revisit_trigger: any change to the data-file format, any new pool/component, any
  distributed/multi-node use, or any power-loss durability claim.
```

---

## 14. Explicitly out of scope / not claimed

* No data-file format change and no data-file scan.
* No distributed/Raft/placement/migration/network-failure semantics.
* No correctness claim from benchmark/throughput results (RP-RDB-045).
* No performance/tuning values frozen here; group bounds are correctness bounds pending P2C.
* No product/test code change in this design write-back task; D7 is RULED (a)
  (`USER-RULING-20260912-G1`) and implementation is authorized for the intake's design-target
  product/test paths under that ruling.

---

## 15. Design decisions — USER-RULED 2026-09-12 (binding)

Recorded verbatim from the user ruling `USER-RULING-20260912-G1` (2026-09-12); these are final and
binding and are not revisited for "stricter fsync".

| id | decision | RULED | frozen meaning / consequence |
|---|---|---|---|
| **D1** | Allowed post-crash recovered prefix | **(b) PROCESS-CRASH SEMANTICS** | For SIGKILL / process crash: every operation that completed a WAL-durable commit AND was ACKed to the upper layer MUST be recoverable after restart. For power loss / kernel crash: extent DATA BYTES are explicitly NOT promised on stable media — a separate, stronger durability tier that this design does not claim. HARD INVARIANT `NM-INV-20`: the extent data write must be completed to the kernel/page-cache BEFORE the WAL `GROUP_COMMIT` becomes durable AND BEFORE the upper-layer ACK; the interleaving `WAL durable -> ACK -> data write not yet complete` is FORBIDDEN. The crash acceptance oracle tests ONLY SIGKILL/process restart and is labelled as such; it is never packaged as power-loss durability. Governs §4.3 steps 3/5/7, §4.4, §5, §12, §13, `NM-F-22`. |
| **D2** | Power-loss (vs process-crash) data durability | **(a) WAL `fdatasync` only** (DECIDED, non-blocking) | Payload bytes on stable media are not promised for power loss; no per-group `fdatasync(data_fd)`. Consistent with D1(b); affects `NM-INV-03`. |
| **D3** | Fail-closed vs salvage for a corrupt manifest/WAL | **(a) FAIL CLOSED** | Committed manifest/WAL corruption -> refuse to start that cache namespace (fail closed). The already-designed torn ACTIVE tail/frame repair stays (D-02/`NM-INV-17`). Committed-region corruption must NOT be auto-truncated/salvaged and served, and there must be no silent cold-start pretending durability is intact. Rationale to record: wrong resurrection of KV+Mamba state is far worse than a cache miss. Governs §5, §13; `NM-F-05/06`. Corpus note `RDB-C10 best-efforts salvage` is superseded by the ruling. |
| **D4** | Sidecar ACK semantics | **(b) defer sidecar ACK to `GROUP_COMMIT`** (DECIDED, non-blocking) | Must hold because KV + Mamba are one hybrid restore unit: a sidecar ACK is only valid once the group's `GROUP_COMMIT` is durable (D-08; `NM-INV-08`, `NM-F-10`). |
| **D5** | `component` representation | **(a) persist explicit enum, keep `ExtentRef` 4-field and derive at runtime** (DECIDED, non-blocking) | Preserves the frozen `ExtentRef` struct (§3.1); no mechanism change; key-suffix derivation remains the hot-path source of `component`. |
| **D6** | Metadata IO accounting | **(a) separate metadata counters** (DECIDED, non-blocking) | The re-dispositioned unit oracles must not fold metadata opens/preads into the data-file counters (`§12.1`). |
| **D7** | Durable group-id identity/epoch (from D-03) | **(a) 128-bit random `namespace_epoch` + per-run `group_seq`** | `group_id = (namespace_epoch[16 B], group_seq)`; epoch from a CSPRNG per writer/runtime incarnation; `group_seq` monotonic within the epoch; the epoch is persisted in WAL/group metadata so old/new runs never collide; KV and Mamba sidecar use the IDENTICAL `group_id`; `(0,0)` is ONLY the explicit `ungrouped` sentinel; all-zero epoch is FORBIDDEN for any normal grouped operation. CHOSEN over a persisted monotonic counter (no self-referential crash-safety loop; no run-count leak; negligible 128-bit collision). Governs §4.0, §9; `NM-INV-18`, `NM-F-18/19`. |
| — | Novel Mechanism `NM-EXTENT-RESTART-REBUILD-01` | **ACCEPTED** (`USER-RULING-20260912-G1`) | Accepted scope = the frozen mechanism ONLY: "compact manifest/checkpoint + append-only WAL -> restart rebuild RAM-authoritative index". Explicitly NO open-ended mechanism expansion. Acceptance basis = the user ruling plus the independent review `G1-GATE-INDEPENDENT-REREVIEW-R3-01.md` (ACCEPT-WITH-CONDITIONS; N-1..N-4 applied). |

D1, D3, and D7 were the authority blockers. All three are now DECIDED by user authority, so the
gate is no longer `BLOCKED` on authority; implementation is authorized for the intake's
design-target product/test paths under the frozen revision. This contract still does not
self-approve: the acceptance is the user ruling plus the independent review.

---

## 16. Risks and uncertainty

* **R1 (fsync latency/correctness of group commit):** up to two fsyncs on a reuse group. Mitigated
  by group commit and bounded groups; correctness is independent of the performance outcome (P2C).
* **R2 (payload durability vs metadata durability):** see D2. If only the WAL is fsynced, a power
  loss could leave a durable index entry whose payload bytes are missing.
* **R3 (group-id contract):** D7 changes the hybrid KV+sidecar identity contract and needs its own
  review.
* **R4 (clear/generation semantics):** `clear` keeps generations; WAL `CLEAR` is defined against
  concurrent drops.
* **R5 (multi-rank shared dir):** `config_suffix` covers tp/pp/cp; the fence prevents interleave if
  two backends intentionally share a suffix.
* **R6 (E2E timing):** the E2E oracle depends on the sidecar trailing window and
  `storage_cached_tokens` accounting; making the extent variant green may depend on D1/D4/D7.
* **R7 (W5 orphan segment):** WAL segment enumeration is explicit and traverses no directory (see
  §5): recovery opens the resolved contiguous named range `[wal_floor, G_active]` (manifest floor +
  `.wal.current`), each must exist and validate; `wal_floor == G_active+1` is the benign
  pending-rotation state and is promoted, `wal_floor > G_active+1` fails closed; probes at most
  `G_active+1` with one bounded `stat`, never trusts an orphan with an invalid header, and fails
  closed on a missing/malformed in-range segment (`NM-F-20`; NEW-11).

**Gate consequence:** this contract is ACCEPTED under `USER-RULING-20260912-G1` (2026-09-12), on the
basis of the independent review `G1-GATE-INDEPENDENT-REREVIEW-R3-01.md` (ACCEPT-WITH-CONDITIONS;
N-1..N-4 applied). The Pattern Intake is `status: complete` and the Novel Mechanism declaration is
`accepted:USER-RULING-20260912-G1`. D1/D3/D7 are decided; implementation is authorized for the
intake's design-target product/test paths. The orchestrator repins the new digests in
`.memory/phase2-hicache-design/authority.yaml` (this bundle does not edit it).

---

## Appendix A — defect-response (review R1)

| review id | status | exact textual fix |
|---|---|---|
| D-01 | fixed | §4.3 rewritten: write-ahead invalidation phase (steps 1-2) + no-clobber rule; §8 rewired (pure selection, durable `DROP_SLOT` before RAM mutation/pwrite); §7 "before clobbering pwrite"; NM-INV-16 + NM-F-15/16; false "orphan ... harmless" claim removed |
| D-02 | fixed | §4.3 "D-02 (tail repair)"; §5 replay step `ftruncate`+`fdatasync` before any append; NM-INV-17 + NM-F-17 |
| D-03 | fixed (design) / needs-decision | §4.0 durable `(namespace_epoch, group_seq)`; §3 payload `namespace_epoch`; §9 group identity; decision D7; NM-INV-18 + NM-F-18/19 |
| D-04 | fixed | §6 quiesce barrier holds `_write_gate` through unlink; conditional `max_seq <= checkpoint_lsn` unlink; crash windows updated |
| D-05 | fixed | §5 derive+cross-check now compares derived vs post-replay `expected` fold, not raw checkpoint; exact equality stated |
| D-06 | fixed | §11 `_write_gate` = leader sequencer; group formation under it; followers never plan/pwrite; §4.3 lead-in; §4.4 |
| D-07 | fixed | §4.3 D-07 paragraph; §8; NM-F-05/11 wording changed to "durable prefix" (drops applied after durable fsync, no new install on failure) |
| D-08 | fixed | §4.3 D-08 paragraph; §9 live-process deferred install/rollback; NM-INV-08 extended to live process |
| D-09 | fixed | §3.1 13-value component enum table incl. `DEEPSEEK_V4_*`/`DRAFT_*`, `OTHER=255` reserved |
| D-10 | fixed | intake `status: blocked`; intake §3 adds RP-RDB-036 row; contract §12.1 #3 no longer asserts D6 |
| D-11 | fixed | §4.2 frame layout + CRC range `header[0..22)` |
| A-01 | fixed | §0.1 inspected-revision declaration + corrected HEAD/worktree anchor table; `_t38c_operation_id` citation corrected (hybrid set / backend read); `mem_cache/hybrid_cache/…` added to blast radius (§13) and intake |
| A-02 | fixed | intake §3 and §7 anchors tightened (RP-RDB-014 :311-332, RP-RDB-017 :380-401, RP-RDB-034 :780-801, FDB-IMP-19 :370-388); open decision cited at `crash-matrix.md:8-9` |

### Appendix B — R2 defect-response (re-review NEW-1..NEW-10, §0.2, W5)

| review id | status | exact textual fix |
|---|---|---|
| NEW-1 | fixed (superseded by R3 unified form) | §4.3 step 1 NEW-1 formula (`base[s]`/`ref.gen`/`pending_gen[s]`) **plus the `pending_drops ∩ passed = ∅` disjointness clause** (a slot that is both passed and a GC victim is dropped once, else it double-counts), §7 NEW-1 paragraph + unified fallback form, §8 `plan`/`apply_drops`/`commit_install` row; novel `NM-INV-19`. R3 replaces the primary/disjointness split with the single unified form (Appendix C "hardening"). |
| NEW-2 | fixed (option (a)) | §4.3 D-02 deletes rotate-and-abandon and mandates in-place `ftruncate`+`fdatasync`; §5 replay + tolerated-vs-fail-closed table; NM-F-17 retained |
| NEW-3 | fixed | §5 derive+cross-check: `SET` folds only when batch complete and (if grouped) group COMPLETE; install predicate mirrored |
| NEW-4 | fixed | §4.3 NEW-4 split API (`plan`/`apply_drops`/`commit_install`), step 6 install-only; §8; §10 hook table; `NM-F-21` |
| NEW-5 | fixed | §4.3 CLEAR note, §6 `CLEAR` paragraph, §8 clear row, §10 clear row: clear/detach/reset take `_write_gate`; quiescent-only |
| NEW-6 | fixed | §2 fence rule: `fcntl.flock(fd, LOCK_EX)` (+`LOCK_NB` typed refusal, auto-release, stale handling); `O_CREAT|O_EXCL` removed |
| NEW-7 | fixed | intake §3 single merged RP-RDB-036 row (was duplicated) |
| NEW-8 | fixed | novel `NM-F-15` boundary reworded to kill points at steps 3/4/5 after the step-2 invalidation fsync |
| NEW-9 | fixed | §9 `open_group()`/`commit_group()` backend-owns-`group_seq`; novel §4 agrees |
| NEW-10 | rejected-with-reason | `os.open` is at `:368`, `os.ftruncate` at `:370` at HEAD and in the clean worktree; the existing `:368-370` was correct. §0 now cites the two anchors explicitly. |
| §0.2 | fixed | §0.2 replaced: `bytes`/`str` claim refuted (`hicache_storage.py:84-85`); semicolon patch-block claim withdrawn (no anchor); no open item |
| W5 | fixed | §5 enumeration rule (contiguous named range `[wal_floor, G_active]` from the manifest floor + `.wal.current`; no listdir; one bounded orphan `stat`; missing/malformed in-range -> FAIL CLOSED); §3 manifest fields `wal_floor`/`wal_active_gen`; §6 checkpoint publishes the floor; §5 table; §16 R7; `NM-F-20` |

### Appendix C — R3 defect-response (re-review R2-01: NEW-11, NEW-12, hardening, minor residuals)

| review id | status | exact textual fix |
|---|---|---|
| NEW-11 | fixed (rule (a)) | §6 quiesce barrier rewritten: the "release the gate after step 4" optimization is **DELETED**; `_write_gate` is held exclusively through step 6. §6 defines `wal_floor = G_active+1` at publish, the exact unlink set (exactly generations `< wal_floor`, provably identical to `max_seq <= L` under the barrier), and the crash windows including the (4)-(5) pending-rotation window. §5 defines the resolved range: `wal_floor <= G_active` normal; `wal_floor == G_active+1` benign promotion (validate/recreate header, publish `.wal.current`, no data loss under the barrier); `wal_floor > G_active+1` fail closed. §5 tolerated-vs-fail-closed table and §16 R7 updated. `NM-F-13/17/20` re-verified; `NM-INV-03/04` unchanged and still hold. |
| NEW-12 | fixed | contract §12 gains the `NM-F-21` oracle row (previously defined only in novel §6:250) after `NM-F-20`; `NM-F-13/20` rows updated; intake §8 gains the `NM-INV-19` row and Appendix B's unsupported "by reference" claim corrected. |
| hardening | fixed | §4.3 step 1 and §7 now mandate the **unified** generation form `pending_gen[s] = _generations[s] + max(passed.count(s), 1 if s in pending_drops else 0)`, `ref.gen = pending_gen[slot]`; the §4.3 "counted in the `passed` branch only" sentence and the `pending_drops ∩ passed = ∅` precondition are deleted. Overlap is tolerated, never double-counted. |
| D1/§13 | fixed | §13 `forward_migration` now states the pre-existing-non-empty-data-file/no-metadata cold start IS OPEN DECISION D1 (recommended D1(b)); §15 D1 consequence notes it governs §5/§13. |
| `_write_gate` NEW + lock order | fixed | §0 OBSERVED adds `_write_gate` does not exist at HEAD (only `self._lock` at `extent_file_backend.py:348`); §11 declares it G1-introduced and pins the one-way lock order `_write_gate -> _lock`. |
| partial-header orphan | fixed | §5 enumeration EXCEPTION + §5 table + §6 step 5: a same-generation partial-header segment at the promoted `wal_floor` is repaired in place (`os.ftruncate(fd,0)`/`O_TRUNC`, valid header at offset 0, `fdatasync`, publish `.wal.current`), never trusted as-is. |
| `commit_install` atomicity | fixed | §4.3 step 6: install is all-or-nothing under `_lock`; a failure installs nothing, returns failure, and the backend QUIESCES rather than diverge from the durable WAL. |
| `wal_active_gen` staleness | fixed | §5 tolerated-vs-fail-closed table + §6: `wal_active_gen` is a checkpoint-time validation-only hint; a newer `.wal.current` after rotation is expected and not corruption. |
| failed-group truncation | fixed | §4.4: exact truncation boundary is the **post-drop offset** (immediately after the last durable `DROP_SLOT` of the group; `pre_group_offset` if none), followed by `fdatasync`; `NM-F-11` updated. |

### Appendix D — authority-ruling write-back (`USER-RULING-20260912-G1`, 2026-09-12)

Surgical write-back of the user's binding decisions; no mechanism/invariant change beyond the one
required new hard invariant. Mapping:

| ruling | recorded in |
|---|---|
| D1=(b) process-crash semantics + hard invariant | §4.3 (D1 block), §4.4, §5, §12 intro/§12.3, §13, §15; `NM-INV-20` + `NM-F-22` |
| D3=(a) fail closed | §5 (branch + table + D3 note), §13, §15 |
| D7=(a) 128-bit CSPRNG epoch + per-run group_seq | §4.0, §9, §15 |
| D2=(a), D4=(b), D5=(a), D6=(a) accepted defaults | §15; §12.1 (D6 test outcome) |
| Novel `NM-EXTENT-RESTART-REBUILD-01` ACCEPTED (frozen scope only) | §15 |

New invariant `NM-INV-20` and failure case `NM-F-22` are the only semantic additions; every prior
`NM-INV`/`NM-F` id and the `NOVEL_MECHANISM` classification are retained.
