# OPS-20260909-RH-OFF-RESTART

ENTRY: ACCEPT

status: blocked
task_id: D3060-RH-OFF-RESTART-20260909
orchestration_epoch: 20260909-rh-ab
role: devops-executor

## Summary

The old RTX3060 service was stopped safely and the prescribed RH-OFF seeded-storage
profile was launched on the authorized host. The new process exited during startup
before binding port 30000. No product source, git state, or seeded storage files
were modified.

## Commands and evidence

Remote access used the established key:

```text
ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 -o BatchMode=yes -o StrictHostKeyChecking=no root@i-1.gpushare.com
```

Pre-restart read-only evidence at `2026-09-09T11:45:38+08:00`:

```text
PID 90793 listening on 127.0.0.1:30000
health=200
storage bytes=23051071488
storage files=550080
```

The observed command was the established Qwen3.5-4B profile, with no
`--enable-ready-horizon` or RH-specific flags.

The authorized operation sent `SIGTERM` to PID 90793, waited for exit, exported
`SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`,
and launched the same profile into:

```text
/tmp/sglang3060-rh-off-restart-20260909.log
```

Post-launch evidence at `2026-09-09T11:46:22+08:00`:

```text
new launch PID 92788
health=000 (connection refused)
storage bytes=23051071488
storage files=550080
```

The launch log records the immediate terminal failure:

```text
ImportError: [sgl_kernel] CRITICAL: Could not load any common_ops library!
GPU Info: Compute capability: 86
Expected variant: SM86
CUDA version: 12.4
ImportError: libnvrtc.so.13: cannot open shared object file: No such file or directory
```

## Changed resources

- Service process replaced: PID `90793` -> failed launch PID `92788`.
- New log created: `/tmp/sglang3060-rh-off-restart-20260909.log`.
- Seeded directory was not deleted, cleared, copied, moved, or modified by this operation.

## Verification

- Old process exited after SIGTERM.
- New process command contained the requested RH-OFF profile and port 30000.
- New process did not reach HTTP health; port 30000 was closed after failure.
- Seeded storage byte count and file count are unchanged.
- Immediate traceback/import failure is present; acceptance criterion "no immediate traceback/assert/OOM" is not met.

## Followups

Requires a fresh Task ID for diagnosis, dependency remediation, or any rollback/restart method.

## Open issues

- Service is not running because startup failed in `sgl_kernel` loading.
- No rollback method was defined in the supplied procedure; no alternative was selected.

Extra work requires a fresh Task ID.
