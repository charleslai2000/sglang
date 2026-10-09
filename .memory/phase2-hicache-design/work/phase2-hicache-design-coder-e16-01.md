# phase2-hicache-design-coder-e16-01 — P2-1c promotion admission（专家批准 + 4 细节钉死）

## 1. status

**done** — 按设计 p2-promotion-admission.md §5 改动面 8 项实施 + 四条钉死；28 新测 RED→GREEN；
本机 torch-free 151（145 执行 + 6 skip）全绿 + torch 151/151 全绿；远端 3090 151/151 + py_compile OK；
双侧 md5 7/7 一致；引擎未启动（远端 tester 引擎原样在跑，未触碰）；未 commit 未 push。

## 2. artifacts

生产文件（5）：
- `python/sglang/srt/managers/scheduler_components/hicache_restore.py`
  - 新增纯函数 `promotion_budget_fits(locked, reserved, new_restore, capacity, margin)`（§3.1 公式逐字落地，负值 clamp）+ `promotion_wait_blocked(reason, host_hit_length, budget_fits)`（T11 预算项决策表，纯函数可测）
- `python/sglang/srt/managers/schedule_policy.py`
  - 新增 `device_locked_tokens(allocator, tree_cache)`（改 5：镜像 available_and_evictable_tokens 的 isinstance 分派，capacity=size_full）
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - 改 1 检查点 1（load_back 入口门，inc_host_lock_ref 之前）：est=req.host_hit_length，拒绝 = return False → 既有 RESTORE_DENIED 通路；est=0（纯 aux）跳过
  - 改 2 检查点 2（_load_back_transfers 精确门 + reserve，evict_for_alloc **之前**）：exact kv_tokens；拒绝时不启动 walker（forced_drop 下降机制点）；reserve 后全出口 exactly-once（try/finally 兜异常）
  - 改 3 `inflight_promotion_reserved` 计数器 + `_OngoingLoadBack` 第 4 字段 reserved_tokens（= 残余，注册时转锁后为 0）+ ack 归还经 `_finalize_load_back_entry` + sanity_check I2 断言（counter == Σ 活条目残余）
  - 所有权转换（专家①）：ongoing 注册点（inc_lock_ref 后）`_transfer_promotion_reservation`——span 进入派生 locked 后 reserved 只计未转锁部分
  - 全终态释放（专家②）：E3（evict_fail）/E4（load_fail）/异常（finally）/E5（ack finalizer）/cancel（ack 仍达）/shutdown+fatal（`_release_all_load_backs` 扫清 + shutdown() 挂接）；计数器永不为负（underflow 日志 + clamp）
  - 埋点（改 8 + 专家④）：evt=promotion_denied / promotion_denied_exact / promotion_reserve / promotion_transfer / promotion_release，全部携带 `_promotion_pool_observation()`（full_free/full_evictable/full_locked + mamba_free/mamba_evictable/mamba_locked + swa_* 启用时）；峰值 gauge `_promotion_inflight_peak`
- `python/sglang/srt/managers/scheduler.py`
  - 改 6 T11 谓词预算项（_restore_wait_capacity_fits）：DEVICE_QUOTA + host_hit>0 且 budget 不足 → 不 wake（经 promotion_wait_blocked 纯函数）；host_hit=0（T6 材料未就绪）不拦截
- `python/sglang/srt/server_args.py`
  - 改 7 `hicache_promotion_margin_tokens: int = 2048`（专家③：参数化，help 注明 sweep {1024,2048,4096} 与 margin=0 不串行化 2×16K 的算术）

