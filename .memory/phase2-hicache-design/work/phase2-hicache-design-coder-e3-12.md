# P2-0a I7 插桩 bug 修复 + 1318 NoneType 排查（coder e3-12）

## status

**done** — I7 崩溃根因定位（hybrid `_page_transfer` override 无 return → None）并修复
（单行 guard，[P2A] 格式不变）；1318 NoneType 判定为**引擎既有 bug（优雅退出生命周期竞态）**，
只报不修；本机 py_compile exit 0、git diff 只含修复行（vs 部署态仅 1 个 token 变化）、
已部署 3090 双侧 md5 一致、远端 py_compile exit 0；未启动引擎（3090 无引擎进程，GPU 15 MiB 空闲）。

## 产物 1：`_page_transfer` 返回 None 的路径说明（I7 根因）

**None 来自 hybrid 子类 override，不是基类路径。**

- 本部署为 hybrid 引擎（Qwen3.5-9B mamba），运行时控制器类 =
  `HybridCacheController`（`python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py:110`）。
- `HybridCacheController._page_transfer`（hybrid_cache_controller.py:662-667）：
  - 664 行 `kv_completed_pages = super()._page_transfer(operation)`（基类返回 int）；
  - 667 行 `self._page_transfer_sidecar(operation, kv_completed_pages)`；
  - **函数体无 `return` 语句 → 隐式 `return None`**（注解 `-> bool` 也写错）。
- 基类 `CacheController._page_transfer`（managers/cache_controller.py:1080-1124）恒返回
  `completed_pages`（int，初始 0），**基类自身不存在返回 None 的路径**（空批次→0、
  异常→抛错由线程 try 接住继续循环）。唯一 None 路径 = hybrid override。
- **为什么之前没炸**：I7 落地前（e3-11 之前）`prefetch_io_aux_func` 调用
  `self._page_transfer(operation)` 不捕获返回值——hybrid override 的缺失 return 是
  **潜伏引擎 bug**，无人消费所以不可见。I7 捕获返回值后暴露：
  `n_pages=None` → 1186 行 `n_pages * self.page_size` → `TypeError: unsupported operand
  type(s) for *: 'NoneType' and 'int'` → **Thread-2（prefetch IO 线程）死亡** → 无
  io_finished、无 completed_req ack → prefetch 永不 finalize → 请求无限等待
  （admission 空转 1,316,229 次）→ 0 请求完成。
- 证据（3090 远端只读，engine-a2.log 14:15:35，L37086-37096 区域）：
  `File ".../managers/cache_controller.py", line 1186, in prefetch_io_aux_func` +
  `TypeError: ... 'NoneType' and 'int'`（已抓取原文，单帧 traceback，无 _page_transfer 内帧
  ——佐证 _page_transfer 是"正常返回 None"而非"内部抛错"）。

## 产物 2：1318 行 NoneType 判定 — 引擎既有 bug（只报不修）

**判定：引擎既有生命周期 bug（优雅退出竞态），与插桩无关**（1318 行
`success = self.page_set_func(...)` 是纯引擎逻辑，`_page_backup` 内无任何插桩行）。

- 完整 traceback（engine-a1.log 12693-12706，已抓取原文）：
  `Thread-4 (backup_thread_func)` → hybrid `_page_backup`（hybrid_cache_controller.py:733
  `super()._page_backup`）→ 基类 cc:1318 `page_set_func` → `_generic_page_set`
  （cc:1296）→ `storage_host_pool.get_data_page`（pool_host/mha.py:508
  `self.kv_buffer[...]`）→ `TypeError: 'NoneType' object is not subscriptable`。
- **None 来源**：`HostKVCache.destroy()`（`python/sglang/srt/mem_cache/pool_host/base.py:230`
  `self.kv_buffer = None`）。调用链：scheduler.py:5524 `scheduler.release_host_resources()`
  （仅 `gracefully_exit` 分支）→ unified_radix_cache.py:534 `host_pool_group.destroy()` →
  pool_host/group.py:180 → base.py:230。
- **触发条件（时间证据）**：异常 14:11:27，紧跟 "Gracefully exiting... Remaining number of
  requests 0"——SIGTERM 优雅退出，backup 线程仍在排空 `backup_queue` 中未完成的
  write_back 操作时，host pool 已被 destroy（kv_buffer=None）。`storage_stop_event` 只在
  `reset()`（cc:783）中 set，优雅退出路径**从不 set 也不 join backup_thread**，池先死、
  线程后醒 → 竞态。
- **建议（引擎修复，需另行裁决）**：优雅退出路径在 `release_host_resources()` 之前先
  set `storage_stop_event` 并 join 各 storage 线程（或先排空 `backup_queue`）；
  或 `get_data_page` 对 `kv_buffer is None` 返回 dummy（防竞态兜底）。
  影响：A1 中 32 请求虽全部完成，但写路径尾批可能部分页未落 L3（tester 的 open_issue 3 佐证）。

## 产物 3：修复后 I7 行最终写法

