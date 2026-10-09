# phase2-p4-round2-design-architect-e1 — 点3 独立收紧（miss re-arm durable_ancestor 物材覆盖）+ 点2 裁决 + 6 点全 PASS 可达性

```text
status: done
artifacts:
  - 本报告（read-only 架构设计，未改任何代码；spec 供 coder 实现）
evidence:
  - tester P4 复测: work/phase2-p4-tester-e1.md（4/6 PASS；点2 103→77；点3 2.964 FAIL；
    MISS_RECOMPUTE 1718>1659；§7 缺陷 2 条）
  - architect 上轮 P4 设计: work/phase2-p4-p3-design-architect-e1.md（§P3 轮 2 独立收紧预判）
  - coder P4 实现: work/phase2-p4-coder-e1.md（920003bf07；Form A 纯 predicate）
  - 统一模型: work/phase2-re-unified-architect-e1.md（态 1 definitive-miss 四元组）
  - 代码（只读诊断）: scheduler.py T6 re-arm :4763-4777 / miss 记录 :3247-3252 /
    _current_prefetch_suffix_lt_threshold :3841-3849 / _restore_wait_capacity_fits :3721-3814 /
    _apply_restore_event :3334-3387；hicache_restore.py miss_rearm_allowed :295-335 / next_restore T6 :135-146；
    unified_radix_cache.py deepest_durable_ancestor :2414-2443 / is_l3_durable :2374-2379 /
    anchor_storage_version :2389-2397 / prefetch_from_storage :2629-2698（declined_too_short 门）；
    unified_tree_core.py is_l3_durable :2253-2260 / storage_version 字段 :154-163 / advance_storage_persisted :2262-2280
summary:
  Conclusion
  Current Architecture（证据核实）
  Problem / Forces
  ① 点3 独立收紧设计（miss re-arm durable_ancestor 物材覆盖）
  ② 点2 裁决（接受 77）
  ③ 合并后 6 点全 PASS 可达性 + no-heuristic 逐条自查
  优先级排序
  Migration / Impact
  Alternatives
  Open Decisions
```

## Conclusion（一页裁决）

1. **点3 的残留 = 合法同锚 re-arm 的"空探活"子集**：P4 已杀掉 REVALIDATE-bet 每 pass 空转（too_short 315→2），残留的 MISS_RECOMPUTE 1718 全部来自 Q1 恢复后的真实 restore 探活（同锚 version 前移触发 re-arm → re-probe → miss）。其中**一部分 re-probe 在结构上注定失败**：同锚 version 前移也可能由"durable-belief 清除 / evict 后重建"这类**不产生可恢复物材**的事件触发，此时 re-probe 该锚必然 miss，白贡献 revoked:miss。
2. **最小 no-heuristic 独立收紧 = 复用 Q1 的 deepest_durable_ancestor 物材覆盖判定**：同锚 version 前移 re-arm 额外要求"该锚链现在确有 durable 物材覆盖请求前缀"（deepest_durable_ancestor(anchor) 非 None）。无 durable 祖先（纯 device 链）→ 保持 sticky，不 re-arm。这是**结构判定（物材存在性），非计数/TTL**，完全落在用户 re-arm 白名单内（不加新触发条件，只约束"同锚 version 前移"这一条需有物材佐证）。re-anchor / generation 两条 re-arm 原样放行。
3. **② 裁决：接受 restore_success 77，不微调 P4 门语义**。103→77 的 delta 正是 P4 消除 too_short 空转的**结构性代价**（亚阈值 waiter 的投机兑现从每 pass 试探改 T13 有界一次）。77 仍高于修复前 peranchor 53（restore 能力基线），且点1/5/6 PASS 证明无 no-material 误杀、同锚 re-restore 循环真实工作。恢复 103 的手段（亚阈值 waiter 容量唤醒但"当前 suffix 未变则不 re-issue"）会重新打开点4 空转，收益 26 次 restore 远小于 313 次 empty-spin 的代价，不值得。
4. **① 与 ② 正交，无张力**：① 只移除"注定 miss 的 no-material re-probe"（这些从不产生 restore_success），restore_success 77 稳定，不会被 ① 进一步压低。
5. **③ 合并后 6 点全 PASS = 可达（条件性）**：唯一 gate 项 = ① 使 revoked:miss/req 从 2.964 降到 ≤2.5。若 ① 后仍 >2.5，残留 = 带 durable 物材的合法同锚 re-probe（点5 领域，结构上不可再压），须升级用户裁决（接受 ≈peranchor-2.9 或放宽目标），不能靠 heuristic 硬压。
6. **no-heuristic 零违禁**：本轮唯一新判定 = deepest_durable_ancestor 物材存在性（几何/durability），复用 Q1 既有 predicate，无计数器/TTL/次数阈值，re-arm 白名单四条件原样保留。

