# OPS-20260909-RH-ON-RESTART

- status: done
- task_id: `D3060-RH-ON-RESTART-20260909`
- orchestration_epoch: `20260909-rh-ab9`
- role: `devops-executor`
- target: `root@i-1.gpushare.com:27460`, RTX 3060

## Scope and authorization

Only the known SGLang listener was gracefully stopped and relaunched. No product
source/git files were modified. The protected storage directory
`/hy-tmp/hicache-qwen35-4b-p4-retry-20260909` was not cleared, deleted, or altered;
only read-only counts were taken. No unrelated process was signalled.

## Procedure and commands

SSH used the explicit key `/home/dev-codex/.ssh/sglang_3060_ed25519`, BatchMode, and
the documented target. Preflight identified PID `100040` as the sole listener on
`127.0.0.1:30000`; its command line matched the RH-OFF clean-restart profile.

Graceful stop: `kill -TERM 100040`; the process exited within the bounded poll.

The RH-ON launch used the same executable/profile and added only:

```text
--enable-ready-horizon
--ready-horizon-frontier-n 8
--hicache-prefetch-speculative-fraction 0.6
```

Launch environment and executable:

```text
PATH=/root/sglang-env-3060-4b/bin:$PATH
SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/hy-tmp/hicache-qwen35-4b-p4-retry-20260909
/root/sglang-env-3060-4b/bin/python -m sglang.launch_server
```

All RH-OFF profile settings were retained, including model/tokenizer paths,
`--max-running-requests 1`, `--hicache-storage-prefetch-policy wait_complete`,
retry settings, HiCache ratio `2.0`, FP8 KV, and CUDA graph settings.

## Evidence

- Before: listener PID `100040`; cache `du -sb` = `23051071488` bytes; regular files
  = `550080`.
- After: listener PID `102147` on `127.0.0.1:30000`; cache `du -sb` =
  `23051071488` bytes; regular files = `550080`.
- Readiness log: `/tmp/sglang3060-rh-on-restart-20260909.log`; readiness marker at
  `2026-09-09 14:38:29`.
- Health verification: `GET /health` returned HTTP `200`.
- `/proc/102147/cmdline` contains the Qwen3.5-4B AWQ model, the complete retained
  RH-OFF profile, and the three RH-ON flags.
- Parsed `server_args` from the launch log:

  ```text
  enable_ready_horizon: True
  ready_horizon_frontier_n: 8
  hicache_prefetch_speculative_fraction: 0.6
  max_running_requests: 1
  hicache_ratio: 2.0
  hicache_storage_prefetch_policy: wait_complete
  hicache_storage_backend_extra_config: {"hicache_storage_pass_prefix_keys":true}
  ```

- `/proc/102147/environ` confirms the venv-first PATH and exact seeded storage
  directory.
- GPU verification: `NVIDIA GeForce RTX 3060`, compute capability `8.6`.
- Fatal scan of `/tmp/sglang3060-rh-on-restart-20260909.log` for
  `Traceback|AssertionError|OOM|ImportError|FileNotFoundError|Killed|Segmentation fault|scheduler exception`:
  zero matches.

## Summary

RH-ON restart completed and is ready for the identical bounded five-request trace.
The service is healthy as PID `102147`, RH-ON arguments are parsed as required, the
seeded storage baseline is unchanged, and the fatal scan is clean.

## Followups

- Run the separately authorized identical bounded five-request RH-ON trace.

## Open issues

- None for this dispatch.

```text
status: done
artifacts: OPS-20260909-RH-ON-RESTART.md; /tmp/sglang3060-rh-on-restart-20260909.log
evidence: PID 102147; readiness marker; health 200; parsed RH-ON args; unchanged cache; SM86 GPU; clean fatal scan
summary: RH-ON service restarted and ready for identical bounded five-request trace
followups: bounded RH-ON trace requires its own Task ID
open_issues: none
```
