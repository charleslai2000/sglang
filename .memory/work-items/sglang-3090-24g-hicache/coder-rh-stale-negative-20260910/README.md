# CODER-RH-STALE-NEGATIVE-20260910

- **工作标题：** CODER-RH-STALE-NEGATIVE-20260910
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/CODER-RH-STALE-NEGATIVE-20260910.md`：**
artifacts:
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py
evidence:
- Inspected the final review finding and the production lifecycle. The successful RH issue path previously left an existing SPEC_BUDGET negative entry in place; this could be re-considered on a later unrelated causal pass when the request remained eligible.
- Implemented the smallest lifecycle fix in `_ready_horizon_pass`: after a successful issue, consume the prior negative entry. The production restore state machine and active attempt now own retries; no stale release history remains attached to the request.
- Extended the real-helper ABA regression to call `UnifiedRadixCache.reserve_prefetch`/`release_prefetch`, perform a complete 0 -> N -> 0 release cycle, then add a later unrelated frontier event and assert no duplicate issue. The test also asserts the request is RESTORING and the negative entry is consumed.
- `python3 -m py_compile /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py` passed.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/CODER-RH-STALE-NEGATIVE-20260910.md` → `.memory/phase2-hicache-design/work/CODER-RH-STALE-NEGATIVE-20260910.md`; SHA256 `1f433f623146bdab8e45f208b749e24f00a93e79c030aad149a700e917a4c571`; source state `tracked`
