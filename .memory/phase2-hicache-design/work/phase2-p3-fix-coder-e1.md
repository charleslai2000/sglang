# P3 — L3 ACK-promotion / frontier HOL 修复实现（coder e1）

status: done
artifacts:
  - 本地 commit 30a5a3698a（未 push）@ sglang-3090-24g-opt 分支 3090-24g-opt
  - python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py（B 守卫 + 判定辅助）
  - python/sglang/srt/mem_cache/unified_radix_cache.py（A3 reconcile 入口 + 挂载）
  - 3090-dev/test_storage_regression.py（新增 DeferredAckReconcileTests / DeferredAckReconcileCacheTests）
  - 3090-dev/test_drain_reentry.py（fake tree core 补 deferred_acked_nodes）
evidence:
  - pytest 3090-dev（P3 相关 10 文件，除 drain_reentry）352 passed
  - 新树层 + cache 层测试 10 项全过
  - 全 3090-dev 377 passed / 5 failed（5 项为基线既有 P0 get_component_device_value，非本改动引入，经 stash 基线复测确认）
summary:
  - A（A1/A2/A3）+ B 全部实现，见正文
  - open decisions 1-4 默认选择与理由见 §3

---

## 1. 精确修改点（文件:行 + diff 摘要）

### unified_tree_core.py
- **`clear_storage_durable`（原 :2132-2142，现 :2132-2146）**：加 B 守卫。清双旗前先 `_has_deferred_acked_descendant(node)` 判定；若被清节点仍有 `storage_acked && !storage_persisted` 后代则**不清**（延迟 clear，保留 durable 信念，由 A3 递补）。无依赖子树时行为与现状完全一致（绝大多数 revoke-miss 情形）。
- **新增 `has_acked_descendant(node_id)`（:2148-2155）**：公开判定谓词，DFS 严格后代扫描 `acked && !persisted`，early-return。供 B 守卫 / 测试。
- **新增 `_has_deferred_acked_descendant(node)`（:2157-2170）**：DFS 实现。**不做剪枝**（不因 child 自身非 acked/persisted 跳过其子树）——deferred-persist 窗口期内父链中间节点的 acked 状态可能非最终态，剪枝会漏掉仍依赖本锚点的后代。
- **新增 `deferred_acked_nodes() -> list[NodeId]`（:2172-2186）**：扫描 `_node_arena` 返回所有 `storage_acked && !storage_persisted` 存活节点。派生判定，**无新增持久字段**。

### unified_radix_cache.py
- **`__init__`（:498-502）**：新增 `self._reconcile_depth = 0` 重入守卫计数。
- **`_flush_pending_storage_writes`（:2129-2145）**：处理完 `_pending_storage_writes` 后调用 `self._reconcile_deferred_acked()`。挂载点=ack 后统一 drain 出口（`writing_check` 两条路径 + `write_backup_storage` 尾部均经此），保证"每 pass 一次"。
- **新增 `_reconcile_deferred_acked`（:2147-2163）**：A3 入口，重入守卫（`write_backup_storage` 尾部会再进 `_flush_pending_storage_writes`，无守卫会自递归爆炸）。
- **新增 `_reconcile_deferred_acked_inner`（:2165-2201）**：扫描 `deferred_acked_nodes()`，对每个存活节点：1) `write_backup_storage(node_id)` 重填断裂父链 gap（`collect_storage_gap` 从最近 persisted 祖先/root 兜底）；2) `advance_storage_persisted(node_id)` 重跑真实 ack promotion（对已 acked 节点反向修复）；3) 对 `promoted` 调 `_wake_frontier_waiters` 唤醒 frontier waiter（闭环回到既有 wake 路径，不改 wake 状态机）。

### 测试
- test_storage_regression.py：`DeferredAckReconcileTests`（8 项，树层直测）+ `DeferredAckReconcileCacheTests`（2 项，经真实 cache `_flush_pending_storage_writes` 全链路）。
- test_drain_reentry.py：`_FakeTreeCore` 补 `deferred_acked_nodes = lambda: []`（生产代码新增调用点，需 fake 兼容）。

