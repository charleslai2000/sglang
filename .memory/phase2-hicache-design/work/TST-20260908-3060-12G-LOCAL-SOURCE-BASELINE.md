# TST-20260908-3060-12G-LOCAL-SOURCE-BASELINE

status: done
invocation_status: done
task_id: TST-20260908-3060-12G-LOCAL-SOURCE-BASELINE
orchestration_epoch: phase3-3060-4b-navigator/2026-09-08
role: test-runner

## Scope and environment

- Repository: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- Branch: `3060-12g-qwen35-4b`
- HEAD: `d49214e59228a555dc9f878426928a8a628d8848`
- Initial and final `git status --short --branch`: `## 3060-12g-qwen35-4b`
- Repository-local `AGENTS.md`: absent; supplied task contract was followed.
- Checks were local and read-only with respect to product source. No remote access, live-system claim, model run, or benchmark was performed.

## Verification evidence

Working directory for commands: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`

### `python3 3090-dev/test_p0_residency_barrier_emitter.py`

Exit status: `0`

Exact output:

```text
Six-field leaf/parent sidecar and no-last-write-wins checks: PASS
Exact NodeId/string lookup, missing, and ambiguity checks: PASS
Final-node-only eligibility and bounded parent diagnostic: PASS
Async durability readiness and exact-free retry: PASS
Required component snapshot and live blocker proof: PASS
Bounded diagnostic outcome emission under repeated reconcile: PASS
No-next-request final-token trigger: PASS
Non-empty host-release queue barrier: PASS
F-3 run-ID collision probe: PASS
F-4 invalid residency context none-trace-context: PASS
F-4 invalid residency context absent-trace-context: PASS
F-4 invalid residency context missing-schema_version: PASS
F-4 invalid residency context missing-run_id: PASS
F-4 invalid residency context missing-session_id: PASS
F-4 invalid residency context missing-session_generation: PASS
F-4 invalid residency context missing-build_rid: PASS
F-4 invalid residency context missing-warm_rid: PASS
F-4 invalid residency context missing-node_id: PASS
F-4 invalid residency context missing-final_kv_hash: PASS
F-4 invalid residency context node-context-mismatch: PASS
Real TP=1 scheduler checkpoint primary/extra probe: PASS
P0 residency-barrier emitter focused checks: PASS
```

### `python3 3090-dev/test_p0_trace_context_v4.py`

Exit status: `0`

Exact output:

```text
P0 trace-context V4.3 focused checks: PASS
```

### `python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_p0_residency_barrier_emitter.py`

Exit status: `0`; exact output: none.

### `git diff --check HEAD`

Exit status: `0`; exact output: none.

### AST parse

Command:

```text
python3 -c 'import ast; from pathlib import Path; files=[Path("python/sglang/srt/mem_cache/unified_radix_cache.py"), Path("3090-dev/test_p0_residency_barrier_emitter.py")]; [ast.parse(p.read_text(), filename=str(p)) for p in files]; print("AST parse: PASS"); print("Parsed:"); [print(p) for p in files]'
```

Exit status: `0`

Exact output:

```text
AST parse: PASS
Parsed:
python/sglang/srt/mem_cache/unified_radix_cache.py
3090-dev/test_p0_residency_barrier_emitter.py
```

## Summary

All specified local source checks passed. The worktree was clean at completion and remained on the recorded branch and HEAD.

## Followups

- None.

## Open issues

- None within the authorized local verification scope.
