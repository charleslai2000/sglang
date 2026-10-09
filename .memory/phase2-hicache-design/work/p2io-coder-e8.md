# p2io-coder-e8 — P2-IO 性能收口 P0：restore 查询/重试相位压缩（backup-completion 事件驱动 T15）

## 1. status

**done** — 重试退避来源已定位（非指数退避，是 T6/T11 再发行循环）；按专家修正方向实现
**backup-completion 事件驱动 restore wake**（T15 BACKUP_PENDING，复用 M2 frontier wake 机制，
未采用命中率阈值方案）；引擎核心 4 文件 + 状态机 + 调度器改动；RED→GREEN 全证；extent + file
LRU 全门 104 tests OK + 三套新/扩测试全绿（54+20+5+94）。本机编码+单测完成，3090 验证另派。

## 2. artifacts（本次 e8 改动面，7 文件 + 1 新测试）

| 文件 | 改动 | 理由 |
|---|---|---|
| `python/sglang/srt/managers/scheduler_components/hicache_restore.py`（+58） | 新增 `RestoreEvent.BACKUP_PENDING`(T15)、`RestoreWaitReason.BACKUP_PENDING`、`next_restore` T15 行（→WAIT_CAPACITY/WAIT）、`wait_reason_for` 映射、`capacity_wake_applies` 纳入、新纯函数 `backup_wait_applies` | 状态机层：部分命中+备份在途 → 等待而非重算/部分恢复 |
| `python/sglang/srt/mem_cache/unified_radix_cache.py`（+63） | `chain_backup_in_flight(anchor)`（扫 `ongoing_backup`，按祖先链归属）；`revoke_pending_prefetch` 分类新增 `backup_pending`（miss/insufficient 之前）；terminal 记录新增 `revoked_backup_pending`；`_drain_and_alloc_storage_hit` ≥阈值部分命中在途时改 park 而非 alloc+IO；disposition 标 WAIT | drain 侧：查询结果分类——在途 → T15 park |
| `python/sglang/srt/managers/scheduler.py`（+20） | `_feed_restore_terminal` 映射 `revoked_backup_pending`→T15 事件 + 注册 M2 frontier waiter（`register_frontier_waiter`，自触发 write_backup_storage）；`_restore_wait_capacity_fits` 新增 BACKUP_PENDING 分支（`not chain_backup_in_flight`，ACK drain 翻转 = 事件驱动）；step4 T11 discard 纳入 | 调度器侧：park 注册 + 唤醒谓词（非轮询） |
| `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py`（+18） | 新增 `is_ancestor_or_self`（沿 parent 链判定链归属，删除节点 False） | 在途写归属判定（备份按祖先先序写，anchor 子树即请求跨度写入者） |
| `python/sglang/srt/mem_cache/unified_cache/unified_tree_core_interface.py`（+5） | 接口同步声明 | 同左 |
| `3090-dev/test_hicache_restore.py`（+8 用例） | T15 转移/唤醒环/早唤醒重 park/超时兜底/wake 后 miss 重算/时钟语义 + `BackupWaitAppliesTests` 4 边界 | 纯状态机行为守卫 |
| `3090-dev/test_drain_reentry.py`（+6 用例 + fake 扩展） | `BackupPendingRevokeTests`：在途部分命中→`revoked_backup_pending`、排空后仍 miss、0 命中不 park、无关链写在途不 park、anchor 删除不 park、**≥阈值部分命中 drain 级 park**；fake tree core 补 `is_ancestor_or_self`/`clear_storage_durable`，fake controller 补 `append_host_mem_release`/`prefetch_tokens_occupied`，`_make_cache` 补 `_prefetch_outcome_stats`/`prefetch_threshold`/`_storage_prefetch_missed_rids` | drain 分类守卫 |
| `3090-dev/test_hicache_restore_scheduler_feed.py`（新，5 用例） | `_feed_restore_terminal` park+注册、非 miss 分支、唤醒谓词在途 False/排空 True、quota deny 不变 | 调度器接线守卫 |
| `3090-dev/test_storage_regression.py`（+1 行） | fake tree core 补 `is_ancestor_or_self=lambda: False`（无链模型 harness） | 兼容新分类调用 |

既有未提交改动（前 epoch 面，本 epoch 未动）：cache_controller.py（e6 extent 接线）、
hicache_storage.py（e5 STORAGE_BATCH_SIZE=1024）、extent_file_backend.py（e7 IOV_MAX 分片）、
test_extent_file_backend_unit.py（e7）。`git status --porcelain` 见 evidence §5。

## 3. evidence（真实命令与输出）

