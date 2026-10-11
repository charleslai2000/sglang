# phase2-rhono-rootcause-architect-e1

- **工作标题：** phase2-rhono-rootcause-architect-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-rhono-rootcause-architect-e1.md`：**
- epoch: e1（本任务首份报告）
- 时间: 2026-09-05
- 任务: P1 主线 — 收敛 Ready Horizon（RH）剩余 bug 的代码级根因（三个硬矛盾）
- 类型: root-cause 收敛（只读分析；**禁止改代码**，本会话无任何代码/schema/依赖修改）
- 依据: Phase-2 已 CLOSED 机制不再重开；六个事后 fix 门（clean window RH 优势 / DEVICE_QUOTA 恢复 / restore_success+storage_hit 不冻结 / 首次回收不显著提前 / 正确性无回归 / 2h soak）

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-rhono-rootcause-architect-e1.md`：本报告正文（现状结论见 summary 节）。支撑工件：
- 分析对象代码（只读，路径见 evidence 节）：
  - `python/sglang/srt/managers/scheduler_components/ready_horizon.py`
  - `python/sglang/srt/managers/scheduler_components/hicache_restore.py`
  - `python/sglang/srt/managers/scheduler.py`
  - `python/sglang/srt/managers/cache_controller.py`
  - `python/sglang/srt/managers/schedule_policy.py`
  - `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py`
  - `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`
  - `python/sglang/srt/server_args.py` / `python/sglang/srt/environ.py`
- 证据报告（tester/scout/orchestrator 已产出，本报告引用）：…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-rhono-rootcause-architect-e1.md` → `.memory/phase2-hicache-design/work/phase2-rhono-rootcause-architect-e1.md`; SHA256 `d9bbe1b625c4e71c733d91fb762932a22d983db490561616c7b70bb89ad13707`; source state `tracked`
