# COD-20260908-T38C-FIX

- **工作标题：** COD-20260908-T38C-FIX
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/COD-20260908-T38C-FIX.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/COD-20260908-T38C-FIX.md`：**
Implemented the minimal restore-frontier fix while retaining all-or-nothing
KV+sidecar semantics:
- The hybrid controller establishes the contiguous KV hit frontier first,
  truncates the sidecar query to that frontier, and materializes trailing
  sidecar keys from the actual historical hit window.
- Trailing-window size prefers the sidecar transfer's host-buffer page count,
  so appended request tokens cannot inflate a Mamba trailing query.
- Extent sidecar folding now evaluates each transfer against the current
  `final_pages` frontier, preserving intersection semantics across multiple
  sidecars.

### 报告列出的产物/证据
- `phase2-hicache-design/work/COD-20260908-T38C-FIX.md`：- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/COD-20260908-T38C-FIX.md` → `.memory/phase2-hicache-design/work/COD-20260908-T38C-FIX.md`; SHA256 `ce85c7e61e5848b26015bdb2025fc41e95ebd3562c012abeaace029993570a99`; source state `tracked`
