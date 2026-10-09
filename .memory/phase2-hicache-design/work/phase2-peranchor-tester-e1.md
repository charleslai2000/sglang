# phase2-peranchor-tester-e1 — P1 deterministic workload 6 点验证 + no-material fast-forward 验证

```text
status: done
artifacts:
  - 24052 引擎同步: commit 183001f860 六生产文件 + 四测试文件 (备份 .bak-peranchor-pre 十份, 核验 == 3c71553a20 strip base)
  - 远程单元: 5 目标文件 300 passed; 全 3090-dev 相关套件 406 passed / 5 failed (drain_reentry pre-existing BASE mock 缺陷, 已确认与 per-anchor 无关)
  - stress run: /root/evidence-gate3-peranchor/ (565 reqs, elapsed 1827.9s, rc=0) + /root/engine-gate3-peranchor.log
  - 本地分析副本: /tmp/peranchor-check/{engine-gate3-peranchor.log, evid-peranchor/, evid-p1fix-runs.csv, evid-p3fix-runs.csv, evid-strip-runs.csv}
  - 本报告
evidence:
  - 见下分节: 环境/同步/单元; 对照表; 6 点逐点; no-material fast-forward; 环境复原
summary:
  - 核心目标 (点 2 无关链不再解除 MISS) 得到部分系统级证据: revoked:miss/req 从 P3 4.67/strip 4.45 降到 2.52 (-46%),
    证明 per-anchor 消除了约一半的 P3 式无关链 spurious re-arm。但未回到 P1 的 2.06, 最差 offender 36 反而
    高于 P3 的 35 / strip 的 22 (未回落到 P1 的 9)。
  - 发现两个产品缺陷候选 (均不破坏正确性, 但影响 restore 效率与 too_short 修复): 见 open_issues。
  - no-material fast-forward 机制成立 (80 次立即 forward, 无 60s 等待, timeout 降至 1), 但存在同 turn 竞态误 forward。
```

## 0. 环境与代码前置（均核实）

- 机: 175.155.64.171:24052 (root), RTX 3090 24G; 起始 GPU 0%/15MiB, /data 15% (160G free)。
- 引擎 repo: /root/sglang-b1-continuity (editable install, 非 git)。
- **代码同步核查 (per-anchor 纯增量确认)**:
  - 部署当前六生产文件 == 本地 opt strip base 3c71553a20 (逐字节 md5 全同: scheduler/schedule_batch/hicache_restore/ready_horizon/tree_core/radix_cache)。
  - 本地工作树 183001f860 六生产文件 + 四测试文件逐字节 == commit (md5 复核 OK); test_p3_warmtree_hol.py 为未跟踪 harness (两种代码版本均可跑)。
  - commit 183001f860 diff = 恰好 6 生产 + 4 测试 (+1158/-138), 无其它改动。备份 .bak-peranchor-pre 十份核验 == strip base。
  - 同步后部署 10 文件 md5 == 183001f860 (已复核: scheduler 228eca2f... == git show 183)。
- 同步后远程单元 (sglang-patch env, CUDA_HOME=/root/miniconda3):
  - test_hicache_restore + scheduler_feed + p3_warmtree_hol + ready_horizon_unit + storage_regression: **300 passed**。
  - 其余相关 (ready_horizon_partition/capacity_model_unit/fbe_flush/backup_spec/prefetch_budget/writeback_reserve/drain_reentry): **106 passed, 5 failed**。
  - 5 failed 全在 test_drain_reentry.py (`_FakeTreeCore` 缺 `get_component_device_value`, radix_cache.py:2241) — BASE 预先存在 mock 缺陷, 与 per-anchor 无关 (前几轮已复核)。全 3090-dev 合计 406 passed / 5 failed, 与 coder e1 报告一致。
- deployed 复核: miss_rearm_allowed 签名改锚 (miss_version/current_version/miss_anchor/current_anchor/miss_generation), 移除 current_epoch>miss_epoch; no_material_fast_forward (FrontierAnchorInfo 5 事实) live @ scheduler.py:3081/3818; anchor_storage_version/_bump_anchor_storage_version live @ tree_core.py:2153/2165。
- 并发: 无 gate3 lock / 无残留引擎; 未动 22151; 只 24052。

## 1. stress 配置与运行（复刻 P1/too_short/P3/strip 同一负载）

