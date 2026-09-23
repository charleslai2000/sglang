ENTRY: ACCEPT

# Independent final code-gate review — RH match telemetry repair R2

```yaml
status: done
task_id: T3060-RH-MATCH-FINAL-REVIEW-R2-20260909
orchestration_epoch: 20260909-rh-ab56
role: reviewer
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
reviewed_revision: 9213ee01d90ba3925e7fe928e80cc41354ee4fff
parent_revision: c4ad01ef5d7578bb542fe3e514a71cdbccb6c07a
verdict: PASS
code_gate: PASS
runtime_rh_value: UNPROVEN
```

## Artifacts

- Repinned architecture gate:
  `review/gates/ARCH-20260909-RH-MATCH-PREP.md`.
- Repinned Novel Mechanism declaration:
  `review/gates/NOVEL-MECHANISM-20260909-RH-MATCH-PREP-R2.md`.
- Repinned Pattern Intake:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/storage/review/gates/pattern-intake/PATTERN-INTAKE-20260909-RH-MATCH-PREP.md`.
- Prior blocked final review:
  `review/gates/REVIEW-20260909-RH-MATCH-FINAL.md`.
- Coder report:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODER3060-RH-MATCH-TELEMETRY-FIX-20260909.md`.
- Package-backed tester report:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST3060-RH-REALPATH-VERIFY-20260909.md`.
- Preserved logs:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST3060-RH-REALPATH-VERIFY-20260909-logs/`.

Only this review artifact was written. Product source, tests, deployment state,
remote services, and load state were not modified.

## Evidence

### Pinning and exact scope

- `git rev-parse HEAD` independently resolves to
  `9213ee01d90ba3925e7fe928e80cc41354ee4fff`; its direct parent is
  `c4ad01ef5d7578bb542fe3e514a71cdbccb6c07`.
- The parent-to-final commit changes exactly:
  `python/sglang/srt/managers/scheduler.py` and
  `test/registered/unit/mem_cache/test_rh_contract_dependency_free.py`.
- The product change is confined to
  `Scheduler._emit_rh_match_prepare`; the test change adds the later-pass
  telemetry regression. `git diff --check` passes.
- The repinned baseline-to-final manifest is the five-file authorized surface:
  `scheduler.py`, `unified_radix_cache.py`,
  `test_prefetch_gate_skip_regression.py`, `test_ready_horizon_unit.py`, and
  `test_rh_contract_dependency_free.py`.

### Telemetry joins and nullable fields

- `scheduler.py:4440` now derives positive preparation `decision_id` as
  `f"{req.rid}:rh:{pass_seq}"`. This is the same current-pass construction used
  by `_emit_rh_decision` at `scheduler.py:4192-4195`; a prior cached request ID
  can no longer be reused by preparation telemetry.
- The local `field(...)` helper at `scheduler.py:4419` is used for
  `decision_id`, `attempt_id`, anchor ID, duration, and
  `session_generation` at `scheduler.py:4458-4460`. An absent nullable value is
  therefore emitted as the contract token `null`, not Python `None`.
- The committed regression sets stale `r1:rh:1`, exercises pass 2, and checks
  that preparation and preadmission both use `r1:rh:2` while
  `session_generation=null` is emitted.
- The unchanged emitter still includes the required identity, result/reason,
  hit/fill, anchor, gate, `cow_mamba=false`, duration, match-count/fallback,
  and five Mamba delta fields. Emission is observational and remains wrapped
  so telemetry failure cannot drive control.

### Package-backed and focused evidence

The RTX3060 report used the existing package environment and an isolated
checkout whose source/test hashes matched the requested commit. Preserved log
hashes independently match the report's table. The evidence is:

- focused commit telemetry/no-COW/valid-ticket/fallback oracles: **7/7**;
- focused Scheduler/Ready Horizon pass oracles: **13/13**;
- non-failing scheduler-feed selection: **43/43**;
- Ready Horizon partition suite: **18/18**;
- RH contract suite: **16/16**;
- gate-skip regression: **2/2**;
- restore suite: **92/92**.

The focused evidence exercises the committed scheduler preparation, issue,
decision, fallback, anchor, no-COW, and RH-OFF paths through the package-backed
modules. It closes the prior review's missing-dependency evidence gap for this
narrow telemetry descendant. It does not make a runtime or performance claim.

### Ownership and compatibility boundaries

- RH-OFF remains eager-before-append at `scheduler.py:5524-5528`; the reviewed
  diff does not alter this ordering or add RH preparation in OFF mode.
- The 7/7 no-COW evidence preserves request Mamba fields and allocation/eviction
  counters, and the source diff introduces no Mamba operation.
- Admission retains its separate normal `req.init_next_round_input` call at
  `scheduler.py:6241`; no RH ticket or telemetry field suppresses admission
  matching/COW.
