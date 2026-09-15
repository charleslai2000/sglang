# Independent final review — RH current-match telemetry fix

```yaml
status: done
task_id: T3060-RH-MATCH-FINAL-REVIEW-20260909
orchestration_epoch: 20260909-rh-ab54
role: reviewer
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
reviewed_revision: 9213ee01d90ba3925e7fe928e80cc41354ee4fff
parent_revision: c4ad01ef5d7578bb542fe3e514a71cdbccb6c07a
verdict: BLOCK
code_gate: BLOCK
runtime_rh_value: UNPROVEN
```

## Artifacts

- Repinned architecture gate:
  `review/gates/ARCH-20260909-RH-MATCH-PREP.md`.
- Repinned Pattern Intake:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/storage/review/gates/pattern-intake/PATTERN-INTAKE-20260909-RH-MATCH-PREP.md`.
- Repinned Novel Mechanism R2:
  `review/gates/NOVEL-MECHANISM-20260909-RH-MATCH-PREP-R2.md`.
- Coder report:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODER3060-RH-MATCH-TELEMETRY-FIX-20260909.md`.
- Tester report:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST3060-RH-MATCH-TELEMETRY-VERIFY-20260909.md`.
- Prior R2 review:
  `review/gates/REVIEW-20260909-RH-MATCH-PREP-R2.md`.
- This final independent review artifact.

No product source, test source, deployment state, remote host, or runtime
process was modified by this review. Only this gate artifact was written.

## Evidence

### Immutable revision and scope

- `git rev-parse HEAD` independently resolves to
  `9213ee01d90ba3925e7fe928e80cc41354ee4fff` on
  `3060-12g-qwen35-4b`.
- `git rev-list --parents -n 1 9213ee01d90ba3925e7fe928e80cc41354ee4fff`
  confirms the direct parent is
  `c4ad01ef5d7578bb542fe3e514a71cdbccb6c07a`.
- The parent-to-final commit changes exactly:
  `3090-dev/test_rh_contract_dependency_free.py` and
  `python/sglang/srt/managers/scheduler.py`.
- The repinned baseline-to-final manifest contains exactly the two authorized
  product files and the three focused tests:
  `scheduler.py`, `unified_radix_cache.py`,
  `test_prefetch_gate_skip_regression.py`, `test_ready_horizon_unit.py`, and
  `test_rh_contract_dependency_free.py`.
- `git diff --check 9213ee01d9^ 9213ee01d9` passes. The worktree has no
  tracked modifications; pre-existing untracked gate/memory artifacts were
  preserved.

### Telemetry join, null encoding, and schema

- At `python/sglang/srt/managers/scheduler.py:4440`,
  `_emit_rh_match_prepare` derives `decision_id` as
  `f"{req.rid}:rh:{pass_seq}"` for the current positive pass. It no longer
  reuses `req.hicache_last_rh_decision_id` from an earlier pass.
- At `scheduler.py:4419` and `:4460`, the existing `field(...)` helper maps
  absent nullable values to the literal `null`; this covers
  `session_generation` as well as the other nullable telemetry fields.
- The committed regression at
  `3090-dev/test_rh_contract_dependency_free.py:370-427` sets stale
  `r1:rh:1`, exercises pass 2, and asserts preparation and preadmission both
  carry `r1:rh:2` while `session_generation=null` is emitted.
- The emitter at `scheduler.py:4443-4480` contains the required schema fields:
  identity/join fields, result/reason, fill and hit lengths, anchor
  classification/existence/gate, `cow_mamba=false`, duration, match count and
  fallback, and all five Mamba delta fields. No telemetry field is used for
  control flow.

### Independent deterministic evidence

Run at the checked-out immutable commit with `PYTHONDONTWRITEBYTECODE=1`:

- `python3 3090-dev/test_rh_contract_dependency_free.py -v`: **16/16 passed**.
- `python3 3090-dev/test_prefetch_gate_skip_regression.py -v`: **2/2 passed**.
- `python3 3090-dev/test_hicache_restore.py -v`: **92/92 passed**.
- `PYTHONPYCACHEPREFIX=<temporary> python3 -m py_compile` over the changed
  product/test files and the two unchanged focused files: **PASS**.
- `git diff --check`: **PASS**.

These results independently reproduce the requested `16+2+92` evidence and
close the two prior telemetry findings: stale cross-pass decision IDs and
non-contract `session_generation=None` encoding.

### Real-path, no-COW, and boundary review

- The prior tester’s additional method-path harness executes committed
  scheduler method bodies through preparation and issue, and reports valid,
  invalidation/fallback, and unchanged Mamba fields/counters. Its
  collaborators are synthetic test doubles, not the real request/cache
  components required by the architecture gate.
- The final tester report confirms package-backed scheduler tests did not reach
  collection/runtime. The exact archive attempts for
  `test_ready_horizon_unit.py`, `test_ready_horizon_partition.py`, and
  `test_hicache_restore_scheduler_feed.py` all fail at import with
  `ModuleNotFoundError: No module named 'orjson'`; `msgspec`, `torch`, and
  `pytest` are also unavailable.
- Therefore the evidence is useful bounded method/source evidence, but it is
  not the required real valid-ticket, real fallback, real request/cache
  no-COW, real admission-separation, complete lifecycle, and real L3 parity
  oracle set.
- Structural source/diff inspection finds no new allocator, eviction, Mamba,
  HOST_ALLOC, persistence, or admission authority in the reviewed descendant.
  RH-OFF still issues before `waiting_queue.append` at
  `scheduler.py:5524-5528`; admission retains its separate normal
  `req.init_next_round_input(self.tree_cache)` at `scheduler.py:6241`; and
  `has_restore_potential` now has the exact L3 parity term at
  `unified_radix_cache.py:6096-6100`, matching `prefetch_gate_ok` at
  `:4951-4955`.

### Package and runtime limitations

- The architecture gate requires package-backed collection at the immutable
  descendant and says AST/source extraction cannot replace the real oracles
  (`ARCH-20260909-RH-MATCH-PREP.md:128-165`).
- The Pattern Intake likewise records the real 17-case contract as required and
  identifies the independent-oracle gap as still blocking implementation
  acceptance (`PATTERN-INTAKE-20260909-RH-MATCH-PREP.md:231,
  :251-253, :280-318`).
- No dependency installation, deployment, remote load, live RH-OFF/RH-ON
  replay, or performance test was attempted. Runtime RH value and performance
  remain uncomputable/unproven.

## Findings

### BLOCKER-1 — Mandatory real-component acceptance oracles are unavailable

Location: `review/gates/ARCH-20260909-RH-MATCH-PREP.md:128-165`, with the
corresponding required-test contract in the repinned Pattern Intake
`:280-318`; evidence limitation in
`TEST3060-RH-MATCH-TELEMETRY-VERIFY-20260909.md:102-116`.

The authoritative architecture gate states that a reviewer may not PASS
without real valid-ticket and invalidation/fallback integration, fail-closed,
real request/cache no-COW, admission separation, lifecycle, real L3 parity,
and RH-OFF/telemetry-independence oracles. It also explicitly requires
package-backed collection. The supplied tester evidence has the requested
`16+2+92` deterministic passes and the prior method-path harness, but the
harness uses synthetic collaborators; the package-backed scheduler suites
cannot collect because dependencies are missing. The tests therefore do not
establish the required real `match_prefix`, allocator/Mamba counter,
admission-COW, HOST_ALLOC, or full lifecycle behavior.

Acceptance impact: the telemetry repair is independently correct and the
reviewed diff preserves the stated ownership boundaries structurally, but the
implementation gate cannot be accepted under its explicit minimum oracle
contract. The tester report’s `code_gate: PASS` is not sufficient to override
that contract.

## Requirement summary

| Requirement | Independent result |
| --- | --- |
| Exact SHA, parent, branch, and scope | PASS |
| Current-pass decision-id join | PASS; source and later-pass regression |
| Explicit nullable `null` encoding | PASS; source and regression |
| Complete `rh_match_prepare.v1` telemetry | PASS by source/schema inspection and focused tests |
| `16+2+92` evidence | PASS; independently rerun |
| Real-path/no-COW/admission/lifecycle/L3 oracles | BLOCK; synthetic bounded harness only and package-backed collection unavailable |
| RH-OFF ordering and HOST_ALLOC/Mamba/admission boundaries | PASS structurally; required real behavioral evidence unavailable |
| Security/scope/compatibility regression in this descendant | No finding; narrow telemetry-only parent-to-final diff |
| Package-backed scheduler tests | BLOCKED by missing `orjson` (also `msgspec`, `torch`, `pytest`) |
| Runtime RH value/performance | UNPROVEN; explicitly separate from code correctness |

## Summary

**BLOCK for code acceptance.** The immutable commit has the requested exact
scope and repairs the prior telemetry defects: current-pass decision joins,
explicit nullable encoding, and the complete preparation telemetry schema are
supported by source inspection and the independent focused suites. The
`16+2+92` evidence, compile, and diff checks pass.

The code gate remains blocked because the repinned architecture and Pattern
Intake require real-component/package-backed integration and no-COW/admission/
lifecycle/L3 oracles that are not available in this environment. This is an
acceptance-evidence blocker, not a newly observed product defect. Runtime RH
value, performance, deployment, and remote-load behavior remain separately
unproven.

## Followups

- Fresh tester Task ID: provide the approved package-backed environment and run
  the architecture-mandated real valid-ticket, fallback, fail-closed, no-COW,
  admission, lifecycle, L3 parity, RH-OFF, and telemetry-independence oracles.
- Fresh reviewer Task ID: re-evaluate the code gate after those artifacts are
  pinned to `9213ee01d90ba3925e7fe928e80cc41354ee4fff`.
- Fresh runtime Task ID, only after code-gate acceptance: run the hash-pinned
  paired RH-OFF/RH-ON replay and report missing joins as not computable.

## Open issues

- `orjson`, `msgspec`, `torch`, and `pytest` are unavailable, preventing
  package-backed scheduler collection.
- No real-component no-COW/admission/lifecycle oracle artifact is available;
  the bounded method-path harness uses synthetic collaborators.
- Runtime RH value, performance, deployment, and remote-load evidence remain
  unverified by explicit scope and environment limits.
- Extra implementation, test, review, deployment, or runtime work requires a
  fresh Task ID.
