# p2io-tester-e7e

- **工作标题：** p2io-tester-e7e
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-tester-e7e.md`：**
blocked — **引擎 41s 崩溃（AssertionError: node 66 not host-only），e15 引入的 eviction 回归**。硬门全部无法判定（运行未完成）。已定位精确根因 + 候选修复建议，交 coder。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/p2io-tester-e7e.md`：**
**e7e 无法判定任何硬门：e15 代码在 host-pressure 下 41s 崩溃。** 这是 e15 的确定回归（e7b/e14 同负载 583s 无崩溃；e7e/e15 崩）。正面信号：reserve 配置生效，Z3 从 59 降到崩溃前的 21（-64%），说明 writeback-reserve 方向有效——但降幅不足且间接引发了 forced_drop 与 drop_subtree 的 invariants 冲突。
诚实标注：仅 90s 崩溃前的观测，无法给出全链 survivability / full-prefix / ready_pool / 16-diff 细分等硬门数字。测试层面：现有单测（test_unified_radix_cache_unittest.py:7425）只覆盖 `drop_subtree_no_host` 单点 mock drain，**无 forced_drop + ancestor drop_subtree 交错的集成覆盖**——这是 coder 修复时应补的 RED 复现。

### 报告列出的产物/证据
- `phase2-hicache-design/work/p2io-tester-e7e.md`：- 远端运行：
  - `/root/p2io-m4t-e7e-run.sh`（new config: HICACHE_SIZE=8, reserve=1.5G, margin=0.3G）
  - `/root/launch-l3-3090.sh`（已注入两个新 flag；`.bak-e15run` 备份）
  - `/root/engine-p2io-m4t-e7e.log`（崩溃日志，1124 行）
  - `/root/p2io-m4t-e7e-{status,run}.log`、`evidence-p2io-extent-m4t-e7e/`（90/96 失败，elapsed=41s）
- 本地修复现场（未改，供 coder）：`python/sglang/srt/mem_cache/unified_radix_cache.py:891-913`（`_drop_device_leaf_to_miss`, e15 新增）、`.../unified_cache/unified_tree_core.py:1314-1357`（`drop_subtree_no_host` assert 1340）
- GPU 已归零（15 MiB），无孤儿进程，dmesg OOM=0

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-tester-e7e.md` → `.memory/phase2-hicache-design/work/p2io-tester-e7e.md`; SHA256 `3475ef2f035b5862bbc250871bde1297f0ddc6ce1136e9c86a111a43ce92d8f9`; source state `tracked`
