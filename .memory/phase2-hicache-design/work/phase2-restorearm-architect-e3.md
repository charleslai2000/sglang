# P1 restore eligibility / admission re-arm churn: 只读架构定位

- status: **done**
- epoch: e3
- owner: architect
- task: 只读定位 restore eligibility / admission re-arm 核心缺陷（不做实现、不做计数器 heuristic），给出精确代码链、device-hit 阻塞原因、正确状态语义裁决、Fix A 边界
- 代码基线: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt`（分支 3090-24g-opt，含 Fix A/B patch）
- 既有证据: `phase2-rhfix-architect-e1.md`、`phase2-rhfix-fixb-crosstest-tester-e1.md`、`phase2-rhfix-tester-e1.md`

---

## 0. Conclusion

生产病态 `WAIT[DEVICE_QUOTA] → RESTORING → revoked:miss → ADMISSION_DENY → re-WAIT`（~13ms churn）的根因是一个**状态语义缺陷**，不是容量缺陷：

1. **definitive miss 后 restore_potential 立即 True 的原因**：miss 只把状态机置回 `NONE`（`next_restore` T9 genuine miss → `(NONE, ADMIT_RECOMPUTE)`），但 **restore 资格谓词 `has_restore_potential` 是"结构存在性"检查，不携带"这个前缀刚被证明 L3 缺失"的负证据**。`_storage_prefetch_missed_rids` 在 miss 路径上只增不减（仅 admission pop / paced retry(默认关) / abort 清），anchor 的 `is_backuped/is_root` 也不因 miss 而失效——所以下一次 admission 重判时资格仍 True，立即 re-arm。**NONE 同时表示"从未尝试"和"试过并失败"，失败证据在 re-arm 判定中被完全丢弃。**

2. **re-arm 的确切代码路径**：不是 `next_restore` 里的转换，而是 **admission 循环的 T6**：`scheduler.py:4501` NO_TOKEN → `4502 _restore_potential_for` → True 且 `4523 device_quota_degraded(timeouts)` 为 False → `4526 _apply_restore_event(ADMISSION_DENY)` → `hicache_restore.py:119-120` `(WAIT_CAPACITY, WAIT)` 重新 arm。

3. **缺 generation/cache/resource epoch 条件**：re-arm 资格对 epoch 完全无感。系统已有 `l3_publish_epoch`（L3 持久/发布单调 epoch）与 `session_generation`（身份 epoch），但 re-arm 判定不读它们。definitive miss 在 epoch=E 被探测，同 episode 内 re-arm 到同一 WAIT 会在 E 重新探测同一缺失前缀——必然再 miss → churn。

4. **device-hit 仍进同一 restore WAIT 的原因**：admission gate（`_restore_wait_capacity_fits` 与 adder 的 NO_TOKEN）**只检查空闲容量**，与设备命中无关。working set = pool 时 `available_and_evictable_tokens ≈ 0`，任何新 charge（哪怕 device 已覆盖大部分输入，仍要 max_new+page_size）都 NO_TOKEN → T6。T6 的资格谓词是结构性的（host/L3 存在），所以 device-hit 请求照常进入同一 WAIT。**device-hit 被 WAIT 阻塞是纯容量问题（Fix A 领域），不是 miss 问题（P1 领域）。**

**目标状态语义裁决**：definitive miss 后，restore 资格必须绑定"上次 miss 被探测时的 L3 持久 epoch + 身份 generation"。re-arm 仅在 `l3_publish_epoch` 前移（cache 状态真实变化）或 generation/prefix 身份改变时才被允许；否则应转可前进 recompute/admit。状态机应以一个**粘性 MISS 状态（或 miss_epoch 字段）**保存失败证据，而不是塌缩回与"从未尝试"无法区分的 NONE。**不选"连续 miss N 次放弃"计数 heuristic**（§5 理由）。

---

## 1. 精确代码链（revoked:miss → restore_potential True → re-arm → WAIT）

### 1.1 完整循环（每 lap ~13ms）

```
scheduler.py:3224   REVOKED_MISS, genuine_miss=True    # drain 记录终端结果
      ↓
scheduler.py:3225   _apply_restore_event(T9, genuine_miss=True)
      ↓
hicache_restore.py:131-137  next_restore: genuine_miss → (NONE, ADMIT_RECOMPUTE)
      ↓                                            # 状态机清到 NONE，日志 miss
scheduler.py:3267-3268      _log_restore_recompute(req, "miss")
      ↓
