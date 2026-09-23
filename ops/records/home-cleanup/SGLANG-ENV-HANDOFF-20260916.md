# SGLang 运行环境交接 — VM 2500 `sglang-build` (192.168.20.250)

> 面向在本 VM 内工作的 opencode 实例。除标注 **未复验** 者外，本文事实于 **2026-09-16** 在本机核实。
> 目的：**不要重新发现环境、不要重装依赖、不要下错模型。**

## 0. 三条铁律（先读这段）

1. **只用专用 venv**：`/home/ubuntu/venvs/sglang-3090/bin/python`（或用其 `bin/activate`）。
   系统 `python3` **没有 pip**，不是本环境；另一个 `/home/ubuntu/venv` 与本任务无关，**不要用**。
2. **不要重装或"修复"依赖。** 该 venv 已按 CUDA 12.9 配好。本分支 `python/pyproject.toml` 默认解析到
   **CUDA-13** 栈（`flashinfer_python[cu13]`、`cuda-python>=13.0`、`nvidia-cutlass-dsl[cu13]`），
   在这台机器上跑 `pip install -e "python[sglang]"` 会引入冲突。详见 §2.3。
3. **只用 canonical 模型** `/home/ubuntu/models/qwen35-9b-gptq-int4/`，详见 §5。

## 1. 主机 / 硬件

| 项 | 值 |
|---|---|
| 主机名 | `sglang-build`（pve1 上的 VM **2500**） |
| OS / 内核 | Ubuntu 24.04.5 LTS / `6.8.0-139-generic` |
| CPU / 内存 | 32 vCPU / 48 GiB（`numactl`：单 node，32 CPU，48167 MB） |
| GPU | **RTX 3090**，24576 MiB，compute capability **8.6（sm_86）**，已直通到 guest |
| 驱动 | **580.178.04**（与 pc01 同版本） |
| 根文件系统 | `/dev/sda1` 96G，已用 71G，可用 25–26G（74%） |

宿主与 guest 均报 UTC；不要对时区做额外假设或断言。

## 2. Python 环境

### 2.1 路径

| 项 | 值 |
|---|---|
| venv | `/home/ubuntu/venvs/sglang-3090` |
| Python | **3.12.3** |
| 解释器 | `/home/ubuntu/venvs/sglang-3090/bin/python` |
| 安装方式 | `sglang` 以 **editable** 方式装自 §4 的源码树 `python/` |
| 关联 venv（勿用） | `/home/ubuntu/venv`（无关） |
| pyvenv.cfg | 存在且生效（`sys.prefix` = `/home/ubuntu/venvs/sglang-3090`） |

> 细节：venv 内 `bin/python3` 是指向 `/usr/bin/python3` 的符号链接，靠 `pyvenv.cfg` 生效。
> `bin/pip`、`bin/sglang`、`bin/torchrun` 等均正常。**最稳的用法是直接用绝对路径 `bin/python`。**

### 2.2 关键包版本（`pip list` 实测）

| 包 | 版本 |
|---|---|
| `torch` | **2.13.0+cu129** |
| `torchvision` / `torchaudio` | 0.28.0+cu129 / 2.11.0+cu129 |
| `sglang` | **0.5.20.dev22+g9c9e7b7c7**（editable） |
| `flashinfer-python` / `flashinfer-cubin` | 0.6.17 / 0.6.17 |
| `flashinfer-jit-cache` | 0.6.17+cu129 |
| `sglang-kernel` | 0.4.6.post1+cu129 |
| `sgl-deep-ep` / `sgl-deep-gemm` | 0.1.2+cu129 / 0.1.5.post2+cu129 |
| `transformers` | 5.12.1 |
| `triton` | 3.7.1（另有 `tokenspeed-triton` 3.8.10.post20260906） |
| `compressed-tensors` | 0.18.0 |
| `cuda-python` | 12.9.7 |
| `nvidia-cutlass-dsl` | 4.6.2（`-libs-cu12` 变体） |

**版本串口径**：`pip list` 显示的 sglang 版本串仍带 `+g9c9e7b7c7`，因为 editable 元数据是旧 pin 时
生成的，而 checkout tip 已前进到 `ad749d6f28`（§4）。**以 checkout 为准**；不要为此自行重装。

