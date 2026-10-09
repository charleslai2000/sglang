# phase2-hicache-design-coder-e14-01 — 候选 A：L3 持久性谓词覆盖 restore 链（K=32 evict 死锁修复）

## 1. status

**done** — 候选 A 已实现（architect e10 定稿语义 + 4 硬约束逐条落实）；8 新测 RED→GREEN；本机 torch-free 109 执行全绿 + torch 侧 115/115；远端 3090 115/115；双侧 md5 4/4 一致；引擎未启动（远端 GPU 15 MiB、0 引擎进程）；未 commit 未 push。

## 2. 实现形态（字段/谓词设计）

按 architect e10 定稿公式（报告 L56）：**统一谓词 `is_l3_durable(node) = storage_persisted OR storage_restored`**；`storage_restored` 为节点上的 restore 来源标志（restored 是事件来源、is_l3_durable 是当前事实——专家命名规范），`mark_storage_restored` 置位。

- `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py`
  - `UnifiedTreeNode.__init__` 新增 `storage_restored: bool = False`（:149-154，注释给出统一谓词公式）
  - `mark_storage_restored(node_id)`（:1988-1993）：restore 来源置位
  - `is_l3_durable(node_id)`（:1995-2002）：`node.storage_persisted or node.storage_restored`
  - `_split_node` 四标志双向传播（:1113-1119）：storage_written / storage_acked / storage_persisted / **storage_restored**（E13 同族）
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - `is_l3_durable` 缓存层包装（:1830-1835）
  - `_handle_prefetch_result` restore 标记（:2252-2262）：insert_host 成功分支、commit_hicache_transfers 之后、`inserted_host_node is not None` 才 `mark_storage_restored`
  - hollow 命中 info 日志（:761-770）：`[P2A] ... evt=hollow_evict node=%d freed=%d`
  - 三处谓词替换 + frontier_anchor_ready 镜像扩展（见 §3）

**设计决策记录（实现中裁决）**：write-ACK 来源取 `storage_persisted`（acked+父链连续）而非裸 `storage_acked`——M2 既有钉（test_drain_reentry `test_drain_backup_unpersisted_node_does_not_wake`）明确 acked-但-未-promoted 节点不得 wake（父链 L3 写仍在途时 wake = 把预取发进不完整链 = M2 premature-wake 同类）；restored 来源无父链要求（restore 本身读回即验证了跨度）。这正是 architect e10 公式 `is_storage_persisted or is_storage_restored` 的原意，单标志 acked-OR-restored 形态与 M2 钉冲突，弃用。

## 3. 4 硬约束逐条落实证据（file:line）

| 约束 | 落实 | 证据 |
|---|---|---|
| 1. 标记在完整成功之后 | insert_host 成功 + commit_hicache_transfers（required KV/Mamba）完成后才标；shortfall 只标 completed 前缀（inserted 节点 = `fetched_key=prefetch_key[:completed_tokens]` 精确跨度）；hybrid_discard 早退不标；host_insert_dropped 分支不标 | unified_radix_cache.py:2238-2262（else 分支）、:2195-2201（buffer 早退）、:2232-2237（dropped 分支）、`_check_hybrid_prefetch_result` 早退 :2164-2182 |
| 2. split 双向继承 | 原 node 四标志 → 两段都继承；partial restore 只标 prefix（suffix 未标，自然保持 False） | unified_tree_core.py:1113-1119；测试 test_shortfall_marks_only_completed_prefix / test_persisted_split_keeps_all_storage_flags_on_both_fragments |
| 3. stale durable 非 correctness 前提 | 检查结论：l3_durable 未被任何路径用于"跳过未来 backup"——四处消费点（hollow fallback / prefetch_gate_ok / _wake_frontier_waiters / frontier_anchor_ready）均为 evict/读门/wake，无写路径跳过；`collect_storage_gap` 只查 storage_written/persisted，从不查 storage_restored → **miss 清除钩子"如适用"= 不适用**，未加（最小改动）；陈旧降级 = hollow → L3 miss → recompute（architect 已容忍语义） | 钉：test_l3_durable_does_not_skip_future_backup（restored 节点仍被 gap fill 重新收集重写） |
| 4. 命名 l3_durable + 统一谓词 | 谓词名 is_l3_durable（非 storage_restored）；全部 hollow/eviction/gate/wake 判断只看该谓词 | unified_radix_cache.py:830（hollow）、:1811（prefetch_gate_ok）、:2457（_wake_frontier_waiters）、:1848（frontier_anchor_ready 镜像扩展）；unified_tree_core.py:2002 |