- 驱动: `gate3_ab.sh --tag peranchor --agents 8 --launch /root/direct-launch-gate1-rhon.sh --rt 400 --budget 1800 --cmax 900 --max-size 200G --file-size 30G`
- 引擎: RH ON, write_back, L3 extent, MAX_SIZE=200G FILE_SIZE=30G, max_total_tokens=65536, hicache_ratio=1.5, 与 P1/too_short/P3/strip 同配置。
- 结果: **COMPLETE rc=0**, 引擎存活满 1827.9s (verdict elapsed_s), 565 请求, 无崩溃无重启。
- /data 起始 15% (160G free), 独立 STORAGE_DIR /data/l3/p2io-gate3-peranchor, 实验后已清理 (28G→4K), /data 复原 15%。
- 负载可比性: extent_write 9344 (P1=9893, too_short=9940, P3=9008, strip=9485) 同量级 ✓; 请求 565 (545-568) ✓。

## 2. PASS Gate（运行自身）

| Gate | 判据 | 结果 | 判定 |
|---|---|---|---|
| 无崩溃 | Scheduler exception | 0 (62 处 Traceback 全为 libtorchcodec 启动 benign) | PASS |
| correctness | 565/565 HTTP 200, finished=True, output_sha16 全非空 | PASS | PASS |
| 无 OOM | CUDA out of memory / MemoryError | 0 | PASS |
| 无 zero-progress | GPU avg 96.5% max 100%; last restore_success 23:05:24 (run 末 23:06:02) | PASS | PASS |
| 无 HTTP error | 0 非 200 | PASS | PASS |
| forward recompute | 全请求完成; wall avg 25.2s max 197.8s | PASS | PASS |

## 3. 核心判据对照表（同一 gate3_ab 负载）

| 指标 | P1 | too_short | P3 | strip | peranchor |
|---|---|---|---|---|---|
| revoked:miss | 1159 | 1205 | 2615 | 2529 | **1423** |
| revoked:miss /req | 2.06 | 2.21 | 4.67 | 4.45 | **2.52** |
| restore_recompute | 1194 | 1242 | 2658 | 2609 | 1557 |
| restore_success | 97 | 90 | 93 | 100 | **53** |
| restore-hit turns (runs.csv) | 25 | - | 32 | 43 | **13** |
| restore-hit tokens (runs.csv) | 211K | - | 152K | 306K | **69K** |
| too_short | 307 | 53 | 365 | 318 | **195** |
| too_short tight<1s loops | 229 | 5 | 290 | - | **138** |
| frontier_wait | 215 | - | 221 | 208 | **11** |
| restore_retry cause=frontier | 153 | - | 208 | 199 | **5** |
| DEVICE_QUOTA WAIT | 649 | 417 | 1448 | 1333 | 845 |
| worst offender revoked:miss | 9 | - | 35 | 22 | **36** |
| restore_recompute timeout | 5 | 4 | 1 | 3 | 1 |
| no_material recompute | 0 | 0 | 0 | 0 | **80** |

## 4. 六点逐点验证

### 点 1 — P3 并发 ACK/reconcile 仍大量发生: **PASS**
- extent_write 9344 (vs P1 9893, P3 9008, strip 9485) 同量级; 逐 5-min bucket 1332-1603 连续不停 (写 ACK 流量持续)。
- restore_backup (flush/ack 写) 3176 (vs P1 3270, P3 3052), 逐 5-min 418-548 连续。
- P3 reconcile 机制 (_reconcile_deferred_acked) 在 per-anchor diff 中零改动; 仍每次 flush pass 扫描 deferred_acked_nodes。
- ⇒ per-anchor 改动未减少并发 ACK/reconcile 量级。**满足**。

### 点 2 — 无关链 epoch/version 变化不再解除 MISS: **partially-confirmed (系统级)** 
- revoked:miss/req 从 P3 4.67 / strip 4.45 → 2.52 (-46%)。这是最直接的系统级证据: per-anchor 消除了约一半 P3 式"无关链 bump → spurious re-arm → 反复 miss"。
- 全局 l3_publish_epoch 保留为纯诊断 (prefetch_revoke storage_generation 持续前移 77→3155→3182... 证明并发写 durability 持续推进, 诊断计数照常), 但门判据已改锚 (miss_rearm_allowed 只比较同锚 version / re-anchor / generation)。
- **局限**: 未直接观测到"同锚 MISS 被无关链 bump 期间保持不解除"的单例 counterfactual —— 日志不打印 re-arm 时刻的同锚 version 值, 只能从系统级 revoked:miss 降低推断。**核心机制证据为系统级, 非逐链直接证据**。
- **注意**: peranchor 的 MISS→WAIT(0.5s 内) 立即 re-arm 次数 (129) 高于 P1 (24)。这反映了 peranchor 更多地把 sticky miss 转成合法 re-arm (同锚 version 前移放行), 而非 P3 式无关链放行。但此点与"最差 offender 36 未回落"共同表明: per-anchor 并未完全消除 churn (见点 3)。

