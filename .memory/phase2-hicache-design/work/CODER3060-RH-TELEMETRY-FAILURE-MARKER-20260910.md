# CODER3060-RH-TELEMETRY-FAILURE-MARKER-20260910

status: done
entry: ACCEPT
task_id: C3060-RH-TELEMETRY-FAILURE-MARKER-20260910
invocation_id: INV-20260910-CODER-TELEMETRY-MARKER-R1
orchestration_epoch: 20260910-rh-telemetry-handoff
role: coder
capability_level: L3
de_escalation: L2 causal decision accepted in DEBUG3060-RH-MATCH-RUNTIME-PROVENANCE-20260910

## Binding

- workdir: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- memory_root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design`
- memory_inputs:
  - `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/DEBUG3060-RH-MATCH-RUNTIME-PROVENANCE-20260910.md`
  - `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/escalations/ESC-20260910-RH-MATCH-RUNTIME-MISMATCH.md`
- memory_report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODER3060-RH-TELEMETRY-FAILURE-MARKER-20260910.md`
- parent_thread_id: `01a07bea-d668-75b2-8280-6a2cf0870c1e`
- observed workspace root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` (`pwd` matched the binding)

## Communication

- Native `mcp__codex_tui__send_message_to_thread` was attempted for ENTRY and phase events but was unavailable/not callable in this runtime.
- Last successfully sent event: none.
- Communication path: degraded; lifecycle evidence is recorded here.

## Exact authorized diff

- `python/sglang/srt/managers/scheduler.py:4422-4478`: snapshot the already-safe `req.rid` once; use it for normal telemetry joins; replace the silent emitter catch with a guarded fixed `rh_match_prepare_emit_failed.v1` marker containing only `rid` and `exception_class`.
- `3090-dev/test_rh_contract_dependency_free.py:463-497`: add an injected `prefix_indices.__len__` failure regression asserting exactly one safe failure marker and no normal schema marker. The existing nullable normal-emission regression remains unchanged.
- No RH scheduling, prefetch/staging, Mamba, HiCache semantics, 3090 branch policy, remote host, deployment, or commit was changed.

## Evidence

- `python3 3090-dev/test_rh_contract_dependency_free.py`: **18/18 passed** in 1.059s, including `test_match_preparation_emits_with_nullable_fields` and `test_match_preparation_emits_safe_failure_marker_for_field_error`.
- `python3 -m py_compile python/sglang/srt/managers/scheduler.py 3090-dev/test_rh_contract_dependency_free.py`: passed.
- `python3 -m compileall -q python/sglang/srt/managers/scheduler.py 3090-dev/test_rh_contract_dependency_free.py`: passed.
- Direct AST parsing of both authorized files: passed.
- Deterministic source/test marker checks: passed (normal schema, failure schema, exception class, and both regressions present).
- `git diff --check`: passed.
- `python3 -m pytest ...`: unavailable (`No module named pytest`); `python ...`: unavailable (`python: command not found`).
- Formatter attempts were unavailable: `python3 -m black` and `python3 -m ruff` reported missing modules. No formatter was installed or changed.
- Typecheck attempts were unavailable: `python3 -m mypy` and `python3 -m pyright` reported missing modules.

## Artifacts

- Modified source: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py`
- Modified focused regression test: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_rh_contract_dependency_free.py`
- This report.

summary: done; the telemetry-only failure path now emits a fixed failure marker with the safe RID and exception class while preserving normal nullable `rh_match_prepare.v1` behavior. Focused tests and local deterministic checks pass.

followups: an independently authorized bounded live probe may verify that each request produces either `rh_match_prepare.v1` or the explicit failure marker before the same RID's stage event. No deployment or commit was performed.

open_issues:

- Black/Ruff and mypy/Pyright could not run because the local environment lacks those tools.
- Native parent lifecycle events could not be delivered because the runtime tool was unavailable.
