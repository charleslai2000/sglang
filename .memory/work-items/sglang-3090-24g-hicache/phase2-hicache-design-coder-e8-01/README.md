# phase2-hicache-design-coder-e8-01

- **工作标题：** phase2-hicache-design-coder-e8-01
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-coder-e8-01.md`：**
**done** — M2 wake 链双断点已修复（写触发缺失 + T11 提前唤醒），torch-free 全绿
（35/36/12，含新增 5 测 + RED→GREEN 突变验证 ×2）；部署 3090 双侧 md5 4 文件一致；
远端真实 torch（2.13.0+cu130）35/36/12 全绿；引擎未启动（GPU 15 MiB、0 进程）。
未 commit 未 push。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-coder-e8-01.md`：**
M2 wake=0 是双断点而非单点：write_back 模式下无人推进 L3 frontier（等待永远等不来），
且 T11 容量谓词用 is_backuped（D->H 提交即真）比 L3 就绪早数十秒——wait 被提前唤醒
丢弃、重发打进空 L3 变 miss→recompute，等真 ACK 到达时 waiter 已注销。修复 =
① 注册即触发 anchor 链 gap-fill 写（等待本身推进 frontier，设计前提"写在途"变真）；
② T11 谓词与 ACK 同条件（storage_persisted / deleted / root，刻意排除 is_backuped）。
两处都是最小语义改动，全部逻辑落在 cache 层可 torch-free 测试。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-coder-e8-01.md`：1. 本机 `python3 -m py_compile`（4 文件）：`PY_COMPILE_OK`。
2. 本机 torch-free：`test_hicache_restore.py` **35/35**、`test_storage_regression.py`
   **36/36**（既有 34 + 新 2）、`test_drain_reentry.py` **12/12**（既有 9 + 新 3）。
3. **RED→GREEN ×2（突变验证）**：① `frontier_anchor_ready` 改回 is_backuped →
   `test_frontier_anchor_ready_requires_persisted` 失败（`True is not false`）；
   ② 删掉注册触发 → `test_register_trigger_persists_anchor_chain` 失败；还原后全绿。
4. 部署 3090 `root@175.155.64.171:24052` `/root/sglang-b1-continuity/`（scp 4 文件，
   误放根目录已 mv 纠正），**双侧 md5 逐文件一致**：
   - unified_radix_cache.py `5f07791c343e6e11e67ea78542e6df86`
   - scheduler.py `2bb64a91641c1133910dd4c3e14f04cf`…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-coder-e8-01.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-coder-e8-01.md`; SHA256 `db220e9c05c52068387a72a91f5826e1458ef321a311b638b9ce22f06738b26b`; source state `tracked`
