# P0-B-LINEAGE-COMPLETE-20260911-R106b

- **工作标题：** P0-B-LINEAGE-COMPLETE-20260911-R106b
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
续做 R106 producer telemetry lineage wiring，闭合五项缺口：grant predecessor、terminal recording、统一 lifecycle_key、wake_event_id 传播、缺失/矛盾 predecessor fail-closed；并修正 re-park wait identity。

## 实际改了什么
R106b 指定本次唯一 source edit 为 `python/sglang/srt/managers/scheduler.py` 的 `_capture_host_alloc_wait`（每次 park 按新 FIFO sequence 生成 wait_id），新增 `3090-dev/test_host_alloc_lineage.py` 8 tests。telemetry_context、arbiter 及其他 producer wiring 在原文列为 invocation 前已存在，不归为本次新改；无 commit/push。

## 生成结果与验收
修复 stale wait_id 后 re-park `wait:1` 与 predecessor `wait:0` 不同。8 项 lineage、46 scheduler-feed、11 HOST_ALLOC、74 ready-horizon、92 restore state-machine 与 55 adjacent tests 均通过，另 py_compile 通过；black/ruff/mypy 不可用。代码在 target branch `3060-12g-qwen35-4b` @ `4f41f5bab5`（报告短 hash）。这证明本机 focused semantics，不是 live P0-B chain：live chain 与独立 review 未运行，11-predicate reducer 尚待真实事件 schema 冻结。遗留项包括未用 wait_event_id、re-park attempt_number 固定 0、host_allocability_change 无 lifecycle join，以及 durability event 使用 operation_id；均未在本次修复。

### 报告列出的产物/证据
- `phase2-hicache-design/work/P0-B-LINEAGE-COMPLETE-20260911-R106b.md`：- Report (this file):
  `.memory/phase2-hicache-design/work/P0-B-LINEAGE-COMPLETE-20260911-R106b.md`
- New tests: `3090-dev/test_host_alloc_lineage.py` (417 lines)
- Fixed source: `python/sglang/srt/managers/scheduler.py` (the only source edit
  made by this invocation; line range 3786-3791, replacing the previous
  `if wait_id is None:` guard)
Pre-existing (present before this invocation, verified not blindly trusted):
- `python/sglang/srt/mem_cache/telemetry_context.py` (new, 237 lines):
  producer identity + `next_event_id`/`producer_context`/`lifecycle_key` +
  bounded lineage registry (`record_host_alloc_lineage`,
  `host_alloc_lineage`, `host_alloc_lineage_fields`,…（节选；见来源报告）

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4f41f5bab5`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-B-LINEAGE-COMPLETE-20260911-R106b.md` → `.memory/rh-p0b-harness-durability/P0-B-LINEAGE-COMPLETE-20260911-R106b.md`; SHA256 `c44ff04a2f455b53e7097c570505e81d4af1180dfb3332cc272d91968cba9c96`; source state `tracked`
