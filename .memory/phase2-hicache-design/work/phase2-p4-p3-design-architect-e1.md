# phase2-p4-p3-design-architect-e1 — Q1 修复后残留 FAIL 点（点3 revoked:miss / 点4 too_short）最小 no-heuristic 修复设计

```text
status: done
artifacts:
  - 本报告（read-only 架构设计，未改任何代码；spec 供 coder 实现）
evidence:
  - tester: work/phase2-p0fix2-tester-e1.md（6 点复测 4/6 PASS；点3 FAIL 2.84 / 点4 FAIL 380/315；
    too_short 归因 = REVALIDATE-bet 漂移；never-case 残留 11 事件）
  - architect 上轮: work/phase2-peranchor-diagnose-architect-e1.md（Q2 归因修正见 coder §4）
  - coder: work/phase2-p0fix2-coder-e1.md（commit 0f8542c1a5，Q1 durable_ancestor + Q2 对齐回归锁；
    Q2 前提证伪：门本就页对齐、f4b42595 非纯容量客户）
  - 统一模型: work/phase2-re-unified-architect-e1.md（五态 × 四元组契约；态 2 too_short / 态 4 capacity）
  - 代码（只读）: scheduler.py _restore_wait_capacity_fits:3721-3805 / _reconcile_restore_states step4
    T11:3169-3217 / _prefetch_kvcache GATE_SKIP:2963-3091 / T6 ADMISSION_DENY:4693-4735 /
    _anchor_version_or_zero:3931；hicache_restore.py capacity_wake_applies:482-502 / wait_reason_for:270 /
    miss_rearm_allowed:295 / next_restore DENIED_SHORT T4:124-132；ready_horizon.py SAFETY_FUSE:98
    / host_release epoch:27,179,3568-3581；unified_radix_cache.py prompt_can_qualify_for_prefetch:3235-3245
    / has_restore_potential:3247-3284
summary:
  Conclusion
  Current Architecture（关键证据核实）
  Problem / Forces
  P4 设计（点4 主修 + 点3 主杠杆 + never-case 闭合）
  P3 判定（点3 是否随 P4 解决，量化预期）
  never-case 残留边界闭合
  优先级排序 + 6 点全 PASS 可达性
  no-heuristic 禁令逐条自查
  Migration / Impact
  Alternatives
  Open Decisions
```

## Conclusion（一页裁决）

1. **点4（too_short REVALIDATE-bet 紧循环）的根不是"REVALIDATE bet 设计错"，而是"这类请求被错误地归入 DEVICE_QUOTA 容量态并被每 pass 容量兜底唤醒"**——其真实拒绝因是"当前 suffix 亚阈值"（too_short），不是"容量不足"。容量唤醒对它是**必然再失败**（re-issue 必 declined_too_short），因此构成 13-600ms 紧循环。**最小 no-heuristic 修复 = 把 DEVICE_QUOTA 容量唤醒的门从"只查 charge<available"改为"当前实际可 prefetch 后缀 >= prefetch_threshold 且 charge<available"**。当前 suffix 亚阈值（REVALIDATE-bet / never-case 残留）的 waiter 不被容量兜底唤醒，其唯一合法再触发 = 当前 suffix 实质增长越过阈值（device match 衰减）或 T13 兜底 recompute。这**不是**计数器/TTL/次数——是既有 too_short 几何判据在"当前实际 suffix"（而非理论 max）上的复用，属统一模型态 2 的 sticky 负证据 + "几何实质变化"再触发，完全落在用户允许集内。

2. **点3（revoked:miss/req 2.84）主杠杆就是 P4**：DEVICE_QUOTA 竞争（845→1107）被 REVALIDATE-bet 亚阈值 waiter 的每 pass 空转人为抬高；P4 把它们移出容量唤醒 churn，竞争回落 → revoked:miss 随降。**量化预期：revoked:miss/req 2.84 → 约 2.2-2.4（≤2.5），最差 offender 34 → 约 15-22**。判定：**先 P4，后复测观点 3**；若仍 >2.5 再上独立小门（见 §P3 残留源），不建议本轮先做独立门（可能白改）。

3. **never-case 残留 11 事件（3%，max_suffix<256）不是 gate 边界缺口**，而是"请求进入 WAIT 时 max_suffix 尚 ≥256（host 物材未就位）、wait 期间 host 物材增长使 max_suffix 缩到 <256"的中途状态变化；**P4 的当前-suffix 门天然闭合它**（当前 suffix 也 < 阈值 → 不再被容量唤醒 → T13 recompute），无需独立改动。

