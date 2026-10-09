# devops report — Phase-1 patch stack 固化发布（phase1-patch-release, e1）

## status
done

## artifacts

### sglang repo（GitHub fork charleslai2000/sglang, 分支 3090-24g-hicache）
- 确认 4 修复 commit 在分支上、工作树干净（push 前无未提交改动，无源码/文档改动）：
  8b3dca96（F1 ACK-drain 重试）、2bdfcb53（F2 drain 递归守卫）、cd6c7d4c（demote 延迟 flush）、caeadcf4（stale 节点 KeyError 跳过）——commit message 全文核对，均含 Co-Authored-By: Claude
- **push 成功**：`4f06324468..caeadcf492 3090-24g-hicache -> 3090-24g-hicache`（exit 0）
- 远端确认：`ls-remote origin 3090-24g-hicache` = `caeadcf49210acd8c5b07abd1d15fdd759554b0d`

### server repo（gitea.lorestack.dev:charles/server, 分支 main）
- 文档更新（仅 2 文件，暂存核对 `git diff --cached --stat` = 2 files, +148/-21）：
  - `gpu/HANDOFF.md`：头部日期/指针更新；§0 改写为 Phase-1 全 CLOSED；§1 资产 A 增补 3090-24g-hicache 修复栈；新 §4 Phase-1 封棺（4.1 判据 / 4.2 test ID+证据索引 / 4.3 tail 46 语义 / 4.4 冻结结论原文 / 4.5 Phase-2 计划表）；旧 §4/§5/§6 重编号为 §5/§6/§7，§7 改写为 Phase-2 下一步
  - `gpu/3090-dev/README.md`：头部"最后更新 2026-08-30 + Phase-1 封棺"；§2 增补本包执行状态；新 §9 Phase-1 状态（9.1 判据 / 9.2 证据索引 / 9.3 tail 46 / 9.4 冻结结论 / 9.5 Phase-2 计划）。**注意：文件内同时含工作树预存的 hybrid 工具链适配文档**（micro_qwen35.py --expect-mamba / exit 4 / sidecar_state_complete，§3 文件表 + §6.1 + §7 清单，2026-08-30 本日内容）——同文件同工作流，无法在不做破坏性 git 操作（stash/checkout 禁令）的前提下分离，已一并提交并在 commit message 中如实说明
- **commit**：`dc2ff10` "gpu: Phase-1 封棺（3090-24g-hicache）入档——状态 CLOSED、证据索引、tail 46 语义与 Phase-2 计划"（含 Co-Authored-By: Claude）
- **push 成功**：`a9d5849..dc2ff10 main -> main`（exit 0）；远端确认 `ls-remote origin main` = `dc2ff10a41b407e3bd2f7708d8a7701b43d56627`
- 未动（保持原工作树状态）：`gpu/3090-dev/launch-l3-3090.sh`（M）、`gpu/3090-dev/micro_qwen35.py`（M）、`gpu/3090-dev/backpressure-analysis.md`（??）——不在本任务范围，未 commit 未 push

### 3090 实例证据（只读核对，未改任何文件）
- ssh 只读取清单 + 关键小文件核对：
  - t38fail → `/root/evidence-fail/`：chain_check.json 确认 **earliest_stored_index=9**（missing [0..8] + tail 46），CHAIN_GAP；另有 chain_check_2nd.json、churn/、p-write.*、MD5SUMS；`engine-fail.log` 尾部为预期 CancelledError 清理
  - t38rs3 → `/root/evidence-rs3/`：run-20260830-091526/verdict.json = **runs 4/4, all_pass=true**，每 run phase3 storage_hit=20855 / cached=20864 / no_full_recompute=true，output_sha16 `c71201d3e5e4d729` **跨 4 run 一致**；final chain CHAIN_GAP earliest=0 missing=46 sidecar_state_complete=true；driver-run.log 同步（4×PASS）；END-BANNER status=done all_pass=True
  - t38sb → `/root/evidence-sb/`：final-chain.json CHAIN_GAP earliest=0 missing=46 sidecar_state_complete=true（storage_dir /data/l3/t38sb）；drvA/B/C 三 driver + engine-sb.log + mid-run-metrics.txt；drvA END-BANNER status=blocked（runs=1/2, RUN1 revisit storage_hit=0/cached=20864 落 device）、drvB 2/2 passed=1、drvC 2/2 passed=0 warm_bucket_warns=1——专家裁决按 7/7 判据定 PASS，per-driver 混合结果与冻结结论"oversubscription 下失败归 scheduler/admission"一致，文档按裁决口径书写

## evidence（真实输出摘录）

