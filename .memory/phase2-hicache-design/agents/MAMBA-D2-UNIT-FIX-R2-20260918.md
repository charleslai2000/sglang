# MAMBA-D2-UNIT-FIX-R2-20260918

Status: DONE

Terminal state: DONE

## Task

Replace the botched D2 WAIT_CAPACITY unit-mismatch fix. Reconcile the ACTUAL bytes on
disk (do not trust prior reports), express `required_aux_units` for the failing aux pool in
REAL HOST SLOT units — never a prefix-token count, never a forced 0 — add non-vacuous
regression tests that fail under both wrong behaviors, and delete the vacuous
`tests/unit/test_mamba_unit_fix.py`.

## Scope

Write domain only (owner override):
- `python/sglang/srt/mem_cache/unified_radix_cache.py` — MODIFIED
- `python/sglang/srt/managers/scheduler.py` — NOT modified (not required; see Result)
- `test/registered/unit/managers/test_hicache_host_allocability.py` — MODIFIED
- `tests/unit/test_mamba_unit_fix.py` — DELETED (`tests/unit/` and `tests/` removed)

Read-only elsewhere. CPU only. No server, no GPU, no `/opt/**`, no `/data/**`, no git
history changes, no `.memory/**` besides this artifact. This artifact only.

## Result

**The D2 producer is now unit-correct.** The failing auxiliary pool's requirement is the
REAL host-slot demand captured at the allocator's reclaim seam and is compared against
`free + evictable` slots by an unchanged scheduler consumer.

Design (all in `unified_radix_cache.py`):

1. `evict_host(num_tokens, component_type)` now records `num_tokens` per component before
   running the eviction walk (`_note_host_alloc_reclaim_enter` /
   `_note_host_alloc_reclaim_exit`, depth-guarded first-write-wins). This is the
   authoritative slot demand because `MambaComponent.prepare_prefetch` calls
   `host_pool_group.alloc(1, pool=MAMBA, reclaim=lambda size: cache.evict_host(size, MAMBA))`
   and `SWAComponent.prepare_prefetch` calls `alloc(num_tokens, pool=SWA, reclaim=...)`;
   `HostPoolGroup.alloc` (pool_host/group.py:108-127) invokes `reclaim(need_size)` on
   alloc failure. Capture happens before the buffer-mode early return so it is always
   recorded.
2. Site A (`prefetch_from_storage`) builds `required_aux_units` via the new
   `_host_alloc_required_aux_units(comp_xfers, failed_component=ct)`. Successfully staged
   components contribute their real `host_indices` slot count; the failing component
   (which `break`s before entering `comp_xfers`) contributes its captured slot demand.
   No pool is ever assigned 0.
3. Site B (`revoke_pending_prefetch`) uses `_host_alloc_aux_transfer_slot_demand(transfer)`
   for the same slot unit: the primary `len(host_indices)` branch, and the
   `transfer.keys` fallback (pages) converted to slots via the owning host pool's
   `page_size`; the empty-transfer case returns the real-slot floor 1.
4. `_host_alloc_aux_slot_demand` never returns 0: when the capture is unavailable it
   returns the conservative real-slot floor 1 (a host-slot count, never a token count).
   This value only gates the wake/retry decision; the allocator remains the final
   authority (`free + evictable >= required` is never allocation success).

**Why `scheduler.py` was NOT changed.** The consumer at
`scheduler.py:3754-3764` is already slot-correct: for `pool == "kv"` it uses
`cursor.requested_primary_tokens` (token domain), otherwise
`int(cursor.required_aux_units.get(str(pool), 0))` compared against
`free_units_by_pool + evictable_units_by_pool` (host slot domain), and it skips
`required <= 0`. The defect was entirely producer-side. Changing the consumer would have
been out of the minimal fix and risked the KV-domain semantics.

Fail-closed properties preserved:
- No false wake from a deleted constraint: the failing pool now carries a positive
  slot requirement, so an empty/pinned pool (`free + evictable = 0`) holds the waiter.
- No permanent jam beyond the real allocator: a wake is granted when the generation
  advances OR when `free + evictable >= required` for the real slot demand; the allocator
  still decides success, and a failed retry re-parks through the existing arbiter path.

## Evidence

All commands run CPU-only with `/opt/sglang/local-prod-v1/env/bin/python`,
`CUDA_VISIBLE_DEVICES=999`, `PYTHONDONTWRITEBYTECODE=1`, in
`/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`.

### E0. Pre-fix reconciliation of on-disk bytes (FACTS)

`git diff -- python/sglang/srt/mem_cache/unified_radix_cache.py` (before my edit) was
exactly the predecessor's 1/1 change:

```
-            required_aux_units.setdefault(failed_pool, len(prefetch_key))
+            required_aux_units.setdefault(failed_pool, 0)
```

`git show HEAD:...unified_radix_cache.py | sed -n '5457p'` →
`required_aux_units.setdefault(failed_pool, len(prefetch_key))`.
`git show HEAD:...scheduler.py | sed -n '3757p'` →
`required = int(cursor.required_aux_units.get(str(pool), 0))`.
`tests/unit/test_mamba_unit_fix.py` existed (6223 bytes, untracked), vacuous: it imports
no product code and compares locally-built literal dicts to themselves.

