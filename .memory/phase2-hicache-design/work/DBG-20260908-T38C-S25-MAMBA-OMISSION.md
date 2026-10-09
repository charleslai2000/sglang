# DBG-20260908-T38C-S25-MAMBA-OMISSION — s00005 post-fix Mamba omission

## Invocation

- Task / epoch: `DBG-20260908-T38C-S25-MAMBA-OMISSION` / `T38C-fix1`.
- Status: **done**; **NEEDS_REROUTE: coder** for the narrowly scoped paired
  write/query diagnostic described below.  A subsequent GPU reproduction is a
  separate `tester` task.
- Scope respected: code and supplied evidence were read only; no product or
  control-plane files were changed and no GPU experiment was started.

## Finding

`s00005` is a genuine state-incomplete L3 restore, not a KV miss and not a
failure of the post-fix frontier calculation.  Its `KV=55145` observation is
the raw contiguous KV frontier; the Mamba trailing scan found **no valid
checkpoint at any candidate endpoint in that 55,145-page range**, so the
required KV+Mamba intersection is zero.  The zero then correctly becomes a
full-miss/recompute.

The record is **not an expected early-settle transient**.  It occurred 762.451
seconds after `s00005`'s build completed, and valid KV+Mamba restores occurred
in the same run immediately before and after the failed branch.  It is also
not a vehicle-only failure: the storage query made the deterministic
state-completeness decision.  The best-supported classification is therefore
an **unresolved product persistence/lifecycle hole for one branch's Mamba
checkpoint**.  The present probe cannot yet distinguish (a) transfer omitted
because the checkpoint had no host value, (b) independent Mamba sidecar-write
failure while KV still committed, (c) subsequent sidecar recycle/removal, or
(d) a write/read hash disagreement.  Do not claim Gate PASS.

## Observed event chain

All times below are Unix seconds from the target remote evidence, not inferred
wall-clock ordering.

| Session | Build end | Round-1 resume RID / query time | Query outcome |
| --- | ---: | --- | --- |
| s00000 | 1788800190.184 | `e98e…f45b` / 1788800842.964 | KV 55145, Mamba 55145, restored 55145 |
| s00001 | 1788800190.185 | `d0fa…2a1` / 1788800864.688 | KV 55124, Mamba 55124, restored 55124 |
| s00002 | 1788800190.185 | `ada8…718` / 1788800886.969 | KV 55102, Mamba 55102, restored 55102 |
| s00003 | 1788800190.185 | `a2ec…117` / 1788800908.550 | KV 55104, Mamba 55104, restored 55104 |
| s00004 | 1788800190.185 | `78a8…edf` / 1788800930.801 | KV 55103, Mamba 55103, restored 55103 |
| **s00005** | **1788800190.184** | **`e1e2…7f8` / 1788800953.231** | **raw KV 55145; folded KV/Mamba 0; full miss** |
| s00006 | 1788800190.184 | `be5b…cb6` / 1788800990.182 | KV 55104, Mamba 55104, restored 55104 |
| s00007 | 1788800190.184 | `6855…f7c` / 1788801012.086 | KV 55125, Mamba 55125, restored 55125 |

Evidence:

1. The target `join.log` records `s00005` build RID
   `bfe4ae42…` ending at `1788800190.184`, then its round-1 resume RID
   `e1e2a362…` beginning at `1788800952.635`; that is a 762.451-second
   settle interval.  It also records zero storage prefill for that resume
   (`prefill_storagehit_delta=0`) while s00000–s00004 and s00006–s00007 each
   record 54K–55K storage prefill.
   (`root@175.155.64.171:24052:/root/evidence-gate3-parked/s25-t38c-frontier-fix1/run-20260908-005403/join.log:26-33`)
2. At `1788800952.947`, s00005's prefetch gate was root-anchored and passed;
   it issued normally.  At `1788800953.231`, the storage query returned
   `sidecar_hits={"kv":55145}` but `kv_hit_pages=0` and
   `storage_hit_count=0`; its drain immediately classified
   `revoked_full_miss` at `1788800953.235`.
   (`.../s25-t38c-frontier-fix1/t38c-probe.log:1105-1110`)
3. The adjacent successes make the absence branch-specific rather than a
   global backend outage: s00004 returned `{kv:55103,mamba:55103}` at
   `1788800930.801` and completed host restore at `1788800932.593`; s00006
   returned `{kv:55104,mamba:55104}` at `1788800990.182` and completed at
   `1788800991.832`. (`t38c-probe.log:1043-1103,1167-1227`)
4. The engine independently records s00005's revoke as
   `storage_hit=0`, `miss_reason=miss`, then `MISS_RECOMPUTE`; it records no
   admission, GPU, or HTTP failure before the decision.
   (`/root/engine-gate3-parked-s25-t38c-frontier-fix1.log:14210-14221`)

