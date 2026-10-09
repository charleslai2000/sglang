# phase2-peranchor-diagnose-architect-e1 — per-anchor + no-material FAIL 内部因果诊断（read-only）

```text
status: done
artifacts:
  - 本报告（read-only 架构诊断 + 修复方向，未改任何代码；spec 供 coder 实现）
evidence:
  - tester: work/phase2-peranchor-tester-e1.md（3/6 FAIL + D2.1 误 forward + 2 产品缺陷候选）
  - coder: work/phase2-peranchor-coder-e1.md（commit 183001f860 实现）
  - 先验: work/phase2-re-unified-architect-e1.md（统一模型）、work/phase2-churn-rebound-architect-e1.md
  - 代码（只读）: scheduler.py / scheduler_components/hicache_restore.py /
    scheduler_components/ready_horizon.py / mem_cache/unified_radix_cache.py /
    mem_cache/unified_cache/unified_tree_core.py
  - 证据日志（行级 grep + 局部 Read，无跨距正则）:
    /tmp/peranchor-check/engine-gate3-peranchor.log 中 rid
    98c75a55 / 1c417fdc / 1b8c727（误 forward）/ f4b42595（too_short 最差 69 次 @13ms）
summary:
  Conclusion
  Current Architecture
  Problem / Forces
  Q1-Q4 逐问诊断
  Proposed Architecture（修复方向 + 优先级）
  Migration / Impact
  Alternatives
  Open Decisions
```

## Conclusion（一页裁决）

1. **Q1 = 真缺陷（re-anchor 竞态结构根因），最小修复不破坏 no-material 主收益**。误 forward 的根因**不是**测试者假设的"同 turn 内 re-match 换 gate-ok 更深锚"（该路径已在 3 案例中被日志排除），而是：**no-material 5 事实判定的锚粒度（node_id）与实际 restore 覆盖范围（页范围）在物理节点维度错配**——`last_host_node` 是 host 树匹配锚（同一 host 前缀可跨多代 L3 写复用），其 `is_l3_durable`/`is_storage_written` 是"该节点 KV 的"布尔事实，而 `prefetch_from_storage(query)` / `_storage_hit_query` 是**页级内容寻址查询**。当浅锚节点非 durable 但**请求前缀的更深页已 durable**（host 锚在 L3 写 ack 更新后被拆成新浅节点），5 事实全缺失而实际 restore 能命中 7168 页 → 误 forward。3 案例（98c75a55 / 1c417fdc / 1b8c727）全为"判定时刻 storage 事实存在但锚节点错位漏检"，同 turn 内后续由 T11 capacity wake 触发 re-issue（不需要 re-match、不需要新区块），最终 restore_success。**最小修复 = no_material 判定前先解析到"请求前缀在其 last_host_node 下能 query 到的最深耐久覆盖锚"，再判 5 事实（尤其事实 2），或直接对该锚前缀做一次低成本 storage hit query**。无物材请求解析到根仍全缺失 → 立即 forward 主收益保留。

2. **Q2 = 交互为主（too_short 回退是 per-anchor 的 WAIT 集合漂移 + 保底守卫失效），方差为辅**。per-anchor 使 MORE 请求进入 WAIT[DEVICE_QUOTA]（MISS 不带 sticky、纯容量客户新增 139 个），f4b42595 是纯容量客户（无 miss、无 sticky、`host_hit_length=0`）——其 `requested=29 < prefetch_page_size` 使 `query_storage_hit_length` 在 `prefetch_anchor_info` 之前 **prefetch_threshold 门提前返回 0** **根本不进入 prefetch_from_storage**，因此 too_short 统计的 69 次**全部来自 WAIT wake 时的 `declined_too_short` re-issue 回环**，而 `_restore_wait_capacity_fits` 的 DEVICE_QUOTA 保底（`prompt_can_qualify_for_prefetch` 用 `max(prompt_len - host_hit_length, 0)` 与 prefetch Length 的 `len(new_input_tokens)` 对齐）**不拦它**。修复 Q1 不解决 Q2（Q1 只收窄 no-material 误 forward，f4b42595 不进 no-material 路径）。**需独立脚手架修复**（`_restore_potential_for` 的同门短路 / WAIT 入口 manifest 判定），顺带降低 845 DEVICE_QUOTA WAIT。

3. **Q3 = 残留 spurious re-arm 源主要是 (d) T6 门语义收紧后 WAIT 集合变化带来的 sticky 不适用**（per-anchor 让 sticky miss 从"全局 epoch 秒级必然放行"收紧到"同锚 version/re-anchor/identity"，直接效果 = MISS_RECOMPUTE 态从"锁本前缀窗口内可续量"变为"恢复误探"部分转成同链合法 re-arm (129 vs P1 24)，最差 offender 36 的 22 个 <1s 紧循环是**容量驱动兜底**（`_restore_wait_capacity_fits` 的 `charge<available` 兜底被纯容量客户反复命中 → WAIT→RESTORING→too_short→WAIT），**不是 spurious**；Q2 修完即随降。另一残留源是修复 Q1 前的 no-material 误 forward 转成 recompute 再被同链新请求 re-probe（Q1 修完后减少）。**(a) 同锚 version 前移仍被无关链 bump 源不存在**（tree_core 逐节点 bump 已验证），**(b) promotion 逐节点 bump 与请求前缀粒度错配源不存在**（bump 是"该节点自身链"，错配在 no-material 判定不在 re-arm）。

