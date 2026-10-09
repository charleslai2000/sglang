ENTRY: ACCEPT

# P0.1 readiness-to-residency timing-fix remediation

- Task ID: `COD-20260908-P0-RESIDENCY-R17-TIMING-FIX2`
- Orchestration epoch: `phase2-hicache-design/2026-09-08`
- Role: `coder`
- Invocation status: `blocked`
- Live/remote decision: no remote, live, deployment, or vehicle action was performed.

## Change manifest

Authorized files touched:

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py`
  - Production `_t38c_residency_log` now admits supported `FULL` and `MAMBA` frees for device/host tiers using the same exact digest/token path.
  - Added an explicit production detach-manifest seal boundary; incomplete/unsupported manifests retire fail-closed, and a late exact detach cannot be omitted after sealing.
  - Added an owning drain-transaction callback for queue-blocked identities after release drains commit. The storage drain no longer invokes the polling helper as its correctness trigger.
  - Separated reconcile-attempt and reason-attempt accounting from bounded physical diagnostic deduplication, and added the P0.1 terminal diagnostic aggregate fields/schema.
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py`
  - Extended the AST fixture loader to expose the production residency-log and explicit-seal/drain-callback boundaries.
  - The focused matrix was not completed because the existing direct-helper cases require explicit seal wiring before their publication assertions can remain valid.
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/COD-20260908-P0-RESIDENCY-R17-TIMING-FIX2.md`
  - This report.

## Verification evidence

Run from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `python3 3090-dev/test_p0_residency_barrier_emitter.py` — **FAIL**. It reaches the existing asynchronous retry case, then fails at `3090-dev/test_p0_residency_barrier_emitter.py:885` because `len(_published_records(records)) == 1` is false. This is the explicit-seal integration gap; no further repair was attempted after the user-directed stop.
- `python3 3090-dev/test_p0_trace_context_v4.py` — **PASS** (`P0 trace-context V4.3 focused checks: PASS`).
- `python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_p0_residency_barrier_emitter.py` — **PASS**, exit 0.
- AST parse of both authorized Python files — **PASS** (`AST parse: PASS`).
- `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_p0_residency_barrier_emitter.py` — **PASS**, exit 0, no output.
- `git diff --no-index --check /dev/null 3090-dev/test_p0_residency_barrier_emitter.py` — exit 1 because the authorized fixture is untracked in this shared worktree; no whitespace diagnostics were produced.

## Summary

The minimum production-side B1–B4 remediation is saved, but the task is **blocked** because the required deterministic fixture does not pass after the explicit seal boundary was introduced. B5 therefore cannot be claimed complete, and no gate acceptance or readiness claim is made.

## Followups

- Fresh Task ID: wire explicit seal calls into the dependency-free fixture's production-boundary scenarios, then add the requested two-identity, all-tier, fail-closed, poll-disabled drain, logger-retry, and terminal-aggregate assertions.
- Re-run the complete required verification set after the fixture passes.
- Obtain independent gate review before any remote/live work.

## Open issues

- Focused residency fixture is failing at the async publication assertion because direct `_t38c_note_detach` setup no longer establishes the required production detach seal.
- B5 coverage is incomplete; no deterministic acceptance evidence exists for the full requested matrix.
- No remote/live result exists by design.
