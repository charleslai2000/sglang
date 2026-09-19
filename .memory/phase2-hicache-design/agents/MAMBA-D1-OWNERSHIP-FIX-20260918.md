# MAMBA-D1-OWNERSHIP-FIX-20260918

Status: DONE

## Task
Step (2) of the owner's ordered plan (3 -> 1 -> 2). Repair the REAL Mamba L3-backup pin
ownership/lifecycle so that an in-run backend failure cannot leak a submit-time host pin until
shutdown.

Binding owner ruling (do NOT violate): route backend failure through the EXISTING storage-failure
ownership path (`_handle_storage_failure` / `storage_failure_reason`); restore fatal handling in
the hybrid `backup_thread_func`; make `_page_backup` failure ATTRIBUTABLE. A timeout / forced-unpin
watchdog MUST NOT become the normal lifecycle. An orphan-pin invariant guard is acceptable only as
a last-resort safety net, never as the mechanism.

Acceptance: (1) a backend failure that prevents the ack is observable, not silently swallowed;
(2) it is routed through the existing storage-failure path so the affected `ongoing_backup` pin(s)
are released in-run, exactly once, via the SAME ownership mechanism (not a new timer); (3) a
dead/failed backup thread likewise leads to in-run pin release; (4) exactly-once release; no
double-dec; no release of a pin whose write actually succeeded; allocator remains final authority.

## Scope
Write domain (owner explicit override):
- `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py` — MODIFIED
- `python/sglang/srt/mem_cache/unified_radix_cache.py` — NOT modified by me (reconciliation only)
- `python/sglang/srt/managers/scheduler.py` — NOT modified (not required; see Result)
- Tests: `test/registered/unit/managers/test_hybrid_group_wiring.py` — MODIFIED

CPU only. No server/GPU/`/opt/**`/`/data/**`/git history/other `.memory`. No new observation
mechanism (reused the existing `_storage_thread_fatal` / `storage_failure_reason` /
`_handle_storage_failure` machinery). No new timer/watchdog. This artifact only.

Worktree edited: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`, HEAD
`ea7b0e9b445e23852cd900ee0abe9e2a1eab17ee`. Frozen-tree correspondence is noted per line.

## Result

**The pin-lifecycle break is repaired by making a failed L3 backup a terminal, attributable
storage failure that flows through the pre-existing degraded-storage ownership path.**

Minimal, localized change in `hybrid_cache/hybrid_cache_controller.py` (the only production file
I changed; frozen-tree counterpart `hybrid_cache/hybrid_cache_controller.py`, same class
`HybridCacheController`):

1. **Attributable failure helper** `_fail_backup(operation, reason, *, exc_info=False)` (new,
   `:1107-1127`). Records `operation.backup_failure_reason`, logs at ERROR with the operation id
   and node id, and always returns False. Every failure branch of `_page_backup` now returns
   through it instead of a bare `return False`:
   - `:1177` `sidecar_set_failed`
   - `:1215` `kv_set_failed`
   - `:1219` `group_commit_failed`
   - `:1222` `sidecar_set_failed`
   - `:1224-1229` `except Exception as exc -> exception:<Type>: <msg>` with `exc_info=True`
     (frozen `:1198-1199` was a SILENT `except Exception: return False`).

2. **Fatal handling restored in the hybrid `backup_thread_func`** (`:1257`). A False
   `_page_backup` now raises `RuntimeError("backup did not commit: <reason>")` (`:1276-1283`)
   instead of `continue`; the per-op `except Exception` (`:1378-1385`) calls the inherited
   `_storage_thread_fatal("backup_thread_func", exc)` and returns. This is exactly the base
   controller semantics at frozen `managers/cache_controller.py:1458-1460` that the hybrid
   override had dropped (frozen hybrid had only `except Empty` at `:1333-1334`). The thread now
   dies *diagnosed* rather than silently, never retries a degraded backend, and never fabricates
   an ack.

3. **`open_group()` moved inside the `try`** (`:1145-1147`) so a group-open exception is also
   attributed and aborted rather than escaping unattributed.

**Ownership release uses the EXISTING mechanism, not a timer.** The only new signal is the
already-defined `storage_failure_reason`. The unchanged scheduler poll
(`unified_radix_cache.py:8118-8122`, frozen `:7975-7979`) sees it and calls the unchanged
`_handle_storage_failure` (`:8093-8116`, frozen `:7950-7973`), which `dec_host_lock_ref`s every
`ongoing_backup` pin and clears the dict, one-shot guarded by `_storage_failure_handled`. The
same controller `storage_failure_reason` gates further L3 queries/writes
(`unified_radix_cache.py:5054`, `:5394`, `:5472`). `scheduler.py` needs no change.

**Exactly-once.** `_handle_storage_failure` is one-shot (`:8103-8105`). The ack drain pops with
`self.ongoing_backup.pop(operation.id, None)` (`:7278`) and only decs when the entry is non-None,
and `check_hicache_events` runs `_handle_storage_failure` (`:8121`) before the drain (`:8172`),
so an op whose commit succeeded but whose ack is still queued is released once by the failure
path and its later drain is a no-op. No double-dec. A successful `commit_group` returns True
(`:1220`) and never enters the failure path, so no pin is released for a write that committed.

## Evidence

All commands run CPU-only in `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt` with
`/opt/sglang/local-prod-v1/env/bin/python`, `CUDA_VISIBLE_DEVICES=999`,
`PYTHONDONTWRITEBYTECODE=1`.

### E0. On-disk reconciliation BEFORE editing (FACTS)
```
$ git rev-parse HEAD
ea7b0e9b445e23852cd900ee0abe9e2a1eab17ee
$ git status --short -- <write-domain>
 M python/sglang/srt/mem_cache/unified_radix_cache.py
 M test/registered/unit/managers/test_hicache_host_allocability.py