---

## Current Architecture（证据核实）

### 1. miss re-arm 链（已核实）

- **miss 记录**（scheduler.py:3247-3252）：REVOKED_MISS+genuine_miss 时记 `hicache_restore_miss_epoch`（= `_anchor_version_or_zero(anchor)`，anchor=`last_host_node`）、`miss_anchor`、`miss_generation`。
- **T6 re-arm 判定**（scheduler.py:4763-4777）：`miss_rearm = miss_rearm_allowed(miss_epoch, cur_anchor_version, miss_gen, cur_gen, miss_anchor, cur_anchor)`，传给 `_apply_restore_event(ADMISSION_DENY, rearm_allowed=miss_rearm)`。
- **pure 判定**（hicache_restore.py:295-335 `miss_rearm_allowed`）：`miss_version is None → True`；re-anchor（cur_anchor != miss_anchor）→ True；**同锚 `current_version > miss_version` → True**；generation 变 → True；否则 False。
- **T6 转移**（next_restore :135-146）：`state==MISS_RECOMPUTE and not rearm_allowed` → 保持 MISS（sticky，ADMIT_RECOMPUTE）；rearm_allowed → WAIT_CAPACITY → 下一 pass T11 容量唤醒 re-probe。

### 2. durable_ancestor 物材覆盖信号（Q1，已核实）

- `deepest_durable_ancestor(node_id)`（unified_radix_cache.py:2414-2443）：沿 parent 链找最 rootward 的 L3-durable 祖先，O(depth)；None = 纯 device 链（锚无 L3 物材）或锚已死。
- `is_l3_durable`（unified_tree_core.py:2253-2260）= `storage_persisted or storage_restored`（写入 ACK + 父链连续，或 restore 读回）。
- Q1 在 `_no_material_fast_forward_for` 用 `deepest_durable_ancestor` 把浅锚解析为判定锚（避免"浅锚非 durable 但深祖先 durable"的误 forward）。**核心覆盖事实 = fact 2 `storage_material = durable_ancestor is not None`**（该锚链有可 restore 的 L3 物材）。
- 同锚 version（`anchor_storage_version`，tree_core:2165 / storage_version 字段 :154-163）：**仅该锚链的 durability 事件 bump**（写 ack promotion / restore 读回 / durable-belief clear）。注：**clear 也 bump**（统一模型 Open Decision 1 采纳"实际清除时 bump"）。

### 3. P4 门（已核实，与 ① 正交）

- `_current_prefetch_suffix_lt_threshold`（scheduler.py:3841-3849）：current_suffix = match_end − (len(prefix_indices)+host_hit_length)，页对齐比较 prefetch_threshold。
- 挂在 `_restore_wait_capacity_fits` DEVICE_QUOTA 分支（:3763-3791），抑制亚阈值 waiter 的容量唤醒。**只作用于 WAIT_CAPACITY 的唤醒，不触碰 T6 re-arm**（re-arm 在前，容量唤醒在后）。

