# R17-CACHE — HiCache 分层恢复与性能测量

## Goal
在唯一主线 `3090-24g-hicache` 上完成 Falcon FULL KV+MAMBA 的 L1/L2/L3 有效缓存恢复、逐层命中/等待/传输/恢复测量及正确性验证；只有真实 Host/Disk 恢复通过后才报告缓存收益。

## Authority and constraints
- 工作树 `/home/ubuntu/workspaces/3rdparty/sglang-hicache`，分支 `3090-24g-hicache`，基线/验收提交 `51caa48cf9ff6c5b525b8b355e276a1572748f61`；唯一开发主线，不建分支/worktree，不触碰 sibling `opt`。
- 保留并保护全部已有 Runtime 修改和证据；保留此提交验收的 NCU 与 clean TPS，不重复采集。
- RTX 3090 独占及 sudo 已授权；每次作业前检查 GPU PID、端口、锁和目标，作业后清理本任务服务。
- 优先复用 R7C/R11/R15、现有 telemetry、工具与已存在上游修复；不新建 tracing/benchmark/认证框架，不重复认证 R11 durable write。
- 先从已有 `detach_not_sealed` 日志、Runtime diff、Host eviction 实现定位原因；普通工程/测试问题自行诊断修复，不盲目压力复现。
- correctness/assertions 不降级；逻辑命中、Host/Disk有效恢复、OS page cache 与物理设备 I/O 分别陈述。未通过层保持 NOT_QUALIFIED，不宣称缓存收益。

## Scope
1. 对照 R15/R7C/R11 现存原始证据及当前dirty Runtime，核实 FULL Host leaf、MAMBA Host LRU、lock/ownership/residency/ACK；修复导致 Host-only/Disk restore 不可达的实际缺陷。
2. 用确定性共享前缀负载完成当前主线 FULL+MAMBA L2：有效备份、Device eviction、Host-only match、H→D CUDA completion、greedy token IDs一致。
3. 复用 R11 已通过的 Extent durable write，修复Host eviction/Storage read-back，完成 L3→Host→GPU真实恢复；分辨 OS page cache与物理I/O。
4. 复用现有 telemetry 计量 L1/L2/L3所列有效命中、lookup/wait、迁移字节/耗时/带宽、DMA完成至GPU ready及总恢复时延；FULL KV/MAMBA分开。
5. correctness门通过后，用正常容量的确定性多轮 workload 对比GPU-only/GPU+Host/GPU+Host+Extent，报告Prefill节省、恢复成本、有效吞吐、E2E TTFT变化；计时边界明确且异步重叠不重复计算。
6. 完成必要定向回归；对合格代码、测试、结果选择性 commit/push，记录精确身份并清理GPU服务。

## Completion
- L1/L2/L3命中率和逐层延迟/等待/IO表可由本次主线原始证据复算；FULL KV/MAMBA迁移字节与实际带宽分列。
- L2 Host-source H→D及L3 Extent read-back→Host→GPU均有设备状态、完成/ACK与greedy correctness证据；否则相应层明确 NOT_QUALIFIED。
- 仅在有效恢复后给出 Prefill 节省、恢复成本和净性能收益；OS page cache状态及物理I/O证据明确。
- 定向回归、精确commit/push记录完成；无本任务GPU服务遗留。不得把51caa48已验收NCU/TPS重跑或重新计入。
