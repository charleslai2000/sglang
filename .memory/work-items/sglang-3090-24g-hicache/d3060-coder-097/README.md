# D3060-CODER-097

- **工作标题：** CODE-20260909-SM86-GDC
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/CODE-20260909-SM86-GDC.md`：**
ENTRY: ACCEPT
task_id: D3060-CODER-097
orchestration_epoch: 2026-09-09
role: coder
branch: 3060-12g-qwen35-4b
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
status: done
invocation_status: done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/CODE-20260909-SM86-GDC.md`：**
Implemented the smallest scoped fallback for the Qwen3.5-4B GDN/Mamba Triton
decode chain. GDC is now enabled only when both conditions hold:
1. `is_arch_support_pdl()` reports a supported CUDA architecture (SM90+); and
2. the installed Triton exposes both `tl.extra.cuda.gdc_wait` and
   `tl.extra.cuda.gdc_launch_dependents`.
On RTX 3060/SM86, or with a Triton build lacking either intrinsic, the existing
ordinary Triton launch path is used. The GDC kernel bodies and the supported
architecture behavior were not changed.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/CODE-20260909-SM86-GDC.md` → `.memory/phase2-hicache-design/work/CODE-20260909-SM86-GDC.md`; SHA256 `265f806de652c92eb03bb2a43d908058c8d78c44351536aa3b4e512c574ca57a`; source state `tracked`
