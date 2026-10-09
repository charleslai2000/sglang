# P0-A-RH-REGRESSION-RECONCILED-20260911-R3

- **工作标题：** P0-A-RH-REGRESSION-RECONCILED-20260911-R3
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P0-A-RH-REGRESSION-RECONCILED-20260911-R3.md`：**
artifacts:
- This report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/P0-A-RH-REGRESSION-RECONCILED-20260911-R3.md`
- Remote checkout used: `/root/sglang-3060-12g-hicache`
- No source, test, Git, gate, storage, server, or live-trace files were modified.
evidence:
- Authorized endpoint: `root@i-1.gpushare.com:27460`, key `/home/dev-codex/.ssh/sglang_3060_ed25519`.
- Remote identity probe exited `0`: hostname `I2aff9805ac001019d1`; GPU `NVIDIA GeForce RTX 3060`, `12288 MiB`, compute capability `8.6`; interpreter Python `3.11.11`; pytest `9.1.1`.
- The required six test-file hashes and four observed modified product-file hashes were checked locally and remotely before execution. All ten matched exactly:

## 实际改了什么
使用 source-reconciled RTX 3060 checkout 只做 hash gate 与指定 pytest 命令；未改源码/test/Git/gate/storage/server，也未跑 live trace。六个测试文件与四个观察到的修改产品文件本地/远端 hash 一致。

## 生成结果与验收
source gate 通过，但 P0-A regression 总体 **NOT VERIFIED**：7 条命令中 3 条全过、4 条 exit 1，共 164 passed、17 failed。失败含 `PrefetchIssueResult` 类型断言/API 不匹配、测试 double `charge(origin=...)` 签名、旧日志 token expectation、`_t38c_node_context_index` fixture 缺失、容量 fixture 与 `pop_host_alloc_failure` API mismatch。失败未以修改 fixture 或产品代码绕过。未起 server、未做 live RH-OFF/ON trace。Reported commit/target is source-reconciled remote checkout `/root/sglang-3060-12g-hicache`; no Git revision was established by this excerpt beyond matching file hashes; acceptance remains NOT_VERIFIED。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-A-RH-REGRESSION-RECONCILED-20260911-R3.md` → `.memory/rh-p0a-budget-residency/P0-A-RH-REGRESSION-RECONCILED-20260911-R3.md`; SHA256 `102d4d4dca9877d72ccd20a5408d3a5a7c9f21a5d266abe128452fbc247d92f5`; source state `tracked`
