# Goal: NInfer V100 + Qwen3.8-27B NVFP4 部署与验收

## 内容概要
在单张 Tesla V100 32GB 上获取、构建并验证 NInfer Qwen3.8-27B NVFP4：环境/工具链、artifact 版本、服务启动、网络桥接、基准、SWE-bench 与生产验收门禁。

## 已建立事实
- 目标 GPU 为 Tesla V100 32GB / sm_70；远端原生 CUDA 为 12.4，另在隔离路径准备 CUDA 12.8、CMake/Ninja 与 CUTLASS。
- 通过 conda 依赖路径完成构建，未修改 inference runtime 源码。
- rev3 artifact 与旧二进制不兼容；回溯并恢复 rev2 artifact 后解除阻断。
- 服务可在 `0.0.0.0:8080` 监听；公网路径失败，但 SSH 隧道连接 harness 可用。
- SWE-bench Verified 24 个实例完成，resolved rate 为 21/24 = 87.5%，无基础设施失败、无空 patch。

## 约束
不扩大硬件/模型范围，不进行 kernel/runtime 优化，不混淆评分进度与 resolved rate。

## 终局判断
核心部署与评估已完成，但生产验收不是全通过：decode 和部分并发门禁通过；MTP acceptance、128K cold TTFT、growing-prefix reused ratio、device-hit TTFT 未达设定门槛。soak 的最终状态以已有记录为准，不能把中间状态宣称为全项 PASS。
