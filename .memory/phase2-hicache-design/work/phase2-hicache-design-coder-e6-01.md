# P2-1 Step 2+3 (M1b 状态机 + M2 注册唤醒) — coder e6-01

## status

**done** — M1b + M2 按设计 §5/§6 落地，本机 torch-free 全绿（25/32/9），部署 3090
`/root/sglang-b1-continuity/` 双侧 md5 10 文件一致，远端真实 torch 回归 25/32/9 全绿，
远端 py_compile OK，引擎未启动（GPU 15 MiB 空闲、0 引擎进程——K=8 主判据归 tester）。
未 commit 未 push。RED→GREEN 已做（T10 突变 → 测试捕获 → 还原）。

## artifacts（改动清单）

| 文件:行 | 改动 | 语义 |
|---|---|---|
| `python/sglang/srt/managers/scheduler_components/hicache_restore.py`（新，166 行） | RestoreState/RestoreWaitReason/RestoreEvent/RestoreDecision 4 枚举（:19/:28/:38/:57）+ `next_restore()` 纯函数（:67，设计 §2.2 全表）+ `wait_reason_for()` 事件→原因映射（:146） | 设计 §4.3 模块；scheduler 只喂事件、执行决策；miss 决策 ≠ 容量决策（T9 真 miss→ADMIT_RECOMPUTE，T13 超时兜底，RESTORING 不参与计时） |
| `python/sglang/srt/managers/schedule_batch.py:99-103,1041-1046` | Req +3 字段（`hicache_restore_state` / `_wait_reason` / `_state_ts`） | 设计 §4.1，与 storage_prefetch_retry_* 平铺 |
| `python/sglang/srt/managers/schedule_policy.py:520-551` | 模块级纯函数 `device_charge()` + `available_and_evictable_tokens()` | 与准入同公式的共享公式（T11 谓词用）；`_device_charge`（:892）改为委托（M1a 等价表测试钉死逐位等价） |
| `python/sglang/srt/managers/schedule_policy.py:1414-1419` | `init_load_back` 空结果且仍 `needs_host_load_back()` → `AddReqResult.RESTORE_DENIED`（T7） | C4 消除：host 材料在、device 配额瞬时不足不再静默回落为空匹配；检查放 cat 变更前（无部分变更）；P2A 计数器 `load_back_denied` |
| `python/sglang/srt/managers/scheduler.py:2928-2962` | `_prefetch_kvcache`：prefetch_from_storage outcome（issued/declined_*）喂状态机 T1-T4；gate skip else 分支 → T5 WAIT[FRONTIER] + `register_frontier_waiter`（cache 模式；buffer 模式不注册，见 open_issues） | 设计 §2.2 T1-T5 挂载点；`evt=frontier_wait` 打点 |
| `python/sglang/srt/managers/scheduler.py:2961-3046` | `_retry_missed_storage_prefetches` 演进为 `_reconcile_restore_states`：① terminal outcome 喂入（T8/T9/T10）② 既有 paced retry（interval>0 保留）③ M2 `pop_frontier_ready` 消费（T12）④ WAIT 超时（T13）与容量谓词（T11） | 设计 §4.5；每 pass 容量重读（rem_total_tokens 为现成属性 + `_restore_wait_capacity_fits`）；`evt=restore_retry/restore_recompute` 打点 |
| `python/sglang/srt/managers/scheduler.py:3048-3172` | helpers：`_feed_restore_terminal` / `_apply_restore_event`（字段+state_ts+`evt=restore_state`）/ `_restore_wait_capacity_fits`（§2.3 三条件：device 增量 charge、host 预算、FRONTIER anchor 兜底+删除自愈）/ `_cleanup_not_added_req`（mamba cleanup 提取，R7） | 状态机喂入与决策执行的唯一通道 |
| `python/sglang/srt/managers/scheduler.py:3824-3836` | 准入循环：`check_prefetch_progress` 后先 `_feed_restore_terminal`（吞掉 check_prefetch_progress 自身触发的 finalize/revoke），再 WAIT_CAPACITY skip（不设 batch_is_full） | 设计 §2.5-4/§4.5；队头 WAIT 不落 adder，杜绝准入时刻无 restore 材料 |
| `python/sglang/srt/managers/scheduler.py:3867-3912` | deny 分支：NO_TOKEN + `has_restore_potential` → T6 WAIT[DEVICE_QUOTA] + continue；`RESTORE_DENIED` → T7 同款 + `evt=restore_loadback_fail`；既有 NO_TOKEN/OTHER break 路径行为不变 | 设计 §4.5/§2.5-1；2,358 次 deny 风暴消除路径 |
| `python/sglang/srt/mem_cache/unified_radix_cache.py:411-421` | `_reset_full` +3 注册表：`_storage_frontier_waiters` / `_storage_frontier_ready` / `_storage_prefetch_terminal` | 设计 §3.1/§4.2 + M1b terminal outcome 表（drain→scheduler 同线程传递） |
| `python/sglang/srt/mem_cache/unified_radix_cache.py:1775-1780,2310-2398` | `node_exists` proxy + M2 4 API（register/pop/discard/_wake）+ `has_restore_potential`（§2.5-1 公式）+ terminal 表 API | 设计 §4.2；全部 set 成员操作；wake 前 node_exists+is_storage_persisted 双闸，绝不解引用 stale NodeId（R-key） |
| `python/sglang/srt/mem_cache/unified_radix_cache.py:1830-2010` | `prefetch_from_storage` 返回 outcome 码（issued/declined_rate_limited/declined_too_short/forfeited_alloc_failed/skipped_no_l3/skipped_dup） | 事件喂入的唯一 issue 侧通道；既有调用方不检查返回值，兼容 |
| `python/sglang/srt/mem_cache/unified_radix_cache.py`（finalize 3 点 + revoke） | terminal 记录："finalized"（cache 成功/混合丢弃/buffer stage 三处）、"revoked_terminated"（revoke_reason=terminated）/"revoked_miss"（miss/insufficient/alloc_failed） | 设计 T8/T9/T10 的 drain 侧事实来源 |
| `python/sglang/srt/mem_cache/unified_radix_cache.py:2663-2668` | `_drain_backup` `advance_storage_persisted` 后加 `_wake_frontier_waiters` | M2 唤醒钩：只 set 操作、零队列消费/回调/写，F2 exactly-once 不动（test_drain_reentry 强制回归门）；`evt=frontier_wake` 打点 |
| `python/sglang/srt/mem_cache/unified_radix_cache.py:2297-2312,2340-2347` | `pop_prefetch_loaded_tokens` / `release_aborted_request` 扩展清 terminal + frontier waiter | 设计 §3.3 清除 1/3（abort 唯一出口 + 准入消耗点） |
| `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:1942-1947` | `is_storage_persisted()` 访问器 | M2 wake 闸（node.storage_persisted 无现成访问器） |
| `python/sglang/srt/server_args.py:2840-2852` | `hicache_restore_wait_timeout_s: float = 60.0` | 设计 §4.6/O2；0 = 不设界 |
| `3090-dev/test_hicache_restore.py`（新，25 测） | 状态机全表 | 见覆盖表 |
| `3090-dev/test_storage_regression.py`（+12 测） | M2 注册表 9 测（register/re-register/wake 幂等/删除节点闸/ready 一次性/清理/terminal 一次性/restore_potential）+ T7 3 测（空 load_back→RESTORE_DENIED / 成功仍准入 / 无 host 材料不触发） | 设计 §5 改动 7/3 的 torch-free 面 |
| `3090-dev/test_drain_reentry.py`（+2 测） | `_drain_backup` ACK → advance_storage_persisted + wake 移入 ready（恰好一次，重复 drain 不重唤）；未提升节点不唤 | F2 exactly-once 强制回归门扩展（改动 8） |

