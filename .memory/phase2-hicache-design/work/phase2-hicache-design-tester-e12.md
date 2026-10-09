# phase2-hicache-design-tester-e12 — M2 wake 修复复测

## status
done（frontier_wake 首次出现 ✓、wait→wake 配对 28 组、K=1 回归、K=8 三判据对照完成；判据全绿；
**遗留：K=1 restore turn 仍 61s（wake 后 60s 时钟未复位 bug 残留）**——见 followups）

## 部署确认
unified_radix_cache.py **5f07791c** / scheduler.py **2bb64a91**（双侧 md5 匹配）；frontier_anchor_ready
谓词确认（unified_radix_cache.py:1787）；fresh /data/l3/p2b0-1d

## 1. frontier_wake 首次出现（42ms-gap 场景验证 ✓）
- **frontier_wake 28 次**（上轮 0）——wait→wake 配对出现，M2 双断点修复生效
- **配对样本（K=8 窗口，wait→wake 延迟 5-7s）**：
  - 0e0c8089: wait 17:39:54 node=103 → wake 17:40:01（6.5s）
  - 1f2eb88c: wait 17:40:06 node=121 → wake 17:40:12（5.2s）
  - 2681f22e: wait 17:40:13 node=133 → wake 17:40:18（5.2s）
  - 7e149216: wait 17:40:22 node=146 → wake 17:40:28（5.7s）
  （K=1 窗口 node 27-40 小节点 wake 3-35ms；K=8 大节点 5-7s = 注册即触发写的 backup 完成时间）
- restore_ready 9 次（完整链：wake→RESTORING→restore_ready 样本 b426c223 ×3 分段）
- **新事件**：restore_loadback_fail 4 次（restore 后 H→D load_back 失败——记录）

## 2. K=1 基线回归
- 12/12 完成，**elapsed 220s**（未达预期 20-55s：restore turn t5/t8/t12 wall 61s）
- 归因：**wake 后 60s 超时时钟未复位**——t5（71f49ed9）时间线：17:34:31 WAIT_CAPACITY 上弦
  → 17:34:36 wake+RESTORING+too_short 判定（requested=46）→ **但 17:35:31 才 timeout 放行**
  （60s 时钟未随 wake 取消）；对照 t2（8de0dd44）wake 后立即 miss（无 60s）——时钟复位
  仅在部分分支生效
- HEALTH_CHECK 不阻塞维持 ✓（restore_retry cause=capacity=0）；restore_retry 3 次（cause=frontier 正常重试）

## 3. K=8 主判据（3 分 52 秒截断：引擎 17:43:11 被协调人侧时间盒 SIGTERM——我的 timebox kill
因 pgrep 匹配到 bash 包装自身（命令行含 "sglang.launch_server" 字样）误报 No such process，
SIGTERM 从未到引擎，由协调人侧截断；38 成功 / 58 failed 为截断后请求）
**三判据对照（本轮 vs P2-0a 基线 vs 上轮 1c）**：
| 判据 | P2-0a | 上轮 1c | 本轮 1d | 结论 |
|---|---|---|---|---|
| recompute_served_tokens | 1,866,880 | 365,040 | **653,873** | ↓65%（vs P2-0a）；窗口 235s vs 180s + fresh 链 miss 多 |
| restore_served_tokens | 0 | 224,276 | **4,096** | ↑（vs P2-0a）；1d 链量少（仅 K=1 预热 12 turns）vs 1c 复用 0c 15G 链 |
| turns/s | 0.175 | 0.166 | **0.170** | 持平 |
| p95_round_interval | 52.8s | 106.4s | **67.6s** | 恢复 37%（vs 1c）但未回基线（restore 60s 时钟 bug 残余）|

**事件分布（全程）**：frontier_wait **536** / frontier_wake **28**（5.2%，其余 wait 被
discard——并发 churn 下请求走其他路径）/ restore_ready 9 / restore_recompute 192
（**cause=miss 183 + timeout 9**——timeout 从 1c 的 10 维持低位，miss 为真 miss 语义
（L3 无链），非缺陷）/ restore_retry 694（cause=frontier/capacity 正常重试）/ prefetch
issued 193 → io_finished 9 → revoke 184 / restore_loadback_fail 4
- disposition：RECOMPUTE 214（revoked:miss 184、too_short 26、hybrid_discard 3、
  denied_rate_limit 1）+ PARTIAL 6（shortfall）
- prefill_deny_summary：rem_total_tokens 低位 + rem_total_tokens_lock（7 次/窗口）
- width：num_running max=1（预期内）

## 4. 判据
签名 0 ✓（OOM/KeyError/RecursionError/SchedulerException 全 0）；SIGTERM 优雅退场 ✓
（17:43:11 destroy_process_group → 17:43:14 kill_process_tree，无崩溃堆栈）；进程 0 残留 ✓；
GPU 18975→15 MiB ✓；CHAIN_GAP 语义**未测**（引擎已停 + 时间盒；1d 链量少（K=1 12 turns +
K=8 截断），读侧 chain_check 需引擎进程——记录原因）

## 交付物（/root/evidence-p2b0-1d/）
- p2a-lines.txt（3,711 行）、state-machine.txt（1,459 行：frontier_wait/wake/restore_ready/
  retry/recompute 全量）
- k1/run-20260830-173402（join 12 行）、run-20260830-173919（join 96 行 + metric-table
  json/csv + events-table + mid-run 快照）
- k1-driver.log / k8-driver.log、MD5SUMS（459 文件）、engine log /root/engine-p2b0-1d.log

## followups
1. **60s 时钟未随 wake 复位（残余 bug）**：K=1 restore turn 仍 61s（t5/t8/t12）——wake 后
   too_short 分支的请求等满 60s 才放行；对照 t2（wake→miss 立即放行）说明复位只在部分分支；
   K=1 因此 220s 而非 20-55s，p95 67.6s 未回 52.8s 基线
2. K=8 的 58 failed（协调人侧截断后请求）——下一轮若需完整 96 请求对照，建议截断时同步停
   driver 或缩短窗口
3. restore_loadback_fail 4 次（restore 后 H→D 失败）——新事件，与 load_back 预算门交互
   需归因（p2-0-10 输入）
4. wait 536 中 508 未 wake 未 timeout（discard）——wait 生命周期统计建议补 abort 计数
5. CHAIN_GAP 语义补测：下轮 run 后用 chain_check.py 直读 L3（引擎外，0c/1d 均可）

## open_issues
- 1d 链量少导致 restore-served 低（4096 vs 1c 224,276）——链量差异 vs 修复效果需同链条件
  对照（复用 0c 链 + 本修复复跑 K=8）
- timeout/miss 构成：miss 183（真 miss）+ timeout 9（残余时钟）——wake 修复后 timeout 已
  从全超时（1c 的 wait 29/29）降到 9/536，方向正确
