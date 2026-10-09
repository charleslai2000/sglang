# P1-ACCEPTANCE-CONDITIONS

- **工作标题：** P1-ACCEPTANCE-CONDITIONS
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
冻结 R120 SPEC_BUDGET full-chain 的用户批准验收标准，确保单一 target T 身份连续、真实 durable coverage、唯一 park 原因、release→wake 因果、完整 KV+Mamba restore 与运行前 host headroom 均可证。

## 实际改了什么
这是规范/验收合同文件，没有代码修改或实验执行。规定禁止 decoy、产品改动、instrumentation、扩大 workload；条件不全只能报告 NOT_VERIFIED。

## 生成结果与验收
冻结 C1–C5：storage-backed 且 Mamba sidecar durable 的 full T coverage；SPEC_BUDGET 唯一 park（排除 HOST_ALLOC/DEVICE_QUOTA 等）；F1 exactly-once release 使 epoch +1 并因果唤醒 T；FULL disposition、KV/Mamba 数量完整且无 partial/recompute/discard；运行前证明 F1+T+margin 小于正确 basis 的 host allocable。PARTIAL 即 FAIL，缺少 `restore_recompute` 不足以证明完整。只有单一冻结 bundle 五项全过才可 closure PASS；本文件本身不代表 R120 已实测或关闭。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R120-bundle/P1-ACCEPTANCE-CONDITIONS.md` → `.memory/rh-p1-durable-replay-eviction/R120-bundle/P1-ACCEPTANCE-CONDITIONS.md`; SHA256 `b5ffa106be7863a2baedd528249eb6bccb63469619af73970a4c477813c27822`; source state `tracked`