### 3.1 退避来源定位（实现前读码 + e13 §13 数据交叉验证）

**无指数退避代码**。重试循环 = `_prefetch_kvcache` 再发行 × T6/T11 循环：
1. 查询在途链 → 部分命中（备份按 128 页/batch 原子可见，`_storage_hit_query` 遇首缺批即断）；
2. ≥阈值部分命中 → 部分恢复 IO（0.17–0.92s）→ finalize READY → admission `add_one_req`
   NO_TOKEN（device 满）→ T6 `ADMISSION_DENY` → WAIT[DEVICE_QUOTA]；
3. 逐 pass T11 谓词（`charge < available_and_evictable_tokens`，含 evictable，宽松）→
   `_prefetch_kvcache` 再发行 → 重新全链查询（13ms–604ms）→ 部分恢复 → T6 ……
   直到备份追平 → 全链命中 → 恢复 → 准入。
- "重试等待（revoke→next issued）p50=15ms" = 一个调度 pass 间隔（谓词立过）；
- "p90=15.7s / max=33.5s" = WAIT_CAPACITY 驻留（谓词被 device 占用/rate-limit 挡住）期间
  的**合法等待**，但每次 wake 都浪费一次全链查询 + 部分 IO——慢样本（9.7–49.7s）即此循环。

### 3.2 方案选择理由（按专家修正）

放弃命中率阈值（方案 a：启发式，partial prefix / extent 覆盖 / backup stalled / 长度依赖阈值
语义均不可靠）；采用方案 b：**T15 备份完成感知**——查询发现 `0 < hit < requested` 且链上有
在途 L3 写（`ongoing_backup` 中节点是 anchor 或其后代）→ park WAIT[BACKUP_PENDING] +
`register_frontier_waiter(anchor)`（复用 M2 机制：注册即 `write_backup_storage` 自触发写；
anchor 提升时 T12 ACK wake；逐 pass T11 谓词 = `not chain_backup_in_flight(anchor)`，ACK
drain 弹队即翻转 = 事件驱动，非轮询）→ wake 后恰好一次 re-lookup → 全链命中 → 一次恢复。
lookup 次数：初始 1 + wake 后 1（链多节点时每 ACK 至多 1 次，观察场景 ≤2–3）。

### 3.3 语义保持论证（P2-1 CLOSED 机制不退化）

- **60s 超时兜底**：T15 是 WAIT_CAPACITY 常规条目，`wait_clock_next` 首入上弦、重入不重上弦
  （`test_t15_clock_armed_like_any_wait` 守卫）；T13 从该等待照常 → ADMIT_RECOMPUTE
  （`test_t15_timeout_still_bounds_the_wait`）。
- **quota deny ≠ recompute decision**：T6/T7/DEVICE_QUOTA 路径零改动（`test_quota_deny_semantics_unchanged`）；
  T15 是 capacity 型等待，`next_restore` 永不从 BACKUP_PENDING 发 ADMIT_RECOMPUTE
  （`test_t15_backup_pending_is_capacity_wait_not_recompute`）；wake 后 re-lookup 真 miss
  （T9 genuine）仍立即重算（`test_t15_miss_after_wake_still_recomputes`）。
- **wake 单一上弦**：T12/T11 wake 路径原样（`pop_frontier_ready` 一次消费；`register_frontier_waiter`
  重注册丢弃 ready 标记；早唤醒（anchor 先 ack、深节点仍在途）→ re-lookup 部分命中 → T15
  重 park（`test_t15_repark_after_early_wake`）——事件重上弦，非逐 pass 轮询（在途时 T11 谓词
  False）。
- **无死锁**：备份完成 → ACK drain 弹队 → 谓词翻转 → wake；备份失败（partial ack →
  `clear_storage_written`）→ 写放弃 → `ongoing_backup` 弹队 → 谓词翻转 → wake → re-lookup
  部分命中且无在途写 → 不重 park → 现行部分恢复/重算行为；anchor 删除 → 谓词 True 自愈
  （re-match root）或 T13；T13 兜底一切。
- **零命中绝不 park**（`backup_wait_applies` 0 < hit 条件）：全新后缀（从未写 L3）保持现行
  立即重算，避免 60s 空等回归；真部分（ring 覆盖）无在途写 → 不 park，现行行为不变。
- **buffer mode**：`ongoing_backup` 恒空（ack 走 buffer_pipeline 分支）→ 天然不 park。

### 3.4 RED（新行为对 HEAD 旧码，逐项失败）

