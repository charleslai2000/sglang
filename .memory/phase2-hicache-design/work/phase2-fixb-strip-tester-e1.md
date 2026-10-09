# phase2-fixb-strip — tester e1 — deterministic miss-churn A/B（剥离 Fix B 后 epoch 门单独验证）

```text
status: done
claim: 剥离 Fix B 后 P1 的 epoch 门单独是否维持系统级 miss-churn 改善
verdict: refuted（当前负载下改善不再成立，且证明与剥离无关——回归早于剥离）
artifacts:
  - 代码同步: 3c71553a20 五文件 → 24052 引擎（备份 .bak-strip-pre 五份）
  - 远程单元: test_hicache_restore.py + feed = 95 passed；相关套件 215 passed；
    test_drain_reentry.py 5 failed（pre-existing mock，与本任务无关）
  - stress run: /root/evidence-gate3-fixbstrip/（verdict 568 reqs, elapsed 1820.3s, rc=0）
  - 分析副本: /tmp/stripcheck/{fixbstrip-engine.log,p3fix-engine.log,tooshort-engine.log,evid/}
evidence:
  - 对照表（同一 gate3_ab 负载: 8 agents, rt=400, MAX_SIZE=200G FILE_SIZE=30G）
  - 剥离后 run 全 PASS gate（见 §3）
  - 关键: P3-with-FixB 与剥离 run 的 miss churn 同量级 → 剥离中性
  - 归因: miss churn 在 P3(30a5a3698a) 引入时已翻倍，早于剥离
summary: 剥离本身中性（strip ≈ P3 均 ~2500-2600）；但 P1 声称的改善在当前负载下
  不可复现——连含 Fix B 的 P3 基线都在 P0 水平以上。epoch 门单独不足以维持 P1 改善，
  且这并非剥离所致（见 §4 归因）。
followups:
  - (open) P3 deferred-ACK reconcile 引入 miss churn 翻倍（1159→2615），需 architect 复核
  - (open) l3_publish_epoch ~2.1/s 全局前移 → epoch 门实际退化为"永远放行 re-arm"，
    与 architect open issue 1 完全吻合
open_issues:
  - P1 声称的"最差 offender 68→1 miss"未复现：P1 run 实测最差 9 miss（我分析）
  - DEVICE_QUOTA 紧循环在当前引擎两条路径（epoch 门 + Fix B）都无法拦截（见 §4.2）
```

## 0. 环境与代码前置（均核实）

- 机: 175.155.64.171:24052 (root), RTX 3090 24G; 起始 GPU 0%/15MiB, /data 15% (160G free)。
- 引擎 repo: /root/sglang-b1-continuity (editable install, 非 git)。
- **代码同步核查 (cleanup 纯增量确认)**:
  - 部署当前五文件 == 本地 opt 30a5a3698a（逐字节 md5 全同: scheduler/schedule_batch/
    hicache_restore 3 生产文件 + 2 测试文件）。
  - cleanup 3c71553a20 diff = 纯剥离（-135/+5）：删 device_quota_degraded /
    DEVICE_QUOTA_MAX_TIMEOUTS / hicache_restore_device_quota_timeouts / T13 累加 /
    restore_success 清零 / T6 的 if-not-degraded 包装（改无条件应用）+ 测试类
    DeviceQuotaBoundedDegradationTests 删除 + feed 字段删除。无其它改动。
  - 按授权同步 3c71553a20 五文件，备份 .bak-strip-pre 五份（核验 == 30a5a3698a）。
- 同步后远程单元 (sglang-patch env):
  - test_hicache_restore.py + test_hicache_restore_scheduler_feed.py: **95 passed**
  - ready_horizon_unit/partition + storage_regression + p3_warmtree + prefetch_budget:
    **215 passed**
  - drain_reentry + writeback_reserve + backup_spec + fbe_flush + capacity_model:
    **64 passed, 5 failed** — 5 个全在 test_drain_reentry.py
    (`_FakeTreeCore.get_component_device_value` AttributeError)，coder e1 已在
    30a5a3698a 干净 worktree 复现为 pre-existing mock 缺陷，与本任务无关。已复核失败点。
