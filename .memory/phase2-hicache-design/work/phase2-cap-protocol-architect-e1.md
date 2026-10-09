# phase2-cap-protocol-architect-e1 — ②③④ 容量实验可执行协议（纯设计，只读）

- Agent: architect
- Epoch: 1
- Date: 2026-09-07
- Scope: **纯设计**。② ratio sweep + ③ capacity curve + ④ parked-session 的可执行实验协议 + 驱动 I/O 契约 + reconciliation 决策点。不实现驱动、不跑 GPU、不改产品代码。
- Repo（只读）：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt` @ 9c9e7b7c7c
- 输入事实：scout e1（work/phase2-cap-scout-e1.md）+ tester e2（work/phase2-cap-e2-tester-e1.md）+ ledger 权威裁决（2407-2436 行）+ 源码核对（见 evidence）。

---

## status: done

## artifacts
- 本报告：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-cap-protocol-architect-e1.md`
- 已读并核对的输入：`work/phase2-cap-scout-e1.md`、`work/phase2-cap-e2-tester-e1.md`、`ledger.md:2407-2436`、`work/phase2-hicache-design-tester-warmctx-e1.md`（64K=64030 长历史 shape 先例）、`work/phase2-hicache-design-tester-conc-sweep-e1.md`（c8≈601 tok/s compute-bound 基线、pool64 推荐点）

## evidence（源码行号 / 报告行号）

> 路径前缀 `SRT=` = `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/`；`MEM=` = `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/`

### 分辨率链（② memory 数学的源码实证）
1. KV 池 byte 预算来源：`SRT/mem_cache/kv_cache_configurator.py:1811-1858` `_profile_available_bytes`：
   - `rest_memory = available_gpu_memory - slack_gb - mm_reservation_gb`（:1836），`slack_gb = pre_model_load_memory × (1 - mem_fraction_static)`（:1822）；
   - **mambaish 模型在池预算内先扣 mamba**：`if self.mambaish_config is not None: rest_memory = self._handle_max_mamba_cache(rest_memory)`（:1837-1838）→ 返回 `total_rest_memory - mamba_state_memory`（:2183）。
2. mamba budget 计算式：`mamba_budget = total_rest_memory × ratio / (1 + ratio)`（:2124-2128）；`per_slot = per_req + replayssm_ring_per_req`（:2151，replayssm=0 主路径）；`max_mamba_cache_size = int((mamba_budget_bytes - per_slot) // per_slot)`（:2152-2157）。
3. mamba 逐请求字节：`mamba2_cache_params.mamba_cache_per_req`（`SRT/configs/mamba_utils.py:116-125`）= (conv_numel×conv_dtype + ssm_numel×ssm_dtype) × mamba层数；float32 下实测 64 slots=3.12GB（tester e2，ssm 3.05 + conv 0.07）。
4. attention KV 池：`available_bytes = rest_memory_after_mamba`（:1858 return × 2^30）；`max_total_num_tokens = available_bytes // cell_size`（`SRT/model_executor/pool_configurator.py:419-428`，DefaultPoolConfigurator，bias=0、page-align）；FP8 cell_size≈15,268 B/token（e2：448,000 tokens = K 3.42GB + V 3.42GB）。page_size 对齐见 :427。
5. `_apply_token_constraints`（:1891-1918）：`user_limit = max_total_tokens` 若 > 计算值则 warning 并取 min——**② sweep 不设 cap 才能观测 memory-computed 池**（关键设计点）。
6. max_running 会被 mamba 池 cap：`resolve_max_num_reqs`（:1920-1973）`min(max_num_reqs, max_mamba_cache_size // ratio)`（:1948-1952），`_calculate_mamba_ratio()` base=3（:156,1865)+overlap buffer（:1874-1877，可到 3-5）→ **低 ratio 档必须验证 running 不降**。

