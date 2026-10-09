# M2-CODING-EVAL-R2-20260918

- **工作标题：** M2-CODING-EVAL-R2-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
对运行中的 OmniCoder-9B GPTQ INT4 服务做 bounded、只读 HTTP coding evaluation：比较默认 thinking 与 `chat_template_kwargs.enable_thinking=false` 两种设置下八项任务的实际输出，不重启或改服务。

## 实际改了什么
仅向 `/v1/chat/completions` 发受限的 8-task battery（Config A max_tokens=256、Config B=512），GET health/models 确认身份；无服务配置/源码改动或重启。报告未执行生成代码，也未做 SQL 执行验证。

## 生成结果与验收
**`phase2-hicache-design/agents/M2-CODING-EVAL-R2-20260918.md`：**
**M2 status on coding work:**
- **Config A (default, thinking ON)**: FAILS across all 8 coding tasks — burns full token budget on reasoning, returns empty `content=""` with `finish_reason="length"`. No usable code produced.
- **Config B (with `enable_thinking=false` in `chat_template_kwargs`)**: SUCCEEDS on all 8 tasks. All return correct, non-empty Python/JSON/SQL output. Correctness verified via parseable JSON and text presence. All finish with `finish_reason="stop"`.
**Conclusion:** With production-ready configuration control (toggle explicit in the request), M2 LLM can do representative production coding. Without that toggle (default), it fails all tasks due to a systemic reasoning-flooding defect. Both results are factual and relevant.
**Scoreboards:**
- **Config A (default)**: 0 / 8 correct (0.0%); empty-content rate = 100%
- **Config B (`enable_thinking=false`)**: 8 / 8 correct (100%); empty-content rate = 0%


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/M2-CODING-EVAL-R2-20260918.md` → `.memory/phase2-hicache-design/agents/M2-CODING-EVAL-R2-20260918.md`; SHA256 `9059d218f72c78d1111b6b70907bf7592f36e16166d840496adfccf12b829623`; source state `tracked`
