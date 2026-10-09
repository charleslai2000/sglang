# TEST3060-AWQ-RUNTIME-AUDIT-20260910

status: done
entry: ACCEPT
task_id: T3060-AWQ-RUNTIME-AUDIT-20260910
invocation_id: INV-20260910-TEST-AWQ-RUNTIME-AUDIT-R1
orchestration_epoch: 20260910-awq-runtime-audit
role: tester
capability_level: L3

## Binding and workspace check

- workdir: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- memory_root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design`
- memory_inputs:
  - `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-TENSOR-BOOL-PROBE-R4-20260910.md`
  - `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-ENV-PATH-RESTORE-20260910.md`
- memory_report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST3060-AWQ-RUNTIME-AUDIT-20260910.md`
- parent_thread_id: `01a07bea-d668-75b2-8280-6a2cf0870c1e`
- observed workspace root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` (matched)

The repository had pre-existing untracked `.memory/`, `review/gates/`, and `storage/`
entries at entry. No product implementation file was changed by this audit. The audit
used only read-only remote commands and GET requests to `/health` and `/model_info`; no
inference request was sent.

## Result summary

The remote service was healthy at the final check. PID `140507` is the service process
and owns listener `127.0.0.1:30000`; `/health` returned HTTP 200 at
`2026-09-10T02:55:27+08:00`.

The running checkpoint/backend evidence is:

- Checkpoint path: `/hy-tmp/models/Qwen3.5-4B-AWQ`.
- Model metadata: `Qwen3_5ForConditionalGeneration`, `model_type=qwen3_5`.
- Checkpoint config: `quant_method=compressed-tensors`, `format=pack-quantized`,
  `quantization_status=compressed`, INT4 group size 128, symmetric W4A16.
- `recipe.yaml` directly identifies `AWQModifier` and `QuantizationModifier` with
  `scheme: W4A16`; the model README identifies it as AWQ 4-bit in compressed-tensors
  format.
- SGLang startup directly reports `quant=compressed-tensors`.
- Marlin is proven for this startup: the log directly says
  `You are running Marlin kernel with bf16 on GPUs before SM90.` This is not an inference
  from the model name.

## Reproducible commands and outputs

All remote commands used:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=20 \
  -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 \
  root@i-1.gpushare.com '<read-only ps/ss/curl/nvidia-smi/log/package commands>'
```

The final process/listener/health command returned:

```text
REMOTE_DATE=2026-09-10T02:53:00+08:00
140507 ... /root/sglang-env-3060-4b/bin/python -m sglang.launch_server \
  --model-path /hy-tmp/models/Qwen3.5-4B-AWQ \
  --tokenizer-path /hy-tmp/models/Qwen3.5-4B-AWQ \
  --host 127.0.0.1 --port 30000 --tp-size 1 \
  --mem-fraction-static 0.82 --max-running-requests 1 \
  --max-total-tokens 65536 --chunked-prefill-size 2048 \
  --max-prefill-tokens 16384 --kv-cache-dtype fp8_e4m3 \
  --enable-hierarchical-cache --hicache-host-memory-mode cache \
  --hicache-ratio 2.0 --hicache-write-policy write_through \
  --hicache-io-backend kernel --hicache-mem-layout page_first \
  --hicache-storage-backend file --hicache-storage-prefetch-policy wait_complete \
  --enable-ready-horizon --ready-horizon-frontier-n 8 \
  --hicache-prefetch-speculative-fraction 0.6 \
  --cuda-graph-backend-decode full --cuda-graph-backend-prefill breakable \
  --cuda-graph-bs-decode 1 --cuda-graph-bs-prefill 4 8 16 32
LISTEN ... 127.0.0.1:30000 ... users:(("python",pid=140507,fd=59))
HTTP/1.1 200 OK
server: uvicorn
```

The current `/model_info` GET returned, in relevant fields:

```json
{"model_path":"/hy-tmp/models/Qwen3.5-4B-AWQ",
 "served_model_name":"/hy-tmp/models/Qwen3.5-4B-AWQ",
 "tokenizer_path":"/hy-tmp/models/Qwen3.5-4B-AWQ",
 "is_generation":true,"model_type":"qwen3_5",
 "architectures":["Qwen3_5ForConditionalGeneration"]}
```

Imported package metadata from `/root/sglang-env-3060-4b/bin/python`:

```text
IMPORT sglang file=/root/sglang-3060-12g-hicache/python/sglang/__init__.py version=0.0.0.dev0
IMPORT torch file=/root/sglang-env-3060-4b/lib/python3.11/site-packages/torch/__init__.py version=2.6.0+cu124
IMPORT transformers file=/root/sglang-env-3060-4b/lib/python3.11/site-packages/transformers/__init__.py version=5.12.1
IMPORT compressed_tensors file=/root/sglang-env-3060-4b/lib/python3.11/site-packages/compressed_tensors/__init__.py version=0.18.0
IMPORT autoawq ERROR ModuleNotFoundError: No module named 'autoawq'
DIST compressed-tensors version=0.18.0 location=/root/sglang-env-3060-4b/lib/python3.11/site-packages
DIST autoawq ERROR PackageNotFoundError
MODULE sglang.srt.layers.quantization.awq origin=/root/sglang-3060-12g-hicache/python/sglang/srt/layers/quantization/awq/__init__.py
CLASS AWQMarlinConfig module=sglang.srt.layers.quantization.awq.awq
CLASS AWQMarlinLinearScheme module=sglang.srt.layers.quantization.awq.schemes.awq_marlin
MODULE sglang.srt.layers.quantization.compressed_tensors path=/root/sglang-3060-12g-hicache/python/sglang/srt/layers/quantization/compressed_tensors
```