## evidence

1. 本机 py_compile（10 文件）：exit=0。
2. 本机 torch-free（各独立进程）：`test_hicache_restore.py` **25/25 OK**；
   `test_storage_regression.py` **32/32 OK**（既有 20 + 新增 12）；`test_drain_reentry.py` **9/9 OK**（既有 7 + 新增 2）。
3. **RED→GREEN**：把 `next_restore` 的 T10（REVOKED_TERMINATED）突变为
   `NONE/ADMIT_RECOMPUTE` → `test_t10_terminated_revoke_waits_for_prefetch_budget` 失败
   （`<RestoreState.NONE> is not <WAIT_CAPACITY>`）；还原后 25/25 全绿——测试确实守卫
   "容量性 revoke 进 WAIT、真 miss 才 RECOMPUTE"的核心语义。
4. 部署 3090 `root@175.155.64.171:24052` `/root/sglang-b1-continuity/`（scp 10 文件），
   双侧 md5 逐文件一致（部署中途 3 文件 scp 目标目录错误已用 mv 纠正并复验）：
   - hicache_restore.py `1e9f5f4214e3d1b06e67bdabe4bf5900`、schedule_batch.py
     `ccaacce70370797675747896d303b192`、schedule_policy.py
     `4457cd5cf6b880efa40281d8665b8eaa`、scheduler.py
     `432196b0fadcdfe951f25ebb380e1277`、unified_radix_cache.py
     `8fc48e7b9b287eb4b4b5f20e7c3450bf`、unified_tree_core.py
     `31a826962ae013abfb02ec39a812bbb6`、server_args.py
     `ad9dfb11c5948c33f44814c50cc09a2d`、test_hicache_restore.py
     `aa427c28194767595d8101b7f46cbce8`、test_storage_regression.py
     `5b1dee02b604bdd08fd414a383c2a8ff`、test_drain_reentry.py
     `feb83ecddb28da5b36b06fa87c92acee`（双侧一致）。
5. 远端 `/root/miniconda3/envs/sglang-patch/bin/python -m py_compile`（Python 3.10.21）10 文件
   `REMOTE_PY_COMPILE_OK`；远端 `schedule_policy.__file__` = 部署路径（真实安装包路径）。
