# CODER3060-RH-MATCH-EMIT-ROBUST-20260910

status: done
task_id: T3060-RH-MATCH-EMIT-ROBUST-20260910
orchestration_epoch: 20260910-rh-ab60
role: coder
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
base_revision: 9213ee01d90ba3925e7fe928e80cc41354ee4fff
commit: 03a170ef4f

## Artifacts

- Product commit: `03a170ef4f` (`fix(hicache): harden RH match telemetry emission`).
- Changed product files, exactly within authorization:
  - `python/sglang/srt/managers/scheduler.py`
  - `3090-dev/test_rh_contract_dependency_free.py`
- This report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODER3060-RH-MATCH-EMIT-ROBUST-20260910.md`.

## Change manifest

- `Scheduler._emit_rh_match_prepare`: changed only the observational log construction from deferred `%` formatting to one pre-rendered message. Nullable join fields continue to use the existing `field()` normalization and the event schema, field order, IDs, and numeric values are preserved. A missing `retraction_count` value is rendered as the existing numeric default `0`; no RH policy/state, match, issue, admission, Mamba, storage, or allocator path was changed.
- `RHContractDependencyFreeTests.test_match_preparation_emits_with_nullable_fields`: added an eager-formatting logger regression with null enqueue/session/attempt/duration fields and a missing retraction count; asserts one `rh_match_prepare.v1` record and explicit `null` encoding.

## Evidence

- `python3 -m unittest 3090-dev/test_rh_contract_dependency_free.py 3090-dev/test_prefetch_gate_skip_regression.py`: **19/19 passed**.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile python/sglang/srt/managers/scheduler.py 3090-dev/test_rh_contract_dependency_free.py`: passed.
- Source compilation via `compile(source, ...)`: passed.
- `git diff --check` and cached diff check: passed.
- Deterministic AST check: `_emit_rh_match_prepare` has one `logger.info` argument and no `%d` directive; required schema/join fields remain present.
- Commit scope check: commit contains exactly the two authorized files.

## Validation limitations

- `ruff`, `black`, `pre-commit`, `mypy`, and `pyright` are unavailable in this workspace, so their commands could not run.
- No runtime deployment, remote process control, storage, Mamba, or 3090 code changes were performed.

## Summary

RH preparation telemetry now reaches the logger as a fully rendered string, so `%d`/`None` interpolation cannot raise inside the broad observational catch and suppress the event. Nullable contract fields remain explicit `null`; RH policy/state semantics are unchanged.

## Followups

- Independent tester/reviewer acceptance remains a separate follow-on dispatch.

## Open issues

- Formatter/typecheck evidence is unavailable because the corresponding tools are not installed.
