# G3-MATRIX-PROTOCOL-20260907

- **工作标题：** G3-MATRIX-PROTOCOL-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
只读查找 G3 C1/C4/C8/C16 baseline matrix 的权威协议，判断是否已有可执行且可复核的 workload/scorecard 定义；避免协议缺失时启动不可比较的 benchmark。

## 实际改了什么
只读检查 Git history、scripts 与 `/data/qwen3-g3-baseline` 中现有材料；未发 benchmark/API request，未改变 frozen baseline process，也没有产品文件变更。

## 生成结果与验收
结果 **blocked**：未找到完整权威 protocol，因而没有 C1/C4/C8/C16 执行。缺失项包括 exact command、input/output lengths、seed、warmup/flush、prompt count、output schema 与 concurrency mapping。需由新 Task ID 明确这些绑定后再运行；此项不是测试结果。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-MATRIX-PROTOCOL-20260907.md` → `.memory/g3-smoke-protocol-validation/work/G3-MATRIX-PROTOCOL-20260907.md`; SHA256 `0fa34cb9fe6f1d0049451d63da6b43da616c26860f007b676bec36ceb878d4a9`; source state `local-only`
