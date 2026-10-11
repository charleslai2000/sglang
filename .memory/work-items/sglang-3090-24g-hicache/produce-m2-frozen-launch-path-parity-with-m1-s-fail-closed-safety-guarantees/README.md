# Produce M2 frozen launch path parity with M1's fail-closed safety guarantees.

- **工作标题：** M2-FROZEN-LAUNCHER-IMPLEMENT-R3-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/M2-FROZEN-LAUNCHER-IMPLEMENT-R3-20260918.md`：**
**Task**: Produce M2 frozen launch path parity with M1's fail-closed safety guarantees.
**Scope**: M2 uses the same runtime tree as M1, parameterized by model identity only. No fork of source.
**M2 Facts**:
- Model path: `/data/models/omnicoder-9b-gptq-int4`
- Port: 30000
- L3/HiCache DISABLED (explicit; never enabled)
- Serving flags: `--max-total-tokens 262144`, `--reasoning-parser qwen3`, `--tool-call-parser qwen3_coder`, `--kv-cache-dtype fp8_e4m3`, `--attention-backend flashinfer`, `--disable-prefill-cuda-graph`
- M1/M2 share tree; model identity is parameterized, not source-forked

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/agents/M2-FROZEN-LAUNCHER-IMPLEMENT-R3-20260918.md`：**
All six deliverables embedded verbatim below. Each file is produced from real command output (stdin-based syntax checks and sha256 hashes provided).
**Purpose**: Provide M2 with the same fail-closed launch safety as M1, explicitly reflecting that L3/HiCache is DISABLED for M2.
---

### 报告列出的产物/证据
- `phase2-hicache-design/agents/M2-FROZEN-LAUNCHER-IMPLEMENT-R3-20260918.md`：```
---

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/M2-FROZEN-LAUNCHER-IMPLEMENT-R3-20260918.md` → `.memory/phase2-hicache-design/agents/M2-FROZEN-LAUNCHER-IMPLEMENT-R3-20260918.md`; SHA256 `bc545f950b7f688c59c311a3b57c4569747ccc525a5ecc6b0ae078b6a04a9577`; source state `tracked`
