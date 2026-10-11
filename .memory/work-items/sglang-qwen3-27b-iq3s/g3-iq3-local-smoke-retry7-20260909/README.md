# G3-IQ3-LOCAL-SMOKE-RETRY7-20260909

- **工作标题：** G3-IQ3-LOCAL-SMOKE-RETRY7-20260909
- **来源仓：** `sglang-qwen3-27b-iq3s`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`

## 工作目标
在离线 wheelhouse requirements 安装和 `prepare_server_args()` 预检后，尝试本机 GPU1 RTX 3090 的隔离 smoke startup，使用指定模型、端口 18035 与冻结 server argv。

## 实际改了什么
报告记录离线确认/安装 29 项锁定 requirements 已满足，并执行无 GPU 的 server-args preflight；随后在共享 GPU lock 下以前台精确命令尝试启动。未触碰其他进程、driver、CUDA 或仓库产品代码；未发送请求。

## 生成结果与验收
启动在模型加载前因缺少 `sgl_kernel` 退出。无服务遗留、无 request、无 GPU test；smoke **blocked**。wheelhouse 缺匹配 `sgl_kernel` package/wheel，不能自行选择其他来源。后续需提供 checkout-compatible 扩展及 provenance/hash，再以新 invocation 重试。

### 报告列出的产物/证据
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-SMOKE-RETRY7-20260909.md`：- Offline wheelhouse installation completed with `pip install --no-index --require-hashes -r /mnt/data/qwen3-g3-baseline/artifacts/torch-cu130-wheelhouse-requirements.txt --find-links /mnt/data/qwen3-g3-baseline/wheels`; all 29 requirements already satisfied, including `torch==2.13.0+cu130`.
- Preflight `prepare_server_args()` with `CUDA_VISIBLE_DEVICES=''` and exact frozen server argv returned `PREPARE_SERVER_ARGS_OK`.
- GPU inventory before launch: GPU1 RTX3090, 53 MiB / 24576 MiB, 0% utilization; port 18035 unused; lock was free.
- Foreground launch under `flock -x /mnt/data/gpu/3090.lock`, `CUDA_VISIBLE_DEVICES=1`, exact requested model/server flags, exited before model load with:…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `qwen3-27b-iq3s` @ `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `g3-baseline-20260907/work/G3-IQ3-LOCAL-SMOKE-RETRY7-20260909.md` → `.memory/g3-iq3-kernel-build/work/G3-IQ3-LOCAL-SMOKE-RETRY7-20260909.md`; SHA256 `22c08d3c3ecb9822d4db19a013d5ae2e862cca0d2829bb2aa79e6f643de15928`; source state `local-only`