**结构结论**：点3 残留的 revoked:miss = T6 同锚 version 前移 re-arm → WAIT → T11 容量唤醒 → re-probe → miss。其中**无物材的 re-probe 是结构性必败**：同锚 version bump 不完全等于"产生了覆盖该请求的物材"——clear（移除 durable 信念）与 evict-rebuild（链清空重建）都 bump version 却可能不留下可 restore 物材。这正是我上轮 P4 §P3 预判的"合法同锚 re-arm 过多"残源。

---

## Problem / Forces

- 用户硬约束：禁止计数/TTL/次数阈值；miss_rearm 判据只允许 sticky 负证据 / 同锚 version 前移 / re-anchor / generation 变。
- 点3 已证实不随 P4 回落反升（2.964 > 2.5；offender 38 反升），需独立收紧，但**不能违反 re-arm 白名单**。
- 点2 部分回落（103→77）是 P4 消除点4 空转的次生代价，需裁决可接受性。
- 收紧必须**不破坏点5**（合法同锚 re-restore 仍工作：物材真正覆盖时放行）与**不破坏点4**（P4 已达成，收紧不得重新引入 too_short 空转）。

---

## ① 点3 独立收紧（miss re-arm durable_ancestor 物材覆盖）

### 核心判定（一句话）

> **同锚 version 前移 re-arm 额外要求"该锚链现在确有 durable 物材覆盖请求前缀"（复用 Q1 的 deepest_durable_ancestor：non-None = 有物材）；无 durable 祖先（纯 device 链 / clear 后无物材）→ 保持 sticky 不 re-arm。re-anchor 与 generation 两条 re-arm 原样放行。**

结构依据：同锚 version 前移是"该锚链发生 durability 事件"的因果信号，但**不保证事件留下可 restore 物材**——clear（移除 durable 信念）与 evict-rebuild（链清空重建）都 bump version 却不产生覆盖物材。对这些 re-probe 是结构性必败（revoked:miss 白贡献）。Q1 的 `deepest_durable_ancestor is not None` 正是"该锚链有可 restore L3 物材"的精确判定（Q1 fact 2），直接复用。

### 伪代码（scheduler.py T6 调用点，:4763 处重构为显式分支）

```python
# scheduler.py T6 admission（替换现有单点 miss_rearm_allowed 调用为显式三分支）
if req.hicache_restore_miss_epoch is None:
    miss_rearm = True                                  # defensive：无记录 → 放行
else:
    cur_anchor = getattr(req, "last_host_node", None)
    miss_anchor = req.hicache_restore_miss_anchor
    cur_gen = getattr(req, "session_generation", None)
    miss_gen = req.hicache_restore_miss_generation
    re_anchored = (miss_anchor is not None and cur_anchor is not None
                   and cur_anchor != miss_anchor)
    generation_changed = (cur_gen is not None and cur_gen != miss_gen)
    if re_anchored or generation_changed:
        miss_rearm = True                              # 新候选 / 身份变：旧证据作废
    elif self._anchor_version_or_zero(cur_anchor) > req.hicache_restore_miss_epoch:
        # 同锚 version 前移：re-arm 仅在"该锚链确有 durable 物材覆盖"时放行
        # （Q1 deepest_durable_ancestor 复用；无物材 = 结构性必败 re-probe）
        miss_rearm = self._miss_rearm_durable_coverage(req)
    else:
        miss_rearm = False                             # 同锚 version 未变 → sticky
```

新增辅助（紧邻 `_anchor_version_or_zero`，复用 Q1 的 `deepest_durable_ancestor`）：

