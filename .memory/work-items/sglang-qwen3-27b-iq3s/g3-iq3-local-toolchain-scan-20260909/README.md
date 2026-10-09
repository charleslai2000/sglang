# G3-IQ3-LOCAL-TOOLCHAIN-SCAN-20260909

- **工作标题：** G3-IQ3-LOCAL-TOOLCHAIN-SCAN-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
只读盘点本地 IQ3/SM86 build 所需 toolchain、venv、wheelhouse、模型与 GPU 状态，确认后续机械构建可用条件。

## 实际改了什么
只执行 toolchain/package/filesystem/GPU inventory；没有安装 package、构建、启动 GPU workload 或改变资源。transcript 与 hash report 保存在原始 raw directory。

## 生成结果与验收
观察到 CMake 4.4.3、CUDA 13.0 nvcc 存在但不在 PATH；系统 Python 无 torch/sglang/sgl_kernel/triton/ninja，`uv` 缺失，目标 venv/wheels 目录未建立。RTX 3090 与 GGUF 存在，但 GPU 仅是扫描时状态，测试前仍须 queue lock。该扫描只说明环境盘点事实，不代表 AOT build ready 或 SM86 artifact 存在。
Complete command transcript is [scan.txt](raw/g3-iq3-toolchain-scan-20260909/scan.txt); hashes are in [hashes.txt](raw/g3-iq3-toolchain-scan-20260909/hashes.txt).
- CMake: `/usr/local/bin/cmake`, version 4.4.3.
- CUDA: `/usr/local/cuda -> /usr/local/cuda-13.0`; `nvcc` exists at `/usr/local/cuda/bin/nvcc` and `/usr/local/cuda-13.0/bin/nvcc` (30,161,576 bytes), but is not on `PATH` (`which nvcc` failed). Explicit `/usr/local/cuda/bin/nvcc --version` reports release 13.0, V13.0.48. Include/lib64 symlinks exist.
- Compilers: `/usr/bin/gcc` and `/usr/bin/g++`, Ubuntu 13.3.0-6ubuntu2~24.04.1.
- Python: `/usr/bin/python3` 3.12.3; pip 24.0 system package. `uv` absent.
- System Python import probes found no `torch`, `sglang`, `sgl_kernel`, `triton`, or `ninja`; filtered pip list likewise had no relevant packages. No `/mnt/data/qwen3-g3-baseline/venv`, `wheels`, or `wheelhouse` directories were present.
- `/mnt/data/qwen3-g3-baseline` remains with `artifacts`, `build`, `locks`, `models`, and `toolchain`; model present at `models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`, 11,771,546,784 bytes. SHA-256: `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810`.
- GPU 1 is an NVIDIA GeForce RTX 3090, UUID `GPU-2e3ed202-3655-d919-0a64-259209bc6587`, 24,576 MiB total / 53 MiB used / 0% utilization at scan time. GPU 0 is a GT 1030 and reported 885 MiB used.



### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-TOOLCHAIN-SCAN-20260909.md`：Complete command transcript is [scan.txt](raw/g3-iq3-toolchain-scan-20260909/scan.txt); hashes are in [hashes.txt](raw/g3-iq3-toolchain-scan-20260909/hashes.txt).
- CMake: `/usr/local/bin/cmake`, version 4.4.3.
- CUDA: `/usr/local/cuda -> /usr/local/cuda-13.0`; `nvcc` exists at `/usr/local/cuda/bin/nvcc` and `/usr/local/cuda-13.0/bin/nvcc` (30,161,576 bytes), but is not on `PATH` (`which nvcc` failed). Explicit `/usr/local/cuda/bin/nvcc --version` reports release 13.0, V13.0.48. Include/lib64 symlinks exist.
- Compilers: `/usr/bin/gcc` and `/usr/bin/g++`, Ubuntu 13.3.0-6ubuntu2~24.04.1.
- Python: `/usr/bin/python3` 3.12.3; pip 24.0 system package. `uv` absent.…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-TOOLCHAIN-SCAN-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-TOOLCHAIN-SCAN-20260909.md`; SHA256 `ded2cc6c05b75a558a8a9d73cf9cebb16579fa6cb21d73ba029ef3a2a657d5d3`; source state `local-only`
