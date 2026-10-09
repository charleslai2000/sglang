# P0-A-CLEAN-RERUN-20260911-R28

- **工作标题：** P0-A-CLEAN-RERUN-20260911-R28
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P0-A-CLEAN-RERUN-20260911-R28.md`：**
artifacts:
- .memory/phase2-hicache-design/work/P0-A-CLEAN-RERUN-20260911-R28.md
- .memory/phase2-hicache-design/work/P0-A-CLEAN-RERUN-20260911-R28.transcript
- Remote backup: /root/sglang-3060-12g-hicache/p0a-backup-20260910T214626Z
evidence:
- Authorized target only: root@i-1.gpushare.com:27460, checkout /root/sglang-3060-12g-hicache.
- Local exact hashes matched required values; all required local symbols present.
- Remote backup hashes and post-transfer destination hashes matched each other and local hashes.

## 实际改了什么
在授权远端 3060 checkout 做 hash-gated clean rerun；先备份并传输三份指定测试文件，backup/destination/local hashes 一致。运行八条命令，无产品改动。

## 生成结果与验收
八条均 exit 0：focused ready 13 passed/61 deselected；focused budget 9/15；full ready 74；full budget 24；restore feed 46；partition 18；prefetch gate 2；dependency-free 19。Transcript SHA256 `7dfe4b10…f9d19c61`。报告判 **P0-A VERIFIED DONE**，限定于该测试组合及文件 provenance；不自动证明 live-runtime 或其它 acceptance scope。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-A-CLEAN-RERUN-20260911-R28.md` → `.memory/rh-p0a-budget-residency/P0-A-CLEAN-RERUN-20260911-R28.md`; SHA256 `2fc313e1725b6e89b2611edec10de7b07f5e2a45a701e9ed38510e82698d2dbd`; source state `tracked`