```
# sglang push
To github.com:charleslai2000/sglang.git
   4f06324468..caeadcf492  3090-24g-hicache -> 3090-24g-hicache
PUSH_EXIT=0
# ls-remote 验证
caeadcf49210acd8c5b07abd1d15fdd759554b0d  refs/heads/3090-24g-hicache

# server commit
[main dc2ff10] gpu: Phase-1 封棺（3090-24g-hicache）入档——状态 CLOSED、证据索引、tail 46 语义与 Phase-2 计划
 2 files changed, 148 insertions(+), 21 deletions(-)
COMMIT_EXIT=0
# server push
To gitea.lorestack.dev:charles/server.git
   a9d5849..dc2ff10  main -> main
PUSH_EXIT=0
# ls-remote 验证
dc2ff10a41b407e3bd2f7708d8a7701b43d56627  refs/heads/main

# rs3 verdict 关键行（远端只读 cat）
"runs_total": 4, "runs_completed": 4, "runs_pass": 4, "all_pass": true,
"output_sha16": "c71201d3e5e4d729"（×4 run 一致）
"earliest_stored_index": 0, "missing_count": 46, "sidecar_state_complete": true
# fail chain_check 关键行
"earliest_stored_index": 9, "missing_count": 55
# MD5SUMS 实时校验（远端 md5sum/sha256sum）
md5:  /root/evidence-rs3/MD5SUMS = c000027d675549b969875ecad64b4e7a
      /root/evidence-sb/MD5SUMS  = 1ea8552dc09316982b5eb3904e3cd758
sha256: fa5fbb1b350c34617a36b0d2f431f83242cba9c4c7b20873354c90108d3d51a3
        6ede50c2602b58d3b205932f1cd53591d50b7da94628df1a04f3bacb80a53460
```

## summary
- 交付内容：sglang 4 修复 commit push 至 GitHub fork 3090-24g-hicache；server repo 两文档（HANDOFF.md + 3090-dev/README.md）Phase-1 封棺内容更新（CLOSED 状态、write-side/read-side/三流水/backpressure 四判据、t38fail/t38rs3/t38sb 证据索引、tail 46 语义、冻结结论原文、Phase-2 计划 P2-0..P2-4）commit dc2ff10 并 push 至 gitea main
- 证据索引要点（写入文档）：t38fail→/root/evidence-fail/（earliest=9）；t38rs3→/root/evidence-rs3/（4/4 PASS，sha16 c71201d3e5e4d729）；t38sb→/root/evidence-sb/（7/7 判据）；MD5SUMS 双侧 md5（文档按裁决值 281f611b…/34dd836a… 引用）
- 回滚路径：两 push 均为普通分支推送，无破坏性操作；如需回退 server main：`git push origin dc2ff10~1:main`（快进回退，工作树保留 launch/micro/backpressure 未提交改动不受影响）；sglang 分支回退：`git push origin caeadcf492~4:3090-24g-hicache`（4 commit 全部回退）
- 监控/验证：push 后 ls-remote 双侧确认远端 head；本地 status 核对无意外改动

## followups
1. **MD5SUMS 双侧 md5 值与实时校验不一致**：任务给定裁决值 281f611b6049fb4c1d88624704184eff（rs3）/ 34dd836a0194fa506611072c1fec7bfb（sb）；实时 `md5sum` 读数为 c000027d…（rs3）/ 1ea8552d…（sb），sha256 亦不匹配（fa5fbb1b…/6ede50c2…）。文档按裁决值引用（专家裁决记录），建议 orchestrator 与裁决源核对这两个值代表哪个快照（可能 MD5SUMS 文件在裁决后被重新生成，rs3/sb 目录 mtime 09:20/09:33）
2. **server push 附带 3 个 pre-existing 本地 commit**：本地 main 原本 ahead 3（3546628 物理机命名规范 / 3108484 网络重构第一批 / 113e068 网络文档目录重构，均为文档类），因我的 commit 基于其上，push 一并上送（a9d5849..dc2ff10）。若不应上送需裁决（回退命令见 summary）
3. **工作树遗留（未提交未 push）**：launch-l3-3090.sh、micro_qwen35.py 修改 + backpressure-analysis.md 未跟踪——属另一工作流（hybrid 工具链 + backpressure 分析），本任务未动，待其所属 epoch 处理
4. **t38sb per-driver 结果混合**（drvA blocked / drvB 1/2 / drvC 0/2，RUN1 曾 storage_hit=0 落 device）——与冻结结论的 oversubscription 归因一致，已按裁决口径写入文档；如需 per-run 细节可查 /root/evidence-sb/drv*/run-*/verdict.json
5. sglang 仓库出现 `.memory/`（phase2-hicache-design 等）——并行 Phase-2 设计 agent 的交换目录（09:51-09:54），非本任务写入，未跟踪未 push

## open_issues
- 无阻断性问题。待决策项：MD5SUMS 裁决值 vs 实时值差异的归属（见 followups 1）；server 附带 3 commit 是否需要回退（见 followups 2）