4. **Q4 = no-material 吸收是 restore_success 下降主因（保守保 frontier wait 可恢复大部分），per-anchor 过严次因**。80 次 no-material 吸收掉"有物材但锚节点错位"的请求直接 recompute（其中 3 个确定性误 forward，其余因物材判定窗口内晚到淘汰）；frontier_wait 215→11 说明 no-material 判定把大量本会走 frontier wait 的请求 fast-forward。修复 Q1（保守保 frontier wait）把 80 次里"判定时刻物材已在/在途"的子集还给 frontier wait → restore_success 大致可回到 P1 水平（估计 40+）。

5. **6 点复测判据：修复 Q1+Q2 后 6 点全部 PASS 是可达的**（点 3 需随 Q2 观察，点 4 需 Q1+RESTORE 面护栏，点 6 只需 Q2），但**目标运行**可能因修复后的 `prefetch_gate_ok`（被 no-material 收纳）而 over-approximate，**存在回归到 P3 式 RESTORE 面（frontier wait）未发生但物材在途的边界**，因此复测**必须带** Q1 的判定（或至少带 no-material 的 re-probe 阻尼）否则可能"过 6 点但引入新 churn"。

---

## Current Architecture（证据核实）

### 1. per-anchor 后 re-arm 门语义（已核实）

- **miss_rearm_allowed**（hicache_restore.py:295-335，T6 admission 调用 scheduler.py:4685-4694）:
  `rearm_allowed = miss_version is None OR (anchors 都存在且 current != miss，新候选) OR current_version > miss_version（同锚实质变化）OR generation 变`。
  **全局 l3_publish_epoch 移除出门判定**（tree_core.py:2130-2151 只留诊断统计）。
- **miss 见证记录**（scheduler.py:3247-3252）：`hicache_restore_miss_epoch = anchor_storage_version(req.last_host_node)`、
  `miss_anchor = req.last_host_node`、`miss_generation = session_generation`。
- **NO_L3 ready-horizon 负缓存**（ready_horizon.py:113-132 NegativeCacheEntry + :309-382 entry_cleared）：同样改 per-anchor
  （`anchor`/`anchor_version` 前移才放行；`entry.anchor is None` 时**只看 identity 变化**放行）。
- **version bump 点**（tree_core.py）：`mark_storage_restored`(node) :2128 / `_promote_persisted_subtree`(node) :2298 /
  `clear_storage_durable`(node) :2209（B 守卫抑制时无 bump）/ `advance_storage_persisted` 经 `_promote_persisted_subtree`。
  每次 bump 只在**该 node 自身**的 storage_version += 1；promotion batch 只对**实际 promotion 的节点**bump。
  全局 `_bump_l3_publish` 仍每次 promotion/restore bump 一次（诊断计数）。

### 2. no-material fast-forward 判定（已核实，scheduler.py:3818-3895 + hicache_restore.py:203-267）

- 落点：GATE_SKIP_FRONTIER（scheduler.py:3066-3091），`prompt_can_qualify_for_prefetch` 内侧。
- `prefetch_gate_ok`（radix_cache.py:2345-2357）= `is_backuped(anchor) OR is_root(anchor) OR is_l3_durable(anchor) OR (buffer_mode and has_hash)`。
- 5 事实 `no_material_fast_forward(info)` 全部缺席才 True：
  host_material（`req.host_hit_length>0`）/ storage_material（`tc.is_l3_durable(anchor) or tc.is_root(anchor)`）/
  pending_durable_ack（`tc.is_storage_written(anchor)` 或 `ongoing_backup` op 的 node==anchor）/
  deferred_durable_desc（`tc.has_acked_descendant(anchor)`）/ restorable_epoch_change（`ongoing_load_back` 含 anchor 或 `anchor_storage_version(anchor)>0`）。

### 3. RESTORE 查询路径（已核实，radix_cache.py）

- `prefetch_from_storage(req_id, last_host_node_id, new_input_tokens, last_hash, prefix_keys, ...)`（:2600+）：
  用 `tree_core.prefetch_anchor_info(last_host_node_id)` + `new_input_tokens` 构造 `RadixKey(...).page_aligned(page_size)`，
  `prefetch_length = len(prefetch_key)`；`prefetch_length < prefetch_threshold` → `declined_too_short`（:2654-2667）。
- `prefetch_threshold` 与 `page_size` 的关系（非同一：「the number of tokens」与「page of kv」）；
  关键量 `query_storage_hit_length`（:2536-2579）在 `len(prefetch_key) < prefetch_threshold` 时**提前返回 0**（:2559-2560），
  根本不生成 `PrefetchOperation`。
- 真实 restore（cache mode）`_finalize_prefetch`（:2939-2999）：fetch 后 `insert_host` → `mark_storage_restored(inserted_node)` → READY → admission 消费 → `restore_success`。

### 4. WAIT/WAKE 回环（已核实）