4. **本轮修复后 tester 复测 6 点全 PASS 可达**：点4 由 P4 满足（too_short 380→~53，tight 315→~5）；点3 大概率随 P4（2.84→≤2.5，残风险需轮 2 观察）；点1/2/5/6 P4 不触碰，不回归（点2 restore_success 103 的 population A 当前 suffix 已合格，容量唤醒照常）。

5. **no-heuristic 自查（零违禁）**：P4 全部新增/改动 = 复用既有几何判据（当前 suffix vs prefetch_threshold）+ 既有容量判据（charge<available），无新增计数器、无 TTL、无次数阈值、无"连续 N 次后降级"。REVALIDATE bet 保留语义不变（has_restore_potential 的 max-suffix 判据原样，亚阈值 waiter 仍有 restore potential，device match 衰减后当前 suffix 增长即唤醒兑现 bet）。既有 SAFETY_FUSE / Fix A host_release epoch / T13 兜底 / P3 reconcile / P1 sticky-miss 全部不动。

---

## Current Architecture（证据核实）

### 1. 点4 紧循环的唤醒链（已核实）

- REVALIDATE-bet 请求（host-heavy：current suffix 23-61，max_suffix 16K-22K）在 T6（scheduler.py:4693-4735）被 `ADMISSION_DENY`（NO_TOKEN）送入 `WAIT[DEVICE_QUOTA]`：
  - `_restore_potential_for(req)`（:3807-3816）→ `has_restore_potential`（unified_radix_cache.py:3247-3284）。对 host-heavy 请求 `host_hit_length>0` → 直接 True，**不因当前 suffix 亚阈值而短路**（只有 max_suffix<阈值 的 never-case 才短路）。
  - `wait_reason_for(ADMISSION_DENY)`（hicache_restore.py:286-287）→ `DEVICE_QUOTA`。
- 每 pass `_reconcile_restore_states` step 4 T11（scheduler.py:3169-3217）：
  - `capacity_wake_applies(DEVICE_QUOTA)`（hicache_restore.py:497-502）= True；
  - `_restore_wait_capacity_fits`（scheduler.py:3721-3805）：
    - 现有 too_short 保底门（:3763-3769）只在 `prompt_can_qualify_for_prefetch(max_suffix)` 为 False 时拦；REVALIDATE-bet 的 max_suffix≥256 → **不拦**（设计上刻意保留 bet）；
    - `promotion_wait_blocked`（:3779-3792）：host_hit_length>0 且 budget 不足才拦——budget 够则不拦；
    - `charge < available_and_evictable_tokens`（:3793-3805）：容量充足时 **True** → `RETRY_PREFETCH` → `_prefetch_kvcache`（:2963）→ gate ok（backuped）→ `prefetch_from_storage(new_input_tokens=当前 suffix 23-61)` → `prefetch_length < threshold` → `declined_too_short`。
  - `DENIED_SHORT` 在 re-issue leg（state=RESTORING）→ `next_restore` T4（hicache_restore.py:124-132）→ NONE + ADMIT_RECOMPUTE → `_log_restore_recompute("too_short")`（scheduler.py:3213-3217）。
- 请求 recompute 后下一 pass 又因 restore-potential True 再入 DEVICE_QUOTA → 被容量兜底再唤醒 → 循环。**每 pass 一次，13-600ms**。tester 归因（367/378 = REVALIDATE-bet）与此链完全一致。

**结构结论**：唤醒源 = `charge < available` 的容量兜底对"当前 suffix 亚阈值"的 waiter 也成立。容量兜底只应服务"容量不足是真实拒绝因"的 waiter（population A，当前 suffix 已合格、re-issue 有产出）；对"真实拒绝因是 too_short"的 waiter（population B），容量兜底是**错误信号源**——容量释放不改变其 too_short 结果。

### 2. 点3 的 DEVICE_QUOTA 竞争构成（已核实）

- Q1 修复恢复 restore 路径（restore_success 53→103）后，更多请求进入 DEVICE_QUOTA 竞争（WAIT 845→1107，tester 表）。
- 其中 REVALIDATE-bet 亚阈值 waiter 是**人工抬高竞争**的成员：它们每 pass 空转 re-issue，占据队列位置、制造调度压力，且从不真正 restore（必 too_short）。
- revoked:miss 的 offender（34/36）含大量 <1s 紧循环（peranchor Q3 判定：容量驱动兜底），与被抬高的 DEVICE_QUOTA 池强相关。

