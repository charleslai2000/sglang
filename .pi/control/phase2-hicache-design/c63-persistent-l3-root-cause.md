# Phase C6.3 — persistent L3 lookup root-cause closure

Authority: `c4d550255c9b697f21026ff19b779a72bc534cfc`.

## Verdict

```text
PERSISTENT_L3_ACROSS_RESTART=FAIL
HICACHE_STORAGE_REUSE=FAIL
HICACHE_STORAGE_RESTORE=FAIL
HICACHE_CORRECTNESS=PASS
CANONICAL_TREE_CLEAN=YES
CANONICAL_COMMIT=c4d550255c9b697f21026ff19b779a72bc534cfc
```

No canonical source fix was justified or made.

## Persistent metadata and reopen

The existing C6.1 root was retained without deletion or repopulation:

```text
root=/data/l3/c61-qwen-20260922-220343
run_id=c61-qwen-20260922-220343
model=/data/models/qwen35-9b-w4a16
config suffix=_-data-models-qwen35-9b-w4a16_0_1
```

The new process reopened the exact same data path and geometry:

```text
extent=67108864 B
slots=1024
max_size=100 GiB
min_free=50 GiB
```

The persistent manifest parsed successfully in a standalone canonical import:

```text
entries=2049
next_slot=807
max persisted generation=3
slot_bytes=85065728
checkpoint_lsn=4846
wal_floor=1
```

The data file remained a 64 GiB sparse address space with approximately 39 GiB actual usage. Startup produced no manifest-corruption, WAL-corruption, geometry, or allocator-recovery error. This proves manifest/WAL reopen and allocator generation/index recovery completed; it is not a recovery initialization failure.

The manifest contained keys with the expected suffix, for example:

```text
..._-data-models-qwen35-9b-w4a16_0_1
```

and generation-bearing entries. The C6.2 runtime nevertheless reported `storage_generation=0` only for the queried prefix, not for the backend globally.

## Lookup chain evidence

The new process started with empty GPU/Host pools and replayed the C6.1 document-0 prefix with a changed suffix. It returned HTTP 200 and coherent output, but the direct restore path recorded:

```text
prefetch_revoke ... storage_hit=0 ... requested=57025 ... miss_reason=miss
restore_state=MISS_RECOMPUTE
rh_preadmission ... negative_cache ... NO_L3
```

Metrics remained:

```text
hicache_host_used_tokens=0
prefill_effective_tokens_total{mode="device_hit"}=0
prefill_effective_tokens_total{mode="host_hit"}=0
prefill_effective_tokens_total{mode="storage_hit"}=0
```

Thus the first decisive runtime boundary is:

```text
persistent metadata: readable
backend reopen: PASS
allocator generation/index recovery: PASS (2049 entries, generations through 3)
lookup key for replayed prefix: absent from recovered index / storage_hit=0
extent read: not reached
KV restore: not reached; MISS_RECOMPUTE
```

No extent read error or KV restore error occurred because the lookup returned no reference.

## Root-cause classification

This is **not** currently classified as a manifest/WAL recovery defect, generation persistence defect, or extent read defect. The recovered allocator is populated and the storage backend is using the expected data file/suffix.

The original C6.1 root was kept active during the pressure run after the first Host-tier reuse. The final manifest has only 2049 live entries and generation 3, while the pressure run performed repeated extent slot drops/rewrites. The C6.1 successful request was explicitly satisfied by Host (`device=10, host=14326, storage=0`), not by L3. Therefore the exact document-0 L3 pages were not proven to survive as live entries until shutdown; they may have been evicted/replaced during continued pressure. Reusing the root later does not resurrect keys that the live allocator legitimately dropped.

A separate offline tokenization comparison also found no exact match against the current manifest's bare KV hashes for the reconstructed prompt form; the HTTP tokenizer path adds special handling, so that comparison is supportive rather than the acceptance proof. The decisive runtime fact remains the recovered-index miss with no backend read.

## Why no source change

A minimal source change would require changing persistent retention/eviction or key/namespace semantics, which is outside the frozen production contract and would not be a local correctness fix. The observed behavior is consistent with an evicted target prefix and/or replay prompt key not being one of the currently live persisted entries. No code was changed and no pressure/population was repeated, per C6.3 boundaries.

## Correctness and boundaries

The fresh-process replay produced HTTP 200 and coherent non-empty output. No OOM, illegal access, cache corruption, or fatal runtime error was observed. The service was stopped and GPU memory returned to 4 MiB used / 24121 MiB free.

No branch/worktree/deployment cleanup, push, `main` modification, root deletion, root recreation, or repopulation occurred.

## Remaining acceptance gap

To pass persistent L3 restore without changing semantics, a future run must preserve a specifically identified live L3 key set through shutdown, then restart before additional eviction can remove the target, and verify the exact runtime-generated hash sequence. C6.3 did not claim PASS because the existing root alone cannot prove that the requested prefix remained in its recovered live index.
