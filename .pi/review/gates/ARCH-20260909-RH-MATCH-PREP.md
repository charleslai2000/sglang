# Architecture gate — Ready Horizon current-match preparation R2

```yaml
schema_version: project-architecture-gate-1
artifact_id: ARCH-RH-MATCH-PREP-20260909-02
task_id: T3060-RH-MATCH-GATE-ACCEPT-20260909
orchestration_epoch: 20260909-rh-ab49
repin_task_id: T3060-RH-MATCH-GATE-REPIN-20260909
repin_orchestration_epoch: 20260909-rh-ab53
role: architect
branch: 3060-12g-qwen35-4b
design_baseline_revision: f629d4e2c19eb74571b4154438fd651ce24ff53b
accepted_scope_revision: 20260909-rh-ab49
pattern_intake: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/storage/review/gates/pattern-intake/PATTERN-INTAKE-20260909-RH-MATCH-PREP.md
novel_mechanism: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/NOVEL-MECHANISM-20260909-RH-MATCH-PREP-R2.md
architect_verdict: ACCEPT
orchestrator_acceptance: ACCEPTED
orchestrator_acceptance_source: T3060-RH-MATCH-GATE-REPIN-20260909
implementation_revision: 9213ee01d90ba3925e7fe928e80cc41354ee4fff
implementation_parent_revision: c4ad01ef5d7578bb542fe3e514a71cdbccb6c07a
implementation_status: PINNED_PENDING_INDEPENDENT_IMPLEMENTATION_REVIEW_TESTER_AND_RUNTIME_ACCEPTANCE
runtime_value: UNPROVEN
```

## Verdict

**ARCHITECT ACCEPT** for the bounded design chain. The
`UnifiedRadixCache.has_restore_potential` L3-durable clause is explicitly
authorized as part of the same narrow current-match eligibility-alignment
boundary; it is not removed or split into another task.

Reason: RH policy calls `has_restore_potential` after current-match preparation,
while issue reruns `prefetch_gate_ok`. The latter already recognizes extant
backuped, root, or L3-durable anchors. Omitting L3 from the former creates a
policy-before-issue false negative. Adding that one disjunct aligns predicates
without changing the owner of durability truth or introducing an effectful
cache operation.

The orchestrator accepted this architecture recommendation through repin task
`T3060-RH-MATCH-GATE-REPIN-20260909`, and the chain is now pinned to immutable
implementation commit `9213ee01d90ba3925e7fe928e80cc41354ee4fff` (parent
`c4ad01ef5d7578bb542fe3e514a71cdbccb6c07a`). This records design-chain
authority and traceability only. It does not accept implementation conformance,
tester evidence, independent reviewer PASS, deployment, or runtime value.

## Authorized implementation boundary

Authorized product symbols:

1. `python/sglang/srt/managers/scheduler.py`: a frozen pass-local prepared-match
   value; causal preparation; candidate filtering; identity/anchor validation;
   one-shot routing/consumption; exactly-one fallback rematch; fail-closed
   handling; and `rh_match_prepare.v1` emission.
2. `python/sglang/srt/mem_cache/unified_radix_cache.py`:
   `UnifiedRadixCache.has_restore_potential` only, adding
   `tree_core.is_l3_durable(anchor_node_id)` to the existing extant-anchor
   backuped/root disjunction. No signature or caller contract change.
3. Focused tests under `3090-dev/` and existing registered scheduler/cache test
   locations.

Forbidden without a fresh Task ID: any other cache symbol; traversal/component,
allocator, eviction, finalizer, persistence, durability publication,
HOST_ALLOC, admission, wire/storage format, deployment, or runtime change.
Test-only edits may not replace the real integration path with stubs for the
mandatory oracles below.

## Required interfaces and invariants

- Preparation occurs only after `epoch_event`/`should_refill`, before
  `ReadyHorizonView.staging_eligible`, and calls the existing request
  initialization with `cow_mamba=False` exactly once.
- The immutable value fences request object/RID, pass/enqueue/session/retraction,
  fill identity and length, output length, key/salt, and device/host anchors.
- Consumption is RH-origin-only, same-pass, immediate, and after the active
  attempt claim. It reruns anchor existence and `prefetch_gate_ok`.
- A valid value suppresses issue-time rematch. An invalid/missing value performs
  exactly one non-COW fallback and then issues or fails closed.
- Admission always performs its separate normal match/COW.
- Preparation creates no allocation, eviction, reservation, storage query,
  restore transition, HOST_ALLOC wake, or READY marker. Normal match-owned
  LRU/split/action effects remain cache-owned.
- RH-OFF call order and behavior remain unchanged.
- `has_restore_potential` and `prefetch_gate_ok` must agree on extant
  backuped/root/L3-durable potential; missing/non-durable anchors are rejected.

## Exact telemetry schema

`rh_match_prepare.v1` is one structured event per candidate disposition and per
fallback attempt. Gate evidence must run with sampling disabled (100% capture).
All fields are mandatory; nullable fields are emitted explicitly as `null`.

