# phase2-cap-scout-e1

- **工作标题：** phase2-cap-scout-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-cap-scout-e1.md`：**
- Agent: scout
- Epoch: 1
- Date: 2026-09-07
- Scope: 只读事实侦察（不实现/不测试/不改码/不加埋点），为 24052 后续实验②③④ 提供基线事实。
- Repo: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt` @ 3090-24g-opt @ 9c9e7b7c7c
- 检索范围：`python/sglang/srt/`（server_args.py / managers/scheduler.py / mem_cache/* / model_executor/pool_configurator.py / observability/metrics_collector.py）+ 3090-dev/ 测试 + `.memory/phase2-hicache-design/{context.md,ledger.md,work/*.md}`。
---

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-cap-scout-e1.md`：**
**核心事实（可直接支撑实验设计）：**
1. **FP8 KV 只压缩 attention KV，不碰 mamba state**。`kv_cache_dtype=fp8_e4m3`（server_args.py:636-662, kv_cache_dtype.py:53-57）作用于全注意力层 KV cell（pool_configurator.py:152-160,244-253）；mamba SSM state 用 `mamba_ssm_dtype`（bf16/float16/float32，无 fp8，server_args.py:2607-2614），缓存 state 用 int8（mamba_checkpoint_pool.py:31-34）。所以 ② 的 "FP8 KV + 400-480K active KV" 中，FP8 只提高注意力 KV pool 的 token 上限；mamba state 容量靠 ratio/显式 max_mamba_cache_size（或 bf16 选项）另定。**无 SM80/3090 arch 禁用 fp8 的源码注释**，只要求 CUDA 11.8+；真卡数值行为待实测。
2. **sweep knob 准确名 = `--mamba-full-memory-ratio`，float 默认 0.9**（server_args.py:2633-2640），单位比率；计算式 `mamba_budget = total_rest_memory*ratio/(1+ratio)`（kv_cache_configurator.py:2126）；`--max-mamba-cache-size`（slot 单位）设置后则绕过 ratio 路径（:2075-2081）。No single "total active KV" 量——注意力 KV token 与 mamba slot 分两处核算。
3. **观测口径现成**：`sglang:kv_used_tokens` + `sglang:mamba_used_tokens`（各有 available/evictable）+ `sglang:max_total_num_tokens`、Host 侧 `hicache_kv_host_usable_tokens` / `hicache_mamba_host_usable_tokens`（metrics_collector.py:360-419,655-733,1441-1450）。**num_used_tokens 不含 mamba pool**（pool_stats_observer.py:53-62）；判定 ② 的 400-480K 需 kv_used + mamba_used 聚合。
4. **50-80K 长 context 负载已存在**：gate2_warmctx 已跑 64K=64030 / 128K=128155 token（warmctx-e1.md:29-31）；差距在"4/6/8 subagent 各 50-80K 同时活跃的 capacity-curve"无现成驱动（需把长历史 shape 与多并发组合）。…（节选；见来源报告）

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-cap-scout-e1.md`：- 本报告：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-cap-scout-e1.md`
- 侦察结论表（见 summary 下逐项）。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-cap-scout-e1.md` → `.memory/phase2-hicache-design/work/phase2-cap-scout-e1.md`; SHA256 `73c8a5dc1009a23ceef37b2cf0ac32d31afa7c2febfb6111f4cef47ea8881ba7`; source state `tracked`
