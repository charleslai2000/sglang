# G3-E3-PRODUCTION-A-LAUNCH-20260907

- **工作标题：** G3-E3-PRODUCTION-A-LAUNCH-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
启动获准的 Production A 基准矩阵 wrapper，先运行 C1/repeat-1，并记录运行身份、初始 admission 和 telemetry 进程，供后续 monitor/verification 继续。

## 实际改了什么
在远端 run root 启动 `run-production-a.sh`（wrapper SHA-256 见原报告），启动首个 C1/repeat-1 workload/client 与指定 dmon/query 采集器；无报告记录的产品源码改动。

## 生成结果与验收
原报告截点为 **pending/running**：wrapper PID `434309`、client `434364`、dmon/query `434362/434363`；C1/repeat-1 尚在运行，无完成矩阵或 scorecard。后续独立 monitor/verify 报告才记录最终 run 结果；不能把此启动报告本身视作 benchmark 完成或当前进程状态。

### 产物
RUN_ID `g3-e3-prod-a-20260907T145045488234751Z` 的远端目录及 wrapper 元数据见报告。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-E3-PRODUCTION-A-LAUNCH-20260907.md` → `.memory/g3-performance-and-serving/work/G3-E3-PRODUCTION-A-LAUNCH-20260907.md`; SHA256 `39fd6b6cd4681a0aae8ff3c9e08c61c6f28c8db5e9e27f83e8705e00e4494391`; source state `local-only`
