# P0: build_backup_spec assert 根因 + 最小复现（架构分析）

```text
status: done
artifacts: phase2-backupassert-architect-e3.md
evidence: TC:2030-2050, RC:1580-1613/2097-2165, TC:1694-1761/1484-1511/2019-2027, git log -S/blame; phase2-rhfix-tester-e1.md §S2/S3/S6
summary:
  Conclusion: assert (TC:2037) 是过强不变式，被 write-back+storage gap-fill 的合法中间态
    (unbacked + value=None, host-only) 击穿；根因在 RC:2143 守卫只查 is_backuped，假设
    "未 backuped ⇒ 有 device value"，对 gap 节点不成立。
  Current Architecture: 崩溃链 RC:801->3889->2097->2120->2144->1596->TC:2037；
    value 释放路径 _demote/_evict_host_leaf/_release_device_leaf_layers/插入仅写 host_value。
  Problem / Forces: unbacked+host-only 是合法缓存态；node_exists 不区分有无 device value；
    KeyError backstop 不兜 assert；gap-fill 把 host-only 祖先误当 D->H backup 对象。
  Proposed Architecture: RC:2143-2144 追加 device value 存在守卫；该态改走 storage-write
    (build_storage_backup_spec 读 host_value 写 L3)，不进入 D->H backup。不动 assert 语义。
  Alternatives: 放宽 assert(B)/gap 过滤(C) 均破坏 D->H backup 或 L3 连续性语义，不推荐。
  Migration / Impact: 预存缺陷，非 Fix A/B 引入；修复不改变 Fix A/B 语义，消除 stress 崩溃回归。
  Open Decisions: 生产 host-only unbacked 祖先来源(demote vs insert)未 dump 确认；
    RC:2155 对 host_value 也 None 的 gap 节点需额外守卫；RC:968/1336 同守卫是否需复核。
followups:
  - tester: 在 TC:2037 崩溃点加日志 dump node_id/backuped/value is None/host_value，确认生产来源
  - coder: 按 §4 实现 RC:2143 device-value 守卫（不实现，属后续派发）
open_issues: 见 §6 四项
```

---

