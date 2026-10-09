# p2io-coder-e22 — L3 写查一致性：64-hex 全宽埋点 + page_set_func 绑定确认 + deterministic 断言

- 任务：e22（e7l 后继；coordinator 重定向：seed 已实锤无罪（字节一致），缺陷收窄到"index 注册 key vs 查询 key 不命中"；64-hex 对拍 + 绑定确认 + 修复 + deterministic 断言）
- 运行：2026-09-02（本机静态 + 纯 Python hash oracle；无 3090 权限跑 live）
- 报告：p2io-coder-e22.md

## 1. status

**pending**（Task 1/2/4 完成；Task 3 修复方向待 3090 64-hex 对拍数据定夺——写/读两侧静态链已自洽，live 是否仍 miss 需 64-hex 全宽对比最终裁决）

## 2. artifacts

- `python/sglang/srt/mem_cache/unified_radix_cache.py`（~2205）— **pc_write_seed 升级为完整 64-hex**：`write_seed`（写链 page-0 种子 = parent.last hash 全宽）、`page0_hash`、`page1_hash`、`n_pages`。供与读侧全宽对拍，定位第一个分歧字节。
- `python/sglang/srt/managers/scheduler.py`（~2982）— 读侧 gate **anchor.last_hash8 → 全宽 `last_hash`**（`tree_cache.get_last_hash_value(last_host_node)` 完整 64-hex）。
- `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`（~625）— **pc_storage_query 的 keys 全宽**：`[k for k in hash_value[:8]]`（去掉 `[:16]` 截断），记录查询侧完整 64-hex 首 8 键。
- `test/registered/unit/mem_cache/test_extent_file_backend_unit.py` — **新增 `TestExtentWriteQueryRoundTrip`**：`test_same_span_write_then_query_storage_hit_4`。内联纯 Python refhash oracle（逐字节对齐原生），真实 `ExtentFileBackend`（qwen3.5-9b-gptq / `_qwen3.5-9b-gptq_0_1` 后缀）+ 真实 `HiCacheController._storage_hit_query`（`object.__new__` 隔离实例化）→ 同 span 写→读断言 `storage_hit_count == 4*page_size` 且 `hash_value == write_keys`。
- 三处埋点全部 log-only，`/tmp/t38c-on` gate，零数值路径改动。

## 3. evidence（命令 + 真实输出）

### 3.1 编译与测试
```
py_compile 3 生产文件 -> PY_COMPILE_OK exit=0
新测试：unittest ...TestExtentWriteQueryRoundTrip -> ok (Ran 1 test OK)
extent 全文件：unittest ...test_extent_file_backend_unit -> Ran 71 tests OK (70+1 新)
全门 327：Ran 327 tests in 0.112s OK
```

### 3.2 断言有意义性（RED 基线证明）
```
同 seed 写 4 页 -> batch_exists=4, _storage_hit_query storage_hit_count=16(4*page_size) 
不同 seed 查询 -> storage_hit_count=0
=> 断言正确区分对齐(命中)与错位(miss)两态，是 Task 4 的确定性判据
```

### 3.3 Task 2 绑定确认（page_set_func）
- extent backend → `page_set_func = _page_set_zero_copy`（cache_controller.py:691，因 extent ∈ zero-copy 名单）→ `batch_set_v1`。
- `batch_set_v1`（extent_file_backend.py:525+）commit：`storage_keys = [_storage_key(k) for k in keys]`，`_allocator.commit(storage_keys, ...)`。
- 读侧 `batch_exists`（:392）/`batch_exists_v2`（:618）：`lookup(_storage_key(key))`——**同一 `_storage_key` transform**。
- `_storage_key(key) = key + config_suffix`（:283）；`config_suffix = _qwen3.5-9b-gptq_0_1`（e7l §3.9 已证两侧一致）。
- `_page_set_zero_copy`（cache_controller.py:1379）= `all(batch_set_v1(...))`，key 不经任何二次变换。
- **结论：写注册 key 与读查询 key 在同一 backend 实例内 transform 字节一致**（generic batch_set 与 zero-copy batch_set_v1 都走 `_storage_key`）。

