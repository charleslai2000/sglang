ENTRY: ACCEPT
Task ID: D3060-GPU-OWNER-AUDIT-RETRY-20260909
Orchestration epoch: 20260909-rh-ab4
Role: devops-executor
Invocation status: done

## Scope and authorization

Read-only remote GPU/process/port audit. No process was killed, suspended, restarted, or modified; no files, storage, or source were touched remotely.

## Command and authentication evidence

SSH command used exactly:

    ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@i-1.gpushare.com

Authentication succeeded (SSH exit code 0). The remote read-only command ran:

    nvidia-smi -q -d PIDS,COMPUTE,MEMORY,UTILIZATION
    ps -eo pid,etime,cmd | grep -Ei "[g]pu|[n]euron|[s]glang|[v]llm|[t]orch"
    ss -ltnp "sport = :30000"
    lsof -nP -iTCP:30000 -sTCP:LISTEN

The final `lsof` probe reported `bash: line 1: lsof: command not found`; `ss` completed successfully.

## Observed evidence

- GPU: one device at PCI address `00000000:41:00.0`; driver `550.144.03`; CUDA `12.4`.
- FB memory: total `12288 MiB`, reserved `251 MiB`, used `8513 MiB`, free `3525 MiB`.
- Current utilization: GPU `0%`, memory `0%`; 14-second samples also max/avg `0%`.
- GPU PIDs:
  - `3065498`, compute process, `120 MiB` GPU memory.
  - `3065786`, compute process, `8370 MiB` GPU memory.
- Process classification: PID `97921` is `/root/sglang-env-3060-4b/bin/python -m sglang.launch_server` serving model `Qwen3.5-4B-AWQ` with `--port 30000`, hierarchical cache and file storage options. Its related processes include `sglang::scheduler` PID `98056`, `sglang::detokenizer` PID `98057`, Torch Inductor workers, and resource tracker PID `98055`.
- Neuron status: no process containing `neuron` was present in the returned process listing. The active workload is classified as SGLang/Torch, not Neuron.
- Port 30000: `LISTEN` on `127.0.0.1:30000`, process `python` PID `97921`, file descriptor `59`; no externally bound listener was shown.
- The process listing also contained an unrelated AOT dependency-build watcher for `OPS-20260908-3060-AOT-DEPS-REMOTE-056`; it was not a GPU owner in the `nvidia-smi` process section.

## Determination and recommendation

The user-mentioned Neuron experiment is not active by process-name evidence. The GPU is nevertheless owned by an active SGLang/Torch experiment: PID `3065786` holds `8370 MiB`, PID `3065498` holds `120 MiB`, and the SGLang server is listening on port 30000. Despite zero instantaneous utilization, the allocation and live server indicate the GPU remains occupied.

Recommendation: wait/do not resume or start another GPU workload on this host until the active SGLang experiment is explicitly released by its owner. Any stop or cleanup action requires a separate authorized Task ID.

## Followups

None within this read-only task.

## Open issues

- `lsof` is unavailable on the remote host; port-state evidence is from `ss`.
- `nvidia-smi` reports GPU PIDs `3065498` and `3065786`, while the process listing exposes the SGLang parent as PID `97921`; the audit does not perform further diagnosis or process correlation beyond the requested commands.
