# T003 — Falcon 在线损失与 HiCache 实测阶段报告

状态：在线 c8/c16 Nsight/FPM workload 已采集；HiCache L2/L3 与瓶颈优化未完成。此报告仅列本次 profiling 观测，未将 profiling throughput 与 clean runs 混作 A/B。

## A. Offline Forward vs online GPU Step

| 形状/负载 | T002 离线 CUDA Event ms (n=3 mean) | 在线观测 | 边界 |
|---|---:|---:|---|
| Prefill EXTEND 1K | 285.822 | UNKNOWN（本次在线不是固定1K；Prefill batch/token形状变化） | 不能直接比较 |
| Prefill EXTEND 4K | 1,113.026 | UNKNOWN（本次在线不是固定4K） | 不能直接比较 |
| Decode Graph b1 | 13.678 | 本次真实40请求窗口未观察到 | 窗口外warmup/尾部的迭代未用于统计 |
| Decode Graph b2/b4 | 15.018 / 15.875 | 本次未观察到 | UNKNOWN |
| Decode Graph b8 | 17.440 | c8 17.652 ms (n=620); c16 17.585 ms (n=128) | 对应batch实测，但服务/调度上下文与离线不同 |
| Decode Graph b16 | 20.665 | c16 21.547 ms (n=256) | profiling workload；FPM Event与离线 Event同类但不是配对试验 |

在线统计严格限制到manifest wall start/end经capture-start epoch转换出的真实40请求窗口。窗口内step为c8 632（Decode b8=620，Prefill=12）、c16 394（Decode b8=128、b16=256，Prefill=10）；不纳入Nsight workload前warmup或capture后尾部。窗口内FPM交集c8 630/632（缺143、536），c16 391/394（缺14、147、278）；原始完整capture交集分别661/664、403/406。统计未填补缺失记录。完整FPM逐step记录、NVTX、CUDA timeline位于各自`runs/t003-nsys-.../`。

## B. Scheduler 与 GPU Busy/Idle 分解

| 并发 | Workload wall | Nsight profiling output tok/s | CUDA kernel execution union | Union占窗口 | 无kernel区间（窗口减union） | GPU Event sum (FPM) | API queue mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| c8 | 17.0924 s | 299.548 | 13.4872 s | 78.91% | 3.6053 s | 16.9131 s | 47.17 ms |
| c16 | 13.3152 s | 384.523 | 10.0477 s | 75.46% | 3.2675 s | 13.1129 s | 297.98 ms |

“CUDA kernel execution union”是Nsight kernel start/end区间在客户端 workload wall window 内的并集，重叠只计一次；无kernel区间是同一窗口内没有已记录kernel执行的时间，不能归因Scheduler、queue、launch或GPU未工作，也不等价于等待请求的时长。Nsight kernel interval 尚未能按异步 CUDA Graph replay 可信地逐轮归属；旧 `analyze_nsys.py` 用runtime API start关联的per-step kernel union结果不合格，不用于本报告。FPM `gpu_forward_s` 是CUDA Event测量，不能用其和kernel union差额推断未归因GPU工作。

全局 1 kHz GA10x metrics 在 workload窗口内：c8/c16 SMs Active均值64.98%/65.04%，Tensor Active 13.92%/14.50%，DRAM Read Bandwidth Throughput 43.61%/39.73%，Write 6.25%/8.10%；这是整卡采样，不能映射到请求或单step。指标样本数17,093/13,316。该Nsight导出SQLite原始 `GPU_METRICS.value` 对时钟频率为Hz量级编码、对吞吐百分比为0–100数值；上面只报告单位明确的吞吐比例。Scheduler CPU per-step、实际queue wait、launch delay、Token Ready、按step的GPU idle原因仍UNKNOWN。FPM API queue均值是跨请求聚合，不是step queue wait。

Profile workload summary：c8 40×128输出、墙钟17.0924s、299.548 tok/s；c16 40×128、13.3152s、384.523 tok/s。与此前R17 clean TPS 311.515/395.708不同测量条件，不是matched profiling-overhead A/B，不推断差异来源。nsys捕获由 `--capture-range=none`覆盖进程生命周期；Nsight metrics以manifest epoch start/end转换为capture-relative时间后裁 workload interval。每个SQLite含NVTX、CUDA runtime/kernel、CUDA graph-node、GPU_METRICS；kernel launch rows主要标为regular，虽有graphNodeId和graph-node记录，尚未建立完整逐轮异步replay对应关系。

## C. HiCache L1/L2/L3

| Tier | 有效命中率 / tokens | FULL KV+MAMBA恢复 | Host/Disk等待与迁移 | H2D完成→GPU Ready | Saved Prefill tokens / 净收益 |
|---|---|---|---|---|---|
| L1 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| L2 Host | UNKNOWN | NOT_QUALIFIED (current target restore not proven) | UNKNOWN | UNKNOWN | UNKNOWN |
| L3 Extent/Disk | UNKNOWN | NOT_QUALIFIED (read-back not proven) | UNKNOWN | UNKNOWN | UNKNOWN |

复用历史R15：backup/ACK及durable write存在，但实际目标device detach未发生（`device_detach_seen=false`、`component_tiers=[]`、`expected_release_count=0`、queues empty）；不是restore evidence。当前dirty Runtime生命周期尚未闭环；历史R7C不代替当前主线认证。

## D. 最大三个损失来源与优化 A/B

| Rank | Loss source | Decisive evidence | Optimization A/B |
|---:|---|---|---|
| 1 | UNKNOWN | 总窗口存在3.605/3.268s无kernel区间，但无可信逐轮CPU/queue/launch归属，不能排序成某一根因 | NOT_RUN |
| 2 | UNKNOWN | GPU SM/Tensor/DRAM metrics为整卡workload聚合；不能单独证明瓶颈 | NOT_RUN |
| 3 | UNKNOWN | Cache有效恢复与节省账本未验证 | NOT_RUN |

## E. 状态与待解问题

| 项目 | 状态 |
|---|---|
| T002七形状离线基线 | DONE, reused; no rerun |
| T003 c8/c16在线 Nsight + FPM capture | DONE (single profiled 40×128 capture each; per-step GPU kernel attribution incomplete) |
| CUDA kernel workload-window union / no-kernel intervals | MEASURED; strictly window-level, no per-step attribution |
| Per-step scheduler CPU / queue wait / launch delay | UNKNOWN |
| HiCache L2完整FULL+MAMBA Host restore | NOT_QUALIFIED |
| HiCache L3 read-back/restore | NOT_QUALIFIED |
| 优化/A-B/回归 | NOT_RUN |
| T003 commit/push | NOT_RUN |
| RTX 3090及服务 | 本轮检查为空闲（GPU 1 MiB, 0%；未发现本目标进程） |

原始证据索引：T002 `control/falcon-h1-3090-cupti-forward/`; c8/c16 Nsight、FPM、SQLite及逐step join `control/falcon-h1-3090-online-hicache/runs/t003-nsys-c8-t94-n40/`、`t003-nsys-c16-t95-n40/`; R17 NCU `control/falcon-h1-3090-hicache-perf/runs/R17-20261012T0100Z/`; HiCache R7C/R11/R15 `control/falcon-h1-3090-hicache-perf/runs/`及`falcon-h1-3090-hicache-cache/`。未完成项为unknown/not qualified，不是零。