- status: **done**
- epoch: e3
- owner: architect
- task: 只读定位 `build_backup_spec` 的 `assert device_value is not None` 崩溃根因，设计最小复现 + 修复语义（不实现）。
- repo: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-opt`（分支 3090-24g-opt）
- 约定：所有行号为当前分支实测；两条路径文件为
  - `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py`（TreeCore，下称 **TC**）
  - `python/sglang/srt/mem_cache/unified_radix_cache.py`（UnifiedRadixCache，下称 **RC**）

---

## 结论（Conclusion）

`assert device_value is not None`（TC:2037）是**一个过强的状态机不变式断言**，在 **write-back + storage 启用的 gap-fill（补链写 L3）路径**上会被一个**合法可达的中间状态**触发：一个处于 storage gap、`backuped=False` 但 `value=None`（host-only）的节点被 gap-fill 误当作"需要 D->H backup 的未备份设备叶"去执行 `_execute_and_commit_kv_backup`。

- **触发链（已逐环验证）**：load_back 需设备空间 → `evict_for_alloc` → `_evict`（RC:779）→ write-back 下 `writing_check(write_back=True)`（RC:801/3889）→ `_flush_pending_storage_writes`（RC:2097）→ `write_backup_storage`（RC:2120）→ `collect_storage_gap`（RC:2132）→ 对未 backuped 的 gap 节点 `_execute_and_commit_kv_backup(BackupKV([nid]), write_back=False)`（RC:2144）→ `build_backup_spec`（RC:1596）→ TC:2037 assert。
- **根因**：RC:2143 的守卫只看 `is_backuped(nid)`，**假设"未 backuped ⇒ 有 device value"**。该假设对 gap-fill 不成立：gap 节点可以 `backuped=False` 且 `value=None`（host-only）——要么插入只写 host_value（TC:2023，新节点 host-only、backuped=False、value=None），要么被设备 eviction（demote/`_evict_host_leaf`/hollow/forced-miss）提前释放 device value。这些是缓存状态机的合法中间态，不是数据损坏。
- **预存 vs Fix A/B**：崩溃行与整条 gap-fill/flush 机制**先于** Fix A/B（b1-continuity 4f06324468、caeadcf492、2bdfcb5327，均在 2026-09-04 冻结基线 202a37eba4 之前）。**判定为预存 backup 路径缺陷，非 Fix A/B 引入**；Fix A/B 只是通过改变 admission/eviction 时序把工作集推进到更深容量耗尽，先触达这条此前休眠的路径。
- **修复语义（最小、结构正确）**：把 RC:2143 的 D->H backup 调用**再叠加"device value 存在"前置守卫**——未 backuped 的 gap 节点若 `value=None`（host-only），不执行 `_execute_and_commit_kv_backup`，而是直接落到 RC:2155 的 storage-write 循环，由 `build_storage_backup_spec`（RC:2174，读 `host_value`）从 host 副本写 L3。该状态合法，不应进入 D->H backup 路径。

---

## 1. 崩溃链根因（代码链，文件:行 + 行内容）

### 1.1 崩溃栈（str-fx2 实测，权威，来自 phase2-rhfix-tester-e1.md）

```
scheduler.py:4491 _get_new_batch_prefill_raw -> add_one_req
unified_radix_cache.py:4031 init_load_back -> load_back
unified_radix_cache.py:1983 _load_back_transfers -> evict_for_alloc
unified_radix_cache.py:801  _evict -> writing_check -> _flush_pending_storage_writes
unified_radix_cache.py:2144 write_backup_storage -> _execute_and_commit_kv_backup
unified_tree_core.py:2037 build_backup_spec -> assert device_value is not None
AssertionError
```

### 1.2 崩溃点（TC:2034-2050）

```python
2034  def _build_backup_spec(self, node: UnifiedTreeNode):
2036      device_value = node.component_data[BASE_COMPONENT_TYPE].value
2037      assert device_value is not None          # <-- 崩溃点
2038      if node.backuped:
2039          device_value = device_value[:0]
```
`build_backup_spec(node_id)`（TC:2030）→ `_build_backup_spec(node_by_id(node_id))`。此函数是 **D->H backup 的 spec 构建**：需要 `value`（GPU device KV）来执行 D->H 拷贝。被 `_execute_and_commit_kv_backup`（RC:1596）调用。

### 1.3 崩溃路径逐环验证

**① RC:779 `_evict` → ② RC:801 write-back 下 `writing_check(write_back=True)`**
```python
779  def _evict(self, params, available_size_targets=None):
791      self._evict_components(request_by_type, tracker, available_size_targets=...)
797      if (self.cache_controller is not None
799          and self.cache_controller.write_policy == "write_back"):
801          self.writing_check(write_back=True)
```
（`_evict` 由 `evict_for_alloc` RC:735 调，由 load_back 路径 RC:1983 的 evict_for_alloc 触发。）

**③ RC:3865 `writing_check` → RC:3889 `_flush_pending_storage_writes()`**
```python
3884  if flush_pending:
3889      self._flush_pending_storage_writes()
```

**④ RC:2097 `_flush_pending_storage_writes`**
```python
2103  while self._pending_storage_writes:
2104      node_id = self._pending_storage_writes.pop(0)
2105      if not self.tree_core.node_exists(node_id):   # 存活 guard
2106          self._skip_stale_storage_persist(node_id); continue
2108      try:
2109          self.write_backup_storage(node_id)
2110      except KeyError:   # backstop：node 在 guard 与 arena 查询间死亡
```
`_pending_storage_writes` 在 RC:1693（`_finish_write_through_ack`）填充：D->H write-through ack 后把 `publish_node_ids` 延后到 drain 之外持久化。见 1.5。

**⑤ RC:2120 `write_backup_storage` → gap-fill**
```python
2132  gap = self.tree_core.collect_storage_gap(node_id)          # 锚点→node 间未写 L3 的 gap
2136  gap = [nid for nid in gap if self.tree_core.node_exists(nid)]
2139  for nid in gap:
2140      if not self.tree_core.node_exists(nid):
2141          self._skip_stale_storage_persist(nid); continue
2143      if not self.tree_core.is_backuped(nid):                # 守卫只看 backuped
2144          self._execute_and_commit_kv_backup(BackupKV([nid]), write_back=False)  # <-- 崩溃入口
```

**⑥ RC:1580 `_execute_and_commit_kv_backup`**
```python
1595  for node_id in action.node_ids:
1596      device_value, comp_xfers = self.tree_core.build_backup_spec(node_id)   # -> assert
```

### 1.4 `collect_storage_gap` 与 gap 节点构成（TC:2079-2099）

```python
2088  gap = []
2089  node = self.node_by_id(node_id)
2090  while (node is not None and node is not self.root_node and not node.storage_persisted):
2095      if not node.storage_written:
2096          gap.append(node.id)
2097      node = node.parent
2098  gap.reverse()   # ancestors-first
```
**关键**：gap 收集只过滤 `storage_persisted` / `storage_written`，**不过滤 backuped，也不过滤 device value 是否存在**。因此 gap 可包含 `backuped=False` 且 `value=None` 的 host-only 节点。

### 1.5 并发/前置释放路径（该 gap 节点为何 backuped=False 且 value=None）

**A. 插入只写 host_value（TC:2019-2023）** —— 新节点 host-only、backuped=False、value=None：
```python
2019  new_node = self._new_node(priority=node.priority)
2023  new_node.component_data[BASE_COMPONENT_TYPE].host_value = host_value.clone()
```
（`backuped` 默认 False，device `value` 默认 None。）这类 host-only 未备份节点可成为 storage gap 的祖先。

**B. `_demote`（value→None、host-only）** —— TC:1694-1721，`_cascade_evict` 在 TC:1761 置 `value = None`：
```python
1761  if EvictLayer.DEVICE in target and base_evicted:
1761      node.component_data[BASE_COMPONENT_TYPE].value = None
```
运行于 `evict_device_leaf`（TC:1317→`_demote`），或 `_evict_components` 的 write-back D-leaf 路径（RC:978）。demote 后节点 backuped=True（host 副本在），value=None——此时 RC:2143 `is_backuped` 为 True 会跳过；但**同一 `_evict` 的 `_evict_components`（RC:791）在 flush 之前刚运行**，可能已把该 gap 祖先的 device value 释放，而该祖先从未 backuped（见 D）。

**C. `_evict_host_leaf`（TC:1655-1680，`drive_host_eviction` 内）** —— 对 host 叶 `target=EvictLayer.ALL` 释放所有 component 的 device+host（含 Full.value）。`evict_host`（RC:1356→TC:1364 `drive_host_eviction`）在 `_execute_kv_backup`（RC:1622-1633）host 不足 recovery 路径被调；也作为 RC:2145 注释所述"gap-fill 的 D->H backup 会 evict_host"。

**D. hollow / forced-miss 释放 device 层** —— `_release_device_leaf_layers`（TC:1484-1511）经 `_cascade_evict` 置 value=None；`evict_device_leaf_storage_backed`（TC:1395）、`drop_device_leaf_to_miss`（TC:1453）、`detach_miss_dropped`（TC:1414）都走此共享机制。这些节点可能 `backuped=False` 且 L3 不 durable，却留在 arena。

**要点**：RC:2144 的调用**假设 gap 中未 backuped 的节点必有 device value**。但上述任意一条路径都能产生"unbacked + value=None"的合法存活节点。崩溃正是该假设被击穿。

### 1.6 为何 node_exists guard（RC:2105）没拦住

`node_exists`（TC:526）只查 `node_id in self._node_arena`（节点是否被 `_unregister_node` 删除）。被 device-evict 但**未删除**的节点（demote/hollow/forced-miss 都保留节点、只释放层）仍在 arena → guard 放行 → 进入 2144 → assert。RC:2110 的 `KeyError` backstop 只兜 arena 查询，不兜 assert。

---

## 2. 预存 vs Fix A/B 暴露判定

**判定：预存 backup 路径缺陷，非 Fix A/B 引入；Fix A/B 仅通过时序变化先触达。**

证据：
- 崩溃行 `assert device_value is not None`（TC:2037）由 `3c533acec6 [Hicache][2/2]...` 引入；`build_backup_spec` 由 `cd145f840f Radix Cache Split` 引入。均远早于 Fix A/B。
- 整条 gap-fill/flush 机制为本地 b1 系列提交引入，均**早于** 2026-09-04 冻结基线 `202a37eba4`：
  - `4f06324468` b1-continuity（2026-08-29）：`write_backup_storage`/`collect_storage_gap`/`_execute_and_commit_kv_backup`/`_pending_storage_writes`（blame 证实 RC:2139/2143/2144 属此提交）。
  - `caeadcf492`（2026-08-30）：`node_exists` guard + `_skip_stale_storage_persist`（blame 证实 RC:2105-2110/2140-2142）。
  - `2bdfcb5327`：`_flush_pending_storage_writes` 从 ack drain 拆出。
- Fix A（`e0e83b11a1` NO_HEADROOM epoch wake）与 Fix B（`3bca0989f4` DEVICE_QUOTA timeout 上限）均为冻结基线**之后**的 HEAD 提交（git log -20 证实顺序：`202a37eba4` → ... → `e0e83b11a1` → `3bca0989f4`），不触碰 `unified_tree_core.py` / `unified_radix_cache.py` 的 gap-fill 路径。
- tester 证据（phase2-rhfix-tester-e1.md §S6）：崩溃发生在未打补丁的 `unified_tree_core.py`；触发路径经过 patched `scheduler.py:4491`；且同一配置下 baseline 存活、fixed 崩溃——**唯一已确立事实**是 fixed 因行为差异先到达纯容量耗尽 + 高压力 write-back 状态，该状态下预存 backup 路径缺陷被击穿。

**结论**：这是**独立缺陷**，与 Fix A/B 的"WAIT/recompute 慢尾"根因解耦；修复它不改变 Fix A/B 语义，只消除一个会打断 stress 验证的崩溃回归。str-fx2 的"C: FAILED"判定应重估——崩的是预存路径，不是 Fix 逻辑本身。

---

## 3. 最小复现设计（前置状态，不必 GPU）

**机制**：构造"write-back + storage 启用，storage gap 含一个 host-only（unbacked + value=None）祖先节点"，触发 `_flush_pending_storage_writes` 落到 RC:2144。

**前置**：`enable_storage=True`、`cache_controller.write_policy == "write_back"`、`enable_hicache=True`。无需 GPU——gap-fill 在 `_execute_and_commit_kv_backup` 的 spec 构建（内存操作）就崩溃，不会真发 DMA。

**步骤（单元级，直接驱动 TreeCore/RadixCache 方法）**：
1. 插入 host-only 祖先节点 A：走 insert 路径（TC:2019-2027）使 A 仅持 `host_value`（backuped=False、value=None）。或对 A 跑一次 `_demote`（A 先 backuped 再 device-evict）得到 host-only 态。
2. 在 A 下插入/激活子节点 B，使 B 走一次 D->H write-through（`_execute_and_commit_kv_backup(BackupKV([B]), write_back=False)`），经 `_finish_write_through_ack`（RC:1676-1693）把 `publish_node_ids`（含 B）extend 进 `_pending_storage_writes`。
3. 调用 `_flush_pending_storage_writes()`（RC:2097）。B 存活、未写 L3：
   - `write_backup_storage(B)` → `collect_storage_gap(B)` 得 `gap=[A, B]`（A 未 storage_written）。
   - 循环到 A：`is_backuped(A)==False` → RC:2144 `_execute_and_commit_kv_backup(BackupKV([A]))` → TC:2037 `value is None` → **AssertionError**。

**对照（证明确为 gap-fill 误判而非其他）**：同一 setup 但跳过 RC:2144（或给 A 先跑 D->H backup 使其 backuped=True）→ 不崩，A 在 RC:2155 循环经 `build_storage_backup_spec`（读 host_value）正常写 L3。此对照证明"unbacked + host-only"是合法态，应走 storage-write 而非 D->H backup。

**回归判定**：期望修复后，A 不再进入 D->H backup，L3 链连续，无 assert，无 KeyError backstop 触发。

---

## 4. 修复语义（结构正确，不实现）

### 4.1 状态是否合法
**合法**。`backuped=False`（无 D->H 副本）与 `value=None`（无 device KV）可同时成立：插入即 host-only 未备份（TC:2023）；或 device-evict 释放 value 而未建立 backuped（hollow/forced-miss/`_evict_host_leaf`）。节点在 arena 中存活即"存在"，`node_exists` 无法区分"有 device value"与"host-only"。**该状态不构成 corruption，是分级缓存（D/H/L3）的正常中间态。**

### 4.2 assert 应改什么
**不应放宽/删除 assert 作为修复**（那会在 D->H backup 语义上制造空 spec 隐患）。正确做法是**在调用方 RC:2143-2144 修正前置守卫**：D->H backup 的合法前置是"未 backuped **且 device value 存在**"。

```python
# RC:2143-2144 现在：
if not self.tree_core.is_backuped(nid):
    self._execute_and_commit_kv_backup(BackupKV([nid]), write_back=False)