6. 远端真实 torch（2.13.0+cu130）回归：`test_hicache_restore.py` **25/25**、
   `test_storage_regression.py` **32/32**（首跑 1 error：`torch.cat` 需真 tensor——测试 fake
   改 torch-aware（torch 路径用 `torch.arange`，stubenv 用 list）后全绿，重传 md5 复验）、
   `test_drain_reentry.py` **9/9**。
7. 3090 引擎未启动：`nvidia-smi` 15 MiB 空闲、`ps` 0 引擎进程（K=8 主判据归 tester）。
8. git diff 审查：改动仅限任务面 10 文件（+3 测试），无无关改动；既有未提交的
   P2A 插桩/M1a 改动叠加其上（e4/e5 遗产），未触碰 cache_controller/hiradix_cache/
   hybrid_cache_controller。

## summary

M1b 把设计 §2.2 的 14 条转换实现为独立纯模块 `hicache_restore.py`（scheduler 冻结大类
不加状态逻辑，design O4），scheduler 侧只做"喂事件 + 执行决策"：issue 侧（T1-T5）、
准入侧（T6/T7 + WAIT skip）、drain 侧（T8-T10 经 rid-keyed terminal outcome 表）、
reconciliation（T11-T13）。M2 注册表 + 4 API 全 set 操作，唤醒钩挂在
`advance_storage_persisted` 之后，F2 exactly-once 语义零触碰（test_drain_reentry
9 测双端全绿 = 强制回归门）。T11 谓词用与准入同公式的共享纯函数（M1a helper 提取为
模块级 `device_charge`），容量侧故意不含 adder 运行余量 → 只可能更宽松，永不漏唤醒，
过早唤醒自愈。成功判据路径：C1/C2/C4 型 deny → WAIT → 每 pass 谓词/ACK 唤醒 →
RESTORING → READY → 准入消耗（K=8 recompute 1.87M→接近 0 归 tester 实测）。

## followups

- tester：K=8 主判据（restore_retry/restore_ready/restore_recompute 计数、recompute 1.87M→0、
  turns/s 与 p95 恢复）；K=1 基线回归（rs3 型 99.8% 不回归）；42ms-gap 场景
  （K=1 单 agent 快速双 turn → `evt=frontier_wait`/`frontier_wake` 配对出现）；
  `evt=prefill_deny_summary` 30s 聚合观察 deny 次数下降与 width 不变。
- 集成测试要求（供 orchestrator 排期）：engine log grep
  `[P2A] evt=restore_retry|restore_ready|restore_recompute|restore_loadback_fail|
  frontier_wait|frontier_wake|restore_state`；`evt=restore_recompute cause=miss` 之外 ≈0。
- 待裁决：open_issues 1/2/4/6。

## open_issues

1. **alloc_failed revoke 分类**（设计未覆盖）：drain 时 `_try_alloc_storage_hit` host staging
   失败 revoke（revoke_reason=alloc_failed）按真 miss 类 → RECOMPUTE（保守默认 = 现状行为）。
   `next_restore` 的 `genuine_miss=False` 分支（→ WAIT[HOST_ALLOC]）已实现并测试，若裁决
   "容量性重试"翻转 revoke 映射一行即可。
2. **buffer_mode gate skip 不注册 frontier waiter**（设计 T5 只覆盖 cache 模式）：buffer 模式
   按 hash 读、无 anchor backup 概念，注册会造成 60s 长眠回归；保持现状（跳过 → 重算）。
3. **谓词 charge 不含 mamba_gap**（M1a helper 的 gap 依赖 adder 内部 `_mamba_slot_cost`）：
   只可能低估 → 严格更宽松，永不漏唤醒；过早唤醒代价 = 一次重发自愈（门拒绝 → 再 WAIT）。
   同理不含 adder 运行余量（§2.3 的 rem_total_tokens 含 offset；有意排除）。
4. **check_prefetch_progress 中途 revoke 竞态**：准入循环内 check_prefetch_progress 自身
   触发 terminated-revoke 时该 req 当 pass 仍被准入（T10 WAIT 次 pass 才生效）——wait_complete
   下 terminated 事件走 drain 主路径，此路径罕见且有界；如需闭合可在 check_prefetch_progress
   True 分支后立即查 terminal 表（当前 `_feed_restore_terminal` 已在该位置，实际已闭合——
   记录点是 revoke_pending_prefetch 内部，先于 check_prefetch_progress 返回）。
5. `evt=restore_ready` 在 FINALIZED→READY 转换处打点（设计写"READY 消费处"，观测等价，
   消费处在准入 loop）。
6. legacy paced retry（interval>0）按 missed_rids 对全 rid 生效（含 T9 真 miss 已清状态的
   req）→ 仍会被旧机制重试至 max_attempts（有界）；默认 interval=0 无影响（设计 §3.2
   已声明 interval 降级为 REVALIDATE 兜底）。