### 3. never-case 残留（已核实）

- never-case 门 = `prompt_can_qualify_for_prefetch(max_suffix)`（unified_radix_cache.py:3235-3245），page_size=1 时 = `max_suffix >= 256`。
- 残留 11 事件的成因（推断，tester 未逐例深挖）：请求进入 WAIT 时 `max_suffix = prompt_len - host_hit_length >= 256`（host 物材未就位 → 理论 max 大），wait 期间 host 物材增长（host_hit_length 变大）→ max_suffix 缩到 <256 → re-issue 时 current suffix 也 < 256 → too_short。**不是 entry 时门没拦，是中途几何实质变化**。这与 REVALIDATE-bet 同链（都是"当前/理论 suffix 亚阈值"），P4 一并处理。

---

## Problem / Forces

- 用户硬约束（no-heuristic）：禁止新增计数器/TTL/次数阈值；miss_rearm 判据只允许 sticky 负证据 / 同锚 version 前移 / re-anchor / generation 变；tester 建议的"REVALIDATE-bet 次数/时长上限"明确违反。
- 必须在"保留 REVALIDATE bet（max-suffix 合格者保持 restore potential）"与"抑制每 pass 空转"之间取结构解——**不是去掉 bet，而是让 bet 的再触发绑定到"当前 suffix 实质增长（device match 衰减）"而非"容量释放"**。
- 统一模型契约（re-unified §3）已把 capacity 归态 4（资源在途）、too_short 归态 2（几何终局/REVALIDATE bet）。点4 的错配 = **态 2 的拒绝被错误归入态 4 的 wait reason**（DENIED via ADMISSION_DENY→DEVICE_QUOTA，而非 DENIED_SHORT→REVALIDATE），于是态 4 的容量唤醒错误地服务了态 2 的拒绝。P4 是最小对齐。

---

## P4 设计（点4 主修；spec 级）

### 核心判定（一句话）

> **DEVICE_QUOTA 容量唤醒只在"当前实际可 prefetch 后缀 >= prefetch_threshold 且容量实质充足"时触发；当前 suffix 亚阈值的 waiter 不被容量兜底唤醒，其再触发 = 当前 suffix 实质增长越过阈值（device match 衰减）或 T13 兜底 recompute。**

### 伪代码（scheduler.py `_restore_wait_capacity_fits`，DEVICE_QUOTA 分支）

```python
if req.hicache_restore_wait_reason is RestoreWaitReason.DEVICE_QUOTA:
    # --- 现有保底门（保留）：can-never-qualify（max_suffix < 阈值）→ 不唤醒 ---
    if req.full_untruncated_fill_ids is not None and not (
        self.tree_cache.prompt_can_qualify_for_prefetch(
            len(req.full_untruncated_fill_ids), req.host_hit_length
        )
    ):
        return False
    # --- P4 新增门（no-heuristic）：当前实际 suffix 也必须合格 ---
    # 当前可 prefetch 后缀 = 请求超过"宿主匹配 + device 匹配"的余量。
    # 它是 prefetch_from_storage 实际传给 new_input_tokens 的长度；
    # 当前 suffix < 阈值（REVALIDATE-bet / never-case 残留）时，容量唤醒的
    # re-issue 必然 declined_too_short → 每 pass 空转。容量释放不改变该
    # 结果，故不把容量作为该 waiter 的唤醒源。其合法再触发 = 当前 suffix
    # 实质增长越过阈值（device match 衰减 = 统一模型态 2 的"几何实质变化"）
    # 或 T13 兜底 recompute。max-suffix 合格（REVALIDATE bet）保留 restore
    # potential（has_restore_potential 不动），仅不因容量唤醒空转。
    if self._current_prefetch_suffix_lt_threshold(req):
        return False
```

其中 `_current_prefetch_suffix_lt_threshold(req)` 是复用既有几何判据的**当前口径**：

```python
def _current_prefetch_suffix_lt_threshold(self, req) -> bool:
    """当前实际可 prefetch 后缀是否 < prefetch_threshold（page_size 对齐）。
    与 prompt_can_qualify_for_prefetch 同口径，但用当前 match 几何
    （match_end - (len(prefix_indices) + host_hit_length)），而非理论 max
    （prompt_len - host_hit_length）。实现需保证当前 match 几何刷新
    （见 Migration 注 2）。"""
    matched_len = len(req.prefix_indices) + req.host_hit_length
    match_end = req._compute_max_prefix_len(len(req.full_untruncated_fill_ids))
    current_suffix = max(0, match_end - matched_len)
    return (current_suffix // self.page_size * self.page_size) < self.prefetch_threshold
```

