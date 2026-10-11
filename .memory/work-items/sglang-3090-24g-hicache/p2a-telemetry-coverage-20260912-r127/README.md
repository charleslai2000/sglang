# P2A-TELEMETRY-COVERAGE-20260912-R127

- **工作标题：** P2A-TELEMETRY-COVERAGE-20260912-R127
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/P2A-TELEMETRY-COVERAGE-20260912-R127.md`：**
- Task ID: `P2A-SCOPE`
- Invocation: `ses-p2a-telemetry-coverage-20260912-r127`
- Epoch: `2026-09-12`
- Role: `scout` (private, read-only)
- Status: **done**
- ENTRY: `ACCEPT`
Claim boundary: read-only telemetry-coverage inventory. No product/test/gate/storage/git
change; no server run; no product import; no new IDs created. This report states what is

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** PARTIALLY; done

**`phase2-hicache-design/work/P2A-TELEMETRY-COVERAGE-20260912-R127.md`：**
| # | Quantity | Verdict | Start mark (today) | End mark (today) | Monotonic? | Per rid/attempt? | Missing mark(s) |
|---|---|---|---|---|---|---|---|
| 1 | `queued -> switch` lead | **PARTIALLY** | enqueue: `wait_queue_entry_time` internal mono-f only (`scheduler.py:6072`; `req_time_stats.py:738-757`); emitted `[P2A] evt=admission` wall-ms (`scheduler.py:6736`) and `[P3] …request_enqueue_seq` (counter) | switch-in: `admission.v2 admission_monotonic_ns` mono-ns (`scheduler.py:6820-6836`); `forward_entry_time` internal mono-f (`scheduler.py:6934`) | mixed; derived `queue_duration` is mono-f but opt-in/log-derived | rid yes; attempt n/a | emitted mono-ns enqueue per rid; cross-request `B_enqueue`/`A_finished`; queue-depth series; deadline/miss class |
| 2 | `L3 -> L2` stage duration | **PARTIALLY** | `ready_stage ts_ns` mono-ns RH-only (`scheduler.py:5365`); `prefetch_issued`/`restore_retry` wall-ms (`unified_radix_cache.py:5543`; `scheduler.py:4297`) | `ready_host ready_monotonic_ns` mono-ns (`scheduler.py:4437-4485`); `[HAE] restore_hybrid_finalize ts_mono_ns` mono-ns (`unified_radix_cache.py:5682/5717`); `prefetch_finalize`/`prefetch_io_finished`/`restore_ready` wall-ms | RH start mono; other starts wall | rid yes; **attempt namespaces differ** (`:prefetch:N` vs `:N`) | mono-ns issue mark for all origins with attempt id; one consistent attempt identity |…（节选；见来源报告）


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4f41f5bab562b99562f30c67540eb05344d13637`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P2A-TELEMETRY-COVERAGE-20260912-R127.md` → `.memory/phase2-hicache-design/work/P2A-TELEMETRY-COVERAGE-20260912-R127.md`; SHA256 `dc29b41236906f8541d9c1eae7cb449ea63ef7b3e1f3e226bb785ed6c4f6a4cd`; source state `tracked`
