# COD-20260908-P0-VEHICLE-TARGET-CHURN-FIX1

- **工作标题：** COD-20260908-P0-VEHICLE-TARGET-CHURN-FIX1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/COD-20260908-P0-VEHICLE-TARGET-CHURN-FIX1.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/COD-20260908-P0-VEHICLE-TARGET-CHURN-FIX1.md`：**
Added a deterministic auxiliary churn phase of `FROZEN["active"] + 1 = 9`
builds after `_run_build_phase` and before `_run_warm_scheduler`.
- Churn IDs use `p0-s25-churn-00000` through `p0-s25-churn-00008`.
- Builder seeds are disjoint from the 25 target seeds (`25..33`), and duplicate
  target or churn histories fail closed.
- Churn admission requires HTTP 200, terminal completion, and `response.id`.
- Successful churn requests establish only reducer build identity; they are not
  inserted into `build_rows`, planned/eligible accounting, or warm submission.
- Churn response metrics and per-request failures are emitted in
  `churn-builds.jsonl` and summarized in `verdict.json`.
- Any churn failure is fatal and prevents the warm scheduler from starting.
- Final accounting explicitly checks that churn IDs do not overlap planned IDs.

### 报告列出的产物/证据
- `phase2-hicache-design/work/COD-20260908-P0-VEHICLE-TARGET-CHURN-FIX1.md`：Changed only the authorized implementation and focused fixture:
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`
Required report:
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/COD-20260908-P0-VEHICLE-TARGET-CHURN-FIX1.md`

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/COD-20260908-P0-VEHICLE-TARGET-CHURN-FIX1.md` → `.memory/phase2-hicache-design/work/COD-20260908-P0-VEHICLE-TARGET-CHURN-FIX1.md`; SHA256 `a044b6bc4d2fbcb86db5a3075029733632c80e4a059872cd010d7a4fba82e429`; source state `tracked`
