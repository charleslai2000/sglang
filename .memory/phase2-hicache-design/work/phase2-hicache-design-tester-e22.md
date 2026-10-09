# phase2-hicache-design-tester-e22 — P2-IO Test A 主验收（Z3+Y）：K=1/16/32 验证

## 1. status

**in-progress**（增量记录；epoch 22 = 本轮 3090 实验）。Phase 0 完成（md5 3/3 + 清理）；**K=1 回归完成（fresh 12/12 + warm 12/12，forced_drop_to_miss=0，restore 路径无行为变化确认）**；**K=16 主验收完成（128/128、950.5s、越过 470s 崩溃点、OOM=0、优雅退场）**；K=32 进行中（10:19:50 起，预算 1500s，989s 崩溃点 = 10:36:20）。

## 2. artifacts

- 本报告: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-hicache-design-tester-e22.md`
- 远端: /root/evidence-p2b0-3k1/（K=1 fresh + warm 复跑）、/root/evidence-p2b0-3a/、/root/evidence-p2b0-3b/、/data/l3/p2b0-3{k1,a,b}/、engine-p2b0-3k1.log

## 3. evidence（已落盘）

### 3.1 Phase 0 — md5 核对（双侧 3/3，与 coder e15 一致）
| 文件 | 本机 | 远端 3090 | coder e15 |
|---|---|---|---|
| unified_tree_core.py | 8e15bd81e4991cb2ee1cd6e17d1994c1 | 8e15bd81e4991cb2ee1cd6e17d1994c1 | 8e15bd81… ✓ |
| unified_radix_cache.py | 9e36323a3223f4b5d968fa3bde41902f | 9e36323a3223f4b5d968fa3bde41902f | 9e36323a… ✓ |
| test_storage_regression.py | 3bde33dc132c8678784b8a489fc12ec4 | 3bde33dc132c8678784b8a489fc12ec4 | 3bde33dc… ✓ |

### 3.2 顺带清理（已授权）
- 删除 stray: `/root/sglang-b1-continuity/python/sglang/srt/mem_cache/unified_cache/unified_radix_cache.py`（rm 单文件；原 9c43597a… = 旧内容错误副本）
- 删后正确副本 md5 未变: mem_cache/unified_radix_cache.py = 9e36323a3223f4b5d968fa3bde41902f ✓；unified_cache/ 目录现仅真文件

### 3.3 K=1 fresh-ns 回归（run-20260831-094950，ns p2b0-3k1，MAX_SIZE=60G）
- 启动: engine-p2b0-3k1.log L660 `HiCacheFile eviction enabled: cap=60000000000 B ... existing=0 B (0 entries)` — fresh ✓
- driver: `--agents 1 --turns 12 --stagger 1 --evidence-dir /root/evidence-p2b0-3k1 --health-check --no-probe`
- verdict: **12/12 http 200, 0 failed, 0 downgraded, elapsed 411.8s**（预算 2700s）status=done
- TTFT walls: t1 6.2 / t2 18.4 / t3 63.8 / t4 64.2 / t5-restore 60.2 / t6 1.4 / t7 1.5 / t8-restore 60.2 / t9 61.4 / t10 1.5 / t11 62.0 / t12-restore **0.2**
- L3 写: 3.5G / 57,487 文件，mtime 09:49-09:56（run 窗口内实时落盘）
- 引擎事件: restore_recompute 11（restore_disposition: revoked:miss 5 + too_short 4）、prefetch_issued 5 全部 revoked:miss（storage_hit=0）、frontier_wait 7 / wake 1
- **forced_drop_to_miss = 0** ✓；hollow_evict = 0；backup_failed/drop_declined = 0
- 解释: 所有 prefetch 在 run 内写链上 storage_hit=0 → revoked:miss → 60s 超时 → recompute。与 2a（M1/M2 代码，fresh ns K=16，revoked:miss 177/178）同型 = **既有 fresh-ns 写→prefetch 可见性缺口，非 Z3+Y 回归**；e17/2b-r4 K=1 基线均为 warm ns（existing=16G/18.9G），restores 快因此可比性需 warm 复跑对照
- **warm-ns 复跑（run-20260831-095803，同引擎同 ns，e17 条件）: 12/12 http 200, 0 failed, elapsed 14.4s**；TTFT walls 全部 0.2-0.5s（restore t5/t8/t12 = 0.2s），p95 round 1.24s —— **restore 路径无行为变化（e17 warm 级 0.4-4.9s，同或更优）**；cross-pass sha16 12/12 一致
- K=1 计数器全 0：forced_drop_to_miss=0 / hollow_evict=0 / drop_without_backup=0 / backup_failed=0 / drop_declined=0 / stays device-resident=0 / OOM=0 / RuntimeError=0
- 12 指标表（collect_metrics.py）：fresh run metric-table.json/csv（recompute_served 76240 tokens，p95 64.6s）+ warm run（recompute_served 592，h_to_d_wait 0.019s）；l3_to_h_wait/quota_denied/quota_compressed 3 项 missing（P2-0 已知 gap，非本轮）
- 证据完整：MD5SUMS 已生成（/root/evidence-p2b0-3k1/）；p2a-k1.log 75 行

### 3.4 K=16 主验收（run-20260831-100042，fresh ns p2b0-3a，MAX_SIZE=60G）
- 启动: engine-p2b0-3a.log L660 `cap=60000000000 B ... existing=0 B (0 entries)` — fresh ✓
- driver: `--agents 16 --turns 8 --stagger 1 --time-budget 1500`；**verdict: status=done, 128/128 http 200, 0 failed, downgraded 15, elapsed 950.5s**（预算 1500s）
- **越过旧崩溃点 470s（r3 同型）**；比 e20/2a 的 1112.9s 更快（60G cap 无逐出 churn）
- 优雅退场: `Gracefully exiting... remaining_rids=[]`（10:16:47）+ 0 残留 + GPU 15 MiB
- Test A 计数器（testa_extract.py）:
  - **forced_drop_to_miss = 8** ✓（逃生路径真实触发，节点 147/130/302/296/295…，freed 1458-2048）
  - **hollow_evict = 21**（主路径）→ forced 占 evict 事件 8/29 = 28%，hollow 2.6× forced（Z3 非主路径）
  - **backup_failed = 0、drop_declined = 0**（2b 轮 r2=2/r3=1 → 显著下降 ✓）
  - **drop_without_backup = 0**（2b r2=161/r3=23 → 归零 ✓）
  - **walker_zero_progress = 0** ✓；stays device-resident = 0 ✓
  - **OOM = 0、RuntimeError = 0、SchedulerException = 0、KeyError = 0、RecursionError = 0** ✓
- 归因: restore_disposition = RECOMPUTE 161（revoked:miss 88 + hybrid_discard 44 + alloc_failed 15 + too_short 14）+ PARTIAL shortfall 64 + WAIT denied_rate_limit 87；prefetch_revoke 103（storage_hit=0 88 + 命中 15）；restore_recompute 192；frontier_wait 103 / wake 65（63%）
- 12 指标表（collect_metrics.py）: turns/s 0.135、p95 round 234.1s、active width 4、slot_refill_gap 20.1s、restore_served 377,203、recompute_served 2,184,974（recompute_fraction 85%，fresh-ns revoked:miss 主导）、h_to_d_wait 0.070s、device free 3.5K/evictable 25.4K/locked 0；l3_to_h_wait/quota_denied/quota_compressed 3 项 missing（P2-0 已知 gap）
- **sha16 一致性**: 122 组（session,level,variant,kind）中 120 组单 sha16（完全一致）；2 组多 sha16 均为 **downgrade 转（reasoning 采样输出）**——2a 基线（M1/M2 代码）同样有 3 组 downgrade mismatch → **既有引擎采样特性，非 Z3+Y 回归**；downgrade payload 字节级相同（md5 一致），差异在采样推理 token；非 downgrade 链组零不一致 → **无 corruption**
- L3 写: /data/l3/p2b0-3a 大小待记（p2a-k16.log 2735 行）
- 证据: /root/evidence-p2b0-3a/（run dir 完整 + p2a-k16.log + metric-table.json/csv + events.csv）；MD5SUMS 待生成

## 4. followups

1. ~~K=1 warm-ns 复跑对照~~ → 完成：restores 0.2s，restore 路径无行为变化确认
2. ~~K=16 主验收~~ → **通过**（128/128、950.5s、越 470s、OOM=0、forced_drop=8/hollow=21、backup_failed=0）
3. K=32 主验收（fresh ns p2b0-3b，必须越 989s 崩溃点）—— 进行中（10:19:50 起，989s 点 = 10:36:20）
4. Test A 判据逐项 + 计数器 + sha16 一致性 + 12 指标表 + MD5SUMS（K=16 已落、K=32 待补）

## 5. open_issues

- fresh-ns in-run 写链对 prefetch 不可见（storage_hit=0）→ restore 60s 超时→recompute：既有现象（2a 同型），非 Z3+Y 引入；已登记为长期 open issue（storage_existence_cache 填充）的又一证据
- /data 可用 136G（非指令所称 173G；60G cap 充足）

### 3.5 K=32 主验收（BLOCKED — 远端失联，结局未知）

- 启动: 10:19:50，fresh ns p2b0-3b，MAX_SIZE=60G，driver 32×8=256 请求，time-budget 1500s
- 运行中证据（失联前最后确认 10:30:28）:
  - rows=100/256，RUNNING，**OOM=0**
  - forced_drop_to_miss 递增: 9@10:22 → 20@10:24 → 23@10:25（Z3 阀在 K=32 深度压力下真实触发）
  - hollow_evict 并行: 8→21→27（主路径仍在工作）; walker_zero_progress=0
- **失联时间线**:
  - 10:30:28 最后成功 SSH 检查（正常）
  - ~10:35:12 首次 ssh 挂起（120s 超时未返回）
  - 10:36:20 = 989s 崩溃点（旧 2b 轮同型）；失联窗口正覆盖该点
  - 10:37-10:43 诊断: 本机网络正常（网关 192.168.1.1 OK）；Astrill tun0 UP，隧道远端 198.18.0.1 ping 通（153ms）；**10.0.8.1 与 10.0.8.16 均 100% 丢包**；TCP 22/8024 全闭；10.0.8.16 无备用路由（ssh config 仅 vps01→10.0.8.16 一条）
  - 10:43:48 有界前台轮询 13×20s 全程 FINAL_DOWN
- **判据结论: 无法判定**。989s 崩溃点是否越过、OOM 是否 0、verdict 均未取到。已发生的运行证据（engine log + evidence dir）保留在远端 /root/engine-p2b0-3b.log、/root/evidence-p2b0-3b/，恢复访问后第一时间取证（tail + verdict + testa_extract）
- 两种假设（需远端恢复后区分）: (a) 远端主机在崩溃点前后宕机/重启（时间高度吻合）→ run 失败; (b) Astrill 隧道路由漂移（远端 198.18.0.1 仍通）→ run 可能已完成，证据完好
- **结论: Test A 验收不完整** — K=1（forced_drop=0）与 K=16（128/128、越 470s、OOM=0、forced_drop=8/hollow=21、backup_failed/drop_declined/drop_without_backup 全 0）通过；K=32 为未知态，须重跑或恢复后取证

## 6. 最终 status: **blocked**（环境故障 — 远端 10.0.8.16 自 ~10:35 起不可达，K=32 结局未定）

### 3.6 K=32 结局更新（10:46-10:50 新证据）— 关键反转

- **后台 ssh 会话 by38gkhly 于 10:46:21 送达 driver 最终输出**（本地任务通知 exit 0），全文:
  `driver rc=2 / probe_notes=0 b15_events=0 t38c_events=0 / final chain: not requested / elapsed=1618s (budget 1500s)`
- **rc=2 语义**（coder e3-05 §4.1）: 超时强制 verdict（status=blocked）— 预算截断，非崩溃
- **结论更新: 远端主机未在 989s 崩溃** — driver 在远端完整跑满 1618s 预算（远越 989s 崩溃点），最终被预算截断退出。2b 轮同点是引擎 OOM 死、run 夭折；本轮 driver 全程存活 → Z3+Y 修复在 K=32 压力下存活到预算耗尽（强正向信号）
- 剩余待取证: verdict.json 的 requests_total/failed（截断可能致 failed>0）、engine log OOM 计数、forced_drop/hollow/backup_failed 计数器、优雅退场、sha16、MD5SUMS — 全部在远端 /root/evidence-p2b0-3b/ + /root/engine-p2b0-3b.log
- **网络状态（10:50:29 复查）**: Astrill tun0 UP、隧道端点 198.18.0.1 ping 通（153ms 稳定）→ 但 10.0.8.0/24 子网仍不可达（.16/.1 全丢包、TCP 22 超时）；10:47-10:50 连续 6 次 ssh 重试全失败 → 判定为隧道远端到目标子网的路由/路径问题（或主机网络栈），pc01 侧无法修复，超出本人边界
