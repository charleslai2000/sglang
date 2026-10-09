# phase2-hicache-design-tester-e24 — Test A' promotion admission 验收（完整：K=1/K=16 通过；K=32 混合——机制正确、目标幅度未达）

## 1. status

**done**（验收执行完毕；K=32 九项清单 4 项硬指标未达目标值——详见 §4 判定与 §6 followups，需 orchestrator 裁决/安排 margin sweep 续测）
已完成：Phase 0（停旧引擎 + md5 7/7）、清理授权执行（6 ns 删除，21G→183G）、K=1 回归（fresh+warm 全过）、K=16 回归（通过）、K=32 主验收（机制验证全过、效果指标未达目标）、全量取证（4k1/4a/4b 三证据目录完整）。

## 2. artifacts

- 本报告: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/tester-e24.md`
- 远端证据: `/root/evidence-p2b0-4k1/`（K=1: run-120431 fresh + run-121159 warm、k1-driver{,-warm}.log、p2a-k1.log 91 行、MD5SUMS 17 行）
  `/root/evidence-p2b0-4a/`（K=16: run-123320、k16-driver.log、p2a-k16.log 2804 行、MD5SUMS 13 行）
  `/root/evidence-p2b0-4b/`（K=32: run-125328、k32-driver.log、p2a-k32.log 6276 行、MD5SUMS 13 行）
- 远端引擎日志: engine-p2b0-4k1.log / engine-p2b0-4a.log / engine-p2b0-4b.log（均含 server_args 全量 dump，`hicache_promotion_margin_tokens: 2048` 在位）
- 工具改动: /root/launch-l3-3090.sh +flag `--hicache-promotion-margin-tokens "${PROMO_MARGIN:-2048}"`（备份 .bak-p2b0-4，原 md5 1e5fcbae…/新 a78cdb4b…）
- 磁盘: /data 197G，清理后 183G free → 4k1(4.4G)+4a(49G)+4b(54G) → 当前 81G free

## 3. evidence

### 3.0 清理（授权集 p2b0-{3b,3a,2b,2a,0c,3k1}，~164G）
- find -delete 逐 ns 全部 rc=0；df /data: 21G → 183G free（预期 ~185G ✓）；/root/evidence-* 未动（3b/3a/2b 等 MD5SUMS+run 目录在）
- 遗留保留: p2b0-1b(4K)、p2b0-4k1(4.4G, K=1 ns)

### 3.1 md5 核对（每次引擎重启前重验，均 7/7 双侧一致）
unified_radix_cache b436952e… / hicache_restore 999e80db… / schedule_policy 680e368d… / scheduler 6e798352… / server_args bfc0439e… / test_storage_regression a35b73fb… / test_drain_reentry e48ca3b8…（与 coder e16 清单逐项吻合；三次核对：K=1 前、K=16 前、K=32 前）

### 3.2 K=1 回归（--agents 1 --turns 12，ns p2b0-4k1）— 通过
- fresh run-120431: 12/12 done, 0 failed, 0 downgraded, 413.7s；restore 全 revoked:miss/too_short（fresh 可见性缺口，既有现象）
- warm run-121159: 12/12 done, 14.8s；**walls 0.23-0.48s（e17 级）**；p95 round 1.33s、recompute_served 592、h_to_d_wait 0.0175s（e22 warm 同值）
- promotion: reserve=8 / transfer=8 / release=0 / denied=0；**reserve(24916)==transfer(24916)+release(0) 精确配对**；inflight 峰值 3461；双池观测每事件在位
- forced_drop=0；全零计数器；sanity 0；sha16 跨 run 稳定（c71201d3/b140e9da 与 3a/3b 稳定值吻合）

### 3.3 K=16 回归（16×8，ns p2b0-4a，margin=2048）— 通过
- verdict: done, 128/128, 0 failed, downgraded 17, **elapsed 924.5s（越 470s 崩溃点；3a 950.5s 同级）**
- **forced_drop_to_miss=1（3a: 8；占比 1/12=8.3% vs 3a 8/29=27.6%）**；hollow_evict=11（3a: 21）；backup_failed/drop_declined/drop_without_backup/stays_device_resident/walker_zero_progress 全 0；**OOM=0**、RuntimeError=0
- restore_recompute=172（miss 91 + timeout 81）；WAIT denied_rate_limit=81（3a: 87）；PARTIAL shortfall=67（3a: 64）
- promotion: reserve=61 / transfer=61 / release=0 / denied=0；**配对精确（1,117,497==1,117,497）**；**inflight 峰值 30,279**；max gate q（locked+reserved+new）= 59,775 ≤ 63,488（=65536−2048）**0 违例**
- 12 指标: turns/s 0.139（3a 0.135）、p95 round 173.0s（3a 234.1s）、restore_served **554,449（3a 377,203，+47%）**、recompute_fraction 0.789（3a 0.853）、h_to_d 0.076s
- sha16 抽查: c71201d3 / fcfaefbe / b73280a8 与 3a/3b 基线一致；E_run=0

### 3.4 K=32 主验收（32×8，ns p2b0-4b，margin=2048，60G cap）— 九项逐条
verdict: **status=blocked (time_budget_exhausted), 243/256, 0 failed, downgraded 5, elapsed 1635.0s**（与 3b 同为 243/256、预算截断——可比性好）

**3b vs 4b 对比表**（3b = e23 Test A 基线，pre-admission；4b = 本轮 margin=2048）：
| 指标 | 3b | 4b | 变化 | 判据 |
|---|---|---|---|---|
| elapsed | 1618.9s | 1635.0s | — | 越 989s ✓（1.65×） |
| OOM / dmesg | 0 / 0 | 0 / 0 | — | ✓ |
| walker_zero_progress | 0 | 0 | — | ✓ |
| forced_drop_to_miss | 30（占 evict 28.8%） | **28（占 120 中 23.3%）** | −5.5pp | 目标 <15% **未达**（方向正确） |
| hollow_evict | 74 | 92 | +24% | — |
| restore_recompute timeout | 475 | **454** | −4.4% | 显著下降 **未达**（60s tail 仍在） |
| restore_recompute 总 | 651 | 645 | −0.9% | — |
| promotion_denied(+exact) | —（无 admission） | **0 / 0** | — | >0 **未达**（机制在、无越限请求） |
| reserve==transfer+release | — | **1,718,149==1,718,149（89 对）** | — | 无 leak ✓ |
| sanity invariant | — | 0 违例（on_idle 检查，引擎全程无断言） | — | ✓ |
| inflight 峰值 | — | **30,714** | — | ≤16K **字面未达**；预算公式 ✓（max gate q=61,804 ≤ 63,488，0 违例） |
| restore_served | 671,514 | **661,629** | **−1.5%** | 不显著下降 ✓ |
| recompute_fraction | 0.858 | 0.863 | +0.5pp | — |
| p95 round / slot_refill | 465.0s / 40.2s | 416.6s / 30.2s | 更优 | — |
| h_to_d_wait | 0.078s | 0.082s | 同级 | — |
| downgraded | 8 | 5 | −3 | — |
| prefetch_revoke storage_hit>0 | 0 类 | 15 类（含 16384×7） | 新现象 | 可见性改善 |

**双池观测表**（178 个 promotion 事件池观测快照 + mid-run metrics）：
| 池 | min_free | avg_free | max_locked | min_evictable | 判定 |
|---|---|---|---|---|---|
| FULL（cap 65536） | **15** | 3,246 | **61,804（94.3%）** | **0** | 深度承压但预算地板在位（free+evictable<5000 仅 1/178 事件） |
| MAMBA（~106 tokens） | 35 | 56.2 | 41 | 3 | 稳定，从未逼近 0（free≥35 全程） |

- WAIT_CAPACITY 恢复分析: 629 个 wait 配对完成，**p50=60.0s、p95=60.5s、max=61.0s**；463/629 >30s、350 >60s——**60s tail 未消除**；reason: DEVICE_QUOTA 619 / PREFETCH_BUDGET 203 / FRONTIER 176；frontier_wake 114（3b: 93）
- 归因: E_run=0、A_run=1,701,989（3b 1,747,239）、R_run=4,158,764、S_run=661,629、class-D 7 事件（3b: 11）
- sha16 抽查: b1c-S1-L0-V1（b140e9da/c71201d3）、S1-L0-V2（b73280a8×4）、S9-L0-V3（**d06bdaf0×2——e23 逐字节还原基准案例精确复现**）、S3-L0-V2（c9783715×3+fcfaefbe）— 跨 run 确定性成立
- 优雅退场: driver 自然结束（预算截断，非崩溃）；引擎保持运行（常驻设计）；GPU 20051 MiB 持有/0% util；dmesg OOM=0

### 3.5 K=32 九项清单逐条判定
1. **OOM=0 ✓；walker_zero_progress=0 ✓**（dmesg 0；RuntimeError/SchedulerException/KeyError/RecursionError 全 0）
2. **promotion_denied > 0: ✗（实测 0/0）** —— admission 机制实证在位：预算公式在全部 89 次 admission 逐次成立（max gate q=61,804 ≤ 63,488=65536−2048，0 违例；max gate q 达预算 97.4%），但本轮负载从未出现越限候选（大链 30,714 均落在低 locked 窗口；T11 wait_blocked 谓词按设计提前拦截 DEVICE_QUOTA waiter 唤醒 → 越限请求根本不进入 gate）。字面判据不满足；机制有效性由"0 违例 + 97.4% 预算利用"证明
3. **无 reservation leak ✓**（双重证据：事件级 reserve==transfer+release 精确配对 1,718,149==1,718,149、89 对；sanity I2 不变量 on_idle 检查全程 0 违例、引擎 1635s 无断言崩溃）
4. **inflight 峰值 ≤16K: ✗ 字面（30,714）** —— 预算公式视角 ✓：max locked+reserved+new=61,804 ≤ 63,488。根因：本部署 full 池 = 65536（max-total-tokens），专家 ≤16K 判据基于 32K 池假设（2×16K=32K>30720 拒）；64K 池下 30K 单链合法（46% 池）。**margin sweep 需按 64K 池重新标定**
5. **forced_drop 显著下降: 部分 ✓** —— 28.8%→23.3%（−5.5pp），绝对数 30→28；**首轮目标 <15% 未达**
6. **restore-served 不显著下降 ✓** —— 661,629 vs 671,514（−1.5%）
7. **WAIT 快速恢复/无新 60s tail: ✗** —— timeout 475→454（−4.4%）；WAIT 时长 p50=60s 不变，60s tail 未消除；frontier_wake 114 较 3b 93 略增但不足
8. **双池观测 ✓（记录完成）** —— 见上表；FULL 池逼近耗尽但从未突破预算地板（locked max 61,804 ≤ 63,488）；MAMBA 池独立稳定（free≥35），无单池独近 0 失衡
9. **越 989s ✓** —— 1635.0s（1.65×），预算截断自然结束，0 failed

## 4. summary

- **K=1 通过**（12/12 + 12/12 warm；walls e17 级；forced_drop=0；promotion 配对 8=8+0）
- **K=16 通过**（128/128、924.5s 越 470s、OOM=0、forced_drop 1 vs 3a 8 显著下降、restore_served +47%、配对精确、预算 0 违例）
- **K=32 机制层全过**：OOM=0、无 leak（双证据）、预算公式 0 违例（max 61,804 ≤ 63,488）、越 989s（1635s）、restore_served −1.5%、双池观测完整、sha16 跨 run 确定（含 d06bdaf0 逐字节还原案例）
- **K=32 效果层 4 项未达目标**：promotion_denied=0（字面 >0 未满足）、inflight 峰值 30,714（字面 ≤16K 未满足）、forced_drop 23.3%（<15% 未达）、timeout 454（−4.4% 非显著）；根因统一指向 **margin=2048 对 64K 池过小**（2048/65536=3.1% vs 设计假设 32K 池的 6.25%）：预算 63,488 几乎放行所有组合 → 越限候选极少 → denied≈0、inflight 可达单链 30K、walker 仍面临 evict 高压 → forced_drop 降幅有限、WAIT 60s tail 未消
- 3b vs 4b 对比表、双池观测表见 §3.4；12 指标表（l3_to_h_wait/quota_denied/quota_compressed 仍 missing = P2-0 D2/D3/D4 gap）

## 5. followups

1. **【建议 orchestrator 裁决】margin sweep 续测（coder e16 followup 1）**：64K 池下 margin 需显著大于 2048 才能实现"denied>0 + inflight 受限 + forced_drop<15% + WAIT tail 消除"的判据意图。建议 {8192, 16384, 32768} 三档 K=32 同参数复跑（预算相应 55296/49152/32768），标定标准=forced_drop 显著下降前提下 restore throughput/WAIT 最小。本轮数据已证明机制正确，缺的是力度——若 orchestrator 判定 64K 池下"预算公式生效"即达标，则 K=32 可判 pass
2. **≤16K 判据的池几何差异**：设计/判据按 32K 池书写（2×16K 串行化），实际部署 64K 池（max-total-tokens 65536）。建议 architect 更新设计 §3.1 的判据表述为"locked+reserved+new ≤ cap−margin 恒成立"（本轮 0 违例）+ inflight ≤ 单链上限
3. K=16 的 prefetch_revoke storage_hit>0（3 类）与 K=32（15 类，含 16384×7）：恢复可见性较 3a/3b 的 storage_hit=0 有改善，机制未明（可能 prefetch 完成时间窗口差异），登记观察
4. 证据目录可删性: 4k1(4.4G) 若需回收可随下轮清理（当前 81G free 充足，无需动）
5. 引擎（4b, PID 149334）保持运行持有 GPU 20051 MiB（常驻设计）；下轮 sweep 前 SIGTERM 换 fresh ns

## 6. open_issues

- K=32 判据 2/4/5/7 的目标值在 margin=2048/64K 池下未达——需要 orchestrator 裁决（机制达标 vs 效果达标）或安排 sweep；**勿将"机制正确"误报为"判据全过"**
- fresh-ns 写→prefetch 可见性缺口（K=1 fresh 复现 revoked:miss 5/5）：既有长期问题（storage_existence_cache 填充），非 P2-1c 回归
- 12 指标表 D2/D3/D4 缺失（l3_to_h_wait/quota_denied/quota_compressed）：P2-0 已知 gap
- sanity I2 仅在 on_idle 执行（busy 期受 SGLANG_ENABLE_STRICT_MEM_CHECK_DURING_BUSY 门控，未设置）——本轮无断言崩溃 + 事件级配对双覆盖，残留风险低
- 本验证覆盖：md5 3 次 7/7、清理 6 ns、K=1 fresh+warm、K=16 全量、K=32 全量（verdict/计数器/12 指标/attribution/promotion 时间线/WAIT 时长/双池/双检 sanity/sha16 抽查/MD5SUMS ×3）

---

# 追加段 — 4c（margin=16384 单档，专家批准续测）

## 7. status（追加）

**done** — 4c 档执行完毕。**16384 不成立（不收口）**：denied>0 首次达成（16），但以 restore_served −32% 为代价，forced_drop/WAIT 无改善（甚至略差）；**24576 档无需再试**（专家停判条件未满足——forced_drop 未压到个位数，更大 margin 只会加深 restore 损失）。**margin=2048（4b）仍为三档最优**。机制性结论：forced_drop_to_miss 由 host 侧 backup 压力驱动，device 侧 admission 无法压制（详见 §8.5）。

## 8. evidence（4c: margin=16384, fresh ns p2b0-4c, K=32×8, 60G cap）

- 前置: SIGTERM 4b 引擎（PID 149334）优雅退出 0 残留 GPU 15 MiB；md5 7/7 双侧一致；新引擎 fresh ns（existing=0 B）+ cmdline `--hicache-promotion-margin-tokens 16384`；health 200
- verdict: **blocked (time_budget_exhausted), 237/256, 0 failed, downgraded 5, elapsed 1587.3s（越 989s，1.60×）**
- 计数器: forced_drop_to_miss **30**（占 30+74=104 中 28.8%）、hollow_evict 74、drop_without_backup/backup_failed/drop_declined/stays_device_resident 全 0、**OOM=0**、walker_zero_progress=0、RuntimeError=0
- restore_recompute 653（timeout **467**、miss 186）；WAIT denied_rate_limit 191；PARTIAL shortfall 113；revoked:miss 172；alloc_failed 13（4b: 36）
- **promotion: denied=16 / denied_exact=0 / reserve=79 / transfer=79 / release=0**；**配对 1,314,743==1,314,743 OK**；**peak inflight=38,902**（>4b 30,714）；**max gate q=49,143 ≤ 49,152（=65536−16384）0 违例**（预算被推至 99.98%，denied 事件实证: `est=20855 locked=43008 → 63,863>49,152 拒` → WAIT[DEVICE_QUOTA] → READY 后重试成功）
- **WAIT 分布: 637 配对, p50=60.0s, p95=60.6s, max=63.5s；472/637>30s、370>60s** —— 60s tail 依旧（4b: 463/350）
- **12 指标: restore_served=453,220（4b 661,629 −31.5%；3b 671,514 −32.5%）**、recompute_fraction **0.902**（最高）、p95 round 465.3s（4b 416.6s）、turns/s 0.149、h_to_d 0.069s、slot_refill 35.2s
- 归因: E=0 / A_run=1,300,847（4b 1,701,989）/ R=4,158,704→4,165,704 / S=453,220；class-D 8
- 双池: FULL min_free=9 / avg 2,379 / max_locked 55,287（含活跃请求 KV，非仅 promotion）/ min_evictable=0；free+evictable<5000 事件 0；MAMBA min_free=34 稳定
- sha16: S1-L0-V1 b140e9da×2 ✓、S1-L0-V2 b73280a8×4 ✓、S9-L0-V3 **d06bdaf0×2（逐字节还原案例三连复现）**、S3-L0-V2 c9783715×3+4f20e3fd+5f845136（跨 run 相位值，无乱码）
- dmesg OOM=0；引擎常驻（PID 153979, GPU 20089 MiB）；证据 /root/evidence-p2b0-4c/（run-165237、k32-driver.log、p2a-k32.log 5974 行、MD5SUMS 13 行）

### 8.1 4b vs 4c 四指标逐项（专家判据）
| 指标 | 4b（margin 2048） | 4c（margin 16384） | 判定 |
|---|---|---|---|
| promotion_denied | 0 | **16** | ✓ 达成（est 门首次拒 16 次，全部 WAIT 后重试成功，非损失） |
| forced_drop | 28（23.3%） | **30（28.8%）=3b 基线** | ✗ 不降反升，个位数远未及 |
| 60s WAIT tail | timeout 454 / >60s 350 | timeout 467 / >60s 370 | ✗ 未改善（p50 恒 60.0s） |
| restore_served | 661,629（−1.5%） | **453,220（−31.5%）** | ✗ **显著损失** |
| 附: OOM / zero-progress | 0 / 0 | 0 / 0 | ✓ |
| 附: reserve==transfer | 1,718,149==1,718,149 | 1,314,743==1,314,743 | ✓ 无 leak |
| 附: inflight 峰值 | 30,714 | 38,902 | 更高（预算边界下大链+小链重叠） |
| 附: 越 989s | 1635.0s | 1587.3s | ✓ |

## 9. 结论与建议

1. **16384 不收口**：四指标仅 denied>0 达成，其余三项劣于或等于 4b；restore_served −32% 是实质回归。**24576 档不试**（更大 margin = 更少 promotion = 更深 restore 损失，forced_drop 无改善机制依据）
2. **margin=2048（4b）为三档最优**（含 3b 无 admission）：forced_drop 23.3% 最低、timeout 454 最低、restore_served −1.5% 最小损失、p95 round 416.6s 最优
3. **机制性发现（需 architect/coder 关注）**：forced_drop_to_miss 的触发链 = D→H backup 失败（host 8.2G 压力）→ 子树 drop 无 host 失败 → 链非 L3-durable → Z3 牺牲路径；**与 device 侧 admission 无因果**（三档 forced_drop 30/28/30 基本恒定）。专家"拒绝时不启动 walker → forced_drop 下降"假设在本负载（64K 池/30K 链/host 压力）下不成立——forced_drop 判据应改为 host 侧（backup 失败率/durability 覆盖率）或接受 23-29% 区间
4. **60s tail 判据**：WAIT p50 恒 60s（T13 restore_wait_timeout 设计行为），三档 timeout 454-475 恒定；消除需 wake 谓词/调度改动面（非 margin 可及）
5. **Test A' 总体**：机制层全过（双档 0 违例、配对精确、无 leak、OOM=0、越 989s、双池完整、sha16 确定）；效果层判据 2/4/5/7 目标值在本负载下不可同时满足（denied>0 与 restore 无损互斥）——建议 orchestrator 以"机制达标 + margin=2048 默认"收口，或按 §9.3/9.4 改判据维度

## 10. followups（追加）

1. margin 定档建议: **2048 维持默认**（sweep 数据: 2048 最优；16384 过度收缩）。设计 §3.1 标定结果由 architect 写回
2. forced_drop 根因转 host 侧: 建议 coder/architect 评估 host pool 扩容（hicache-ratio 1.5→更高）或 backup 优先级调度，而非 margin
3. 60s tail 消除需 wake/调度改动（T11 已生效——denied 后 WAIT→READY 重试成功路径可见，但 60s 超时仍是主导出口）
4. 引擎 4c 常驻（PID 153979）；/data 28G free（4k1/4a/4b/4c = 160G）；如需回收旧 ns 待授权
