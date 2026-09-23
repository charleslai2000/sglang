# SGLang 3090 任务交接（给 VM 2500 内的 opencode）

> 本文件由 pc01 侧编排 agent 写入，把 SGLang(3090) 这条线正式交接给 VM 内的 opencode。
> 环境细节见 `/home/ubuntu/SGLANG-ENV.md`（**先读它**）。本文只讲：任务、边界、陷阱、开放项。
> 写入时间：2026-09-16。所有事实均已由 pc01 侧独立核验，可直接依赖，不必重查。

## 0. 一句话
环境已完全就绪。**下一步的决定性动作 = 用 canonical 模型把 SGLang 真正起起来**（至今从未在本 VM 上完整启动过一次）。

## 1. 已核实状态

| 项 | 值 |
|---|---|
| GPU | RTX 3090，24576 MiB，compute capability **8.6 (sm_86)**，已直通客机 |
| 驱动 | **580.178.04**（与 pc01 同版本） |
| CUDA toolkit | `/usr/local/cuda-12.9`，`nvcc` = **V12.9.86**（**不在 PATH**） |
| `CUDA_HOME` | **未设置** |
| venv | **`/home/ubuntu/venvs/sglang-3090`**（Python 3.12.3） |
| torch | `2.13.0+cu129`（CUDA 12.9 运行时），`torchvision 0.28.0+cu129`，`torchaudio 2.11.0+cu129` |
| sglang | `0.5.20.dev22+g9c9e7b7c7`，**editable** 指向下面的仓库 |
| 其他关键包 | `flashinfer-python 0.6.17`、`flashinfer-cubin/-jit-cache 0.6.17+cu129`、`sglang-kernel 0.4.6.post1+cu129`、`sgl-deep-ep 0.1.2+cu129`、`sgl-deep-gemm 0.1.5.post2+cu129`、`transformers 5.12.1`、`triton 3.7.1`、`compressed-tensors 0.18.0`、`cuda-python 12.9.7` |
| 仓库 | `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`，分支 **`3090-24g-opt`**，HEAD **`ad749d6f28`** |
| 远端 | `origin = git@github.com:charleslai2000/sglang.git`；另有一个 `upstream` |
| 模型（VM 内有两份，均完整） | ① **`/home/ubuntu/models/Qwen3.5-9B-w4a16/`** = `RedHatAI/Qwen3.5-9B-quantized.w4a16`（compressed-tensors W4A16，12 文件 / 11,456,889,104 B，index 自洽）—— **3090 线既定模型**（`gpu/3090-dev/README.md` §8.1，2026-08-29 用户决策；已冒烟验证：compressed-tensors 正常加载、mem 10.36 GB、`/health` 200、16 token 生成成功）<br>② `/home/ubuntu/models/qwen35-9b-gptq-int4/` = GPTQ v2（8 文件 / 7,690,244,644 B，来自 pc01 `/mnt/data/models/local-prod-baseline-v1/`）<br>**用哪个由 owner 确认**（两条工作线可能不同），见 §6 |
| 根文件系统 | ext4 193 G 总量 / 可用约 125 G（2026-09-16 由 100 G 扩容至 200 G 后） |
| 仓库内启动模板 | 本 VM checkout **没有** `gpu/` 目录；模板 `gpu/3090-dev/launch-l3-3090.sh` 在 pc01 的 `server` 仓库里，需要重建而非直接跑 |
| 外网通路 | 已配（`/etc/environment` 代理 → pc01:8118；内网直连）。HF / PyPI / GitHub / npm / flashinfer 均实测可达；`git@github.com` 认证为 `charleslai2000` |
| background subagent 标志 | 已在 `/etc/environment` 落地并实测生效（非交互/登录/普通 shell 均可拿到） |
| GPU 当前占用 | **空闲**（0%，1 MiB） |

## 2. 你的工作现场（重要，别自己踩自己）
你（VM 内 opencode）**正在编辑**上面那个仓库的 4 个文件：

