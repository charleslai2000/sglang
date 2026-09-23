# B4-R4 report

## Verdict

```text
BLOCKED — R4 reached host-only target and host-hit, but did not prove the
required FULL/MAMBA H→D transfer completion and target device restoration.
```

B5/B6 were not run.

## WRITE_THROUGH SEMANTICS — code audit

The actual lineage call chain is:

```text
UnifiedTreeCore._insert_tail_step()
  -> _should_backup_after_insert()
  -> _inc_hit_count_and_check()
  -> BackupKV action
  -> UnifiedRadixCache._execute_and_commit_kv_backup()
  -> tree_core.build_backup_spec()
  -> cache_controller.write()
  -> tree_core.commit_backup()
```

Relevant files:

```text
python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py
  _inc_hit_count_and_check: 896
  _should_backup_after_insert: 1043
  _insert_tail_step: 1117
  evict_device_leaf: 1306
  _demote: 1704
  _build_backup_kv_action: 2451

python/sglang/srt/mem_cache/unified_radix_cache.py
  _evict_device_leaf: 3119
  evict loop / deferred backup: 3234-3252
  _execute_and_commit_kv_backup: 4351

python/sglang/srt/mem_cache/hiradix_cache.py
  write_backup: 878
  _inc_hit_count: 1020
  _evict_write_through: 1251
  _evict_backuped: 1316
```

Answers:

1. Ordinary request completion does not universally trigger backup. A new leaf
   must pass the insert hit-count path; chunked inserts skip it. The R3 target
   was chunked because it exceeded `chunked_prefill_size=2048`, explaining its
   host_used=0. R4 used a 1900-token target and did trigger backup.
2. For this `write_through` runtime, device eviction of an unbacked leaf does
   not issue D→H before eviction. `UnifiedTreeCore.evict_device_leaf()` deletes
   an unbacked leaf when `is_write_back=False`. A backed-up leaf is demoted by
   `_demote()`; the D→H backup happened earlier through the insert hit-count
   path. The deferred D→H-before-demote branch in `UnifiedRadixCache` is for
   `is_write_back=True`.
3. For a write-through backed-up node, backup commit/ack precedes device value
   release. `_finish_write_through_ack()` confirms DMA and releases the lock;
   `_demote()` then removes device residency during eviction. The R4 durable
   trace records backup_host_commit for target node 18 before its later device
   detach.
4. FULL and MAMBA are coordinated in one `build_backup_spec`/`commit_backup`
   action. The R4 trace recorded `kv_transfer=true` and `mamba_transfer=true`
   for target node 18. `_demote()` cascades from the Full trigger to equal/lower
   priority components, so device removal is coordinated.
5. Backup is skipped when the node is a new/unchunked leaf that has not reached
   the hit threshold, when `chunked=True`, when write policy is write_back in
   the insert hit path, when the parent is not backed (contiguous-prefix
   invariant), when no device value/transfer remains, or when host allocation
   fails. Device eviction also directly deletes an unbacked leaf in write-through.

## TARGET INITIAL / BACKUP

Target was 1900 input tokens, aligned to 1792 cache tokens, and was never
requested again until suffix B.

After target A:

```text
FULL host_used: 1792
MAMBA host backup counter: +1
FULL backup counter: +1792
```

Durable probe:

```text
backup_host_commit node_id=18
host_tokens=1792
kv_transfer=true
mamba_transfer=true
```

This establishes the target's FULL and MAMBA host backup. Public metrics do not
expose node refcount/LRU membership; the marker-gated durable trace supplies
node/device detach lifecycle events but not a complete LRU snapshot.

## TARGET EVICTION

Pressure used 14 batches × 8 distinct prefixes × approximately 1900 tokens,
with no target request during pressure. Runtime host usage reached:

```text
201423 tokens / 281377-token runtime FULL host pool
```

Device eviction occurred:

```text
evicted_tokens_total: 67735
hicache_dropped_tokens_total{pool=kv}: 0
hicache_dropped_tokens_total{pool=mamba}: 0
```

For target node 18, the durable trace recorded:

```text
backup_host_commit node 18, kv_transfer=true, mamba_transfer=true
then:
  mamba device detach, reason=device_leaf
  FULL/KV device detach, reason=device_leaf
  MAMBA device detach, reason=device_leaf
```

The target node remained addressable through host lookup: suffix B reported
`cached_tokens=1792` and `cached_tokens_details={device: 0, host: 1792}`.
This is authoritative host-only match evidence. The trace does not show a
node deletion for node 18.

## RESTORE

Suffix B completed successfully:

```text
HTTP: PASS
cached tokens: 1792
FULL host hit: +1792
MAMBA host hit: not separately exposed by public counter
FULL/MAMBA H→D transfer issue/completion: not independently exposed/proven
post-request device residency: not captured as a complete node snapshot
```

The request generated coherent output and the target sentinel was present in
the prompt path, but semantic/state acceptance is not upgraded to B4 PASS
without the requested component-specific H→D transfer evidence.

Counter delta from before to after B:

```text
host_hit: +1792
input: +116
load_back / PoolName.FULL: no independent positive counter
load_back / PoolName.MAMBA: no independent positive counter
```

The R4 artifacts show a host-only lookup and successful request, but not the
required separate FULL and MAMBA H→D issued/completed transfer IDs. Therefore
R4 is not classified as Case F.

## ROOT CAUSE

The R3 single-request result was explained by actual code semantics: its
approximately 2K+ request was chunked and `chunked=True` suppresses the
write-through hit-count backup trigger. R4 corrected the test with a 1900-token
unchunked target and demonstrated the backup and eviction lifecycle. The
remaining blocker is observability: public metrics and the existing durable
trace do not independently expose completed FULL/MAMBA H→D transfer IDs or a
post-restore node snapshot.

## PATCH

```text
none
```

No production source was modified.

## ARTIFACTS

```text
runs/r4/server.log
runs/r4/probe.stdout
runs/r4/r4-result.json
runs/r4/metrics-before.txt
runs/r4/metrics-after-A.txt
runs/r4/metrics-b00.txt ... metrics-b13.txt
runs/r4/metrics-before-restore.txt
runs/r4/metrics-after-B.txt
runs/r4/t38c-probe-tail.txt
/tmp/t38c-probe.log (copied/filtered as above)
```
