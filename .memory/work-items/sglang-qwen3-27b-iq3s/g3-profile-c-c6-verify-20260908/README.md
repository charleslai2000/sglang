# G3-PROFILE-C-C6-VERIFY-20260908

- **工作标题：** G3-PROFILE-C-C6-VERIFY-20260908
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
独立只读复核 Profile C6（并发 6）三次 decode 原始结果、服务容量/身份、GPU telemetry 与数据完整性，报告通过范围及证据限制。

## 实际改了什么
tester 只读复制并逐项核验远端 `measure/` artifacts；未启动 workload、未修改产品文件、未加入 audit/tracing 或 telemetry 进程。交付 verification report 与本地 raw copy/hash comparison evidence。

## 生成结果与验收
Verdict **PASS_WITH_EVIDENCE_LIMITATION**：33 个 measure 文件远端/本地 SHA256 一致；报告核对候选服务与 effective C6 admission capacity、三次 native runner workload 与 telemetry。此为对保存的 C6 run 的独立验证，未运行新 workload。报告明确的缺失/不一致证据仍作为限制；不扩展为无条件验收。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-PROFILE-C-C6-VERIFY-20260908.md` → `.memory/g3-performance-and-serving/work/G3-PROFILE-C-C6-VERIFY-20260908.md`; SHA256 `f4c69cdcd6c5315c40d2079b0efefc5e7b5603fc0cc2820aefef37495d4ada80`; source state `local-only`
