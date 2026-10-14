# T003 — 在线 GPU Step 与 HiCache 闭环实测

## A. c8/c16 在线逐轮 CPU/GPU/Idle 时间分解

| 并发 / 在线shape | n | Scheduler forward NVTX wall P50/P95 (ms) | FPM CUDA Event P50/P95 (ms) | GraphLaunch API→首个GPU kernel P50/P95 (ms) | Graph kernel interval union P50/P95 (ms) | 相邻graph间无kernel/memcpy记录时间 P50/P95 (ms) |
|---|---:|---:|---:|---:|---:|---:|
| c8 Decode b8，Graph replay | 569 | 5.266 / 6.235 | 17.149 / 17.346 | 13.493 / 13.847 | 17.001 / 17.192 | 0.030 / 0.042 |
| c8 Decode b8，非Graph尾段 | 51 | 5.35 / 7.24 | 17.215 / 17.337 | N/A | 约17.0（kernel interval并集） | N/A |
| c16 Decode b8，Graph replay | 84 | 4.919 / 5.405 | 17.123 / 17.272 | 13.765 / 14.042 | 16.977 / 17.063 | 0.031 / 0.040 |
| c16 Decode b8，非Graph尾段 | 44 | 4.79 / 5.10 | 17.209 / 17.319 | N/A | eager-kernel可由NVTX correlation join，但不在本次graph-launch延迟列 | N/A |
| c16 Decode b16 | 256 | 5.052 / 5.903 | 20.611 / 36.276 | 17.156 / 30.731 | 20.463 / 36.139 | 与b8相邻全局gap合并，见下方 |
| c8 Prefill（batch/token可变） | 10 FPM / 12 step | 239.194 / 253.062 | 284.738 / 806.151 | N/A（非Graph） | 279.323 / 562.001* | N/A |
| c16 Prefill（batch/token可变） | 7 FPM / 10 step | 239.879 / 286.231 | 559.571 / 714.368 | N/A（非Graph） | 508.707 / 559.548* | N/A |


definition：NVTX wall 是 scheduler `_run_batch_impl` 外围 range 的主机墙钟区间，不是纯CPU线程运行时间；scheduler CPU active time 未直接测得。Decode 的GraphLaunch通过**同一CUDA Runtime `correlationId`**连接其kernel活动，再以GraphLaunch API start位于同scheduler线程NVTX step range内唯一归属；Graph Node ID未作为replay身份。GraphLaunch→first kernel延迟包含已在GPU队列中的先前工作，故不是纯driver launch overhead。Graph kernel union按所join kernels的时间并集计算。相邻replay间“无kernel/memcpy记录”先取Graph GPU execution边界之间的gap，再扣除同区间全部CUDA kernel及memcpy union；仍不包括未被这两类活动表覆盖的设备工作，故不称绝对GPU idle。全程P50/P95分别统计，不把重叠时间重复累计。

*Prefill没有CUDA GraphLaunch；该项是按其NVTX range中同一进程/线程Runtime correlation归属的kernel interval union，FPM缺失的step不计。Prefill range可能包含主机准备、设备等待与forward，不作纯模型CPU时间解读。

整请求窗口（仅c8/c16请求的manifest wall start/end）汇总：

| 并发 | 请求窗口 | Scheduler NVTX steps / FPM匹配 | GraphLaunch→step唯一join | Kernel interval union | Memcpy interval union | Kernel+Memcpy并集 | 未被kernel/memcpy覆盖的窗口时间 | 1kHz整卡SM/Tensor/DRAM读/写均值 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| c8 | 17.0924 s | 632 / 630 | 569 (Decode) | 13.4872 s | 47.14 ms | 13.5275 s | 3.5649 s | 64.98% / 13.92% / 43.61% / 6.25% |
| c16 | 13.3152 s | 394 / 391 | 340 (Decode) | 10.0477 s | 31.57 ms | 10.0749 s | 3.2403 s | 65.04% / 14.50% / 39.73% / 8.10% |

GPU metrics是整卡区间均值，不分摊到request或step。未被两类CUDA活动覆盖的时间**单独列出**，不推定全为idle、scheduler、queue或launch成本。Nsight `GPU Active` 该计数器恒100%，不作为SM活跃率；SM/Tensor/DRAM使用单位为throughput百分比的GA10x metrics。Nsight 1kHz配置下窗口样本数分别17,093及13,316。

### 逐轮身份和FPM缺失调查

