# Phase 1A — GPU-window preparation

## VERDICT: PASS

Preparation completed without GPU access and without stopping, restarting, or
interfering with the incumbent M4 service.

## Artifact

- HF repo: `tiiuae/Falcon-H1-7B-Instruct-GPTQ-Int4`
- Resolved revision/cache commit: `52036ae497a2c0c253e17f98cc8652f2f7082ae3`
- Local path: `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`
- Artifact bytes excluding `.cache/huggingface`: `7,808,609,972` bytes
- Weight bytes: `7,797,756,040` bytes
- Weight files:
  - `model-00001-of-00002.safetensors`: `3,998,869,672` bytes; SHA256 `00a9f15ca3dec4de0d4698e638b9d0a3328a1b3a95556b2b17746274ba21f822`
  - `model-00002-of-00002.safetensors`: `3,798,886,368` bytes; SHA256 `2c2fb440852a7450690c6c3229d8db5cf2a1933404209fc6a180906223b67906`
- `config.json`: SHA256 `ca8c91f8a18a4917f9580ce1cbcb015a6f7cee2b24022cf6c3e8c94d6943a7f7`
- `generation_config.json`: SHA256 `1689c9ee2a9b2d312bd6bfbc21dde4e0894b998fa429203da89ccbfb0ac3d2f4`
- `tokenizer.json`: SHA256 `51922642a37b5aa79b25e7f9fa119c3c272ab580cd14acb3df165e5b80ed33c6`
- `tokenizer_config.json`: SHA256 `5673338a8e379784b25e7f9fa119c3c272ab580ed33c6`
- `quantize_config.json`: SHA256 `9dff516714538d60ceba57c997e94a90d7533495c99291ddfbe50c647e5d4816`
- No BF16/Int8 replacement checkpoint was downloaded.

The model directory contains the complete official GPTQ artifact and HF cache
metadata. (The model is not copied into the git worktree.)

## Checkpoint config

From the actual `config.json`:

| field | value |
|---|---:|
| model_type | `falcon_h1` |
| architecture | `FalconH1ForCausalLM` |
| hidden layers | 44 |
| hidden size | 3072 |
| attention heads | 12 |
| KV heads | 2 |
| head dim | 128 |
| Mamba state size | 256 |
| Mamba conv kernel | 4 |
| Mamba heads/groups | 24 / 1 |
| `mamba_d_ssm` | 3072 |
| `torch_dtype` | BF16 |
| GPTQ bits/group | 4 / 128 |
| `desc_act` | true |
| `sym` | true |
| quant method | GPTQ, checkpoint format GPTQ |

The runtime config matches the checkpoint fields used by
`python/sglang/srt/configs/falcon_h1.py`.

## Quantized module coverage

The safetensors index/header inspection found **132 qweight tensors / 132
quantized projection modules**: for every 44 layers, the three
`feed_forward.{gate_proj,up_proj,down_proj}` projections have GPTQ
`qweight/qzeros/scales/g_idx` tensors.

The following remain non-GPTQ high precision according to actual tensor headers:

- `self_attn.{q_proj,k_proj,v_proj,o_proj}.weight`: BF16
- `mamba.in_proj.weight` and `mamba.out_proj.weight`: BF16
- `model.embed_tokens.weight`: BF16
- `lm_head.weight`: BF16 (`lm_head: false` in quant config)
- layer norms and Mamba parameters (`A_log`, `D`, `dt_bias`, norms, conv bias/weight): non-GPTQ checkpoint tensors, with exact per-tensor dtypes available from the safetensors headers

Expected runtime path on RTX 3090 is compatible native `GPTQ -> GPTQ-Marlin`,
subject to startup confirmation. No runtime claim is made before the GPU run.

## Static weight accounting

- Serialized artifact and serialized weight values are recorded above.
- Safetensors tensor-payload estimate from actual headers: `7,797,625,024`
  bytes (`7.2621 GiB`), excluding allocator/runtime overhead. Breakdown:
  BF16 `5,205,643,456` B, I32 packed GPTQ `2,514,124,800` B, F16
  `77,856,768` B.
- Serialized weights are not identical to loaded GPU allocation: GPTQ packed
  tensors, scales, zeros, BF16 tensors, allocator alignment and runtime buffers
  affect loaded memory. Exact loaded weight memory must be captured from startup.

## KV bytes/token

For the standard MHA layout, TP=1, 44 layers, 2 KV heads, head dimension 128,
and the conservative BF16 expected KV dtype:

