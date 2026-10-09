# G3-IQ3-DRIVER-RESEARCH-20260909

状态：done（公开资料调研；未访问任何私有主机、IP、路径、凭据、用户进程或私有日志）  
调研日期：2026-09-09  
任务：G3-IQ3-DRIVER-RESEARCH-20260909  
角色：external-researcher

## 结论

对 RTX 3090（Compute Capability 8.6 / `sm_86`）运行 CUDA 12.x、PyTorch 2.x 和 SGLang AOT CUDA 扩展，**没有公开资料表明需要因为“3090”本身升级驱动**。NVIDIA 的 CUDA 12.x minor-version compatibility 最低 Linux 驱动是 `525.60.13`；CUDA 12.8/12.9 对应的 toolkit driver 版本分别为 `570.26`/`575.51.03`（GA）。因此，输入包中所述的 **R580 系列在原则上已高于 CUDA 12.x 运行时要求**。CUDA 兼容性仍应以精确的已加载驱动版本和实际 PyTorch/CUDA runtime 验证为准。

关键区分：

1. **驱动升级解决的是运行时兼容/缺陷问题**，不会把已经构建的 `.so` 自动变成含 `sm_86` native cubin 的扩展。
2. **`sm_86` native AOT cubin 属于构建产物问题**：需在构建时把 `sm_86` 作为 real GPU code 目标（或保留可由驱动 JIT 的 `compute_86` PTX）。NVIDIA 文档明确说明 `-gencode`/`-arch` 控制 cubin/PTX 生成，运行时驱动从 fatbin 选择合适代码。
3. 所以当前优先级应是：在不升级驱动的前提下，重新构建/验证 SGLang AOT 扩展是否包含 `sm_86`；只有精确驱动低于所用 CUDA runtime 最低要求、或实测出现明确的 driver/runtime incompatibility，才考虑驱动变更。

## NVIDIA CUDA 12.x 驱动门槛（Linux x86_64）

以下版本来自 NVIDIA CUDA Toolkit 12.9.2 release notes 的 driver 表；“Toolkit Driver Version”是该 toolkit 发行时配套/开发驱动版本，“minor compatibility”总表给出 CUDA 12.x 的统一最低版本。

| CUDA toolkit | GA / update 对应的 Linux toolkit driver（最低） |
|---|---:|
| 12.0 GA / Update 1 | 525.60.13 / 525.85.12 |
| 12.1 GA / Update 1 | 530.30.02 |
| 12.2 GA / Update 1 / Update 2 | 535.54.03 / 535.86.09 / 535.104.05 |
| 12.3 GA / Update 1 | 545.23.06 / 545.23.08 |
| 12.4 GA / Update 1 | 550.54.14 / 550.54.15 |
| 12.5 GA / Update 1 | 555.42.02 / 555.42.06 |
| 12.6 GA / Update 3 | 560.28.03 / 560.35.05 |
| 12.8 GA / Update 1 | 570.26 / 570.124.06 |
| 12.9 GA | 575.51.03 |

NVIDIA 的兼容性指南将 CUDA 12.x 的 minor-compatibility 最低线概括为 Linux `>=525`，并说明较新的驱动仍通过向后兼容支持旧 toolkit 应用。故 R580 分支在版本线意义上满足上述 CUDA 12.x 门槛；若实际使用 CUDA 13.x，兼容性指南给出的 CUDA 13.x 最低驱动分支也是 `>=580`，但仍需按精确 CUDA 13 minor 版本核对。

来源：