- The reviewed product diff contains no allocator, eviction, HOST_ALLOC,
  persistence, cache-authority, wire-format, or deployment change. The
  43/43 scheduler-feed selection and 18/18 partition result provide neighboring
  boundary evidence; the three omitted feed cases are classified explicitly
  below.
- No security, compatibility, or regression finding is attributable to the
  two changed symbols. Runtime RH value, paired live replay, load, deployment,
  and performance remain outside this code-gate decision.

## Explicit residual classification

The two broad package-backed suites are not fully green. The preserved logs
show `test_ready_horizon_unit.py` at 70 tests with 2 failures and 4 errors,
and `test_hicache_restore_scheduler_feed.py` at 46 tests with 1 failure and 2
errors. These are six mismatch categories, not silently ignored passes:

1. **NON-BLOCKING / fixture API mismatch:** four
   `DeterministicMissParkTests` errors use a fixture-local `charge()` that does
   not accept the production `origin=` keyword. This is outside
   `_emit_rh_match_prepare`; follow up by reconciling the fixture signature.
2. **NON-BLOCKING / expectation/API mismatch:**
   `test_active_prefetch_claim_blocks_duplicate_and_classifies_retry` expects
   the legacy enum identity, while the current method returns the typed
   `PrefetchIssueResult`. This is outside the changed symbol and requires test
   owner reconciliation, not a telemetry-commit change.
3. **NON-BLOCKING / expectation mismatch:**
   `test_ready_stage_log_reports_issue_result` searches for the legacy
   `evt=ready_stage.v2` token; the current record is
   `evt=ready_stage schema=rh_stage.v2`. The reviewed diff changes neither
   ready-stage logging nor this API/token.
4. **NON-BLOCKING / fixture API mismatch:**
   `test_backup_pending_wake_reissues_as_demand_restore` supplies a fixture
   lambda without the current `origin=` keyword. It is outside
   `_emit_rh_match_prepare` and outside the final commit's changed behavior.
5. **NON-BLOCKING / incomplete fixture:**
   `test_positive_alloc_failure_maps_to_host_capacity_wait` supplies a
   `tree_cache` without `pop_host_alloc_failure`, which the current terminal
   path reads. The reviewed commit does not touch that terminal path or
   HOST_ALLOC authority.
6. **NON-BLOCKING / unresolved expectation or semantic residual:**
   `test_host_alloc_wait_wakes_only_for_complete_requested_span` expects
   `False` at available size `54976`, while the current helper returns `True`.
   This remains unresolved and must not be called green; it is outside the
   changed telemetry symbol and is assigned to a fresh HOST_ALLOC owner task.

These residuals prevent a claim that either broad suite is fully green. They do
not block acceptance of this exact two-file telemetry repair because each
failing path is outside the commit's changed symbols and the focused
commit-specific oracles, contract, restore, gate-skip, scheduler-feed, and
partition evidence pass. Any attempt to change the fixtures, APIs, or
HOST_ALLOC semantics requires a fresh Task ID.

## Findings

No blocking correctness, security, compatibility, scope, or regression finding
remains for commit `9213ee01d90ba3925e7fe928e80cc41354ee4fff`.

The six residual categories above are recorded findings for follow-up, not
questions and not hidden test exclusions. They do not alter the code-gate
verdict because the commit changes only telemetry decision-ID/null formatting
and its focused regression.

## Summary

**PASS for the code gate at `9213ee01d90ba3925e7fe928e80cc41354ee4fff`.**
The exact scope is verified; current-pass preparation joins now match the
downstream decision; nullable session generation is encoded as `null`; and the
package-backed focused, contract, restore, gate-skip, scheduler-feed, and
partition evidence passes. RH-OFF ordering, admission separation, Mamba
no-COW, and HOST_ALLOC ownership remain intact in the reviewed descendant.

The six broad-suite fixture/API/expectation mismatch categories remain
documented residuals and require fresh follow-up before those suites may be
claimed fully green. They are outside this commit's changed symbols and are not
evidence of a regression in this telemetry repair.

Runtime RH value is **UNPROVEN**. No live paired RH-OFF/RH-ON replay, load,
deployment, or performance acceptance is included.

## Followups

- Fresh test-owner Task ID: reconcile the six broad-suite fixture/API/
  expectation mismatches and rerun both suites without exclusions.
- Fresh runtime Task ID, only if runtime acceptance is desired: run the
  hash-pinned paired RH-OFF/RH-ON replay with complete joins; report missing
  joins as not computable rather than inferring RH value from HTTP success.
- Extra implementation, test, review, deployment, or runtime work requires a
  fresh Task ID.

## Open issues

- The six broad-suite mismatch categories remain unresolved; the two suites are
  not fully green.
- No runtime RH value, performance, deployment, or load evidence is claimed.
- The reviewer did not modify product source, test source, deployment state, or
  remote systems.
