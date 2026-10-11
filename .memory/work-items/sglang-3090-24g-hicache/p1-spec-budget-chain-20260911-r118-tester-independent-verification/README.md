# P1-SPEC-BUDGET-CHAIN-20260911-R118`  (tester / independent verification)

- **工作标题：** P1-SPEC-BUDGET-CHAIN-20260911-R118
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/P1-SPEC-BUDGET-CHAIN-20260911-R118.md`：**
Run id: `run-48806-4187756182262`  Profile: `profile-97ee3d5d3bfdca6237dc746e`
Server: `http://127.0.0.1:30000` (PID 48746, scheduler 48806), read-only.
Source HEAD: `4f41f5bab562b99562f30c67540eb05344d13637` (worktree dirty; hashes in bundle).
Method: public HTTP only (`GET /health`, `POST /v1/tokenize`, `POST /v1/completions`),
temperature 0, top-level `session_id`, `prompt` as `input_ids` (batch path; the
tokenizer is not batch-encode enabled). No product edits, no instrumentation, no
server control. 6 build requests + 1 input_ids batch replay + 1 trigger request per
run. Driver: `/tmp/r118/driver118.py` (copied into the bundle as `driver.out` transcript).

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/P1-SPEC-BUDGET-CHAIN-20260911-R118.md`：**
The SPEC_BUDGET park and the budget-release epoch are **reproducibly captured** for the
same rid. The downstream legs (RH wake / L3->L2 stage / host-ready / admission /
L2->L1 restore+generation) are **not reached** for the parked rid: it is never
re-evaluated by the ready horizon after the park, and host headroom is structurally
insufficient to stage it. Verdict: full chain **not produced**; park + release-epoch
legs verified, downstream legs missing.

### 报告列出的产物/证据
- `phase2-hicache-design/work/P1-SPEC-BUDGET-CHAIN-20260911-R118.md`：- `raw.log` sha256 `420ea7f7d2d10c64aae435989ce765525b48172589420edd7a9e5b0b3bda226f`
  (server log lines 1056603.., includes run1 + n2 + n3 windows).
- `probe.log` sha256 `8e91defa6a2c36263a42844c3a586d467ae21ce4df5c88174aa6c4bab563e306`.
- `requests.jsonl` sha256 `2e6721d7e800d017957e29543dfc9c17e532a328b62eea40a69f616500f408a1`
  (build/replay/trigger request records for R118-n3).
- `state.jsonl` sha256 `8f4291d1fb92e61b4f2ad8e528102981fddf673e012e10aa898e7a40ded4a9af`.
- `chain.json` (structured chain + line refs), `manifest.json` (`p0b.raw-bundle.v3`),
  `baseline-offsets.txt`, `source-hashes.txt`, `driver.out`, `watch.log`.

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4f41f5bab562b99562f30c67540eb05344d13637`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P1-SPEC-BUDGET-CHAIN-20260911-R118.md` → `.memory/phase2-hicache-design/work/P1-SPEC-BUDGET-CHAIN-20260911-R118.md`; SHA256 `71deca7cbf963eccdc3cc99378873d88d4d97d0a2a4437866dac3dc99486435a`; source state `tracked`
