# P2IO coder e11 — P3 Ready Horizon v0 3.1（预算拆分 + 集中 bookkeeping）

## status

done

## artifacts

### 源码（5 文件）

- `python/sglang/srt/server_args.py`
  - 新增 `enable_ready_horizon: bool = False`（NS("memory")）——3.1 主闸；off = 逐字节基线
  - 新增 `hicache_prefetch_speculative_fraction: float = 0.6`（NS("memory")）——spec 子预算占比
- `python/sglang/srt/managers/cache_controller.py`
  - `__init__`：`self.prefetch_speculative_fraction = 0.6`（构造期静态；tree 在 init_hicache 用 server_args 覆盖）
  - `attach_storage_backend`（attach 处，M1）：`prefetch_speculative_capacity_limit = int(fraction * prefetch_capacity_limit)`；`inflight_speculative_tokens = 0`（物理计数器 `prefetch_tokens_occupied` 保留原名——buffer pipeline / storage_attachment / hiradix 均依赖，改名风险高）
  - `reset()`：`inflight_speculative_tokens = 0` 随物理计数器同清
  - 新增 `prefetch_speculative_rate_limited()`（镜像 `prefetch_rate_limited`）
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - 新增 `PrefetchKind(Enum)`（SPECULATIVE/DEMAND）+ `PrefetchReservation`（tokens/kind/released，`__slots__`）
  - `_reset_full`：`self._prefetch_reservations = {}`
  - `init_hicache`：`self.enable_ready_horizon = server_args.enable_ready_horizon`（构造期静态）；controller 上 `prefetch_speculative_fraction = server_args.hicache_prefetch_speculative_fraction`（attach 前写入）
  - 新增 `reserve_prefetch(req_id, tokens, kind)` / `release_prefetch(req_id, reason)`（M5 单 helper，exactly-once；double reserve assert 兜底；release 幂等）
  - `prefetch_from_storage`：rate check 改两轨——`_prefetch_budget_denied(demand_restore)`（spec 轨道 = 物理满 OR（flag on 且 spec 满）；demand 轨道 = flag on 且物理满）；issue 时 cache 模式 + flag on 分类 reserve（DEMAND if demand_restore else SPECULATIVE）
  - 五条释放路径全走 `release_prefetch`：finalize（`_handle_prefetch_result`）、hybrid-discard（`_check_hybrid_prefetch_result` 丢弃分支）、abort（`release_aborted_request`，在 ongoing 检查前无条件释放=自愈）、revoke（`revoke_pending_prefetch` pop 前释放=自愈）、detach（`storage_attachment._release_pending_storage_ops` 两处 + 异常分支）
  - M2 禁驱逐：`_try_alloc_storage_hit` alloc 失败 → 仅当 reservation 为 None（off 基线）或 DEMAND 才 `evict_host`；SPECULATIVE 静默走 revoke decline
- `python/sglang/srt/mem_cache/unified_cache/storage_attachment.py`
  - `_release_pending_storage_ops`：detach 路径两处 + except 分支走 `cache.release_prefetch(req_id, "detach")`
- `python/sglang/srt/managers/scheduler.py`（仅 orchestration 级，遵守 large-class-style）
  - `__init__`：`self.enable_ready_horizon = server_args.enable_ready_horizon`
  - T11/T12 wake re-issue（:3048/:3103）：`demand_restore=self.enable_ready_horizon or was_backup_pending`

### 测试（4 文件）

- `3090-dev/test_prefetch_budget_split_unit.py`（新，24 测试）——M1 两轨 rate check、M5 exactly-once（五路径 + 重复 release 幂等）、M2 禁驱逐、off 基线、scheduler 接线 on/off。放 3090-dev 而非 test/registered/unit/mem_cache/（任务允许"或就近"）：与 e10 全部 HiCache 测试同目录、复用其 stubenv 双模 harness（test_drain_reentry/test_storage_regression 的 `_make_cache`），torch 有/无双模式均 24/24 绿
- `3090-dev/test_drain_reentry.py`：`_make_cache` 加 `enable_ready_horizon=False` + `_prefetch_reservations={}`（off 默认 = 既有测试断言基线；空 dict 使五路径 release 调用安全 no-op）
- `3090-dev/test_storage_regression.py`：同上
- `3090-dev/test_hicache_restore_scheduler_feed.py`：`_scheduler()` 加 `enable_ready_horizon=False`

### 未触碰（约束清单）

- `scheduler_components/hicache_restore.py` 零改动（T15 状态机/票池 DEMAND_RESTORE_MAX_INFLIGHT=4 专用不动）
- `schedule_policy.py` 零改动；extent 后端 / allocator / T15 旁路逻辑（`_backup_park_applies` 门控）零改动
- 物理计数器 `prefetch_tokens_occupied` 全部既有记账保留（buffer 门 :448/724/794/940、storage_attachment :386、hiradix :1635-2029 依赖）

