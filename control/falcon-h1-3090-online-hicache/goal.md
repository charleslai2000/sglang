# T003 — Falcon 在线性能损失与 HiCache 实测

## Goal
在唯一主线 `3090-24g-hicache`，复用已完成 T002 七组 CUPTI 离线Forward基线、现有 FPM/Nsight/HiCache 工具及既有恢复证据，定位真实在线 c8/c16 的Forward/调度/GPU idle损失，闭合 L1/L2/L3 有效恢复与收益账本；仅对实证瓶颈实施针对性优化和同负载 A/B，完成定向回归及精确提交推送。

## Authority and constraints
- 唯一工作树 `/home/ubuntu/workspaces/3rdparty/sglang-hicache`、branch `3090-24g-hicache`；不新建分支/worktree，不触碰 sibling opt。保留全部dirty/untracked Cache/Runtime/实验资产；按文件/ownership选择stage。
- RTX 3090独占及sudo已授权。GPU作业前复核PID/端口/锁/target，完成后清理本任务进程。
- 不重测T002已通过七形状离线矩阵；复用已验收NCU和clean TPS，不重采。已有Cache写入/ACK不重复认证。
- 优先复用现有FPM、Nsight 1kHz GPU metrics、R7C/R11/R15驱动和telemetry；不新建通用profiling/认证框架。必要计量要以相同请求/iteration/Batch/GPU range关联；禁止把不同负载吞吐差额归因调度。
- 保持正确性断言，不用零命中、D→H写入或设备命中冒充Host/Disk有效恢复；L3不阻断独立在线GPU计量。未知结果明确UNKNOWN/NOT_QUALIFIED。

## Completion
1. 复核T002 Prefill4K logits差、Prefill1K离群排除证据、Event/CUPTI时间边界；不重测完整矩阵。
2. c8/c16真实在线负载下获得实际 Decode Batch/Graph分布、Prefill/Decode每轮GPU forward、Kernel Busy Union、Scheduler CPU与轮间GPU idle、Queue Wait/Launch Delay、Prefill/Decode tokens/吞吐；可与T002同shape对照，明确不同负载限制。
3. 复用现有Nsight 1kHz硬件活动并关联实际execution timeline，给出稳态SM/Tensor/DRAM与空闲区间的证据边界。
4. L1/L2/L3有效命中、FULL KV+MAMBA恢复、Host/Disk等待/迁移/H2D完成/GPU ready、saved prefill tokens和净收益账本；未通过层NOT_QUALIFIED。
5. 依据证据排序最大三个损失来源；只对已证实瓶颈做同负载优化A/B，保存正确性/回归结果。
6. 必要回归通过，精确allowlist commit/push，GPU清理。

## Current result
T003已完成c8/c16 Nsight/FPM 40×128 capture并将A–E报告升级为逐轮Graph association结果。以CUDA GraphLaunch Runtime correlationId→kernel活动并经同TID唯一NVTX iteration range归属，窗口内569/569（c8）与340/340（c16）Graph replay均闭合；非Graph Decode尾段与FPM缺失Prefill均从CUDA记录分类。Scheduler纯CPU active、queue wait和纯driver launch成本仍UNKNOWN。HiCache L2/L3 current-mainline恢复尚未qualified，基于当前cache证据的优化A-B未运行。详细边界和raw paths见`plan.md`及`report.md`。