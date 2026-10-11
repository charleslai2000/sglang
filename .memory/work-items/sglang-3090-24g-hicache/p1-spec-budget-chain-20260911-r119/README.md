# P1-SPEC-BUDGET-CHAIN-20260911-R119

- **工作标题：** P1-SPEC-BUDGET-CHAIN-20260911-R119
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/P1-SPEC-BUDGET-CHAIN-20260911-R119.md`：**
- task_id: `P1-SPEC-BUDGET-CHAIN-20260911-R119`
- invocation: `ses-p1-spec-budget-rerun-r119-20260911` (fresh)
- role: `tester`
- epoch: `2026-09-11`
- status: **done**
Server (read-only, never started/stopped/restarted/killed/reconfigured):
PID `48746` (`launch_server`), scheduler child PID `48806`,
`http://127.0.0.1:30000`, health `200` throughout and at finish.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/P1-SPEC-BUDGET-CHAIN-20260911-R119.md`：**
The COMPLETE SPEC_BUDGET causal chain (legs 1–8) was captured for target
identity `r119-p1-R-T` / `lifecycle_key r119-p1-R-T:28` in session
`r119-s-p1` (generation 28) under the unchanged frozen R117 profile.
All legs are real events with file:line refs (`chain.json`). The batch
HTTP request returned **200** in **69.759 s** (terminal outcome
`completed`), and no `restore_recompute` and no hybrid discard were
emitted for the target.
A second run (`p2`, secondary/corroborating) proved the R118-defect-3
durability fix end-to-end for the target prefix (27392/27403 tokens
durable in L3) but the target's host allocation timed out and it
recomputed (`restore_recompute cause=timeout`); `p2` is therefore not
the primary chain. Both runs together bracket the residual host-pool
bottleneck honestly (see §6).


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4f41f5bab562b99562f30c67540eb05344d13637`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P1-SPEC-BUDGET-CHAIN-20260911-R119.md` → `.memory/phase2-hicache-design/work/P1-SPEC-BUDGET-CHAIN-20260911-R119.md`; SHA256 `5906545273e8c4c468b83e0a3e1cee525fef8fa049c3633338059215491f6b3f`; source state `tracked`
