# G3-E3-SMOKE-EXEC-20260907

- **工作标题：** G3-E3-SMOKE-EXEC-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在 runbook drain gate 通过后，执行一次获准的 native SGLang 单请求 smoke，作为 Production A 矩阵的前置 gate；失败时不重试、不替换 workload。

## 实际改了什么
通过 admission 后启动一次 native benchmark client，RUN_ID `g3-e3-smoke-20260907T135400Z`；client 在 Python import 阶段失败。未产生 generation request，无产品文件变更记录。较早的 135120Z 目录仅是 launcher quoting preflight，不含 audit/client/result/request evidence，被报告排除。

## 生成结果与验收
Smoke **blocked**：required drain gate 通过，但 client 在 import 阶段被 audit-hook/runtime open 拒绝，未创建 generation request。按 runbook 未 retry、未替换 workload；正式 Production A 仍需解决 hook compatibility 并获得新 decision/Task ID。Remote 与 local raw roots 保存失败证据；失败目录不能当作 smoke PASS。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-E3-SMOKE-EXEC-20260907.md` → `.memory/g3-smoke-protocol-validation/work/G3-E3-SMOKE-EXEC-20260907.md`; SHA256 `591d7be7ba0155e56f1f3e1195aee46a3b822e55a0e2bd09c7f3227b202841c2`; source state `local-only`
