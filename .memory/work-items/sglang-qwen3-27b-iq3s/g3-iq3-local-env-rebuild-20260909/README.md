# G3-IQ3-LOCAL-ENV-REBUILD-20260909

- **工作标题：** G3-IQ3-LOCAL-ENV-REBUILD-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
重建独立 Python 3.12.3 venv，并用 hash-locked wheelhouse 安装 Torch/CUDA 依赖，继而安装 editable SGLang 与验证 import，为后续本地 smoke 准备环境。

## 实际改了什么
在 `/mnt/data/qwen3-g3-baseline/{venv,wheels,build,artifacts}` 重建 venv，使用 requirements 原样执行 `pip download --only-binary=:all: --require-hashes`；未更改 requirements 或产品源码，未运行服务、benchmark、GPU kernel，也未使用 GPU lock。网络读取中断后确认下载进程并停止已识别重复进程。

## 生成结果与验收
环境重建 **blocked**：60.4 MB 的 `nvidia-nvshmem-cu13` wheel 下载读超时，未完成任何 wheel；离线 install 随即因缺少 `MarkupSafe==3.0.2` 失败。Torch/editable SGLang install/import 均未进行，不能算环境验收。后续应同样 hash-pinned 下载在网络可用时重试，不得绕过 hash 或换包；原报告所列 toolchain 仅是观测值。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-ENV-REBUILD-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-ENV-REBUILD-20260909.md`; SHA256 `bc4e56d3726b175e15689ccca577469ca9b0681caee482111a076a046696e5e5`; source state `local-only`
