# OPS-20260908-3060-STORAGE-CHECKPOINT

Status: blocked
Task ID: D3060-STORAGE-CHECKPOINT-022
Orchestration epoch: 20260908-3060
Role: devops-executor
Date: 2026-09-08 (Asia/Shanghai)

## Scope and authorization

Authorized target: the user's rented RTX3060 host `root@i-1.gpushare.com:27460`,
storage `/hy-model`, and destination `/hy-model/models/Qwen3.5-4B-AWQ`.
Authorized method: inspect mount, remount `/hy-model` read-write if read-only,
then resumably download public `LostGentoo/Qwen3.5-4B-AWQ` revision `main`.
Explicit exclusions: no server, benchmark, or 3090 modification. SSH secret was
not written to this report or remote storage.

## Commands and observed output

1. Read-only inspection over SSH:

```text
HOST
I2aff9805ac001019d1
MOUNT
TARGET    SOURCE               FSTYPE OPTIONS
/hy-model /dev/nvme0n1[/model] xfs    ro,relatime,attr2,inode64,logbufs=8,logbsize=32k,prjquota
DF
Filesystem     Type  Size  Used Avail Use% Mounted on
/dev/nvme0n1   xfs   1.9T  927G  936G  50% /hy-model
LS
ls: cannot access '/hy-model/models': No such file or directory
drwxr-xr-x 2 root root 6 Apr  3  2025 /hy-model
ROTEST
touch: cannot touch '/hy-model/.codex_rw_probe_3060': Read-only file system
rc=1
```

2. Prescribed remount attempt:

```text
mount -o remount,rw /hy-model
mount: /hy-model: permission denied.
```

No destination directory was created and no transfer was started.

3. Capability and mount evidence:

```text
ID
uid=0(root) gid=0(root) groups=0(root)
CAPS
/proc/1/status:CapEff: 00000000a80425fb
/proc/self/status:CapEff: 00000000a80425fb
MOUNTINFO
1864 1791 259:0 /model /hy-model ro,relatime - xfs /dev/nvme0n1 rw,attr2,inode64,logbufs=8,logbsize=32k,prjquota
DEVICE
lsblk: /dev/nvme0n1: not a block device
```

The `/hy-model` mount is read-only in this namespace. The effective capability
set does not include `CAP_SYS_ADMIN`, which is required for the authorized
remount operation. The mountinfo line shows the XFS source superblock as `rw`
but the namespace mount as `ro`; this is evidence only, not authorization for
an alternative procedure.

## Changed resources

- None on the remote host.
- No model directory, partial file, or download artifact was created.
- This report is the only artifact written, at the exact requested local path.

## Verification evidence

- Host identity confirmed: `I2aff9805ac001019d1`.
- `/hy-model` mount and free space captured: 1.9T total, 927G used, 936G free,
  50% use.
- Write probe failed with `Read-only file system` and was removed/left no artifact.
- Remount failed with `permission denied` before any write or transfer.
- Therefore file inventory, model metadata/checksums, and post-download free-space
  verification are not applicable.

## Summary

blocked: the exact authorized remount method cannot execute because the remote
root session lacks the required mount capability. The task stopped before any
unauthorized alternative, directory creation, or network transfer.

## Followups

Provide a host/session with `CAP_SYS_ADMIN` or have the host operator remount the
existing `/model` bind view read-write, then issue a fresh Task ID for the
download and verification procedure.

## Open issues

- `/hy-model` remains read-only.
- The requested model revision `main` was not queried or downloaded.
- No weights or resumable partials exist at the requested destination.