### 关键基线事实（tester e2，FP8+pool64+graph bs8+c8+RH OFF + L3 extent 200G + max_total_tokens=448000）
- KV 448K tokens = 6.84GB（FP8 减半实证，engine log 17:13:44）；max_total_num_tokens=448000（请求值，**未观察到 clamp warning → memory-computed ≥448K**）。
- mamba 64 slots（显式）= 3.12GB float32 → per_slot ≈ 48.9MB。
- CUDA graph 0.64(prefill)+0.08(decode)GB；free VRAM startup 1.74GB；GPU mem mean 22.8/24G。
- kv_used **max 341,818 / p90 216,244**（工作集）；kv_available min 163（池未耗尽）；c8 running max 8 实跑满；272/272 finished；DQ≥55s=0、restore timeout=1、TTFT≥55s=1/272。
- 归因（ledger:2430）：341.8K < 400-480K 是**负载形状**（每 agent 历史仅 L0-L3 21-44K），非池容量。

### 长历史 shape 先例（warmctx）
- `gate2_warmctx.py`：COLD 发整段历史（tokenizer 精确截档 64K→64030 / 128K→128155），WARM 同 session 重发全历史+assistant+短 delta（7-33 token），stream:true 取真 TTFT。64K warm wall p50=1.30s / ttft p50=0.45s，全 device-hit（prefill_devicehit_delta=64064）。→ **"每 turn 重发全历史"是让工作集 resident 的正确驱动形状**。

### c8 性能基线（conc-sweep）
- pool64+c8+graph ON ≈ 596-606 tok/s（compute-bound，350W 墙）；pool96+c16≈992 tok/s；c8 时 mamba used mean=24/avail=11（pool64 未耗尽）。

---

## summary

## Conclusion（先行结论）

1. **② 的回答**：在 pool64+FP8+graph bs8+c8+RH OFF 基础上扫 `--mamba-full-memory-ratio`，**满足"attention KV 池 ≥480K 且 c8 活性不降"的 ratio 区间 ≈ [0.30, 0.45]，推荐单点 r*=0.33**（推导：r 越低 mamba 占比越小、attention KV 池越大；r=0.33 时 memory-computed 池 ≈ 498K、mamba ≈ 51 slots）。r=0.90（默认）时池仅 ≈351K **无法**容纳 400-480K 工作集——这就是默认配置达不到用户目标的 memory 学根源。
2. **③ 的回答**：一张 3090 稳定支持 N 真实 subagent 的可量化判据 = **稳态 TTFT p99≤40s ∧ >60s≤0.5% ∧ DEVICE_QUOTA≥55s=0 ∧ restore timeout=0 ∧ aggregate decode TPS ≥ 450 tok/s ∧ kv_available min>0 ∧ 100% finished**；N∈{4,6,8} 按该判据给对照表。
3. **④ 的回答**：**停放上限 = active-window(c8)+L3 可持久驻留的 session 数**；H=60K 时 200G extent 仅能持久驻留 ~170 session——S=100 为 L3-fit 锚点，S=500/1000 是**显式超配**单元（测 thrash/退化曲线，含 recycle-GC），其降级瓶颈预期在 L3/disk 而非 GPU。
4. 全部由 tester 用现有观测 gauge + engine log 照跑；驱动按 §5 契约实现。

---

## Current Architecture（容量现状：已确认基线）

- 单卡 3090 24G，Qwen3.5-9B-w4a16 hybrid（FP8 attention KV + mamba SSM）。
- 两块独立 cache：attention KV 池（`max_total_num_tokens`，FP8 cell≈15.27KB/token）+ mamba state 池（`max_mamba_cache_size` slot，float32 ≈48.9MB/slot）。无单一 total-active-KV 量。
- memory 求解顺序（源码实证）：`available - slack` → mamba 先扣（budget=rest×r/(1+r)）→ 剩余给 attention KV。
- e2 实测基线：448K 池/6.84GB KV + 64 slots/3.12GB mamba + 0.72GB graph + 1.74GB free + 权重。
- c8 稳态 ≈ 600 tok/s（compute-bound）；warmctx 64K warm turn ttft p50=0.45s（全 device hit）。
- **400-480K 目标 = attention KV working set（8×~50-60K 历史 resident），mamba 独立约束列（ledger 2409-2413 权威）。**

## Problem / Forces