- deployed 复核: T6 分支现为纯 miss_rearm_allowed 门（scheduler.py:4546-4555），
  无 device_quota_degraded；grep 0 命中 Fix B 引用。

## 1. stress 配置与运行（复刻 P1/too_short/P3 同一负载）

- 驱动: `gate3_ab.sh --tag fixbstrip --agents 8 --launch /root/direct-launch-gate1-rhon.sh
  --rt 400 --budget 1800 --cmax 900 --max-size 200G --file-size 30G`
- 引擎: RH ON, write_back, L3 extent, MAX_SIZE=200G FILE_SIZE=30G, max_total_tokens=65536,
  hicache_ratio=1.5，与 P1/too_short/P3 同配置。
- 结果: **COMPLETE rc=0**，引擎存活满 1820.3s，568 请求，无崩溃无重启。
- /data 起始 15%（160G free），独立 STORAGE_DIR /data/l3/p2io-gate3-fixbstrip，实验后已清理（28G→4K），/data 复原 15%。
- 负载可比性: extent_write 9008-9940（P1=9893, too_short=9940, P3=9008, strip=9485），
  请求 545-568，同一 gate3_ab 配置 → 可比。

## 2. PASS Gate 逐条（剥离后 run）

| Gate | 判据 | 结果 | 判定 |
|---|---|---|---|
| 无崩溃 | Scheduler exception | 0 | PASS |
| correctness | 568/568 HTTP 200, finished=True, output_sha16 全非空 | PASS | PASS |
| 无 OOM | 真实 CUDA OOM | 0 | PASS |
| 无 zero-progress | GPU avg 97.4% max 100%; last restore_success 18:30:11 (run 末 18:31) | PASS | PASS |
| 无 HTTP error | 0 非 200 | PASS | PASS |
| forward recompute 完成 | 所有请求完成; max_wall 148.8s p50 22.3s p90 40.9s | PASS | PASS |

## 3. 核心判据对照表（同一负载）

| 指标 | P0 | P1(74246bb90f w/FixB) | too_short(7155cd8973 w/FixB) | P3(30a5a3698a w/FixB) | STRIP(3c71553a20 无FixB) |
|---|---|---|---|---|---|
| revoked:miss | 2222 | 1159 | 1205 | **2615** | **2529** |
| revoked:miss /req | 3.95 | 2.06 | 2.21 | 4.67 | 4.45 |
| DEVICE_QUOTA WAIT | 1752 | 649 | 417 | **1448** | **1333** |
| restore_recompute | 2262 | 1194 | 1242 | 2658 | 2609 |
| tight loops(<100ms 连续 DEVQ) | 1094 | 364 | 164 | 825 | 742 |
| 最差 offender revoked:miss | 68 | 9 | 9 | 35 | 22 |
| T13 timeout 重算 | 11 | 5 | 4 | 1 | 3 |

## 4. 关键判定与归因

### 4.1 剥离本身中性（无回归，也无贡献）
- STRIP (2529) ≈ P3-with-FixB (2615)，DEVICE_QUOTA 1333 vs 1448 —— 同量级。
- ⇒ 剥离 Fix B **没有**改变 miss churn。Fix B 在当前引擎（P3 之后）对 miss churn 无贡献，
  移除它既不恢复 P1 改善也不恶化。
- 反推 dispatch 判据："若剥离后反弹→说明 P1 依赖 Fix B" —— **不成立**：
  反弹在剥离前（P3）就已发生，且 P3 仍含 Fix B。

### 4.2 为何 epoch 门与 Fix B 都拦不住当前紧循环（根因）
- 紧循环是 `WAIT_CAPACITY → RESTORING → revoked:miss → MISS_RECOMPUTE → (re-arm)
  → WAIT_CAPACITY → ...`，每 loop ~0.5-1s（不等 T13 60s timeout）。
