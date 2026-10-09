# p2io-coder-e28 — 进程内 live 路径探针：mamba TRAILING/ALL_PAGES 边界钳制的定位与修复

## status
done

## artifacts
- `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py` — `batch_exists_v2`（648-651，唯一定位点）：placeholder-key 守卫。
  - 改动：ALL_PAGES 分支加 `not placeholder_keys` 条件。当 transfer.keys 全为 `"__placeholder__"`（mamba_component/swa_component PREFETCH 构建时真实 keys 未知，只占位）时，即使 hit_policy 被重建丢失而回落到 `PoolTransfer` 默认 ALL_PAGES（hicache_storage.py:112），也强制走 TRAILING 扫描。
  - 理由：mamba/SWA 池只写 node-last checkpoint（mamba N=1，SWA N>1）；TRAILING 扫描按节点边界命中。ALL_PAGES 扫描从页 0 开始逐页查 `_component_key(MAMBA, keys[i])`，mamba 只存末页 → 第一个 KV-only 页即失败 → boundary=0 → kv_hit=0（正是 live 签名）。
- `test/registered/unit/mem_cache/test_extent_file_backend_unit.py` — 2 个新测试（`TestExtentV2`，706/749）：
  - `test_v2_placeholder_keys_never_interpreted_as_all_pages`（RED→GREEN 主体）：live 形状（两节点 3+6 页、mamba checkpoint 在 chain[2]/chain[8]），KV batch_set_v2 全 9 页 + mamba checkpoint 写入，查询用 placeholder+ALL_PAGES → 断言 kv_hit_pages>0 且 KV/MAMBA 都=9。
  - `test_v2_placeholder_keys_all_pages_explicit_still_all_pages`（负向守卫）：真实 key 的 ALL_PAGES 保持严格逐页边界（boundary=0，mamba 不进 extra）——placeholder 特判不吞有意的 ALL_PAGES。
- 探针（本 epoch 新增/复用，均在 `3090-dev/` 或 /tmp）：
  - `3090-dev/p2io_e28_hybrid_probe.py`（复用）：20910 页全链 + 13 个 node-last mamba key，`batch_exists_v2` TRAILING(placeholder) → kv_hit=20541，extra={'kv':20541,'mamba':20541}。
  - `/tmp/p2io_e28_trailing_check2.py`（复用）：HEAD9 TRAILING(placeholder) → kv_hit=9/extra={'kv':9,'mamba':9}；HEAD9 ALL_PAGES → kv_hit=0/extra={'kv':9}（live 签名）。修复后 ALL_PAGES(placeholder) → kv_hit=9/extra={'kv':9,'mamba':9}。
  - `/tmp/p2io_e28_trailing_fullchain.py`（复用）：TRAILING(full chain, trailing=N) → kv_hit=0（live 签名）——两条非 TRAILING(placeholder) 路径都产生 live 签名。
  - `3090-dev/p2io_e28_barekey_hypothesis.py`（新增）：裸 key mamba 检查假设 → kv_hit=9（不匹配 live），排除。
  - `3090-dev/p2io_e28_live_path_probe.py`（复用，KV 三向）：spec==commit==query==1748 EQUAL，index 1748/1748 present，exists 全 → BRANCH E。
- 探针运行环境：`PATH=/home/charles/sglang-venv/bin:$PATH CPATH=.../include/python3.12 LIBRARY_PATH=... timeout 300 python3 <probe>`。

## evidence（三份 keys 对照表 + 分支判定 + 根因 + 修复）

### 三份 keys 对照表（KV 层，e28_live_path_probe 实跑输出）
| 层 | keys 数量 | 内容 | 是否一致 |
|---|---|---|---|
| A. spec.hash_value（写侧计划链） | 1748 | B 节点的 1748 页链 | = B |
| B. batch_set_v1 实际 commit storage_keys | 1748 | 经 `_v1_buffer_meta` blocks 拆分 | = A |
| C. 查询侧重建 keys（`_storage_hit_query`→batch_exists） | 1748 | A 的 last_hash 续链 | = B |

`A vs B: EQUAL (1748 keys)`；`B vs C: EQUAL (1748 keys)`；`index hit bitmap: 1748/1748 present`；`storage_query_count=1748`。
**分支判定：BRANCH E**（spec==commit==query 全等、index 全在、exists 全 hit）→ **KV 层完全洗脱**。确定性层全过后 live 层 miss 的剩余矛盾只在 mamba 边界钳制。

### mamba 边界钳制的决定性经验表（当前代码，batch_exists_v2 修复前）
| 配置 | kv_hit_pages | extra_pool_hit_pages | 是否 live 签名 |
|---|---|---|---|
| TRAILING(placeholder)（代码实际交付） | 20550/9 | {'kv':N,'mamba':N} | **否** |
| ALL_PAGES(placeholder) | 0 | {'kv':N} | **是** |
| TRAILING(placeholder) HEAD9 | 9 | {'kv':9,'mamba':9} | 否 |
| ALL_PAGES HEAD9 | 0 | {'kv':9} | **是（= live）** |
| TRAILING(full chain, trailing=N) | 0 | {'kv':N} | **是（= live）** |
| 裸 key mamba 检查 TRAILING(placeholder) | 9 | {'kv':9,'mamba':9} | 否（排除） |

live 日志（t38c-probe.log，340 个 pc_storage_query）：kv_hit_pages 恒 0；sidecar_hits 分布全部 `{'kv':N}`（95×{kv:9}, 71×{kv:1027}, ...），**mamba 从未出现在 sidecar_hits**。

