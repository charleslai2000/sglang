# SGLANG-REASONING-CONTROL-AUDIT-20260918

- **工作标题：** SGLANG-REASONING-CONTROL-AUDIT-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/SGLANG-REASONING-CONTROL-AUDIT-20260918.md`：**
**Task:** Independent, read-only audit for the owner: do the externally-exposed reasoning-control
parameters (`reasoning_effort`, `enable_thinking`, `chat_template_kwargs`) actually take effect,
and does the same conclusion apply to the previous Qwen3.5 arm (M1)?
**Auditor role:** `debugger-deep` (diagnostic/investigative). Read-only w.r.t. server, product
source, tests, config. No restarts, no signals, no port/state changes. Only new scratch files
written under `/tmp/opencode/SGLANG-REASONING-CONTROL-20260918/` plus this artifact.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/agents/SGLANG-REASONING-CONTROL-AUDIT-20260918.md`：**
The prior conclusion "no API control exists" was **wrong**. Both M2 and M1 use the **same,
byte-identical** Qwen3.5 chat template that implements exactly one effective toggle:
**`enable_thinking`** (strict boolean `false` disables reasoning; anything else, including
unset, enables it). The correct placement is **inside `chat_template_kwargs`** —
`"chat_template_kwargs": {"enable_thinking": false}` — which was proven effective both at the
tokenizer/render level and end-to-end (`reasoning_tokens` 174 → 0, `completion_tokens` 177 → 2,
`reasoning_content: null`, `content: "4"`). Top-level `enable_thinking` is **silently dropped by
pydantic** (`ChatCompletionRequest` has no `extra="allow"`), which explains the prior agent's
"ignored" observation. Top-level `reasoning_effort` works **only for `"none"`** (it is translated
into `chat_template_kwargs.enable_thinking=false`); all other effort tiers (`minimal/low/medium/
high/xhigh/max`, floats) are **inert** because the template contains no effort-tier variable.
`stop` sequences are **truncation-only**, not a control. For M1, the static evidence is
**byte-identical** to M2 (same template hash, same detected toggle, same parser), so the same
control surface is expected; **runtime verification on M1 still requires a separate GPU window**


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/SGLANG-REASONING-CONTROL-AUDIT-20260918.md` → `.memory/phase2-hicache-design/agents/SGLANG-REASONING-CONTROL-AUDIT-20260918.md`; SHA256 `a25056ce8285cf59f29251c6f2340edb722ff37e3b36d38bf863cacee8a50d8c`; source state `tracked`
