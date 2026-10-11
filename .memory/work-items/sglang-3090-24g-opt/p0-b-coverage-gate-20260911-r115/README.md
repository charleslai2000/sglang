# P0-B-COVERAGE-GATE-20260911-R115

- **工作标题：** P0-B-COVERAGE-GATE-20260911-R115
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P0-B-COVERAGE-GATE-20260911-R115.md`：**
- **Task ID:** `P0-B-COVERAGE-GATE-20260911-R115`
- **Invocation:** `ses-p0b-coverage-gate-r115-20260911` (fresh)
- **Role:** coder
- **Epoch:** 2026-09-11
- **Status:** `done`

## 实际改了什么
在 `work/R115-coverage/` 新增 stdlib `coverage_gate.py`、`test_coverage_gate.py`、README、manifest 与 R113 control output；未改产品代码、R111/R113/R114 artifacts 或 sibling mirror。

## 生成结果与验收
实现 fail-closed companion gate `durable_frontier_coverage`，补足 R111 predicate 4 只检查 barrier 存在、不验证其 lineage 覆盖 target restore frontier 的缺口；P0-B closure 必须同一 frozen bundle 同时 R111 11/11 与本 gate PASS。8 个 synthetic unit tests 全通过，py_compile 通过；R113 frozen control 返回 exit 1 / `no_durable_barrier`（正确 FAIL）。这是 harness/gate 实现与测试，不是 P0-B live PASS；严格实现要求 target chain `storage_persisted.frontier_end >= R`，不会用 barrier kv count 放宽替代。
complete `durability_barrier` exists at the target's `session_generation`; it
does not verify that the barrier's durable lineage covers the frontier the
target restore requires. This gate closes that gap: P0-B closes only when R111
is 11/11 **and** this gate PASSes on the same frozen bundle.
No product code, R111/R113/R114 artifacts, or sibling mirror were modified.

### 报告列出的产物/证据
- `phase2-hicache-design/work/P0-B-COVERAGE-GATE-20260911-R115.md`：All under
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/R115-coverage/`:
| File | sha256 |
| --- | --- |
| `coverage_gate.py` | `c6a8492f365f5755a117075d1a74f88979fc89040399a160bf04187f8f74b328` |
| `test_coverage_gate.py` | `a610b88fb3151554acc10688540ba54035b44df3169ba6d24cc8621364ac81a3` |
| `README.md` | `56d9fb0e31a58424bebe1aec9edc65ee86837561a4b2c55559dd3b5f519b329e` |
| `R113-control.out.json` | `a938fdc992571a3615a411d4f1f825698bc91665f8b44df4ac7af0fc90b84760` |
Local deterministic checks run: `python -m unittest test_coverage_gate -v`
(8/8 ok), `python -m py_compile coverage_gate.py test_coverage_gate.py` (ok),…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-B-COVERAGE-GATE-20260911-R115.md` → `.memory/rh-p0b-harness-durability/P0-B-COVERAGE-GATE-20260911-R115.md`; SHA256 `0cac877c3449f8e55f1c016c3cc40f46b2088d579969eff576dcde32f2b58502`; source state `tracked`
