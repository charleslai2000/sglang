# T005 — M3 Q3_K_M artifact与运行验证材料整理

Status: DONE
Work area: control / evidence synthesis
Objective: 从 `.memory` 提炼 Q3_K_M artifact 身份、类型分布、dispatch 证据、A/B runbook 与边界，不保留模型下载或虚拟环境。
Inputs: `M3-BASE-Q3KM-OFFLINE-VERIFY-20260919` 记录。
Completion: durable identity、hash、tensor census、dispatch结论、VRAM边界和未执行项进入正式控制记录。
Result:
- GGUF `Qwen3.8-27B-Q3_K_M.gguf`，大小 `13,500,736,896`，SHA256 `864049a910dc66b4861bad8f798c8c7caec3e73246a6c29e2083b363d6a15746`。
- 866 tensors：F32 360、Q3_K 358、Q4_K 141、Q5_K 6、Q6_K 1；无 IQ3_S/F16/BF16。
- architecture=`qwen35`，65 blocks，hidden=5120，context=262144；embedded chat-template hash 与冻结身份精确匹配。
- 当前源码已观察到 Q3_K 的 MMVQ/MMQ dispatch；实际 GPU A/B 尚未执行，loaded footprint 不作声称。
- 13.5GB GGUF、venv 和下载日志均判定为 runtime/generated artifact，不进入控制树。
Remaining: 若需 A/B，另建实验任务。
