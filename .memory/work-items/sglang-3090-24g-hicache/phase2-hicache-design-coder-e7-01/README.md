# phase2-hicache-design-coder-e7-01

- **工作标题：** phase2-hicache-design-coder-e7-01
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-coder-e7-01.md`：**
**done** — restore 状态机 capacity 死循环（tester e10 阻塞项）已修复：两重防御 + 超时统一兜底。
本机 py_compile OK + torch-free 35/34/9 全绿；部署 3090 双侧 md5 5 文件一致；远端真实 torch
35/34/9 全绿；引擎未启动（GPU 15 MiB、0 进程）。RED→GREEN 已做（3 处突变均被测试捕获）。
未 commit 未 push。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-coder-e7-01.md`：**
根因三层：短 prompt 被 T4 无条件接入 WAIT（入口误判）、T11 容量谓词对 REVALIDATE 恒真导致
per-pass 重发（错误唤醒）、state_ts 每次重入重弦导致 T13 永不触发（超时失效）。修复 = 入口
排除（`prompt_can_qualify_for_prefetch` 门 + has_restore_potential 修正，T4/T5/T6 三入口共用）+
唤醒切除（T11 只对谓词可验证的原因生效）+ 时钟保留（`wait_clock_next`，任何 WAIT 循环 ≤60s
有界退出）。HEALTH_CHECK 类短 prompt 现在全程不进状态机，直接正常路径；K=1 基线不再被循环
占满调度 pass。所有新语义均为纯函数/缓存方法，torch-free 全量可测。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-coder-e7-01.md`：1. 本机 `python3 -m py_compile`（5 文件）：`PY_COMPILE_OK`。
2. 本机 torch-free（Python 3.12，stubenv）：`test_hicache_restore.py` **35/35**（既有 25 + 新 10）、
   `test_storage_regression.py` **34/34**（既有 32 + 新 2）、`test_drain_reentry.py` **9/9**。
3. **RED→GREEN ×3**：① 注释掉 prompt 门 → `test_short_prompt_never_has_restore_potential`
   失败（`True is not false`）；② `wait_clock_next` 改回每次重弦 → `RestoreWaitClockTests`
   3 失败（`11.0 != 1.0`）；③ `capacity_wake_applies` 加入 REVALIDATE → 唤醒表测试失败。
   还原后全绿。
4. 部署 3090 `root@175.155.64.171:24052` `/root/sglang-b1-continuity/`（scp 5 文件，
   首传误放根目录已 mv 纠正），**双侧 md5 逐文件一致**：
   - hicache_restore.py `a5b39c10dba3c44d5a1d5598f04062bb`…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-coder-e7-01.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-coder-e7-01.md`; SHA256 `4cafa64b1b6d8de0c0da9753333ec2cea08877fa2a51e919a0fccff7f6cb893b`; source state `tracked`
