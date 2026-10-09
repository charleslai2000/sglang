# phase2-hicache-design-tester-e6 — P2-0a 归因插桩批次（K=8 短实验，3 分钟时间盒）

## status
done（前置两步 + 3 分钟时间盒实验 + 归因表全部完成；判据全绿）

## 前置步骤结果
1. **B 类口径修正部署**：metrics_schema.py（classify_event：D_r 与 E_r 分裂 >tol 时以 E_r 为准）+
   collect_metrics.py（self-test 更新：r-2→A + 新增 r-4 真 B 场景）scp 到 3090 /root/p2-0/；
   远端 self-test PASS（13/13 字段、18/18 检查）
2. **6 个历史 run 表新旧分类对比**（全部重跑）：
   | run | 旧 class (A/B/D) | 新 class (A/B/D) | 假 B 转 A |
   |---|---|---|---|
   | K=1 (104949) | 5/1/2 | 5/1/2 | 0（K=1 的 B 是真 partial）|
   | K=8 (110016) | 1/3/0 | **3/1/0** | 2 ✓ |
   | K=16 r1/r2 | 0/0/0 | 0/0/0 | -（无恢复事件）|
   | K=32 r1 (120724) | 4/14/0 | **12/6/0** | 8 ✓ |
   | K=32 r2 (124754) | 2/9/1 | **8/3/1** | 6 ✓ |
   假 B 全部消失（K=8 2 个、K=32 r1 8 个、K=32 r2 6 个，共 16 个 E_r=A_r 完整恢复被误判 B 的
   事件修正为 A）；真 partial（A_r<E_r，如 K=1 d8f57f7c、K=32 各第二段 load_back 6144/8192）
   保留 B。各 run metric-table.json/events-table.csv 已覆盖更新。

## 实验（3 分钟时间盒，K=8 × 12 turns）
- launch 脚本 STORAGE_DIR → /data/l3/p2b0-0a（.bak-p2b0-0a 备份）；[P2A] 插桩确认在引擎树
  （scheduler.py 8 处 / unified_radix_cache.py 2 处 / schedule_policy.py 6 处，ts_ms 自带）
- 引擎 13:47 起，health 16 轮；driver 13:48:58 启动（run-20260830-134858，96 请求预算）
- **13:51:58 SIGTERM 引擎（3 分钟）**→ 优雅 drain（日志 "Gracefully exiting... Remaining
  number of requests 2"）→ 6 轮询退出；driver pkill 停止
- 判据：引擎签名（OOM/KeyError/RecursionError/SchedulerException）grep = 0；进程 0 残留；
  GPU 18975 → 15 MiB

## 收集物（/root/evidence-p2b0-0a/）
- p2a-lines.txt（[P2A] 行全量 11,713 行）
- run-20260830-134858/：join.log（32 行：grow 16 + downgrade 15 + restore 1）、mid-run-metrics.txt
  （44 帧）、turns/（32）
- attribution-table.json + attribution-table.csv（32 请求归因表）
- MD5SUMS（143 文件）
- k8-driver.log

## 归因表与三方向观测
[P2A] 事件统计：admission 2519、prefill_deny 2358、no_token 2358、bif_set 2358、
bif_reset 2112、prefetch_issued 8。

**1. batch_is_full 时间线（bif）**：
- bif_set 2358 次 100% reason=no_token_hicache（单一原因）；bif_reset 2112 次 → 复位机制
  活跃（#35537 修复痕迹验证 ✓：每 pass 复位，差值 246 = SIGTERM 截断时点未复位残留，
  非粘性）。每请求连续 set 跨度（span）3.9-7.6s，p50 4.15s → **无跨 pass 粘性**（最长
  7.6s 后复位/请求完成）。31/32 请求有 bif_set。

**2. io_done→finalize 延迟**：**不可观测（插桩覆盖缺口）**——[P2A] 事件全集只有 6 种
（admission/bif_set/bif_reset/no_token/prefill_deny/prefetch_issued），无 io_done/finalize/
success 行（grep "io_done"=0、"HiCache prefetch success"=0）。prefetch_issued 8 条是唯一
prefetch 事件；I3↔success 配对无数据。替代观测：prefetch_issued→请求完成 wall 6.2-49s
（含排队+prefill，非纯 finalize）。**记 followup：插桩需补 io_done/finalize 行才能观测
#32724 型延迟。**

