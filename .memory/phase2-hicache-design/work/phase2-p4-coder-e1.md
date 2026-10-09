# phase2-p4-coder-e1 — P4 DEVICE_QUOTA 容量唤醒加当前-suffix 门（coder 实现）

```text
status: done
artifacts:
  - commit 920003bf07（本地，未 push）：仓库 /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt，
    分支 3090-24g-opt，HEAD 由 0f8542c1a5 -> 920003bf07（独立 commit，仅含 P4 生产改动 + 单测）
  - 生产改动 1 文件 + 测试 1 文件（详见 diff 摘要）
  - 报告：本文件
evidence:
  - 受影响 5 套件全绿：314 passed（基线 310 -> 314，净 +4 为本次新增用例）
  - 全 3090-dev/：420 passed，5 failed 为 BASE 预存在已知问题
    （test_drain_reentry `_FakeTreeCore` 缺 get_component_deviation，与本次改动无关；
    基线 416 -> 420，净 +4 为本次新增测试）
  - 运行命令：PYTHONPATH=python /home/charles/sglang-venv/bin/python -m pytest 3090-dev/<file>.py
summary:
  - commit hash: 920003bf07
  - P4 门实现点：scheduler.py `_restore_wait_capacity_fits` DEVICE_QUOTA 分支，
    在既有 can-never-qualify 保底门之后、promotion_wait_blocked 之前追加 `_current_prefetch_suffix_lt_threshold(req)`
    判定；新增辅助方法 `_current_prefetch_suffix_lt_threshold`（复用 `_compute_max_prefix_len` /
    `self.page_size` / `self.tree_cache.prefetch_threshold`）。
  - Open Decision 1 核验结论：字段未每 pass 刷新 -> 采用 architect 首选的低成本 Form A（纯 predicate），
    读取请求当前 on-disk 几何字段。详见 §2。
  - 单测：4 类新用例 + 1 直接辅助方法用例 + 1 页对齐边界用例（详见 §4）。
  - no-heuristic 逐条自查：零违禁（详见 §6）。
followups:
  - tester 复测 P1 deterministic workload 6 点（重点点 3/点 4）：P4 预期把 too_short 380/315 tight
    降到 ~53/~5（REVALIDATE-bet 空转消，剩 never-case 11 + 少量真实 too_short）；点 3 revoked:miss
    预期 2.84 -> ~2.2-2.4（≤2.5）。
open_issues:
  - Open Decision 2（点 3 PASS 判据）与 Open Decision 3（轮 2 独立收紧是否采纳）待 tester 复测数据裁决，本轮未做。
```

## 1. P4 核心改动（生产）

`_restore_wait_capacity_fits`（scheduler.py）DEVICE_QUOTA 分支，在既有保底门之后追加 P4 门：

```python
if req.hicache_restore_wait_reason is RestoreWaitReason.DEVICE_QUOTA:
    if req.full_untruncated_fill_ids is not None:
        if not (
            self.tree_cache.prompt_can_qualify_for_prefetch(
                len(req.full_untruncated_fill_ids), req.host_hit_length
            )
        ):
            return False
        # P4 gate (no-heuristic): 当前实际可 prefetch 后缀也必须合格。
        if self._current_prefetch_suffix_lt_threshold(req):
            return False
```

新增辅助方法（紧接 `_restore_wait_capacity_fits` 之后）：

```python
def _current_prefetch_suffix_lt_threshold(self, req) -> bool:
    matched_len = len(req.prefix_indices) + req.host_hit_length
    match_end = req._compute_max_prefix_len(len(req.full_untruncated_fill_ids))
    current_suffix = max(0, match_end - matched_len)
    return (
        current_suffix // self.page_size * self.page_size
        < self.tree_cache.prefetch_threshold
    )
```

