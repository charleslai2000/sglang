# phase2-hicache-design-coder-e15-01 — Z3 drop-to-miss safety valve + Y anchor durable 清除（专家批准收紧版）

## 1. status

**done** — Z3 + Y 已实现（最小改动：2 生产文件 + 1 测试文件）；9 新测 RED→GREEN（RED 10 失败项，其中 2 个是既有测试的契约翻转）；本机 torch-free 118 执行全绿 + torch 侧 124/124；远端 3090 124/124 + py_compile OK；双侧 md5 3/3 一致；引擎未启动（远端 0 引擎进程、GPU 15 MiB）；未 commit 未 push。

## 2. artifacts

- `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py`
  - 新增 `drop_device_leaf_to_miss(node_id)`（:1372-1393）：Z3 树层实现——释放 device 层、保留节点与 host-only 子树、不留任何 hollow/restore 期望；`assert _is_device_leaf`（= lock_ref==0 三条件①）+ `assert write_through_pending_id is None`（三条件② D→H）
  - 新增 `clear_storage_durable(node_id)`（:2029-2039）：Y 实现——精确清除单节点 `storage_persicted`/`storage_restored`，不扩散 subtree；写 ack 经既有 `advance_storage_persisted` 重置
  - 抽出 `_release_device_leaf_layers(node, result)`（:1395-1424）：hollow（evict_device_leaf_storage_backed）与 drop-to-miss 共享的机械核心（8 行，避免复制粘贴；既有 hollow 方法行为零变化）
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - 新增 `_drop_device_leaf_to_miss(node_id, tracker)`（:772-794）：撞墙 else 分支的新兜底；日志 `[P2A] ts_ms=%d evt=forced_drop_to_miss node=%d freed=%d`（与 hollow_evict 同格式，Test A 计数点）
  - else 分支（:866-872）：warning 放弃 → `_drop_device_leaf_to_miss`
  - `revoke_pending_prefetch`（:2675-2682）：`storage_hit_count==0` 时 `tree_core.clear_storage_durable(last_host_node_id)`（Y）
- `3090-dev/test_storage_regression.py`
  - `_HollowWalkTree` 增 `forced_drop`/`drop_tracker` + `drop_device_leaf_to_miss` stub；`_FakeTreeCore` 增 `clear_storage_durable`（记录 + 从 durable/persisted 集合移除）
  - stubenv：`EvictDeviceLeafResult` 从 `object` 改为工作类 `_EvictResult`（device_frees/host_frees/tracker/字段默认值，e15 真实树 eviction 钉需要）；`EvictLayer` fake 从 plain Enum 改 `IntFlag{DEVICE:1,HOST:2,ALL:3}`（真实树 `EvictLayer.DEVICE in target` 位运算成员测试需要）；`KVCacheEventRecorder` 补 record_remove/record_store no-op；`StorageMedium` fake 从 object 改 Enum{GPU,CPU}
  - `_SplitComponent` 补 eviction 面（evict_component/eviction_priority/node_has_component_data，镜像 FullComponent 的 len 语义）
  - 9 新测 + 2 契约翻转（见 §4）

## 3. evidence（验证命令与真实输出）

- RED（实现前，测试已就位）：`python3 -m unittest test_storage_regression` → `Ran 67 tests ... FAILED (failures=4, errors=6, skipped=6)`——4×AttributeError（drop_device_leaf_to_miss / clear_storage_durable 缺失）+ 4×`[] != [42]`（forced_drop / durable_cleared 未触发）+ 2 契约翻转测试失败
- GREEN 本机 torch-free（逐文件独立进程，stubenv 互斥属既有设计）：
  - `python3 -m unittest test_storage_regression` → `Ran 67 tests OK (skipped=6)`（执行 61）
  - `python3 -m unittest test_drain_reentry` → `Ran 14 tests OK`
  - `python3 -m unittest test_hicache_restore` → `Ran 43 tests OK`
  - 合计执行 118，全绿（基线 109 + 9 新）