测试文件（2）：
- `3090-dev/test_storage_regression.py`：stubenv 补 `sglang.srt.managers.scheduler_components` fake + 真实 hicache_restore 先于 cache 模块加载；`IncLockRefResult`/`DecLockRefParams`/`EvictParams`/`MatchResult` fake 升级为带真实字段面；`_SplitComponent` 扩展 lock 面（acquire/release_component_lock 镜像 full_component.py 的 evictable/protected 算术）+ hicache transfer 面（build/commit LOAD_BACK 镜像 list 值）；新 harness `_PromoAllocator`/`_LoadBackController`/`_make_loadback_cache`/`_attach_host_chain`（key_offset 防兄弟链碰撞）；28 新测
- `3090-dev/test_drain_reentry.py`：stubenv 补 scheduler_components fake + 真实 hicache_restore 预加载（新 import 的加载顺序）

## 3. evidence

- **双计验证结论（专家①，实证）**：`device_locked_tokens()`（= capacity − available − evictable）在 H→D **开始后包含** promotion 锁——证据：
  - 代码面：full_component.py:294-295/334-335 lock/unlock 同步迁移 evictable↔protected 计数；`full_available_size()` 随 load() 分配同步下降；sanity PART 4（unified_tree_core.py:2528-2551）以 lock_ref 重算 evictable 交叉验证
  - 计数实证（真实树 + 真实 load_back）：`test_gate_locks_do_not_move_span_into_derived_locked`——入口门锁（inc_host_lock_ref+inc_lock_ref，设备less链）后 derived locked 不变（tombstone-skip 路径，span 仍为 free）→ 检查点处 span **不在** locked，reserve 是唯一覆盖（gate 无双计）；`test_post_commit_span_enters_locked_and_reservation_transferred`——commit+注册锁后 locked==2048 且 counter==0（转移后）→ 保留 reserve 到 ACK 会在整个 DMA 窗口双计
  - 事件实证：`evt=promotion_reserve n=2048 reserved=2048 full_locked=0` → `evt=promotion_transfer n=2048 reserved=0 full_locked=2048`（同批 token 恰好计一次）
  - **落法：所有权转换**（reserved 只计未转锁部分）；2×16K 串行化仍成立（margin=2048 下 32K>30720 拒），小 promotion 在 16K 在途时可通过（18432≤30720）——专家"严重压缩吞吐"场景消除
- **exactly-once 全终态释放清单（专家②）**：① success ACK → ack drain pop+`_finalize_load_back_entry`（pop 即 exactly-once）；② explicit failure → E3 evict_fail / E4 load_fail 内联释放 + controller.load 异常 → `_load_back_transfers` finally 释放；③ cancel → release_aborted_request 不取消在途 load（E6），ack 仍达 → finalizer；④ controller fatal/shutdown → `_release_all_load_backs(cause=...)` 扫清（shutdown() 挂接）；⑤ debug 不变量 → sanity_check `assert inflight_promotion_reserved == Σ lb.reserved_tokens`（pass 边界恒成立：gate→注册窗口同线程不可观测）+ 永不为负（underflow 日志 + clamp，R3）
- **margin 参数化（专家③）**：server_args 默认 2048；sweep {1024,2048,4096} 由 tester 跑 Test A' 标定，选择标准 = forced_drop 显著下降前提下 restore throughput/WAIT 最小（非"OOM 不发生"——Z3 已保证）
- **双池观测埋点（专家④）**：全部 promotion 事件携带 full_free/full_evictable/full_locked/reserved + mamba_free/mamba_evictable/mamba_locked（启用时 + swa_*）——per-component budget 未实现（按裁决）
- RED→GREEN：RED = 28 新测对预-P2-1c 生产代码（/tmp 副本精确反向 revert 后）全部 ImportError（缺 promotion_budget_fits 符号，3 测试类抽样 3 errors 捕获）；GREEN 见下
- 本机 torch-free（逐文件独立进程，stubenv 互斥属既有设计）：`test_storage_regression` Ran 94 OK (skipped=6)；`test_drain_reentry` Ran 14 OK；`test_hicache_restore` Ran 43 OK → 合计 151（145 执行）
- 本机 torch（/home/charles/sglang-venv）：`python -m unittest test_storage_regression test_drain_reentry test_hicache_restore` → `Ran 151 tests in 0.089s OK`
- py_compile：7 文件 `PY_COMPILE_OK`
- 远端 3090（root@175.155.64.171:24052，/root/sglang-b1-continuity/，sglang-patch env）：`REMOTE_PY_COMPILE_OK` + `Ran 151 tests in 0.096s OK`
- 双侧 md5 7/7：unified_radix_cache.py `b436952e…`、hicache_restore.py `999e80db…`、schedule_policy.py `680e368d…`、scheduler.py `6e798352…`、server_args.py `bfc0439e…`、test_storage_regression.py `a35b73fb…`、test_drain_reentry.py `e48ca3b8…`
- 引擎未启动：远端 0 新引擎进程；tester 引擎（port 8024，engine-p2b0-3b.log，Aug31 10:17 起）原样存活，GPU 20087 MiB 部署前后不变；部署全程未触碰

