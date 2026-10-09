# phase2-hicache-design-coder-e9-01 — P2-1 残余 bug 修复：restore 状态机 60s 时钟未随 wake 复位

## status

**done** — wake 后 too_short 分支 60s 空等已修复：T4 转换表补"重发腿（RESTORING）上
too_short = 终态判定 → 立即放行 recompute"（同 T9 miss 语义），wait_clock_next 单一上弦
防御未动。本机 py_compile OK + torch-free 40/36/12 全绿（新增 5 测，RED→GREEN 已做）；
部署 3090 双侧 md5 3 文件一致；远端真实 torch（2.13.0+cu130）40/36/12 全绿；
引擎未启动（双侧 0 进程、GPU 15 MiB）。未 commit 未 push。

## 根因（file:line）

**`python/sglang/srt/managers/scheduler_components/hicache_restore.py:103-105`（旧
DENIED_SHORT 行无条件返 WAIT_CAPACITY）**——wake（T12 FRONTIER_READY / T11 CAPACITY_FITS）
消费后 `_prefetch_kvcache` 重发（scheduler.py:3028 / 3069 新行号），若被
`declined_too_short` 拒绝（t5 现场 requested=46 < prefetch_threshold）则喂 DENIED_SHORT →
`next_restore(RESTORING, DENIED_SHORT)` → 无条件重进 WAIT[REVALIDATE]，而
`wait_clock_next`（hicache_restore.py:190-191）对 WAIT 重入**保留首次上弦的 state_ts**
（死循环修复的正确防御）→ T13 判定 `now - state_ts > 60`（scheduler.py:3036 旧行号）
继续用 17:34:31 的旧基准 → **17:35:31 才放行**。对照 t2：wake 重发 → L3 空 → REVOKED_MISS
genuine → NONE/ADMIT_RECOMPUTE 立即放行（T9 行无条件清状态）——**两分支差异 =
DENIED_SHORT 无 RESTORING 终态行**。

语义判定：wake 表明状态已变化（frontier 就绪），重发腿上的 too_short 是**终态重判定**
（suffix 仍 < 阈值，无恢复收益），与 miss 同为终态；重进 REVALIDATE 只会空等旧 T13 时钟。
设计文档 p2-1-design.md §2.2 T4 行仅定义 NONE→WAIT[REVALIDATE]（首次拒绝 + device 匹配
衰减兜底），未定义重发腿行为——本次按 e12 证据定稿。

## 修复清单（2 源 + 1 测 + 设计文档一致性）

| 文件:行 | 改动 | 语义 |
|---|---|---|
| `scheduler_components/hicache_restore.py:103-117` | DENIED_SHORT 行：`state is RESTORING` → `(NONE, ADMIT_RECOMPUTE)`；其余（NONE 首次/WAIT 重拒）保持 `(WAIT, WAIT)` | wake 重发腿 too_short = 终态（同 T9 miss）；REVALIDATE 首次等待与 paced-retry 重验证循环不变；模块 docstring 同步 |
| `managers/scheduler.py:3029-3037`（T12 腿）| wake 重发后 `state is NONE` → 日志 `evt=restore_recompute cause=too_short` | 放行观测（state NONE ⇔ DENIED_SHORT 终态行唯一入口）；证据可归因 |
| `managers/scheduler.py:3070-3082`（T11 腿）| 同上（capacity wake 腿） | 同 T12 规则，日志统一 cause=too_short |
| `3090-dev/test_hicache_restore.py`（+5 测）| `test_wake_reissue_too_short_degrades_to_recompute` / `test_capacity_wake_reissue_too_short_degrades_to_recompute` / `test_frontier_wake_miss_degrades_to_recompute`（钉住 wake→miss 既有行为）/ `test_t4_too_short_redecline_from_wait_stays_waiting`（钉住死循环防御）/ `test_clock_cleared_on_wake_too_short_terminal`（时钟复位回归） | 见 evidence RED |
| `p2-1-design.md`（服务器侧，3 处）| §2.2 T4 行、§2.5-2 表加"wake 重发腿 too_short = 终态重判定"行、§3.2 消费语义补该分支 | 转换表设计文档一致性（代码先行改文档，按 coder 纪律补） |