```text
2 (K+V) * 2 KV heads * 128 head_dim * 2 bytes * 44 layers
= 45,056 bytes/token
= 44 KiB/token
```

The actual KV dtype and resulting capacity remain a GPU-window observation. No
explicit `--kv-cache-dtype` is added to the prepared command.

## Mamba bytes/slot

Using current SGLang layout and actual config:

```text
conv shape per layer = [3584, 3]
temporal shape per layer = [24, 128, 256]
conv dtype = BF16
SSM dtype = BF16
layers = 44
```

| quantity | bytes/layer/slot | all 44 layers / slot |
|---|---:|---:|
| conv state | 21,504 B | 946,176 B / 0.9023 MiB |
| SSM state | 1,572,864 B | 69,206,016 B / 66.0 MiB |
| total | 1,594,368 B | **70,152,192 B / 66.9023 MiB** |

## State-slot ratios

From `kv_cache_configurator.py:_calculate_mamba_ratio`:

| path | slots per running request |
|---|---:|
| normal/no-buffer | 3 |
| extra-buffer + overlap | 5 |
| extra-buffer-lazy + overlap | 4 |
| no-buffer + decode-lock-skip | 3 |
| extra-buffer + overlap + decode-lock-skip | 4 |
| extra-buffer-lazy + overlap + decode-lock-skip | 3 |

With the prepared minimal command, the runtime resolves the model-specific
Mamba strategy; the actual selected ratio must be captured from startup/logs.

## Expected Mamba memory table — STATIC EXPECTATION

Values below are per-request state slots multiplied by the corresponding ratio;
they are not measured runtime allocations.

| running requests | no-buffer (3x) | extra-buffer-lazy (4x) | extra-buffer (5x) |
|---:|---:|---:|---:|
| 1 | 0.196 GiB | 0.261 GiB | 0.327 GiB |
| 2 | 0.392 GiB | 0.523 GiB | 0.653 GiB |
| 4 | 0.784 GiB | 1.045 GiB | 1.307 GiB |
| 8 | 1.568 GiB | 2.091 GiB | 2.613 GiB |
| 16 | 3.136 GiB | 4.181 GiB | 5.227 GiB |
| 24 | 4.704 GiB | 6.272 GiB | 7.840 GiB |
| 32 | 6.272 GiB | 8.363 GiB | 10.453 GiB |
| 48 | 9.408 GiB | 12.544 GiB | 15.680 GiB |
| 64 | 12.544 GiB | 16.726 GiB | 20.907 GiB |

Generator and machine-readable full table:

```text
control/G001-falcon-h1-phase1/static_accounting.py
/data/models/falcon-h1-phase1-artifact-accounting.json
```

## Prepared server command

Script:

```text
control/G001-falcon-h1-phase1/scripts/falcon_h1_phase1_server.sh
```

Effective command:

```bash
/home/ubuntu/venv/bin/python -m sglang.launch_server \
  --model-path /data/models/Falcon-H1-7B-Instruct-GPTQ-Int4 \
  --host 127.0.0.1 --port 30170 \
  --context-length 32768 \
  --mamba-ssm-dtype bfloat16
```

HiCache is off by omission, speculative decoding is off by omission, and Radix
cache remains at normal default. Port `30170` does not conflict with M4 `30000`.
No speculative, quantization, memory, or performance tuning flags were added.

## Prepared probe

```text
control/G001-falcon-h1-phase1/scripts/falcon_h1_phase1_probe.py
```

Fixed prompt, deterministic sampling (`temperature=0`, `top_p=1`, seed
`20260920`), default 32 output tokens, levels `1,2,4,8,16` with conditional
`24,32`. It uses SSE streaming and records first-chunk TTFT, request latency,
completion count, decode tok/s over the post-first-token window, aggregate rate,
success/failure, and `nvidia-smi` GPU samples. Queue time is not exposed by this
client and must be obtained from server/runtime evidence during the GPU window.

## GPU handoff runbook

```text
control/G001-falcon-h1-phase1/GPU-WINDOW-RUNBOOK.md
```

The fixed sequence is sanity -> start -> startup accounting -> health -> one
correctness request -> c=1/2/4/8/16 -> conditional 24/32 -> targeted clean
shutdown -> verify GPU released. It contains no kill of PID 2064356 or unknown
processes.

## Runtime modifications

**NONE.** No SGLang runtime, model weight, or incumbent M4 service was modified.

## Remaining blocker

Phase 1A preparation is complete. Phase 1 GPU execution remains blocked until
the owner explicitly releases the RTX 3090 and `nvidia-smi` confirms no serving
workload. No Phase 2 work was started.
