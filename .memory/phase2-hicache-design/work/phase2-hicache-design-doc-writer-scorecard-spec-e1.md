# phase2-hicache-design-doc-writer-scorecard-spec-e1

## status
done

## artifacts
- `/home/charles/Workspaces/homenet/server/gpu/3090-dev/phase2-scorecard-spec.md` — Phase-2 业务 Scorecard 指标定义与测试规范（新增）
- `/home/charles/Workspaces/homenet/server/gpu/3090-dev/README.md` — §3 目录内容索引表追加一行登记 `phase2-scorecard-spec.md`（不重构 README，仅追加）

## evidence
交叉核对（全部只读，未改代码、未跑实验）：
- `phase2-decbm-baseline-report.md` — 冻结指标口径：TPOT≈conc/agg_tps（§3.2）、ttft=wall=E2E（§3.3）、GPU util 与 CPU-bound 降级措辞（§3.4）、冻结推荐 pool64+Graph ON+c8≈596 tok/s
- `.memory/phase2-hicache-design/work/phase2-hicache-design-tester-scorecard-e1.md` — 逐请求守恒校验（cache_reused+recompute=historical_prefix）、storage_hit 虚高说明、NOT MEASURABLE 清单、clean 窗 effective cache ratio ≈99.8%
- `.memory/phase2-hicache-design/work/phase2-hicache-design-devops-hicap-wrapper-e1.md` — `direct-launch-hicap.sh`（MAX_RUNNING_REQUESTS/CUDA_GRAPH_MAX_BS）、Mamba cap 106→21、graph capture bs=[1,2,4,8,12,16,21]
- `.memory/phase2-hicache-design/work/gate2_warmctx.py` — 长上下文 warm-turn driver 先例（COLD 建历史 / WARM 同 session 测真 TTFT，stream:true）
- `.memory/phase2-hicache-design/work/phase2-hicache-design-tester-gate2-s32-e1.md` — 32-slot 饱和先例（pool cap 机制、5 state slots/请求）
- gpu/README.md — 归档文档风格（`<平台>-<标识>.md` 命名、表格密集、结论先行）

## summary
写了一份 Phase-2 业务 Scorecard 指标定义与测试规范文档，把用户 8 个业务问题映射为「指标名 + 定义/计算式 + 测试方法 + 数据源 + 当前状态 + 目标/期望」总表。文档落实口径铁律：禁止 event count 冒充性能（cache/restore 一律 token 量、decode TPS 一律 metrics delta）；GPU-Util 100% ≠ 算满（bound 必须 SM/Tensor/DRAM/Power）；ttft=wall=E2E 沿用基线 §3.3（warm-turn 改用 stream:true 取真 TTFT）；不可测项按 NOT MEASURABLE + 缺字段如实标注。测试方法给出 6 项（T1 并发扫描 / T2 decode 基准 / T3 warm-turn / T4 parked sessions / T5 bound profiler / T6 soak 稳定性），每项含驱动/wrapper/profiler、跑多久、怎么算，均引用真实产物（gen_load.py、direct-launch-hicap.sh、gate2_warmctx.py、gate3_soak.sh、nvidia-smi dmon GPM、pucvt）。状态列如实：基线冻结值标「已冻结」，其余「待测 / 进行中」，实验①②③ 结果后续回填。风格对齐 gpu/ 归档（表格密集、结论先行、中文）。

## followups
1. 文件 `.memory/phase2-hicache-design/context.md` / `ledger.md` 若需登记本规范入口 → 属 context-manager 职责，已报告需求，doc-writer 未触碰
2. 阶段② 已确认的 NOT MEASURABLE 缺口（L3 字节占用 gauge、GC 精确丢失 token、correctness 字段）在 §0 清单与总表后列出，建议后续引擎侧补字段（tester-scorecard-e1 同建议）
3. Mamba cap 数值（32→6/64→12.8/96→19/106→21）来自派发指令与 wrapper 报告（106→21 实测），pool32/64/96 档 cap 值为机制推算，回填实验时以引擎日志 cap 消息为准核对

## open_issues
- 无阻塞。bound 类型（T5）与 parked sessions（T4）尚无现成证据，测试方法为规范定义，待实验①②③ 回填后再写结论。