- WAIT[DEVICE_QUOTA] 的每 pass wake 在 `_reconcile_restore_states` step 4（T11，scheduler.py:3172-3217）：
  `capacity_wake_applies(reason)`（DEVICE_QUOTA 需 host material? 见下）`and _restore_wait_capacity_fits(req)` 则
  `CAPACITY_FITS → RETRY_PREFETCH → _prefetch_kvcache(req, ...)`；若 re-issue 返回 `declined_too_short` 且状态归 NONE → `_log_restore_recompute(req,"too_short")`。
- `_restore_wait_capacity_fits`（:3721-3805）：DEVICE_QUOTA 分支 `if not prompt_can_qualify_for_prefetch(len(full), host_hit_length): return False`（:3763-3769，too_short 保底门）；
  然后 `promotion_wait_blocked(...)` + `charge < available_and_evictable`（:3793-3805 capacity 兜底）。
- **保底门与 prefetch 的实际 Length 不一致**（重要）：
  - re-issue 的 actual `prefetch_length` 来自 `prefetch_from_storage`：`RadixKey(new_input_tokens).page_aligned` 后 `len()` 版对齐；
  - 保底门用的是 `prompt_can_qualify_for_prefetch(max(prompt_len - host_hit_length,0) 对 prefetch_threshold)`；
  - **但对 `host_hit_length==0` 且整 prompt 在新页内的请求，Length 的门提前在 `query_storage_hit_length` 阶段返回 0（不报告 terminal），
    而 `prefetch_from_storage` re-issue 的 `declined_too_short`（:2654-2667）才计数** → 每次 WAIT wake 重新进入
    → 每 pass 统计 too_short +1 → 13ms 循环。**此即 f4b42595 模式**。

### 5. T6 处 MISS sticky 与容量客户分流（已核实，scheduler.py:4661-4701）

- NO_TOKEN（无 token 命中）：`if enable_hicache_storage and _restore_potential_for(req):` 走 T6：
  `miss_rearm_allowed(...)` → `_apply_restore_event(ADMISSION_DENY, rearm_allowed=miss_rearm)`；MISS 且 !rearm → 保持
  MISS_RECOMPUTE（`ADMIT_RECOMPUTE` decision：继续 recompute forward），否则进 WAIT[DEVICE_QUOTA]。
- **结构洞察**：per-anchor 让"锁 MISS 恢复"只在**同锚 version 前移 / re-anchor / identity 变**发生，
  ⇒ 一个本前缀内、跨 re-run 的新 miss 会被拒（sticky）或**放行（同链合法 re-arm）**二分。
  f4b42595（无 miss、host_hit_length=0、纯容量客户）进入 WAIT[DEVICE_QUOTA] 后，因容量兜底每 pass 被唤醒 → re-issue → 13ms too_short 环。

---

## Problem / Forces

- 用户仲裁：不进 2h soak，先修（6 点判据 3/6 FAIL + D2.1 + 2 缺陷候选）。
- no-material 判断权的误差松紧：误 forward（本可 restore 先行 recompute）= 额外 recompute + restore 延迟 + 效率损失（点 4）；
  过保守（无物材仍保 frontier wait）= 回到 60s T13 空等（点 2 改善部分回退）。需在"物材判定时刻已存在但锚节点错位"与"永不 forward"之间取最小修复。
- 统一模型契约（re-unified-architect-e1 §3）已把 no-material 归为骨架态 3：negative evidence = 锚无物材 + 无在途生产者；
  本诊断确认它还需要一个**物材事实的锚解析层级**（"锚" 到底是节点还是页范围），这是统一契约里的 anchor binding 精化。

---

## Q1：no-material 误 forward 有物材请求 —— re-anchor 竞态根因与最小修复

### 结论：**判定用锚 与 restore 实际覆盖 的节点粒度错配（结构根因），不是 re-match 竞态**

先**证伪**测试者的 re-match 假设，再给出根因：

**证伪（日志证据）**：三个误 forward 案例（98c75a55 / 1c417fdc / 1b8c727）的 no_material 判定后，同 turn 的 restore（T11 cause=capacity re-issue）**都是由 WAIT 状态直接 RETRY_PREFETCH，不经 re-match**。
_reconcile_restore_states step 4 的 RETRY_PREFETCH 调用 `_prefetch_kvcache` 直接用**已在 req 上的 `last_host_node`**（T11 wake 不清 `last_host_node`），`_prefetch_kvcache` 确实每 pass 调 `init_next_round_input` 做 match_prefix re-match —— 但 `match_prefix` 的 `last_host_node` 是请求**前缀**的宿主匹配，**它不可能把"同一请求前缀"匹配到"更深的 L3-durable 锚"再"剥离出一段退宿的宿主前缀"**（re-match 只告诉你 request 前缀命中宿主前缀的哪里，而 request 前缀被宿主树复用时不会因为 L3 写 ack 把它重新拆成多个 host 节点）。

