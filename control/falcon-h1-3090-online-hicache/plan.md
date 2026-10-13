# T003 当前计划

## Reusable evidence
- T002 CUPTI离线矩阵已在commit `48d6e1ef1c4ff82c4258afe77916352143478676`完成并推送；7种Forward每形状三独立session。复用报告 `control/falcon-h1-3090-cupti-forward/report.md` 与`runs/`，不得重测。
- T002异常定点复核：Prefill4K `p4-final-r0` profiling-vs-unprofiled max abs logits diff `0.4529533386`，argmax仍相同；`r1/r2` exact，另一次相同fixture ON/OFF parity trial也exact。差异仅出现于一对执行，原因现有证据无法唯一定位，不能声称CUPTI导致；需检查GPTQ/GPU数值确定性/模型状态和是否只是接近argmax的低幅值分量差。Prefill1K离群 `p1-final-r2` Event 370.618ms、CUPTI 370.077ms、SM Active 69.45%、DRAM peak 32.68%；其它被排除的同组三样本及稳定重采均值约284–287ms、SM Active约92%，说明整次异常GPU工作进度变慢，不是Event与CUPTI计时口径彼此矛盾；原因UNKNOWN。其为三trial首组中一个sample；保留原始run，稳定独立三样本用于主统计，并未删除/伪称单次异常不存在。Event/CUPTI时间差跨行Prefill约0.05–0.16%、Decode约2.75–4.32%，反映不同计量边界，应分别报告，尚无证据表明某方错误。
- R17当前HEAD NCU `R17-NCU-HARDWARE-MATRIX.md`有代表Marlin/BF16/Mamba/Decode Attention kernel counters；不提供整阶段/逐轮GPU union，不重采通过的NCU和clean TPS。
- R17 Nsight 1kHz/FPM报告`R17-GPU-PER-STEP-TIMELINE.md`已有40×128相同workload观测：c8墙钟17.2449s/output 296.900 tok/s，FPM forward event sum17.0661s、runner remainder估算0.17876s、API queue均值47.85ms；c16墙钟13.4028s/output382.010 tok/s、FPM forward event sum13.2231s、runner remainder估算0.17969s、API queue均值301.70ms。GPU_METRICS/Kernels总数有证据，但动态step NVTX capture此前未触发，故上述 remainder不等于kernel-union idle、mean API queue不是每step queue wait，既有观测与clean吞吐差也不是matched开销A/B。
- Nsight复用材料：`run_nsys_falcon.py`已经配置trace cuda/nvtx、Graph node与1kHz GPU metrics；动态inner step range完整message为`sglang.step;worker=...;iter=...`，capture trigger尝试只写前缀`sglang.step`因此未触发。Nsight 2025.1.3帮助确认`--capture-range=nvtx`的trigger按range message；修复需通过静态外层capture marker触发/停止，内层动态step marker仅供ID join。现有workload driver和同库capture机制优先复用，无需新框架。
- HiCache R15已有backup/ACK和durability，但目标node detach未发生（device_detach_seen=false、component_tiers=[]、expected_release_count=0、queues empty）；因此根因不在ACK队列未排空已被排除。R7C旧run不能代当前current-mainline H→D认证；L3 readback未闭合。
- 工作区branch HEAD/remote `3090-24g-hicache @ aba9da99b1641e83e21075333168ca18563e0af9`。既有Runtime/cache/frontier大量dirty及untracked实验资产需保护，不准reset/clean。

## Decisive frontier
1. T002异常定点复核已完成，无GPU。保留所述UNKNOWN并在report给出准确证据/口径。
2. 修正并验证Nsight trigger：复用当前run driver加固定外层NVTX capture gate，范围覆盖R17 workload期间；内层动态step names仍带worker/iter/stage/batch/token。做一次短c8请求验证，要求SQLite有NVTX_EVENTS、CUDA runtime/kernel/graph和GPU_METRICS；FPM iteration可与step range exactly join，graph launch可通过correlation连接到kernel intervals，且范围capture确实自动关闭。短验证通过后以同一40×128负载采c8/c16，避免重采T002/NCU/TPS。
3. 输出per-step实际batch/Graph、forward GPU event、kernel interval union、Scheduler CPU边界、API/request queue、Launch Delay、Idle定义、tokens/throughput。Kernel duration不可直接求和成Busy；分辨GPU event时长和union overlap。
4. 并行查HiCache实际detach owner/lifecycle code against R15 evidence及当前dirty diff，复用R7C/R11驱动；只在确认代码路径/修复后做小范围真实L2验证，先FULL+MAMBA完整correctness、Host-only match、H2D complete/GPU ready；继而独立L3 read-back、物理设备与page cache分层。历史D→H ACK不重验。
5. 基于已join c8/c16和Cache数据确认瓶颈排序；只对明确证据支持的瓶颈做相同workload优化A/B，保存correctness。
6. 定向回归、报告、gpu cleanup后精确allowlist commit/push；其它用户dirty工作不进stage。

## Unknowns
- 目前没有T003新在线测量；R17已有Nsight没有step markers join，C表命中和D表loss仍UNKNOWN/NOT_RUN。
- R15 detach失败的直接调用链根因仍未定；当前dirty changes不能默认代表已修复。
- Prefill4K低幅度logits差与Prefill1K单次SM/GPU slowdown尚无唯一cause。
