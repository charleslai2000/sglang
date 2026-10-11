# D3060-CODE-067

- **工作标题：** COD-20260908-3060-MINIMAL-KERNEL-FIX2
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/COD-20260908-3060-MINIMAL-KERNEL-FIX2.md`：**
ENTRY: ACCEPT
task_id: D3060-CODE-067
orchestration_epoch: 2026-09-08
role: coder
status: done
invocation_status: done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/COD-20260908-3060-MINIMAL-KERNEL-FIX2.md`：**
Closed the remaining minimal-SM86 registration gap. The `shuffle_rows` and
`apply_shuffle_mul_sum` schema/implementation registrations are now guarded by
`#ifndef SGL_KERNEL_MINIMAL_SM86`, matching their provider in
`csrc/moe/prepare_moe_input.cu`, which is removed from the source list when
minimal SM86 mode is enabled.

### 报告列出的产物/证据
- `phase2-hicache-design/work/COD-20260908-3060-MINIMAL-KERNEL-FIX2.md`：- Implementation commit: `a76cce39723654cb93ee186b9c3fb570961d7794`
- This report: `COD-20260908-3060-MINIMAL-KERNEL-FIX2.md`
Extra work requires a fresh Task ID.

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `a76cce39723654cb93ee186b9c3fb570961d7794`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/COD-20260908-3060-MINIMAL-KERNEL-FIX2.md` → `.memory/phase2-hicache-design/work/COD-20260908-3060-MINIMAL-KERNEL-FIX2.md`; SHA256 `82b562e849773282abdc1635f19a8d4c7a2fa13a6c6818c784bd6240c577c22f`; source state `tracked`
