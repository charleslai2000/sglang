# G3-IQ3-LOCAL-PROVISION-20260909

- **工作标题：** G3-IQ3-LOCAL-PROVISION-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在授权本地实验目录准备 IQ3/SM86 运行所需的隔离 venv、目录结构与批准模型，并完成 hash-locked cu130 runtime dependencies provisioning；不使用 GPU 测试。

## 实际改了什么
在 `/mnt/data/qwen3-g3-baseline/` 建立 venv/models/build/artifacts/locks 目录，记录授权模型 URL/tree，并开始下载目标 GGUF。只做 `CUDA_VISIBLE_DEVICES=''` 安装检查，未启动/停止 GPU process 或服务。

## 生成结果与验收
任务 **blocked_on_dependency_network**：模型下载仍进行中（报告时约 4.5%，未有最终 size/hash）；模型仓库无 tokenizer/config/chat-template sidecars，不允许擅自替换模型。两个官方 cu130 wheel 尝试在 nvidia-cudnn/nvidia-cublas hash integrity 失败，未绕过 hash；Torch/runtime import 未完成。SM86 shared object 构建不在此项范围。需可校验 wheel cache 或修复 index/network 后再续；不能把启动中的模型下载视为完成。
invocation: INV-G3-IQ3-LOCAL-PROVISION-001



## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-PROVISION-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-PROVISION-20260909.md`; SHA256 `08a2979ebdd011e206874bfd53922bf9277630daca133b34187a807974c1588c`; source state `local-only`
