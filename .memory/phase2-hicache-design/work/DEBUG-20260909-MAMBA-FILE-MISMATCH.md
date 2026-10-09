# DEBUG-20260909-MAMBA-FILE-MISMATCH

```text
status: done
task_id: DBG-20260909-MAMBA-FILE-MISMATCH
orchestration_epoch: 20260909-P4
role: debugger-deep
scope: read-only local source and authorized remote source/log/storage inspection
```

## Conclusion

The two failures are caused by a **hybrid prefetch frontier mismatch introduced
by cache-mode host allocation**, not by a file-name construction mismatch.

The storage query correctly found a 54,976-page KV prefix and confirmed that a
Mamba state existed at *that queried prefix's tail*.  The scheduler then lacked
enough host staging space and silently shortened each operation to 21,060 or
21,121 pages.  The hybrid sidecar reader consequently changed the required
Mamba key to the tail of the shortened prefix, but did not re-run the
existence check at that new frontier.  Those two new keys do not have Mamba
files.  The file read returns `FileNotFoundError`, the all-or-nothing hybrid
check discards the otherwise-read KV prefix, and the request recomputes.

This makes the diagnostic field `sidecar_hits={mamba:54976}` easy to
misinterpret.  For `TRAILING_PAGES`, it means “the Mamba tail condition holds
at the 54,976-page query frontier,” not “54,976 independently retrievable
Mamba pages” and not “a Mamba file exists at every later host-cropped
frontier.”

## Reconstructed timeline

All times are remote, 2026-09-09 +08:00.  The trace and server log use the
same epoch timestamps.

| RID | Query | Cache-mode allocation/IO | Actual Mamba read | Terminal result |
| --- | --- | --- | --- | --- |
| `c68cd7e4f0484aaf915443d0764eada4` | `06:23:37.984`: KV=54,976; Mamba=54,976 | issued `06:23:31`; `pc_l3_host` / IO complete=21,060 at `06:25:01.329` | `c08bb650…mamba`, absent; sidecar `hit_pages={mamba:0}` | `06:25:12.397` `RECOMPUTE`, `hybrid_discard` |
| `80bd3e2ca21f49a989386f6f563a97a8` | `06:25:18.688`: KV=54,976; Mamba=54,976 | issued `06:25:12`; `pc_l3_host` / IO complete=21,121 at `06:25:30.577` | `c7c2f7ee…mamba`, absent; sidecar `hit_pages={mamba:0}` | `06:25:35.837` `RECOMPUTE`, `hybrid_discard` |

The relevant exact log lines are:

```text
[06:25:01] Failed to fetch c08bb650...bed4fb88.mamba from HiCacheFile storage.
[06:25:12] HiCache hybrid prefetch discarded req=c68... completed=21060 requested=21060 kv_beliefs_kept_pages=21059
[06:25:30] Failed to fetch c7c2f7ee...9422ccd9.mamba from HiCacheFile storage.
[06:25:35] HiCache hybrid prefetch discarded req=80bd... completed=21121 requested=21121 kv_beliefs_kept_pages=21120
```

The two query records and two sidecar-read records are in remote
`/tmp/t38c-probe.log`; the failures and terminal states are in remote
`/tmp/sglang3060-p4-fix.log`.

## Causal chain and code locations

1. `HybridCacheController._storage_hit_query`
   ([hybrid_cache_controller.py](/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py:848))
   first queries KV, then aligns each `TRAILING_PAGES` sidecar to the found
   KV frontier in `_align_storage_query_transfers` (lines 943–958).  Thus the
   Mamba check is for the final page of the 54,976-page storage hit.

2. The scheduler's cache-mode fallback deliberately crops a known L3 hit to
   currently free host capacity:
   [unified_radix_cache.py](/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py:5859).
   It sets both `operation.storage_hit_count = alloc_len` and
   `operation.hash_value = operation.hash_value[:alloc_len // page_size]`
   at lines 5874–5875.  The observed `alloc_len` values are 21,060 and
   21,121, despite the query's 54,976 pages.

3. Once cropped, the KV IO is complete relative to the *cropped* hash list,
   so `_page_transfer_sidecar` runs
   ([hybrid_cache_controller.py](/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py:998)).
   It calls `_sync_trailing_keys` at lines 1018–1020, which changes the Mamba
   key to the last hash at the 21,060/21,121-page frontier.  This is exactly
   the `c08bb650…` / `c7c2f7ee…` pair printed by the file backend.

4. `HiCacheFile._read_page` makes that key into
   `<hash>.mamba_-hy-tmp-models-Qwen3.5-4B-AWQ_0_1.bin` via
   `_log_key` and `_get_suffixed_key`
   ([hicache_storage.py](/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/hicache_storage.py:442),
   [hicache_storage.py](/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/hicache_storage.py:659)).
   `open()` raises `FileNotFoundError`, logged at line 491; the sidecar read
   reports zero hits.

5. `_check_hybrid_prefetch_result` requires all non-KV hybrid transfers to
   succeed and otherwise releases the loaded KV staging and reports
   `hybrid_discard`
   ([unified_radix_cache.py](/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py:5293)).
   Hence an otherwise valid 21K KV prefix cannot be used without its Mamba
   state, resulting in full-history recomputation.

The assigned local branch and remote runtime source agree for all four
causally relevant files:

