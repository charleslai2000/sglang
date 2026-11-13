# T002 — HiCache L1/L2/L3 恢复时延与备份账本

Status: READY
Work area: experiments；证据落在隔离 R17 worktree 的既有 `runs/R17-*` 范围

## Objective
复用既有验收用例与 R7C 成功 L2 restore workload，取得可归因的 GPU L1、Host L2 H→D 和 Disk L3→Host→GPU 有效命中、字节、时延与 KV/MAMBA 恢复正确性；解释 R17 的 25.82 GB D→H backup。优先修复 L3 read-back/restore，继承 R11 已通过的持久化证据，不重做写入认证。

## Inputs
- `goal.md`、`plan.md`
- R7C 通过的 FULL+MAMBA L2 Host-source/H→D restore 和 greedy token `[10553]` 证据、driver 与源码边界（从仓库历史/证据检索定位）
- R11 durable ACK/persistence evidence；R17 `R17-METRICS-STATUS.md`、Host c8 t5 原始结果、运行窗口指标与现有 telemetry source
- 隔离基线 `/tmp/sglang-r17`，commit `20c837f1a3daaec47508feaecf5514dd586c636c`

## Completion
- 逐层列 logical lookup、effective reused tokens、按 prompt token 加权命中率、新 prefill tokens、saved prefill tokens；cache restore 未完成的 lookup 不记有效命中。
- L1 确认复用设备驻留并有 KV+MAMBA 正确性；L2 完成目标 device eviction → Host source → H→D，记录真实 bytes、duration、CUDA DMA completion 和 Restore-complete→scheduler-ready；输出重复一致。
- L3 从现存 durable 写入出发完成 storage read、FULL+MAMBA Host/GPU 恢复和 greedy 一致；分开测 lookup、IO queue、buffered/page-cache或物理 I/O、Host-ready、H2D、GPU-ready；物理设备 I/O 不可辨时准确标注。
- 对 25.82GB D→H 按 FULL KV/MAMBA、重复/唯一 operation 与 ACK、async 与传输时间分项核算；只基于确切 attribution，说明 GPU/PCIe/Host 带宽影响，区分缺证据项。
- 原始 event/metrics/请求证据可重算，correctness tests/driver/config/artifact provenance齐全。L3 restore 未通过则记录具体失败 seam 与证据，明确性能 `NOT_QUALIFIED`。

## Result
未开始。当前 R17 短请求 workload 对所有 cache tier 命中均为零，25.82 GB 是 aggregate D→H，H→D 计数缺失；不能用该样本推导缓存性能。R7C Host 恢复已独立 PASS，可复用其目标 workload/恢复路径。

## Remaining
检索 R7C/R11 原始 driver 与代码版本，审计到 R17 frozen source；先复用成功 L2 restore，再依据历史证据修复 L3 read-back/restore。