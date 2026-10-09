# 范围、索引方法与待核事项

## 目标

降低散落在多个仓库、分支、worktree、日期化任务包和 raw evidence 目录里的工作知识检索成本；为未来开发者提供入口，明确每项工作的目的、依赖的分支和 commit、相关代码、主要报告/证据以及尚未解决事项。

## 本轮覆盖范围

检查了 `/home/dev-codex/workspaces/3rdparty/` 下六个 `sglang*` Git 仓库：

- `sglang-3090-24g-hicache`
- `sglang-3090-24g-opt`
- `sglang-qwen3-27b-iq3s`
- `sglang-2060-6g-hicache`
- `sglang-5090-32-hicache`
- `sglang-v0519-integration-20260913`

其中前三者有 `.memory`；后三者未发现 `.memory`。当前先索引前三者可见的 handoff/context/plan/ledger、关键 closure/review、代表性工作包和相关代码目录。目标是可导航，不是把 2100 余份小报告逐篇复制进本仓。

## 原始资料保留与隐私边界

- 不移动、删除、重命名或改写任一来源仓库文件；不改来源仓库工作区或分支。
- 不把 `.memory` 下的大型 raw metrics、日志、压缩证据包、服务环境快照、tokenizer/model 文件拷贝过来。
- Qwen 工作树里的 raw 目录是源仓本地未跟踪资料，既可能含机器/运行信息，也可能没有稳定 commit。当前只提供路径/主题入口，不宣称这些文件已提交或可从远程重现。
- 不把 `/home/charles` 私有路径中不可见的材料、外部 `/mnt/data` 证据、GPU 主机运行状态、token/secret 引入索引；必要时只记录来源文档自身给出的路径，并标记它不能从本机验证。
- 若后续确实需要可移植证据，另行判断最小、安全、可审阅的摘要；不因“归档”目标默认上传原始环境快照。

## 状态和重复材料处理

- `hicache` 与 `opt` 都有 `.memory/phase2-hicache-design/`；文件内容及分支历史相似但不等同。以各自路径、各自 HEAD 为来源，不擅自合并成单一权威副本。
- 两个 context 文档自述 branch/HEAD 可能属于历史 epoch；有些文档特意保留旧状态。索引标注这是“文档陈述”，须以 Git 树及专门的 reconciliation/handoff 交叉核验。
- 新近资料与旧 handoff 有矛盾时，不覆盖旧证据；标明冲突、日期、证据链和待确认权威。
- 状态分类建议：`VERIFIED`（可重查的证据支持）、`REPORTED`（文档自述）、`OPEN`、`BLOCKED`、`SUPERSEDED`、`UNTRACKED/LOCAL-ONLY`。

## 工作状态

- 已完成：六仓库盘点、当前分支/HEAD/工作区快照；识别三个有 `.memory` 的来源；确认 HiCache 两个仓库重叠但 HEAD 不同；确认 Qwen 存在大量本地 raw/untracked 材料。
- 已完成：建立 `.memory/README.md`、`REPOS.md`、`SCOPE.md` 和主题索引 `INDEX.md`。
- 后续可以继续：对 INDEX 中被标为“待逐篇扩展”的每个 work 文件生成机器可追踪的逐文件 catalogue（相对路径、blob oid/文件状态、目的摘要、分支/commit、代码路径）。本次不复制 raw 文件，不把所有 agent 子报告逐篇摘要伪装成已完成。
- 本任务当前验证：来源仓库 `git status` 在本轮初始盘点时均干净，唯 `sglang-v0519-integration-20260913` 有 1154 个 staged entries、8 个 unstaged changes；未对其操作。Qwen raw `git status` 显示 1244 个 untracked entries，当时保留而不暂存；后来通过它自己的 `.git/info/exclude` 忽略，仍未加入该仓 Git。