（下一 admission pass）
scheduler.py:4491   res = adder.add_one_req(...)      # 设备满 → NO_TOKEN
      ↓
scheduler.py:4501   res == NO_TOKEN
scheduler.py:4502   _restore_potential_for(req) == True   # ← 结构谓词，miss 后仍 True
scheduler.py:4523   not device_quota_degraded(timeouts)   # Fix B，快环内 rarely True
      ↓
scheduler.py:4526   _apply_restore_event(ADMISSION_DENY)  # T6 re-arm
      ↓
hicache_restore.py:119-120  (WAIT_CAPACITY, WAIT) reason=DEVICE_QUOTA  # 重新 WAIT
```

### 1.2 T9 genuine miss 转换（definitive）

`hicache_restore.py:131-137`：
```python
if event is RestoreEvent.REVOKED_MISS:  # T9
    if genuine_miss:
        return RestoreState.NONE, RestoreDecision.ADMIT_RECOMPUTE
    return RestoreState.WAIT_CAPACITY, RestoreDecision.WAIT
```
genuine miss 置 NONE。`_apply_restore_event`（scheduler.py:3301-3345）把 `hicache_restore_wait_reason` 清 None、state_ts 清 0。**没有任何 miss 证据字段被保留。**

### 1.3 为什么 miss 后 `has_restore_potential` 立即 True（Q1 的精确答案）

`scheduler.py:3738-3747 _restore_potential_for` → `unified_radix_cache.py:3080-3104 has_restore_potential`：

```python
if host_hit_length > 0:            # (a) host 物材仍在
    return True
if prompt_len is not None and not self.prompt_can_qualify_for_prefetch(...):
    return False
if req_id in self.ongoing_prefetch or req_id in self._storage_prefetch_missed_rids:
    return True                     # (b) in-flight / 已登记 miss
if not self.tree_core.node_exists(anchor_node_id):
    return False
return self.tree_core.is_backuped(anchor_node_id) or self.tree_core.is_root(anchor_node_id)  # (c)
```

三条路都在 definitive miss 后仍返回 True：

- **(b)** `_storage_prefetch_missed_rids` 在 miss/decline 路径**只 add 不减**（`unified_radix_cache.py:2529, 2540, 2615, 2727, 3471, 3493, 3507`），仅在 `pop_prefetch_loaded_tokens`（真正 admission）、`pop_storage_prefetch_miss`（paced retry，`interval>0` 才轮询，M2 默认 0 关闭）、`release_aborted_request`（abort）时 discard。**一次 revoked:miss 把 rid 留在这个集合里**，直接命中 (b)。
- **(c)** `is_backuped(anchor)` 的失效是 anchor-precise 的（`clear_storage_durable`），且 `is_root(anchor)` 无条件 True——miss 查询的 absent-hash 反馈不保证清掉该 anchor 的 durability 信念，root anchor 更是永久 True。
- **(a)** host_hit_length>0 只反映 host 侧 staging/持留，与"L3 该前缀缺失"正交。

**核心缺陷**：`has_restore_potential` 是"结构存在性"谓词，只回答"有没有可恢复物材的迹象"，不回答"这个前缀是否刚被证明 L3 缺失"。miss 的负证据（哪个前缀、哪个 generation、在哪个 l3_publish_epoch 被探测）完全不进入资格判定，因此 re-arm 判定把失败当成"从未尝试"。

### 1.4 缺 epoch/generation 条件的证据（Q3）

re-arm 资格（4502）与 T6 转换（4526）均不读任何 epoch。系统已有现成信号：
- `l3_publish_epoch()`：单调 L3 持久/发布 epoch（`unified_tree_core.py:2127-2130`，write-ack 提升/restore 读回时 bump）。
- `session_generation`：per-session 身份 epoch（`unified_radix_cache.py:4222`，scheduler.py:2701/2745 赋值）。

Ready Horizon 的 NO_L3 负缓存已用 `epoch_cursor = l3_publish_epoch()`（scheduler.py:3238-3249），但**仅 RH 专用、且 gate 在 `enable_ready_horizon`**；核心 restore re-arm（T6）没有对应的 epoch 门。一个 definitive miss 在 epoch=E 探测 → 同 episode re-arm → 在 E 重探同一缺失前缀 → 必然再 miss → 结构性 churn。

---

## 2. 哪个状态转换重新 arm restore（Q2 精确答案）

**re-arm 不是状态机转换，而是 admission 循环的 T6 分支**。确切调用链：

```
scheduler.py:4501   if res == AddReqResult.NO_TOKEN:
scheduler.py:4502       if self.enable_hicache_storage and self._restore_potential_for(req):
scheduler.py:4523           if not device_quota_degraded(req.hicache_restore_device_quota_timeouts):
scheduler.py:4526               self._apply_restore_event(req, RestoreEvent.ADMISSION_DENY)
scheduler.py:4529           self._cleanup_not_added_req(req, adder)
scheduler.py:4530           continue
```

`hicache_restore.py:119-120`：
```python
if event is RestoreEvent.ADMISSION_DENY:  # T6
    return RestoreState.WAIT_CAPACITY, RestoreDecision.WAIT
