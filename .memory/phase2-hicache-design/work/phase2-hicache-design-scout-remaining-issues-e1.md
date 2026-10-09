# phase2-hicache-design-scout-remaining-issues-e1 — 当前仍成立的 remaining-issues 审计

## status
done

## artifacts（本审计读取的全部只读材料）
- 基线：`/home/charles/Workspaces/homenet/server/gpu/3090-dev/phase2-decbm-baseline-report.md`（§0-§7）
- 决策账本：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/ledger.md`（L370-398、L1020-1058 关键节）
- 状态：`.../.memory/phase2-hicache-design/context.md`
- 实验报告（`.../.memory/phase2-hicache-design/work/`）：
  - `phase2-hicache-design-tester-rh-ab-e1.md` / `-rh-ab-e2.md`（RH A/B 决定性实验）
  - `phase2-rhono-bug-architect-e1.md`（RH 全灭代码级定位）
  - `phase2-hicache-design-orchestrator-gate3-closeout-e1.md`（Gate-3 收口）
  - `phase2-hicache-design-tester-gate3-soak-e1.md`（Gate-3 Run A soak）
  - `phase2-hicache-design-devops-gate2-b64-e1.md`（64G Phase-0 retest）
  - `phase2-hicache-design-tester-gate2-saturation.md` / `-gate2-fbe-rerun.md` / `-gate2-redesign-e1.md` / `-gate2-s32-e1.md`
  - `phase2-hicache-design-coder-restore-hit0-e1.md`（restore-side 根因）
  - `phase2-hicache-design-tester-revoked-miss-decomp.md`（full-miss 拆分）
  - `phase2-hicache-design-tester-hbm-budget-e1.md`（HBM 安全边界）
  - `phase2-hicache-design-tester-conc-sweep-e1.md`（c>8 并发 sweep）
- 代码（只读定位）：`python/sglang/srt/server_args.py`、`python/sglang/srt/managers/scheduler.py`、`python/sglang/srt/managers/scheduler_components/ready_horizon.py`、`.../hicache_restore.py`、`python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`
- 远程证据目录确认存在：`work/gate2-b64-evidence/`、`work/gate3-rhon-evidence/`、`work/gate2-s32-evidence/`（均未读取原始样本，仅核对存在 + 报告引用）

---

## summary — remaining-issues 表（当前仍成立）

> 判定口径：仅列真实剩余 OPEN / DEFERRED；凡被 Gate-2(64G)/Gate-3(A/B soak / A' 决定性) 证伪或覆盖的旧问题一律不重开（见 §"被覆盖项"）。类型：OPEN=未闭合缺陷/未决问题；DEFERRED=已量化但推迟的性能优化/配置决策/方法论。

| # | item | 类型 | 当前状态描述 | 证据指向 | 为什么仍成立（未被证伪/覆盖） | 建议下一步 |
|---|---|---|---|---|---|---|
| 1 | RH 容量压力下 READY/DEVICE_QUOTA 恢复冻结 | OPEN（deferred known issue） | RH ON 时首 recycle 后 ready_pool 永久停止、restore 进入 WAIT_CAPACITY(reason=DEVICE_QUOTA) 永不释放 → restore_success→0、storage_hit 冻结（B 218,883 永久停 vs A 线性到 7.08M）；B 36,527 recycle vs A 6,513 | rh-ab-e2 §5/§6.5（B ready_pool per-60s `[4,30,3,0,...]` last=+121.7s；restore_success last=+121.1s；WAIT_CAPACITY 全程 bins）；ledger L1034/L1041-1047；baseline §6；context.md | A' 实验只裁决出"RH 状态机无独立缺陷"，并把 root cause 收敛到"RH+capacity-pressure thrashing feedback"，但**恢复链死锁的具体实现缺陷未闭合**；用户封板明确列为 Deferred known issue（rh-recovery-bug backlog），非覆盖 | 仅当"以后真有必要再修"时按 rh-recovery-bug 建档；当前不阻塞生产（RH=OFF） |
| 2 | RH ON 早 recycle 根因（30.4 vs 81.6 GiB 硬矛盾） | OPEN（deferred，未解释） | RH OFF 首 recycle 81.6 GiB vs RH ON 30.4 GiB，但共同 clean window 内 extent_write 仅多 1.07x（28.7→30.7GB）→ 不能简单归因写放大；RH ON 更早触达容量的机制未闭合 | rh-ab-e2 §4-5（A +314.5s/81.6GiB vs B +126.5s/30.4GiB；共同窗口 extent_write 1.07x）；ledger L1042（"硬矛盾（未解释）"）；baseline §6 | 写放大只解释 7%，大头缺口（81.6/30.4≈2.7x）未解释；Gate-3 早期 5.7x recycle 归因（closeout §3.2）在 A' 共同窗口下被收敛到 1.07x，但**早 recycle 本身仍无完整机制** | 属 rh-recovery-bug / Followup 2（写放大量化），本轮不做；若要闭合需容量充足场景复测以区分"RH 固有写放大" vs "recycle 反馈放大" |
| 3 | ready_host_watermark_low=43513 vs ready-host 实际峰值 ~28K（数量级差异） | OPEN（强嫌疑，未证明） | 43513 是 token-mode 低水位，远高于 ready_pool 实达 ~28K；疑致 pool 永远到不了 low → WAIT_CAPACITY 死锁；但单位/状态转换一致性未证明 | ledger L1037/L1042；rh-ab-e2 followup 1；code：server_args.py:2905 默认 43_513、scheduler.py:1382-1388（`watermark_low = low if state_p95==0 else state_p95`；state_p95 默认 0 → 回落固定 43513）、ready_horizon.py:206（`ready_tokens < watermark_low`） | 仅"强嫌疑"，未证明；A' 实验未闭合这一机制，封板措辞明确保留"未证明单位/状态转换完全一致" | 深挖 ready_pool 冻结时 watermark 判定是否永不满足（RH ON 路径），属 rh-recovery-bug 核心断点 |
| 4 | c16 scheduler / Mamba headroom 优化（pool96+c16 vs pool106+c16） | DEFERRED（性能优化，非缺陷） | 3090 单卡最大有效并发≈16（~992 tok/s）；c16→c21 卡 ~965-1035 达 compute-bound 天花板；Mamba 池耗尽 eviction 惩罚 4-6%；推荐点仍 pool64+Graph ON+c8≈596-606 | conc-sweep §3-4/§6.3；baseline §7.2-7.5（pool96-c16 T10 992.5/T20 967.7；pool106-c16 未跑；pool 耗尽 avail~0/evict~49 时 -4%） | 是待权衡的优化选择而非缺陷，未有任何实验"关死"；conc-sweep 只量化、未实施；"复核推荐点是否也存在 eviction 影响"明确列为后续（§7.5） | 若追求 ~990 tok/s 需 c16+pool≥96 且池不耗尽（24G 上 pool96 多占 ~1.5GB 且高并发池必近满）——权衡项，无代码改动 |
| 5 | host L2 饱和 backup drop（host_pressure） | OPEN（deferred，正确性/容量缺口） | 生产 RH OFF 基线（Gate-3 Run A）host cache 饱和 99.5%，KV 453,698 + mamba 96 tokens 无 host backup 被丢弃；closeout 明确"是否追根因留给用户裁决（Gate-3 PASS 不依赖它）" | gate3-soak §3/§4（host cache 97821/98305=99.5%；host_pressure dropped KV 453,698）；closeout §2.3/§6.4 | 未被任何后续实验修复/覆盖：A' 用 90G/200G（不同容量、且 RH ON），未重测 RH OFF 生产基线的 host_pressure；这是生产基线（RH OFF）的现存缺口 | 待用户裁决是否追根因；可能属"host L2 配额 vs 写回 reserve 配置"问题（关联 ledger 2026-09-01 writeback_reserve 设计） |
| 6 | 64G extent GC 长期 soak 触发 → L0 restore 退化 | OPEN（配置级决策） | 64G×0.9=57.6G 水位在 2h soak 触发 6454 次 LRU eviction（~323GB），L0 exact-restore 0.6184、20.8% full-miss；closeout followup：决定 64G 水位是否可接受、或上调 max_size/eviction_ratio 换 no-GC 长 soak | gate3-soak §3/§4/§6（GC active at 57.6G；L0 0.6184）；closeout §2.4/§6 | 生产基线仍 64G；A' 靠 200G max_size 规避 GC，未回填 64G 生产配置的判定；K≤8 无 GC 时 exact restore ≥95%（冻结事实）只在 short/no-GC 成立 | 配置级决策（非代码）：生产长 soak 是否上调 max_size/eviction_ratio；需用户裁定 |
| 7 | recycle=0 下 genuine full-miss（revoked:miss）仍非零 | OPEN（归因未决，低置信） | b64 64G retest：K4/K8 extent_recycle=0 且 L0 exact 0.9599 PASS，但 revoked:miss 仍 94/233（K16 915）；devops 判定"不是容量故事可解释，需看——rate-limit/too_short 负载形状 artifact 或真实 restore-side shortfall，本 run 未决" | devops-gate2-b64 followup 2、open_issue（k8 233 / k16 915 at recycle=0） | 明确"Not resolved this run"；未被 Gate-3 覆盖（Gate-3 用不同口径，且 class-A storage>0 已被 Gate-3 证否）；但可能部分是 denied_rate_limit/too_short/shortfall 负载形状——置信度低 | 若要闭合：在 recycle=0 的 b64 K8 上细分 revoked:miss 的 reason（denied_rate_limit / too_short / shortfall / hybrid_discard），区分 artifact vs 真短供 |

---

## 被覆盖/证伪项（明确不重开，附覆盖证据）

| 旧问题 | 覆盖/证伪证据 |
|---|---|
| **RH ON 使 L3 restore 全灭 / RH 状态机独立缺陷**（rhono-bug C1/C2/C3 假设：extent 环写覆盖） | A' 决定性实验（rh-ab-e2 §5）：共同 clean window 内 RH ON storage_hit 2.26x、recompute 0.51x、restore_success 持平 → **RH 状态机无独立缺陷**；root cause 收敛为 thrashing feedback。封板措辞（ledger L1041）确认 |
| **restore-side L3 读回缺陷（958/958 durable 链 storage_hit=0，gate-2 FBE blocker）** | b64 64G retest（devops-gate2-b64）：MAX_SIZE 20G→64G 后 K8 时 extent_recycle=0、storage_hit>0 行出现（41/96）、L0 exact-restore 0.9599 PASS → 原 0-hit 根因 = **L3 容量预算不匹配**（20G ≪ ~232GB 聚合写，coder-restore-hit0 B primary），非 restore-side 缺陷 |
| **class-A（storage>0 但 restore 断 / mamba TRAILING 折叠）** | Gate-3 closeout §2.4：Run A 627 条 storage>0 行全部 restore 成功、Run B storage>0 行 1 条 → **class-A ≈ 0**，"Step① K8 33% 的 class-A 在 Gate-3 两轮均未再现" |
| **partial restore fallback / TRAILING_PAGES 语义** | 冻结事实：partial fallback 已禁用；TRAILING_PAGES 语义已定（任务已知冻结事实，未重开） |
| **p106-c21 名义 21 实际 15-16 ≈1021-1034 异常** | conc-sweep §1/§2：固定 trace 驱动每 agent 串行 turn，conc≥19 时驱动无法维持 21 长批内（`queue=0` 证明非引擎 admission 限制）→ **驱动 artifact，非引擎缺陷**；仅残留"真 21 并发稳态需开放式客户端（改变 trace 语义，未测）" |
| **pool32 Mamba cap / pool64 去 cap（c8 时）** | 已冻结为基线结论（pool64 最小去 cap 点，baseline §4.1），属已 CLOSED 性能结论，非 open item |
| **GPM 不可用（SM vs Tensor 无法拆分）** | 方法论限制（conc-sweep §6.1、baseline §7.1），已降级 pucvmt+功耗墙判定，判 compute-bound 已足够；如需严格区分需 Nsight（本机无）——**DEFERRED 低优先级，仅记录**，非缺陷 |

---

## followups（编号建议）

1. **rh-recovery-bug 建档深挖**（item 1/2/3 合并）：Ready/DEVICE_QUOTA 恢复链死锁 + 早 recycle 硬矛盾 + watermark 43513 嫌疑——三者同属一个未闭合根因，需在 RH ON 路径上核对 ready_pool 冻结时 `_below_low`（ready_horizon.py:206）是否永不满足。位置：`ready_horizon.py` / `hicache_restore.py` / `scheduler.py` restore-reconcile 链。本轮明确不做（用户封板）。
2. **host_pressure backup drop 根因裁决**（item 5）：是否追，待用户拍板；若追，位置 = host L2 配额 vs writeback_reserve（ledger 2026-09-01 设计，scheduler/写回通道）。
3. **64G 生产长 soak 配置裁决**（item 6）：max_size/eviction_ratio 是否上调，配置级，非代码。
4. **recycle=0 下 revoked:miss 归因**（item 7，低优先）：在 b64 K8 证据上细分 reason，区分负载形状 vs 真短供。
5. **c16 高吞吐选项权衡**（item 4）：不实施，仅记录为 24G 上的吞吐/显存权衡（pool≥96 + 池不耗尽 vs pool64+c8 安全点）。

## open_issues（本审计未决/边界）
- 原始远程证据（`/root/evidence-*`、engine logs）不在本机，未读原始样本；本表结论基于报告 + 本机源码定位，报告内数字均为报告引用值（未复算）。
- item 7 置信度低（可能部分是负载形状 artifact）；是否列为"真实剩余缺陷"需以细分 reason 为准。
- RH watermark 的 43513 在 token-mode 下是否实际生效取决于运行时 `ready_horizon_state_p95_tokens` 是否传入；生产 wrapper 若未设该参数则默认 state_p95=0 → 回落固定 43513/87026（server_args.py:3061 默认 0、scheduler.py:1382-1388）。该生效条件未在 runner 配置中确认，属 item 3 未闭合的一部分。