```
python/sglang/srt/managers/tokenizer_manager.py
python/sglang/srt/mem_cache/unified_radix_cache.py
python/sglang/srt/observability/hicache_telemetry.py
test/registered/unit/observability/test_hicache_request_telemetry.py
```

这些是**你的未提交 WIP**。pc01 侧已明确记录：**任何人不得对它们执行 `git checkout` / `git stash` / `git reset` / `git clean`**。
提交与否由你决定；注意 `origin` 是你自己的 fork。

## 3. 硬边界（越界即严重违规）
1. **不碰宿主**：不修改 pve1（PVE 宿主）的任何配置——VM 配置、存储、网络、直通、NUMA 全不归你。需要宿主侧资源（扩盘、改直通、调 NUMA）时**报告需求**，不要自己动。
2. **不碰其他 VM**，不碰 pc01。
3. **不删除/不格式化**：`rm` 一律禁止；需要腾空间用 `mv` 挪走并报告。**任何删除都要先拿到 owner 明确批准。**
4. **不重装/不"修"依赖**：venv 已正确。**特别禁止**用新 checkout 跑 `pip install -e "python[sglang]"` —— 本分支 `python/pyproject.toml` 默认是 **CUDA-13** 依赖栈（`flashinfer_python[cu13]`、`cuda-python>=13.0`、`nvidia-cutlass-dsl[cu13]`），与本机 CUDA 12.9 冲突。
5. **不改** `/etc/environment` 的代理设置（是 load-bearing）。
6. **不打印凭据**：任何 API key / token / 密码值不得出现在输出、日志、报告、提交里。
7. **不用 `pkill -f`** 之类的广域模式杀进程。
8. 长任务/大产物按 `AGENTS.md` §10 放在指定大容量位置，不要塞进源码树。

## 4. 陷阱（会真的咬人）
1. **两个模型名字相近，别搞错**：`/home/ubuntu/models/` 下有两份模型（`Qwen3.5-9B-w4a16` 与 `qwen35-9b-gptq-int4`），**两者都是完整的**（见 §1）。用哪个**由 owner 确认**，不要凭名字猜；在确认前**不要删除任何一份**。
2. **系统 `python3` 没有 pip，也不是这个环境。** 必须显式用 `/home/ubuntu/venvs/sglang-3090/bin/python`，或先 activate venv。另有一个无关的 `/home/ubuntu/venv`，别用。
3. **cu13 残留是惰性的，别"清理"**：`pip list` 里仍有通用 `nvidia-*` 13.x 传递依赖（例如 `nvidia-cuda-runtime 13.4.49`、`nvidia-cuda-nvcc 13.4.59`，以及 `site-packages/nvidia/cu13/` 475 MB）。它们**不参与**：`torch.utils.cpp_extension.CUDA_HOME` 解析到 `/usr/local/cuda` → `cuda-12.9`，JIT 用的是 **nvcc 12.9.86**。
4. **cwd 遮蔽**：在 `/home/ubuntu` 下跑 `python -c "import sglang"` 可能解析到**同名的兄弟目录** `/home/ubuntu/sglang`（空的 namespace）而不是已安装的包。请在中立 cwd（如 `/tmp`）或仓库目录内运行。
5. **磁盘（已扩容，2026-09-16）**：`/` 现为 **ext4 193 G 总量，可用约 125 G（36% 已用）**。扩展理由 = 完整 L3 HiCache 配置需约 30 G 余量（20 G cap + 10 G min_free）。起服务仍有编译缓存等额外开销，注意监控不要写满。
6. **`gpu/` 目录在本 VM checkout 里不存在** —— 别去找那个启动脚本。
7. **CUDA 栈差异（需留意）**：本 VM 的 venv 是 **CUDA 12.9 (cu129)**；而 `gpu/3090-dev/README.md` §8.1 记录的环境修复出自**老 3090 机器**，那台是 **CUDA 13（nvcc 13.3.73、python 3.10 conda）**。§8.1 的若干修复（JIT 链接需 `libcudart.so` symlink、flashinfer 的 CTK 检查要求 nvcc 版本 == cudart 头版本、HiCache native hash 扩展需 `CPLUS_INCLUDE_PATH`/`LIBRARY_PATH`）**在 cu129 下需重新对一遍**。**切勿照搬 cu13 的路径**（如 `/root/miniconda3/.../nvidia/cu13`，本机不存在）。引擎加载若报 CUDA/JIT 类错误，先查这一条。

