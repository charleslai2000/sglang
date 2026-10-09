# phase2-rhfix-fixb-crosstest-tester-e1 — Fix B 生产路径交叉验证（RH OFF）

- status: **done**
- epoch: e1
- owner: tester
- 任务: 在实验机 24052 上执行 Fix B 交叉验证（RH OFF，生产路径），判定生产观测的 RECOMPUTE 长尾 loop 与 Fix B 修复的是否为同一状态机根因。
- 机: 175.155.64.171:24052（root）；GPU 0%/15MiB 空闲；/data 清理至 2%-12%
- 代码: /root/sglang-b1-continuity（非 git，editable）；patch=/root/rhfix-a-b.patch（Fix A + Fix B + telemetry 整体）；apply=opt / revert=frozen baseline
- 模型: /root/models/Qwen3.5-9B-w4a16；env=sglang-patch
- 驱动: /root/gate3_ab.sh；启动 wrapper: direct-launch-gate1.sh（RH OFF）
- 全程 **RH OFF**，未启用 --enable-ready-horizon（与 Fix A/RH 无关，不混淆）

---

## 0. 结论速览

**Fix B 的判定：FAIL / NOT-ESTABLISHED（机制未在生产路径触发）。**

核心发现（跨全部 6 条 trace 一致）：
- **Fix B 的触发条件（单 episode 内 ≥2 次连续 DEVICE_QUOTA T13 timeout）在任何 trace 中都从未发生**。全部 6 条 trace 的 max_timeouts_per_episode = 1，从没到过 cap=2。
- 生产 RH OFF 的 RECOMPUTE 长尾是**快速 wake-loop + miss 驱动**（WAIT[DEVICE_QUOTA] → RESTORING → disposition RECOMPUTE too_short/revoked:miss → 立即 re-WAIT，13ms 级周期），**不是 T13 timeout 驱动**。
- 因此 Fix B 的 gate（`device_quota_degraded(attempts>=2)`）在生产路径**从不触发**，Fix B 不能归因生产长尾的改善。
- 生产慢请求（60-80s TTFT）**无 60s/120s/180s 周期性峰**（TTFT [59,61]=1、[119,121]=0、[178,182]=0），慢尾是 churn+recompute 体量驱动，**不支持"61-77s = 60s T13 等待 + decode"的强假设**。
- 我的 A/B 两组（baseline vs opt，同 trace，20G extent，RH OFF）均 rc=0、**无 `device_value is not None` 崩溃**、100% http 200/finished，correctness/OOM/HTTP=0。

---

## 1. 执行记录（2 run，均 30min / rc=0，RH OFF）

| # | tag | 代码 | 容量 | 起始 /data | 结果 |
|---|---|---|---|---|---|
| A | rhfix-ba20 | 冻结基线（patch 回滚） | FILE_SIZE=20G / MAX_SIZE=200G | 2% | COMPLETE rc=0, 551 rows, 无崩溃 |
| B | rhfix-ba20-opt | opt（patch 应用） | 同 A（20G/200G） | 2% | COMPLETE rc=0, 525 rows, 无崩溃 |

容量说明：采用小 extent（20G）在 170G 空盘上制造容量压力，同时 filesystem 留足 margin（min_free=10G，20G extent 累计写 ~18G 时不跨 min_free GC）。`/data` 每 run 前回 2%-12%，未触发 filesystem GC，两 run 均 VALID。

---

## 2. 状态链 / 指标（collector: /root/fixb_cross_collect.py）

### Run A（baseline, RH OFF, 20G, 1800s）
```
write_bytes=341.7GB write_count=9291  recycles=4362 distinct_gen=22
restore_success=97 (tokens=1,024,099)
recompute=1952  (miss=1949 / timeout=3)
dq_wait(DEVICE_QUOTA WAIT)=1749  FRONTIER=111  PREFETCH_BUDGET=31
disposition_recompute=2186  partial=135  restore=2
admission=76335  no_token=1957  loadback_fail=0  retry_capacity=1833
first_recycle_offset=+114.8s
fixb_counter_peak_dist={0:518, 1:3}  fixb_rids_peak_ge_2=0  fixb_max_peak=1
rids_in_window=546
correctness: http=200 all 551, finished=True all, http503=0
TTFT: n=551 min=0.3 med=21.3 p90=35.1 p95=43.8 max=111.1
WALL: min=3.1 med=24.4 p90=38.6 p95=46.3 max=117.1
TTFT [59,61]=1  [119,121]=0  [178,182]=0  (无 60s 周期累积)
```

