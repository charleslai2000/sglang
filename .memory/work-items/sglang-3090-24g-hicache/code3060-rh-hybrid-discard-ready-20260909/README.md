# CODE3060-RH-HYBRID-DISCARD-READY-20260909

- **工作标题：** CODE3060-RH-HYBRID-DISCARD-READY-20260909
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/CODE3060-RH-HYBRID-DISCARD-READY-20260909.md`：**
ENTRY: ACCEPT
status: done
task_id: CODE3060-RH-HYBRID-DISCARD-READY-20260909
orchestration_epoch: 20260909-rh-ab29
role: coder
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
base_revision: 6881529acbb55c9dc55745d08fca62b585ecdbad

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/CODE3060-RH-HYBRID-DISCARD-READY-20260909.md`：**
The scheduler now consumes the finalizer-owned `finalize_result` before applying
the terminal event. `accepted` retains `FINALIZED -> READY` and emits
`rh_ready_host.v1`. `discarded` and `rejected` retain the terminal handoff but
use the recompute transition (`DENIED_SHORT` with `short_tail_recompute=True`),
leaving the request in `NONE` and suppressing ready-host emission. The hybrid
discard telemetry now records `restore_state_after=NONE`. Mamba and
all-or-nothing finalizer behavior remain unchanged.

### 报告列出的产物/证据
- `phase2-hicache-design/work/CODE3060-RH-HYBRID-DISCARD-READY-20260909.md`：- Commit `67b39b5aca` — `fix(hicache): reject discarded hybrid readiness`.
- Required report: this file.
- Source result path: `Scheduler._feed_restore_terminal` in
  `python/sglang/srt/managers/scheduler.py:3765`.
- Finalizer result path: `UnifiedRadixCache._handle_prefetch_result` and
  `_check_hybrid_prefetch_result` in
  `python/sglang/srt/mem_cache/unified_radix_cache.py:5576` and `:5832`.

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `67b39b5aca`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/CODE3060-RH-HYBRID-DISCARD-READY-20260909.md` → `.memory/phase2-hicache-design/work/CODE3060-RH-HYBRID-DISCARD-READY-20260909.md`; SHA256 `fac5927d7af2997a45c3b00a5d681f96df12fe31ddb016f1c2c6f6873b6bfeba`; source state `tracked`
