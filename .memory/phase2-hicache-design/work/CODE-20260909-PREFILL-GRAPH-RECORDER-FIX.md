ENTRY: ACCEPT

# CODE-20260909-PREFILL-GRAPH-RECORDER-FIX

Task: `D3060-CODER-104`, orchestration epoch `2026-09-09`
Role: coder
Invocation status: done
Branch: `3060-12g-qwen35-4b`
Commit: `277dd61100` (`fix: keep Qwen3.5 recorder context trace-safe`)

## Summary

Unblocked the Qwen3.5 layer loop's no-op/non-recording expert-distribution
recorder path for PyTorch Dynamo tracing. The loop now uses `nullcontext()` when
the global recorder is not recording, while the active recording path continues
to use `with_current_layer(layer_idx)` unchanged.

## Changed files

- `python/sglang/srt/models/qwen3_5.py`
  - Imported `nullcontext`.
  - Selected the layer context from `recorder.recording`; no-op/non-recording
    execution uses the trace-safe null context.
- `test/registered/core/test_qwen35_prefill_graph_recorder.py`
  - Added a focused AST regression test asserting the conditional context
    selection and preserving the real recorder call.

The commit contains exactly these two files. Existing untracked governance and
storage artifacts in the worktree were preserved and not staged.

## Verification evidence

- `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile python/sglang/srt/models/qwen3_5.py test/registered/core/test_qwen35_prefill_graph_recorder.py` — passed.
- Direct invocation of the focused static regression function — passed
  (`static regression: PASS`).
- `git diff --check` before commit — passed.
- `git show --format= --check HEAD` after commit — passed.
- Final commit scope: `git show --stat HEAD` reports the two authorized files;
  final branch is `3060-12g-qwen35-4b` at `277dd61100`.

## Verification limitation

- `python3 -m pytest -q test/registered/core/test_qwen35_prefill_graph_recorder.py`
  could not run because `/usr/bin/python3` has no `pytest` module.
- No remote CUDA runtime, server launch, or 3090 branch operation was run.

## Followups

- Run the focused pytest test in the approved SGLang test environment.
- Re-run the authorized remote tc_piecewise CUDA Graph capture smoke separately.

## Open issues

- Local pytest execution remains unavailable; the dependency-free static test
  and source compilation passed.
- Remote runtime acceptance remains with the tester/operations owner.

status: done
