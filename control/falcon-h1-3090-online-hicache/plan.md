# T003 当前计划

## Reusable evidence
- T002 CUPTI离线矩阵已在commit `48d6e1ef1c4ff82c4258afe77916352143478676`完成并推送；7种Forward每形状三独立session。复用报告`control/falcon-h1-3090-cupti-forward/report.md`与`runs/`，不得重测。
- T002异常定点复核：Prefill4K `p4-final-r0` profiling-vs-unprofiled max abs logits diff `0.4529533386`，argmax仍相同；`r1/r2` exact，另一次相同fixture ON/OFF parity trial也exact。差异只出现在一对执行，原因无法唯一定位，不能声称CUPTI导致。Prefill1K离群 `p1-final-r2` Event 370.618ms、CUPTI 370.077ms、SM Active 69.45%、DRAM peak 32.68%；稳定组约284–287ms、SM Active约92%，说明整次GPU工作进度变慢；原因UNKNOWN。Event/CUPTI时间差是不同测量边界，应分别报告。
- R17 NCU `R17-NCU-HARDWARE-MATRIX.md`提供代表性kernel counters，但不代表整阶段/逐轮GPU union；不重采已验收NCU和clean TPS。
- R17旧Nsight/FPM c8/c16总窗口观测可作历史参考，不能替代kernel union/per-step queue/idle，也不是matched profiling-clean对照。
- HiCache R15 backup/ACK和durability已通过，但目标node device detach未发生（`device_detach_seen=false`、`component_tiers=[]`、`expected_release_count=0`、queues empty）。R7C旧run不等于当前主线Host restore认证；L3 readback未闭合。
- 工作树 `3090-24g-hicache`；本Goal记录commit `cf9ab2fed2c113dd16347f910d8b6c32c1d660d9`已推送。其它Runtime/cache/frontier dirty及untracked实验资产须保护，不得reset/clean或宽泛stage。

## Established results
- 新capture短验证及同一40×128 c8/c16 Nsight/FPM workload完成：`runs/t003-nsys-c8-t94-n40/`和`runs/t003-nsys-c16-t95-n40/`。SQLite包含NVTX、CUDA runtime/kernel、CUDA graph-node、GPU_METRICS；GPU metrics以1kHz配置采集。
- FPM iteration与step NVTX标记相交：c8 661/664（缺12/143/536），c16 403/406（缺14/147/278）。在线Decode实际batch：c8 b1=8、b8=640；c16 b1=8、b8=128、b16=256。
- workload-window Nsight kernel interval union：c8 13.4872s / 17.0924s = 78.91%；c16 10.0477s / 13.3152s = 75.46%。同窗口no-kernel intervals分别3.6053s/3.2675s。它们仅为整窗口kernel timeline统计；不得解释为Scheduler idle或按step归因。异步CUDA Graph replay尚不能可靠映射到单个step；旧runtime-launch-start join不合格。
- 全卡workload-window GPU metrics：c8/c16 SMs Active均值64.98%/65.04%，Tensor Active 13.92%/14.50%，DRAM read throughput 43.61%/39.73%，write 6.25%/8.10%。不映射到请求或step。
- profiling 40×128观测c8 17.0924s/299.548 tok/s，c16 13.3152s/384.523 tok/s；不是clean-run matched A/B。细节见`report.md`。

## Decisive frontier
1. 在线profiling结果和A–E报告已更新。Per-step kernel busy/idle、Scheduler CPU、queue wait、launch delay仍UNKNOWN；不重采T002/NCU/TPS。
2. 主要下一步：核查当前dirty Runtime与R15实际detach未发生链路及ownership；复用R7C/R11既有驱动，确认代码路径后尝试当前主线L2 FULL+MAMBA Host-only→H2D/GPU Ready正确性；随后独立闭合L3 read-back，区分OS page cache与物理I/O。
3. 仅当从现有记录或定向分析可建立可信的异步Graph replay→step identity时，继续逐轮GPU归属；否则保留UNKNOWN。
4. 只有数据足以排序损失来源后才做同负载优化A/B。完成必要回归、报告与GPU cleanup后，精确allowlist本Goal成果commit/push，不stage其它dirty资产。

## Unknowns
- 异步CUDA Graph replay与单step间的完整kernel归属、step级GPU idle原因、Scheduler CPU、queue wait和launch delay。
- 当前主线L2 Host restore及L3 read-back真实性能/正确性、有效命中、saved-prefill与净收益。
- loss ranking与任何优化/A-B结论。
- Prefill4K低幅logits差与Prefill1K单次GPU slowdown的唯一原因。
