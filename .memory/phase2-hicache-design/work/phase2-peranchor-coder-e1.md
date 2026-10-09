# phase2-peranchor-coder-e1 — P1 epoch 门 per-anchor 修正 + no-material fast-forward（coder 实现）

```text
status: done
artifacts:
  - commit 183001f860 （本地，未 push）：仓库 /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt，分支 3090-24g-opt，HEAD 由 3c71553a20 -> 183001f860
  - 生产改动 6 文件 + 测试 4 文件（详见下方 diff 摘要）
  - 报告：本文件
evidence:
  - 全部受影响 unit/state-machine 测试通过：300 passed（test_hicache_restore / test_hicache_restore_scheduler_feed / test_p3_warmtree_hol / test_ready_horizon_unit / test_storage_regression）
  - 全 3090-dev/ 目录：406 passed，5 failed 为 BASE 预先存在（test_drain_reentry _FakeTreeCore 缺 get_component_deviation，已用 git worktree 在 HEAD=3c71553a20 复核确认，与本次改动无关）
  - 运行命令：PYTHONPATH=python /home/charles/sglang-venv/bin/python -m pytest 3090-dev/<file>.py
summary:
  见下方分节：①per-anchor version 实现与最终语义；②no-material fast-forward 实现；③统一状态机骨架衔接；
  ④测试结果；⑤diff 摘要
followups:
  - tester 承接 P1 deterministic workload 6 点验证（ledger:2114）：P3 并发 ACK/reconcile 仍大量发生 /
    无关链 epoch-version 变化不再解除 MISS / revoked:miss churn 保持低 / restore_success-storage_hit 不被误杀 /
    legitimate 同链变化后可重新 restore / too_short 不回退
  - tester 验证 no-material fast-forward（正常有物材请求不误 forward；epoch/version 变化后可重新获得 restore eligibility）
  - 随后 tester 跑完整 2h L3 ON warm-tree soak 按原完整 Gate 验收
open_issues:
  - NO_L3 cursor 已同步改锚 version（architect Open Decision 4 建议项，本轮已做，成本低）
  - clear_storage_durable 已采纳 bump 锚 version（Open Decision 1）；实现期测试未发现 clear->re-arm->re-probe->clear 新环
    （re-probe 若仍 miss 会重新记录锚 version，负证据自我续期）
  - 统一状态机骨架未实现（用户裁决 ledger:2113 不做大重构），仅以 FrontierAnchorInfo + per-anchor 语义作为骨架态 1/3 首例落地
```

## 1. per-anchor version 实现与最终语义

### 1.1 数据/接口（unified_tree_core.py）

- `UnifiedTreeNode.storage_version: int = 0`：per-anchor 单调版本，初始 0。
- `_bump_anchor_storage_version(node_id)`：对 node 的 version +1（仅该节点自身链的 durability 事件）。
- `anchor_storage_version(node_id) -> int`：读该锚 version；node_id 为 None / 节点已删 / 不在 arena → 返回 0（self-heal 到 re-match from root，等价新候选）。
- `mark_storage_restored(node_id)`：restore 读回 → bump 该 node 的锚 version。
- `_promote_persisted_subtree(node)`：写 ack promotion → bump 该 node 的锚 version（每次被 promotion 的节点各 bump 自身）。
- `clear_storage_durable(node_id)`：实际清除 durability 信念时 bump 该锚 version；被 P3 B 守卫（有 deferred-ACK 后代）抑制时不 bump。
- 全局 `_bump_l3_publish` / `l3_publish_epoch` **保留**，降为纯诊断统计，不参与任何门判定。

### 1.2 miss 判据改锚（scheduler.py + hicache_restore.py）

- 记录（scheduler `_feed_restore_terminal`，REVOKED_MISS+genuine_miss）：`hicache_restore_miss_epoch = anchor_storage_version(last_host_node)`（per-anchor，不再全局）、`hicache_restore_miss_anchor = last_host_node`、`hicache_restore_miss_generation`。
- re-arm（T6，scheduler admission）：`miss_rearm_allowed(miss_anchor_version, current_anchor_version, miss_generation, current_generation, miss_anchor, current_anchor)`。
- `miss_rearm_allowed` 最终语义：
  ```
  rearm_allowed =
      miss_version is None（防御）
      OR (miss_anchor != None and current_anchor != None and current_anchor != miss_anchor)  # 重锚定=新候选
      OR current_version > miss_version                                                   # 同锚实质变化
      OR current_generation != miss_generation                                            # 身份变化
  ```
  移除 `current_epoch > miss_epoch`（全局）。无关链写 ack / restore 只 bump 全局诊断计数，**不**再解除本请求 MISS。
