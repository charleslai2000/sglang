# DEBUG3060-RH-READY-RELEASE-20260910

- **工作标题：** DEBUG3060-RH-READY-RELEASE-20260910
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/DEBUG3060-RH-READY-RELEASE-20260910.md`：**
- task_id: `TASK-20260910-RH-READY-RELEASE`
- invocation_id: `INV-20260910-DEBUG-RH-READY-RELEASE-R1`
- epoch: `20260910-r5`
- role/capability: `debugger-deep` / L2
- workdir: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- observed workspace root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` (`pwd` matched before reads)
- memory_root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design`
- memory_inputs: `HANDOFF-2026-09-10-RH-SPEC-BUDGET.md`, `DEBUG3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/DEBUG3060-RH-READY-RELEASE-20260910.md`：**
**No cache-mode release-timing patch is required.** In cache mode, the speculative reservation is already released at the cache material finalizer, before the terminal handoff that the scheduler consumes to set `RestoreState.READY`/emit `ready_host`, and therefore before admission. Releasing it at admission would be incorrect: it would retain a staging-only budget charge while the request is already usable in Host and prevent the causal `SPEC_BUDGET` wake for another queued request.
The exact cache-mode success release point is `UnifiedRadixCache._handle_prefetch_result` immediately after the host insert/transfer commit (or dropped-material cleanup) and anchor unlock, at `unified_radix_cache.py:5746`, before removing `ongoing_prefetch`, decrementing physical occupancy, and publishing terminal `finalized` at lines 5747-5752.
Workspace note: after the diagnosis probes, the worktree contained an uncommitted buffer-mode addition at `unified_radix_cache.py:5683-5695` which calls `release_prefetch(..., "finalize")` after `stage_completed_prefetch`, plus a test import. I did not create, modify, or revert those product changes. Under the current issue path, buffer mode does not call `reserve_prefetch` (`5508-5520`), so this added buffer-mode call is presently an idempotent no-op for speculative accounting. It neither explains nor fixes cache-mode `SPEC_BUDGET` behavior; its future-purpose semantics need ordinary implementation review.

### 报告列出的产物/证据
- `phase2-hicache-design/work/DEBUG3060-RH-READY-RELEASE-20260910.md`：- Source: `python/sglang/srt/mem_cache/unified_radix_cache.py:5106-5143`, `5508-5521`, `5690-5752`, `5921-5934`, `6165-6220`, `6303-6542`.
- Scheduler: `python/sglang/srt/managers/scheduler.py:3874-3992`, `6226-6301`.
- Buffer-mode contrast: `python/sglang/srt/mem_cache/buffer_mode/pipeline.py:696-750`, `771-950`.
- Existing regression: `3090-dev/test_prefetch_budget_split_unit.py:280-402`; retrigger tests at `3090-dev/test_ready_horizon_unit.py:1035-1097`.

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4f41f5bab5`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/DEBUG3060-RH-READY-RELEASE-20260910.md` → `.memory/phase2-hicache-design/work/DEBUG3060-RH-READY-RELEASE-20260910.md`; SHA256 `88460339a9b0567d48642e5cb3ae08bfae26eb006afa80e80c20a05b442ba03b`; source state `tracked`