```
`unified_radix_cache.py` sha256 `4a5128828dc2cf67a214c794984be6f2d5177178d64cda070e35e467ec03fe1b`
= the D2 agent's AFTER hash (`MAMBA-D2-UNIT-FIX-R2` E1), `git diff --numstat` 160/17. I did NOT
touch it. `hybrid_cache/hybrid_cache_controller.py` was clean at HEAD
`4462403deb5b4975a5be95072cd344bb98a01dba78f10c40eb9aead08b843729` (this is also the ACK-audit's
frozen-tree hash, so the file I edited was byte-identical to the frozen analysis base).

### E1. Changed-file digests BEFORE -> AFTER

```
BEFORE (sha256):
4462403deb5b4975a5be95072cd344bb98a01dba78f10c40eb9aead08b843729  hybrid_cache/hybrid_cache_controller.py
4a5128828dc2cf67a214c794984be6f2d5177178d64cda070e35e467ec03fe1b  unified_radix_cache.py   (D2, untouched)
a85e8078d476b1f5107186b58babf78d3becedf596cfc1df92343bd29165efdc  managers/scheduler.py     (untouched)
bf3bf46ed6c058d6c8106745edaad409c2967a73dc035c1a3112667e3a5860ff  test_hybrid_group_wiring.py

AFTER (sha256):
d5ec3a761929087b0c3e69abb33a2f167381836e91a51dc00e75392c3fac3ee8  hybrid_cache/hybrid_cache_controller.py
4a5128828dc2cf67a214c794984be6f2d5177178d64cda070e35e467ec03fe1b  unified_radix_cache.py   (IDENTICAL)
a85e8078d476b1f5107186b58babf78d3becedf596cfc1df92343bd29165efdc  managers/scheduler.py     (IDENTICAL)
44e7be03d5cbdb0f98015b78e0144ed91fa6f86b9322257417579a91c382bd6c  test_hybrid_group_wiring.py

AFTER (git hash-object):
12fc0c6db2064162cc24b67fb5abc4e57237faf9  hybrid_cache/hybrid_cache_controller.py
e3774b9c18c2c5725264ef1a92718ec49216d9ca  unified_radix_cache.py
dc6bf2ec4c1c7c545716bd3613cc31af2514a70d  managers/scheduler.py
87554f43cdbac06cdd61bfec7a9001039cbef399  test_hybrid_group_wiring.py
```

`git diff --numstat` (scoped):
```
61	10	python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py
160	17	python/sglang/srt/mem_cache/unified_radix_cache.py      (D2, pre-existing)
163	0	test/registered/unit/managers/test_hybrid_group_wiring.py
```
`scheduler.py` absent from numstat = unmodified.
`git status --short` scoped: ` M hybrid_cache_controller.py`, ` M unified_radix_cache.py` (D2),
` M test_hybrid_group_wiring.py`. No other paths.

### E2. py_compile (changed production + test)
```
$ CUDA_VISIBLE_DEVICES=999 PYTHONDONTWRITEBYTECODE=1 /opt/sglang/local-prod-v1/env/bin/python -m py_compile \
    python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py \
    python/sglang/srt/mem_cache/unified_radix_cache.py \
    test/registered/unit/managers/test_hybrid_group_wiring.py
