# p2io-coder-e4 — 30× read amplification 修复（exact-range 读 + 合并策略 + 放大计数器）

## 1. status

**done** — 本机编码 + 单测全部完成：RED 复现（7 新用例对旧代码全失败，REAL_EXIT=1）→ 修复 →
GREEN（7/7 通过）；全量门 87 tests OK（extent 53 = 46 旧 + 7 新，file LRU 34）；引擎核心零改动
（git status --porcelain 仅 2 文件 + 未跟踪 .memory/ 交换目录）。3090 未触碰（本机 + venv 验证）。

## 2. artifacts

| 文件 | 变更 | 为什么 |
|---|---|---|
| python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py | ① 模块 docstring 读侧描述改写（"extent 是分配单位不是读取单位"）；② 新增 `_MERGE_GAP_THRESHOLD = 4096` 常量 + 纯函数 `_merge_requested_ranges()`；③ `_stats` 增 6 计数器（requested_bytes / physical_bytes_read / prefetch_bytes_read / last_batch_*×3）；④ `_read_pages` 重写：per-extent sort by offset → 相邻 range 合并（gap ≤ 4KiB）→ 每个合并 range 一次 exact pread → 按原 ExtentRef 切片回组装 | 专家裁决：64MB extent 保留为分配单位，读取改 exact range；旧 span 读 [min..max) 把同 extent 内其它链的夹页全读进来 = 30×（M3：335MB 请求 / 10GB 物理） |
| test/registered/unit/mem_cache/test_extent_file_backend_unit.py | 新增 `TestExtentReadAmplification` 类 7 用例 | 守卫 30× 回归 + 合并策略 derived property（阈值边界 4096/4097）+ 计数器 bookkeeping + v1/v2 双路径覆盖 |

引擎核心（scheduler/cache_controller/hybrid_cache_controller/hicache_storage/unified_radix_cache/
extent_allocator/backend_factory/environ/server_args）零改动。

## 3. evidence（真实命令与输出）

**RED（旧代码，新测试先行）**：
```
$ PYTHONPATH=python:test /home/charles/sglang-venv/bin/python -m unittest \
    registered.unit.mem_cache.test_extent_file_backend_unit.TestExtentReadAmplification
Ran 7 tests in 0.010s
FAILED (errors=7)        # REAL_EXIT=1（无管道直读退出码）
```
7 例全失败：KeyError: 'last_batch_requested_bytes'（计数器不存在）+ span 读导致
physical/requested 断言不满足。

**GREEN（修复后）**：
```
$ ... -m unittest registered.unit.mem_cache.test_extent_file_backend_unit.TestExtentReadAmplification
Ran 7 tests in 0.003s
OK                        # REAL_EXIT=0
```

**全量门（extent 全量 + file LRU）**：
```
$ PYTHONPATH=python:test /home/charles/sglang-venv/bin/python -m unittest \
    registered.unit.mem_cache.test_extent_file_backend_unit \
    registered.unit.mem_cache.test_hicache_file_lru_unit
Ran 87 tests in 0.885s
OK                        # REAL_EXIT=0；extent 单套 53（-v 逐例计数 53 ok）
```

**改动面固化**：
```
$ git status --porcelain
 M python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py
 M test/registered/unit/mem_cache/test_extent_file_backend_unit.py
?? .memory/
```
（.memory/ 为交换目录，不入版本控制——引擎核心零改动证据。）

**py_compile** 两文件 EXIT=0；grep 确认新常量/函数/计数器落盘（extent_file_backend.py:61/64/251-256/550-554）。

**附带检查**：test_unified_radix_cache_unittest 本机 venv 无法跑（native_hash C++ 扩展
cpp_extension.load 编译失败，预存环境项，与本 diff 无因果——该文件未触碰，且不在本任务门内；
前历 epoch 门同为 extent+file LRU）。

## 4. summary

**合并策略（明确定义）**：每次 `_read_pages` 调用内，per extent：
1. 收集该 extent 内本批请求的 refs（offset, length, key_index）；
2. 按 offset 升序排序；
3. 贪心线性合并：维护当前 range [start, end)；下一 item [s, e) 满足 `s - end ≤ 4096`（gap ≤ 一个
   4KiB sector）则并入（end = max(end, e)），否则收尾开新 range；
4. 每个合并 range 一次 pread exact [start, end)（文件偏移 = extent_id×extent_size + start）；
5. 成功读回的 range 内按原 ExtentRef 切片（buf[ref.offset - start : ... + ref.length]）组装回
   调用方——v1 batch_get / v1 get / v2 batch_get_v2 三入口共用，接口与返回语义零变化。