**根因（代码证据）**：`last_host_node` 是**宿主匹配锚**（写透宿主流式更新），请求的前缀在宿主缓冲树里**可能跨多个 L3 写 ack 产生的宿主节点**。L3 durability 是**节点级事实**（`storage_persisted` / `storage_restored` / `storage_written` 各节点独立），而 `query_storage_hit_length` / `prefetch_from_storage` 是**内容寻址的页级事实**（prefetch_key = new_input_tokens 的 RadixKey 页对齐 + 锚的 extra_key/cache_salt，直接对 L3 extent 查询或恢复）。因此：
- 判定用锚 = `req.last_host_node`（节点维度的布尔事实）；
- 实际 restore = 请求后缀的页范围内容寻址（可命中该锚下更深、或同前缀反复写后的新页）。

当 host 树因 D→H 提交把前缀拆出新浅节点（浅节点非 durable）+ L3 里同一内容的前缀已被更早/并行的写覆盖时，一个 `anchor_storage_version=0`、非 durable、非 backed 的浅锚会出现，而请求后缀在 L3 里实际可恢复 → 5 事实全缺失 → 误 forward。

**查询替代修复本质**：no-material 判定**不该以 `last_host_node` 的节点级布尔事实做唯一证据**，而应在判定前先把"该请求在该锚下能查询到的最深耐久覆盖"解析出来（沿锚向根走最接近根的 durable 祖先，或直接对该锚做一次低成本 storage query），再以此解析锚判 5 事实。

### 为什么 tester 假设里的"判定与 restore 用锚不同"方向对、机制错

- 方向上：判定用锚（节点）≠ 实际 restore 用锚（页范围），**确实是竞态**；
- 机制上：不是"同 turn re-match 换 gate-ok 更深锚"，而是"判定时刻锚节点错位，实际 restore 的页级内容已存在但节点的 durable 标志没挂到判定锚上"。

### 5 事实哪一事实漏检？

**漏检的是事实 2（storage_material、is_l3_durable(anchor)）**——它读的是**节点级 durable 标志**。
案例中 restore 成功恢复的 7168 页（matched=1027 来自 `insert_host` 的 host 前缀 + loaded=6141 为后缀；`prefetch_issued prefetch_length=11427`，query 命中部分缺失读到 7168）说明**页级可恢复的 L3 内容确实存在**，而 `is_l3_durable(anchor)`（判定锚节点本身 `storage_persisted`/`storage_restored`）为 False。
事实 3（is_storage_written(anchor)）同样漏检：如果写 ack 已把更深的页标记 durable 而浅锚没挂 storage_written（写发生在浅锚更深的节点上），`pending_durable_ack` 也不触发。
事实 5（`anchor_storage_version>0`）无法兜底：浅锚 version=0（新节点），无任何 version 记录 → self-heal 到 re-match-from-root 读 0，正是其"新候选"语义，**而新候选判定的代价恰恰是最差情况下的误 forward**。

### 最小修复方向（三选一，推荐 B）

**方向 A —— last_host_node 非最终锚时保守保 frontier wait**：
在 `_no_material_fast_forward_for` 前检查 `anchor_storage_version(anchor) == 0 AND is_l3_durable(anchor)==False AND 锚非 root AND 锚在 L3 写 ack 后被拆成新浅节点的可疑性` —— 本质是"无法确认永无物材"就保 wait。缺点：对`host树本来就没有L3内容`的无物材请求，任何浅锚都停 wait（恢复过保守）；它其实把"不确认=等"挂在"锚节点生命周期"上，不精确。

**方向 B（推荐）——判定前解析到"请求前缀在该锚下的最深耐久覆盖锚"**：
把 no-material 判定改成"两个层次"：
1. **物理 search**：从 `last_host_node` 沿 host 树向上（parent 链）找最接近 root 的 `is_l3_durable` 祖先 = `durable_ancestor`；
   同时确认 `durable_ancestor` 是否覆盖请求后缀的起点（`page_block_in_request` / `get_prefix_hash_values` 对齐请求的页哈希，可复用 `prefetch_anchor_info` 的 key 逻辑）。
2. **判定在 `durable_ancestor` 上做 5 事实**：`storage_material = is_l3_durable(durable_ancestor)`；
   `pending_durable_ack = is_storage_written(durable_ancestor) or op in ongoing_backup`（按 durable_ancestor）；
   `deferred_durable_desc = has_acked_descendant(durable_ancestor)`；
   `restorable_epoch_change = anchor_storage_version(durable_ancestor) > 0（含被 clear 的历史）`。
   `durable_ancestor` 找不到（沿上行没有 durable 节点）→ 判为 no-material → 立即 forward。
   无物材请求（纯设备链 9d8b5428 形状）沿上行到 root 找不到 durable → 仍立即 forward，**主收益保留**。
   有物材请求（锚下方页已 durable）→ durable_ancestor 非空 → 不 forward，保留 frontier wait / 正常 restore。

**方向 C —— 对锚做一次低成本 storage hit query**（`query_storage_hit_length` 的兄弟调用，或对 `prefetch_from_storage` 的 re-issue 节流）：
判定对 `last_host_node` + 请求后缀构造 `RadixKey`，跑一次只读 `_storage_hit_query`（不产生实际 fetch）。若 `storage_hit_count>0` → storage_material=True → 不 forward。**成本**：每 FRONTIER 判定一次 L3 查询，比 pure-predicate 贵但在 FRONTIER 判定入口、每次请求一次，可接受；但注意 prefetch_rate_limited 时的语义（查询被吞返回 0 → 误判 no-material，需要把 rate-limited 也视为"存疑保 wait"）。

