# F1 Option-C — independent durability-review protocol (extent-slot live-ref relocation)

Task: `f1-optionC-durability-review-scaffold-20260917`, role `reviewer`.
Status of this document: **review plan + executable falsification harness**, not a
verdict. The candidate implementation does not exist yet; this protocol is
designed so the real review can execute the moment it lands, without depending
on the implementer's own tests.

Authoritative inputs used to derive expectations (read-only):

| artifact | role |
|---|---|
| `/opt/sglang/local-prod-v1.1-candidate/src/python/sglang/...` | frozen tree; identity §1 |
| `/tmp/opencode/f1-optionA-anchorrun-20260916/BOUND-PROOF.md` | why write-side refresh was rejected (O(context)) |
| `/tmp/opencode/f1-restore-miss-20260916/F1-ROOT-CAUSE-REPORT-20260916.md` | defect: `batch_exists` consecutive-prefix contract; whole-chain false miss |
| `/tmp/opencode/f1-optionA-anchorrun-20260916/frames.json`, `analyze_wal.log` | real round-1 WAL write history (ground truth shape) |

Contract under review (from the dispatch):

1. on selecting victim slot `(slot, generation=g)`, BEFORE any bump/reuse:
   enumerate every currently-live index ref into that generation;
2. relocate ONLY live refs to non-victim space; bytes exact; opaque KV/Mamba
   payload not re-interpreted; dead/stale refs NOT copied; cost bounded by the
   victim live bytes (max ~1 slot);
3. publish through the EXISTING durability path
   `data write -> SET(s) -> BATCH_COMMIT/GROUP_COMMIT -> index publication`;
4. latest committed ref wins after live lookup, checkpoint, WAL replay, restart;
5. only after EVERY live ref has a durable published replacement may the victim
   be dropped / generation-bumped / reused.

---

## 0. How to read this protocol

Every row is a single falsification question answerable as:

* **PASS** — the observation required by the contract was made and held;
* **FAIL** — the contract was violated (bug);
* **INVALID** — the reclaim/relocation window was never reached (e.g. the write
  fail-closed) or the needed surface is unavailable. INVALID is *not* PASS; the
  row stays open and must be re-driven with a scenario that reaches the window.

Evidence identity: a row is bound to the reviewed bytes (the candidate tree
commit/hash and the oracle script hash recorded in each result JSON). A change
to the candidate bytes invalidates the dependent rows only; unchanged rows may
be reused.

`ST-*` = synthetic mechanism self-test (`oracles/selftest_oracle_logic.py`),
never product evidence.

---

## 1. Reviewed-tree identity (pin before running)

