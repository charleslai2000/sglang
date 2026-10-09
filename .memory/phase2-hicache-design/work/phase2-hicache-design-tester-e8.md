# phase2-hicache-design-tester-e8 — 场景 A2 重跑（I7 guard 部署后，prefetch 生命周期延迟链）

## status
done（预热→链核对→重访→延迟链测量全部完成；4 对完整生命周期 + 1 revoke；#32724 型判据未出现；判据全绿）

## 执行序
1. I7 guard 确认：cache_controller.py md5 **f0737a73**（1186 行 `(n_pages or 0) * self.page_size`）✓
2. 预热：fresh /data/l3/p2b0-0c，K=1 12 turns（14:35:56 起 23s，12/12 完成，downgraded=0）→ SIGTERM 优雅退出（9s，GPU 15MiB）
3. 链完整性核对（chain_check.py --json 直读 L3，引擎外）：
   - verdict=CHAIN_GAP 但**非 FAIL 型**：earliest_stored_index=**0**、无内部 hole（internal_holes=None）、
     stored_is_contiguous [0,20351] 连续
   - **尾缺口 [20352..20909]（558 页）**= 预热最后一批 write_back 未完全落盘（1318 竞态痕迹，
     对比 07 K=1 基线 final-chain-check 后尾缺 46 页——本次 SIGTERM 未触发 finalize 语义）
   - 结论：链主体完整可用（97.3%），缺口形态已记录为证据
4. 重访：同引擎重启（0c 续用），K=1 12 turns（14:38:47 起 55s，12/12 完成，failed=0）→ SIGTERM
   优雅退出（9s，GPU 15MiB，进程 0，签名 grep 0）

## 重访结果与延迟链（核心交付）
P2A 签名：prefetch_issued **5** → io_finished **4** → io_done **4** → finalize **4** → revoke **1**；
"HiCache prefetch success" 4 行。

**延迟分布（prefetch-lifecycle.json，配对 by rid）**：
| 段 | n | min | p50 | p95 | max |
|---|---|---|---|---|---|
| issued→io_finished（纯 IO）| 4 | 2,987ms | 11,267ms | 11,267ms | 16,011ms |
| io_finished→io_done | 4 | 1ms | 1ms | 1ms | 2ms |
| io_done→finalize | 4 | 0ms | 0ms | 0ms | 1ms |
| issued→revoke（miss 判定）| 1 | 131ms | - | - | - |
| finalize→success（log 1s 粒度）| 4 | -650ms | -359ms | - | -162ms（负值=asctime 秒 floor 对齐误差，真实 <1s）|

**#32724 型判据（io_finished→finalize 秒级？）：未出现** —— io_finished→finalize = 1-2ms
（scheduler 消费即时，几十 ms 级预期满足）

**io_finished n_tokens=0 确认**（guard 后"不可得"信号）：4/4 行 n_tokens=0，最终完成量以
I8 finalize completed_tokens 为准：18432 / 27776 / 17408 / 5120 ✓（协调人背景要点验证）

**per-rid 生命周期（ts_ms）**：
| rid | issued | io_finished | finalize | success completed |
|---|---|---|---|---|
| 53981be1 (t1 L0) | ...929090 | ...940357 | ...940359 | 18432 |
| c3b0776d (t2 L1) | ...941149 | ...958160 | ...958162 | 27776 |
| 933edb3a (t7 L1) | ...961131 | ...970649 | ...970650 | 17408 |
| 020d543f (t6 L0) | ...972649 | ...975636 | ...975637 | 5120 |
| 1b235c66 | ...979705 | - | - | revoke（131ms，storage_hit=0 requested=3502）|

## 重访归因（12 请求）
RESTORE 2（t1 sh=18429、t2 sh=10365）+ PARTIAL 6（t5/t6/t7/t8/t10/t12：device 17408-20864 /
host 5120-17408，L3 未参与）+ REJECTED 4（t3/t4/t9/t11 L2/L3 超限退化体 0.35-0.45s）。
storage_hit 合计 28,794 = join 口径；restore turn（t5/t8/t12）全 device 命中（0.95s，K=1 顺序
churn 下 device 池保留链）→ L3 未参与 restore（device 优先）。

## 判据
预热与重访两 run 均全绿：SIGTERM 优雅退出（kill_process_tree）、签名 grep 0、进程 0 残留、
GPU 18975→15 MiB

## 交付物（/root/evidence-p2b0-0c/）
- p2a-lines-prewarm.txt / p2a-lines-revisit.txt、prefetch-lifecycle.json（5 行生命周期明细）
- attribution-revisit.json（12 请求归因）、prewarm/run-20260830-143556、run-20260830-143847
  （join 12+12 行、mid-run-metrics、turns）、prewarm-driver.log / revisit-driver.log
- MD5SUMS（115 文件）
- 链核对证据：/tmp/chain-0c.json（earliest=0、尾缺口 558）

## followups
- **纯 IO 成本是新发现**：issued→io_finished 3-16s（20910 页级文件读取，~0.5-0.8ms/页）——
  L3 文件读是延迟大头（非 scheduler 消费）；P2-1 设计输入（prefetch 并发/分页/元数据缓存）
- 尾缺口 558 页 = SIGTERM 时最后 write_back 未落（1318 竞态痕迹）——协调人判定是否需
  finalize 语义修正；重访未受影响（主体链 97.3% 命中）
- revoke 1 例（1b235c66 requested=3502 storage_hit=0）：对应链尾缺口段的请求（L2/L3 链未
  在 L3）——revoke 原因 = L3 无链（正确行为），非异常
- finalize→success 的 1s 粒度对齐误差（负值）：如需亚秒精度，success 行需带 ms 时间戳
  （当前 asctime 秒 floor）
- 重访的 4 个 REJECTED（L2/L3 超限退化体）在 K=1 轨迹中稳定出现——32762 上限导致的
  payload 无法全链验证（L2/L3 链从不写入 L3），K=1 的 L3 覆盖只有 L0/L1 链

## open_issues
- completed_tokens（I8）vs success loaded（H→D）口径：53981be1 completed=18432 loaded=18429
  （3 页差）、933edb3a completed=17408 loaded=0（全 host 命中无 H→D）——多口径对齐留
  p2-0-10 归因
- 预热 K=1 与重访 K=1 的 session 轨迹完全同构（确定性模板）→ 重放即同链重访成立
