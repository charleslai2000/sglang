# REASONING-EFFORT-TIERS-AUDIT-20260918

- **工作标题：** REASONING-EFFORT-TIERS-AUDIT-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/REASONING-EFFORT-TIERS-AUDIT-20260918.md`：**
- **Task:** Focused re-review of the **graded `reasoning_effort` tiers (分档)** advertised by the served SGLang deployment — does a real grading mechanism exist anywhere, why do the advertised tiers not take effect, and what is the smallest repair direction?
- **Role:** `debugger-deep` (non-worker; read-only wrt server and product code; bounded read-only requests only)
- **Target (live):** `/data/models/omnicoder-9b-gptq-int4` served by SGLang on `127.0.0.1:30000` (M2, Qwen3.5-derived, `model_type=qwen3_5`, `architectures=[Qwen3_5ForConditionalGeneration]`)
- **Served tree:** `/opt/sglang/local-prod-v1.2.1-candidate` (frozen, read-only)
- **Prior baseline built upon (not redone):** `.memory/phase2-hicache-design/agents/M2-THINKING-VERIFY-20260918.md`, `.memory/phase2-hicache-design/agents/SGLANG-REASONING-CONTROL-AUDIT-20260918.md`
- **Result artifact path (this file):** `.memory/phase2-hicache-design/agents/REASONING-EFFORT-TIERS-AUDIT-20260918.md`
- **Terminal state: DONE**
---

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/REASONING-EFFORT-TIERS-AUDIT-20260918.md`：**
**A real graded-effort mechanism EXISTS in the served code — but only for OTHER model families, and it is selected by the chat template / chat-encoding spec, not by the API surface.** The served `protocol.py` advertises `reasoning_effort` as string tiers plus a fine-grained float `[0.0, 0.99]` **unconditionally for every model** (`protocol.py:793-808, 869-881`, and served `/openapi.json`). For the served Qwen3.5 model, the value is correctly parsed, normalized, and **forwarded into `apply_chat_template`**, but the model's template (`chat_template.jinja:149`) references **only `enable_thinking`** and never `reasoning_effort`, `thinking_budget`, `low_effort`, or any graded variable. Detected config is `ReasoningToggleConfig(toggle_param='enable_thinking', default_enabled=True, special_case=None, effort_kwarg=None)`, so the one generic graded branch (`serving_chat.py:1364-1373`) is dead. **Runtime result: every advertised tier (`minimal/low/medium/high/xhigh/max`) and every float (`0.0`, `0.25`, `0.99`) is byte-for-byte identical to baseline** (same full `content` SHA, same full `reasoning_content` SHA, same 177 completion / 174 reasoning tokens), and the render-level `/v1/tokenize` prefill is token-identical. Only `"none"` changes anything, by collapsing to the existing on/off toggle. A genuine length-budget mechanism (`max_thinking_tokens` → `custom_params.thinking_budget` → `ThinkingBudgetLogitProcessor`) also exists in-tree, but it is **not exposed on the chat request, not connected to `reasoning_effort`, disabled on this server (`--enable-strict-thinking` absent), and its…（节选；见来源报告）

### 报告列出的产物/证据
- `phase2-hicache-design/agents/REASONING-EFFORT-TIERS-AUDIT-20260918.md`：- **Harness/logs:** `probe.py`, `probe.out`, `compare.py`, `compare.out`, `render_probe.py`, `render_probe.out`, `detection_probe.out`
- **Consolidated:** `completions_summary.json` (21 requests with request bodies), `tokenize_summary.json` (11 render probes)
- **Service (read-only GET):** `ev_health.txt`, `ev_models.json`, `ev_server_info.json`, `ev_openapi.json`
- **Raw graded-tier responses:** `raw/cc_00_baseline_P1.json`, `raw/cc_effort_{none,minimal,low,medium,high,xhigh,max}_P1.json`, `raw/cc_effort_float_{0_0,0_25,0_99}_P1.json`, `raw/cc_positive_ctk_false_P1.json`, `raw/cc_00_baseline_P5.json`, `raw/cc_effort_high_P5.json`, `raw/cc_positive_ctk_false_P5.json`…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/REASONING-EFFORT-TIERS-AUDIT-20260918.md` → `.memory/phase2-hicache-design/agents/REASONING-EFFORT-TIERS-AUDIT-20260918.md`; SHA256 `ec37ed79cc41155e1e143b1e609e4d5927211b659f98267fcd7649cd99566422`; source state `tracked`
