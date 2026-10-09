# p2io-tester-e7o.md — e28 修复 12G M4T 终验（storage_hit 仍未恢复：mamba 组件 key 封锁包）

## 1. status

done（实验已跑完、证据已拉回、分析完成、远端已清理、GPU 已归零）。结论为 **FAIL**：e28 修复
（batch_exists_v2 placeholder 强制 TRAILING）**未能恢复 storage_hit**，但实验产生了决定性证据，
将封锁点从之前的 "allocator 注册缺陷"（e7m 结论）修正为 **mamba 组件 key 位置错位**（写侧
`node.hash_value[-1]` → `.mamba` key，读侧 TRAILING 扫描窗口内永远找不到该 key）。

## 2. artifacts

- 实验：e7o 12G M4T 终验（配置同 e7j）——driver rc=0，elapsed=453s，8 agents / 96 req / 12 turns，failed=0，downgraded=14
- 证据（本机保留）：
  - `/tmp/p2io-e7o-ev/t38c-probe.log`（2920 行：54 write_seed + 592 prefetch_enter + 396 storage_query + 16 stats_snapshot + 1270 outcome）
  - `/tmp/p2io-e7o-ev/engine-p2io-m4t-e7o.log`（23922 行）
  - `/tmp/p2io-e7m-ev/t38c-probe.log`（340 storage_query，对照用）
- 远端清理：evidence/run/samples/gauge/engine/launch/status/log、`/tmp/t38c-probe.log`、`/tmp/t38c-on`、`/data/l3/p2io-extent-e7o` 全部 find -delete；GPU 15 MiB；无 sglang/p2io-e7o 进程残留（仅 jupyter-lab）

## 3. evidence

### 3.1 部署核对（e28 已同步）

```
3090: extent_file_backend.py md5 = bc9c7770dbaef8a58431ce4bb7102f6c  (双侧一致)
-loop: batch_exists_v2 已含 placeholder 守卫：
  648-651: placeholder_keys = bool(transfer.keys) and all(k == "__placeholder__" for k in transfer.keys)
            if transfer.hit_policy == PoolHitPolicy.ALL_PAGES and not placeholder_keys: ALL_PAGES scan
            else: TRAILING scan
```
import 冒烟：sglang-patch conda env 可加载（上文 `PoolName.KV=<PoolName.KV: 'kv'>`，`extra_pool_hit_pages` 键为 PoolName 枚举）。

### 3.2 storage_hit 分布（判据 2 —— FAIL）

| 指标 | e7m（修复前） | e7o（e28 修复后） |
|---|---|---|
| pc_storage_query 总数 | 340 | 396 |
| storage_hit_count 分布 | {0: 340} | **{0: 396}** |
| kv_hit_pages 分布 | {0: 340} | **{0: 396}** |
| 命中 >0 的查询 | 0 | 0 |
| 末次写后查询命中>0 | 0 | **0/311** |
| sidecar_hits 含 'mamba' | 0 | **0（396/396）** |
| sidecar_hits 含 'kv'（raw KV present） | 95+ 条 | **253/311 after-write** |
| raw KV present 最大值 | — | **1892（< 2048 节点边界）** |

决定性发现：e7o 中 **253 条 after-write 查询的 `sidecar_hits` 非空，含 `{'kv': N}`（N 最高 1892）**。
这说明 `batch_exists_v2` 被调用（pool_transfers 非空 → MAMBA 侧车 transfer 在 `operation.pool_transfers` 里），
**raw KV 扫描找到了数百页 present（KV allocator 注册是正常的）**，但 `final_pages = min(kv_pages, mamba_boundary=0) = 0`，
被 **mamba TRAILING 扫描恒返回 0** 封顶。

### 3.3 根因证明（mamba 组件 key 位置错位）

1. **写侧 mamba key**：`mamba_component.py` BACKUP_STORAGE 分支
   `keys=[node.hash_value[-1]]` → `batch_set_v2` → `_component_key(MAMBA, key) = key + ".mamba" + config_suffix`。
   即 mamba 写键 = **写节点最后一项 KV page hash（index n_pages−1）**。
2. **读侧 mamba key**：PREFETCH 侧车 transfer `keys=["__placeholder__"]`、
   `hit_policy=TRAILING_PAGES`；e28 修复后 TRAILING 扫描
   `trailing = max(1, len(transfer.keys) or 1)` = 1 → 检查
   `keys[kv_pages−1 : kv_pages]` （命中窗口最后一页）的 `.mamba` 键。
3. **位置错位**：写节点 n_pages 分布 {3, 61, 6, 2039, 2048×36, 384×2, …}，写键在 index n_pages−1
   （如 2047）；查询 raw KV present 最高 1892（for 2048 节点查询也 < 2048），命中窗口末页
   index kv_pages−1 ≤ 1891 **永远 ≠ 写键 index 2047** → `.mamba` 键查不到 → TRAILING boundary=0
   → final_pages=0。
4. **全 or 无语义**：`unified_radix_cache.py:2921` `if pool_transfers and not all_succeeded`——
   mamba boundary=0 → prefetch 全丢弃（`pc_get_v2` 事件 0 条，sidecar `batch_get_v2` 从未执行）→ `revoked_full_miss`。

### 3.4 六门逐条

