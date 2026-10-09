# G3-IQ3-LOCAL-PROVISION-20260909

status: blocked_on_dependency_network
invocation: INV-G3-IQ3-LOCAL-PROVISION-001

## Scope

Prepared only `/mnt/data/qwen3-g3-baseline/`; no GPU process was started,
stopped, or attached. Installation checks use `CUDA_VISIBLE_DEVICES=''`.

## Completed

- Host exposes GT 1030 and RTX 3090; CUDA toolkit reports `12.0.140`.
- Created `venv`, `models`, `build`, `artifacts`, and `locks` under the authorized directory.
- Python `3.12.3`; pip `24.0`.
- Hugging Face tree recorded at `artifacts/hf-tree.json`.
- Exact authorized model URL recorded at `artifacts/model-url.txt`.
- Target GGUF download is actively running in invocation session; expected size
  `11771546784` bytes. At report creation it had reached approximately 4.5%.

## Not yet complete

- GGUF SHA-256 and final size (download pending).
- Tokenizer/config/chat-template sidecars: target GGUF repository contains none;
  do not substitute or download another model without a fresh authorization.
- Python package installation/import verification: blocked. Two official cu130
  attempts failed integrity validation on mutable `pypi.nvidia.com` wheels
  (`nvidia-cudnn-cu13`, then `nvidia-cublas`); retries were stopped without
  bypassing hashes or changing versions/index.
- SM86 shared-object production/verification is outside this invocation and is
  not claimed.

Raw logs: `.memory/g3-baseline-20260907/work/raw/g3-iq3-local-provision-20260909/`

## Blocker

Root must provide a verifiable wheel cache or repair the `pypi.nvidia.com`
network path before Torch provisioning can resume. No GPU/service was started.
