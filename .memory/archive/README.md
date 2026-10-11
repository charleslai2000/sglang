# 归集归档使用说明

## 归集布局

- `.memory/data/<source-repo>/<sha-prefix>/<sha256><extension>`：大于等于 1 MiB、raw/telemetry、运行日志/状态、压缩包/wheel/二进制等本地数据。根 `.gitignore` 忽略整个 `.memory/data/`。
- `data-refs/<source-repo>/<original-path>.data-ref`：大文件每个源路径的引用，包含归档位置、SHA、大小、来源 Git state、source HEAD。
- `MANIFEST.tsv`：所有源路径的逐项映射，包含来源 repo/分支/full commit、源 `.memory` 相对路径、docs/data 类别、tracked/local-only、字节数、SHA、去重状态和归集位置。
- `<source-repo>-SOURCE.txt`：来源 snapshot 的本地仓路径、branch、HEAD。

## 去重

去重只在**相同来源仓**内按 SHA-256 完全相同执行。同一源仓的相同字节内容只存一份；原来每个路径仍在 Manifest 和 data reference 中保留。不同源仓不跨仓去重，即使 blob 相同也各自留存，避免失去分支/epoch provenance。

## 查找

1. 按旧路径查原文件：搜 `MANIFEST.tsv` 的 `source_path`。
2. 确认来源身份：读取该行的 `source_repo`、`branch_at_snapshot`、`source_head`。
3. 正式文档：通过 `stored_path` 打开 `.memory/<workstream>/...`。
4. 数据：正文在 `.memory/data/...`（该目录本机忽略）；每路径引用在 `data-refs/...`，哈希/尺寸在 Manifest。
5. 正式文档按 workstream 放在 `.memory/` 根目录下；工作线视图见 `../catalog/{hicache,opt,qwen}-workstreams.md`。

Source files were copied, never moved or changed. data is local-only, not remote-backed up. Treat runtime logs/process snapshots as operational evidence: review content and authorization before sharing.
