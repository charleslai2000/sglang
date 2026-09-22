# Phase C5 — canonical build + two-model RTX 3090 runtime

Reference authority at start: `578da796777ec0ed307ee24927793c1e2079e08e`.

## Result

```text
LOCAL_MODEL_A=LOCAL-PROD-v1.1.2 / Qwen3.5-9B W4A16
LOCAL_MODEL_B=LOCAL-PROD-v1.2.1-M2 / OmniCoder-9B GPTQ-Int4
CANONICAL_BUILD=PASS
RUNTIME_PROVENANCE=CANONICAL
LOCAL_MODEL_A_3090_RUNTIME=PASS
LOCAL_MODEL_B_3090_RUNTIME=PASS
```

The canonical source worktree was clean after the run. No `/opt/sglang/*/src` was placed on `PYTHONPATH`, and neither runtime was launched from an `/opt` source tree.

## Actual model identity and configuration

Identity was taken from the available frozen launcher/configuration and the model files, not from historical M3/M4 labels.

### Model A

* logical/frozen identity: `LOCAL-PROD-v1.1.2`
* physical model path: `/data/models/qwen35-9b-w4a16`
* model architecture: `Qwen3_5ForConditionalGeneration`; config `model_type=qwen3_5`
* quantization: compressed-tensors `pack-quantized`, int4, group size 128, symmetric; runtime reported `quant=compressed-tensors`
* endpoint: `127.0.0.1:30000`
* launch command:

```text
/home/ubuntu/venvs/sglang-3090/bin/python -m sglang.launch_server \
  --model-path /data/models/qwen35-9b-w4a16 --host 127.0.0.1 --port 30000 \
  --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 65536 \
  --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer \
  --linear-attn-prefill-backend triton --linear-attn-decode-backend triton \
  --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 \
  --enable-hierarchical-cache --hicache-write-policy write_back \
  --hicache-storage-backend extent --hicache-storage-prefetch-policy wait_complete \
  --hicache-size 32 --enable-ready-horizon --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder --enable-metrics --disable-prefill-cuda-graph
```

This is the v1.1.2 launcher model/argument contract, with the production scaffold's per-run lock/L3 wrapper omitted because C5 used an isolated endpoint and did not perform HiCache acceptance.

### Model B

* logical/frozen identity: `LOCAL-PROD-v1.2.1-M2`
* physical model path: `/data/models/omnicoder-9b-gptq-int4`
* model architecture: `Qwen3_5ForConditionalGeneration`; config `model_type=qwen3_5`
* quantization: GPTQ int4, group size 128, symmetric, `desc_act=false`; runtime reported `quant=gptq`, bits=4, and selected `gptq_marlin`
* endpoint: `127.0.0.1:30001`
* launch command:

```text
/home/ubuntu/venvs/sglang-3090/bin/python -m sglang.launch_server \
  --model-path /data/models/omnicoder-9b-gptq-int4 --host 127.0.0.1 --port 30001 \
  --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 262144 \
  --context-length 131072 --max-running-requests 8 --max-mamba-cache-size 48 \
  --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer \
  --linear-attn-prefill-backend triton --linear-attn-decode-backend triton \
  --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 \
  --enable-hierarchical-cache --hicache-write-policy write_back --hicache-size 32 \
  --hicache-host-memory-mode cache --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder --enable-metrics --disable-prefill-cuda-graph
```

This matches the M2 launcher’s actual model path and host-memory configuration. No model or quantization conversion was performed.

## Build and provenance

* canonical commit used: `578da796777ec0ed307ee24927793c1e2079e08e`
* build command: `cd python && /home/ubuntu/venvs/sglang-c5-canonical/bin/python -m build --wheel --no-isolation --outdir /home/ubuntu/c5-artifacts`
* wheel: `/home/ubuntu/c5-artifacts/sglang-0.5.21.dev114+g578da7967-cp312-cp312-linux_x86_64.whl`
* canonical editable install: `/home/ubuntu/venvs/sglang-c5-canonical`
* runtime environment: `/home/ubuntu/venvs/sglang-3090` with canonical editable SGLang source, used only after confirming its editable project location is the canonical worktree
* `sglang.__file__`: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/__init__.py`
* Rust native extensions:
  * `_server`: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/rust_extensions/_server.cpython-312-x86_64-linux-gnu.so`
  * `_grpc`: same canonical `python/sglang/srt/rust_extensions/` directory
  * `_multimodal`: same canonical directory
* `sgl_kernel`: `/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages/sgl_kernel/__init__.py`; this is an installed binary dependency, not an `/opt` source import
* Python: 3.12.3; Torch: `2.13.0+cu129`; CUDA runtime: 12.9
* GPU: NVIDIA GeForce RTX 3090, driver `580.178.04`, 24576 MiB

The first isolated build environment exposed missing `wheel`, `setuptools-rust`, and `setuptools-scm`; these were installed into the new C5 environment. The final wheel build passed. The wheel output was kept outside the Git worktree.

## Runtime evidence

### Model A

* server startup completed; `/health` returned HTTP 200 at `2026-09-22 20:51:42` after initial warmup/cuda-graph capture
* runtime log: `/tmp/c5-qwen.log`
* weight load: `quant=compressed-tensors`, weight load memory usage `10.36 GB`; available GPU memory after load `12.88 GB`
* peak observed during service: `18593 MiB used`, `5532 MiB free`
* request 1: HTTP 200, response `canonical runtime pass.` with `enable_thinking=false`
* request 2: HTTP 200, non-empty reasoning response; a follow-up non-thinking request also returned HTTP 200 and exact non-empty text
* no OOM, illegal access, or fatal runtime error observed

### Model B

* server startup completed; `/health` returned HTTP 200 at `2026-09-22 20:55:07`
* runtime log: `/tmp/c5-omni.log`
* weight load: `quant=gptq`, `bits=4`, weight load memory usage `10.97 GB`; available GPU memory after load `12.27 GB`
* peak observed during service: `19127 MiB used`, `4998 MiB free`
* request 1: HTTP 200, response `canonical OmniCoder runtime pass.`
* request 2: HTTP 200, non-empty coherent response: `A compiler is a program that translates source code written in a high-level language into machine code that a computer can execute.`
* no OOM, illegal access, or fatal runtime error observed

The environment emitted repeated non-fatal `torchcodec`/missing `libavutil.so` warnings during multimodal import. They did not affect either text model startup or requests and are not counted as runtime failures.

Both servers were stopped after evidence collection; GPU memory returned to 4 MiB used / 24121 MiB free.

## Boundary compliance

No HiCache formal acceptance was performed. No old branch, worktree, deployment tree, or `/opt` directory was deleted. No push or `main` modification occurred. No model files, quantization formats, or production source semantics were changed.
