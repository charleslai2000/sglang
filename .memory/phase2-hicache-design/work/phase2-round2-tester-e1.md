# phase2-round2-tester-e1 — 点3 miss re-arm durable_coverage 收紧 (9c9e7b7c7c) 后 P1 deterministic workload 6 点复测

```text
status: done
artifacts:
  - 24052 引擎同步: commit 9c9e7b7c7c 两文件 (scheduler.py + test_hicache_restore_scheduler_feed.py),
    部署 md5 495b8851 / 465b6c68 == 9c9e7b7c7c blob (hash-object 核对), 关键方法 present=10
  - 备份 .bak-round2-pre 两份核验 == 920003bf07 (scheduler e1b74995 / test c94a55db), 保留
  - 远程单元: 5 目标套件 323 passed; test_drain_reentry 5 failed 为 BASE 预存在 mock 缺陷
    (_FakeTreeCore 缺 get_component_device_value, unified_radix_cache.py:2241, 与本次改动无关)
  - stress run: /root/evidence-gate3-round2/ (566 reqs, elapsed 31min, rc=0) + /root/engine-gate3-round2.log (48MB)
  - 本地分析副本: /tmp/round2-evidence/{engine-gate3-round2.log, runs.csv, analyze_*.py}
  - 分析脚本 (analyze_p4/p5/states/cycle/loop2/http) 已对 P4 基线校准:
    P4 复核 = revoked:miss 1669/2.964, too_short 54/3, restore_success 77, worst offender 38 (逐字节复现)
  - /data 实验命名空间 /data/l3/p2io-gate3-round2 已清理 (28G→4K), /data 复原 15% (160G free)
  - 本报告
evidence:
  - 见下分节: 同步/单元; 负载可比性; 6 点逐点 (含机制实证); 点3 削减分解; 环境复原
summary:
  - 点 1/2/4/5/6 PASS; 点 3 FAIL (唯一 gate 项)
  - 点 3 revoked:miss/req 2.964 → 2.786 (-6%, -92 events), 仍 > 2.5 gate 上限
  - 最差 offender 38 → 34 (回落但未到 15-22); revoked:miss tight<1s loops 116 → 102
  - 机制实证 (决定性): 削减全部落在 never-restore (rm-only) 桶 -113 (1450→1337),
    即 ① 成功拦截了注定 miss 的无物材 re-probe; restored 桶 +21 (219→240, 随 restore_success 53→55)
    为点5 合法物材 re-probe, 未被误压
  - 残量 1337 全为"同锚 version 前移 + 链有 durable 物材 (gate 正确放行)" 的合法 re-probe,
    物材在 offender 窗口持续写入 (32% re-probe 窗内有 extent_write, 全局写入持续),
    结构上不可再压 (任何再压将误杀点5) → 触发升级用户裁决
verdict: 6 点中 5 点 PASS (1/2/4/5/6), 点 3 FAIL (revoked:miss/req 2.786 > 2.5) → 总判 FAIL, 不进 soak
```

## 0. 环境与代码前置 (均核实)

- 机: 175.155.64.171:24052 (root), RTX 3090 24G; 起始 GPU 0%/15MiB, /data 15% (160G free)。
- 引擎 repo: /root/sglang-b1-continuity (editable install, 非 git, 手工同步)。
- **同步前核验**: 部署 scheduler=e1b74995 == 920003bf07 逐字节; test=c94a55db == 920003bf07;
  备份 .bak-p4-pre 核验 == 0f8542c1a5。
- **备份**: `.bak-round2-pre` 两份 (scheduler + test) 创建并核验 == 920003bf07
  (scheduler e1b74995 / test c94a55db), 保留。
- **同步**: commit 9c9e7b7c7c 两文件 scp 至远程, 部署 md5 495b8851 / 465b6c68 == 9c9e7b7c7c blob
  (git hash-object 495b8851 / 465b6c68), 关键方法 present (`_miss_rearm_decision` :3991 /
  `_miss_rearm_durable_coverage` :4039 / 调用点 :4849 / deepest_durable_ancestor) = 10。
- 其余生产文件 (unified_radix_cache/radix_cache/schedule_batch/ready_horizon/hicache_restore) 未动,
  部署 md5 与同步前一致。
- 并发: 无 gate3 lock / 无残留 sglang 引擎; 未动 22151; 只 24052。

## 1. 远程单元复核 (sglang-patch env)

- 5 目标套件 (test_hicache_restore / test_hicache_restore_scheduler_feed / test_p3_warmtree_hol /
  test_ready_horizon_unit / test_storage_regression): **323 passed** (匹配 coder 报告 323;
  基线 314 → 323 净 +9 为本次新增用例)。
