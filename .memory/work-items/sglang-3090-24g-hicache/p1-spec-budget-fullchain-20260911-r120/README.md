# P1-SPEC-BUDGET-FULLCHAIN-20260911-R120

- **工作标题：** P1-SPEC-BUDGET-FULLCHAIN-20260911-R120
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/P1-SPEC-BUDGET-FULLCHAIN-20260911-R120.md`：**
- task_id: `P1-SPEC-BUDGET-FULLCHAIN-20260911-R120`
- invocation: `ses-p1-spec-budget-fullchain-r120-20260911` (fresh)
- role: `tester`
- epoch: `2026-09-11`
- status: **not_verified** (verification executed to completion; P1 does NOT close)
Frozen acceptance file verified before starting:
`work/R120-bundle/P1-ACCEPTANCE-CONDITIONS.md` sha256
`b5ffa106be7863a2baedd528249eb6bccb63469619af73970a4c477813c27822` (matches;

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** not_verified

**`phase2-hicache-design/work/P1-SPEC-BUDGET-FULLCHAIN-20260911-R120.md`：**
The single clean no-decoy line (one F1 + one T, distinct build sessions, one
`input_ids` batch replay `prompt=[[F1],[T]]`) was run 3× under the frozen R117
profile. **The SPEC_BUDGET park does not occur and the chain is not produced.**
At the replay, T is already device-resident (`device_hit_tokens=27520/27521`),
so its prefetch is declined `too_short` and T is never a speculative candidate.
F1 is 95 % device+host resident (`device_hit=36864`, `host_hit=4096`), so its
replay prefetch is only **2047 tokens** — far below the 39321 speculative limit:
the budget is never exhausted, nothing parks, and T is recomputed
(`disposition=RECOMPUTE reason=too_short`). Upstream, neither build reached full
L3 durability (frozen `storage_persisted`: F1 20 nodes/40958 of 43008; T 1
node/2046 of 27521). The no-decoy workload supplies no eviction/write-back
pressure, and the live host pool is near-saturated (free+evictable 28672 <
F1+T 70529), so the evicted suffix is not written through. All five frozen
conditions are unmet.

### 报告列出的产物/证据
- `phase2-hicache-design/work/P1-SPEC-BUDGET-FULLCHAIN-20260911-R120.md`：| file | sha256 |
|---|---|
| `raw.log` (frozen server slice lines 2051152–2107393, 56242 lines) | `0cb8ea6bc7898f392e99e66a570e16326447f1c3e4a440064282aecd5d3f2347` |
| `probe.log` (frozen probe slice beyond byte 33890204) | `7936097d8a6de7ce8c76efab659ae31967aa2b4bfaa1bd37fcf5d93c597287b1` |
| `requests.jsonl` (complete transcript incl. batch terminal response) | `39a327bad565eb2cc0341bd7d5a2012f6f9aba96f2dbf8bc3b95a7f325ba9f17` |
| `state.jsonl` | `31d7dd015e251431ff3d1789b7fabef8b2441217b3d723a5326b070ae1abd5f4` |
| `chain.json` (per-condition C1..C5 + evidence + unmet_conditions) | `27ece4c370f2823408e2911ffd08c452c3f985d1948cf95179e9a1b9ffa531b6` |…（节选；见来源报告）

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4f41f5bab562b99562f30c67540eb05344d13637`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P1-SPEC-BUDGET-FULLCHAIN-20260911-R120.md` → `.memory/phase2-hicache-design/work/P1-SPEC-BUDGET-FULLCHAIN-20260911-R120.md`; SHA256 `4c3cc39fe4def49cda66aeff9670f85b2dd30a0c23a659473bb4c5d0c1fe6ba4`; source state `tracked`
