# QQUESTION-HALLUCINATION-HUNT-20260918

- **工作标题：** QQUESTION-HALLUCINATION-HUNT-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/QQUESTION-HALLUCINATION-HUNT-20260918.md`：**
Owner question: does the harness contain handling for TOOL HALLUCINATION, specifically for a
hallucinated tool named `qquestion`? A repo-only grep for the literal string returned nothing;
find the real runtime evidence, and determine what the production `qwen3_coder` tool-call parser
does when the model emits a call to an undeclared tool.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/QQUESTION-HALLUCINATION-HUNT-20260918.md`：**
**(1) YES — `qquestion` IS REAL and it was EMITTED by the served model.**
The production SGLang server for `/data/models/qwen35-9b-w4a16` (launched with
`--tool-call-parser qwen3_coder`) logged, at 21:39:43 on 2026-09-17:
```
[2026-09-17 21:39:43] Tool 'qquestion' is not defined in the tools list.
```
That message is emitted only by `qwen3_coder_detector.py:91`, i.e. it is proof that the model
actually produced a tool call whose function name was `qquestion`, and that the `qwen3_coder`
detector saw it. This settles the owner's question: `qquestion` is not a typo in the question;
it is a hallucinated tool name the model emitted at runtime.
Additionally the same server logged a second undeclared-name event:
`[2026-09-17 21:57:55] Tool 'None' is not defined in the tools list.` — the name was the literal
Python `None` (empty/nulled `<function=...>` name), so this is a second, distinct malformed-name
event, not a `qquestion` recurrence.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/QQUESTION-HALLUCINATION-HUNT-20260918.md` → `.memory/phase2-hicache-design/agents/QQUESTION-HALLUCINATION-HUNT-20260918.md`; SHA256 `73f1a18e13329cdd327e21aa219d403c5b083d79685f6bd57348920e2c882a62`; source state `tracked`
