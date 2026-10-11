# REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX2

- **工作标题：** REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX2
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX2.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX2.md`：**
FIX2 correctly closes the five blockers from FIX1 in the tested repair paths.
However, the gate cannot accept the scheduler because a product warm event
that arrives before exact durability/residency barriers is recorded as
`lookup_before_barrier` but is not checked by `ready_for_warm()`. After the
barriers arrive, `_run_warm_scheduler` can submit a warm request anyway. This
violates the required causal order and can perturb the next live S=25 run even
though final accounting later rejects the row.
See the gate for exact lines, independent probe evidence, acceptance impact,
and the required fresh Task ID repair.

### 报告列出的产物/证据
- `phase2-hicache-design/work/REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX2.md`：- Gate: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-VEHICLE-BARRIER-SCHEDULER-FIX2.md`
- Reviewed vehicle: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- Reviewed fixture: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX2.md` → `.memory/phase2-hicache-design/work/REV-20260908-P0-VEHICLE-BARRIER-SCHEDULER-FIX2.md`; SHA256 `8a7ea18dafcb0f0e77fab2195aef9bc47292bd723d757b886a387720b422e71d`; source state `tracked`
