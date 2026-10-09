# phase2-hicache-design-coder-e6-01

- **工作标题：** phase2-hicache-design-coder-e6-01
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-coder-e6-01.md`：**
**done** — M1b + M2 按设计 §5/§6 落地，本机 torch-free 全绿（25/32/9），部署 3090
`/root/sglang-b1-continuity/` 双侧 md5 10 文件一致，远端真实 torch 回归 25/32/9 全绿，
远端 py_compile OK，引擎未启动（GPU 15 MiB 空闲、0 引擎进程——K=8 主判据归 tester）。
未 commit 未 push。RED→GREEN 已做（T10 突变 → 测试捕获 → 还原）。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-coder-e6-01.md`：**
M1b 把设计 §2.2 的 14 条转换实现为独立纯模块 `hicache_restore.py`（scheduler 冻结大类
不加状态逻辑，design O4），scheduler 侧只做"喂事件 + 执行决策"：issue 侧（T1-T5）、
准入侧（T6/T7 + WAIT skip）、drain 侧（T8-T10 经 rid-keyed terminal outcome 表）、
reconciliation（T11-T13）。M2 注册表 + 4 API 全 set 操作，唤醒钩挂在
`advance_storage_persisted` 之后，F2 exactly-once 语义零触碰（test_drain_reentry
9 测双端全绿 = 强制回归门）。T11 谓词用与准入同公式的共享纯函数（M1a helper 提取为
模块级 `device_charge`），容量侧故意不含 adder 运行余量 → 只可能更宽松，永不漏唤醒，
过早唤醒自愈。成功判据路径：C1/C2/C4 型 deny → WAIT → 每 pass 谓词/ACK 唤醒 →
RESTORING → READY → 准入消耗（K=8 recompute 1.87M→接近 0 归 tester 实测）。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-coder-e6-01.md`：1. 本机 py_compile（10 文件）：exit=0。
2. 本机 torch-free（各独立进程）：`test_hicache_restore.py` **25/25 OK**；
   `test_storage_regression.py` **32/32 OK**（既有 20 + 新增 12）；`test_drain_reentry.py` **9/9 OK**（既有 7 + 新增 2）。
3. **RED→GREEN**：把 `next_restore` 的 T10（REVOKED_TERMINATED）突变为
   `NONE/ADMIT_RECOMPUTE` → `test_t10_terminated_revoke_waits_for_prefetch_budget` 失败
   （`<RestoreState.NONE> is not <WAIT_CAPACITY>`）；还原后 25/25 全绿——测试确实守卫
   "容量性 revoke 进 WAIT、真 miss 才 RECOMPUTE"的核心语义。
4. 部署 3090 `root@175.155.64.171:24052` `/root/sglang-b1-continuity/`（scp 10 文件），
   双侧 md5 逐文件一致（部署中途 3 文件 scp 目标目录错误已用 mv 纠正并复验）：
   - hicache_restore.py `1e9f5f4214e3d1b06e67bdabe4bf5900`、schedule_batch.py…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-coder-e6-01.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-coder-e6-01.md`; SHA256 `b83da625c38b7b63d49b17013e185bc46311c1f6e25cfb1a899af9a630210085`; source state `tracked`