`python/sglang/srt/managers/cache_controller.py:1186`（唯一改动行，vs e3-11 部署态仅
`n_pages * self.page_size` → `(n_pages or 0) * self.page_size` 一个 token）：

```python
logger.info("[P2A] ts_ms=%d evt=prefetch_io_finished rid=%s n_tokens=%d", int(time.time() * 1000), operation.request_id, (n_pages or 0) * self.page_size)
```

- 未选"按语义跳过日志"：hybrid 正是本部署形态，跳过会使 io_finished 事件整体消失，
  A2 延迟链测量（issued→io_finished→finalize）直接作废；guard 让事件照常发射。
- 语义说明：基类路径 n_tokens 不变（实际完成页数×页大小）；hybrid 路径 n_tokens=0
  （引擎丢弃了实际值，见 open_issues 引擎修复建议——补 `return kv_completed_pages`
  后自动恢复准确值）。0 是"不可得"的诚实信号，优于用 `len(operation.hash_value)`
  冒充分批/终止场景会高估。

## artifacts

| 文件 | 改动 | 说明 |
|---|---|---|
| `python/sglang/srt/managers/cache_controller.py` | 1186 行 guard（`(n_pages or 0)`） | I7 崩溃修复，[P2A] ts_ms 格式不变，唯一改动行 |

3090 部署路径：`/root/sglang-b1-continuity/python/sglang/srt/managers/cache_controller.py`。
未 commit 未 push（临测件，I1-I10 同树共存待 P2-0a 裁决）。

## evidence

1. 本机 `python3 -m py_compile python/sglang/srt/managers/cache_controller.py`：`exit=0`。
2. git diff（vs HEAD，含 e3-10/e3-11 未提交的 I1-I10 全批次）：`4 files changed, 23
   insertions(+), 1 deletion(-)`；本次任务增量 = 部署态 md5 6923aa1d → f0737a73，
   `git diff` 中唯一与上轮不同的行是 1186（`n_pages` → `(n_pages or 0)`）。
3. 部署前基线：远端 cache_controller.py md5 `6923aa1d24f3db397321e9a0c8fe3edb` == 本机
   部署前（e3-11 状态）；部署后双侧 md5 一致：`f0737a73a381c93ec283c77912eee684`。
4. 远端 `/root/miniconda3/envs/sglang-patch/bin/python3 -m py_compile`（Python 3.10.21）：
   `REMOTE_PY_COMPILE_OK`；远端 1186 行内容核对含 `(n_pages or 0)`；远端
   `grep -c '\[P2A\]'` cache_controller.py = 1（未变）。
5. 3090 引擎进程：`ps -eo pid,args | grep -E 'launch_server|engine.*server'` = 0；
   nvidia-smi 显存 15 MiB（空闲）；**未启动引擎**（实验启动归 tester）。
6. 证据抓取（只读）：engine-a2.log L37086-37096 区域（I7 traceback）、engine-a1.log
   12693-12706（1318 traceback）原文已核对。
7. 56-regex-safety：全程行级 `grep -n -F` / `sed -n` 行段，无跨距正则。

## summary

I7 崩溃根因 = **hybrid `HybridCacheController._page_transfer` override 缺 return 语句
（潜伏引擎契约 bug）**，I7 捕获返回值后暴露 → IO 线程死亡 → prefetch 永不完成 → 请求
无限等待。修复采用任务建议的 guard `(n_pages or 0) * self.page_size`（单行，[P2A] 格式
不变）：基类路径语义不变，hybrid 路径事件照常发射（n_tokens=0 为不可得信号）。
1318 判定为**引擎优雅退出竞态**（release_host_resources 先 destroy host pool、
backup 线程后消费队列），只报不修并给出修复建议。已部署 3090 双侧一致、远端
py_compile 通过、未启动引擎。

## followups

- tester 重跑 A2（预热→重访，K=1）：预期 I7 修复后 io_finished 照常发射（hybrid
  n_tokens=0），issued→io_finished→finalize→success 延迟链可测；建议 fresh 0c 保干净。
- 解析侧注意：hybrid 路径 io_finished 的 n_tokens=0 是"不可得"信号，勿与 issued 的
  prefetch_length=20910 做差值；最终完成量以 I8 finalize 的 completed_tokens 为准。
- 引擎修复两项（另行裁决）：① hybrid_cache_controller.py:662-667 补
  `return kv_completed_pages`（零行为变化，恢复 I7 准确度）；② 优雅退出先停 storage
  线程再 destroy host pool（1318 竞态）。
- 1318 竞态下 A1 尾批写可能未落 L3——A2 重跑时顺带核对 L3 文件数/write_back 计数。

## open_issues

- hybrid override 的 `-> bool` 注解与基类 `-> int` 契约不符（同一引擎 bug 的一部分，
  见 followups ①）。
- 优雅退出路径无 storage 线程停摆机制（storage_stop_event 仅 reset() 设置）——P2-1
  admission/生命周期设计输入。
- 本分支 I1-I10 插桩为临测件，P2-0a 裁决后保留或回退（git checkout 受限，回退需
  `git show HEAD:<path>` 或按 diff 逆操作；本任务未 commit）。
