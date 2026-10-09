# phase2-p4-tester-e1 — P4 DEVICE_QUOTA 当前-suffix 门 (920003bf07) 后 P1 deterministic workload 6 点复测

```text
status: done
artifacts:
  - 24052 引擎同步: commit 920003bf07 两文件 (scheduler.py + test_hicache_restore_scheduler_feed.py),
    部署 md5 e1b74995 / c94a55db == 920003bf07 blob (0043274c / 4fd596db), P4 门 present=2
  - 备份 .bak-p4-pre 两份核验 == 0f8542c1a5 (scheduler 12e10a79 / test 0ebc776b)
  - 远程单元: 5 目标套件 314 passed; test_drain_reentry 5 failed 为 BASE 预存在 mock 缺陷
  - stress run: /root/evidence-gate3-p4/ (563 reqs, elapsed 1845.6s, rc=0) + /root/engine-gate3-p4.log
  - 本地分析脚本 (复制至远程): analyze_p4.py / analyze_p5.py / analyze_states.py / analyze_cycle.py /
    analyze_loop2.py (empty-spin 检测器), 已对 p0fix2 基线校准
  - /data 实验命名空间 /data/l3/p2io-gate3-p4 已清理 (28G→4K), /data 复原 15%
  - 本报告
evidence:
  - 见下分节: 同步/单元; 对照表; 6 点逐点; P4 机制实证; 环境复原
summary:
  - 点 4 (too_short) 达成 architect 量化预期: 380/315 → 54/3 (tight<1s), empty-spin 315→2,
    全 54 事件 requested<256 (亚阈值), 13-600ms 紧循环消除
  - 点 1/5/6 PASS: no_material 误 forward 消除 (80→1, 0 restore-kind 误 forward),
    同锚 re-restore 循环工作 (73/77 restore_success 有 prior WAIT+RESTORING), 全请求正确
  - 点 2 部分回落: restore_success 103 → 77 (storage_hit tokens 206K→160K), 低于"~103 保持"预期
  - 点 3 FAIL: revoked:miss/req 2.964 > 2.5 上限 (architect 预期 2.2-2.4), 最差 offender 34→38
    (预期 15-22), 未回落反升
verdict: 6 点中 4 点 PASS (1/4/5/6), 2 点未达标 (2 部分回落 / 3 FAIL) → 总判 FAIL, 不进 soak
```

## 0. 环境与代码前置 (均核实)

- 机: 175.155.64.171:24052 (root), RTX 3090 24G; 起始 GPU 0%/15MiB, /data 15% (160G free)。
- 引擎 repo: /root/sglang-b1-continuity (editable install, 非 git, 手工同步)。
- **同步前核验**: 部署 scheduler=12e10a79 == 0f8542c1a5 逐字节; test=0ebc776b == 0f8542c1a5;
  P4 门 (grep `_current_prefetch_suffix_lt_threshold`) = 0 (尚未应用)。
- **备份**: `.bak-p4-pre` 两份 (scheduler + test) 创建并核验 == 0f8542c1a5
  (scheduler 12e10a79 / test 0ebc776b), 保留。
- **同步**: 两文件 scp 至远程, 部署 md5 e1b74995 / c94a55db == 920003bf07 blob
  (git hash-object 0043274c / 4fd596db), P4 门 present=2。其余生产文件 (unified_radix_cache/
  radix_cache/schedule_batch/ready_horizon/hicache_restore) 未动, 保持 == 0f8542c1a5。
- 并发: 无 gate3 lock / 无残留 sglang 引擎; 未动 22151; 只 24052。

## 1. 远程单元复核 (sglang-patch env)

- 5 目标套件 (test_hicache_restore / test_hicache_restore_scheduler_feed / test_p3_warmtree_hol /
  test_ready_horizon_unit / test_storage_regression): **314 passed** (预期 310+, 匹配 coder 报告,
  基线 310→314 净 +4 为本次新增 P4 用例)。
