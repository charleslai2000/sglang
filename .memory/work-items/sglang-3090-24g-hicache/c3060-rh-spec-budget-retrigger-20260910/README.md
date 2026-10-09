# C3060-RH-SPEC-BUDGET-RETRIGGER-20260910

- **工作标题：** CODER3060-RH-SPEC-BUDGET-RETRIGGER-20260910
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/CODER3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`：**
stable_task_id: C3060-RH-SPEC-BUDGET-RETRIGGER-20260910
invocation_id: INV-20260910-CODER-RH-SPEC-BUDGET-R1
epoch: 20260910-rh
role: coder
branch: 3060-12g-qwen35-4b

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** blocked

**`phase2-hicache-design/work/CODER3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`：**
- Post-issue SPEC_BUDGET parking now builds a causal epoch snapshot with the observed `cc.inflight_speculative_tokens`, so a tail candidate records cursor N after the issue rather than the pre-issue cursor.
- SPEC_BUDGET parking is now gated on the speculative limiter. A physical-only limiter stops the pass without assigning a speculative negative-cache cursor.
- Added regressions for post-issue cursor attribution plus clearing/reissue when the current speculative budget drops below the cursor, and for the physical-only distinction.
- No commit, deployment, or unrelated product-file edits were performed.

### 报告列出的产物/证据
- `phase2-hicache-design/work/CODER3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`：- `python/sglang/srt/managers/scheduler.py`
- `3090-dev/test_ready_horizon_unit.py`

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/CODER3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md` → `.memory/phase2-hicache-design/work/CODER3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`; SHA256 `7b27cbd60c5a1921ce1f54311a12f507cc3cfa958222679ace65af0cccec5bf8`; source state `tracked`
