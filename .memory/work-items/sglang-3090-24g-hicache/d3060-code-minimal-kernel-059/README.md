# D3060-CODE-MINIMAL-KERNEL-059

- **工作标题：** COD-20260908-3060-MINIMAL-KERNEL
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/COD-20260908-3060-MINIMAL-KERNEL.md`：**
ENTRY: ACCEPT
status: done
invocation_status: done
task_id: D3060-CODE-MINIMAL-KERNEL-059
orchestration_epoch: 20260908-3060
role: coder

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/COD-20260908-3060-MINIMAL-KERNEL.md`：**
Added `SGL_KERNEL_MINIMAL_SM86`, default `OFF`, at `CMakeLists.txt:181`. When enabled,
the option applies `list(REMOVE_ITEM SOURCES ...)` after the unchanged 50-entry default
source list. The filter removes only MLA/sparse-attention, expert-specialization, and
MoE paths. Common extension, basic attention merge, activation/norm/copy/position/topk,
AWQ/GPTQ/generic quantization, kvcacheio transfer, Mamba, grammar, speculative sampling,
and the other default common sources remain available.
The FA3 and FlashMLA sections were not modified. With the option `OFF` (the default),
the `SOURCES` list is unchanged, so the 3090 behavior is preserved.

### 报告列出的产物/证据
- `phase2-hicache-design/work/COD-20260908-3060-MINIMAL-KERNEL.md`：- Repository: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- Branch: `3060-12g-qwen35-4b`
- Changed file: `python/sglang/kernels/aot/CMakeLists.txt`
- Commit: `4e1e7cfeb5ea35751338f821b8e27809b26b5ef5`
- Commit subject: `build: add minimal SM86 kernel source option`
- Worktree after commit: clean; branch remains `3060-12g-qwen35-4b`

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4e1e7cfeb5ea35751338f821b8e27809b26b5ef5`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/COD-20260908-3060-MINIMAL-KERNEL.md` → `.memory/phase2-hicache-design/work/COD-20260908-3060-MINIMAL-KERNEL.md`; SHA256 `aff8e828f003fa19aa570fc9263efab3d26015feeb6a2ec27bdb8718adbc83d0`; source state `tracked`
