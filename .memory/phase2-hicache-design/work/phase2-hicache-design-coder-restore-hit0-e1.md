# phase2-hicache-design-coder-restore-hit0-e1

## status
done

## artifacts

Root-cause analysis only — **no production code changed**. Read 3090 FBE-rerun
evidence over SSH (`root@175.155.64.171 -p 24052`, evidence
`/root/evidence-gate2-fbek{4,8,16}/`, engine logs
`/root/engine-gate2-fbek{4,8,16}.log`, extent file
`/data/l3/p2io-gate2-fbek16/hicache.data_qwen3.5-9b-gptq_0_1`) plus local
`3090-dev/evidence/gate2-k{4,8,16}/` and the gate1/gate2 reports.

Verdict: **B primary (1949/1951), C secondary (2/1951), A ruled out.**

- **B root cause = extent backend watermark GC eviction of committed keys.**
  `ExtentFileBackend._gc_evict` (extent_file_backend.py:860-889, watermark
  `used_bytes > max_size × eviction_ratio` = 20G×0.9 = 18G) evicts LRU slots
  on every `_write_pages`. Gate2's aggregate logical write volume is ~232GB,
  ~11.6x the 20G budget → GC recycles every slot continuously. Committed
  KV/mamba keys are recycled before their restore query → `_allocator.lookup`
  returns None → `kv_hit_pages=0`, `sidecar_hits={}`.
- **C secondary = mamba TRAILING boundary clamp.** When KV pages do survive
  to the query, `batch_exists_v2`'s mamba TRAILING scan (extent_file_backend.py
  :648-668) finds no contiguous mamba checkpoint (it was GC'd, 51.5MB evicted
  first) → `boundary=0` → `final_pages = min(kv_pages, 0) = 0`. The 2/1951
  queries with `sidecar_hits={'kv':594}` and `kv_hit_pages=0` prove this.
- **A ruled out**: query keys[0] byte-identical to committed pc_write_seed
  page0_hash (1643/1951); single backend instance, single file, single
  config_suffix; get_prefix_hash_values has no lru_cache (PR #26177 fix
  present — returns fresh lists).

## evidence

All 3090 commands real, exit codes captured directly. Key numbers:

### Write volume vs GC budget
```
gate1-churn.log (WORKS):  kv pages=133374 (4.37GB) + mamba 71 (3.66GB) = ~8GB
                          < 20G budget -> 0 extent_recycle events -> restores hit
gate2-fbek16.log (FAILS): kv pages=3,871,854 (126.9GB) + mamba 2051 (105.6GB)
                          = ~232GB logical >> 20G budget
                          -> 6144 extent_recycle events (slot 0 generation 1..6144)
```
GC config (engine log): `ExtentFileBackend: file=... extent=67108864 B
slots=1024 max_size=20000000000 min_free=10000000000` (extent 64MB, 1024
slots, max 20G, eviction_ratio 0.9 default).

### Recycle frees (all 232GB logical recycled)
```
recycle events: 6144 ; total freed 232.5GB
mamba-sized recycles (51511296 B): 2051  (every mamba checkpoint eventually evicted)
kv-1024 recycles    (33554432 B): 3496
first recycle at 13:44:14 generation=1 (a mamba slot recycled right after write)
mamba-write->next-recycle gap: 2-90 ms
```

### Query vs commit timing (rules out "too early")
```
queries ts range 1788500637.588 - 1788501794.409
extent_write commit ts range 1788500654.229 - 1788501801.85
queries after first commit: 1928 ; query before first commit: 23
query first-keys submitted-before-query: 1605/1951
single canonical boot chain key0 f9ec16cd... : 721 queries, ALL kv_hit_pages=0,
  including at ts 1788501794 (well after its commit at 1788500654229)
```

### A ruled out — key equality
```
unique query keys[0]: 240 ; query keys[0] present in seed page0 set: 1643/1951
the 2 C-cases: sidecar_hits={'kv':594} / {'kv':498} but kv_hit_pages=0
  (kv pages PRESENT, clamped by mamba TRAILING boundary to 0)
```

### Backend single-instance
```
grep -c "ExtentFileBackend: file=" = 1  (one instance, one data file)
file size 68719476736 (64G sparse), actual 50M used (sparse — GC frees slots
but file stays sparse; no disk-pressure eviction, pure watermark GC)
```

## summary

The dominant defect behind "958/958 durable-L3 KVs return storage_hit=0" is
**not** a write/read key mismatch (A) and **not** a Mamba sidecar TRAILING
fold of otherwise-present KV (C, only 2/1951). It is **B**: the extent
backend's watermark GC evicts committed keys before the restore query reads
them, because the aggregate logical write volume (~232GB across the gate2
run) exceeds the configured `max_size` budget (20G) by ~11.6x.

Code path (B): `_write_pages` (extent_file_backend.py:826) →
`_gc_evict` (:860) → `_allocator.evict_slot_lru()` (extent_allocator.py:174)
→ `_drop_slot` (generation++ + index entry removal). Query side:
`HybridCacheController._storage_hit_query` (hybrid_cache_controller.py:599)
→ `batch_exists_v2` (:618) → `_allocator.lookup(self._storage_key(key))`
(:628) returns None on the GC'd key → `kv_pages=0` → `sidecar_hits={}`.

C (secondary, 2/1951): same `batch_exists_v2`, mamba TRAILING scan (:648-668)
boundary=0 when the 51.5MB mamba checkpoint for the last page was GC'd →
`final_pages=min(kv_pages, 0)=0`.

Gate1 worked because its total logical write (~8GB) stayed under the 20G
budget (0 recycles). Gate2's high-concurrency multi-session load writes the
same chains repeatedly and in aggregate far exceeds the budget. The 20G
`max_size` was designed around ~640MB chains / ~30-chain residency
(plan-p2io.md:14 "链 ~640MB/20G 配额"); gate2's 232GB aggregate is 11x that.

## followups

1. **Fix direction (not implemented here)**: raise the extent backend
   `max_size` budget to cover the real working set (or size it by
   chains × chain bytes), OR fix `_gc_evict` to not evict L3-durable /
   recently-restored anchors (LRU on logical write volume treats a hot
   restore target as evictable the moment a new write lands). The restore
   query needs its target to survive from write-time to query-time.
   Concretely: gate2 needs max_size ≳ working-set (chains held × bytes), not
   the 20G that assumed ~30 chains. Verify a re-run with an adequate
   `MAX_SIZE` (e.g. 128G+, or matching the 64G file) yields kv_hit>0 and
   restores.
2. **C residual**: after B is fixed, re-check the mamba TRAILING clamp — the
   mamba checkpoint (51.5MB, one extent) is evicted preferentially (LRU
   oldest) and its loss zeroes the whole chain even when KV survives. A
   per-pool eviction-priority or pin for the mamba sidecar may be needed.
3. **Metric to confirm fix**: after a budget increase, `extent_recycle`
   count should drop to ~0 for the working set, and pc_storage_query
   `kv_hit_pages` should go >0 on chains written-before-query.

## open_issues

- The 20G `max_size` is passed from the launch script
  (`direct-launch-gate1.sh` line 39, `MAX_SIZE:-20G`), shared between gate1
  and gate2. The budget itself is not wrong per se — it is mismatched to the
  gate2 aggregate working set. Confirmed as the gate-2 blocker; the extent
  GC is behaving exactly as designed (watermark GC), just with a budget
  11x smaller than the load's logical volume.
- No production code changed; evidence gathered read-only from 3090 logs.
  No engine left running on 3090 (evidence from prior SIGTERMed runs).
