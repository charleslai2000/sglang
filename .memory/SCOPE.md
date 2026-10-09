# 范围、处理规则与待核事项

## 目标

把 `3rdparty/` 下各 SGLang 仓库的 `.memory` 文件按工作项目归集至当前 `3090-24g-hicache` 分支，做同源内容去重，形成后续开发可检索的目的/分支/commit/代码/证据入口。

## 来源仓库

本轮盘点六个 `sglang*` 仓库：

- `sglang-3090-24g-hicache`
- `sglang-3090-24g-opt`
- `sglang-qwen3-27b-iq3s`
- `sglang-2060-6g-hicache`
- `sglang-5090-32-hicache`
- `sglang-v0519-integration-20260913`

后三个当前未发现 `.memory`，因此其 branch/commit 入口记在 `REPOS.md`，没有源 memory 可归集。前三个有 memory，已生成归集副本。

## 分类规则

- `documents`：文本/代码/报告/账本/handoff/JSON 文本配置等，按 source repo + 工作流目录归集；同一 source repo 内 SHA-256 相同的文件只保留一个 payload，并把全部旧路径记入 Manifest。
- `data`：>=1 MiB、raw/telemetry、常见运行日志和进程快照、wheel/压缩包/二进制等；本地留在 `.memory/data/`，由 `.gitignore` 整体忽略。逐源路径保留 `.data-ref`。
- 同内容跨 source repo 不折叠，防止丢失各自的 branch/commit/epoch provenance。
- 来源 `.memory` 不移动或修改；当前工作树如已存在完整源副本，仅新增归集，不覆盖源 repo。

## 文件数/体量（按最终归集快照）

- 三个来源合计 3254 条源路径映射，包含 source repo 内 tracked 与 local-only 文件。
- 文档类按每个来源仓分别 SHA-256 去重后有 1726 个对象、跨来源共享哈希后实际全文可存 1321 个对象；文档 payload 在归集树约 18.5 MiB（du 约 27 MiB）。
- 数据类 1504 条路径按来源仓去重后 898 个对象、跨来源共享 hash 后 889 个对象；本地 ignored data payload 约 848.6 MiB（du 约 853 MiB）。Manifest 保留全部源路径、tracked state 和 canonical/duplicate 状态。
- HiCache 来源 `.memory` 本轮扫描时有未提交 changes（与本次新建的 catalog/archive 管理文件有关）；其它两个来源 `.memory` 在扫描时 clean。完整 branch/commit 和 dirty 位见 Manifest / `*-SOURCE.txt`；不得把这个 snapshot 误当永久状态。
- 有些文件结构（如 JSON runtime metrics）按数据/日志证据归入 data，不因文本可读就移入 tracked documents。

## 安全、限制

- `data/` 约 849 MiB，被忽略而不提交；没有远程备份。本仓库 checkout/clone 将无法自动恢复它，需从有授权的本地备份或来源仓工作树恢复。
- 对归集的 docs 副本做了明显私钥/GitHub token/AWS key/bearer literal/credential assignment 模式扫描，0 命中；这是自动 pattern check，不是完整安全审计。
- Qwen 本地-only raw 数据中有 server/env/proc 状态类型文件，全部归到 ignored `data/`，不对 Git 提交。
- 每个文件的 snapshot commit 和 tracked/local-only 来源状态在 `.memory/archive/MANIFEST.tsv`，不要只看报告文字推断当前代码。
- 本轮未修改三套源仓文件；`sglang-v0519-integration-20260913` 仍有先前检查到的大量 staged/unstaged 变更，始终只读保留。`sglang-v0519-integration-20260913` 仍有先前检查到的大量 staged/unstaged变更，始终只读保留。

## 当前结果

- 已建立实际复制、同源哈希去重、数据隔离和按 workstream 的文档归集。
- 索引入口 `.memory/INDEX.md` 与 Manifest/catalog 要同步指向新归集结构。
- 远程提交范围限于文档类归集、索引、Manifest、data-ref 和 `.gitignore`，不包含 `.memory/data/` payload。