- [NVIDIA CUDA 12.9.2 Toolkit Release Notes](https://docs.nvidia.com/cuda/archive/12.9.2/pdf/CUDA_Toolkit_Release_Notes.pdf)（Table 2/3，CUDA 12.x 最低兼容驱动与各 minor toolkit driver）。
- [NVIDIA CUDA Minor Version Compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)（CUDA 11/12/13 分支范围及后续驱动的 backward compatibility）。
- [NVIDIA CUDA/driver/architecture matrix](https://docs.nvidia.com/datacenter/tesla/drivers/cuda-toolkit-driver-and-architecture-matrix.html)（Ampere 8.0/8.6 的 CUDA 支持状态；8.6 仍在持续支持表中）。

## RTX 3090、SM86 与 AOT 构建

NVIDIA 的 GPU compute capability 页面把 GeForce RTX 3090 列为 CC 8.6；NVIDIA 的 NVCC 文档把 `sm_86` 列为 Ampere real GPU target，并说明：

- `-arch=sm_86` 生成目标架构的 PTX 与 cubin；
- `-gencode=arch=compute_80,code=sm_86` 生成 `sm_86` native cubin；
- 仅嵌入 `compute_86` PTX 时，实际 cubin 会延迟到运行时由 CUDA driver JIT；
- fatbin 可同时包含多个 `sm_*` cubin，驱动在运行时选择最合适的翻译。

这直接支持本 G3 的判断：如果预编译 `common_ops` 只含别的 native targets，**升级 R580 不会补齐缺失的 `sm_86` cubin**；应检查/修正 AOT 的 gencode，再用 `cuobjdump` 或等价工具确认最终 `.so`。如果扩展仅有可兼容的 PTX，驱动可能 JIT，但这与“有 native SM86 AOT cubin”不是同一验收条件。

来源：

- [NVIDIA CUDA GPU Compute Capability](https://developer.nvidia.com/cuda/gpus)（RTX 3090 = 8.6）。
- [NVIDIA NVCC GPU compilation documentation](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/nvcc.html)（`-arch`、`-gencode`、PTX/cubin 与 fatbin 选择）。
- [NVIDIA PTX overview](https://developer.nvidia.com/blog/understanding-ptx-the-assembly-language-of-cuda-gpu-computing/)（CC 8.6 对应 `sm_86` cubin 的说明）。

## PyTorch 2.x 与 SGLang AOT 的含义

PyTorch 官方安装页按 CUDA runtime 变体提供二进制包（例如 `cu126`、`cu128` 等），并要求用 `torch.cuda.is_available()` 检查驱动和 CUDA 是否可访问。PyTorch 的 C++/CUDA extension 文档说明，扩展构建会依据可见 GPU/指定架构生成代码，并可通过 `CUDA_HOME` 等选择本地 CUDA 工具链；这意味着：

- PyTorch wheel 的 CUDA runtime 选择和主机 NVIDIA kernel driver 是两个层次；
- 本地 AOT 扩展的 `nvcc`/gencode 目标仍决定 `.so` 内是否有 `sm_86`；
- 驱动满足 runtime 最低版本是必要条件，但不是 native cubin 存在性的充分条件。

SGLang 官方贡献文档把 AOT `sglang-kernel` 定义为单独的 kernel 包，要求 AOT kernel 在 `python/sglang/kernels/aot/` 下实现、更新注册/CMake、添加 correctness test 和 benchmark，并在该目录构建测试。当前公开的 SGLang AOT CMake 文件中，`ENABLE_BELOW_SM90` 的 common-ops flags 展示了 `sm_80` 与 `sm_89`，而可选 FA3 的 SM8x 分支单独展示 `sm_86`；这说明“某个 wheel/target 没有 `sm_86`”可能是构建矩阵/打包选择，不应直接归因于驱动。

来源：

- [PyTorch Start Locally](https://pytorch.org/get-started/locally/)（CUDA wheel 选择与 `torch.cuda.is_available()` 检查）。
- [PyTorch previous versions](https://pytorch.org/get-started/previous-versions/)（各 PyTorch 2.x 的 CUDA wheel 变体）。
- [PyTorch C++/CUDA extension documentation](https://docs.pytorch.org/docs/main/cpp_extension.html)（扩展的 CUDA 工具链与架构代码生成）。
- [SGLang contribution guide](https://docs.sglang.io/docs/developer_guide/contribution_guide)（AOT package、源码位置、注册/CMake、测试和构建要求）。
- [SGLang AOT CMakeLists.txt](https://raw.githubusercontent.com/sgl-project/sglang/main/python/sglang/kernels/aot/CMakeLists.txt)（公开构建 flags；请注意 upstream 版本可能与本地 checkout 不同）。

## 保守建议

1. **当前不要在 `gpu-burn` 运行期间升级驱动。** NVIDIA 官方安装指南的标准流程包含驱动包升级和重启；这类 host-wide 操作会中断现有 GPU 作业，且不能替代 AOT 重新编译。先让验收测试完成，保存精确驱动版本、CUDA runtime/toolkit 版本，再单独安排维护窗口。
2. 在当前 R580 分支保持不变，先完成隔离 AOT 构建验收：检查 `sm_86` native cubin、加载/import、一个最小 CUDA/PyTorch kernel smoke，以及目标 SGLang operator 的 correctness/graph replay。不要因为 `.so` 缺少 `sm_86` 就先升级驱动。
3. 仅当后续精确版本证明低于所用 runtime 的 NVIDIA 最低驱动，或最小复现明确报 driver/runtime incompatibility，才升级；升级前应保存旧驱动/包状态、安排重启窗口，并在空闲后重新做 GPU 验收。
4. **不要把“驱动支持 SM86”和“当前 AOT wheel 含 SM86 cubin”混为一谈。** 前者是平台兼容性，后者是构建产物事实。

## 限制与待验证项

- 本报告只使用公开官方文档/公开项目页面，未验证任何具体主机的精确 `nvidia-smi` 输出、内核模块、PyTorch runtime 或 `.so` ELF 内容。
- 输入包仅给出“R580-series / CUDA 12.x / 需要 native SM86 AOT cubin”的脱敏事实；“R580 足够”是基于版本门槛的原则性判断，不替代运行时 smoke。
- SGLang 的公开 AOT CMake 是随 upstream 版本变化的参考；最终以实际构建命令和 `cuobjdump` 结果为准。

## invocation

`done`

