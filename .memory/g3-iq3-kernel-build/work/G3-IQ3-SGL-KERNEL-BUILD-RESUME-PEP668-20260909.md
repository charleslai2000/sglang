# G3-IQ3-SGL-KERNEL-BUILD-RESUME-PEP668-20260909

status: pending
task_id: G3-IQ3-SGL-KERNEL-20260909
invocation_id: INV-G3-IQ3-SGL-KERNEL-004
epoch: E45
role: devops-executor (L4)
workdir: /home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s
memory_root: /home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s/.memory/g3-baseline-20260907
memory_inputs: [/home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s/.memory/g3-baseline-20260907/work/G3-IQ3-SGL-KERNEL-BUILD-RESUME-20260909.md]
memory_report: /home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s/.memory/g3-baseline-20260907/work/G3-IQ3-SGL-KERNEL-BUILD-RESUME-PEP668-20260909.md
observed_workspace_root: /home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s

The prior system-pip PEP668 failure is preserved in raw `build.log`. Per fresh dispatch, build dependencies were installed/verified with explicit venv Python under `sg dev -c`, using shared `PIP_CACHE_DIR=/mnt/data/cache/pip`; command exited 0. Raw evidence: `raw/.../deps.log`, `deps-status.txt`.

The existing build was resumed with venv `pip` and `uv` first on PATH, CUDA 13.0.48, and MAX_JOBS=2. CMake configured successfully and emitted SM86 gencode. Ninja is still actively compiling (PID 735313 observed); no service, benchmark, lock, or GPU workload was run. Raw log: `raw/.../build-final.log`.

Followups: wait for build completion, then install wheel and perform requested import/.so/SHA256/cuobjdump verification.
Open issues: none.