**未动**：`wait_clock_next`（单一上弦防御原样）、unified_radix_cache.py、cache_controller、
hiradix_cache、hybrid_cache_controller、schedule_policy。

## evidence

1. **RED→GREEN**：先加 5 测 → `python3 3090-dev/test_hicache_restore.py` 输出
   `FAILED (failures=3)`（wake/capacity wake→too_short + 时钟终结链，`WAIT_CAPACITY is not
   NONE`）；修 T4 行后 `Ran 40 tests ... OK`。
2. 本机 `python3 -m py_compile`（3 文件）：`PY_COMPILE_OK`。
3. 本机 torch-free：`test_hicache_restore.py` **40/40**（既有 35 + 新 5）、
   `test_storage_regression.py` **36/36**、`test_drain_reentry.py` **12/12** 全绿。
4. 部署 3090 `root@175.155.64.171:24052` `/root/sglang-b1-continuity/`，**双侧 md5 逐文件一致**：
   - hicache_restore.py `2bc86bbdcdbbe39f8e51022e495b05bf`
   - scheduler.py `f58517a3f836f170cbd8bca416bd462c`
   - test_hicache_restore.py `5c3fea5834a5e5852c78ce726c82c302`
5. 远端 `/root/miniconda3/envs/sglang-patch/bin/python -m py_compile`（Python 3.10.21）：
   `REMOTE_PY_COMPILE_OK`；torch `2.13.0+cu130` 真实回归 40/36/12 全绿。
6. 引擎未启动：双侧 `ps -eo cmd | grep -E 'python.*(launch_server|sglang)'` 均 0 命中
   （此前 pgrep 命中为 bash 包装自身，与 tester e12 同现象，已用不含自匹配方式复核）；
   `nvidia-smi` memory.used = 15 MiB。
7. git 审查：本 epoch 改动 = 上述 3 文件 + 服务器侧设计文档；未 commit 未 push。

## summary

根因 = T4 转换表无条件重进 WAIT[REVALIDATE]，而时钟保留防御（wait_clock_next 单一上弦）
使该重进继续用首次上弦的 state_ts → wake 后 too_short 请求空等满 60s 才被 T13 放行
（K=1 220s、K=8 p95 67.6s 的机制）。修复 = DENIED_SHORT 在重发腿（RESTORING，即
T11/T12 wake 重发）上按终态处理（NONE + ADMIT_RECOMPUTE，同 T9 genuine miss），
fresh 首次拒绝（NONE→WAIT[REVALIDATE]）与 paced-retry 重拒（WAIT→WAIT）语义不变——
死循环修复防御零改动。预期：K=1 restore turn 61s → 即时，K=1 回 ~20-55s，K=8 p95 回
~53s，`restore_recompute cause=timeout` 趋 0、新增 cause=too_short 可见于 state-machine.txt。

## followups

- tester 复测（e13）：K=1 应回 ~20-55s（无 61s restore turn）；engine log 中
  `evt=restore_recompute cause=too_short` 应取代 t5 型 60s 空等；K=8 p95 应回 ~53s；
  cause=timeout 应趋 0。
- 集成验证点：同链条件对照（复用 0c 链）跑 K=8 以消除 1d"链量少"干扰（tester e12
  open_issues 1）；CHAIN_GAP 语义补测（链外直读 L3）。

## open_issues

- REVALIDATE 首次等待（T4 fresh）在 interval=0 下仍只能走 T13 60s 超时——e7 待裁决项
  （"60s 超时等待 vs 立即重算"）本次仅对重发腿定稿为立即重算；fresh 首次拒绝保留等待
  （device 匹配衰减兜底），若后续实测 fresh 型也出现 60s 延迟影响 turns/s，可复用本
  次终态行语义或缩短 REVALIDATE 超时（本次未动，避免范围外改动）。
- e12 open_issues 其余项（restore_loadback_fail 4 次归因、wait abort 计数）未触碰。