不跨 extent 合并（不同 slot 是文件不相邻区域）。放大上界：physical ≤ requested + 4096×合并次数
（每次合并最多吸收 4KiB 死字节，31KB 页单次合并 ≤1.13×）；稀疏请求（gap ≫ 4KiB，M3 形态）不合并
→ physical == requested → 比值 1.0。旧 span 读（每 extent 一次 [first..last]）正是 30× 来源：
本批请求只覆盖 extent 的一小部分，span 把其它链夹在中间的页全读入。

**放大计数器设计**（stats_snapshot() 下，engine get_stats() 仍返回 None 不变）：
- 累积：`requested_bytes`（各批 ref.length 之和，miss 不含）、`physical_bytes_read`（合并 range
  span 之和；正常路径与旧 `bytes_read` 相等）、`prefetch_bytes_read`（恒 0：本后端无预读逻辑，
  每个 pread 都是请求驱动；引擎侧 proactive prefetch 以普通 batch_get/batch_get_v2 到达，与
  restore 读无法在 backend 层区分，归入 requested/physical 同口径——引擎侧用
  prefetch_io_finished/restore_served 做 pread 归属拆分，任务口径满足"单独统计"）；
- 每批：`last_batch_requested_bytes` / `last_batch_physical_bytes` / `last_batch_preads`（最近一次
  _read_pages 的瞬时值，便于逐批断言与 M4 采批）。
判据口径：amplification = physical_bytes_read / requested_bytes < 1.2×。

**单测 7 例**（RED→GREEN 逐例）：64MiB extent 内 100×4KiB 页、请求每第 25 页（100KiB 间隔）→ 4
次 pread、physical == requested（旧代码 400KiB/16KiB = 25×，本用例即 30× 回归守卫）；连续页 10 键
合并 1 次 pread 且 physical == requested（spy 计数 1）；5KiB 间隔两键不合并（2 pread，physical
2000）；阈值边界 4096 合并 / 4097 不合并（物理字节 2000+len / 2000，preads 1/2）；v2 路径
（batch_get_v2 10 页写、请求 0/7 两键 → physical == 2000 == requested）；累积 + 每批计数器语义
（get 与 batch_get 都计数、跨批累加）；prefetch_bytes_read 恒 0。

## 5. followups

1. **3090 同步 + M4 实测**（tester）：同步 2 文件 → 部署树（本机 md5 记录后）；M3 同负载重跑，
   读侧口径 = stats_snapshot 增量 physical_bytes_read/requested_bytes（预期 ≈1.0–1.1×，<1.2×
   判据）；prefetch_bytes_read 恒 0 实证。
2. **设计文档对齐**（文档属主）：p2-io-design.md §2.3"每 extent 内取 [first..last] 连续区间一次
   读入"已被专家裁决取代（64MB extent = 分配单位非读取单位）——需在文档标注读侧 exact-range 语义。
3. **O_DIRECT 标定档**（挂账）：仍无实现（fd flags 02100002 无 O_DIRECT 位）；exact-range 读使
   每 pread 区间变为任意对齐的请求区间，O_DIRECT 需整 extent 对齐缓冲方案，属独立 tier。
4. **per-tid io 计数器**（挂账）：M3 报告指出 raw p50 含 IPC/HTTP 等引擎背景读无法精确剥离；
   backend 侧现只有累计/每批字节计数，per-tid 归属需引擎侧探针，不在本后端范围。
5. 合并阈值现为模块常量（4096）；若 M4 显示相邻链碎片 gap 分布有更优切点，可提为
   extra_config/env 键（"merge_gap"）——当前无消费方，不提前加配置面。
6. test_unified_radix_cache_unittest 在本机 venv 需 native_hash C++ 扩展（cpp_extension.load
   失败）；如需本机跑 URC 门，先修扩展构建环境（预存问题，非本任务引入）。

## 6. open_issues

- URC 单测本机 venv 预存失败（native_hash 编译），与本 diff 无因果，已如实记录。
- M3 的 10GB 物理读为旧 span 读路径产物；修复后物理读预期回落至请求字节量级，但 3090 实测
  （M4）才是裁决依据——本机只到组件级（87 门）验证。
- 循环文件覆盖（M3 §9.4 根因）与读放大无关、不随本修复变化；整链 640MB 服务时间样本仍需
  规避覆盖的专项用例。
