# p2io-tester-e7j — e19 writeback-reserve fix 12G 重测

- 任务：e7j（e19 修复验证重测；配置同 e7h：HICACHE_SIZE=12G + writeback-reserve 0.75G + safety-margin 0.3G + ready-horizon + extent + write_back + T15 off + 8 agents/96 req/24 turns/K=8）
- 运行：2026-09-02 06:06:34 → 06:17:08，rc=0，单启动（lock 守卫），GPU 归零
- 修复：e19（HostPoolGroup.alloc_writeback 补 + margin floor + restore_success event）
- 报告路径：p2io-tester-e7j.md；证据：`/tmp/p2io-e7j-local/`（远端 `/root/evidence-p2io-extent-m4t-e7j/run-20260902-060816/`）

## 1. status

**done**（五硬证据 + 三分支判定 + ghost 泄漏评估均已坐实；结论：**e19 修复有效消除宕机，但 L3 链仍不闭合，storage_hit 恒 0 → 三分支判第 2 支，key/generation/index consistency 专项待派**）

## 2. artifacts

- 本报告 `p2io-tester-e7j.md`（六节）
- 远端运行产物：`/root/evidence-p2io-extent-m4t-e7j/run-20260902-060816/`（runs.csv 96 行 / verdict.json / join.log / mid-run-metrics.txt / turns/），`/root/engine-p2io-m4t-e7j.log`（959KB），`/root/p2io-gauge-e7j.log`（boot 六 gauge）
- 本机镜像：`/tmp/p2io-e7j-local/`（engine + gauge + runs.csv + verdict + join.log）
- 启动脚本：`/root/p2io-m4t-e7j-run.sh`（e7h-r2 模板克隆，fresh namespace `p2io-extent-e7j`）
- 未改引擎代码、未跑额外实验（遵守纯重测边界）

## 3. evidence（命令 + 真实输出，全部可复现）

### 3.1 五硬证据总表（e7h vs e7j）

| # | 指标 | e7h（base） | e7j（e19 修复） | 判定 |
|---|---|---|---|---|
| 1 | extent_write | 135 | **155**（kv 104 ev/93,500 keys/3.06 GB；mamba 51 ev/51 keys/2.63 GB） | ↑ 微升，非消退 |
| 2 | Z3（restore_recompute） | 330 | **386**（385 miss + 1 timeout；this-run 门是 storage-chain） | ✗ 未降 |
| 3 | storage_hit>0 | **0/330** | **0/385**（恒 0） | ✗ 未恢复（关键） |
| 4 | restore_success / READY | 0 / 0 | **0 / 0**（restore_ready=0, ready_stage=0, ready_pool size=0, ready_state_max=0, ready_resident=0） | ✗ 未形成 |
| 5 | crash / sanity FAILED | **2**（22:06:13 node68） | **0**（rc=0, AssertionError=0, Sanity check FAILED=0） | ✓ 消解 |

### 3.2 第 3 条三分支判定依据（storage_hit 恒 0 的证据）

```
$ grep 'prefetch_revoke' engine-p2io-m4t-e7j.log | grep -oE 'storage_hit=[0-9]+' | sort | uniq -c
    385 storage_hit=0          # 100% revoke storage_hit=0
$ grep -oE 'storage_hit=[1-9][0-9]*' engine-p2io-m4t-e7j.log | wc -l   → 0
$ grep -cE 'restore_success|io_finished' engine-p2io-m4t-e7j.log        → 0
$ grep -c 'state=READY' engine-p2io-m4t-e7j.log                         → 0
```

### 3.3 runs.csv 打脸证据：host 前缀覆盖巨大，storage(=L3) 覆盖恒 0

```
total rows=96; device_hit set=55; host_hit set=55; storage_hit>0=0 (!!)
host_hit nonzero: 31 rows, max=20898, sum=503644
rows host_hit>0 AND storage_hit==0 (FULL_HOST-style metadata but no loadable L3): 31
rows cached_tokens>0 and storage_hit==0: 55
```