### 分支判定（针对 e28 三选一）
- spec.hash_value ≠ commit storage_keys：**否**（A==B）。
- commit storage_keys ≠ 查询 keys：**否**（B==C）。
- 三者全等但同线程 batch_exists 仍 miss → allocator 实例/状态：**部分——KV 三者全等且 index 全在**，但 miss 不是 allocator 层，而是 **mamba 边界钳制**（final_pages = min(kv_pages, mamba boundary)）。live 恒 0 是 mamba boundary 恒 0 所致。

### 根因
live 时 extent backend 的 `batch_exists_v2` 对 mamba PREFETCH transfer 施加了 **ALL_PAGES 语义**（或该 transfer 的 hit_policy 在重建中丢失而回落到 `PoolTransfer` 默认 ALL_PAGES）。证据链：
1. live 控制器 pyc（13:50）与 mamba_component pyc（Aug 30）字节级同当前代码：mamba PREFETCH transfer = TRAILING_PAGES + `keys=["__placeholder__"]`（`'__placeholder__'` 字符串常量在 pyc 中确认）。
2. live unified_radix_cache pyc（13:50）同当前：`prefetch_from_storage` 直接 `extra_pools=[mamba TRAILING(placeholder)]` → `_storage_hit_query` → `batch_exists_v2`，无任何重建/改写。
3. 当前代码 TRAILING(placeholder)（KV 链在、node-last mamba key 在 chain[2]/chain[8]）→ kv_hit≥1（实证）。
4. live 日志 kv_hit=0 + sidecar 只含 `{'kv':N}` → 只有 ALL_PAGES 边界（从页 0 起第一个 KV-only 页即 fail → boundary=0）能产生。裸 key 假设已排除。
5. live 后端 pyc 已于 20:41 被探针覆盖（唯一 extent_file_backend.pyc），live 时确切实现不可恢复（e281df3635 HEAD 无 batch_set_v1 → live 用了中间态，git 无记录）。

**可复现缺陷（当前代码同样存在）**：placeholder-key transfer 的 `hit_policy` 一旦被重建丢弃，`PoolTransfer` 默认 ALL_PAGES 接管 → 每个 hybrid 查询 mamba boundary=0 → kv_hit=0，即 live 事故的完整签名。这不是假设——修复前的当前代码 `ALL_PAGES(placeholder)` 实证产生 kv_hit=0/extra={'kv':N}。

### 修复
`extent_file_backend.py` `batch_exists_v2`（648-651）：placeholder-key transfer 强制走 TRAILING 扫描，即使 hit_policy 回落到 ALL_PAGES。
```python
placeholder_keys = bool(transfer.keys) and all(
    k == "__placeholder__" for k in transfer.keys
)
if transfer.hit_policy == PoolHitPolicy.ALL_PAGES and not placeholder_keys:
    boundary = next(...)   # 严格逐页
else:  # trailing_pages
    ...
```
- 设计契约（p2-io-design.md §2.2/§2.3）：每 transfer 的 `hit_policy`（ALL_PAGES/TRAILING_PAGES）；mamba N=1/SWA N>1 为 TRAILING；placeholder 是构建期 keys 未知的唯一生产者（mamba_component:771、swa_component:904）——placeholder 即 TRAILING 意图的信号。
- 范围：只改定位点（extent `batch_exists_v2`）。sim_storage/HiCacheFile 有同构脆弱性但不在本任务范围，列入 followup。

## summary
确定性层（KV spec→commit→exists 三向恒等、写链==查询链逐页字节等）全过后，live 层 storage_hit=0 的剩余矛盾定位到 **mamba 边界钳制**：live 日志 kv_hit=0 + sidecar 只含 {'kv':N}（mamba 永不在）只能是 mamba PREFETCH transfer 被按 ALL_PAGES 读（placeholder keys + 默认策略）。修复 = placeholder-key transfer 强制 TRAILING 扫描（当前代码可复现该缺陷，fix 后实证消除）。修复前后对比：`ALL_PAGES(placeholder)` kv_hit 0→20550/9，mamba 进入 sidecar；显式 TRAILING(placeholder) 行为不变。

## followups（integration/性能要求 → orchestrator 调度）
- Integration（tester）：① 真实引擎 hybrid（KV+MAMBA）prefetch 全链 warm 后 storage_hit>0 且 sidecar 含 mamba；② live 签名判据（kv_hit=0/mamba 不在 sidecar）在修复后不再出现；③ mamba N=1 与 SWA N>1 两池的 TRAILING 边界在真实树形状下与 checkpoint 对齐。
- Performance：④ 修复后 3090 M4 全量 sweep storage_hit 分布（对照 e7m 的 340 查询全 0 基线）；⑤ mamba checkpoint 密度（node-last 写入 vs 查询 chain 对齐率）对可恢复前缀长度的实际收益。
- 同构脆弱性：sim_storage.py:188 / HiCacheFile（hicache_storage.py:639）的 ALL_PAGES-vs-TRAILING 分支与 extent 同构，placeholder 守卫未移植——若后续后端/模拟器复用，需同步（本任务范围外）。

## open_issues
- live 时 extent backend 的 `batch_exists_v2` 确切实现不可恢复（pyc 于 20:41 被探针覆盖，HEAD 无 batch_set_v1，live 用中间态）——根因判定基于"控制器/mamba/radix pyc 字节同当前 + live 签名只可能由 ALL_PAGES 产生 + 当前代码可复现"三条证据链，属高置信推断而非现场取证。
- `test_umbp_store.py` 收集报 `ModuleNotFoundError: No module named 'mori'`——环境缺 mori 包，与本改动无关的既有环境缺口。
- 本 epoch 改动只落 extent `batch_exists_v2` 一处 + 2 个单测；未触碰 Z3/reserve/RH/[P3]、未删 t38c 埋点。
