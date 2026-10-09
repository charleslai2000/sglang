# T3060-AWQ-RUNTIME-AUDIT-20260910

- **工作标题：** TEST3060-AWQ-RUNTIME-AUDIT-20260910
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/TEST3060-AWQ-RUNTIME-AUDIT-20260910.md`：**
entry: ACCEPT
task_id: T3060-AWQ-RUNTIME-AUDIT-20260910
invocation_id: INV-20260910-TEST-AWQ-RUNTIME-AUDIT-R1
orchestration_epoch: 20260910-awq-runtime-audit
role: tester
capability_level: L3

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/TEST3060-AWQ-RUNTIME-AUDIT-20260910.md`：**
The remote service was healthy at the final check. PID `140507` is the service process
and owns listener `127.0.0.1:30000`; `/health` returned HTTP 200 at
`2026-09-10T02:55:27+08:00`.
The running checkpoint/backend evidence is:
- Checkpoint path: `/hy-tmp/models/Qwen3.5-4B-AWQ`.
- Model metadata: `Qwen3_5ForConditionalGeneration`, `model_type=qwen3_5`.
- Checkpoint config: `quant_method=compressed-tensors`, `format=pack-quantized`,
  `quantization_status=compressed`, INT4 group size 128, symmetric W4A16.
- `recipe.yaml` directly identifies `AWQModifier` and `QuantizationModifier` with
  `scheme: W4A16`; the model README identifies it as AWQ 4-bit in compressed-tensors
  format.
- SGLang startup directly reports `quant=compressed-tensors`.
- Marlin is proven for this startup: the log directly says
  `You are running Marlin kernel with bf16 on GPUs before SM90.` This is not an inference


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/TEST3060-AWQ-RUNTIME-AUDIT-20260910.md` → `.memory/phase2-hicache-design/work/TEST3060-AWQ-RUNTIME-AUDIT-20260910.md`; SHA256 `42ad147e1b03aaf7ec82f14229bfc2113d23bd8fbfa1372ac8ae170cbbe3cc4c`; source state `tracked`
