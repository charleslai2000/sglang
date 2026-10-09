# phase2-round2-coder-e1 — 点3 独立收紧（miss re-arm durable_ancestor 物材覆盖）实现

```text
status: done
artifacts:
  - commit 9c9e7b7c7c（本地，未 push）：仓库 /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt，
    分支 3090-24g-opt，HEAD 由 920003bf07 -> 9c9e7b7c7c（独立 commit，仅含点3 生产改动 + 单测）
  - 生产改动 1 文件 + 测试 1 文件（详见 diff 摘要）
  - 报告：本文件
evidence:
  - 受影响 5 套件全绿：323 passed（基线 314 -> 323，净 +9 为本次新增用例）
  - 全 3090-dev/：429 passed，5 failed 为 BASE 预存在已知问题
    （test_drain_reentry `_FakeTreeCore` 缺 get_component_deviation，与本次改动无关；
    基线 420 -> 429，净 +9 为本次新增测试）
  - 命令：PYTHONPATH=python /home/charles/sglang-venv/bin/python -m pytest 3090-dev/<file>.py
summary:
  - commit hash: 9c9e7b7c7c
  - T6 三分支实现：scheduler.py `_miss_rearm_decision`（:3991，唯一调用点 :4849）显式替换
    原单点 miss_rearm_allowed 调用；miss_epoch None -> 放行；re-anchor / generation 变 -> 放行
    （优先于物材门）；同锚 version 前移 -> `_miss_rearm_durable_coverage` 物材门；否则 sticky。
  - 新增 `_miss_rearm_durable_coverage`（:4039，仅被决策内部 :4036 调用）：复用 Q1
    `self.tree_cache.deepest_durable_ancestor(anchor)`，non-None -> True；dda None（纯 device 链 /
    clear 后）-> False（sticky）；anchor None -> True（无锚可判）；dda 代理缺失（stub）-> True（回退放行）。
  - 实现期核验（Form A）：deepest_durable_ancestor 在 re-arm 时刻读当前锚链 on-disk 字段
    （is_l3_durable = storage_persisted/storage_restored），O(depth)，无每 pass 树匹配，纯 predicate。
  - 单测：新增 MissRearmDurableCoverageSchedulerFeedTests 9 用例（详见 §4），
    sync P1StickyMissSchedulerFeedTests._rearm_gate 到新三分支（原走模块级 pure 函数）。
  - no-heuristic 逐条自查：零违禁（详见 §6）。
followups:
  - tester 复测 P1 deterministic workload 6 点（重点点 3 revoked:miss/req ≤2.5；点 2/4 不回归）。
  - 点 3 若 ① 后仍 >2.5 -> 编排升级用户裁决（残留为带物材的合法同锚 re-probe，结构上不可再压）。
open_issues:
  - architect Open Decision 1（① 实际削减量）待复测确认；Open Decision 2（点 2 PASS 判据定格）待确认。
```

## 1. 核心改动（生产，scheduler.py）

### T6 调用点（:4763 原单点 -> 显式三分支，委托新方法）

原代码单点调用 pure 函数 `miss_rearm_allowed(...)`（已删 import，pure 函数本体保留在
hicache_restore.py:295，供其他调用/单测参考）。现改为：

```python
miss_rearm = self._miss_rearm_decision(req)
```

### 新增 `_miss_rearm_decision`（紧邻 `_anchor_version_or_zero` 之后，:3991）

显式三分支，architect spec 伪代码逐字实现：

```python
if req.hicache_restore_miss_epoch is None:
    return True                                  # defensive：无记录 -> 放行
cur_anchor = getattr(req, "last_host_node", None)
miss_anchor = req.hicache_restore_miss_anchor
cur_gen = getattr(req, "session_generation", None)
miss_gen = req.hicache_restore_miss_generation
re_anchored = (miss_anchor is not None and cur_anchor is not None
               and cur_anchor != miss_anchor)
generation_changed = cur_gen is not None and cur_gen != miss_gen
if re_anchored or generation_changed:
    return True                                  # 新候选 / 身份变：旧证据作废（优先于物材门）
if self._anchor_version_or_zero(cur_anchor) > req.hicache_restore_miss_epoch:
    return self._miss_rearm_durable_coverage(req)  # 同锚 version 前移：需物材覆盖
return False                                     # 同锚 version 未变 -> sticky
```