Frozen control (this scaffold's baseline), sha256 of the files the contract
touches:

| file | sha256 |
|---|---|
| `srt/mem_cache/storage/extent/extent_allocator.py` | `285df97c01da9d754c33153aedf3cf21d77ec0449740220e8d758819ee552566` |
| `srt/mem_cache/storage/extent/extent_file_backend.py` | `fbd19f10e66900a48dcc5acbeb5901c9c00cbc0e5a73fe208b6cac799b1b6b13` |
| `srt/mem_cache/storage/extent/extent_metadata.py` | `5a69af5ede6bd2b404e770fdc089e0c77b45d09ec9a057dd6b5d269093a2d924` |
| `srt/mem_cache/hicache_storage.py` | `7c5c7331eda1ded25a25bb5d9938aa76311651b16025f5b8743a17318ff1d1d7` |

Every oracle asserts `sglang.__file__` resolves inside the `--tree` it was
given and records it in the result JSON; a wrong tree is a hard error, not a
silent cross-tree run.

---

## 2. Table A — contract points

| ID | Effective requirement | Falsification question | Observation that falsifies | Oracle / check id | Frozen control |
|---|---|---|---|---|---|
| C1 | every live index ref in the victim generation is enumerated | is there any victim-resident index ref (KV **or** sidecar) that does not survive? | a key with a matching-generation ref in the victim slot pre-trigger is unresolved or unreadable post-trigger | `payload`: `{kv,mixed}:live-refs-survive`; `live_dead`: `LD-1:uniform-preservation` | **FAIL** |
| C2 | relocate ONLY live refs, to non-victim space | does any surviving relocated ref still live in a bumped victim slot? | `ref.extent_id ∈ victims` after a successful reclaim | `payload`: `{kv,mixed,v1}:dest-non-victim`; `generation`: `GEN-4:old-generation-unreachable` | **FAIL** |
| C3 | byte-exact; opaque KV/Mamba payload not re-interpreted | do relocated bytes equal the pre bytes by sha256 (not merely length)? | same-length, different-content read-back | `payload`: `{kv,mixed,v1}:bytes-checksum-exact`; self-test `ST-2`/`ST-3` | **FAIL** |
| C4 | dead/stale refs are NOT copied | is a generation-stale victim entry turned back into a live ref? | `lookup(stale_key)` non-None after reclaim | `live_dead`: `LD-2:stale-not-resurrected` | PASS (defensive seam; see §7) |
| C5 | cost bounded by victim live bytes (~1 slot) | is `bytes_written` for the reclaim bounded by victim bytes + new page + 2 slots? | delta grows with context/file, or a full-file rewrite | `payload`: `{kv,mixed}:cost-bounded` | PASS on frozen (no relocation performed) — vacuous here; meaningful only once relocation runs |
| C6 | publish via the existing path only (`data write -> SET -> BATCH_COMMIT/GROUP_COMMIT -> index`) | are only frozen frame types emitted, in the required order? | an unknown frame type, or `DROP_SLOT` before the replacement commit | `crash`: `CM-0:no-new-wal-protocol`, `CM-2:no-drop-before-replacement-commit`; static diff | **FAIL** (`CM-2`) |
| C7 | latest committed ref wins after lookup / checkpoint / WAL replay / restart | after a fresh process, does every key resolve to the folded latest committed ref, byte-exact? | resolved ref ≠ independent WAL fold, or key lost | `restart`: `{checkpointed,walonly}:refs-byte-exact-after-restart`; `crash`: `{CP2,CP3}:fold-equals-replay` | **FAIL** |
| C8 | victim dropped only after every live ref has a durable replacement | is any `DROP_SLOT` for a live victim emitted before its replacement commit? | `DROP_SLOT` precedes the first post-trigger commit | `crash`: `CM-2:no-drop-before-replacement-commit`; `CP1-before-commit:refs-reachable-bytes-exact` | **FAIL** |

Adversarial note for C1/C2: a maintainer's test typically asserts over *the
list of keys their relocator produced*. That cannot catch a **live ref the
relocator never enumerated** (a sidecar component key, a grouped member, a key
whose `_slot_keys` entry exists but whose component path the maintainer did not
consider). `LD-1` and `LD-3` deliberately put KV and Mamba in the same victim
slot so an enumeration that stops at KV head pages is caught.

---

## 3. Table B — crash invariants

Crash points are derived from the produced WAL stream (offsets captured through
the existing `_append_wal_frame`), truncated at frame boundaries, and replayed
by a **fresh process**; each cut's expected index is also produced by an
independent fold (committed batches/groups install; `DROP_SLOT` removes a
slot's keys).

| ID | Effective requirement | Falsification question | Observation that falsifies | Oracle / check id | Frozen control |
|---|---|---|---|---|---|
| K1 | crash before relocation commit → old refs authoritative | after truncating before the first post-trigger commit, do all old refs survive byte-exact? | any victim key lost or corrupted at the CP1 cut | `crash`: `CP1-before-commit:refs-reachable-bytes-exact` (+ `:fold-equals-replay`) | **FAIL** |
| K2 | crash after commit, before victim retirement → new committed refs win | after truncating before the first post-commit `DROP_SLOT`, does every key resolve to the committed replacement, byte-exact? | key lost, or ref ≠ folded committed ref | `crash`: `CP2-after-commit-before-retire:refs-reachable-bytes-exact` | **FAIL** |
| K3 | crash after retirement/reuse → only new refs reachable | at the full cut, are victim old generations unreachable and only new refs reachable? | a key resolves into a pre-bump victim generation, or is lost | `crash`: `CP3-after-retire-reuse:refs-reachable-bytes-exact`; `generation`: `GEN-4` | **FAIL** |
| K4 | no state exposes a ref to overwritten victim bytes | at every cut, does every *reachable* ref read back byte-exact (sha256)? | reachable ref whose bytes differ from pre-state | `crash`: all three `:refs-reachable-bytes-exact`; `no_capacity`: `fragmented:no-old-generation-exposure` | **FAIL** |

Adversarial notes:

* A test that only checks **existence** after replay misses K4's real hazard: a
  ref can still resolve to a slot whose bytes were overwritten *after* the
  crash point. The oracle compares sha256 on every reachable ref.
* A crash point that truncates before any relocation frame (e.g. a fail-closed
  trigger) does **not** exercise a window. `CM-1:window-exercised` reports
  INVALID in that case rather than PASS.
* The `checkpoint` interaction is covered separately (`RS-5`) because a
  concurrent checkpoint can rotate the WAL between the commit and the drop; the
  crash matrix deliberately runs with `wal_checkpoint_bytes=0` so truncation is
  meaningful.

---

## 4. Table C — allocator safety

| ID | Effective requirement | Falsification question | Observation that falsifies | Oracle / check id | Frozen control |
|---|---|---|---|---|---|
| A1 | never recursively reclaim the same victim | was the same victim slot bumped more than once inside one reclaim, or used as its own relocation destination? | `post_gen[s] - pre_gen[s] > 1`, or a relocated ref landing in the victim | `generation`: `GEN-3b:single-step-bump`, `GEN-2/GEN-4` | PASS (frozen bumps once) |
| A2 | destination capacity secured BEFORE touching the victim | was the victim overwritten while the destination was not secured? | trigger returns True, victim bytes change, and no non-victim replacement exists | `no_capacity`: `{full,fragmented}:victim-intact`; `payload`: `:dest-non-victim` | **FAIL** |
| A3 | no capacity → fail closed / backpressure, never recycle a live victim | does an exhausted write recycle the victim anyway? | `ok == True` with lost/corrupted victim keys, or `ok == False` with mutated state | `no_capacity`: `{full,fragmented}:victim-intact`, `:fail-closed-state-unchanged`, `:reclaim-succeeded-without-capacity` | **FAIL** |
| A4 | preserve lock order (`_write_gate -> _lock`) and checkpoint interaction | can a reader observe a half-moved victim, or a checkpoint snapshot a partial move? | torn index/bytes under concurrency; checkpoint manifest missing relocated refs; lock-order inversion | **STATIC** diff argument + `restart`: `checkpoint-load:refs-byte-exact` stress | dynamic stress PASS on frozen; **strict lock-order invariant is not dynamically provable (see §7)** |

Adversarial note for A2/A3: the tail-feasibility model counts only append-cursor
free space. An implementation may legitimately free *holes* behind cursors. The
oracle therefore does not fail merely because a write succeeded when the tail
model says "no capacity": it fails only on **loss/corruption** or on
**mutated state after a fail-closed**. Conversely, a `write-succeeds-with-capacity`
FAIL is raised when the tail model is packable and the write still fail-closed —
that is a liveness regression, not a safety one, and is reported separately.

---

## 5. Table D — hybrid (KV + sidecar) and group contract

| ID | Effective requirement | Falsification question | Observation that falsifies | Oracle / check id | Frozen control |
|---|---|---|---|---|---|
| H1 | all live refs in the victim treated uniformly (not only KV head pages) | is a Mamba sidecar ref in the victim preserved byte-exact and with its component intact? | Mamba key lost, corrupted, or re-emitted as KV | `live_dead`: `LD-1:uniform-preservation`; `payload`: `mixed:mamba-component-preserved`; `restart`: `:mamba-component-restored` | **FAIL** |
| H2 | KV/Mamba refs in the existing group durability preserve the group contract | after staging a group, triggering reclaims, then committing: are staged KV+Mamba members exact and visible, and invisible before commit? | staged member visible before `GROUP_COMMIT`; commit fails; staged bytes changed | `live_dead`: `LD-3a:stage-accepted`, `LD-4:staged-invisible`, `LD-3b:group-commit-succeeds`, `LD-3c:staged-bytes-exact` | PASS (non-regression baseline) |

Adversarial note for H2: a group-commit boundary that splits KV from Mamba is
exactly the case a per-pool test misses. The oracle stages both through
`batch_set_v2(group_id=...)`, forces reclaims in between, then commits and
checks both payloads **and** that nothing was visible early.

---

## 6. Table E — non-goals enforced as non-regressions

| ID | Non-goal | Falsification question | Observation that falsifies | Oracle / check id |
|---|---|---|---|---|
| N1 | lookup semantics unchanged | does `batch_exists` still return the consecutive-prefix length; do flat/v2 round-trips still work? | `batch_exists` returns a gap-tolerant count, or a non-consecutive run | `restart`: `{checkpointed,walonly}:batch-exists-contract`; `payload`: read-back checks | 
| N2 | no permanent pinning | after relocation, can the write path keep making progress, or does it deadlock into permanent backpressure? | the last 200 churn writes all fail (pinned relocated refs never reclaimable) | `generation`: `GEN-6:no-permanent-pinning` (bounded churn) |
| N3 | no general compaction/GC | are non-victim refs left byte/ref-identical, and is only the victim's bytes copied? | a non-victim ref rewritten; cost proportional to file | `payload`: `{kv,mixed}:non-victim-untouched`, `:cost-bounded` |
| N4 | non-Extent backends byte/behaviour inert | are there any changes outside the Extent surface, or behaviour changes in `HiCacheFile`/others? | diff touching non-Extent files; non-Extent regression | **DIFF-SCOPE** (see §7) + repo non-Extent suite |

Adversarial note for N3: an implementation that "relocates" by rewriting the
whole extent set (or by invoking the GC path) would pass a naive relocation
test while violating the bounded-cost and no-GC non-goals; `:cost-bounded` and
`:non-victim-untouched` are the catches. `GEN-6` catches the opposite failure
mode (relocation that pins instead of moving).

---

## 7. Explicitly UNVERIFIABLE with the current evidence/harness

These are stated rather than papered over with a check that would pass by
construction:

* **A4 / lock order (`_write_gate -> _lock`).** Lock order is a static property
  of the candidate source. The dynamic harness can only stress it
  (`checkpoint-load`) and cannot prove the absence of an inversion or a
  reader-visible half-move. Required evidence: a **static argument in the final
  review** naming every acquisition site on the relocation path, plus the
  `checkpoint-load` stress as corroboration. The structural N/A for
  panic/cancel outside these locks is valid only after auditing current code,
  runtime lifecycle, handle ownership, and the call path, with a stated reopen
  condition.
* **N4 / non-Extent inertness.** Requires the candidate **diff** and the repo's
  non-Extent unit suite; the differential harness cannot see files it does not
  execute. Required evidence: diff scope (`git diff --stat`) plus the existing
  non-Extent backend tests on the candidate tree.
* **C4 stale-entry reachability.** The frozen allocator has no production path
  that leaves a generation-mismatched entry in `_index` (`apply_drops` removes
  slot keys; `lookup` lazily evicts mismatches), so `LD-2` is a **defensive
  seam**, not a production state. It catches a relocator that turns a stale
  slot key into a live ref; it cannot prove the state is reachable. Do not cite
  `LD-2` as production evidence.
* **Recursive reclaim beyond one bump (A1 full form).** `GEN-3b` detects a
  double bump of the same slot in one trigger; it cannot prove the absence of a
  deeper re-entrancy (e.g. relocation allocating by re-entering the write
  path) unless that re-entrancy emits a second bump. Required evidence: the
  static call graph on the relocation path, plus `GEN-3b`.
* **Exact bounded-cost constant.** `C5` checks an inequality
  (`victim + new + 2 slots`). The "max ~1 slot" contract is a design bound; the
  harness establishes it is not O(file/context), not the precise constant.

---

## 8. Oracle inventory (what each catches)

| oracle | catches | exit codes |
|---|---|---|
| `oracles/oracle_payload_bytes.py` | lost/corrupted relocated KV **and** Mamba bytes; destination-in-victim; component downgrade; non-victim collateral rewrite; unbounded I/O; the real v1 zero-copy surface | 0 PASS / 1 FAIL / 2 INVALID / 3 ERROR |
| `oracles/oracle_generation.py` | stale pre-refs still verifying; wrong generation on survivors; non-monotonic/double bumps; old-generation exposure; instability across victim reuse; permanent-pinning backpressure | same |
| `oracles/oracle_live_dead.py` | sidecar (Mamba) not treated uniformly; stale entry resurrection (defensive); group staging visibility and post-commit exactness | same |
| `oracles/oracle_no_capacity.py` | silent live-victim recycling under exhaustion; non-atomic fail-closed (state mutated despite `False`); fragmented near-full case | same |
| `oracles/oracle_crash_matrix.py` | wrong durability ordering (`DROP` before commit); loss at each of CP1/CP2/CP3; replay≠fold; new WAL frame types | same |
| `oracles/oracle_restart_replay.py` | post-checkpoint and WAL-only replay loss; Mamba component not restored; `batch_exists` regression; checkpoint-worker race | same |
| `oracles/selftest_oracle_logic.py` | **mechanism only**: proves the comparator classifies exact vs corrupted, feasibility packing, and fold semantics correctly (non-vacuity) | same |
| `oracles/run_all.py` | aggregation; flags a vacuous oracle that PASSes on the frozen control | 0 expected / 1 unexpected / 2 INVALID on candidate / 3 harness |

---

## 9. Recorded frozen-control baseline (negative controls)

Run: `CUDA_VISIBLE_DEVICES=999 python run_all.py --tree /opt/sglang/local-prod-v1.1-candidate --mode frozen-control`.
Result: `overall_exit=0` (all six oracles FAILed as required — none is vacuous).
Key falsified rows (abridged, full JSON under `results/`):

* `payload`: `kv|mixed|v1: live-refs-survive`, `bytes-checksum-exact`,
  `dest-non-victim` — the frozen allocator drops the live victim slot.
* `generation`: `GEN-5:stable-across-victim-reuse` — relocated refs never existed.
* `live_dead`: `LD-1:uniform-preservation`.
* `no_capacity`: `full|fragmented: victim-intact`,
  `reclaim-succeeded-without-capacity` — the frozen path returns success while
  dropping 16 (resp. 2) live refs.
* `crash`: `CM-2:no-drop-before-replacement-commit`
  (order `DROP_SLOT, SET, BATCH_COMMIT`), and loss at CP1/CP2/CP3.
* `restart`: `checkpointed|walonly: refs-byte-exact-after-restart`,
  `batch-exists-contract` (chain of 4 → `batch_exists == 0`);
  `checkpoint-load: refs-byte-exact`.

Mechanism self-test (`selftest_oracle_logic.py`) PASSes: `ST-1` feasibility,
`ST-2` accepts exact bytes, `ST-3` rejects same-length corruption, `ST-4` fold
semantics. This is synthetic and is **not** product evidence.

---

## 10. Acceptance rule for the terminal review

* Any `FAIL` on a required row is a **blocking finding**: name the invariant
  (`C#`/`K#`/`A#`/`H#`/`N#`), the effective requirement, the observed bytes /
  replay state, and the acceptance impact.
* An `INVALID` row is **not** accepted as PASS. The review must either re-drive
  it with a scenario that reaches the window, or record it as
  `UNVERIFIABLE: <reason>` with the smallest missing capability.
* The strict lock-order and non-Extent-inertness rows require a static argument
  in addition to the dynamic results.
* Do not add oracle variants for generic language/runtime errors; every check
  above must reduce a named uncovered risk in §2–§6.
