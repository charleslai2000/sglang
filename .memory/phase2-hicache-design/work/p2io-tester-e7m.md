# p2io-tester-e7m.md — 64-hex live 对拍（e22 Task 3 修复分支裁决）

- task: e7m / e22 64-hex full-hash live comparison
- tester epoch 报告；日期 2026-09-02
- 3090: `root@175.155.64.171:24052`；部署 `/root/sglang-b1-continuity`（UnifiedRadixCache live 路径，e22 instrumentation）

## 1. status

**done** — 已完成 64-hex live 对拍（M4T 12G/0.75G/0.3G，同 e7l，短 run）、逐 matched span 全 hash 字节对比、分歧字节位定位、裁决与清理。

**裁决（e22 Task 3 分支）：64-hex 全等仍 miss → allocator index 注册路径缺陷。**

- 5 个 matched chain 的 **write 完整 64-hex（page0_hash + page1_hash）与 read 完整 64-hex（query keys[0], keys[1]）逐字节全等，分歧字节位 = 无（0 个字节分歧）**。
- gate 侧 `last_hash`（full 64-hex）与写侧 `write_seed`（full 64-hex）对 5 个 matched chain **全部一致**（seed_consistent=5/5，inconsistent=0）。
- 写 93389 kv 页全部落盘（`evt=extent_write` 157 批次，keys 累计 93389），零 refuse、零 extent_recycle、零写失败。
- 其中 4 个 matched chain（node29/55/57/65）写于查询前 0.5-3.2s，仍 **全部 miss（storage_hit_count=0）**。
- 260/340（76%）的查询落在 5 个字节全等的 write chain 上，**全部 0 hit**。

## 2. artifacts

- 本地证据目录：`/tmp/p2io-e7m-ev/`
  - `t38c-probe.log`（1085735 B，2524 行：pc_write_seed 56 / pc_prefetch_enter 1020 / pc_storage_query 340 / pc_outcome ~1100 / pc_stats_snapshot ~8）
  - `engine-p2io-m4t-e7m.log`（3163848 B）
- 远端已清理：evidence/run 日志/engine log/sampler/t38c gate+probe log/lock/extent 存储（find -delete 全清）；GPU 归零 15 MiB；进程树干净。
- 运行配置同 e7j/e7l：HICACHE_SIZE=12G + writeback-reserve 0.75G + safety-margin 0.3G + ready-horizon + extent + write_back + T15 off + 8 agents/96 req/24 turns/K=8；`touch /tmp/t38c-on` 全程开启。

## 3. evidence

### 3.1 e22 instrumentation 确认（4 文件已同步）

```
unified_radix_cache.py:2205-2211  pc_write_seed 记录 write_seed / page0_hash / page1_hash（全 64-hex）+ n_pages
scheduler.py:2973-2982           gate 记录 anchor.last_hash（全 64-hex）
hybrid_cache_controller.py:625    pc_storage_query 记录 keys=[k for k in hash_value[:8]]（全 64-hex，未截断）
```

### 3.2 事件计数

```
$ wc -l t38c-probe.log        # 2524
$ grep -c pc_write_seed       # 56
$ grep -c pc_storage_query    # 340
$ grep -c "phase":"gate"     # 514
```

### 3.3 64-hex 完整对比表（逐 matched span）

写侧 `pc_write_seed`（node_id → write_seed / page0_hash / page1_hash）与读侧 `pc_storage_query` keys[0]/keys[1]、gate `last_hash` 全 64-hex 逐字节对比：

| 写节点 | write_seed (64hex 前16) | gate last_hash (64hex 前16) | seed 一致 | page0_hash == keys[0] | page1_hash == keys[1] | 分歧字节位 | n_pages | 匹配查询数 |
|---|---|---|---|---|---|---|---|---|
| node19 | (root, '') | (root, '') | ✅ | ✅ 全等 | ✅ 全等 | 无 | 3 | 108 |
| node29 | 0b4304e2... | 0b4304e2... | ✅ | ✅ 全等 | ✅ 全等 | 无 | 2048 | 45 |
| node55 | 47f6ac45... | 47f6ac45... | ✅ | ✅ 全等 | ✅ 全等 | 无 | 1889 | 18 |
| node57 | cccc87fd... | cccc87fd... | ✅ | ✅ 全等 | ✅ 全等 | 无 | 1458 | 45 |
| node65 | 3689cb01... | 3689cb01... | ✅ | ✅ 全等 | ✅ 全等 | 无 | 2048 | 44 |