### 是否破坏 no-material 主收益？

**不破坏**。主收益是"无物材请求立即 forward、不 idle 60s"（tester D2.2 PASS：80 次全部立即 ADMIT_RECOMPUTE）。
方向 B/C 只改变**有物材但锚节点错位**的请求：它们本就该走 frontier wait/restore（当前被误 forward），修复后它们保留 wait（等待该链的 durability）或正常 restore —— 这是**把错误类别纠正**，不增加任何无物材请求的等待。
方向 B 里"沿上行找不到 durable 祖先"的无物材请求 **仍立即 forward**，唯一可能新加的等待是"锚是 durable 但该锚并不覆盖请求后缀的起点、且 L3 实际仍无物材"——这个类别判定为 `storage_material=True`（durable 祖先存在）→ 保 wait → 回到目前 P3 的行为（T13 兜底 60s），不是无限等待；且该情形（锚 durable 但覆盖不到请求起点）在当前 P3 语义里也已经走 frontier wait，**不是 no-material 的收益范围**（no-material 只承诺"明确无物材"的立即 forward）。
结论：主收益（立即 forward 无物材、消除 60s idle）由 durable_ancestor 缺失分支覆盖，**不回归**。

### 伪代码（spec 级，供 coder）

```python
# scheduler.py _no_material_fast_forward_for 前置解析
def _deepest_durable_ancestor(self, anchor) -> NodeId | None:
    """沿 host 树 parent 链向上找最接近 root 的 is_l3_durable 祖先。
    请求后缀在 anchor 之下；该祖先若存在，是"该请求前缀可被 L3 restore 服务"的最终锚。
    找不到 durable 祖先（纯设备链/无 L3 内容形状，root 默认 non-durable）→ None ⇒ no-material 成立。

    注意：root 的 storage_persisted 默认 False（tree_core.py:147），不是自动 durable——
    沿上行绝不会误把 root 当 durable 返回；纯设备链沿行到 root 仍返回 None ⇒
    no-material 主收益（立即 forward）保留。root 锚的"永远可发"只在判定锚本身是 root
    时由事实 2 的 is_root(anchor) 分支体现（原代码已含），此处不重复。"""
    cur = anchor
    while cur is not None and self.tree_cache.node_exists(cur):
        if self.tree_cache.is_l3_durable(cur):
            return cur
        # host 树的 parent 链（需要 tree_core 暴露 parent 或沿 prefetch_anchor_info 的祖先序列）
        cur = self.tree_core.parent_of(cur)
    return None  # 上行到 root（含）无 durable 祖先 ⇒ no-material 成立

def _no_material_fast_forward_for(self, req, anchor) -> bool:
    durable_ancestor = self._deepest_durable_ancestor(anchor)
    # 判定锚 = durable_ancestor if found else original anchor；
    # 5 事实全部改在判定锚上求值；durable_ancestor is None ⇒ 5 事实缺失 ⇒ forward（主收益）。
    # （事实 1 host_material 不变；事实 2 storage_material = durable_ancestor is not None；
    #  事实 3/4/5 用 durable_ancestor 求值。）
    ...
```

**约束要求（实现前确认）**：
- `tree_core` 需暴露 parent 链访问（当前 `node_by_id` 有 `parent` 属性，需确认可安全沿行；max O(depth)，判空/死锚自愈）。
- 判定锚沿行解析**每次**调用最多 O(depth) 次 `node_exists`/`is_l3_durable`，per-request 开销可忽略（不 O(subtree)）。

---

## Q2：too_short 修复回退 —— 交互 vs 方差

### 结论：**交互为主（per-anchor 改变 WAIT[DEVICE_QUOTA] 集合构成 + 保底门失效），单次 run 方差为辅**

**算术看整体构成**：
- too_short 195（per-anchor）vs too_short-fix 53：**+142**；
- 紧循环 <1s **138** vs 5：per-anchor 几乎全部集中在这个类别（138 个 <1s）。
- **per-anchor 相比 too_short-fix 的 WAIT 集合差异 = MISS 客户流出（重挂 sticky）所释放的 DEVICE_QUOTA 队列位置，被纯容量客户（无 MISS、`host_hit_length=0` 的 T6 客户）填充**。
  证据支撑：f4b42595 的首个 restore_recompute（too_short）在 22:42:12，其后在 22:42:17 立即 WAIT[DEVICE_QUOTA]（admission deny due to NO_TOKEN，running_bs 4/5 满载）→ 在 22:42:17/18/19 连续 21 次 WAIT→RESTORING→REQUESTED=29→too_short→WAIT，**全程无任何 MISS_RECOMPUTE / sticky / miss 记录**（f4b42595 的日志里没有任何 `cause=miss` 或 `revoked:miss` 或 `MISS_RECOMPUTE` lineline）—— 纯容量客户。