### 点 3 — revoked:miss churn 保持 P1 修复后低水平: **FAIL (未回到 P1 水平)**
- revoked:miss /req = 2.52。要求"≈2.06 (P1 水平)", 现高于 P1 22%; 虽远低于 P3/strip 的 4.5-4.7 (per-anchor 确实把 P3 反弹砍掉一半), 但未回落到 P1 水平。
- **最差 offender revoked:miss = 36**, 高于 P3 的 35 / strip 的 22, 更远高于 P1 的 9。P1 run 独立复现最差 9 (fixb-strip tester 亦复现 P1 最差 9)。per-anchor 的最差 offender 反而在 P3/strip 水平以上, 未回落。
- 22/36 次为 <1s 紧循环 (worst offender 22 tight / 13 gap), churn 仍存在。
- ⇒ **点 3 FAIL**: revoked:miss /req 未回到 ~2.06, 最差 offender 未回到 P1 水平 (反到 36)。

### 点 4 — restore_success / storage_hit 不被误杀: **FAIL (系统性下降)**
- restore_success 53 (vs P1 97, P3 93, strip 100) — 约减半。
- runs.csv restore-turn (同 ~333 restore turns) 转换: peranchor 13 turn / 69K tokens vs P1 25/211K, P3 32/152K, strip 43/306K。**系统性下降, 非 run 间方差** (strip 甚至 43)。
- frontier_wait 215(P1)/221(P3)/208(strip) → **11**; restore_retry cause=frontier 153/208/199 → **5**。no_material fast-forward (80) 大量吸收了原本会走 frontier-wait 并可能 restore 的请求。
- 其中 3 个 restore-kind 同 turn 案例 (1c417fdc/98c75a55/1b8c727) 显示 no_material 判定后 4-23s 同 turn 仍成功 restore (见 D2 缺陷), 证明有物材请求被误 forward。
- ⇒ **点 4 FAIL**: restore_success/storage_hit 系统性下降, 与 P1/P3/strip 同负载对照显著偏低。

### 点 5 — legitimate 同链状态变化后仍可重新 restore: **PASS (机制被锻炼)**
- 34 个 rid 既有 MISS_RECOMPUTE 又有 restore_success; 同 turn MISS→WAIT→RESTORING→restore_success 循环真实存在。
- 例 3b6c9f3d: MISS_RECOMPUTE(22:41:17, storage_generation 654) → WAIT → RESTORING → PARTIAL restore_success 8610 tokens (22:41:30), 期间同锚 generation 前移 (654→664) 触发 re-arm 放行。
- 例 1c417fdc/98c75a55: 同 turn 多次 re-probe (generation 3155→3171 前移), 门正确放行, 最终 restore_success。
- ⇒ per-anchor 门在**同锚 version 前移 / re-anchor** 时确实允许重新 restore。**满足**。

### 点 6 — too_short 修复不回退: **FAIL (too_short 修复回退)**
- too_short 195 (vs too_short-fix 53, P1 307, P3 365)。**too_short 紧循环 <1s = 138**, 最差 rid f4b42595 **69 次**, 42 次为 **13ms** 间隔。
- 这正是 too_short 修复 (7155cd8973) 设计消除的 `WAIT_CAPACITY(DEVICE_QUOTA)→RESTORING→restore_retry(capacity)→too_short(requested=29)→WAIT` 紧循环。too_short-fix run 紧循环仅 5, 最差 rid 6 次。
- per-anchor diff 未触碰 too_short 代码 (_restore_wait_capacity_fits live @ scheduler.py:3721), 但 too_short churn 反弹 (53→195), 紧循环反弹 (5→138)。**机制归因未闭合** (可能因 per-anchor 改变哪些请求进入 WAIT 路径, 或 run 间方差), 但对照 too_short-fix 基线明确是修复回退。
- ⇒ **点 6 FAIL**: too_short 未保持 too_short-fix 的低水平, never-case/DEVICE_QUOTA 守卫未拦下紧循环。