- **F1（memory 分配冲突）**：mamba 与 attention KV 争抢同一 `total_rest_memory`；ratio 大 → mamba 多 → attention KV 池小。默认 0.9 时 attention KV 池仅 ≈351K < 400-480K 目标。
- **F2（负载形状）**：旧负载每 agent 历史 21-44K → 工作集 342K；对齐 400-480K 必须把每 agent 历史推到 50-60K 且每 turn 重发全历史保持 resident（e2 归因，ledger:2430）。
- **F3（编码约束）**：8×50-60K 历史（每 agent ~900MB FP8 bytes）× S session 的 L3 驻留需求 vs /data 160G free + extent max 200G → S≥500 必然 L3 超配。
- **F4（时间预算）**：CUDA graph prefill capture 312.5s/boot（e2），②③④ 合计 ~13-16 次 boot ≈ 1.2-2h 纯启动；每次 cell 独享 GPU。
- **F5（驱动缺口）**：无现成"50-60K 历史 × 多并发"驱动（③）、无"parked 轮换+随机 wake"驱动（④）——契约见 §5，实现归并行 coder。
- **F6（观测口径）**：`num_used_tokens` 不含 mamba（pool_stats_observer 注）；主判据用 `kv_used_tokens`（attention KV working set），mamba 列独立（`mamba_used/available/evictable`）。

---

## Proposed Architecture — ② ratio sweep 协议（核心交付）

### ②.0 配置基准（所有档固定，仅 ratio 变化）
```
kv_cache_dtype=fp8_e4m3
--cuda-graph-max-bs 8      （CUDA Graph bs8）
--max-running-requests 8   （c8）
RH OFF（现状）
L3 extent: {"max_size":"200G","min_free_space":"10G"} + waite_complete prefetch + write_back + hicache_ratio 1.5
--mamba-full-memory-ratio <r>   ← 唯一 sweep 变量
**不设 --max-total-tokens**（或设 600000 顶格）：让 max_total_num_tokens = memory-computed 值（F6/evidence 5：设 cap 会掩盖 ratio 效应）
```
不用 `--max-mamba-cache-size`（显式会绕过 ratio 路径，ledger:2394）。

### ②.1 memory 数学推导（候选档数值从何而来）

**标定公式**（源码实证，evidence 1-4）：
```
T   = total_rest_memory（available - slack - mm，在 FP8+graph bs8 启动配置下 ≈9.4-9.6 GiB，含 graph 0.72GB 先占）
per_slot ≈ 48.9 MB（float32，e2 实测 64 slots=3.12GB）
预算   = T × r/(1+r)
K(r)  = floor((预算 - per_slot) / per_slot)
KV_bytes = T - (K+1)×per_slot
池tokens(r) ≈ KV_bytes / 15,268 B/token（FP8 cell，page-align 后略低）
```

**标定锚点**：e2 explicit-64 档 ≈ ratio 0.44-0.49 行为（64 slots ↔ r≈0.45 预算 3.15GB），observed 池 448K → 反解 T≈9.45 GiB（±5%，graph 先占致 pool 略小于 bf16 soak 的 ~10.3 GiB）。r=0.90 默认档（non-FP8 soak 得 mamba≈106 slots bp 同式）自洽。

**候选档表**（预测值，±5% 校准误差；**判定一律用实测 max_total_num_tokens gauge**，预测仅用于选档）：

| 档 # | ratio r | mamba budget | 预测 slots K | 预测 attention 池 tokens | 预期 c8 活性 | 用途 |
|---|---|---|---|---|---|---|
| C0 | **0.90**（默认） | 4.48 GiB | ~97 | **≈351K** | 池<工作集 → 强制 evict/recompute | **控制档**：演示"不 sweep 会怎样" + 标定 T |
| C1 | 0.60 | 3.55 GiB | ~76 | ≈418K | 池<480K，工作集会部分 evict | 下界方向 |
| C2 | **0.45** | 3.15 GiB | ~63 | ≈460K | ≈ e2 explicit-64 等价点 | 交叉校验（与 e2 基线对齐） |
| C3 | **0.33** | 2.52 GiB | ~51 | **≈498K** | max_running cap=51//3..5≥10，c8 安全 | **推荐单点 r*** |
| C4 | **0.25** | 2.03 GiB | ~41 | ≈530K | cap=41//5=8 **贴 c8 边** | 区间下界探针（c8 活性风险档） |
| C5(opt) | 0.40 / 0.30 | 2.90/2.34 GiB | 59/47 | ≈473K/511K | c8 安全 | 精确定位 480K 穿越点（可选二分） |

