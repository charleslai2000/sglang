# p2io-coder-e6 — P2-IO 主修复：Extent v1 zero-copy（batch_get_v1/batch_set_v1）

## 1. status

**done** — v1 zero-copy 实现 + 接线 + 单测全部落地，本机门全绿（100 tests OK）。

## 2. artifacts（本次改动）

- `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`
  — 新增 v1 zero-copy 面：`batch_get_v1` / `batch_set_v1` / `_v1_buffer_meta`（契约守卫）/
  `_v1_host_blocks`（ctypes 别名宿主块）/ `_preadv_full`（多 iovec 续读）；模块 docstring 更新。
- `python/sglang/srt/managers/cache_controller.py` — 接线（方案 b，1 行）：零拷贝名单
  `:668-669` 加入 `"extent"`。
- `test/registered/unit/mem_cache/test_extent_file_backend_unit.py` — 新增
  `TestExtentV1ZeroCopy`（13 用例，真实 page_first MHA host pool）+ 模块 docstring 一行。
- 既有未提交改动（非本次）：hicache_storage.py STORAGE_BATCH_SIZE=1024（e5）、
  extent 包 e4 基础（_storage_key 统一等）——git status 确认改动面 = extent 包 + 测试 + 接线点三处。

## 3. evidence（命令与真实输出）

- **RED**（v1 回退到 ABC 默认后跑新 13 用例）：
  `python /tmp/red_v1_run.py`（把 ExtentFileBackend.batch_get_v1/set_v1 指回 HiCacheStorage 默认）
  → `Ran 13 tests ... FAILED (errors=13)`，核心失败逐字：
  `TypeError: 'NoneType' object is not iterable`（= scout 预警的控制器崩溃形态：
  `_page_get_zero_copy :1084` 对 None 的 TypeError 家族）与 `AssertionError: None != [False, False, False]`（返回契约）。
- **GREEN**：
  `PYTHONPATH=python:test /home/charles/sglang-venv/bin/python -m unittest registered.unit.mem_cache.test_extent_file_backend_unit`
  → `Ran 66 tests in 0.060s OK`（53 既有 + 13 新 v1）。
- **全量门**：
  `... -m unittest registered.unit.mem_cache.test_extent_file_backend_unit registered.unit.mem_cache.test_hicache_file_lru_unit`
  → `Ran 100 tests in 0.923s OK`（extent 66 + file LRU 34；TestExtentV2/TestExtentV1V2KeyScope 侧车
  v2 与跨路径回归全绿）。
- **编译**：`py_compile` 三个改动文件 → OK。
- **改动面**：`git status --porcelain` = M cache_controller.py / M hicache_storage.py /
  M extent_file_backend.py / M test_extent_file_backend_unit.py / ?? .memory/（交换目录）。
- **环境事实**：本机 sglang-venv 无 pytest（unittest 等价驱动，与 e2/e3 一致）；
  本机可用内存 8GiB < 10GiB 保留 → 真实 host pool 构造须 mock `base.psutil.virtual_memory`
  （沿用 test_mem_pool_host.py 的 `RESERVE + 64GiB` 先例）。

## 4. summary

### v1 契约实现摘要（签名对齐 ABC hicache_storage.py:226-248 + nixl 模板）

- **读侧 batch_get_v1(keys, host_indices, extra_info) -> List[bool]**：
  `len(host_indices) == len(keys)*page_size`（page_size = mem_pool_host.page_size，每 key 占
  page_size slot，与 cache_controller.py:1136-1138 切片契约一致）→
  `get_page_buffer_meta(host_indices)` 解析目标块（page_first MHA = 每页 k/v 双块，
  块序 == flat 页字节序）→ allocator.snapshot（RAM index）→ 按 extent 分组 +
  `_merge_requested_ranges`（复用 e4 exact-range 合并）→ **每合并区间一次 preadv 直写宿主**：
  iovec 序列 = [k块, v块, gap 擦除缓冲, ...]，总长 == 区间跨度；≤4KiB gap 落 scratch 丢弃 →
  锁内 verify 世代（复用失败 = miss，宿主半写字节不被消费，语义同 _read_pages 丢弃 scratch）+
  touch 刷新 LRU。返回逐 key bool，**恒为 list，永 None、永不 raise**。
- **写侧 batch_set_v1**：同一 meta 解析 → 锁内 `_gc_evict` + `plan(zip(storage_keys, page_lens))`
  → 每 extent 按 offset 排序后 **一次 pwritev**（块序 [k,v] 重组 flat 页字节）→ `commit`；
  整批 all-or-nothing（拒绝 = 全 False，同 _write_pages 语义）。config_suffix 与 v2 共用
  `_storage_key`（extent_file_backend.py:273-279），v1 写 → v2 batch_exists_v2 命中已验证。
