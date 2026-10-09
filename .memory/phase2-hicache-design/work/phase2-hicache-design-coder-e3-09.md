# P2-0a 前置勘察 — 19 项归因字段可得性矩阵（coder e3-09）

## status

**done** — 只读勘察完成，未修改任何引擎/工具文件。19 项矩阵逐项落证据（本机代码 file:line +
3090 实测日志样例 + upstream #32724/#35537 对照）。交付本报告。

## artifacts

- 本报告 `phase2-hicache-design-coder-e3-09.md`（唯一交付物；无代码/文档改动）
- 读入参考：plan.md、coder-e1-01/02、architect-e2-03/04、coder-e3-05/06、fetched-hicache-upstream.md、
  fetched-issue35537-batch-is-full-latch.md

## evidence

本机（sglang-3090-24g-hicache checkout）行级 grep + 局部 Read；3090 实测日志经只读 ssh
（root@175.155.64.171:24052，仅 cat/grep/awk 读 /root/evidence-p2b0-01/、/root/engine-p2b0-01.log、
/tmp/b15-probe.log、/root/sglang-b1-continuity 部署代码）。**部署代码与本地 checkout 关键行号
逐一对齐**（3451/3579/2520/2105/2912 五处一致），以下 file:line 对部署引擎同样成立。

关键 grep 命中（本地 checkout）：
- `batch_is_full`：schedule_batch.py:2084（字段定义）、scheduler.py 14 处（reset 3289/3308/3326/
  3452/3767/3836/5077；set 3483/3564/3569/3619/3623）
- `NO_TOKEN`：schedule_policy.py:507（枚举）+ 13 处 return；`PrefillAdder` 511
- `check_prefetch_progress`：unified_radix_cache.py:1983、scheduler.py:3579（FCFS 扫描内）
- `ongoing_prefetch`：unified_radix_cache.py:392/1847/1946/2100/2193/2245/2333/2402/2438/2458/2509-2519
- `prefetch_rate_limited`：cache_controller.py:1197-1215、unified_radix_cache.py:1751/1837/2409
- 7 探针 evt（`grep -rn '"evt": "pa_'` = 4 命中 scheduler.py:3917、unified_radix_cache.py:652/2821/2936；
  pb_* 3 处 cache_controller.py:984/129、unified_radix_cache.py:2893）
- t38c 门控：`/tmp/t38c-on` touch（unified_radix_cache.py:139-150），17 个 `_t38c_log({` 发射点

3090 实测样例：
- 引擎日志 `[2026-08-30 10:50:02] HiCache prefetch success req=a15b11a... completed=5248 matched=1787
  loaded=3461 occupied=0`（engine-p2b0-01.log:908，**部分恢复现场**）；成功行 ×6、Prefill batch ×1062
- **`batch_is_full` 全日志 0 命中**；`HiCache load_back failed` 0（prefill 模式）；`init_load_back`
  0 / `HiCache storage prefetch retry` 0（info 级不可见，log_level='info' 实测）
- b15 探针实样：pa_lb_init{rid,host_hit_length=3461,ts=1788058202.731}（:14092，rid=a15b...）→
  pb_load_submit{producer_id,n_tokens=6144,n_nodes} → pb_load_done{n_tokens,n_pending}（无 rid）；
  pa_batch{step_kind,batch_size,forward_iter,consumer_index}（无 rid）；pa_evict/pa_writing_check 同 02 表
- join.log v2 行（run-20260830-110016:1-2）：rid/device_hit=20864/host_hit=20855/storage_hit=0/
  new_tokens_est=47/ttft_s 等齐备；a15b... 行（:7）device_hit=24315/host_hit=0/storage_hit=3461
- server_args dump：schedule_policy='fcfs'、max_running_requests=8、log_level='info'、
  host_memory_mode='cache'（非 buffer_only）、hicache_storage_prefetch_policy='wait_complete'、
  hicache_storage_prefetch_retry_poll_interval=0（retry 机制该部署关闭）、page_size=1、enable_cache_report=True

