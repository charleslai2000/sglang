ENTRY: ACCEPT

# REV-20260908-P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1

- Task ID: REV-20260908-P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1
- Orchestration epoch: phase2-hicache-design/2026-09-08
- Role: reviewer
- Invocation status: done
- Admission: ACCEPT
- Gate verdict: ACCEPT for the narrow implementation gate

## Artifacts and scope

- Gate contract: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1.md
- Reviewed product: python/sglang/srt/mem_cache/unified_radix_cache.py
- Reviewed focused test: 3090-dev/test_p0_residency_barrier_emitter.py
- Inputs: coder FIX1 report, r16 evidence summary in the phase2 ledger,
  prior node-sidecar FIX1 gate/report, prior R15 debugger diagnosis, current
  source, and focused test.

The product checkout is an aggregate dirty worktree with no task-specific
commit boundary. Review attribution is path- and behavior-scoped. Product
source and tests were not modified. No SSH, remote, live, vehicle, or
telemetry-as-runtime-evidence action was performed.

## Evidence

- python3 3090-dev/test_p0_residency_barrier_emitter.py — PASS.
- python3 3090-dev/test_p0_trace_context_v4.py — PASS.
- py_compile of both authorized Python files with a temporary bytecode
  prefix — PASS.
- Independent AST parse of both authorized files — PASS.
- Product git diff --check — PASS.
- Untracked focused-test whitespace check — PASS with expected no-index
  status and no diagnostics.
- Independent helper matrix — PASS for actual int NodeId, canonical
  decimal string, missing, wrong node, bool/noncanonical rejection, distinct
  int/string objects, and same-object alias resolution.
- Source review confirmed NodeId = int, TreeCore's dictionary-backed
  node_by_id, ID validation in the new helper, and the subsequent existing
  node hash plus strict identity validation in the barrier.
- The full focused fixture retains queue, completion, deduplication,
  invalid-identity, sidecar, and scheduler-surface regressions.

## Summary

The r16 failure mode is fixed at the intended boundary: a serialized decimal
node ID can resolve the actual integer TreeCore handle, while missing,
wrong-node, and distinct int/string alias resolutions fail closed. The helper
does not alter the six-field identity tuple, parent/hash binding, queue guard,
barrier predicates, deduplication, scheduler, vehicle, or Ready Horizon
behavior. The narrow implementation gate is accepted.

## Findings

No blocking findings and no questions.

The earlier P2 observation about an unguarded direct lookup in
_t38c_record_node_context remains outside this task's strict residency-fold
boundary. Addressing it would require a fresh Task ID; no repair was made in
this review.

## Followups

- Obtain fresh authorized live S=25 RH-off evidence after this gate. The r16
  run remains NOT_VERIFIED and is not converted into runtime acceptance.
- Preserve path-level attribution before merge/release in the aggregate dirty
  worktree.
- If stale recorder IDs are a supported boundary, dispatch separate lookup
  hardening under a fresh Task ID.

## Open issues

- No blocking implementation issue.
- No live/runtime acceptance claim.
- Aggregate worktree has no task-specific commit boundary.
- Prior recorder missing-node P2 remains open outside this gate.

## Status packet

- Status: done
- Artifacts: the gate contract above and this report.
- Evidence: direct source/test review, r16 ledger evidence, prior debugger and
  node-sidecar reviews, focused/V4.3/static verification, and independent
  typed-lookup probes.
- Summary: ACCEPT FIX1 for fresh live deployment of the narrow typed lookup
  hardening, subject to the separate fresh live gate.
- Followups: fresh live task; optional recorder hardening under a new Task ID.
- Open issues: no blocking findings; no live claim.