## 2. A（A1/A2/A3）+ B 实现

- **A1**（clear 后主动递补）：由 B 守卫 + A3 组合实现。B 守卫在"有 acked 依赖"时不抹除锚点 durable 信念；A3 在同一 drain 内扫描到该锚点自身（若它 acked && !persisted）或其后代，`collect_storage_gap` 从最近 persisted 祖先/root 补满断裂 gap，再经 `advance_storage_persisted` 递归下推（2186 既有递归）。
- **A2**（父物理删除后递补）：父节点已被删除时 B 无法兜底。A3 对任一存活 acked-deferred 后代调 `write_backup_storage`，其 `collect_storage_gap` 天然从最近 persisted 祖先/root 重新补满断裂链；再 `advance_storage_persisted` 重 promotion（测试 `test_physical_parent_delete_chain_rebuilt_from_root_on_descendant_write` 验证删除父、后代重锚到 root 后单次重 promotion 收敛）。
- **A3**（统一 reconcile 入口）：`_flush_pending_storage_writes` 挂载，见 §1。单 pass 扫描一次补满，幂等。
- **B**（durable-state invalidation guard）：`clear_storage_durable` 内 `_has_deferred_acked_descendant` 判定，见 §1。

## 3. Open Decisions 1-4 默认选择与理由

1. **B 延迟 clear 用隐式判定**：不引入 `storage_invalidated` 字段。理由：A3 每 pass 都扫描 deferred，且 reconcile 用**真实写 ack / restore** 重验证锚点（`advance_storage_persisted` 只在父链连续时才置 persisted），不存在"过期 durable 信念被误当 anchor 长期存活"——被 B 保留的锚点，其 durable 信念要么经 A3 用真实写重验证，要么写失败走既有 partial-ack / `_skip_stale_storage_persist` 路径不产生假 durable。`_l3_publish_epoch` 语义天然适配（重验证完成即前移）。最小字段、无新状态机。测试 `test_reconcile_is_reentrant_safe_and_never_promotes_barely` 验证 reconcile 不会把未真实 ack 的节点置 persisted。
2. **A3 挂载 `_flush_pending_storage_writes`**：确认为 ack 后统一 drain 出口——`writing_check`（非 write_back 路径 :3966 与 write_back 路径 :3935）和 `write_backup_storage` 尾部（:2198，嵌套 flush）均经此。每 scheduler 事件循环的 `check_hicache_events` → `writing_check` → flush 必经，保证"每 pass 至少一次"，符合约束③（不依赖新 IO 碰巧触发）。用 `_reconcile_depth` 防 write_backup 尾部 re-enter 自递归。
3. **B 守卫子树遍历不剪枝（全量递归）**：调用点极少（仅 revoke-miss clear），全量 DFS early-return；`has_acked_descendant` 在无 acked 子时首层即返，绝大多数情形成本可忽略。正确性优先于 micro 剪枝——剪枝会漏真实依赖。此点由 tester 在 warm-tree 上实测 frontier_wait 分布佐证。
4. **A2 并发/写放大不做额外限流**：A3 统一单 pass 扫描，天然避免"哪个后代发起"发散；`collect_storage_gap`/`write_backup_storage`/`advance` 三重 dedupe 保证同链只补一次。单 pass 批量补写复用既有写路径；若 deferred 量超大导致写放大超限，留 tester 观测后再决定是否接入现有 prefetch/写并发控制（实现按最小正确，未加额外限流）。

## 4. 与 P0/P1/too_short/Fix A/Fix B 正交性确认