**分歧字节位：全部 NONE（0 个字节分歧）。** 写链 page0/page1 与读链 keys[0]/keys[1] 全 64-hex 相等。

### 3.4 决定性 temporal 证据

```
node29: write_ts=1788328879.800  first_query=1788328880.994  delta=+1.194s  hits={0:45}
node55: write_ts=1788328882.047  first_query=1788328882.600  delta=+0.553s  hits={0:18}
node57: write_ts=1788328881.027  first_query=1788328884.188  delta=+3.161s  hits={0:45}
node65: write_ts=1788328896.097  first_query=1788328897.154  delta=+1.057s  hits={0:44}
```
（node19 是特例：first_query=8863.077 早于本次 write_ts=8879.663，因该链内容是既有内容、query 命中前一轮的同 hash 数据——但它同样 0 hit。）

### 3.5 全局 hit 结果

```
$ total storage queries: 340
$ storage_hit>0: 0
$ kv_hit_pages>0: 0
$ 匹配字节全等 write chain 的查询: 260/340 (76%)，全部 0 hit
```

### 3.6 写侧落盘完整性（排除 write-drop）

```
$ ExtentFileBackend: file=/data/l3/p2io-extent-e7m/hicache.data_... extent=67108864 B slots=1024
$ kv keys 累计写入 = 93389（evt=extent_write 157 批次）
$ grep -c evt=extent_recycle  # 0（allocator 从未 drop slot）
$ 写失败/refuse：无
$ node29 写窗口（8879.8-8881.5s）27×1024 + 其他 = 27648 kv 页落盘，早于首查 8880.994s
```

### 3.7 allocator index 注册路径（batch_exists 查了什么 vs 写侧注册了什么）

代码路径逐层核对（同一 allocator 实例、同一 key transform、同一 key 字节）：

```
写侧:
  _page_backup(hybrid) # hybrid_cache_controller.py:724 → 对 KV 调 super()._page_backup
  → base _page_backup(cache_controller.py:1385) → page_set_func
  → _page_set_zero_copy(:1381) → storage_backend.batch_set_v1(hash_values, host_indices, extra_info)
  → batch_set_v1(extent_file_backend.py:487) → storage_keys=[_storage_key(k) for k in keys] (:508)
  → _allocator.commit(storage_keys, refs, passed) (:536)  <-- 注册到 _index

读侧:
  _storage_hit_query(hybrid_cache_controller.py:585) → get_hash_str(tokens, last_hash) (:587)
  → storage_backend.batch_exists(hash_value, extra_info) (:615)   [pool_transfers 为空时]
  → batch_exists(extent_file_backend.py:392) → _allocator.lookup(self._storage_key(key)) (:397)
  或 batch_exists_v2(:618) → present(key)=_allocator.lookup(self._storage_key(key)) (:630)

_storage_key(key) = key + config_suffix       # :283，双侧同一函数
_component_key(PoolName.KV, key) = _storage_key(key)   # PoolName.KV="kv" :66/:287
hicache_storage_pass_prefix_keys=False        # 写读两侧 prefix_keys 均为 None
```

**结论：写注册与读查询使用完全相同的 key 字节与完全相同的 `_storage_key` transform，且写（batch_set_v1 → `_allocator.commit`）与读（batch_exists → `_allocator.lookup`）作用于同一 allocator `_index`。但实测 64-hex 全等的 key 在 lookup 时返回 None → 写注册路径与读查询路径之间存在一个未在代码阅读层面暴露的分歧（allocator 状态/另实例/注册时序/线程可见性）。**

### 3.8 batch_exists_v2 候选差异（已排除）

```
live 读路径 pool_transfers 为空时走 batch_exists（:615），不经过 batch_exists_v2 的 pool_transfers 分支。
batch_exists_v2 的 KV present() 与 batch_exists 使用同一 _storage_key transform。
=> v1/v2 读路径对 KV 的 key 变换一致，排除 v2 特有 bug。
```

