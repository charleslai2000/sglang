# M2-THINKING-VERIFY-20260918

- **工作标题：** M2-THINKING-VERIFY-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/M2-THINKING-VERIFY-20260918.md`：**
- **Date:** 2026-09-18
- **Role:** `debugger-deep` (non-worker; read-only wrt server and product tree)
- **Target:** M2 = `/data/models/omnicoder-9b-gptq-int4` served on `127.0.0.1:30000` (SGLang)
- **Prior artifact under review:** `.memory/phase2-hicache-design/agents/M2-THINKING-EFFORT-20260918.md`
- **Terminal verdict:** **DONE**
---

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/agents/M2-THINKING-VERIFY-20260918.md`：**
- The prior agent's **per-prompt raw numbers are real and match its raw JSON exactly** (all 5 base prompts, 0 mismatches). Its raw evidence files all exist.
- The prior agent's **interpretation is wrong on three material points**:
  1. **Token double-count** — it added `reasoning_tokens` to `completion_tokens`. `reasoning_tokens` is a **SUBSET** of `completion_tokens`. Honest total is `prompt_tokens + completion_tokens`; this is confirmed by every one of 25 raw responses and by SGLang source.
  2. **"No API control exists" is FALSE.** The correct path is `chat_template_kwargs: {"enable_thinking": false}`, which **genuinely disables thinking** (`reasoning_tokens = 0`, `reasoning_content = null`), and `reasoning_effort: "none"` does the same. The prior agent almost certainly sent `enable_thinking` at the top level (where SGLang ignores it).
  3. **Coding is not "efficient."** With a constrained prompt ("Output only the code") M2 over-deliberates unboundedly: at `max_tokens` 2048 **and** 8192, `completion_tokens == reasoning_tokens == limit`, `content == ""`, `finish_reason == "length"`. The prior agent's low coding ratio came from *unconstrained* prompts (reproduced here), where the model happened to choose a short answer.
- **M2 is systematically overthinking on every class tested**, worst on trivial/extraction/math where **~98% of generated tokens are reasoning**.
- **Control is real and production-usable**: `chat_template_kwargs.enable_thinking=false` yields correct answers with **94–99% fewer completion tokens** and ~7–30× less latency.
---


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/M2-THINKING-VERIFY-20260918.md` → `.memory/phase2-hicache-design/agents/M2-THINKING-VERIFY-20260918.md`; SHA256 `eabc639c7fa5d1817c92a9057effcda5afe5863b08833ae13ff99ab305bad867`; source state `tracked`
