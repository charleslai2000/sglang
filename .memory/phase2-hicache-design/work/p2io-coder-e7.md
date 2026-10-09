# p2io-coder-e7 — P0 修复：Extent v1 IOV_MAX(1024) 溢出（pwritev 分片 + preadv 守卫）

## 1. status

**done** — 写侧 pwritev 分片 + 读侧 preadv 守卫 + 4 个新单测（RED→GREEN 全证），
extent 全量 + file LRU 门全绿（104 tests OK），本机编码+单测，引擎核心零改动。

## 2. artifacts（本次改动，仅 extent 包 + 测试两文件）

- `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`（915 → 946 行，+31）：
  - 模块常量 `_IOV_MAX = 1024`（:70，注释锚定实测证据：3090 与本机均 1024 OK / 1025 EINVAL）。
  - `_pwritev`（:917-946）重写为分片循环：`for start in range(0, len(buffers), _IOV_MAX)`
    每片 ≤1024 iovecs，片间 offset 按已写字节推进；**每片独立错误处理**——单片 OSError
    或 short write 立即 log + 返回 False（调用方 all-or-nothing 拒绝整批，语义与旧版一致）；
    `pwrites` 统计按真实 syscall 计数（≤1024 iovecs 的批与旧版逐次相同）。
  - `_preadv_full`（:877-912）加同限守卫：每 syscall 的 iov 段数 ≥1024 即 break（剩余段
    由下一轮从 `done` 续取），防御性一行级包装，统计口径不变。
- `test/registered/unit/mem_cache/test_extent_file_backend_unit.py`（+4 用例，70 总数）：
  - `TestExtentV1ZeroCopy.test_v1_large_batch_over_iov_max_shards_and_round_trips`：
    600 页 × 2 块 = 1,200 iovecs 写→wipe→读全等；pwritev/preadv spy call_count 均 == 2
    （1024+176 片）。
  - `TestExtentV1ZeroCopy.test_v1_write_exactly_iov_max_stays_single_syscall`：
    512 页 = 恰好 1,024 iovecs 保持单次 pwritev（分片不得提前），round-trip 全等。
  - `TestExtentIovMaxBoundary.test_pwritev_over_iov_max_shards_and_round_trips`：
    1025 个 raw buffer（奇数 iovec 数，池几何造不出）→ 2 片、内容逐字节全等（写侧+读侧守卫同证）。
  - `TestExtentIovMaxBoundary.test_pwritev_at_iov_max_stays_single_syscall`：
    恰好 1,024 iovecs 单 syscall（守护分片下限不被误调低）。
  - 新 helper `_big_pool_backend`（torch 类内）：更大 host pool（600/512 页容量）+
    独立 backend（256Ki extent / 1Mi file）；module docstring 补一行。

## 3. evidence（真实命令与输出）

- **本机边界复现（= 3090 M4 阈值，无需 GPU）**：
  `/home/charles/sglang-venv/bin/python` 探针（os.sysconf + pwritev/preadv 直调）：
  `SC_IOV_MAX: 1024`；`pwritev n=1024: OK wrote=8192` / `n=1025: OSError 22 Invalid argument` /
  `n=1200: OSError 22` / `n=2048: OSError 22`；`preadv n=1024: OK` / `n=1025: OSError 22`。
- **RED**（4 新用例对旧码，`... -m unittest` 三行选择器）→ `Ran 4 tests ... FAILED (errors=2)`：
  - helper 1025 用例：`AssertionError: False is not true` @ `self.backend._pwritev(0, buffers)`，
    日志逐字 `ExtentFileBackend: pwrite failed at 0: [Errno 22] Invalid argument`（M4 症状复现）。
  - v1 600 页用例：`batch_set_v1` 返回 `[False]*600`（all-or-nothing 整批拒绝，即 M4
    1,495 次备份失败的生产形态）。
  - 两个边界用例（恰好 1024 iovecs）旧码即过——本就是守护"分片不得提前"。
