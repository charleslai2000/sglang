# architect e7 — P2-0 阶段性归因分析（width=1 与 restore=0→recompute 爆炸）

- status: done
- task: P2-0 阶段性归因分析（只读）—— 基于现有全部证据回答五问，输出归因报告
- 产出: /home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/attribution-report-phase2a.md（只写文档不 commit）
- 日期: 2026-08-30

## 证据基线

- P2-0a 插桩批次（远程 3090，证据已 scp 至 /tmp/arch-e7/p2b0-0a/）：p2a-lines.txt（11,713 行 [P2A]）、
  attribution-table.json/csv（32 请求）、join.log（32 行）、mid-run-metrics.txt（44 帧）、
  b15-probe.log（138,029 行，多 run 追加）、engine-p2b0-0a.log（1.6MB，完整 [P2A] 集）
- 历史批次：p2b0-01（K=1/2/8）、p2b0-02（K=16/32 各 2 runs，单引擎实例 4 run 连跑）、rs3（K=1 型 L3 restore 对照）
- 已定案事实（tester，作为输入）：bif 每 pass 复位；deny 2358 次 100% rem_total_tokens；
  running_bs 恒 1；qlen 峰值 7；prefetch_issued 仅 8 条全在早期、0 finalize；32 请求全 L0/L1

## 五问结论摘要

1. **width=1 定稿**：prefill 准入门 total_tokens（全长 prompt+max_new+page）≥ rem_total_tokens
   （= available+evictable−offset，schedule_policy.py:672-690,1244-1246）→ NO_TOKEN。池 32,768，
   单请求足迹 20,976（L0）/27,877（L1），27,877/32,768=85.06%；两个最小请求也要 41,952 > 32,768
   → 物理单槽。实测 rem=4,891-11,792 < 最小需求 → 2,358 次 deny → FCFS 串行。K=1..32 实测
   width（num_running_reqs 帧均值）0.20/0.70/0.98/0.99/1.00，max=1（K=32 run2 仅 4 帧=2）。
2. **recompute 因果链**：三段链，锚点被逐为中段（确证）；首段为 arrival 时 prefetch 不产
   （is_backuped 门 skip：turn-2 距本链写回仅 42ms，L3 backup 需 ~5-7s；turns 3-5 锚点已逐 →
   root → rate_limited），尾段为 retry_poll_interval=0 永不重试。b15：32 请求 0 个 pa_lb_init。
3. **三形态对照**：K=16 run2（L3 链存在，storage=0）与 P2-0a（链有但 0 restore）证明链存在性
   不是约束；K=32 部分恢复 5,117-10,234；rs3 单重访 restore=20,855 全通 → 约束在 L3→H 投递
   路径（预算占用 + 门 + 重试），H→D 机制本身可用（teardown 事件 14,336 全通）。
4. **prefetch 0 finalize**：8 条发出后 216s 内零终止事件（io_done/finalize/revoke/abort 全 0，
   "HiCache prefetch" 行 0）→ occupied ≥ 41,820 ≥ 上限 24,576 永久饱和 → 后续全部 rate_limited
   （静默）+ retry 禁用 → 无任何 L3→H 交付。存储查询未完成的原因（写回争用 vs prefetch 线程
   死亡）证据不足待插桩。
5. **P2-1 输入**：见报告 §5（准入时机/前缀保留/KV 预算与 width 关系式/新埋点清单）。

## 关键证据引用（≥5）

1. p2a-lines.txt:23-33 — deny 全 rem_total_tokens，rem 每 pass 递减 2,048（chunk 消费）
2. p2a-lines.txt:4,19,22,35,44,49,372,375 — 8 条 prefetch_issued（全 turn-1、arrival 时点、len=20,910）
3. attribution-table.csv:2-33 — deny_total_min 20,976/27,877；deny_rem_min 11,792/4,891（=32,768−used）
4. mid-run-metrics.txt:3,9,42,44 — host_used 0→20,925→47,845（97% 饱和）；input 累计 703,531→738,778；
   storage/device/host_hit 全程 0；backup 计数 681,016→722,726
5. join.log:1-32 — 32 请求 prompt_len 20,911/27,812，mode=input 累计 703,531，其余三 mode 全 0
6. b15-probe.log（窗口 1788068900-1788069170 过滤）— 仅 1 条 pa_lb_init（1788069159.643，
   rid=f145a933…非 32 请求，host_hit_length=14,336 → pb_load_submit 14,336 → pb_load_done 14,336）
7. engine-p2b0-0a.log:11 — server_args：hicache_storage_prefetch_retry_poll_interval=0、
   max_attempts=4、chunked_prefill_size=2048、page_size=1、enable_hierarchical_cache=True
8. engine-p2b0-0a.log 全文件 — "HiCache prefetch" 0 行；prefetch_finalize/revoke/io_done/abort 0 事件
9. engine-p2b0-02.log:661-662 — 单引擎实例 4 run 连跑，L3 目录 /data/l3/p2b0-02 跨 run 持久
10. rs3 driver-run.log:9,20 — 单重访 L3 restore 全通（cached=20,864 dev=9 host=0 storage=20,855，
    no_full_recompute=True）
11. 代码：schedule_policy.py:672-690,1244-1246；scheduler.py:2885-2893,3579-3584,2912-2940；
    unified_radix_cache.py:1933,1963-1964,2016,2103-2112,2336-2365；cache_controller.py:620-621,1212-1213
12. 历史 width 曲线：p2b0-01/02 各 run mid-run-metrics.txt num_running_reqs 帧统计

## 未定案项（证据不足）

- A. 8 条 prefetch issue 自身如何全部通过 rate-limit 门（静态推导第 3 条起 occupied=41,820 ≥ 24,576
  应被拒）与"零释放事件"矛盾 — 需 occupied 随事件打点 + prefetch 线程心跳插桩
- B. 8 条 prefetch 存储查询未完成的根因：写回争用（file backend 读写串行）vs prefetch 线程静默死亡
  — 需查询开始/结束探针
- C. turns 3-5 的 L2 锚点具体深度（root vs 部分前缀）不可观测（t38c 关闭）— 影响 root 分支判定
- D. K=32 部分恢复（5,117-10,234）的逐请求路径不可观测（无 P2A 插桩）— 聚合级确证，机制级推断
- E. K=16 run2 开始时 L3 内实际存留链集未验证（20G 逐出次序未知）— 但聚合行为与 P2-0a 一致

## P2-1 输入建议要点

见 attribution-report-phase2a.md §5（capacity-aware admission 设计输入 + 新埋点清单）

## artifacts

- /home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/attribution-report-phase2a.md（本次交付）
- 证据本地副本：/tmp/arch-e7/（p2b0-0a 含 b15/engine log；p2b0-01/02 各 run join.log+mid-run-metrics）

## followups

- 补插桩场景 A（冷 L3 首波 + 排队重访）：prefetch 延迟/心跳、occupied gauge、declined 计数、
  is_backuped skip 计数、L3 backup 完成时点 vs 重访到达时点、host 锚点 eviction rid 级事件
- t38c 门文件启用（零引擎改动）以拆分 ②/②b 与 D 类确证（attribution-design §5.2）

## open_issues

- 见"未定案项"A-E；其中 A 属引擎行为与代码静态推导的硬矛盾，需 tester 补插桩优先排查
