# CODE-20260909-HOST-ALLOC-EPOCH-TELEMETRY-FINAL

- **工作标题：** CODE-20260909-HOST-ALLOC-EPOCH-TELEMETRY-FINAL
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/CODE-20260909-HOST-ALLOC-EPOCH-TELEMETRY-FINAL.md`：**
ENTRY: ACCEPT
status: done
Task ID: `CODE-20260909-HOST-ALLOC-EPOCH-TELEMETRY-FINAL`
Orchestration epoch: `20260909-P4`
Role: `coder`
Branch: `3060-12g-qwen35-4b`
Base review: `REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH-FINAL`
Commit: `82ab235606`

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/CODE-20260909-HOST-ALLOC-EPOCH-TELEMETRY-FINAL.md`：**
- F-HAE-FINAL-01: hybrid all-or-nothing and sidecar telemetry access is now
  optional-field safe for duck-typed transfers. Missing `hit_policy`, pool
  source/name, keys, or hit-page maps produce conservative observational
  values and cannot raise from telemetry. The hybrid validation path uses the
  same safe access for compatibility fixtures.
- F-HAE-FINAL-02: cache-side `host_allocability_change` records retain the
  complete monotonic generation and mutation sequence, but emission is bounded
  independently of scheduler wake decisions. Per `(pool, cause, request,
  trace)` key, the policy emits the first 16 mutations, samples every 128th
  mutation, and caps at 64 records; each cache instance caps the family at 256
  records. Sample fields retain the sequence, mutation count, sample index, and
  coalesced count for joins. Allocation, generation, and wake behavior are not
  suppressed.
- F-HAE-FINAL-03: discarded hybrid finalize telemetry now reports

### 报告列出的产物/证据
- `phase2-hicache-design/work/CODE-20260909-HOST-ALLOC-EPOCH-TELEMETRY-FINAL.md`：- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `3090-dev/test_storage_regression.py`
- This report at the requested sibling-workspace path.
No remote, sibling 3090 repository, storage artifact, or unrelated branch file
was changed or staged.

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `82ab235606`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/CODE-20260909-HOST-ALLOC-EPOCH-TELEMETRY-FINAL.md` → `.memory/phase2-hicache-design/work/CODE-20260909-HOST-ALLOC-EPOCH-TELEMETRY-FINAL.md`; SHA256 `d7b2747daa9b08a2fa152f0d5bf4e3a50120d1430ae99da6a40b80fd6ca6c314`; source state `tracked`