**三处替换 + 镜像扩展**：
- hollow fallback `elif self.tree_core.is_storage_persisted(node_id)` → `is_l3_durable`（:830）
- `prefetch_gate_ok` `or self.is_storage_persisted(node_id)` → `or self.is_l3_durable(node_id)`（:1811）
- `_wake_frontier_waiters` `if not self.tree_core.is_storage_persisted(node_id)` → `is_l3_durable`（:2457）
- `frontier_anchor_ready`（:1848，dispatch 三处之外的**镜像一致性扩展**）：其 docstring 自述 "Mirrors _wake_frontier_waiters"，wake 谓词升级后镜像必须同步，否则 gate/wake/mirror 三方不一致（M2 修复的同类漂移）；T11 容量 wake 对 restore 链 anchor 的唤醒即 fd99588b 型 frontier spin 的解除路径

**日志点**：`_evict_device_leaf_storage_backed`（:761-770）`[P2A] ts_ms=... evt=hollow_evict node=%d freed=%d`（freed = result.tracker[FULL]）。实测输出：`INFO [P2A] ts_ms=... evt=hollow_evict node=42 freed=2048`。K=32 验收将看到 `[1600] ... evt=hollow_evict freed=16374` 形态。

## 4. 新增测试（8 测 = dispatch 6 项；全部 torch-free，RED→GREEN）

| 测试 | 对应项 | 钉住语义 |
|---|---|---|
| test_full_restore_marks_inserted_node_durable | 2 | 完整 restore：insert_host 成功 + commit 后 → mark_storage_restored(inserted) 恰一次 |
| test_shortfall_marks_only_completed_prefix | 1 | 短 fall：insert_host 只收到 completed 前缀（inserted_key_len=4），只标 prefix 节点，suffix 不标 |
| test_hybrid_discard_marks_nothing | 3 | all-or-nothing sidecar 短fall → 整体丢弃 → 不标、不进 insert |
| test_restored_durable_split_keeps_both_fragments_durable | 4（K=32 形态） | 真实树：restored 节点 split → 两段 storage_restored + is_l3_durable |
| test_persisted_split_keeps_all_storage_flags_on_both_fragments | 4（E13 同族） | 真实树：written/acked/persisted 四标志两段继承 + 写源谓词保持 |
| test_unmarked_split_stays_unmarked | 4（安全钉） | 纯 recompute 链 split 后永不 hollowable |
| test_hollow_evict_breaks_deadlock_on_restored_chain | 5（如适用形态=K=32 单元钉） | walker 唯一候选为 restored 链（持久性标志 False）→ backup 失败 + drop 被拒 → hollow 释放 2048 |
| test_no_hollow_for_pure_recompute_chain | 5（安全钉） | 无任何 L3 副本 → 不 hollow（设备层是唯一副本） |
| test_l3_durable_does_not_skip_future_backup | 5（约束 3 钉） | restored 标记不清除任何写路径守卫：gap fill 仍收集重写节点 |
| test_write_ack_marks_l3_durable | 6 | advance（写 ACK）→ persisted → is_l3_durable True（写源不退化） |

RED 证据（修复前，测试已就位）：8 测失败——3 处 `AttributeError: 'UnifiedTreeCore' object has no attribute 'is_l3_durable'` 系 + 2 处 `[] != [77]` 标记缺失 + `[] != [42]` hollow 未触发 + `True is not false` 类断言（`test_hollow_evict...`）；既有 105 全部保持绿。GREEN：全绿。

## 5. 证据（验证命令与真实输出）

