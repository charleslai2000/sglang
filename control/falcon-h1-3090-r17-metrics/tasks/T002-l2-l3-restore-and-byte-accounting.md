# T002 — HiCache L1/L2/L3 恢复时延与备份账本

Status: ACTIVE
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
已检索 R7C 与 R11 原始 driver。R7C `l2_driver.py` 是确定可复用的目标 L2 workload：固定输入1920 tokens，prefix SHA256 `987fd70c…`；target node/hash精确匹配、D→H operation ACK闭合，压力后要求 FULL KV与MAMBA两component device detach，然后 Host source>0且greedy `[10553]`一致。R7C按 metrics记录 load-back：KV 1,792 tokens、MAMBA 2 states、`load_back_bytes_total=359,456,768`；需要核实其 bytes归属/operation 和计时边界，不能直接认为都是 DMA字节或该次单操作。

R11 `extent_driver.py` 确认同 target FULL+MAMBA durable storage submit/ACK PASS：1792 KV pages + 1 MAMBA page，`kv_durable=true`/`mamba_durable=true`。但它在19个 competitor后未看到目标 KV Host detach，抛 `target KV Host eviction not observed within 19 unique competitors`，故其后的 storage read/restore代码没有执行；R11只证明写入，不证明L3读回。R17当前 source是否与R7C/R11完全一致尚需audit。

## Interim results — R17 fresh L2 attempt (NOT QUALIFIED)
在隔离 `/tmp/sglang-r17` 冻结代码、模型 revision、全新 `T38C_RUN_ID=falcon-r17-final-l2-20261011T102121Z` 和空 `r17-l2-probe.jsonl` 下运行复用的 R7C FULL+MAMBA target。当前服务本轮 probe 确有 target `build_complete`（node 26/hash `721e82…`）及 `backup_host_commit`（`kv_transfer=true`,`mamba_transfer=true`,`host_tokens=1792`）；但 build registration 时的 `residency_barrier_outcome` 为 `detach_not_sealed`，`component_tiers=[]`、`expected_release_count=0`。关闭 target session 后四个 competitor 请求虽让 metrics `mamba_host_usable_tokens=91`，target 的设备释放证据链没有闭合。Driver 打印的 detach event id 属于旧 R7C run (`falcon-r7c-l2-...`)，本轮 probe 中 target 没有一条 `residency_detach` 记录，说明不能拿该数组当本轮 detach 证据。最终 restore 请求 greedy `[10553]` 与 reference 相同，但 `cached_tokens_details={device:1792,host:0}`，是 L1 device hit，不是 L2；因此 R17 L2 **未通过**，也没有本轮 Host H→D bytes/duration/DMA 完成证据。遗留 `l2_driver.py` 中输出的旧 run-id event id 揭示 R7C driver 的事件过滤仍绑定旧 run identity；修复应先在新服务/新 target 构建之前完成，并增加 event run/source/context 的硬断言。R17 初始预填请求因 prompt 与试图复用的另一 tokenizer/workload tokenization 对齐不一致，观测到 `cached_tokens=0`；不能报作 L1 hit。L3仍 `NOT_QUALIFIED`，R11旧 ACK不覆盖本次恢复。

## Remaining
修复并单测 L2 probe identity/ownership 与 target-session eviction 前提（一次新服务和新 target之前完成）；确认本轮 target 的 FULL KV 与 MAMBA 真实 device detach、Host source>0、H→D transfer/DMA bytes/duration和 greedy parity后方可判定 L2。L3从R11既有持久化实现出发，但必须先证明R17目标Host eviction与当前 storage mapping，再执行并计量 read-back及FULL+MAMBA恢复；否则标记`NOT_QUALIFIED`。完善25.82GB D→H唯一operation/ACK/bytes attribution，现有Host吞吐差异不得归因 HiCache。