### E1. Changed-file digests BEFORE → AFTER

```
BEFORE (sha256):
9f6d4103664728df272a140e73cdb52c6513652f340573e37293774b2356d290  python/sglang/srt/mem_cache/unified_radix_cache.py
a85e8078d476b1f5107186b58babf78d3becedf596cfc1df92343bd29165efdc  python/sglang/srt/managers/scheduler.py
5303c544c06b1767b422a9d3d923e08460ff76df01177b486b5bfcb8ad1b7419  test/registered/unit/managers/test_hicache_host_allocability.py
ef667dc7652df7d9d236178b6c8d9085083f4a2aba26787c72f24730e33871b3  tests/unit/test_mamba_unit_fix.py

BEFORE (git hash-object):
33eaf514a4e594a9e0cc0e6f8b40898529dc110a  python/sglang/srt/mem_cache/unified_radix_cache.py
dc6bf2ec4c1c7c545716bd3613cc31af2514a70d  python/sglang/srt/managers/scheduler.py
c40ca198486528a7290e3262803a18bdd3335974  test/registered/unit/managers/test_hicache_host_allocability.py
2f4ef963da4b2c024ddd07dd0bd12e4da0afedb2  tests/unit/test_mamba_unit_fix.py

AFTER (sha256):
4a5128828dc2cf67a214c794984be6f2d5177178d64cda070e35e467ec03fe1b  python/sglang/srt/mem_cache/unified_radix_cache.py
a85e8078d476b1f5107186b58babf78d3becedf596cfc1df92343bd29165efdc  python/sglang/srt/managers/scheduler.py   (UNCHANGED)
a5ad77f88e9edaec45139c4442009ffbf449beeded3329c5561e3d1b64614663  test/registered/unit/managers/test_hicache_host_allocability.py
(tests/unit/test_mamba_unit_fix.py DELETED)

AFTER (git hash-object):
e3774b9c18c2c5725264ef1a92718ec49216d9ca  python/sglang/srt/mem_cache/unified_radix_cache.py
dc6bf2ec4c1c7c545716bd3613cc31af2514a70d  python/sglang/srt/managers/scheduler.py
7ff3452a0abf40309d520532c9fd0c47ce892cfd  test/registered/unit/managers/test_hicache_host_allocability.py
```

`git diff --numstat` vs HEAD:
```
160	17	python/sglang/srt/mem_cache/unified_radix_cache.py
185	1	test/registered/unit/managers/test_hicache_host_allocability.py
```
(scheduler.py absent from numstat = unmodified.)

`git status --short` scoped:
```
 M python/sglang/srt/mem_cache/unified_radix_cache.py
 M test/registered/unit/managers/test_hicache_host_allocability.py
```
`tests/` ABSENT; `tests/unit/test_mamba_unit_fix.py` ABSENT.

### E2. py_compile (changed production + test)

```
$ /opt/sglang/local-prod-v1/env/bin/python -m py_compile \
    python/sglang/srt/mem_cache/unified_radix_cache.py \
    test/registered/unit/managers/test_hicache_host_allocability.py
PY_COMPILE_OK exit=0
```

### E3. Canonical test (verbatim)

```
$ pytest test/registered/unit/managers/test_hicache_host_allocability.py -q
23 passed, 17 warnings in 18.25s
rc=0
```

Baseline before this task (predecessor stub state) was `18 passed`. Five new tests were
added; all 23 pass.

### E4. New tests and their discriminators (FAIL under both wrong behaviors)

New class `HostAllocAuxSlotUnitTests` (5 tests). Each drives the REAL production path:
`_NoopHostPoolGroup` mirrors `HostPoolGroup.alloc` (fail → `reclaim(need_size)` → retry →
fail) and the component is the real `MambaComponent.prepare_prefetch`
(via `MambaComponent.__new__`), so the `evict_host` capture is genuinely exercised.

Discriminator run (monkeypatching only the production helper to the two pre-fix
behaviors; no repo file modified; script `/tmp/opencode/d2_discriminate.py`):

```
PRE-FIX SIMULATION: token fallback (len(prefetch_key)) ->
  test_failing_pool_requirement_is_real_slot_demand_not_prefix_tokens
  AssertionError: {'mamba': 64} != {'mamba': 1}
  [token fallback (len(prefetch_key))] failures=1 errors=0
PRE-FIX SIMULATION: forced 0 fallback ->
  test_failing_pool_requirement_is_never_zero
  AssertionError: 0 not greater than 0
  [forced 0 fallback] failures=1 errors=0
token-fallback discriminates (test FAILS): True
zero-fallback discriminates (test FAILS): True
SCRIPT_EXIT=0
```

- Token-vs-slot discriminator: real demand is 1 slot; with `free_mamba=1` the waiter is
  eligible (True), while a token quantity `64` is ineligible (False).
