ENTRY: ACCEPT

status: blocked

Task ID: OPS-20260908-3060-12G-QWEN35-4B-ENV-BOOTSTRAP-2  
Orchestration epoch: phase3-3060-4b-navigator/2026-09-08  
Role: devops-executor

## Summary

SSH connection and mandatory audit completed. A dedicated target directory was created and
the `sglang==0.5.19` wheel was installed without dependencies under the authorized target
environment directory. Verification is blocked because importing SGLang fails on missing
`orjson`. Per user instruction, no further installation or long-running operation was
attempted. No model was downloaded, no server was started, no benchmark was run, and no data
disk expansion was performed.

## Redacted commands and evidence

All SSH commands used `sshpass -e` with the authorized credential supplied out-of-band; the
password is intentionally absent from this report and all command output.

Audit command (remote, summarized):

    ssh -p 27460 root@i-1.gpushare.com 'bash -s'
    nvidia-smi; nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap --format=csv,noheader
    uname -a; cat /etc/os-release; findmnt -D; df -hT; df -ih
    du -xhd1 /; du -xhd2 /root; free -h; nproc; lscpu
    python --version; conda env list; pip --version; python -c 'import torch; ...'
    find /root -maxdepth 3 -type d ...; du -sh /root/.cache/huggingface /root/.cache/torch /root/models
    pip list | grep -Ei 'sglang|torch|awq|marlin|transformers|triton'

Key audit output:

    GPU: NVIDIA GeForce RTX 3060, 12288 MiB, compute capability 8.6 (SM86)
    Driver: 550.144.03; reported CUDA: 12.4
    Kernel: 5.15.0-136-generic; OS: Ubuntu 22.04.4 LTS
    GPU processes: none; GPU memory: 2 MiB / 12288 MiB
    RAM: 125 GiB total, 119 GiB available; swap: 0
    CPU: 48 logical CPUs, 2 sockets x 12 cores x 2 threads; Xeon E5-2697 v2
    System Python: 3.11.11; system torch: 2.5.1+cu124; torch CUDA available: True
    Conda command: not found; /root/miniconda3 did not exist initially

Disk/mount evidence at audit:

    / (overlay): 30G total, 88M used, 30G available, 1% (later 244M used after wheel)
    /root: on system overlay; initial du approximately 2.9G, mostly /root/.cache/pip
    /hy-model: xfs, 1.9T total, 912G used, 951G available, 49%; existing model mount
    /hy-tmp: xfs, 50G total, 0 used, 50G available; temporary mount
    Root filesystem inodes: approximately 5.2M used / 182M free (3% use)
    `/root/.cache/huggingface` and `/root/.cache/torch`: absent/zero reported; pip cache ~2.9G

Installation commands and output:

    python3 -m venv --system-site-packages /root/miniconda3/envs/sglang-3060-4b
    Result: failed; ensurepip returned non-zero because host Python lacks usable ensurepip.

    rm -rf /root/miniconda3/envs/sglang-3060-4b
    mkdir -p /root/miniconda3/envs/sglang-3060-4b
    ln -s /usr/local/bin/python /root/miniconda3/envs/sglang-3060-4b/python
    /usr/local/bin/python -m pip install --no-cache-dir --no-deps --target \
      /root/miniconda3/envs/sglang-3060-4b sglang
    Result: downloaded/installed `sglang-0.5.19` wheel, approximately 26.2 MB wheel and
    approximately 157M target directory. No dependency resolver was run.

Verification command:

    PYTHONPATH=/root/miniconda3/envs/sglang-3060-4b /usr/local/bin/python -c 'import torch; import sglang'

Verification output:

    python 3.11.11
    torch 2.5.1+cu124 cuda 12.4 available True capability (8, 6)
    sglang import ModuleNotFoundError: No module named 'orjson'
    sglang 0.5.19 is present in the target directory
    triton 3.1.0; torch 2.5.1+cu124; torchaudio 2.5.1+cu124; torchvision 0.20.1+cu124

## AWQ / Marlin detection

Import probes in the dedicated target path reported:

    awq: ABSENT (ModuleNotFoundError)
    autoawq: ABSENT (ModuleNotFoundError)
    marlin: ABSENT (ModuleNotFoundError)
    sgl_kernel: ABSENT (ModuleNotFoundError)

This is only package availability detection. It does not claim Qwen3.5 AWQ checkpoint or
Marlin kernel compatibility.

## Existing repositories and models

No `/root/models`, `/root/models/qwen35-4b-awq`, `/root/miniconda3`, or
`/root/sglang-3060-12g-hicache` existed at the initial path check. No existing SGLang/Qwen
repository or model was found by the authorized shallow scan. The setup directory was then
created with `SETUP_ONLY.md`; it contains no source checkout or checkpoint.

Created paths:

    /root/miniconda3/envs/sglang-3060-4b/
    /root/miniconda3/envs/sglang-3060-4b/python -> /usr/local/bin/python
    /root/miniconda3/envs/sglang-3060-4b/sglang/ (wheel and metadata only)
    /root/sglang-3060-12g-hicache/SETUP_ONLY.md

## L3 disk budget recommendation

No expansion was performed. The user states the data disk may be expanded up to 700G, but the
current task explicitly does not auto-expand. Treat the future data disk as L3-only and keep
it separate from system/model mounts. Recommended budget after an explicitly authorized
expansion: reserve about 600G usable for L3 payload, retain about 100G for filesystem headroom,
metadata, cleanup margin, and rotation. Do not place pip/Hugging Face/Torch caches, traces,
logs, source trees, or unrelated artifacts on that L3 disk. Current observed candidate mounts
are `/hy-model` (existing 1.9T model mount) and `/hy-tmp` (50G temporary mount); neither was
used for L3 setup or cache filling.

## Explicit exclusions

No BF16 model or any large checkpoint was fetched. No Qwen3.5 checkpoint was fetched. No
benchmark or performance experiment was run. No serving process was started. No unrelated
process was stopped. No 3090 Phase-2 product-candidate state was modified. No data disk was
expanded.

## Failure / next input

Blocking failure: dedicated SGLang import is incomplete because the dependency `orjson` is
absent; the initial venv method also failed because `ensurepip` is unavailable. The next
required input/action is a fresh Task ID authorizing a bounded dependency completion method
(and, if required, an explicit decision on whether a non-Conda isolated target directory is
acceptable). After that, SGLang import/version and AWQ/Marlin package detection can be
re-verified without downloading a checkpoint.

## Followups

None within this Task ID. Any dependency completion, model preparation, serving, benchmark,
cache relocation, or disk expansion requires a fresh Task ID and authorization.

## Open issues

1. SGLang import verification is blocked by missing `orjson` (observed, not inferred).
2. The requested path is not a real Conda environment because Conda is absent and `venv`
   bootstrap failed; it is currently an isolated package target using the system interpreter.
3. AWQ/Marlin support remains uninstalled and checkpoint compatibility remains unverified.
