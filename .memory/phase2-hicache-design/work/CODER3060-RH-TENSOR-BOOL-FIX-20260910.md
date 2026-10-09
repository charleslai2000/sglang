# CODER3060-RH-TENSOR-BOOL-FIX-20260910

status: done
entry: ACCEPT
task_id: C3060-RH-TENSOR-BOOL-FIX-20260910
invocation_id: INV-20260910-CODER-TENSOR-BOOL-FIX-R1
orchestration_epoch: 20260910-rh-tensor-bool-fix
role: coder
capability_level: L3

## Binding

- workdir: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- memory_root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design`
- memory_inputs:
  - `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-TELEMETRY-DEPLOY-PROBE-R3-20260910.md`
  - `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODER3060-RH-TELEMETRY-FAILURE-MARKER-20260910.md`
  - `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/REVIEW-20260910-RH-TELEMETRY-FAILURE-MARKER.md`
- memory_report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODER3060-RH-TENSOR-BOOL-FIX-20260910.md`
- parent_thread_id: `01a07bea-d668-75b2-8280-6a2cf0870c1e`
- observed workspace root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` (`pwd` matched)
- branch: `3060-12g-qwen35-4b`

## Communication

- Native `mcp__codex_tui__send_message_to_thread` was unavailable/not callable in this runtime.
- Last successfully sent event: none.
- Communication path: degraded; lifecycle evidence is recorded in this report.

## Exact authorized diff

- `python/sglang/srt/managers/scheduler.py`: replaced the telemetry-only `getattr(req, 'prefix_indices', ()) or ()` path with an explicit `None` check and `len(prefix_indices)` inside the existing guarded emitter block. Normal device-hit token values are preserved without tensor truth testing.
- `3090-dev/test_rh_contract_dependency_free.py`: added a dependency-free regression using a bool-hostile, length-bearing Tensor-like object. It asserts one normal `rh_match_prepare.v1` record with `device_hit_tokens=2` and no failure marker.
- Existing `test_match_preparation_emits_safe_failure_marker_for_field_error` was preserved and remains passing.
- No other product files were changed; no deployment or commit was performed.

## Evidence

- `PYTHONDONTWRITEBYTECODE=1 python3 3090-dev/test_rh_contract_dependency_free.py -v`: **19/19 passed**.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile python/sglang/srt/managers/scheduler.py 3090-dev/test_rh_contract_dependency_free.py`: passed.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q python/sglang/srt/managers/scheduler.py 3090-dev/test_rh_contract_dependency_free.py`: passed.
- Direct AST parsing of both authorized files: passed.
- Deterministic checks: passed for removal of the truth-test expression, presence of normal/failure schemas and both regressions, exact authorized `git diff --name-only`, and `git diff --check`.
- Formatter attempts: `python3 -m black --check ...` and `python3 -m ruff check ...` unavailable because the modules are not installed.
- Typecheck attempts: `python3 -m mypy ...` and `python3 -m pyright ...` unavailable because the modules are not installed.

## Artifacts

- Modified source: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py`
- Modified focused regression test: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_rh_contract_dependency_free.py`
- This report.

summary: done; the RH telemetry device-hit length path no longer truth-tests multi-element tensor-like values, preserves the existing token count, and has focused normal-emission coverage while retaining failure-marker behavior.

followups: none within this invocation.

open_issues:

- Black/Ruff and mypy/Pyright could not run because the local environment lacks those tools.
- Native parent lifecycle events could not be delivered because the runtime tool was unavailable.
