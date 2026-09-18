# Q3A3-QWEN3CODER-IMPLEMENT-20260918

Status: WORKING
Terminal state: WORKING
Role: coder (private implementation specialist; repo-only, CPU-only)

## Task

Implement the adjudicated `qwen3_coder` detector fix in the repo (branch `3090-24g-opt`), exactly two files:
`python/sglang/srt/function_call/qwen3_coder_detector.py` and the existing `TestQwen3CoderDetector` class in
`test/registered/unit/function_call/test_function_call_parser.py`. Fix the five defects under the delay-commit
framing / single-EOS rules from `QWEN3CODER-SCOPE-ADJUDICATE-20260918.md`, with the dispatch REQUIRED BEHAVIOUR
and acceptance table as the governing test spec. No commits; no `/opt`; no GPU; no service ops.

## Scope

- IN: the two files above; CPU-only unit runs; `py_compile`.
- OUT: `base_format_detector.py`, `function_call_parser.py`, serving/template/sampling/quant files, new files
  under `python/`, `/opt/**`, `/data/**`, GPU, services, commits, other agents' artifacts.

## Result

PENDING — implementation in progress.

## Evidence

PENDING.

## Defects / blockers

PENDING.

## Remaining claims / exclusions

PENDING.

## Terminal state: WORKING