- Forced-0 discriminator: requirement is `> 0`; with `free_mamba=0` the waiter is
  ineligible (False); under `0` it would be treated as "not a real constraint" and
  return True (a false wake).
- `test_evict_seam_captures_larger_real_demand_verbatim`: `evict_host(8, MAMBA)` →
  demand 8 (not 1, not a token count).
- `test_staged_aux_transfer_uses_slot_count`: staged `host_indices=arange(3)` → 3.
- `test_storage_revoke_key_fallback_is_page_to_slot_converted`: 5 keys × page_size 4 →
  20 slots; empty transfer → 1.

### E5. Adjacent host-alloc / mamba / dispatch tests (verbatim)

```
$ pytest test/registered/unit/mem_cache/test_unified_radix_allocation_eviction.py \
         test/registered/unit/mem_cache/test_unified_radix_hicache_dispatch.py \
         test/registered/unit/mem_cache/test_mamba_donated_alloc_ratio.py \
         test/registered/unit/mem_cache/test_mamba_path_state_cap.py -q
35 passed, 5 skipped, 18 warnings, 2 subtests passed in 20.12s
rc=0
```

### E6. Pre-existing failures (baseline-verified, NOT caused by this change)

`test_hicache_restore_prefetch_budget.py` (2) and
`test_mem_pool_host.py::TestLazyHostPoolRelease::test_mamba_pool_lazy_release` (1) fail
identically with my file swapped back to HEAD (sha256
`5b5dc29fa21eefdf44ac660881cab02e9bc6ab1408cd33ca645a4bb326f6bf6f`):

```
at HEAD:  3 failed, 17 warnings
at mine:  3 failed, 17 warnings
```
Mine was restored to `4a5128828dc2cf67a214c794984be6f2d5177178d64cda070e35e467ec03fe1b`
and recompiled (PY_COMPILE_OK) after the comparison.

Likewise the broad `-k "evict_host or host or alloc"` selection in
`test_unified_radix_cache_unittest.py` yields the SAME counts at HEAD and at mine
(`109 failed, 4 passed, 126 skipped, 2049 deselected`), so those are pre-existing
harness/mock failures, not regressions.

### E7. Style / format tooling

`black`, `ruff`, `isort` are NOT installed in
`/opt/sglang/local-prod-v1/env` (verified via `python -m <tool> --version` → UNAVAILABLE).
Kept 88-col style manually: every added/changed line is `<= 88` columns
(`git diff -U0 | grep '^+' | awk 'length($0) > 89'` produced no output for both files).

## Defects / blockers

None blocking. The D2 defect is fixed and verified.

Residual note (not a blocker): the fix relies on the failing component's
`prepare_prefetch` routing its failed alloc through the `evict_host` reclaim seam. This is
true for both aux components today (`mamba_component.py:842-846`,
`swa_component.py:803-807`) and `HostPoolGroup.alloc` always invokes `reclaim` on failure.
If a future component allocates aux host slots WITHOUT a reclaim callback that routes to
`evict_host`, the capture would be stale/absent; the code then falls back to the
real-slot floor of 1 (still a slot count, never 0 or tokens), which is fail-closed.

## Remaining claims / exclusions / open issues

- **Established (FACTS):** the producer now emits host-slot units; the scheduler consumer
  is unchanged and slot-correct; the vacuous test is deleted; 23/23 canonical and 35
  adjacent tests pass; the two new discriminators fail under both pre-fix behaviors.
- **Could NOT establish:** live (GPU/server) end-to-end behavior — CPU only, per scope.
  No live run proves the capture is fresh at site A in production; the claim rests on the
  code-path reading (both aux `prepare_prefetch` implementations always pass a reclaim
  lambda) plus the seam-mirroring test. D1 (mamba host-pin lifetime / L3 ack non-drain)
  from P8B is OUT OF SCOPE and untouched; this fix addresses only D2 (liveness / unit
  mismatch). Even with D2 fixed, `free+evictable=0 < required` still holds during D1
  contention, so the park remains until the real allocator can make room.
- **Not claimed:** that this fixes the production restore tail; that capacity or split
  ratio changes anything; that the scheduler consumer needed changes (it did not).
- **Excluded:** no `scheduler.py` edit; no ledger edit; no other `.memory/**` write; no
  git commit; no server/port-30000 interaction; no `/opt/**` or `/data/**` change.

## Changed-artifact list

| Path | Change |
| --- | --- |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | +160/−17. Reclaim-seam slot-demand capture; `_host_alloc_required_aux_units`; site A + site B slot-unit wiring; per-component depth guard; `reset()` clears capture state. |
| `test/registered/unit/managers/test_hicache_host_allocability.py` | +185/−1. New `_NoopHostPoolGroup` + `HostAllocAuxSlotUnitTests` (5 tests). |
| `tests/unit/test_mamba_unit_fix.py` | DELETED (vacuous). `tests/unit/` and now-empty `tests/` removed. |
| `python/sglang/srt/managers/scheduler.py` | UNCHANGED (sha256 identical before/after). |

## Terminal state: DONE
