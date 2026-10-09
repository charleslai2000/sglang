# HICACHE-NATIVE-CACHE-TELEMETRY-R2-20260918

- **工作标题：** HICACHE-NATIVE-CACHE-TELEMETRY-R2-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/HICACHE-NATIVE-CACHE-TELEMETRY-R2-20260918.md`：**
Scope:
- `python/sglang/srt/managers/scheduler.py`
- `python/sglang/srt/managers/schedule_policy.py`
- `python/sglang/srt/managers/schedule_batch.py`
- `python/sglang/srt/disaggregation/decode.py`
- `python/sglang/srt/managers/scheduler_components/output_streamer.py`
- `python/sglang/srt/entrypoints/openai/protocol.py`
- `python/sglang/srt/entrypoints/openai/serving_chat.py`

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** (ii) REPORTING GAP.; DONE

**`phase2-hicache-design/agents/HICACHE-NATIVE-CACHE-TELEMETRY-R2-20260918.md`：**
**Verdict: (ii) REPORTING GAP.**
The SGLang server DOES populate cached-token accounting internally:
1. `Req` objects have `cached_tokens`, `cached_tokens_device`, `cached_tokens_host`, `cached_tokens_storage` fields
2. Cache trees (tree_cache) track device/host/storage hits in `log_hit_tokens`, `log_device_hit_tokens`, etc.
3. `schedule_batch.py:2599` accumulates hits: `req.cached_tokens += new_cached`
4. `disaggregation/decode.py:2145` assigns decoder results to `req.cached_tokens`
5. `output_streamer.py` extracts and forwards these values in stream metadata
**The gap:** The internal accounting is ENABLED but the mapping from internal `Req.cached_tokens` to the OpenAI spec `usage.prompt_tokens_details.cached_tokens` is NOT unconditional—it's gated by `enable_cache_report` (server flag).
External callers reported 0% because:
- Default value of `enable_cache_report` was `False`
- External tool may not set this flag at server startup
- External tool may be reading `meta_info["cached_tokens"]` (stream metadata path) instead of `usage.prompt_tokens_details.cached_tokens` (OpenAI wire contract)

### 报告列出的产物/证据
- `phase2-hicache-design/agents/HICACHE-NATIVE-CACHE-TELEMETRY-R2-20260918.md`：`server_args.py:1391` previously had `enable_cache_report = False`

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/HICACHE-NATIVE-CACHE-TELEMETRY-R2-20260918.md` → `.memory/phase2-hicache-design/agents/HICACHE-NATIVE-CACHE-TELEMETRY-R2-20260918.md`; SHA256 `e03606a9894e99314e68eecad9993e02822727f264f31b7e96665d8f7f13aaa3`; source state `tracked`
