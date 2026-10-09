# P0-B-FOCUSED-RERUN-20260911-R42

- **工作标题：** P0-B-FOCUSED-RERUN-20260911-R42
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P0-B-FOCUSED-RERUN-20260911-R42.md`：**
- Task ID: `P0-B-FOCUSED-RERUN-20260911-R42`
- Invocation: `ses-p0b-focused-r42-20260911`
- Epoch: `2026-09-11`
- Status: execution completed; results classified only (no P0-B pass/live-chain claim).
- Target: `root@i-1.gpushare.com:27460`, RTX 3060, SSH key `/home/dev-codex/.ssh/sglang_3060_ed25519`
- Checkout: `/root/sglang-3060-12g-hicache`
- Python: `/root/sglang-env-3060-4b/bin/python`
- Backup directory: `/root/p0b-focused-r42-backup-20260911` (outside checkout)

## 实际改了什么
在授权 RTX 3060 依赖齐备环境备份并 hash-verify 6 份测试文件，按原序执行六个 pytest suites；未安装依赖或改产品代码。

## 生成结果与验收
六项测试结果：HOST_ALLOC 9 项中 6 pass/3 fail；drain reentry 31 项中 25 pass/6 fail（失败均为缺 `_t38c_node_context_index`）；storage regression 126/126 pass；restore scheduler feed 46/46 pass；restore selection 92/92 pass（非空）；ready partition 18/18 pass。执行结束但不是 P0-B pass/live-chain evidence；失败分类保留，不推广至产品结论。远端备份保留，无需 rollback。

报告已列明各 suite 计数及限制；该 focused run 不代表 live P0-B acceptance。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-B-FOCUSED-RERUN-20260911-R42.md` → `.memory/rh-p0b-harness-durability/P0-B-FOCUSED-RERUN-20260911-R42.md`; SHA256 `f456aeabf2145a3a68b3fcbaec06efcafb087c7979e961c1d5846057d612ac4c`; source state `tracked`
