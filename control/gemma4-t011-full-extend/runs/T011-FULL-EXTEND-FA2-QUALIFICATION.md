# T011 Full Extend FA2 candidate — applicability review

Date: 2026-11-27. Decision: **STOP before GPU experiment or production integration**. The requested target (`head_dim=512` Full Extend) is absent from the exact frozen production checkpoint. Constructing a synthetic 512-dim GQA case would not qualify the actual production geometry; changing scope to `head_dim=256` requires the user's decision and is outside this task as stated. No alternative attention algorithm was considered or implemented.

## Frozen identity and environment

- Repo HEAD and origin: `c102ccbc5cfd17b510f896b23107204daf5ed0d7`.
- Production source SHA: `a76206a5fbd65b81ddbb470ac8088a46cf78697a` (T010 capture manifest).
- Model config: `/data/sglang-hicache/gemma4/model/config.json`, used by T010 launch command. The `text_config` fields are `head_dim=256`, `num_attention_heads=8`, `num_key_value_heads=2`, `num_hidden_layers=42`, `num_kv_shared_layers=18`, `sliding_window=512`.
- Full layer IDs from `text_config.layer_types`: `[5, 11, 17, 23, 29, 35, 41]`; the final 18 layers (24–41) are KV-sharing layers. Per `Gemma4Attention` source, the three shared Full layers use the nearest earlier Full owner, layer 23. There is no Full layer with head dimension 512 in this model config: `Gemma4DecoderLayer` passes `config.head_dim` for Full layers and `config.swa_head_dim` only for SWA layers.
- Current environment has FlashInfer 0.6.17, torch 2.13.0+cu129, RTX 3090 SM86. This is inventory only, not a support or performance qualification.
- No GPU workload ran. Before review, `nvidia-smi` showed 1 MiB use / 0% utilization and the project lock was available. No lock was held for this no-run conclusion.

## Existing trace hotspot (no recapture)

Trace: `/data/sglang-hicache/gemma4/runs/20261127T-t010-hwprof/nsys/gemma4.sqlite`; its manifest points to the same frozen production source. Kernel summary row:

| Demangled symbol | Grid (X,Y,Z) | Calls | Total GPU time | Mean |
|---|---:|---:|---:|---:|
| `_fwd_kernel` | (1,8,128) | 63 | 2708.544 ms | 42.993 ms |

The existing DB provides kernel name, grid, launch geometry, times, and a single generic `CCCL` NVTX string; it contains no model layer ID/type, head dimension, Q/KV head count, or per-launch input lengths. Therefore the trace does **not** establish which actual layer produced these 63 launches, and it does not separate Full from SWA. Assigning the row to a layer would fabricate trace attribution.

For the production checkpoint's known Full `Lq=Lv=256` on SM86, frozen source `_get_block_sizes_for_extend_attention(256,256)` selects `BLOCK_M=64`, `BLOCK_N=64`, 8 warps. Given the public launch grid `(batch_size, head_num, cdiv(max_len_extend,BLOCK_M))`, `(1,8,128)` corresponds to 8,192 query rows for that geometry. This does not match the T010 controlled extend phases documented as 1024/1280/4096 and chunk=4096, so this row cannot be assigned to those phase shapes from the SQLite kernel row alone. The separately documented controlled row `(1,8,64)` is consistent with 4096 queries under the same geometry; phase result JSON identifies the ext4096 request but does not join individual kernel calls to layer IDs. The report's trace review had already cautioned that layer attribution was absent.

Exact source evidence:
- `python/sglang/srt/configs/model_config.py:get_attention_sliding_window_size` / `get_hybrid_layer_ids` maps `layer_types` into Full/SWA IDs.
- `python/sglang/srt/models/gemma4_causal.py:Gemma4DecoderLayer.__init__` sets Full `head_dim=config.head_dim`; `Gemma4Attention.__init__` uses Full `num_attention_heads` and `num_key_value_heads` and calculates sharing among same-type layers.
- `python/sglang/kernels/ops/attention/extend_attention.py:_get_block_sizes_for_extend_attention` has explicit SM86/SM89 selection for dimensions >256: `(32,32)` when Lq>256, but the actual Full path at Lq=256 selects `(64,64)`.
- `extend_attention_fwd` launches grid `(batch_size, head_num, triton.cdiv(max_len_extend, BLOCK_M))` unless compact tiling is enabled; compact tiling is HIP-only and thus not this CUDA SM86 path.

## Candidate decision

The requested fixed operator cases use `head_dim=512` and actual GQA geometry. Production Full attention instead has `head_dim=256`, Q/KV heads 8/2. They are materially different kernel inputs and wrapper specialization; measured performance on synthetic 512 would not answer whether this production hotspot improves. The target is thus **not applicable to frozen production source**, independent of whether installed FlashInfer FA2 can run a synthetic 512 case.

Consequently, did not run the three proposed isolated timings, did not compare plan+attention+merge against Triton, and did not create a 512-dim synthetic proxy. No support/performance claim about FlashInfer 0.6.17 on arbitrary 512-dim input is made. No production file changed, no oracle or C-8/three-tier run was made, and there is no speedup, memory-cost, or end-to-end claim.

To proceed with the user's chosen FA2 algorithm while optimizing this frozen production service, the scope must target actual Full head_dim=256, or a different frozen checkpoint with Full head_dim=512 must be supplied. This review itself does not choose that scope change.

## Final state

Candidate falsified on applicability; stop condition satisfied. Production source remains at frozen `c102ccbc5c` / `a76206a5fb`. Durable artifact is this report. No production integration or benchmark was made. Control/report records are committed separately; no production source is included. Existing unrelated untracked `control/gemma4-rtx3090-throughput-scheduling/runs/T011-ATTENTION-REVIEW.md` remains preserved and unstaged.
