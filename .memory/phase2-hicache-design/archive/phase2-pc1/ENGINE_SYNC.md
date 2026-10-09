# ENGINE_SYNC.md — Phase-2 production candidate 引擎同步与版本对应

本文件记录 tag `3090-hicache-phase2-pc1`（commit `9c9e7b7c7c`）对应的引擎部署
md5、备份名、同步方法，以及 Phase-2 五 commit 栈在 24052 实验机（RTX 3090 24G）
与本地 git 仓库之间的对应关系。

## 1. 核心对应：9c9e7b7c7c = 两个生产文件

Phase-2 production candidate（commit 9c9e7b7c7c）在生产路径上**只有两个文件**参与了
同步（`scp` → 24052 引擎 repo），全部其它生产文件（unified_radix_cache /
radix_cache / schedule_batch / ready_horizon / hicache_restore）未动。

| 文件 | 仓库路径（本地） | 24052 部署路径 | MD5（部署 == 9c9e7b7c7c blob） |
|---|---|---|---|
| scheduler.py | `python/sglang/srt/managers/scheduler.py` | `/root/sglang-b1-continuity/python/sglang/srt/managers/scheduler.py` | `495b88515cc2e932c57448359443604d` |
| test_hicache_restore_scheduler_feed.py | `3090-dev/test_hicache_restore_scheduler_feed.py` | `/root/sglang-b1-continuity/3090-dev/test_hicache_restore_scheduler_feed.py` | `465b6c68ce813b0522200ac96fea0828` |

- 关键方法（9c9e7b7c7c 引入）：`_miss_rearm_decision`（scheduler.py:3991）、
  `_miss_rearm_durable_coverage`（scheduler.py:4039，被 :4036 内部调用，调用点 :4849）。
  本归档对 commit blob 直接复核确认（行号 3991/4002/4036/4039/4849）。
- 备份 `.bak-round2-pre` 两份保留（== 920003bf07）：
  - scheduler `e1b749956459edb599ee956812334b40`
  - test `c94a55db82859913a8ff836f6c9a12dc`

## 2. 备份名与历史备份链（24052 /root/sglang-b1-continuity/）

| 备份目录 | 对应 commit | 内容 | 备份前部署 md5 |
|---|---|---|---|
| `.bak-p4-pre` | 0f8542c1a5 | scheduler + test 两份 | scheduler 12e10a79 / test 0ebc776b |
| `.bak-round2-pre` | 920003bf07 | scheduler + test 两份 | scheduler e1b74995 / test c94a55db |

> 备份为手工同步流程的一部分：同步前把当前部署文件复制为 `.bak-<阶段>-pre`，
> 核验 md5 == 上一 commit，再 scp 新两文件。全部备份保留不删。

## 3. 同步方法（手工，24052 非 git）

引擎 repo `/root/sglang-b1-continuity` 是 **editable install、非 git**，代码通过
手工 `scp` 从本地 git 仓库同步：

```bash
# 本地：从 commit 9c9e7b7c7c 导出两文件的 blob
git -C /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt show HEAD:python/sglang/srt/managers/scheduler.py > /tmp/scheduler-9c9e7b7c7c.py
git -C /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt show HEAD:3090-dev/test_hicache_restore_scheduler_feed.py > /tmp/test-schedfeed-9c9e7b7c7c.py

# 远程：先备份当前部署（.bak-round2-pre 模式），再 scp
ssh root@175.155.64.171 -p 24052 \
  'cp /root/sglang-b1-continuity/python/sglang/srt/managers/scheduler.py \
     /root/sglang-b1-continuity/.bak-round3-pre/ 2>/dev/null || mkdir -p ... '
scp -P 24052 /tmp/scheduler-9c9e7b7c7c.py root@175.155.64.171:/root/sglang-b1-continuity/python/sglang/srt/managers/scheduler.py
scp -P 24052 /tmp/test-schedfeed-9c9e7b7c7c.py root@175.155.64.171:/root/sglang-b1-continuity/3090-dev/test_hicache_restore_scheduler_feed.py

# 远程：复核部署 md5 == 期望
md5sum /root/sglang-b1-continuity/python/sglang/srt/managers/scheduler.py \
       /root/sglang-b1-continuity/3090-dev/test_hicache_restore_scheduler_feed.py
```

## 4. Phase-2 五 commit 栈（本地 git，分支 3090-24g-opt）

```text
9c9e7b7c7c  fix(hiscache): P4-round2 point-3 same-anchor miss re-arm requires durable material coverage   <- HEAD / tag 3090-hicache-phase2-pc1
920003bf07  fix(hiscache): P4 DEVICE_QUOTA capacity wake adds current-suffix gate
0f8542c1a5  fix(hiscache): P0 Q1 durable-ancestor no-material judgment + Q2 aligned-gate regression lock
183001f860  fix(hiscache): per-anchor L3 durability version + no-material fast-forward
3c71553a20  revert(hiscache): strip Fix B DEVICE_QUOTA timeout-count gate from production path
```

各 commit 影响的文件（`git show --stat --oneline`）：

| commit | 生产文件 | 测试文件 |
|---|---|---|
| 3c71553a20 (revert Fix B) | schedule_batch.py / scheduler.py / hicache_restore.py | test_hicache_restore.py / test_hicache_restore_scheduler_feed.py |
| 183001f860 (per-anchor L3 持久化版本) | schedule_batch.py / scheduler.py / hicache_restore.py | test_hicache_restore.py / test_hicache_restore_scheduler_feed.py / test_ready_horizon_unit.py / test_storage_regression.py |
| 0f8542c1a5 (P0 Q1/Q2) | scheduler.py / unified_radix_cache.py | test_hicache_restore_scheduler_feed.py / test_storage_regression.py |
| 920003bf07 (P4 current-suffix gate) | scheduler.py | test_hicache_restore_scheduler_feed.py |
| 9c9e7b7c7c (P4-round2 point-3 物材门) | scheduler.py | test_hicache_restore_scheduler_feed.py |

## 5. 部署状态（2026-09-07 soak-final 复核，均已核实）

- 机：175.155.64.171:24052（root），RTX 3090 24G（driver 580.173.02）。
- 引擎 repo：/root/sglang-b1-continuity（editable install，python 3.10.21
  env sglang-patch）。
- 部署 scheduler.py md5 = `495b88515cc2e932c57448359443604d`；
  test md5 = `465b6c68ce813b0522200ac96fea0828` —— 与本归档 launcher 中
  期望值逐字节一致。
- 备份 `.bak-round2-pre` 保留（scheduler e1b74995 / test c94a55db）。
- 其余生产文件未动；未动 22151。

## 6. 注意

- 24052 引擎为**非 git 手工同步**部署：任何一位工程师后续手动改过 /root 下
  scheduler.py，部署就不再等于 tag。启动实验前按 TEST（launcher 的 md5 预检）
  复核。
- 本归档为**实验环境复现**，非生产。生产部署见
  `.memory/phase2-hicache-design/work/phase2-hicache-design-devops-prod-deploy-22151-e1.md`
  的对应流程。