# OPS-20260909-DEPLOY-HYBRID-GUARD

## Invocation

- Task ID: `OPS-20260909-DEPLOY-HYBRID-GUARD`
- Epoch: `20260909-P4`
- Role: `devops-executor`
- Target: `i-1.gpushare.com:27460`
- Reviewed commit: `5b61e63993b65ee1fe6380f6bfab455e40b34270`

## Result

`blocked`

The reviewed file was backed up and deployed. The existing PID `68025` was stopped and replacement PID `70561` was started with the existing launch profile. Startup then exited during the existing FlashInfer warmup because `ninja` is unavailable. No dependency installation, profile change, storage deletion, or alternate procedure was performed.

## Evidence

- Reviewed local file: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py`
- Reviewed file SHA-256: `395e55efc4d472547581d2a33d7b989933fb78990cf4a455d8daa0e02845a203`
- Remote file: `/root/miniconda3/envs/sglang-3060-4b/sglang/srt/mem_cache/unified_radix_cache.py`
- Backup: `/root/miniconda3/envs/sglang-3060-4b/sglang/srt/mem_cache/unified_radix_cache.py.backup-20260908T224845Z`
- Backup pre-deploy SHA-256: `267446324db6725b1b978b2fdc8ac19d4709f962135d551f82bd338643b461c8`
- Deployed SHA-256: `395e55efc4d472547581d2a33d7b989933fb78990cf4a455d8daa0e02845a203`
- Storage verification: `/hy-tmp/hicache-qwen35-4b-p4-retry-20260909` remains a `755` root-owned directory.
- Pre-restart readiness: `GET http://127.0.0.1:30000/health` returned HTTP `200`.
- Restart command used the requested model, `fp8_e4m3`, `0.82`, `65536`, `1`, CUDA graph settings, HiCache file backend, `wait_complete`, retry interval `1`, retry attempts `120`, restore timeout `180`, and the existing storage environment variable.
- New PID: `70561`.
- Post-restart readiness: HTTP `000`, connection refused; PID `70561` exited.
- Restart error from `/tmp/qwen35-4b-hicache-p4-20260909.log`:

  ```text
  FileNotFoundError: [Errno 2] No such file or directory: 'ninja'
  [2026-09-09 06:49:56] Received sigquit from a child process.
  [2026-09-09 06:49:56] kill_process_tree called: parent_pid=70561, include_parent=True, pid=70561
  ```

## Changed resources

- Replaced only the remote `unified_radix_cache.py` with the reviewed file.
- Created the timestamped remote backup above.
- Stopped PID `68025`; attempted replacement service as PID `70561`, which exited.
- No storage files or directories were deleted or cleared.

## Followups

- A fresh Task ID is required to resolve the missing `ninja` prerequisite or to authorize any alternate startup procedure.

## Open issues

- Service is not ready; port `30000` is not listening after failed startup.
- Existing service rollback/restart was not attempted because no rollback procedure was authorized.
