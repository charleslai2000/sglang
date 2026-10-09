# C3060-RH-SPEC-BUDGET-RETRIGGER-20260910

status: blocked
stable_task_id: C3060-RH-SPEC-BUDGET-RETRIGGER-20260910
invocation_id: INV-20260910-CODER-RH-SPEC-BUDGET-R1
epoch: 20260910-rh
role: coder
branch: 3060-12g-qwen35-4b

## Bindings

- workdir: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- memory_root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design`
- memory_inputs:
  - `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-QUEUE-COMPARE-R1-20260910.md`
  - `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/escalations/ESC-20260910-RH-SPEC-BUDGET-RETRIGGER.md`
- memory_report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODER3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`
- parent_thread_id: `01a07bea-d668-75b2-8280-6a2cf0870c1e`
- observed_workspace: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`

## Artifacts

- `python/sglang/srt/managers/scheduler.py`
- `3090-dev/test_ready_horizon_unit.py`

## Summary

- Post-issue SPEC_BUDGET parking now builds a causal epoch snapshot with the observed `cc.inflight_speculative_tokens`, so a tail candidate records cursor N after the issue rather than the pre-issue cursor.
- SPEC_BUDGET parking is now gated on the speculative limiter. A physical-only limiter stops the pass without assigning a speculative negative-cache cursor.
- Added regressions for post-issue cursor attribution plus clearing/reissue when the current speculative budget drops below the cursor, and for the physical-only distinction.
- No commit, deployment, or unrelated product-file edits were performed.

## Evidence

- `python3 -m py_compile python/sglang/srt/managers/scheduler.py 3090-dev/test_ready_horizon_unit.py`: passed.
- `python3 -m compileall -q python/sglang/srt/managers/scheduler.py 3090-dev/test_ready_horizon_unit.py`: passed.
- `git diff --check`: passed.
- `git diff --name-only`: only the two authorized product/test files listed above.
- Focused test attempted: `python3 -m unittest 3090-dev/test_ready_horizon_unit.py -v`; blocked at import because `orjson` is unavailable. The plain `python` command is also unavailable.
- Formatter/typechecker checks were not available because `ruff`, `black`, `mypy`, `pyright`, and `pre-commit` are absent from the workspace.

## Followups

- Re-run `3090-dev/test_ready_horizon_unit.py` in the project dependency environment; this is required before runtime acceptance.
- Orchestrator may dispatch a fresh test-runner invocation for the blocked focused test evidence.

## Open issues

- Focused unit/runtime acceptance is unresolved solely because the current workspace lacks the package dependency `orjson` (and has no installed test runner/formatter/typechecker tooling).

## Communication

- Native parent event call succeeded for ENTRY and implementation phase events.
- Last event sent: `event=phase`, `status=pending`, `phase=implemented`, report path this file.
