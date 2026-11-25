# R17 GPU Per-Step Timeline — 当前主线观测结果

日期：2026-10-12。目标 HEAD：`51caa48cf9ff6c5b525b8b355e276a1572748f61`。本结果不重采既有 NCU 和 clean TPS。

## 摘要与边界

| c | 确定性负载完成 | Nsight有效1ms时间点 | CUDA kernel rows | FPM active iterations | FPM Prefill tokens | FPM Decode steps | metrics窗口跨度 | 观测负载墙钟 | 带观测 output tok/s |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 40/40×128 | 262,805 | 853,460 | 661 | 13,601 | 648 | 262.803 s | 17.245 s | 296.90 |
| 16 | 40/40×128 | 255,803 | 513,760 | 403 | 11 | 13,760 | 255.801 s | 13.403 s | 382.01 |

采集命令使用 Nsight Systems 2025.1.3、GA102 `ga10x` metric set、1,000 Hz、CUDA + CUDA Graph node tracing、CUDA event trace off、CPU sampling/context-switch off；在独占设备上对已有R17确定性40请求workload与scheduler FPM同时采集。c8/c16分别完成全部40个请求，每请求128输出。profile期吞吐只用作观测开销/窗口描述，**不是 clean TPS**；不与51caa48验收clean点直接当成等价重复。

## 每毫秒整卡活动

Nsight导出 `TARGET_INFO_GPU_METRICS` 有31项：GPC/SYS clock、GPU Active、SM Active/Issue、Tensor Active、DRAM读写带宽比例、PCIe RX/TX、同步/异步copy engine及compute-warps等；无显式L2 Activity/Throughput metric。预检及两份Falcon capture的GPU_METRICS timestamp均以约1 ms均匀采样（已观察的相邻间隔约999,992–999,996 ns；没有>1.5 ms的缺口）。这些是整卡1 ms采样，不按单request/token归因。工具CSV/SQLite中计数值的命名单位是Throughput %；原始时钟字段以Hz编码（例如885,000,000对应885 MHz），报告脚本不得再乘GPU-Util或推造L2指标。

全Nsight进程窗口（包含约232–235 s模型加载与预热）SM Active均值：c8 4.72%（range 0–100），Tensor Active 1.04%（0–48），DRAM read 3.18% peak（0–98），write 0.51%（0–98）；c16 SM Active 3.97%（0–100），Tensor 0.94%（0–49），DRAM read 2.41%（0–98），write 0.53%（0–98）。这些全窗均值被长模型启动/空闲时间稀释，**不是稳态负载利用率**。必须用下列精确负载窗重算1 ms分布/曲线，不能把上述全窗均值写成活跃负载效率。

CUDA timeline包含c8 853,460/c16 513,760个kernel rows、147,171/（对应c16数可由SQLite复算）CUDA runtime活动及24,879个graph-node记录（此set内Graph-node metadata出现但非NVTX step label）。细于1 ms的kernel可由CUDA timestamp定位，不把异步kernel durations简单求和为GPU union。

## 时间窗、FPM与可归因范围

Nsight `TARGET_INFO_SESSION_START_TIME` 提供UTC session start。与R17 runner保存的workload `wall_start_epoch_ns`/`wall_end_epoch_ns`同处Unix epoch；差值：c8 workload开始在Nsys start后 **234.977050561 s**，c16在 **231.568433158 s**。负载窗口可据此选取Nsight timestamp `[offset, offset + workload_wall_duration]`，在设备/主机这条统一SessionNs时间轴上过滤CUDA kernel/runtime和1ms hardware samples。两份CUDA kernel实际时间都覆盖整个对应workload窗口，身份 `CUPTI_ACTIVITY_KIND_KERNEL.globalPid`唯一对应各自本次Falcon scheduler worker；FPM记录以现有ZMQ counter_id递增，worker=`falcon-mainline`，每个active iteration含scheduled Prefill/Decode requests/tokens及`wall_time`。

明确限制：
- FPM collector仅保存接收侧`time.monotonic_ns()`，没有记录与Nsight SessionNs同一时钟域的校准锚点；UTC窗口偏移只能确定请求 workload总区间，不能把FPM counter_id精确映射到某个GPU metric sample/Kernel launch。
- NVTX表共819行但只有1个有名范围（`CCCL`），没有scheduler per-step batch marker；不满足Batch ID join。CUDA graph-node表有node creation元数据，不含scheduler batch ID。因此逐step scheduler start/end、cache wait、H2D completion、token ready→下一轮间隔和按真实batch切分的GPU utilization均 **UNKNOWN**，不从相邻FPM时间或kernel中点推算。
- 已有FPM `gpu_forward_s`是scheduler iteration wall duration，active iterations：c8 661、c16 403；其中prefill/decode计数和token如摘要。FPM iteration duration会包含forward执行边界内异步活动，不等于GPU kernel union或调度空档。旧runner汇总的 `elapsed - sum(FPM wall_time)` 仅为estimated non-forward remainder，不能称作设备空档。
- GPU Active字段在该GA10x采集返回100，不能以其本身代表SM忙碌；报告采用SM Active/Tensor/DRAM等实际指标且分列。

## 观测影响

已验收clean throughput：c8均值311.515 tok/s、c16均值395.708 tok/s。当前带Nsight/FPM观测单次c8窗口296.900 tok/s，c16 382.010 tok/s；分别比已有clean均值低约4.7%/3.5%。但本次确定性工作负载runner、Profiling窗口、温控/同一采集配置并不构成预注册matched overhead AB，因此仅记作“观测run对既有clean参考的差值”，不将其解释为纯Nsight/FPM overhead或显著性能结论。没有10kHz run；1kHz已提供CUDA异步timeline解析短kernel，故未以更高频率增加采样负担。未测10kHz overhead/丢样。

## 证据与身份

- c8目录：`gpu-per-step/nsys-falcon-c8-t23-1khz-r9/`；SQLite `falcon.sqlite`、原始`.nsys-rep`、status、NSYS日志；请求/FPM证据 `mainline-gpu-only-c8-t23/`。
- c16目录：`gpu-per-step/nsys-falcon-c16-t24-1khz-r11/`；对应SQLite和原始报告；请求/FPM `mainline-gpu-only-c16-t24/`。
- Nsys report身份含GA102/3090、metrics及时间；workload manifests记录HEAD、dirty tracked hash、模型revision、配置和workload hash。
- 失败attempt目录`nsys-falcon-c8-t23-1khz[-r2..r8]/`保留，皆因runner AOT环境/路径覆盖或一次错误汇总路径造成，不作为测量样本。c8有效Nsys report rc=0；c16也成功。两个由本任务停止并禁用的常驻systemd服务：`sglang-swift.service`、`sglang-swift15-iq3s.service`，均保持disabled/inactive；最终GPU 1MiB、0%，无本任务server/NSYS PID、端口30000/30107/30160无listener。

## 未通过/下一步

本deliverable完成“1ms硬件活动+kernel timeline+FPM aggregate”的当前主线里程碑，但不满足用户要求的逐step完整join、GPU空档逐因解释、稳态负载曲线输出和matched采样开销AB。不得宣称step级performance decomposition PASS。下一步若继续该目标，需要仅针对当前主线调整已有runner，让CUDA profiler API仅覆盖稳态采样窗口或另做可验证同session时间锚；不能改已验收clean throughput，也不可使用新增通用trace框架。逐step ID若无现成scheduler NVTX，须明确缺口/按目标授权做最小必要的现有marker方案，而不是把FPM迭代顺序等同GPU sample归因。
