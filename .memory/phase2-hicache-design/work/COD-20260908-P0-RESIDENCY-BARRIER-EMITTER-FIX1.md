STATUS: done

# COD-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX1

## Changed files

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py`
  - Added strict V3 residency identity validation.
  - Required a successfully logged exact `build_complete` identity and exact combined `durability_barrier` readiness before cold residency publication.
  - Required at least one keyed device detach, all keyed detach completions, no live FULL/Mamba values, and no forced-miss tombstone.
  - Re-polled pending node folds after KV/extra host release queues drain, closing the observed `residency_free_complete`-without-barrier gap.
  - Added generation/session retirement and full-reset cleanup for residency readiness/build identity state.
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py`
  - Added dependency-free deterministic causal probes.
- `mamba_component.py`: unchanged by this task; the existing tree-component Mamba detach hook already registers exact Mamba lifecycles.

## Causal root

The existing fold was attempted immediately after a free batch, before asynchronous host-release queue completion, and had no later product retry after those completions. It also did not enforce exact build/durability readiness or reject host-only detach sets. Individual `residency_free_complete` records therefore could exist without an authoritative node-level barrier.

## Evidence

- Command: `python3 /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py` — exit 0; output: `P0 residency-barrier emitter focused checks: PASS`. Covers the observed partial-completion path, post-queue retry, exact top-level event payload inputs, duplicate polling, generation reuse rejection, host-only, partial, missing durability, ambiguous context, and forced-miss suppression.
- Command: `python3 /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py` — exit 0; output: `P0 trace-context V4.3 focused checks: PASS`.
- Command: `PYTHONPYCACHEPREFIX=/tmp/codex-p0-residency-pycache python3 -m py_compile /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py` — exit 0; no output.
- Command: `PYTHONPYCACHEPREFIX=/tmp/codex-p0-residency-test-pycache python3 -m py_compile /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py` — exit 0; no output.
- Command: `python3 -c 'import ast; from pathlib import Path; paths=[Path("/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py"),Path("/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py"),Path("/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py")]; [ast.parse(p.read_text(), filename=str(p)) for p in paths]; print("AST parse: PASS")'` — exit 0; output: `AST parse: PASS`.
- Command: `git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py 3090-dev/test_p0_residency_barrier_emitter.py` — exit 0; no whitespace diagnostics. The separate untracked-file check `git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt diff --no-index --check /dev/null 3090-dev/test_p0_residency_barrier_emitter.py` produced no diagnostics and exit 1, as expected for a no-index difference.
- No remote live run was executed and no vehicle file was modified.

## Open issues

- Fresh live S=25 RH-off acceptance remains unverified and is outside this implementation task.
- The existing worktree contains prior dirty product, vehicle-adjacent, and review changes; they were preserved and not independently reviewed.

## Exact next live acceptance conditions

Run a fresh `T38C_RUN_ID` with `/tmp/t38c-durable-trace` created before requests and the existing `--enable-session-radix-cache` launcher feature enabled. Preserve the frozen S=25 RH-off workload plus nine unique churn sessions. For all 25 targets, require:

- one exact logical identity across `build_complete`, KV/Mamba durability evidence, `durability_barrier`, and `residency_barrier`;
- product `build_rid == response.id`, non-null scheduler generation, and canonical TP-group leader publication;
- `build < KV/Mamba durable < durability_barrier < residency_barrier < warm` in arrival order;
- `residency_barrier` with top-level `schema_version=p0_durable.v3`, exact `session_id`, `session_generation`, `build_rid`, `node_id`, `final_kv_hash`, `cold_residency=true`, and `result=true`;
- zero V2 evidence, conflicting identities, ancestor/final-node cross-joins, duplicate event IDs, reducer errors, or early warm lookups; and
- 25/25 warm/restore acceptance under the unmodified vehicle.
