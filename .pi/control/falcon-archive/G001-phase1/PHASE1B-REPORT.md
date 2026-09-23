# Phase 1B — GPU bring-up + active-concurrency baseline

## VERDICT: BLOCKED

## GPU ownership

B0 passed at the start of this attempt:

```text
GPU: NVIDIA GeForce RTX 3090
UUID: GPU-2e3ed202-3655-d919-0a64-259209bc6587
memory: 1 MiB / 24576 MiB
utilization: 0%
compute processes: none
sglang serving processes: none
ports 30000/30170: none
```

The incumbent M4 service was not killed, restarted, or otherwise disturbed.
After the failed Falcon-H1 startup, the GPU returned to 1 MiB / 0% and no
Falcon-H1 process or `:30170` listener remained.

## Actual bring-up command

The existing Phase 1A command was used, with the already identified explicit
context override required to attempt the frozen 32768 cap:

```bash
CUDA_VISIBLE_DEVICES=0 \
SGLANG_MAMBA_SSM_DTYPE=bfloat16 \
SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1 \
PYTHONPATH=/home/ubuntu/workspaces/3rdparty/sglang-falcon-h1-7b/python \
/home/ubuntu/venv/bin/python -m sglang.launch_server \
  --model-path /data/models/Falcon-H1-7B-Instruct-GPTQ-Int4 \
  --host 127.0.0.1 --port 30170 \
  --context-length 32768 \
  --mamba-ssm-dtype bfloat16
```

Startup log:

```text
control/G001-falcon-h1-phase1/runs/phase1b-20260920-r2/server.log
```

## Actual quant/kernel path

Runtime log confirms:

```text
The model is convertible to gptq_marlin during runtime. Using gptq_marlin kernel.
```

Thus the actual selected quantization path reached the GPTQ-Marlin resolution,
not plain GPTQ. The process did not reach a successful completed model load.

## Decisive native load failure

Weight loading reached the Falcon-H1 model loader and failed with:

```text
KeyError: 'model.layers.0.qkqkv_proj.weight'
```

Traceback path:

```text
python/sglang/srt/models/falcon_h1.py:558 in load_weights
python/sglang/srt/model_loader/loader.py:1000 in load_weights_and_postprocess
```

The checkpoint's actual tensor mapping contains separate BF16 attention tensors:

```text
model.layers.0.self_attn.q_proj.weight
model.layers.0.self_attn.k_proj.weight
model.layers.0.self_attn.v_proj.weight
model.layers.0.self_attn.o_proj.weight
```

The current fork's `FalconH1ForCausalLM.load_weights` requested a fused
`model.layers.0.qkqkv_proj.weight` parameter that is absent from the official
checkpoint. This is a native checkpoint/model-loader incompatibility, not an
OOM or GPU-capacity result.

The log also records before failure:

```text
Load weight begin. avail mem=23.24 GB
```

No complete memory pool or runtime accounting was produced.

## B2–B5 status

STOP condition reached at native load failure. Not executed:

- `/health`
- OpenAI-compatible correctness request
- deterministic generation
- actual KV dtype/capacity
- Mamba radix strategy/slot ratio runtime confirmation
- `max_mamba_cache_size`
- requested/effective `max_running_requests`
- CUDA graph capture
- c=1/2/4/8/16 or c=24/32 benchmark
- 32K sanity
- bottleneck verdict

## Static-vs-runtime reconciliation

Only the following runtime facts were observed before failure:

| item | runtime evidence |
|---|---|
| context | 32768 accepted with explicit existing override; warning retained because derived config is 8192 |
| quant method | GPTQ-Marlin conversion selected |
| initial available GPU memory | 23.24 GB at weight-load start |
| model load | failed at missing fused QKV parameter |
| KV/Mamba pools | not initialized successfully |
| effective concurrency | not produced |

No static capacity table may be treated as a runtime result.

## Runtime modifications

```text
NONE
```

No SGLang runtime source, model weights, or checkpoint files were modified. The
explicit context override was an environment setting for this attempted launch,
not a code change.

## Recommended next frontier

Phase 1 must remain blocked pending an authority decision on the discovered
checkpoint/model-loader incompatibility. Continuing requires either an existing,
non-runtime-change compatibility configuration/path already present in the fork,
or explicit authorization for a narrowly scoped model-loader compatibility fix.
Do not enter concurrency measurement, HiCache, or performance work before native
load succeeds.