- **GREEN**：同三行选择器 → `Ran 4 tests in 0.053s OK`。
- **全量门**：`... -m unittest registered.unit.mem_cache.test_extent_file_backend_unit
  registered.unit.mem_cache.test_hicache_file_lru_unit` → `Ran 104 tests in 0.976s OK`
  （extent 70 = 66+4，file LRU 34；v1 17 用例 -v 复跑 OK）。
- **编译**：`py_compile` 两改动文件 → COMPILE_OK。
- **改动面**：`git status --porcelain` = M cache_controller.py / M hicache_storage.py /
  M extent_file_backend.py / M test_extent_file_backend_unit.py / ?? .memory/。
  cache_controller.py（e6 "extent" 接线 1 行）与 hicache_storage.py（e5 STORAGE_BATCH_SIZE=1024）
  为**既有未提交改动**（diff 已逐行核对），本次增量仅 extent 包 + 测试两文件。

## 4. summary

### 分片策略定义

- **上限**：每 syscall ≤ `_IOV_MAX = 1024` iovecs（Linux UIO_MAXIOV；1024 OK / 1025 EINVAL
  双机实测）。
- **写侧（batch_set_v1 经 `_pwritev` 自动受益，batch_set_v1 本体零改动）**：对 extent 的
  扁平 iovec 序列按 1024 切连续片；片 n 的偏移 = extent 基址 + 前 n-1 片字节和。MHA
  page_first 双块页下 1024 片界恰落在第 512 页后（页对齐是 2 块/页的巧合，非依赖——
  文件是扁平字节流，任意块数都正确）。每片独立 `os.pwritev` + 独立错误分支：单片
  EINVAL/short → log + False → 调用方整批拒绝、不 commit（ACK = pwrite 成功 + 索引注册
  的既有契约不变）。generic `_write_pages`（1 iovec/页）同享该分片，1024 页 generic 批
  恰为单片，行为不变。
- **读侧（防御性守卫）**：`_preadv_full` 每 syscall 的 iov 段数封顶 1024，超出段由续读
  循环下一轮从 `done` 起重建 iov 承接；EOF/短读语义与统计口径不变。当前 3–4 合并区间
  × 2 块 ≤8 段无风险，未来 2048+ 页批或更碎落盘不踩 EINVAL。

### 测试要点（按 unit-test-admission 归类）

- 600 页 / 1025 buffer 用例 = **bug regression**（M4 1,495 次 EINVAL 备份失败；旧码即红）。
- 恰好 1024 iovecs 两用例 = **派生边界**（守护分片阈值 1023/1025 的误调与 1024 提前分片，
  删之则"分片下限"回归无人看守）。
- 读侧守卫由 600 页用例的 preadv call_count==2 断言 + 1025 helper 读回覆盖。

## 5. followups

1. **3090 复测（tester）**：M4 口径重跑裁决 0.8s 整链目标（e3 §11.5 followup 2）；
   v1 写侧修复后 backup 应满载（对比 M4 的 21% KV / 1,495 失败）。本机代码 md5 同步
   需含本次两文件。
2. **syscall/state 判据**（e3 §11.4-5）：修复后整链 21 批 × 2 片 ≈ 42 pwritev + 3–4
   preadv/批 —— 若仍超 32 上限，下轮归因落盘连续性与 allocator 打包（e3 §11.5-3）。

## 6. open_issues

- `pwrites` 统计从"每批一次"变为"每 syscall 一次"（>1024 iovecs 批会 >1）；`preads`
  仍按"每合并区间一次"——两统计口径不完全对称，但均不破坏既有断言；如需统一为
  逐 syscall 口径（更诚实反映 syscall 数）是独立小改，不在本刀。
- 本机无 pytest：CI（base-a-test-cpu）侧需按 pytest 复跑同一文件（既有惯例，同 e6）。
- 引擎核心零改动（cache_controller/hicache_storage 未触碰）；3090 侧旧探针版本
  （.bak-m4）替换时注意只同步 extent_file_backend.py 与测试文件。