```
$ python /tmp/p2io_red_check.py
RED-OK  old module has no RestoreEvent.BACKUP_PENDING: AttributeError
RED-OK  old module has no RestoreWaitReason.BACKUP_PENDING: AttributeError
RED-OK  old module has no backup_wait_applies: AttributeError
RED-OK  old drain module: BackupPendingRevokeTests fail (errors=0 failures=2)
RED-OK  old scheduler path: unknown terminal -> REVOKED_MISS -> recompute (no park)
```
（旧 drain 模块经 stubenv 强制路径实测：部分命中在途分类仍为 revoked_miss；旧调度器对未知
terminal 落入 revoked_miss genuine → 立即重算——park 语义在旧码上不可能成立。RED 脚本在 /tmp。）

### 3.5 GREEN（新码全门）

```
$ PYTHONPATH=python:test .../python -m unittest registered.unit.mem_cache.test_extent_file_backend_unit \
    registered.unit.mem_cache.test_hicache_file_lru_unit
Ran 104 tests in 0.960s OK

$ PYTHONPATH=python:test .../python 3090-dev/test_hicache_restore.py            -> Ran 54 tests OK
$ PYTHONPATH=python:test .../python 3090-dev/test_drain_reentry.py              -> Ran 20 tests OK
$ PYTHONPATH=python:test .../python 3090-dev/test_hicache_restore_scheduler_feed.py -> Ran 5 tests OK
$ PYTHONPATH=python:test .../python 3090-dev/test_storage_regression.py         -> Ran 94 tests OK
```
（本机 venv = /home/charles/sglang-venv，torch 2.13.0+cu129；PYTHONPATH=python 强制本地树，
已验证 `sglang.__file__` 指向本地——早前一次无 PYTHONPATH 的运行误测到 site-packages 旧拷贝，
已纠正重跑。py_compile 9 文件 COMPILE_OK。）

## 4. summary

- **退避来源**：无指数退避；重试相位 = T6/T11 再发行循环（每次 wake 浪费一次全链查询 + 一次
  部分恢复 IO），15ms p50 = pass 间隔，15.7s/33.5s p90/max = WAIT_CAPACITY 驻留 + 反复部分
  恢复被拒的组合。
- **实现**：查询发现链备份在途（部分命中 + `ongoing_backup` 有链内节点）→ T15 park
  WAIT[BACKUP_PENDING] + M2 frontier waiter 注册 → ACK drain 事件唤醒（T12/T11 双通道）→
  一次 re-lookup → 全链恢复。预期整链 p50 1.32s → ~0.9s（0.41 读 + ~0.2 查询 + 0.08 mamba），
  慢样本（9.7–49.7s）随重试循环消失；验证另派 3090。
- **语义**：T13 超时、quota deny ≠ recompute、wake 单一上弦全部保持；失败/驱逐链最终可唤醒
  或超时（无死锁）；0 命中与真部分不 park（无 60s 空等回归）。

## 5. followups

1. **3090 验证（tester）**：M4T 同配置短实验，判据 = ① 同 rid lookup 次数 ≤2–3（[P2A] 事件
   restore_issued/revoke 序列）；② 重试等待 p90 从 15.7s 降为备份尾延迟（秒级）；③ 整链
   issued→io_finished p50 → ~0.9s；④ restore_recompute cause=miss 的备份在途样本消失；
   ⑤ 0 崩溃/0 OOM/事件守恒（issued = revoke + io_finished）。
2. 同步面：本报告 §2 的 9 文件（5 引擎 + 4 测试）需同步 3090 部署树（md5 双侧核对，旧版备份）。
3. 遗留观察：T6 device-full 等待本身（非重试循环）仍是 restore turn 尾延迟来源——属
   Ready Horizon / host tier 问题域，不在本任务范围。

## 6. open_issues

- `test_unified_radix_cache_unittest.py` / `test_tree_core_registry.py` 直接跑报
  `unified_tree_core_inspection_interface` ModuleNotFoundError——**既有 harness 路径问题**
  （兄弟文件需目录在 path），与本次改动无关；加目录后 registry 10 tests OK，unified_radix
  套件 620 errors 为 GPU/环境依赖（MagicMock 交互，HEAD 版本等值复现，已 cp 交换验证 + md5
  复原）。
- 备份在途判定依赖 `ongoing_backup`（提交未 ack 的写集合）；提交后未 ack 前与"排队未开始"
  同桶（`write_storage` 即登记）——与 ack drain 语义一致，无遗漏路径。
- e8 未改 extent 后端读批大小（10.4 的 7.7s 批循环归因）与 allocator 连续化（12.3 A/B）——
  按 ledger 优先级在查询/重试相位之后，属后续 epoch。
