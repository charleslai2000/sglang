# RTX3090 Falcon Prefill Unlock A/B

## 目标
同一 Falcon-H1-7B-Instruct-GPTQ-Int4 checkpoint、运行时与固定 token-ID 输入下，对RTX3090 350W Unlocked/Stock测量1K/4K/8K/16K Prefill；Batch 1为主，Batch 4显存允许时补充。至少5次有效重复。独立Prefill GPU时间以同步`ModelRunner.extend()`计时为主，辅以真实服务scheduler Prefill/queue计时、TTFT、kernel分布及chunk/cache证据。

## 边界
复用现有模型、环境、启动参数、工具与证据；不得修改生产 kernel、模型、量化或 SGLang 实现，不做其他性能优化或 T004 扩展。保持并行 dirty tree；不重启/操作宿主机。Stock 必须在 Guest 重启后通过短 GEMM 回到历史 Stock 性能区间确认，否则停止 A/B、恢复 Unlocked，不将结果标为 Stock。

## 完成条件
先完成并保存 Unlocked 全矩阵，再完成经 GEMM 确认的 Stock 同矩阵，最终恢复并确认 Unlocked；输出原始数据、环境身份、Profiler 摘要、真实服务验证及汇总表。实验后停止服务、释放 GPU 锁。