- **对比 too_short-fix 的 53 紧循环=5**：too_short-fix 运行时 DEVICE_QUOTA WAIT 集合主要是 MISS 客户（sticky 挂住、不再每 pass 唤醒），纯容量客户少，所以紧循环少。
- **方差因素**：跨 run 的 /data 热度/L3 碎片不同，会改变不 cache 客户进入 WAIT 的分母，但不改变"保底门对 requested=29 的请求系统性失效"的结构。

**为什么 69 次 @13ms（f4b42595）能持续**：`_restore_wait_capacity_fits` DEVICE_QUOTA 分支只拦
`prompt_can_qualify_for_prefetch(len(prompt), host_hit_length)`；f4b42595 `host_hit_length=0`，
`len(prompt)` 由参数决定，只要 `max(prompt_len, 0)` 对 `prefetch_threshold` 判为"可 qualify"，保底门就不拦 ——
而 **`query_storage_hit_length` 的 Length 门在 `page_size` 维度把后缀判成 0**（`prefetch_length < threshold`），
即**保底门对齐的是"几何上能 qualify"，出站却按"页对齐"判定**，中间差一次对齐（`page_size` vs `threshold`）→
`requested=29` 的请求永远在"保底门认为可 qualify"、"出站判定 too_short"之间循环。
**这是保底门（门用几何口径）与 prefetch 出站（用页对齐口径）的错配**，per-anchor 只是让这类客户更多地进入 WAIT。

### 修复 Q1 是否连带修复 Q2？

**不会**。Q1 只收窄 no-material 误 forward（FRONTIER 判定路径），f4b42595 走 T6+DEVICE_QUOTA+too_short，**不进 no-material**。
必须独立修复。可能方向（脚手架，不属于统一模型大重构）：
1. **`prompt_can_qualify_for_prefetch` 在 no-material/保底门/恢复路径三处口径统一**：用 `page_size` 对齐后的最大后缀数
   `max(0, prompt_len-host_hit_length) // page_size * page_size` 与 `prefetch_threshold` 比较，三处一致；
2. **WAIT 入口 manifest（per-wait 单次 re-issue）**：NO_TOKEN 且 `host_hit_length==0` 时（T6 纯容量客户），
   `_restore_potential_for` 返回 True 但后续 re-issue 必然 too_short —— 在 `_prefetch_kvcache` 判定
   `_restore_potential_for(req)` 时同门短路，或 T6 处对 `host_hit_length==0 and not prompt_can_qualify_aligned(...)` 直接
   `ADMIT_RECOMPUTE` 而不进 WAIT；
3. **`_restore_wait_capacity_fits` 保底门对齐**：DEVICE_QUOTA 分支改成和出站口径一致的判定（同 1），把
   `requested=29` 客户拦在 WAIT 外（`return False` 后 T13 兜底释放）。

推荐 1+3 组合（最小、纯 predicate 对齐），2 为可选加固。

### 量化预期

- too_short 195 → 接近 too_short-fix 的 53（甚至更低，因对齐后这些客户根本进不了 WAIT）；
- 紧循环 138 → 个位数；
- DEVICE_QUOTA 845 → 下降（对齐后纯容量客户不再循环）。

---

## Q3：最差 offender 36 的残留 spurious re-arm 源

### 结论：**残留源主要是 (d) T6 门语义收紧后的同链合法 re-arm + 容量兜底快循环，不是 per-anchor bump 遗漏；可修（随 Q2）**

消歧四个候选：

- **(a) 同锚 version 前移仍被"本锚相关但非本请求前缀"的事件 bump？—— 无**。
  tree_core 逐节点 bump（_promote_persisted_subtree 只 bump 实际 promotion 的 node；mark_storage_restored 只 bump restore 读回节点；
  clear 只 bump 实际清除节点）已把 bump 收窄到"该节点自身链"。**同锚 promotion 确实是"该锚相关的 L3 变化"**，ir 会在同一锚上更新，
  但 per-anchor 门判据是"同锚 version 前移 **或 re-anchor**"，这本身是设计的重 arm 条件——**不是 spurious**。
- **(b) promotion 逐节点 bump 与请求前缀粒度错配？—— 无独立源**。bump 是"该节点自身"，对同锚请求确为该前缀的覆盖变化。
  粒度错配在 **no-material 判定**（Q1 的节点 vs 页范围），不在 re-arm 门。
- **(c) MISS_RECOMPUTE 后同锚快速 re-arm（tester 观测 129 vs P1 24）？—— 是"合法性偏移"而非 spurious**。
  per-anchor 把全局 epoch 回归（无关链 bump 就放行）收紧为同锚变化才放行，Miss 客户从"MISS 被无关链解除"变成"MISS 持住不放 +
  同链新写（version 前移）合法重入"；重启检出的 immediate re-arm 129 正是把这些合法重入从"被误拦"转换为"合法处理"。
  **它有点 2 的核心价值，2.52 对比 P1 2.06 的缺口主要不在这。**
- **(d) 容量兜底快循环（f4b42595 等纯容量客户）= 残留主源**（见 Q2）。其 revoked:miss 计数低（主要 too_short），
  但 same-tag WAIT 循环计数高——被计成 revoked：miss 的最差 offender 36 里的 22 次 <1s 紧循环，正是 w/ T11 容量兜底
  NOT（同锚 version/re-anchor）——**Q2 修完即随降**。