PY_COMPILE_OK exit=0
```

### E3. Canonical suite (verbatim)
```
$ pytest test/registered/unit/managers/test_hybrid_group_wiring.py -q -p no:cacheprovider
8 passed, 17 warnings in 16.64s
rc=0
```
Baseline before this task was 3 tests (all passed). I added 5; 8/8 pass.

### E4. New tests and their discriminators (FAIL pre-fix, PASS post-fix)
New tests in `HybridGroupWiringTests` drive the REAL `HybridCacheController._page_backup` and
`backup_thread_func` with a group-capable stub backend, and drive the REAL
`UnifiedRadixCache._handle_storage_failure` for the ownership release:
- `test_failed_backup_is_attributable_and_routes_to_storage_failure` — sidecar failure:
  `operation.backup_failure_reason == "sidecar_set_failed"`, `controller.storage_failure_reason`
  set, no ack enqueued, group aborted.
- `test_commit_group_failure_is_attributable` — `commit_ok=False`:
  reason `group_commit_failed`, degraded, no ack.
- `test_backup_thread_exception_is_fatal_not_silent` — backend raises
  `RuntimeError("backend exploded")`: `backup_thread_func` returns (does not propagate),
  `storage_failure_reason` contains `RuntimeError: backend exploded`, no ack.
- `test_storage_failure_releases_unacked_backup_pin_exactly_once` — controller's
  `storage_failure_reason` (produced by the failed thread) drives the unchanged
  `UnifiedRadixCache._handle_storage_failure`; one `dec_host_lock_ref` for the pinned node; a
  second scheduler pass does not double-dec.
- `test_successful_commit_does_not_degrade_or_fabricate_failure` — negative control: happy path
  ack, `storage_failure_reason is None`, no `backup_failure_reason` attribute.

Pre-fix discriminator run (production file swapped to HEAD `4462403d...`; test file unchanged):
```
$ pytest test/registered/unit/managers/test_hybrid_group_wiring.py -q -k \
  "failed_backup_is_attributable or commit_group_failure_is_attributable or \
   backup_thread_exception_is_fatal or storage_failure_releases_unacked"
E       AssertionError: unexpectedly None
E       AttributeError: 'StorageOperation' object has no attribute 'backup_failure_reason'
E       AttributeError: 'StorageOperation' object has no attribute 'backup_failure_reason'
E       AssertionError: unexpectedly None
FAILED ...::test_backup_thread_exception_is_fatal_not_silent
FAILED ...::test_commit_group_failure_is_attributable
FAILED ...::test_failed_backup_is_attributable_and_routes_to_storage_failure
FAILED ...::test_storage_failure_releases_unacked_backup_pin_exactly_once
4 failed, 4 deselected, 17 warnings in 15.17s
rc=1
```
Post-fix: 8 passed (E3). The production file was restored and re-hashed to
`d5ec3a761929087b0c3e69abb33a2f167381836e91a51dc00e75392c3fac3ee8` after the swap.

### E5. Adjacent canonical suites (verbatim)
```
$ pytest test/registered/unit/managers/test_hicache_host_allocability.py -q
23 passed, 17 warnings in 17.80s
rc=0

$ pytest test/registered/unit/mem_cache/test_hicache_staged_write_back_dispatch.py \
         test/registered/unit/mem_cache/test_unified_radix_hicache_dispatch.py \
         test/registered/unit/mem_cache/test_extent_file_backend_unit.py \
         test/registered/unit/mem_cache/test_unified_radix_allocation_eviction.py \
         test/registered/unit/mem_cache/test_minimax_sparse_pool_host_unit.py \
         test/registered/unit/observability/test_hicache_request_telemetry.py \
         test/registered/unit/managers/test_scheduler_hicache_attach.py -q
192 passed, 5 skipped, 17 warnings, 3 subtests passed in 26.51s
rc=0
```

### E6. NEGATIVE self-check — pre-existing failures are NOT regressions
The 2 failures in `test_hicache_restore_prefetch_budget.py` and the 8-failed/3-error broad
managers run are HEAD-identical. Same command with the production file swapped to HEAD
`4462403d...`:
```
$ pytest test/registered/unit/managers/test_hicache_restore_prefetch_budget.py -q   # at HEAD
2 failed, 17 warnings in 17.63s

