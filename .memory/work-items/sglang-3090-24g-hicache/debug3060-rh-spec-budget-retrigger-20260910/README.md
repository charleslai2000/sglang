# DEBUG3060-RH-SPEC-BUDGET-RETRIGGER-20260910

- **工作标题：** DEBUG3060-RH-SPEC-BUDGET-RETRIGGER-20260910
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/DEBUG3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`：**
- task_id: `D3060-RH-SPEC-BUDGET-RETRIGGER-20260910`
- invocation_id: `INV-20260910-DEBUG-RH-SPEC-BUDGET-R1`
- epoch: `20260910-rh`
- role/capability: `debugger-deep` / L2 (hard causal debugging)
- workdir: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- observed workspace root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` (matched before task reads)
- memory_root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design`
- memory_inputs: [`OPS3060-HICACHE-RESTORE-R3-20260910.md`](./OPS3060-HICACHE-RESTORE-R3-20260910.md)

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/DEBUG3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`：**
The `SPEC_BUDGET` negative-cache entry for B captures the **pre-issue**
`spec_budget` snapshot (zero), rather than the actual speculative-inflight
value at the time A's issue exhausts the budget (54,999).  The release rule is
correctly strict: it clears only when `current_spec_budget < epoch_cursor`.
Consequently the real `54,999 -> 0` release evaluates as `0 < 0`, false, and
B remains parked.  When ordinary scheduling later admits B, its RH stage was
never performed, which explains the observed `cached_tokens=0` path.

### 报告列出的产物/证据
- `phase2-hicache-design/work/DEBUG3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`：- Design/live input read: `OPS3060-HICACHE-RESTORE-R3-20260910.md`. It
  confirms the 55K prompt shape and declares multi-session RH-ON staging an
  open area; the prompt supplied the incident-specific trace facts.
- Target checkout: `a96dc148c208d31d6c4b291370ee4e233063c60a` (`fix(hicache):
  avoid tensor truth test in RH telemetry`). Target product files and tests
  were unchanged by this diagnosis.
- Source reconstruction: `scheduler.py:4637-4666`, `4764-4887`,
  `4899-4923`; `ready_horizon.py:309-382`, `434-467`, `546-564`; and
  `unified_radix_cache.py:5106-5143`.
- Isolated execution of the exact parsed `entry_cleared` source (with only
  dependency stubs) produced:…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/DEBUG3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md` → `.memory/phase2-hicache-design/work/DEBUG3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`; SHA256 `1877e97f777a7e3bc4b3776dd169f86e5721d22494fe78a9e7c8641d6adb5804`; source state `tracked`
