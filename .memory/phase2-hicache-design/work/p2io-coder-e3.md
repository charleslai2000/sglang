# p2io-coder-e3 — extent 后端 v1 写 / v2 查 key scoping 不一致修复（P0）

## 1. status

done

## 2. artifacts

- `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`（修改，+12/-7）：
  修复 v1 路径 key scoping。`get`/`set`/`exists`/`batch_get`/`batch_set`/`batch_exists`
  六处入口统一应用 `_storage_key(key) = key + config_suffix`（原来全部用裸 key）；
  v2 路径（`batch_exists_v2`/`batch_get_v2`/`batch_set_v2`）本就应用
  `_storage_key`/`_component_key`，未动。IO 核心（`_read_pages`/`_write_pages`）不应用
  变换（v2 传入的已是 storage key，避免双重后缀）。行为对齐 HiCacheFile
  （hicache_storage.py：get/set/exists 均走 `_get_suffixed_key`）。
  根因：引擎写侧 = backup_thread→`_generic_page_set`→v1 `batch_set`（裸 key）；
  查侧 = HybridCacheController._storage_hit_query（hybrid_cache_controller.py:596）
  带 sidecar pool_transfers → v2 `batch_exists_v2`（查 `key+suffix`）→ v1 裸 key 写
  永不匹配 → storage_hit 恒 0（M2/M3/定向 810+ prefetch 全 revoked:miss）。
- `test/registered/unit/mem_cache/test_extent_file_backend_unit.py`（修改，+150）：
  新增 `TestExtentV1V2KeyScope` 六个跨路径用例（见 evidence RED→GREEN）。

## 3. evidence（真实命令与输出）

### RED（修复前，2026-08-31）

- tester 复现脚本 `/tmp/p2io-v1v2-key-repro.py`（引擎同款 config：
  model_name="qwen3.5-9b-gptq" → suffix `_qwen3.5-9b-gptq_0_1`）：

  ```
  config_suffix: '_qwen3.5-9b-gptq_0_1'
  batch_set: True
  batch_exists (v1, engine write side): 1
  batch_exists_v2 (v2, engine query side): kv_hit_pages = 0
  => MISMATCH: True
  ```

- 新用例先落测试后跑（TDD RED）：`TestExtentV1V2KeyScope` 5/5 error，
  典型 `AssertionError: 0 != 3`（batch_exists_v2 对 v1 写入返回 0）。

### GREEN（修复后）

- 新用例：

  ```
  $ PYTHONPATH=python:test /home/charles/sglang-venv/bin/python -m unittest \
      registered.unit.mem_cache.test_extent_file_backend_unit.TestExtentV1V2KeyScope
  Ran 5 tests ... OK   # 后续补第 6 例后同命令 6 tests OK
  ```

- 复现脚本反转：

  ```
  config_suffix: '_qwen3.5-9b-gptq_0_1'
  batch_exists (v1, engine write side): 1
  batch_exists_v2 (v2, engine query side): kv_hit_pages = 1
  => MISMATCH: False
  ```

- 全量门：

  ```
  $ PYTHONPATH=python:test /home/charles/sglang-venv/bin/python -m unittest \
      registered.unit.mem_cache.test_extent_file_backend_unit \
      registered.unit.mem_cache.test_hicache_file_lru_unit
  Ran 80 tests in 0.886s
  OK
  ```
  （extent 套件 46 = 原 40 + 新 6；file LRU 门 34；原 74+ 用例全绿 → 无后缀/
  同路径行为零回归；v1↔v1、v2↔v2 round-trip、v2 组件 key 隔离、circular wrap、
  watermark GC、crash 全冷、tensor 页等既有语义全部保持）

- `py_compile` 两文件 exit 0。
- `git status --porcelain`：仅 ` M extent_file_backend.py`、` M test_extent_file_backend_unit.py`
  （+未跟踪 .memory/ 工作数据目录）——引擎核心零改动。

## 4. summary

修复 extent 后端 v1/v2 key scoping 不一致：v1 六个入口统一应用
`_storage_key`（对齐 HiCacheFile 双侧同后缀语义），写侧 v1 与查侧 v2 现在产生
相同 storage key；v2 写→v2 查、v1 写→v1 查不受影响（变换对称）。这是本模型
（Qwen3.5-9B + sidecar pool_transfers）storage_hit 全 0 的根因修复，
引擎核心（scheduler/unified_radix_cache/cache_controller/tree_core）零改动。

## 5. followups

- 3090 M2/M3 重跑验证（tester）：storage_hit/restore_served 应从 0 转正；
  聚合读 syscall ≤32/state 与 restore <1s 判据此前因读侧零触发为 NO DATA，
  修复后具备测量条件。
- O_DIRECT 保留档无实现（tester 8.1 实证 fd flags 无 O_DIRECT 位）——coder 跟进项，
  与本次 key scoping 无关，仍挂账。
- `test_unified_radix_cache_unittest.py` 在 unittest 直跑下 import 失败
  （顶层 `from unified_tree_core_inspection_interface import ...`，兄弟模块，
  pytest rootdir 插入才可解析）——前置存在，与本次 diff 无关；本机无 pytest
  （venv 与系统 python3 均无），M1 门按任务指定 runner（unittest）的 extent 全量
  + file LRU 两门执行。

## 6. open_issues

- 无。修复面收敛：v1 六入口 + 注释；对称性由新用例双方向锁定。
