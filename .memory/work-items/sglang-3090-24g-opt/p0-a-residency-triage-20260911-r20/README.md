# P0-A-RESIDENCY-TRIAGE-20260911-R20

- **工作标题：** P0-A-RESIDENCY-TRIAGE-20260911-R20
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P0-A-RESIDENCY-TRIAGE-20260911-R20.md`：**
artifacts:
- Triage report: `/home/dev-codex/workspaces/.memory/phase2-hicache-design/work/P0-A-RESIDENCY-TRIAGE-20260911-R20.md`
- Input transcript: `/tmp/p0a-r19-transcript.txt`
- R19 report: `/home/dev-codex/workspaces/.memory/phase2-hicache-design/work/P0-A-REMOTE-RERUN-20260911-R19.md`
evidence:
- R19 identifies exactly three failures in the full budget suite: `SpeculativeStagingNoEvictTests.test_demand_alloc_failure_still_evicts`, `SpeculativeStagingNoEvictTests.test_speculative_alloc_failure_never_evicts`, and `ReadyHorizonOffModeTests.test_off_alloc_failure_evicts_like_baseline` (R19 report lines 11-13; transcript lines 179-182).
- All three fail in the common helper path `_drain_one_hit` at `3090-dev/test_prefetch_budget_split_unit.py:437` in the supplied transcript, while calling `UnifiedRadixCache._drain_storage_control_queues_impl`; the common exception is `AttributeError: 'UnifiedRadixCache' object has no attribute '_t38c_residency_queue_blocked'` (transcript lines 41-80, 81-121, 122-169).
- The failing production call is `_t38c_residency_release_queues_drained(self)` at `python/sglang/srt/mem_cache/unified_radix_cache.py:7264`; its implementation reads a pending set and then unconditionally calls `cache._t38c_residency_queue_blocked.difference_update(pending)` (source lines 506-516 in the R19-matching `sglang-3090-24g-opt` checkout).

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-A-RESIDENCY-TRIAGE-20260911-R20.md` → `.memory/rh-p0a-budget-residency/P0-A-RESIDENCY-TRIAGE-20260911-R20.md`; SHA256 `2c906ab537f3dae5eb12e441bbe1a11b96fd219e55ddb02f14b9febc6557db79`; source state `tracked`