- `_apply_restore_event` 离开 MISS 态时清 `miss_epoch`/`miss_generation`/`miss_anchor`（负证据随 episode 结束丢弃）。

### 1.3 与全局 epoch 的关系

全局 `l3_publish_epoch` 从所有 re-arm / 负缓存 cursor 判定移除，仅保留作诊断统计（日志 / M3 refill 触发仍读它——refill 触发是粗粒度可用性信号，与 per-anchor re-arm 门正交，architect 设计意图内）。

### 1.4 anchor 生命周期处理

- **clear（durable 变非 durable）**：bump 该锚 version（实质状态变化，按同一规则解除/重挂依赖它的负证据）；P3 B 守卫抑制时不 bump。
- **物理删除/evict**：`anchor_storage_version` 返回 0 → miss/NO_L3 记录读到 0，且 ready_horizon `entry_cleared` 对"declined anchor 已删（anchor 传入 None）"返回 True（self-heal 到 re-match from root，等价新候选，与 `frontier_anchor_ready` node_exists->True 一致）。
- **重新锚定 root/换锚**：`miss_anchor != current_anchor` → 新候选，旧证据作废，允许 re-arm。

## 2. ready-horizon NO_L3 负缓存 cursor（同病同步改锚）

architect Open Decision 4 建议本轮同步，成本低，已做：

- `NegativeCacheEntry` 新增 `anchor: Optional[int]`。
- `_park_ready_decline` / `_feed_restore_terminal` 的 NO_L3 park：`epoch_cursor = anchor_storage_version(anchor)`（per-anchor，不再全局），并记 `anchor`。
- `entry_cleared`：NO_L3 分支改为 per-anchor——`entry.anchor != None and anchor is None`（锚已删→self-heal 放行）；`anchor != entry.anchor`（重锚定→放行）；同锚则 `anchor_version > epoch_cursor` 才放行。`entry.anchor is None`（无锚上下文）时**不放行**（无绑定可验证，保守，且绝不被全局 epoch 放行）。
- `staging_candidates` 从 `view.req.last_host_node` 派生当前锚 + `tree.anchor_storage_version` 传入。
- M3 refill **触发**（`epoch_event`）仍用全局 `l3_publish`，不改。

## 3. no-material fast-forward 实现

### 3.1 落点

`_prefetch_kvcache` 的 GATE_SKIP_FRONTIER 入口（scheduler，原 :3064-3068），在 `prompt_can_qualify_for_prefetch` 之外**并列**加一道 no-material 判定。`prompt_can_qualify` 只表示"后缀几何可达阈值"，不等于"存在可等待物材"。

### 3.2 5 事实判定（hicache_restore.py `no_material_fast_forward(info: FrontierAnchorInfo) -> bool`）

纯函数，全部 5 事实缺席才 True（直接 ADMIT_RECOMPUTE），任一存在则保留 frontier wait / P3 reconcile：

1. `host_material`：host_hit_length > 0（host copy 存在）→ 不 forward。
2. `storage_material`：锚 is_l3_durable 或 is_root → 不 forward。
3. `pending_durable_ack`：该锚 `is_storage_written` 或 `ongoing_backup` 含该锚（L3 写在途，其 ack 可使锚 durable）→ 不 forward。
4. `deferred_durable_desc`：该锚 `has_acked_descendant`（storage_acked && !storage_persisted 后代，P3 reconcile 补写源）→ 不 forward。
5. `restorable_epoch_change`：该锚 `ongoing_load_back` 在途 restore 读回，或 `anchor_storage_version > 0`（该锚有 L3 durability 历史，如刚被 clear，re-restore 可能可兑现）→ 不 forward。

**避免 storage_hit=0 => recompute 简单化**：5 事实逐项独立判定，任一在途生产者 / deferred 后代即保 wait——P3 HOL 修复（依赖 deferred 补链 + frontier wait）不被破坏；有物材请求不误 forward。

调度器侧 `_no_material_fast_forward_for(req, anchor)` 组装 5 事实并委托纯函数；命中时 `_log_restore_recompute(req, "no_material")` + `return`（不 register_frontier_waiter）。仅 cache mode（buffer mode 读 hash 不读锚，GATE_SKIP 已是 final recompute，architect Open Decision 3）。

