# phase2-hicache-design-tester-e11 — P2-1 集成验证重跑（死循环修复后）

## status
done（死循环修复验证 ✓ + K=1 回归完成 + K=8 三判据对照 + 42ms-gap 复核；判据全绿；
**新发现：M2 frontier_wake 路径不工作（29/29 超时）**——见 followups）

## 部署确认
- 三文件 md5 匹配：hicache_restore.py **a5b39c10**（scheduler_components/）、scheduler.py
  **9354ed99**、unified_radix_cache.py **a375208c** ✓；fresh /data/l3/p2b0-1c

## 1. K=1 基线回归（健康检查验证：通过）
- **HEALTH_CHECK 不再进状态机**：engine log 无 HEALTH_CHECK rid 的 restore_state
  WAIT_CAPACITY REVALIDATE；**restore_retry cause=capacity = 0**（修复前 834,363 次）
- 12/12 完成（elapsed 323s——**变慢**：frontier_wait 4 次 × 60s 超时 + 正常 prefill；
  wall t2=64s/t5=61s/t6=62s/t8=61s，均含 60s wait 超时）
- 修复验证点全过：无死循环、无异常、签名 0

## 2. K=8 主判据（3 分钟截断，39 请求完成）
**三判据对照表（vs P2-0a 基线 1,866,880 / 0 / 0.175 t/s、52.8s）**：
| 判据 | P2-0a 基线 | P2-1（本次）| 结论 |
|---|---|---|---|
| recompute_served_tokens | 1,866,880 | **365,040** | ↓ **80.4%**（未完全归零；39 vs 32 请求窗口）|
| restore_served_tokens | 0 | **224,276** | ↑ 显著（29 次 restore_ready × ~7.7K tokens）|
| turns/s | 0.175 | 0.166 | ~5% 内持平 |
| p95_round_interval | 52.8s | **106.4s** | 恶化 2×（frontier_wait 60s 超时所致）|

**新计数分布（K=1+K=8 全程）**：
- restore_ready **29**（首次出现）、restore_recompute 64（miss 54 + timeout 10）、
  restore_retry 92（cause=capacity——正常重试，容量恢复后放行，非循环）
- frontier_wait **29**（K=1 4 + K=8 25）、**frontier_wake 0**
- disposition：PARTIAL 23（shortfall）+ RECOMPUTE 102（revoked:miss 54、too_short 25、
  **denied_rate_limit 16**（配额门拒绝首次观测）、hybrid_discard 6、revoked:terminated 1）
- prefetch：issued 85 → io_finished 30 → io_done 30 → finalize 29 → revoke 55
- prefill_deny_summary：rem_total_tokens 2-21 + rem_total_tokens_lock 7（vs P2-0a 288-350
  → 进一步下降 ~94%）
- l3_to_h_wait 13.8s（29 对均值，纯 IO 3-16s 区间一致）、h_to_d_wait 0.073s
- width：num_running max=1（预期内，不判失败）

## 3. 42ms-gap（M2 复核）：**wake=0 确认（M2 wake 路径不工作）**
- frontier_wait 29 次全部注册成功（node 27-40 等 host 尾节点）→ **60s 超时
  restore_recompute cause=timeout（10 次）**，无一次 wake
- 归因：修复未触碰 wake 路径（协调人所料）——wait 注册后 ancestor backup ACK 从未
  触发 wake（或 wake 广播未接上）；每个 wait 请求吃满 60s 超时 → K=1 从 20s 退化到
  323s、K=8 p95 106s
- 对照 M1 前（skip 不登记→直接 recompute）：现在多花 60s 等待比直接 recompute 更慢——
  wake 修复前 42ms-gap 场景净亏

## 判据
签名 0 ✓、SIGTERM 优雅退场 ✓、进程 0 残留 ✓、GPU 19023→15 MiB ✓；
CHAIN_GAP=0 语义未测（引擎已停 + 时间盒；1c 为 fresh namespace 短 run，链数据少，
读侧校验需引擎进程，记录原因）

## 交付物（/root/evidence-p2b0-1c/）
- p2a-lines.txt（879 行）、restore-disposition.txt（125 行）、state-machine.txt（214 行：
  frontier_wait/wake + restore_ready/retry/recompute 全量）
- k1/run-20260830-170030（join 12 行）、run-20260830-170634（join 39 行 + metric-table
  json/csv + events-table + mid-run 快照）
- MD5SUMS（229 文件）、engine log /root/engine-p2b0-1c.log

## followups
1. **M2 wake 修复（阻断项）**：frontier_wake=0 确认——wait 注册后 wake 从未触发（29/29
   超时）；需查 backup ACK → wake 广播链（unified_radix_cache 2297 discard 附近）；修复前
   42ms-gap 场景净亏 60s/请求
2. wake 修复后复测：K=1 应回到 ~20-55s、K=8 p95 应回到 ~53s 基线
3. denied_rate_limit 16 次（配额门）——M1a/M1b 增量计费与配额交互的首次观测，p2-0-10
   归因输入
4. recompute 365K 未归零：54 次 revoked:miss（L3 无链）+ 10 次 timeout（wait 超时）——
   wake 修复后预计进一步下降
5. CHAIN_GAP 语义未测（需引擎进程），建议下轮 run 后补 chain_check

## open_issues
- restore_retry 92 次 cause=capacity 的正常性：容量恢复后放行（无 60s 惩罚）——与
  wait 超时路径的交互待 wake 修复后重审
- 39 vs 32 请求窗口的 recompute 对照不完全等长——下轮用同请求数对照