The supplied local copied probe is an earlier run (its first timestamp is
`1788509655.869`, unlike target run timestamp `1788800058+`).  It corroborates
the historical raw-KV/zero-Mamba symptom but cannot establish causation for
this post-fix s00005 branch; the remote target probe above is authoritative.

## Code-level causal reconstruction

1. Mamba prefetch deliberately creates one host staging page and a
   `TRAILING_PAGES` placeholder transfer
   (`mamba_component.py:683-696,765-774`).  The storage writer emits the Mamba
   checkpoint only if `cd.host_value` exists, keyed by the node's last hash
   (`mamba_component.py:752-763`).
2. The fix first asks raw KV storage for its contiguous frontier, truncates
   `query_hashes` to that frontier, and aligns the trailing Mamba window to
   `all_hashes[kv_hit_pages-1:kv_hit_pages]`
   (`hybrid_cache_controller.py:601-624,675-690`).  Thus an appended warm-turn
   tail cannot explain the s00005 zero.  The success records containing
   `mamba==kv` demonstrate this code path works for its peer branches.
3. `ExtentFileBackend.batch_exists_v2` first preserves the raw KV result in
   `hit_count[KV]`, then scans every candidate prefix from the remaining
   frontier down for the Mamba trailing window and applies
   `final_pages=min(final_pages,boundary)`
   (`extent_file_backend.py:640-690`).  Consequently, s00005's
   `{kv:55145}` plus final zero entails `boundary==0`; because a zero boundary
   is intentionally omitted, no `mamba:0` appears in the log.  This is the
   direct cause, and preserves correct recurrent-state safety.
4. The scheduler uses only the folded `storage_hit_count`; a value below the
   256-token threshold is revoked, with zero specifically labelled
   `revoked_full_miss` (`unified_radix_cache.py:3660-3675`).  The observed
   revoke is therefore an effect, not the source of the missing Mamba state.

## Competing hypotheses

| Hypothesis | Result | Reason |
| --- | --- | --- |
| Post-fix query still uses appended warm tokens for Mamba | Ruled out | Controller establishes/uses the raw KV frontier before the trailing check; seven peers restore both pools. |
| KV L3 data is missing | Ruled out | s00005 has raw contiguous KV 55145. |
| Generic trailing fold is faulty | Ruled out as root cause | It correctly refuses KV without the required recurrent state; bypassing it would be unsound. |
| Query happened before the build had settled | Ruled out | 762.451 seconds elapsed; s00004 succeeded 20.4 seconds earlier and s00006 succeeded 36.9 seconds later. |
| A branch-specific Mamba persistence/lifecycle failure exists | Supported | That is the only way the Mamba trailing scan can be zero while raw KV remains 55145. |
| Mamba transfer omitted, Mamba write failed, Mamba was recycled, or hash mismatched | Open | The existing `pc_write_seed` logs only KV-chain seed/page hashes. They contain neither the constructed Mamba key nor the `batch_set_v2` result, nor a removal event. |

## Smallest next diagnostic and owner

**Owner: `coder` (fresh task).** Add a narrowly gated paired Mamba evidence
record; do not alter restoration semantics.

- At `_write_backup_storage_node`, emit `node_id`, the node's final KV hash,
  whether `BACKUP_STORAGE` produced a Mamba transfer, its exact Mamba key, and
  the `batch_set_v2` Mamba success boolean.  This is necessary because
  `build_storage_backup_spec` silently omits a component when its transfer is
  `None` (`unified_tree_core.py:2062-2087`) and Mamba returns `None` when
  `host_value` is absent (`mamba_component.py:752-755`).
- At the extent query, emit the actual trailing Mamba key tested and its
  `present()` result, alongside raw KV frontier and boundary.  Do not emit
  token text or state bytes.
- Also log any component-key removal/recycle, keyed the same way.  The extent
  writer processes a sidecar independently and exposes only a per-transfer
  boolean (`extent_file_backend.py:747-782`); the hybrid backup path writes
  that sidecar before the base KV operation (`hybrid_cache_controller.py:777-814`).

This is a diagnostic-only code change.  A fresh `tester` task should then run
one S=25 RH-off reproduction and classify the result: omitted transfer means
Mamba host-state/lifecycle ownership bug; `False` write means atomicity/error
handling bug; prior success then absence means recycling bug; successful write
under a different key means hash-chain bug.

## Followups

- Retain all-state intersection semantics and the 256-token threshold; neither
  is a safe remediation for this event.
- Have the coder add a focused regression that a storage operation containing
  KV but no required Mamba transfer cannot be marked restore-durable for a
  hybrid prefix.

## Open issues

- No authorized log records the final raw-KV hash at s00005's 55,145 boundary.
- No authorized log pairs s00005's Mamba transfer construction/write ack with
  that queried key, and none records component-key recycle.  These are the
  critical missing observations; do not select one sub-cause without them.
