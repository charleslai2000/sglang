# phase2-p0fix2-tester-e1 — Q1 durable_ancestor 修复 (0f8542c1a5) 后 P1 deterministic workload 6 点复测

```text
status: done
artifacts:
  - 24052 引擎同步: commit 0f8542c1a5 四文件 (unified_radix_cache.py + scheduler.py + 2 测试), 备份
    .bak-p0fix2-pre 两份核验 == 183001f860 (per-anchor)
  - 远程单元: 5 目标套件 310 passed; test_drain_reentry 5 failed 为 BASE 预存在 mock 缺陷
  - stress run: /root/evidence-gate3-p0fix2/ (569 reqs, elapsed 1825.2s, rc=0) + /root/engine-gate3-p0fix2.log
  - 本地分析副本: /tmp/p0fix2-check/{engine-gate3-p0fix2.log, evid-p0fix2-runs.csv, gpu-util.csv, metrics-final.txt}
    及对照基线 peranchor/tooshort/p1fix/fixbstrip 日志 + runs.csv
  - 本报告
evidence:
  - 见下分节: 同步/单元; 对照表; 6 点逐点; too_short 机制归因; 环境复原
summary:
  - Q1 修复目标达成 (点 1/2/5): no_material 误 forward 消除 (80→1, 3 个关键 restore-kind 误杀案例全消失),
    restore_success 恢复 53→103 (超 P1 97/strip 100), restore-kind turns 13→29, frontier_wait 回 152。
  - 但点 3 (revoked:miss/req 2.84 > ~2.5 上限) 与点 4 (too_short 380/315 tight 反弹) FAIL。
  - too_short 反弹机制经实证确认为 REVALIDATE-bet 漂移 (367/378 事件来自 max_suffix>=256 的
    host-heavy 重请求反复进 WAIT), 非 gate 未对齐 (page-align 本就正确)。
verdict: 6 点中 4 点 PASS (1/2/5/6), 2 点 FAIL (3/4) → 总判 FAIL, 不进 soak
```

## 0. 环境与代码前置 (均核实)

- 机: 175.155.64.171:24052 (root), RTX 3090 24G; 起始 GPU 0%/15MiB, /data 15% (160G free)。
- 引擎 repo: /root/sglang-b1-continuity (editable install)。
- **同步前核验**: 部署 unified_radix_cache=03fb1896, scheduler=228eca2f == 183001f860 (per-anchor) 逐字节。
- **备份**: `.bak-p0fix2-pre` 两份创建并核验 == 183001f860 (unified 03fb1896 / scheduler 228eca2f)。
- **同步**: 四文件 (unified_radix_cache.py, scheduler.py, test_hicache_restore_scheduler_feed.py,
  test_storage_regression.py) scp 至远程, 部署 md5 == 0f8542c1a5:
  - unified bf4e2cba / scheduler 12e10a79 / scheduler_feed 0ebc776b / storage_regression 500609d2。
- 其余生产文件 (radix_cache/schedule_batch/ready_horizon/hicache_restore) 未动, 保持 == per-anchor。
- 并发: 无 gate3 lock / 无残留引擎; 未动 22151; 只 24052。

## 1. 远程单元复核 (sglang-patch env)

- 5 目标套件 (test_hicache_restore / scheduler_feed / p3_warmtree_hol / ready_horizon_unit / storage_regression):
  **310 passed** (预期 300+, 匹配 coder 报告)。
- test_drain_reentry: **5 failed, 25 passed** — 全部为 `_FakeTreeCore` 缺 `get_component_device_value`
  (unified_radix_cache.py:2241), BASE 预存在 mock 缺陷, 与本次改动无关 (逐例确认 failure mode)。

## 2. stress 配置与运行 (复刻同一 gate3_ab 负载)

- 驱动: `gate3_ab.sh --tag p0fix2 --agents 8 --launch /root/direct-launch-gate1-rhon.sh --rt 400
  --budget 1800 --cmax 900 --max-size 200G --file-size 30G`
- 引擎: RH ON, write_back, L3 extent, MAX_SIZE=200G FILE_SIZE=30G, max_total_tokens=65536,
  hicache_ratio=1.5, page_size=1 — 与 P1/too_short/P3/strip/peranchor 同配置。
