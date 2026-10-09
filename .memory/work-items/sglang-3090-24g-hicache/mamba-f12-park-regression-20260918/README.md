# MAMBA-F12-PARK-REGRESSION-20260918

- **工作标题：** MAMBA-F12-PARK-REGRESSION-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/MAMBA-F12-PARK-REGRESSION-20260918.md`：**
Terminal live verification: do the two already-completed code repairs (D1 + D2) actually
fix the Mamba L2 long-tail pin defect, verified against the REAL 42-park failure signature
on a live run?

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/MAMBA-F12-PARK-REGRESSION-20260918.md`：**
**PASS for D1 (the defect signature no longer reproduces); D2 remains unit-verified only and
is NOT independently live-observable in this run.**
Two live runs with the *same* deterministic backend-failure induction and the *same* load:
| Arm | Tree | Park events | WAIT_CAPACITY | admitted/failed | lock_release_evictable (in-run) |
| --- | --- | --- | --- | --- | --- |
| FROZEN (control) | frozen `src/python` only | **64** | 1334 | 189 / 3 (3 `TimeoutError`) | **0** |
| REPAIRED | frozen + ONLY D1/D2 | **0** | 0 | **192 / 0** | **2** (kv and mamba) |
Per-criterion:
1. **Generator advances — PASS.** Frozen stalls: first park 12:29:22, last park 12:39:09,
   load wall 937 s, TTFT max 184.06 s, 3 requests timed out, and 53 of 64 parks captured the
   same frozen mamba generation `77` (12:29:47 → 12:39:09, ~9.4 min). Repaired: 192/192
   admitted, 0 failed, wall 385 s, TTFT max 15.71 s, 0 parks, 0 `WAIT_CAPACITY`.
2. **Pins released DURING the run — PASS.** Repaired console lines 946–947 (raw
   `host_allocability_change`, `cause=lock_release_evictable`, `ts_wall_ms` 1789733666725/6)


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/MAMBA-F12-PARK-REGRESSION-20260918.md` → `.memory/phase2-hicache-design/agents/MAMBA-F12-PARK-REGRESSION-20260918.md`; SHA256 `0b67415357c2856eafdc726d95599de79b5254495c7353e95c291a7e0134bbab`; source state `tracked`
