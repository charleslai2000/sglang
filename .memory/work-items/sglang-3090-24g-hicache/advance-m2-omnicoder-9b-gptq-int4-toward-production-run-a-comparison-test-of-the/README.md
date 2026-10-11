# Advance M2 (OmniCoder-9B GPTQ-INT4) toward production; run a COMPARISON test of the two 9B models.

- **工作标题：** MLINE-M2-VS-M1-COMPARE-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/MLINE-M2-VS-M1-COMPARE-20260918.md`：**
- Read-only comparison of two running 9B arms (M1: qwen35-9b-w4a16 / M2: omnicoder-9b-gptq-int4)
- CPU-only evidence (no server restart, no GPU allocation)
- Deliver: an executable comparison protocol + M2 readiness assessment
---

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** BLOCKED; qwen35-9b-local

**`phase2-hicache-design/agents/MLINE-M2-VS-M1-COMPARE-20260918.md`：**
| Arm | On-Disk Path | On-Rank Model ID | Identity Verdict |
|:---|:---|:---|:---|
| **M1** | `/data/models/qwen35-9b-w4a16` | `qwen35-9b-local` | **IDENTITY MATCH** = Qwen3.5-9B W4A16 (PKD quantization).  |
| **M2** | `/data/models/omnicoder-9b-gptq-int4` | `omnicoder-9b-int4` | **NOT M1** = OAuth base `Qwen3_5ForConditionalGeneration`, but **different quant** (GPTQ=int4 vs W4A16). |
**Verdict:** `qwen35-9b-local` is **NOT** M1 unless it uniquely matches the known W4A16 PKD-leftover. The served model-id is `"qwen35-9b-local"`, but this is an alias—the true identity discriminator is the **container checksum and quant compression clazz**.
**Comparison Blocker:** M2 is not **OmniCoder-9B-GPTQ-INT4** from `open coder` repo; it is a `Qwen3_5ForConditionalGeneration` checkpoint (architecture mismatch with OmniCoder). Identity-cryptographic verification is impossible because checksum is **`STALE-SUPERSEDED`** and no external repo is pin-compatible. The available `config.json` asserts `"architectures": ["Qwen3_5ForConditionalGeneration"]`, which is **not** `OmniCoder-9B`.
---


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/MLINE-M2-VS-M1-COMPARE-20260918.md` → `.memory/phase2-hicache-design/agents/MLINE-M2-VS-M1-COMPARE-20260918.md`; SHA256 `a51997b4a56e664c25e9a5eef3738f957a628808423133605006dae362ed6304`; source state `tracked`
