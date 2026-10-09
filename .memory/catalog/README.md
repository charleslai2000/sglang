# 逐文件路径目录说明

本目录三个清单由本轮从各来源 `.memory` 工作树盘点生成：

- `hicache-files.md`：`sglang-3090-24g-hicache` 的 `.memory` 文件路径，共 1244 项；其中 tracked 按来源 HEAD 计算，22 项当时为本地-only。
- `opt-files.md`：`sglang-3090-24g-opt` 的 `.memory` 文件路径，共 576 项；其中 421 项 tracked，155 项 local-only。
- `qwen-files.md`：`sglang-qwen3-27b-iq3s` 的 `.memory` 文件路径，共 1438 项；当时来源 HEAD 中无 `.memory` 跟踪文件，故均标为 local-only。
- `hicache-work-groups.md`：HiCache `work/` 子目录与 run bundle 统计、tracked/local-only 数量和示例路径。

`*-files.md` 列出相对来源路径、粗粒度类型、跟踪状态、字节数、可用的 Git blob OID。`*-docs.md` 为非 `work/raw/` Markdown/text 提供第一行标题提示和 Git 状态，便于路径检索；这是机械提取，不代表语义审阅或对文档结论背书。内容不搬运。Qwen 的 local-only 项包含大量 raw 运行证据；HiCache `opt` 也有 local-only 文件。清单不会暴露 raw 文件内容，需在对应仓库核实后再用。

这些是生成时快照，不会自动更新。任何来源仓库变更后，应重新生成/核实对应清单，并在提交中注明来源 HEAD。粗分类只是导航提示，不表示内容已语义审阅。
