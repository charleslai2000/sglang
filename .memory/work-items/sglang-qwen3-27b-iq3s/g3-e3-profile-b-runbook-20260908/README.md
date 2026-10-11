# G3-E3-PROFILE-B-RUNBOOK-20260908

- **工作标题：** G3-E3-PROFILE-B-RUNBOOK-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
编制 Profile B 的只读、可执行 runbook，定义 v1→B 转换、C1/C4/C8/C16 decode 与多档 prefill 测量、admission/容量门槛、证据清单和精确 v1 rollback。

## 实际改了什么
仅写入本地 runbook 报告；未发送 benchmark request、远端写入、signal、restart、download、source/model edit，也未注入审计/trace/instrumentation。报告不是主机转换授权，执行另需独立 launch/admission task。

## 生成结果与验收
交付设计型 runbook，规定 v1 identity precheck 后才可由独立授权任务停止明确 PID、启动固定 8036 Profile B；C1/C4/C8/C16 各三次 decode，P2K/P8K/P32K 各三次 prefill，并按每次 flush、有效 server concurrency、完整 telemetry/artifact 执行。硬门槛包括有效容量至少 16/33024/64、实际观测并发达各 C、精确长度、无 OOM、每点三次及证据完整。失败时只可按精确 PID 清理并以冻结 argv 恢复 v1；还原失败则 blocked，不得另行试启。该 invocation 自身 **NO-GO 执行**，runbook 设计交付完成不表示测试已跑或主机已转换。



## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-E3-PROFILE-B-RUNBOOK-20260908.md` → `.memory/g3-performance-and-serving/work/G3-E3-PROFILE-B-RUNBOOK-20260908.md`; SHA256 `1e09a2b187593619b568678fe22b982d0c0a4b8407464b2b807d7fd88d0bb66e`; source state `local-only`
