# p2io-tester-e1 — P2-IO M2 3090 验证（中断于本机重启，extent 实验在 3090 脱离续跑）

## 1. status

pending（本机重启打断；3090 侧 extent 实验已脱离自跑，完成标记在 /root/p2io-m2-status.log；恢复后由新 tester 继续——3090 状态文件含全部进度与剩余步骤）

## 2. artifacts

**同步（已完成，双侧 md5 核对一致）**：本地 P2-IO → 3090 部署树 `/root/sglang-b1-continuity`（4c 部署树，conda env `sglang-patch` editable install，Python 3.10.21/torch 2.13.0）。同步前逐文件 diff 确认差异恰为 P2-IO delta（environ.py +10 行、backend_factory +8、server_args 3 hunks、spec 测试 +73）；引擎核心 md5 与本机逐字节一致。被覆盖 4 文件备份于 3090 `/root/p2io-presync-bak/`。同步 8 文件：extent/ 3 文件、environ.py、backend_factory.py、server_args.py、test_extent_file_backend_unit.py、test_hicache_spec_file_storage.py。

**launch 脚本（已完成）**：/root/launch-l3-3090.sh 改造——`--hicache-storage-backend "${L3_BACKEND:-file}"` + extent env 注入（SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR/MAX_SIZE/MIN_FREE_SPACE，native+docker 两分支）；STORAGE_DIR fail-fast 与 file env 流不变；保留 4c 时代 --hicache-promotion-margin-tokens；备份 .bak-p2io。3090 版与本机版本有差异（margin 参数），基于 3090 版编辑。

**单测（已完成）**：3090 pytest 三 env 全缺 → unittest 等价（同本机）。test_extent_file_backend_unit + test_hicache_file_lru_unit = 66 tests OK（修复前）。unified_radix_cache 门（2288 例）：post-sync 212 errors / pre-sync 202 errors（A/B），失败类全部既有环境性：host-pool 容量校验（~90-100 例）、**ninja 缺失导致 native_hash JIT 编译失败（112 例，sglang-patch env 无 ninja）**、cudaHostRegister 冲突（6-36 例，pin 内存残留）、mock 漂移断言（26-36 例）；P2-IO 引入 0 新失败（本机基线 860 errors → 3090 显著更近绿）。注意该门需 PYTHONPATH 含 test/registered/unit/mem_cache（模块级 import inspection interface）。

**file 基线运行（已完成）**：证据 /root/evidence-p2io-file-01/run-20260831-180853/ + /root/engine-p2io-file.log。96 请求 0 失败 1 降级，elapsed 983s。restore turns n=24：ttft p50=66.4s/p95=106.2s/max=139.2s；storage_hit 合计 648,718 tokens（与引擎 metric storage_HiCacheFile 精确一致）；[P2A] issued=150 / io_finished=80（n_tokens 合计 1,404,544）/ restore_recompute=92（70 miss+22 timeout）/ retry=134 capacity+37 frontier；issued→io_finished 间隙 n=59 p50=25.4s/p95=43.6s/max=48.5s。scheduler(164812) 累计 io：syscr=1,501,305 / syscw=607,036 / read_bytes=37.4GB。引擎 SIGTERM 优雅退出（ENGINE_EXIT=0，GPU 15MiB）。

**Bug 发现并修复（TDD 完成，双侧 GREEN）**：extent 引擎启动约 2 分钟崩溃（无请求时）：`AttributeError: 'dict' object has no attribute 'prefetch_stats'`（unified_radix_cache.py:3738 check_hicache_events → StorageMetricsCollector.log_storage_metrics assert isinstance(StorageMetrics)）。根因：get_stats() 契约 = None 或 StorageMetrics，extent 返回 dict（file/sim 均返回 None）。修复（仅 extent 后端，引擎核心零改动）：get_stats() → None；新增 stats_snapshot() 返回 io 计数 dict。测试：新增 test_get_stats_matches_engine_contract（bug regression，RED 确认 `{'opens': 1, ...} is not None` → 修复后 GREEN），6 处既有 get_stats() 调用点改 stats_snapshot()。本地+3090 均 67 tests OK。修复后 md5：extent_file_backend.py=7ab80c08…、test=0788ae97…（双侧一致，3090 /tmp/p2io-fix.tar.gz 留存）。

