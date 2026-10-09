# DEVOPS-20260909-RECONSTRUCT-SM86-LAUNCH

## Invocation

- Task ID: `DEVOPS-20260909-RECONSTRUCT-SM86-LAUNCH`
- Orchestration epoch: `20260909-P4`
- Role: `devops`
- Target: `root@i-1.gpushare.com:27460` (RTX 3060, SM86)
- Status: `done`

## Summary

Reconstructed the working 3060 runtime and brought the reviewed hybrid-frontier
fix online. The live service is PID `76671`; `/health` returned HTTP `200`, the
process remained alive, and port `30000` remained listening during final
verification.

The essential runtime correction is:

```text
PATH=/root/sglang-env-3060-4b/bin:$PATH
PYTHONPATH=/hy-tmp/ops-081-sm86-import-20260909:/root/sglang-3060-12g-hicache/python
```

The first reconstructed launch used the historical unquoted-prefix-key string
and exited with `JSONDecodeError`. That failed attempt is preserved. The final
launch uses the equivalent valid JSON object for the reviewed controller.

## Observed environment facts

- GPU: `NVIDIA GeForce RTX 3060`, compute capability `8.6`, 12 GiB.
- NVIDIA driver: `550.144.03`.
- CUDA toolkit: `12.4`, `nvcc 12.4.131`.
- Runtime Python: `/root/sglang-env-3060-4b/bin/python`, Python `3.11.11`.
- Torch: `2.6.0+cu124`; `torch.version.cuda=12.4`; CUDA is available.
- `ninja`: `/root/sglang-env-3060-4b/bin/ninja`, version `1.13.2`.
- SM86 staging package: `/hy-tmp/ops-081-sm86-import-20260909/sgl_kernel`.
- Full SGLang source: `/root/sglang-3060-12g-hicache/python`.
- Model: `/hy-tmp/models/Qwen3.5-4B-AWQ`.
- Existing storage: `/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`.
- Storage was not cleared or deleted. Final observed mode/owner: `755 root:root`.

## Diagnosis and repair

The previous retry had two independent runtime faults:

1. Without the runtime `PATH`, FlashInfer could not execute `ninja`.
2. Without the staging `PYTHONPATH`, import selected the environment's
   `sgl_kernel/sm100/common_ops.abi3.so`, which requires CUDA 13 libraries and
   is incompatible with the SM86/CUDA 12 host.

The staging directory contains the SM86 binary and was placed first in
`PYTHONPATH`. Import-only verification passed before service start:

```text
sgl_kernel.common_ops =
/hy-tmp/ops-081-sm86-import-20260909/sgl_kernel/sm86/common_ops.cpython-311-x86_64-linux-gnu.so
torch.version.cuda = 12.4
GPU capability = (8, 6)
```

The reviewed file was already present at:

```text
/root/miniconda3/envs/sglang-3060-4b/sglang/srt/mem_cache/unified_radix_cache.py
```

The full source tree used by the prior launch still had the pre-fix file, so it
was backed up and overlaid with the reviewed file. No other source file was
changed.

## File and provenance evidence

Reviewed SHA-256:

```text
395e55efc4d472547581d2a33d7b989933fb78990cf4a455d8daa0e02845a203
```

Observed after repair:

```text
395e55efc4d472547581d2a33d7b989933fb78990cf4a455d8daa0e02845a203  /root/miniconda3/envs/sglang-3060-4b/sglang/srt/mem_cache/unified_radix_cache.py
395e55efc4d472547581d2a33d7b989933fb78990cf4a455d8daa0e02845a203  /root/sglang-3060-12g-hicache/python/sglang/srt/mem_cache/unified_radix_cache.py
0eba576ee9aa36aa5ecb2e901273dc70e379d71b4663a774e5c53910b44ab970  /root/sglang-3060-12g-hicache/python/sglang/srt/mem_cache/unified_radix_cache.py.backup-DEVOPS-20260909-RECONSTRUCT-SM86-LAUNCH
3d2a6efd611a0aa2109ccc1cfac72c0669ffbe49c354e4f0dda742dabc66ffc9  /hy-tmp/ops-081-sm86-import-20260909/sgl_kernel/sm86/common_ops.cpython-311-x86_64-linux-gnu.so
```

The live process environment and memory map recorded:

```text
PATH=/root/sglang-env-3060-4b/bin:...
PYTHONPATH=/hy-tmp/ops-081-sm86-import-20260909:/root/sglang-3060-12g-hicache/python
SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/hy-tmp/hicache-qwen35-4b-p4-retry-20260909
/hy-tmp/ops-081-sm86-import-20260909/sgl_kernel/sm86/common_ops.cpython-311-x86_64-linux-gnu.so
```

The SM86 binary's dynamic dependencies are CUDA 12 (`libcublas.so.12`,
`libcudart.so.12`). Host verification found `CUDA13_RUNTIME_ABSENT`; no CUDA 13
installation or toolkit replacement was performed.

## Exact final launch command

Executed remotely with `nohup`; log and PID file are listed below.