## 5. 六点结论

**6 点中仅点 1、点 5 明确 PASS; 点 2 部分确认 (系统级改善但缺逐链直接证据); 点 3、4、6 FAIL。**

- 点 2+5 (本任务核心): 点 5 机制被锻炼 (PASS); 点 2 系统级改善成立 (revoked:miss 减半) 但缺"无关链 bump 期间同锚 MISS 不被解除"的逐链直接日志证据 (日志不打印 re-arm 时刻同锚 version)。counterfactual 为**系统级**证明, 非单例。
- 点 3 revoked:miss/req 2.52 未回到 ~2.06, 最差 offender 36 (高于 P3/strip), **FAIL**。
- 点 4 restore_success/storage_hit 系统性下降 (13 vs 25/32/43 restore-hit turns), **FAIL**。
- 点 6 too_short 修复回退 (195 / 138 tight / 最差 69 @13ms), **FAIL**。

⇒ **Deliverable 1 (P1 6 点验证) 判据: FAIL** (点 3、4、6 不满足; 点 2 仅部分)。

## 6. Deliverable 2 — no-material fast-forward 验证

### D2.1 正常有物材请求不误 forward: **FAIL (存在误 forward)**
- 80 次 no_material recompute; 其中 6 次所在同 turn 结束时 storage_hit>0。按 turn kind 分类:
  - 3 write/branch-kind (552c5259/f7d5d34/24f87b5): no_material 发生在 turn 自身写物材**之前**, 判定时刻物材确缺席 (该 turn 随后写入), 属**合理**。
  - **3 restore-kind (1c417fdc/98c75a55/1b8c727): 误 forward 缺陷**。no_material 判定后 4/11/23s 同 turn 仍成功 restore (6673/6141/1412 tokens)。判定时刻物材已存在 (该窗口无新 extent_write/promotion, 见下), 但 5 事实判定漏检。
- 机制: no_material 基于当前 last_host_node 的 5 事实快照; 同 turn 内 re-match 可换到 gate-ok 的更深 last_host_node, 使原本可 restore 的请求被先行 forward。事实 2 (is_l3_durable) 读取的锚节点与后续 restore 使用的锚可能不同 (re-anchor 竞态)。
- 例 98c75a55: no_material @22:55:13, 22:55:13-22:55:24 窗口 0 extent_write / 0 promotion, 22:55:24 restore 7168 tokens → 物材在判定时刻已存在, 判定漏检。
- ⇒ **点 1 FAIL**: 有物材请求被误 forward (3 个 restore-kind 确定性同 turn 案例)。

### D2.2 无物材请求直接 forward: **PASS**
- 80 次 no_material 全部立即 ADMIT_RECOMPUTE (无 register_frontier_waiter, 无 60s T13 等待); no_material rids 与 frontier_wait rids 交集 0 (证明未走 frontier wait)。
- restore_recompute cause=timeout 仅 1 (vs P1 5, P3 1, strip 3) — 60s 死等基本消除 (9d8b5428-shape 被 fast-forward)。
- 全部 80 次无 60s 等待; 立即 forward。**满足**。

### D2.3 epoch/version 变化后可重新获得 restore eligibility: **PASS**
- 14 个 no_material rid 在 60s 内重新 restore_success; 6 个同 turn 案例 (含 3 个误 forward 的) 都显示 no_material 不是永久否决 —— 同锚 version 前移 / re-anchor 后的新请求仍能正常 restore。
- 点 5 的 MISS→WAIT→RESTORING→restore_success 循环同样适用。**满足**。

### D2 结论
- 机制成立: no-material 无物材请求立即 forward (D2.2 PASS), version 变化后可重获 eligibility (D2.3 PASS)。
- **但有物材请求误 forward 缺陷 (D2.1 FAIL, 3 restore-kind 同 turn 案例)** — no_material 与同 turn re-anchor 存在竞态, 会先行 forward 本可 restore 的请求, 造成额外 recompute 与 restore 延迟。

## 7. 产品缺陷候选

