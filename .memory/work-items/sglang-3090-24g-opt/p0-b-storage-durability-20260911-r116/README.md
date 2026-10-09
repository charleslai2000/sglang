# P0-B-STORAGE-DURABILITY-20260911-R116

- **工作标题：** P0-B-STORAGE-DURABILITY-20260911-R116
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P0-B-STORAGE-DURABILITY-20260911-R116.md`：**
`R116 storage-backed durability reducer`: a NEW, additive, offline,
stdlib-only, fail-closed checker that re-judges the FROZEN R114 bundle plus the
FROZEN L3 evidence. No live calls, no server interaction, no product imports,
no instrumentation, no synthetic events. R111/R115 were not modified or
imported.
- CLI: `python storage_durability.py --raw <raw.log> --probe <probe.log> --manifest <manifest.json> --l3-evidence <l3-evidence.json> [--json]`
- Exit `0` = STORAGE_DURABILITY PASS, `1` = FAIL (fail-closed), `2` = INVALID_INPUT.

## 实际改了什么
新增 offline stdlib-only `work/R116-storage-durability/storage_durability.py` 与 unittest、README、R114 control output：对 frozen R114 raw/probe/manifest/L3 evidence 做 storage-backed fail-closed re-judgement。不调用 live/server/product imports、不 instrument、不造 synthetic events；不改 R111/R115。

## 生成结果与验收
新增 reducer 实现 8 predicates（身份一致性、KV prefix coverage、durable object existence、write→restore、Mamba sidecar durability、L3→host completion、finalize 消费 restore、negative safety）。10 unittest 全过；真实 frozen R114 control exit 0、status PASS、8/8 predicates PASS，prefix 27,008 tokens；frozen inputs hashes re-verified unchanged。报告注明粒度限制：durability 对象仅固定 8-key set 加 page hit counts、无逐页 hash enumeration；probe identity 仅能按 rid join。predicate 4 的 qualifying different-rid/keyset 记录是 warm/build rid，非 finalize trace_context build_rid，属命名/observability caveat，记录但未判阻塞。这是离线 storage subcheck，不新作 live execution。

### 报告列出的产物/证据
- `phase2-hicache-design/work/P0-B-STORAGE-DURABILITY-20260911-R116.md`：- `work/R116-storage-durability/storage_durability.py`
  `2e6cbdb9943b766a5fc94c17d5bbef58ad61b47fc476bf159938d5f6f2bfea35`
- `work/R116-storage-durability/test_storage_durability.py`
  `368107b2b601e1e4f4fb02212e2e6dc563d3baf51a48d0b3f201c1460a1fa554`
- `work/R116-storage-durability/README.md`
  `523a45469d361372b501220f7998148a193cd01fbc490615c0ef6aaa8e54d937`
- `work/R116-storage-durability/R114-control.out.json`
  `be6a74d74d4a2e582c828848dbee555029c66e7e06179ae9f2a0ba6d5abdea04`
Frozen inputs re-verified unchanged: `raw.log`
`9df12929…dcb8c`, `probe.log` `9f41d92f…0f961`, `l3-evidence.json`
`3f1638a406511851ce8ae9005965f99a5ecef069b6cd16baadc25a8490607a4e`.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-B-STORAGE-DURABILITY-20260911-R116.md` → `.memory/rh-p0b-harness-durability/P0-B-STORAGE-DURABILITY-20260911-R116.md`; SHA256 `3aec21475076f54c6b1ddf6afbc0a4fca2381953a8d817caae0d81eb2969bf14`; source state `tracked`
