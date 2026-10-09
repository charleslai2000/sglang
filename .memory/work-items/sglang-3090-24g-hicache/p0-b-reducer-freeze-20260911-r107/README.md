# P0-B-REDUCER-FREEZE-20260911-R107

- **工作标题：** P0-B-REDUCER-FREEZE-20260911-R107
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/P0-B-REDUCER-FREEZE-20260911-R107.md`：**
- `ORACLE_NAMES` / `oracle_names()` expose **exactly 11** names in canonical
  order: `provenance`, `singular_identity`, `pid_profile_source_binding`,
  `positive_full_hit`, `host_alloc_park`, `generation_transition`,
  `fifo_predecessor`, `attempt_lineage`, `accepted_finalization`,
  `ready_after_finalize`, `negative_safety`.  `raw_provenance` is an input
  gate, not a predicate; `negative_safety` is predicate 11.
- Real event names/fields only, derived from the emission sites:
  `restore_host_alloc_wait` (`scheduler.py:3844`),
  `restore_host_alloc_wake_decision` grant/release/hold
  (`scheduler.py:3985/3661/4183`), `restore_host_alloc_retry_result`
  (`unified_radix_cache.py:5460/6576`), `restore_hybrid_finalize`
  (`unified_radix_cache.py:5683/5718`), `host_allocability_change`
  (`unified_radix_cache.py:3798`), the `[P3] evt=ready_host
  schema=rh_ready_host.v1` line (`scheduler.py:4409`), and

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。

### 报告列出的产物/证据
- `phase2-hicache-design/work/P0-B-REDUCER-FREEZE-20260911-R107.md`：All under
`.memory/phase2-hicache-design/work/R107-reducer/` (the authorized write set):
```
sha256  file
f080886734e5a6b58b35286140697d48050438fda8d6211a02660d608efc19f5  FREEZE-11-PREDICATES.md
253facede369f7e258eab922cc45e4bf959594de18b8b5ae0c11baee9fe211ce  README.md
11de96819a75dc5b82d0ca1d230c3fef9aab3fb81ecee2f0ec903e0e154c4b08  p0b_reducer.py
32b409e0b84222886baabd1a7d56c71ca2939d2866ba9b91405b54318b0599e6  test_reducer.py
b118299381816806c3b96c21171c1501f24276e61a11fae313273e6554f8d852  manifest.sha256
```
`sha256sum -c manifest.sha256` → all four pinned files `OK`.
Report (this file):
`.memory/phase2-hicache-design/work/P0-B-REDUCER-FREEZE-20260911-R107.md`.

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4f41f5bab5`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-B-REDUCER-FREEZE-20260911-R107.md` → `.memory/phase2-hicache-design/work/P0-B-REDUCER-FREEZE-20260911-R107.md`; SHA256 `1cf6b061329fdbeb7e46af374cddb1db2125fe2ac22d5c2e8d9768894c140183`; source state `tracked`