## summary

### 19 项矩阵（字段 | 可得性 | 获取方式 | 不可得时的最小方案）

| # | 字段 | 可得性 | 获取方式（来源 file:line / evt 字段 / 公式） |
|---|---|---|---|
| 1 | RID / req_id | **直接** | join.log rid + x-request-id（driver 侧）；"HiCache prefetch success req=..."（unified_radix_cache.py:2104-2112）；pa_lb_init.rid（:2936-2938）；ReqTimeStats rid（schedule_batch.py:1855，--enable-request-time-stats-logging 配置开关） |
| 2 | waiting_queue_position | **不可得，需插桩** | 无任何日志含位置。现有最近似：Prefill/Decode batch 行 `#queue-req: N`（metrics_reporter.py:617，仅长度）。**插桩 I2**：scheduler.py:3551-3571 FCFS 扫描循环——admit 时打 `enumerate(self.waiting_queue)` 位置 + rid + running_bs（与 I4 合并一行）。客户端代理（派生）：同 run 内 ts_sched 升序在排请求计数——注意默认 fcfs 下队列=到达序（server_args.py:803 默认 'fcfs'，3090 实测确认），但 abort/retract 会扰动，代理≠引擎真值 |
| 3 | device/host/storage hit | **直接** | join.log cached_tokens_details{device,host,storage}（sglext，output_streamer.py:85-116 构造；3090 join.log 实测三字段齐）；引擎计数器 prefill_effective_tokens_total{mode=device_hit/host_hit/storage_hit/input}、cached_tokens_total{cache_source=}（metrics_collector.py:898-911/1272-1288）；storage_hit 亦在 "HiCache prefetch success loaded=%d" |
| 4 | prefetch: spawned? | **t38c 门控直接 / info 不可得** | t38c（touch /tmp/t38c-on，零引擎改动）：pc_outcome issue/attempt（prefetch_length）+ issued（unified_radix_cache.py:1816/1934，rid+1ms）。info 级无 spawn 日志；派生：出现 success 行 ⇒ 曾 spawn（但被拒/revoke 的 spawn 不可见）。精确 spawn 时间戳：**插桩 I6**（unified_radix_cache.py:1932-1937，1 行） |
| 5 | prefetch: io_completed? | **不可得，需插桩** | 无日志/探针在 io 完成时刻发射。最近似：t38c pc_get_v2（cache_controller.py:1164，IO 线程逐批）末批 ≈ io_done（近似，批次内偏差）。**插桩 I3**：unified_radix_cache.py:2518-2522（`ack.completed_req` 排空分支，scheduler 线程，1 行）或 cache_controller.py:1187-1193（IO 线程视角，1 行） |
| 6 | prefetch: scheduler_finalized? | **直接** | "HiCache prefetch success req=%s completed=%d matched=%d loaded=%d occupied=%d"（unified_radix_cache.py:2104-2112，info；dropped 变体 2106；3090 实测 6 行）。ms 精度：t38c pc_l3_host（:2021-2024，rid+completed_tokens+requested_tokens）。**注意**：buffer_only 模式下 _handle_prefetch_result 于 :2056-2061 提前返回 → success 行不发射（本部署 mode='cache'，不受影响） |
| 7 | completion→finalization latency | **半可得，需插桩 io_done 端** | finalize 时间点已有（#6：success 行 asctime 1s / pc_l3_host 1ms）。io_done 端缺失 → **插桩 I3**（同上）。配对：I3 行 ↔ success 行（或 pc_l3_host）按 rid。精度：logger 行需 SGLANG_LOG_MS=1（environ.py:333，launch env 零代码）或 b15 风格 ts 字段（1ms）。**关键背景**：本地代码已在 ack 排空点主动 finalize（:2518-2522，#32725 模式）→ 该延迟≈同步线程跳 + 一个 scheduler pass 边界，与 #32724 的 FCFS-scan 耦合延迟（~2.4s）不同量级，测量值预期小 |
| 8 | restore quota: requested_tokens | **H→D 直接；L3→H 需 t38c/插桩** | H→D requested = pa_lb_init.host_hit_length（探针 :2936-2938，3090 实测 a15b...=3461）。L3→H requested = prefetch_length：t38c pc_outcome attempt/issued 有（:1816/1934）；success 行无 requested（只有 completed/matched/loaded）→ 精确值需 **I6** 或 t38c-on |
| 9 | restore quota: granted_tokens | **直接** | L3→H granted = success 行 loaded=%d（:2104；实测 3461/20855）；H→D granted = pb_load_done.n_tokens（:2893-2895，**无 rid**，按 ts+n_tokens 与 pa_lb_init 配对，02 已述）；或 load_back_tokens_total 计数器 Δ（metrics_collector，join.log 内嵌实测 3461） |
| 10 | restore quota: compression_ratio | **派生** | per-req = granted/requested：H→D 段 pb_load_done.n_tokens / pa_lb_init.host_hit_length（配对）；L3→H 段 success.loaded / t38c prefetch_length；run 级 = A_run/E_run（04 §3.2 公式，metrics_schema.py 已实现）。join.log storage_hit/prompt_len 交叉校验 |
| 11 | restore quota: reject_reason | **decode 直接 / prefill 不可得** | decode 模式：warning "HiCache load_back failed ... (l1,l2,l3)"（decode_hicache_mixin.py:216-226，rid 级）。prefill 模式全静默：① 预算门 prefetch_rate_limited（cache_controller.py:1212-1213）→ 仅 t38c declined_rate_limited（unified_radix_cache.py:1840/2498）；② L3 部分命中 → 仅 t38c pc_get_v2 clamped_pages（cache_controller.py:1164）；③ H→D avail/evict 门（unified_radix_cache.py:1535-1542/1554-1556）→ **零输出**；mem_quota 门 inert（全仓无调用者传非 None，02 已证）。精确原因需插桩（④⑤ 门内各 1 行 logger，见 followups） |
| 12 | admission: running_bs | **聚合直接 / per-req 需插桩** | 聚合：Prefill batch 行 `#running-req`（metrics_reporter.py:616，批次执行后）；pa_batch.batch_size（scheduler.py:3917-3923，执行时，无 rid）。per-req admit 时刻 running_bs：**插桩 I2**（scheduler.py:3555 `running_bs = len(running_batch.reqs)`，与位置并入同一行） |
| 13 | admission: batch_is_full false→true→false | **不可得，需插桩** | 字段存在于 ScheduleBatch（schedule_batch.py:2084），但**任何日志/探针/度量均不含**（3090 实测 0 命中）。状态机已定位：reset 3452（pass 起点，#35537 修复痕迹）、set 3483（allocatable≤0）/3564（can_run≥allocatable）/3569（disagg）/3619-3623（NO_TOKEN）、其余 reset 3289/3308/3326/3767/3836/5077。**插桩 I1**：3452 处（reset 且前一值为 True 时打一行）+ 各 set 点（4 处，带原因）→ 完整 false→true→false 时间线，全 log-only |
| 14 | admission: max_running_requests | **直接** | 启动日志 scheduler.py:1161（实测 "max_running_requests=8"）；/get_server_info `effective_max_running_requests_per_dp`（scheduler.py:4676，driver 可读）；server_args dump 行（3090 实测） |
| 15 | admission: free/evictable/locked device tokens | **派生（快照粒度）** | free=sglang:kv_available_tokens（metrics_collector.py:348）、evictable=sglang:kv_evictable_tokens、locked=max_total−available−evictable−used（01 修正公式，不变式 metrics_collector.py:93-95；四 gauge 同周期）。per-request admit 时刻 = 最近快照近似（decode_log_interval=40 迭代 ≈ 秒级）；OOM 现场有精确形态 available_and_evictable_str（unified_radix_cache.py:3182-3207）。精确 per-req：并入 I2 一行读 pool_stats_observer 快照值 |
| 16 | PrefillAdder result / NO_TOKEN reason | **不可得，需插桩** | scheduler.py:3615-3623 分支区分 NO_TOKEN vs OTHER 但**无日志、无原因**；schedule_policy.py 无任何 admission 日志（logger 仅 3 处：101 warning/461/481 routing-key，与 admission 无关）。原因面已定位：NO_TOKEN=rem_total_tokens（1243/1282）、SWA 预算（1256-1267/1292-1304）、mamba slots（847-850）；OTHER=prefill_max_requests（1217）、rem_input_tokens（1270/1336）、prefill_delayer（1309-1318）、dsa cp（1214）。**插桩 I5**：scheduler.py:3615-3623 一行（res+rid+can_run_list 长度）；原因粒度需 schedule_policy.py 门内 6 处各 1 行 logger（log-only） |
| 17 | 最终 RESTORE / PARTIAL_RESTORE / RECOMPUTE | **派生** | per-req 分类 = join.log cached_tokens（device+host+storage）vs prompt_len：input_delta≈0 → RESTORE；部分命中且 input_delta>tol → PARTIAL_RESTORE；cached≈0（input_delta≈prompt）→ RECOMPUTE（04 §4 A/B/C/D 事件签名，metrics_schema.py 已实现）。引擎侧无 per-req 结局日志；storage 段分类可用 t38c pc_l3_host requested vs completed（:2021-2024） |