- 结果: **COMPLETE rc=0**, 引擎存活满 1825.2s, 569 请求, 无崩溃无重启。
- /data 起始 15%, 独立 STORAGE_DIR /data/l3/p2io-gate3-p0fix2 (28G), 实验后已清理 (28G→4K), /data 复原 15%。
- 负载可比性: extent_write 9713 (P1=9893, peranchor=9344, too_short=9940, strip=9485) 同量级; 请求 569 (545-568)。

## 3. 核心判据对照表 (同一 gate3_ab 负载)

| 指标 | P1 | too_short-fix | per-anchor | strip | **p0fix2** |
|---|---|---|---|---|---|
| revoked:miss | 1159 | 1205 | 1423 | 2529 | **1618** |
| revoked:miss /req | 2.06 | 2.21 | 2.52 | 4.45 | **2.84** |
| revoked:miss worst rid | 9 | 9 | 36 | 22 | **34** |
| restore_success | 97 | 90 | 53 | 100 | **103** |
| restore-hit turns (restore-kind, runs.csv) | 25 | 21 | 13 | 43 | **29** |
| restore-hit tokens (restore-kind) | 211K | 214K | 69K | 306K | **206K** |
| too_short | 307 | 53 | 195 | 318 | **380** |
| too_short tight<1s loops | 219 | 5 | 138 | 250 | **315** |
| too_short worst rid | 68 | 6 | 69 | 67 | **72** |
| frontier_wait | 215 | 162 | 11 | 208 | **152** |
| restore_retry cause=frontier | 153 | 105 | 5 | 199 | **138** |
| no_material recompute | 0 | 0 | 80 | 0 | **1** |
| DEVICE_QUOTA WAIT | 649 | 417 | 845 | 1333 | **1107** |
| restore_recompute timeout | 5 | 4 | 1 | 3 | **1** |
| extent_write | 9893 | 9940 | 9344 | 9485 | **9713** |
| 请求数 | 562 | 545 | 565 | 568 | **569** |

> 注: 我的 restore-hit turns/tokens 采用 peranchor tester 同口径 (仅 turn_kind=restore 且 storage_hit>0),
> 故 peranchor 重现 13/69K 与历史报告一致。p0fix2 全部 hit 含 write/branch = 55 turns/456K tokens。

## 4. 六点逐点验证

### 点 1 — no-material 不误杀合法 restore (D2.1 修复验证): **PASS**
- no_material recompute 从 peranchor 80 → **1**。
- 3 个关键误 forward 案例 (98c75a55 / 1c417fdc / 1b8c727) 全消失 (引擎日志 0 命中)。
- 唯一剩余 no_material 案例 (7bc65911) 为 write turn (host_hit=0, storage_hit=0), 判定后无
  restore_success 跟进 (trace 无 evt=restore_success) — 属合法 no-material 快速 forward, 非误杀。
- 全 run 无 "no_material 判定后同 turn 又 restore_success" 的 restore-kind 误 forward 案例。
- Q1 机制 live (scheduler diff 含 deepest_durable_ancestor 解析 + storage_material 在判定锚上求值)。
- ⇒ **点 1 PASS**: 误 forward 消除, 合法 restore 不再被 no_material 提前转发。

### 点 2 — restore_success / storage_hit 恢复: **PASS**
- restore_success 53 → **103** (超 P1 97 / strip 100; 相对 peranchor 约翻倍)。
- restore-hit turns (restore-kind) 13 → **29** (接近 P1 25, 低于 strip 43); tokens 69K → **206K** (≈P1 211K)。
- frontier_wait 11 → **152** (P1=215 同量级, 不再塌到 11); restore_retry cause=frontier 5 → 138 (P1=153)。
- no_material 吸收 frontier-wait 路径的现象大幅消退 (80→1), restore 路径恢复。
- ⇒ **点 2 PASS**: restore_success/storage_hit 恢复到合理水平 (接近 P1 量级, 显著高于 peranchor 53)。

