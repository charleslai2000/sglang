# Independent gate review — RH tensor-bool fix R3

```yaml
status: done
entry: ACCEPT
task_id: R3060-RH-TENSOR-BOOL-FIX-20260910
invocation_id: INV-20260910-REVIEW-TENSOR-BOOL-FIX-R3
orchestration_epoch: 20260910-rh-tensor-bool-review-r3
role: reviewer
capability_level: L3
workdir: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
memory_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design
memory_inputs:
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODER3060-RH-TENSOR-BOOL-FIX-20260910.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-TELEMETRY-DEPLOY-PROBE-R3-20260910.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/REVIEW-20260910-RH-TELEMETRY-FAILURE-MARKER.md
memory_report: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/REVIEW-20260910-RH-TENSOR-BOOL-FIX-R3.md
parent_thread_id: 01a07bea-d668-75b2-8280-6a2cf0870c1e
observed_workspace_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
reviewed_revision: 1a8879750de9560a9acb3710357a45c115d4ac09 plus current uncommitted diff
verdict: PASS
code_gate: PASS
runtime_normal_event: UNPROVEN
deployment_acceptance: OUT_OF_SCOPE_FOR_THIS_LOCAL_GATE
communication: degraded; lifecycle event attempt was interrupted and no terminal event was confirmed
```

## Scope and decision

**PASS for the declared local implementation gate.** The change removes the
tensor truth test from the `device_hit_tokens` calculation while preserving
the existing nullable behavior and failure-marker containment. It is limited
to the scheduler telemetry emitter and its dependency-free regression test.

No blocking correctness, security, compatibility, regression, or scope
finding was identified in the reviewed diff.

## Independent evidence

### Binding and exact scope

- Immediate `pwd` check matched the declared workspace root.
- `git rev-parse HEAD` returned
  `1a8879750de9560a9acb3710357a45c115d4ac09`.
- `git diff --name-only HEAD` contains exactly:
  `python/sglang/srt/managers/scheduler.py` and
  `3090-dev/test_rh_contract_dependency_free.py`.
- `git diff --check` passed.
- The unrelated untracked workspace files were not treated as part of this
  gate and were not modified.

### Correctness and compatibility

- The old expression `len(getattr(req, 'prefix_indices', ()) or ())` could
  truth-test a multi-element `torch.Tensor`, raising before the normal event
  was emitted.
- The new code reads the field once, treats only `None` as absent, and calls
  `len(prefix_indices)` directly. This preserves `0` for absent values,
  preserves the one-dimensional tensor length for real request objects, and
  handles a bool-hostile tensor-like value without invoking `__bool__`.
- A length accessor failure remains inside the existing observational catch
  and emits the fixed `rh_match_prepare_emit_failed.v1` marker; the change
  does not alter RH matching, admission, cache, allocation, Mamba, storage,
  or request state transitions.
- The existing nullable-field regression and failure-marker regression remain
  present.

### Executed verification

- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_rh_contract_dependency_free.py -v`:
  **19/19 passed**, including the bool-hostile tensor-like regression,
  nullable emission, and safe length-failure marker checks.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile
  python/sglang/srt/managers/scheduler.py
  3090-dev/test_rh_contract_dependency_free.py`: passed.
- `git diff --check`: passed.
- Prior gate evidence independently supplied focused prefetch, restore,
  compile, and logger-failure containment checks; this review did not count
  those as newly executed.
- The declared operational evidence reports a successful HTTP probe and
  rollback, but observed `rh_match_prepare_emit_failed.v1` and no normal
  `rh_match_prepare.v1`. The report does not expose the failure's exception
  class, so it cannot prove or disprove the specific tensor-bool scenario.

## Findings

### Blocking findings

None.

### Non-blocking findings and acceptance impact

1. **P2 — Normal live preparation telemetry remains unproven.** The supplied
   deployment probe observed the failure marker rather than a normal
   preparation event. Because the exception class and failing field were not
   included, this is not attributable to the reviewed tensor-bool expression
   and does not block the local code gate. It does prevent claiming that the
   deployed request path is fully healthy.

2. **P2 — Broader package-backed/static-tool coverage is unavailable.** The
   coder report records missing Black/Ruff and mypy/Pyright, and this gate ran
   only the available dependency-free contract suite plus compilation. This
   is sufficient for the bounded expression change, not a claim that every
   broader scheduler suite or static check is green.

## Summary

**PASS for the narrow local implementation gate.** The None-safe length
calculation fixes the targeted multi-element tensor truth-test failure, keeps
normal and failure schemas bounded, and has passing focused coverage. Live
normal-event behavior remains unresolved by the supplied operational evidence.

## Followups

- If end-to-end telemetry acceptance is required, run a fresh authorized
  probe that records `exception_class` and distinguishes the target
  bool-hostile path from unrelated emitter failures.
- Repin/commit the exact reviewed revision when the overall gate chain
  requires immutable current-SHA acceptance.

## Open issues

- Runtime normal `rh_match_prepare.v1` emission is not established.
- Broader package-backed scheduler tests and formatter/type-check evidence
  remain unavailable.
- No product files, deployment state, remote host, or unrelated process was
  modified by this review.

## Communication

- The required parent thread binding was preserved in this report.
- A compact lifecycle event was attempted for
  `01a07bea-d668-75b2-8280-6a2cf0870c1e`, but the call was interrupted before
  confirmation; no terminal event is claimed.
