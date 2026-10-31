# 当前状态

- **MEASURED**：在线服务c1/2/4/8/16/24/32各三轮，所有请求生成256 tokens；Output TPS、请求延迟、真实active batch与GPU监控见`runs/GEMMA4-BF16-DECODE-BASELINE-20261031.md`。c24吞吐下降作为观测结果保留，不推测根因、不改调度器。
- **MEASURED（隔离微基准）**：独立ModelRunner CUDA Graph Forward b1/2/4/8/16，各25次CUDA Event；request/KV pool与在线服务不完全等价。
- **未测得**：精确TTFT、在线服务实际Forward时间。首轮HEAD声明不证明dirty运行源码身份与HEAD完全相同；报告限定可证实的源码差异范围。
- 用户明确排除为`/model_info`或逐replay ShapeKey重跑在线矩阵；不再启动GPU实验。G1仍FAILED / NOT ACCEPTED。

性能基线按上述范围归档；缺失指标不补造测量、不为提升完备性而扩大实验范围。