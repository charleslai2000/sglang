# phase2-cap-e6-architect-e1 — ② ratio sweep 档表重推（T=10.78 GiB 实测 + hicache_ratio 1.3）

- Agent: architect
- Epoch: 1
- Date: 2026-09-07
- Scope: **纯设计/数学**。按 tester e3 实测（T=10.78 GiB）+ orchestrator 裁决（hicache_ratio 1.5→1.3）重推 ② ratio sweep 档表、r* 推荐、boot-verify 检查表、与 Gate D 衔接、重标定记录。不跑 GPU、不改产品代码、不写驱动。
- 触发规则：协议 §②.1/§②.4"偏差 >10% → 重标定再推档"（protocol-e1:157,285）+ ledger:2554-2558 裁决。

---

## status: done

## artifacts
- 本报告：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-cap-e6-architect-e1.md`
- 已读输入：`work/phase2-cap-e3-tester-e1.md`（实测锚点）、`work/phase2-cap-protocol-architect-e1.md`（原协议/标定规则）、`ledger.md:1587-1591`（host-RAM 墙 478K 先例 + 显式 size 下 ratio NO-OP）、`ledger.md:2488-2536`（4 Gate 权威版）、`ledger.md:2545-2558`（e3 阻断 + orchestrator 裁决选 A）
- 源码核对（只读）：`kv_cache_configurator.py:1811-1858,1891-1918,2124-2183`（ratio 预算/分档式/余量返还）、`pool_configurator.py:419-428`（page-align）、`pool_host/base.py:51-58,151-174`（host budget=available−10GB；ratio 定 host=device×ratio）、`pool_host/mamba.py:79-106`（mamba host=device×ratio，超额 raise）、`hybrid_cache/hybrid_pool_assembler.py:420-422`（host pages=device_pages×ratio）、`overrides.py:2650-2669`（page_size=1 默认）

## evidence
- **T 实测**：C0(r=0.90) 与 C3(r=0.33) 两档独立反解 10.79 / 10.78 GiB（0.1% 一致）→ T=10.78 GiB（tester e3，报告 §54-62）。vs 协议假设 9.45 GiB = **+14% > 10% 阈值**。
- **per_slot**：48.9 MiB（e2 实测 64 slots=3.12GB float32；mamba 式 预算=T·r/(1+r)，slots=⌊(预算−per_slot)/per_slot⌋）。
- **KV tokens/slot**：由两锚点差分实证 = **(536,435−376,091)/(106−55) = 3144 tokens/slot**（即释放 1 mamba slot 换 3144 KV tokens）。此实证系数比纯 cell_size 反推（≈3180）低 ~1%，已将 GPU 端非 cell 开销（graph 先占、page-align、bias）**全额折入**，避免协议 §②.1"9.45 GiB + 15,268 B/token"式高估。
- **Host 模型**：host 池 = device 池 × hicache_ratio（源码 base.py:156/84, mamba.py:84; hybrid assembler:421-422，ratio-path 非显式 size 时成立）。分配次序 **kv-host 先 → mamba-host 后**（base.py:173-175 vs mamba.py:98-106）；budget=psutil available − 10GB reserve（base.py:27,58）。
- **host factor**：ratio1.5 时实测 total host 17.2GB（device sum 10.78）→ padding ≈1.064（tester e3 报 ≈1.6 已含 ratio 1.5×padding）；**ratio1.3 时 factor≈1.383 → total host ≈14.91GB**（tester e3 预测 14.9GB 一致）。

---

## summary

## Conclusion

1. **② 的更新回答**：在 T=10.78 GiB、hicache_ratio=1.3 下，扫 `--mamba-full-memory-ratio`，**满足 KV 池 ≥499,200（480K+4%）∧ mamba slots≥51（c8 实测需求）∧ c8 活性不降 的 ratio 区间 = [0.30, 0.43]，推荐 r*=0.43**（非整 0.05 档，落在判据带内，允许）。r*=0.43 → **KV 池 ≈501,851 tokens（480K×1.046，+4.6% 裕量）**、**mamba ≈66 slots**、c8 活性安全、**total host ≈14.91GB（预算 16.7，余 ~1.79GB）boot 可行**。
2. 原协议 r*=0.33（区间 [0.30,0.45]）基于 T=9.45 GiB 假设，重标定后**已失效**：r=0.33 实测池 ≈536K 远超目标带且 mamba 仅 55 slots（仍 ≥51 可用，但偏离"最大留白给 mamba"的经济性）；r=0.44 以上 KV 池跌破 499K 阈值。**r* 上移是 T 实测更大的必然结果**（T↑ → 同 r 下 KV 池更大 → 达阈值的 r 可更高）。
3. **host 墙已解除**：ratio 1.3 下 total host ≈14.91GB < 预算 16.7GB（裕量 1.79GB）→ 全档 boot 可行（含 C0 控制档，原先 1.5 下 C0 失败）。host 池为 **ratio-invariant**（=1.383×device sum 恒 14.91GB），故不改变 ② 判定（device 侧 verdicts 不受影响，ledger:2554）。
4. **③ ④ 衔接**：③④ 继承 r*=0.43 的 engine 配置（KV≈502K、mamba≈66、graph bs8、c8、RH OFF、L3 200G、memory-computed 池）；L2 host 池 ≈1.3×device KV ≈ 652K tokens，**覆盖 active working set 440-480K 的 1.36-1.48×，L2 余量充足**支撑 ③④ 的 host-ready/restore 实验。

---

## Current Architecture（重标定后的容量基线）

- 单卡 3090 24G、Qwen3.5-9B-w4a16 hybrid、31GB host RAM；FP8 attention KV（cell≈15.27KB）+ float32 mamba state（per_slot≈48.9MiB）。
- memory 求解顺序（源码实证）：`available−slack` → mamba 先扣（budget=T·r/(1+r)）→ 剩余返还 attention KV（kv_cache_configurator.py:1836-1838,2124-2183）。
- **T=10.78 GiB**（实测，含 graph 0.72GB 先占与 CUDA graph capture 后余量）。
- host 池 = device×hicache_ratio（ratio-path）；预算 = psutil available−10GB ≈16.7GB；分配次序 kv-host→mamba-host。
- c8 下 mamba 活性需求：**slots≥51**（c8 实测需求，dispatch 给定）且 running cap=⌊slots/ratio⌋（ratio≈3-5，c8 需 ⌊slots/5⌋≥8 → slots≥40，c8 实际需求 51 更严）。

**关键校正**：协议假设 T=9.45 GiB 源自 e2 explicit-64 档反推（≈ratio 0.44-0.49 行为），其误差来自"显式 size 分支绕过 ratio 预算"（ledger:2394/1589）→ 用 ratio 路径观测的 e2 档并非干净的 ratio 标定点。tester e3 用**两条 ratio-path 锚点**（0.90 / 0.33）独立反解，故 T=10.78 为本 sweep 的权威标定。

## Problem / Forces

- **F1（T 重标定）**：T 实测 +14% → 原预测表整体偏高 KV 池 ~8-15%（e.g. 原 C3 预测 498K/51 slots vs 实测 536K/55 slots）。不重推则 r* 定位错误、③ 继承的池/裕量数字失真。
- **F2（host-RAM 墙，ratio1.5 下）**：host total 17.2GB 恒 > 预算 16.7GB → 任何 r 均 boot 失败（tester e3 复现 2/2）。裁决选 A：降 hicache_ratio 1.3（host≈14.9GB，裕量 ~1.79GB）——纯 host/L2 侧改动，device verdicts 不受影响。
- **F3（KV 目标带 vs mamba 经济性）**：目标 480K+4% 需 r≤0.43（实测模型）；但 mamba slots≥51（c8 实际需求）需 r≥0.30 → **可接受窗 [0.30, 0.43]**，比原协议 [0.30,0.45] 收窄上界（0.45/0.44 已跌破 499K 阈值）。
- **F4（观测口径）**：判定以实测 `max_total_num_tokens` / `max_mamba_cache_size` / host 分配成功为权威，预测仅用于选档（protocol §②.1）。

## Proposed Architecture — 重推档表（ratio sweep）

### 配置基准（不变，仅 ratio 变 + hicache_ratio 1.3）
```
kv_cache_dtype=fp8_e4m3 + --cuda-graph-max-bs 8 + --max-running-requests 8 (c8)
RH OFF + L3 extent 200G + waite_complete prefetch + write_back + hicache_ratio 1.3
--mamba-full-memory-ratio <r>   ← 唯一 sweep 变量
不设 --max-total-tokens（memory-computed 池，防 clamp 掩盖 ratio 效应）
```

### 重推档表（T=10.78 GiB, per_slot=48.9MiB, kv tokens/slot=3144 实证；host@1.3≈14.91GB 全档恒）

| 档 | r | mamba slots K | KV device tokens | 距 480K | 距 499,200(480K×1.04) | total host@1.3 | boot | 预期/用途 |
|---|---|---|---|---|---|---|---|---|
| C0 | **0.90**（默认） | 105 | **≈379,235** | −21.0% | −24.0% | 14.91GB | ✅ | **控制档**：演示默认 r 不达标（KV<400K 下界）+ 标定复核（锚点 376,091 实测复现） |
| C1 | 0.60 | 83 | ≈448,403 | −6.6% | −10.2% | 14.91GB | ✅ | 工作集带内下段（400-480K 可装），但池 <499K 阈值 → FAIL-覆盖率 |
| C1b | 0.55 | 79 | ≈460,979 | −4.0% | −7.7% | 14.91GB | ✅ | 工作集带上段，仍 <499K → FAIL-覆盖率（可选） |
| C2 | **0.50** | 74 | ≈476,699 | −0.7% | −4.5% | 14.91GB | ✅ | 贴 480K 但 <499K 阈值；交叉校验 e2 explicit-64（≈448K） |
| C2b | 0.47 | 71 | ≈486,131 | +1.3% | −2.6% | 14.91GB | ✅ | 首次跨 480K；480K 穿越点探针（可选） |
| C2c | 0.44 | 67 | ≈498,707 | +3.9% | **−0.1%** | 14.91GB | ✅ | 阈值边缘（<499,200 差 ~500 tokens），判 FAIL-覆盖率-边缘 |
| **r*** | **0.43** | **66** | **≈501,851** | **+4.6%** | **+0.53%** | 14.91GB | ✅ | **推荐单点**（非整 0.05 档，判据带内允许）；满足 KV≥499,200 ∧ slots≥51 ∧ c8 |
| C3 | 0.33 | 55 | ≈536,435 | +11.8% | +7.5% | 14.91GB | ✅ | 上探（原推荐点，重标定后为过剩档）；slots≥51 活性安全 |
| C4 | **0.25** | 44 | ≈571,019 | +19.0% | +14.4% | 14.91GB | ✅ | 上界探针：**c8 活性边缘**（running cap=⌊44/5⌋=8 贴边，slots<51< c8 实际需求）→ 判定 FAIL-活性/边界 |

**推导要点**（T=10.78 实证模型）：
```
预算(r) = 10.78 × r/(1+r)  GiB
slots(r) = ⌊(预算×2^30 − 48.9MiB) / 48.9MiB⌋
KV tokens(r) = 536,435 + (55 − slots(r)) × 3144   （锚定 C3 实测，斜率=tokens/slot 实证）
total host = 1.383 × 10.78 ≈ 14.91 GB            （ratio 1.3，padding≈1.064，r 无关恒值）
```

**主判据对齐**（PASS 阈值，protocol §②.4 保留 + dispatch 给定）：
- **KV ≥ 499,200**（480K+4%）⇔ r ≤ 0.43（r=0.44 边缘失败）。
- **mamba slots ≥ 51**（c8 实际需求）⇔ r ≥ 0.30。
- **c8 running max=8**（⌊slots/5⌋≥8）：全档 r≥0.25 均 ≥8，但 slots≥51 更严约束下 **r∈[0.30,0.43]** 为有效窗。
- **boot 成功**：全档 host≈14.91GB < 16.7GB 预算（余 1.79GB）→ ✅。

**可接受窗 = [0.30, 0.43]**，**推荐 r*=0.43**（窗内最大 r = 最大留白给 mamba 且池恰好达标）。r=0.30（K=51）为活性下界探针档；r=0.44 以上为 FAIL-覆盖率。

### r* 推荐决策 + L2 支撑
- **r\*=0.43**：满足 KV≥480K+4%（501,851 = 480K×1.046）∧ slots≥51（66）∧ c8 活性不降 ∧ 无 OOM/admission cap ∧ graph bs8 成功。选 0.43 而非更低 r（如 0.33）的理由：**窗内最大 r = 给 mamba 最大留白**（协议 §②.4 取 PASS 中最大 r 规则），同时池恰好覆盖 480K+4% 而非过量，避免低 r 的 mamba 池过小与 running cap 风险。
- **L2 对 ③④ 支撑**：r*=0.43 下 L2 host KV 池 ≈ **1.3×501,851 ≈ 652K tokens**，为 active working set（440-480K）的 **1.36-1.48×**——host-ready/restore 的 L2 余量充足，③（N=8×55K working set≈440-480K）与 ④（parked session 需 Host/L3 驻留）的 host 侧不构成瓶颈。mamba host ≈66×1.3≈86 slots 容量，覆盖 c8 active mamba 需求有余。

### boot-verify 检查表（tester 每档启动确认 3 行）
1. **KV tokens**：engine log "KV Cache is allocated. … #tokens: <实测>（对比档表预测值，r*=0.43 应 ≈501,851，±5% 内）"；无 clamp warning（`larger than the profiled value`）。
2. **mamba slots**：engine log "Mamba Cache is allocated. max_mamba_cache_size: <K>（r*=0.43 应 ≈66）"。
3. **host 分配成功**：engine log "Allocating kv hierarchical KV host pool: <tokens>, <GB>" 与 "Allocating … Mamba host pool" 均**无 ValueError**（`Not enough host memory available`）→ boot 通过（ratio1.3 下预期 14.91GB < 16.7GB budget 全过）。

### 与 Gate D 衔接（③④ 消费清单）
③（e4 spec GATED）与 ④（e5 spec）原写"r*=0.33、池≈498K"，**需随本重推更新为 r\*=0.43、池≈502K、slots≈66**：
- **引擎启动参数**：`--mamba-full-memory-ratio=0.43` + `--hicache-ratio 1.3`（③④ 在 24052 一律 1.3）+ graph bs8 + c8 + RH OFF + L3 200G + 不设 max-total-tokens。
- **预期 KV/slots**：memory-computed 池 ≈502K / mamba ≈66 slots；Gate D "pool64 或 sizing 后最终 profile" = ② r* 定档 memory-computed 池（502K）为准（e4 §0.1，pool64 仅锚参照）。
- **L2 容量**：≈652K host tokens（1.3×device）→ ③ 的 kv_available/evictable 判据、④ 的 Host/L3 occupancy 判据的 host 侧预算基线。
- **Gate D 判定影响**：KV 池 502K > 480K working set，③ 主矩阵 N=8×55K（~440-480K 工作集）resident 无强制 evict（kv_available min>0 可满足）；③ 若某 cell FAIL-挤压（kv_available min=0），按规则降 r=0.30 重跑（协议 §③.3-5 / e4 §3.2-7）——r=0.30 池 ≈549K 仍 ≥480K+4%，为 ③ 的降级备用点。
- **④ 继承**：e5 报告的 r*=0.33 引用全部替换为 0.43；boot 必须核对解析出的 slots（66）与 KV 池（502K）。

### 重标定记录（T=10.78 vs 协议假设）
- **偏差处置**：T 实测 10.78 GiB vs 假设 9.45 GiB = +14% > 10% 阈值 → 触发协议 §②.1/§②.4 重推档。已按 T=10.78 更新全部预测（本表），锚点档（C0/C3）由 tester 实测复核（379K/536K 与锚点 376K/536K 内一致）。
- **对 ③ 的级联**：③ 继承配置从"r*=0.33 池≈498K"改为"r*=0.43 池≈502K"；Gate D 判据阈值不变，但 **r* 上移后 mamba slots 从 55→66**，c8 活性裕量更大（running cap=⌊66/5⌋=13）。
- **对 ⑤ 的级联**：⑤（parked/④ 体系）依赖 ② 定稿 engine 配置（e5 §Stage0-1）。r* 0.43 + hicache_ratio 1.3 更新后：L2 host 池 ≈652K tokens，④ 的 host-ready / RH-staged / L3 occupancy 判据的 host 侧预算略低于原 1.5 假设（1.3×device vs 1.5×device）——**host 侧余量仍充足**（active set 440-480K 的 1.36-1.48×），但 host 池绝对容量比 1.5 时小 ~13%，④ 超配档（S=500/1000）的 L3 依赖不受影响（L3 非 host RAM）。
- **与 ledger:1589 先例一致性**：1589 的"最大有效 KV pool=478K，瓶颈 host RAM 31GB"结论是**显式 max_total_tokens + ratio 路径**下、hicache_ratio 1.5 时测得；本重推在 ratio1.3 下 KV 池可到 502K+（host 墙从 16.7GB→14.91GB 释放），**不冲突**——host 墙是 hicache_ratio×device 的函数，降 ratio 即降低 host 侧占用、放宽 device 池上限。生产 1.5 在 31GB 本机仍受 478K 上限约束（ledger:2554 已确认 = 发现本身）。

## Alternatives（重推过程中评估）
1. **保持 r*=0.33（原推荐）**：重标定后池 ≈536K 远超 480K+4%（过度分配），mamba 仅 55 slots——偏离"最大 r = 最大留白给 mamba"的经济性，且无必要牺牲 mamba 裕量。**否决**。
2. **r*=0.44（非整档下探）**：池 ≈498,707 差 ~500 tokens 未达 499,200 阈值（−0.1%），判 FAIL-覆盖率-边缘；margin 过薄，host RAM 波动（tester e3 先例 4.25-4.99GB 波动）下风险高。**否决**，选 0.43（+0.53% 裕量）。
3. **显式 --hicache-size 控 host / 显式 max-mamba-cache-size**：orchestrator 已否决（B/C：解耦 L2↔device 偏离生产语义；显式 mamba 令 r NO-OP 击穿 sweep 语义，ledger:2557）。本表严格走 ratio-path + hicache_ratio 1.3。

## Migration / Impact
- **无产品代码改动**；配置层：启动 wrapper flag 集更新（`--mamba-full-memory-ratio=<r>` 扫 + `--hicache-ratio 1.3`），③④ 继承 r*=0.43。
- **执行序**：本档表 → tester 重跑 ②（C0/C1/C2/r*/C3/C4 + 可选 C1b/C2b/C2c，6-8 boots）→ ③ → ④。② C2 档（0.50，≈477K）与 ③ 无关，C2b（0.47）为 480K 穿越探针。
- **运行预算**：② ≈6-8 boots × ~15min ≈ 1.5-2h GPU（含失败重跑）；③④ 依 ② 定稿后照排。

## Open Decisions
- **R2（clamp warning）保留**：不设 max-total-tokens 时若引擎出 clamp（memory-computed > 某 cap）：记录 warning 值；异常时退顶格 600000 标注 cap 值。
- **host factor 精确值待实测回填**：本表用 padding≈1.064（ratio1.3→factor≈1.383，total≈14.91GB），为 tester e3 反推的间接值；tester 重跑首档（C0）boot 后应回填实际 `Allocating … host pool … GB` 值，若 factor 偏差 >5% 仅影响 host 裕量（不影响 device verdicts / r*）。
- **C4（r=0.25）slots=44 < 51**：为 c8 活性边界探针（running cap 贴 8 边），判定预期 FAIL-活性/边界——非 r* 候选，仅示证低 r 边界。

## followups
- **tester**：按本档表重跑 ②（hicache_ratio 1.3），每档按 §"boot-verify 检查表"确认 3 行特征；报告按 protocol §②.4 格式（8 项分列 + 主判据/约束/长尾/GPU + verdict + r* 落点），并回填 host factor 实测值。
- **③ ④（e4/e5 spec）**：更新 r*=0.33→0.43、池≈498K→≈502K、slots≈55→66 的引用后照跑。
- **orchestrator**：确认 ③④ 对 ② 定稿（r*=0.43 + hicache_ratio 1.3）的继承，安排 ③④ 在 ② 完成后启动。

## open_issues
- host factor（ratio1.3）精确值待 tester 首档 boot 回填（标注量，不阻塞 r*）。
- C4 边界档是否必跑由时间预算定（活性判据已由 r≥0.30 保证，C4 仅示证）。
