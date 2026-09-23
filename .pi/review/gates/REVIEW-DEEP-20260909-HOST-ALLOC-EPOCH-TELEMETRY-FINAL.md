ENTRY: ACCEPT

# Deep final review: host allocation epoch telemetry

- Task ID: `REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH-TELEMETRY-FINAL`
- Orchestration epoch: `20260909-P4`
- Role: `reviewer-deep`
- Reviewed revision: `82ab235606233160701b15f657a71794cfd29a30`
- Branch: `3060-12g-qwen35-4b`
- Review scope: read-only review of the target repository; this report is the only authorized write.

## Verdict

**ACCEPT for the commit-level source and dependency-free final gate.** No blocking defect from the prior deep-final rejection remains in commit `82ab235606`.

This is not a claim of live 3060 runtime acceptance. The live prerequisites below remain open, and the pending architecture/pattern/novel-mechanism governance decisions remain an orchestrator/design-authority responsibility.

Invocation status: `done`.

## Reviewed artifacts

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `test/registered/unit/mem_cache/test_storage_regression.py`
- Prior rejection: `review/gates/REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH-FINAL.md`
- Implementation handoff: `../sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODE-20260909-HOST-ALLOC-EPOCH-TELEMETRY-FINAL.md`
- Architecture, pattern-intake, and novel-mechanism artifacts under `review/gates/` and `storage/review/gates/pattern-intake/`

The commit changes only the two tracked files above. `git diff --check 82ab235606^ 82ab235606` passed. No code, remote, storage, or sibling 3090 repository was modified by this review.

## Evidence

### Reproducible checks

- `PYTHONDONTWRITEBYTECODE=1 python3 test/registered/unit/mem_cache/test_drain_reentry.py`: **31/31 passed**.
- `PYTHONDONTWRITEBYTECODE=1 python3 test/registered/unit/mem_cache/test_hicache_restore.py`: **92/92 passed**.
- `PYTHONDONTWRITEBYTECODE=1 python3 test/registered/unit/mem_cache/test_storage_regression.py RestoreDurabilityMarkingTests HostAllocMutationTelemetryTests`: **5/5 passed**.
- Dependency-free total: **123/123 passed**; focused final-fix set: **5/5 passed**.
- Direct `compile()` checks for both changed Python files passed.
- A source-loaded duck-typed transfer probe with a transfer missing optional fields completed without `AttributeError` and reached terminal `finalized`.
- A source-loaded `HostAllocWakeArbiter` probe confirmed the same post-cleanup generation does not self-wake, while a newer generation does wake.

Registered tests were attempted but are **blocked, not passed**: `pytest` is unavailable; direct unittest collection is blocked by missing `orjson` for host-allocability tests and missing `torch` for mem-pool-host tests. The scheduler-feed fixture is also blocked by missing `orjson`. No result from those tests is counted as acceptance evidence.

### Exact fixes from the prior rejection

1. **Optional duck-typed transfer accessors — fixed.** The crop validator, hybrid all-or-nothing validator, sidecar counter, and hybrid result checker use optional-safe access (`getattr`/safe mapping access) for `hit_policy`, `indices_from_pool`, `keys`, `name`, and related fields. The focused duck-typed-gap case completes normally; the full accepted-restore case still records `result=accepted`, `restore_state_after=READY`.

2. **Cache mutation telemetry bound — fixed.** Sampling occurs after complete mutation accounting. `generation` and mutation sequence advance on every mutation, while emission is bounded by the per-key head/stride limit, per-key cap, cache-instance key/total caps, and coalescing. The 5,000-mutation regression produced complete generation/sequence counts, first sequence `1`, coalescing evidence, and no more than 64 emitted records for the repeated key. The wake arbiter consumes allocation generations/snapshots, not telemetry-emission state; the 31+92 scheduler/restore tests remain green.