Checkpoint config/recipe excerpts:

```text
config.json: format=pack-quantized
config.json: weights.group_size=128, num_bits=4, strategy=group, symmetric=true, type=int
config.json: quant_method=compressed-tensors, quantization_status=compressed
recipe.yaml: AWQModifier
recipe.yaml: QuantizationModifier ... scheme: W4A16
```

The current service log is `/tmp/sglang3060-rh-tensor-bool-rollback-r4-20260910-024837.log`.
Relevant startup lines are:

```text
[02:49:17] Load weight end. elapsed=3.75 s, type=Qwen3_5ForConditionalGeneration, quant=compressed-tensors, avail mem=7.77 GB, mem usage=3.85 GB.
[02:49:20] Mamba Cache is allocated. max_mamba_cache_size: 53, conv_state size: 0.06GB, ssm_state size: 2.53GB
[02:49:20] KV Cache is allocated. dtype: torch.float8_e4m3fn, #tokens: 65536, K size: 0.50 GB, V size: 0.50 GB
[02:49:20] Memory pool end. avail mem=4.11 GB
[02:49:21] Capture target prefill CUDA graph begin. backend=breakable, num_tokens=[4, 8, 16, 32], avail mem=3.70 GB
[02:49:23] You are running Marlin kernel with bf16 on GPUs before SM90.
[02:49:26] Capture target prefill CUDA graph end. elapsed=5.44 s, mem usage=0.06 GB, avail mem=3.64 GB.
[02:49:26] Capture target decode CUDA graph begin. backend=full, num_tokens_per_req=1, bs=[1], avail mem=3.64 GB
[02:49:27] Capture target decode CUDA graph end. elapsed=1.28 s, mem usage=0.03 GB, avail mem=3.61 GB.
[02:49:27] max_total_num_tokens=65536, chunked_prefill_size=2048, max_prefill_tokens=16384, max_running_requests=1, context_len=262144, available_gpu_mem=3.61 GB
[02:49:27] Allocating kv hierarchical KV host pool: 131073 tokens, 2.15 GB host memory.
[02:49:29] Allocating 5.51 GB host memory for hierarchical Mamba cache (layout=page_first).
[02:49:33] Engine startup timings (s): load_weight=3.75, kv_cache_allocation=0.02, scheduler_e2e=28.73, cuda_graph={prefill=5.44, decode=1.28, target_verify=0.00, draft_prefill=0.00, draft_decode=0.00, draft_extend=0.00}, tokenizer_e2e=42.06
[02:49:39] INFO: 127.0.0.1:46616 - "GET /health HTTP/1.1" 200 OK
```

The log had no matches for `Traceback`, `RuntimeError`, `CUDA out of memory`, `FATAL`,
`CRITICAL`, `NCCL.*error`, or `failed to` in the focused fatal-class check. It does contain
non-fatal optional-dependency warnings for `cutlass`, `torchcodec`, and `openai_harmony`,
plus the FP8 scaling-factor warning; these did not prevent readiness.

Current remote GPU snapshot at `2026-09-10 02:54:46 +08:00`:

```text
GPU 0 NVIDIA GeForce RTX 3060
Memory-Usage: 8513MiB / 12288MiB
Free: 3525MiB
GPU-Util: 0%
Driver 550.144.03, CUDA 12.4
```

The startup log's `mem usage=3.85 GB` is the directly reported weight-load GPU memory.
The current `nvidia-smi` aggregate is 8513 MiB used and 3525 MiB free. `nvidia-smi`
showed an empty process table in the remote container, so the 8513 MiB aggregate cannot
be independently attributed entirely to PID 140507 from that table. The service PID,
its `/proc` status, command line, listener ownership, and startup memory accounting were
independently verified.

## Acceptance criteria

- Model checkpoint/backend/quantization path: PASS; process, `/model_info`, config,
  recipe, package metadata, and startup log agree on Qwen3.5-4B-AWQ and
  compressed-tensors/W4A16.
- Marlin claim discipline: PASS; Marlin is directly shown by the startup log, not inferred.
- Weight VRAM: PASS with source qualification; startup reports 3.85 GB.
- Mamba pool: PASS; max pool 53, device state sizes 0.06 GB + 2.53 GB, hierarchical host
  allocation 5.51 GB.
- FP8 KV pool/token budget: PASS; `torch.float8_e4m3fn`, 65,536 tokens, K/V 0.50 GB each,
  max-total-token budget 65,536.
- CUDA graph capture: PASS; prefill breakable [4,8,16,32] and decode full bs [1] both ended.
- Current VRAM: PASS; 8513 MiB used / 3525 MiB free of 12288 MiB at snapshot time.
- Exact PID/health: PASS; PID 140507, listener owned by PID 140507, `/health` HTTP 200.
- Safety scope: PASS; no restart, deploy, inference request, file edit, Neuron action, or
  unrelated GPU-process action performed.

## Followups

None within this invocation.

## Open issues

- `nvidia-smi` process attribution is limited by the remote container PID namespace: the
  aggregate GPU usage is reliable, but the process table is empty. Do not interpret 8513
  MiB as a PID-exclusive measurement.
- The service logs the expected FP8 warning that no scaling factors were provided and
  defaults them to 1.0; this is an operational quality risk, not a readiness failure.
- Optional dependency warnings (`cutlass`, `torchcodec`, `openai_harmony`) were observed;
  none blocked this text/generation service's HTTP readiness.

## Lifecycle communication

`mcp__codex_tui__send_message_to_thread` was available and accepted the ENTRY event for
`parent_thread_id=01a07bea-d668-75b2-8280-6a2cf0870c1e`. A terminal done event is sent
after this report is written.
