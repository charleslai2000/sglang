# G3-E3-SMOKE-NATIVE-20260907

- **工作标题：** G3-E3-SMOKE-NATIVE-20260907
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
执行恰好一次 uninstrumented native SGLang serving smoke，核验冻结 v1 服务未变、固定 2048/512 请求成功、flush 与生成均来自 loopback，并保存可复审客户端/服务证据；不启动正式矩阵。

## 实际改了什么
在获准 host/service 上发起一条 benchmark runner 请求并保存 run artifact。没有重启/重配服务、下载模型、改产品、注入 audit hook/sitecustomize/preload 或 interposer；先前失败 smoke artifacts 未改动。

## 生成结果与验收
Smoke 完成：native client exit 0，单条 JSONL 为 `completed=1`、输入 2048、输出 512；服务日志有一次成功 `/flush_cache` 与一次 `/generate` HTTP 200，且 prefill `#new-token: 2048`。pre/post health 200，loads idle，服务 PID/cmdline 保持冻结身份。此为单请求 smoke gate，不是正式 C1/C4/C5 或 Profile C 矩阵性能验收。报告保存 command/env/stdout/stderr/result、服务快照、source hash、进程/RSS、连接与 server-log evidence。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-E3-SMOKE-NATIVE-20260907.md` → `.memory/g3-smoke-protocol-validation/work/G3-E3-SMOKE-NATIVE-20260907.md`; SHA256 `121ac521c54523fef531dcd0556bfbc022d7a477ee199be8bed5d44ef18e4644`; source state `local-only`
