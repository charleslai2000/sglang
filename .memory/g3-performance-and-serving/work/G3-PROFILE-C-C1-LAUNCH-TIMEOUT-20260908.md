# G3-PROFILE-C-C1-LAUNCH-TIMEOUT-20260908

ENTRY: ACCEPT

status: done
invocation_status: done
task_id: G3-PROFILE-C-C1-LAUNCH-TIMEOUT-20260908
epoch: E4
role: devops-executor

## Result

C1 admission PASS after the authorized full 600-second startup gate. No benchmark traffic, decode, dmon, query sampler, audit, tracing, GPU reset, download, or source/model edit was performed. Candidate is intentionally left running for a dependent task.

- RUN_ID: `g3-profile-c1-timeout-20260908T025800Z`
- Remote artifacts: `/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c1-timeout-20260908T025800Z/c1-timeout/launch/`
- Candidate PID: `478926`; port `18035`
- Tuple: `max-running-requests=4`, `max-mamba-cache-size=20`, `cuda-graph-max-bs-decode=4`
- Health: HTTP 200; 8035 absent; 18035 owned only by PID 478926
- Loads: idle (`num_running_reqs=0`, `num_waiting_reqs=0`), effective `max_running_requests=4`, `max_total_num_tokens=148053`
- Allocation: weights 11.857 GB; Mamba conv 0.06 GB + SSM 2.95 GB; KV 2.26 GB K + 2.26 GB V; graph 1.90 GB
- CUDA graphs: prefill completed in 70.41 s and decode completed in 2.21 s; no OOM; free VRAM 1.46 GB after decode graph
- GPU attribution: one candidate tree via `/dev/nvidia0` handles (478926/479012/479013); driver query shows one `[Not Found]` worker row (500367, 22792 MiB), with no competing fuser owner

## Commands and evidence

Pre-transition identity check matched PID 477405 to the exact restored `python -m sglang.launch_server` v1 argv and health/idle state. Only that numeric PID was TERM-stopped. Candidate was launched with the canonical argv and exact JSON argument `{"preserve_thinking": false}`, PATH including `/opt/cuda-conda/bin`, and offline/no-proxy environment.

Remote `final-admission.txt` records exact argv, health/loads, listener state, GPU/fuser attribution, client absence, allocations, and graph completion. `c1.log` records complete startup. `SHA256SUMS` records remote artifact hashes.

## Followups and open issues

Followup: dependent C1 decode may run only under its fresh authorized Task ID and plan workload contract; no traffic was sent here.

Open issue: NVIDIA compute-app query labels the candidate worker `[Not Found]`; device-handle ownership and process tree attribute all handles to the candidate, with no competing owner observed.

Final status: **done**
