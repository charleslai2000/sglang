# OPS-20260908-3060-KERNEL-STATUS

- Task ID: `D3060-KERNEL-STATUS-011`
- Orchestration epoch: `20260908-3060`
- Role: `devops-executor`
- Result: `done`
- Scope: read-only audit of the specified remote host and paths after D3060-KERNEL-BUILD-010.
- Remote host: `root@i-1.gpushare.com:27460`
- Audit timestamp observed remotely: `2026-09-08T20:46:40+08:00`

## Commands and evidence

The audit used SSH read-only commands only: `stat`, `pip show`, `find`, `ps`, `df`, `du`, `readlink`, `ls`, and `tail`. No install, compile, download, start, stop, delete, or modification command was issued.

### Target paths

- `/root/sglang-env-3060-4b`: present, directory, mode `755`, owner `root:root`, size `74`, mtime `2026-09-08 20:38:18 +0800`.
- `/root/sglang-3060-12g-hicache/python/sglang/kernels/aot`: present, directory, mode `775`, owner `root:root`, size `4096`, mtime `2026-09-08 20:42:10 +0800`.

### Installed packages

Using `/root/sglang-env-3060-4b/bin/python -m pip show`:

- `transformers`: installed, version `5.12.1`, location `/root/sglang-env-3060-4b/lib/python3.11/site-packages`.
- `sgl-kernel`: not found.
- `sgl_kernel`: not found.
- Pip emitted: `WARNING: Ignoring invalid distribution ~etuptools (/usr/local/lib/python3.11/dist-packages)`.

The environment search found the Transformers package and executable, but no matching installed `sgl_kernel` package path.

### AOT/build/dist artifacts

- The AOT source tree is present, including `python/sgl_kernel`, C/C++/CUDA/MUSA sources, tests, `build.sh`, and `CMakeLists.txt`.
- `/root/sglang-3060-12g-hicache/build`: missing.
- `/root/sglang-3060-12g-hicache/dist`: missing.
- `/root/sglang-3060-12g-hicache/python/sglang/kernels/aot/build`: missing.
- `/root/sglang-3060-12g-hicache/python/sglang/kernels/aot/dist`: contains only `.gitignore` (1 byte; mtime `2026-09-08 20:42:10 +0800`).
- No wheel files were found under the requested repository tree.

### Processes

At the first process snapshot, a build-related command was running:

- PID `9893`, command began `bash -c set -eux; V=/root/sglang-env-3060-4b; R=/root/sglang-3060-12g-hicache; ... python -m pip install ... cmake>=3.26 ... uv build --wheel ...`.
- PID `9894`: `/root/sglang-env-3060-4b/bin/python -m pip install --disable-pip-version-check cmake>=3.26`.
- The snapshot showed PID `9893` in `Ss` state and PID `9894` in `Sl` state, both started `2026-09-08 20:42:21 +0800` and elapsed about `04:18`.

On the second read-only process-detail query, PIDs `9893` and `9894` were absent. This establishes that the observed build command exited between snapshots; no process was stopped by this audit.

Other persistent processes observed were JupyterLab, sshd, supervisord, docker-init, and tini. No SGLang server process was observed in the first snapshot.

### Disk usage

- Filesystem: `overlay`, size `30G`, used `1.2G`, available `29G`, use `4%`.
- `/root/sglang-env-3060-4b`: `212M`.
- `/root/sglang-3060-12g-hicache`: `128M`.

### Logs

No dedicated runtime/build log file was found in the searched locations. The only recent `.log` files returned were:

- `/root/.hycloud_ossutil_log/sdk.log` — empty.
- `/root/.hycloud_ossutil_log/ossutil.log` — empty.

The repository search returned source/build-named files and review documents, not an execution log. Therefore there is no available file-log tail identifying the final build exit reason.

## Changed resources

None. The audit was read-only. The requested local report file is the only artifact written.

## Verification

- Remote SSH completed successfully twice.
- Requested target paths, package state, AOT tree, build/dist/wheel state, processes, disk usage, and available logs were queried.
- Follow-up artifact query confirmed no build directory and no wheel; only `aot/dist/.gitignore` remained.
- Report path was verified to exist before writing.

## Followups

None within this Task ID. Any further diagnosis, rerun, process control, build, installation, or artifact recovery requires a new Task ID.

## Open issues

- The initial snapshot showed an active build/install command despite the audit being requested after a stopped build; it exited before the follow-up snapshot.
- No execution log was available, so the exit/failure reason cannot be established by this read-only audit.
