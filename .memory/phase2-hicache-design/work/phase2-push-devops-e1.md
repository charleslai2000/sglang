# phase2-push-devops-e1 — Push Phase-2 状态机修复 commit 栈至远端

- epoch: e1
- agent: devops-executor
- repo: /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt
- branch: 3090-24g-opt
- date: 2026-09-07

## status: done

Push 已成功完成并通过全项验证（含 rev-parse 对照）。全程无 force push、无历史改写、无分支意外创建。

## 任务核对（步骤 1）

| 检查项 | 结果 |
|---|---|
| 工作树 | 干净；唯一未跟踪文件 `?? 3090-dev/test_p3_warmtree_hol.py`（dispatch 声明不 push，保持未动） |
| HEAD | `9c9e7b7c7c` = `9c9e7b7c7cfdf2ef2b0100662513361c1e17a013` ✓ 与 dispatch 一致 |
| 远端 | origin = git@github.com:charleslai2000/sglang.git（pushes installed）；upstream = git@github.com:sgl-project/sglang.git |
| 分支 | 本地 `3090-24g-opt` 当前分支，push 前无上游（branch -vv 无 [origin/...] 标注） |

## 远端核对（步骤 2，关键）

- `git fetch origin` exit 0。
- **`origin/3090-24g-opt` 不存在**（`git show-ref origin/3090-24g-opt` exit 1）→ 该分支首次推送（新建分支路径，非 force）。
- `git log --oneline HEAD..origin/HEAD` **为空**（exit 0）→ 本地不含未知远端默认分支的 commit，无分叉。
- `git merge-base HEAD origin/HEAD` = `54c394a2e1712a657d7282cb2d7f4e95feb632f3`（= origin 默认分支 tip）→ 8 个 commit 严格线性叠加于 fork 共享历史上。
- 结论：非 fast-forward 分叉 / 本地未知 commit 情形均不存在，可安全普通 push。

## Push（步骤 3）

- 命令：`git -C ... push -u origin 3090-24g-opt`
  （`-u` 仅设置上游跟踪；**非 force**；`--force` / `--force-with-lease` / `-f` 全程零使用）
- 输出摘要：`* [new branch] 3090-24g-opt -> 3090-24g-opt`；`branch '3090-24g-opt' set up to track 'origin/3090-24g-opt'`；GitHub 提示可创建 PR。exit 0。
- 远端路径：`git@github.com:charleslai2000/sglang.git`（remote URL 保持干净，未改 .git/config）。

## 验证（步骤 4 / Acceptance）

- `git -C ... rev-parse HEAD` = `git -C ... rev-parse origin/3090-24g-opt` = `9c9e7b7c7cfdf2ef2b0100662513361c1e17a013` ✓（远端 ref == 本地 HEAD）
- `git log --oneline origin/3090-24g-opt..HEAD` 为空（0 个待 push commit）✓
- 最新 commit == `9c9e7b7c7c` ✓
- push 后工作树状态与 push 前一致：仅 `?? 3090-dev/test_p3_warmtree_hol.py`。

## 推送的 commit 清单（`54c394a2..origin/3090-24g-opt`，共 24 个）

```
9c9e7b7c7c fix(hiscache): P4-round2 point-3 same-anchor miss re-arm requires durable material coverage
920003bf07 fix(hiscache): P4 DEVICE_QUOTA capacity wake adds current-suffix gate
0f8542c1a5 fix(hiscache): P0 Q1 durable-ancestor no-material judgment + Q2 aligned-gate regression lock
183001f860 fix(hiscache): per-anchor L3 durability version + no-material fast-forward
3c71553a20 revert(hiscache): strip Fix B DEVICE_QUOTA timeout-count gate from production path
30a5a3698a fix(hiscache): P3 deferred-ACK reconciliation for frontier HOL
7155cd8973 fix(hiscache): too_short recompute churn gate for permanent sub-threshold residues
74246bb90f fix(hiscache): P1 sticky MISS_RECOMPUTE restores eligibility re-arm gate
cc718c3c2e fix(hiscache): guard storage-gap D->H backup on device value presence
3bca0989f4 fix(hiscache): bound DEVICE_QUOTA wait with forward-progress degradation
e0e83b11a1 fix(hiscache): NO_HEADROOM waiter wakes on release epoch, not level
036fb89451 fix(hiscache): meter single-key extent set() like the batch paths
fac8ccb4cf chore(3090-dev): commit experiment scripts as baseline assets (p2io probes, evidence, README)
202a37eba4 fix: freeze 3090-24g-hicache stable baseline (2026-09-04)
e281df3635 feat: P2-IO extent-based L3 storage backend
f3fffa7f09 fix: P2-1 restore retry + frontier wake for L3 (HiCache)
caeadcf492 fix: skip stale L3 persists for deleted nodes
cd6c7d4c27 fix: defer persist flush past demote in write-back evict
2bdfcb5327 fix: defer L3 persists out of the ack drain (drain recursion)
8b3dca9674 b1-f1: backup 失败后 drain ACK 重试 evict_host 一次（F1）
4f06324468 b1-continuity: write_back 补链写 L3，保证 anchor→leaf 连续覆盖（T38c）
```

