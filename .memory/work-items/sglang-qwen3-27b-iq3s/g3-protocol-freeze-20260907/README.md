# G3-PROTOCOL-FREEZE-20260907

- **工作标题：** G3-PROTOCOL-FREEZE-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
冻结 G3 性能矩阵 workload/scorecard 协议，并在执行前指出 runner 语义与固定长度、并发上限、prefill 统计及 telemetry 之间的未决冲突。

## 实际改了什么
仅写入本地 specialist report；报告明确没有 benchmark、API call、remote mutation、service restart 或 product/MMQ edit。

## 生成结果与验收
协议未能完整冻结：`random_range_ratio=0` 并非固定 ISL/OSL；3 个 built-in warmups 在 C semaphore 外并发；prefill prompts 数未定；client/backend/dataset binding、性能服务器容量参数与 telemetry 方法也未解决。结果是要求 fresh Task ID 先裁定这些绑定再启动 benchmark；invocation 文档完成不等于有可执行/已接受的 benchmark protocol。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROTOCOL-FREEZE-20260907.md` → `.memory/g3-smoke-protocol-validation/work/G3-PROTOCOL-FREEZE-20260907.md`; SHA256 `47d4ebb49f2bd51d58caa2b796032842b0602d21d8e0afac41afbe20a00ca5b8`; source state `local-only`