$ pytest test/registered/unit/managers/ -q                                          # at MINE
8 failed, 600 passed, 15 skipped, 22 warnings, 3 errors, 608 subtests passed
$ pytest test/registered/unit/managers/ -q                                          # at HEAD
12 failed, 596 passed, 15 skipped, 22 warnings, 3 errors, 608 subtests passed
```
(At HEAD the same path has 12 failed because my 4 new tests are present in the tree but fail; the
pre-existing failure set is the same 8+3.) `test_unified_radix_cache_unittest.py -k
"hicache_l3_write_storage or hicache_l3_prefetch"` gives `26 failed, 12 skipped` at BOTH HEAD and
mine (accelerator/mock-harness failures; error text is
`NotImplementedError` / `No accelerator (CUDA, XPU, HPU, NPU, MUSA, MPS)`), so not regressions.
`test_mamba_unittest.py`/`test_decode_retraction_backup.py` likewise `12 failed, 2 passed` at
both HEAD and mine for the same accelerator reason.

### E7. NEGATIVE checks — no watchdog, no fabricated ack, no new thread
```
$ git diff -- hybrid_cache/hybrid_cache_controller.py | grep '^+' | grep -inE "timer|watchdog|threading|sleep|time\.monotonic|interval"
(no timer/watchdog/threading/sleep added)
$ git diff -- hybrid_cache/hybrid_cache_controller.py | grep '^+' | grep -n "ack_backup_queue.put"
(no new ack put)
```
Added lines all <= 88 columns (checked with `git diff -U0 | grep '^+' | awk 'length($0)>89'` →
no output). `black`, `ruff`, `isort` are NOT installed in the prod venv
(`python -m <tool> --version` → "No module named ..."), so style was kept manually.

## Defects / blockers

None blocking. The D1 ownership/lifecycle defect is repaired and verified.

Design note (not a blocker): this repair triggers the degraded-storage path on the FIRST failed
backup commit and stops the backup thread for the run. That is the owner-mandated behavior
(route through the existing storage-failure ownership path) and matches the base controller's
fail-fast semantics. It is intentionally a terminal degradation, not a retry. It does not
fabricate durability: the degraded `storage_failure_reason` disables further L3 queries/writes
(`unified_radix_cache.py:5054`, `:5394`, `:5472`) and requests fall back to recompute.

## Remaining claims / exclusions

- **Established (FACTS):** every `_page_backup` failure branch is now attributable (reason stored
  + ERROR log); a False/exception path stops the thread via `_storage_thread_fatal` and sets
  `storage_failure_reason`; the unchanged `_handle_storage_failure` then releases every unacked
  `ongoing_backup` pin exactly once; a committed write returns True and never enters this path;
  the 4 new discriminator tests fail at HEAD and pass with the fix; 23/23 host-allocability and
  192 adjacent tests pass; `unified_radix_cache.py` and `scheduler.py` are byte-identical to
  their pre-task state (D2 preserved).
- **Could NOT establish (matching the ACK audit's R1):** WHICH backend reason (H1 swallowed
  exception > H2 silent thread death > H3 backend refusal) actually occurred in the failing prod
  run. This fix is reason-agnostic by design: it converts ALL three into one attributable,
  in-run-released terminal failure. No live/GPU run was performed (CPU-only scope), so the
  production end-to-end path is not re-verified live.
- **Not claimed:** that this alone restores the prod restore tail (the D2 liveness/unit fix is a
  separate, already-done step); that the extent backend is defect-free; that capacity or split
  ratio changes anything.
- **Excludes:** no timeout/forced-unpin watchdog; no orphan-pin invariant guard (not needed
  because the real ownership path now fires); no `scheduler.py` edit; no `unified_radix_cache.py`
  edit; no ledger edit; no git commit; no server/port-30000/`/opt/**`/`/data/**` interaction.
- **Line-number basis:** all `file:line` references are to the WORKTREE file as edited
  (`d5ec3a76...`). The frozen-tree counterparts are named inline where relevant; the pre-edit
  hybrid file was byte-identical to the frozen tree (`4462403d...`), so D1's frozen `file:line`
  reasoning carries over exactly for that file.

## Changed-artifact list

| Path | Change |
| --- | --- |
| `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py` | +61/−10. New `_fail_backup`; all `_page_backup` failure branches attributable; `open_group` moved into `try`; `backup_thread_func` routes False/exception to `_storage_thread_fatal` and stops; no fabricated ack. sha256 `d5ec3a761929087b0c3e69abb33a2f167381836e91a51dc00e75392c3fac3ee8`. |
| `test/registered/unit/managers/test_hybrid_group_wiring.py` | +163/−0. `_OneShotOperationQueue`, `_RecordingAckQueue`, 5 focused tests (4 fail pre-fix, 1 negative control). sha256 `44e7be03d5cbdb0f98015b78e0144ed91fa6f86b9322257417579a91c382bd6c`. |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | UNCHANGED by me; D2 change preserved (sha256 `4a51288...`). |
| `python/sglang/srt/managers/scheduler.py` | UNCHANGED (sha256 identical). |

## Terminal state: DONE

D1 ownership/lifecycle repaired in `hybrid_cache/hybrid_cache_controller.py`; backend failure is
now attributable and routed through the existing `storage_failure_reason` ->
`_handle_storage_failure` in-run release (exactly-once), the hybrid backup thread restores the
base fatal handler, and no watchdog/timer was introduced. 8/8 canonical + 23/23 host-allocability
+ 192 adjacent tests pass; the new tests fail 4/4 at HEAD and pass with the fix; pre-existing
failures confirmed HEAD-identical. The concrete prod-run backend reason (H1/H2/H3) remains
unestablished (no live run; out of CPU-only scope) and is orthogonal to this reason-agnostic fix.