- GREEN 本机 torch（/home/charles/sglang-venv，torch 2.13.0+cu129）：`python -m unittest test_storage_regression test_drain_reentry test_hicache_restore` → `Ran 124 tests in 0.061s OK`（115 基线 + 9 新）
- py_compile：`python3 -m py_compile unified_tree_core.py unified_radix_cache.py test_storage_regression.py` → `PY_COMPILE_OK`
- 日志实测：`INFO:stubenv_unified_radix_cache:[P2A] ts_ms=1788140418996 evt=forced_drop_to_miss node=42 freed=2048`
- 远端 3090（root@175.155.64.171:24052，`/root/sglang-b1-continuity/`，sglang-patch env）：`REMOTE_PY_COMPILE_OK` + `Ran 124 tests in 0.079s OK`
- 双侧 md5 3/3：unified_tree_core.py `8e15bd81…`、unified_radix_cache.py `9e36323a…`、test_storage_regression.py `3bde33dc…`（旧值 6cbd9452/08a1f1ea/85e19321）
- 引擎未启动：远端 `ps` 0 引擎进程（仅 fail2ban 系统守护）、nvidia-smi memory.used = 15 MiB（部署全程未触碰引擎）

## 4. 测试（RED→GREEN + 契约翻转说明）

新增 9 测（全部 torch-free；GREEN 状态）：
| 测试 | 钉住语义 |
|---|---|
| test_drop_to_miss_when_chain_not_persisted（**契约翻转**，原 test_no_hollow_when_chain_not_persisted） | 无 L3 副本链双败（backup fail + drop 拒）→ drop-to-miss 释放 2048（forced_drop==[42]、hollowed==[]、tracker==2048） |
| test_drop_to_miss_for_pure_recompute_chain（**契约翻转**，原 test_no_hollow_for_pure_recompute_chain） | 纯 recompute 链（无任何 L3 副本）双败 → 仍不 hollow，但 drop-to-miss 兜底推进 walker |
| test_drop_to_miss_releases_device_and_leaf_misses（真实树） | 释放后节点 evicted、无 host 副本、is_l3_durable False、不在 evictable 集、节点保留——后续访问走 miss/recompute |
| test_drop_to_miss_keeps_host_subtree（真实树） | host-only 后代原样保留（崩溃现场形态：在途 L3 写读 host 槽） |
| test_locked_device_leaf_refuses_drop（真实树） | lock_ref>0 → 不在 evictable 集 + helper AssertionError（三条件①安全钉） |
| test_inflight_d2h_write_refuses_drop（真实树） | write_through_pending_id 非 None → AssertionError（三条件②安全钉） |
| test_full_miss_revoke_clears_anchor_durable（fake 树） | storage_hit==0 revoke → anchor durable 清除（persisted+restored 双源） |
| test_partial_hit_revoke_keeps_anchor_durable（fake 树） | hit>0 → 不清（anchor 前缀仍可能完好） |
| test_terminated_revoke_still_clears_on_zero_hit（fake 树） | 契约按查询结果（storage_hit==0）而非 revoke 分类：terminated+hit0 同样清除 |
| test_write_ack_resets_cleared_durable（真实树） | 清除后 advance_storage_persisted → is_l3_durable 恢复 True（自愈） |
| test_clear_durable_is_anchor_precise（真实树） | 清父不清子：子节点标志保留（不扩散 subtree，全局一致性留 Test B） |

**契约翻转说明（architect e11 提示，已确认）**：`test_no_hollow_for_pure_recompute_chain`（e14 安全钉："无 L3 副本 → 不 hollow，设备层是唯一副本"）与 `test_no_hollow_when_chain_not_persisted`（e11 同语义）在 Z3 下语义更新为："仍不 hollow（无 L3 副本可 hollow 入），但双败后 drop-to-miss 兜底——walk 必推进"。这是有意变更：设备层从"唯一副本不可动"变为"可牺牲的缓存（未来 recompute）"；liveness 可牺牲命中率，但不伪造持久性。既有 hollow 路径（is_l3_durable 分支先行）零变化，两个 durable 场景测试补了 `forced_drop==[]` 断言防回归。

## 5. summary

