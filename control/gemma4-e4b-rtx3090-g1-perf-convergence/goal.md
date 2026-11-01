# G1 RTX3090 Gemma4 性能测量收敛

## Goal
基于已验收的真实 batch16/24/32 服务测量与 Nsight 归档，解释相同运行内 Scheduler/CPU提交、CUDA Graph replay、GPU执行/排队/空闲、请求输出时间线的关系；补齐1K/4K/8K Prefill GPU时长/TPS及全并发cohort的Prefill统计。

## Constraints
复用既有GPU batch32验证与有效归档；不得改模型、KV精度、缓存语义、生产性能路径或时钟；Prefill chunk固定8192。Profiler只作短窗归因，在线指标取非Profiler基线。137原因仅基于此前已读日志，未知则保留UNKNOWN。所有GPU run持有`/tmp/f1-r16b-gpu-exclusive.lock`；保留dirty/untracked工作，只提交可独立归属文件。

## Completion
同轮step→Graph launch correlation→GPU replay和请求时间戳可复算；1K/4K/8K独立Prefill计时/TPS、full-cohort Prefill forwards/token/TTFT/peak memory完整；已证实瓶颈与未知因果清晰区分；报告与可复算代码定向提交/push并验证SHA，既有batch32验证不重跑。
