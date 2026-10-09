STATUS: done

# COD-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX3

## Changed files

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py`

No vehicle, Mamba component, ledger, gate report, remote host, or unrelated file was modified.

## Root cause and implementation

FIX2 formed residency lifecycle state from a five-field tuple and added the run ID only at logging time. It also lacked direct residency-fold evidence for absent or incomplete V3 context.

FIX3 now validates a non-empty `run_id` in the residency context and uses the exact six-field identity:

`(run_id, session_id, session_generation, build_rid, node_id, final_kv_hash)`

The run ID is carried into the product trace context from the authoritative `T38C_RUN_ID`, preserved in detach lifecycle tokens, included in the cache-owned identity/dedup/readiness/barrier state, and explicitly published on `residency_barrier`. Polling and session-retirement indexing were adjusted for the six-field layout. Invalid context fails closed before ledger mutation.

The focused fixture retains the prior repeated-recycle, same-node cross-cache, concurrency, partial/host-only, durability, warm/forced-miss, and marker-off checks. It adds named direct residency cases for `None`, absent context, every missing V3 field including `run_id`, node-context mismatch, and asserts no event or ledger mutation. It also includes a run-ID-only collision probe.

## Verification evidence

- `python3 3090-dev/test_p0_residency_barrier_emitter.py` — PASS. Output names all F-4 cases and reports `F-3 run-ID collision probe: PASS`.
- `python3 3090-dev/test_p0_trace_context_v4.py` — PASS.
- `PYTHONPYCACHEPREFIX=/tmp/codex-p0-residency-fix3-pycache python3 -m py_compile ...` for the authorized product and focused test files — PASS.
- AST parse of both authorized files — PASS.
- Independent AST-extracted run-ID collision probe — PASS: `('run-a', 's', 1, 'b', 'n', 'h') != ('run-b', 's', 1, 'b', 'n', 'h')`.
- `git diff --check` on the product file — PASS with no diagnostics.
- `git diff --no-index --check /dev/null 3090-dev/test_p0_residency_barrier_emitter.py` — expected exit 1 because the focused test is untracked, with no whitespace diagnostics.
- No remote, live, launcher, engine, or pytest run was performed.

## Summary

Both FIX2 blockers are addressed without weakening F-1/F-2 protections or changing the cache-owned ledger and lock design.

## Fresh review conditions

Run a fresh independent FIX3 gate review against the exact two authorized source/test files and this report. The reviewer should rerun the focused emitter, V4.3, py_compile, AST, diff-check, run-ID collision, and named missing-context probes. Live/remote acceptance remains outside this task.

## Followups

- Fresh independent reviewer gate acceptance for FIX3.
- Separate authorized operational/live task if live P0 evidence is required.

## Open issues

- No live or remote residency evidence is claimed.
- The aggregate worktrees remain pre-existing dirty worktrees without a task-specific commit boundary.