Graph相关字段核对：两份SQLite均**没有** `CUPTI_ACTIVITY_KIND_GRAPH_TRACE`、`CUDA_GRAPH_EVENTS` 或graph-exec identity表；有 `CUDA_GRAPH_NODE_EVENTS`，但事件类型只有“Graph Node Creation”，不编码replay实例。Kernel `graphNodeId`只能指静态node，不能独自识别每次执行。因此采用实际存在的 `cudaGraphLaunch_v10000` Runtime记录（其`correlationId`与该replay kernel records相同），结合同一`globalTid`、GraphLaunch API start在唯一NVTX iteration range内的包含关系。请求窗口569/569（c8）与340/340（c16）GraphLaunch都唯一归属step；correlation到kernel记录也全部存在。基于该硬件/API证据已完成Decode Graph-to-Step闭合，无需在生产forward添加新的replay marker。

FPM与scheduler NVTX窗口差额不是Decode缺失：完整capture中NVTX/FPM matched为c8 661/664、c16 403/406。差额全为Prefill EXTEND：c8 iter143/536，c16 iter14/147/278。它们各自在SQLite中有Prefill NVTX range、eager CUDA runtime calls以及1,862或2,235条kernel活动，故是**实际完成的forward，但FPM记录缺失**，不是非forward iteration。当前collector在GPU DeviceTimer `_report()`观察到累计`wall_time==0`时会直接return、不发布FPM；这与小Prefill forward的异步Event尚未ready时被延后/最终零累计的实现路径相符，但具体事件轮询竞争没有单独实验确认，列为推断。iteration 12等capture窗口外记录被manifest请求窗口排除，不计入窗口缺失数。

### 带宽和在线shape

Nsight Decode replay P50/P95及同Batch T002离线 CUDA Event均值：c8 online b8 17.149/17.346 ms 对 offline 17.440 ms；c16 online b8 17.123/17.272 ms 对offline 17.440 ms；c16 online b16 20.611/36.276 ms 对offline 20.665 ms。Nsight replay kernel union P50比FPM Event稍低，二者边界不同；上述为同batch近似比较，不是同session或clean A/B。

GraphLaunch API→首kernel P50约13.5–17.2 ms，显著包含前一GPU队列尚未完成时的排队；将其直接解释为CPU launch delay会错误。在线window中 Decode Graph执行并集间隔的中位无kernel/memcpy记录时间约0.03 ms；另有c8 51轮、c16 44轮Decode b8在窗口尾段未调用`cudaGraphLaunch`，但它们有FPM及分别471/400条eager kernel记录，FPM Event P50/P95约17.22/17.34 ms及17.21/17.32 ms，属于真实非Graph Forward而非非Forward事件。Graph API join完整覆盖其余Decode replay。最大Graph间隙包含请求阶段转换（c8 283 ms/c16 298 ms）及采集尾界，不能当steady inter-step idle。其余Gap时间分布和逐轮values可由`step-join.json`及SQLite复算。

## B. Prefill/Decode实际Batch与T002离线对照

| 并发/阶段 | 实际在线Batch及step数（40请求窗口） | Prefill tokens或Decode workload | T002同Batch CUDA Event均值 | 在线GPU时间（FPM CUDA Event或Graph kernel union P50/P95） | 解释 |
|---|---|---|---:|---|---|
| c8 Prefill | b1=4, b2=2, b3=2, b5=2, b6=2；12 steps，10条FPM | Extend tokens可变，含2048-token chunk及尾chunk | b1 EXTEND 1K基线285.822 ms；非同token shape | FPM中可观测range时长P50/P95 239.194/253.062 ms；GPU Event仅10条，P50/P95 284.738/806.151 ms | 含真实变长负载及scheduler/设备timer累计边界，非固定1K/4K配对 |
| c16 Prefill | b1=4, b2=1, b3=1, b5=2, b6=2；10 steps，7条FPM | Extend tokens可变，含2048-token chunk及尾chunk | b1 EXTEND 1K基线285.822 ms；非同token shape | FPM可观测range wall P50/P95 239.879/286.231 ms；GPU Event 7条，P50/P95 559.571/714.368 ms | 3个FPM缺失step有CUDA kernel活动；不把小range wall当GPU时长 |
| c8 Decode | b8=620 steps | 固定40请求×128输出 workload | b8 offline 17.440 ms | 全部FPM n=620 P50/P95 17.155/17.356 ms；Graph union n=569 P50/P95 17.001/17.192 ms；eager尾段51轮FPM 17.215/17.337 ms | 尾段51轮有eager kernel records，是实际非Graph Forward |
| c16 Decode | b8=128, b16=256 steps | 固定40请求×128输出 workload；最大活跃请求16 | b8 17.440 ms；b16 20.665 ms | b8全FPM n=128；Graph union n=84 P50/P95 16.977/17.063 ms，eager尾段44轮FPM 17.209/17.319 ms；b16 Graph union n=256 P50/P95 20.463/36.139 ms | b8尾段44轮为有eager kernel活动的非Graph Forward；与b16分列 |