### 新增 `_miss_rearm_durable_coverage`（:4039）

```python
anchor = getattr(req, "last_host_node", None)
if anchor is None:
    return True                                  # 无锚可判，交给身份/锚判据
dda = getattr(self.tree_cache, "deepest_durable_ancestor", None)
if not callable(dda):
    return True                                  # stub/fallback：保守放行（保持既有行为）
return dda(anchor) is not None
```

Docstring 完整说明 clear/evict-rebuild bump version 却不留物材的结构语义，以及 O(depth)
物材存在性判定（非计数/TTL）。

## 2. Form A 核验（实现期核验项）

- **`deepest_durable_ancestor` 在 re-arm 时刻读的是否为当前锚链状态**：是。unified_radix_cache.py:2414
  `deepest_durable_ancestor(node_id)` 沿 parent 链调用 `tree_core.is_l3_durable(cur)`（=
  `storage_persisted or storage_restored`，写 ack + 父链连续 / restore 读回），每次 re-arm 时刻
  现场走链，读 on-disk 当前字段。O(depth)，无每 pass 树匹配 / 无缓存快照。与 P4
  `_current_prefetch_suffix_lt_threshold`（读 on-disk 几何字段）同 Form A 低开销。
- **`miss_epoch is None` 分支保留**：是（三分支第一支，防御放行）。
- **re-anchor 判定优先于覆盖判定**：是（第二支先于物材门；新候选不被物材门拦）。
- **纯函数保留**：`miss_rearm_allowed`（hicache_restore.py:295）本体未改，其专用单测
  StickyMissRearmGateTests（test_hicache_restore.py）8 passed 保持绿。T6 改为显式三分支调用
  （便于单测三路径）。

## 3. 不破坏面（硬约束逐条核验）

| 约束 | 核验 |
|---|---|
| has_restore_potential / prompt_can_qualify_for_prefetch / _current_prefetch_suffix_lt_threshold / _restore_wait_capacity_fits（P4 门，点4 不反弹） | 全部未改。原样保持在 :3721-3814 / :3841-3849。 |
| capacity_wake_applies / ready_horizon / hicache_restore 状态机 | 未改（hicache_restore.py 零 diff）。 |
| unified_radix_cache / tree_core | 未改（零 diff）。deepest_durable_ancestor 只读复用 Q1。 |
| Fix A / T13 / P3 A+B / P1 sticky-miss / SAFETY_FUSE / NO_L3 cursor | 未改。 |
| miss_rearm_allowed pure 函数本体 | 保留（hicache_restore.py:295，未改；供其他调用/单测参考），仅 T6 调用点重构。 |
| re-arm 白名单 | re-anchor / generation 原样放行（无条件 True，优先判定）；sticky 负证据语义不变；仅"同锚 version 前移"加物材覆盖守卫（结构判定）。 |
| 点5 不回归 | 真物材到达（写 ack promotion -> 链获 durable 祖先 -> dda non-None）-> 覆盖判定放行 -> re-arm -> restore 工作（单测 ① 锁定）。 |
| 点4 不回归 | P4 门零 diff，本改动在 T6 re-arm 层（准入前），不触碰容量唤醒。 |

## 4. 单测（+9，MissRearmDurableCoverageSchedulerFeedTests）

| 用例 | 覆盖（architect spec 4 类） |
|---|---|
| test_same_anchor_version_advance_with_durable_material_rearms | ① 同锚 version 前移 + 链有 durable 祖先 -> re-arm（点5 不回归，测试 1） |
| test_same_anchor_version_advance_without_durable_material_stays_sticky | ② 同锚 version 前移 + 链无 durable 祖先（纯 device / clear 后）-> 不 re-arm（sticky，测试 2） |
| test_same_anchor_version_unchanged_stays_sticky | P1 回归守卫：同锚 version 未变 -> sticky（无论物材门）。附双回路确认（dda non-None 也不触发物材门——门只在 version 前移时被咨询） |
| test_reanchor_rearms_regardless_of_material | ③ re-anchor（锚 42->99）-> 仍 re-arm，链无 durable 祖先也不拦（白名单保留，测试 3a） |
| test_generation_change_rearms_regardless_of_material | ③ generation 变（3->9）-> 仍 re-arm，无 durable 祖先也不拦（白名单保留，测试 3b） |
| test_no_miss_record_releases | ④a miss_epoch None（防御分支）-> 放行，不consult 树态 |
| test_missing_dda_proxy_falls_back_to_release | ④b deepest_durable_ancestor 代理缺失（stub）-> 回退放行（测试 4） |
| test_coverage_helper_anchor_none_releases | ④c 辅助方法直接覆盖：anchor None -> True |
| test_coverage_helper_direct | 辅助方法直接覆盖：dda non-None -> True / dda None -> False |