## evidence

本机 venv（torch 2.13.0+cu129），`PYTHONPATH=python:3090-dev` 强制本地树（`sglang.__file__` = 仓库 python/ 已核）。

RED→GREEN（TDD）：新测试文件先于实现运行 → 3 failures + 18 errors（PrefetchKind/reserve/release/两轨全缺，scheduler 接线 [False]≠[True]）；实现后 24/24 OK。

全门（实现后最终跑）：

| 套件 | 结果 |
|---|---|
| 3090-dev.test_hicache_restore（64→实际 69） | Ran 69 OK |
| 3090-dev.test_drain_reentry（30） | Ran 30 OK |
| 3090-dev.test_hicache_restore_scheduler_feed（7） | Ran 7 OK |
| 3090-dev.test_storage_regression（94） | Ran 94 OK |
| 3090-dev.test_prefetch_budget_split_unit（新 24） | Ran 24 OK |
| test_extent_file_backend_unit（70）+ test_hicache_file_lru_unit（34） | Ran 70 OK / Ran 34 OK |

合计 328 全绿。另验证 torch-free stubenv 路径（meta_path 阻断 torch）：新测试 24/24 OK。

注：test_hicache_restore 单文件跑 6.8s 系 torch/transformers 惰性导入 warmup（cProfile 证实为 custom_op 注册/transformers 导入，非测试逻辑），与 test_drain_reentry 同进程跑时 warmup 提前完成 → 0.04s；两种顺序均全绿，与本次改动无关。

编译检查：5 个改动源文件 `py_compile` 全过。

## summary

3.1 交付完成：M1（spec 子预算 `prefetch_speculative_capacity_limit` + `inflight_speculative_tokens` 计数器，物理计数保留原名）、M5（`PrefetchReservation` + `reserve_prefetch`/`release_prefetch` 单 helper，finalize/revoke/abort/hybrid-discard/detach 五路径 exactly-once，upstream #31445 泄漏类 bug 防护）、M2（speculative staging alloc 失败静默 decline，仅 DEMAND/off 基线可 evict_host——`evict_host` 在 prefetch 路径唯一调用点 `_try_alloc_storage_hit` 已确认）、scheduler 接线（T11/T12 wake re-issue 在 flag on 时全部 demand 分类，T15 票池不动）。off 语义逐字节论证见 open_issues 附注；双模测试证明。

## followups

- 3.2（ready_horizon 协作模块 + 水位维持 M2/M3/M6）可开工；本阶段 rate check 已为 3.2 的事件驱动 refill 留好接口（declined_rate_limited 仍进 WAIT[PREFETCH_BUDGET]，T11 物理预算谓词未动）
- 3090 同步由 orchestrator 执行（本机未 push）

## open_issues

**off 行为逐字节论证**（enable_ready_horizon=False，对照 e10 基线）：
1. rate check：`_prefetch_budget_denied` 对 speculative 返回 `physical_full or (False and ...)` = 物理单轨（= 原 `not demand_restore and prefetch_rate_limited()`）；对 demand 返回 `False and physical_full` = 不拒（= 原 demand 完全旁路）。逐字节等价
2. spec 计数器：reserve 仅在 flag on 且 cache 模式调用 → off 恒 0，物理计数路径全部保持现状（issue += / finalize −= / discard −= / revoke −= / buffer hit-alloc += 原样）
3. 五路径 release 调用：off 时 `_prefetch_reservations` 恒空 → 全部 no-op，无任何可观测行为
4. M2 门：reservation None → evict 允许（= 基线）；`_prefetch_reservations.get` 空 dict 查找无副作用
5. scheduler：`enable_ready_horizon or was_backup_pending` = `was_backup_pending`（= 基线逐字节）
6. `prefetch_speculative_rate_limited` off 时短路永不调用
7. 新增控制器属性为惰性状态，无外部读取
— 差分面仅：替换的条件表达式（语义等价）+ 幂等 helper 调用（空 dict no-op）+ M2 门条件（语义等价）。行为对照由 `ReadyHorizonOffModeTests` 4 测试锁定（spec 计数恒 0、单轨物理检查、demand 旁路、alloc 失败仍 evict）。

**已知说明**：
- 单文件跑 test_hicache_restore 的 7s 为导入 warmup（见 evidence），非回归
- 新测试文件放 3090-dev/ 而非 test/registered/unit/mem_cache/（任务"或就近"），理由见 artifacts；如需进 registered 由 orchestrator 裁决
- 任务给定测试数 64 与实测 69 之差为 e10 后续新增（T15 positive/off 变体），以实际为准，全绿
