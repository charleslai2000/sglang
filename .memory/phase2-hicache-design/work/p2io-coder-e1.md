# p2io-coder-e1 — P2-IO 第一刀（ExtentFileBackend）本机编码 + 单测（M1 前半）

## 1. status

done

## 2. artifacts（实现文件清单）

| 文件 | 变更 | 内容 | 子任务 |
|---|---|---|---|
| python/sglang/srt/environ.py | 修改（+11 行） | 新增 6 个 extent env（STORAGE_DIR/MAX_SIZE/MIN_FREE_SPACE/EXTENT_SIZE/FILE_SIZE，均 EnvStr(None)，DIRECT_IO=EnvBool(False)）+ 选择器 SGLANG_L3_BACKEND=EnvStr(None)；挂在 "HiCache storage backends" 段 | 01 |
| python/sglang/srt/mem_cache/storage/backend_factory.py | 修改（+8 行） | 注册 "extent" → sglang.srt.mem_cache.storage.extent.extent_file_backend.ExtentFileBackend（懒加载）；`_create_builtin_backend` ("file","sim") → ("file","sim","extent") | 02 |
| python/sglang/srt/server_args.py | 修改（+4 行，配置层） | `--hicache-storage-backend` choices 加入 "extent" + help 文本；`_handle_hicache` Step 0：flag 未显式给出且 SGLANG_L3_BACKEND 已设时回退（declare 于解析管线内，先于 :8362/:9188 校验） | 02 |
| python/sglang/srt/mem_cache/storage/extent/__init__.py | 新建 | 包 docstring | 03 |
| python/sglang/srt/mem_cache/storage/extent/extent_allocator.py | 新建（202 行） | 纯逻辑核心：ExtentRef(msgspec.Struct frozen)；circular allocator（plan 纯计算 + commit 两阶段，失败写零状态残留）；slot generation 单调（reuse/GC 时 ++）；RAM 索引 dict[key→ExtentRef] + slot 反查 + OrderedDict recency；evict_slot_lru 按 LRU 回收最旧 slot；4096 倍数强制（ValueError）；零 torch import | 03 |
| python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py | 新建（573 行） | v1 全实现（get/set/batch_get/batch_set/exists + batch_exists 覆盖，主 KV 路径）+ v2 三件套（侧车池语义）。config_suffix 复刻 hicache_storage.py:370-390；extra_config 优先于 env（lru evictor 先例）；单预分配 sparse 文件（64GiB 默认，per-rank 文件 hicache.data{suffix}）+ 持久 fd；batch_set 内按 extent 聚合（字节双限 min(extent_size, 批次剩余)）→ 每 extent 一次 pwritev；batch_get 按 extent 分组 span → 一次 preadv → 页切片（快照(锁)→IO(无锁)→generation 复检(锁)，失配=miss 且丢弃半读数据）；写 ACK = pwritev 成功 + 索引登记（全批锁内执行，pwrite 失败零状态）；水位 lazy GC（used>max_size×ratio 或 free<min_free → 同步回收 LRU slot）；duck-typed 字节转换（torch 张量 .numpy()+cast("B")，测试 bytearray，模块顶层无 torch import）；get_stats（preads/pwrites/opens/bytes_*）；clear/close；DIRECT_IO env 解析 + 预留警告（buffered 实现） | 04, 05 |
| test/registered/unit/mem_cache/test_extent_file_backend_unit.py | 新建（646 行，32 用例） | TestExtentAllocator（11：回绕/generation 失效/GC 水位/plan 纯性/4096 强制/超限拒绝）+ TestExtentV1（14：round-trip/聚合 pread=1 与 pwrite=1（mock.patch 双保险 + stats）/多 extent/回绕/水位 GC/min_free 压力/拒绝语义/clear/crash 重开全冷/stats）+ TestExtentV2（4：round-trip/组件 key 隔离/前缀语义/索引长度失配）+ TestExtentFullFile（1：3×128 跨批多 extent）+ TestExtentFactory（1：create_backend 真实实例化）；torch-free 驱动（bytearray 页） | 03-06 |
| test/registered/hicache/test_hicache_spec_file_storage.py | 修改（+73 行） | 兄弟类 TestHiCacheSpecExtentStorage（storage_backend="extent"、expected="ExtentFileBackend"、env=SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR）；等待谓词从 .bin 计数改为 extent 语义（st_blocks 分配块稳定 3 轮 = 首请求已吸收）；E2E 实跑归 tester/3090 | 06 |

