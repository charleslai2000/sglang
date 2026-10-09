# OPS-20260909-3060-RUNTIME-SMOKE-DEPS

Status: blocked at bounded runtime smoke; no product or 3090 files changed.

## Target and procedure

- Remote: `root@i-1.gpushare.com:27460`, BatchMode key `/home/dev-codex/.ssh/sglang_3060_ed25519`
- Venv: `/root/sglang-env-3060-4b`
- Source: `/root/sglang-3060-12g-hicache`, editable SGLang source
- Staging input: `/hy-tmp/ops-081-sm86-import-20260909`
- Model: `/hy-tmp/models/Qwen3.5-4B-AWQ`
- GPU: NVIDIA GeForce RTX 3060, compute capability 8.6

## Baseline evidence

- Python: `3.11.11`
- Torch: `2.5.1+cu124`
- Torch CUDA: `12.4`
- `torch.cuda.is_available()`: `True`
- Initial GPU memory: `2 MiB / 12288 MiB`
- Existing kernel wheel: `sglang-kernel 0.4.6.post1`, from `/hy-tmp/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl`

## Authorized dependency changes

Installed only dependencies named by the import-gated procedure:

- `dill 0.4.1`
- `openai 3.8.0` (pip transitively installed/updated environment packages `anyio 4.15.1`, `httpx2 2.12.0`, `httpcore2 2.12.0`, `jiter 0.16.0`, `idna 3.19`, `h11 0.16.0`, `truststore 0.10.4`)
- `partial-json-parser 0.2.1.1.post7`
- `xgrammar 0.2.1`
- `sentencepiece 0.2.2`

No Torch, CUDA, SGLang, or old `sgl_kernel` package was uninstalled or replaced. Pip reported pre-existing/inherent project requirement conflicts, including the source metadata requiring `openai==2.6.1` and `torch==2.13.0`; those packages were not changed.

## Verification and blockers

`python -m sglang.launch_server --help` progressed past missing imports but failed while formatting argparse help:

```text
TypeError: %o format: an integer is required, not dict
```

Kernel resolution without staging override:

- Python module location: `/root/sglang-env-3060-4b/lib/python3.11/site-packages/sgl_kernel/__init__.py`
- Detected compute capability: `86`
- Package attempted SM100 binary and failed with:
  `ImportError: libnvrtc.so.13: cannot open shared object file`
- This was not repaired because installing a different CUDA 13 kernel is explicitly prohibited.

Bounded smoke command used staging first in `PYTHONPATH`, localhost port `30000`, TP1, FP8 E4M3 KV, CUDA graph max batch 1, max running requests 1, memory fraction `0.82`, max total tokens `65536`, and radix/RH disabled. The deprecated flag warning identified the exact equivalent `--cuda-graph-max-bs-decode`, but no retry was made because startup failed before model load.

Smoke result:

```text
SMOKE_RC=1
ImportError: cannot import name '_cuda_beginAllocateCurrentThreadToPool' from torch.cuda.memory
```

The service never reached HTTP readiness, no request was sent, and final GPU memory remained `2 MiB / 12288 MiB`. The process was terminated by the bounded command and did not leave a running server.

## Summary

The authorized missing-dependency gate was advanced through the named imports. Acceptance is not met: help has an argparse formatting failure, and the runtime smoke is blocked by the Torch API mismatch before model load. Further remediation would require a new Task ID and explicit procedure/authorization for the Torch/kernel compatibility issue.

## Open issues / followups

- Resolve the source help formatter `%o` error under a fresh task.
- Resolve Torch/SGLang compatibility without violating the prohibition on CUDA 13 kernel installation.
- Re-run HTTP/TTFT/output validation only after those blockers are authorized and fixed.
