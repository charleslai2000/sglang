# G3-IQ3-LOCAL-PREREQ-SCAN-20260909

Task ID: `G3-IQ3-LOCAL-PREREQ-SCAN-20260909`  
Epoch: E10  
Role: scout  
Status: `done` (read-only prerequisite scan)

## Scope and safety

Inspected only the local workstation and repository. No GPU workload was
started or stopped, no package/model download or installation was attempted,
and no user process was attached to beyond read-only `nvidia-smi` listings.

## Confirmed local state

The workstation has two visible GPUs:

| index | device | VRAM total | VRAM used | VRAM free | GPU util |
|---:|---|---:|---:|---:|---:|
| 0 | NVIDIA GeForce GT 1030 | 2048 MiB | 890 MiB | not queried | 1% |
| 1 | NVIDIA GeForce RTX 3090 | 24576 MiB | 37 MiB | 24086 MiB | 0% |

RTX 3090 read-only details: PCI bus `00000000:26:00.0`, driver
`580.178.04`, temperature 35 C, power 20.86 W. `nvidia-smi -i 1
--query-compute-apps` showed one Chrome GPU process (PID 4543); it uses the
reported 37 MiB. This is not a benchmark process. Because another program is
expected to use this machine, the 3090 must still be acquired through an
external queue/lock immediately before any test; this scan did not reserve it.

No `/data` mount exists on this workstation. In particular, these expected
deployment paths are absent:

- `/data/models/`
- `/data/sglang-qwen35-env/`
- `/opt/cuda-conda/`

Only `/usr/bin/python3` was found as a system Python command. Its import
specification has no `torch`, `sglang`, `transformers`, or `safetensors`.
No local `*.gguf` or IQ3_S model artifact was found under the searched local
roots (`/home/dev-codex`, `/mnt/data`, `/workspace`, `/models`, max depth 5).
The only matching `/mnt/data` item is the previously supplied source-review
ZIP, not model weights.

## Repository inputs

The checkpoint [3090-dev/qwen3-27b-iq3s-b2-checkpoint.md](../../../../3090-dev/qwen3-27b-iq3s-b2-checkpoint.md)
documents the remote deployment, including the model path
`/data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`, the
`/data/sglang-qwen35-env` environment, and the frozen launch parameters. Those
are remote-host facts from the checkpoint, not local prerequisites. Existing
local launch/evidence material is under `3090-dev/`; no local script supplies
the absent model or environment.

The worktree is already dirty with user and experiment files and is one commit
ahead of its configured origin. This scan made no product or user-file edits;
the only new file is this specialist report.

## Readiness conclusion

The new local RTX 3090 hardware is visible and currently has approximately
24.1 GiB free, but local deployment is **not ready**: the SGLang runtime,
CUDA/venv toolchain, and 27B IQ3_S GGUF are absent locally. The remote
`/data/...` paths must not be assumed to exist on this workstation.

## Safe queued preparation checklist

1. Agree on a queue/lock owner with the other GPU user; do not launch while
   the lock is held by the other program.
2. At queue acquisition, re-check `nvidia-smi -i 1` and record all processes;
   do not kill the Chrome process or any newly appearing owner process.
3. User supplies or mounts the approved IQ3_S GGUF and the matching SGLang
   environment/toolchain locally; verify exact paths and hashes read-only.
4. Validate `torch.cuda.get_device_capability()` is `(8, 6)` and import the
   intended checkout/venv before any server launch.
5. Use the frozen v1 profile and an isolated local port/process. Release the
   queue lock and preserve logs/artifacts after the test.

No deployment or benchmark should be claimed from this scan alone.

## Commands/evidence

Read-only commands used: `nvidia-smi --query-gpu`, `nvidia-smi -i 1
--query-compute-apps`, `ls -ld` for expected mount paths, targeted `find` for
GGUF/IQ3_S artifacts, Python `importlib.util.find_spec`, targeted repository
`find`/`rg`, and `git status --short --branch`.

Open issues: model/env provisioning location is unspecified; queue/lock
mechanism with the other local GPU user is not yet established.