### 2.3 CUDA-13 残留是"惰性"的 —— 不要清理

`pip list` 中仍可见 generic `nvidia-*` 13.x 传递依赖（如 `nvidia-cuda-runtime 13.4.49`、
`nvidia-cuda-nvcc 13.4.59`、`nvidia-cuda-cccl 13.3.4.2.1`），以及休眠的
`site-packages/nvidia/cu13/`（**475 MB**）。

它们**不参与实际编译**：`torch.utils.cpp_extension.CUDA_HOME` 解析为 `/usr/local/cuda` →
`/usr/local/cuda-12.9`，因此 JIT 构建用的是 **nvcc 12.9.86**，而不是 pip 那份 13.x。
→ **视为惰性残留，保持原样，不要"清理"。**

## 3. CUDA / PATH

- `CUDA_HOME` **默认未设置**（`echo ${CUDA_HOME:-<unset>}` → `<unset>`）。
- 任何构建 / JIT 工作前先导出：

```bash
export CUDA_HOME=/usr/local/cuda-12.9
export PATH=/usr/local/cuda-12.9/bin:$PATH   # 仅当需要 nvcc 命令名时
```

- 软链链：`/usr/local/cuda` → `/etc/alternatives/cuda` → `/usr/local/cuda-12.9`（`cuda-12` 同）。
- **`nvcc` 不在 PATH**（`which nvcc` 为空）。直接调用：
  `/usr/local/cuda-12.9/bin/nvcc --version` → `release 12.9, V12.9.86`。

## 4. 源码树

| 项 | 值 |
|---|---|
| 权威工作副本 | `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt` |
| 分支 | **`3090-24g-opt`** |
| HEAD | **`ad749d6f28`**（`ad749d6f283b7d6c59a8df928304325eda90e98b`） |
| remotes | `origin git@github.com:charleslai2000/sglang.git`（fetch+push）；另有 `upstream git@github.com:sgl-project/sglang.git` |
| GitHub SSH | 以 `charleslai2000` 认证成功 |