### 3.9 顺带确认：query keys 数组全量内容 vs 写侧

```
16 个 distinct 8-key 数组。5 个的 keys[0]/keys[1] 与某写节点 page0/page1 字节全等（matched，260 查询）。
其余 11 个数组 keys[0]/keys[1] 不在 56 个观测写节点的 page0/page1 中——
但写节点只记录前 2 页，这些数组可能对应写节点第 3+ 页或从未写入的链；
不构成对本裁决的干扰（matched 案例已独立坐实缺陷）。
```

## 4. summary

e22 64-hex live 对拍完成：**写读全 hash 逐字节全等（0 分歧）、seed 全等、写先于查、零 eviction、93k 页全部落盘——但 340 次查询全部 0 hit。** 判定为 e22 Task 3 的 **allocator index 注册路径缺陷**分支。

关键证据链：
1. 5 个 matched chain 的 write page0/page1 64-hex 与 read keys[0]/keys[1] 64-hex **逐字节全等**（分歧字节位无）。
2. gate last_hash 与 write seed 64-hex 全等（5/5）。
3. 写侧 `_allocator.commit(_storage_key(hash))` 与读侧 `_allocator.lookup(_storage_key(hash))` 使用 key 变换与字节完全相同（代码逐层核对）。
4. 写后 0.5-3.2s 查询仍 miss（4/5 matched chain），排除时序/GC。
5. 落盘完整（93389 页，零失败零 recycle），排除 write-drop。

因此写到文件 + 写到 allocator `_index` 的路径与读 lookup 的路径存在不一致——**"写进文件/RAM index 未注册或注册错"** 被坐实。可能的微观根因（需 coder/进程内状态进一步定位，本 tester 不修改产品代码）：
- MHA/MLA 的 `hash_value` 在 `_page_backup` 拆分批次时发生了 key 改写（如 `page_aligned`/`RadixKey` 重排）导致注册 key 与 spec.hash_value 不同；
- 或 `_v1_buffer_meta` 走零拷贝时对 host_indices 做了某种偏移使 commit 的 storage_keys 与传入 keys 不一致；
- 或 allocator 实例在 backup 线程与 prefetch 线程间存在复制/替换。

**次级观察（与裁决独立，需上报）**：shutdown 时 sanity check FAILED（4 violations across 81 nodes）——与 e7l 相同的现象（上轮 84 nodes/4 violations），host 层一致性隐患，非本裁决点。

## 5. followups

1. **进程内 allocator 状态探针（下一任务建议）**：在 engine 内对 node29 的 64-hex key 直接 `batch_set_v1` 后立即 `batch_exists`，同一线程同一实例——若立即 miss 则坐实"注册 key ≠ 查询 key 的字节/变换分叉"；若 hit 则坐实"跨实例/线程可见性"。位置：`extent_file_backend.py:487` batch_set_v1 / `:392` batch_exists。
2. **核对 `build_storage_backup_spec` 产出的 `spec.hash_value` 与 `_page_backup` 实际提交的 keys 是否一致**：在 `batch_set_v1` 的 `_log_extent_write`（:538）打印 commit 的 storage_keys 前 16 字节，与 spec.hash_value 对拍。位置：`unified_tree_core.py:2037 build_storage_backup_spec`。
3. **核对 `_v1_buffer_meta` 的 blocks_per_page 拆分**：`batch_set_v1` 用 `page_lens` 计算 plan/commit，若 `_v1_buffer_meta` 返回的 meta 与 `keys` 长度/块数不一致会静默拒绝但已确认无 refuse——核对 block 数正确性。位置：`extent_file_backend.py:504-511`。
4. **shutdown sanity check FAILED（81 nodes / 4 violations）**：独立于本裁决，live 路径一致性隐患，建议 coder 查。位置：`unified_radix_cache.py:4349` sanity_check。

## 6. open_issues

- 未覆盖：进程内 allocator 状态直接验证（区分"注册 key 分叉" vs "跨线程可见性"需进程内探针，属下一任务）。
- 11/16 个 query 数组的完整写侧覆盖未全量验证（写节点仅记录前 2 页）；matched 5 chain 已独立坐实裁决，不影响结论。
- 远端已全部清理（证据仅存本机 `/tmp/p2io-e7m-ev/`）。