```

此外 WAIT 内还有两个**重新进入 RESTORING** 的 arm（T11/T12），但那是"WAIT 内重发 prefetch"，不是"WAIT 之外 re-arm"：
- T11 CAPACITY_FITS：`hicache_restore.py:139-142` → `(RESTORING, RETRY_PREFETCH)`，触发自 `scheduler.py:3152+` 的每 pass 容量唤醒。
- T12 FRONTIER_READY：`hicache_restore.py:144-147`，触发自 `scheduler.py:3135`。

在生产 churn 中，fast path 是 T9 miss→NONE 后，**下一次 admission 的 T6** 重新 arm WAIT。Fix B 的 `device_quota_degraded`（`hicache_restore.py:190-197`，`attempts >= DEVICE_QUOTA_MAX_TIMEOUTS(=2)`）在快环中几乎不触发——因为它数的是 **T13 timeout**（`scheduler.py:3168` 仅在 `now-state_ts > timeout_s` 才 +1），而快环每个 episode 只吃 0-1 次 T13 timeout（6 条 trace max=1，见 fixb-crosstest-tester-e1 §3）。所以 Fix B gate 拦不住 miss 驱动的 re-arm。

---

## 3. device-hit 仍被 restore admission 阻塞的确切原因（Q4）

### 3.1 admission gate 只看容量，与设备命中无关

NO_TOKEN 判定在 `PreflightAdder.add_one_req`（容量核算），WAIT 唤醒谓词 `_restore_wait_capacity_fits`（scheduler.py:3672-3736）：

```python
charge = device_charge(              # scheduler.py:3728-3733
    len(req.full_untruncated_fill_ids),
    len(req.prefix_indices),         # 设备命中已体现在 prefix_indices
    max_new, self.page_size,
)
return charge < available_and_evictable_tokens(self.req_to_token_pool, self.tree_cache)  # :3734
```

`device_charge`（`schedule_policy.py:520-534`）= `max(0, full_input_len - device_prefix_len) + max_new + page_size`。即使 device 前缀覆盖了绝大部分输入，`max_new + page_size` 的增量 charge 仍 > 0。working set = pool（生产冻结基线 host_used≈97370/98305）时 `available_and_evictable_tokens ≈ 0`（`schedule_policy.py:537-551` = available + evictable），所以 `charge < 0` 恒 False → 每 pass 唤醒都失败，admission 每 pass NO_TOKEN。

### 3.2 为什么 device-hit 还进 WAIT

NO_TOKEN → T6 分支的资格谓词 `_restore_potential_for` 是结构性的（host 物材 / L3 anchor / in-flight 存在即可），**device-hit 请求天然有 host/L3 物材** → 资格 True → 进 WAIT[DEVICE_QUOTA]。所以：
- **device-hit 被 WAIT 阻塞是纯容量问题**（池满、无空闲可 evict），不是 cache 缺失问题。
- 设备命中不豁免容量核算，也不豁免 T6 re-arm。

### 3.3 这对 P1 语义的关键含义

P1 的 miss-epoch 门**不应**拦住 device-hit/容量性 denied 的 re-arm——它的 restore 意图仍然有效，只是被容量卡住。这属于 Fix A（容量 release 唤醒）领域。见 §6 正交边界。

---

## 4. 正确状态语义裁决（语义 + 建议字段/转换，不实现）

### 4.1 需要区分的三种"deny"（当前被 T6 混为一谈）

| 场景 | 根因 | 正确处置 | 归属 |
|---|---|---|---|
| A. 本 episode 已 definitive miss，pool 满 | cache 缺失 + 容量 | **不 re-arm**，转 forward recompute/admit；仅 epoch 变化才恢复资格 | **P1** |
| B. device-hit / 有效物材，pool 满 | 纯容量 | re-arm 合理，等容量 release（Fix A epoch 唤醒） | Fix A |
| C. host staging / frontier / backup 瞬态 | 瞬态 | 保持 retryable（现行为正确） | 现行为 |

当前 T6 对 A 与 B 不加区分：只要 `has_restore_potential` True 且未到 Fix B cap，一律 re-arm。这既是 B 的正确行为，也是 A 的病态 churn。

### 4.2 建议的资格判据（语义）

**definitive miss 后，restore 资格应绑定"上次 miss 被探测的 L3 持久 epoch + 身份 generation"**：

```
restore_eligible =
    has_restore_potential(req)                       # 结构性物材（保留）
    AND (
        restore_miss_epoch is None                   # 本 episode 未 miss
        OR l3_publish_epoch() > restore_miss_epoch   # L3 持久真实前移（cache 状态变化）
        OR generation_changed(previous_generation)   # 身份/prefix 改变
    )
