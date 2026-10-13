# T003 — Falcon 在线损失与 HiCache 实测阶段报告

状态：新T003采样尚未开始。T002离线结果仅为已有baseline；T003 online/HiCache/A-B均未完成。详见`plan.md`限定。

## A. Offline Forward vs online GPU Step

| 形状 | T002离线CUDA Event ms (n=3 mean) | 在线实际GPU Forward Step | 在线Batch/Graph / 同形状比较 |
|---|---:|---:|---|
| Prefill EXTEND 1K | 285.822 | UNKNOWN | UNKNOWN |
| Prefill EXTEND 4K | 1,113.026 | UNKNOWN | UNKNOWN |
| Decode Graph b1 | 13.678 | UNKNOWN | UNKNOWN |
| Decode Graph b2 | 15.018 | UNKNOWN | UNKNOWN |
| Decode Graph b4 | 15.875 | UNKNOWN | UNKNOWN |
| Decode Graph b8* | 17.440 | UNKNOWN | UNKNOWN |
| Decode Graph b16* | 20.665 | UNKNOWN | UNKNOWN |


a. `T002 CUPTI GPU Duration`及repeat分布在`../falcon-h1-3090-cupti-forward/report.md`；此处不混成Event数。b8/b16为离线Graph batch，非在线并发。

## B. Scheduler 与 GPU Busy/Idle 分解

| 并发 | Scheduler CPU/轮 | GPU Kernel Busy Union | 轮间GPU Idle | Queue Wait | Launch Delay | Tokens/s |
|---|---:|---:|---:|---:|---:|---:|
| c8 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | 已存R17 clean 311.515 tok/s；非本次测量 |
| c16 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | 已存R17 clean 395.708 tok/s；非本次测量 |

可复用同负载但有profiling观测的R17 Nsight/FPM窗口：c8 40×128、17.2449s、296.900 tok/s；c16 40×128、13.4028s、382.010 tok/s。汇总FPM forward event 17.0661s/13.2231s，runner记录的remainder估计0.17876s/0.17969s，API queue均值47.85/301.70ms。此remainder不是kernel-union idle，queue字段不是每step等待，均非matched clean A/B；不得因果归因。

## C. HiCache L1/L2/L3

| Tier | 有效命中率 / tokens | FULL KV+MAMBA恢复 | Host/Disk等待与迁移 | H2D完成→GPU Ready | Saved Prefill tokens / 净收益 |
|---|---|---|---|---|---|
| L1 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| L2 Host | UNKNOWN | NOT_QUALIFIED (current target restore not yet proven) | UNKNOWN | UNKNOWN | UNKNOWN |
| L3 Extent/Disk | UNKNOWN | NOT_QUALIFIED (read-back not yet proven) | UNKNOWN | UNKNOWN | UNKNOWN |

已通过的备份/ACK与durable write不重复认证、不作为restore证据。

## D. 最大三个损失来源与优化 A/B

| Rank | Loss source | Decisive online evidence | Optimization A/B |
|---:|---|---|---|
| 1 | UNKNOWN | NOT_RUN | NOT_RUN |
| 2 | UNKNOWN | NOT_RUN | NOT_RUN |
| 3 | UNKNOWN | NOT_RUN | NOT_RUN |

## E. Commit/push 与未解决问题

| 项目 | 当前状态 |
|---|---|
| T002离线七形状基线 | DONE, reused; no rerun |
| T003当前主线GPU在线采集 | NOT_RUN |
| HiCache L2完整恢复 | NOT_QUALIFIED |
| HiCache L3 read-back/restore | NOT_QUALIFIED |
| 优化/A-B/回归 | NOT_RUN |
| T003 commit/push | NOT_RUN |
| RTX 3090 当前占用 | preflight pending |

原始证据索引：T002 `control/falcon-h1-3090-cupti-forward/`; R17 NCU/NSYS `control/falcon-h1-3090-hicache-perf/runs/R17-20261012T0100Z/`; HiCache R7C/R11/R15 `control/falcon-h1-3090-hicache-perf/runs/` 与目标`falcon-h1-3090-hicache-cache/`。本报告的空白均为未知/未测量，不是零。