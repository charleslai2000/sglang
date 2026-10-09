# p2io-coder-e21 — read-side seed alignment fix: instrumentation restored + critical path finding

- 任务：e21（e20 后继；coordinator 重定向：e7k 实锤读侧 last_hash 种子错位 → 修复；附带恢复 _t38c last_hash8 埋点 + 最小 deterministic 断言）
- 运行：2026-09-02（本机静态 + 纯 Python hash oracle 对拍；无 3090 权限跑 live）
- 报告：p2io-coder-e21.md

## 1. status

**pending**（侧任务 1 完成：写侧 seed 埋点恢复，全门 327 绿；侧任务 2 与核心 seed 修复被一个关键路径发现阻塞——coordinator 诊断引用的 legacy HiRadixCache 行不在 live 路径上，候选 A 在 live 对齐场景是 no-op。需 orchestrator 裁决：跑 live seed 对拍 或 采纳 B。）

## 2. artifacts

- `python/sglang/srt/mem_cache/unified_radix_cache.py` — `_write_backup_storage_node` 内新增 **T38C write-seed 埋点**（log-only，`/tmp/t38c-on` gate）：`pc_write_seed` 事件记录 `write_seed8`（写链 page-0 种子 = `node.parent.get_last_hash_value()`）+ `page0_hash8` + `n_pages`，供修复后与读侧 `pc_prefetch_enter` 的 `anchor.last_hash8` 直接字节对拍。`py_compile` OK。
- 读侧 `pc_prefetch_enter`（scheduler.py:2965-2990）**已存在且 live**：记录 `anchor.is_root/is_backuped/last_hash8`（无需恢复，已在）。
- `3090-dev/p2io_refhash.py` — 已存在；**经验证**：纯 Python 实现逐字节复现 e7k 原生值（CASE A page0 `9d373db1...` 全 4 页、CASE B page0 `fffe6757...`）→ 成为本机可信 hash oracle。

## 3. evidence（命令 + 真实输出）

### 3.1 hash oracle 对拍（本机）
```
CASE A root-seed page0 -> 9d373db168e3e6a0... (matches e7k §3.1)
CASE A full 4 pages   -> 9d37..., ba16..., 903f..., 45ff... (all match)
CASE B seed=page0     -> fffe67578a7510f5... (matches e7k §3.2)
```

### 3.2 全门 327
```
cd 3090-dev && PYTHONPATH=<repo>/python:<repo>/3090-dev python3 -m unittest \
  test_storage_regression test_hicache_restore test_drain_reentry \
  test_hicache_restore_scheduler_feed test_prefetch_budget_split_unit \
  test_ready_horizon_unit test_ready_horizon_partition \
  test_writeback_reserve_unit test_capacity_model_unit
-> Ran 327 tests in 0.132s  OK   (with new instrumentation)
```

### 3.3 关键路径发现（决定候选选择）
- **live 树缓存是 `UnifiedRadixCache`，不是 coordinator 引用的 legacy `HiRadixCache`**：
  - `registry.default_radix_cache_factory`（registry.py:80-148）对 qwen+`--enable-hierarchical-cache`（launch-l3-3090.sh:118）恒走 `_create_unified_radix_cache`（registry.py:199）。`HiRadixCache`（hiradix_cache.py:81）未被任何 live 工厂实例化/注册（grep 仅 hybrid_pool_assembler.py 的 DSA/MiniMax 路径引用）。
  - coordinator 根因引用的 `hiradix_cache.py:940 write_backup_storage`（signature `(node, backup_len)`）与 `hiradix_cache.py:1755-1773 match_prefix` 的 **deepest-backuped-ancestor walk-up** —— 都只在 legacy HiRadixCache。unified 的 `match_prefix`（unified_tree_core.py:843-850）`last_host_node = best_match_node`（无 walk-up 到不同 backuped 祖先）。
- **候选 A 在 live 对齐场景是 no-op**（oracle 实证）：
  ```
  对齐：write seed = A.hash_value[-1]；read seed = A.get_last_hash_value() = A.hash_value[-1]
  -> C write page0 == C read page0 == 84976891  HIT
  => 候选 A ('write node parent last hash') == 当前 read seed，不能改变对齐结果
  ```
