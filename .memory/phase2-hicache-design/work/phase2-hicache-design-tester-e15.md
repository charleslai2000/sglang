# P2-1 正式终判（B）— tester e15 报告

## 1. status

**blocked** — K=8 完整 run 第四次失败（第三次重跑 run-20260830-220336，新代码仍 OOM）。**SIGTERM 来源已定案：不是外部 SIGTERM，是 GPU KV 池 OOM 导致的引擎内部崩溃**（四次全部同模式）。根因完整定位：locked 前缀链（16384 tokens = 半池）使 evict 无法回收 → prefill 2048-token 分配失败 → Scheduler exception → SIGQUIT watchdog。需协调人（coder）修锁泄漏后重跑。

## 2. artifacts

- /root/evidence-p2b0-1g/：run-20260830-220336（38 http 200 + 58 failed，elapsed 314.8s）、k8-driver.log、launch-1g.out
- /root/engine-p2b0-1g.log（新代码引擎日志，OOM traceback 完整）
- 代码 md5 核对（启动前）：hicache_restore.py **0d24bb9f** ✓ / scheduler.py **30e9e0c7** ✓ / unified_radix_cache.py **5f9d3f76** ✓（与协调人给定一致）
- 旧证据保留：/root/evidence-p2b0-1f/（两次旧代码 run）+ e14 报告

## 3. summary

### 3.1 SIGTERM 来源定案（关键结论）

**不是外部 SIGTERM。** 四次 K=8 复用 0c 链全部同模式（引擎日志尾部）：
"Out of memory. Try to lower your batch size." → "Scheduler hit an exception: Traceback" → "**SIGQUIT received** ... It usually means one child failed" → "Sleeping 5 seconds before crash diagnostics" → "kill_process_tree called: parent_pid=...". **kill_process_tree 是崩溃清理流程，不是信号响应**——我之前（e14）误判为"外部 SIGTERM"。已排除 cron/systemd/我的进程/ssh 会话（启动命令双层 nohup+disown+全 fd 重定向，ssh 30s 内返回）。

| run | 代码 | 崩溃时刻 | elapsed | failed |
|---|---|---|---|---|
| e13（run-180715） | 旧（时钟修复） | 18:10:47 | 217s | 74 |
| 1f | 旧 | 21:45:56 | 392s | 46 |
| 1f2 | 旧 | 21:53:41 | 293s | 57 |
| 1g | **新（0d24bb9f/30e9e0c7/5f9d3f76）** | 22:08:45 | 315s | 58 |

**e13 的 K=8 也不是干净值**（74 failed + OOM）——e13 报告的 recompute 130K 是截断值，非完整 run 值。

### 3.2 OOM 根因（确定性，非随机）

崩溃 traceback（1g 与 1f 同位置）：alloc_token_slots → allocator.alloc(2048) 返回 None：
- **Available full tokens: 16384（full_available_size=9 + full_evictable_size_=16375）**——device 池（32768）一半"可回收"却分配失败
- 崩溃 dump：**locked 前缀链 [9]→[19]→[22]→[187]→[188]→…→[195]，locked 总 token = 16384 = 恰为整个 evictable 空间**
- evict_from_tree_cache（common.py:116）→ evict_for_alloc 只回收**无锁叶子**——**锁链的子树全部受父节点 lock_ref 保护**（radix_cache.py:614 `if ... parent.lock_ref == 0`），16375 evictable 实际回收 0
- 锁来源：radix_cache.py:572 `inc_lock_ref(new_last_node)`（请求引用/restore 路径）——**锁链对应某请求的 16K 前缀（cache_protected_len 机制），OOM 时刻仍未释放**
- 触发链：96 请求 96s 内全部入队（OOM 前 #pending-token 166,754）→ 调度器持续 prefill 2048 → 锁链保护 → 树碎片化 → 分配失败 → **Scheduler exception 直接抛 RuntimeError（不是降级等待）→ SIGQUIT 崩溃**

### 3.3 新代码评估（1g vs 旧代码 1f）

- recompute 事件 36→**15**（timeout 14 + miss 1；old 16/8/6）；denied_rate_limit 34→22；too_short 28→23——**restore 路径确实改善**
- 但 **frontier_wake 7 次 vs wait 注册 8,351 次**（old 11 vs 1,042）——wake 稀缺依旧，协调人预期"大幅改善"未兑现
- **OOM 未解决**——锁泄漏在 5f9d3f76/30e9e0c7 未修复

### 3.4 判据

- CHAIN_GAP（0c，引擎外 chain_check）：**earliest_stored_index=0、stored_runs=[[0,20863,20864]]、无内部洞、尾部 missing 46（=验收线）、sidecar 11/11** ✓
- 签名：38 成功请求 downgraded=0 ✓（截断前）
- 优雅退出：**无**（OOM 崩溃）
- 0 残留：pgrep 无引擎/驱动 ✓；GPU 15MiB/0% ✓

## 4. followups

1. **锁泄漏修复（协调人→coder）**：restore/write_back 路径的 inc_lock_ref 需有对应 dec_lock_ref（OOM 时 16384-token 锁链 [187]…[195] 未释放——对照 radix_cache.py:571-572 inc/dec 配对 + cache_protected_len 释放路径）。修完需跑 K=1 回归 + K=8 完整。
2. 参数缓解（若需临时绕过）：降低 prefill 批量（--chunked-prefill-size 1024）或增大 max-total-tokens 留给锁链余量——**不推荐**（冻结参数），仅记录。
3. 重跑前置：锁修复部署后，复用 0c 链（CHAIN_GAP 已验证 ✓）+ 新代码 md5 核对，96 请求完整 run。

## 5. open_issues

- **K=8 复用 0c 链确定性 OOM（四次实证）**——终判唯一阻塞项；根因已定（locked 链使 evict 失效）
- 新代码 frontier_wake 依旧稀缺（7 vs wait 8,351）——若终判后优化，方向是 wake 谓词覆盖（frontier_anchor_ready 之外的 wait 场景），仅记录不判定
