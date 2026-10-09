# SGLang work archive index

本目录是 `/home/dev-codex/workspaces/3rdparty/` 下 SGLang 仓库的跨仓知识归集区。目标是在多仓、多分支、多 worktree 任务分散的情况下，让后续工作能按**工作目的/工作流/来源分支与 commit/代码路径/证据**直接检索。

## 入口

- [WORKSTREAMS.md](WORKSTREAMS.md)：跨仓工作综合，按工作项提炼目标、结论、依赖、代码关联及接续边界（区别于原始文件目录）。
- [work-items/README.md](work-items/README.md)：从原始工作报告逐项清理出的独立工作卡索引（按来源仓+Task ID 聚合；每卡列目标、实际改动、结果、证据、执行 commit 和来源快照）。
- [INDEX.md](INDEX.md)：按目的和工作流导航，记录相关代码与主要交接材料。
- [REPOS.md](REPOS.md)：六个 `sglang*` 仓库的本地分支、HEAD、远程跟踪快照。
- [SCOPE.md](SCOPE.md)：归集规则、安全边界与未完成/待核项目。
- [archive/README.md](archive/README.md)：实际归集结构、去重与来源映射说明。
- [archive/MANIFEST.tsv](archive/MANIFEST.tsv)：逐源路径 mapping，含来源 repo/branch/full commit/tracked 状态、内容 SHA、归集路径。
- [catalog/README.md](catalog/README.md)：归集后按路径/文档/工作流查找的方法。
- [data/README.md](data/README.md)：大型/raw 文件本地归档说明；`.memory/data/` 已纳入根 `.gitignore`，不会随普通提交上传。

## 工作内容综合与原始证据

`WORKSTREAMS.md` 是可接手的工作总结；按主题整理的原始报告是其证据，不应把搬动/列目录当成工作综合。对历史结论，需回到来源 epoch 的 handoff/closure，并按 Manifest 核验对应来源 HEAD 与路径。

## 原始文件如何归集

三套有 `.memory` 的仓库已经归集到 `.memory/` 下各工作项目录和 `.memory/data/`：

- `sglang-3090-24g-hicache`
- `sglang-3090-24g-opt`
- `sglang-qwen3-27b-iq3s`

正式文档按来源工作项目录放在 `.memory/<workstream>/`（如 `phase1-patch-release/`、`phase2-hicache-design/`、`g3-baseline-20260907/`）；同一来源仓内 SHA-256 完全相同的重复文件仅保留一个内容副本，所有原始路径、分支和 commit 均在 `.memory/archive/MANIFEST.tsv` 中保留。不同来源仓之间不合并相同内容，以保留 branch/epoch provenance。

大于等于 1 MiB、raw/telemetry、运行日志/状态、压缩包、wheel、二进制等放入 `.memory/data/<source-repo>/<hash-prefix>/`，由根 `.gitignore` 排除。对应每个原始路径会在 `.memory/archive/data-refs/` 留轻量引用文件，Manifest 可查完整 hash 和位置。

## 边界

- 源仓库保持不变；归集副本不替代源仓原文件。
- 归集反映 snapshot 时的文件，报告内历史结论不自动成为当前结论；用 Manifest 的 commit 回到对应历史检查代码。
- 提交 `.memory/` 下正式工作项文本、Manifest、目录和索引；不提交 `.memory/data/` 中的本地运行数据。
- 当前本地 data 约 849 MiB；这些大数据没有远程备份。迁移本工作区前需单独做批准的本地数据备份。