- **守卫**（_v1_buffer_meta）：无池/无 get_page_buffer_meta / indices 长度错 / 块数不整除 /
  meta 异常 → 拒绝并返回 [False]*n（消除 scout 的运行时崩溃风险）；
  **layout == "layer_first" 显式拒绝**（layer_first 的 flat 页序 = K 平面后 V 平面，而
  get_page_buffer_meta 块序 = 逐层 k/v 交错，顺序散射会损坏数据；默认布局 page_first
  server_args.py:2789 不受影响）。
- **宿主直写机制**：`(ctypes.c_char * n).from_address(ptr)` 别名 torch 宿主内存
  （mmap_allocator.py:107 同款），os.preadv/pwritev 接受 ctypes 数组（venv 实测确认）；
  零中间页缓冲、零 dummy 页分配。

### 接线选择：方案 (b)（cache_controller.py:668-669 名单加 "extent"），理由

1. 方案 (a) dynamic 路径 `_create_dynamic_backend` 调 `backend_class(storage_config, kwargs)`
   ——空 dict 恰巧落在 `file_path` 形参上，只是签名巧合兼容；dynamic 是给外部后端设计的，
   用于 builtin 属脆弱 hack。
2. (b) 保持 builtin 注册路径（backend_factory.py:161-162 `backend_class(storage_config)`）干净；
   且 `storage_backend_type == "extent"` 使 hiradix_cache.py:402 / storage_attachment.py:77 的
   后端身份判定正确（(a) 下身份是 "dynamic"）。
3. v1 已真实实现 + 13 负/正用例锁死契约，"实现必须真实可用才开"的风险已消除；
   extent 部署（Qwen3.5 hybrid，anchor=MHATokenToKVPoolHost page_first）即 zero-copy 目标，
   无保留 legacy generic 路径的必要。file 后端不受影响（4c 现状不变）。

### 测试（13 新用例，真实 MHATokenToKVPoolHost + 真 torch 内存）

非空 config_suffix 断言 + v1 写→v1 读（wipe 后全量复原，k/v 双段精确拆分）、v1 写→v2 查一致性、
v2 写→v1 读、config_suffix 跨模型隔离（读写双向）、indices 长度错 → 全 False、未注册池 →
返回 False list（负契约，防 None 崩溃）、layer_first 拒绝且池零改动、部分 miss 不连坐、
单 extent 一次 preadv（syscall spy）、gap 合并单 preadv + scratch 不位移散射、
字节计数/调用计数统计、存储页长与池布局不符 → miss（布局漂移拒绝）。

## 5. followups

1. **3090 验证（tester）**：launch-l3-3090.sh 切 `${L3_BACKEND:-extent}`（plan-p2io 任务 07 已有
   计划）即自动走 v1 zero-copy（名单式接线，无需 extra_config）；t38c 测 restore 窗口
   prefetch_io_finished-issued 间隔 + get_stats 计数；8.31s 整链重测裁决 44ms/批成分。
2. **侧车 v2 是否升指针直写**（MambaPoolHost.get_page_buffer_meta mamba.py:534-594 已在）：
   v1 落地后若 mamba 侧车成新瓶颈再议——不在本刀。
3. **layer_first 池的 v1**：当前显式拒绝（日志可辨）；如需支持需按池特化块重排（引擎侧
   pool 接口扩展，超本任务范围）。
4. **O_DIRECT 校准层**（SGLANG_HICACHE_EXTENT_BACKEND_DIRECT_IO 保留位）：v1 直写宿主块的
   对齐约束未验证（page_first 页跨度为 4KiB 倍数时 is_stride_page_aligned 可查），进入该层前
   需加守卫。

## 6. open_issues

- 44ms/批 的固定/每页成分仍无插桩证据（e3 归因为推断）；STORAGE_BATCH_SIZE=1024 的
  "~8x" 假设未实测——zero-copy 落地后 3090 整链重测为裁决。
- layer_first 模型 + extent = v1 全 miss（restore 读不到数据，日志有 refusal）——当前
  Qwen3.5 page_first 部署不受影响；若未来启用 layer_first 模型须先做 followup 3。
- 本机无 pytest：CI（base-a-test-cpu）侧需按 pytest 复跑同一文件确认（测试文件
  torch-optional，无 torch runner 下 v1 类 skip）。
