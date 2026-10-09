# SGLang work archive index

本目录是 `/home/dev-codex/workspaces/3rdparty/` 下 `sglang*` 仓库历史工作记录的**导航索引**。目标是在多个分支、worktree 和实验项目并行、记录分散的情况下，能按目的、仓库/分支/commit、代码位置、阶段和证据快速找到原始材料。

## 重要约定

- 这是索引/导航，不是新的事实权威，也不替代各项目的原始 ledger、handoff、review、gate 或运行证据。
- 原始文档留在来源仓库；此处主要记录相对路径和主题导航，不搬运大包、raw telemetry、日志、模型数据或可能含敏感信息的材料。
- 每个记录的 Git 身份必须包含来源仓库、分支、完整 commit SHA、路径和跟踪状态。HEAD 会随仓库变化；本索引生成时的快照见 `REPOS.md`。
- 原始文档中的分支/HEAD/状态可能是历史 epoch 值。不能仅凭文档名或其陈述认定事实；核对时查看记录引用的代码、commit 和证据，并标明 `FACT / CLAIM / OPEN / SUPERSEDED`。
- `3rdparty` 子仓库的 `.memory/` 不会由本索引复制到当前仓。新增或重新组织索引时，继续使用相对来源路径。
- Qwen IQ3 仓库可能存在仅本地、不在 Git 跟踪的原始运行文件。索引不会对外暴露其内容，也不将它们加入 Git。

## 从哪里开始

1. [仓库/分支/commit 快照](REPOS.md)
2. [主题和工作线总索引](INDEX.md)
3. [索引范围、分类办法与未完成事项](SCOPE.md)

## 索引维护

发现新的 `sglang*` repo、分支或主要工作线时，更新 `REPOS.md` 和 `INDEX.md`。提交前检查：来源路径可在本地找到、commit 写完整 SHA、注明此项工作的目的与代码路径、状态引用最新证据且未把计划误记为已完成。