- test_drain_reentry: **5 failed, 25 passed** — 全部为 `unified_radix_cache.py:2241` `_FakeTreeCore`
  缺 `get_component_device_value` 的 BASE 预存在 mock 缺陷, 与本次改动无关 (逐例确认 failure mode:
  AttributeError)。前几轮已复核。
- 注: 需 `CUDA_HOME=/root/miniconda3` + `PATH=/root/miniconda3/bin:$PATH` 才能通过 deep_ep 集合
  (find_cuda_home 需 nvcc)。非产品改动。

## 2. stress 配置与运行 (复刻同一 gate3_ab 负载)

- 驱动: `gate3_ab.sh --tag round2 --agents 8 --launch /root/direct-launch-gate1-rhon.sh --rt 400
  --budget 1800 --cmax 900 --max-size 200G --file-size 30G` (与 P4 逐参一致)
- 引擎: RH ON, write_back, L3 extent, MAX_SIZE=200G FILE_SIZE=30G, max_total_tokens=65536,
  hicache_ratio=1.5, page_size=1 — 与 P4/p0fix2/P1/too_short/peranchor 同配置。
- 结果: **COMPLETE rc=0**, 引擎存活满 31min, 566 请求, 无崩溃无重启 (driver finished 08:58:05 rc=0)。
- /data 起始 15%, 独立 STORAGE_DIR /data/l3/p2io-gate3-round2 (28G), 实验后已清理 (28G→4K), /data 复原 15%。
- **负载可比性**: extent_write 9660 (P4=9402, p0fix2=9713, P1=9893 同量级);
  请求 566 (P4=563, 545-569 区间内); storage_generation max 3407 (P4=3469 同量级);
  GPU avg 95.0% (P4 95.0%); mem avg 19.6GB/24G (P4 20.0GB)。可比。

## 3. 核心判据对照表 (同一 gate3_ab 负载, 同一分析脚本)

| 指标 | P1 | p0fix2 | P4 | **round2** | 判定 |
|---|---|---|---|---|---|
| revoked:miss | 1159 | 1618 | 1669 | **1577** | 点3 -92 |
| revoked:miss /req | 2.06 | 2.84 | 2.964 | **2.786** | 点3 FAIL (>2.5) |
| revoked:miss worst rid | 9 | 34 | 38 | **34** | 点3 回落未到 15-22 |
| revoked:miss tight<1s loops | — | 73 | 116 | **102** | — |
| restore_success | 97 | 103 | 77 | **80** | 点2 PASS (>53) |
| restore-hit turns (restore-kind) | 25 | 29 | 23 | **14** | — |
| restore-hit tokens (restore-kind) | 211K | 206K | 160K | **126K** | — |
| too_short | 307 | 380 | 54 | **40** | 点4 PASS |
| too_short tight<1s loops | 219 | 315 | 3 | **0** | 点4 PASS |
| too_short worst rid | 68 | 72 | 6 | **2** | 点4 PASS |
| **empty-spin DQ→too_short→DQ <1s** | — | 315 | 2 | **0** | 点4 机制 PASS |
| frontier_wait | 215 | 152 | 136 | **111** | — |
| restore_retry cause=frontier | 153 | 138 | 127 | **98** | — |
| no_material recompute | 0 | 1 | 1 | **0** | 点1 PASS |
| DEVICE_QUOTA WAIT (state evt) | 649 | 1107 | 685 | **740** | — |
| restore_retry cause=capacity | — | 1063 | 671 | **652** | — |
| restore_recompute cause=miss | 1659 | — | 1718 | **1636** | — |
| restore_recompute timeout | 5 | 1 | 14 | **12** | — |
| extent_write | 9893 | 9713 | 9402 | **9660** | 负载可比 |
| 请求数 | 562 | 569 | 563 | **566** | 负载可比 |

> 分析脚本复现校准: analyze_p4.py 对 P4 基线逐字节复现 revoked:miss 1669/2.964, too_short 54/3,
> restore_success 77, worst offender 38 — 保证同口径可比。

## 4. 六点逐点验证

### 点 1 — no-material 不误杀合法 restore: **PASS**
- no_material recompute = **0** (P4=1, peranchor=80 早已消除)。
- no_material rid ∩ restore_success rids = 0; 无 restore-kind 误 forward。
- ⇒ **点 1 PASS**。

### 点 2 — restore_success: **PASS (定格判据 >53 且点1/5 无回归)**
- restore_success **77 → 80** (P4 77, 微升), restore-hit tokens 160K → 126K。
- 高于修复前 peranchor 53; 点1/5/6 无回归。符合 architect 点2 裁决接受判据 (77 定格 >53)。
- ⇒ **点 2 PASS**。

