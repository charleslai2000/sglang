# G3-RUNBOOK-A-20260907

- **工作标题：** G3-RUNBOOK-A-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
编制冻结 Production Profile A（unchanged v1，C1/C4/C5）的可审计运行手册，核实 runner 命令与 warmup/flush 语义、执行前置条件、repeat evidence 和评分材料。

## 实际改了什么
只写入 runbook 报告；只读远端 discovery。明确未做远端写入、状态变化、benchmark workload、process control 或安装。

## 生成结果与验收
确认 runner 参数可用；native SGLang 的 mutating endpoints 是 workload 自身 `/generate` 与显式 `--flush-cache` 的 `/flush_cache`，warmup 在测量前执行，必须每次独立 invocation 并显式 flush。手册规定 C1/C4/C5 及其 prompts/repeats、日志/telemetry、原始结果与 scorecard 的收集方式。该工作是执行设计，不是 benchmark 运行或性能结果；无服务状态变化授权。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-RUNBOOK-A-20260907.md` → `.memory/g3-performance-and-serving/work/G3-RUNBOOK-A-20260907.md`; SHA256 `1785ad0ec9f3fe30429e6154ad38e84e5e96cd1db4b1117396f60fe0d67f73ef`; source state `local-only`