- **Z3 实现形态**：撞墙 else 分支（unified_radix_cache.py:866-872）→ 新 cache helper `_drop_device_leaf_to_miss`（:772-794）→ 新树层方法 `drop_device_leaf_to_miss`（unified_tree_core.py:1372-1393）。机械核心与 hollow 共用 `_release_device_leaf_layers`（:1395-1424），语义独立（docstring 明示"无 L3 副本背书，缓存持久性被牺牲而非伪造"）。
- **三条件落实**：① lock_ref==0——`assert self._is_device_leaf(node)`（_is_device_leaf 含 `any(cd.lock_ref>0)` 拒绝；walker 的 evictable_device_leaves 成员资格同源，unified_tree_core.py:1799-1815）；② 无在途 DMA——D→H：`assert node.write_through_pending_id is None`（:1390；双败路径上 drop_subtree_no_host 已先断言 `not backuped and write_through_pending_id is None`，:1318）；H→D：lock_ref==0 结构保证（load_back 在 DMA 全程持链锁，unified_radix_cache.py:1547→1618→1632，无解锁-无逐出窗口）；③ 释放后非有效 hit——cascade 将 `Full.value` tombstone 为 None（:1635/1638）、节点自身无 host_value（unbacked）、is_l3_durable 在分支判定处已为 False 且 drop 路径不设任何标志。
- **分流判定**：`elif self.tree_core.is_l3_durable(node_id)`（写 ack 或 restore 来源）→ 既有 `_evict_device_leaf_storage_backed` hollow（L3 副本是持久备份，可恢复期望合法）；else → drop-to-miss（无任何副本，普通 miss/recompute）。hollow 与 drop-to-miss 树形态相同（device-less 节点 + host 子树），差异只在 durable 标志与日志事件名。
- **Y 实现**：`revoke_pending_prefetch` 在 `operation.storage_hit_count == 0` 时（terminated/insufficient/alloc_failed 分类之前、无条件按查询结果）调用 `tree_core.clear_storage_durable(last_host_node_id)`（unified_radix_cache.py:2675-2682；树层 :2029-2039 清 storage_persisted + storage_restored 恰一节点）。写 ack（advance_storage_persisted）路径未动，自然重置。
- 最小改动：未触碰锁生命周期 / walker 候选集 / L3 写 / ack / prefetch 生命周期；未 commit 未 push。

## 6. followups

1. **tester 回归**（按 architect e11 验证设计）：K=16 重测（fresh ns，必过线 = 越过旧崩溃点 470s + OOM=0 + 签名 0 + `forced_drop_to_miss` 计数落盘）；K=32 重测（fresh ns，越 989s）；K=1 回归（无压力时新兜底不触发）；"stays device-resident" warning 0 次判据自然满足（该 warning 已删除）。
2. **devops 附带项**（architect e11 §验证设计 6）：launch-l3-3090.sh native 分支 export 四个 `SGLANG_HICACHE_FILE_BACKEND_*` env（r1-invalid ENOSPC 缺陷）。
3. 集成/性能要求（Division of labor）：集成覆盖 = K=1/16/32 三级 + 双侧 md5；性能观测 = hollow_evict / forced_drop_to_miss 事件计数分离、restore→recompute 转化率不升、E8 型 revoked:miss 风暴次数下降（Y 的直接效果面）。

## 7. open_issues

- **远端残留文件（本次部署失误，需授权清理）**：首次 scp 把 unified_radix_cache.py 误拷到 `/root/sglang-b1-continuity/python/sglang/srt/mem_cache/unified_cache/unified_radix_cache.py`（错误路径，该位置本无此文件；已把正确副本放到 `mem_cache/` 正确路径并 md5 验证）。残留文件惰性无害（无任何 import 解析该路径），但按删除纪律未自行 rm——请 orchestrator/用户授权删除，或 tester 顺手清理。
- `_release_device_leaf_layers` 抽出后 hollow 行为零变化（同 8 行机械序列），但 e14 的 hollow 方法体被重构——如需在 git diff 里单独看 hollow 语义不变，对照 unified_tree_core.py:1347-1371。
- Y 对"terminated 且查询未完成"（storage_hit==0 为初始值）的清除是按专家契约（storage_hit==0 无条件）执行的；风险面 = 仅缓存损失（hollow/gate 拒绝陈旧链），无正确性问题（写 ack 重置），已钉进 test_terminated_revoke_still_clears_on_zero_hit。
- 既有 open_issues 不变：storage_existence_cache 填充（长期）、host 池精确占用核算探针（长期）、split 于 L3 写 in-flight 窗口的 prefix promoted（已容忍）。
