# phase2-cap-scout-e1 — 容量/性能实验（②③④）可执行性事实侦察

- Agent: scout
- Epoch: 1
- Date: 2026-09-07
- Scope: 只读事实侦察（不实现/不测试/不改码/不加埋点），为 24052 后续实验②③④ 提供基线事实。
- Repo: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt` @ 3090-24g-opt @ 9c9e7b7c7c
- 检索范围：`python/sglang/srt/`（server_args.py / managers/scheduler.py / mem_cache/* / model_executor/pool_configurator.py / observability/metrics_collector.py）+ 3090-dev/ 测试 + `.memory/phase2-hicache-design/{context.md,ledger.md,work/*.md}`。

---

## status: done

## artifacts
- 本报告：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-cap-scout-e1.md`
- 侦察结论表（见 summary 下逐项）。

## evidence（每结论 文件:行号 佐证）

> 路径前缀 `SRT=` = `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/`。
> `MEM=` = `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/`

### Q1 FP8 KV on 3090 — 真实支持面

1. `kv_cache_dtype` 合法取值与 CUDA 版本前提：
   - `SRT/server_args.py:636-662` — `kv_cache_dtype: A[str, ...]`，choices 含 `auto/fp8_e5m2/fp8_e4m3/mxfp8/bf16/bfloat16/nvfp4/fp4_mx_block16/fp4_e2m1`，默认 `"auto"`。
   - `SRT/server_args.py:640-646` — 原文注释：`"fp8_e5m2" and "fp8_e4m3" are supported for CUDA 11.8+.`（**无 SM80/3090 arch 显式禁用字样**；仅 CUDA 版本门槛）。无 "3090"/SM80 限制注释在 fp8 定义处。
2. `kv_cache_dtype` 的 dtype 解析：
   - `SRT/mem_cache/kv_cache_dtype.py:53-57` — `elif server_args_kv_cache_dtype == "fp8_e4m3": ... kv_cache_dtype = torch.float8_e4m3fn`（非 HIP 分支）；`fp8_e4m3` → `torch.float8_e4m3fn`。
   - `SRT/mem_cache/kv_cache_dtype.py:14-19` — `TORCH_DTYPE_TO_KV_CACHE_STR` 将 fp8_e4m3fn / fp8_e4m3fnuz 均映射回 `"fp8_e4m3"`。
3. FP8 KV 作用对象 = **注意力 KV cache，不是 mamba SSM state**：
   - `SRT/model_executor/pool_configurator.py:152-160` — mambaish 模型 `num_layers = len(full_attention_layer_ids ...)`（**仅计 full-attention 层**；mamba 层不计入 KV cell）。
   - `SRT/model_executor/pool_configurator.py:244-253` — `kv_cache_dtype = kvc.kv_cache_dtype; kv_size = torch._utils._element_size(kv_cache_dtype)`，cell_size 直接乘 `kv_size`。**FP8 直接减半注意力 KV 每 token 字节。**
   - mamba SSM state 的 dtype 独立、**无 fp8 选项**：
     - `SRT/server_args.py:2607-2614` — `mamba_ssm_dtype: A[Optional[str], choices=["float32","bfloat16","float16"]]`（无 fp8）。
     - `SRT/mem_cache/mamba_checkpoint_pool.py:31-34` — 明确写 "Why int8 (not fp8)"：缓存 state 用 **int8**（非 fp8），注释直述 fp8 浪费指数位。即使 MambaCheckpointPool（Host 残留物/缓存）也是 int8 而非 fp8。
   - **结论**：`fp8_e4m3` 只压缩 prefill/decode 的 **attention KV pool**；**mamba state（SSM 状态）不受 `kv_cache_dtype` 控制**，用 `mamba_ssm_dtype`（bf16/float16/float32，无 fp8）。
4. FP8 KV 是否作用于大 concurrency 池（实验② 的 "KV pool"）：
   - `SRT/model_executor/pool_configurator.py:145,162` — `max_tokens = (available_bytes - bias) / coeff`，`coeff = cell_size（每 token 全部注意力层字节）`。FP8 减半 cell_size → 相同内存下 `max_total_num_tokens`（= 注意力 KV pool token 容量）近似翻倍。**即 FP8 直接提高注意力 KV pool 的 active-token 上限。**
5. kv_cache_dtype 与 enable-batch / cuda-graph-backend-* / pool 配置：
   - 在 server_args 中无 `--kv-cache-dtype` 与 `--enable-batch` / `--cuda-graph-backend-*` 的互斥/禁用分支（grep 未见冲突代码）。fp8 dtype 解析独立于 batch/graph 选择。
   - 唯一相关的 interaction 是 DFLASH draft attention（`kv_cache_dtype.py:85-99`）：fa4 draft 读不了 fp8 KV，故 draft 被覆盖回 compute dtype；**对 target/目标模型（本实验 Qwen3.5-9B）无影响**。
   - 需要实测确认：fp8_e4m3 KV 与 triton/线性注意力 kernel 在当前 3090+CUDA 上的数值行为（SM80 真卡 kernel 支持面）。**待实测**（源码无禁，但真卡行为是源码检索不可判定的）。

### Q2 mamba ratio sweep knob

1. 准确参数名 / 默认 / 类型 / 域：
   - `SRT/server_args.py:2633-2640` — **`mamba_full_memory_ratio: A[float, Arg(help="The ratio of mamba state memory to full kv cache memory.", resolvable=True), NS("schedule")] = 0.9`**。float，默认 **0.9**，单位 = 比率（无单位），可解析（resolvable），`NS("schedule")` 命名空间。
   - CLI 名：`--mamba-full-memory-ratio`（`_margin` 解析自 `mamba_full_memory_ratio`）。
2. ratio 如何决定 mamba state cache 大小（计算式）：
   - `SRT/mem_cache/kv_cache_configurator.py:2121-2129` — 注释原文 `(K + 1) * per_req + (K / ratio + 1) * D * per_req = mamba_budget_bytes`，且
     `mamba_budget = total_rest_memory * ratio / (1 + ratio)`。
   - **`total_rest_memory * ratio/(1+ratio)`** = 分配给 mamba state cache 的字节预算。`ratio` 升高 => mamba budget 占 `total_rest_memory` 的比例升高；`ratio→0.9` 时 mamba ≈ 47.4% 的 rest memory。
   - `SRT/mem_cache/kv_cache_configurator.py:2150-2157` — **无 spec_dec 主路径**：`per_slot = per_req + replayssm_ring_per_req; max_mamba_cache_size = (mamba_budget_bytes - per_slot) // per_slot`。**单个制片点**。
3. `max_mamba_cache_size` 与之并存/冲突：
   - `SRT/mem_cache/kv_cache_configurator.py:2075-2081` — 若**显式设置 `--max-mamba-cache-size`**：走 `max_mamba_cache_size // attn_dp_size` 直接定池，**绕开 ratio 计算**（`else` 分支才是 ratio 路径，2116-2157）。
   - **二者互斥选择**：`--max-mamba-cache-size`（显式 slot 数）与 `--mamba-full-memory-ratio`（比率自动 fit）二选一；都未设则 ratio=0.9 默认自动 fit。
   - `max_mamba_cache_size` 单位 = **state slot 数**（每 request 一个去重 state slot），非 token：
     - `SRT/mem_cache/kv_cache_configurator.py:1936-1951` — `ratio = _calculate_mamba_ratio(); mamba_cap = max_mamba_cache_size // ratio; ... min(max_num_reqs, mamba_cap)`（ratio = "state slots per request"，cap 与 **requests** 计数比较）。
4. total active KV（400-480K 目标）与 ratio/pool64/FP8 的现成计算式：
   - **没有单一 "total active KV" 聚合量**。两块独立 cache：
     - **注意力 KV pool**：`max_total_num_tokens` token 上限，独立由 `cell_size`（FP8 影响）+ `total_rest_memory` 决定（pool_configurator.py:145,253）。
     - **mamba state pool**：`max_mamba_cache_size` slot 数，由 `mamba_budget = total_rest_memory*ratio/(1+ratio)`（kv_cache_configurator.py:2126-2127）决定。
   - 计算路径存在但分置两处：`pool_configurator.py:145`（full KV token）× `kv_cache_configurator.py:2124-2129`（mamba budget）。**"400-480K active KV" 需按两池分开核算**（见 Q3 观测口径、Q6 抉择点）。
   - **FP8 对 mamba budget 的间接作用**：FP8 减半注意力 KV cell_size → 相同 `total_rest_memory` 下注意 KV 容量 +，**同时 `total_rest_memory` 变大 → mamba budget 也随之增**（同一 ratio）。需实测确认 3090 上总收益分配。

### Q3 active KV 观测口径（现存可观测指标，无新埋点）

> 全部来自 `SRT/observability/metrics_collector.py`（Prometheus gauge），已有驱动（`common.fetch_metrics_text`）在前置实验使用。

1. 注意力 KV pool token 口径:
   - `sglang:kv_used_tokens`（活跃使用 slot）— metrics_collector.py:378-383。
   - `sglang:kv_available_tokens` / `sglang:kv_evictable_tokens`（空闲 / radix 可驱逐）— 366-371, 372-377。
   - `sglang:num_used_tokens` — 360-365；但注意 pool_stats_observer.py:53-62 注释：**注意力 KV 的 token usage 计算不含 mamba pool**（`num_used = max(full_num_used, swa_num_used)`）。
   - `sglang:max_total_num_tokens` / `_swa` — 1112-1119,1598-1600。
2. mamba state 口径（前实验已用过 `mamba_used`/`mamba_evictable`/`mamba_available`）：
   - `sglang:mamba_usage`（ratio）— 350-356,1438。
   - `sglang:mamba_available_tokens` — 402-407,1448。
   - `sglang:mamba_evictable_tokens` — 408-413,1449。
   - `sglang:mamba_used_tokens` — 414-419,1450。
   - **单位 = state slot 数**，非 token。
3. Host/KV pool（实验④ Host/L3 residency）：
   - `sglang:hicache_host_used_tokens` / `hicache_host_total_tokens` / `hicache_kv_pool_tokens` / `hicache_writeback_reserve_tokens` / `hicache_ready_resident_tokens` / `hicache_working_tokens` / `hicache_spec_inflight_tokens` / `hicache_usable_tokens` — 152-171 定义，655-733 注册。
   - `sglang:hicache_kv_host_usable_tokens` / `hicache_mamba_host_usable_tokens` — 169-171,721-733（**分 KV 与 mamba 两个 Host pool usable**）。
4. 既有驱动已用这些量：`MEM/.../work/phase2-hicache-design-tester-conc-sweep-e1.md:35`（mamba used/avail mean=24/11）、`:84-87`（mamba used/avail/evict 轨迹）、`warmctx-e1.md:16`（prefill_devicehit_delta 全量命中）。
5. **判定 ② 的 400-480K "total active KV" 的可用口径**：不存在单一口径；需聚合 `kv_used_tokens`（≠ num_used，num_used 不含 mamba）+ `mamba_used_tokens`。各量现成、无新埋点。

### Q4 50-80K context 负载现状

1. **已有 32K/64K/128K 三档长上下文负载**（不是空白）：
   - `MEM/.../work/phase2-hicache-design-tester-warmctx-e1.md:20-23,29-31` — `gate2_warmctx.py`：COLD 发整段历史（tokenizer 精确截档 32K→32053 / 64K→64030 / 128K→128155 token）→ WARM 同 session 增量。MAX_TOTAL_TOKENS 按档（64K=131072 / 128K=196608）。
   - **64K 档 = 64030 token 已跑过**（warmctx-e1.md:30），落在 50-80K 目标区间内；**128K 档已证明 128K 可表达**。
2. 负载形状能否表达"真实 Claude subagent 行为"：
   - gate2_warmctx 是**单 session 长历史 + 小增量 warm-turn**（warmctx-e1.md:20-21：WARM 只发历史 + assistant + 短 delta ~7-33 token）。
   - gate2_load.py 是 **agentic chain 写入 + restore**（3090-dev/gate2_load.py:54-86），但 prompt 规模在本侦察的源内未见 50-80K 单 request（conc-sweep 用 16 固定 prompt + gen_load）。
   - **差距**：现有 50-80K 负载是"单 session 长历史 warm 模型"；**4/6/8 subagent × 每 agent 50-80K context 同时活跃的 capacity-curve（实验③）无现成直接驱动**——需把 warmctx 的长历史 shape 与 gate2_load 的多 subagent 并发形状组合。**不实现**，仅报差距。
3. 有效载荷上限：`max_total_tokens` 可显式给定（server_args.py:743-756），128K 档已证可到 ~196608。**无代码层面 50-80K 阻塞**；24G 单并发置信（warmctx-e1.md:53-54：128K 档 mem_fraction 0.92 boot avail 5.21G）。多 subagent 并发时每 request 50-80K 需按 pool 核算（Q2/Q6）。

### Q5 parked-session 机制现状

1. 两类 "parked" 语义需区分：
   - **(a) 全局引擎暂停** `PauseGenerationReqInput`（io_struct.py:1727-1746，mode 有 abort/retract/in_place），`continue_generation`（1749-1755）。HTTP 入口存在：`SRT/entrypoints/http_server.py:1688-1709`（`POST /pause_generation` / `POST /continue_generation`）。**它暂停整个引擎**（scheduler.py:6251-6253 `self._engine_paused = True`），**不是逐 session park** —— 对"100/500/1000 parked session 各自 park/wake"不适用。
   - **(b) request 级 WAIT_CAPACITY park**（实验④ 意图）：scheduler 的 restore/wake 机制：
     - `scheduler.py:3133-3166` M2 frontier-ACK 唤醒（T12），`RestoreState.WAIT_CAPACITY` / `RestoreWaitReason.BACKUP_PENDING`。
     - `scheduler.py:1418-1425` `_ready_horizon_negatives`（rid 因果负缓存 park）。
     - `scheduler.py:1402-1411` NO_HEADROOM 订阅 + `_ready_host_release_epoch` release 计数（capacity wake）。
     - `scheduler.py:3168-3184` M1 WAIT timeout（T13）与 per-pass capacity wake（T11）。
   - **这是 scheduler 内部状态机；"parked session" 是失 headroom/缺 capacity 时 request 停在 waiting_queue，靠 T11/T12/M2 事件唤醒恢复（resume/recompute/restore）。**
2. 可否从外部以 100/500/1000 parked + 随机 wakeup 驱动：
   - **现有 harness 不覆盖**规模化 parked 驱动：
     - `3090-dev/test_hicache_restore_scheduler_feed.py`（feed 测试）是**状态机单测**（scheduler.__new__ + SimpleNamespace tree_cache，head 40 行），覆盖 BACKUP_PENDING 唤醒映射，**非** 100-1000 session 驱动。
     - `gate2_load.py`（3090-dev/gate2_load.py:1-289）是多 subagent 注入，但**无显式 pause/park/wake 编排**；靠 LRU eviction 制造池满，无"随机 wakeup"。
   - 驱动入口缺：要人为制造 500/1000 个 request 停在 WAIT_CAPACITY 再随机唤醒，需要主动制造 headroom 缺口 + 事件触发（prefetch/frontier）。**现无现成 harness；需造**（不实现，仅报缺口）。HTTP 层无 per-session park 端点（pause_generation 是全局引擎级）。

### Q6 ②③④ 相互约束 / 抉择点

1. **同一批 cache 吗？**
   - ② 的 400-480K "active KV" = 注意力 KV pool（`kv_used`）+ mamba state（`mamba_used`）**两块**。
   - ④ 的 Host/L3 residency：`hicache_kv_host_usable_tokens` + `hicache_mamba_host_usable_tokens`（metrics_collector.py:721-733）→ **KV 与 mamba 各有独立的 Host pool**。
   - **不完全是同一批**：② 关注 device 上 active KV/mamba 容量；④ 关注 Host（L3）residency。二者通过 `total_rest_memory` / extent / ready-horizon 联动。
2. **FP8 只作用 attention KV** ⇒ 抉择点：
   - **② 用 FP8 提升的是 attention KV active-token 上限；mamba state 不因 `kv_cache_dtype=fp8_e4m3` 获益**（mamba_ssm_dtype 无 fp8，mamba_checkpoint_pool 用 int8 非 fp8）。若 ② 的 400-480K 目标依赖 mamba state 容量，FP8 只能间接（total_rest_memory 增大）影响 mamba budget，不能直接压缩 mamba state。
   - 但 `--enable-int8-mamba-checkpoint`（server_args.py:2664-2668）+ `--mamba-ssm-dtype bfloat16`（:2607）是 mamba 侧可选的压缩途径（注释建议：`halve the state size with --mamba-ssm-dtype bfloat16`，kv_cache_configurator.py:1946）。
3. **③（多 subagent × 50-80K）与 ②（ratio sweep 找 400-480K）的抉择**：
   - ③ 的并发突增会使注意力 KV + mamba state 同时涨；ratio sweep 只在固定负载下稳定 400-480K。**③ 需在 ② 定好的 ratio/pool 基础上验证 capacity-curve**，二者顺序依赖：② 先定配置，③ 在同一匹配上跑。
   - ③ 的 50-80K 每 request 长 context + ④ 的 100-1000 parked session 会叠加在 pool 上（每 request 一个 mamba state slot）；**pool64 是 decode 推荐，但高并发/多 session 场景 pool 需按 ④ 场景重核算**（conc-sweep-e1.md:115：pool64+c8=596-606 tok/s 是 c8 单卡推荐，pool96 需 +1.5GB）。
4. **未决（清单，见 open_issues）**：FP8 在 3090 真卡行为、required total_active_kv 口径裁决、parked 驱动 shape、多 subagent 50-80K 并发负荷核算。

---

## summary

**核心事实（可直接支撑实验设计）：**

1. **FP8 KV 只压缩 attention KV，不碰 mamba state**。`kv_cache_dtype=fp8_e4m3`（server_args.py:636-662, kv_cache_dtype.py:53-57）作用于全注意力层 KV cell（pool_configurator.py:152-160,244-253）；mamba SSM state 用 `mamba_ssm_dtype`（bf16/float16/float32，无 fp8，server_args.py:2607-2614），缓存 state 用 int8（mamba_checkpoint_pool.py:31-34）。所以 ② 的 "FP8 KV + 400-480K active KV" 中，FP8 只提高注意力 KV pool 的 token 上限；mamba state 容量靠 ratio/显式 max_mamba_cache_size（或 bf16 选项）另定。**无 SM80/3090 arch 禁用 fp8 的源码注释**，只要求 CUDA 11.8+；真卡数值行为待实测。
2. **sweep knob 准确名 = `--mamba-full-memory-ratio`，float 默认 0.9**（server_args.py:2633-2640），单位比率；计算式 `mamba_budget = total_rest_memory*ratio/(1+ratio)`（kv_cache_configurator.py:2126）；`--max-mamba-cache-size`（slot 单位）设置后则绕过 ratio 路径（:2075-2081）。No single "total active KV" 量——注意力 KV token 与 mamba slot 分两处核算。
3. **观测口径现成**：`sglang:kv_used_tokens` + `sglang:mamba_used_tokens`（各有 available/evictable）+ `sglang:max_total_num_tokens`、Host 侧 `hicache_kv_host_usable_tokens` / `hicache_mamba_host_usable_tokens`（metrics_collector.py:360-419,655-733,1441-1450）。**num_used_tokens 不含 mamba pool**（pool_stats_observer.py:53-62）；判定 ② 的 400-480K 需 kv_used + mamba_used 聚合。
4. **50-80K 长 context 负载已存在**：gate2_warmctx 已跑 64K=64030 / 128K=128155 token（warmctx-e1.md:29-31）；差距在"4/6/8 subagent 各 50-80K 同时活跃的 capacity-curve"无现成驱动（需把长历史 shape 与多并发组合）。
5. **parked-session 有 scheduler 内部机制（WAIT_CAPACITY + T11/T12/M2 wake），但无规模化驱动**。HTTP `/pause_generation` 是全局引擎暂停（http_server.py:1688-1709, scheduler.py:6251），非 per-session；现有 harness（test_hicache_restore_scheduler_feed 为单测、gate2_load 无 park/wake 编排）不覆盖 100-1000 parked + 随机 wakeup。
6. **②③④ 联动**：FP8 只增益注意 KV ⇒ ② 的 mamba 目标需 ratio/bf16/int8 侧解决；③ 依赖 ② 定好的配置；④ 的 Host residency 与 ② 的 device active KV 分两池（各有 Host pool），通过 total_rest_memory/extent 联动，布局时注意 pool64 是 c8 推荐、多 session 场景 pool 需重核算。

## followups
- ② 设计时先裁决 "400-480K total active KV" 的口径（= kv_used + mamba_used？还是仅注意 KV？），再定 ratio sweep 的游标。
- ③ 的 capacity-curve 需在 ② 定稿配置上构造 4/6/8 subagent × 50-80K 负荷（造驱动，但不在本次侦察范围实现）。
- ④ 若走 scheduler WAIT_CAPACITY park 语义，需造"制造 headroom 缺口 + 随机 wakeup"的驱动 harness（现状无）。

## open_issues
1. **待实测**：FP8_e4m3 KV 在 3090(SM80) 真卡 + triton/线性注意 kernel 的数值行为与正确性（源码无 arch 禁用，但需真卡确认）。
2. **待实测**：FP8 后 3090 上 attention KV token 容量与 mamba budget 的实际再分配（`total_rest_memory` 增大对 mamba 的间接增益量）。
3. **待裁决**：② 的 "400-480K total active KV" 口径（单池 or kv_used+mamba_used 聚合），决定观测游标与 sweep 判据。
4. **待造**：③ 多 subagent×50-80K 并发能力曲线驱动（长历史 shape × 并发编排组合）。
5. **待造**：④ 100/500/1000 parked session + 随机 wakeup 驱动（现 harness 只覆盖 scheduler 状态机单测 + 无 park/wake 编排的注入）。
6. **设计抉择**：mamba state 容量在 ② 中走 ratio 自动 fit 还是显式 `--max-mamba-cache-size`（二选一，server_args 路径不同，需在实验布局时择一）。
7. **设计抉择**：pool64 是 c8 decode 推荐（conc-sweep-e1.md:115）；③④ 的高并发/多 session 场景 pool 是否加大（每 request 一个 mamba slot + 注意 KV 叠加），需核算。