```text
PRODUCT_DEFECT_FOUND  (no-material fast-forward 误 forward 有物材请求)
affected_behavior:  restore-turn 请求在物材已存在/在途时被 no_material 先行 ADMIT_RECOMPUTE,
                    同 turn 内 (4-23s 后) 又成功 restore — 额外 recompute + restore 延迟 + restore_success 计数降低
reproduction:        同一 gate3_ab 负载, rid 1c417fdc/98c75a55/1b8c727 (restore turn):
                    no_material @T 后同 turn @T+4/11/23s restore_success (6673/6141/1412 tokens)
suggested_owner:     coder / architect
```
```
PRODUCT_DEFECT_FOUND  (too_short 修复回退 — 紧 churn 反弹)
affected_behavior:   too_short 195 (too_short-fix 53), 紧循环 138 (<1s), 最差 rid f4b42595 69 次 @13ms
                    `WAIT(DEVICE_QUOTA)->RESTORING->too_short->WAIT` 紧循环复活 (too_short-fix 基线仅 5 tight)
reproduction:        同一 gate3_ab 负载 (per-anchor 引擎), worst rid f4b42595
suggested_owner:     coder / architect (per-anchor diff 未触碰 too_short 代码, 机制归因未闭合)
```

## 8. claim 判定

```text
claim: per-anchor 修正后 P1 deterministic workload 6 点全过 + no-material fast-forward 全过
verdict: refuted (6 点中 3 点 FAIL; D2.1 存在误 forward 缺陷)
basis:
  - 点 2 系统级改善成立 (revoked:miss 4.67/4.45→2.52, -46%), 点 5 机制被锻炼 (MISS→restore 循环, 34 rid)
  - 点 3 FAIL (2.52 未回 ~2.06, 最差 offender 36 高于 P3/strip)
  - 点 4 FAIL (restore-hit turns 13 vs P1 25/P3 32/strip 43; restore_success 53 vs 90-100)
  - 点 6 FAIL (too_short 195/138 tight, 最差 69@13ms, too_short-fix 基线 53/5)
  - D2.1 FAIL (3 个 restore-kind 同 turn 误 forward), D2.2 PASS (80 立即 forward 无 60s 等待), D2.3 PASS
limitations:
  - 点 2 counterfactual 为系统级证据 (revoked:miss 降半), 缺逐链"同锚 MISS 不被无关链解除"的直接日志证据
  - 单次 run; 每 run 独立时刻 /data 与 L3 碎片不同, 可能引入跨 run 噪声; 但 restore 转换/too_short 紧循环
    与 P1/P3/strip 对照趋势稳定
  - too_short 反弹机制归因未闭合 (per-anchor 未触碰 too_short 代码, 是否交互/方差待 architect 判定)
```

## 9. 环境最终状态

- 代码: 24052 引擎 10 文件 = commit 183001f860 (per-anchor + no-material); 备份 .bak-peranchor-pre 核验 == strip 3c71553a20 保留。未动 22151; P1/P3/strip 历史未改写。
- /data: 15% (160G free), 本实验命名空间 /data/l3/p2io-gate3-peranchor 已清理 (28G→4K)。
- GPU: idle 0%/15MiB; 无残留引擎/lock。

## 10. followups

- (open) no-material 误 forward 缺陷 (D2.1): 3 个 restore-kind 同 turn 案例 — 建议 coder/architect 复核 5 事实判定与同 turn re-anchor 竞态 (是否应在 last_host_node 非最终锚时保守保 frontier wait)。
- (open) too_short 修复回退 (点 6): per-anchor 下 13ms 紧循环复活 — 机制归因未闭合, 建议 architect 判定交互/方差。
- (open) restore_success 系统性下降 (点 4): no_material 吸收 frontier-wait 路径 + 3 误 forward, 需量化并修复后复测。
- (open) 点 2 逐链 counterfactual: 建议加日志打印 re-arm 时刻同锚 version, 以直接证明"无关链 bump 期间同锚 MISS 不被解除"。
- (open) revoked:miss 最差 offender 36 未回落 (点 3): 与 P3/strip 同量级, 需复核是否 per-anchor 仍有其它 spurious re-arm 源。

## 11. open_issues

- 两个产品缺陷候选 (见 §7) 未修复, 均不破坏正确性 (全请求 HTTP 200 完成) 但影响 restore 效率 / too_short churn / restore_success。
- 6 点判据中 3 点 (3/4/6) FAIL, Deliverable 1 不 PASS。
