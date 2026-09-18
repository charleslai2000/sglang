# SGLang Reasoning Usage Telemetry Implementation

## Task
Make the SGLang server report reasoning tokens natively and authoritatively via OpenAI-compatible `usage.completion_tokens_details.reasoning_tokens`, eliminating client-side reconstruction heuristics and fixing the bug where `reasoning_tokens` are conflated with `completion_tokens`.

## Scope
Read and modify:
- `python/sglang/srt/managers/usage_processor.py`
- `python/sglang/srt/entrypoints/openai/protocol.py`
- `python/sglang/srt/entrypoints/openai/serving_chat.py`
- `python/sglang/srt/managers/io_struct.py`
- `python/sglang/srt/managers/tokenizer_manager.py`
- Tests under `test/registered/unit/`

Forbidden: `/opt/**`, `/data/**`, git commits, running server/port 3090, weights/training, `.memory/**` (except this artifact), `python/sglang/srt/metrics/**`, `mem_cache/**`.

## Evidence

<tool_call>
<function=bash>