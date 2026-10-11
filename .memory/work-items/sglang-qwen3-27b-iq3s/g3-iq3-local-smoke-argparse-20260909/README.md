# G3-IQ3-LOCAL-SMOKE-ARGPARSE-20260909

- **工作标题：** G3-IQ3-LOCAL-SMOKE-ARGPARSE-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
针对 stable Task `G3-IQ3-LOCAL-SMOKE-20260909` 的 `launch_server --help` preflight 失败，按升级请求定位最小、非产品代码 workaround；约束为无 GPU lock、无服务启动、无源码更改，保持冻结 launch 参数语义。

## 实际改了什么
此 escalation packet 记录 L4→L2 debug 子任务的范围、前序已知事实与待回答问题；没有执行 GPU/服务操作或源码改动。实际 root cause 与 workaround 分析见同 Task 下独立的 `G3-IQ3-LOCAL-SMOKE-ARGPARSE-DEBUG-20260909.md`，不能将 escalation 本身算作修复。

## 生成结果与验收
本文件是受理/转派材料：确认 `--help` 在 Python 3.12 发生 argparse `%o` TypeError，并要求调查受支持入口或安全 workaround；不含最终分析结论或 smoke 执行结果。后续 debug 报告最终定位为 help text 字面量 `67%` 被 argparse 旧式插值解释，并验证 frozen argv 的 `prepare_server_args()` 无 GPU 预检通过；这些结论来自另一个报告，不能归为本 escalation 的执行产物。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/escalations/G3-IQ3-LOCAL-SMOKE-ARGPARSE-20260909.md` → `.memory/g3-smoke-protocol-validation/escalations/G3-IQ3-LOCAL-SMOKE-ARGPARSE-20260909.md`; SHA256 `f38809800ed189f47996978f9f6a7caa673031bdfe96012763532a1502fe8ab8`; source state `local-only`