- 本机 torch-free（plain python3，stubenv，逐文件独立进程——两测试文件各自安装进程级 stubenv，同进程互斥属既有设计）：`python3 -m unittest test_drain_reentry` → **Ran 14 OK**；`test_hicache_restore` → **Ran 43 OK**；`test_storage_regression` → **Ran 58 OK (skipped=6)**（6 skip = 既有 torch-gated 两 class；执行 109 = 99 旧 + 10 新）
- 本机 torch（sglang-venv，torch 2.13.0+cu129）：`python -m unittest test_drain_reentry test_hicache_restore test_storage_regression` → **Ran 115 tests in 0.063s OK**（105 基线 + 10 新）
- py_compile 4 文件：本机 venv + plain python3 双解释器 **PY_COMPILE_OK**
- hollow 日志实测（INFO 开启）：`INFO [P2A] ts_ms=1788134108113 evt=hollow_evict node=42 freed=2048`
- 远端 3090（root@175.155.64.171:24052，`/root/sglang-b1-continuity/`，sglang-patch env，torch 2.13.0+cu130）：REMOTE_PY_COMPILE_OK + **Ran 115 tests in 0.083s OK**
- **双侧 md5 4/4 一致**：unified_tree_core.py `6cbd9452…`、unified_radix_cache.py `08a1f1ea…`、test_storage_regression.py `85e19321…`、test_drain_reentry.py `8fee04cc…`（旧值 a2721792/b77e23ac/95037123/f88220a9）
- 引擎未启动：远端 `ps` 0 引擎进程、nvidia-smi memory.used = 15 MiB（部署全程未触碰引擎）

## 6. summary

- 根因（architect e10）：唯一 evictable 候选 [1600]（16374 tokens）为 43s 前从 L3 restore 的链，`is_storage_persisted=False`（restore 路径从不标记）→ hollow 拒绝 → 三段死锁 → OOM。
- 修复 = 统一谓词 `is_l3_durable = storage_persisted OR storage_restored`：restore 成功（`_handle_prefetch_result` insert_host 成功 + commit 后）标记 inserted 节点；split 四标志双向传播；hollow / prefetch_gate_ok / _wake_frontier_waiters 三处谓词替换 + frontier_anchor_ready 镜像扩展；hollow 命中补 `[P2A] evt=hollow_evict` info 日志。
- write 源取 persisted（非裸 acked）：M2 既有钉（acked-未-promoted 不 wake）与 architect 公式一致；不触碰锁生命周期 / walker / L3 写入 / ack 路径。
- 未 commit 未 push；工作树保持 e11-e14 累积未提交状态。

## 7. followups（交接给 tester/orchestrator）

1. **K=32 复测**（tester，需部署后调度）：fresh ns 2b，同 driver 配方（8 turns × 32，25 分钟护栏）；判据 = 越过旧崩溃点 387s 无 OOM + 签名 0 + 优雅退场 + 0 残留；观测 = 原 1600×3 警告处应变为 `[P2A] evt=hollow_evict node=1600 freed≈16374`（新日志点的直接验收）。
2. **K=16 回归**：上次 10 次 walker-wall 应消失或 hollow 化；K=1 回归 restore 路径 12/12 无行为变化。
3. 远端已同步 4 文件（md5 4/4），tester 复测直接用 `/root/sglang-b1-continuity/` 即可，无需再部署。
4. 集成/性能要求（按 Division of labor 写入）：集成覆盖点 = K=1/16/32 三级回归 + 双侧（本机 venv / 远端 3090）md5；性能场景 = hollow 事件计数 vs 旧 warning 计数对比、restore→recompute 转化率不升。

## 8. open_issues

- split 于 L3 写 in-flight 窗口（storage_written=True 未 ack）时，prefix 新节点继承 storage_written 后 ack 只路由到 suffix（child id 保留）——prefix 页确在 L3（同批写入覆盖）但永不 promoted；降级安全（页在 L3、不 hollow 误判、不 corruption），且下一 gap fill 的 dedupe 守卫跳过它是事实正确的。与 architect E13 批准方向一致；如需精确 promoted 需为 storage 写路径加 ReplaceWriteThroughOnNodeSplit 同类 action（范围外，登记）。
- L3 GC / namespace 重建后的陈旧 durable：与现有 ack 标志同型，miss 降级 recompute 已容忍（architect open_issues 确认）；storage_existence_cache 填充模式（hollow 谓词直查 L3 页存在性）为长期项（architect followups 3）。
- host 池精确占用核算探针（architect followups 3）仍缺，不影响本修复（A 不依赖 host）。