```

- `l3_publish_epoch` 是单调 L3 覆盖信号：它动了 = 有新的/恢复的 L3 覆盖，re-probe 可能命中；它没动 = 同 episode 内同缺失前缀 re-probe 必 miss，re-arm 无意义。
- `session_generation` 变化 = 这是另一个身份的前缀，旧 miss 证据不适用。
- **容量 epoch（Fix A 的 host_release）不作为 miss 的 re-arm 依据**：容量释放不改变"该前缀是否在 L3"，只改变"能否 admit"（那由 T6/唤醒谓词容量侧处理）。

### 4.3 状态机如何表达"同一 episode 无真实变化不得 re-arm"（语义 + 建议）

核心：**当前把"试过并失败"塌缩回 NONE，与"从未尝试"不可区分**。必须保存失败负证据。两个等价表达：

**(建议 A) 粘性 MISS 状态**——新增 `RestoreState.MISS_RECOMPUTE`：
- T9 genuine miss → `(MISS_RECOMPUTE, ADMIT_RECOMPUTE)`（不再回 NONE）。
- MISS_RECOMPUTE 下的 T6 ADMISSION_DENY → **不 re-arm**（`next_restore` 对该状态 T6 返回 WAIT 前，先查 epoch 门；epoch 未动则保持 MISS_RECOMPUTE / ADMIT_RECOMPUTE，走 forward recompute）。
- 仅当 `l3_publish_epoch` 前移或 generation 改变 → 离开 MISS_RECOMPUTE（允许重新走 WAIT/restore）。
- `restore_success`（T8 → READY）天然离开 MISS_RECOMPUTE，健康链不被饿死。

**(建议 B) miss_epoch 字段**——保留 NONE，加 `req.hicache_restore_miss_epoch`：T9 genuine miss 时写入当前 `l3_publish_epoch()`；T6 re-arm 前检查 `l3_publish_epoch() > miss_epoch`（或 generation 变）。侵入更小，但把"不可 re-arm"散在调度器分支里，不如 A 把约束显式放进状态机。

**裁决**：结构上 A 更干净——把"不能再 WAIT"作为显式状态而非隐式条件，T6 分支读状态即可，与 Fix B 的计数启发式彻底解耦。两种都满足"同一 episode 无真实变化不得 re-arm"的目标语义。

### 4.4 与 generation 的衔接

- miss 证据必须按 (generation, prefix, miss_epoch) 记录——同一 rid 跨 session/prefix 复用时应以 generation 变化作废旧 miss。
- `session_generation` 已在请求上（scheduler.py:2701/2745），直接可用；`l3_publish_epoch` 已在 tree_cache 上（`unified_radix_cache.py:2270`）。

---

## 5. 为何不选"连续 miss N 次放弃"计数器 heuristic（Q4 语义缺陷）

Fix B 的 `DEVICE_QUOTA_MAX_TIMEOUTS` 就是这一形态，其缺陷：

1. **频率代理无结构意义**：计数测"多频繁"，不测"cache 状态是否变化"。正确阈值取决于 churn 率与 epoch 前移频率，随负载漂移，任意 N 都脆弱。
2. **与正确信号错位**：计数在 `restore_success`（前向步）时清零（scheduler.py:4471），但**不在 epoch 前移时清零**。一个健康链在 L3 多次前移间合法 re-probe，若恰有 N 次早期 miss，会被误砍（饿死）；反之一个零 L3 变化的 churn 链只要没到 N 就继续转。计数器无法区分"N 次 miss 且 L3 零变化"（该停）与"N 次 miss 且 L3 有前移"（该续）。
3. **实证不触发**：Fix B 数的是 T13 timeout，快环每 episode ≤1（6 条 trace max=1），gate 从不 fire（fixb-crosstest-tester-e1 §3）。即便改成数 miss，仍是频率代理，带 1-2 的缺陷。
4. **状态非自描述**：计数是隐藏可变状态，调试/推理成本高；epoch 门是单调、自描述、可观测的信号，re-arm 允许 ⟺ miss 前提被作废。

**Epoch 门是结构性判据（作废 miss 前提），计数是频率近似（估"该不该放弃"）**。前者直接表达用户冻结的目标语义。

---

## 6. 与 Fix A 边界（正交确认）

**Fix A**（`ready_horizon.py`，`host_release` 单调 epoch，NO_HEADROOM waiter 订阅）解 **resource-release 唤醒**：working set = pool、headroom≈0 时，容量 release 发生后 waiter 应被唤醒前进。这是**容量/资源 epoch**。

**P1**（本报告）解 **无 release 时的 miss churn**：release 不发生、且 probe 因 L3 缺失反复失败 → 反复 re-arm 转圈。这是**cache 证据 / L3 持久 epoch**。

**正交性**：
- Fix A 触于容量 release，**不改变**"该前缀是否在 L3"——容量释放后重探缺失前缀仍 miss，Fix A 不消 churn（这正是 tester 观察的"capacity release 后仍反复 WAIT"）。
- P1 触于 L3 持久/身份 epoch，**不创造**设备容量——L3 前移后请求仍可能因 quota NO_TOKEN 被拒（那属 Fix A 领域）。
- 各门一个不同决策：Fix A 门"waiter 何时可唤醒"（容量）；P1 门"missed 请求是否可 re-arm restore"（cache 证据）。
- 二者都需，互不包含。冻结 headroom + miss churn：Fix A 永不 fire（无 release），须 P1 兜底（不 re-arm → forward recompute）。
- 唯一交接点：§3.3 场景 B（device-hit + 纯容量）归 Fix A 的容量唤醒；场景 A（本 episode miss + 容量）归 P1 的 miss 门。T6 分支需按此分流，避免 P1 误伤合法容量 re-arm。

---

## 7. 与 Fix B 的关系（补充，同根）

Fix B（T13 timeout 计数 cap）与 P1 目标相同（打断 WAIT 环）但机制错误：Fix B 等 timeout 累积，P1 等 epoch 证据。Fix B 实证不触发（§5.3）。P1 是 Fix B 的结构性替代（建议收编其 episode 概念——按 (generation, epoch) 界定 episode，而非按 restore_success 清 counter）。若保留 Fix B，其 gate 应重定向为 miss 驱动的 epoch 门（即 P1），而非 timeout 计数。

---

## 8. Open Issues

1. **l3_publish_epoch 前移频率**：需运行中观测该 epoch 在 churn 场景下是否确实静止（预期静止——缺失前缀不会被写回）。若在某些路径它频繁前移（如无关链写回也 bump），miss 门可能放行过多 re-probe，需界定"覆盖该 anchor 的 L3 前移"而非全局 epoch（`l3_publish_epoch` 是全局单调，anchor 粒度粒度需另行锚定）。此为**证据依赖**，可 EVIDENCE_REQUIRED 给 tester 观测。
2. **场景 B（device-hit + 纯容量）的分流**：T6 需能区分"本 episode 已 miss"与"从未 miss"。建议状态（§4.3）天然携带此区分，但需确认 `host_hit_length>0` 且未 miss 的请求不会误入 MISS 门。低风险，实现期校验。
3. **generation 变更来源**：`session_generation` 的 bump 语义（何时身份变）需与 cache 侧确认，避免把正常前缀演进误判为新身份（放行过多）或相反。
4. **Fix A/P1 联合验证**：正交性需在"冻结 headroom + 无 release + miss churn"与"容量 release + 有效物材"两种场景分别验证，确保无互相掩盖。
5. **MISS_RECOMPUTE 状态下 T13**：建议语义下 MISS_RECOMPUTE 不再 arm T13（无 WAIT 可超时），需确认 forward recompute 有独立前进保证（admission 容量释放后 admit），不引入新饿死。

---

## 9. 证据 / 产物路径

- 状态机: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler_components/hicache_restore.py:119-137,190-197`
- re-arm T6 分支: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py:4501-4530`
- T13 计数与 cap: `scheduler.py:3152-3172, 3168`；重置 `scheduler.py:4471`
- 唤醒谓词/容量: `scheduler.py:3672-3736`；`schedule_policy.py:520-551`
- 资格谓词: `unified_radix_cache.py:3080-3104`；`_storage_prefetch_missed_rids` add 点 `2529/2540/2615/2727/3471/3493/3507`，discard 点 `2979/2987-2990/3135`
- T9 终端产出: `unified_radix_cache.py:3333-3341`；scheduler 消费 `scheduler.py:3211-3268`
- epoch 信号: `unified_tree_core.py:2127-2130`（l3_publish_epoch）、`unified_radix_cache.py:2270`、`ensure_session_generation:4222`
- 既有证据: `phase2-rhfix-architect-e1.md`、`phase2-rhfix-fixb-crosstest-tester-e1.md`、`phase2-rhfix-tester-e1.md`（同目录）

---

## summary

### Conclusion
restore eligibility / admission re-arm churn 的根因是**状态语义缺陷**：definitive miss 把状态塌缩回 NONE，丢失"该前缀刚被证明 L3 缺失"的负证据；re-arm 资格谓词 `has_restore_potential` 是结构存在性检查，不读任何 epoch/generation，因此同 episode 内无真实 cache 变化时仍立即 re-arm，形成 ~13ms churn。修复方向 = 以粘性 MISS 状态（或 miss_epoch 字段）携带负证据，re-arm 仅在 `l3_publish_epoch` 前移或 generation 改变时放行，否则转 forward recompute/admit。不用"连续 miss N 次放弃"计数 heuristic（频率代理无结构意义、与正确信号错位、Fix B 实证不触发）。

### Current Architecture
`next_restore` 把 genuine miss（T9）→ `(NONE, ADMIT_RECOMPUTE)`；T6 ADMISSION_DENY 在 `has_restore_potential` True 且 Fix B 计数未达 cap 时 → `(WAIT_CAPACITY, WAIT)` re-arm。资格谓词只看结构性物材（host/ongoing/missed-set/anchor-backed），不看 epoch。admission/唤醒容量谓词只算空闲容量，device-hit 不豁免。Fix B 以 T13 timeout 计数为 cap（`>=2`），快环每 episode ≤1 故不触发。

### Problem / Forces
working set = pool、headroom≈0（可用容量≈0）+ miss 反复失败 → T6 反复 re-arm 同一缺失前缀 → WAIT→RESTORING→revoked:miss→ADMISSION_DENY→WAIT 13ms churn。restore_potential 结构与容量双重无感。

### Proposed Architecture
- 区分三种 deny（本 episode miss / 纯容量 device-hit / 瞬态）。
- definitive miss 后 restore 资格 = 结构性物材 AND（未 miss OR l3_publish_epoch 前移 OR generation 变）。
- 建议新增粘性 `MISS_RECOMPUTE` 状态（或 miss_epoch 字段）携带负证据；MISS 下 T6 不 re-arm，走 forward recompute；epoch/generation 变化才恢复资格。
- T6 按 场景A(miss门=P1)/场景B(容量=Fix A) 分流。

### Alternatives
Fix B（T13 timeout 计数 cap）——同目标但机制错误，实证不触发；P1 是其结构性替代。ready_horizon NO_L3 负缓存——已用 epoch_cursor 门，但仅 RH 专用、非核心 T6，方向可借鉴。

### Migration / Impact
P1 与 Fix A 正交（Fix A=容量 release epoch；P1=cache 证据 epoch），二者都需。建议 P1 收编 Fix B 的 episode 概念（按 generation/epoch 界定 episode）。实现期校验：T6 分流不误伤 device-hit 合法容量 re-arm；MISS 状态 T13 不再 arm；l3_publish_epoch anchor 粒度界定（open issue 1）。

### Open Decisions
见 §8：l3_publish_epoch 是否需 anchor 粒度（证据依赖）；generation bump 语义确认；MISS 下 forward 前进保证。

---

## followups
- （不阻塞）tester 观测 churn 场景下 `l3_publish_epoch` 是否静止、以及是否需 anchor 粒度版本（EVIDENCE_REQUIRED 候选，见 open issue 1）。
- （不阻塞）实现期校验 §4.3 状态方案 A/B 对 T6 分流的影响，确认 device-hit（场景 B）不受 miss 门误伤。

## open_issues
见 §8 五点：① l3_publish_epoch 粒度/静止性（证据依赖）；② T6 场景 A/B 分流校验；③ generation bump 语义确认；④ Fix A/P1 联合验证；⑤ MISS 下 forward 前进保证。
