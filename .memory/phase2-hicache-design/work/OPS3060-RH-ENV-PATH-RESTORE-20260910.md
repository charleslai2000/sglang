# OPS3060-RH-ENV-PATH-RESTORE-20260910

status: done
entry: ACCEPT
task_id: O3060-RH-TELEMETRY-DEPLOY-PROBE-20260910
invocation_id: INV-20260910-OPS-ENV-PATH-RESTORE-R2
orchestration_epoch: 20260910-rh-env-path-restore
role: devops-executor
capability_level: L4
workdir: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
memory_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design
memory_inputs:
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-TELEMETRY-DEPLOY-PROBE-20260910.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-TELEMETRY-COMMIT-20260910.md
memory_report: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-ENV-PATH-RESTORE-20260910.md
parent_thread_id: 01a07bea-d668-75b2-8280-6a2cf0870c1e
observed_workspace_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt

## Summary

Restored the remote 3060 AWQ service using the exact prior RH-ON launch flags with
`PATH=/root/sglang-env-3060-4b/bin:$PATH`. No product code or scheduler file was changed,
no request was sent, and no Neuron or unrelated GPU process was touched.

## Commands and evidence

- Remote target: `root@i-1.gpushare.com:27460`; service: `127.0.0.1:30000`.
- `command -v ninja`: `/root/sglang-env-3060-4b/bin/ninja`.
- `ninja --version`: `1.13.2.git.kitware.jobserver-pipe-1`.
- Scheduler SHA256 before and after restart: `cc63e1319e7c84f525647bc20370e6f8ad84dbdcc5fa70ce531457ace3cb846`.
- Launch PID: `135729`; launch log: `/tmp/sglang3060-rh-env-path-restore-20260910.log`.
- Process command verified the exact Qwen3.5-4B-AWQ, FP8 KV, HiCache file, wait_complete,
  ratio 2.0, max-running 1, CUDA graph, RH frontier 8, speculative fraction 0.6 profile.
- `server_args` verified `enable_ready_horizon=True`, `ready_horizon_frontier_n=8`,
  `hicache_prefetch_speculative_fraction=0.6`, and `hicache_restore_wait_timeout_s=180.0`.
- Health reached HTTP 200; final log contains `Uvicorn running on http://127.0.0.1:30000` and
  repeated `GET /health HTTP/1.1 200 OK`.
- CUDA graph startup passed:
  `Capture target prefill CUDA graph end. elapsed=5.65 s` and
  `Capture target decode CUDA graph end. elapsed=1.36 s`.
- No `ninja` failure, traceback, RuntimeError, OOM, or fatal startup marker was observed.

## Exact log tail

```text
[2026-09-10 01:53:08] The server is fired up and ready to roll!
[2026-09-10 01:53:09] INFO:     127.0.0.1:37016 - "GET /health HTTP/1.1" 200 OK
[2026-09-10 01:53:10] INFO:     127.0.0.1:37032 - "GET /health HTTP/1.1" 200 OK
```

## Followups

None within this invocation. The service is left running.

## Open issues

- Native `mcp__codex_tui__send_message_to_thread` was unavailable/not callable; lifecycle
  communication is degraded. Evidence is recorded in this report.