```bash
export PATH=/root/sglang-env-3060-4b/bin:$PATH
export PYTHONPATH=/hy-tmp/ops-081-sm86-import-20260909:/root/sglang-3060-12g-hicache/python
export SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/hy-tmp/hicache-qwen35-4b-p4-retry-20260909

/root/sglang-env-3060-4b/bin/python -m sglang.launch_server \
  --model-path /hy-tmp/models/Qwen3.5-4B-AWQ \
  --tokenizer-path /hy-tmp/models/Qwen3.5-4B-AWQ \
  --kv-cache-dtype fp8_e4m3 \
  --mem-fraction-static 0.82 \
  --max-total-tokens 65536 \
  --max-running-requests 1 \
  --chunked-prefill-size 2048 \
  --max-prefill-tokens 16384 \
  --tp-size 1 \
  --attention-backend flashinfer \
  --sampling-backend flashinfer \
  --mamba-backend triton \
  --mamba-full-memory-ratio 0.9 \
  --mamba-radix-cache-strategy extra_buffer \
  --mamba-track-interval 256 \
  --cuda-graph-backend-decode full \
  --cuda-graph-max-bs-decode 1 \
  --cuda-graph-bs-decode 1 \
  --cuda-graph-backend-prefill breakable \
  --cuda-graph-bs-prefill 4 8 16 32 \
  --enable-hierarchical-cache \
  --hicache-ratio 2.0 \
  --hicache-write-policy write_through \
  --hicache-io-backend kernel \
  --hicache-mem-layout page_first \
  --hicache-storage-backend file \
  --hicache-storage-prefetch-policy wait_complete \
  --hicache-storage-backend-extra-config '{"hicache_storage_pass_prefix_keys":true}' \
  --hicache-storage-prefetch-retry-poll-interval 1 \
  --hicache-storage-prefetch-retry-max-attempts 120 \
  --hicache-restore-wait-timeout-s 180 \
  --enable-cache-report \
  --host 127.0.0.1 \
  --port 30000
```

The effective `server_args` line confirms the requested profile, including
`max_total_tokens=65536`, `max_running_requests=1`, `tp_size=1`, FP8 E4M3 KV,
HiCache ratio 2.0, write-through, file backend, prefix keys, retry interval 1,
retry attempts 120, restore timeout 180, RH off, and the decode/prefill CUDA
graph settings above.

## Service verification

Live process:

```text
PID 76671, PPID 1, state Sl
LISTEN 127.0.0.1:30000, users:("python",pid=76671)
```

Health checks returned HTTP `200` on the readiness probe and on three additional
stability probes. The final log contains:

```text
Load weight end ... quant=compressed-tensors
Mamba Cache is allocated. max_mamba_cache_size: 53 ...
KV Cache is allocated. dtype: torch.float8_e4m3fn, #tokens: 65536
Capture target prefill CUDA graph end ...
Capture target decode CUDA graph end ... bs=[1]
Init Unified Radix Cache. Components: (FULL, MAMBA)
The server is fired up and ready to roll!
```

The final log has zero `Traceback`, `JSONDecodeError`, `ImportError`,
`FileNotFoundError`, CUDA-error, out-of-memory, or `ERROR` matches.

## Artifacts and evidence

Remote artifacts:

- Final service log:
  `/tmp/qwen35-4b-hicache-p4-reconstruct-sm86-20260909-json.log`
  - SHA-256: `4df1162755980b60ba4bb760df59e8acda0c97c82d003ec479d37292e4e70f03`
- Final PID file:
  `/tmp/qwen35-4b-hicache-p4-reconstruct-sm86-20260909-json.pid`
  - content: `76671`
- Preserved failed-attempt log:
  `/tmp/qwen35-4b-hicache-p4-reconstruct-sm86-20260909.log`
  - SHA-256: `ae934782d1130ed032d16b657670694a7a2decc9c78d0f834fc6a5ce1b9d2965`
- Source pre-change backup:
  `/root/sglang-3060-12g-hicache/python/sglang/srt/mem_cache/unified_radix_cache.py.backup-DEVOPS-20260909-RECONSTRUCT-SM86-LAUNCH`

Prior reports read:

- `OPS-20260909-DEPLOY-HYBRID-GUARD.md`
- `OPS-20260909-RESTART-NINJA.md`
- `HANDOFF-2026-09-07.md`
- `TEST-20260909-3060-BASELINE-CAP-CONC.md`
- `TEST-20260909-3060-P4-HICACHE.md`
- `TST-20260908-3060-12G-LOCAL-SOURCE-BASELINE.md`

## Rollback and boundaries

Rollback is prepared but not executed: restore the source file from
`unified_radix_cache.py.backup-DEVOPS-20260909-RECONSTRUCT-SM86-LAUNCH`, then
stop PID `76671` using its exact PID and verify port `30000` is closed. Do not
delete the HiCache directory or evidence logs.

No 3090 worktree or branch was touched. No CUDA 13 package/toolkit was
installed. No HiCache storage or prior evidence log was deleted.

## Followups

- Keep PID `76671` and the final log as the active 3060 test service/evidence.
- If a request-level test or shutdown is required, dispatch a fresh Task ID.

## Open issues

- The exact original shell command was not present in remote shell history; the
  prior effective arguments were recovered from the historical `server_args`
  log and matched by the final live process command line.
- The historical prefix-key string was not valid JSON for the reviewed
  controller; the final command uses valid JSON with the same key/value.
- The service is validated for readiness and startup provenance here; no new
  request workload was issued by this operational task.

## Invocation handoff

`status`: `done`  
`artifacts`: final service/PID logs, preserved failed-attempt log, source backup,
reviewed deployed file  
`evidence`: import gate, live `/proc` provenance, CUDA/SM86 dependency checks,
health 200, process/listener state, final startup log  
`summary`: 3060 Qwen3.5-4B HiCache service reconstructed and running with the
reviewed hybrid-frontier fix and SM86/CUDA12 kernel provenance  
`followups`: fresh Task ID for any request test or shutdown  
`open_issues`: original shell history unavailable; no request workload run

Extra work requires a fresh Task ID.
