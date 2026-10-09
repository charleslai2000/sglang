# phase2-hicache-design-doc-writer-scorecard-spec-e1

- **工作标题：** phase2-hicache-design-doc-writer-scorecard-spec-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-doc-writer-scorecard-spec-e1.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-doc-writer-scorecard-spec-e1.md`：**
写了一份 Phase-2 业务 Scorecard 指标定义与测试规范文档，把用户 8 个业务问题映射为「指标名 + 定义/计算式 + 测试方法 + 数据源 + 当前状态 + 目标/期望」总表。文档落实口径铁律：禁止 event count 冒充性能（cache/restore 一律 token 量、decode TPS 一律 metrics delta）；GPU-Util 100% ≠ 算满（bound 必须 SM/Tensor/DRAM/Power）；ttft=wall=E2E 沿用基线 §3.3（warm-turn 改用 stream:true 取真 TTFT）；不可测项按 NOT MEASURABLE + 缺字段如实标注。测试方法给出 6 项（T1 并发扫描 / T2 decode 基准 / T3 warm-turn / T4 parked sessions / T5 bound profiler / T6 soak 稳定性），每项含驱动/wrapper/profiler、跑多久、怎么算，均引用真实产物（gen_load.py、direct-launch-hicap.sh、gate2_warmctx.py、gate3_soak.sh、nvidia-smi dmon GPM、pucvt）。状态列如实：基线冻结值标「已冻结」，其余「待测 / 进行中」，实验①②③ 结果后续回填。风格对齐 gpu/ 归档（表格密集、结论先行、中文）。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-doc-writer-scorecard-spec-e1.md`：- `/home/charles/Workspaces/homenet/server/gpu/3090-dev/phase2-scorecard-spec.md` — Phase-2 业务 Scorecard 指标定义与测试规范（新增）
- `/home/charles/Workspaces/homenet/server/gpu/3090-dev/README.md` — §3 目录内容索引表追加一行登记 `phase2-scorecard-spec.md`（不重构 README，仅追加）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-doc-writer-scorecard-spec-e1.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-doc-writer-scorecard-spec-e1.md`; SHA256 `a62dbb3efa650b8db10b2e9c8677995ba47d2cf5bfc01a68c4f0cd1722a7b813`; source state `tracked`