- test_drain_reentry: **5 failed, 25 passed** — 全部为 `unified_radix_cache.py:2241` `_FakeTreeCore`
  缺 `get_component_deviation` 的 BASE 预存在 mock 缺陷, 与本次改动无关 (逐例确认 failure mode)。
- 注: 需 `CUDA_HOME=/root/miniconda3` + `PATH=/root/miniconda3/bin:$PATH` 才能通过 deep_ep 集合
  (find_cuda_home 需 nvcc)。非产品改动。

## 2. stress 配置与运行 (复刻同一 gate3_ab 负载)

- 驱动: `gate3_ab.sh --tag p4 --agents 8 --launch /root/direct-launch-gate1-rhon.sh --rt 400
  --budget 1800 --cmax 900 --max-size 200G --file-size 30G`
- 引擎: RH ON, write_back, L3 extent, MAX_SIZE=200G FILE_SIZE=30G, max_total_tokens=65536,
  hicache_ratio=1.5, page_size=1 — 与 p0fix2/P1/too_short/peranchor 同配置。
- 结果: **COMPLETE rc=0**, 引擎存活满 1845.6s, 563 请求, 无崩溃无重启。
- /data 起始 15%, 独立 STORAGE_DIR /data/l3/p2io-gate3-p4 (28G), 实验后已清理 (28G→4K), /data 复原 15%。
- 负载可比性: extent_write 9402 (p0fix2=9713, P1=9893, peranchor=9344, too_short=9940) 同量级;
  请求 563 (545-569 区间内)。

## 3. 核心判据对照表 (同一 gate3_ab 负载)

| 指标 | P1 | too_short-fix | per-anchor | p0fix2 | **P4** | 判定 |
|---|---|---|---|---|---|---|
| revoked:miss | 1159 | 1205 | 1423 | 1618 | **1669** | — |
| revoked:miss /req | 2.06 | 2.21 | 2.52 | 2.84 | **2.964** | 点3 FAIL (>2.5) |
| revoked:miss worst rid | 9 | 9 | 36 | 34 | **38** | 点3 FAIL (未回落反升) |
| revoked:miss tight<1s loops | — | — | — | 73 | **116** | — |
| restore_success | 97 | 90 | 53 | 103 | **77** | 点2 部分回落 |
| restore-hit turns (restore-kind, runs.csv) | 25 | 21 | 13 | 29 | **23** | — |
| restore-hit tokens (restore-kind) | 211K | 214K | 69K | 206K | **160K** | — |
| too_short | 307 | 53 | 195 | 380 | **54** | 点4 PASS (~53) |
| too_short tight<1s loops | 219 | 5 | 138 | 315 | **3** | 点4 PASS (~5) |
| too_short worst rid | 68 | 6 | 69 | 72 | **6** | 点4 PASS |
| **empty-spin DQ→too_short→DQ <1s** | — | — | — | **315** | **2** | 点4 机制 PASS |
| frontier_wait | 215 | 162 | 11 | 152 | **136** | — |
| restore_retry cause=frontier | 153 | 105 | 5 | 138 | **127** | — |
| no_material recompute | 0 | 0 | 80 | 1 | **1** | 点1 PASS |
| DEVICE_QUOTA WAIT (state evt) | 649 | 417 | 845 | 1107 | **685** | — |
| restore_retry cause=capacity | — | — | — | 1063 | **671** | — |
| restore_recompute timeout | 5 | 4 | 1 | 1 | **14** | — |
| restore_recompute cause=miss | — | — | — | 1659 | **1718** | — |
| extent_write | 9893 | 9940 | 9344 | 9713 | **9402** | 负载可比 |
| 请求数 | 562 | 545 | 565 | 569 | **563** | 负载可比 |

> empty-spin 检测器 (analyze_loop2.py): 模式 WAIT_CAPACITY(DEVICE_QUOTA)→[RESTORING]→
> restore_disposition too_short→WAIT_CAPACITY(DEVICE_QUOTA), 全程 <1000ms。已对 p0fix2 校准
> (315, 最差 3b64d686=71 与历史报告一致)。
> P4 restore-hit turns/tokens 与 p0fix2 同口径 (仅 turn_kind=restore 且 storage_hit>0)。

