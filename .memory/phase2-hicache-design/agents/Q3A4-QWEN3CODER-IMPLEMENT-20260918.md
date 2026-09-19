# Q3A4-QWEN3CODER-IMPLEMENT-20260918

Status: DONE
Terminal state: DONE

## Task

Implement the already-adjudicated `qwen3_coder` detector fix (defect #6 on the production path),
per `QWEN3CODER-SCOPE-ADJUDICATE-20260918.md` (normative rules R3/R4/R5 + acceptance table E4) and
`AUDIT-QWEN3CODER-ADJUDICATION-20260918.md` (verdict: implementable as-is; 5 defects CONFIRMED;
single-file write domain sufficient; corrections C1/C2).

## Scope

Write domain (exactly two files):
1. `python/sglang/srt/function_call/qwen3_coder_detector.py`
2. existing `TestQwen3CoderDetector` in `test/registered/unit/function_call/test_function_call_parser.py`

Five defects: (i) duplicate `</function>` extra `}`; (ii) missing `</function>` unclosed JSON;
(iii) `-1` from orphan fragments; (iv) inherited no-op `finish()`; (v) name extraction swallows body.
Single EOS rule = delay-commit; `finish()` releases uncommitted held text as `normal_text`.
Corrections: C1 (EOS=return-to-content reconciled vs P1 §3.2 and §4 rows 6/7); C2 (row 3b/13 marked
as owner-flippable default).

Out of scope / not touched: `base_format_detector.py`, `function_call_parser.py`, serving/template/
sampling/quant files, `/opt/**`, `/data/**`, new files, git mutation. CPU only.

## Result

DONE. Single-file detector rewrite plus targeted tests; all five defects fixed and all 13 E4 rows
behaviourally verified.

Implementation (detector):
- `parse_streaming_increment` replaced by a delay-commit scanner. An enclosed call is held until its
  `</tool_call>`; a bare `<function=...>` is held until `</function>`. On commit, exactly one
  `ToolCallItem` is emitted with `tool_index = ++self.current_tool_id`, a well-formed `name`, and
  `parameters` = one complete JSON object. Malformed/orphan/duplicate/partial fragments never become
  calls; independently framed non-whitespace bytes around a body are released as `normal_text`
  (no silent drop).
- Added `_is_well_formed_name` (non-empty, no `<`, `>`, or whitespace), `_parse_parameter_values`
  (value terminators `</parameter>`, next `<parameter=`, `</function>`, or body end; strips one
  leading/trailing `\n`), and `_parse_committed_block`.
- `detect_and_parse` non-stream path now skips malformed/empty names (E4 rows 5/9); `func_body`
  None-guard added.
- `finish(self, tools)` override releases `_buffer[parsed_pos:]` as `normal_text` and resets buffer
  state; no call repair.
- Removed dead streaming state (`json_started`, `current_tool_param_count`, `is_inside_tool_call`,
  `current_func_name`) that only the replaced algorithm used.

Tests: 12 new methods in `TestQwen3CoderDetector` (+ shared `_stream` helper) covering E4 rows 1–13,
including name-withholding, EOS content release, no-negative-index, duplicate `</function>`,
unclosed envelope, empty/malformed name, stray parameter, missing `</function>` (row 13), two calls,
undeclared-name pass-through, and non-stream rows 5/9.

C1 documentation (per audit): the EOS content-release IS the integrated rule under delay-commit.
P1 §3.2 "do not degrade a decoded call to plain text" and P1 §4's "rows 6/7 usable-empty" are
superseded for framing-incomplete blocks by the later, more specific owner-relayed expert rule
(complete framing required; EOS unclosed `<tool_call>` → ordinary assistant content). No call is
silently dropped: held bytes are surfaced as visible `normal_text`; unknown names still pass through
verbatim (I6). No JSON repair is performed.

C2 documentation (per audit): E4 row 13 (closed block, missing inner `</function>`, params
terminated) is implemented as the owner-flagged reversible default = COMMIT a complete JSON object
at `</tool_call>`. If the owner prefers the content alternative, flip
`_parse_committed_block`'s missing-`</function>` handling; no other rule or file changes.

## Evidence

### Base sha

- before: `92eeaeaf02ac1c1e966a8b9bbd4393141353ca9177265044fe12e250c0e38089`
  (verified pristine at implementation start; `git show HEAD:` equals this)
- after: `848e0690cb80719e70c7ceedb7c1eb253c879d39a1b7be1cb85645f861a9d151`
- test file before: `bb8363f554fb9eebc2dd92b50cde2745ea0892fb069cce2d7cdf88d2c03fbceb`
- test file after: `7e831bf4807811128d76d51251bf12353c980a77c59aa1ce75b2c2b9f3637bfc`
- `base_format_detector.py` / `function_call_parser.py`: `git diff --name-only` empty (untouched).

### Diff

`git diff --numstat` (scoped):
```
212  204  python/sglang/srt/function_call/qwen3_coder_detector.py
187    0  test/registered/unit/function_call/test_function_call_parser.py
```
`git status --short` (scoped): both files ` M`; no new files, no commits.

### Commands + verbatim results

Interpreter `/opt/sglang/local-prod-v1/env/bin/python`, `CUDA_VISIBLE_DEVICES=999`,
`PYTHONDONTWRITEBYTECODE=1`.

1. Compile both files:
   `/opt/sglang/local-prod-v1/env/bin/python -m py_compile <both>` → `COMPILE_OK`.
2. `pytest test/registered/unit/function_call/test_function_call_parser.py -q`
   → `256 passed, 1 warning, 4 subtests passed in 27.55s` (baseline was 243 passed; +13 new tests).
3. `pytest test/registered/unit/function_call/test_function_call_parser.py::TestQwen3CoderDetector -q`
   → `30 passed, 1 warning in 9.67s`.
4. `pytest test/registered/unit/function_call/ -q` (whole directory)
   → `532 passed, 17 warnings, 18 subtests passed in 43.45s`.
5. Canary `pytest test/registered/unit/entrypoints/openai/test_serving_responses_stream.py -q`
   → `8 passed, 3 warnings in 16.83s` (file baseline includes the required
   `MultiToolCallStreamingOrderTestCase`: 3 passed).
6. `pytest ...::MultiToolCallStreamingOrderTestCase -q` → `3 passed, 3 warnings in 12.86s`.
7. Standalone CPU probe `/tmp/opencode/qwen3coder-impl-20260918/probe.py` asserts all 13 E4 rows
   plus non-stream rows 5/9 → `ALL PROBE ASSERTIONS PASSED`. Measured per-row outcome matches the
   E4 "After" column, including: r1 commit idx0 `{"command":"ls -la"}`; r2 exactly one `}`; r3 no
   call + content; r4 no call/content; r5 no malformed-name call; r6/r7 no call + content; r8 first
   call commits + stray fragment no call; r9 no call; r10 `cat` passthrough idx0; r11 content; r12
   idx0/idx1; r13 commit `{"command":"ls -la"}`.
8. Edge probe (plain text, text+call+text, partial tag at EOS, stray `</function>`, whitespace
   separators between two calls) → `EDGE OK`; no spurious calls, no dropped content.

Formatting: `black`/`ruff`/`isort` are not installed in the offline environment (verified
`ModuleNotFoundError`), so no formatter run was possible; edits were kept inside the repo's 88-col
black style and verified clean of trailing whitespace and with a final newline.

### Defect closure map

| # | Defect | Fix | Evidence |
|---|---|---|---|
| i | duplicate `</function>` extra `}` | single object built at commit; close tokens outside the body are released as content | test dup + probe r2 |
| ii | missing `</function>` unclosed JSON | no partial JSON ever emitted; `finish()` releases as content | test name-withheld + probe r3/r6/r7/r11 |
| iii | `-1` orphan fragments | index assigned only at commit via `>= 0` monotonic counter | test orphan + test two-calls `[0,1]` |
| iv | inherited no-op `finish()` | override releases held bytes as `normal_text` | tests + probe |
| v | name swallows body | strict `_is_well_formed_name` in both paths | malformed/empty tests (stream + non-stream) |

## Defects / blockers

None. No production-path blocker found; the canary passes unchanged.

## Remaining claims / exclusions

- ESTABLISHED: the two authorized files changed; detector-only scope sufficient; base/parser untouched;
  `py_compile` clean; targeted + full-directory unit tests and the streaming-order canary pass;
  all 13 E4 rows behaviourally verified on CPU.
- NOT CLAIMED: independent acceptance (this is implementation evidence, not tester/reviewer
  acceptance); that the named contract documents support the rules (absent per audit); any `/opt`
  landing/pin update/restart; any GPU or service operation; that model faults are eliminated.
- C1/C2 recorded as specification documentation above, not code changes.
- Follow-on for the orchestrator (not performed here): land the repo fix into the frozen tree and
  re-pin the four surfaces (separate authorized procedure); owner ratification of C2 row 13 default.
- Unrelated pre-existing workspace changes (`ledger.md`, `gguf_native.py`, deleted
  `gate_common.py`, untracked files) were left untouched.

## Terminal state: DONE
