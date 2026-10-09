# P3 L3 durable-frontier HOL 验证（tester e1）

status: done

## 阶段 1：代码同步 + 远程单元（done）

- 本地 opt 分支 3090-24g-opt，commit 30a5a3698a（未 push）含 P3。
- diff `7155cd8973..30a5a3698a`：仅 4 文件（tree_core +58/-1、radix_cache +78、test_storage_regression +357、test_drain_reentry +3），纯增量无既有逻辑改动。
- 部署引擎 `/root/sglang-b1-continuity`（editable install，非 git）pre-P3 文件 md5 与本地基线 7155cd8973 完全一致（tree_core b254cf59…/radix 722539ada1…/两个测试文件），确认为纯增量，patch 干净可应用。
- 备份到远程 `.bak-p3pre/`（4 文件），再 scp 同步 4 个 P3 文件，md5 与本地 opt 一致（tree e04bbc2f…/radix 6ab86a51…/test_storage 3f8ee843…/test_drain 6ea760d7…）。
- 远程单元（24052 root, sglang-patch env）：
  - test_storage_regression.py -k "DeferredAckReconcile or StoragePromotionChain"：13 passed（10 新 + 3 基线）。
  - test_storage_regression.py 全量：111 passed。
  - 其余相关 10 文件（hicache_restore / scheduler_feed / ready_horizon_unit / ready_horizon_partition / capacity_model / fbe_flush / backup_spec_assert / prefetch_budget_split / writeback_reserve / drain_reentry）：266 passed / 5 failed。
  - 5 failed 全为 test_drain_reentry 的 P0 既有缺陷（`_FakeTreeCore` 缺 `get_component_device_value`，radix_cache.py:2241 的 P0 路径）。**基线复测确认**：换回 .bak-p3pre（pre-P3）文件后同样 5 failed —— 与 P3 无关，P0 另案。P3 文件已恢复，md5 复核一致。
  - 说明：4 个文件 collect 阶段需 `CUDA_HOME=/root/miniconda3`（deep_ep 依赖 cuda_home），非 P3 问题。

## 阶段 2：deterministic warm-tree（done，无 GPU，树层确定性单元）

无现成 warm-tree harness，按 dispatch 用树层确定性单元级验证（真实 UnifiedTreeCore + 真实 UnifiedRadixCache flush 路径，驱动与 coder DeferredAckReconcileCacheTests 相同的真实代码路径）。

新增独立 harness（tester 自建，只用 pre-P3 即有 API，两种代码版本均可跑）：
- 文件：`3090-dev/test_p3_warmtree_hol.py`（本地 opt + 远程均已落）
- 场景：root→a→b（及 4 深链），a 先 persisted → clear_storage_durable(a)（revoke-miss clear，无 acked 后代时放行）→ b acked 于未 persisted 的 a 下 → b 变 deferred（acked && !persisted）→ scheduler 在 b 上 park frontier waiter → 跑一 pass flush。

结果（两种版本同 harness 实测）：
- **BASELINE（换回 .bak-p3pre）**：2/2 FAIL。`frontier_anchor_ready(b)` 恒 False，b 永不 persisted，waiter 永不 wake —— 即永久 HOL 前驱，唯一出口是 60s T13 timeout → restore_recompute(timeout)（与历史 p95≈61s 根因吻合）。确定性复现。
- **P3（当前部署）**：2/2 PASS。单 pass flush 的 reconcile 补满 a 链 → a 重 promoted（root 兜底）→ b promoted → `_wake_frontier_waiters` 唤醒 waiter → frontier_anchor_ready(b)=True、pop_frontier_ready("r1")=True、restore_recompute(timeout)=0。deferred 集合清空。

结论（阶段 2）：P3 确定性消除了"deferred 永不 promotion → frontier 60s HOL"的根因链；修复前基线在完全同场景下确定性卡死，修复后单 pass 愈合。frontier_wait 从 ≈60s（timeout）→ 单 pass 内（<60s），restore_recompute(timeout)=0。

## 阶段 3：GPU c8 A/B（done，真实引擎 24052，P3 补丁）

驱动：`gate3_ab.sh --tag p3fix --agents 8 --launch /root/direct-launch-gate1-rhon.sh --rt 400 --budget 1800 --cmax 900 --max-size 200G --file-size 30G`（与 P1/P0 同款 c8 容量压力配置）。560 请求，elapsed 1822s，rc=0，GPU 空闲 15MiB 恢复，lock 清理。证据 /root/evidence-gate3-p3fix/ + engine-gate3-p3fix.log。

### 核心指标（P3 vs 基线 p1fix）
| 指标 | 基线 p1fix (pre-P3) | P3 (p3fix) |
|---|---|---|
| frontier_wait p50 | 2.3s | 1.1s |
| frontier_wait p90 | 45.2s | 12.4s |
| frontier_wait p95 | 53.4s | 25.6s |
| frontier_wait ≥55s（60s cliff） | 6 | **1** |
| frontier_wait ≥30s | 17 | 3 |
| restore_recompute cause=timeout | 5 | **1** |
| wall_s ≥58s | 24 | 23（多为容量/队列 bound，非 cliff） |

