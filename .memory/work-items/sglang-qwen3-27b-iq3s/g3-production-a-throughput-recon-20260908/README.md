# G3-PRODUCTION-A-THROUGHPUT-RECON-20260908

- **工作标题：** G3-PRODUCTION-A-THROUGHPUT-RECON-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
只读 reconcile 保存的 Production A 与 Profile C raw scorecards，澄清 runner 的 output TPS 与 total TPS 标签/计算口径，避免跨指标比较造成吞吐误读。

## 实际改了什么
只读检查既存本地 raw artifacts 并以 duration、input/output token totals 重算吞吐；未 SSH、运行 workload、改服务、源码或 benchmark client。

## 生成结果与验收
报告确认 `output throughput = total_output_tokens / duration`，`total throughput = (total_input_tokens + total_output_tokens) / duration`，计算与 raw JSONL runner 字段一致；retokenized output count 单独保留，不替代请求生成量。指出输出约 170 tok/s 是 total throughput，不能与约 35 tok/s output throughput 混为同一指标。reconciled medians 为离线复核结果，不是新测量；各点数据仅限被检查的 raw runs。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PRODUCTION-A-THROUGHPUT-RECON-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PRODUCTION-A-THROUGHPUT-RECON-20260908.md`; SHA256 `7dff42b9781b25a6822c5511dfeacbf2fa3c296eb2d88846fa09f35249fb691b`; source state `local-only`
