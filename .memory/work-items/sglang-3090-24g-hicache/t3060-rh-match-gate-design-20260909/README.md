# T3060-RH-MATCH-GATE-DESIGN-20260909

- **工作标题：** ARCH3060-RH-MATCH-GATE-DESIGN-20260909
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/ARCH3060-RH-MATCH-GATE-DESIGN-20260909.md`：**
ENTRY: ACCEPT
status: done
task_id: T3060-RH-MATCH-GATE-DESIGN-20260909
orchestration_epoch: 20260909-rh-ab43
role: architect
source_repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
source_branch: 3060-12g-qwen35-4b
source_revision: f629d4e2c19eb74571b4154438fd651ce24ff53b

## 实际改了什么
**`phase2-hicache-design/work/ARCH3060-RH-MATCH-GATE-DESIGN-20260909.md`：**
Authorized future implementation scope should be limited to:
- `python/sglang/srt/managers/scheduler.py` for one-shot preparation, causal
  ordering, ticket validation/consumption, and telemetry;
- a focused test file under `3090-dev/` and, if package-backed fixtures are
  available, registered scheduler tests.
No change is recommended to `schedule_batch.py`, cache tree traversal,
allocator, Unified cache finalization, Mamba component, persistence format,
HOST_ALLOC generations/FIFO, or remote/deployment files. If implementation
requires one of those files, stop and obtain a fresh architecture dispatch;
that is evidence the minimal boundary does not fit.
The implementation manifest must map actual spellings to the symbols above,
pin the descendant revision, and demonstrate that only the normal
`Req.init_next_round_input(..., cow_mamba=False)` call moved into preparation
and was consumed by RH issue. Formatting/type checks and dependency-backed

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/ARCH3060-RH-MATCH-GATE-DESIGN-20260909.md`：**
Recommend a scheduler-only, causal-gated, one-shot non-COW match preparation
whose result is consumed by the RH issue path. It repairs eligibility before
RH policy, avoids the duplicate issue-time match, fences fresh/retracted/
changed requests, preserves separate admission-time Mamba COW, leaves RH-OFF
and HOST_ALLOC unchanged, and cannot bypass Mamba flush-before-evict. Current
matching is conditionally safe for this use but is not literally read-only.

### 报告列出的产物/证据
- `phase2-hicache-design/work/ARCH3060-RH-MATCH-GATE-DESIGN-20260909.md`：- This gate-contract/design plus implementation/test contract:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/ARCH3060-RH-MATCH-GATE-DESIGN-20260909.md`
- Read-only inputs: source revision `f629d4e2c1`; accepted RH architecture,
  Pattern Intake, Novel Mechanism, and review artifacts; final RH-ON and RH-OFF
  reports; prior RH causal diagnosis.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/ARCH3060-RH-MATCH-GATE-DESIGN-20260909.md` → `.memory/phase2-hicache-design/work/ARCH3060-RH-MATCH-GATE-DESIGN-20260909.md`; SHA256 `619c225d93ccfcb9aace8690da51144597ea3450adeea7fae9a0160323703606`; source state `tracked`