推导要点：`池tokens(r)` 在 r∈[0.9,0.25] 单调从 ~351K → ~530K，**跨越 400-480K 目标发生在 r≈0.40-0.35**。mamba 活性下界：c8 需 slots ≥ 40（concat：conc-sweep c8 used mean 24 + 安全裕量 + max_running cap 要求 slots≥8×5=40）→ **r≥0.30**（K≈47）为硬下界。故**区间 = [0.30, 0.45]，推荐 r*=0.33**（池≈498K ≥ 480K+4% 裕量，slots≈51 活性安全）。

### ②.2 负载 shape（驱动契约要件，与 ③ 共享同一 shape）
- 固定 **N=8 agents**；每 agent 历史 `H0 = 52-56K token`（tokenizer 精确截档，实测 prompt_len 记录）；每 turn delta `d = 180±(64-256 jitter)`；**TURNS=20**。
- **每 turn 重发全历史 + assistant + delta**（warmctx 模式，evidence）；最终每 agent ≈ H0+d×20 ≈ 55.5-60K；**预期工作集 = 8×(H0+d×T) ∈ [440K, 480K]**（主判据对齐）。
- Prime：8 agent 串行 COLD 全历史（各自首 turn，空 cache）→ 之后并发 warm turns r2..r20。
- stream:true（真 TTFT：warmctx 纪律）；record per-req：prompt_len / history_len / delta_len / ttft_s / wall_s / http / finished / device_hit / host_hit / storage_hit。
- 跨档控制：同 shape 同 seed、同 turn 结构、同 N；engine random_seed 每 boot 不同（已知 confound，记录）。

### ②.3 每档观测清单（8 项分列 + 主判据 + 约束列 + 长尾 + GPU）
| # | 项 | 取法 |
|---|---|---|
| 1 | resolved attention KV capacity tokens | `max_total_num_tokens` gauge + engine log "KV Cache is allocated … #tokens"（**memory-computed 值**） |
| 2 | KV bytes | engine log K/V sizes（该档实际字节） |
| 3 | mamba slots | engine log max_mamba_cache_size（ratio 自动 fit 结果） |
| 4 | mamba bytes | engine log ssm+conv（该档实际字节） |
| 5 | max effective active requests | mid-run `num_running_reqs` max；**必须=8**（mamba cap 未压低 running，evidence 6） |
| 6 | CUDA Graph | boot-metrics 0.64+0.08GB（恒量，记录确认） |
| 7 | free VRAM startup | boot-metrics `startup_available_gpu_memory_gb`（**≥1.2GB 才继续**，防低 ratio 大池 + graph OOM） |
| 8 | c8 真实可运行 | running max=8 ∧ 100% finished ∧ sha16 非空 ∧ 0 OOM/BackendError |

**主判据**：`kv_used_tokens` **max / p90 是否达 400-480K**（工作集达目标区且全部 resident）。预期：C0 ≈351K 池 clamp（工作集超池 → evict）、C2 ≈460K、C3 ≈480-498K 达标。

**约束列（mamba 独立，不折算）**：`mamba_used_tokens` / `mamba_available_tokens` / `mamba_evictable_tokens` max/mean + slots/bytes；mamba drive 压低 running（engine log "max_running_requests was reduced"）必须为 0。

**长尾**：DQ≥55s（DEVICE_QUOTA 型 WAIT 次数）、restore timeout、TTFT>30s 比例、>60s 比例、TTFT p50/p95/p99；restore_recompute 总数。

**GPU/VRAM**：GPU util mean/p50、mem mean、无 OOM。

### ②.4 PASS / FAIL 判定
**档级判定**（每档 verdict=PASS/FAIL + 原因）：
- **PASS 候选** ⇔ 全部：① 实测 max_total_num_tokens ≥ **500,000**（覆盖 480K+4% 裕量）；② mamba slots ≥ 40 且 running max=8（活性不降）；③ 稳态窗 `kv_available_tokens` min > 0（工作集峰值时池不全满 → 无强制 evict）；④ 稳态 DEVICE_QUOTA≥55s = 0、restore timeout = 0；⑤ 100% finished。
- **FAIL-覆盖率**：max_total_num_tokens < 480K（r 过高，池装不下工作集）。
- **FAIL-活性**：running < 8 或 mamba_available 稳态 = 0（r 过低，mamba 池不够 c8）。
- **FAIL-挤压**：稳态 kv_available min=0 且出现 DQ/evict（池 ≈ 工作集，无裕量 → 判定为边界，需降 r）。
- **FAIL-运行**：OOM / BackendError / finished<100%。