| # | 判据 | 结果 | 证据 |
|---|---|---|---|
| 1 | 无崩溃全程（ghost 四类/sanity 0） | **PASS** | rc=0；END-BANNER status=done failed=0；engine 无 sanity/violation/assert；23522 行仅 torcchcodec import 噪音 |
| 2 | storage_hit > 0 恢复 | **FAIL** | e7m 340 全 0 → e7o 396 全 0；raw KV present 数百但 mamba 封顶到 0 |
| 3 | restore_success/READY 真实链首现 | **FAIL** | restore_success=0；READY 仅 1 条 ready_pool 初始化（size=0）；restore_recompute 396 全 cause=miss，final_storage_survivability=host 396 次 |
| 4 | Z3 回落（e7j 386） | **PASS（部分）** | prefill_deny_summary 15 条，rem_total_tokens 合计 213（含锁 120）——较 386 下降约 45%，但主因 shuttle 仍是全 miss 重算，非 L3 链闭合 |
| 5 | survivability/full-prefix/16 差额细分 | **部分可测** | final_storage_survivability=host 396/396（storage 存活率 0）；probe 无 full-prefix/16 差分埋点；downgraded=14（END-BANNER） |
| 6 | reserve 不侵占 + spec eviction=0 | **PASS** | reserve/margin=8.3%/3.0%（mamba host pool 8.65GB）=0.72GB/0.26GB 符合 0.75G/0.3G 配置；extent_recycle=0、spec eviction=0；mamba host 池全程有余量（mamba_free 62→90） |
| 7 | B_ep/B_fin 恢复可测 | **不可测** | B_ep/B_fin 埋点在 samples.jsonl（已清理）；t38c probe / engine log 无此键；storage_hit=0 下 io_finished=0、restore_success=0、prefetch_revoke 396 全 miss |

### 3.5 佐证数据

- 写侧：extent_write 154 条（kv 103 批 / mamba 51 批，每批 1 页 51MB），kv 页总数 93551，首写 ts=1788388903036，末写 ts=1788388996908
- 读侧：storage_query 396，311 条在末次写之后；query_suffix_len max=27811（span 未封顶）；matched_len>0 474/592（L1/L2 命中存在但 L3 查询全 0）
- 计数守恒：attempts 437 = issued 396 + declined_too_short 34 + declined_rate_limited 4 + forfeited 0？——outcome 分发：attempt 437 / issued 396 / revoked_full_miss 396 / declined_too_short 34 / declined_rate_limited 4（issued=revoked 全 miss）；l3_demand_requests 395 = l3_demand 全部 full miss；l1l2_miss_tokens == l3_miss_tokens（6.3M）始终相等

## 4. summary

- 实验跑完，state=done rc=0，无崩溃，但 **storage_hit 仍 100% 为 0**（396/396）。
- **e28 修复未恢复 storage_hit**——但它已进入正确路径：`sidecar_hits={'kv': N}` 证明
  `batch_exists_v2` 被调用、mamba 侧车在 `pool_transfers` 中、KV raw 扫描翻出数百页 present。
  因此 **e7m 判的 "allocator 注册缺陷" 不成立**（KV 键确实注册进 allocator 且用相同 `_storage_key` 查得到）。
- 真正封锁点：**mamba 后端写/读 key 位置错位**——写侧用写节点最后一项 hash（index n_pages−1），
  读侧 TRAILING 扫描只查命中窗口最后一页（index kv_pages−1，永远 < n_pages−1），两者从不相交，
  导致 mamba `.mamba` 键 396/396 调用 0 命中 → 全 or 无丢弃 → revoked_full_miss。
- 这是设计级缺陷（不是 e28 能修的扫描策略）：需要裁决两侧 key 约定。建议选项（供 coder/orchestrator 判断）：
  1. 读侧 TRAILING 扫描改为从**链尾**取窗口（`all_hashes[-trailing:]`，即对齐写侧 `node.hash_value[-1]`），
     语义 = "该节点最后 N 页"，而非"命中窗口最后 N 页"；
  2. 写侧改为写命中窗口末页（违背 "node-last checkpoint" 语义，mamba 状态实际以节点末页为准）；
  3. KV 与 mamba 共键降级为 async write-through 探测（临时绕过）。

## 5. followups

1. **mamba key 位置错位（根因）**——`unified_cache/components/mamba_component.py` BACKUP_STORAGE
   `keys=[node.hash_value[-1]]` vs `hybrid_cache_controller.py:834` `_sync_trailing_keys`
   `all_hashes[max(0,kv_hit_pages-trailing_n):kv_hit_pages]` 与 `extent_file_backend.py:662` TRAILING 扫描
   窗口 `keys[max(0,prefix_len-trailing):prefix_len]`。三处对 "trailing 窗口" 的定义不一致，需统一为链尾对齐。
2. **B_ep/B_fin 不可测**——samples.jsonl 已清理；下次 e7p 前请协调者确定是否保留 samples 供指标回注。
3. **Z3 回落 45% 的归因**——213(含锁) vs 386 部分来自并发/scheduling 差异还是 L1L2 演进，需后续对照。
4. **e7m 结论修订**——allocator 注册缺陷 → mamba key 位置错位（e7o 证据推翻前判），ledger 应有修订记录。

## 6. open_issues

- storage_hit=0 使判据 3（L3 链闭合 / READY 链首现）与判据 7（B_ep/B_fin）无法验证——L3 三级链实际
  从未成立，仍停留在 write→L3 单向 + full miss 重算。
- mamba 51MB/页 写 51 批（约 2.6GB）占用 extent 而永不可读，为纯写放大；若按判据 6 的 reserve 守护
  设计，这部分是近期容量压力的隐患候选（MAMBA 写不回读）。
- probe 未覆盖 mamba 写键的实际 64-hex 内容（`pc_write_seed` 只记 KV page0/page1）；若要字节级钉死
  错位，需在 mamba BACKUP_STORAGE / TRAILING 扫描处补发 key 日志（下次实验）。