**extent 运行（3090 脱离自跑中）**：脚本 /root/p2io-extent-run.sh（启动引擎→health→采样器挂 scheduler PID→driver K=8→SIGTERM→完成标记）。引擎 healthy 于 18:48:48，driver 18:48:49 启动，证据 /root/evidence-p2io-extent-01/run-20260831-184849/。引擎日志 /root/engine-p2io-extent2.log；采样器 /root/p2io-extent-samples.jsonl（正确挂在 scheduler）；io 前后快照 /root/p2io-extent-io-{before,after}.txt。

## 3. evidence（真实命令与输出）

- 同步 md5：`MD5_ALL_MATCH`（8 文件双侧一致；修复后 2 文件再验一致）。
- 单测：`PYTHONPATH=python:test /root/miniconda3/envs/sglang-patch/bin/python -m unittest registered.unit.mem_cache.test_extent_file_backend_unit registered.unit.mem_cache.test_hicache_file_lru_unit` → `Ran 66/67 tests ... OK`（EXIT=0）。
- unified 门：`Ran 2288 tests in 46.8s / FAILED (errors=212, skipped=1149)`；A/B pre-sync `errors=202`；失败类 uniq：`112 FileNotFoundError: ninja`、`147/75/63/51/24 ValueError: Not enough host memory`、`6 cudaHostRegister rc=712`、`26 AssertionError`。
- file 运行归因：[P2A] `prefetch_io_finished` ×80、`restore_recompute` ×92（cause=miss 70 / timeout 22）、`restore_retry` ×171（capacity 134 / frontier 37）。
- get_stats 契约实证：本地 python 直测 syscr 计 read/pread64/readv/preadv（2002=2000+2）、syscw 计 write/writev/pwritev 但**不计 pwrite64**（1001=1000+1）。
- 崩溃证据：engine-p2io-extent.log tail：`AttributeError: 'dict' object has no attribute 'prefetch_stats'` → `ENGINE_EXIT=137`。
- RED 证据：`AssertionError: {'opens': 1, 'preads': 0, ...} is not None`（test_get_stats_matches_engine_contract，EXIT=1）；修复后 `Ran 67 tests in 0.878s OK`（本机）与 `Ran 67 tests in 0.891s OK`（3090）。
- file 引擎清理：ps 无 python3/sglang comm，GPU 15 MiB，`ENGINE_EXIT=0`。

## 4. summary

同步/单测/基线对照前段全部完成并有证据。M2 验证中发现并修复一个 M2 阻塞 bug（get_stats 契约违约导致 extent 引擎必崩），已按 TDD 完成（RED 证据→修复→双侧 GREEN）。file 基线 restore 病理实测：restore 请求 ttft p50=66.4s（含 60s 超时与 miss 回退 recompute 的混合），纯 IO 窗口 p50=25.4s；restore 归因 80 服务 vs 92 recompute——判据比较必须按"restore_served 的 IO 服务时间"对照，不能直接比含超时重算的 ttft。extent 实验正在 3090 脱离自跑（修复后首次运行）。

## 5. followups

1. extent 运行完成后按状态文件 §4 步骤分析并逐项裁决（判据：<1s / p50≤0.6s / open-read 数量级下降 / K=8 无 OOM/corruption）。
2. sha16 双侧（file vs extent 同 session/level/variant turn）交叉验证——corruption 检查（file 轮次证据已存）。
3. unified 门的 112 例 ninja 失败：sglang-patch env 缺 ninja（native_hash JIT 编译）——环境缺口，如需全绿待 devops 补装或授权。
4. extent 后端 get_stats 契约修复已同步 3090 但**尚未在本地仓库提交**（无 git 提交惯例——本任务不提交；但若后续拉新分支需重新应用，修复在两个文件：extent_file_backend.py + test_extent_file_backend_unit.py）。

## 6. open_issues

- file 基线采样器最初挂错进程（HTTP 主进程而非 scheduler），/root/p2io-file-samples.jsonl 的 syscall 形状数据无效；已用 scheduler 的 /proc/PID/io 精确计数（syscr/syscw）替代；extent 轮次采样器已正确挂 scheduler。
- /proc/PID/syscall 逐线程采样被引擎 dumpable=0 阻断（EPERM）——open/close 计数无法逐 syscall 采样，以 syscr/syscw + 文件数（348,535 .bin）+ extent fd 计数（预期 1 个持久 fd）构成如实证据链。
- extent 实验为修复后首跑，若脚本内 driver rc 非 0 或引擎再崩，证据在 /root/p2io-extent-run.log / engine-p2io-extent2.log，恢复后先读这两个文件。