**引擎核心（scheduler/unified_radix_cache/cache_controller/unified_tree_core/hiradix_cache/hybrid_cache_controller/schedule_batch/schedule_policy）：零改动**（见 §4 git 对比）。

## 3. evidence（验证命令与真实输出）

环境事实：本机 sglang-venv（torch 2.13.0+cu129）**无 pytest**（全系统无），测试以 unittest 等价驱动（测试文件均为 unittest.TestCase）；PYTHONPATH=python:test 指向仓库代码。

- 新套件 + file LRU 回归门（M1 前半门）：
  `PYTHONPATH=python:test /home/charles/sglang-venv/bin/python -m unittest registered.unit.mem_cache.test_extent_file_backend_unit registered.unit.mem_cache.test_hicache_file_lru_unit`
  → `Ran 66 tests in 0.879s OK`（32 新 + 34 既有，零改动）
- 基线门（改动前）：test_hicache_file_lru_unit → `Ran 34 tests in 0.872s OK`
- allocator 门：`grep -c "import torch" extent_allocator.py` = **0**；extent_file_backend.py 亦为 0
- env 门：grep 恰 **7** 行；`envs.SGLANG_L3_BACKEND.get() is None`、`envs.SGLANG_HICACHE_EXTENT_BACKEND_EXTENT_SIZE.get() is None`、`DIRECT_IO.get() is False` 均通过
- factory 门：`'extent' in StorageBackendFactory._registry` ok；`import sglang.srt.server_args` ok；TestExtentFactory 用例内 `create_backend("extent", cfg, None)` → `type(...).__name__ == "ExtentFileBackend"` 且可读写
- 聚合用例（04 验收）：100 key 同 extent 批读 → `spy.call_count == 1` 且 stats pread 增量 = 1；批写 pwrite 增量 = 1
- crash 语义：同目录重建 → 全 key exists False、get None、stats 归零（preads=0/pwrites=0/opens=1）
- torch 生产路径冒烟：fp16 张量 set/get 逐字节 round-trip、fp32 batch round-trip 全等（`.numpy()+cast("B")` 路径；`memoryview(tensor)` 直接失败已被该路径替代）
- SGLANG_L3_BACKEND 回退四象限（`_handle_hicache` 直驱，构造后 resolve 需要模型路径，故直接调用 handler）：env 设+flag 未设 → "extent"；显式 flag 优先；env 未设 → None；hicache 未激活 → 不回退
- spec 兄弟类 collect：类列表含 TestHiCacheSpecExtentStorage，storage_backend=extent / expected_storage_backend=ExtentFileBackend；实跑需 GPU+HF 模型（本机 401，归 tester）

## 4. git 前后对比（引擎核心零改动证据）

实施前基线 `git status --porcelain`（已记录）：M = 3090-dev/test_drain_reentry.py、cache_controller.py、schedule_batch.py、schedule_policy.py、scheduler.py、hiradix_cache.py、hybrid_cache_controller.py、unified_tree_core.py、unified_radix_cache.py、server_args.py；?? = .memory/、3090-dev/test_hicache_restore.py、test_storage_regression.py、scheduler_components/hicache_restore.py。

实施后新增条目（仅本计划文件）：
- M python/sglang/srt/environ.py（本计划）
- M python/sglang/srt/mem_cache/storage/backend_factory.py（本计划）
- M test/registered/hicache/test_hicache_spec_file_storage.py（本计划）
- ?? python/sglang/srt/mem_cache/storage/extent/（本计划）
- ?? test/registered/unit/mem_cache/test_extent_file_backend_unit.py（本计划）
- server_args.py：基线已 M（既有工作），本次新增 diff 恰 4 行（help/choices/回退块），配置层非引擎核心

