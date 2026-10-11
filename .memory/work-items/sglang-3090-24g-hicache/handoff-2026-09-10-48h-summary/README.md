# HANDOFF-2026-09-10-48H-SUMMARY

- **工作标题：** HANDOFF-2026-09-10-48H-SUMMARY
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/HANDOFF-2026-09-10-48H-SUMMARY.md`：**
On the RTX 3060 12G target, optimize the complete HiCache hierarchy end to end:
L1 GPU, L2 host RAM, and L3 persistent storage. The desired steady state is that
L3→L2 staging for the next task overlaps current GPU computation, so task
switch/admission does not synchronously wait for L3. Outcome metrics are GPU
utilization approaching 100%, `TTFT <1s` as an optimization target (not an
absolute gate), total throughput, aggregate TPS, and c4/c5/... scenario gains.
The earlier `TFTT` reference was the user's typo and is not a required metric.
Additionally, the capacity baseline must always record the complete server
arguments. The apparent `FP8 KV≈65,536` versus allocator `≈193,294` token
 difference must not be treated as a contradiction until mem-fraction, mamba
ratio, max-total-tokens, and related profile parameters are compared.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。

### 报告列出的产物/证据
- `phase2-hicache-design/work/HANDOFF-2026-09-10-48H-SUMMARY.md`：- Dependency-complete focused RH runtime tests are **PENDING**. The local interpreter
  lacks pytest/orjson/msgspec/torch. A remote environment `/root/sglang-env-3060-4b`
  exists in prior evidence; an earlier focused remote run passed the two new
  SPEC_BUDGET tests but had six pre-existing fixture/API failures in the broader file.
- Clean post-fix 3060 blocker+A/B OFF/ON acceptance is **NOT VERIFIED**. The previous
  driver/join bundle and stable RID→intended-A/B mapping are unavailable; later
  x/y/z/w/q runs cannot be relabeled as the old A/B. Therefore B-specific cursor,
  release wake, host-ready-before-admission, no cached=0, and no recompute claims remain
  unestablished.…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/HANDOFF-2026-09-10-48H-SUMMARY.md` → `.memory/phase2-hicache-design/work/HANDOFF-2026-09-10-48H-SUMMARY.md`; SHA256 `6956be5b3aab238c447d8ffa5488155c7f06c43f4b714479788b00bb56771ecd`; source state `tracked`
