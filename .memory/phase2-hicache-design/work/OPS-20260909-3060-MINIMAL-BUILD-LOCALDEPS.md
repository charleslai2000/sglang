# OPS-20260909-3060-MINIMAL-BUILD-LOCALDEPS

Status: blocked
Task: D3060-OPS-073
Epoch: 2026-09-09

## Scope and authorization

Remote target was limited to `root@i-1.gpushare.com:27460`, with source
`/root/sglang-3060-12g-hicache`, `/hy-tmp` build/dependency data, and venv
`/root/sglang-env-3060-4b`. No local product files or 3090 branches were
modified. The only local artifact written is this report.

## Entry and procedure

`ENTRY: ACCEPT` was issued. The prescribed procedure required configuring the
exact source path, then compiling with the specified CUDA/SM86/minimal settings
and all seven local FetchContent overrides. Execution stopped at read-only
preflight because the source path is not a runnable CMake/Git source tree.

## Commands and evidence

SSH command used:

```text
ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 -o BatchMode=yes root@i-1.gpushare.com ...
```

Observed output:

```text
HOST
I2aff9805ac001019d1
SOURCE
fatal: not a git repository (or any of the parent directories): .git
```

The subsequent read-only inspection showed:

```text
REVIEWED=a76cce39723654cb93ee186b9c3fb570961d7794
CMAKE_FILES
(none)
BRANCH_LAYOUT
(none)
CMAKE_MISSING
GITDIR_MISSING
```

The directory listing contained repository-like files and a
`.reviewed-source-commit` marker, but no root `CMakeLists.txt`; a search to
depth four found no `CMakeLists.txt` anywhere under the authorized source
directory. Therefore the exact configure command cannot be formed or run
without selecting an unapproved path or restoring/changing source state.

## Changed resources

Remote: none. No build directory, cache, configure, compile, dependency, or
source mutation was performed. Local: this report only.

## Verification

SSH BatchMode authentication succeeded and the host identity was recorded.
The reviewed marker was read and matched the requested commit. Configure,
CMakeCache override verification, no-download-subbuild verification, build,
artifact hashing, and venv import/loadability were not reached.

## Summary

blocked — the authorized source path lacks both Git metadata and any
`CMakeLists.txt`, so the prescribed exact procedure cannot proceed.

## Followups

Fresh Task ID required to restore or select a valid source tree, then rerun the
full prescribed configure/build procedure.

## Open issues

- The remote path does not contain the expected reviewed CMake source tree.
- No authorized instruction identifies a permitted source subdirectory or
  permits source restoration.