**矩阵计数**：直接 6 项（1/3/6/9/14 + 8 的 H→D 半边 + 11 的 decode 半边）+ 门控直接 1.5 项
（4、8 的 L3→H 半边，t38c touch 零改动）+ 派生 3 项（10/15/17，其中 15 为快照粒度）+
需 log-only 插桩 6.5 项（2/5/7/12/13/16 及 11 的 prefill 静默原因）。

### 重点结论

1. **batch_is_full（#13）**：现有日志/探针/度量**完全不可观测**（3090 实测 engine log 0 命中；
   无 debug 日志、无探针字段、无 gauge）。false→true→false 追踪需 log-only 插桩 I1（scheduler.py
   3452 一处 + 3483/3564/3569/3619-3623 四处 set 点，全部 logger.info，零逻辑改动）。**本地代码含
   #35537 修复痕迹**：3451-3452 在 early-return 检查（3454-3457）前无条件 reset（per-pass 语义，
   与上游 issue 的 proposed fix 及 PR #35609 逐字一致），故本地不会复现 #35537 的跨 pass 锁死；
   插桩顺带可实证该修复的每 pass 复位行为。
2. **waiting_queue_position（#2）**：不可得。引擎侧零输出（#queue-req 仅长度）；客户端可用
   ts_sched 到达序做代理（fcfs 默认下近似成立），非引擎真值。需插桩 I2（scheduler.py:3551-3571
   admit 点一行）。