Prefill在线是变量batch/长度；不能由batch size自身推断对应T002固定1K/4K prompt。T002 Decode是孤立real Falcon Graph forward，在线是Scheduler驱动的同类Graph batch，仍然是不同执行上下文；没有clean matched A/B及非等价结论不用于归因。

## C. L1/L2/L3命中率、迁移量及分层耗时

| 层 | Lookup/Match | 有效命中Tokens | Backup/Eviction/Admission/等待 | 实际迁移Bytes/Duration | DMA完成→GPU Ready / Scheduler可运行等待 | FULL KV+MAMBA联合恢复 | Saved Prefill / 净成本 |
|---|---|---|---|---|---|---|---|
| L1 GPU | UNKNOWN | UNKNOWN | UNKNOWN | 不适用（同卡复用，不代表零成本） | UNKNOWN | UNKNOWN | UNKNOWN |
| L2 Host | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | **NOT_QUALIFIED** | UNKNOWN |
| L3 Extent/Disk | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | **NOT_QUALIFIED** | UNKNOWN |

这两次Falcon profiling manifest明确 `hicache: off`，因此没有本次HiCache命中/成本测量；不得用disabled workload的零或历史ACK构造hit rate。R15 node 26旧证据表明FULL+MAMBA backup Host commit、同步ACK及L3 durability存在，但其`device_detach_seen=false`、`component_tiers=[]`、`expected_release_count=0`、queues empty，随后以`invalid_identity` retire；备份成功不等于有效Host/Disk恢复。R7C历史L2 restore为旧run，不能替代当前dirty Runtime/current-mainline验收。

## D. 最大三个可量化损失来源、优化和 A/B

| Rank | 来源/可量化现象 | 因果结论 | 优化/A-B |
|---:|---|---|---|
| 1 | c8/c16窗口未被kernel+memcpy区间覆盖的时间分别3.565/3.240 s | 这是可量化的未归因预算，不等于GPU idle或Scheduler；无法继续细分为CPU、队列、设备待机，不能列为已确认loss source | 未启动；先从既有Scheduler线程/事件证据闭合 |
| 2 | c16 b16 Graph kernel P95 36.139 ms，较P50 20.463 ms高约15.676 ms；其FPM P95 36.276 ms | 是已测尾延迟，不证明来源（设备竞争、系统频率/上下文、图内调度皆未分开）；一个capture不能作因果归因 | 未启动；无 matched A/B |
| 3 | 在线40请求运行共5条Prefill step没有FPM记录，但Nsight有实际forward kernels；DeviceTimer累计为零时collector跳过发布是源码已证路径 | 是遥测缺失，不是Forward未执行；优先级是修复/定向验证telemetry，而非推断性能损失 | 未改产品Telemetry；未启动修复/性能A-B |

T002 NCU/roofline仅作为可复用kernel evidence，不能把aggregate SM/DRAM percentage变成主瓶颈裁决。由于HiCache本轮关闭、scheduler纯CPU active时间也未测，三方向成本尚未完整排序；本次未启动未经证据支持的优化。

## E. 原始证据、状态及提交

| 项目 | 状态/位置 |
|---|---|
| c8 40×128 capture | `runs/t003-nsys-c8-t94-n40/`（SQLite、report、manifest、FPM、NVTX join、request result） |
| c16 40×128 capture | `runs/t003-nsys-c16-t95-n40/`（同上） |
| T002离线基线 | `../falcon-h1-3090-cupti-forward/report.md`；不重跑 |
| R15/R7C/R11 Cache evidence | `../falcon-h1-3090-hicache-perf/runs/{R15-20261011T0400Z,R7C-20261010T0400Z,R11-20261010T1600Z}/` |
| L2/L3 current-mainline recovery | NOT_QUALIFIED / NOT_RUN |
| 同负载优化/A-B | NOT_RUN（无归因充分的瓶颈） |
| 本次进度提交 | `729c0708c`（online table初版/report）；当前Graph-to-Step补充待精确提交 |
| RTX3090 | GPU及任务进程检查空闲；1 MiB / 0% |
