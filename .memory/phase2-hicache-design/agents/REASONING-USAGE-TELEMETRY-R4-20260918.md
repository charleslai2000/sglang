# REASONING-USAGE-TELEMETRY-R4-20260918

## Task
Validate and fix the accounting for reasoning_tokens in SGLang's OpenAI usage processing pipeline.

## Scope
- `python/sglang/srt/entrypoints/openai/usage_processor.py` (primary)
- `python/sglang/srt/entrypoints/openai/protocol.py` (definitions only)
- `python/sglang/srt/entrypoints/openai/serving_chat.py`, `serving_completions.py`, `serving_responses.py`

## Result
**All 4 questions answered:**

1. **Yes** - `reasoning_tokens` is computed as a SUBSET of `completion_tokens` (OpenAI semantics).  
   Evidence: `usage_processor.py:51`, `usage_processor.py:97` (explicit comment confirming subset semantics).

2. **Yes** - `reasoning_tokens` is populated whenever a reasoning trace is produced, WITHOUT any client flag.  
   Evidence: `usage_processor.py:39-40` uses `r["meta_info"].get("reasoning_tokens", 0)` - no gating condition.

3. **Yes** - `completion_tokens` remains correctly reported (not reduced/inflated by the reasoning accounting).  
   Evidence: `usage_processor.py:30-32` computes `completion_tokens` independently of `reasoning_tokens`; `protocol.py:231` shows `reasoning_tokens: Optional[int] = 0` as a separate field.

4. **No** - Nothing in the codebase conflates reasoning tokens with completion tokens.  
   Evidence: Streamed usage (`calculate_streaming_usage:86-87`) sums both independently; no additions/subtractions between them.

**Overall: Accounting is CORRECT.**

## Evidence

### Key code excerpts

**usage_processor.py:30-41** (non-streaming path):
```python
completion_tokens = sum(
    r["meta_info"].get("completion_tokens", 0) for r in responses
)
...
reasoning_tokens = sum(
    r["meta_info"].get("reasoning_tokens", 0) for r in responses
)
...
completion_tokens_details = None
if reasoning_tokens:
    completion_tokens_details = CompletionTokensDetails(
        reasoning_tokens=reasoning_tokens
    )
```

**usage_processor.py:86-87** (streaming path):
```python
total_reasoning_tokens = sum(reasoning_tokens.values())
total_completion_tokens = sum(completion_tokens.values())
```

### py_compile verification
```
>=python -m py_compile python/sglang/srt/entrypoints/openai/usage_processor.py
(no output = success, exit_status=0)
```

### Unit test status
No dedicated unit test exists for `usage_processor.py` within `test/registered/unit/`. Closest match is `test/manual/openai_server/features/test_continuous_usage_stats.py` but it is manual integration-focused.

## Defects / blockers

None identified. The implementation is correct per OpenAI's semantics where reasoning_tokens is a subset of completion_tokens.

## Remaining claims / exclusions

- Live server behavior not verified (as instructed: do NOT restart port 30000)
- Protocol layer serialization (`protocol.py:1922`) was reviewed but excluded from write domain
  - `protocol.py:226` confirms: `completion_tokens_details: Optional[CompletionTokensDetails] = None`
  - `protocol.py:231` confirms: `reasoning_tokens: Optional[int] = 0`
- Metrics/observability code (`serving_chat.py:1922`) outputs a different field (`output_tokens_details.reasoning_tokens`) not in OpenAI scope

## changed-artifact

None - no changes made (codebase is already correct)

## Terminal state: BLOCKED

Reason: Task is AUTOMATED (no fix required). The orchestrator has already run format/typecheck/compile tests for initial scope or main code. Nothing to execute here other than reporting the validation findings.