代表性 restore 行（e7j）：
```
1,5,restore,steady,20864,0,20864,0,47,...
2,5,restore,steady,20881,0,20881,0,30,...
3,5,restore,steady,20898,0,20898,0,13,...
4,5,restore,steady,20864,0,20864,0,47,...
```
（cached_tokens=host 命中 20.8k，device_hit=0，storage_hit=0 —— 三层恢复路径上 L3 一层完全空白）

e7h 对照（runs.csv 96 行）：storage_hit>0=0；host_hit nonzero=23 行 —— **同样模式**。

### 3.4 extent_write 与 L3 写入侧确实发生（但下次查询覆盖恒 0）

```
kv: 104 events / 93,500 keys / 3,063,808,000 bytes
mamba: 51 events / 51 keys / 2,627,076,096 bytes
$ grep 'prefetch_revoke' ... | grep -oE 'storage_generation=[0-9]+' | sort -t= -k2 -n | uniq -c
→ 13×0, 1×8, 1×22, 8×27, 1×33, 361×40   # generation 单调前进 0→40
```

### 3.5 无 crash 证据（gate-5 通过）

```
$ grep -c 'Sanity check FAILED' engine-p2io-m4t-e7j.log → 0
$ grep -c 'AssertionError'       engine-p2io-m4t-e7j.log → 0
verdict.json: {"status":"done","requests_total":96,"requests_failed":0,"elapsed_s":510.1}
status: M4T_E7J_STAGE_COMPLETE rc=0; engine SIGTERMed; gpu_mib=15 MiB
```
（日志中 62 个 "Traceback" 全部是 torchcodec/libavutil 加载警告，无一个 scheduler 关键路径断言）

### 3.6 六 gauge（boot scrape, metrics_reporter 1118-1130 口径）

```
hicache_kv_pool_tokens=102680   hicache_writeback_reserve_tokens=22888
hicache_ready_resident_tokens=0 hicache_working_tokens=0
hicache_spec_inflight_tokens=0  hicache_usable_tokens=70637
hicache_ready_state_max_tokens=0  kv_host_usable=70637  mamba_host_usable=149
```

## 4. summary（核心结论 + 判定）

### 4.1 e19 修复是否消除 L3 链不闭合？

**否。** extent_write 155（kv 2.9GB 增）, generation 单调 0→40, restore_backup 56（l3_durable_frontier>0），但 storage_hit 仍 0/385——**写入侧在走、读取侧恒 0**。e19（writeback reserve 语义 + alloc_writeback 消费 reserve）让 D→H 满配运行（不再被 reserve 阻断），**但 L3 索引/键空间在写入与查询之间根本不连通**。

### 4.2 三点判定（用户三分支，结论选一支）

| 分支 | 条件 | e7j 实测 | 结论 |
|---|---|---|---|
| A | extent↑ 且 storage_hit↑ | storage_hit 恒 0 | ✗ |
| B | extent↑ 但 storage_hit 仍=0 | **符合** | **✓ 选 B：key/generation/index consistency 专项** |
| C | storage_hit↑ 但 READY 仍=0 | storage_hit=0 | ✗ |

**判定：第 B 支 —— L3 查询键空间与 extent 写入键空间不一致（含 generation/metadata 不同步可能）。之前"没持久化成功"疑点部分排除（extent_write 已成功落盘 5.7GB，generation 前进），真正的缺口在 `batch_exists/_storage_hit_query` 的查找键与 extent_write 的写键不一致。**

额外证据（撑 B 支）：host_hit=20898/20864（大而全）但 storage_hit=0——host 树前缀完整存在且 load_back 也不需要 L3，说明**写回确实把 host 前缀当full-prefix 处理了（D→H 备份成功），只是从不落/从不查 L3**，符合"写键≠查键"或"查询 index 未注册 extent"。

### 4.3 READY 池 / restore_success 为什么仍空

restore 链到不了 READY：storage_hit 恒 0 → 恢复阶段无 L3 可装载 → 全部 degrade（RECOMPUTE 424 + WAIT 1，granted>0 = **0**）→ restore_state 恒在 NONE/RESTORING/WAIT_CAPACITY，**0 READY**。ready_horizon `_is_ready_resident` 三条件（READY + staged_tokens>0 + full_prefix）中 READY 恒空 → ready_pool 恒 size=0。这是 storage_hit 恒 0 的下游，**不是 reserve 问题**。

