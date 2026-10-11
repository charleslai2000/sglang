# FIX-PROVIDER-CONTEXT-METADATA-20260918

- **工作标题：** FIX-PROVIDER-CONTEXT-METADATA-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/FIX-PROVIDER-CONTEXT-METADATA-20260918.md`：**
Owner-authorized bounded defect fix: client/provider model metadata declared a context window of
400000 tokens, causing 8 deterministic HTTP 400 responses. Correct the declaration to exactly
131072 and eliminate the incorrect 400000 declaration so it cannot be used again. Server side must
not be changed (must remain at 128K / context_length=131072). No restarts, no GPU, no git mutation.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/FIX-PROVIDER-CONTEXT-METADATA-20260918.md`：**
The incorrect declaration was **`"context": 400000` inside
`~/.config/opencode/opencode.json`, under `provider.opencodex.models.*.limit`** — an OpenCode
client/provider model-metadata block (tokens; sibling `"output"` is also in tokens). It is the
local OpenCodex provider (`baseURL http://192.168.1.203:3456/v1`) used by all agent tiers.
All 8 occurrences now read exactly `"context": 131072`, and the stale 400000 copies in the same
config tree's backup files were changed consistently (no 400000 remains anywhere in
`~/.config/opencode/` JSON):
| File (role) | BEFORE | AFTER |
|---|---|---|
| `~/.config/opencode/opencode.json` (ACTIVE client/provider config) | 8× `"context": 400000` (lines 75, 97, 119, 163, 182, 201, 220, 239) | 8× `"context": 131072` at same lines |
| `~/.config/opencode/opencode.json.bak-before-gpt55-20260916T112940Z` (stale backup) | 3× at 74, 96, 118 | 3× `131072` |
| `~/.config/opencode/.bak-before-low-variant-20260917-203524/opencode.json` (stale backup) | 8× at 74, 96, 118, 162, 181, 200, 219, 238 | 8× `131072` |
| `~/.config/opencode/.bak-before-tier-rebind-20260917-202809/opencode.json` (stale backup) | 3× at 74, 96, 118 | 3× `131072` |
| `~/.config/opencode/.bak-before-topmodel-20260917-204306/opencode.json` (stale backup) | 8× at 74, 96, 118, 162, 181, 200, 219, 238 | 8× `131072` |


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/FIX-PROVIDER-CONTEXT-METADATA-20260918.md` → `.memory/phase2-hicache-design/agents/FIX-PROVIDER-CONTEXT-METADATA-20260918.md`; SHA256 `87f5ffe45c1288d316db4fb9220e0be3b1cb9c6ed8f63046a71ae1e6908220c0`; source state `tracked`
