# p2io-coder-e9

- **工作标题：** p2io-coder-e9
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
按协调人 correction #3 修正 P2-IO R1/R2：用 durable/backup-target/requested 三 frontier 取代旧 span-overlap park；引入独立有界 DEMAND_RESTORE ticket，仅绕过 speculative PREFETCH_BUDGET，保留 DEVICE_QUOTA 语义。

## 实际改了什么
报告明确列出 5 个 SGLang/Python 实现文件与 4 个测试文件，涉及 `hicache_restore.py`、`unified_tree_core(.interface).py`、`unified_radix_cache.py`、`scheduler.py` 及 3090-dev restore/drain/feed/regression tests。实现 frontier 判定、wake、ticket 生命周期与 scheduler reissue 接线；未改 cache_controller、storage/backend/allocator。本 epoch 没有同步 3090 或做远端实测。

## 生成结果与验收
本机 RED→GREEN 证据显示 e8 surface 上 14 个新语义测试失败，修正版 counter-example 从错误 park 变为不 park；本机 104+64+29+7+94=298 tests 通过，9 个改动文件 py_compile 通过。一个预存 `test_unified_radix_cache_unittest` import/GPU mock failure 重现但非本轮引入。故本机单测验收通过，不代表 3090 runtime/performance 已验收；后续 orchestrator 仍需同步并按六项门槛实测。open issues 包括恢复锚 persisted-frontier 角落由 T13 兜底及预存失败待排期。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-coder-e9.md` → `.memory/phase2-hicache-design/work/p2io-coder-e9.md`; SHA256 `0c7dd81513f7e8f998801bf72dce1b6ddd1e1cb70a567da7a49c0d1a716c081c`; source state `tracked`
