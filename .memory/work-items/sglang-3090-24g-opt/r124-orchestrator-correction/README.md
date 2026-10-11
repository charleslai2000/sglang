# R124-ORCHESTRATOR-CORRECTION

- **工作标题：** R124-ORCHESTRATOR-CORRECTION
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/R124-bundle/R124-ORCHESTRATOR-CORRECTION.md`：**
sha256 `9c599adf…`) is **substantially wrong**. Bundles/checksums are valid
(`sha256sum -c` all OK); the EVIDENCE is good, the INTERPRETATION is not. Product
code unchanged; server untouched. All claims below are re-derived from
`work/R124-bundle/raw.log` and `probe.log` with line numbers.

## 实际改了什么
对 R124 frozen `raw.log`/`probe.log` 做只读独立重判，验证 bundle checksums；未改 product code、server 或 evidence bundle。

## 生成结果与验收
Orchestrator 指出原 tester interpretation **substantially wrong**，但原始证据本身有效。重判发现：L3 durable pipeline “broken” 被同 run F1 从 L3 restore 42,752 tokens 反证；T 确实 non-resident 且 SPEC_BUDGET park（C2 PASS），但先于 release epoch 被 admission/recompute，所以 T 无 prefetch/HOST_ALLOC/wake，C3/C4 仍失败。唯一 F1 HOST_ALLOC grant 时 KV/Mamba 两域都推进，wake fix 未 runtime-exercised。修正分类为 recipe/scheduling-race gap，不是 durability defect，也不授权 product change。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R124-bundle/R124-ORCHESTRATOR-CORRECTION.md` → `.memory/rh-p1-durable-replay-eviction/R124-bundle/R124-ORCHESTRATOR-CORRECTION.md`; SHA256 `c57905ffbb0338a86fc5e91fc47add9023ce5c29a3228beb36a52abacd413cd2`; source state `tracked`