```python
def _miss_rearm_durable_coverage(self, req) -> bool:
    """Q1 物材覆盖复用：该锚链是否确有 durable L3 物材（deepest_durable_ancestor
    non-None）。同锚 version 前移是"该锚链发生 durability 事件"的因果信号，但
    clear（移除 durable 信念）与 evict-rebuild（链清空重建）都 bump version 却
    不留下可 restore 物材；对无物材链 re-probe 是结构性必败（revoked:miss 白贡献）。
    纯 device 链（deepest_durable_ancestor=None）→ 保持 sticky，不 re-arm；
    其真实 re-arm 路径 = re-anchor / generation 变 / 后续物材真正到达（届时
    该锚链重获 durable 祖先，判定放行）。O(depth) 物材存在性判定，非计数/TTL。
    无 deepest_durable_ancestor 代理（测试 stub）→ 回退放行，保持既有行为。"""
    anchor = getattr(req, "last_host_node", None)
    if anchor is None:
        return True                                   # 无锚可判，交给身份/锚判据
    dda = getattr(self.tree_cache, "deepest_durable_ancestor", None)
    if not callable(dda):
        return True                                   # stub/fallback，保守放行
    return dda(anchor) is not None
```

### 它如何降 revoked:miss

- 无物材的同锚 re-arm（clear 后 / 纯 device 链）→ `_miss_rearm_durable_coverage` False → rearm_allowed=False → `next_restore` T6 保持 MISS sticky（不 re-arm）→ 不 re-probe → 不产生 revoked:miss。
- 真正写 ack promotion / restore 读回使链 durable（dda non-None）→ 放行 → re-arm → re-probe → 物材覆盖时 restore_success（点5 保留）。

### 不破坏面（明确清单）

- **点5（legitimate 同锚 re-restore）**：真物材到达（写 ack promotion → 链获 durable 祖先 → dda non-None）→ 覆盖判定放行 → re-arm → restore 工作。73/77 restore_success 的 prior WAIT+RESTORING 循环不受影响（它们链上有物材）。被压掉的只是"无物材却 re-probe 必败"的空探活。
- **点4（too_short 54/3）**：① 在 T6 re-arm 层（准入前），不触碰 `_restore_wait_capacity_fits` 容量唤醒（P4 门原样）。被 ① 压住的请求走 sticky recompute-forward，不进 WAIT 空转。too_short 不反弹。
- **re-arm 白名单**：不加新触发条件；re-anchor / generation 原样放行；仅约束"同锚 version 前移"需有物材佐证（结构判定，类比 P4 对容量唤醒加几何门）。sticky 负证据语义不变。
- **ready-horizon NO_L3 cursor / SAFETY_FUSE / T13 / P3 A+B / P1 sticky-miss 状态机**：全部不动。
- **不丢最终 restore 机会**：被 ① 压住 → 保持 sticky → ADMIT_RECOMPUTE（recompute-forward）。后续若物材真正到达，请求以新候选身份（非 MISS 态）重新评估，可 restore。单发请求 recompute-forward 是正确 fallback（点6 正确性）。

---

## ② 点2 裁决（restore_success 77）

### 裁决：**接受 77，不微调 P4 门语义**。

依据：
- **77 仍是结构性提升**：高于修复前 peranchor 53（restore 能力基线，+45%），点1/5/6 PASS 证明无 no-material 误杀、同锚 re-restore 循环真实工作。
- **103→77 的 delta = P4 消除点4 空转的结构性代价**：亚阈值 waiter 的投机兑现从"每 pass 容量试探"改"T13 有界一次"（tester §4 点2 归因：cause=capacity retry 1063→671，timeout 1→14）。恢复 103 = 恢复亚阈值投机兑现 = 重新打开 too_short empty-spin（315）。收益 ~26 次 restore << 313 次 empty-spin 代价，**不值得**。
- **与 ① 无张力**：① 只移除"注定 miss 的 no-material re-probe"，这些从不产生 restore_success；restore_success 77 在 ① 下稳定，不会进一步压低。故点2 与点3 可同时达标，无需协调取舍。

### 已考虑但否决的微调

- **"容量释放时唤醒亚阈值 waiter，但当前 suffix 未变则不 re-issue"**：等价于恢复亚阈值 per-pass 试探（每个 T11 唤醒都跑当前-suffix 判定 + re-issue 决策），正是 P4 要消除的开销。否决。
- **"T13 前额外加一次容量兑现窗口"**：在"无空转"与"投机兑现"之间再加一个 TTL/定时触发，接近 heuristic，且收益（少量 restore）不明确。否决。