### 残留 spurious re-arm 的真实剩余（修复 Q1 前的残留）

- **修复 Q1 前**：no-material 误 forward 转成 recompute 的请求，可能会被同一前缀的后续请求重新 probe（新请求 → 新 miss/持久化 → 旧的证据不适用）——这一类是 Q1 修复的边际收益（收窄误 forward 即减少这一残留）。
- **修复 Q1 后估计**：offender 36 → 接近 P1 最差 9 的量级需看 Q2 后纯容量客户循环是否被脚手架消除；理想 9-15，保守 15-22。

### 是否可修（本轮 vs 留统一模型）

**本轮可修（随 Q2 脚手架）**——把 DEVICE_QUOTA 保底门对齐（1+3），纯容量客户不再循环。这不依赖统一模型。
统一模型（骨架态）把 capacity 归为态 4（资源在途），其 re-arm/退避语义留待统一实现 —— 本轮不涉及。

---

## Q4：restore_success 系统性下降归因

### 结论：**no-material 吸收是主因（80 次直接转 recompute，其中含有物材误转发）；per-anchor 门过严其次；Q1 修复保守保 frontier wait 可恢复大部分**

**证据**：
- frontier_wait 215(P1)/221(P3)/208(strip) → **11**；restore_retry cause=frontier 153/208/199 → **5**。
  80 次 no_material 全部在 GATE_SKIP_FRONTIER 入口直接 `_log_restore_recompute` + return（不 register_frontier_waiter），
  **就是这 215→11 的消失**。
- 其中 3 个确定性误 forward（98c75a55/1c417fdc/1b8c727）在 no_material 判定后被同 turn restore_success
  （6141/6673/1412 tokens）——这 3 个若保留 frontier wait，restore_success 直接 +3。
- 其余 77 次 no_material 里，有一部分是"判定时刻锚节点错位但物材在/在途"的**同一根因误吸**（概率上在 8-agent
  concurrent 写下同频）；另一部分是真无物材（9d8b5428 形状，本来就该 forward）。
- **per-anchor 门过严**其次：同锚 version 前移才允许重入，跨 resurf 的同前缀热身更慢、restore 期更短，
  但 tester 已在点 5 PASS 证明"同链状态变化后可重新 restore"真实存在（34 rid 既有 MISS 又有 success）。

**修复后量化估计**：
- 若 Q1 修复（判定前解析 durable_ancestor），"有物材但在途/晚到"的误 forward 子集回到 frontier wait，
  restore_success 53 → 粗略 40+（strip 43 水平；保守 35-45）。
- 加上 Q2 修完释放的 DEVICE_QUOTA 循环，restore-hit turns 13 → 25-35（P1 25 / strip 43）。
- **要回到 strip 43 需要把 no-material 的全部"晚到"类别也保留 wait**（判定时物材尚未持久，但请求后缀在 L3 有内容可恢复——这才真正 lie in Q1 的 durable_ancestor 分支：durable 祖先存在但不覆盖请求起点，或 storage_written 在 durable_ancestor 上缺失但 L3 有内容）。
  这些属于"边界不可全知"，预计恢复不到 strip 43 的 100%，但恢复到 P1 25-33 的可接受区间是本轮 Q1 的能力上限。

**需要护栏（restore 面不被过度保留）**：Q1 修复让"锚 durable 但覆盖不到请求起点"也保 wait（P3 语义），必须验证不出现
"wait 但何物都不来"的 9d8b5428 类别新增 —— 若出现，需把 durable_ancestor 存在但 `prefetch_gate_ok(durable_ancestor)` 为 False
（非 root/非 durable 但 storage_written/deferred）也纳入 pending_durable_ack/deferred 事实（即 5 事实把"在途生产者"覆盖完整）。

---

## Proposed Architecture — 修复方案优先级排序

| 优先级 | 修复 | 对应问题 | 本轮 vs 统一模型 | 判定 |
|---|---|---|---|---|
| P0 | Q1：durable_ancestor 解析后判 5 事实（方向 B，或 C 成本可接受则 B+C act-hedge） | 点 4 + D2.1 | **本轮必修**（误 forward 直接违反 D2.1；且民族点 4） | 修复后不破坏 no-material 主收益（无物材沿上行到 root 无 durable → 仍立即 forward） |
| P0 | Q2：三处 prefetch_can_qualify 口径 page_size 对齐（1+3） | 点 6 + too_short 缺陷 | **本轮必修**（紧循环 13ms 违反 too_short 不回退） | 拦下 138 紧循环 + 195 too_short → 53 水平 |
| P1 | Q3 随 Q2（容量兜底快循环） | 点 3（offender 36 → 背景水平） | 本轮随 Q2 观察，若仍高则本轮+back-to-back | 无需 independent gate |
| P2 | Q1 修复后的 RESTORE 面护栏验证（durable 存在但不覆盖起点 → 保 wait 且不新 dead-end） | 防止 over-retain | 本轮验证，若需微调为 P2 小修 | 带 T13 兜底即有界 |
| P3 | 统一状态机骨架（态 3 no-material 的 anchor binding 精化 = `anchor_chain` 而非 `anchor`） | 结构性归纳 | **留统一模型** | 契约里补充"锚 = (chain/prefix, 页范围)" |

