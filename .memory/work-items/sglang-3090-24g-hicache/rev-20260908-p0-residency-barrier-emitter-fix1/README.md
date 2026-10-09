# REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX1

- **工作标题：** REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX1.md`：**
**REJECT** — the narrow emitter gate is not accepted.
The retry is product-owned and the nominal focused proof is green, but two
blocking boundary findings prevent acceptance:
1. `unified_radix_cache.py:398-418` deduplicates with a key containing the
entire expected-token set. A second real detach/free cycle for the same
exact `(run_id, session_id, session_generation, build_rid, node_id,
final_kv_hash)` therefore emits a second residency barrier. Independent
AST-extracted probing produced two records from two distinct lifecycle token

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX1.md`：**
**REJECT** — the narrow emitter gate is not accepted.
The retry is product-owned and the nominal focused proof is green, but two
blocking boundary findings prevent acceptance:
1. `unified_radix_cache.py:398-418` deduplicates with a key containing the
   entire expected-token set. A second real detach/free cycle for the same
   exact `(run_id, session_id, session_generation, build_rid, node_id,
   final_kv_hash)` therefore emits a second residency barrier. Independent
   AST-extracted probing produced two records from two distinct lifecycle token
   sets for one identity.
2. `unified_radix_cache.py:143-147,378-430` stores retry state in module-global
   maps keyed only by node ID and mutates/iterates them without a common lock.
   An independent cross-cache probe seeded completion in cache A and caused
   cache B, with a different session/generation/build identity and no B detach,
   to publish using A's global expected set. This violates the no cross-node/


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX1.md` → `.memory/phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX1.md`; SHA256 `881532dfafd89be1329f13c07273c0a2d1d949ac4be9cd62c69665f1301cc07d`; source state `tracked`