### 点 3 — revoked:miss tight churn 不反弹: **FAIL (回落但未达 ≤2.5)**
- revoked:miss/req = **2.786** (P4 2.964, -6%, -92 events)。**仍 > 2.5 gate 上限**。
- 最差 offender 38 → **34** (回落 4, 未到 architect 预期 15-22); tight<1s loops 116 → 102。
- **机制实证 (决定性, 削减分解)**:
  - 削减全落在 never-restore (rm-only) 桶: **-113** (1450 → 1337)。这正是 ① 设计拦截的
    "注定 miss 的无物材 re-probe"。
  - restored 桶 (rm+rs): **+21** (219 → 240), 随该桶 restore_success **+2** (53 → 55)。
    这是点5 合法物材 re-probe, **未被误压** (① 不减少真物材到达后的 re-restore)。
  - 总削减 -92 = rm-only -113 + restored +21。① 机制按设计工作。
- **残量结构**: 全部 1577 revoked:miss 均紧邻同 rid 的 prefetch_revoke (100% 是真实 re-probe)。
  残量 1337 rm-only 全为"同锚 version 前移 + 链有 durable 物材 (deepest_durable_ancestor non-None,
  gate 正确放行)" 的合法 re-probe。物材在 offender 窗口持续写入 (最差 offender a6ff48d1 34 次
  re-probe 中 32% 窗内有 extent_write, 全局 extent_write 9660 持续); storage_generation 52→161
  持续前移但每次 re-probe storage_hit=0、final_storage_survivability=host — 即物材存在于链上
  (gate 通过) 但该请求的具体前缀不可恢复 (不同 requested 前缀竞争同一锚)。
- **结构结论**: 残量是带物材的合法同锚 re-probe (点5 领域), 结构上不可再压 — 任何再压都会
  误杀点5 合法 re-restore。**此点触发升级用户裁决** (见 §6)。
- ⇒ **点 3 FAIL** (2.786 > 2.5), 附完整机制证据与削减分解。

### 点 4 — too_short 不反弹: **PASS**
- too_short 54 → **40**; tight<1s 3 → **0**; 最差 rid 6 → **2**; empty-spin 315 → **2 → 0**。
- 全 40 事件 requested<256 (亚阈值), 散布单发, 无 13-600ms 紧循环。
- P4 门在 T6 re-arm 层 (准入前) 未被 ① 触碰, 容量唤醒 (DEVICE_QUOTA 685→740, cause=capacity
  retry 671→652) 同量级; empty-spin 保持 0。
- ⇒ **点 4 PASS** (达成并保持 architect 量化预期, 未反弹)。

### 点 5 — legitimate 同锚重新 restore: **PASS**
- restore_success 80 中 **72** 有 prior WAIT_CAPACITY + RESTORING (P4 73/77) — MISS→WAIT→
  RESTORING→restore_success 循环真实工作。
- 49 rid 同时有 revoked:miss + restore_success (完整 cycle)。
- restored 桶 +21 rm evts 随 +2 restore_success, 证明真物材到达后的 re-restore 未被 ① 减少。
- ⇒ **点 5 PASS** (① 不减少真物材到达后的 re-restore, 对照上轮 73/77 保持)。

### 点 6 — correctness / HTTP / OOM / zero-progress: **PASS**
- 566/566 HTTP 200, finished=True, output_sha16 全非空。
- CUDA out of memory / MemoryError = 0; Scheduler exception = 0。
- GPU avg 95.0% (max 100%, min 0%), mem avg 19.6GB (max 19.7GB, 24G 卡); 最后 restore_success
  08:57:03 (run 末 08:58:05), 无 zero-progress。
- TTFT p50=19.9 / p90=38.1 / max=147.4s (与 P4 20.2/36.3/116.8 可比); wall p50=22.7 max=148.3。
- restore_recompute timeout 12 (有界, final_storage_survivability 10 none + 2 l3)。
- ⇒ **点 6 PASS**。

## 5. 六点结论

**6 点中 5 点 PASS (1/2/4/5/6), 点 3 FAIL (唯一 gate 项)。总判 FAIL, 不进 soak。**

- 点 1 (no-material): **PASS**。no_material 0, 0 restore-kind 误 forward。
- 点 2 (restore_success): **PASS**。77 → 80, 高于 peranchor 53, 点1/5 无回归 (architect 定格判据)。
- 点 3 (revoked:miss): **FAIL**。2.964 → 2.786 (>2.5), 最差 offender 34。① 削减全在 never-restore
  桶 (-113), 残量全为带物材合法同锚 re-probe (结构不可再压)。触发升级用户裁决。
- 点 4 (too_short): **PASS**。54/3 → 40/0, empty-spin 315→2→0, 未反弹。
- 点 5 (同锚 re-restore): **PASS**。72/80 restore_success 有 prior WAIT+RESTORING, restored 桶
  物材 re-probe 未被误压。