**3. NO_TOKEN 原因分布**：prefill_deny 2358 次 100% reason=rem_total_tokens（六门只触发
一门）；deny 时 total=27877（L1 请求）rem min=11792（剩余 KV 预算仅 11.8K < 请求需求）→
rem_total_tokens=32768 池上限被并发请求占满。本次 3 分钟 run 的 join 无 L2/L3 请求
（32 完成请求全 L0/L1），engine log "exceeds maximum" = 0 → 与 07 的 24 行超限拒绝无对应
（07 的 24 行来自 L2/L3 的 tokenizer 层快速拒绝，与本 run 的调度层 prefill_deny 是两条
独立路径，样本内无 L2/L3 故无法关联）。

**4. width=1 gate 判定**：admission running_bs 恒 ∈{0,1}（max 1）；qlen 峰值 7（2341 次
qlen=7）；can_run 首值 31/32=1（首个请求 0）。排队时长 = admission_first_ts − ts_sched：
样本 2（b693ce13）33.5s、样本 3（495c5e84）38.8s。**结论：width=1 由双 gate 共同决定——
① 调度器单槽执行（running_bs 恒 1，队列深 7）；② rem_total_tokens KV 预算门（deny 时
rem 11.8K < 请求 27.9K，每次 pass 重新 deny，请求持续 5.6s 排队后才有预算）**。allocatable
（KV 预算）才是主瓶颈：请求需要的 27877 tokens 超过池内剩余 ~11.8K。

## 归因表样本（3 行代表性完整状态转换）
1. **7274d0e3**（a1-t1 L0 grow，wall 6.2s，PREFETCH_NO_HIT）：prefetch_issued ts=...940114
   len=20910（比 join ts_start 早 188ms=传输/解析）；admission 14 次（first can_run=0）；
   bif_set 0/deny 0（首个请求不排队）；input_delta=20911（全量 prefill，fresh L3 0 命中）；
   pa_lb_init 无（无 H→D 加载）。
2. **b693ce13**（a1-t2 L1 grow，wall 44.5s，RECOMPUTE）：admission 75 次，first 比 ts_sched
   晚 33.5s（qlen=6 running_bs=1 排队）；bif_set 73 次 span 5.56s；deny 73 次 rem_total_tokens
   （total=27877 rem_min=11792 rem_last=11793）；无 prefetch_issued（host 锚点缺失后不再
   发起）；input_delta=153278（队列期间重叠计数——07 K=8 R_run 爆炸同源）；分类 RECOMPUTE。
3. **495c5e84**（a2-t2 L1 grow，wall 52.7s，RECOMPUTE）：同构——admission 75（first 晚 38.8s
   qlen=6）、bif span 5.57s、deny 73（rem_min 11792）、input_delta=181090。

## followups
- **插桩缺口（P2-0a 核心）：无 io_done/finalize/success 行** → #32724 型延迟不可观测；
  建议补插桩：prefetch_issued 后 2 个点（H→D 传输完成 I3 行、成功行 finalize）
- 本 run 无 L2/L3 请求（3 分钟截断 32 请求全 L0/L1）→ 32762 超限拒绝与 prefill_deny 的
  关联留待全量 run（P2-0b 或批次 3 首个 run 前 3 分钟窗口内已有 0 超限样本可对照）
- prefetch_issued 8 条全在 run 早期（host 锚点尚存时），host 池被 churn 挤空后无新 prefetch
  ——与 K=16/32 观察一致；锚点缺失阈值待量化
- B 类修正后的 K=16 两 run 仍全 0 事件（无恢复）——K=16 的 L3 完全断路，与 K=32 部分
  恢复（11 次 prefetch）形成对照，P2-0a 的 8 次 prefetch 为第三种形态（fresh L3 全 miss）
- t38c 探针仍不启用（本 run D 类事件 0）

## open_issues
- rem_total_tokens deny 的 rem 波动（11792→20479）与并发请求的 KV 占用关系：需 prefetch
  成功后 KV 归还时间线（插桩补 io_done 后可用 pa_lb_init/pb_load_done 配对近似）
- join input_delta 在排队窗口内被重叠污染（样本 2/3 的 15-18 万 vs payload 2.8 万）——
  归因表的 input_delta 列仅作参考，真实 prefill 输入以引擎 counter delta 为准（07 已证）
