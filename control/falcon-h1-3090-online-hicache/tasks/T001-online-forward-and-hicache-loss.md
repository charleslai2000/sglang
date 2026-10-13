Status: ACTIVE
Work area: experiments
Objective: 复用T002 CUPTI baselines、R17 current-mainline NCU/Nsight与现有HiCache驱动，在唯一主线完成Falcon c8/c16真实在线逐轮GPU/调度关联、HiCache L1/L2/L3有效恢复测量、瓶颈针对优化A/B、必要回归及精确提交推送。
Inputs: `goal.md`/`plan.md`; T002 report/raw; R17 `R17-NCU-HARDWARE-MATRIX.md`, `R17-GPU-PER-STEP-TIMELINE.md`及Nsight/FPM/runner manifests; `falcon-h1-3090-hicache-cache/`中R15/R7C/R11原始记录与当前dirty Runtime差异;现有NVTX/FPM/HiCache工具。
Completion: A-E完整阶段报告；在线forward/queue/scheduler/kernel-union/idle/token指标有可复算同request/iteration/batch身份；c8/c16与T002离线同shape合理对照；HiCache有效L1/L2/L3命中、KV/Mamba恢复、传输/ready/token节省与净收益或NOT_QUALIFIED；实测确定的loss ranking和matched A/B；必要回归通过；精确allowlist commit/push；GPU/服务清洁。
Result: 2026-10-13启动。T002七形状基线已完成，不重跑。现有R17 NCU有kernel级profile数据但不代表whole-stage attribution；已有Nsight/FPM session只能按workload总窗口对齐，缺少iteration公共时钟锚和动态step NVTX，逐轮Busy/Idle尚UNKNOWN。R15真实失败链显示backup/ACK通过而device detach未发生，具体dirty-source原因待查。没有启动T003 GPU采样或新Cache认证；开始时先核实当前主线和设备。
Remaining: 执行plan.md decisive frontier；在任何进度报告顶部先给report.md的A-E状态表，NOT_RUN/UNKNOWN不可补猜。