# RESULT-EXPERT-BRIEFING-REVISE-20260918

- **工作标题：** RESULT-EXPERT-BRIEFING-REVISE-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/RESULT-EXPERT-BRIEFING-REVISE-20260918.md`：**
**Task:** Documentation revision to hand revised briefing to EXTERNAL experts
**Scope:** Revise ONE existing document in-place to fix documented defects and incorporate graded-tiers audit findings
**Constraints:** Do NOT edit server/product code/tests/config/git/ledger/memory files; write only target document plus result artifact
---

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/agents/RESULT-EXPERT-BRIEFING-REVISE-20260918.md`：**
The document `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/REASONING-CONTROL-EXPERT-BRIEFING-20260918.md` was revised in-place and replaced by the authored document:
`/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/EXPERT-BRIEFING-REVISE-20260918.md`
**What changed:**
1. **Sanitization violation fixed:** All internal absolute paths have been removed/replaced with neutral placeholders. The sanitized list included paths under `/data/models/`, `/opt/sglang/`, `/tmp/opencode/`, hostnames like `127.0.0.1`, PID values, run-ids, and `.memory/` paths. Public upstream file names (`protocol.py`, `serving_chat.py`) and API surfaces (`/v1/chat/completions`, `/openapi.json`) are retained.
2. **Corrupted sentence fixed:** The previous garbled line mixing `""""`/`</think>` token markers and `<thinking>` text has been rewritten into clean, precise prose that plainly states the cause:
   > "With the thinking toggle disabled via `enable_thinking=false`, the template prefills a closed empty thinking block. With any other value (including `"none"` being translated to `enable_thinking=false`), the template emits an open thinking block."
3. **Graded-tiers audit folded in:** Added a dedicated Section 4 declaring the full advertised gradation (string tiers + float) and the measured reality that every non-`none` tier is byte-identical to baseline.…（节选；见来源报告）


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/RESULT-EXPERT-BRIEFING-REVISE-20260918.md` → `.memory/phase2-hicache-design/agents/RESULT-EXPERT-BRIEFING-REVISE-20260918.md`; SHA256 `6f6d0282b30602b2023fef667a6b7497d26b665e22df8149bf1f0465f46c0af2`; source state `tracked`