> 注：77 的 PASS 判据应定格为"**> peranchor 53 且点1/5 无回归**"，而非"保持 ~103"。103 是含空转的虚高值，不是 restore 能力上限。

---

## ③ 合并后 6 点全 PASS 可达性

### 判断：可达（条件性），唯一 gate 项 = ① 使点3 ≤2.5

| 点 | 当前 | 合并后预期 | 判据 |
|---|---|---|---|
| 点1 no-material | PASS（1） | PASS（① 不触碰） | 保持 |
| 点2 restore_success | 77（裁决接受） | **77（稳定，① 不压低）** | PASS（>53 且点1/5 无回归） |
| 点3 revoked:miss/req | **2.964 FAIL** | **≤2.5（① 主修）** | **唯一 gate 项** |
| 点4 too_short | PASS（54/3） | **54/3（P4 保持，① 不触碰）** | PASS 不反弹 |
| 点5 同锚 re-restore | PASS | PASS（真物材 re-arm 仍放行） | 保持 |
| 点6 correctness | PASS | PASS | 保持 |

### 量化预期（估计，需复测确认）

- **revoked:miss/req：2.964 → 目标 ≤2.5，期望落 ~2.3-2.5**。需从 1669 事件移除 ~260（~16%）才能到 2.5；即 ① 需拦截 ~260 个无物材 re-probe。这是**唯一不确定项**（无法静态断言多少 revoked:miss 落在 dda-None 链上，必须实测）。
- **restore_success：77 稳定**（① 只移除必败探活，不触碰真 restore）。
- **too_short：54/3 不反弹**（① 不在容量唤醒层，P4 门原样）。
- **点3 若 ① 后仍 >2.5**：残留 = 带 durable 物材的合法同锚 re-probe（点5 领域）。这些**结构上不可再压**（任何再压都会误杀点5 合法 re-restore），且不能用 heuristic 硬压 → **升级用户裁决**：接受 ≈peranchor-2.9 水平，或放宽目标上限，或接受点5/点3 的固有 trade。

### 新增/改动 no-heuristic 逐条自查（零违禁）

| 检查项 | 结论 |
|---|---|
| 新增计数器？ | 无。`_miss_rearm_durable_coverage` 是物材存在性判定（deepest_durable_ancestor non-None），复用 Q1 既有 predicate + 既有字段，不新增任何计数状态。 |
| 新增 TTL？ | 无。不新增时间戳/超时；T13/SAFETY_FUSE 既有不动。 |
| 新增次数阈值？ | 无。无"连续 N 次 miss 后降级"、无频率 cap。 |
| 违反 miss_rearm 白名单（sticky / 同锚 version 前移 / re-anchor / generation）？ | 未违反。四条件原样作为 re-arm 触发；仅对"同锚 version 前移"加"确有物材"的**结构守卫**（类比 P4 对容量唤醒加几何门）——不新增第五种触发，只是约束已有触发需有物材佐证。sticky 负证据语义不变。 |
| 触碰 P4 / SAFETY_FUSE / Fix A / T13 / P3 A+B / P1 状态机 / ready_horizon？ | 否，均不动。仅 T6 调用点重构为显式分支 + 新增一辅助 predicate。 |

---

## 优先级排序

| 优先级 | 项 | 判定 |
|---|---|---|
| **必修（本轮唯一代码改动）** | ① miss re-arm durable_ancestor 物材覆盖 | 点3 gate 项；no-heuristic 自查通过 |
| **裁决（无代码）** | ② 接受 restore_success 77 | PASS 判据定格为 >53 且点1/5 无回归 |
| **观察（随 ① 复测）** | ③ 6 点全 PASS | 点3 ≤2.5 → 全 PASS；>2.5 → 升级用户裁决（残留为点5 领域，结构不可再压） |

---

## Migration / Impact

改动面（单文件 scheduler.py，纯 predicate 追加 + 调用点重构，无状态机/字段大改）：