- **60s cliff 确定性消除大幅达成**：p95 从 53.4s→25.6s，≥55s cliff 6→1。但 **PASS gate 严格项 restore_recompute(timeout)=0 未达（余 1）**。
- **单剩余 timeout 分类（rid 9d8b5428, BB2, dev=17079/host=0/store=0）**：请求 anchor 链为**纯设备缓存**（无 L3 write ack、无 host copy）。P3 reconcile 只 promote `acked && !persisted`（有真实 L3 写 ack）节点，绝不伪造 durable——该链无 L3 物材，reconcile 按设计不能也不应 promote → **此 timeout 是"无 durable 物材"的正确兜底 recompute，非 P3 缺陷**。wait→timeout 恰 60.3s，与 T13 语义一致。
- L3 保持 ON 且服务：54 请求 storage_hit（313,606 tokens）全 HTTP 200；68 个 hicache 指标在 /metrics。
- **open decision 4（写放大）**：P3 无写放大，反降。extent_write 9008 vs 9893、recycle 3448 vs 3832、dropped 39886 vs 58937、backuped 5.54M vs 6.16M、prefetched 0.51M vs 1.06M。reconcile 幂等补写未增加 L3 写，反而因消除 timeout churn 减写。
- **open decision 3（B 守卫开销）**：revoke-miss clear 路径调用点极少，无异常延迟观测（frontier 唤醒分布显示绝大多数 0.2-3.4s 内 resolve）。无异常。

## 阶段 4：correctness 4 项（done）+ soak（未做，见 followups）

- **0 OOM**：grep OOM/RuntimeError/CUDA error = 0（1467 系 grep -i 误匹配 ready_stage 行，逐项复核后 OOM=0）。GPU mem max 20183<24576。
- **0 HTTP error**：560 请求全 http=200，0 非 200。
- **0 zero-progress**：560 全 finished=True 且有 output_sha16（非空输出）。new_tokens_est=None 的 113 条为 write turn 无生成指标，非零进度。
- **0 durability violation**：54 个 storage_hit（L3 真实读回）请求全 finished+HTTP 200，无 fake-durable 读回失败。2 个 restore_loadback_fail 为 revoked:miss/alloc_failed 正常回退，请求均 200 完成，非伪造 durable 读回失败。
- soak：因 30min A/B 已覆盖 c8 容量压力且正确性 4 项全过，预算内未另跑 2h soak（见 followups）。

artifacts:
- 远程备份：/root/sglang-b1-continuity/.bak-p3pre/（4 文件）
- 远程同步：4 个 P3 文件（md5 与本地 opt 30a5a3698a 一致）
- 独立 harness：3090-dev/test_p3_warmtree_hol.py（本地 + 远程，两种代码版本可跑）
- GPU 证据：/root/evidence-gate3-p3fix/ + engine-gate3-p3fix.log
evidence:
- 见各阶段正文
summary:
- 阶段 1-2 done：P3 纯增量同步成功，远程单元绿（111 storage_regression + 相关套件，P0 既有 5 failed 基线复测无关）；deterministic warm-tree 修复前 HOL 确定性复现、修复后单 pass 愈合。
- 阶段 3-4 done：GPU c8 A/B 60s cliff 6→1、frontier p95 53.4→25.6s、L3 ON 且服务、correctness 4 项全 0、无写放大（反降）。
- **核心判据 restore_recompute(timeout)=0 未完全达成（余 1，分类为"无 durable 物材的正确兜底 recompute"而非 P3 缺陷）**。p50=1.1s（达标 1-2s），p95 无 60s 确定性峰。
followups:
- 2h warm-tree soak（确认长期无 60s cliff 复发）未做，预算内可补。
- 若严格 gate 要求 timeout 必须=0：建议评估该单例是否需进一步处理（如对"纯设备缓存无 L3 物材"的 FRONTIER 等待提供更快的前向判定）。此为优化建议，非 P3 缺陷。
open_issues:
- 无阻塞。1 个剩余 restore_recompute(timeout) 已分类为正确兜底（无 durable 物材），非 P3 缺陷。

## 结论（claim 判定）
claim: P3（commit 30a5a3698a，A+B reconcile）消除 L3 durable-frontier 确定性 HOL（60s cliff）。
verdict: **partially-confirmed**
basis:
- 确定性 warm-tree：修复前 frontier 永久不 ready（60s HOL 前驱），修复后单 pass 愈合、frontier_wait<60s、restore_recompute=0 —— 根因链确定性消除。
- GPU c8：60s cliff 6→1、frontier_wait p95 53.4→25.6s、p50=1.1s、L3 ON 服务正常、correctness 4 项全 0、无写放大。
limitations:
- 严格 PASS gate restore_recompute(timeout)=0 未达（余 1 例，分类为"无 durable 物材的正确兜底 recompute"，非 P3 缺陷）。
- p95=25.6s 高于 dispatch 所述"1-2s"目标（该目标针对 p50=1.1s 已达标；p95 偏高由容量/队列 bound 与少量 FRONTIER 等待构成，非确定性 60s 峰）。
- 未跑 2h soak。

