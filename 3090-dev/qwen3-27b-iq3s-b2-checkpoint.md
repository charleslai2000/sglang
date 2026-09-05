# Qwen3.8-27B GSQ-RCO IQ3_S — B2 bring-up checkpoint

> 本文件是实验分支 B2 bring-up PASS 后的**可回退 checkpoint 说明**。
> 冻结的是"已实际 PASS 的精确代码 revision"（本分支当前 HEAD），供后续
> MMQ/质量（S3a）/容量（S2.5）实验随时 `git checkout` 回退。
> 2026-09-06。

## 1. 分支与基线

- worktree：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s/`
- 分支：`sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s`（fork charleslai2000/sglang）
- 基线 HEAD（alias commit）：`ec8db606ba4e59f6a4aa735aeb77cc7e1576d58c`
  - `feat(loader): add qwen3_5_text -> qwen35 alias for GGUF loading`
- 本 checkpoint 在 `ec8db606ba` 之上追加 B2 loader/runtime + test harness + 本说明。
- 本分支基于 `3090-24g-hicache` 基线 `0a725c6385`（22151 HiCache production env handover）。

## 2. B2 冻结内容（本 checkpoint 新增，相对 `ec8db606ba`）

### Loader / runtime
- `python/sglang/srt/model_loader/qwen35_gguf.py`（新）：dense qwen35 专用 name map，
  851 tensors 完整性/重复/碰撞检查；先 yield `qweight_type` 再原样复制 packed rows；
  BF16 alpha/beta 保留 GGUF packed representation（bytes → bf16 view，不 round）；
  F32/F16/BF16 norm/state/conv 小参数转换：A=负数校验→`log(-A)`、普通 norm 减 1、
  `linear_attn.norm` 不减 1、conv1d `unsqueeze(1)`。
- `python/sglang/srt/configs/qwen35_gguf.py`（新）：从 GGUF metadata 构造 text-only
  `Qwen3_5Config`（`language_model_only=True`）。
- `gguf_name_maps.py`：注册 `qwen3_5_text`/`qwen3_5` → `build_qwen35_name_map`。
- `loader.py`：匹配 qwen3_5_text + actual arch=qwen35 时设
  `text_config.gdn_v_head_layout="tiled"`；暂限 TP=1/PP=1；调用专用 iterator，
  校验 `model.named_parameters()` 全部落入 `load_weights` 返回集合。
- `qwen3_5.py`：packed loader wrapper 增加 `qweight`/`qweight_type`，处理 tuple shards；
  GGUF 模式 embedding 传 quant_config，避免默认 BF16 embedding 与 qweight 名不匹配。

### GDN（Route B — tiled V-head pairing，只改 K→V head 映射）
- `radix_linear_attention.py`：`RadixLinearAttention` 增加 `gdn_v_head_layout`（默认 grouped）。
- `qwen3_5.py`：显式传 layout 给 GDN。
- `gdn_backend.py`：把 bool 传入 packed_decode/decode/extend/target_verify；初始化时拒绝
  非 CUDA Triton 与 ReplaySSM（tiled 模式）。
- `gdn_triton.py`：仅 `tiled_v_heads=True` 时给底层传新 keyword，不破坏 grouped 接口。
- fla kernels（`kernels/ops/attention/fla/`）：`chunk.py`/`chunk_fwd.py`/`wy_fast.py`/
  `chunk_delta_h.py`/`chunk_o.py` 加布尔参数及 constexpr（chunk 路径用 `i_h % Hg`）；
  `fused_recurrent.py`（仅 packed_decode kernel/wrapper）与
  `fused_sigmoid_gating_recurrent.py`（kernel/wrapper）改可选 `i_hv % H`。
- 未改 generic recurrent/KDA/ReplaySSM kernels；tiled 模式误走未覆盖路径会被初始化拒绝。

### Tokenizer（native GGUF）
- `gguf_native.py`：注册 qwen35 builder、qwen35 pretokenizer regex；qwen35 走
  `ignore_merges=False`、NFC normalizer、`trim_offsets=False`；control/FIM marker
  special-id 处理。已验证与下载的官方 `tokenizer.json` 中英/数字/混合/代码 + 全部
  特殊 token parity。

### Test harness（`test/registered/quant/qwen35_gguf/`）
- `reference.py`：grouped/tiled fp64 单层 reference（B1a-1 synthetic proof）。
- `real_oracle.py`：真实 GGUF 20 节点 hard assertions（CPU fp64，research-only）。
- `test_tiled_kernels.py`：CUDA Triton 真核 layout / state-continuation 回归（5 passed）。
- `test_packed_loader.py`：tuple QKV shards 标量 qtype / 字节保持 split（2 passed）。
- `serve_smoke.py`：5 项 sanity（英/中/算术/Python/JSON），有限 logprob 门。
- `verify_stage3.py`：config / name-map / tokenizer sanity（851 tensors、64 层、48 GDN、无碰撞）。

## 3. B2 bring-up 验证结果（已 PASS）

- Stage 4：`test_tiled_kernels.py` 5 passed（真 CUDA Triton，12.48s）；`test_packed_loader.py` 2 passed。
- Stage 5：实验服务 127.0.0.1:8035，loader 行 `qwen35 GGUF: 851/851 tensors mapped;
  packed qtypes preserved; V-head layout=tiled`；首 token 有限 logprob。
- Stage 6：5 项 sanity 全 correct、全 `finite_returned_logprobs=True`；determinism PASS；
  128-token 全有限；多轮 4→7 state continuity OK。
- 真实权重 oracle：CPU fp64，4 层各 20 节点 ALL PASS（final max_abs ~1e-15）——
  数值正确性锚点（research-only，不用于加载 serving 权重）。

## 4. 启动参数 / FlashInfer JIT 环境要求

实验服务启动命令（SGLang `serve` 子命令）：

```bash
sglang serve --model-path /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf \
  --port 8035 --tp-size 1 --pp-size 1 --trust-remote-code --log-level info
