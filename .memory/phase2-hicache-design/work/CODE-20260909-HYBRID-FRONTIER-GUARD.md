# CODE-20260909-HYBRID-FRONTIER-GUARD

```text
status: done
task_id: CODE-20260909-HYBRID-FRONTIER-GUARD
orchestration_epoch: 20260909-P4
role: coder
branch: 3060-12g-qwen35-4b
base_commit: 7caa438f623b5acd3f5c05183d0b083d27b337f5
commit: 5b61e63993b65ee1fe6380f6bfab455e40b34270
```

## Summary

Implemented the minimal safe guard for the confirmed hybrid L3 prefetch
frontier mismatch. In cache-mode host-capacity fallback, an operation with a
`TRAILING_PAGES` sidecar is no longer cropped to an arbitrary shorter KV
frontier. It follows the existing revoke/decline path before mutating
`storage_hit_count` or `hash_value`, so no sidecar read or hybrid discard is
claimed for an unvalidated boundary.

KV-only crops and full-size hybrid allocations retain their prior behavior.
No file naming, durability, ACK, all-or-nothing discard, or scheduler logic
was changed. The 3090 production-candidate worktree was not modified.

## Changed files

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - Added `_storage_hit_crop_is_safe` using the existing
    `PoolHitPolicy.TRAILING_PAGES` contract.
  - Gated only the cache-mode shorter-prefix allocation path.
- `test/registered/unit/mem_cache/test_unified_radix_hicache_dispatch.py`
  - Added deterministic regression for a 54,976-page validated KV/Mamba
    frontier cropped to 21,060 pages whose shortened Mamba boundary is absent.
  - Added compatibility assertions for KV-only crop and full-fit hybrid load.

## Verification

Passed:

```text
python3 -m py_compile \
  python/sglang/srt/mem_cache/unified_radix_cache.py \
  test/registered/unit/mem_cache/test_unified_radix_hicache_dispatch.py
git diff --check
```

The focused test was attempted with:

```text
python3 test/registered/unit/mem_cache/test_unified_radix_hicache_dispatch.py
PYTHONPATH=python python3 test/registered/unit/mem_cache/test_unified_radix_hicache_dispatch.py
```

The first command could not import the source package (`No module named sglang`).
With `PYTHONPATH=python`, import reached the repository source but stopped on
the pre-existing environment dependency `orjson` (`No module named orjson`).
No focused test body executed. `pytest` is not installed in the
available environment.

Final scope check after commit showed only the two requested files in the
commit. Existing unrelated untracked paths remain unmodified:
`review/gates/P0-3060-RUNTIME-COMPAT.md`, `review/gates/P0-3060-SM86-GDC.md`,
and `storage/`.

## Followups

- Run the focused regression in the project test environment with SGLang
  dependencies installed.
- Perform the separately authorized 3060 runtime reproduction before claiming
  live hybrid reliability.

## Open issues

- Focused unit execution is pending because this environment lacks `orjson`
  and `pytest`.
- No runtime or remote system action was performed under this implementation
  task.
