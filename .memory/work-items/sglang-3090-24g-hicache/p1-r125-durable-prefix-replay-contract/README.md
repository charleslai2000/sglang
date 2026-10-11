# P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT

- **工作标题：** P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/R125-bundle/P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT.md`：**
- Applies to `P1-DURABLE-PREFIX-REPLAY-20260912-R125`.
- Binding additive superset of `R121-bundle/P1-R121-CONTROLLED-EVICTION-CONTRACT.md`
(`2ac86b5a…b3b`) and `R123-bundle/P1-R123-TEMPORAL-WAKE-GATE-CONTRACT.md`
(`bf7b09ee…1e1f8`). Gate basis is v2 (L2 host pool via `host_alloc.v1`).
- User ruling (2026-09-12): execute **Option A** — restore-path replay of R121's
KNOWN durable prefix on the rebuilt server (which loads the HOST_ALLOC
wake-liveness fix). NO product patch, NO profile change, NO workload redesign.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R125-bundle/P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT.md` → `.memory/phase2-hicache-design/work/R125-bundle/P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT.md`; SHA256 `f78a2fc698de375de612ace8c023e4a6518a6781c155c2f5e92b66dd521f3c1f`; source state `tracked`
