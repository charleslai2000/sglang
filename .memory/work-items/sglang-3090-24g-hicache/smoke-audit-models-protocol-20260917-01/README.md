# SMOKE-AUDIT-MODELS-PROTOCOL-20260917-01

- **工作标题：** SMOKE-AUDIT-MODELS-PROTOCOL-20260917-01
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`protocol-subagent-smoke-20260917/agents/SMOKE-AUDIT-MODELS-PROTOCOL-20260917-01.md`：**
Audit of the orchestrator's dispatch behavior for the `protocol-subagent-smoke-20260917` run, requested
as a dedicated audit deliverable. Three questions, each requiring an explicit verdict:
- **Q1** Model & variant accuracy for each dispatched subagent, including whether any dispatch was
  silently downgraded or served by a fallback.
- **Q2** Communication integrity of orchestrator→child packets and child→orchestrator returns,
  including re-assessment of accepted defects I7 and I8.
- **Q3** `.memory` artifact protocol compliance (exact path, WORKING→terminal lifecycle,
  one-writer-per-artifact, orchestrator sole writer of `ledger.md`, no cross-child amendment,
  no missing/misnamed/non-canonical artifacts).
Claim under test (orchestrator's, treated as a claim, not as truth):
> "The orchestrator's task-dispatch tool exposes only `subagent_type`, `description`, `prompt`,
> `task_id`, and `background`. It exposes NO model parameter and NO variant parameter. Therefore the
> orchestrator never selected a model or a variant; per-agent model/variant selection is performed by
> the runtime's agent configuration, not by the orchestrator."

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`protocol-subagent-smoke-20260917/agents/SMOKE-AUDIT-MODELS-PROTOCOL-20260917-01.md`：**
Overall: no blocker; Q1 clean, Q2 partially defective (three non-blocking communication defects, all
attributable to the orchestrator's packet wording, one of them already accepted as I8), Q3 compliant
with two recorded observations.

### 报告列出的产物/证据
- `protocol-subagent-smoke-20260917/agents/SMOKE-AUDIT-MODELS-PROTOCOL-20260917-01.md`：Method/commands used (all read-only against the authorized set; representative outputs quoted):
- **E1 — config mapping.** `read /home/ubuntu/.config/opencode/opencode.json` (373 lines); agent
  blocks at the line numbers cited in the Q1 table; `agents/*.md` frontmatter lines 5–6 for all 12
  agree. Config mtimes: `opencode.json` 2026-09-17 20:43:11.046Z; agent .md files 20:28/20:35;
  `date -d @1789677979` = 2026-09-17 20:46:19 UTC (first dispatch). Snapshot diffs:
  `.bak-before-tier-rebind-20260917-202809` (agent model aliases), `.bak-before-low-variant-...`
  (3 variant changes medium→low), `.bak-before-topmodel-...` (empty agent-section diff).…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `protocol-subagent-smoke-20260917/agents/SMOKE-AUDIT-MODELS-PROTOCOL-20260917-01.md` → `.memory/protocol-subagent-smoke-20260917/agents/SMOKE-AUDIT-MODELS-PROTOCOL-20260917-01.md`; SHA256 `df699ceef8023a17e27e4f56a2dae950ee3a319c4ec75e0a335cc05ee4f5f7c8`; source state `tracked`