dispatch 标记的 5 个 Phase-2 状态机修复 commit（3c71553a20、183001f860、0f8542c1a5、920003bf07、9c9e7b7c7c）以及更早的 P0/P1/too_short/Fix A/P3 修复 commit 全部在内、顺序正确。

## evidence

- 只读核实命令：`git status --short` / `git log --oneline -15` / `git branch -vv` / `git remote -v` / `git show-ref origin/3090-24g-opt` / `git log --oneline HEAD..origin/HEAD` / `git merge-base HEAD origin/HEAD`
- push 命令：`git -C /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt push -u origin 3090-24g-opt`（exit 0）
- 验证命令：`git rev-parse HEAD` 与 `git rev-parse origin/3090-24g-opt`（均 `9c9e7b7c7cfdf2ef2b0100662513361c1e17a013`）
- material_exit_status：全部退出码 0

## followups

- 可选（非阻塞）：如需提 PR，GitHub 提示 `https://github.com/charleslai2000/sglang/pull/new/3090-24g-opt`；不在本 dispatch scope 内，未执行。

## open_issues

- 无。Gitea 环境规则与 50-forbidden 5.1 均已对照检查：本任务未产生任何 force push 变体。

---

# 追加：production-candidate tag（同一收口指令序列第 2 步，phase2-tag，2026-09-07）

## status: done

在 commit 9c9e7b7c7c 打 annotated tag `3090-hicache-phase2-pc1` 并推送远端成功。零 force、零历史改写、不动其他 tag/分支。

## 核实（步骤 1，全部通过）

| 检查项 | 结果 |
|---|---|
| `git rev-parse HEAD` | `9c9e7b7c7cfdf2ef2b0100662513361c1e17a013` ✓（仍在刚 push 的 commit） |
| `git tag -l '3090-hicache-phase2-pc1'` | 空（本地无同名 tag）✓ |
| `git ls-remote --tags origin '3090-hicache-phase2-pc1'` | 空（远端无同名 tag）✓ |

## 打 tag（步骤 2）

- 命令：`git -C ... tag -a 3090-hicache-phase2-pc1 9c9e7b7c7c -m "Phase-2 production candidate: HOL/miss/too_short state-machine long-tail closed; 2h L3 ON soak 7/7 PASS (commit 9c9e7b7c7c)"`，exit 0。
- 类型确认：`git cat-file -t 1bb8dc86...` = `tag`（annotated）。

## push tag（步骤 3）

- 命令：`git -C ... push origin 3090-hicache-phase2-pc1`（普通 push，禁 force），exit 0。
- 输出：`* [new tag] 3090-hicache-phase2-pc1 -> 3090-hicache-phase2-pc1`。
- 远端路径：`git@github.com:charleslai2000/sglang.git`（URL 未动）。

## 验证（步骤 4）

- `git ls-remote --tags --exit-code origin '3090-hicache-phase2-pc1'` → `1bb8dc8674da36a18e97675f872954f535aa2f7e  refs/tags/3090-hicache-phase2-pc1`（exit 0，远端 tag 存在）✓
- 本地 `git rev-parse 'refs/tags/3090-hicache-phase2-pc1'` = `1bb8dc8674da36a18e97675f872954f535aa2f7e` == 远端 tag 对象 SHA（同 tag 对象）✓
- `git rev-parse '3090-hicache-phase2-pc1^{commit}'` = `9c9e7b7c7cfdf2ef2b0100662513361c1e17a013` == HEAD == 刚 push 的 commit ✓
- 结论：远端 tag 指向 commit 9c9e7b7c7c 的 annotated tag，完全满足 dispatch 步骤 4。

## tag 相关 evidence

- 核实：`rev-parse HEAD` / `tag -l` / `ls-remote --tags`
- push：`git -C /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt push origin 3090-hicache-phase2-pc1`（exit 0）
- 验证：`ls-remote --tags --exit-code` / `rev-parse refs/tags/...` / `rev-parse '...^{commit}'` / `cat-file -t`
- material_exit_status：全部 exit 0

## open_issues（tag 步骤）

- 无。force push 变体全程零使用。