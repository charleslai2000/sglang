# OPS-20260909-RESTART-NINJA

Status: blocked
Task ID: OPS-20260909-RESTART-NINJA
Epoch: 20260909-P4
Target: root@i-1.gpushare.com:27460

## Scope and baseline

- SSH key: `/home/dev-codex/.ssh/sglang_3060_ed25519`
- Reviewed deployed file checksum observed:
  `395e55efc4d472547581d2a33d7b989933fb78990cf4a455d8daa0e02845a203`
  at `/root/miniconda3/envs/sglang-3060-4b/sglang/srt/mem_cache/unified_radix_cache.py`.
- Existing backup was not modified.
- Existing storage directory observed and not deleted:
  `/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`.

## Commands and evidence

1. Inspected remote host, PATH, processes, and port 30000. Remote login PATH did not include either SGLang environment. No active 3060 service or listener was present.
2. Inspected environments:
   - `/root/miniconda3/envs/sglang-3060-4b` has no `bin/python`.
   - `/root/sglang-env-3060-4b` has Python 3.11.11 and `ninja` 1.13.2 at `/root/sglang-env-3060-4b/bin/ninja`.
3. Read `/tmp/qwen35-4b-hicache-p4-20260909.log`; failed PID 70561 showed FlashInfer `FileNotFoundError: ... 'ninja'` and stack paths under `/root/sglang-env-3060-4b`.
4. Started one non-destructive restart attempt with PATH prefixed by `/root/sglang-env-3060-4b/bin`, source tree `/root/sglang-3060-12g-hicache`, existing model/profile values, port 30000, and working directory `/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`. PID recorded: 73609. Log: `/tmp/qwen35-4b-hicache-p4-retry-20260909-ninja.log`.
5. Restart attempt exited before binding port 30000. Log evidence:
   `ImportError: [sgl_kernel] CRITICAL: Could not load any common_ops library!`
   It found an `sm100/common_ops.abi3.so`, while GPU capability is SM86; the binary also requires `libnvrtc.so.13`, unavailable on the host (CUDA 12.4 libraries are present).
6. Verification after attempt: `curl http://127.0.0.1:30000/health` returned HTTP 000 / connection refused; no `launch_server.py.*30000` process; PID 73609 absent.

## Changed resources

- No product files changed.
- No storage files deleted or cleared.
- No 3090 resources touched.
- The failed restart created only `/tmp/qwen35-4b-hicache-p4-retry-20260909-ninja.log` and its PID marker; the process is no longer running.

## Blocker and follow-up

Blocked: the authorized ninja/PATH remediation is evidenced, but the exact reviewed launch procedure cannot be recovered from an active process or launch script, and the attempted reconstruction exposes a pre-existing incompatible `sgl_kernel` runtime. Fixing that requires a fresh Task ID and explicit reroute/authorization for runtime-package or launch-procedure work. Do not delete storage or alter 3090 state.