| Field | Type / allowed values |
| --- | --- |
| `ts_ns` | monotonic integer >= 0 |
| `evt` / `schema` | `rh_match_prepare` / `rh_match_prepare.v1` |
| `rid` | non-empty string |
| `enqueue_seq` | integer or null |
| `pass_seq` | integer >= 1 |
| `decision_id` | string or null; same value as downstream RH decision when one exists |
| `attempt_id` | string or null; populated for issue-path invalidation/fallback |
| `session_generation` | integer or null |
| `retraction_count` | integer >= 0 |
| `restore_state_before` | stable state name or `NONE` |
| `result` | `prepared`, `skipped`, `ineligible`, `failed`, or `invalidated` |
| `reason` | stable reason token; no free-form text |
| `fill_len`, `device_hit_tokens`, `host_hit_tokens` | integer >= 0 |
| `anchor_kind` | `unknown`, `root`, `node`, or `buffer_device_fallback` |
| `anchor_id` | stable printable node identity or null |
| `anchor_exists`, `anchor_gate_ok` | boolean |
| `cow_mamba` | literal `false` |
| `match_duration_us` | integer >= 0 for a match attempt; null for zero-match skipped/ineligible |
| `match_count_for_pass` | integer 0, 1, or 2; 2 only after `invalidated` fallback |
| `fallback_rematch` | boolean |
| `mamba_pool_idx_changed`, `mamba_cow_src_changed`, `mamba_needs_clear_changed` | boolean; all false for every preparation/fallback |
| `mamba_alloc_calls_delta`, `mamba_evict_calls_delta` | integer; both zero for every preparation/fallback |

For each potentially stageable candidate, `(rid, enqueue_seq, pass_seq)` must
join preparation to `rh_preadmission.v1`. `decision_id` then joins decision to
`rh_stage.v2`; `attempt_id` joins issue/finalize/readiness/admission. A candidate
rejected before matching emits `skipped` or `ineligible` with
`match_count_for_pass=0`; telemetry failure or sampling cannot affect control.

`anchor_kind=buffer_device_fallback` means buffer-only mode selected the current
device anchor because no usable host anchor was returned. `node` excludes root.
`anchor_gate_ok` reports the real issue gate result and never substitutes for
rerunning that gate at consumption.

## Minimum reviewer-PASS test oracles

The next tester/reviewer may require more, but may not PASS without all of:

1. **Real valid-ticket integration:** execute `_ready_horizon_pass` through
   `_prefetch_kvcache` and `_prefetch_kvcache_impl` without stubbing preparation
   or issue. Assert one real `match_prefix`, one claim, one storage query, one
   attempt, valid join telemetry, and no issue-time rematch.
2. **Real invalidation/fallback integration:** invalidate token/session/
   retraction/key/salt/anchor or delete a later anchor between preparation and
   consumption. Assert exactly two total matches, one `invalidated` event, one
   fallback event, no stale-anchor query, and at most one claim/query/attempt.
3. **Fail-closed integration:** force preparation and fallback failure. Assert
   zero storage query, reservation, allocator/evict call, restore transition,
   HOST_ALLOC wake, and READY marker.
4. **No-COW oracle using real request/cache components:** snapshot
   `mamba_pool_idx`, `mamba_cow_src_index`, `mamba_needs_clear`, allocator
   availability, and Mamba alloc/evict counters around preparation and fallback;
   assert all unchanged/zero and all telemetry deltas false/zero.
5. **Admission separation:** after accepted staging, execute the real admission
   path and prove its normal match/COW still occurs and receives no RH ticket.
6. **Lifecycle matrix:** fresh, retracted-with-stale-host-anchor,
   active-chunked, requeued-formerly-chunked, terminal, active-attempt,
   RESTORING/READY/HOST_ALLOC/REVALIDATE/FRONTIER/BACKUP_PENDING. Assert fresh or
   requeued candidates get current preparation; excluded cases get zero match
   and zero issue.
7. **L3 parity matrix:** execute real `has_restore_potential` and
   `prefetch_gate_ok` for extant backuped, root, L3-durable-only,
   non-durable, and missing anchors. Both predicates must agree on potential.
8. **RH-OFF and telemetry independence:** prove eager-before-append, zero RH
   preparation, and identical decisions/state with telemetry enabled, disabled,
   or emission failure.

Package-backed collection must succeed at the immutable descendant. AST/source
extraction tests may supplement but cannot replace items 1, 2, 4, 5, 6, and 7.
The existing claim, hybrid-discard, HOST_ALLOC full-span/FIFO,
flush-before-evict, causal-event, and telemetry-join suites must also remain
green.

## Pinning and migration

The searched/design baseline remains immutable
`f629d4e2c19eb74571b4154438fd651ce24ff53b`. The final implementation pin is
`9213ee01d90ba3925e7fe928e80cc41354ee4fff`, whose parent is
`c4ad01ef5d7578bb542fe3e514a71cdbccb6c07a`. Read-only Git evidence shows the
baseline-to-pin surface is limited to `scheduler.py`, the exact
`UnifiedRadixCache.has_restore_potential` L3-parity clause, and focused tests.
The final telemetry-fix commit changes `Scheduler._emit_rh_match_prepare` and
one focused dependency-free regression. Independent review must verify that
manifest and conformance at the full pin; this repin is not implementation
acceptance.

No data or protocol migration exists. Rollout/rollback requires drain/restart;
RH-OFF is the compatibility path. Revert both scheduler mechanism and exact L3
predicate clause together to remove this design cleanly.

## Rejected alternatives and risks

Removing/splitting the exact L3 clause is rejected because it preserves the
policy/issue eligibility mismatch. General cache-layer authorization is also
rejected. Double matching, persistent tickets, enqueue-time preparation, a new
peek walker, preparation-time COW, or direct RH allocation/eviction remain out
of scope.

Primary risks are match-owned mutation before issue claim, cross-candidate
anchor invalidation, duplicate work, and accidental admission-COW suppression.
They are bounded by causal placement, one-pass lifetime, immediate validation,
one fallback, exact counters, no-COW oracles, and full rollback. Scheduler
serialization remains an implementation-review obligation.