## 4. 六点逐点验证

### 点 1 — no-material 不误杀合法 restore: **PASS**
- no_material recompute = **1** (与 p0fix2 同, peranchor 80 → 消除)。
- 唯一 no_material 案例 (28643896, 06:33:39, run 起点 06:33:03 后 36s) 为 write turn
  (host_hit=15944, storage_hit=0), 判定后**无** restore_success 跟进 (trace 0 命中) —
  属合法 no-material 快速 forward, 非误杀。
- 全 run 无 "no_material 判定后同 turn 又 restore_success" 的 restore-kind 误 forward 案例
  (no_material rid ∩ restore_success rids = 0)。
- ⇒ **点 1 PASS**: 误 forward 消除, 合法 restore 不被 no_material 提前转发。

### 点 2 — restore_success / storage_hit 恢复: **部分回落 (低于预期)**
- restore_success **103 → 77** (-25%), 低于 "保持 ~103" 的 P4 预期。
- restore-hit turns (restore-kind) 29 → **23**; tokens 206K → **160K**。
- frontier_wait 152 → 136 (同量级); restore_retry cause=frontier 138 → 127。
- **归因**: P4 门把亚阈值 waiter 从容量唤醒 churn 移出 (DEVICE_QUOTA 1107→685,
  cause=capacity retry 1063→671), 总 RESTORING 尝试 3224→2841; 但其中本会在 device-decay
  后容量唤醒兑现的 restore 被推迟到 T13 timeout (timeout 1→14, 全 final_storage_survivability=none,
  即有界一次 recompute, 6/14 之后仍 restore_success)。RESTORING 成功率相近 (P4 2.7% vs p0fix2 3.2%)。
- **判定**: restore_success 未保持 ~103, 明显回落至 77, 属 **P4 次生代价** (亚阈值 waiter 的
  restore 兑现从"每 pass 试探"改为"T13 有界一次"后, 兑现频率下降)。低于验收预期, 记 FAIL 项。
- 需 architect 裁决: 77 是否可接受 (仍高于 peranchor 53, 但低于 P1 97 / p0fix2 103 / strip 100)。

### 点 3 — revoked:miss tight churn 不反弹: **FAIL (未回落, 反升)**
- revoked:miss/req = **2.964**, 高于 p0fix2 2.84 且高于 ~2.5 目标上限, 更高于 P1 2.06。
- 最差 offender **38** (c966e65b), 高于 p0fix2 34, 未回落反升 (architect 预期 15-22)。
- revoked:miss tight<1s loops = **116** (p0fix2 73)。
- revoked:miss 请求数 1669 > p0fix2 1618, 但请求数 563 < 569 → 每请求指标升高。
- **归因**: P4 消除了 empty-spin (315→2), 但 revoked:miss 未随 DEVICE_QUOTA 竞争回落
  (1107→685)。恢复的 restore 路径 (Q1 修复) 仍使大量合法同锚 re-arm 探活产生 revoked:miss,
  P4 未抑制该源。DEVICE_QUOTA 池收缩但 revoked:miss 反升, 说明 revoked:miss 不再被
  REVALIDATE-bet 空转主导, 而是被 Q1 恢复后真实 restore 探活 (MISS_RECOMPUTE 1718 > 1659)
  驱动。架构师 Open Decision 2 的残风险路径被证实: 点3 需独立收紧。
- **此点触发 architect Open Decision 2/3 裁决** (revoked:miss/req 2.964 > 2.5; 最差 offender
  38 未回落 15-22)。

### 点 4 — too_short 紧循环实证: **PASS (达成 architect 量化预期)**
- too_short 380 → **54** (预期 ~53, 匹配); tight<1s 315 → **3** (预期 ~5, 匹配);
  最差 rid 72 → **6**。
