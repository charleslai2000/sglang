# phase2-hicache-design-coder-e4-01

- **工作标题：** phase2-hicache-design-coder-e4-01
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-coder-e4-01.md`：**
**done** — A/B/C/D 四项全部落地；本机 py_compile exit 0、新增 torch-free 回归
`3090-dev/test_storage_regression.py` 11/11 通过（C 的 RED→GREEN 已验证）、既有
`test_drain_reentry.py` 7/7 通过；已部署 3090 双侧 8 文件 md5 一致、远端 py_compile
exit 0、远端（真实 torch + 真实安装包路径）两套回归 11/11 + 7/7 通过；未启动引擎
（GPU 15 MiB 空闲、0 进程）。未 commit 未 push。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-coder-e4-01.md`：**
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

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-coder-e4-01.md`：| 文件 | 改动 | 说明 |
|---|---|---|
| `python/sglang/srt/managers/cache_controller.py` | +55 | **A**：`storage_failure_reason` 健康位（__init__ 378 后）；`_storage_thread_fatal`（记录 fatal reason + logger.error + exc_info）；4 个 storage 线程函数（prefetch_io_aux / prefetch_thread / backup_thread / prefetch_sync_thread）统一加 `except Exception → _storage_thread_fatal + return`（不重启线程）。**B**：`stop_storage_threads()` 公开方法（优雅退出停摆，委托 `_stop_storage_threads`：stop event → wake → join 10s → 存活则 raise fail-fast）。reset()/attach 时清 `storage_failure_reason`（显式重启=新租约） |…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-coder-e4-01.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-coder-e4-01.md`; SHA256 `978636d65430c0874bb4790f2439714c0f51852a5f726c34e94e4dd3940b336c`; source state `tracked`
