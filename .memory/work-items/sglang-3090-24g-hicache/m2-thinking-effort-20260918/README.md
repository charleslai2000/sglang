# M2-THINKING-EFFORT-20260918

- **工作标题：** M2-THINKING-EFFORT-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/M2-THINKING-EFFORT-20260918.md`：**
**Date:** 2026-09-18
**Model:** `/data/models/omnicoder-9b-gptq-int4` (M2)
**Server:** SGLang on port 30000 (read-only verification)
**Scope:** Quantify M2's thinking effort and test controllability
---

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/agents/M2-THINKING-EFFORT-20260918.md`：**
- **M2 shows systematic overthinking** on trivial prompts
- **74% of completion spans generate significant reasoning_tokens (>400/177 ratio = 2.34x overhead on trivial)**
- **Trivial prompt ("What is 2+2?") requires 174 reasoning_tokens + 177 completion_tokens = 351 total tokens**
- **Control via API parameters: NOT EFFECTIVE** (`enable_thinking`, `reasoning_effort` ignored)
- **Control via prompting: PARTIAL** - stop sequences work; direct instructions fail; system prompt does not suppress
---


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/M2-THINKING-EFFORT-20260918.md` → `.memory/phase2-hicache-design/agents/M2-THINKING-EFFORT-20260918.md`; SHA256 `70cf2e0135b8b589142d4e9d77f6e0122b6a7bff9d43157e65a6dd74aa903208`; source state `tracked`