3. **PrefillAdder result / NO_TOKEN reason（#16）**：不可得。调度侧 3615-3623 只有分支无日志；
   schedule_policy.py 零 admission 日志（debug 级也没有）。需插桩 I5（调度侧一行必做；原因粒度
   6 处可选）。
4. **completion→finalization latency（#7）**：finalize 时间点现成（success 日志 :2104 秒级 /
   pc_l3_host :2021 毫秒级）；io_done 时间点缺失 → 1 行 log-only 插桩 I3（:2518-2522
   `ack.completed_req` 分支）即得完整配对。注意本地 #32725 式主动 finalize 已消除 FCFS 耦合段，
   测量值预期≈同步线程+一个 pass 边界（几十 ms 级），与 #32724 的 2.4s 量级不同。
5. **#32724 / #35537 对照结论**：#32724（prefetch finalization lag）——本地含**修复痕迹**
   （#32725 模式）：_drain_ack_prefetch 在 completed_req ack 到达即调 _handle_prefetch_result
   （unified_radix_cache.py:2518-2522，注释 "check_prefetch_progress() is not called for this rid
   yet" 与 PR #32725 语义一致），FCFS 扫描内 check_prefetch_progress（scheduler.py:3579）仍在但仅
   兜底；另含本地独有 paced retry（_retry_missed_storage_prefetches scheduler.py:2912-2940，
   debug 日志 2935，该部署 retry_poll_interval=0 关闭）。#35537——含修复痕迹（见结论 1）。两个
   upstream 修复 PR（#32725/#35609）均未合并，本地 fork 自带等价机制。

