# P2-1 前置引擎修复 — A 守护 / B 退出顺序 / C hybrid return / D 插桩分层（coder e4-01）

## status

**done** — A/B/C/D 四项全部落地；本机 py_compile exit 0、新增 torch-free 回归
`3090-dev/test_storage_regression.py` 11/11 通过（C 的 RED→GREEN 已验证）、既有
`test_drain_reentry.py` 7/7 通过；已部署 3090 双侧 8 文件 md5 一致、远端 py_compile
exit 0、远端（真实 torch + 真实安装包路径）两套回归 11/11 + 7/7 通过；未启动引擎
（GPU 15 MiB 空闲、0 进程）。未 commit 未 push。

## artifacts

| 文件 | 改动 | 说明 |
|---|---|---|
| `python/sglang/srt/managers/cache_controller.py` | +55 | **A**：`storage_failure_reason` 健康位（__init__ 378 后）；`_storage_thread_fatal`（记录 fatal reason + logger.error + exc_info）；4 个 storage 线程函数（prefetch_io_aux / prefetch_thread / backup_thread / prefetch_sync_thread）统一加 `except Exception → _storage_thread_fatal + return`（不重启线程）。**B**：`stop_storage_threads()` 公开方法（优雅退出停摆，委托 `_stop_storage_threads`：stop event → wake → join 10s → 存活则 raise fail-fast）。reset()/attach 时清 `storage_failure_reason`（显式重启=新租约） |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | +108 | **A**：`check_hicache_events` 顶部健康检测 → `_handle_storage_failure`（一次性：error 日志 + revoke 全部 ongoing_prefetch（走 release_aborted_request，不残留悬空）+ 释放 ongoing_backup 的 host lock ref）；`query_storage_hit_length` / `prefetch_from_storage` / `_write_backup_storage_node` 三处降级门（storage_failure_reason 非 None → L3 视为空 → recompute 回退）。**B**：`release_host_resources` 先 `stop_storage_threads()` 再 destroy host_pool_group（1318 竞态）。**D**：`_log_restore_disposition` 每请求一次 final disposition（decline 3 处 RECOMPUTE/too_short·denied_rate_limit·aux_alloc_failed + revoke 漏斗 RECOMPUTE/revoked:{terminated·miss·insufficient·alloc_failed} + finalize RESTORE/PARTIAL/RECOMPUTE{miss·shortfall·full·hybrid_discard}），requested/granted/deny_reason 合一事件 |
| `python/sglang/srt/managers/scheduler.py` | +36 | **D**：8 条每 pass 级插桩（bif_reset/bif_set×5/admission/no_token）改经 `_p2a_trace()`（`/tmp/t38c-on` 文件门控，同 t38c 先例，无需重启）；`prefill_deny_summary` 30s 节流聚合行（消费 schedule_policy 计数器）；`_last_deny_stats_ts` 字段；import `prefill_deny_snapshot` |
| `python/sglang/srt/managers/schedule_policy.py` | +21 | **D**：6 条 `prefill_deny` 逐尝试行 → 模块级 `_PREFILL_DENY_COUNTERS` 计数器（reason 键）+ `prefill_deny_snapshot()`（取走并清零）；移除已无用的 `import time` |
| `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py` | +5/-1 | **C**：`_page_transfer` 补 `return kv_completed_pages`（缺失 return → None 杀死 IO 线程的 I7 潜伏 bug），注解 `-> bool` 修正为 `-> int`；纯防御，正常命中/恢复状态机零变化 |
| `python/sglang/srt/mem_cache/hiradix_cache.py` | +5 | **B**：`release_host_resources` 先 `stop_storage_threads()` 再 destroy token_to_kv_pool_host（同 1318 竞态的另一缓存路径） |
| `3090-dev/test_storage_regression.py` | 新增 | torch-free stubenv 回归（11 测试）：C FULL/Mamba 两路径 return 断言 + sidecar ack 计数（用真实 STORAGE_BATCH_SIZE 计算，双模式鲁棒）；A 两线程致命处理、健康门（query/issue/write）、`_handle_storage_failure` 清理（ongoing_prefetch/ongoing_backup/锁释放/解阻塞等待请求）；B release 顺序与空引用；reset 清健康位 |
| `3090-dev/test_drain_reentry.py` | +1 | `_FakeController` 补 `storage_failure_reason = None`（新控制器契约字段，既有 7 测试保持通过） |

## evidence

1. 本机 `python3 -m py_compile`（7 引擎文件 + 2 测试文件）：`exit=0`（Python 3.12.3）。
2. 本机回归（torch 不可用 → stubenv 路径，执行真实源码）：`test_storage_regression.py`
   `Ran 11 tests / OK`；`test_drain_reentry.py` `Ran 7 tests / OK`。
