# P2-1 金标准第五次复测 — tester e16 报告

## 1. status

**blocked（接近达标）** — eviction deadlock 修复版（7d5ac691/d992a972/7305eb0b）下：**OOM 不复发**（elapsed 639s，远超五次历史崩溃点 217-392s）、94/96 成功、三项硬性验收全过、wake 率 91%（旧代码 0.08%）。**唯一新问题**：所有请求完成后引擎 idle sanity_check 断言失败（node 511 hollow 状态与断言冲突）→ SIGQUIT 崩溃 → 最后 2 个请求（a5-t11/t12）in-flight 失败 + 优雅退场判据不满足。需协调人裁决：sanity_check 断言接受 hollow 节点，或修 hollow 创建路径，然后（可选）重跑收尾 2 请求。

## 2. artifacts

- /root/evidence-p2b0-1h/：run-20260830-231001（K=8：94 http 200 + 2 failed、downgraded=5=turn_kind 计数）、run-20260830-230828（K=1：12/12 成功）、k1-driver.log、k8-driver.log、MD5SUMS（6 项）
- /root/engine-p2b0-1h.log（含 sanity AssertionError traceback 完整）
- 12 指标表：run-20260830-231001/metric-table.json/.csv
- **md5 启动前核对：unified_tree_core.py 7d5ac691 ✓ / unified_radix_cache.py d992a972 ✓ / scheduler.py 7305eb0b ✓ / test_storage_regression.py c884b7c4 ✓（4/4）**

## 3. summary

### 3.1 K=1 回归（run-20260830-230828）：12/12 成功、0 failed、0 downgraded、elapsed 65.8s
- walls：14.5/17.4（冷）→ 0.4-10.8s（链命中）——restore 路径正常
- 引擎事件：restore_disposition 15（末 3：revoked:miss 1 + too_short 2=terminal degradation）、recompute 仅 1（true miss）、frontier_wait 1/wake 1——**hollow-eviction 修复无回归**，wait 重注册 cadence 低

### 3.2 K=8 完整 run（run-20260830-231001）：94/96、elapsed 639.2s（预算 3600s）、OOM=0
- **引擎存活 639s > 五次历史崩溃点（217/392/293/315/217s）——OOM 不复发确认**
- 12 指标：turns/s **0.148**（vs e14 截断 0.130）、p95 **133.6s**、restore_served **428,468**、recompute_served **752,440**（vs P2-0a 1.87M，降 60%）、h_to_d_wait 0.064s、active_width 1、**device_locked_tokens 0.0**（锁泄漏已修——此前 OOM 时锁链 16384）
- l3_to_h_wait / quota_denied / quota_compressed 指标 missing（collect_metrics 未采到，原因待查）

### 3.3 三项硬性验收
| 项 | 结果 | 证据 |
|---|---|---|
| 60s REVALIDATE stall | **0** ✓ | REVALIDATE wait 事件 0 次 |
| orphan WAIT | **0** ✓ | 31 个 frontier_wait rid 全部有终态（wake/ready/recompute/disposition） |
| rate-limit false recompute | **0** ✓ | 46 个 denied rid：32 restored + 14 recompute；14 个**全部 cause=timeout（60s 容量等待后）**，0 个"拒绝后立即放弃"——false（立即放弃）口径 = 0，14 个归 policy-terminal timeout |

### 3.4 frontier_wake 计数（对比）
- 本次：**frontier_wait 32 / wake 29 = 91% wake 率**（K1 1 + K8 31）
- 旧代码 1g：wait 8,351 / wake 7 = 0.08%；旧 1f：wait 1,042 / wake 11
- **prefetch_gate_ok 一致性修复兑现预期**：wake 成为主导结束路径，60s 超时不再是主导（recompute timeout 仅 17）

### 3.5 归因 100% 可解释（220 dispositions + 35 recompute）
- dispositions：shortfall 72（PARTIAL restore）、too_short 63（policy-terminal）、denied_rate_limit 46（32 restored + 14 timeout）、revoked:miss 18、hybrid_discard 21
- recompute 35 = **miss 18（↔ revoked:miss 18，1:1 对应）+ timeout 17（14 个 rate-limit 后超时 + 3 个普通）**——全部有原因分类，无 unknown
- restore_ready 93 次（成功 restore 服务）

### 3.6 判据
- **签名 0 ✓**：94/94 成功行 output_sha16 与 payload 期望一致（mismatch 0）
- **CHAIN_GAP ✓**：chain_check 直读 0c——earliest=0、stored_runs=[[0,20863,20864]]、无内部洞、尾部 missing 46（=验收线）
- **优雅退场 ✗**：23:20:35 idle sanity_check AssertionError → SIGQUIT（非 OOM、非时间盒）
- 0 残留 ✓、GPU 15MiB/0% ✓

### 3.7 新问题：sanity_check 与 hollow 节点冲突（唯一阻塞项）
- 23:20:35（94/96 完成后 idle）：`Sanity check FAILED: node 511 mamba host present but Full.host_value=None; node 511 dead: no Full device and no Full host` → unified_tree_core.py:2477 AssertionError → SIGQUIT
- node 511 轨迹：23:17:37 `prefetch success ... loaded=5117`（prefetch 加载节点）——之后 mamba host 保留但 Full 被 evict → **hollow 状态**（hollow-eviction fallback 的设计产物）
- **hollow 节点与 sanity_check 断言冲突**：断言要求"有 Full 或无 host"，hollow 中间态（有 mamba host 无 Full）被判 violation。引擎日志无 "hollow" 字样（hollow 逻辑不打印）
- 影响：最后 2 请求（a5-t11-downgrade、a5-t12-restore）在引擎死时 in-flight 失败

## 4. followups

1. **协调人裁决/修复**（唯一阻塞项）：hollow-eviction fallback 产生 node 511 态（mamba host 无 Full）→ sanity_check（unified_tree_core.py:2477）断言冲突。二选一：(a) sanity_check 接受 hollow 合法态（更新断言——hollow 是设计）；(b) 修 hollow 创建路径（不该残留 mamba host）。修后重跑确认 96/96 + 优雅退场
2. collect_metrics l3_to_h_wait/quota 指标 missing 原因待查（窗口/计数器）
3. 12 指标表中 turns/s 0.148 / p95 133.6s / recompute 752K 为**本次非截断值**（94/96 窗口），重跑后可作最终基线

## 5. open_issues

- sanity_check AssertionError（node 511 hollow）——优雅退场判据缺口 + 2 failed 的原因
- OOM 问题已确认修复（五次 OOM → 本次 OOM=0，device_locked_tokens=0）
