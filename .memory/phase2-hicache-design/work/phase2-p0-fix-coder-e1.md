# P0: build_backup_spec assert 修复（coder e1）

```text
status: done
artifacts:
  - python/sglang/srt/mem_cache/unified_radix_cache.py (修改点)
  - 3090-dev/test_backup_spec_assert_fix.py (新增 unit 测试)
evidence:
  - 5/5 新测试通过 (pytest 3090-dev/test_backup_spec_assert_fix.py -v)
  - 相关既有测试全绿: test_hicache_restore 74 / test_ready_horizon_unit 60 /
    test_fbe_flush_before_evict 8 / test_storage_regression 99
  - 原 assert 单元级稳定复现 (tc.build_backup_spec on forced-miss tombstone -> AssertionError)
  - commit cc718c3c2e
summary: 见下
followups:
  - tester: 在真实 stress (str-fx2 配置) 验证 P1/Fix A stress 不再被此崩溃打断
  - tester: 确认 _storage_gap_skipped_d2h_count / _storage_gap_skipped_nokv_count
    在生产观测到的来源 (demote vs insert vs forced-miss)
open_issues: 无 (本 P0 范围内)
```

## 1. 精确修改点

文件: `python/sglang/srt/mem_cache/unified_radix_cache.py`（RC）

1. **RC ~486**（`__init__` 计数器区）新增两个可观测计数器：
   - `_storage_gap_skipped_d2h_count`
   - `_storage_gap_skipped_nokv_count`

2. **RC 2148-2163**（`write_backup_storage` gap-fill 的 D->H 循环）：在
   `if not is_backuped(nid):` 内追加 device value 存在性守卫——
   `get_component_device_value(nid, BASE_COMPONENT_TYPE) is None` 时跳过 D->H
   backup（`continue` + 计数），不进入 `_execute_and_commit_kv_backup`。

3. **RC 2178-2191**（storage-write 循环）：在 `_write_backup_storage_node` 前追加
   `if not is_backuped(nid):` 显式跳过 + 计数（`_storage_gap_skipped_nokv_count`）。

diff 见 git（`git show cc718c3c2e`）。不改 `unified_tree_core.py` 的 assert 语义；
不删 assert、不 catch exception、不伪造 backup。

## 2. 原 assert 是否稳定复现

是。单元级直接复现（无需 GPU）：

```
forced-miss tombstone: device value=None, host_value=None, backuped=False
tc.build_backup_spec(node_id) -> AssertionError
```

固定复现脚本逻辑见 `3090-dev/test_backup_spec_assert_fix.py` 的
`test_both_absent_skipped_not_crashed`（修复前即触发，修复后由调用方守卫拦截）。

## 3. 修复后路径实际走向

关键语义澄清（来自 TC:165-167 `backuped == (FULL host_value is not None)`）：

| 状态 | D->H backup | Storage-write (host->L3) | 守卫 |
|---|---|---|---|
| device present, unbacked | ✅ 原路径（不回归） | 备份后 host 存在，随后写 L3 | 无（守卫不触发） |
| device absent, host present | 天然跳过（`is_backuped` True） | ✅ `build_storage_backup_spec` 读 host_value 写 L3 | 无 |
| device absent, host absent | 跳过（新守卫，否则原 assert 崩） | 跳过（新守卫，否则空写 L3 伪造链） | `_storage_gap_skipped_d2h_count` + `_storage_gap_skipped_nokv_count` |

- 修复真正拦截的是最后一行（both absent = forced-miss tombstone / hollow 无 KV），
  正是 architect 崩溃链 RC:2143→2144→1596→TC:2037 的节点。
- "device absent + host present" 本就因 `backuped==True` 走 host→L3 路径；
  守卫只是补强前两类并显式记录第三类，不改变既有合法路由。

## 4. 是否解除 P1/Fix A stress 的阻塞

基于语义判断 + unit 佐证：是。崩溃为预存 backup 路径缺陷（architect e3 判定，
Fix A/B 之前的既有代码），本修复消除了该崩溃回归。P1/Fix A stress（str-fx2 纯
容量耗尽 + write-back）不再被 `assert device_value is not None` 打断。后续需
tester 在真实 stress 配置确认（followups）。

## 5. unit 测试结果

```
3090-dev/test_backup_spec_assert_fix.py 5 passed
3090-dev/test_hicache_restore.py        74 passed
3090-dev/test_ready_horizon_unit.py     60 passed
3090-dev/test_fbe_flush_before_evict.py  8 passed
3090-dev/test_storage_regression.py     99 passed
```

运行方式: `PYTHONPATH=<repo>/python /home/charles/sglang-venv/bin/python -m pytest 3090-dev/<file>.py`

## 约束遵守

- 只修 P0，未动 restore re-arm / Fix A / durable-frontier reconciliation / filesystem GC。
- 不 push；本地 commit `cc718c3c2e`。
- 禁跨距正则已遵守（行级 grep + Read 局部窗口）。
- 与 Mamba flush-before-evict durability 不冲突：FBE 涉及 mamba host checkpoint
  eviction 延迟（test_fbe_flush_before_evict 8/8 通过）；本修复只路由 FULL value 的
  gap 节点，mamba 路径独立，互不干扰。
