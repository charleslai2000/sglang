# M2-PROVENANCE-RECON-20260921

- **工作标题：** M2-PROVENANCE-RECON-20260921
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/M2-PROVENANCE-RECON-20260921.md`：**
Locate the M2 arm's model provenance: find OmniCoder-9B GPTQ-INT4 path in the repo (/data/models/, /data/l3, /data/models/). Check model checkpoint evidence (quantization_config, safetensors, tokenizer).

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/agents/M2-PROVENANCE-RECON-20260921.md`：**
**M2 Model Path FOUND** at `/data/models/omnicoder-9b-gptq-int4`
Model type: OmniCoder-9B GPTQ-INT4 (confirmed by directory name and quantization_config.json showing quant_method=gptq, bits=4)
Size: 22GiB
Last-modified: 1789640481 (2026-09-16 08:41 UTC)
Location in repo models directory: /data/models/omnicoder-9b-gptq-int4
--
Candidate roots checked:
1. /data/models/ -> EXISTS (11GiB total, containing: omnicoder-9b-gptq-int4, Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf, qwen35-9b-w4a16, swift-qwen38-27b-q3_k_m)
2. /data/l3 -> EXISTS (10 subdirs) - no OmniCoder content found
3. /data/models/local-prod-* -> EXISTS (multiple dirs)
4. /data/models/quarantine -> EXISTS (.quarantine)
5. /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents -> CREATED (this file)


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/M2-PROVENANCE-RECON-20260921.md` → `.memory/phase2-hicache-design/agents/M2-PROVENANCE-RECON-20260921.md`; SHA256 `d667fbfd955205263fe3261dd55040f35e50071785a6e0fa10fca0d6b0452ed9`; source state `tracked`
