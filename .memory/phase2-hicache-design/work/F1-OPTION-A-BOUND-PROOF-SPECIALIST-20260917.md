# F1 Option-A — durability-anchor run: BOUND PROOF

Task: `f1-optionA-anchorrun-20260916`, role `coder`.
Frozen tree analysed (read-only): `/opt/sglang/local-prod-v1.1-candidate/src/python/sglang`
(`sglang.__file__` asserted inside the frozen tree by every harness below).
Scratch: `/tmp/opencode/f1-optionA-anchorrun-20260916/`.
Nothing under `/opt/**`, the workspace, `/data/**`, or an existing `/var/log/**` evidence dir was
modified; no GPU lock, no server, no port.

## VERDICT — STEP 1 decision gate

**The durability-anchor run is NOT structurally bounded. It grows ~with the logical prefix
length (exactly: with the leading cache-resident, never-deleted prefix), up to
`min(context, L1+L2 capacity)`; when the prefix is cache-resident it equals the whole prefix.**
Refreshing the run is therefore O(context) in the reachable workload the owner named
("prefix grows to 64K then 128K and is re-used repeatedly").

Per the binding decision gate ("if the run is NOT structurally bounded ... STOP ... implement
NOTHING"), **STEP 2 was not started and no source change was made**. Result of the requested fix:
**UNAVAILABLE**.

The remainder of this document is the proof.

---

## 0. What the run is

For the incident the run is `{p0,p1,p2}`. The owner's rule is semantic, not the instance:

> refresh every durability-anchor page in the leading chain that
> (1) is required for `batch_exists()` contiguous-prefix validity, and
> (2) would otherwise not be rewritten by the normal backup spec before its current extent slot
> can be recycled.

So the quantity to bound is:

```
RUN = leading contiguous page run P[0..k) of a chain such that
      count_of_normal_backup_writes(P[i]) <= 1   for every i < k
      (equivalently: P[i] is never re-entered by any backup after its first write)
```

If `RUN` can grow with the chain, the "refresh every page of the run" fix rewrites O(context)
pages and is forbidden by the task.

---

## 1. (a) Why the anchor pages are never rewritten by the normal backup spec

All citations are the frozen tree.

### 1.1 The spec writes only the target node's own pages — never its ancestors

`UnifiedTreeCore.build_storage_backup_spec` (`unified_tree_core.py:2062-2087`) returns
`hash_value=node.hash_value` and `host_value=node.component_data[FULL].host_value` — the target
node's **own** pages. The ancestor pages are returned only as `prefix_keys`
(`node.get_prefix_hash_values(node.parent)`, `:2071`; recursive, `:195-199`) which is *query /
commit metadata*, not written bytes.

The writer consumes only `spec.hash_value`:
`unified_radix_cache._write_backup_storage_node` (`unified_radix_cache.py:4907-5010`) builds
`kv_xfer = PoolTransfer(host_indices=spec.host_value, keys=spec.hash_value)` (`:4920-4924`) and
`write_storage(...)`. The hybrid controller's `_page_backup`
(`hybrid_cache/hybrid_cache_controller.py:1107-1203`) forwards the operation to the base
`CacheController._page_backup` (`managers/cache_controller.py:1415-1440`), which iterates
`operation.hash_value` only. `prefix_keys` is passed to `HiCacheStorageExtraInfo(prefix_keys=...)`
(`cache_controller.py:1426`) — extra_info for the backend, never bytes.

Executable confirmation (this task, `bound_demo.py`): over a chain grown to 6/12/24/48 nodes and
written by the real helper path, `n_ever_written_pages == n_pages` and
`n_write_once_pages == n_pages` — i.e. **no ancestor page is ever written by a later node's
backup**.

### 1.2 The gap collector walks past anything already submitted; it never re-collects it

`UnifiedTreeCore.collect_storage_gap` (`unified_tree_core.py:2089-2109`):

```python
while (node is not self.root_node and not node.storage_persisted):
    if not node.storage_written:          # :2105
        gap.append(node.id)
    node = node.parent                     # :2107
```

Two facts follow:
* A node with `storage_written == True` is **never** collected, so `write_backup_storage`
  (`unified_radix_cache.py:4899-4900`) never re-submits it:
  `if not self.tree_core.is_storage_written(nid): self._write_backup_storage_node(nid)`.
* The walk stops at the first `storage_persisted` ancestor (`:2103`), so once a node is a persisted
  anchor it is never even a gap candidate.

`storage_written` is set at submission (`mark_storage_written`, `unified_tree_core.py:2111-2113`;
called at `unified_radix_cache.py:5010`) and set again on ack
(`advance_storage_persisted`, `unified_tree_core.py:2270`). It is cleared in exactly one path:
a *partial* page batch ack (`clear_storage_written`, `unified_tree_core.py:2115-2119`, called at
`unified_radix_cache.py:7442`) — the fail-closed "will rewrite" case, not normal traffic.
`clear_storage_durable` (`unified_tree_core.py:2176-2209`, called on a zero-hit prefetch at
`unified_radix_cache.py:6657`) clears `storage_persisted` / `storage_restored` but **does not**
clear `storage_written`, so it does **not** re-enable collection either. This is the exact
"`mark_storage_written` dedupe + `collect_storage_gap` walks past `storage_written`/`storage_persisted`"
mechanism the task asked to identify.

### 1.3 Eviction does not re-enable the write; only deletion does

Normal demotion keeps the node: `UnifiedTreeCore.evict_device_leaf`
(`unified_tree_core.py:1306-1333`) calls `_demote` for a backed-up node; the node and its
`storage_written` survive. `evict_device_leaf_storage_backed` hollows in place
(`unified_radix_cache.py:3134-3152`). The node is *deleted* only by the write-back fallbacks
`drop_subtree_no_host` (`unified_tree_core.py:1335+`, invoked at `unified_radix_cache.py:3125-3132`)
and `drop_device_leaf_to_miss` (`unified_tree_core.py:1463+`, invoked at `:3154-3191`), which
detach the subtree. A later insert of the same content then creates a **new** node with
`storage_written=False`, and that new node is written again.

So the only production mechanism that ever produces a second write for a page is
**delete-then-reinsert**, and deletion happens to *evicted subtrees* — i.e. tail-first under
capacity pressure.

### 1.4 Matched pages are excluded from the backup span (the L1/L2 short-circuit)

`insert` matches the resident chain and only creates/extends the unmatched suffix
(`unified_tree_core.py:1985-2010`); `_should_backup_after_insert` (`:1095-1109`) only backs up a
new leaf or a node with an unmet incremental component backup. The anchor pages that are hit in
L1/L2 are never the target of `write_backup_storage`, and (1.2) they are never a gap node either.
Hence the observed write-once head.

Empirical confirmation from the preserved WAL (`frames.json`, `analyze_wal.log`): over 2044 SET
frames / 23168 marker pages, `{n_writes -> n_pages} == {1: 3, 2: 23165}`; pages 0,1,2 have exactly
one write each (`seq=1` p0; `seq=4` p1,p2), every other page has two. Round-1 body pages were
written at `seq=29` / `seq=2098..2175`; round-2 re-entered only pages 3.. (not 0..2) at
`seq=3735..3784`. That is precisely (1.4): the round-2 request matched 0..2 in cache and started
its span at 3.

---

## 2. (b) What bounds the SIZE of the run — the decisive question

### 2.1 There is no tree- or storage-semantic cap

From §1, once a node is written/persisted, **nothing in the tree or the extent backend ever
re-enters it**. The only thing that can re-enter a page is deletion + re-insertion (§1.3), which
requires the prefix to be evicted. Eviction is LRU/capacity/workload policy — it is not a
tree/storage invariant, and there is no periodic refresh of persisted ancestors anywhere in the
write path (`write_backup_storage` + `_flush_pending_storage_writes` +
`_reconcile_deferred_acked` only touch gap / deferred nodes, never fully persisted ancestors).

Therefore:

```
RUN = the leading prefix that is never deleted (never evicted) for the lifetime
      (or, a superset: the leading prefix that is simply never re-requested)
```

which is exactly the **leading cache-resident prefix**.

### 2.2 Explicit model: the owner's "64K then 128K, re-used repeatedly" session

Let the session prefix grow by appends at the tail and be re-used; let the cache keep a leading
resident run `R` pages (LRU on a radix tree evicts leaves, i.e. the tail, so the head is the part
that survives).

* While `context <= capacity`, the whole prefix is resident. Every append creates a new node that
  is written exactly once; no existing node is ever re-entered. So `RUN == context/page_size`
  — it **grows linearly from 64K to 128K**. This is the negative case.
* While `context > capacity`, `RUN == R <= capacity`, which is still not a small constant and is
  set by buffer size, not by tree semantics.

There is no structural reason the run is a small constant. The incident's run was only 3 pages
because *that* workload's body was evicted at a small cache (the body is what re-wrote: page 3
has 2 writes), not because tree semantics cap the run. The empirical instance is a property of
capacity/workload, not of the rule.