**② 整体判定（"找到 400-480K 配置" = 输出）**：
- 取 PASS 候选档中 **最大 r** 为 r*（最大留白给 mamba）；推荐 r*=0.33，区间 [0.30, 0.45] 报告为可接受窗。
- **报告格式**：每档 8 项分列表 + 主判据/约束/长尾/GPU 行 + verdict + 最终 "recommended: mamba-full-memory-ratio=r*（区间 [a,b]）"，附 C0 控制档的 evict/recompute 量化（示证"默认 0.9 为何不达标"）。
- 若无档 PASS：按 FAIL 原因分类报；C0 标定 T 偏差 >10% → **重标定**再推档（换档后重跑）。

---

## Proposed Architecture — ③ capacity curve 协议

### ③.0 配置
**继承 ② 的定稿**：kv_cache_dtype=fp8_e4m3 + `--mamba-full-memory-ratio=r*` + graph bs8 + c8 + RH OFF + L3 extent 200G + memory-computed max_total_tokens。`--max-running-requests=N`（每档 N）。

### ③.1 run 结构
**主矩阵：N∈{4,6,8} × H0=55K**（3 个必跑 cell）；**可选追加：N=8 × H0=50K、N=8 × H0=80K**（历史维度；视时间/GPU 预算）。

每 cell（与 ②.2 同 shape 模板，N 可变）：
1. **Prime（串行 COLD）**：N agent 各自首 turn 发全 H0（空 cache）→ 填 L1，COLD prefill 数据归档（TTFT p50 max）。
2. **稳态**：r2..r20 并发 warm turns（delta 180±jitter），**每 turn 重发全历史**。
3. **时长**：prime ≈ N×15-25s（64K COLD≈19s，warmctx 参照）+ 稳态 ≈ 30-80s decode 量 240-450 受 600 tok/s 约束 → **cell 总数 ≈ 6-10 min（不含 boot 7.3min）**。稳态窗必须覆盖 ≥150 次请求（对齐 e2 272 次的 DQ 统计力）。

### ③.2 测量（每 cell 对照表列）
| 列 | 指标 |
|---|---|
| N / H0 / 实际 final 工作集 | 8×(H0+d×20)，实测 kv_used |
| resident device KV | kv_used max/p90/mean, kv_available min, kv_evictable mean |
| 命中分布 | device_hit / host_hit / storage_hit tokens（每 cell 总和 + per-req 比例） |
| recompute | Σ(prompt_len − (device+host+storage)_hit) per req；recompute fraction = recompute/total served |
| TTFT | 稳态 p50/p95/p99、>30s 比例、>60s 比例、max |
| decode | aggregate decode TPS（realtime_tokens_total mode=decode delta / 稳态窗）、per-req TPS(TPS/N) |
| GPU | util mean/p50、mem mean |
| 长尾/健康 | DQ≥55s、restore timeout、restore_recompute、OOM、finished=100%、sha16 非空 |

### ③.3 判定："一张 3090 稳定支持 N 真实 subagent"（全 AND）
1. 100% finished、0 error/OOM；
2. 稳态 **TTFT p99 ≤ 40s** ∧ **>60s 比例 ≤ 0.5%** ∧ **>30s 比例 ≤ 2%**（校准锚：e2 448K 池 p99=45.5s/1×55s@272；H 涨到 55K 可预期 p99 收紧，p99>60s 即 FAIL-不稳定）；
3. **aggregate decode TPS ≥ 450 tok/s**（=600 tok/s 天花板的 75%；低于此 = 并发/tail 开销主导）；
4. 稳态 **DEVICE_QUOTA≥55s = 0** ∧ **restore timeout = 0**；
5. 稳态 **kv_available min > 0**（工作集 resident 无强制 evict；若 N=8×H0=55K 时裕量消失 → 判 borderline，按 ② 规则降 r=0.30 重跑该 cell 后再判）；
6. recompute fraction ≤ 5%。