- **empty-spin 机制实证 (决定性)**: DQ→too_short→DQ <1000ms 循环 p0fix2=**315**
  (最差 3b64d686=71, 与历史完全一致) → P4=**2** (单发, d905b9ed/9dcafafc 各 1)。13-600ms
  REVALIDATE-bet 空转彻底消除。
- **全 54 事件 requested<256 (亚阈值)**: 无任一 current-suffix 合格 (>=256) 请求被误判 too_short。
  54 事件散布 41 distinct rid (max 6), 稀疏单发, 非紧循环。
- **机制验证 (rid cf42cdb1 trace)**: DEVICE_QUOTA WAIT 后容量唤醒仅发生一次 (cause=capacity→
  RESTORING), 但 re-issue 是 revoked:miss (requested=2049, storage 无物材), 非 too_short 紧循环;
  剩余 too_short 事件来自 frontier-wake 重入 (requested=1), 稀疏。
- **亚阈值 waiter 不再被容量每 pass 唤醒**: DEVICE_QUOTA WAIT 1107→685, cause=capacity retry
  1063→671, 证明容量兜底不再服务亚阈值 waiter。
- **bet 兑现 / T13 兜底**: 14 个 timeout recompute (有界, final_storage_survivability=none),
  6/14 之后 restore_success — 证实 architect 设计的"current suffix 越过阈值 (device match
  衰减) 后兑现 restore, 无物材走有界 T13 recompute 一次"。
- ⇒ **点 4 PASS**: too_short 380/315 → 54/3, empty-spin 315→2, 达到 architect 预期 (~53/~5)。

### 点 5 — legitimate 同锚重新 restore: **PASS**
- 51 rid 有完整 cycle (revoked:miss + RESTORING + restore_success)。
- **73/77 restore_success** 的 rid 在 restore_success 前有 WAIT_CAPACITY + RESTORING 状态
  (MISS→WAIT→RESTORING→restore_success 循环真实存在)。
- state 分布: MISS_RECOMPUTE 1718 / WAIT_CAPACITY(DEVICE_QUOTA) 685 / RESTORING 2036 / READY 233。
- ⇒ **点 5 PASS**: 同锚 restore 循环机制被锻炼且工作。

### 点 6 — correctness / HTTP / OOM / zero-progress: **PASS**
- 563/563 HTTP 200, finished=True, output_sha16 全非空。
- CUDA out of memory / MemoryError = 0; Scheduler exception = 0。
- Traceback 62 处全为 libtorchcodec/torchcodec 启动 benign (load_torchcodec_shared_libraries
  FFmpeg 30 处 + shutdown noise), 非运行时失败。
- GPU avg 95.0% (max 100%, min 0%), mem avg 20.0GB (max 20.2GB, 24G 卡); 最后 active util
  1788735843 (run 末), 无 zero-progress; 最后 restore_success 07:03:07 (run 末 07:04)。
- TTFT p50=20.2 / p90=36.3 / max=116.8s (与 p0fix2 21.5/38.1/117.6 可比)。
- restore_recompute timeout 仅 14 (有界, 单发)。
- ⇒ **点 6 PASS**。

## 5. 六点结论

**6 点中 4 点 PASS (1/4/5/6), 2 点未达标 (2 部分回落 / 3 FAIL)。总判 FAIL, 不进 soak。**

- 点 1 (no-material): **PASS**。no_material 1, 0 restore-kind 误 forward。
- 点 2 (restore_success): **部分回落**。103 → 77 (storage_hit 206K→160K), 低于 "保持 ~103" 预期,
  为 P4 亚阈值 waiter 兑现推迟的次生代价。
- 点 3 (revoked:miss): **FAIL**。revoked:miss/req 2.964 > 2.5; 最差 offender 38 (未回落反升)。
  → 触发 architect Open Decision 2/3。
- 点 4 (too_short): **PASS**。380/315 → 54/3, empty-spin 315→2, 全亚阈值, 达到 architect 预期。
- 点 5 (同锚 re-restore): **PASS**。73/77 restore_success 有 prior WAIT+RESTORING。
- 点 6 (correctness): **PASS**。全请求正确, 无 OOM/exception/zero-progress。

