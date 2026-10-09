# p2io-coder-e2 — 修复 ExtentFileBackend bf16 写入 bug（M2 崩溃根因）+ 真实张量单测

## 1. status

done

## 2. artifacts（本次会话变更文件）

| 文件 | 变更 | 内容 |
|---|---|---|
| python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py | 修改（2 处 helper） | `_page_byte_view`（:55-80）与 `_target_byte_view`（:82-96）：torch.Tensor 分支由裸 `.numpy()` 改为 bit 级 uint8 视图 `value.contiguous().cpu().view(torch.uint8)` 再 `.numpy()`——与 HiCacheFile（hicache_storage.py:476/:531 的 `view(dtype=torch.uint8)` 路径）对称；bytes/bytearray/memoryview duck-typed 分支原样保留；torch 为函数内 lazy import（模块顶层零 torch import 契约不变） |
| test/registered/unit/mem_cache/test_extent_file_backend_unit.py | 修改（+113 行，新增 7 用例 + `_TensorPagePool`） | 新增 `TestExtentTensorPages`（7 用例）：bf16/fp16/fp32 CPU tensor 写→读 round-trip（dtype 不变 + torch.equal 数值全等 + uint8 视图逐字节全等）；9 页混合 dtype batch round-trip；non-contiguous 写侧输入；写侧字节视图零拷贝断言（view.obj 数据指针 == tensor.data_ptr()）；v2 bf16 tensor pool（真实 torch 页，覆盖 batch_get_v2 的 dummy tensor 读回路径）。torch 缺失时 skipTest（模块级 try/except import）；文件头 docstring 与 register_cpu_ci est_time 15→20 同步更新 |

引擎核心（scheduler/unified_radix_cache/cache_controller/unified_tree_core/hiradix_cache/hybrid_cache_controller/schedule_batch/schedule_policy）：零改动（git status 与 M1 基线一致，本会话 Edit 未触及）。

## 3. evidence（验证命令与真实输出）

环境：/home/charles/sglang-venv（torch 2.13.0+cu129，无 pytest，unittest 等价驱动）。

- **RED（修复前）**：新 7 用例中 4 个在 `extent_file_backend.py:67 arr = value.numpy()` 抛
  `TypeError: Got unsupported ScalarType BFloat16` —— 与 tester-e2 记录的 M2 崩溃逐字一致
  （`Ran 7 tests ... FAILED (errors=5)`，其中 1 个为测试自身 numel 笔误，已修）。
- **GREEN（修复后）**：
  `PYTHONPATH=python:test /home/charles/sglang-venv/bin/python -m unittest registered.unit.mem_cache.test_extent_file_backend_unit.TestExtentTensorPages -v`
  → `Ran 7 tests ... OK`。
- **全量回归门**：
  `PYTHONPATH=python:test /home/charles/sglang-venv/bin/python -m unittest registered.unit.mem_cache.test_extent_file_backend_unit registered.unit.mem_cache.test_hicache_file_lru_unit`
  → `Ran 74 tests in 0.885s OK`（extent 40 = 33 既有 + 7 新；file LRU 34 既有回归门）。
- **M2 场景冒烟**（模拟 backup_thread 首次 batch_set）：128 页 × 16KiB bf16（共 2MB）batch_set →
  batch_get → 逐字节全等，`OK in 0.007 s`。
- **零拷贝确认（实测）**：`t.contiguous().cpu().view(torch.uint8).data_ptr() == t.data_ptr()` 为 True；
  `.cpu()` 对 CPU tensor 返回 self；`.numpy()` 数组 `__array_interface__["data"][0] == t.data_ptr()` 为 True；
  非 contiguous 输入 `contiguous()` 复制（新对象）——零拷贝链仅对 contiguous CPU 张量成立（引擎 flat page 契约）。
- **顶层零 torch import**：`grep -n "import torch" extent_file_backend.py` → 仅 :73/:91 两处函数内 lazy import。
- **git 改动面**：`git status --porcelain` 与 M1 基线一致（引擎核心均为基线既有未提交工作）；本会话仅 Edit
  extent_file_backend.py 与测试文件（工具调用记录可查）。

## 4. summary（设计与实现落点）

- **根因**：`_page_byte_view`/`_target_byte_view` 对 torch.Tensor 调裸 `.numpy()`；torch 的 numpy() 不支持
  bf16/fp16（`TypeError: Got unsupported ScalarType BFloat16`）。引擎 host pool flat page 为 bf16 CPU tensor
  （kv_cache_dtype=bf16 配置），backup_thread 首次 batch_set 即死 → 全链零写入 → restore 零服务。
- **修复**：与 HiCacheFile 已验证路径对称——`value.contiguous().cpu().view(torch.uint8)` 是 bit 级 reinterpret
  （共享 storage，零拷贝），`.numpy()` 在 uint8 上无 bf16 限制；读侧重构 target 同款（`view[:] = page` 填充
  writable uint8 视图）。duck-typed 兼容：byte-like 分支未动；numpy 数组等无 `contiguous` 属性的对象走原
  `.numpy()` 路径。
- **单测缺口**：原套件 torch-free（duck-typed bytearray），`.numpy()` bf16 分支零覆盖；新 7 用例直驱真实
  torch.Tensor（bf16/fp16/fp32 CPU）覆盖写/读两侧与 v1/v2 路径。

## 5. followups

1. M2 重跑（tester）：修复后须在 3090 以 kv_cache_dtype=bf16 配置重跑 20911-token 链 restore，验证 extent
   写入真实发生（get_stats pwrites/bytes_written > 0）且 restore <1s；并单独验证 tester-e2 根因 2（既有核心
   竞态）是否仍可在正常负载下触发。
2. CI 侧（base-a-test-cpu）：新用例在 CI runner 有 torch 时直接执行，无 torch 时 skip——两分支均不失败；
   可按 pytest 命令复跑同一文件（本机无 pytest，unittest 等价）。

## 6. open_issues

1. **non-contiguous read target 无法原地填充（既有语义，契约内）**：`_target_byte_view` 对 strided target
   `contiguous()` 产生副本、写入副本、原对象不变——引擎读回 target 恒为 contiguous flat page，不受影响；
   测试中已注明该边界（写侧 non-contiguous 输入正确，读回须 contiguous target）。
2. **0-dim 张量**：`view(torch.uint8)` 对 0-dim 抛错（HiCacheFile 同款路径），页恒非 0-dim，契约内。
3. **torch-free skip 路径未在本机实测**：本机 sglang 依赖 torch，无法在无 torch 解释器下导入测试文件；
   skip 逻辑为模块级 try/except + skipTest，经代码审查确认。
4. **requires_grad tensor 的 `.numpy()` 仍抛错**（既有行为，torch 限制）：引擎 flat page 为 no-grad，不受影响。