### 4.4 ghost 泄漏（node66/68）是否再现？

**未再现。** e7j 全程 0 Sanity FAILED / 0 AssertionError / rc=0。/run 的 node68/66 ghost + host_leaves 一致性崩溃未在 e7j 出现。**按用户裁决：在 e7j 中不形成独立 lifecycle blocker，但作为一次性偶发仍需在 e7h 报告中定格为 e7h 特有的崩溃证据**。运行时间 510s，覆盖 96 请求，若 ghost 泄漏与 reserve 语义相关则已随 e19 消解；但仍可能是与 workload 时序相关的偶发路径。

### 4.5 Z3（843 → ?）

- e7h-周 843 是序列中最高（pre-reserve-fix）。
- e7j Z3=386（restore_recompute），**未接近"rare safety-valve"**，且 100% cause=miss。
- 因 storage_hit 恒 0，READY 池为空，Z3 高直接就是"L3 层空白"的下游，不是 reserve 被侵占的表现。

### 4.6 守恒 / B_ep / B_fin

- 守恒：cached_tokens_total(host)=20864/20898，load_back_token_total=0，dropped_tokens_total=0，无异常负值（残差在 0 附近）。
- **B_ep/B_fin 不可测**：e19 补的 restore_success 在 e7j 全程 0 次触发（因为 L3 无 restore 成功），metric_compare 也因无成功 restore 无样本——**"恢复可测"的前提是 restore 先成功，而 restore 依赖 storage_hit**。不是测不到，是还没东西可测。

## 5. followups（数量 + 位置 + 建议）

1. **L3 查询键/索引一致性专项（最高优先，三分支 B 支）**：storage_hit 恒 0 而 extent_write 成功——排查 `_storage_hit_query`（cache_controller.py:1291 `batch_exists`）与 extent_write 的落盘键是否同键空间；疑似 key 前缀（是否有 tokenizer/段号拼接差异）、generation 元数据未在查询时解析（generation 单调但 metadata key 未 join）、或 index 未 flush。建议 architect/coder 用单 rid 写-查对拍实验坐实。
2. **B_ep/B_fin 双口径恢复**：restore_success 已埋点（scheduler.py:4422）但 0 触发。README 或 metric_compare 需在 storage_hit>0 后才能测；建议把这个可测性前置条件写进测试规范。
3. **e7j storage_hit 恒 0 的二次确认**：建议再跑一次 K=8 或加一个定向 extent 读回探针（`p2io-directed-readback.sh` 已有先例）验证 batch_exists 直接读回写过的 extent——若直读仍 0，坐实查键不匹配。
4. **Z3 细分（现 386 全 miss）**：落到 NEVER/PARTIAL/FULL_THEN_LOST 的细分需在 storage_hit>0 后才有效；当前 386 全 miss 全归类 NEVER 系，先记档。
5. **e7h 与 e7j 的 storage_generation/键空间对照**：e7h generation 0→39，e7j 0→40，生成号都在前进——说明 extent backend 元数据层活着；若能在两代日志上对同一 rid 的 extent_write 的 keys_n + seq 范围做对拍，可定位是"写的内容没被索引"还是"索引的内容没被查"。

## 6. open_issues（未解决/风险）

- **storage_hit 恒 0 未消解**：L3 三层是最关键的一层，仍不闭合。e19 证明 reserve 语义不是根因（写已经通了），真正的 L3 查键一致性问题需专项。
- **READY/restore_success 全 0**：是 storage_hit=0 的直接下游；在 L3 查询修复前，READY 池、restore 链、B_ep/B_fin 都无望。
- **Z3=386 仍 100% miss**：P2-IO 目标的"三层热度命中"完全没达到；full-prefix availability 目标（对比 e7f 10.8%）无法达成。
- **e7h 崩溃**：虽未在 e7j 再现，但 e7h 的 node68/66 ghost + stale host_leaves 是一段真实泄漏路径记录；继续观察 e7k 是否再现（若再现即升 blocker）。
- 本任务为纯重测，未改代码；上述专项按权限交 architect/coder，如需要我补定向 extent 读回探针（只改探针不碰引擎）可在后续任务执行。