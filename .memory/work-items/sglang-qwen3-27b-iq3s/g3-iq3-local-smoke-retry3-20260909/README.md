# G3-IQ3-LOCAL-SMOKE-RETRY3-20260909

- **工作标题：** G3-IQ3-LOCAL-SMOKE-RETRY3-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在隔离 RTX 3090 smoke 前执行不触碰 GPU 的启动入口预检；只有 `sglang.launch_server --help` 成功后才继续获取 GPU queue/启动流程。

## 实际改了什么
只执行 local-only、`CUDA_VISIBLE_DEVICES=''` 的入口命令；未获取 GPU lock、启动 server/benchmark/GPU process、停止其他进程或修改 repository/product 文件。

## 生成结果与验收
预检失败（exit status 1）：导入 `sglang.srt.configs.internvl` 时缺少 `sentencepiece`。因此未获取 GPU lock，也未启动 smoke；工作被依赖阻塞。后续须在授权环境安装批准依赖后，以新 invocation 重跑同一预检。

### 产物/证据
stdout/stderr 和退出码分别记录于 `work/raw/g3-iq3-local-smoke-retry3-20260909/preflight-help.txt` 与 `preflight.rc`。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-SMOKE-RETRY3-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-SMOKE-RETRY3-20260909.md`; SHA256 `fe461f11777a7e696eba0e890a540c4534df97f31e303d85e7907846ac588f9a`; source state `local-only`