**输出**：对照表（行=N 或 N×H）+ 每 cell verdict + 汇总句："3090 在 r* 下稳定支持 N=8×(50-80K) 真实 subagent（TTFT p99 Xs / DQ=0 / TPS Y tok/s / recompute Z%）"，N=4/6 为拟合下界与退化趋势。

---

## Proposed Architecture — ④ parked-session 协议

### ④.0 配置
继承 ② 定稿（r*），c=8 固定（active 窗口）。**禁 WAIT_CAPACITY、禁 /pause_generation**（ledger:2415-2419 权威）；轮换驻留完全由"turn 完成 → 停发 → 随机后再次发"自然产生。

### ④.1 run 结构
- **主矩阵：S∈{100, 500, 1000} × H0=55K × wake=指数(mean 0.6s, seed 固定 20260907)**（3 个必跑 cell）。
- **H 与 L3 容量的硬约束**（先算账）：每 session 55K 全历史 ≈ 55,000×15.27KB ≈ **840MB** L3 bytes；200G extent 耐久驻留上限 ≈ **~170 session@55K**，/data 实际可用 ≈160G。→ **S=100 是 L3-fit 锚点**（~84GB ✓）；**S=500/1000 为显式 L3 超配 cell**（需 ~420G/~840G 存储）——其降级瓶颈预期在 **disk/recycle 而非 GPU/架构**，这正是"能停放多少"的答案边界（**结论将由 recycle-GC 度量支撑，而非伪装成架构失败**）。
- **rotation**：主策略 = **random-seeded**（seed 固定，跨 S 可比）；可选对照 cell = S=500 round-robin。active 窗口恒 8：请求完成 → 从窗口移除 → 按指数间隔 pick 下一 session（若 session 在窗口内则重新抽）。
- **wake 节奏**：mean 0.6s ≈ 1.67 turn/s → 稳态 80-95% GPU 利用（~500±100 tok/s）；S=100 cell 30min 稳态 → 每 session ~30 turns；S=500/1000 45/60min 稳态（对齐 turns/hour 统计力）。**每 cell 记录 S、seed、λ、实际 turns/hr**。
- **前置**：devops 预检 /data free ≥ S×840MB×1.2+20G；不足 → 对 S=500/1000 报 reconciliation（见 §6 R1），不静默缩 H。

### ④.2 测量（每 cell）
- **随机 resume TTFT** p50/p95/p99、max、>30s/>60s 比例（col descent：这部份含 L1/L2/L3 restore 全程）。
- **命中分布**：device_hit / host_hit / storage_hit tokens + per-req 比例；**recompute tokens + fraction**。
- **驻留/占用**：Host pool（`hicache_kv_host_usable_tokens` / `hicache_mamba_host_usable_tokens` / `hicache_host_used_tokens` / `hicache_working_tokens`）；L3 occupancy（extent slots in use、extent_write bytes cumulative）。
- **recycle-GC**：extent_recycle 次数、GC bytes、recycle 触发率（与 S、turns/hr 对照）。
- **吞吐**：turns/hour、aggregate decode TPS。
- **session age vs resume latency**：按 age 桶（<1min /1-5min /5-30min /30min+）输出 TTFT p50/p95（预期单调上升；拐点 = 层间驻留边界证据）。
- **健康**：0 OOM、100% finished、DQ≥55s、restore timeout、GPU util。

### ④.3 判定："能停放多少长期 Agent 随机唤醒而不显著退化"
**稳定停放（PASS）** ⇔ 全 AND（基准校准：e2 Phase B restore TTFT p50=0.5s / warmctx 64K warm p50=0.45s）：
1. resume TTFT **p50 ≤ 5s** ∧ **p95 ≤ 30s** ∧ **>60s 比例 ≤ 1%**；
2. turns/hour ≥ 80% × (schedule 上限)（无 thrash collapse）；
3. **recompute fraction ≤ 5%**（recycle 未摧毁有效缓存比）；
4. DQ≥55s=0、restore timeout=0；
5. 0 OOM、100% finished。

**输出**：per-S 对照表（resume TTFT / hit 分布 / recompute / turns-hr / TPS / Host-L3 occupancy / recycle-GC / age-latency 表）+ verdict。**回答格式**："一张 3090 + H0∈[50-80K] 可稳定停放 **S_ok** 个长期 Agent（满足上述判据的 max S）；S=500/1000 的退化由 **<瓶颈名>**（预期 L3/disk recycle）主导,量化值如上。"

