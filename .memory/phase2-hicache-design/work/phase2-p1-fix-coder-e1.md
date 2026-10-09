# P1 restore eligibility / admission re-arm churn — 实现 + unit 验证

- status: done
- epoch: e1
- owner: coder
- task: 实现 P1 修复（restore eligibility / admission re-arm churn），unit 验证
- 仓库: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt`（分支 3090-24g-opt）
- 本地 commit: `74246bb90f`（未 push，符合约束）
- 基线: cc718c3c2e（含 P0 修复）

## 方案选择：A（粘性 MISS_RECOMPUTE 状态），不用 B（miss_epoch 字段）

理由：architect §4.3 也倾向 A。把"不可 re-arm"显式做进状态机，T6 分支只读状态 +
epoch 门布尔即可，与 Fix B 的计数启发式彻底解耦；B 会把"不可 re-arm"散在调度器分支。
实现代价低（新增 1 个状态 + 1 个纯函数 + Req 两字段），已按要求选 A。

## 精确修改点

1. `python/sglang/srt/managers/scheduler_components/hicache_restore.py`
   - `RestoreState` 新增 `MISS_RECOMPUTE`（粘性 miss 状态）。
   - `next_restore` 新增 `rearm_allowed: bool = True` kwarg；T6 ADMISSION_DENY 分支：
     `state is MISS_RECOMPUTE and not rearm_allowed` → 保持 MISS_RECOMPUTE /
     NONE 决策（不 re-arm，recompute forward）；否则原 WAIT[DEVICE_QUOTA]。
   - T9 REVOKED_MISS genuine_miss → `(MISS_RECOMPUTE, ADMIT_RECOMPUTE)`（不再塌缩回 NONE）。
   - 新增纯函数 `miss_rearm_allowed(miss_epoch, current_epoch, miss_generation,
     current_generation)`：epoch 前移 或 generation 变 → True（可 re-arm）；
     否则 False（同一 probe 必再 miss，churn）。

2. `python/sglang/srt/managers/schedule_batch.py`（Req 字段）
   - 新增 `hicache_restore_miss_epoch: Optional[int]` 与
     `hicache_restore_miss_generation: Optional[int]`（负证据：probe 时 l3_publish
     epoch + session generation）。

3. `python/sglang/srt/managers/scheduler.py`
   - import `miss_rearm_allowed`。
   - `_feed_restore_terminal`：REVOKED_MISS genuine_miss 时记录
     `req.hicache_restore_miss_epoch = tree_cache.l3_publish_epoch()` 与
     `req.hicache_restore_miss_generation = req.session_generation`。
   - `_apply_restore_event`：新增 `rearm_allowed` kwarg 并转发 `next_restore`；
     `next_state is not MISS_RECOMPUTE` 时清空两负证据字段（离开粘性态即作废 miss）。
   - T6 分支（scheduler.py:4554-4573）：计算 `miss_rearm = miss_rearm_allowed(...)`，
     仅 `not device_quota_degraded(timeouts)`（Fix B 保留）时
     `_apply_restore_event(ADMISSION_DENY, rearm_allowed=miss_rearm)`。
     状态机内若 sticky 且 epoch 未前移则 no-op（不 WAIT）→ 请求走 forward recompute。

4. `python/sglang/srt/managers/scheduler_components/ready_horizon.py`
   - `_state_funnel`：MISS_RECOMPUTE 视同 NONE（staging_eligible）。ready horizon 自己的
     NO_L3 negative cache（按 l3_publish cursor）是权威 retry 门，epoch 前移清 park 后
     的重探正是 P1 合法 re-arm，粘性态本身不得拦。

## T6 三态分流实现

- **场景 A（本 episode 已 definitive miss + pool 满）→ P1**：状态 = MISS_RECOMPUTE，
  `miss_rearm_allowed` 为 False（epoch 未前移且 generation 同）→ T6 状态机 no-op 不
  re-arm，请求在容量释放时按普通 recompute admit（forward path）。
- **场景 B（device-hit / 有效物材 + 纯容量）→ Fix A**：状态不是 MISS_RECOMPUTE
  （未 miss 或 epoch/generation 已前移）→ `miss_rearm_allowed` True → T6 照常
  re-arm WAIT[DEVICE_QUOTA]，等容量 release（Fix A 的容量 epoch 唤醒）。未被 P1 门误伤。
- **场景 C（host staging / frontier / backup 瞬态）**：保持 retryable 现行为
  （PREFETCH_BUDGET / FRONTIER / BACKUP_PENDING 等 wait reason 不经过此 miss 门）。

## 必补 unit/state-machine 测试结果

新增/更新于 `3090-dev/test_hicache_restore.py`（纯状态机）与
`3090-dev/test_hicache_restore_scheduler_feed.py`（调度器接线）：

- sticky 状态 T6 不被 re-arm（`rearm_allowed=False` 保持 MISS，NONE 决策）；override
  （`rearm_allowed=True`）→ WAIT[DEVICE_QUOTA]。
- 健康链 restore_success 天然离开 MISS（MISS→override→WAIT→CAPACITY_FITS→RESTORING→
  FINALIZED→READY）。
- `miss_rearm_allowed` 矩阵：无 epoch（可）、同 epoch（不可）、epoch 前移（可）、
  generation 变（可）、generation None 仅 epoch 生效、repeated invocation 幂等。
- 调度器接线：genuine_miss 记录 epoch+generation；同 epoch+同 generation 不 re-arm；
  epoch 前移 / generation 变 re-arm；forward READY 清负证据；repeated 幂等不误 promotion。
- 更新既有 4 个 T9 测试（NONE → MISS_RECOMPUTE 语义）。

`PYTHONPATH=<repo>/python /home/charles/sglang-venv/bin/python -m pytest <file>`：
- test_hicache_restore.py: 84 passed
- test_hicache_restore_scheduler_feed.py: 13 passed（+6 新增）
- test_ready_horizon_unit.py / _partition.py: 78 passed
- 其余相关（prefetch_budget_split / writeback_reserve / capacity_model /
  fbe_flush_before_evict / storage_regression / backup_spec_assert_fix）: 全绿
- 合计 337 passed。

注：`test_drain_reentry.py` 5 个失败为**基线既有**（`_FakeTreeCore` 缺
`get_component_deviation`，git stash 到 cc718c3c2e 干净基线同样失败），与本次改动无关。

## 与 Fix A / Fix B / P0 正交性

- **Fix A**（容量 release epoch，ready_horizon host_release）：正交。P1 门=cache 证据
  epoch（l3_publish/generation），不创造设备容量；Fix A 门=容量 release。场景 B
  （device-hit + 纯容量）不被 P1 miss 门误伤，仍可 re-arm 等容量。
- **Fix B**（DEVICE_QUOTA_MAX_TIMEOUTS / device_quota_degraded）：**保留未动**，作为
  历史证据（约束要求不 merge 不删除）。P1 以 epoch 门（结构性判据）叠加在其上，收编
  Fix B 的 episode 概念——按 (generation, l3_publish_epoch) 界定，而非 restore_success
  清 counter。二者并存互不冲突：Fix B 拦 timeout 累积，P1 拦 miss 驱动 re-arm。
- **P0**（build_backup_spec）：未触碰。
- 未触碰：P3 durable-frontier / filesystem GC / ABANDON commit。

## evidence
- commit: 74246bb90f（本地，未 push）
- 337 passed（相关 unit/state-machine 套件），5 个 drain_reentry 失败为基线既有
- 命令见上（pytest，各文件通过数）

## summary
选 A（粘性 MISS_RECOMPUTE 状态 + Req miss_epoch/miss_generation 负证据字段）。
T9 genuine miss → MISS_RECOMPUTE/ADMIT_RECOMPUTE（不再回 NONE）；T6 在 sticky 且
l3_publish_epoch 未前移 / generation 未变时不 re-arm，请求 forward recompute；
epoch 前移或 generation 变恢复资格。三态分流（miss / 纯容量 / 瞬态）由状态 + epoch 门
区分，device-hit 容量 re-arm 不被误伤。Fix B 保留为历史证据。与 Fix A/P0 正交。

## followups
- （不阻塞，tester）集成/系统级验证：生产病态负载下 churn 是否消除（WAIT→RESTORING→
  revoked:miss→ADMISSION_DENY→re-WAIT 不再出现）；l3_publish_epoch 在 churn 场景的
  静止性观测（architect open issue 1）。
- （不阻塞）Fix A/P1 联合验证：冻结 headroom + 无 release + miss churn 与
  容量 release + 有效物材两种场景分别验证，确认无互相掩盖。
- （不阻塞）`test_drain_reentry.py` 5 个基线既有失败（get_component_deviation）——
  独立于 P1，建议另行跟进。

## open_issues
- architect open issue 1：l3_publish_epoch 是否需 anchor 粒度（当前全局单调，
  无关链写回也可能 bump → miss 门可能放行过多 re-probe）。实现期未处理，证据依赖，
  交 tester 观测。
- architect open issue 3：session_generation bump 语义（何时身份变）需 cache 侧确认，
  避免把正常前缀演进误判为新身份放行过多。当前实现以 `getattr(req,"session_generation")`
  为准，与既有 RH 用法一致。
- architect open issue 5：MISS_RECOMPUTE 下 T13 不再 arm（无 WAIT 可超时）；forward
  recompute 前进保证依赖 admission 容量释放后 admit，无新饿死路径（unit 已验证
  override + forward READY 可离开 MISS）。系统级确认交 tester。
