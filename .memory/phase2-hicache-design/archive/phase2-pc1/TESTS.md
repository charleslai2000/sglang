# TESTS.md — Phase-2 candidate 测试套件（5 目标）与运行方法

本文件列出 tag `3090-hicache-phase2-pc1`（commit 9c9e7b7c7c）对应的 5 个目标测试
套件、md5、运行命令与基线结果。基线数字来自 round2/peranchor/P4 tester 在 24052
实测（见 `.memory/phase2-hicache-design/work/phase2-round2-tester-e1.md` §1、
`phase2-peranchor-tester-e1.md` §0）。

## 1. 5 目标套件（本地仓库 3090-dev/，24052 /root/sglang-b1-continuity/3090-dev/）

| 套件文件 | 本地 HEAD md5 | 24052 部署 md5 | round2 基线 |
|---|---|---|---|
| test_hicache_restore.py | `56f95383189dfca62e98cc4eb18ae0ba` | 同 | ✓ |
| test_hicache_restore_scheduler_feed.py | `465b6c68ce813b0522200ac96fea0828` | 同 | ✓ |
| test_p3_warmtree_hol.py | `b1d61fda70e1e0fb1bdb375cb9ea6d52` | 同 | ✓ |
| test_ready_horizon_unit.py | `b6e652764af3f94a9aa77fa73f1589b1` | 同 | ✓ |
| test_storage_regression.py | `500609d273a08030ab1f7dff7a8b6ced` | 同 | ✓ |

- 本地 3 个（test_hicache_restore_scheduler_feed / test_ready_horizon_unit /
  test_storage_regression）为 git 跟踪；test_p3_warmtree_hol.py 为**未跟踪**工作树
  文件（push 报告明确声明，不 push），部署以 md5 为准。
- 全部 5 文件本地工作树 md5 == 24052 部署 md5（本次归档全新复核，见 §3）。

## 2. 运行命令（24052，root，sglang-patch env）

```bash
# 引擎 repo 根下（editable install：PYTHONPATH=python 允许仓库树覆盖 site-packages）
cd /root/sglang-b1-continuity

# 单套件
PYTHONPATH=python /root/miniconda3/envs/sglang-patch/bin/python -m pytest 3090-dev/test_hicache_restore.py

# 5 目标套件全跑（round2 基线：323 passed）
PYTHONPATH=python /root/miniconda3/envs/sglang-patch/bin/python -m pytest \
  3090-dev/test_hicache_restore.py \
  3090-dev/test_hicache_restore_scheduler_feed.py \
  3090-dev/test_p3_warmtree_hol.py \
  3090-dev/test_ready_horizon_unit.py \
  3090-dev/test_storage_regression.py
```

环境前置（deep_ep 集合通过 find_cuda_home 需要 nvcc）：

```bash
export CUDA_HOME=/root/miniconda3
export PATH=/root/miniconda3/bin:$PATH
```

> 注：24052 的 sglang-patch env 有 pytest 9.1.1；本地 sglang-venv 无 pytest，
> 本地以 unittest 等价驱动（`python -m unittest 3090-dev.test_hicache_restore`）。
> 本归档的 `323 passed` / `314 / 300 passed` 基线均来自 24052 pytest 口径。

## 3. 基线结果（24052 实测，逐轮）

| 轮次 | commit | 5 目标套件 | test_drain_reentry | 来源 |
|---|---|---|---|---|
| peranchor | 183001f860 | 300 passed | 5 failed / 25 passed（BASE mock） | peranchor-tester-e1 §0 |
| P4 | 920003bf07 | 314 passed | 5 failed（BASE mock） | date P4-tester-e1 §1 |
| round2 | 9c9e7b7c7c | **323 passed**（基线 314→323，净 +9 为新增用例） | 5 failed（BASE mock） | round2-tester-e1 §1 |

- **323 passed 为 production candidate 基线**（round2 全量复核，与 coder 报告一致）。
- 本地 coder 侧全 3090-dev/ 复测口径：429 passed / 5 failed（test_drain_reentry）。

## 4. test_drain_reentry 5 failed — BASE 预存在 mock 缺陷（非本次改动）

- 现象：test_drain_reentry.py 5 failed、25 passed。
- 根因：`unified_radix_cache.py:2241` 的 `_FakeTreeCore` mock 缺
  `get_component_device_value` 方法（AttributeError），是 BASE 预存在 mock 缺陷，
  与 Phase-2 任何 commit 无关（多轮复核：peranchor / P4 / round2 全部一致,
  failure mode 全部是 AttributeError）。
- 处置：不阻塞 production candidate 判定；test_drain_reentry 不进 5 目标套件清单。

## 5. 套件内容说明（Appx 便于复现对照）

- test_hicache_restore.py —— L3 restore 主路径测试
- test_hicache_restore_scheduler_feed.py —— scheduler 状态机 feed（9c9e7b7c7c
  的生产改动所在文件）
- test_p3_warmtree_hol.py —— P3 warm-tree HOL 测试（未跟踪工作树文件）
- test_ready_horizon_unit.py —— Ready Horizon 状态机单测
- test_storage_regression.py —— storage 回归测试

全部为 unittest.TestCase 风格，pytest 可直接收集。