- 该分支 tip 已从早期记录的 `9c9e7b7c7c` 前进到 `ad749d6f28`；**当前 tip 为准**。
- ⚠ **工作区不干净，而且有人正在改**：核实期间（2026-09-16）VM 内有一个活跃的 `opencode` 进程
  （`ps` 显示 cwd = `/home/ubuntu/workspaces/3rdparty`；核实时 PID 59398，启动于 2026-09-15 20:44:32）
  **正在持续写入**这棵源码树。改动集合在核实过程中由 2 个文件变为 **4 个**，同一文件内容哈希在分钟内即变化。
  核实当时的清单（**快照，会变**）：
  - `python/sglang/srt/managers/tokenizer_manager.py`
  - `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - `python/sglang/srt/observability/hicache_telemetry.py`
  - `test/registered/unit/observability/test_hicache_request_telemetry.py`
  → **不要**用 `git checkout` / `git stash` / `git reset` 去把这棵树"清干净"——那会丢掉别人的在制品。
  → 现场一律以 `git status --porcelain` 为准；**本次交接未改动任何源码文件**。
  → 若你的任务与上述文件重叠，先与对方对齐，不要并行编辑同一批文件。
- 兄弟副本 `/home/ubuntu/sglang`（detached HEAD `71de97b264`，origin 为 HTTPS `sgl-project/sglang`）
  **不是**权威副本。
- ⚠ **cwd 陷阱（实测）**：从 `/home/ubuntu` 运行 `import sglang` 会解析到**兄弟目录**（命名空间包），
  而不是已安装包：
  - cwd=`/home/ubuntu` → `sglang.__path__ = ['/home/ubuntu/sglang']`
  - cwd=`/tmp` → `['/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang']`
  → 一律在**中性 cwd**（如 `/tmp`）或仓库内运行。
- `gpu/` 目录**在本 VM 的 checkout 中不存在**（已确认，`find` 无结果）。
  `gpu/3090-dev/launch-l3-3090.sh` 位于 pc01 的 `server` 仓库，**不在此 VM**。

## 5. 模型（canonical）

- 目录：**`/home/ubuntu/models/qwen35-9b-gptq-int4/`** — 8 个文件，合计 **7,690,244,644 bytes**。
- **单文件 checkpoint**：无 `.safetensors.index.json`。

| 文件 | 大小 (bytes) | sha256 |
|---|---|---|
| `model.safetensors` | 7,670,240,000 | `a81fb938ed15819c7e76453fa3e599fa4dee84af75972d3f2aca6b65b11cefaa` |
| `tokenizer.json` | 19,989,343 | `87a7830d63fcf43bf241c3c5242e96e62dd3fdc29224ca26fed8ea333db72de4` |
| `chat_template.jinja` | 7,756 | `a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715` |

- `config.json`：`architectures ["Qwen3_5ForCausalLM"]`，`model_type "qwen3_5_text"`（**text-only**）；
  量化 `quant_method gptq` / `checkpoint_format gptq_v2` / 4-bit / `group_size 128` / `desc_act false`；
  32 层，hidden 4096。
- 与 pc01 `/mnt/data/models/local-prod-baseline-v1/qwen35-9b-gptq-int4/` 逐字节一致（双端已核验）。
- **不要再下载任何模型**（包括 `RedHatAI/Qwen3.5-9B-quantized.w4a16`）。

### 5.1 ⚠ 同目录诱饵：`/home/ubuntu/models/Qwen3.5-9B-w4a16/`

| 项 | 值 |
|---|---|
| 大小 | 5.6 GB（2026-09-15 下载中途状态） |
| 架构 | `Qwen3_5ForConditionalGeneration` / `model_type "qwen3_5"`（**vision+text 多模态**） |
| 完整性 | **不完整**：`model.safetensors.index.json` 声明 `total_size` ≈ 11.4 GB，但主分片 `model.safetensors` **缺失**；磁盘上只有 `model_mtp.safetensors`（486,582,848 bytes） |
| 结论 | **不可用于加载**；不要在启动时指到它 |

与 canonical 的 text-only 架构不同，且权重不全。**留在原地，不要用它**（是否删除由 owner 决定，不要自行处理）。

## 6. 网络 / 代理

- 系统级代理配置在 `/etc/environment`：外部流量走 `http://192.168.1.203:8118`（pc01）；
  内网段（`192.168.x`、`10.x`、`.lorestack.dev`、`.home.arpa`）直连。
- **不要削弱 `no_proxy` / `NO_PROXY`**：Python 不识别 CIDR 条目，因此必须保留其中的**显式 IP**。
- 实测可达（HTTP 200）：`huggingface.co`、`pypi.org`、`github.com`、`registry.npmjs.org`、`flashinfer.ai`。
- `ssh git@github.com` 认证成功（`Hi charleslai2000!`）。
- 内网 Gitea：`https://192.168.20.101` 的 HTTPS 握手在 curl 下失败 ——
  `curl: (60) SSL certificate problem: unable to get local issuer certificate`
  （证书由内部 `S7070 Home CA` 签发，不在本机信任库）。**优先用 SSH remote**：
  `git@gitea.lorestack.dev`（实测认证成功）。
- OpenCodex key 位于 `/home/ubuntu/.opencodex-api-key` —— **只引用路径，不要读取或外传其值**。

## 7. 启动 SGLang

- 推荐入口：**`sglang serve`**（子命令：`serve` / `generate` / `version`）。
- 旧写法 `python -m sglang.launch_server` **仍可用**，但会打印 deprecation warning 指向 `sglang serve`。
- **本 VM 尚未执行过完整 server 启动**（截至 2026-09-16）。这是下一步。

### 7.1 骨架（仅含已核实要素）

```bash
export CUDA_HOME=/usr/local/cuda-12.9
cd /tmp   # 避开 §4 的 cwd 陷阱
/home/ubuntu/venvs/sglang-3090/bin/sglang serve \
  --model-path /home/ubuntu/models/qwen35-9b-gptq-int4
```

端口等其余参数按需指定；上面刻意不写未经复验的取值。

