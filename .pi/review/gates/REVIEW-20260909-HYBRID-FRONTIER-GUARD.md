ENTRY: ACCEPT

# Hybrid prefetch frontier guard independent gate review

- Task ID: `REVIEW-20260909-HYBRID-FRONTIER-GUARD`
- Orchestration epoch: `20260909-P4`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Reviewed artifact: commit `5b61e63993b65ee1fe6380f6bfab455e40b34270`
- Parent: `7caa438f623b5acd3f5c05183d0b083d27b337f5`
- Branch: `3060-12g-qwen35-4b`
- Gate verdict: **ACCEPT**

## Scope and inputs

Read-only review of the requested commit in
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`, plus local static and
focused-test attempts. The only file written by this review is this gate report.
The pre-existing untracked `review/gates/P0-*` and `storage/` paths were not
modified.

Reviewed inputs:

- authoritative hand-off `HANDOFF-2026-09-07.md`;
- `DEBUG-20260909-MAMBA-FILE-MISMATCH.md`;
- `OPS-20260909-MAMBA-INVENTORY.md`;
- `CODE-20260909-HYBRID-FRONTIER-GUARD.md`;
- `CODE-20260909-PREFETCH-WAKE.md`;
- commit diff and focused hybrid test;
- active source path, transfer policy, all-or-nothing finalization, and
  scheduler wake path.

## Findings

No blocking findings. No security or trust-boundary change was introduced.

### Frontier guard is fail-closed for arbitrary trailing-sidecar crops

`python/sglang/srt/mem_cache/unified_radix_cache.py:147-154` returns false for
any allocation shorter than `operation.storage_hit_count` when any transfer has
`PoolHitPolicy.TRAILING_PAGES`. The cache-mode crop gate at lines 5877-5881
checks this predicate before the existing mutations at lines 5888-5890. If the
predicate rejects the crop, no shortened `hash_value` or `storage_hit_count` is
published and the existing no-host-allocation path revokes the pending
prefetch at lines 5882-5886. Therefore `_sync_trailing_keys` and sidecar IO
cannot be reached with the arbitrary host-cropped frontier described by the
debug report.

The active Qwen3.5/Mamba route is covered: registry construction adds the
MAMBA component and creates `UnifiedRadixCache` (`registry.py:161-192`), and
the Mamba prefetch transfer is explicitly `TRAILING_PAGES`
(`unified_cache/components/mamba_component.py:916-924`). The older HiRadix
hybrid attachments inspected here are DSA/MiniMax indexer paths using
`ALL_PAGES`, not the Mamba route.

### KV-only and full sidecar-complete paths remain compatible

The guard returns true when `alloc_len >= operation.storage_hit_count`, so an
allocation at the validated full frontier retains the prior path. With no
trailing transfer, KV-only crops retain the prior shorter-prefix behavior.
The focused regression asserts both cases and asserts that the rejected hybrid
case does not mutate the operation's hash list.

### All-or-nothing hybrid discard is preserved

The commit does not alter `_check_hybrid_prefetch_result` or its cleanup. The
existing all-or-nothing check and release/invalidation behavior remains at
`unified_radix_cache.py:5345-5387`; the reviewed change only prevents an
uncertified frontier from entering that IO/finalization path.

### Scheduler prefetch wake is not regressed

The scheduler wake change is in the reviewed parent commit `7caa438f`, not in
commit `5b61e639`. The target has no diff in
`python/sglang/srt/managers/scheduler.py` or
`test/registered/unit/managers/test_hicache_restore_prefetch_budget.py`.
The current predicate still rejects a physically full prefetch budget before
allowing a `PREFETCH_BUDGET` wake (`scheduler.py:3746-3755`), while
`DEVICE_QUOTA` continues through its device-capacity checks. The focused
scheduler test's intended assertions therefore remain applicable.

## Evidence

- `git diff-tree --name-status` for the reviewed commit: exactly two changed
  tracked files, the implementation and focused hybrid test.
- `git diff --check 5b61e63993b65ee1fe6380f6bfab455e40b34270^ 5b61e63993b65ee1fe6380f6bfab455e40b34270`:
  **PASS**.
- Isolated bytecode compilation with `PYTHONPYCACHEPREFIX` redirected outside
  the repository for the implementation, hybrid test, scheduler, and scheduler
  test: **PASS**.
- Focused hybrid test attempt with `PYTHONPATH=python`: blocked before test
  collection by `ModuleNotFoundError: No module named 'orjson'`.
- Focused scheduler wake test attempt with `PYTHONPATH=python`: blocked before
  test collection by the same missing `orjson` dependency.
- Local availability probe: `pytest=False`, `orjson=False`, `torch=False`.
- `git status --short --branch` after review shows only the pre-existing
  untracked paths; no reviewed tracked file was modified.

## Evidence limitations and open issues

1. The focused hybrid and scheduler tests could not execute in this environment
   because the SGLang runtime dependencies (`orjson`, `torch`) and `pytest`
   are unavailable. No runtime or live 3060 acceptance is claimed.
2. The new hybrid test directly exercises the guard predicate rather than the
   full allocator/drain/revoke lifecycle. Static call-path inspection confirms
   the predicate is placed before the frontier mutation and queue submission.
3. The safe fallback intentionally declines/revokes an arbitrary trailing-sidecar
   crop; this may reduce availability under host pressure, but it cannot issue
   the invalid sidecar frontier and is consistent with the supplied safe-fix
   contract.

These are evidence limitations, not blocking implementation findings for this
source-level gate.

## Summary and followups

The reviewed revision fixes the confirmed query-frontier versus host-crop
mismatch by refusing shorter allocations whenever a trailing sidecar would be
re-keyed. It preserves full-fit hybrid and KV-only behavior, leaves the
all-or-nothing discard contract intact, and does not alter the scheduler wake
implementation from the parent revision.

Followups require a fresh Task ID:

- run the two focused tests in the project dependency environment;
- perform the separately authorized live 3060 hybrid reproduction before making
  a runtime-reliability claim.

Status: `done`