- **候选 B（prefix_keys[-1]）用错种子**：`prefix_keys = get_prefix_hash_values(parent)`（unified_tree_core.py:551），`prefix_keys[-1] = parent.hash_value[-1]`（grandparent last），非 anchor 自身 last → 对齐场景会 MISS（skip anchor 自身页哈希）。
- **unified 路径唯一可复现错位 = split 诱导**（oracle 实证）：
  ```
  P(3页) + C(4页, seed=P.last=a50b91b3) -> 存 C page0=3c1c2168
  P split 成 P1(1页,last=df3f6198) + P2(2页)
  read seed=P1.last=df3f6198 -> C page0=70000149 != 3c1c2168  MISS
  ```

### 3.4 分歧机制归属
- e7j 特征：host_hit 20864-20898（大而稳）、storage_hit 恒 0、extent_write 155。host_hit 巨大且稳定说明 anchor 稳定（非频繁 split）；storage_hit 恒 0 需要写/读种子在每次查询都不同——这与"anchor 稳定但种子错位"不完全吻合。**live 写/读种子是否真的不同，必须用恢复后的 pc_write_seed vs pc_prefetch_enter.last_hash8 对拍才能坐实。**

## 4. summary

侧任务 1（恢复 _t38c last_hash8 埋点）**完成**：写侧补 `pc_write_seed`（记录写链种子 + page0 hash8），读侧 `pc_prefetch_enter` 本就在且 live；两者同一 `/tmp/t38c-on` gate，修复后可逐字节对拍。全门 327 绿。

核心 seed 修复**未盲目实施**：静态 + oracle 实证发现——(1) live 路径是 UnifiedRadixCache（coordinator 引用的 HiRadixCache 行不在 live 路径）；(2) 候选 A 在 live 对齐场景是 no-op；(3) 候选 B 用错种子；(4) unified 唯一可复现错位是 split 诱导，而候选 A/B 都不能正确修复 split 场景（split 后 anchor 的 in-memory last hash 变了，但 stored 链的种子是旧 last hash，无法从当前树状态重建）。e7j 的大且稳 host_hit 与"每次查询种子都不同"的特征也不完全吻合。

因此需要 orchestrator 裁决（见 followups）。不 fake 一个看似交付的 seed 改动。

## 5. followups（数量 + 位置 + 建议）

1. **【最高优先】live seed 对拍**（tester，orchestrator 调度）：在 3090 重跑 e7j 同配置，`touch /tmp/t38c-on` 采集 `pc_write_seed.write_seed8` vs `pc_prefetch_enter.anchor.last_hash8`，对同一 rid/span 比对。这直接决定：两值不同 → 真错位（据实修）；两值相同 → 种子不是根因（转查 backend 键空间 / prefix_keys 传递，回到 e7j 第 B 支）。
2. **候选选择再评估**：若 live 确认写/读种子不同，需先在 unified 路径坐实"何时不同"（split / 多请求交错的具体形态），再选 A 或 B；候选 A/B 在我分析下都有问题（A=no-op、B=错种子），可能需第三方案（如 split 时保持写链种子连续性 / prefix 传递 anchor 自身页）。
3. **分叉/交错形态**：unified `match_prefix` 无 legacy walk-up；若 live 仍错位，需查 unified 的 best_match_node 在多请求/evict/split 下的变化是否改变 anchor.last hash。
4. **RED→GREEN 单元**：once 修复方向确定，用 `3090-dev/p2io_refhash.py` oracle 构造 deterministic 断言（同 span 写→读 storage_hit=4）；当前 split 模型已可复现 0→错位，可作为 RED 基线。

## 6. open_issues（未解决/风险）

- **候选 A/B 均无法正确修复 split 诱导错位**（oracle 实证）：split 后 stored 链种子不可从当前树重建——这是 unified 路径的结构性风险，需设计级解法，非单行 seed 改动。
- **coordinator 根因引用行（hiradix_cache.py:940/1755）不在 live 路径**：诊断机制（deepest-backuped walk-up）属 legacy HiRadixCache；live 用 UnifiedRadixCache。存在"诊断与实现路径错位"的可能，需 live 数据定夺。
- **e7j host_hit 大且稳 + storage_hit 恒 0** 与"每次查询种子都不同"不完全吻合；不排除叠加 backend 键空间/prefix_keys 传递问题（e7j 第 B 支未完全排除）。
- 本任务未改 seed 语义、未动 extent backend/Z3/reserve/RH/[P3]；只加了 log-only 埋点。live 对拍跑完后按数据修复。