3. **C RED→GREEN**：临时移除 hybrid `return kv_completed_pages` 后 C 两测试
   `FAILED (failures=2)`（`assertIsInstance(ret, int)` 断言 None）；恢复后全绿。
4. 部署 3090 `/root/sglang-b1-continuity/`（scp，8 文件含 2 测试）：
   - 双侧 md5 逐文件一致（8/8：2e4e479b/22ef58c0/1939b65b/a92be0d3/3bb6ae94/7095a5f5/
     c5b65bef/c6ebc64e；中途发现 hybrid 首传为 RED 旧版 acb9ee…，重传后 3bb6ae 双侧一致）
   - 远端 `/root/miniconda3/envs/sglang-patch/bin/python -m py_compile`（Python 3.10.21）：
     `REMOTE_PY_COMPILE_OK`
   - 远端真实 torch + 真实安装包路径（`sglang.srt...__file__` = 部署路径，STORAGE_BATCH_SIZE=128）
     跑回归：`test_storage_regression.py` 11/11 OK、`test_drain_reentry.py` 7/7 OK。
     首跑 mamba ack 计数断言失败（2 != 3，假 SBS=2 vs 真 SBS=128）→ 断言改为按真实
     STORAGE_BATCH_SIZE 计算，重传后全绿。
5. 3090 引擎进程 0、nvidia-smi 15 MiB（空闲）；**未启动引擎**（实验归 tester）。
6. git diff：`7 files changed, 228 insertions(+), 3 deletions(-)`（+ 新增
   test_storage_regression.py 未跟踪）；逐行审查过目，无无关改动；56-regex-safety 全程
   行级 grep / 精确字符串替换。

## summary

A：storage 四线程统一致命处理（记录 reason → 标记 unhealthy → 线程退出，**不透明重启**），
scheduler 每步经 check_hicache_events 发现后一次性清理全部 in-flight（prefetch revoke 走
既有 release_aborted_request 路径释放 host/锁/占用，backup 释放 host lock ref），三个 L3
入口（query/issue/write）显式降级（log.error 一次 + L3 视为空 → recompute），#16614 型
"线程死 → L3 静默失效"从此有显式错误与降级语义。B：优雅退出固定顺序
stop→drain→join→teardown（stop_storage_threads 在 host pool destroy 之前），1318 的
NoneType 竞态被消除（SIGTERM 尾 frontier 缺口语义不变）。C：hybrid override 补 return
（`-> int`），I7 根因的契约缺口闭合，正常路径行为零变化，回归测试覆盖 FULL 与 Mamba
两组件并验证了 RED。D：长期层 = prefetch 生命周期 6 事件（I3/I5-I10 保留）+ 每请求
restore_disposition（RESTORE/PARTIAL/RECOMPUTE + requested/granted/deny_reason）+ 30s
deny 聚合；调试层 = 8 条每 pass 行（bif/admission/no_token）经 `/tmp/t38c-on` 门控
（touch 即开、remove 即关，无需重启）。

## followups

- tester 侧：A/B/C 的引擎行为验证（下次实验跑起后核对 `evt=restore_disposition` 每请求
  恰一行、prefill_deny_summary 30s 周期形态、优雅退出日志无 NoneType traceback）。
- 解析侧注意：restore_disposition 与 prefetch_finalize/revoke/abort_cleanup 相邻成组，
  disposition 行是每请求终态唯一标记，建议作为归因主键；deny 聚合窗口 = 30s。
- 调试门控：`touch /tmp/t38c-on`（3090 上）开启 admission/bif/no_token 每 pass 行，
  分析完 `rm /tmp/t38c-on` 关闭。
- 未 commit 未 push：P2-1 统一批次提交（含 I1-I10 插桩与本次修复）时，注意
  schedule_policy 的 `import time` 已被本次移除（vs HEAD 已无此差异）。

## open_issues

- `_stop_storage_threads` join 超时 10s 后 raise（fail-fast）——若某次优雅退出遇到后端
  hang 的线程，release_host_resources 会抛错（进程以异常退出）；这是有意的 fail-fast，
  但 tester 需知晓该签名。
- 分布式（TP>1）语义：failure 是单 rank 局部事件；死 rank 的 sync 线程若参与跨 rank
  all_reduce，其他 rank 可能阻塞——本修复覆盖本地降级与清理，跨 rank 汇合 hang 不在
  本次范围（3090 部署为单卡 TP1，不受影响）。
- storage_failure_reason 在 `_handle_storage_failure` 触发前若 scheduler 未轮询到
  check_hicache_events（极端忙等 pass），清理会延迟一个 pass——语义上无悬空（门已
  生效），仅延迟。
- 上游 #16614 修复 PR 未核实（issue 已因不活跃关闭）；本实现为 fork 自研语义
  （degrade + 一次性错误），与 upstream 可能不同，若日后合上游需对照。
