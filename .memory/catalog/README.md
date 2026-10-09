# 归集目录索引

正式归集材料按工作目的/工作流放在 `.memory/` 根下的专属目录中，而不是 `archive/`。例如 HiCache 主工作线仍在 `phase2-hicache-design/`，opt 来源中可归类的工作材料分入其 `cross-repo/` 子目录，Qwen 基线材料按性能/依赖/内核等工作线进入 `g3-baseline-20260907/workstreams/`。

- `hicache-{docs,files}.md`、`opt-{docs,files}.md`、`qwen-{docs,files}.md`：逐条来源路径及实际归集位置。
- `*-workstreams.md`：按工作目的提供导航。
- `.memory/archive/MANIFEST.tsv`：权威逐文件映射，含来源仓、分支、commit、Git state、哈希、类别和目标路径。
- `.memory/data/`：本地大型/raw数据，保持忽略，不纳入提交。

Catalog 为定位工具，不代表对历史报告结论作当前背书。
