# CODE-20260909-ALLOC-FAILED-TERMINAL

- **工作标题：** CODE-20260909-ALLOC-FAILED-TERMINAL
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/CODE-20260909-ALLOC-FAILED-TERMINAL.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/CODE-20260909-ALLOC-FAILED-TERMINAL.md`：**
`Scheduler._feed_restore_terminal` now maps the drain terminal
`revoked_alloc_failed` explicitly to `RestoreEvent.DENIED_ALLOC` with
`genuine_miss=False`. The existing transition therefore enters
`WAIT_CAPACITY` with `RestoreWaitReason.HOST_ALLOC`; it does not arm sticky
miss evidence or trigger full-history recompute. Real `revoked_miss` continues
to use `RestoreEvent.REVOKED_MISS` with genuine-miss semantics.
The focused scheduler-feed regression now also asserts that miss epoch,
anchor, and generation remain unset for the positive allocation-failure
terminal. Existing drain behavior continues to verify reservation release and
the `revoked_alloc_failed` terminal classification.

### 报告列出的产物/证据
- `phase2-hicache-design/work/CODE-20260909-ALLOC-FAILED-TERMINAL.md`：- `python/sglang/srt/managers/scheduler.py`
- `3090-dev/test_hicache_restore_scheduler_feed.py`
- Commit `1e6a82194e` (`fix(hicache): preserve positive hits on alloc failure`)
The requested crop guard and short-tail path were not modified. No 3090
checkout, remote host, storage data, or unrelated source was changed.

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `1e6a82194e`, `1e6a82194e7f5d071823e4abb68514c6d421e4b3`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/CODE-20260909-ALLOC-FAILED-TERMINAL.md` → `.memory/phase2-hicache-design/work/CODE-20260909-ALLOC-FAILED-TERMINAL.md`; SHA256 `de2b2fb2a22a29922fc450de5e506b7fdae39eaf43bb7cd19f686e41ba6f909b`; source state `tracked`