---

## Proposed Architecture — 驱动 I/O 契约（供并行 coder 对齐）

### ③ 驱动契约（`cap3_driver`）
**输入**：
- `--agents N ∈ {4,6,8}`；`--history-tokens H0 ∈ {50000,55000,80000}`（默认 55000）；`--delta-mean 180 --delta-jitter 64..256`；`--turns 20`（首 turn=COLD prime）；`--stream true`；`--seed`；`--url`。
**行为**：
1. 生成 N 个确定性、互异的长历史文本（tokenizer 精确截档，**实测 prompt_len 记录并断言 H0±2%**）；
2. r=1：N* 串行 COLD prime（全 H0）；r≥2：N* 并发 warm turns，**每 turn 重发全历史+assistant+delta**；
3. 全程并发注入窗口=N（c=N）；每 req 记录。
**输出（runs.csv 列，必含）**：`ts,session_id,turn,prompt_len,history_len,delta_len,ttft_s,wall_s,http,finished,storage_hit,host_hit,device_hit`（hit 单位 tokens；加 engine-independent 冗余：prefill_effective_tokens delta 各 mode，供 tester 交叉验证）。
**健康断言**：all http=200 ∧ all finished ∧ sha16 非空；异常则输出诊断 + 对应 cell FAIL-运行。

### ④ 驱动契约（`cap4_driver`）
**输入**：
- `--sessions S ∈ {100,500,1000}`；`--history-tokens H0`（默认 55000）；`--active 8`；`--wake exp --interval-mean 0.6`；`--strategy random|round-robin`（default random）`--seed 20260907`；`--steady-minutes {30,45,60}`；`--url`。
**行为**：
1. 建 S 个稳定 session（tokenizer 精确 H0 前缀，Cold 预填按需分批——**不一次性全 COLD**，避免启动雪崩：prime 后即可开始轮换）；
2. active 窗口恒 8；turn 完成 → 释放 → 指数间隔（mean λ）pick 下一 session（窗口内重抽）；strategy=random 用固定 seed；
3. **不调用任何 pause/WAIT 端点**（语义铁律）；
4. 每 event 记录 session-id/turn/时间戳；每 req 记录同 ③ runs.csv 列 + `session_age_s`（距该 session 上次 turn 的秒数，age 桶分析用）。
**输出**：runs.csv（含 age 列）+ turns/hr + 调参日志（若实际平均 running < 7 或 GPU util <70%，如实记录 λ 是否需调，不静默改 seed）。
**健康断言**：同 ③ + 轮换无死锁（每 session 至少被 pick 过，最终 turns>0）。

### 通用（两驱动共用）
- runtime confound 记录：engine-alloc.txt（random_seed、各 flag 实际生效值）、boot-metrics；每 cell fresh namespace（`/data/l3/p2io-cap-*`）；run 后 SIGTERM + 确认回 15MiB idle（tester 既有纪律）。

---

## Alternatives（② ratio 之外，考虑过并否决/降级的 sizing 选项）
1. **显式 `--max-mamba-cache-size=64`（e2 基线）**：等价 r≈0.45-0.49，池 448-460K < 480K 目标，且绕过 ratio 语义（ledger:2394 已定不用）→ 仅作交叉校验 C2。
2. **`--mamba-ssm-dtype bfloat16`（mamba state 减半）**：per_slot 减半 → 同 ratio 下 slots 翻倍或 KV 池再大；但改变 e2 基线 dtype（float32），sweep 结论不再可与 e2 对照 → 列为 ② 之后的可选 follow-up cell，不进主 sweep（reconciliation R3）。
3. **提高 `--max-total-tokens` 至 memory-computed cap（r=0.9 下强制 480K+）**：池不在 0.9 下变大——memory 数学下 KV 池由 T/(1+r) 决定，cap 只能缩小不能撑大；default-ratio 下池 ≈351K 是硬算数（evidence 1-4）→ 唯一增大途径是**降 ratio**（或减 graph/权重，不在实验授权内）。
4. **加大 graph bs / pool>64 对 ②③ 的意义**：c16@pool96≈990 tok/s 是 compute-bound 墙内吞吐选项，但用户已定 ③=4/6/8、④=active8（ledger:2413,2422）；pool96 需 +1.5GB 且高并发近满池伤吞吐（conc-sweep）→ ②③④ 主协议不引入，标注为 out-of-scope 观察点。

