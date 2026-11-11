# G2 QUASAR E5M2 c32 × 32K Context Capacity

## 目标
实测单卡 RTX3090、Gemma4 QUASAR、BF16 compute + E5M2 KV 能否同时承载 32 个独立请求、平均驻留上下文约 32K 并持续 Decode；测量 Full/SWA 池容量、峰值显存、Prefill、Decode TPS 和延迟。若不达标，定位限制并记录实际演示负载。

## 边界
复用已验证 HEAD-shadow overlay、AOT binary 和 E5M2 路径；不重跑 GSM8K，不触碰共享 dirty 源码。必须证明 scheduler 同时 active 请求而非只提交客户端并发；不得依赖共享前缀。GPU 按项目锁运行。专属 harness、报告和控制文档精确提交，其余 dirty/untracked 保留。

## 完成条件
真实服务按目标配置执行并提供可复核的 active-batch 证据、实测容量/时序/峰值显存；目标结果或具体限制经实测记录，必要时受控复测并记录演示边界；产物 hash、清理状态、提交及远端 SHA 核验完成。
