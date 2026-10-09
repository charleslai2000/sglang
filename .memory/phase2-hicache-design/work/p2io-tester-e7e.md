# p2io-tester-e7e — e15 writeback-reserve 重跑验证（M4T）

## status
blocked — **引擎 41s 崩溃（AssertionError: node 66 not host-only），e15 引入的 eviction 回归**。硬门全部无法判定（运行未完成）。已定位精确根因 + 候选修复建议，交 coder。

## artifacts
- 远端运行：
  - `/root/p2io-m4t-e7e-run.sh`（new config: HICACHE_SIZE=8, reserve=1.5G, margin=0.3G）
  - `/root/launch-l3-3090.sh`（已注入两个新 flag；`.bak-e15run` 备份）
  - `/root/engine-p2io-m4t-e7e.log`（崩溃日志，1124 行）
  - `/root/p2io-m4t-e7e-{status,run}.log`、`evidence-p2io-extent-m4t-e7e/`（90/96 失败，elapsed=41s）
- 本地修复现场（未改，供 coder）：`python/sglang/srt/mem_cache/unified_radix_cache.py:891-913`（`_drop_device_leaf_to_miss`, e15 新增）、`.../unified_cache/unified_tree_core.py:1314-1357`（`drop_subtree_no_host` assert 1340）
- GPU 已归零（15 MiB），无孤儿进程，dmesg OOM=0

## evidence

### 配置生效确认（server_args 快照）
```
hicache_size: 8, hicache_writeback_reserve_gb: 1.5, ready_horizon_safety_margin_gb: 0.3,
enable_ready_horizon: True, hicache_storage_backend: extent, write_policy: write_back
```
新参数与 e15 配置正确加载，无参数解析错误。

### 崩溃时序（engine log 1067→1120）
1. `17:09:47 forced_drop_to_miss node=66 freed=2048 l3_durable_frontier=0 removal_reason=no_durable_backup`（e15 新增 Z3 路径）
2. 紧接 `Prefill batch ... #queue-req:4`（新一轮 prefill 触发 evict）
3. `Scheduler hit an exception` → `unified_tree_core.py:1340 assert desc.evicted and desc.backuped, "node 66 not host-only"`
   （调用栈：`_evict_components` → `_drop_subtree_no_host(node_id=ancestor)` → `drop_subtree_no_host` → assert 于一 descendant 66）
4. `SIGQUIT` → 全进程树终止（run script 内 kill，41s）

### 根因（确证）
**e15 新增的 `_drop_device_leaf_to_miss`（forced_drop）与既有 `drop_subtree_no_host` 的 descendant 不变量互相冲突：**

- `_drop_device_leaf_to_miss`（unified_radix_cache.py:891-913 → tree_core:1378-1399 → `_release_device_leaf_layers`）：释放 node 的 **device 层**、**保留 node 及其子树**（`_evict_component_and_detach_lru(target=DEVICE)` + `_cascade_evict(DEVICE)`），并把 node 从 `evictable_device_leaves` 移除、刷新父的集。**它不把 node `backuped` 设 True，也不 delete node**——node 留在树里成为 device-less、not-host-backuped 的叶子。
- `drop_subtree_no_host`（tree_core:1314-1357）：对另一（祖先）D-leaf 做 D→H backup 失败后整子树 drop。它遍历 descendants，**assert 每个 descendant 都是 host-only（`desc.evicted and desc.backuped`）**（行 1340）。

**崩溃路径**：同一 `_evict_components` 的 walk（或一个 walk 内先后）里，
(a) 某 descendant（node 66）先被 `_drop_device_leaf_to_miss` 处理 → device 释放、`backuped=False`，留在树中；
(b) 之后其 ancestor 的 `drop_subtree_no_host` 遍历到这个 descendant → `desc.backuped==False` → assert 崩。

e7b（e14，无该路径）59 次 Z3 drop 全部走 `drop_subtree_no_host`，assert 从不触发（descendant 都是真 host-only），583s 无崩溃。e15 引入 forced_drop 让 eviction pass 能产生 not-host-only 的存活 descendant，与既有 assert 不可相容。

### 规避/修复候选（供 coder，未实施）
正解需 tree_core 维护者定，候选：
1. `_drop_device_leaf_to_miss` 释放 device 后，把 node 标记为一种显式的 device-less/miss 态（或复用 `storage_restored=False` 之类），使 `drop_subtree_no_host` 的 descendant 遍历能正确跳过它（而非 assert 失败）。
2. `drop_subtree_no_host` 的 descendant 循环改为容忍 not-host-only 的 descendant（跳过/单独处理），但需论证缓存正确性（丢失 host-only 的持久假设）。
3. 若 forced_drop 后的 node 不应再作为任何 subsequent drop 的 descendant，考虑将其从祖先子树摘除（但会改变查询可见性，需谨慎）。

## summary
**e7e 无法判定任何硬门：e15 代码在 host-pressure 下 41s 崩溃。** 这是 e15 的确定回归（e7b/e14 同负载 583s 无崩溃；e7e/e15 崩）。正面信号：reserve 配置生效，Z3 从 59 降到崩溃前的 21（-64%），说明 writeback-reserve 方向有效——但降幅不足且间接引发了 forced_drop 与 drop_subtree 的 invariants 冲突。

诚实标注：仅 90s 崩溃前的观测，无法给出全链 survivability / full-prefix / ready_pool / 16-diff 细分等硬门数字。测试层面：现有单测（test_unified_radix_cache_unittest.py:7425）只覆盖 `drop_subtree_no_host` 单点 mock drain，**无 forced_drop + ancestor drop_subtree 交错的集成覆盖**——这是 coder 修复时应补的 RED 复现。

## followups
1. **主修复（预编，coder）**：`_drop_device_leaf_to_miss` 与 `drop_subtree_no_host` 的 descendant 不变量冲突。建议候选 1/2/3 之一，需 tree_core 维护者拍板。修复后补交错单测（forced_drop 一个 descendant 后对其 ancestor drop_subtree_no_host 不再崩溃）——RED→GREEN 由 coder 或我按 TDD 跑（引擎核心代码在 coder 边界，但复现测试可先由我写）。
2. **修复后重跑 e7e**：同一 M4T 配置（8G/reserve 1.5G/margin 0.3G），完整 583s。若 reserve 依旧不足（Z3 未到 0），考虑上调 reserve 或 margin（H_min 估算：H_working~3.7G + 2×1.424G + 1.5G + 0.3G ≈ 8.35G，8G 略压，可试 9G）。
3. Z3 从 59→21（-64%）确认 reserve 有效，但目标个位数/0 未达——修复 crash 后此门才能完整评估。
4. 16-diff NEVER_BACKED 细分、survivability>95%、full-prefix>30%、READY_HOST≥2 均待修复重跑后才能判定。

## open_issues
- e15 的 forced_drop 路径在当前 host-pressure 表型（reserve 后仍 21×Z3）下必然周期性触发——**若不做修复，任何写 resume 下都会概率性崩**，非偶发。
- crash 后 evidence 目录 90 帧 failed 请求的挂账——不是有效测量，不得用于任何 gate 判定。
- 我提交时把 launch 补丁与原 run 脚本留在远端及本地 `/tmp/`（本会话产物，非源码改动）；源码树未动。
