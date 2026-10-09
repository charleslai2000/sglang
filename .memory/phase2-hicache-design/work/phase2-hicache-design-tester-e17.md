# P2-1 第六次终判复测 — tester e17 报告

## 1. status

**done** — K=8 完整 run **96/96 全部成功**（0 failed、elapsed 666.2s）、**优雅退场**（SIGTERM→draining→0 残留→graceful exit）、OOM 不复发、五项复核全绿、归因 100% 可解释、签名 0、CHAIN_GAP 通过。**六次复测以来第一次全判据绿。**

## 2. artifacts

- /root/evidence-p2b0-1i/：run-20260830-233620（K=8：**96/96 http 200**、downgraded=1=turn_kind 计数）、run-20260830-233523（K=1：12/12）、k1-driver.log、k8-driver.log、MD5SUMS（6 项）
- /root/engine-p2b0-1i.log：尾部 = 23:47:26 正常 decode + 23:47:41 SIGTERM → 23:47:46 Gracefully exiting（remaining_rids=[]）
- 12 指标表：run-20260830-233620/metric-table.json/.csv
- **md5 启动前核对（4/4）**：unified_tree_core.py **fb931e5c** ✓ / unified_radix_cache.py **d992a972** ✓ / scheduler.py **7305eb0b** ✓ / test **3378313d** ✓

## 3. summary

### 3.1 K=1 回归（run-20260830-233523）：12/12、0 failed、elapsed 47.8s
walls 13.5/14.3（冷）→ 0.4-4.9s（链命中）——restore 路径无回归

### 3.2 K=8 完整 run（run-20260830-233620）：**96/96、elapsed 666.2s（预算 3600s）、OOM=0**
- 引擎全程存活到 run 完成；run 后 idle sanity_check **通过**（sanity 修复 fb931e5c 生效——e16 node 511 AssertionError 未再现）；主动 SIGTERM 关闭 → `Draining requests → Gracefully exiting... remaining_rids=[]` ——**优雅退场 ✓**

### 3.3 四判据干净值（无截断）
| 指标 | 本次（1i） | e16（94/96） | P2-0a 基线 |
|---|---|---|---|
| recompute_served | **675,678** | 752,440 | 1.87M（-64%） |
| restore_served | **626,260** | 428,468 | — |
| turns/s | **0.144** | 0.148 | — |
| p95 (s) | **128.7** | 133.6 | — |
| h_to_d_wait | 0.071s | 0.064s | 0.73s（P2-0 R7） |

### 3.4 复核五项（应保持项全绿）
1. **60s REVALIDATE stall = 0** ✓（REVALIDATE 事件 0 次）
2. **orphan WAIT = 0** ✓（26 wait rids 全部有终态）
3. **rate-limit false recompute = 0** ✓（48 denied：33 restored + 13 timeout + 2 miss；0 个立即放弃）
4. **wake 率**：frontier_wait 27 / wake **23 = 85%**（e16 91%——同水平；wake 仍主导，60s 超时非主导）
5. **OOM 不复发** ✓（OOM=0、elapsed 666s > 五次历史崩溃点 217-392s）+ **device_locked_tokens = 0.0** ✓

### 3.5 归因 100% 可解释（207 dispositions + 48 recompute）
- dispositions：shortfall 66（PARTIAL restore）、denied_rate_limit 48、too_short 48（policy-terminal）、revoked:miss 26、hybrid_discard 19
- recompute 48 = **miss 26（↔ revoked:miss 26 一一对应）+ timeout 22（13 rate-limit 后 60s 等待 + 9 其他）**——无 unknown
- restore_ready 85 次（成功 restore 服务）

### 3.6 判据
- **签名 0** ✓：96/96 成功行 output_sha16 与 payload 期望一致（mismatch 0）
- **CHAIN_GAP** ✓：chain_check 直读 0c——earliest=0、stored_runs=[[0,20863,20864]]、无内部洞、尾部 missing 46（=验收线）
- **优雅退场** ✓：SIGTERM → draining → 0 残留请求 → graceful exit
- **0 残留** ✓（pgrep 空）、**GPU 释放** ✓（325MiB/0%）

## 4. followups

1. collect_metrics 三项仍 missing（l3_to_h_wait / quota_denied / quota_compressed）——窗口/计数器原因待查（非阻塞，12 项中 9 项 ok）
2. p95 128.7s 为 K=8 无截断值——如需与 P2-0 批次 K=8 基线精确对比，可查 P2-0 历史 run 表（active_width=1 单槽特性下 p95≈130s 与 e16 一致）
3. 建议协调人安排 reviewer 过一遍 eviction deadlock 修复（7d5ac691→fb931e5c 两轮）与测试配对（test_storage_regression.py 3378313d）

## 5. open_issues

- 无阻塞项。终判（P2-1）六类归因最终值以本 run 为准：recompute 675,678（true miss 26 + policy-timeout 22 + too_short/shortfall 等 disposition 全量可解释）