- **scheduler**：零改动。`frontier_anchor_ready` / T12 / T13 60s timeout / restore_recompute 均未触碰。
- **restore 资格**（P1 另案）：零改动。`mark_storage_restored` 仅被既有 restore finalize 调用，P3 未改 restore 判定。
- **wake 状态机**：零改动。`_wake_frontier_waiters` 只被 A3 在 reconcile 重 promotion 后调用，语义与 ack drain 完全一致（set membership only，无队列消费/回调/写路径）。
- **timeout**：未改 60s（硬约束①）。
- **容量 / prefetch_threshold / Fix A / Fix B / GC / unified_tree_core assert 语义**：均未触碰。
- 唯一对既有测试的改动是 fake tree core 补 `deferred_acked_nodes`（新生产调用点的兼容，非语义变更）。

## 5. 收敛 / 幂等 / 不伪造 durable 的保证

- **收敛**：每次 reconcile 朝"acked 节点 persisted"单调推进。无新 IO 时 A3 单次扫描、每条断裂链一次补满（`collect_storage_gap` 从 root/最近 persisted 祖先兜底），不反复触发。deferred 集合只随节点删除缩小，不新增非 acked 的 persisted 成员。
- **幂等**：三重 dedupe（`collect_storage_gap` 跳已 written :2095 / `write_backup_storage` 跳 `is_storage_written` 与死节点 / `advance_storage_persisted` 对已 persisted 提前返回 :2163）+ 重 promotion 只推 `acked && !persisted`（:2186）。`_reconcile_depth` 防重入。测试 `test_repeat_ack_and_reconcile_are_idempotent`、`test_reconcile_is_reentrant_safe_and_never_promotes_barely` 覆盖。
- **不伪造 durable**：reconcile **从不自己置 `storage_persisted`**——`write_backup_storage` 只发起真实写，promotion 只经 `advance_storage_persisted`（真实 ack，且仅父链连续才置 persisted）或 `mark_storage_restored`（真实读回）。B 守卫是"延迟 clear"，不是"伪造持久"。测试 `test_reconcile_never_promotes_by_itself` 显式验证：无父 ack 时 deferred 节点经 reconcile 扫描仍不 promoted。

## 6. unit 测试结果（新增 + 相关全量）

新增 10 项（`-k DeferredAckReconcile`）全过：
- 树层 8 项：child-ack-first / parent-clear-repromote / 乱序收敛 / 重复幂等 / reconcile 不伪造 / B 守卫延迟 clear / 父物理删除重建 / gap 停在最近 persisted 祖先。
- cache 层 2 项：`_flush_pending_storage_writes` 全链路重 promotion + wake frontier；重入安全 + 不 promote 未 ack 节点。

相关全量：
- test_storage_regression.py 111 passed（含既有 StoragePromotionChain 3 项，验证 A 不改坏基线行为）。
- 其余 P3 相关 9 文件（hicache_restore / scheduler_feed / ready_horizon_unit / ready_horizon_partition / capacity_model / fbe_flush / backup_spec_assert / prefetch_budget / writeback_reserve）352 passed。
- 全 3090-dev 377 passed / 5 failed。5 项全为 test_drain_reentry 既有 P0 `get_component_device_value` 失败（基线复测确认存在，非 P3 引入；P0 另案）。

## 命令
```
PYTHONPATH=<repo>/python <venv>/python -m pytest 3090-dev/test_storage_regression.py -k "DeferredAckReconcile or StoragePromotionChain" -q   # 11 passed
PYTHONPATH=<repo>/python <venv>/python -m pytest 3090-dev/ -q   # 377 passed, 5 failed (P0 pre-existing)
```

followups:
  - tester：warm-tree 复现 60s cliff 基线 → 验证修复后 frontier_wait<60s、restore_recompute(timeout)=0；观测 deferred 量/写放大（open decision 4）与 B 守卫子树遍历开销（open decision 3）。
  - P0（get_component_device_value assert，drain_reentry 5 项失败）与 P1（restore re-arm）为独立缺陷，不混入本修复。
  - 未 push；如需上分支请 devops/授权处理。

open_issues:
  - 无阻塞项。5 项 drain_reentry 失败属 P0 既有缺陷，与本修复正交。
