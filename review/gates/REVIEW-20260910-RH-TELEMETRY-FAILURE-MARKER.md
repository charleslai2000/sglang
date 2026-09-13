# Independent gate review — RH telemetry failure marker

```yaml
status: done
entry: ACCEPT
task_id: R3060-RH-TELEMETRY-FAILURE-MARKER-20260910
invocation_id: INV-20260910-REVIEW-TELEMETRY-MARKER-R1
orchestration_epoch: 20260910-rh-telemetry-review
role: reviewer
capability_level: L3
branch: 3060-12g-qwen35-4b
workdir: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
memory_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design
memory_inputs:
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/DEBUG3060-RH-MATCH-RUNTIME-PROVENANCE-20260910.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODER3060-RH-TELEMETRY-FAILURE-MARKER-20260910.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/escalations/ESC-20260910-RH-MATCH-RUNTIME-MISMATCH.md
memory_report: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/REVIEW-20260910-RH-TELEMETRY-FAILURE-MARKER.md
parent_thread_id: 01a07bea-d668-75b2-8280-6a2cf0870c1e
observed_workspace_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
reviewed_revision: 03a170ef4f35fe1d87d80a7b6f09e83261aef94e plus current uncommitted diff
parent_revision: 03a170ef4f35fe1d87d80a7b6f09e83261aef94e
verdict: PASS
code_gate: PASS
runtime_rh_value: UNPROVEN
deployment_acceptance: UNPROVEN
```

## Scope and decision

PASS for the declared narrow implementation gate. The current uncommitted
diff changes only `Scheduler._emit_rh_match_prepare` and adds one focused
dependency-free regression. It snapshots the existing RID once, preserves the
normal `rh_match_prepare.v1` message and nullable encoding, and converts a
swallowed emitter exception into a fixed
`rh_match_prepare_emit_failed.v1` marker. No RH scheduling, HiCache matching or
issue policy, Mamba behavior, allocator/eviction path, admission path,
HOST_ALLOC behavior, storage format, deployment, or remote host was changed.

## Independent evidence

### Binding and exact scope

- `pwd` observed
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`, matching the
  declared workdir.
- `git status --short --branch` observed branch `3060-12g-qwen35-4b`.
- `git rev-parse HEAD` is
  `03a170ef4f35fe1d87d80a7b6f09e83261aef94e`; the reviewed changes are
  uncommitted relative to that revision.
- `git diff --name-only HEAD` contains exactly:
  `python/sglang/srt/managers/scheduler.py` and
  `3090-dev/test_rh_contract_dependency_free.py`.
- `git diff --check` passes.

### Correctness, failure containment, and compatibility

- At `python/sglang/srt/managers/scheduler.py:4422`, `req.rid` is captured
  once as `safe_rid`; the normal decision ID and normal event use that same
  value. This closes the identified request-derived evaluation gap without
  changing control flow.
- At lines `4443-4478`, the existing normal event remains inside the broad
  observational catch. The fallback marker contains only fixed event/schema
  tokens plus the captured RID and exception class. Its own `logger.info` call
  is inside a final narrow catch, so logger failure cannot escape or recurse.
- The nullable normal-emission regression remains present and asserts literal
  `null` for nullable fields. The injected `prefix_indices.__len__` failure
  regression asserts one failure marker, the RID and exception class, and no
  normal schema marker.
- A separate direct probe with a logger whose `info` always raises returned
  without propagating, confirming fallback logger-failure containment.
- The diff has no calls or edits to RH selection, preparation, issue,
  admission, cache, Mamba, storage, allocator, eviction, or state-transition
  logic; it is observational only.

### Executed verification

- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_rh_contract_dependency_free.py -v`:
  **18/18 passed**.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_prefetch_gate_skip_regression.py -v`:
  **2/2 passed**.
- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_hicache_restore.py -v`:
  **92/92 passed**.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile` over the changed source
  and focused test: **passed**.
- `git diff --check`: **passed**.

## Findings

### Blocking findings

None. No correctness, security, compatibility, regression, or scope finding
attributable to this two-file diff blocks the narrow code gate.

### Non-blocking findings and acceptance impact

1. **P2 — Runtime/deployment value remains unproven.** The review was
   intentionally local and did not deploy, contact the remote host, or run a
   live probe. This PASS accepts telemetry-failure containment and local
   compatibility only; it does not establish that a deployed request emits
   either normal preparation telemetry or the failure marker.

2. **P2 — Current-SHA control-plane repin is not present.** The authoritative
   Phase-2 design chain is pinned through parent revision
   `9213ee01d90ba3925e7fe928e80cc41354ee4fff`, while this review covers the
   uncommitted telemetry descendant on `03a170ef...`. The descendant is within
   the already-authorized emitter boundary, but terminal chain acceptance
   should record this exact revision after commit/repin.

3. **P2 — Package-backed scheduler suites and formatter/type-check tools were
   not available in the supplied environment.** The focused contract,
   prefetch-gate, restore, compile, and direct failure-containment evidence is
   sufficient for this bounded telemetry gate; it is not a claim that every
   broader scheduler/runtime suite or static tool is green.

## Summary

**PASS for the narrow local implementation gate.** The failure marker is
   guarded against both telemetry-expression and logger failure, normal
   `rh_match_prepare.v1` nullable behavior remains intact, and the product diff
   is telemetry-only within the authorized scope. Runtime/deployment value and
   terminal current-SHA control-plane acceptance remain unproven.

## Followups

- Commit and repin the exact telemetry descendant if the overall gate chain
  requires immutable current-SHA acceptance.
- Use a fresh authorized runtime task for any live paired RH verification.

## Open issues

- Runtime RH value, deployment behavior, and performance are unproven.
- Broader package-backed scheduler evidence and formatter/type-check evidence
  remain unavailable in this environment.
- No product files, deployment state, remote host, or unrelated GPU process was
  modified.

## Communication

- Native `mcp__codex_tui__send_message_to_thread` was invoked for the phase
  lifecycle event using the declared `parent_thread_id`; the call completed
  without a tool error.
- The terminal `done` event was attempted with the same binding, but the tool
  was unavailable/not callable on that attempt. Communication path is
  therefore **degraded**.
- Last event sent/attempted: `phase`, invocation status `pending`, phase
  `verification`, report path this artifact, summary that independent review
  was underway and focused tests/compile/diff checks passed. No terminal event
  was confirmed by the native channel.