引擎核心 4 文件（scheduler.py / unified_radix_cache.py / cache_controller.py / unified_tree_core.py）的 diff 与基线完全一致（工作树状态与基线快照相同，本会话 Edit 从未触及这些文件）；diff 内容全部为既有未提交工作（如 unified_radix_cache.py 810 行）。

## 5. summary（设计与实现落点）

- **聚合**：v1 主路径 batch 入口内聚合——batch_set 按 (key,字节) 经 allocator.plan 排布进 extent（64MiB 默认，字节双限），同 extent 页 pwritev 一次写；batch_get 按 extent 分组取 [min_offset, max_offset+len) span 一次 preadv，页切片拷回 target。写路径全程持索引锁（plan→pwrite→commit 原子；pwrite 失败零状态，ACK=落盘+登记）；读路径快照(锁)→IO(无锁)→generation 复检(锁)，slot 被复用/GC 后旧 ref 失配即 miss（半读数据丢弃）。
- **allocator**：circular + per-slot generation；cursor 逐 slot 前移，进入放不下的 slot 时 drop（旧条目失效 + gen++ + cursor 归零）即复用，单批内重入已打包 slot 则整批拒绝（防自覆盖）；同 key 重写 = 新位置登记 + 旧 slot 记账解链（R3）；used_bytes 按活数据计，水位 GC 同步回收最旧 slot。
- **crash 语义（B4）**：无 metadata persistence，重启索引空 = 整盘作废；单文件 per-rank（config_suffix 进文件名，跨 rank 无共享 allocator 冲突）。
- **v2**：逻辑移植 HiCacheFile fold（最长前缀 + ALL_PAGES/TRAILING_PAGES），全部 RAM 索引 O(1)；组件 key `key.<pool>+suffix` 独立 extent 不串池。
- 目标行数：后端合计 787 行（allocator 202 + backend 573 + __init__ 12），落在 ~600-800 区间。

## 6. followups / open_issues

1. **pytest 缺失**：本机 sglang-venv 无 pytest（未获授权安装），本门以 unittest 等价命令验证；M2/CI 侧按计划 pytest 命令复跑同一测试文件。
2. **test_unified_radix_cache_unittest 回归门在本机不可绿**（环境性，非本次改动引入）：2288 例中 860 error——801×"Not enough host memory"（host pool 容量校验，本机内存/GPU 共享）+ 65×CUDA OOM（GPU 0 仅 5.57GiB 且被其他进程占用）+ 少量 mock 期望与分支既有未提交引擎改动（unified_radix_cache.py 810 行 diff）漂移。该文件保持零改动；tester 需在干净机器/3090 上跑此门。
3. **链级 pread 计数与设计 ≤32 的差异**：本实现每批（128 页）每 extent 一次 pread——20911 页全链 restore ≈ 164 次 pread（而非设计假设的每 extent 整读 10 次）；字节总量不变（640MB），p50≤0.6s 为真判据；≤32 判据需 M2 重基准（tester/architect 裁决）。
4. **O_DIRECT（B2）**：env/配置键已接线，启用时仅告警（页长非 4096 对齐，整 extent 对齐 IO 才安全），缓冲实现待标定档。
5. **B1 标定 / B4 可选文件头目录段 / B5 file 保留**：按计划留待后续（本刀固定 64MiB、v1 全冷、HiCacheFile+"file" 保留作对照与回退）。
6. **spec E2E 实跑**：TestHiCacheSpecExtentStorage 已交付可 collect，实跑（GPU+模型）归 tester（M2/CI）。
7. 遗留小项：`_page_view` 依赖 `.numpy()`（host 池页均为 CPU 张量，契约内）；非连续张量会拷贝。
