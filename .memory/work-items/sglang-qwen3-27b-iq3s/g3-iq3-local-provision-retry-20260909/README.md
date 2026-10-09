# G3-IQ3-LOCAL-PROVISION-RETRY-20260909

- **工作标题：** G3-IQ3-LOCAL-PROVISION-RETRY-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
续跑经批准的本机 IQ3 provision：以 hash-pinned wheelhouse 安装 Torch/CUDA runtime、恢复既有模型下载、补齐经过授权的 Python runtime 依赖，并完成无 GPU 的 import 与模型文件身份验收。

## 实际改了什么
报告记录分阶段完成 wheelhouse 离线安装（含 torch 2.13.0+cu130、triton）、Pillow/torchvision/IPython 等批准依赖安装，并续传原有 GGUF；期间多次 import 发现并补齐 numpy、transformers、flashinfer 等缺项。未更改产品源码，未启动服务或分配 GPU。模型下载未删除/替换原文件。

## 生成结果与验收
虽然报告中间多次标 pending，最终 Finalization 明确 invocation **done**：GGUF 完整为 11,771,546,784 bytes，SHA-256 `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810` 匹配批准值；无 GPU import verification 通过，含 torch 2.13.0+cu130、torchvision 0.29.0+cu130、numpy 2.5.3、transformers 5.12.1、flashinfer 0.6.17 与 editable SGLang 0.5.20.dev16+g5c5f5e3b2。只证明本地 provision/import/model integrity，不等于 GPU kernel build 或 serving smoke 验收。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-PROVISION-RETRY-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-PROVISION-RETRY-20260909.md`; SHA256 `6b752695ca836f239454baa58d4fd90fee3b93fbbdde6536a22283a08c6250bd`; source state `local-only`
