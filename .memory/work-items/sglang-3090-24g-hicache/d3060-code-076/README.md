# D3060-CODE-076

- **工作标题：** COD-20260909-3060-SM86-ARCH
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/COD-20260909-3060-SM86-ARCH.md`：**
ENTRY: ACCEPT
task_id: D3060-CODE-076
orchestration_epoch: 2026-09-09
role: coder
status: done
invocation_status: done
branch: 3060-12g-qwen35-4b
commit: `3bed01ba51c1bd03a3f82ca1a444600f4177702`

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/COD-20260909-3060-SM86-ARCH.md`：**
Implemented the opt-in SM86-native minimal AOT path without changing the
default/OFF 3090 target or source set.
- Minimal mode now uses one `common_ops_sm86_build` target with explicit
  `-gencode=arch=compute_86,code=sm_86` and output/install path
  `sgl_kernel/sm86/common_ops*.so`.
- Minimal mode does not create the SM90/SM100 common targets and skips the
  SM90/SM100-oriented FA3, InfLLM-V2, and FlashMLA targets.
- The loader maps compute capability 86 to `sgl_kernel/sm86/common_ops.*`.
- The reviewed minimal source list and `common_extension.cc` registration
  guards were preserved, including W4A16, hybrid, and Mamba-relevant sources.


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `3bed01ba51c1bd03a3f82ca1a444600f4177702`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/COD-20260909-3060-SM86-ARCH.md` → `.memory/phase2-hicache-design/work/COD-20260909-3060-SM86-ARCH.md`; SHA256 `3dba7270131f49e35fe1feb4201ae6d8499033fb417cb5334aaad54205fc4876`; source state `tracked`
