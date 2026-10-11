# G3-PRODUCTION-A-EXEC-20260907

- **工作标题：** G3-PRODUCTION-A-EXEC-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
按 Production Profile A runbook 尝试 C1 三次基准测量；遵守 RSS 安全阈值，任一 runner OOM 即停止矩阵、保存证据并恢复服务，不从失败运行声称性能结果。

## 实际改了什么
启动 Production A wrapper 并执行 C1/repeat-1..3；三次均 OOM 后停止 wrapper、写入 `HALTED.txt`、保留日志并恢复当时服务至 clean idle。没有产品代码改动记录。

## 生成结果与验收
任务 **blocked**：三次 C1 均 rc=137，匿名 RSS 约 42.6GB（主机 48GB、0 swap）；未生成任何 `result.jsonl`，因此没有可报告测量值或 scorecard。按安全门槛停止，不循环重试。后续需诊断 runner 根因并获得改变执行方法的授权；原冻结命令当时无法安全运行。RUN_ID、wrapper 与 OOM/HALTED 证据路径见原报告。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PRODUCTION-A-EXEC-20260907.md` → `.memory/g3-performance-and-serving/work/G3-PRODUCTION-A-EXEC-20260907.md`; SHA256 `fa933826943fcc90495b625a9c0999e99edd0ba11ba7521ec34c4a7531a79584`; source state `local-only`
