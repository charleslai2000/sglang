# phase2-hicache-design-coder-e12-01 — P2-1 终判唯一阻塞项：sanity_check 接受 hollow 合法态

## status

**done**（语义判定 + 最小修复 + 3 新测 RED→GREEN + 本机/远端全量回归 100/100 + 双侧 md5 一致 + 引擎未启动）

## 1. hollow 态语义判定：**合法态**（非 bug），sanity_check 是过时的两层不变量

**判定：hollow 态是 e11 设计产物，应被 sanity_check 接受。** 证据链：

1. **hollow 创建路径完整且每一步都有持久副本保证**：
   - Full host 层释放：`_reclaim_full_host_duplicates`（unified_tree_core.py:1447）只在 `value 非 None 且 host_value 非 None`（双层都有 = L3 冗余副本）且无 in-flight DMA、host_lock_ref=0 时回收；`_release_full_host_duplicate` docstring 明示"aux host slices stay under their own pools' LRU"——mamba host 残留是设计。
   - Full device 层释放：`evict_device_leaf_storage_backed`（unified_tree_core.py:1336，e11 7d5ac691）仅在 backup 失败 + drop 被拒 + **`is_storage_persisted(node_id)`** 时执行，只释放 device 层（`target=EvictLayer.DEVICE`），docstring："The L3 copy is the durable backup... the node stays as a device-less leaf that a later L3 restore refills"。
   - `storage_persisted` 语义（unified_tree_core.py:1965 `advance_storage_persisted`）：L3 写 ack + 父链到 root 连续 → 整链（Full + aux）可从 L3 恢复。
2. **代码库自己的 dead 定义与 hollow 不冲突**：match_prefix 遍历（:737）注释 "dead node (evicted + not backuped) — stop traversal"——hollow 节点是 evicted 但 **L3-backed**，不是 "not backuped"。sanity_check:2283 "no Full device and no Full host" 是 L3 概念出现前的两层（device/host）不变量，未随 L3 存储层更新。
3. **运行时行为安全（无 bug 证据）**：Full match validator（full_component.py:101）= `value is not None or backuped`——hollow 节点两者皆无 → `best_match_node` 停在 hollow 之前 → prefetch anchor 有效 → L3 restore 从 anchor 重新填充（含 hollow 节点自身）。K=1 12/12、K=8 94/96 成功期间 hollow 节点与正常流量共存无异常。
4. **崩溃现场唯一性**：tester e16 全 run 仅这两条 violation（`node 511 mamba host present but Full.host_value=None` + `node 511 dead: no Full device and no Full host`），PART 3/4/5（leaf 集合、LRU、duplicates、size、ongoing ops）全部一致——证明 hollow 节点与全部追踪结构自洽，只有断言过时。最后 2 请求失败是断言 SIGQUIT 的后果，不是 hollow 数据问题。

**排除"hollow 创建路径有 bug"的另一证据**：hollow 前置条件 `is_storage_persisted` 保证 L3 有完整链（e11 测试 `test_no_hollow_when_chain_not_persisted` 钉住：非 persisted 链不 hollow，绝不丢唯一副本）。

## 2. 修复（unified_tree_core.py sanity_check，PART 2，最小改动）

- :2272 新增 `persisted = node.storage_persisted`
- :2283 aux-host 断言豁免条件 `self.is_write_back and full_dev` → `self.is_write_back and (full_dev or persisted)`：write_back 下 Full host 层可被 L3 冗余回收，aux host 切片可在 Full device 存活**或 L3 链为持久副本**（hollow）时存留
- :2289 dead 断言 `not full_dev and not full_hst` → `not full_dev and not full_hst and not persisted`：节点须在 device / host / **已 ack 的 L3 链**三层至少一层保有 Full；hollow 叶只保留 L3 副本
- 行为变化面 = 恰好 `(is_write_back ∧ persisted ∧ ¬full_dev)` 一种新合法态；非 write_back、非 persisted 的一切原判定不变

## 3. 新增测试（3090-dev/test_storage_regression.py，torch 分支，RED→GREEN 已做）

`HollowStateSanityCheckTests`（3 测，真实 `UnifiedTreeCore` + 真实 RadixKey，stub components）：
- `test_hollow_persisted_leaf_passes`：hollow 合法态（mamba host 在、Full 双层无、storage_persisted=True）sanity_check 通过——**RED 复现与 e16 崩溃逐字一致**（`node X mamba host present but Full.host_value=None` + `node X dead: no Full device and no Full host`，2 violations）
- `test_genuinely_dead_leaf_still_fails`：同构但 persisted=False → 仍 AssertionError（含 "dead"）
- `test_aux_host_without_full_still_fails_outside_write_back`：is_write_back=False + 非 persisted → aux-host violation 仍触发（钉住豁免边界，防过度放宽）

## 4. 证据（验证命令与真实输出）

- 本机（sglang-venv，torch 2.13.0+cu129）：`python -m unittest test_storage_regression test_hicache_restore test_drain_reentry` → **Ran 100 tests in 0.114s OK**（45+43+12；e11 基线 42/42 无回归）
- RED 复现：修复前 hollow 测试 FAIL，violation 与 e16 现场一致（2 violations）
- `python -m py_compile` 2 个改动文件：PY_COMPILE_OK
- 远端（3090，sglang-patch env，torch 2.13.0+cu130）：**Ran 100 tests in 0.079s OK**
- **双侧 md5 一致**：unified_tree_core.py `fb931e5c…`（旧 7d5ac691）、test_storage_regression.py `3378313d…`（旧 c884b7c4）；未动文件仍 e11 值：unified_radix_cache.py `d992a972…`、scheduler.py `7305eb0b…`
- 引擎未启动：GPU 15 MiB/0%，无引擎进程（pgrep 空）

## 5. followups

1. **第六次复测建议（按序）**：先 K=1 回归（复用 0c 链）→ 通过后 K=8 完整第六次 run（md5 已核对：fb931e5c/3378313d）。预期 **96/96**（收尾 a5-t11/t12 不再 in-flight 失败）+ **优雅退场**（idle sanity_check 通过，SIGTERM 正常退出）；三项硬性验收与 wake 率应保持 e16 水平（0 stall / 0 orphan / 0 false recompute / wake 91%）
2. e16 遗留：collect_metrics l3_to_h_wait/quota 指标 missing 原因待查
3. e16 非截断 12 指标值（turns/s 0.148、p95 133.6s、recompute 752K）在第六次 run 后作最终基线

## 6. open_issues

- 无新增。hollow 节点在真实 torch 下 restore 路径行为已被 e16 run（K=1 restore 15 次、K=8 restore_ready 93）覆盖；本修复只放宽 sanity_check 判定，不触碰任何运行时路径
- 不 commit 不 push（工作树保持 e11+e12 未提交状态）