### 3.3 与 P3 reconcile 共存

有在途生产者 / deferred 后代 → 保持既有 frontier wait + A+B 补链 + clear 守卫，语义不变（测试 `test_p3_warmtree_hol.py` 通过确认无回归）。

## 4. 统一状态机骨架衔接（用户裁决：先统一语义不大重构）

本轮**不重写** restore 状态机，但接口按 architect 统一契约（phase2-re-unified-architect-e1 §3）落地首例：

- **per-anchor 修正 = 骨架态 1（definitive miss）特例**：`anchor_binding=(锚, version)`、`rearm_condition=同锚 version 前移 or re-anchor or generation 变`、`forward_fallback=ADMIT_RECOMPUTE`。既有 `miss_rearm_allowed` 只把判据改锚，状态机转换（T5/T6/T9/T12/T13/T15）结构不变。
- **no-material fast-forward = 骨架态 3 特例**：`FrontierAnchorInfo`（frozen dataclass）即该态 `anchor_binding` 快照；`no_material_fast_forward` 即 `has_inflight_producer()==False -> forward_fallback()` 的落地；5 事实字段天然是负证据/在途生产者结构的结构化载体。
- 未来扩展（too_short / capacity / durable-frontier）可复用同一契约逐步填充，不排斥。

## 5. 测试结果

全部受影响测试通过（PYTHONPATH=python /home/charles/sglang-venv/bin/python -m pytest）：

- test_hicache_restore.py：含新增 StickyMissRearmGateTests（per-anchor 语义：同锚 version 前移放行 / 全局 epoch 前进不放行(冻结根因回归守卫) / re-anchor 放行 / 幂等）+ NoMaterialFastForwardTests（5 事实全缺席 forward / 任一存在不 forward / 非 storage_hit=0 简单化）。
- test_hicache_restore_scheduler_feed.py：新增 P1StickyMissSchedulerFeedTests（全局 epoch 前进不 re-arm 同锚 / 同锚 version 前进 re-arm / re-anchor re-arm / generation 变 re-arm）+ NoMaterialFastForwardSchedulerTests（5 事实调度器侧组装）。
- test_ready_horizon_unit.py：NO_L3 负缓存改 per-anchor（同锚 version 前移放行 / 全局 epoch 前进不放行 / re-anchor 放行 / 无锚上下文不放行 / fuse 仅安全界）+ DeterministicMissParkTests 改锚（含无关链全局 bump 永不清除 park 回归守卫）。
- test_storage_regression.py：新增 PerAnchorVersionTests（真实 tree core：promotion/restore 只 bump 自身锚 / 无关链不影响 / clear bump / B 守卫抑制 bump / 死锚读 0）+ NoMaterialFastForwardUnitTests。
- test_p3_warmtree_hol.py：P3 收口无回归（2 passed）。

**汇总**：受影响 5 文件 300 passed；全 3090-dev/ 406 passed，5 failed 均为 BASE 预先存在（drain_reentry `_FakeTreeCore` 缺 `get_component_deviation`，git worktree 在 HEAD=3c71553a20 复核确认，非本次引入）。

## 6. diff 摘要（commit 183001f860）

生产改动：
- unified_tree_core.py：+62 行（storage_version 字段 / _bump_anchor_storage_version / anchor_storage_version / mark_storage_restored+restore bump / _promote bump / clear bump）。
- unified_radix_cache.py：+30 行（anchor_storage_version / has_acked_descendant / is_storage_written 三个 proxy）。
- hicache_restore.py：+113 行（FrontierAnchorInfo + no_material_fast_forward + miss_rearm_allowed 签名改锚）。
- ready_horizon.py：+110 行（NegativeCacheEntry.anchor / entry_cleared per-anchor / subscribe_decline / staging_candidates）。
- scheduler.py：+200 行（miss 记录改锚 / NO_L3 park 改锚 / T6 re-arm 改锚 / GATE_SKIP no-material 判定 + _no_material_fast_forward_for + _anchor_version_or_zero）。
- schedule_batch.py：+8 行（Req.hicache_restore_miss_anchor 字段）。

测试改动：test_hicache_restore / test_hicache_restore_scheduler_feed / test_ready_horizon_unit / test_storage_regression 更新旧全局语义断言为 per-anchor + 新增上述测试。
