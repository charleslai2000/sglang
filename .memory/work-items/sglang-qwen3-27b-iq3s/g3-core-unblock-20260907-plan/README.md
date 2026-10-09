# G3-CORE-UNBLOCK-20260907-PLAN

- **工作标题：** G3-CORE-UNBLOCK-20260907-PLAN
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
将 E3 授权整理成有依赖关系的可执行 DAG，覆盖既有 random-ids 活动审计、单请求 native SGLang smoke、独立 gate、冻结 v1 Production A、独立 A 验证、隔离 true-C16 Profile B admission、B decode/prefill 矩阵及恢复复核。

## 实际改了什么
产出并更新 G3 core-unblock 执行计划；报告未列出产品代码修改。计划范围仅限授权实验机 `175.155.64.171:22109`，并规定 A 阶段冻结服务不变。因已确认 E2 wrapper activity，计划补充其隔离处理边界：E2 data 不计入 E3，也不能在缺少独立 admission decision 时合并或视作已准入证据。

## 生成结果与验收
形成后续任务 DAG 与各阶段验收依赖；这是计划文档，不是任何阶段的执行或 gate 结果。每个 smoke、benchmark、Profile B transition、restore 均需依赖门槛和独立授权/验收。



## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-CORE-UNBLOCK-20260907-PLAN.md` → `.memory/g3-baseline-core-unblock/work/G3-CORE-UNBLOCK-20260907-PLAN.md`; SHA256 `9b7f4917a8524d367657a63271ad208f14e708e0a69e0c8586ed45eea2f15799`; source state `local-only`