## 4. summary

promotion admission 按设计 8 项改动面实施：budget 公式（locked+reserved+new ≤ cap−margin）在 load_back 入口（检查点 1，锁前最廉价拒绝）与 _load_back_transfers 精确门（检查点 2，evict_for_alloc 前）双检查；拒绝走既有 RESTORE_DENIED→WAIT[DEVICE_QUOTA] 通路（状态机零新状态）；T11 谓词加预算项（每 pass 重读即 event-driven wake）；margin 参数化默认 2048。四条钉死：① 实证 device_locked_tokens 在 H→D 开始后含 promotion 锁 → 所有权转换（reserved 只计未转锁部分，转移点 = ongoing 注册）；② exactly-once 全终态（finalizer + E3/E4 + finally 异常 + shutdown/fatal 扫清 + sanity 不变量 + 永不为负）；③ margin 参数化 + sweep 标定标准；④ 双池观测埋点（事件携带 per-pool free/evictable/locked）。测试 28 新测覆盖全部要求（budget 边界 margin=0 钉死、全终态归还含 cancel/fatal/shutdown、拒绝→WAIT 零新状态、T11 预算项、16K 串行化集成、双计验证断言）。

## 5. followups

1. **tester 执行 Test A'**（§6.2）：K=32 同参数 fresh ns——forced_drop 显著下降（基线 28.8%，目标 <15%）、timeout 下降（基线 475/651）、promotion_denied>0 且 inflight 峰值 ≤16K、OOM=0 越 989s；margin 标定 sweep {1024,2048,4096}，标定结果写回设计 §3.1
2. **tester 回归**：K=16（128/128 越 470s）、K=1（fresh+warm 12/12）、F2 test_drain_reentry 4 断言、CHAIN_GAP
3. 集成/性能观测要求（Division of labor）：[P2A] promotion_denied / denied_exact / reserve / transfer / release 事件计数（reserve 计数 == transfer+release 可验 R3）、_promotion_inflight_peak、双池 locked/free/evictable 序列（专家④评估是否需 per-component budget）
4. 解码侧（disagg）专项验证留后续场景（改动自动覆盖同一 load_back 入口）

## 6. open_issues

- **远端 tester 引擎运行中（port 8024，engine-p2b0-3b.log，Aug31 10:17 起，max-total-tokens 65536）**：部署替换了磁盘文件，该引擎进程不受影响（启动时已加载），但其**下一次重启将加载 P2-1c 代码**——若该 run 系列需要旧代码基线，请 orchestrator 协调时序
- 设计 §3.1 的"双计式"文档描述与实现的"所有权转换"差异：实现按专家①裁决走转换式（更优），设计文档 §3.1 双计说明段建议由 architect 后续更新（或保持为历史论证——两种公式同一不变量）
- margin 默认值最终以 Test A' sweep 数据裁决（O1）；单测已钉死 margin=0 不串行化（R6 防误设）
- 既有 open_issues 不变：e15 远端残留文件（unified_cache/ 错误路径副本）待授权清理；storage_existence_cache 填充（长期）等