- 语义：current suffix = 请求超过"宿主匹配 + device 匹配"的余量，即 `prefetch_from_storage` 实际传给
  `new_input_tokens` 的长度（`_prefetch_kvcache` 中 `new_input_tokens = fill_ids[matched_len:match_end]`
  同口径）。current suffix < threshold 时容量唤醒 re-issue 必 declined_too_short，故容量不作为唤醒源。
- 页对齐口径与 `prompt_can_qualify_for_prefetch` 一致（`// page_size * page_size`）。

## 2. Open Decision 1 核验结论（当前-suffix 观测方式）

**核验**：请求停 WAIT 期间 `prefix_indices` / `host_hit_length` / `_compute_max_prefix_len` 输出是否每 pass 刷新？

- **结论：不刷新。** 证据链：
  - admission 循环（scheduler.py:4686-4690）：parked `WAIT_CAPACITY[DEVICE_QUOTA]` 请求在
    `req.init_next_round_input`（:4710）**之前** `continue`，故 parked waiter 每 pass 不被重新 match，
    其 `prefix_indices`/`host_hit_length` 保持入场值。
  - 几何刷新发生在两处：①T6 重入路径——T13 兜底 recompute → state NONE → 下一 admission 先跑
    `init_next_round_input`（fresh geometry）→ 再 quota-deny 重 park（带 fresh 字段）；②`_prefetch_kvcache`
    内部（:2971）re-issue 时刷新。

**采用实现：Form A（纯 predicate）**——architect 首选的低成本路径。
- 理由：`_restore_wait_capacity_fits` 每 pass 对每个 DEVICE_QUOTA waiter 调用；若在其中做每 pass
  `init_next_round_input`（tree match）会对 1100+ parked waiter 引入每 pass 额外匹配成本。Form A 只读
  on-disk 字段，零额外树操作，纯 predicate 易单测。
- 对 bet 兑现的影响（已核验不丢失）：REVALIDATE-bet waiter 入场时 current suffix 亚阈值 → Form A 持住
  （不容量唤醒，不 churn）。device match 衰减后的 current suffix 增长在**有界**的 T13 recompute → T6 重入
  （fresh geometry）点被观察到：若衰减使 current suffix 越过阈值 → 门放行 → 容量唤醒 → re-issue → grant
  （bet 兑现）；否则再次持住（不再每 pass 空转）。这正是 architect 设计的"bet 从每 pass 空转试探改为
  device match 衰减后兑现"语义，且 T13 有界（一次而非每秒 72 次）。
- 与 architect 提供的 Form B（放行 `_prefetch_kvcache` 后判断 still-too-short 不再回环）等价：二者都
  以 current suffix 为门。Form A 在 predicate 层前置拦截（re-issue 根本不发生），Form B 在 re-issue 后拦截；
  Form A 更省（不发无效 re-issue）且更易单测，故采纳 Form A。

## 3. 不破坏面（硬约束逐条核验）

| 约束 | 核验 |
|---|---|
| has_restore_potential / prompt_can_qualify_for_prefetch | 不改（unified_radix_cache.py 未动） |
| miss_rearm_allowed / capacity_wake_applies / ready_horizon | 不改 |
| hicache_restore 状态机 / tree_core / unified_radix_cache | 不改（仅 scheduler.py 一处分支 + 一辅助方法） |
| Fix A host_release epoch / T13 兜底 / P3 reconcile / clear 守卫 / P1 sticky-miss / SAFETY_FUSE | 不改 |
| REVALIDATE bet 保留 | has_restore_potential 不动；仅容量唤醒被抑制 |
| population A（current suffix 合格）容量唤醒照常 | `_current_prefetch_suffix_lt_threshold` 返回 False -> 不持住（回归测试点 2 锁定） |
| promotion_wait_blocked | 保留，在 P4 门之后继续生效 |

## 4. 单测（+7，test_hicache_restore_scheduler_feed.py TooShortWakeSchedulerFeedTests）