### Run B（opt, RH OFF, 20G, 1800s）
```
write_bytes=350.5GB write_count=9505  recycles=4415 distinct_gen=22
restore_success=88 (tokens=1,064,805)
recompute=1909  (miss=1907 / timeout=2)
dq_wait=1683  FRONTIER=154  PREFETCH_BUDGET=38
disposition_recompute=2101  partial=135  restore=0
admission=76134  no_token=2207  loadback_fail=3  retry_capacity=1773
first_recycle_offset=+103.7s
fixb_counter_peak_dist={0:496, 1:2}  fixb_rids_peak_ge_2=0  fixb_max_peak=1
rids_in_window=523
correctness: http=200 all 525, finished=True all, http503=0
TTFT: n=525 min=1.3 med=22.3 p90=36.9 p95=48.4 max=109.2
WALL: min=2.4 med=25.3 p90=41.3 p95=50.9 max=110.6
TTFT [59,61]=1  [119,121]=0  [178,182]=0
```

**A/B 统计不可区分**：restore_success 97 vs 88、recompute 1952 vs 1909、dq_wait 1749 vs 1683、TTFT med 21.3 vs 22.3、max 111 vs 109。Fix B 未改变任何行为（因 gate 未触发）。

---

## 3. 决定性机制分析（跨 6 条 trace 的 Fix B gate 触发核查）

脚本 /root/gate_engagement.py：单 episode 内连续 T13 timeout 峰值（Fix B 计数器语义：仅 T13 timeout 递增，restore_success 重置）：

| trace | max_timeouts_per_episode | total_timeouts | FixB_ENGAGED(≥2) |
|---|---|---|---|
| prod-RH-OFF (ab-a-off) | **1** | 12 | False |
| prod-RH-ON (ab-a-on) | **1** | 20 | False |
| runA-base-rhoff-20G | **1** | 4 | False |
| runB-opt-rhoff-20G | **1** | 3 | False |
| rhfix-bl-on (RHON-base) | **1** | 5 | False |
| rhfix-str-bl (RHON-base-30G) | **1** | 6 | False |

**Fix B 的 gate（`device_quota_degraded` 在 attempts≥2 返回 True）在所有 trace 均未触发。**

### 3.1 生产慢请求时间分解（definitive）
生产 RH OFF 慢尾（ab-a-off）TTFT 分布：n=2490, med=18.6, p90=32.7, p95=37.8, max=80.1；WALL max=85.6。TTFT [59,61]=1、[119,121]=0、[178,182]=0 —— **无 60s/120s/180s 离散峰**。

最慢请求 `6b675ea9`（TTFT=80.1s, wall=85.6s, write turn, new=20557, dev=9, stor=22948）时间分解：0 timeouts；RESTORING 之间 gap 为 **30-33s**（非 60s）；span 72s 内 3 次 restore_success + re-WAIT 交替；大 recompute（20557 token）。

慢请求状态活动（ab-a-off 32 个 TTFT≥55s）：多数 timeout=0-1、miss=2-7、dq_waits=2-65。代表：`9b2b25bd` TTFT=65.7s 有 33 dq_waits/32 miss/2 success；`d04143ef` TTFT=62.0s 有 65 dq_waits。

**结论：生产慢尾是"大量快速 DEVICE_QUOTA wake-loop churn + 大 recompute 体量"驱动，不是 T13 时钟驱动。**

### 3.2 生产 RH OFF 复现（run A 慢请求同构）
run A 慢请求（TTFT≥55s，17 个）同样 timeout=0-1、miss=4-40、dq_waits=1-42。最慢 `dc3e5eb5` TTFT=111.1s 有 12 dq_waits/11 miss/1 success/27636 new。**与生产同构：churn+recompute 驱动。**

### 3.3 T13 timeout 请求的稀有性
run A 仅 4 个 cause=timeout（698ee0/3d7cb9/24b0da/9fc7f1），全部为单次 timeout（max 1/episode），多为近乎全 device-hit 的 restore/branch 请求（如 698ee0 device_hit=20896/20911 仍等满 60s 超时），之后完成，未形成二次 re-WAIT-timeout。

