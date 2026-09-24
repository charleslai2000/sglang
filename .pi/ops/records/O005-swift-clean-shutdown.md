# O005 — Swift clean systemd shutdown fix and R0 runtime sanity

Date: 2026-09-24

## Shutdown root cause

The installed unit had implicit `KillMode=control-group`, `KillSignal=SIGTERM`, `TimeoutStopSec=90`, and no `ExecStop`. systemd therefore sent SIGTERM to both launch-server supervisor and scheduler child. The supervisor's SIGTERM handler is designed to drain requests, stop `SubprocessWatchdog`, send `ShutdownReq`, wait for scheduler exit, then clean remaining workers. The scheduler received SIGTERM first and exited -15; `SubprocessWatchdog._check_processes` misclassified that expected child exit as a crash, sent SIGQUIT to the supervisor, and diverted it to crash cleanup / `kill_process_tree`. The prior stop timed out at 90s and systemd SIGKILLed the parent. PID/state files were not involved.

## Fix

Set explicit `KillMode=mixed` in canonical `tools/swift-service/sglang-swift.service` and install that same unit. Initial SIGTERM now goes only to MainPID, allowing supervisor-owned graceful worker shutdown; if the unchanged 90s deadline is exceeded, systemd's final kill still applies to the cgroup. No runtime/model/HiCache semantics or timeout were changed.

## R0 post-D3 smoke

Canonical repo `/home/ubuntu/workspaces/3rdparty/sglang`, branch `3090-24g-opt`, Python `/home/ubuntu/venvs/sglang-3090/bin/python`, source `PYTHONPATH=/home/ubuntu/workspaces/3rdparty/sglang/python`, CUDA 12.9 and RTX 3090 UUID `GPU-2e3ed202-3655-d919-0a64-259209bc6587`. All models ran serially, bind `127.0.0.1:30080`; L3 disabled. For each, `sglang.__file__` and `sglang.srt.rust_extensions._server.__file__` resolved under canonical source, server logged ready, health 200, one HTTP completion returned nonempty output, and no fatal import/path/CUDA error was observed.

- Swift Q3_K_M: production unit profile, model `Swift-Qwen3.8-27B-Q3_K_M.gguf`, HTTP completion text included `R0-SWIFT-OK`; pass.
- Falcon-H1 GPTQ-Int4: `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`; reconstructed one-shot launch from O004 known-safe profile, GPTQ-Marlin selected, Mamba `extra_buffer`/BF16, eager prefill, decode graph full; HTTP 200 nonempty response; pass. No persistent Falcon unit/launcher exists in canonical tools.
- Qwen3.8 IQ3_S: `/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`; O004 profile (max-total 16384, FP8 KV, FlashInfer/Triton linear attention, Mamba `extra_buffer`/float32, prefill graph disabled, decode graph full); HTTP text included `R0-IQ3S-OK`; pass.
- Logs: `/var/lib/sglang-swift/r0-falcon/server.log`, `/var/lib/sglang-swift/r0-iq3s/server.log`. Swift completion/provenance were checked directly. No performance tests or L3 use.

## Clean stop/restart validation

After R0, IQ3_S one-shot was SIGTERM-stopped; its supervisor/workers, port, and GPU context exited. Original Swift systemd unit then started once successfully. Final verification: unit active/running, `NRestarts=0`, `/health=200`, GPU compute process is Swift scheduler PID 3103972. Canonical unit and installed unit SHA256 both `7d1e07846161063bd590cd4f473a151d482d5e14e89d545abaf257f77b35f921`.

The first post-fix stop validation had already passed: unit went inactive/dead with systemd Result success / exit status 0, no SIGKILL, no remaining process/port/GPU worker. Existing Uvicorn lifespan teardown still prints `SystemExit: 0` and `CancelledError` traceback while the unit exits successfully; this is not a smoke failure and was left unchanged as unrelated runtime shutdown cleanup.

## Commit and push

- Commit `1bb05c68bc6ce0314f284f03b2bf8cc50ceb785d` includes only this record and `tools/swift-service/sglang-swift.service` (`KillMode=mixed`).
- Push attempt `git push origin 3090-24g-opt` failed with `Permission denied (publickey)`; no remote update occurred. Local branch is ahead of `origin/3090-24g-opt` by this one commit. Do not claim push PASS.
- Existing untracked E002/E003 experiment records and `tools/swift-hicache-bench.py` were not staged, committed, or modified by the R0 commit. `git diff --check` passes; all tracked changes are committed.

## Acceptance

```text
SWIFT_POST_D3=PASS
FALCON_POST_D3=PASS
IQ3S_POST_D3=PASS
RUNTIME_PROVENANCE=CANONICAL
SWIFT_SERVICE_RESTORED=YES
CANONICAL_TREE_CLEAN=YES (tracked; unrelated pre-existing untracked experiment files remain)
CANONICAL_COMMIT=1bb05c68bc6ce0314f284f03b2bf8cc50ceb785d
ORIGIN_PUSH=FAIL (SSH public key permission denied; local branch ahead by one)
```
