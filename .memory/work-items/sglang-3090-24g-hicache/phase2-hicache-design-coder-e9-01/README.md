# phase2-hicache-design-coder-e9-01

- **工作标题：** phase2-hicache-design-coder-e9-01
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-coder-e9-01.md`：**
**done** — wake 后 too_short 分支 60s 空等已修复：T4 转换表补"重发腿（RESTORING）上
too_short = 终态判定 → 立即放行 recompute"（同 T9 miss 语义），wait_clock_next 单一上弦
防御未动。本机 py_compile OK + torch-free 40/36/12 全绿（新增 5 测，RED→GREEN 已做）；
部署 3090 双侧 md5 3 文件一致；远端真实 torch（2.13.0+cu130）40/36/12 全绿；
引擎未启动（双侧 0 进程、GPU 15 MiB）。未 commit 未 push。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-coder-e9-01.md`：**
根因 = T4 转换表无条件重进 WAIT[REVALIDATE]，而时钟保留防御（wait_clock_next 单一上弦）
使该重进继续用首次上弦的 state_ts → wake 后 too_short 请求空等满 60s 才被 T13 放行
（K=1 220s、K=8 p95 67.6s 的机制）。修复 = DENIED_SHORT 在重发腿（RESTORING，即
T11/T12 wake 重发）上按终态处理（NONE + ADMIT_RECOMPUTE，同 T9 genuine miss），
fresh 首次拒绝（NONE→WAIT[REVALIDATE]）与 paced-retry 重拒（WAIT→WAIT）语义不变——
死循环修复防御零改动。预期：K=1 restore turn 61s → 即时，K=1 回 ~20-55s，K=8 p95 回
~53s，`restore_recompute cause=timeout` 趋 0、新增 cause=too_short 可见于 state-machine.txt。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-coder-e9-01.md`：1. **RED→GREEN**：先加 5 测 → `python3 3090-dev/test_hicache_restore.py` 输出
   `FAILED (failures=3)`（wake/capacity wake→too_short + 时钟终结链，`WAIT_CAPACITY is not
   NONE`）；修 T4 行后 `Ran 40 tests ... OK`。
2. 本机 `python3 -m py_compile`（3 文件）：`PY_COMPILE_OK`。
3. 本机 torch-free：`test_hicache_restore.py` **40/40**（既有 35 + 新 5）、
   `test_storage_regression.py` **36/36**、`test_drain_reentry.py` **12/12** 全绿。
4. 部署 3090 `root@175.155.64.171:24052` `/root/sglang-b1-continuity/`，**双侧 md5 逐文件一致**：
   - hicache_restore.py `2bc86bbdcdbbe39f8e51022e495b05bf`
   - scheduler.py `f58517a3f836f170cbd8bca416bd462c`
   - test_hicache_restore.py `5c3fea5834a5e5852c78ce726c82c302`…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-coder-e9-01.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-coder-e9-01.md`; SHA256 `3334167bb037a2205c511da10a66abc5474a88069ddd9924d263f8fe5cab03ac`; source state `tracked`
