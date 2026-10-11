# G3-IQ3-LOCAL-ENV-RETRY-SHARED-005-20260909

- **工作标题：** G3-IQ3-LOCAL-ENV-RETRY-SHARED-005-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
按授权在报告的 cache permission repair 后重试一次 hash-locked wheelhouse 下载，以完成 IQ3 本地环境构建的依赖准备。

## 实际改了什么
仅执行一次 pip download；未安装部分包、未更改权限、未修改产品或仓库文件。命令使用既定 requirements、共享 cache 与目的 wheelhouse，详见原报告。

## 生成结果与验收
结果 **blocked**：pip 仍提示 `/mnt/data/cache/pip` 不可写并停用缓存；下载 `nvidia-cuda-nvrtc` 到 44.9/90.2 MB 时发生 HTTPS read timeout。按 dispatch 要求不再重试、不安装不完整包。wheelhouse 仍为空，venv 未填充；需修复 cache 写入条件和/或网络后由新 dispatch 继续。

### 产物/证据
原始下载日志：`raw/g3-iq3-env-retry-shared-005-20260909/env-rebuild-download-005-20260909.log`。工具版本和目录状态见报告；未产出可用环境。

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-ENV-RETRY-SHARED-005-20260909.md`：Command (unchanged requirements, shared cache only):
```text
export PIP_CACHE_DIR=/mnt/data/cache/pip
/usr/bin/python3 -m pip download --require-hashes -r /mnt/data/qwen3-g3-baseline/artifacts/torch-cu130-wheelhouse-requirements.txt --dest /mnt/data/qwen3-g3-baseline/wheels --retries 2 --timeout 60
```
Raw output: [download log](raw/g3-iq3-env-retry-shared-005-20260909/env-rebuild-download-005-20260909.log).
Observed tools: Python 3.12.3, `/usr/local/bin/cmake` 4.4.3,
`/usr/local/cuda/bin/nvcc` CUDA 13.0.48. Wheelhouse remains empty (8.0K);
venv remains 16M/unpopulated; shared cache is 7.8G and reports
`charles:dev drwxrwsr-x`.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-ENV-RETRY-SHARED-005-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-ENV-RETRY-SHARED-005-20260909.md`; SHA256 `70edce1ff88b90dda6e2e45c4c7ac8cda3ea3dbbb8ef15996f706bb4bba1253e`; source state `local-only`