### 点 3 — revoked:miss tight churn 不反弹: **FAIL**
- revoked:miss /req = **2.84**, 高于 peranchor 2.52 且高于 ~2.5 目标上限, 更高于 P1 2.06。
- 最差 offender f0f34fb = **34** (略低于 peranchor 36, 但远高于 P1 9; 未回落)。
- revoked:miss tight<1s loops = 73。
- 解释: p0fix2 恢复 restore 路径后 (点 2 成功), 更多 restore 尝试进入 DEVICE_QUOTA 竞争
  (WAIT 845→1107), 伴随更多 revoked:miss。per-anchor 期 no_material 大量 fast-forward 反而压低了
  revoked:miss, 修复 Q1 后该路径重新开放, revoked:miss 回升至 2.84。
- ⇒ **点 3 FAIL**: revoked:miss/req 2.84 > 2.5, 未回到 P1 水平, 也未低于 peranchor。

### 点 4 — too_short tight churn 实证裁决: **FAIL (机制已归因: REVALIDATE-bet 漂移, 非 gate 未对齐)**
- too_short 380 (vs too_short-fix 53, P1 307, peranchor 195); tight<1s = **315** (vs 5/219/138);
  最差 rid 3b64d686 **72 次** requested=60。
- **机制归因 (决定性证据)**:
  - 4 个 top offender (72/65/65/63 次) 的 runs.csv 特征: host-heavy, current_suffix (requested) 23-61 远低于
    256, 但 max_suffix (prompt_len - host_hit_length) = 16431~21949 远高于 256 → 均通过 gate qualify。
  - 3b64d686 完整循环: `WAIT_CAPACITY(DEVICE_QUOTA) → RESTORING → restore_retry(capacity) →
    restore_disposition(RECOMPUTE requested=60 reason=too_short) → WAIT_CAPACITY(DEVICE_QUOTA)` 重复 72 次,
    间隔多为 sub-second (如 574.9→570.0=0.49s)。
  - 分类: 367/378 too_short 事件 (97%) 来自 max_suffix>=256 的 REVALIDATE-bet 保留案例; 仅 11 事件 (3%)
    来自 max_suffix<256 的 never-case (too_short-fix 应拦下但未全拦)。
  - too_short-fix (7155cd8973) 代码明确 "a prompt whose max suffix still reaches the threshold keeps its
    restore potential" — 设计上保留 REVALIDATE bet, 故这些请求不被 never-case 门拦截。
- **判定**: too_short 反弹是 **REVALIDATE-bet 漂移** (host 重 REVALIDATE-bet 请求反复进入
  WAIT→too_short 紧循环), **不是 gate 未对齐** (prompt_can_qualify_for_prefetch 本就页对齐,
  page_size=1 时 alignment 为 no-op; coder 的 Q2 证伪成立)。
- **但按验收判据**: too_short tight churn 明确反弹 (53/5 → 380/315, 且 worse than peranchor 195/138),
  与"不反弹"相悖。⇒ **点 4 FAIL** (机制归因明确, 但验收数值不满足)。

### 点 5 — legitimate 同锚状态变化后仍可重新 restore: **PASS**
- 68 个 rid 既有 revoked:miss 又有 restore_success; MISS→WAIT→RESTORING→restore_success 循环真实存在。
- 例 3a3b563d: RESTORING→revoked:miss→MISS_RECOMPUTE→WAIT_CAPACITY(DEVICE_QUOTA)→RESTORING→
  PARTIAL→restore_success(3457 tokens), 同锚 generation 前移后重新 restore。
- ⇒ **点 5 PASS**: legitimate 同锚 restore 循环机制被锻炼且工作。

### 点 6 — correctness / HTTP / OOM / zero-progress: **PASS**
- 569/569 HTTP 200, finished=True, output_sha16 全非空。
- CUDA out of memory / MemoryError = 0; Scheduler exception = 0。
- Traceback 62 处全为 libtorchcodec/torchcodec 启动 benign (libtorchcodec 相关 60), 非运行时失败。
- GPU avg 96.5% (max 100%, 尾段 0% 为 SIGTERM 停机期); 最后 restore_success 04:11:06 (run 末 04:12:18)。
- forward 全部完成; restore_recompute timeout 仅 1。
- ⇒ **点 6 PASS**。

## 5. 六点结论

**6 点中 4 点 PASS (1/2/5/6), 2 点 FAIL (3/4)。总判 FAIL, 不进 soak。**