### 它如何消除 13-600ms 紧循环

- REVALIDATE-bet waiter（当前 suffix 23-61 < 256）在 step 4 T11 的 `_restore_wait_capacity_fits` 返回 False → **不再每 pass RETRY_PREFETCH** → 不再 re-issue → 不再 declined_too_short → 不再 re-enter WAIT。紧循环消失。
- waiter 留在 DEVICE_QUOTA（restore potential 仍 True，bet 仍"armed"）。两条退出路径：
  1. **当前 suffix 实质增长越过阈值**（其他请求 evict 共享前缀的 device copy → 下一 pass 当前 match 变短 → current_suffix 变大）→ 门放行 → 容量唤醒 → re-issue → 真正 grant → restore_success（bet 兑现）。
  2. **T13 兜底**（`now - state_ts > timeout_s`，:3175-3180）→ TIMEOUT → ADMIT_RECOMPUTE。有界，一次而非每秒 72 次。

### 不破坏面（明确清单）

- **REVALIDATE bet 保留语义**：`has_restore_potential` / `_restore_potential_for`（max-suffix 判据）**不动**。亚阈值 waiter 仍算有 restore potential、仍能进 DEVICE_QUOTA wait；仅容量唤醒被抑制。bet 从"每 pass 空转试探"改为"仅在 device match 实际衰减（当前 suffix 越过阈值）时兑现"——这是 bet 的正确语义（原 bet 唯一合法唤醒源是 paced retry / 衰减，与统一模型态 2 的"几何实质变化"一致）。
- **population A（当前 suffix 合格的真实容量 waiter）**：`_current_prefetch_suffix_lt_threshold` 返回 False → 容量唤醒照常（charge<available 即 re-issue）。**点2 restore_success 103 的 population 不受影响**。
- **Fix A host_release epoch / ready_horizon**：不触碰。
- **T13 兜底**：保留（P4 waiter 的退出路径之一）。
- **P3 reconcile / A+B 补链 / clear 守卫 / P1 sticky-miss / miss_rearm_allowed / NO_L3 cursor / SAFETY_FUSE**：全部不动。点5（同锚 re-restore）的 re-arm 在 T6（miss_rearm_allowed），P4 不碰。
- **promotion_wait_blocked**（:3779-3792）：保留，在 P4 门之后继续生效（population A 且 budget 不足仍不唤醒）。

---

## P3 判定（点3 是否随 P4 解决）

### 结构因果

- revoked:miss/req 2.84 相对 peranchor 2.52 的增量，主因 = Q1 恢复 restore 路径使 DEVICE_QUOTA 竞争升高（845→1107，tester §4 点3）。竞争池中被 REVALIDATE-bet 亚阈值 waiter 的每 pass 空转人为抬高（它们是竞争成员但不产出 restore）。
- P4 把这些 waiter 移出容量唤醒 churn → DEVICE_QUOTA 池收缩、每 pass 的 re-issue/revoke 事件减少 → revoked:miss 分母（总 re-issue 事件）与分子（miss 事件）同时降，但**分母降得更快**（空转 re-issue 全消）。

### 量化预期（估计）

- revoked:miss/req **2.84 → 约 2.2-2.4**（≤2.5 目标上限）。依据：DEVICE_QUOTA 1107 → 约 700-800（移除 REVALIDATE-bet 空转成员后），且 peranchor 的 2.52 本身已含部分容量空转 churn（peranchor Q3 判定），P4 消除该 churn 的幅度大于 Q1 带来的 restore 恢复增量。
- 最差 offender **34 → 约 15-22**（接近 P1 9 需看 Q1 后合法 re-arm 占比；点5 PASS 证明同锚 re-restore 是合法机制，不应全部压回）。

### 是否需要独立小门？

