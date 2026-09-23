ENTRY: ACCEPT

status: blocked
task_id: T3060-RH-MATCH-PREP-REVIEW-20260909
orchestration_epoch: 20260909-rh-ab48
role: reviewer
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
base_revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
worktree_diff_sha256: 5a0d210512b1eddb9dde8206b6e340879568b42c3d579ee5f672f5f6b51109c2
verdict: BLOCK
code_gate: BLOCK
runtime_rh_value: UNPROVEN_PENDING_HASH_PINNED_LIVE_REPLAY

## Artifacts

- Independent gate artifact: this file.
- Authoritative design: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/ARCH3060-RH-MATCH-GATE-DESIGN-20260909.md`.
- Revised Pattern Intake: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/storage/review/gates/pattern-intake/PATTERN-INTAKE-20260909-RH-MATCH-PREP.md`.
- Revised Novel Mechanism: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/review/gates/NOVEL-MECHANISM-20260909-RH-MATCH-PREP.md`.
- Coder report: `CODER3060-RH-MATCH-PREP-IMPLEMENT-20260909.md` in the sibling task memory.
- Debugger evidence: `DBG-20260909-RH-TELEMETRY-CAUSE.md` and `DBG-20260909-RH-NO-STAGING.md` in the sibling task memory.
- Prior accepted RH review: `REVIEW3060-RH-FINAL-JOIN-20260909.md` in the sibling task memory; accepted ancestor revision `6edf69ce29fe2598fba51c94a99315239cf1a8c8`.
- Reviewed uncommitted product/test files: `scheduler.py`, `unified_radix_cache.py`, `test_ready_horizon_unit.py`, `test_rh_contract_dependency_free.py`, and `test_prefetch_gate_skip_regression.py`.

## Evidence

- `git rev-parse HEAD` = `f629d4e2c19eb74571b4154438fd651ce24ff53b`; the worktree has five modified tracked files and no committed descendant for this implementation.
- `git diff --check` passed; changed-source scope is 339 additions/10 deletions in `scheduler.py`, 4 additions/2 deletions in `unified_radix_cache.py`, and focused test updates.
- Independently ran `python3 test/registered/unit/mem_cache/test_rh_contract_dependency_free.py`: 10 tests passed.
- Independently ran `python3 test/registered/unit/mem_cache/test_prefetch_gate_skip_regression.py`: 2 tests passed.
- Independently ran `python3 -m py_compile` for all five changed Python files: passed.
- `PYTHONPATH=python python3 test/registered/unit/mem_cache/test_ready_horizon_unit.py` could not collect because `orjson` is unavailable. No package-backed RH test evidence was substituted for this missing dependency.
- Source inspection confirms `_get_new_batch_prefill_raw` calls `_reconcile_restore_states`, then `_ready_horizon_pass`, then the admission path; admission still calls `req.init_next_round_input(self.tree_cache)` at `scheduler.py:6040`.
- Source inspection confirms RH-OFF retains `_prefetch_kvcache(... origin=EAGER_RH_OFF)` before `waiting_queue.append(req)` at `scheduler.py:5323-5327`; RH-ON does not eagerly issue.
- Source inspection confirms RH preparation calls `req.init_next_round_input(self.tree_cache, cow_mamba=False)` at `scheduler.py:4342`, and the valid-ticket path does not repeat that call before the storage gate. The lower gate is still rerun at `scheduler.py:3300`.
- Source inspection confirms no changed symbol invokes an allocator, eviction API, HOST_ALLOC generation/FIFO, or Mamba COW; the admission-time match remains separate.
- The L3 alignment itself is source-consistent: `UnifiedRadixCache.has_restore_potential` now includes `tree_core.is_l3_durable(anchor_node_id)` at `unified_radix_cache.py:6096-6100`, matching the existing `prefetch_gate_ok` clause at `unified_radix_cache.py:4951-4955`.

## Findings

### BLOCKER-1 — Match-gate authority is not accepted or revision-pinned

Locations: revised Pattern Intake YAML lines 19-20; revised Novel Mechanism YAML lines 18-20; `ARCH3060-RH-MATCH-GATE-INTAKE-20260909.md:58-60,84-90`.

Both revised gate inputs state `gate_verdict: PENDING`, `implementation_revision: null`, and `implementation_status: NOT_YET_ACCEPTED`. The companion intake explicitly requires gate-owner acceptance and architecture repinning before implementation dispatch/review. The prior accepted RH review only accepts the earlier exclusive-issuer boundary at its ancestor revision; it does not accept this new mutating-match freshness/consumption boundary.

Acceptance impact: this reviewer cannot issue a valid implementation PASS against a proposed, self-non-authorizing design input. The orchestrator must obtain the fresh gate-owner decision and repin the design chain to the reviewed implementation revision. The current uncommitted worktree also cannot serve as an immutable implementation revision.

### BLOCKER-2 — Cache-layer change exceeds the authorized implementation scope

Location: `python/sglang/srt/mem_cache/unified_radix_cache.py:6061-6100`, specifically the added L3-durable branch at lines 6096-6100; authoritative scope `PATTERN-INTAKE-20260909-RH-MATCH-PREP.md:282-299` and design `ARCH3060-RH-MATCH-GATE-DESIGN-20260909.md:467-495`.

The accepted implementation contract limits this mechanism to `scheduler.py` plus focused tests. It explicitly says changes to cache traversal/components exceed the intake and require fresh architecture and dispatch authority. The implementation changes `UnifiedRadixCache.has_restore_potential`, which is a cache-layer policy predicate. The change is semantically aligned with `prefetch_gate_ok` and is supported by a focused test, but that does not waive the declared ownership boundary.

Acceptance impact: this is a scope/authority blocker, not a claim that the L3 condition is incorrect. Either the cache change must be separately authorized and gated under a fresh Task ID, or the implementation must be reduced to the authorized scheduler-local shape.

### BLOCKER-3 — Required one-shot consumption and no-COW oracles are not independently exercised

Locations: `test/registered/unit/mem_cache/test_rh_contract_dependency_free.py:154-179`; `test/registered/unit/mem_cache/test_ready_horizon_unit.py:907-924,359-360`.

The passing tests prove that the preparation helper calls `init_next_round_input(..., cow_mamba=False)` once and that ticket fields can invalidate. They do not execute the real valid-ticket path through `_prefetch_kvcache_impl`: the ready-horizon unit fixture replaces `_prefetch_kvcache` with an issue stub, and the dependency-free pass test replaces `_prepare_ready_horizon_match` with a lambda returning `None`. Consequently there is no executable proof here that a valid ticket suppresses the issue-time match, that an invalid ticket performs exactly one fallback rematch before issue/hold, or that preparation leaves Mamba pool/COW fields and allocator/eviction counters unchanged.

Acceptance impact: the design/intake required deterministic cases for one-shot consumption, fallback rematch, non-COW Mamba safety, retraction/chunk lifecycle, and fail-closed preparation. The present evidence is insufficient to accept those invariants independently, even though the source call path appears directionally correct.

### MAJOR-4 — Required preparation telemetry fields and fallback oracle are incomplete

Location: `scheduler.py:4245-4315` (`_emit_rh_match_prepare`).

The design telemetry contract requires `match_duration_us`, `mamba_pool_idx_changed`, `mamba_cow_src_changed`, `mamba_needs_clear_changed`, and the `buffer_device_fallback` anchor classification. The implementation emits neither the duration nor the three Mamba deltas, and classifies only `unknown`, `root`, and `node`. The tests do not assert these fields or logging/control independence.

Acceptance impact: the required post-implementation evidence cannot independently demonstrate the no-COW/allocator boundary or distinguish the documented buffer fallback. This blocks the telemetry portion of the implementation gate until the schema is either implemented or the design is explicitly amended by its gate owner.

## Requirement matrix

| Requirement | Independent result |
| --- | --- |
| Exact changed symbols | Identified; five tracked files changed, with the cache-layer scope exception in BLOCKER-2. |
| L3-durable eligibility alignment | Source and focused test support alignment with `prefetch_gate_ok`; acceptance remains blocked by scope/gate authority. |
| One-shot freshness/consumption | Source is directionally correct; integration/fallback evidence is incomplete (BLOCKER-3). |
| Fail-closed behavior | Preparation failure returns no ticket and invalid tickets rematch/fail closed in source; no end-to-end test proves the issue path. |
| RH-OFF compatibility | PASS structurally: eager issue remains before queue append and no RH pass is constructed when disabled. |
| No Mamba COW/allocator/eviction authority | PASS by changed-source call graph; required negative runtime/unit oracle is absent (BLOCKER-3/MAJOR-4). |
| Test evidence | Dependency-free 10+2 tests and compile pass; package-backed suite unavailable; required integration cases are missing. |
| Scope | BLOCK: `unified_radix_cache.py` exceeds the declared scheduler-plus-tests scope. |
| Runtime RH value | UNPROVEN; no live RH-ON/RH-OFF replay was run or claimed. |

## Summary

The source change has the intended causal placement, current-match ticket shape,
L3-durable predicate alignment, RH-OFF ordering, and lower-layer ownership
preservation. The independent code gate is nevertheless BLOCKED: the new
Pattern/NM/design chain is still pending and unpinned, the implementation
changes an explicitly unauthorized cache-layer file, and the available tests do
not exercise valid-ticket consumption, fallback rematch, or no-COW allocator
boundaries. The prior accepted RH review remains valid for its ancestor
exclusive-issuer implementation but does not cover this new gate.

Runtime RH value is intentionally separate and remains unproven until a fresh,
hash-pinned live RH-OFF/RH-ON replay supplies the required joins and safety
measurements. No remote load or deployment was performed in this review.

## Followups

- Fresh gate-owner/orchestrator task: accept or amend the revised Pattern Intake and Novel Mechanism, repin the architecture chain, and authorize the exact implementation scope.
- Fresh implementation task if the cache-layer change is retained: obtain architecture authority for that boundary and update the scope/change manifest.
- Fresh tester task: add/run the real valid-ticket, one-fallback, retraction/chunk, no-COW field/counter, fail-closed, and RH-OFF integration cases with dependencies available.
- Fresh reviewer task after those gates and tests: review an immutable descendant revision and update this verdict.
- Fresh runtime task, only after code-gate acceptance: perform the hash-pinned paired RH-OFF/RH-ON replay; report missing joins as not-computable and do not infer RH value from HTTP completion alone.

## Open issues

- No accepted match-gate revision exists; revised Pattern Intake/NM remain pending.
- Current implementation is uncommitted; the recorded diff hash identifies this worktree but is not a mergeable immutable revision.
- Package-backed RH unit/scheduler-feed tests are unavailable because `orjson` is missing; formatter/type-checker tools are also unavailable per the coder report.
- No live post-fix RH evidence exists, so ready-before-admission rate, issue/storage joins, Mamba safety deltas, HOST_ALLOC behavior, and performance remain uncomputable/unproven.
- Extra implementation, gate mutation, test, deployment, or runtime work requires a fresh Task ID.
