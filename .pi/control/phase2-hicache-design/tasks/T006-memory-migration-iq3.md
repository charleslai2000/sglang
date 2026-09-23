# T006 — IQ3_S 审计与 parity 工具整理

Status: DONE
Work area: experiments / control
Objective: 保留 `.memory` 中实际可复用的 IQ3_S 审计、解码验证和 CUDA parity 工具，丢弃二进制 fixture 与输出 dump。
Inputs: `M3-IQ3S-FINAL-AUDIT-20260919`、`K1-PARITY-RESULT.md`、相关源码文件。
Completion: 结论进入控制记录，真正源码/工具迁入 canonical 3090 工具路径，原始大二进制不再作为源码权威。
Result:
- IQ3_S allocation audit：851 tensors，qtype census 与官方 allocation exact match；144 个 IQ3_S tensor、33,116,160 blocks，`d` 非有限值为 0，先前 row0 NaN 判断被完整布局审计 supersede。
- K1 parity：Q8_1 MMVQ fixture output `max_abs_error=4.7683716e-07`，容差内 mismatch=0/10240；结果仅证明 correctness recovery，不等于最终性能。
- 已提取到 `tools/iq3-audit/`：`audit_iq3s_allocation.py`、`k1_iq3s.cu`、`iq3s_recode_verify.py`。
- 删除判定：22.5MB packed fixture、activation/output `.bin`、RCO allocation copy、JSON/文本结果均为 evidence/raw output，不进入 source authority。
Remaining: IQ3_XXS/IQ4_XS/Q*_K mixed backend 仍需独立工作。
