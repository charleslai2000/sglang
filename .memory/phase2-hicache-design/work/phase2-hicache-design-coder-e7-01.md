# P2-1 M1b capacity 死循环修复 — coder e7-01

## status

**done** — restore 状态机 capacity 死循环（tester e10 阻塞项）已修复：两重防御 + 超时统一兜底。
本机 py_compile OK + torch-free 35/34/9 全绿；部署 3090 双侧 md5 5 文件一致；远端真实 torch
35/34/9 全绿；引擎未启动（GPU 15 MiB、0 进程）。RED→GREEN 已做（3 处突变均被测试捕获）。
未 commit 未 push。

## 根因定位（HEALTH_CHECK 为何进 WAIT 且不超时）

循环链条（tester e10 轨迹 1,668,734 restore_state / 834,363 restore_retry cause=capacity 的机制解释）：

1. **入口误判**：HEALTH_CHECK（prompt 3 token）到达 → `_prefetch_kvcache` gate 通过（anchor=root，
   scheduler.py:2910-2917）→ `prefetch_from_storage` 返回 `declined_too_short`
   （`prefetch_length < prefetch_threshold(256)`，unified_radix_cache.py:1880-1893）→
   scheduler.py:2944-2945 无条件喂 `DENIED_SHORT` → WAIT[REVALIDATE]。
   短 prompt 的 suffix **永远**不可能 page-aligned 到 256（`page_aligned` 向下取整，
   radix_cache.py:150-154）→ 该拒绝是终态，不是容量问题。
2. **T11 错误唤醒**：`_reconcile_restore_states` 的容量谓词（device charge / host budget）对
   REVALIDATE 恒真（短 prompt charge 极小）→ 每 pass 都 RETRY_PREFETCH 重发 → 再次
   declined_too_short → 再 WAIT。谓词测的不是拒绝原因（suffix 太短），重发必被同样拒绝。
3. **超时永不触发**：每次重入 WAIT 都执行 `req.hicache_restore_state_ts = time.perf_counter()`
   （scheduler.py 旧 3100 行）→ T13 判定 `now - state_ts > 60`（3023 行）永远不满足。
   对照：真实请求 e04b9498 在 WAIT 中稳定停留（T11 谓词不满足，无重发）→ state_ts 稳定 → 60s
   超时正常触发。**条件差异 = state_ts 在每次 WAIT 重入时被重置**。

`has_restore_potential` 误判 true 的原因：anchor=root 子句（unified_radix_cache.py:2381-2382
`is_root(anchor)` → True）——短 prompt 无前缀也命中 root；且 `_storage_prefetch_missed_rids`
（T4 拒绝时登记，1891 行）在 `interval=0` 下永不弹出 → 后续 T6 判定也恒 True。

## 修复清单（3 源文件 + 2 测试文件，语义）

