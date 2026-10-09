# D3060 kernel rebuild poll

- Task ID: `D3060-KERNEL-REBUILD-POLL-036`
- Orchestration epoch: `20260908-3060`
- Role: `devops-executor`
- Target operation: `D3060-KERNEL-REBUILD-034`
- Invocation status: `done`
- Scope: read-only remote poll; no processes stopped and no remote resources modified.

## Result

At `2026-09-08T22:20:50+08:00`, the rebuild was still active. The timeout wrapper had
elapsed `427` seconds, with `473` seconds remaining in its 900-second limit. The active
build chain was:

| PID | PPID | elapsed seconds | command/state |
|---:|---:|---:|---|
| 18630 | 18601 | 427 | build shell, `Ss` |
| 18631 | 18630 | 427 | `timeout 900s ... uv build`, `S` |
| 18636 | 18633 | 420 | Python scikit-build backend, `Sl` |
| 18836 | 18636 | 420 | CMake `--build build`, `S` |
| 18837 | 18836 | 420 | `ninja -j 2`, `S` |
| 18838 | 18837 | 420 | `/bin/sh ... /usr/local/cuda/bin/nvcc`, `S` |
| 18840 | 18838 | 420 | `nvcc`, `S` |
| 19042 | 18840 | 147 | `cicc`, `S` |
| 19043 | 19042 | 147 | `cicc`, `R` |
| 19106 | 18837 | 36 | second `/bin/sh ... nvcc`, `S` |
| 19107 | 19106 | 36 | second `nvcc`, `S` |

The latest build log is:
`/root/sglang-3060-12g-hicache/python/sglang/kernels/aot/OPS-20260908-3060-KERNEL-REBUILD-034.build.log`

- Size: `5380` bytes
- mtime: `2026-09-08 22:20:14.846112393 +0800`
- Tail state: CMake generation completed; Ninja started; progress at `[3/498]`.
- The tail contains CMake `nvToolsExt` deprecation warnings only; no terminal failure or
  `BUILD_RC` line was present in the captured tail.

No files were returned by the read-only query of:
`/root/sglang-3060-12g-hicache/dist` (no wheel observed).

Disk evidence:

```text
Filesystem      Size  Used Avail Use% Mounted on
overlay          30G  4.4G   26G  15% /
582M    /root/sglang-3060-12g-hicache
```

## Commands and evidence

Executed one SSH read-only command using `date`, `ps`, `stat`, `tail -n 30`, `find` under
`dist`, `df -h`, and `du -sh`. The command completed successfully in about 2 seconds;
remote exit status was zero. The password was supplied through an environment variable and
was not printed. No stop, kill, build, install, or file mutation command was executed.

## Followups

- Continue polling only under a fresh Task ID if another observation is required.

## Open issues

- Build completion and wheel creation remain pending; this poll observed an active build.