- 点 6 (correctness): **PASS**。全请求正确, 无 OOM/exception/zero-progress。

## 6. 点3 裁决升级 (触发用户裁决)

```text
POINT3_GATE_UPGRADE (点3 FAIL, revoked:miss/req 2.786 > 2.5)
evidence:
  - revoked:miss/req 2.964 → 2.786 (-92 events, -6%); 最差 offender 38 → 34; tight<1s 116 → 102
  - 削减分解 (决定性): never-restore 桶 -113 (1450→1337); restored 桶 +21 (219→240, restore_success +2)
  - 残量 1337 全为同锚 version 前移 + 链有 durable 物材 (gate 正确放行) 的合法 re-probe;
    100% 紧邻同 rid prefetch_revoke; 物材持续写入 (32% offender re-probe 窗内 extent_write)
  - restored 桶效率稳定 (ratio 4.36 vs P4 4.13), 未被误压
analysis:
  - ① 机制按设计工作: 精确拦截 never-restore 无物材 re-probe, 不压真物材 re-restore (点5 PASS)
  - 但该桶比 architect 预估小: 需 ~260 削减才能到 2.5, 实际 -92; 残量是带物材的合法同锚 re-probe
    (点5 领域), 结构上不可再压 (任何再压将误杀点5)
  - 这印证 architect §3 预判: "若 ① 后仍 >2.5, 残留 = 带 durable 物材的合法同锚 re-probe (点5 领域,
    结构上不可再压), 须升级用户裁决 (接受 ≈peranchor-2.9 或放宽目标), 不能 heuristic 硬压"
  - 现 2.786 恰在 architect 预判的 "≈peranchor-2.9" 区间
suggested_owner: 用户 (裁决接受 2.786 / 放宽目标上限, 或权衡点5/点3 固有 trade)
```

## 7. claim 判定

```text
claim: 点3 miss re-arm durable_coverage 收紧 (9c9e7b7c7c) 后 P1 deterministic workload 6 点全 PASS
verdict: refuted (6 点中 5 点 PASS, 点 3 FAIL)
basis:
  - 点 1/2/4/5/6 PASS: no_material 0 无误 forward; restore_success 77→80 (>53); too_short 54/3→40/0
    (empty-spin 0); 72/80 同锚 re-restore cycle 工作; 全请求正确无 OOM/zero-progress
  - 点 3 FAIL: revoked:miss/req 2.786 > 2.5 gate 上限
  - ① 机制实证: 削减全在 never-restore 桶 (-113), restored 桶 +21 为合法物材 re-probe (点5 未误压);
    残量为带物材合法同锚 re-probe, 结构不可再压 → 触发升级用户裁决
limitations:
  - 单次 run; /data 与 L3 碎片跨 run 独立, 但对照趋势 (削减分解/桶结构) 稳定且同口径脚本校准
  - 残量"带物材但不可恢复"的判定基于系统级证据 (extent_write 窗口 + storage_generation 前移 +
    storage_hit=0), 非逐链 dda 直接日志 (日志不打印 re-arm 时刻 dda 值)
  - restored 桶 +21 归因 (合法物材 re-probe) 有数据支撑 (restore_success +2, ratio 稳定) 但非决定性因果
```

## 8. 环境最终状态

- 代码: 24052 引擎两文件 = commit 9c9e7b7c7c (scheduler 495b8851, 关键方法 present=10);
  备份 .bak-round2-pre 核验 == 920003bf07 保留; 其余生产文件未动。
- /data: 15% (160G free), 本实验命名空间 /data/l3/p2io-gate3-round2 已清理 (28G→4K)。
- GPU: idle 0%/15MiB; 无残留引擎/lock; 未动 22151。
- 证据保留: /root/evidence-gate3-round2/ + /root/engine-gate3-round2.log (48MB) + 分析脚本;
  本地副本 /tmp/round2-evidence/。

## 9. followups / open_issues

- (open, 触发用户裁决) 点 3 revoked:miss/req 2.786 > 2.5 gate 上限。① 削减 92 全在 never-restore
  桶, 残量 1337 为带物材合法同锚 re-probe (点5 领域), 结构不可再压。与 architect §3 预判
  "≈peranchor-2.9 区间" 一致。需用户裁决: 接受 2.786 / 放宽目标, 或接受点5/点3 固有 trade。
- (closed) 点 2 restore_success 77→80: 高于 peranchor 53, 点1/5 无回归, 符合 architect 定格判据。
- (closed) 点 4 too_short: 40/0, empty-spin 0, 保持 architect 预期, 未反弹。
- (closed) 点 1/5/6: no_material 0 无误 forward; 同锚 re-restore 循环工作 (72/80); 全请求正确。