```text
7c5c7331... hicache_storage.py
5bc3ac23... hybrid_cache_controller.py
0eba576e... unified_radix_cache.py
43b57f5a... managers/cache_controller.py
```

## Remote storage evidence (captured 06:31 +08:00)

`/hy-tmp/hicache-qwen35-4b-p4-retry-20260909` contained 275,065 files,
11,551,690,752 bytes: 274,929 non-Mamba `.bin` files and 136
`.mamba_*.bin` files.  Each Mamba file was 51,511,296 bytes.

Both exact KV files exist while their matching Mamba files do not:

```text
present c08bb650...bed4fb88_-hy-tmp-models-Qwen3.5-4B-AWQ_0_1.bin 16384 B 06:01:27
absent  c08bb650...bed4fb88.mamba_-hy-tmp-models-Qwen3.5-4B-AWQ_0_1.bin
present c7c2f7ee...9422ccd9_-hy-tmp-models-Qwen3.5-4B-AWQ_0_1.bin 16384 B 06:02:46
absent  c7c2f7ee...9422ccd9.mamba_-hy-tmp-models-Qwen3.5-4B-AWQ_0_1.bin
```

This independently confirms the precise filename used by the reader and
rejects a suffix/model/TP-prefix mismatch.

## Competing hypotheses

| Hypothesis | Verdict | Evidence |
| --- | --- | --- |
| Filename or rank/model-prefix mismatch | Rejected | Writer and reader share `_get_component_key`; the exact expected basename is present for KV and absent only for `.mamba`. TP=1 and the suffix on disk is the expected `_..._0_1`. |
| Stale metadata-cache positive lookup | Rejected for this run | The launch extra config is only `{"hicache_storage_pass_prefix_keys":true}` and the server environment has no metadata-cache enable variable. `HiCacheFile` therefore uses `metadata_cache=None`; `batch_exists_v2` scans actual directory entries (lines 589–595). |
| File deletion/eviction after the 54,976 query | Not evidenced; in-process eviction rejected | The server environment has no `MAX_SIZE` or `MIN_FREE_SPACE` setting, so the LRU evictor is inert by default. The log contains zero `HiCacheFile eviction enabled`, reclaim, clear, save-failure, or no-space records. No external deletion audit exists, so external deletion cannot be ruled out absolutely; it is unnecessary to explain the failure. |
| Sidecar never successfully persisted for these exact shortened boundaries | Actual file absence confirmed; historical write cause unproven | Both required files were absent at fetch and remain absent. The retained trace has no per-key write/ACK record for either hash, so it cannot prove whether the state was never submitted, was write-refused, or was externally removed before this run. The runtime fault is nevertheless proven: it asks for a different boundary than it validated. |
| Query/read frontier mismatch after host crop | Confirmed root cause | 54,976 query hit -> 21,060/21,121 crop -> `_sync_trailing_keys` new tail -> exact missing Mamba read -> zero hit -> `hybrid_discard`. |

## Minimal safe fix location and contract

If this behavior is to be fixed, ownership belongs to the implementation
path around `_try_alloc_storage_hit` in `unified_radix_cache.py`, before it
mutates `operation.hash_value` for the cache-mode memory-pressure fallback.

Required contract:

> A hybrid L3 prefetch may launch only at a frontier for which every required
> trailing sidecar is physically present and whose sidecar staging transfer is
> keyed to that same frontier.  Cropping a query hit must either revalidate and
> select a sidecar-complete checkpoint at or below the new capacity, or defer
> the restore until the originally validated frontier fits.  It must not crop
> the KV list and only later discover the sidecar key has changed.

The smallest safe behavioral shape is to select a sidecar-complete prefix
`<= available_size` before allocating host indices, then set both the KV
operation frontier and trailing transfer keys from that selection.  A simpler
but lower-availability safe fallback is to decline/defer arbitrary cropping
for `TRAILING_PAGES` pools rather than issuing a known-invalid hybrid transfer.
Do not alter file naming, write atomicity, ACK meaning, or the all-or-nothing
hybrid discard invariant; those are not the defect.

The implementation needs a focused regression with all of these observables:

1. query hits a long KV prefix and a Mamba tail at its original frontier;
2. host capacity forces a smaller, non-identical frontier;
3. the selected shorter frontier is checked for its Mamba tail before IO;
4. if a valid checkpoint exists below capacity, KV + Mamba read succeed and
   no `hybrid_discard` occurs; otherwise the request remains/defer-waits
   without claiming a Mamba hit for the unusable prefix.

## Open issues / missing evidence

- The existing trace is not a per-key write journal. It does not establish the
  historical producer-side reason each shortened-boundary Mamba file is absent.
- No external filesystem audit was authorized or available. The conclusion
  excludes in-process LRU/clear deletion, not an unlogged external actor.
- The current evidence proves the read-side causal bug; it does not authorize
  an implementation or a new remote reproduction.

## Artifacts

- Remote read-only sources: `/tmp/sglang3060-p4-fix.log`,
  `/tmp/t38c-probe.log`, and
  `/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`.
- Local source: branch `3060-12g-qwen35-4b`, commit reported by prior audit as
  `277dd611001c31edcd3a8894213c5a44b00e9bd4`.
- This report is the only local write made by this task. No product files,
  3090 code, remote source, remote storage, or remote process was changed.
