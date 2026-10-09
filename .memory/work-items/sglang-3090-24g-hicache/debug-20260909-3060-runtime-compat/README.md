# DEBUG-20260909-3060-RUNTIME-COMPAT

- **工作标题：** DEBUG-20260909-3060-RUNTIME-COMPAT
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/DEBUG-20260909-3060-RUNTIME-COMPAT.md`：**
- Inspected source tree: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`, branch `3060-12g-qwen35-4b`, clean at `032bbe7e38f2b06c0efb01bdfb5baa79532974e3`.
- The 3060 branch is five SM86/AOT loader commits ahead of its parent `d49214e592` (`3090-24g-opt`); neither runtime blocker is in those five files. The help string and allocator are inherited from the frozen 3090 lineage. The recommended edits must be committed only on the 3060 branch.
- Prior operational evidence (`OPS-20260909-3060-RUNTIME-SMOKE-DEPS.md`): remote runtime is Python 3.11.11, `torch 2.5.1+cu124`, CUDA 12.4, RTX 3060 (SM86), TP=1; launch help fails with `TypeError: %o format: an integer is required, not dict`, and bounded startup fails before model load with an import error for `_cuda_beginAllocateCurrentThreadToPool`.
- Missing evidence: the remote full traceback and exact smoke command were not included in the prior report, and this task did not access the remote host. The source-level and isolated reproductions below establish both causes independently of that missing trace.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done (causal diagnosis only; no product, remote, 3090, ledger, context, or plan changes made).

没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。

### 报告列出的产物/证据
- `phase2-hicache-design/work/DEBUG-20260909-3060-RUNTIME-COMPAT.md`：- Prior runtime evidence: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS-20260909-3060-RUNTIME-SMOKE-DEPS.md`.
- Source evidence: `python/sglang/srt/server_args.py:2983-3002`, `python/sglang/srt/arg_groups/arg_utils.py:226-345`, `python/sglang/srt/distributed/device_communicators/pynccl_allocator.py:8-21,185-331`, `python/sglang/srt/distributed/parallel_state.py:413-459` in the inspected branch.
- Reproduction command and standard-library traceback are recorded in the Blocker A section above.…（节选；见来源报告）

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `d48095ba537`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/DEBUG-20260909-3060-RUNTIME-COMPAT.md` → `.memory/phase2-hicache-design/work/DEBUG-20260909-3060-RUNTIME-COMPAT.md`; SHA256 `97d8069c844dc80091d85f73acae2850a7f5be8fb5b318f54dda00da51338dd0`; source state `tracked`