---

## 4. 崩溃核查（coordinator 预警的 fixed 版 `device_value is not None`）

- 我的两组（baseline + opt，20G extent，RH OFF，30min）均 **rc=0、无 `device_value is not None` / build_backup_spec 崩溃**（两 log 均 grep=0）。
- 该崩溃发生于另一 stress（fixed 版 +1239s，纯容量耗尽，不同压力水平/时长）。我的 30min/20G 未复现。
- 因我的 baseline（patch 回滚）也未崩溃，无法据此判定崩溃是否 pre-existing——需在更激进容量压力 + 更长时长下由匹配 A/B 验证（见 followups）。

---

## 5. 按 PASS Gate 逐条判定（dispatch 的 1-7）

| # | Gate | 判定 | 依据 |
|---|---|---|---|
| 1 | baseline 稳定复现 WAIT→timeout→recompute→re-WAIT loop | **NOT-REPRODUCED** | run A 仅 4 次 timeout、max 1/episode，无 2+ 次 re-WAIT-timeout 循环；生产 RH OFF 亦仅 12 次 timeout、max 1/episode |
| 2 | opt 同 trace 不再形成无限 re-WAIT | **N/A（机制未触发）** | A/B 均无 2+ timeout 环；两代码统计不可区分 |
| 3 | 单 request DEVICE_QUOTA timeout ≤2/episode | **平凡满足** | 全部 trace max=1（本就 ≤2，Fix B 未起作用） |
| 4 | restore_recompute 从持续增长变成有界 | **NOT-ESTABLISHED（非 Fix B 效果）** | A 1952 vs B 1909 统计不可区分；gate 未触发故非 Fix B 所致 |
| 5 | request 最终完成并输出 | **PASS（两代码均成立）** | http=200 / finished 100% 两组 |
| 6 | correctness/OOM/HTTP error/zero-progress = 0 | **PASS（两代码均成立）** | 0 错误、0 503、t38c 正常 |
| 7 | TTFT 长尾显著下降，60s/120s/300s 峰消失 | **N/A（基线本就无周期峰）** | A/B TTFT 分布不可区分（med 21.3/22.3, max 111/109）；两代码均无 60s 周期峰，非 Fix B 消除 |

**总体判定：FAIL（针对"生产 RECOMPUTE 长尾归入 Fix B 根因范围"）。** Fix B 的机制在生产路径从不触发，不能将其归因生产长尾的根因/改善。correction loop 应回 architect。

---

## 6. 回答 coordinator 的 5 项只读问题

1. **60-77s 中有多少秒实际花在 T13/DEVICE_QUOTA**：生产 trace 的 60-80s 慢请求绝大多数 **0 个 T13 timeout**（32 个慢请求中仅 12 个有过 1 次 timeout，且为单次）。timeout=1 的请求约 60s 花在 T13 等待；timeout=0 的慢请求（占多数）时间花在 DEVICE_QUOTA wake-loop churn（大量短 WAIT↔RESTORING 交替）+ 大 recompute + decode，非单一 T13 时钟。最慢请求（80s）0 timeout，花在大 recompute（20557 token）。
2. **TTFT 与 response wall 分别多少**：见 §2/§3.1。生产：TTFT med=18.6/p95=37.8/max=80.1；WALL max=85.6。run A：TTFT max=111.1、WALL max=117.1；run B：TTFT max=109.2、WALL max=110.6。两者分开报告。
3. **Fix B 是否消除 60s 周期性等待**：**不适用** —— 生产路径本就不存在 60s 周期性等待（TTFT 无 60/120/180 峰）；Fix B 的 gate 因触发条件（2+ timeout/episode）从不发生，无从消除。
4. **Fix B 是否只是把等待换成 recompute**：设计上 Fix B 在 cap 后确实"不再 re-WAIT 而走 recompute 前向路径"；但该转换在生产路径**从不触发**（无 2+ timeout episode）。故既未把等待换成 recompute，也未减少 recompute。
5. **ready_resident=0 究竟代表什么**：两 run metrics-final 均 `hicache_ready_resident_tokens=0` 是**引擎 drain/SIGTERM 后的最终快照**（live gauge，drain 后为 0 属预期），不能据此判"无 cache"。run 中 restore_success/storage_hit 健康（A: storage_hit=322,711 tokens，restore_success=97；B: storage_hit=381,587，restore_success=88）证明 L3 restore 在运行期真实发生。ready_resident=0 的准确语义需在运行中采样而非最终快照确认（见 followups）。

