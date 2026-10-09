# phase2-p0fix2-coder-e1 — Q1 durable_ancestor no-material 判定 + Q2 保底门口径对齐（coder 实现）

```text
status: done
artifacts:
  - commit 0f8542c1a5（本地，未 push）：仓库 /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt，分支 3090-24g-opt，
    HEAD 由 183001f860 -> 0f8542c1a5（独立 commit，仅含 Q1+Q2 改动 + 单测）
  - 生产改动 2 文件 + 测试 2 文件（详见下方 diff 摘要）
  - 报告：本文件
evidence:
  - 受影响 5 套件全绿：310 passed
    （test_hicache_restore / test_hicache_restore_scheduler_feed / test_p3_warmtree_hol /
      test_ready_horizon_unit / test_storage_regression）
  - 全 3090-dev/：416 passed，5 failed 为 BASE 预存在已知问题
    （test_drain_reentry `_FakeTreeCore` 缺 get_component_deviation，git worktree 于 183001f860 复核为
      BASE mock 缺陷，与本次改动无关；基线 406 passed -> 416，净 +10 为本次新增测试）
  - 运行命令：PYTHONPATH=python /home/charles/sglang-venv/bin/python -m pytest 3090-dev/<file>.py
summary:
  见下方分节：①Q1 实现（deepest_durable_ancestor + no-material 判定锚解析）；②Q2 实现与结论（口径已对齐，
  增补 page-align 回归锁）；③prefetch_threshold 语义判断结论；④Q2 前提与实测证据的关键偏差；⑤测试结果；⑥diff 摘要
followups:
  - tester 复测 P1 deterministic workload 6 点（点 4/6 需观察 Q1 修复后 restore_success 是否回 40+、
    too_short 是否回 53 水平）——注意 Q2 前提偏差（见 §4），too_short 回退的机制归因需以实测为准
  - Q1 修复后 RESTORE 面护栏验证（P2）：durable 祖先存在但不覆盖请求起点的 over-retain 边界
open_issues:
  - Q2 的 architect 前提（"保底门几何口径需 page_size 对齐"）与实际代码/证据矛盾：代码已 page-align
    （prompt_can_qualify_for_prefetch 早已 `max_suffix // page_size * page_size`），f4b42595 非 host_hit_length=0
    纯容量客户（实测 host_hit=19281，host-heavy）。见 §4。未做无意义的"几何->对齐"改动（原本就是对齐口径），
    只增补 page-align 回归测试锁定正确语义。
  - too_short 回退（点 6）真正机制：f4b42595 是 REVALIDATE bet 请求（device match 1600 未衰减、max-suffix 1630>=256），
    门设计上保留其 restore potential；13ms 紧循环更可能是 per-anchor 让此类 host-heavy 请求高频进入 WAIT 的集合漂移，
    需 tester 以修复后实测确认（不在 P0 编码范围）。
```

## 1. Q1 — no-material 判定前解析 durable_ancestor（architect 方向 B）

### 1.1 数据/接口（unified_radix_cache.py）

- 新增 `deepest_durable_ancestor(node_id) -> Optional[NodeId]` proxy：沿 `node_by_id().parent` 链向上，
  返回最接近 root 的 `is_l3_durable` 祖先；该节点自身 durable 则返回自身；沿行到 root 无 durable / 死锚返回 None。
  O(depth) per 调用（不 O(subtree)）。root `storage_persisted` 默认 False（tree_core:147），绝不误把 root 当 durable。
- 实现前已确认：`node_by_id` 返回的 `UnifiedTreeNode` 有 `parent` 属性（tree_core:112），可安全沿行；
  `node_exists` 守卫死锚自愈。

### 1.2 判定锚解析（scheduler `_no_material_fast_forward_for`）

- 判定前先 `durable_ancestor = tc.deepest_durable_ancestor(anchor)`；判定锚 = durable_ancestor（找到）else 原 anchor。
- **5 事实全部改在判定锚上求值**：
  - 事实 1 host_material：不变（`req.host_hit_length > 0`）。
  - 事实 2 storage_material：`durable_ancestor is not None`（找到即 durable），或判定锚本身 is_l3_durable / is_root。
  - 事实 3 pending_durable_ack：判定锚 is_storage_written / ongoing_backup 含判定锚。
  - 事实 4 deferred_durable_desc：判定锚 has_acked_descendant。
  - 事实 5 restorable_epoch_change：判定锚 ongoing_load_back / anchor_storage_version>0。
- **durable_ancestor 找不到（沿上行到 root 无 durable）→ None → 5 事实全缺失 → no-material → 立即 forward（主收益保留）**。
- 无 `deepest_durable_ancestor` proxy 的测试 stub 回退到原 anchor（行为不变，旧测试不回归）。

### 1.3 与 P3 reconcile 共存

有在途生产者 / deferred 后代（在判定锚上求值）→ 不 forward，保留 frontier wait + A+B 补链（`test_p3_warmtree_hol` 通过）。

## 2. Q2 — 保底门 page_size 对齐（architect 1+3）

### 2.1 关键结论：门原本已是页对齐口径

- `prompt_can_qualify_for_prefetch`（radix_cache:3214）**已经**是
  `max_suffix = max(0, prompt_len - host_hit_length); return max_suffix // self.page_size * self.page_size >= self.prefetch_threshold`。