## Migration / Impact
- **无产品代码改动**；配置层（启动 wrapper flag 集）+ 驱动层（③④ 驱动由并行 coder 交付）。① → ② 的配置冻结到 devops wrapper（direct-launch-cap-fp8.sh 基准，仅替换 ratio）。
- **执行序**：②（coder 驱动 shape 就绪后）→ ③ → ④（ledger:2422/2432）；GPU 串行独占。② 的 C2 档同时是 ③ 的配置复验点。
- **运行预算**：②=6-7 boots（含可选 C5），③=3-5 boots，④=3-4 boots（+可选项）≈ **13-16 boots × ~15min ≈ 3.3-4h GPU 时间**（含 boot；不含失败重跑），/data 峰值占用 ≈ S=1000 单元 ~300-900GB 累计写（循环）。由 orchestrator 排期。

## Open Decisions（reconciliation 决策点：标注不裁决）
- **R1（④ 的 L3 超配，最重）**：S=500/1000 × H0=55K 需 ~420-840GB L3 存储 >> /data 160G+extent 200G。选项：a) 保持 H0=55K、接受显式 thrash 测量（recycle-GC 成为主指标，回答"上限"）；b) 对 S≥500 缩 H0（破坏 50-80K 前缀规格）；c) devops 扩容 /data/extent（改基础设施）。**冲突时谁优先：规格完整性 vs 磁盘预算** → 需 orchestrator/用户裁决。
- **R2**：② 档不设 max_total_tokens → 若引擎出 clamp warning（`larger than the profiled value`）：记录 warning 值；若 engine 拒绝 memory-computed（异常），退顶格 600000 并标注该档为 cap 值。
- **R3**：mamba_ssm_dtype 保持 float32（对齐 e2）还是 C4/C5 活性失败时切 bf16 救场——切 dtype 会破坏 8 档内对照 → 只能整 sweep 重跑（标注为 follow-up 而非 mid-sweep 修复）。
- **R4**：free VRAM startup < 1.2GB 的档（低 ratio 大池）：重跑前先降 graph bs 或确认 capture 顺序；不改 ratio 判定语义。
- **R5**：④ wake λ（mean 0.6s）若 turns/hr 过低（drive 未喂饱）或过高（active 窗口排队）→ λ 是调节参数，每 cell 如实记录；跨 S 可比性要求同 λ（同 seed）。
- **R6**：history 文本内容类型（指令式/自然语言）影响 FP8 数值行为与 radix 分支分布；统一用 gate2 风格确定性文本，跨档一致。
- **R7**：N<8 档的并发 = N（非 8）；若驱动按 8 注入会造成空窗，必须 c=N。
- **R8**：③ 的 aggregate decode TPS 判据 450 tok/s 若 N=4 天然低（<450）→ N=4 档判据降为"相对 N=8 的 60% 且 monotonically 上升"，不硬套 450 绝对线（标注规则，避免 N=4 被误杀）。
- **R9**：FP8 scale-factor=1.0 默认近似（e2 note）非阻塞；若 ③④ 出现 hit-count/correctness 异常（sha16、缓存恢复崩坏），先升级诊断再信容量数字。

## followups
- tester 照跑 ②（C0-C4 + 可选 C5），报告按 §②.4 格式；之后 ③、④ 依序。
- coder 并行交付 ③④ 驱动（契约 §5）；汇合时过 R1-R9 清单。
- devops 预检：/data free（④ 前置，R1 输入）、runner 无残留、GPU idle。
- 若 ② C0 实测与预测偏差 >10%：重标定 T 后重推档（C0 为标定锚）。

## open_issues
- R1（L3/磁盘预算）为 ④ 能否按规格执行（S≥500）的唯一外部阻塞，需 orchestrator/用户裁决。
- ② 预测表 ±5% 校准误差（源自 GB/GiB 语义 + graph 先占量的不确定性）；判定以实测 gauge 为权威。
- c8 下 mamba 活性下界（slots≥40）源自 conc-sweep used mean 24 + cap 规则推演，非饱和压力实测；C4 档（41 slots）即为该边界的实测探针。