- **T13 timeout 从未触发**（全 run 仅 0-11 次，Fix B 计数只在 T13 触发时 +1，需 2 次才退化
  ⇒ Fix B 门在 P3 之后实际从不生效——引擎的 649→1333 DEVICE_QUOTA 反弹不是因为剥离）。
- epoch 门: l3_publish_epoch 连续前移 0→3902 (~2.1/s)。sticky MISS 的 epoch 判据
  `current_epoch > miss_epoch` 在秒级窗口即变 True → **re-arm 总是放行**，门退化为"永不拦截"。
  这正是 architect open issue 1 的结论（epoch 前移本身反映并发写 durability，不是本请求链）。
- 直接证据: 最差 offender bb4deb 22 次 `WAIT→RESTORING→revoked:miss→MISS→WAIT`，
  无一次 ADMISSION_DENY/no_token 日志（re-arm 不经 gated T6 或 epoch 已前移放行）。

### 4.3 P1 声称的改善不可复现（早于剥离的回归）
- P1 run (74246bb90f) revoked:miss=1159，too_short run (7155cd8973)=1205（仍 P1 水平），
  但 P3 run (30a5a3698a)=2615 —— **翻倍发生在 P3 引入 deferred-ACK reconcile 时**，
  与剥离完全无关。
- P3 改动: unified_tree_core.py + unified_radix_cache.py（l3 publish/durability 机械），
  直接作用于 epoch/epoch 前移机制 → 高度可疑为 miss churn 反弹的引入点。
- 注意: P1 报告声称"最差 offender 68→1 miss"；我独立复现 P1 run 最差 9 miss（同日志）。
  即使用 P1 报告口径，P1 的 miss churn 改善也只是"降低"而非"消除"，且已被 P3 回退。

## 5. 结论

- **剥离 Fix B 是安全的（中性）**：同负载 A/B 下 strip ≈ P3-with-FixB，无新增回归，
  HTTP/correctness/OOM/zero-progress 全 PASS，forward recompute 全部完成。
- **"epoch 门单独维持 P1 系统级改善" 判据 REFUTED（当前引擎）**：改善在 P3 已丢失，
  无论 Fix B 是否在场都在 P0 水平以上（P3=4.67, strip=4.45 vs P0=3.95）。
- 因此 **不能** 判定"剥离后 P1 仍成立、可进入 fast-forward+soak"。当前引擎的 miss churn
  在 P0 基线水平，P1 声称的改善需先在含 Fix B 的 P3 上复核/恢复（疑似 P3 引入），
  与剥离无关。
- 对交付物 #5 的直接回答: 剥离 Fix B 后 P1 的 epoch 门**未**单独维持改善；且反弹**不是**
  剥离引起（P3 已反弹）。这指向 P3（或 P1 结论的环境依赖）需 architect 复核，而非 Fix B。

## 6. limitations

- 每 run 独立时刻（12:12/14:38/16:29/18:00），/data 与 L3 碎片状态、模型缓存热度不同，
  可能引入跨 run 噪声；但驱动配置与写量可比，趋势（P1~1200 → P3~2600）跨 2 次独立 run
  稳定，归因可靠。
- epoch 放行归因基于日志 storage_generation 采样（~2.1/s），非对 re-arm 时刻真实
  l3_publish_epoch 的直接观测。
- 只跑了一个配置（P1 复刻）；未做 RH OFF / 无容量压力对照。
- "P3 引入回归"为强关联 + 时间线推理，非对 P3 代码改动的逐行因果闭合（建议 architect）。

## 7. 环境最终状态

- 代码: 24052 引擎 = 剥离后 3c71553a20 五文件（备份 .bak-strip-pre == 30a5a3698a 保留）。
  未动 22151；P1 74246bb90f 历史未改写。
- /data: 15% (160G free)，本实验命名空间 /data/l3/p2io-gate3-fixbstrip 已清理（28G→4K）。
- GPU: idle 0%/15MiB；无残留引擎/lock。