### 需 log-only 插桩项清单（位置 + 最小方案，均不动逻辑）

| ID | 字段 | 位置 | 最小方案 |
|---|---|---|---|
| I1 | batch_is_full 转换 | scheduler.py:3452（reset）+ 3483/3564/3569/3619-3623（set） | 6 行 logger.info：reset 处仅当旧值 True 时打（转换日志，防每 pass 噪音）；set 处带原因（allocatable/can_run/disagg/NO_TOKEN+rid） |
| I2 | waiting_queue_position + running_bs | scheduler.py:3551-3571（扫描循环内） | 1 行：admit 前 `logger.info("admission rid=%s pos=%d/%d running_bs=%d can_run=%d")`（enumerate 索引 + len(waiting_queue) + 3555 的 running_bs） |
| I3 | io_done 标记 | unified_radix_cache.py:2518-2522（`if ack.completed_req:` 分支内） | 1 行 logger.info（rid+completed_tokens）；配合 SGLANG_LOG_MS=1（launch env）取 ms 精度；可选 IO 线程视角 cache_controller.py:1187-1193 另一行 |
| I5 | PrefillAdder result | scheduler.py:3615-3623 | 1 行：`res==NO_TOKEN` 分支打 rid+res；原因粒度可选 schedule_policy.py 门内 6 处（1243/1256/1270/1282/1292/1309）各 1 行 |
| I6 | L3→H requested | unified_radix_cache.py:1932-1937（stats["issued"] 处） | 1 行 logger.info（rid+prefetch_length）；或直接 t38c-on（零改动，代价是 30s 周期外需自解析 /tmp/t38c-probe.log） |

零代码备选（launch 配置级）：t38c-on touch（4/8/11 部分）、SGLANG_LOG_MS=1（毫秒时间戳）、
--log-requests --log-requests-level 0（请求到达/响应元数据，tokenizer_manager RequestLogger，
含 rid 不含调度状态）、--enable-request-time-stats-logging（per-req 完成摘要 ReqTimeStats，
schedule_batch.py:1843-1863，含 cached_input_len/attempts/各段时长，不含位置）。

## followups

- P2-1 引擎埋点设计可直接采用 I1-I6 清单（本任务仅勘察，未实施）；插桩风格建议沿用 b15/t38c
  先例（JSON 行 append /tmp/*-probe.log，零数值路径改动），或 logger.info + SGLANG_LOG_MS。
- 归因链路现成组合：join.log（1/3/17）+ pa_lb_init/pb_load_done 探针（8/9/10 H→D 段）+ success
  行（6/9 L3→H 段）+ t38c（4/8/11 部分）可覆盖 19 项中 12.5 项，无需等待插桩即可先行。
- 07/08/09 已有产物可直接回填矩阵实证：run-20260830-104949（K=2）+ run-20260830-110016（K=8）
  的 join.log/events-table.csv/metric-table.json 已含 04 归因字段（collect_metrics.py 产物）。

## open_issues

- 无阻塞项。注意点：① buffer_only 模式下 success 日志不发射（:2056-2061 提前返回），若未来
  host_memory_mode 切换需改用 t38c pc_l3_host 作 finalize 标记；② pb_load_submit/done 无 rid
  （02 已知缺口），per-req H→D 配对依赖 ts+n_tokens 推断；③ engine asctime 秒级分辨率，亚秒
  测量需 SGLANG_LOG_MS=1（launch env，P2-0 冻结参数外，登记 P2-1 决策）；④ 3090 部署
  retry_poll_interval=0（retry 关闭），I2 插桩前该机制不可观测（debug 日志 2935 亦不可见）。
