# phase2-tooshort-fix-coder-e1 — too_short recompute churn 修复实现

```text
status: done
artifacts:
  - repo /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt（分支 3090-24g-opt）
    - python/sglang/srt/mem_cache/unified_radix_cache.py（主修）
    - python/sglang/srt/managers/scheduler.py（辅修）
    - 3090-dev/test_storage_regression.py（主修测试 + 既有断言更新）
    - 3090-dev/test_hicache_restore_scheduler_feed.py（辅修 T11 唤醒测试）
    - 本地 commit hash: 7155cd8973e4545028f68204491655bf3bc6a430（HEAD 之后，未 push）
evidence:
  - PYTHONPATH=<repo>/python /home/charles/sglang-venv/bin/python -m pytest
    - 3090-dev/test_hicache_restore_scheduler_feed.py: 16 passed（含新增 3 条 T11 唤醒）
    - 3090-dev/test_storage_regression.py: 101 passed（含新增 2 条 + 1 条既有断言更新）
    - 3090-dev/test_hicache_restore.py + test_ready_horizon_unit.py: 144 passed
    - 3090-dev/ 全量: 367 passed, 5 failed（test_drain_reentry.py，已在 clean HEAD 上复现为既有失败，与本改动无关）
summary:
  见下。
followups:
  - 集成/系统级验证交由 tester（生产 so/真实负载下观测 too_short/declined_too_short 计数是否归零、P3 READY/decline 统计是否干净）
  - open decision 1（device-match-decay REVALIDATE bet 保留粒度）按架构师默认执行：只释放"当前+理论最大都 sub-threshold"，decay 后可达的保留。已在测试中固化。
open_issues:
  - 未触碰任何既有确认基线（RH/ready-horizon 全绿，见 evidence）
```

## 1. 精确修改点（文件:行 + diff 摘要）

- **主修** — `unified_radix_cache.py:3121-3137` `has_restore_potential`：
  把 `host_hit_length > 0: return True` 短路移到 `prompt_can_qualify_for_prefetch` never-case 门**之后**。
  即 never-case 门（当前+理论最大 suffix 都 < prefetch_threshold）现在对 host 有物材的请求同样生效。
- **辅修** — `scheduler.py:3721-3738` `_restore_wait_capacity_fits`：
  在 `cc.prefetch_rate_limited()` 检查之后新增一条 DEVICE_QUOTA 守卫：若
  `req.full_untruncated_fill_ids is not None` 且
  `not prompt_can_qualify_for_prefetch(len(fill_ids), host_hit_length)` → 直接返回 False（不唤醒）。
  该守卫位于 promotion-budget 项之前，只影响 DEVICE_QUOTA waiter，其余 reason 分支不变。
- 无新抽象、无状态机改动、未改 unified_tree_core.py assert 语义、未降 prefetch_threshold、未 merge Fix B、未动 P0/P1/Fix A/Fix B/P3/GC。

## 2. 主修 + 辅修实现与 never-case 判别粒度（open decision 1 默认）

**判别粒度（open decision 1）**：采用架构师推荐——只释放"当前 suffix 与理论最大 suffix 都 < prefetch_threshold"的请求。
- 当前 suffix 由 `prompt_len - host_hit_length` 体现（`_prefetch_kvcache` 的
  `matched_len = prefix_indices + host_hit_length`，matched_len 越大，当前 storage 查询越短）；
  理论最大 suffix 是 device match 完全 decay 后 prompt 超出 host match 的长度。
- `prompt_can_qualify_for_prefetch`（unified_radix_cache.py:3101-3111）正是该 never-case 的单一判据
  （`max_suffix = prompt_len - host_hit_length`，page-aligned 后与 `prefetch_threshold` 比较）。
- **device-match-decay REVALIDATE bet 保留**：当前 sub-threshold 但 `prompt_can_qualify=True`
  （decay 后可达）的请求，主修和辅修都**不**拦截——仍可进 WAIT / 被容量唤醒。误杀面最小。

**主修效果**（准入侧）：
- 之前：host 有物材 + 15-token 尾段 → `host_hit_length>0` 短路 True → T6 准入把请求 park WAIT[DEVICE_QUOTA]。
- 之后：never-case 门先判 → 返回 False → 不 park，直接 recompute 尾段。与 P1/Fix B 的"re-arm 前判据"模式一致。

**辅修效果**（唤醒侧纵深防御）：
- 对任何已进入 WAIT[DEVICE_QUOTA] 的 can-never-qualify waiter，T11 容量唤醒不再把它拉起来
  re-issue 一个必然 declined_too_short 的 prefetch。请求留待 T13 或直接被释放 recompute（无需改动状态机，
  纯谓词收紧，T13 释放路径天然成立）。

## 3. 与 P1/P0/Fix A/Fix B 正交性确认

- 主修只收紧 `has_restore_potential` 的判定；该函数被 T4/T5/T6 与 ready-horizon `staging_eligible` 共用，
  收紧后 can-never-qualify 请求在这些路径上一律视为无 restore intent——正是设计意图，不改变任何正常 ≥threshold 路径。
- 辅修守卫只作用于 `_restore_wait_capacity_fits` 内 DEVICE_QUOTA 分支，位于 P2-1c promotion-budget 项之前，
  不影响 FRONTIER/BACKUP_PENDING/PREFETCH_BUDGET 唤醒。
- P1 miss 门（scheduler.py:4557 `miss_rearm_allowed`）与 Fix B（`device_quota_degraded`）逻辑原样保留，未触碰。
- ready-horizon `_state_funnel` 依赖 `staging_eligible`（来自 `_restore_potential_for`），其"NONE with restore
  potential"与"WAIT DEVICE_QUOTA host_hit==0"分支在 can-never-qualify 下自然变 False，语义自洽，全量 RH 测试通过。

## 4. unit 测试结果

**新增**：
- `test_storage_regression.py::test_never_case_gate_beats_host_material_for_sub_threshold_prompt`
  （sub-threshold + host 有物材 + 当前+理论最大都 < threshold → 无 restore potential，不 park WAIT）
- `test_storage_regression.py::test_revalidate_bet_preserved_when_decay_can_grow_suffix`
  （sub-threshold 但 decay 后可达 → 保留 restore potential，不误杀；含阈值边界 355/356）
- `test_hicache_restore_scheduler_feed.py::TooShortWakeSchedulerFeedTests`（3 条）：
  `test_sub_threshold_never_case_not_woken`（T11 不唤醒）、`test_qualifying_prompt_still_wakes`（decay 可达仍唤醒）、
  `test_never_case_gate_idempotent`（repeated invocation 幂等）

**更新**：`test_storage_regression.py::test_short_prompt_never_has_restore_potential` 中原
  `assertTrue(... host_hit_length=10, prompt_len=3)` 断言改为 `assertFalse`（新语义：host 物材不再覆盖 never-case 门），
  注释同步说明。

**结果**：scheduler_feed 16 passed；storage_regression 101 passed；restore + ready_horizon 144 passed；
  3090-dev 全量 367 passed + 5 failed（test_drain_reentry.py，已在 clean HEAD 复现为既有失败，与本次改动无关——本改动未触碰 drain 路径）。
  正常 ≥threshold 路径（test_prompt_can_qualify_for_prefetch 等既有用例）全部通过，无回归。

## 5. 是否触碰既有确认基线（RH 等）

未触碰。ready-horizon（test_ready_horizon_unit.py）与 restore 状态机（test_hicache_restore.py）全绿；
未改 `unified_tree_core.py` 的 assert 语义；未改任何阈值常量；未 push（仅本地 commit 7155cd8973）。