| 用例 | 覆盖 architect 测试要求 |
|---|---|
| test_revalidate_bet_subthreshold_current_not_woken | ①REVALIDATE-bet waiter（current suffix 亚阈值、max 合格）容量充足时不被唤醒（`_restore_wait_capacity_fits` False） |
| test_revalidate_bet_reward_after_current_suffix_grows | ②current suffix 增长越过阈值后被唤醒（bet 兑现） |
| test_qualifying_prompt_still_wakes（既有，保持 True） | ③population A（current suffix 合格）容量唤醒照常（不回归点 2） |
| test_sub_threshold_never_case_not_woken（既有，保持 False） | ④never-case 残留（当前+max 均亚阈值）不被唤醒 |
| test_p4_gate_page_aligned | P4 门页对齐边界（page_size=16：255->240 持住 / 256->256 放行） |
| test_p4_current_suffix_helper_direct | 辅助方法直接覆盖（含 host+device 匹配扣除、当前 suffix 归零） |
| test_never_case_gate_idempotent（既有） | 纯 predicate 幂等性 |

既有 `test_qualifying_prompt_still_wakes`（population A）与 `test_sub_threshold_never_case_not_woken`
在新门语义下仍保持原断言（True/False），确认不回归。

## 5. 测试结果

- 5 目标套件（test_hicache_restore / scheduler_feed / p3_warmtree_hol / ready_horizon_unit / storage_regression）：
  **314 passed**（基线 310 -> 314，净 +4 本次新增；p3_warmtree_hol 为工作区既有未跟踪文件，仅作为套件参与运行，未纳入 commit）。
- 全 3090-dev/：**420 passed，5 failed**——5 failed 全部为 test_drain_reentry `_FakeTreeCore` 缺
  `get_component_deviation` 的 BASE 预存在 mock 缺陷（前轮已复核），与本次改动无关；基线 416 -> 420 净 +4。

## 6. no-heuristic 逐条自查（零违禁）

| 检查项 | 结论 |
|---|---|
| 新增计数器？ | 无。`_current_prefetch_suffix_lt_threshold` 是几何判据（match_end - matched_len），复用既有 `_compute_max_prefix_len` / `page_size` / `prefetch_threshold`，不新增任何计数状态。 |
| 新增 TTL？ | 无。不新增时间戳/超时。既有 T13（`hicache_restore_wait_timeout_s`）与 SAFETY_FUSE 保留不改。 |
| 新增次数阈值？ | 无。无"连续 N 次后降级"、无"REVALIDATE-bet 次数/时长上限"。 |
| 违反 miss_rearm 判据白名单（sticky / 同锚 version 前移 / re-anchor / generation）？ | 未违反。P4 不动 `miss_rearm_allowed` / T6 re-arm / NO_L3 cursor。新增门属态 2（too_short）"sticky 负证据 + 几何实质变化"：current suffix 亚阈值是 sticky 负证据，越过阈值（device match 衰减）是几何实质变化，同属允许的"状态实质变化驱动再触发"，非计数/TTL。 |
| 触碰既有 SAFETY_FUSE / Fix A host_release epoch？ | 否，均不动。 |

## 7. diff 摘要（commit 920003bf07）

生产改动：
- scheduler.py：+28 行 `_restore_wait_capacity_fits` DEVICE_QUOTA 分支追加 P4 门（含注释）+ 新增
  `_current_prefetch_suffix_lt_threshold` 辅助方法（+22 行）。净 +50/-0。

测试改动：
- test_hicache_restore_scheduler_feed.py：+92/-13 行（`_req` 增 `_compute_max_prefix_len` stub、
  `_capacity_tree` 增 `prefetch_threshold` 参数、新增 3 个 P4 用例 + 1 辅助方法用例 + 1 页对齐边界用例）。

不改：unified_radix_cache.py / radix_cache.py / schedule_batch.py / ready_horizon.py / hicache_restore.py
状态机 / tree_core / P1 sticky miss / NO_L3 per-anchor cursor / P3 A+B 补链 / clear 守卫 / T13 兜底 / Fix A。
