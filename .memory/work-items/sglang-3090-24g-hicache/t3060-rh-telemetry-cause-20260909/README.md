# T3060-RH-TELEMETRY-CAUSE-20260909

- **工作标题：** DBG-20260909-RH-TELEMETRY-CAUSE
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/DBG-20260909-RH-TELEMETRY-CAUSE.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/DBG-20260909-RH-TELEMETRY-CAUSE.md`：**
The primary cause is an RH eligibility logic defect, exposed by the queue-first
RH-ON ownership change: `Scheduler._ready_horizon_views()` makes
`has_restore_potential()` a prerequisite to selecting `plan.to_issue`, but that
predicate is narrower than the real prefetch issue gate.  In particular,
`prefetch_gate_ok()` permits an L3-durable anchor, while
`has_restore_potential()` does not.  A long request with no host hit and an
existing, non-root, L3-durable anchor is consequently excluded before RH can
call `_prefetch_kvcache()`, even though that call's own gate would permit the
storage query.
The final ON run reached precisely this upstream exclusion for every RID.
The lack of request-correlated storage/RH lifecycle telemetry is downstream of
the absence of an issue attempt, not a probe/correlation failure: the probe
toggle was present and there are no target-RID `pc_prefetch_enter`,
`pc_outcome`, or `pc_storage_query` records.  The five HTTP 200 responses only


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/DBG-20260909-RH-TELEMETRY-CAUSE.md` → `.memory/phase2-hicache-design/work/DBG-20260909-RH-TELEMETRY-CAUSE.md`; SHA256 `0e02862287529e9118684918baba973df5233bfc796483101f76e1a0945e1491`; source state `tracked`
