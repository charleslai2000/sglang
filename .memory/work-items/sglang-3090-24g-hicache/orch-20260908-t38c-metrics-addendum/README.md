# ORCH-20260908-T38C-METRICS-ADDENDUM

- **工作标题：** ORCH-20260908-T38C-METRICS-ADDENDUM
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/ORCH-20260908-T38C-METRICS-ADDENDUM.md`：**
The paired trace run completed 25/25 builds, one 300-second post-build settle,
and 8/8 warm requests. All 8 returned HTTP 200 / `rc=0`; total elapsed time
was 954.9 seconds.
Warm request metrics from `runs.csv`:
| session | TTFT (s) | prefill input | device hit | host hit | storage hit | restore result |
|---:|---:|---:|---:|---:|---:|---|
| s00000 | 2.361 | 37 | 6 | 0 | 55139 | KV+Mamba |
| s00001 | 0.638 | 78 | 7 | 55097 | 0 | short suffix; below 256 threshold |

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/ORCH-20260908-T38C-METRICS-ADDENDUM.md` → `.memory/phase2-hicache-design/work/ORCH-20260908-T38C-METRICS-ADDENDUM.md`; SHA256 `1332d7892d30c7b86f967b9daf125e34198d8711c2655c7bdd63820aa3c43d8d`; source state `tracked`
