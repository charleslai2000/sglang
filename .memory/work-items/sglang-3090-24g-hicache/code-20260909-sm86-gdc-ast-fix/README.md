# CODE-20260909-SM86-GDC-AST-FIX

- **工作标题：** CODE-20260909-SM86-GDC-AST-FIX
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/CODE-20260909-SM86-GDC-AST-FIX.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/CODE-20260909-SM86-GDC-AST-FIX.md`：**
Installed missing `tl.extra.cuda.gdc_wait` and
`tl.extra.cuda.gdc_launch_dependents` as `@triton.jit` no-op shims before the
affected kernels are compiled. The dispatch flag is captured before shim
installation, so a missing Triton API cannot enable GDC. Existing real
intrinsics are not replaced. The same guard now covers the exact
`layernorm_gated.py` failure path, the adjacent FLA verify/recurrent paths,
causal conv, and Mamba SSM.


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `20fb45eb2a`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/CODE-20260909-SM86-GDC-AST-FIX.md` → `.memory/phase2-hicache-design/work/CODE-20260909-SM86-GDC-AST-FIX.md`; SHA256 `7e35c38faa62b6eb7d7eea08949c18ef23c2233ba7a9470807b0b5bc3243c803`; source state `tracked`
