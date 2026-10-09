# P2A-TELEMETRY-COVERAGE-20260912-R127

- **工作标题：** P2A-TELEMETRY-COVERAGE-20260912-R127
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
只读盘点现有 P2-A telemetry 是否足以支持 queued→switch lead、L3→L2 stage、cache-induced idle、`query_storage_hit_length` timing 的验收合同；明确每项已有时间戳、粒度与缺失 mark，不设计/实现 probe。

## 实际改了什么
只读检查 opt checkout source、既存 3090 log/sample shapes 与协调仓计划；未改产品/test/gate/storage/Git，未跑 server/import/新增 ID。target 为 `3060-12g-qwen35-4b` @ `4f41f5bab562b99562f30c67540eb05344d13637`，工作树 dirty；这不是当前归集快照 HEAD。

## 生成结果与验收
四类结果：queued→switch 与 L3→L2 timing **PARTIALLY**（已有 mark 时钟/attempt namespaces 混杂）；cache-induced idle 与 query isolated timing **NEEDS_NEW_PROBE**。报告详列缺失项：per-rid mono enqueue mark、cross-request B/A lead、queue-depth/deadline、统一 stage attempt ID、GPU busy/idle + runnable-cache-wait classifier、query enter/exit mono pair 和 backend/lock/syscall/future timers。前三类可用已有内部 mark 的 observation-only log 方案补足；GPU timeline 需额外 profiling/instrumentation authorization。没有建议 redesign，也未跑测试/import/新探针。Frozen R112/R124 profile 下若模式变更需重核 availability；结论仅基于源码和旧日志形态，不是 live coverage 通过。
| 2 | `L3 -> L2` stage duration | **PARTIALLY** | `ready_stage ts_ns` mono-ns RH-only (`scheduler.py:5365`); `prefetch_issued`/`restore_retry` wall-ms (`unified_radix_cache.py:5543`; `scheduler.py:4297`) | `ready_host ready_monotonic_ns` mono-ns (`scheduler.py:4437-4485`); `[HAE] restore_hybrid_finalize ts_mono_ns` mono-ns (`unified_radix_cache.py:5682/5717`); `prefetch_finalize`/`prefetch_io_finished`/`restore_ready` wall-ms | RH start mono; other starts wall | rid yes; **attempt namespaces differ** (`:prefetch:N` vs `:N`) | mono-ns issue mark for all origins with attempt id; one consistent attempt identity |…（节选；见来源报告）


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4f41f5bab562b99562f30c67540eb05344d13637`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P2A-TELEMETRY-COVERAGE-20260912-R127.md` → `.memory/rh-p2-telemetry-metadata-cache/P2A-TELEMETRY-COVERAGE-20260912-R127.md`; SHA256 `dc29b41236906f8541d9c1eae7cb449ea63ef7b3e1f3e226bb785ed6c4f6a4cd`; source state `tracked`