# 修复语义：追加 device value 存在性守卫（需 TC 暴露一个查询，如
# get_component_device_value(nid, BASE_COMPONENT_TYPE) is not None）
```
- 未 backuped 且有 device value → 照旧 D->H backup（正确，缺失 host 副本）。
- 未 backuped 且 value=None（host-only）→ **跳过** D->H backup，让 RC:2155-2160 循环 `_write_backup_storage_node` 处理，其 `build_storage_backup_spec`（RC:2174→TC:2072）读 `host_value` 直接写 L3。
- 两者 value 均 None（真 tombstone）→ 由 RC:2140/2105 的 node_exists / 后续守卫自然跳过或 KeyError backstop 兜底。

### 4.3 状态应走哪条路径
"unbacked + host-only + host_value present" 应走 **storage-write 路径（host→L3）**，由 `build_storage_backup_spec` 完成，**而非** D->H backup。这与 b1-continuity 的"补链写 L3"意图一致：gap 填的是 L3 连续性，host 副本已存在时无需再造 D->H 副本。

### 4.4 验证映射
- 单元：§3 最小复现；修复后 rc=0、无 assert、`is_storage_written(A)` 为 True、`storage_persisted` 链连续。
- 回归：RH ON fixed 纯容量耗尽 stress（复现 str-fx2 配置，agents=8 rt=400 MAX_SIZE=200G FILE_SIZE=30G）存活不崩。
- 语义回归：write-through 路径不受影响（注释 RC:2150-2152 明示 write_through 从无 unbacked gap 节点，新增守卫不触发）。

---

## 5. 备选方案（结构权衡）

| 方案 | 做法 | 评估 |
|---|---|---|
| **A（推荐）** 调用方守卫 | RC:2143 追加 device value 存在检查 | 最小、语义精确；把合法态导向正确的 storage-write 路径；不动 D->H backup 语义。 |
| B 放宽 assert | TC:2037 允许 None 并返回空 spec | 会把 D->H backup 的非法输入静默化，`_execute_and_commit_kv_backup` 无法区分"空节点"与"device-less"，掩盖真实错误；不推荐。 |
| C gap 收集过滤 | `collect_storage_gap` 跳过 value=None 且未 backuped 的节点 | 改变了"gap=未写 L3 链"的定义，可能漏填需要持久化的 host-only 节点，破坏 L3 连续性；不推荐作为主修。 |
| D 守卫+断言内化为诊断 | 在 TC:2037 把 assert 改为带上下文日志的显式检查，明确"调用方前置不满足" | 作为 A 的补充防御（可观测），不单独作修复。 |

---

## 6. 开放问题（open issues）

1. **确认 host-only unbacked 祖先在生产的出现频率**：插入（TC:2023）与 demote 哪条在 str-fx2 实际贡献了崩溃节点，需 crash 时对 `node_id` / `backuped` / `value is None` / `host_value` 的 dump 佐证（运行时可观测项，建议 tester 在崩溃点加日志确认）。这是唯一未被 dump 证实的环节。
2. **RC:2155 循环对 value=None 且 host_value 也 None 的 gap 节点是否安全**：`build_storage_backup_spec`（RC:2174）返回 spec 前不校验 host_value 非空；`PoolTransfer(host_indices=spec.host_value)` 对 None host_value 的行为需确认（若 host_value 也 None，需另一个守卫跳过，避免写 L3 空链）。
3. **修复是否需要把同一守卫应用到其他 `_execute_and_commit_kv_backup` 调用点**：RC:968（write-back D-leaf deferred backup）与 RC:1336（apply CacheAction BackupKV）。这两处调用的是 `evict_device_leaf` 已产生的 `backup_kv`（该路径保证 D-leaf 有 device value，见 TC:1296-1316），与 gap-fill 的任意祖先不同——理论上不需要，但应复核。
4. **str-fx2 "C: FAILED" 判定回退**：本分析表明崩溃为预存缺陷；修复后应重新评估 Fix A/B 的运行时价值（Fix A 的 epoch 价值仍待观测，见 phase2-rhfix-architect-e1.md open issue 1）。

---

## 7. 证据索引（Evidence）

- 崩溃链行号：TC:2030-2050（build_backup_spec/assert）、RC:1580-1613（_execute_and_commit_kv_backup）、RC:1622-1638（_execute_kv_backup/evict_host recovery）、RC:1676-1693（_finish_write_through_ack/pending 填充）、RC:2097-2118（_flush_pending_storage_writes）、RC:2120-2165（write_backup_storage gap-fill）、TC:2079-2099（collect_storage_gap）、RC:3865-3920（writing_check/flush）。
- 释放路径：TC:1694-1761（_demote/_cascade_evict 置 value=None）、TC:1655-1680（_evict_host_leaf target=ALL）、TC:1484-1511（_release_device_leaf_layers）、TC:1395/1414/1453（storage_backed/detach_miss_dropped/drop_to_miss）、TC:2019-2027（插入仅写 host_value）。
- guard 语义：TC:526-529（node_exists）、TC:531-533（is_backuped）、RC:2105/2140（存活 guard）、RC:2110（KeyError backstop）。
- 正确路径（host→L3）：RC:2174-2229（_write_backup_storage_node/build_storage_backup_spec）、TC:2052-2077（build_storage_backup_spec 读 host_value）。
- 预存性：git log -S / blame 证实崩溃行与 gap-fill 机制先于冻结基线 `202a37eba4`；Fix A `e0e83b11a1`、Fix B `3bca0989f4` 在基线之后且不触碰这两文件。
- 崩溃复现：phase2-rhfix-tester-e1.md §S2/S3/S6（str-fx2 崩溃栈、pre-crash 吞吐匹配、属性待定）。
