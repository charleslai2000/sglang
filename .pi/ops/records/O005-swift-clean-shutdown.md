# O005 — Swift clean shutdown fix, R0 sanity, and R0.1 push recovery

Date: 2026-09-24

## Shutdown root cause

The installed unit had implicit `KillMode=control-group`, `KillSignal=SIGTERM`, `TimeoutStopSec=90`, and no `ExecStop`. systemd therefore sent SIGTERM to both launch-server supervisor and scheduler child. The supervisor's SIGTERM handler is designed to drain requests, stop `SubprocessWatchdog`, send `ShutdownReq`, wait for scheduler exit, then clean remaining workers. The scheduler received SIGTERM first and exited -15; `SubprocessWatchdog._check_processes` misclassified that expected child exit as a crash, sent SIGQUIT to the supervisor, and diverted it to crash cleanup / `kill_process_tree`. The prior stop timed out at 90s and systemd SIGKILLed the parent. PID/state files were not involved.

## Fix

Set explicit `KillMode=mixed` in canonical `tools/swift-service/sglang-swift.service` and install that same unit. Initial SIGTERM now goes only to MainPID, allowing supervisor-owned graceful worker shutdown; if the unchanged 90s deadline is exceeded, systemd's final kill still applies to the cgroup. No runtime/model/HiCache semantics or timeout were changed.

## R0 post-D3 smoke

Canonical repo `/home/ubuntu/workspaces/3rdparty/sglang`, branch `3090-24g-opt`, Python `/home/ubuntu/venvs/sglang-3090/bin/python`, source `PYTHONPATH=/home/ubuntu/workspaces/3rdparty/sglang/python`, CUDA 12.9 and RTX 3090 UUID `GPU-2e3ed202-3655-d919-0a64-259209bc6587`. All models ran serially, bind `127.0.0.1:30080`; L3 disabled. For each, `sglang.__file__` and `sglang.srt.rust_extensions._server.__file__` resolved under canonical source, server logged ready, health 200, one HTTP completion returned nonempty output, and no fatal import/path/CUDA error was observed.

- Swift Q3_K_M: production unit profile; HTTP completion text included `R0-SWIFT-OK`; pass.
- Falcon-H1 GPTQ-Int4: `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`; reconstructed one-shot launch from O004 known-safe profile, GPTQ-Marlin selected, Mamba `extra_buffer`/BF16, eager prefill, decode graph full; HTTP 200 nonempty response; pass. No persistent Falcon unit/launcher exists in canonical tools.
- Qwen3.8 IQ3_S: `/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`; O004 profile (max-total 16384, FP8 KV, FlashInfer/Triton linear attention, Mamba `extra_buffer`/float32, prefill graph disabled, decode graph full); HTTP text included `R0-IQ3S-OK`; pass.
- Logs: `/var/lib/sglang-swift/r0-falcon/server.log`, `/var/lib/sglang-swift/r0-iq3s/server.log`. Swift completion/provenance were checked directly. No performance tests or L3 use.

## Clean stop/restart validation

After R0, IQ3_S one-shot was SIGTERM-stopped; its supervisor/workers, port, and GPU context exited. Original Swift systemd unit then started once successfully. Final verification: unit active/running, `NRestarts=0`, `/health=200`, GPU compute process is Swift scheduler PID 3103972. Canonical unit and installed unit SHA256 both `7d1e07846161063bd590cd4f473a151d482d5e14e89d545abaf257f77b35f921`.

The first post-fix stop validation had already passed: unit went inactive/dead with systemd Result success / exit status 0, no SIGKILL, no remaining process/port/GPU worker. Existing Uvicorn lifespan teardown still prints `SystemExit: 0` and `CancelledError` traceback while the unit exits successfully; this was left unchanged as unrelated runtime shutdown cleanup.

## R0.1 SSH push recovery

- `origin` is `git@github.com:charleslai2000/sglang.git`, the intended existing fork; branch remains `3090-24g-opt`.
- Cause: no `SSH_AUTH_SOCK`/agent, no Git `core.sshCommand`, and no GitHub-specific `~/.ssh/config` host entry. OpenSSH's default identity selection did not authenticate. The existing `~/.ssh/id_github` private key (existing file; not printed or changed) successfully authenticated to GitHub as `charleslai2000`; the other extant candidate `id_charles_sglang` was rejected. Thus this was identity selection/key-loading, not remote ownership/URL or missing credentials.
- Per-command `GIT_SSH_COMMAND='ssh -i ~/.ssh/id_github -o IdentitiesOnly=yes -o BatchMode=yes' git push origin 3090-24g-opt` succeeded; no ssh config, agent, global Git setting, remote URL, or ownership change.
- Subsequent unqualified fetch failed again due default identity selection; fetch repeated with the same per-command `GIT_SSH_COMMAND` passed and confirmed both `HEAD` and `origin/3090-24g-opt` equal `57a42710a7681ab41b1dd7666cc4c29920912867`.
- Existing untracked E002/E003 experiment files and `tools/swift-hicache-bench.py` were neither staged nor committed. `git diff --check` passed; branch tracks origin at the same SHA with these pre-existing untracked files preserved.

## Commit and acceptance

- Base commit `57a42710a7681ab41b1dd7666cc4c29920912867` contains the unit fix and O005/R0 results; this R0.1 authentication diagnosis is an additional operational-record-only follow-up commit.
- Stop validation: PASS (inactive/dead, Result success, exit 0, no SIGKILL, no workers).
- Restart validation: PASS (active/running, `/health=200`, `NRestarts=0`).

```text
SSH_PUSH_ROOT_CAUSE=no ssh-agent; existing GitHub fork key ~/.ssh/id_github not selected by default OpenSSH identity order; this existing key authenticates as charleslai2000
ORIGIN_PUSH=PASS
LOCAL_HEAD=57a42710a7681ab41b1dd7666cc4c29920912867
ORIGIN_HEAD=57a42710a7681ab41b1dd7666cc4c29920912867
```