---

## 7. 证据 / 产物路径

- 远程引擎日志：`/root/engine-gate3-rhfix-ba20.log`（baseline）、`/root/engine-gate3-rhfix-ba20-opt.log`（opt）
- 远程证据目录：`/root/evidence-gate3-rhfix-ba20/`、`/root/evidence-gate3-rhfix-ba20-opt/`（run-*/join.log, metrics-final, gpu-util, t38c-probe）
- 远程分析脚本（tester 独立编写）：`/root/fixb_cross_collect.py`、`/root/gate_engagement.py`、`/root/ttft_analyze.py`、`/root/slow_vs_state.py`、`/root/time_decomp.py`
- 本机（读）：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_hicache_restore.py`（Fix B unit, 5 passed @ HEAD）
- 原始 trace（未改动）：`/root/engine-gate3-ab-a-off.log`（RH OFF 生产）、`/root/engine-gate3-ab-a-on.log`（RH ON 原 B）

---

## 8. summary（PASS gate 1-7 逐条，见 §5）

- Fix B 判定 **FAIL/NOT-ESTABLISHED**：生产 RECOMPUTE 长尾与 Fix B 修复的**不是同一状态机根因**。Fix B 目标是 `WAIT→timeout→recompute→re-WAIT`（需 2+ timeout/episode），生产是快速 miss 驱动的 wake-loop churn（≤1 timeout/episode）。
- 生产慢请求无 60s/120s/180s 周期峰，慢尾由 churn+recompute 体量驱动，不支持 coordinator 强假设。
- A/B 两代码统计不可区分，均无崩溃、无 correctness/OOM/HTTP 错误；correctness/OOM/HTTP/zero-progress=0 成立（gate 5/6）。
- gate 1/2/3/4 因 Fix B 机制不触发而 NOT-ESTABLISHED/平凡满足/N-A。
- 不追加第三个 heuristic fix；回报 blocked 回 architect 重评估 Fix B 是否仍是正确修复面。

---

## 9. followups

1. **Fix B 触发条件在生产路径不成立**：建议 architect 复核 Fix B 的设计假设（B-run 的"9,102-miss WAIT→timeout→recompute→ADMISSION_DENY→WAIT loop"在运行时实为 miss 驱动快环，timeout 仅 20 次且 max 1/episode）。Fix B 的 gate 需要 2+ timeout 才 fire，生产路径达不到。
2. **生产慢尾真因**：指向 DEVICE_QUOTA wake-loop churn + 大 recompute（每次 12K-30K token）+ decode 体量。建议深挖为何已 device-hit 的请求仍反复进入 WAIT[DEVICE_QUOTA]（容量核算/charge 路径），以及 recompute 体量为何这么大。
3. **崩溃核验未闭合**：coordinator 预警的 fixed 版 `device_value is not None` 崩溃未在我的 30min/20G 复现；需匹配更长/更激进容量压力（如 FILE_SIZE 更小或更高并发 + 更长 run）做 baseline-vs-opt 核验，判定是否 pre-existing 备份路径缺陷。
4. **ready_resident 语义**：需运行中采样（非最终快照）确认 `hicache_ready_resident=0` 是否为运行期真实状态。

---

## 10. open_issues

1. **Fix B 有效性未被运行时压力路径验证**（与 phase2-rhfix-tester-e1 结论一致）：其 gate 在全部 6 条 trace 均未触发。unit 层验证（5 passed）只证明状态机内部一致，不证明生产触发。
2. **TTFT max 差异（~110s vs 生产 ~80s）**：我的 20G 约束 run 更激进（更早 recycle +103s），max 略高；非 Fix B 影响。
3. **崩溃 pre-existing 判定未闭合**：见 §4/followup 3。
4. **环境最终态**：代码为 opt（patch 应用，DEVICE_QUOTA_MAX_TIMEOUTS=3）；/data 12%；GPU idle 0%/15MiB；无残留引擎/锁。交付态由 orchestrator 决定（需回滚 baseline 时执行 `patch -p1 -R < /root/rhfix-a-b.patch`）。