### 3.4 读/写 hash 计算自洽（静态）
- 写：`compute_node_hash_values(node, page_size)`（utils.py:127）seed = `parent.hash_value[-1]`。
- 读：`get_hash_str(token_ids, last_hash, page_size)`（utils.py:107）。
- 两侧同一 `get_hash_str`（cache_controller.py:627 绑定）+ 同一 `page_size`（tree_core:416 == controller:363 == params.page_size）。
- 种子已 e7l 字节级坐实一致；page0 8-hex 一致。**剩余未覆盖：完整 64-hex 后段是否逐字节一致（e7l followup 1 的开口）——现埋点已升级为全宽，live 可定位第一个分歧字节。**

## 4. summary

Task 1（64-hex 全宽埋点）完成：写侧 pc_write_seed 与读侧 gate/query 均升级为完整 64-hex hash（去掉 8/16-hex 截断），3090 e7l 同配置重跑后即可逐 matched span 对比 write full key vs query[0] full key，定位第一个分歧字节位。Task 2（page_set_func 绑定）确认：extent 走 zero-copy batch_set_v1，写/读同 `_storage_key` transform，commit 与 lookup key 字节一致。Task 4（deterministic 断言）完成：新增单测验证同 span 写→读 storage_hit=4（内联 oracle + 真实 backend + 真实 `_storage_hit_query`），并证明不同 seed 场景正确返回 0（断言有意义）。Task 3（修复）未盲目实施：写/读两侧静态链已自洽，index 注册与查询 key transform 字节一致，唯一未证的是完整 64-hex 是否逐字节一致——这必须由 3090 全宽对拍最终裁决后再定修复方向（若 64-hex 后段分歧 → 修 hash 全宽一致性；若全等仍 miss → 修 allocator index 注册路径）。

## 5. followups

1. **【最高优先】3090 64-hex 对拍**（tester，orchestrator 调度）：e7l 同配置重跑，`touch /tmp/t38c-on`，对比 pc_write_seed（write_seed/page0_hash 全宽）vs pc_prefetch_enter（anchor.last_hash 全宽）vs pc_storage_query（keys 全宽）。逐 matched span 找第一个分歧字节位——决定 Task 3 修 hash 全宽还是修 index 注册。
2. **Task 3 修复分叉**：若 64-hex 后段分歧 → 查哪个环节截断/重算（native get_hash vs compute_node_hash_values 的 page 边界/字节序）；若全等仍 miss → 查 allocator `_index` 注册（commit 与 lookup 是否同 key，`_storage_key` 是否在 commit/lookup 间被二次变换，或 backend 实例重启/重开后 index 未持久化）。
3. **host memory pressure（e7l §4 次级观察，749 subtree drop）** 与 **shutdown sanity FAILED（node104，4 violations）**：独立于 L3 key-space，建议分列跟踪（e7l followup 3/4）。
4. 修复方向确定后，用 `TestExtentWriteQueryRoundTrip` 作为回归门（RED→GREEN 已具备：同 seed 命中 4 / 异 seed miss 0）。

## 6. open_issues（未解决/风险）

- **完整 64-hex 是否逐字节一致未测**（e7l followup 1 的唯一开口）：8-hex 一致 + matched chain 连续强烈暗示全等，但"写进文件却 miss"的 B 分支具体缺陷点（allocator 注册 vs hash 分歧）需全宽对拍最终裁决。
- 原生 hash 模块本机不可编译（缺 libssl-dev / openssl/sha.h）；deterministic 断言用内联 refhash oracle（已验证与原生逐字节对齐，见 e7k CASE A/B）。
- extent backend / Z3 / reserve / RH / [P3] 埋点零改动；本轮只改 3 处埋点全宽 + 新增 1 测试。