### 本轮修复后是否足以让 tester 复测 6 点全 PASS？

**可达，但有明确条件**：
- 点 6（too_short）由 Q2 脚手架满足（53 或更低）。
- 点 4（restore_success/storage_hit）由 Q1 修复满足（frontier_wait 回 25-33，restore_success 40+）。
- 点 3（revoked:miss→2.06、offender→9）由 Q3/Q2 观察判断：若 Q2 后 offender 仍 20+，需要把"纯容量客户 WAIT 集合"再收窄
  （例如 `host_hit_length==0` 时 T6 的 no-material 也可以应用 same-gate 逻辑，或等统一模型）——**这不是 6 点的硬剩**但可能需一轮迭代。
- 点 2（revoked:miss/req）per-anchor 已到 2.52，Q1 修复不触碰 re-arm 门，保持 2.52 或随 Q2 略降。
- 点 1/5 已 PASS，不回归。

**结论**：P0 两项（Q1+Q2）必须修复，复测 6 点全 PASS **可达**；点 3 若迭代则可安排在复测轮 2。

---

## Migration / Impact

改动面（纯 predicate/字段粒度，无状态机大改，与统一模型契约不冲突）：

1. `unified_tree_core.py`：暴露 parent 链访问（或在 radix_cache 层加 `deepest_durable_ancestor` proxy，用 `node_by_id().parent` 沿行）。
2. `scheduler.py` `_no_material_fast_forward_for`：判定前解析 durable_ancestor，5 事实在解析锚上求值；durable_ancestor None ⇒ forward（主收益保留）。
3. `scheduler.py` `_restore_wait_capacity_fits` + `_prefetch_kvcache` / `has_restore_potential`：三处 `prompt_can_qualify_for_prefetch`
   用 page_size 对齐口径统一（或 `prompt_can_qualify` 内部改口径）。
4. 测试：NoMaterialFastForwardTests 增补"锚持久但覆盖不到请求起点"与"durable 祖先沿行"用例；too_short 保底门对齐用例。

不影响已确认基线：P1 sticky miss 状态机 / NO_L3 per-anchor cursor / P3 A+B 补链 / clear 守卫 / T13 兜底 / Fix A。

## Alternatives

- **A. 禁用 no-material（回到 60s T13 等）**：消除误 forward，但点 2 的 fast-forward 主收益（消除 9d8b5428 idle、restore_recompute timeout 1）也消失；成体系是回归，不推荐。
- **B. durable_ancestor 解析**（采纳主方向）：把"锚"从节点维度精化到"链上最耐久覆盖点"，判定与 restore 覆盖对齐；cost O(depth/request)，不 O(subtree)。
- **C. 判定前 storage hit query**：直接测 L3 内容（supports hit_count>0 即 storage_material），最精确；cost 一次 L3 查询/FRONTIER 判定，
  且 rate-limited 需语义化（rate-limit 视为"存疑保 wait"）。可作为 B 的兜底（高成本但更准）。
- **D. wait 一次 re-probe 节流**：对 no-material 候选取"保 wait 一个有限窗口后再次判定"；TTL/heuristic，用户禁止（ledger:2112），不推荐。

## Open Decisions

1. **Q1 修复走 B（durable_ancestor 解析）还是 B+C（叠加低成本 storage query）**：B 无 L3 I/O，C 更准但引入 rate-limit 语义。
   倾向 B 先实现（无 I/O、O(depth)），C 若复测仍残留误 forward 再叠加。需用户/或本诊断建议采纳 B。
2. **Q2 脚手架的口径统一点**：三处 `prompt_can_qualify` 都用 page_size 对齐口径 —— 需确认 prefetch_threshold 语义
   （是否"page 对齐后的 token 数"）后落地；若 threshold 本身是 page 数，则应比较对齐页数。这影响一点实现细节，非架构分歧。
3. **点 3 的 PASS 判据**：若 Q1+Q2 后 offender 仍在 15-22，是否接受（"≈P1 但非 9"）？或必须回到 9 才过？用户裁决 2h soak 前状态。
4. **fix-strip 基线**：Q1/Q2 修复后 tester 复测使用与本次同构的 gate3_ab 负载；对比口径沿用 P1 数据（2.06 / 9 / 25 turns）。

## followups

- P0 修复（Q1+Q2）spec 已出（本报告 §Q1/Q2），交 coder 实现 + 单测增补；
- tester 复测：P1 deterministic workload 6 点 + no-material D2.1/D2.2/D2.3；P 预期 passed 见 §Q4/§一页裁决；
- 统一模型：把 no-material 态 3 的 anchor binding 精化为 "anchor_chain（链上最深耐久覆盖点）"，与 Q1 的 durable_ancestor 一致。

## open_issues

- Q1 修复边界（锚 durable 但覆盖不到请求起点的 over-retain）需要 RESTORE 面护栏验证（P2）。
- 点 3 的 offender 是否必须回 9 待用户裁决（P3）。
- Q2 的 prefetch_threshold 对齐口径需实现前确认（Open Decision 2）。