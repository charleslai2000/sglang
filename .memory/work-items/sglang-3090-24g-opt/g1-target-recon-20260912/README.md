# G1-TARGET-RECON-20260912

- **工作标题：** G1-TARGET-RECON-20260912
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
在 opt 仓 HEAD `4f41f5bab5` 上只读侦察 ExtentFileBackend 的文件格式、索引/allocator 状态、write/ACK/read/eviction 路径和真实 restart E2E oracle；不提出设计、不改源码。

## 实际改了什么
只读源码及现有单测/E2E 测试，引用行号核实；没有文件修改或新增测试。仓库来源快照 HEAD 是 scout 指定的源码对象，不应替代执行身份或其他报告中的 target commit。

## 生成结果与验收
确认 extent 文件没有 header/checksum/metadata，主要 index/generation/cursor/LRU 状态仅在 RAM，重启后新 allocator 无法寻址旧 payload；`test_crash_reopen_all_cold` 已有 cold oracle。共享 storage mixin 的真实 restart E2E 却要求 storage_cached_tokens 保留，HiCacheFile 重启扫描而 extent 当前 cold，因此 extent E2E 预期 RED，但此侦察没有运行它。报告结论是有源码锚点的 read-only facts；不等于接受持久化设计，也不证明具体测试此次执行。


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4f41f5bab5`, `f4e7a98fe5`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/G1-TARGET-RECON-20260912.md` → `.memory/hicache-l3-extent-storage/G1-TARGET-RECON-20260912.md`; SHA256 `03ef4584d4853bb05fd85a0f709dae0b7afe4adf4ae45d3471ee291bce36b566`; source state `tracked`
