# 仓库、分支与 commit 快照

**快照时间：2026-10-09（本机检查时间）**。分支和工作区会变化；本页是目录级发现快照，不是远程最新状态保证。源材料索引见 [INDEX.md](INDEX.md)。

| 仓库目录 | 当前本地分支 | 检查时 HEAD（完整 SHA） | 上游/远程状态 | `.memory` / 工作区备注 |
|---|---|---|---|---|
| `sglang-3090-24g-hicache` | `3090-24g-hicache` | `b864ffe3c232348db8c0e9940737b0288efe93a8` | `origin/3090-24g-hicache` 当时一致 | 有 1122 份文档类记录（约 10.6 MiB 目录统计）；工作区干净。原始 HiCache 主索引来源。 |
| `sglang-3090-24g-opt` | `3090-24g-opt` | `ad749d6f283b7d6c59a8df928304325eda90e98b` | `origin/3090-24g-opt`；当时本地落后 69 commits | 有 345 份文档类记录；与 `hicache` 有大量重叠和不同 snapshot；工作区干净。 |
| `sglang-qwen3-27b-iq3s` | `qwen3-27b-iq3s` | `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2` | 新分支已推送至 `origin/qwen3-27b-iq3s`；该仓 `origin` fetch URL 是失效的本地 bundle 路径，查询 GitHub URL 时验证过分支头 | `.memory/g3-baseline-20260907` 等为本地资料；原始运行记录约 1244 项此前未跟踪，受本机 `.git/info/exclude` 忽略。代码提交不包括这些 raw 文件。 |
| `sglang-2060-6g-hicache` | `sglang-sm75` | `fb2c68a48e0e`（快照时短 SHA） | `origin/sglang-sm75` 当时一致 | 无 `.memory`；干净。 |
| `sglang-5090-32-hicache` | `5090-32-hicache` | `54c394a2e171`（快照时短 SHA） | 没有 upstream 配置；HEAD 被 `origin/3090-24g-hicache` 包含（快照时检查） | 无 `.memory`；干净。 |
| `sglang-v0519-integration-20260913` | `integration/v0.5.19-semantic-20260913` | `993ef8e5c3a6`（快照时短 SHA） | 无 upstream 配置；fetch 过 `origin` 和 `upstream`，未计算任意跟踪分支差异 | 无 `.memory`；有大量 staged/unstaged 工作区变更，属活动工作树，不应写入/清理。 |

## 如何刷新

逐仓库运行 `git -C <repo> status --short --branch`、`git -C <repo> rev-parse HEAD`、`git -C <repo> branch -vv`；只有确认无破坏性影响后再 fetch。注意某些仓库的 remote 配置并非标准 GitHub URL；不要把缺失/失效跟踪误报为同步。
