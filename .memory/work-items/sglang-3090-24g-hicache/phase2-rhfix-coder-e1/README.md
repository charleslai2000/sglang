# phase2-rhfix-coder-e1

- **工作标题：** phase2-rhfix-coder-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-rhfix-coder-e1.md`：**
> Implementer: coder agent, epoch 1
> Date: 2026-09-06
> Repo / branch / baseline: `sglang-3090-24g-opt` @ `3090-24g-opt`, from `fac8ccb4cf`
> (dispatch ruling: work in the existing opt worktree, main branch, no push, frozen baseline untouched)

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-rhfix-coder-e1.md`：**
- Fix A: speculative stage can no longer enter a permanent NO_HEADROOM freeze; the
  NO_HEADROOM waiter subscribes to the monotonic host_release epoch, wakes on genuine
  capacity-releasing events, is debounced by the safety fuse, and speculative staging
  still never evicts / never encroaches on working-set reserve (M2 headroom gate
  unchanged).
- Fix B: DEVICE_QUOTA waits are bounded per episode; after the cap, the admission
  re-arm is refused and the request takes the recompute forward path — the
  `WAIT → timeout → recompute → ADMISSION_DENY → WAIT` loop is broken without faking
  success on working-set exhaustion and without depending on thrash-invalidated L3.
- Telemetry: single-key `set()` is metered like all batch paths.
- Three independent commits with clear messages; no push; frozen baseline commits and
  the main-branch history before `036fb89451` untouched.

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-rhfix-coder-e1.md`：Commits (on top of `fac8ccb4cf`, frozen baseline untouched):
1. `036fb89451` — **telemetry hygiene** (1 file)
   - `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`: single-key
     `set()` now calls `_log_extent_write("kv", None, [storage_key], [value])` on success,
     matching `batch_set` / `batch_set_v1` / `batch_set_v2` (telemetry parity).
2. `e0e83b11a1` — **Fix A** (3 files)
   - `python/sglang/srt/managers/scheduler_components/ready_horizon.py`
   - `python/sglang/srt/managers/scheduler.py` (A-hunks only)
   - `3090-dev/test_ready_horizon_unit.py`
3. `3bca0989f4` — **Fix B** (4 files)
   - `python/sglang/srt/managers/scheduler_components/hicache_restore.py`…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-rhfix-coder-e1.md` → `.memory/phase2-hicache-design/work/phase2-rhfix-coder-e1.md`; SHA256 `08b075ffe172a87d6993428ffda6e2d97e4a063fde7cedd793d41fae4b87f4b8`; source state `tracked`