## 5. 下一步（按顺序做，先便宜后昂贵）
1. **最小冒烟**：用极小配置证明引擎能加载模型、能出 token（例如很小的 `--max-total-tokens`、**先不开** HiCache）。失败要留原始日志。
2. **再上完整配置**。本机记录的冻结常量如下（**12/12 已在本 build 的 `sglang serve --help` 中确认存在**，但**取值组合尚未实测**）：

   ```
   --tp-size 1
   --kv-cache-dtype bf16
   --attention-backend flashinfer
   --linear-attn-prefill-backend triton
   --linear-attn-decode-backend triton
   --mamba-radix-cache-strategy extra_buffer
   --mamba-ssm-dtype float32
   --mem-fraction-static 0.92
   --max-running-requests 8
   --cuda-graph-max-bs 8
   --enable-hierarchical-cache
   --hicache-write-policy write_back
   --hicache-storage-backend file
   --hicache-storage-prefetch-policy wait_complete
   --hicache-ratio 1.5
   --max-total-tokens 65536
   --reasoning-parser qwen3
   --tool-call-parser qwen3_coder
   --enable-metrics
   ```

   运行前建议导出：
   ```bash
   export CUDA_HOME=/usr/local/cuda-12.9
   export PATH=/usr/local/cuda-12.9/bin:$PATH
   export SGLANG_ENABLE_UNIFIED_RADIX_TREE=1
   export SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=<专用L3目录，需 ≥30G 余量>
   export SGLANG_HICACHE_FILE_BACKEND_MAX_SIZE=20G
   export SGLANG_HICACHE_FILE_BACKEND_MIN_FREE_SPACE=10G
   export SGLANG_HICACHE_FILE_BACKEND_ENABLE_METADATA_CACHE=true
   ```
   入口推荐 `sglang serve`（`python -m sglang.launch_server` 仍可用但会告警）。
   **注意**：L3 目录要 ≥30 G 余量（20 G cap + 10 G min_free）。磁盘已扩容到位（可用约 125 G），空间不再是阻塞项。
3. **实测并回填**：把实测到的显存占用、`max_total_tokens` 实际上限、首 token 延迟等，回填进 `/home/ubuntu/SGLANG-ENV.md` 的「未验证」小节。
4. 之后按你自己的优化计划推进（HiCache / 3 层 KV / extent L3 等）。

## 6. 需要上游裁决 —— 不要自行决定
1. **tokenizer 字节差异 = 已记录且已解决，不是待决问题**：`RedHatAI` 模型的 `tokenizer.json` sha256 = `87a7830d…`，与链基记录值 `5f9e4d49…` 字节不同；`chat_template.jinja` 相符。`gpu/3090-dev/README.md` §8.1 已记录并给出**严格功能测试结论**：`apply_chat_template(tokenize=True, add_generation_prompt=True)` 输出 **20911 ints 与 `qwen35-P-ids.json` 逐位一致** → **链基对该 tokenizer 有效，无需重生成**。**不要据此修改任何东西。**
2. **模型选择**：VM 内两份模型（见 §1）用哪个，由 owner 确认。
3. 如需宿主侧资源（扩盘/直通/NUMA），报告需求，等授权。

## 7. 汇报要求
- 有实质进展或阻塞就写清：**命令、原始输出、退出码、结论**。不要把"我做了"当成证据。
- 区分「已实测」与「据文档/推测」。
- 不打印任何凭据值。
