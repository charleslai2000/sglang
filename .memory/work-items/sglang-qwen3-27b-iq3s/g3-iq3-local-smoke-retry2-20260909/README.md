# G3-IQ3-LOCAL-SMOKE-RETRY2-20260909

- **工作标题：** G3-IQ3-LOCAL-SMOKE-RETRY2-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在已修复部分 imports 后，针对本机 RTX 3090/GPU1、指定 venv/checkpoint 和端口 18035 重试隔离 serving startup，验证能否通过健康检查进入 smoke。

## 实际改了什么
只在 GPU lock 下启动一次冻结 argv 服务并保存进程/启动日志；未发送 benchmark request、未改产品文件/driver/CUDA，也未触碰其他进程。模型仅核实文件身份，没有加载。

## 生成结果与验收
Invocation `INV-G3-IQ3-LOCAL-SMOKE-003` / epoch E15 服务在 health 200 前因缺少 `partial_json_parser` 退出。无 benchmark 请求、无模型 load；server PID 退出，端口与 GPU lock 释放。状态 **blocked**，不得用替代 workload；需经新 invocation 补齐批准依赖并重试。raw evidence/hash 见来源报告。

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-SMOKE-RETRY2-20260909.md`：Raw artifacts:
`.memory/g3-baseline-20260907/work/raw/g3-iq3-local-smoke-retry2-20260909/`
This contains queue timing, server PID/log, runner help, post-check GPU telemetry, and
`SHA256SUMS`. The copied artifact directory is
`/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909-retry2/`.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-SMOKE-RETRY2-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-SMOKE-RETRY2-20260909.md`; SHA256 `34ffc2a998232766672576b7e643e1c70f0063b1643a5623d505e9af07e58655`; source state `local-only`