**判定：先 P4，后复测观点 3，不预先做独立门。**理由：
- P4 是点3 的主杠杆，且是点4 的必然修复（两 FAIL 点同一根：DEVICE_QUOTA 池被态 2 拒绝成员污染）。
- 若 P4 后 revoked:miss/req 仍 >2.5，残留源是**合法同锚 re-arm 过多**（Q1 恢复 restore 后探活频率升高）。此时才考虑一个仍 no-heuristic 的独立收紧：**DEVICE_QUOTA 池内 genuine-miss 后 sticky 更彻底**——例如把"revoked:miss 已证明 L3 缺失"的请求，其 sticky 负证据的 re-arm 从"同锚 version 前移"进一步要求"该锚 version 前移**且**新物材确实覆盖该请求前缀"（等价 no-material 的 durable_ancestor 覆盖判定复用到 miss re-arm）。这是结构收紧（物材覆盖判定），非计数/TTL。
- 本轮不做，避免白改（P4 大概率已够）。

---

## never-case 残留边界闭合

- 成因（§Current 3）：中途 host 物材增长使 max_suffix 缩到 <256，非 entry 时门没拦。
- **闭合方案 = P4 的当前-suffix 门天然覆盖**：这些残留请求 re-issue 时 current suffix 也 < 256 → `_current_prefetch_suffix_lt_threshold` 返回 True → 容量唤醒不再触发 → T13 recompute。它们从"每 pass too_short"变成"有界一次 recompute"。
- 无需独立改动；entry 时 `prompt_can_qualify_for_prefetch` 不改（它已在 page 对齐口径正确）。
- 属同一对齐修正（suffix 判据统一到"当前实际"口径），非独立边界。

---

## 优先级排序 + 6 点全 PASS 可达性

| 优先级 | 修复 | 对应点 | 判定 |
|---|---|---|---|
| **P4（本轮唯一）** | DEVICE_QUOTA 容量唤醒加当前-suffix 门 | 点4（主）+ 点3（杠杆）+ never-case 残留 | 一改三得；no-heuristic 自查通过 |
| 观察（随 P4 复测） | 点3 revoked:miss 回落 | 点3 | 若 ≤2.5 PASS；若 >2.5 轮 2 加独立收紧（durable_ancestor 覆盖复用至 miss re-arm） |
| 留统一模型 | 态 2/态 4 wait-reason 对齐（态 2 拒绝归 REVALIDATE 而非 DEVICE_QUOTA） | 结构性归纳 | P4 是最小落地，统一模型吸收为契约精化 |

**6 点全 PASS 可达性：可达（高置信），条件 = P4 + 一次复测。**
- 点1（no-material）/ 点5（同锚 re-restore）/ 点6（correctness）：P4 不触碰 → 保持 PASS。
- 点2（restore_success 103）：population A 容量唤醒照常 → 保持 PASS（无回归风险）。
- 点4（too_short）：P4 主修 → 380→~53、tight 315→~5（REVALIDATE-bet 空转消；剩 never-case 11 + 少量真实 too_short）。
- 点3（revoked:miss）：大概率随 P4 → ≤2.5；唯一残风险，轮 2 兜底。
- **结论：本轮 P4 修复 + tester 复测，6 点全 PASS 可达；点3 为唯一残风险（需复测确认，若不过则轮 2 独立收紧）。**

---

## no-heuristic 禁令逐条自查（零违禁）

| 检查项 | 结论 |
|---|---|
| 新增计数器？ | 无。`_current_prefetch_suffix_lt_threshold` 是几何判据（match_end - matched_len），复用既有 `_compute_max_prefix_len` / `page_size` / `prefetch_threshold`，不新增任何计数状态。 |
| 新增 TTL？ | 无。不新增任何时间戳/超时。既有 T13（`hicache_restore_wait_timeout_s`）与 SAFETY_FUSE 为既有，保留不改。 |
| 新增次数阈值？ | 无。无"连续 N 次后降级"、无"REVALIDATE-bet 次数/时长上限"（tester 建议项明确未采纳）。 |
| 违反 miss_rearm 判据白名单（sticky / 同锚 version 前移 / re-anchor / generation）？ | 未违反。P4 不动 `miss_rearm_allowed` / T6 re-arm / NO_L3 cursor。新增门属于态 2（too_short）的"sticky 负证据 + 几何实质变化"——当前 suffix 亚阈值是 sticky 负证据，越过阈值（device match 衰减）是几何实质变化，同属允许的"状态实质变化驱动再触发"，非计数/TTL。 |
| 触碰既有 SAFETY_FUSE / Fix A host_release epoch？ | 否，均不动。 |

---

## Migration / Impact

改动面（单文件、纯 predicate 追加，无状态机/字段大改，与统一模型契约一致）：

