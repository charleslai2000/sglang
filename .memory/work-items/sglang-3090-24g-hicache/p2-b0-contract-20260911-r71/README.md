# P2-B0-CONTRACT-20260911-R71

- **工作标题：** P2-B0-CONTRACT-20260911-R71
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/P2-B0-CONTRACT-20260911-R71.md`：**
- Task ID: `P2-B0-CONTRACT-20260911-R71`
- Invocation: `ses-p2b0-contract-r71-20260911`
- Epoch: `2026-09-11`
- Role: `domain-analyzer`
- Status: **done**
- ENTRY: `ACCEPT`
- Overall contract-freeze status: **partial** — 4 of 5 questions resolved and frozen;
3 items remain genuinely open (see `Open decisions`); `total_throughput` is

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/P2-B0-CONTRACT-20260911-R71.md`：**
The R65 scorecard ambiguity is resolved as follows. (1) `C1/C4/C5/C6/C8` are
**concurrency levels**; the capital-`C` mamba-ratio tiers are a 3090-line legacy scheme
that must be renamed. (2) `total_throughput` is **undefined** by any authorized source
and is a single hard blocking user decision. (3) The scorecard schema is frozen at the
semantic level (scenario classification, true-streaming TTFT P95, `cache-induced idle`
definition, four-term split with non-overlap and reconciliation-residual rules), but
the current engine has **no request-level duration seam** for `restore_wait`,
`queue_wait`, or `compute` (only `decode` is client-derivable with streaming TTFT);
observability requires either a new observation-only seam or an explicit
`not computable` acceptance. (4) The capacity-matrix axes are undefined in 3060
evidence; a concrete default (`N ∈ {1,4,5,6,8}` × `H ∈ {55K,64K,128K,192K}` with the
listed mandatory cells) is proposed for ratification. (5) Three items genuinely require
the user; everything else is frozen or marked inferred.

### 报告列出的产物/证据
- `phase2-hicache-design/work/P2-B0-CONTRACT-20260911-R71.md`：- Coordination contract: `.../sglang-3090-24g-hicache/.memory/phase2-hicache-design/plan.md`
  (`:11-19` fixed gates/targets; `:16` scorecard; `:17` throughput separation; `:18`
  scenario scope; `:93-101` P2-B0; `:103-111` P2-B1; `:152-158` stop/evidence; `:166`
  open issue).
- Coordination ledger user rulings: `.../hicache/.../ledger.md:4480-4520`, `:4543-4593`
  (esp. `:4562-4591`, and the `cache-induced idle` ruling `:4584-4587`).
- Coordination context: `.../hicache/.../context.md:16-22`.
- `opt` memory: `plan.md:35-44,59-63`; `ledger.md:24-51`; `work/P2P3Q-READINESS-20260911-R65.md`.
- Scorecard schema precedents (not authoritative specs):…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P2-B0-CONTRACT-20260911-R71.md` → `.memory/phase2-hicache-design/work/P2-B0-CONTRACT-20260911-R71.md`; SHA256 `2d37e2720bc27739bc82f49b2a7b7d6462983896e78e7f52988e2d2034911bcb`; source state `tracked`
