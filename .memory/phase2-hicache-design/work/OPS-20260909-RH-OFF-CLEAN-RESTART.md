# OPS-20260909-RH-OFF-CLEAN-RESTART

- status: done
- task_id: `D3060-RH-OFF-CLEAN-RESTART-20260909`
- orchestration_epoch: `20260909-rh-ab6`
- role: `devops-executor`
- target: `root@i-1.gpushare.com:27460`, RTX 3060

## Scope and authorization

Only the listener on `127.0.0.1:30000` was stopped. No product source/git files were
modified. The cache directory `/hy-tmp/hicache-qwen35-4b-p4-retry-20260909` was not
cleared, deleted, or altered by command; only read-only counts were taken.

## Procedure and commands

SSH used the explicit key `/home/dev-codex/.ssh/sglang_3060_ed25519`, BatchMode, and
the documented target. Initial inspection identified PID `97921` as the sole listener
and as `/root/sglang-env-3060-4b/bin/python -m sglang.launch_server`.

Graceful stop: `kill -TERM 97921`; the process exited within the bounded poll and no
other process was signalled.

The final relaunch used the same executable/profile:

```text
PATH=/root/sglang-env-3060-4b/bin:$PATH
SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/hy-tmp/hicache-qwen35-4b-p4-retry-20260909
/root/sglang-env-3060-4b/bin/python -m sglang.launch_server
--model-path /hy-tmp/models/Qwen3.5-4B-AWQ
--tokenizer-path /hy-tmp/models/Qwen3.5-4B-AWQ
--host 127.0.0.1 --port 30000 --tp-size 1 --mem-fraction-static 0.82
--max-running-requests 1 --max-total-tokens 65536 --chunked-prefill-size 2048
--max-prefill-tokens 16384 --kv-cache-dtype fp8_e4m3
--enable-hierarchical-cache --hicache-host-memory-mode cache --hicache-ratio 2.0
--hicache-write-policy write_through --hicache-io-backend kernel
--hicache-mem-layout page_first --hicache-storage-backend file
--hicache-storage-prefetch-policy wait_complete
--hicache-storage-backend-extra-config {"hicache_storage_pass_prefix_keys":true}
--hicache-storage-prefetch-retry-poll-interval 1
--hicache-storage-prefetch-retry-max-attempts 120
--hicache-restore-wait-timeout-s 180
--cuda-graph-backend-decode full --cuda-graph-backend-prefill breakable
--cuda-graph-bs-decode 1 --cuda-graph-bs-prefill 4 8 16 32
```

RH-OFF verification: command line and parsed `server_args` both show
`enable_ready_horizon: False`; no `--enable-ready-horizon` or RH-specific flags were
passed.

## Evidence

- Before: listener PID `97921`; cache files `550080`; cache bytes `23051071488`.
- After: listener PID `100040` on `127.0.0.1:30000`; cache files `550080`; cache bytes
  `23051071488`.
- Readiness log: `/tmp/sglang3060-rh-off-clean-restart-20260909.log`, including
  `The server is fired up and ready to roll!` at `14:17:23`.
- Health verification: `GET /health` HTTP `200` at `14:17:25` and subsequent checks.
- Environment verification from `/proc/100040/environ`: required PATH prefix and exact
  storage directory are present.
- GPU verification: `NVIDIA GeForce RTX 3060`, compute capability `8.6` (SM86).
- Fatal scan of the final log for fatal/traceback/OOM/scheduler exception/
  FileNotFoundError/segmentation fault: zero matches.

## Incident during execution

The first relaunch shell attempt exited before readiness because its remote quoting
reduced the JSON extra-config value to `{hicache_storage_pass_prefix_keys:true}`.
It was not left running. The corrected relaunch above preserved the exact JSON and
completed successfully. This did not modify the protected cache.

## Summary

Clean RH-OFF restart completed and verified. The service is healthy as PID `100040`,
the protected cache byte/file counts are unchanged, and the GPU/kernel target is
verified as RTX 3060 SM86/CUDA-12 runtime.

## Followups

- Proceed with the separately authorized bounded OFF trace replay.

## Open issues

- None for this task.