1. `scheduler.py` `_restore_wait_capacity_fits` DEVICE_QUOTA 分支：追加 `_current_prefetch_suffix_lt_threshold` 判定（在当前保底门之后、promotion_wait_blocked 之前或之后均可，建议保底门后）。
2. 新增辅助 `_current_prefetch_suffix_lt_threshold`（复用 `_compute_max_prefix_len` / `page_size` / `prefetch_threshold`）。
3. **实现期注意（交 coder 核验）**：当前 match 几何（`prefix_indices` / `host_hit_length`）在 waiter 停 WAIT 期间是否刷新到"当前"——若停在入场值，需在 step 4 T11 的 DEVICE_QUOTA 分支做一次轻量当前 match 刷新（或在 `_prefetch_kvcache` 已刷新后复用其值）。这不改变设计语义（"当前实际 suffix"），只影响"能否在下一 pass 观察到 device match 衰减"。若刷新成本高，可将 device-match 衰减的观测放在 re-issue 前的同 pass `_prefetch_kvcache` 内（它本就每 pass 调 `init_next_round_input`）——门可改为"放行进 `_prefetch_kvcache` 后，若 re-issue 仍 declined_too_short 则本 pass 不再回 WAIT 循环"的等价形式。
4. 测试：增补
   - REVALIDATE-bet waiter（current suffix 亚阈值、max 合格）在容量充足时**不**被唤醒（`_restore_wait_capacity_fits` 返回 False）；
   - 当前 suffix 增长越过阈值后**被**唤醒（bet 兑现）；
   - population A（当前 suffix 合格）容量唤醒照常（不回归点2）；
   - never-case 残留（当前+max 均亚阈值）不被唤醒。
5. 不改：`has_restore_potential` / `prompt_can_qualify_for_prefetch` / `miss_rearm_allowed` / `capacity_wake_applies` / ready_horizon / hicache_restore 状态机 / tree_core / unified_radix_cache。

## Alternatives

- **A. 按 tester 建议加 REVALIDATE-bet 次数/时长上限**：TTL/次数 heuristic，用户明确禁止（ledger 多次冻结）。不采纳。
- **B. 把态 2 拒绝改归 REVALIDATE wait（而非 DEVICE_QUOTA）**：语义上最干净（对齐统一模型态 2/态 4 归属），但 REVALIDATE wait 的 `capacity_wake_applies=False` 本就无唤醒，直接 T13 空等 → 等于是"一刀切放弃 bet 的容量侧再触发"，且改动面大（wait_reason_for / 入场路径）。P4 用当前-suffix 门在容量侧保留 bet 兑现路径，更小且不丢 bet。**P4 采纳**，B 留统一模型作结构性归纳。
- **C. 全局降 DEVICE_QUOTA 并发 / 每 pass 只 re-issue 一部分**：容量/节流 heuristic，违反禁令。不采纳。
- **D. 完全禁用 REVALIDATE bet（亚阈值一律 recompute）**：放弃 max-suffix 合格者的 restore potential，点2 可能受影响（host-heavy 请求本可衰减后 restore）。与"保留 bet"契约冲突。不采纳。

## Open Decisions

1. **P4 的当前-suffix 观测点**：在 `_restore_wait_capacity_fits` 内轻量刷新当前 match vs 放行进 `_prefetch_kvcache` 后判断"still too_short 则本 pass 不再回环"——两种都满足设计，实现选成本低者（见 Migration 注 3）。倾向前者（纯 predicate，易单测）。
2. **点3 的 PASS 判据**：P4 后 revoked:miss/req 落 2.2-2.4（≤2.5）即过；若 2.5-3.0 需用户裁决（是否接受 ≈peranchor 水平，或要求回 P1 2.06）。offender 34→15-22 是否接受同样待裁决。
3. **轮 2 独立收紧（若点3 仍超）**：miss re-arm 加 durable_ancestor 物材覆盖复用——是否采纳待复测数据决定，本轮不做。

## followups

- 本 spec 交 coder 实现（P4 单点，含单测）；
- tester 复测 P1 deterministic workload 6 点（重点点3/点4）+ too_short/D2 系列；
- 统一模型：把态 2/态 4 的 wait-reason 归属精化（态 2 拒绝不归 DEVICE_QUOTA）纳入契约后续扩展。

## open_issues

- P4 的当前-suffix 观测实现点未定（Open Decision 1）。
- 点3 若 P4 后仍 >2.5 需用户裁决 / 轮 2 独立收紧（Open Decision 2/3）。