- 三处调用（GATE_SKIP scheduler:3066 / 保底门 scheduler:3765 / `has_restore_potential` radix:3241）**全部**用这同一个
  已页对齐函数，口径一致。不存在"几何口径需改成页对齐"的缺口。
- 因此**未做"几何->对齐"的 no-op 改写**（改也是零行为变化），改为增补 `test_prompt_can_qualify_page_aligns_suffix`
  （page_size=16）锁定页对齐语义，防止未来回归成几何口径。

### 2.2 prefetch_threshold 语义判断（architect Open Decision 2）

- `prefetch_threshold = 256`（radix_cache:363 默认 / cache_controller:340,601，`max(threshold, page_size)` 兜底）。
- 它是"**页对齐后的 token 数**"，不是"页数"：`query_storage_hit_length` 与 `prefetch_from_storage` 都是
  `len(RadixKey(...).page_aligned(page_size))`（token 数）与 threshold（token 数）比较；`storage_hit_count %= page_size`
  亦按 token 对齐。
- 运行时配置 `page_size=1`（gate3_ab 负载），即 alignment 为空操作，几何=对齐，进一步说明该负载下 Q2 前提不成立。
- 结论：threshold 是 token 数；页对齐口径 `max_suffix // page_size * page_size` 与出站一致，门实现正确。

## 3. prefetch_threshold 语义判断结论（报告明确要求）

`prefetch_threshold` 是**页对齐后的最大 token 数**（与出站 `query_storage_hit_length` / `prefetch_from_storage`
的 `len(page_aligned_key)` 同一维度），不是页数。页对齐口径已正确落地在 `prompt_can_qualify_for_prefetch`，
无需改动；新增回归测试锁定。

## 4. Q2 前提与实测证据的关键偏差（须上报）

architect §Q2 声称"保底门几何口径放行、出站页对齐判 too_short"且"f4b42595 纯容量客户 host_hit_length=0"。**两条均与实际不符**：

1. **代码**：`prompt_can_qualify_for_prefetch` 早已页对齐（§2.1），三处同函数，无几何/对齐错配。
2. **证据**：f4b42595 实测 `host_hit=19281, prompt_len=20911, device_hit=1600`（runs.csv 行），是 host-heavy 客户
   （cached 20881/20911），**不是 host_hit_length=0 纯容量客户**。其 `requested=29` 是 page_size=1 下的 current suffix
   （match_end 20910 - matched_len 20881），而 gate 用 theoretical-max suffix `20911-19281=1630 >= 256` 判 qualify=True。

f4b42595 实为 **REVALIDATE bet**（too_short-fix 7155cd8973 明确保留：current suffix 亚阈值但 max suffix 达阈值、
device match 衰减后可增长）。13ms 紧循环的真实机制更可能是 per-anchor 让此类 host-heavy 请求高频进入 WAIT 的集合漂移
（architect 亦部分归因于此），而非保底门口径错配。修复 Q1 不触及此路径；Q2 无需"对齐"改动。请 tester 以修复后实测复核点 6。

## 5. 测试结果

全部受影响套件通过（PYTHONPATH=python /home/charles/sglang-venv/bin/python -m pytest）：

- test_hicache_restore / scheduler_feed / p3_warmtree_hol / ready_horizon_unit / storage_regression：**310 passed**。
- 新增用例：
  - Q1 真实树（test_storage_regression `DeepestDurableAncestorTests`，5 个）：浅锚非 durable 但更深祖先 durable ->
    返回深层祖先 / 锚自身 durable -> 返回自身 / 纯设备链无 durable -> None / root 不报 durable / 死锚 -> None。
  - Q1 scheduler 侧（scheduler_feed `NoMaterialFastForwardSchedulerTests`，4 个）：durable_ancestor 非空不 forward /
    None forward（主收益）/ deferred 后代保 wait / anchor_version>0 保 wait。
  - Q2 页对齐（storage_regression `FrontierWaiterRegistryTests::test_prompt_can_qualify_page_aligns_suffix`）：
    page_size=16 下几何 vs 对齐边界（255->240 不 qualify / 256->256 qualify / host 扣除同对齐）。
- 全 3090-dev/：416 passed / 5 failed（drain_reentry BASE mock 缺陷，与本次无关；基线 406 -> 416 净 +10）。

## 6. diff 摘要（commit 0f8542c1a5）

生产改动：
- unified_radix_cache.py：+31 行（`deepest_durable_ancestor` proxy，parent 链沿行，O(depth)）。
- scheduler.py：+70/-19 行（`_no_material_fast_forward_for` 判定前解析 durable_ancestor，判定锚求值 5 事实）。

测试改动：
- test_hicache_restore_scheduler_feed.py：+62 行（`_tree` 增 deepest_durable_ancestor 注入 + 4 个 Q1 scheduler 用例）。
- test_storage_regression.py：+115 行（`DeepestDurableAncestorTests` 5 个真实树用例 + 1 个 Q2 页对齐回归用例）。

不改：P1 sticky miss 状态机 / NO_L3 per-anchor cursor / P3 A+B 补链 / clear 守卫 / T13 兜底 / Fix A。
