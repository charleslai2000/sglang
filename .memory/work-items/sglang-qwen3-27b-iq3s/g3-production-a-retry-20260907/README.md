# G3-PRODUCTION-A-RETRY-20260907

- **工作标题：** G3-PRODUCTION-A-RETRY-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
启动一次新的 detached Production Profile A C1/C4/C5 矩阵执行，采用已确定的 runner/workload 绑定、每个 repeat flush 及首次 warmup 规则，并监控运行而不提前生成结论。

## 实际改了什么
报告记录启动 fresh RUN_ID 下的远端 wrapper；命令从既有 runbook wrapper 复制，仅调整 RUN_ID 与 warmup sequencing。没有本地产品文件修改记录。

## 生成结果与验收
该启动报告截点为 **pending/running**：C1/repeat-1 正在运行，8/20 requests 完成，runner RSS 约 1,608,960 KiB，尚 0/9 repeats 完成；当时未见 OOM/rc137 或 abort gate。报告只提供中间状态，最终 medians/hash/artifact completeness 需运行结束后的 monitor/verify 报告确认；不能将此卡当作完成或性能结论。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PRODUCTION-A-RETRY-20260907.md` → `.memory/g3-performance-and-serving/work/G3-PRODUCTION-A-RETRY-20260907.md`; SHA256 `a4564c86505b033174677276d964981ab10d205bd812c5ce9b1a9352b1b3a4f2`; source state `local-only`