### 7.2 本机冻结常量（**documented，未在本 VM 复验**）

以下为此机器已记录的调优常量。**flag 名已在本 build 的 `sglang serve --help` 中逐个确认存在**；
但**取值组合从未在本 VM 跑过完整启动**，首次启动请逐项观察后再固化。

| flag | 值 |
|---|---|
| `--tp-size` | `1` |
| `--mem-fraction-static` | `0.92` |
| `--max-total-tokens` | `65536` |
| `--kv-cache-dtype` | `bf16` |
| `--attention-backend` | `flashinfer` |
| `--linear-attn-prefill-backend` | `triton` |
| `--linear-attn-decode-backend` | `triton` |
| `--mamba-radix-cache-strategy` | `extra_buffer` |
| `--mamba-ssm-dtype` | `float32` |
| `--enable-hierarchical-cache` | （开关，无值） |
| `--hicache-write-policy` | `write_back` |
| `--hicache-ratio` | `1.5` |

> 关于 `gpu/3090-dev/launch-l3-3090.sh`：该脚本**不在本 VM**（见 §4）。即便取得，其 `MODE=native`
> 分支假设的是另一台机器的 miniconda 布局，并依赖本机**不存在**的 `STORAGE_DIR` / `KEYFILE`。
> **必须改写后使用，不可原样运行。**

## 8. 禁区速查

| ✗ 不要 | ✓ 应该 |
|---|---|
| `python3 -m pip ...` | `/home/ubuntu/venvs/sglang-3090/bin/python -m pip ...` |
| 用 `/home/ubuntu/venv` | 用 `/home/ubuntu/venvs/sglang-3090` |
| `pip install -e "python[sglang]"` 重装 | 直接用现成 venv |
| "清理" `nvidia-*` 13.x / `nvidia/cu13/` | 视为惰性，保持原样 |
| 从 `/home/ubuntu` 跑 `import sglang` | 从 `/tmp` 或仓库内跑 |
| 下载新模型 / 用 `Qwen3.5-9B-w4a16/` | 用 `qwen35-9b-gptq-int4/` |
| 削弱 `no_proxy` | 保留其中的显式 IP |
| 假设 `nvcc` 在 PATH | 显式用 `/usr/local/cuda-12.9/bin/nvcc` |
| 假设 `CUDA_HOME` 已设 | 先 `export CUDA_HOME=/usr/local/cuda-12.9` |
| `git checkout/stash` 清掉源码树改动 | 见 §4，先搞清归属 |

## 9. 未决问题 / 未复验项

### 未决（需 owner 裁决，不得当作既成事实）

1. **tokenizer 溯源哈希不一致**：仓库记录的 `tokenizer.json` sha256 为
   `5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42`，
   而 canonical 模型实际的 `tokenizer.json` 为
   `87a7830d63fcf43bf241c3c5242e96e62dd3fdc29224ca26fed8ea333db72de4` —— **不匹配**。
   `chat_template.jinja` 则**匹配**记录的 `a4aee8af…f715`。
   上游仓库规则：tokenizer 不匹配可使已记录的 chain baseline 失效。**等 owner 决定，不要自行"修复"。**
2. `/home/ubuntu/models/Qwen3.5-9B-w4a16/`（不完整的多模态诱饵，§5.1）如何处置 —— 由 owner 决定。
3. 源码树中**他人正在进行的未提交改动**（§4；核实时 4 个文件且仍在变动）归属与去留未确认 ——
   确认前不要对其做任何回滚 / 清理。

### 未复验 / 待做

4. **完整 server 启动尚未执行** —— 下一步。
5. §7.2 的 12 个常量：flag 名已确认存在，**取值组合未在本 VM 复验**。
6. sglang editable 的版本串（`+g9c9e7b7c7`）落后于 checkout tip（`ad749d6f28`）；是否重新生成
   editable 元数据由 owner 决定 —— **不要自行重装**。

## 10. 证据与参考

- 交接任务记忆（pc01）：
  `/home/charles/Workspaces/homenet/server/.memory/gpu-3090-vm2500-20260916/`
- 本文事实核对日期：**2026-09-16**（guest UTC）。
