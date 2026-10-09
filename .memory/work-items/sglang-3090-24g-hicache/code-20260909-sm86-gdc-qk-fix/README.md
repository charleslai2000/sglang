# CODE-20260909-SM86-GDC-QK-FIX

- **工作标题：** CODE-20260909-SM86-GDC-QK-FIX
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/CODE-20260909-SM86-GDC-QK-FIX.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/CODE-20260909-SM86-GDC-QK-FIX.md`：**
Applied the existing AST-safe GDC shim/capability pattern to the Qwen3.5
fused QK RMSNorm/RoPE/gate Triton module. Missing GDC attributes are installed
as `@triton.jit` no-op shims before kernel compilation, while the capability
flag is captured as false when shims were needed. `_ENABLE_PDL` therefore stays
false on SM86 and retains real GDC dispatch when both real Triton intrinsics
and SM90+ architecture support are present.
The scoped execution-path scan found the same direct GDC references in the
Triton grouped decode kernels used by the Qwen3.5 full-attention backend.
`decode_attention.py` now installs the same AST-visible shims and clamps the
public `use_pdl` request through the capability guard. The MLA-only
`mla_kv_pack_quantize_fp8.py` site was reviewed and left unchanged because it
is not part of Qwen3.5's non-MLA attention path. Existing FLA and Mamba sites
were already guarded on this branch.


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `20fb45eb2a`, `7224d14629`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/CODE-20260909-SM86-GDC-QK-FIX.md` → `.memory/phase2-hicache-design/work/CODE-20260909-SM86-GDC-QK-FIX.md`; SHA256 `f70466ef9de1d7e18b95b9d2df33d1fc72378e9b4603fbf3c2fac2fecbae9df3`; source state `tracked`