- 点 1 (本任务核心 Q1 目标): **达成**。no_material 误 forward 消除, 3 个 restore-kind 误杀案例全消失。
- 点 2: **达成**。restore_success 103 (超 P1/strip), restore-hit turns/tokens 恢复到接近 P1 量级。
- 点 3: **FAIL**。revoked:miss/req 2.84 > 2.5 上限 (且高于 peranchor 2.52); 最差 offender 34 未回 P1 9。
- 点 4: **FAIL**。too_short 380/315 tight 反弹 (vs 53/5); 机制归因为 REVALIDATE-bet 漂移, 非 gate 未对齐。
- 点 5: **达成**。同锚 restore 循环工作 (68 rid, 例 3a3b563d)。
- 点 6: **达成**。全请求正确完成, 无 OOM/exception/zero-progress。

## 6. claim 判定

```text
claim: Q1 durable_ancestor 修复 (0f8542c1a5) 后 P1 deterministic workload 6 点全过
verdict: refuted (6 点中 2 点 FAIL: 点 3、点 4)
basis:
  - 点 1/2/5/6 PASS: no_material 误 forward 消除 (80→1, 关键案例消失), restore_success 53→103,
    frontier_wait 回 152, 同锚 restore 循环工作, 全请求正确
  - 点 3 FAIL: revoked:miss/req 2.84 > 2.5 上限, 未回落
  - 点 4 FAIL: too_short 380/315 tight (too_short-fix 基线 53/5), 反弹且 worse than peranchor 195/138
limitations:
  - too_short 反弹机制归因为 REVALIDATE-bet 漂移 (367/378 来自 max_suffix>=256), 有决定性 runs.csv + 循环
    trace 证据; 但"是否应由架构改动降低 REVALIDATE-bet 重请求进入 WAIT 的频次"属 architect 判断
  - revoked:miss /req 2.84 高于 peranchor, 部分可归因于 Q1 修复恢复 restore 路径 (DEVICE_QUOTA 竞争升高),
    属修复的次生代价; 是否可接受由 architect 裁决
  - 单次 run; /data 与 L3 碎片跨 run 独立, 但对照趋势 (restore 恢复/too_short 反弹) 稳定
```

## 7. 产品缺陷候选

```text
PRODUCT_DEFECT_FOUND  (too_short 紧 churn 反弹 — REVALIDATE-bet 漂移)
affected_behavior:   too_short 380 (too_short-fix 53), 紧循环 315 (<1s), 最差 rid 3b64d686 72 次 @requested=60
                    `WAIT(DEVICE_QUOTA)->RESTORING->too_short(requested 23-61)->WAIT` 紧循环
                    4 个 host-heavy REVALIDATE-bet 请求 (max_suffix 16K-22K) 反复进 WAIT
reproduction:        同一 gate3_ab 负载, rids 3b64d686/f6ba73fc/8b462084/545a8739
suggested_owner:     architect/coder (REVALIDATE-bet 重请求进入 WAIT 的频次抑制, 非 gate 口径)
```

## 8. 环境最终状态

- 代码: 24052 引擎四文件 = commit 0f8542c1a5; 备份 .bak-p0fix2-pre 核验 == 183001f860 保留; 其余生产文件未动。
- /data: 15% (160G free), 本实验命名空间 /data/l3/p2io-gate3-p0fix2 已清理 (28G→4K)。
- GPU: idle 0%/15MiB; 无残留引擎/lock; 未动 22151。

## 9. followups / open_issues

- (open) too_short REVALIDATE-bet 漂移 (点 4): 367/378 事件来自 max_suffix>=256 host-heavy 请求反复进
  WAIT→too_short。建议 architect 评估抑制 REVALIDATE-bet 重请求进入 WAIT 的频次 (如 DEVICE_QUOTA 下
  REVALIDATE-bet 保留是否需要次数/时长上限)。
- (open) revoked:miss /req 2.84 (点 3): Q1 修复恢复 restore 路径带来 DEVICE_QUOTA 竞争升高次生代价;
  最差 offender 34 未回 P1 9。建议 architect 判定是否需抑制。
- (open) never-case 残留 11 事件: 3% too_short 来自 max_suffix<256, 应为 never-case 门拦下但未全拦,
  可复核边界。
