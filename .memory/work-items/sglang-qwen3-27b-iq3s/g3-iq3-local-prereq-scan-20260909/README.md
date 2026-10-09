# G3-IQ3-LOCAL-PREREQ-SCAN-20260909

- **工作标题：** G3-IQ3-LOCAL-PREREQ-SCAN-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
只读盘点本机对 IQ3_S/SM86 验证的先决条件：GPU 资源、模型、SGLang/PyTorch 环境、CUDA toolchain、部署路径与共享 GPU queue 要求。

## 实际改了什么
仅检查本地 workstation/repository 与只读 GPU inventory；未启动/停止 workload、未下载/安装 package 或 model、未附着用户进程。无文件变更。

## 生成结果与验收
扫描时 RTX 3090 GPU1 仅少量 desktop allocation，但须在测试前经共享 queue/lock 重新取得并复查。此机器缺少目标 `/data` 部署环境与模型；system Python 无 torch/sglang/transformers/safetensors，未找到 GGUF 权重。报告由此判定 local prerequisites 不满足；部署 checkpoint 中的远端路径不代表本地存在。属于时点性只读盘点，不是当前资源状态。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-PREREQ-SCAN-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-PREREQ-SCAN-20260909.md`; SHA256 `f6dab117a4951e1ad128302c1d682c0c7ffd28c82cdd97a48c4030ec865c1854`; source state `local-only`