另：P1StickyMissSchedulerFeedTests._rearm_gate 由 `scheduler_mod.miss_rearm_allowed(...)` sync 到
`scheduler._miss_rearm_decision(req)`（现 T6 生产路径），该测试类 8 用例继续绿（其中
test_same_anchor_version_advance_rearms / test_generation_change_rearms_even_same_anchor /
test_reanchor_to_different_node_rearms 现走过新三分支的相应路径）。

## 5. 测试结果

- 5 目标套件（test_hicache_restore / test_hicache_restore_scheduler_feed / test_p3_warmtree_hol /
  test_ready_horizon_unit / test_storage_regression）：**323 passed**（基线 314 -> 323，净 +9 本次新增；
  p3_warmtree_hol 为工作区既有未跟踪文件，仅作为套件参与运行，未纳入 commit）。
- 全 3090-dev/：**429 passed，5 failed**——5 failed 全部为 test_drain_reentry `_FakeTreeCore` 缺
  `get_component_deviation` 的 BASE 预存在 mock 缺陷（前两轮已复核，与本次改动无关）；
  基线 416/420 -> 429，净 +9 为本次新增测试。
- StickyMissRearmGateTests（pure 函数本体单测）：8 passed。

## 6. no-heuristic 逐条自查（零违禁）

| 检查项 | 结论 |
|---|---|
| 新增计数器？ | 无。`_miss_rearm_durable_coverage` 是物材存在性判定（deepest_durable_ancestor 非 None），复用 Q1 既有 predicate + 既有 Req 字段，不新增任何计数状态。 |
| 新增 TTL？ | 无。不新增时间戳/超时；T13 / SAFETY_FUSE 既有不动。 |
| 新增次数阈值？ | 无。无"连续 N 次 miss 后降级"、无频率 cap。 |
| 违反 miss_rearm 白名单（sticky / 同锚 version 前移 / re-anchor / generation）？ | 未违反。四条件原样作为 re-arm 触发；仅对"同锚 version 前移"加"确有物材"的结构守卫（类比 P4 对容量唤醒加几何门，architect spec 明文）——不新增第五种触发。sticky 负证据语义不变；re-anchor / generation 无条件放行且优先判定。 |
| 触碰 P4 / SAFETY_FUSE / Fix A / T13 / P3 A+B / P1 状态机 / ready_horizon / unified_radix_cache / tree_core？ | 否，均不动。仅 scheduler.py T6 调用点重构 + 两辅助 predicate；hicache_restore.py / unified_radix_cache.py / tree_core 零 diff。 |

## 7. diff 摘要（commit 9c9e7b7c7c）

生产改动（scheduler.py，净 +88/-12）：
- `_miss_rearm_decision`（+55 行，含完整 docstring）+ `_miss_rearm_durable_coverage`（+32 行），
  紧邻 `_anchor_version_or_zero` 之后；
- T6 调用点（:4763-4777）单点 pure 调用 -> `self._miss_rearm_decision(req)`（含点3 语义注释）；
- import 清单移除 `miss_rearm_allowed`（T6 不再直接引用，pure 函数本体保留）。

测试改动（test_hicache_restore_scheduler_feed.py，净 +147/-13）：
- 新测试类 MissRearmDurableCoverageSchedulerFeedTests +9 用例（§4）；
- P1StickyMissSchedulerFeedTests._rearm_gate sync 到新三分支（-8/+7）。

不改：unified_radix_cache.py / radix_cache.py / schedule_batch.py / ready_horizon.py /
hicache_restore.py 状态机 / tree_core / P1 sticky miss / NO_L3 per-anchor cursor / P3 A+B 补链 /
clear 守卫 / T13 兜底 / Fix A / P4 门。