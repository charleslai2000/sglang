# R17 — GPU Per-Step Timeline

## Goal
在唯一 `3090-24g-hicache` 主线，复用 NVIDIA Nsight Systems GPU Metrics、scheduler进程内CUDA trace、现有FPM/NVTX step markers，采集 c8/c16 稳态 Prefill/Decode 的 GPU活动、计算、调度空档及逐step时间分解；将硬件samples按真实batch区间对齐并报告采样开销。

## Authority and constraints
- 工作树 `/home/ubuntu/workspaces/3rdparty/sglang-hicache`，branch `3090-24g-hicache`，当前授权基线 `51caa48cf9ff6c5b525b8b355e276a1572748f61`；不建分支/worktree，不触碰 sibling opt。
- 保留51caa48已验收的NCU与clean TPS；不得重复NCU采集或已完成吞吐测试。Profiling 与不带采样对照必须独立，不能把带采样结果作为干净吞吐。
- RTX3090独占、sudo/capability已授权。作业前确认PID/端口/锁/GPU，本目标服务作业后清理；两个目标systemd服务均已按指示停止并禁用，启动前须核实。
- 复用现有 runner、FPM/NVTX、CUDA trace、sudo Nsight路径；不增加独立framework或产品instrumentation，优先使用已有scheduler markers。
- 每步按真实batch汇报；整卡GPU metric不得硬归因到请求/token。异步重叠的interval分别显示，不重复相加。未有证据的字段明确 UNKNOWN。

## Scope
1. 探明Nsight Systems 2025.1.3 GA102 `ga10x` metric set和权限；1kHz先采，只有必要时10kHz并检查采样间隔/丢样及附加开销。指标覆盖受工具支持为准，不能把NVML当替代。
2. 同时采集 Nsight GPU metrics + CUDA/NVTX外部时间线；复用scheduler in-process profiler/FPM。验证wall/monotonic/CUDA timestamps可对齐，批次身份与真实运行请求数、tokens可关联。
3. 以实际 scheduler batch step 输出Batch ID、running reqs、Prefill/Decode tokens、scheduler start/end及queue/wait、cache wait、H2D completion、forward start/end、kernel/graph replay、Token Ready、下一轮启动。
4. 每1ms归一SM/Tensor Active、DRAM read/write、L2（若set有）、clocks、copy engine等；更短kernel通过CUDA trace事件呈现。统计1ms样本分布、缺样与时间戳差。
5. c8/c16分别测稳定Prefill与Decode；给逐step分解、1ms曲线、GPU空档及可由证据确认的原因、并发效率差异、profiling overhead。
6. 回归/审阅、结果报告及合格成果选择性commit/push；精确保留无关dirty/untracked资产。

## Completion
- c8/c16稳态Prefill和Decode均有身份明确的1kHz真实GPU metric与scheduler step证据；10kHz只在需要且相同权限门下评估。
- 每step区间、tokens/requests和至少可闭合的schedule/forward/kernel timing均能复算；metric samples以已验证时间映射对齐。GPU idle作为1ms上的整卡低活动，非kernel空档需通过CUDA trace定义。
- 缺失的L2/TokenReady/cache-wait等字段保留UNKNOWN，不编造。带/不带profile吞吐差异与来源分开报告。
- GPU服务资源清洁，只有精确allowlist成果commit/push。