### 2.3 Executable demonstration (real tree + real `ExtentFileBackend`)

`bound_demo.py` builds the growing-session model on the real `UnifiedRadixCache` /
`UnifiedTreeCore`: insert `toks[:1]`, `toks[:2]`, … `toks[:N]` (each append matches the chain and
creates one new node), set the host value, then run the **real normal write helpers**
`collect_storage_gap` → `build_storage_backup_spec` → `advance_storage_persisted` for the new
node. It then seeds the real `ExtentFileBackend` with the whole chain, recycles the slots holding
the leading pages (the allocator's circular wrap), and calls the real `batch_exists` from page 0.

`/tmp/opencode/f1-optionA-anchorrun-20260916/bound_demo.json` (abridged; full JSON in the artifact):

```
{"n_nodes": 6,  "n_pages": 6,  "n_ever_written_pages": 6,  "n_write_once_pages": 6,
 "leading_never_rewritten_run": 6,  "run_fraction_of_chain": 1.0,
 "batch_exists_from_page0_after_head_slot_recycle": 0, "recycled_slots": [0,1]}
{"n_nodes": 12, "n_pages": 12, "n_ever_written_pages": 12, "n_write_once_pages": 12,
 "leading_never_rewritten_run": 12, "run_fraction_of_chain": 1.0, ...}
{"n_nodes": 24, "n_pages": 24, ..., "leading_never_rewritten_run": 24, ...}
{"n_nodes": 48, "n_pages": 48, ..., "leading_never_rewritten_run": 48, ...}
```

`leading_never_rewritten_run` equals the **entire chain** (fraction 1.0) and scales 6→12→24→48
with the prefix, and once the leading slots recycle `batch_exists(chain from page 0) == 0` for
every N. This is the requested Step-1 executable demonstration, and it is a negative result.

### 2.4 Why the incident's run was 3 (and why that does not bound the rule)

The preserved WAL proves the boundary between never-rewritten and rewritten is *residency*, not a
tree rule: p0/p1/p2 (nodes A,B) stayed resident and were written once; the body (nodes C,D) was
evicted, re-inserted, and therefore rewritten. The run is the resident head. When the resident
head is the whole prefix (the 64K/128K reused case), the run is the whole prefix.

---

## 3. (c) Explicit bound expression

There is no bounded expression in terms of tree/storage structure. The honest expression is:

```
RUN <= |leading prefix that is never deleted|  <=  min(context / page_size, (L1+L2 capacity)/page_size)
RUN == context / page_size     when  context/page_size <= capacity/page_size
```

and the last line is the owner's 64K→128K case: `RUN` grows with the logical context. The code
that makes the `<=` true is `collect_storage_gap`'s `not storage_written` guard plus the
`storage_persisted` walk stop (`unified_tree_core.py:2089-2109`), `mark_storage_written`
(`:2111-2113`), `advance_storage_persisted` (`:2262-2304`), and the fact that the only
re-entry is delete-then-reinsert (`unified_tree_core.py:1335+`, `:1463+`; invoked at
`unified_radix_cache.py:3125-3132`, `:3154-3191`). **No code makes the run a constant / small
bound.**

Consequence for the requested fix: refreshing "the whole leading never-rewritten run" is
O(context) in the target workload, which the task forbids. **UNAVAILABLE.**

---

## 4. Follow-on design (reported, NOT implemented, per the task)

The bounded replacement is not write-side repetition; it is to make extent-slot reclaim
*non-destructive for live refs* — i.e. **live-ref relocation / compaction on slot reclaim**
(move the refs of pages that are still required to free space before the slot's generation bump,
under the existing group-commit ordering), rather than refreshing an unbounded run of pages on
every backup or pinning pages permanently. This needs its own design/authorization and was not
attempted here.

---

## 5. Artifacts and identity

Frozen tree under test (unmodified):
`/opt/sglang/local-prod-v1.1-candidate/src/python/sglang` — no file newer than the freeze; the
extent dir is read-only (`dr-xr-xr-x`), so no `__pycache__` could be written.

Artifacts (in `/tmp/opencode/f1-optionA-anchorrun-20260916/`):

| file | sha256 | role |
|---|---|---|
| `BOUND-PROOF.md` | (this file) | proof |
| `bound_demo.py` | `7ae91757734926be005741720e1182877294e18720f82dece7ced150031a1147` | executable negative demo (real tree + real backend) |
| `bound_demo.json` | `0bf949f97463ebb14406c0d8c2af3d0bf45da3671aff00e17c619202d3504965` | demo results |
| `analyze_wal.py` | `e4434a3f5c1e241907cd871a0aed64ac2bfe729e25a982df2c951212b606db4c` | WAL write-history (frozen code) |
| `analyze_wal.log` | `2b68771d6859568013a0bb15d3c923550c5da476c87e92c5195100b1622d19d4` | write-once histogram `{1:3, 2:23165}` |
| `fast_frames.py` | `8907e3f8596ce71c167abecb5b26e6415d912d47d0af90e922b7890d7ea226ef` | per-frame SET/DROP scan |
| `frames.json` | `9dff1e58450876ea81cdec05d988f163aad83395db17d9cbd918b2c0bc4ff29b` | 5035 frames; round-1/round-2 page ranges |

`sha256sum` of each changed/added frozen-tree file vs frozen: **none** (no change; changed-file
list is empty). Authoritative tree: none (no candidate tree created).

## 6. Confirmations

* No frozen tree / workspace / `/data` write: `find /opt/sglang/local-prod-v1.1-candidate -newermt '2026-09-17 00:00'` returned nothing; the frozen `src` subtree is read-only.
* No GPU lock acquired or touched (`/tmp/opencode/gpu-3090.lock` untouched); CPU-only
  (`CUDA_VISIBLE_DEVICES=999`) for the demo; no server; no port; ports 30000/30164 unused.
* STEP 2 not started: no implementation, no test-suite runs (no code to test).
