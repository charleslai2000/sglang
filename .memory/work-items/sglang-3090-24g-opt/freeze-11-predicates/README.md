# FREEZE-11-PREDICATES

- **工作标题：** FREEZE-11-PREDICATES
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 2
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
R107 原冻结规则：
- task_id: `P0-B-REDUCER-FREEZE-20260911-R107`
- role: coder
- epoch: 2026-09-11
- authoritative inputs: R54 mandatory legs, R79 execution packet, R98/R100
independent reviews, R101 event contract, R106b lineage report.
- reducer: `p0b_reducer.py` (`ORACLE_NAMES`, `oracle_names()`).
This file freezes the oracle against the **real emitted event names and
fields** of the checked-out producer (branch `3060-12g-qwen35-4b`, HEAD

R111 superseding refreeze：
- task_id: `P0-B-ORACLE-REFREEZE-20260911-R111`
- supersedes: `P0-B-REDUCER-FREEZE-20260911-R107` (kept frozen as history)
- role: coder
- epoch: 2026-09-11
- re-freeze authority: `../P0-B-GAP-CLASSIFY-20260911-R110.md` §1-2 (predicates
6 and 8 contradicted real product emission), plus the original authoritative
inputs R54, R79, R98/R100, R101, R106b.
- reducer: `p0b_reducer.py` (`ORACLE_NAMES`, `oracle_names()`).

## 实际改了什么
此卡合并了两个冻结文件：R107 初版规范与其后 R111 修订版；未混为一个单一任务。R107 freeze 定义 exactly 11 canonical predicates、输入 schemas/provenance gate 与 fail-closed joins；R111 file 明确 supersedes R107，保留 R107 作为历史。具体实现/差异工作项分别见 R107/R111 cards。
## 生成结果与验收
此索引卡仅呈现两个版本的规则与supersession关系，不代表额外实现或验收结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R107-reducer/FREEZE-11-PREDICATES.md` → `.memory/rh-p0b-harness-durability/R107-reducer/FREEZE-11-PREDICATES.md`; SHA256 `f080886734e5a6b58b35286140697d48050438fda8d6211a02660d608efc19f5`; source state `tracked`
- `phase2-hicache-design/work/R111-reducer/FREEZE-11-PREDICATES.md` → `.memory/rh-p0b-harness-durability/R111-reducer/FREEZE-11-PREDICATES.md`; SHA256 `e1da760b9c6cfa92994f9be8934a93e7801ce982101063a19a4d64a07d4c1874`; source state `tracked`