## 6. claim 判定

```text
claim: P4 DEVICE_QUOTA 当前-suffix 门 (920003bf07) 后 P1 deterministic workload 6 点全 PASS
verdict: refuted (6 点中 2 点未达标: 点 2 部分回落, 点 3 FAIL)
basis:
  - 点 1/4/5/6 PASS: no_material 无误 forward, too_short 380/315→54/3 (empty-spin 315→2),
    同锚 re-restore 循环工作, 全请求正确
  - 点 3 FAIL: revoked:miss/req 2.964 > 2.5 上限, 最差 offender 38 未回落反升 → 触发 Open Decision 2/3
  - 点 2 部分回落: restore_success 103→77 (storage_hit 206K→160K), 低于 "保持 ~103" 预期
limitations:
  - 单次 run; /data 与 L3 碎片跨 run 独立, 但对照趋势 (too_short 消除 / restore 回落) 稳定
  - revoked:miss 反升归因 (Q1 恢复 restore 探活 vs P4 未抑制) 有数据支撑 (MISS_RECOMPUTE 1718>1659,
    DEVICE_QUOTA 1107→685) 但非决定性因果, 属 architect 判断
  - restore_success 77 是否可接受 (高于 peranchor 53, 低于 P1 97) 由 architect 裁决
```

## 7. 产品缺陷候选

```text
PRODUCT_DEFECT_FOUND  (点 3 revoked:miss 未回落反升 — P4 主修点4 但点3 主杠杆未兑现)
affected_behavior:   revoked:miss/req 2.964 > 2.5 (p0fix2 2.84, 未回落反升)
                    最差 offender c966e65b = 38 (预期 15-22, 反升)
                    revoked:miss tight<1s loops 116 (p0fix2 73)
                    MISS_RECOMPUTE 1718 (p0fix2 1659) — 恢复 restore 探活驱动
reproduction:        同一 gate3_ab 负载 (563 reqs, extent_write 9402), revoked:miss 1669
suggested_owner:     architect (Open Decision 2/3: 独立收紧 miss re-arm durable_ancestor 物材覆盖,
                    或用户裁决是否接受 2.964)
```

```text
PRODUCT_DEFECT_CANDIDATE  (点 2 restore_success 部分回落 — P4 次生代价)
affected_behavior:   restore_success 103 → 77 (storage_hit tokens 206K→160K)
                    restore-hit turns 29 → 23
                    亚阈值 waiter 兑现推迟至 T13 timeout (1→14, 6/14 仍 restore_success)
reproduction:        同一 gate3_ab 负载, restore_success 77 (高于 peranchor 53, 低于 P1 97)
suggested_owner:     architect 裁决 (是否可接受 / 需微调 gate 语义)
```

## 8. 环境最终状态

- 代码: 24052 引擎两文件 = commit 920003bf07 (scheduler e1b74995, P4 门 present=2);
  备份 .bak-p4-pre 核验 == 0f8542c1a5 保留; 其余生产文件未动。
- /data: 15% (160G free), 本实验命名空间 /data/l3/p2io-gate3-p4 已清理 (28G→4K)。
- GPU: idle 0%/15MiB; 无残留引擎/lock; 未动 22151。
- 证据保留: /root/evidence-gate3-p4/ + /root/engine-gate3-p4.log (24.9MB) + 分析脚本。

## 9. followups / open_issues

- (open, 触发 architect) 点 3 revoked:miss/req 2.964 > 2.5, 最差 offender 38 未回落反升。
  建议 architect 裁决 Open Decision 2/3: 是否采纳独立收紧 (miss re-arm durable_ancestor 物材
  覆盖复用), 或用户裁决是否接受 ≈peranchor 水平。
- (open, 需裁决) 点 2 restore_success 103→77: P4 亚阈值 waiter 兑现推迟的次生代价。
  是否可接受 (仍高于 peranchor 53) 由 architect/用户裁决。
- (closed) 点 4 too_short: P4 达成 architect 预期 (54/3, empty-spin 315→2), 机制实证完整。