1. `scheduler.py` T6 调用点（:4763-4777）重构为显式三分支（miss_version None / re-anchor 或 generation / 同锚 version 前移 + 覆盖）。
2. 新增 `_miss_rearm_durable_coverage(req)` 辅助（复用 `self.tree_cache.deepest_durable_ancestor`，O(depth)）。
3. 不改：`miss_rearm_allowed` pure 函数本体（保留，供其他调用/单测参考；或同步内联——建议保留 pure 函数但 T6 显式分支调用，便于单测三路径）、`has_restore_potential` / `prompt_can_qualify_for_prefetch` / `_current_prefetch_suffix_lt_threshold` / `_restore_wait_capacity_fits` / ready_horizon / hicache_restore 状态机 / unified_radix_cache / tree_core。
4. 测试增补：
   - 同锚 version 前移 + 链有 durable 祖先 → re-arm（点5 不回归）；
   - 同锚 version 前移 + 链无 durable 祖先（纯 device / clear 后）→ 不 re-arm（sticky）；
   - re-anchor / generation 变 → 仍 re-arm（白名单保留）；
   - `deepest_durable_ancestor` 代理缺失（stub）→ 回退放行（防御）。

实现期核验项（交 coder）：
- `deepest_durable_ancestor(anchor)` 在 re-arm 时刻读的是否为当前锚链状态（与 P4 Form A 同：读 on-disk 字段，无每 pass 树匹配）——建议纯 predicate，同 Form A 低开销。
- 确认 `miss_epoch is None` 分支保留（防御），且 re-anchor 判定优先于覆盖判定（新候选不该被物材门拦）。

---

## Alternatives

- **A. 对同锚 re-arm 直接禁用（只留 re-anchor/generation）**：会压掉"真物材到达后的合法 re-restore"（点5 FAIL）。否决——物材覆盖判定是精确的，一刀切过杀。
- **B. miss_rearm_allowed pure 函数内加物材参数**：把树依赖塞进 pure 函数（传 dda 结果进去），可行但需在调用点先算 dda，等价于 ① 只是换位置。**保留 pure 函数、在 T6 调用点做覆盖判定**更内聚（树访问在调度器边界），采纳。
- **C. 全局降 re-probe 频率（TTL/退避）**：heuristic，用户禁止。否决。
- **D. 接受 2.964（不修点3）**：点3 FAIL，不进 soak，违背用户"先修再进 soak"。仅作 ① 无效后的用户裁决回退项。
- **E. 恢复 restore_success 103（微调 P4 门）**：重新打开点4 空转。否决（见 ②）。

## Open Decisions

1. **① 的实际削减量**：多少 revoked:miss 落在 dda-None 链上无法静态断言。若 ① 后 revoked:miss/req 仍 >2.5，残留 = 带物材的合法同锚 re-probe（点5 领域）→ 升级用户裁决（接受 ≈peranchor-2.9 / 放宽目标），不能 heuristic 硬压。
2. **点2 PASS 判据**：建议定格"restore_success > peranchor 53 且点1/5 无回归"，不再以"~103"为标杆（103 含空转虚高）。待用户/编排确认。
3. **`deepest_durable_ancestor` 在 re-arm 时刻的观测**：Form A（读 on-disk 当前态）vs 入场快照——建议 Form A（同 P4），实现期核验。

## followups

- spec 交 coder 实现（① 单点 + 单测）；
- tester 复测 P1 deterministic workload 6 点（重点点3/点2/点4 不回归）；
- 点3 若仍 >2.5 → 编排升级用户裁决（非 heuristic 可解）；
- 统一模型：把"同锚 version 前移 re-arm 需物材覆盖"精化为态 1 definitive-miss 的 rearm_condition 细化（覆盖维度并入契约）。

## open_issues

- ① 的削减量待复测（Open Decision 1）——唯一 gate 项。
- 点2 PASS 判据待确认（Open Decision 2）。
