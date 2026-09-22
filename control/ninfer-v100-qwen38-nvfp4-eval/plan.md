# Plan: Qwen3.8-27B NVFP4 V100 验收

## 结果概要
1. **环境与构建**：V100/sm_70 事实、远端网络、隔离 CUDA 12.8/CMake/Ninja、conda 依赖、CUTLASS 中介、源码传输和构建均已记录；源码未改。
2. **artifact 与服务**：rev3/rev2 版本分歧已定位；rev2 SHA/大小/头部校验通过；CLI 生成、服务监听、health/models 端点通过。
3. **连通与功能**：公网暴露失败，SSH 隧道可用；harness 真实请求成功；SWE-bench 24/24 生成完成，resolved 21/24。
4. **性能与生产门禁**：ABCD 基准已完成；coding workload decode 达线或接近达线；MTP、长上下文 cold TTFT、prefix reuse ratio、device-hit TTFT 未全部达生产门槛；C2 有价值，C4 无扩展价值。

## 决定性结论
这是“部署可用、生产门禁部分不通过”的结果，不是“全项生产验收通过”。历史轮询、诊断、重跑和同一结论的重复记录已归并，不再作为独立任务。

## 剩余
无授权的新执行任务。若要继续，只能新建 Goal，明确是修复生产门禁还是追加 soak 终态核验。