3. **Discarded hybrid finalize telemetry — fixed.** The discard path records `result=discarded` and `restore_state_after=READY` after terminal `finalized` cleanup. This agrees with the scheduler mapping `finalized -> FINALIZED -> READY`. The accepted path remains `result=accepted`, `restore_state_after=READY`; both behaviors are covered by the focused 5/5 set. The separate `RECOMPUTE` restore-disposition event denotes the operational disposition, not a contradictory state-machine terminal state.

## Earlier invariant reconciliation

- **No KV-only crop:** host allocation retry does not mutate the operation into a KV-only partial restore; it either obtains the validated full allocation or follows the existing failure path. Source tracing and the 92 restore tests support this.
- **Per-pool generation and auxiliary rollback:** auxiliary transfers are released before the host-allocation snapshot; KV and each auxiliary pool receive their own post-free generation bump. The callback and no-callback paths preserve this ordering.
- **Post-cleanup no-self-wake:** failed allocation records the post-cleanup snapshot before waiter selection. The arbiter rejects the same generation vector and admits a newer one; direct probe and the dependency-free scheduler suite pass.
- **Callback-absent free:** host transfer freeing occurs before the optional callback is invoked. A missing observer cannot suppress the actual free; rollback source tracing confirms this ordering.
- **Immediate FIFO cleanup:** leaving `HOST_ALLOC`, aborting, or selecting a stale waiter removes it from the waiter map/deque immediately. The drain/re-entry and restore suites pass.
- **One-generation grant:** the arbiter records the granted generation vector and does not regrant the same vector; the direct arbiter probe confirms the newer-generation-only behavior.
- **All-or-nothing hybrid:** a non-KV-derived sidecar shortfall invalidates/reclaims the hybrid attempt and reaches terminal finalize without partial acceptance. Focused discard evidence passes.
- **Real miss semantics:** allocation denial and genuine storage miss remain distinct (`DENIED_ALLOC` versus genuine-miss classification), including the flag-off paths; covered by the 92-test suite.
- **RH OFF / 3090 scope:** RH-off behavior remains covered by passing dependency-free tests. This review makes no live 3090 or fleet-wide claim; the current commit is reviewed only for the stated 3060 branch and changed files.

## Findings

### Confirmed defects

None in the reviewed revision.

### Plausible, non-blocking risk

**P2 — bounded telemetry can intentionally omit later unique causal keys.** The cache-instance total emission cap is 256, so after enough distinct `(pool, cause, request, trace)` keys, later mutation records are suppressed even though generation and mutation sequence remain complete. This is consistent with the requested bounded-sampling fix and does not affect allocation, wake, or restore correctness. Disposition: accept as an explicit observability tradeoff; if the architecture contract instead requires every request-specific join to be emitted, revise the sampling contract and tests under a fresh Task ID.

### Unsupported concerns not treated as findings

No evidence supports treating the missing optional fields as invalid input, the registered dependency failures as test passes, or the pending live hardware run as a source-code defect.

## Live 3060 prerequisites

Before claiming runtime/liveness acceptance on 3060, run the pinned live environment at this exact revision and capture immutable evidence for:

- unlock-to-evictable transition and positive KV-plus-auxiliary retry to `READY`;
- direct and queued KV free, queued auxiliary release, insufficient-generation single retry, no self-spin, and FIFO fairness;
- all-or-nothing hybrid success/discard, KV-only behavior, genuine miss, cancellation/timeout, and RH OFF;
- `host_alloc.v1` accepted/discarded joins, mutation sequence/generation continuity, and bounded emission under repeated cache mutation.

The ARCH gate and pattern-intake/novel-mechanism artifacts are still marked pending at their respective authority boundaries. The orchestrator must resolve those governance gates before terminal program acceptance; this review does not substitute for them.

## Followups and open issues

- Followup: execute the live 3060 prerequisite matrix and attach the runtime evidence to the owning gate.
- Followup: resolve the pending ARCH/intake/novel-mechanism authority decisions.
- Open issue: the P2 sampling-cap tradeoff should remain documented in the telemetry contract and be revisited only with a fresh Task ID.
- No reviewer-owned blocking followup remains.

Summary: `done`; verdict: `ACCEPT`; blocking findings: `0`.
