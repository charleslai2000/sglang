# WORKTREE-RETIRE-20260907

- **工作标题：** retire
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
退役精确指定的旧 linked worktree `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s`，先证明其中 dirty tracked/untracked handoff 内容在当前 clone 已有副本，再安全移除工作树而保留 branch ref。

## 实际改了什么
仅操作本地 Git/filesystem：确认旧 worktree 登记及 HEAD/branch 身份；逐项比较五个 dirty tracked paths 与四个 handoff，确认无旧有独占 nonignored files；检查无 process 使用目标路径。普通 `git worktree remove` 因 dirty 状态拒绝后，对获准的精确目标执行 `git worktree remove --force`。未删 branch、未用 `rm -rf`、未 prune，未碰当前 clone、其他 worktrees、远端或进程。

## 生成结果与验收
完成：目标目录及其 linked-worktree metadata 消失，worktree list 中目标移除、两个无关 worktree 仍登记；branch ref 和 commit `dac6db1ebabdb80209b757fd063cf53e05c091e7` 保留。当前 clone status 与移除前一致，所有九项 dirty/untracked 非忽略副本均可恢复；仅旧 worktree 的 ignored caches 一并移除。该结果仅描述 2026-09-07 本地操作。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `worktree-migration-20260907/work/retire.md` → `.memory/g3-worktree-migration/work/retire.md`; SHA256 `1939a0584b07020ae2ff3b8d640721e674c7a4894b6cb94bc3279fd7be1dca0d`; source state `local-only`