```

必须环境（FlashInfer prefill/full-attention 为 JIT-only，本 wheel 无预编译 .so）：

- `CUDA_HOME=/opt/cuda-conda`（bin/nvcc + include/）
- `PATH` 含 `/opt/cuda-conda/bin` 与 venv `/data/sglang-qwen35-env/bin`（ninja）
- `/opt/cuda-conda/bin/nvcc` 是 **wrapper**（exec `/root/miniconda3/bin/nvcc`，conda CUDA 12.8）：
  直接 symlink conda nvcc 会破坏其相对 `_HERE_` 解析（cicc/cudafe++ 找不到），wrapper 保正确。
- sm86 编译，缓存于 `/root/.cache/sglang/.cache/flashinfer`。缓存清空后必须重设 CUDA_HOME/PATH。
- 上述已固化在远端 `/data/sglang-qwen35/launch_exp.sh`（远端工作树，未提交）。

备注：
- Rust extensions 未构建；默认 Python pipeline 不需要（仅 `SGLANG_RUST_SERVER=1` opt-in）。
- 服务当前仍跑在 22109 `127.0.0.1:8035`（GPU ~22.6GB/24.5GB）。

## 5. 模型

- 文件：`/data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`（11.8GB，851 tensors）
- md5：`a37cff66ad81b0e6311d4b6671ac2b09`
- 架构：qwen35，64 层，hidden 5120，heads 24，kv_heads 4，ssm group 16/state 128/
  inner 6144/time_step_rank 48/conv_kernel 4；48 GDN + 16 full-attention。
- qtype 分布：BF16 96 / F32 353 / IQ1_M 1 / IQ2_S 17 / IQ2_XS 9 / IQ2_XXS 5 / IQ3_S 144 /
  IQ3_XXS 78 / IQ4_XS 96 / Q2_K 13 / Q4_K 39。

## 6. 报告引用（.memory，不入 git）

- 阶段总结：`/home/charles/.memory/qwen3-27b-iq3s/work/stage1-B2-bringup-summary.md`
- bring-up 报告：`/home/charles/.memory/qwen3-27b-iq3s/work/bringup-devops-e1.md`
- 账本：`/home/charles/.memory/qwen3-27b-iq3s/ledger.md`（D-020~D-022 决策）
- 交接：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s/CODEX_HANDOFF.md`

## 7. 口径（D-020/D-021 收紧）

- 本 checkpoint 证明的是 **bring-up correctness gate**（loader + GDN representation 经真实
  权重 oracle + CUDA kernel test + 首 token + 基础多轮 sanity），**不是"模型 correctness
  已完全证明"**（5 sanity 不能单独证明完整模型数值等价）。
- "单卡可驻留运行"成立；"是否剩足够 context/cache"须看 SGLang 实际分配出的
  `max_total_num_tokens / KV pool / Mamba state capacity`（S2.5 capacity record 单独验）。
- 主质量口径不用 `temp=0`；官方 sampling = `temperature=1.0, top_p=.95, top_k=20`（S3a）。