| 文件:行 | 改动 | 语义 |
|---|---|---|
| `scheduler_components/hicache_restore.py:146-212` | 新增纯函数 `wait_clock_next()` + `capacity_wake_applies()` | ① 超时时钟（T13 基准）：**首次进 WAIT 时上弦，此后任何 WAIT 重入/WAIT→RESTORING 重发腿都不重弦**，READY/NONE 才清零——超时成为所有子态循环的硬上限；② T11 唤醒适用范围表：仅 DEVICE_QUOTA/PREFETCH_BUDGET/FRONTIER（谓词可验证的原因）；REVALIDATE/HOST_ALLOC 的拒绝原因谓词测不到，唤醒=必重拒=死循环，只走 paced retry（interval>0）或 T13 |
| `mem_cache/unified_radix_cache.py:2369-2404` | 新增 `prompt_can_qualify_for_prefetch()`（与 prefetch_from_storage 同式 page-aligned 阈值判定）+ `has_restore_potential()` 加 prompt_len 参数（默认 None 向后兼容）与 can-never-qualify 早退 | 短 prompt 的 storage 查询**永远**到不了阈值 → 无恢复意图 → 任何入口都不进 WAIT（host_hit>0 仍优先 True：load_back 恢复路径不受影响） |
| `managers/scheduler.py:2946-2952` | T4 喂入门：`declined_too_short` 仅在 `_restore_potential_for(req)` 时喂 DENIED_SHORT | HEALTH_CHECK 类短 prompt 直接走正常路径（普通准入重算），不进状态机 |
| `managers/scheduler.py:2961-2970` | T5 gate-skip 门：`prompt_can_qualify_for_prefetch` 才注册 frontier waiter | 短 prompt 不挂 M2 等 60s；42ms-gap 长 prompt 合法等待不受影响（只用 prompt 门、不用 anchor 子句——anchor 未 backup 正是等待的意义） |
| `managers/scheduler.py:3046-3051` | T11 前加 `capacity_wake_applies` 过滤 | REVALIDATE/HOST_ALLOC 不再被容量谓词每 pass 重发（循环源头切除）；T13 兜底 |
| `managers/scheduler.py:3116-3129` | `_apply_restore_event` 改用 `wait_clock_next`（state_ts 唯一写点） | 修复"重入重弦"——T13 对所有子态生效（含 REVALIDATE），任何残余循环 ≤60s 有界退出 |
| `managers/scheduler.py:3174-3182` | 新增 `_restore_potential_for(req)` 共享入口判定；T6（3905 行）改用它 | T4/T5/T6 三入口同判据（含 prompt 门），消除 has_restore_potential 旧 3 参调用 |
| `3090-dev/test_hicache_restore.py`（+10 测） | `RestoreWaitClockTests`（7）：首进上弦/重入不重弦/重发腿保留/结束清零/全新 RESTORING 为 0/READY→WAIT 新上弦/**循环后超时仍触发**（端到端）；`CapacityWakeApplicabilityTests`（3）：三可测原因 True、REVALIDATE/HOST_ALLOC False、None False | 钉住"所有子态超时逃逸"与"REVALIDATE 不被 T11 唤醒" |
| `3090-dev/test_storage_regression.py`（+2 测 + fake page_size=1） | `test_prompt_can_qualify_for_prefetch`（阈值/边界/host_hit 缩减）；`test_short_prompt_never_has_restore_potential`（root anchor + 短 prompt False、missed_rids 不覆盖、host_hit 仍 True、长 prompt 保留旧子句、prompt_len 缺省=旧行为） | 钉住 HEALTH_CHECK 误判（回归测试） |

可选防御（retry 频率上限）评估结论：**不实现**。T11 排除（REVALIDATE/HOST_ALLOC）+ 时钟保留后，
观察到的循环类已无 per-pass 重发源；剩余原因（DEVICE_QUOTA/PREFETCH_BUDGET/FRONTIER）的谓词
恰测其拒绝原因，不会"必重拒"；再加频率上限属于过度设计（且会延迟合法唤醒）。

## evidence

1. 本机 `python3 -m py_compile`（5 文件）：`PY_COMPILE_OK`。
2. 本机 torch-free（Python 3.12，stubenv）：`test_hicache_restore.py` **35/35**（既有 25 + 新 10）、
   `test_storage_regression.py` **34/34**（既有 32 + 新 2）、`test_drain_reentry.py` **9/9**。
3. **RED→GREEN ×3**：① 注释掉 prompt 门 → `test_short_prompt_never_has_restore_potential`
   失败（`True is not false`）；② `wait_clock_next` 改回每次重弦 → `RestoreWaitClockTests`
   3 失败（`11.0 != 1.0`）；③ `capacity_wake_applies` 加入 REVALIDATE → 唤醒表测试失败。
   还原后全绿。
4. 部署 3090 `root@175.155.64.171:24052` `/root/sglang-b1-continuity/`（scp 5 文件，
   首传误放根目录已 mv 纠正），**双侧 md5 逐文件一致**：
   - hicache_restore.py `a5b39c10dba3c44d5a1d5598f04062bb`
   - unified_radix_cache.py `a375208c6f0f67d85fa1d051a73139a3`
   - scheduler.py `9354ed99185d8cb3defbf9a76e82ca1c`
   - test_hicache_restore.py `5a33aa39fdaa6fbd0511d39ebcef636c`
   - test_storage_regression.py `2af63689b67e78fe9ea70d1dcfa7e07a`
5. 远端 `/root/miniconda3/envs/sglang-patch/bin/python -m py_compile`（Python 3.10.21）：
   `REMOTE_PY_COMPILE_OK`；`unified_radix_cache.__file__` = 部署路径（真实安装包）。
6. 远端真实 torch（2.13.0+cu130）回归：`test_hicache_restore.py` **35/35**、
   `test_storage_regression.py` **34/34**、`test_drain_reentry.py` **9/9**。
7. 3090 引擎未启动：`nvidia-smi` 15 MiB、0 引擎进程。
8. git diff 审查：本 epoch 改动仅 5 文件（3 源 + 2 测），叠加于既有 P2A/M1a/M1b/M2 未提交遗产之上；
   未触碰 cache_controller/hiradix_cache/hybrid_cache_controller。

## summary

根因三层：短 prompt 被 T4 无条件接入 WAIT（入口误判）、T11 容量谓词对 REVALIDATE 恒真导致
per-pass 重发（错误唤醒）、state_ts 每次重入重弦导致 T13 永不触发（超时失效）。修复 = 入口
排除（`prompt_can_qualify_for_prefetch` 门 + has_restore_potential 修正，T4/T5/T6 三入口共用）+
唤醒切除（T11 只对谓词可验证的原因生效）+ 时钟保留（`wait_clock_next`，任何 WAIT 循环 ≤60s
有界退出）。HEALTH_CHECK 类短 prompt 现在全程不进状态机，直接正常路径；K=1 基线不再被循环
占满调度 pass。所有新语义均为纯函数/缓存方法，torch-free 全量可测。

## followups

- tester：K=1 基线回归重跑（HEALTH_CHECK 不再阻塞）；K=8 三判据；42ms-gap 场景复测
  （frontier_wake=0 待 capacity 修复后复核，本次未触碰 M2 wake 路径）。
- 集成验证点（供 orchestrator 排期）：engine log 中 HEALTH_CHECK rid 不应出现
  `evt=restore_state state=WAIT_CAPACITY reason=REVALIDATE`；`restore_retry cause=capacity`
  计数应趋近 0；`restore_recompute cause=timeout` 只对真实长 prompt REVALIDATE 出现（有界）。
- 待裁决：REVALIDATE 在 interval=0 时 60s 超时等待 vs 立即重算（设计 T13 字面语义，本文未改；
  若 K=8 观测到 fully-matched 型请求 60s 延迟影响 turns/s，可加 interval 或缩短该原因的超时）。

## open_issues

- T9 真 miss 清状态时未 discard frontier waiter（`_feed_restore_terminal` 无 discard 调用）——
  预存问题，条目有界、消费点有 WAIT 态守卫，不影响本修复，未动。
- 短 prompt 在 `_storage_prefetch_missed_rids` 中残留（interval=0 永不弹出）——已无害
  （prompt 门在 intent 子句之前判定），但属历史积留，可后续清理。
