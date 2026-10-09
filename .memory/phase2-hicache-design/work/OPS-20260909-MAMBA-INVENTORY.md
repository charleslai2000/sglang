# OPS-20260909-MAMBA-INVENTORY

Task ID: `OPS-20260909-MAMBA-INVENTORY`  
Orchestration epoch: `20260909-P4`  
Role: `devops-executor`  
Status: done  
Execution time: 2026-09-09 06:31–06:32 +0800

## Authorization and method

Read-only SSH inventory only, using `/home/dev-codex/.ssh/sglang_3060_ed25519` to
`root@i-1.gpushare.com:27460`. Inspected only:

- `/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`
- `/tmp/sglang3060-p4-fix.log`
- `/tmp/t38c-probe.log`

No remote writes, deletes, restarts, or code/storage changes were performed. No rollback
was applicable because the procedure was read-only.

## Commands executed

1. SSH read-only metadata, counts, extension shape, requested-key basename matching, and
   selected log evidence:

```sh
ssh -o BatchMode=yes -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 \
  root@i-1.gpushare.com 'bash -s' <<'REMOTE'
BASE=/hy-tmp/hicache-qwen35-4b-p4-retry-20260909
stat -c ... "$BASE" /tmp/sglang3060-p4-fix.log /tmp/t38c-probe.log
find "$BASE" -type f | wc -l
find "$BASE" -type f -name '.mamba_*' | wc -l
find "$BASE" -type f \( -name '*.kv' -o -name '*.bin' -o -name '*.safetensors' \
  -o -name '*.cache' -o -name '*.data' -o -name '*.dat' \) | wc -l
find "$BASE" -type f -printf '%f\n' | awk '...extension counts...'
find "$BASE" -type f -iname "*${pat}*" ...
grep -c "$id" /tmp/sglang3060-p4-fix.log
grep -c "$id" /tmp/t38c-probe.log
grep -nE '...requested IDs...' "$log" | ...
REMOTE
```

2. A first full listing was also attempted with `find ... -printf '%f\t%p\t%s\t%TY...`;
   it produced the same leading counts but exceeded the local display limit because the
   directory contains 275,065 files. The bounded summary command above is the authoritative
   captured output for this report.

## Captured outputs and evidence

Remote identity and target metadata:

```text
date=2026-09-09T06:32:04+08:00
host=I2aff9805ac001019d1
base mode=drwxr-xr-x type=directory size=41717760 mtime=2026-09-09 06:06:47.696101760 +0800 inode=2489902902
/tmp/sglang3060-p4-fix.log mode=-rw-r--r-- size=53131333 mtime=2026-09-09 06:26:54.254656862 +0800 inode=3429188648
/tmp/t38c-probe.log mode=-rw-r--r-- size=140793479 mtime=2026-09-09 06:30:53.184971463 +0800 inode=3621595861
```

Counts:

```text
total_files=275065
mamba_prefix_files=0
kv_like_extension_files=275065
extension: .bin 275065
```

Requested basename matching:

```text
c08bb650 count=1
c08bb650caccbf640d5ad8060be35d124a2cd234566ead970aa81887bed4fb88_-hy-tmp-models-Qwen3.5-4B-AWQ_0_1.bin  16384  2026-09-09T06:01:27.1601278480+0800
c7c2f7ee count=1
c7c2f7ee1544c2a065addc985f87b7d48b4e0471d65c17f3e344a27b9422ccd9_-hy-tmp-models-Qwen3.5-4B-AWQ_0_1.bin  16384  2026-09-09T06:02:46.5341028460+0800
c2f53a8841a74f6aa33582234f680e64 count=0
6b84c307f139433b84922fc274692d80 count=0
306d949c79574e7fbe96156a26925bec count=0
c68cd7e4f0484aaf915443d0764eada4 count=0
80bd3e2ca21f49a989386f6f563a97a8 count=0
```

Log request-ID occurrence counts (`sglang3060-p4-fix.log`; `t38c-probe.log`):

```text
ID                                               fix.log  probe.log
c08bb650                                         1        0
c7c2f7ee                                         1        0
c2f53a8841a74f6aa33582234f680e64                 76527    61
6b84c307f139433b84922fc274692d80                 32394    61
306d949c79574e7fbe96156a26925bec                 94735    545
c68cd7e4f0484aaf915443d0764eada4                 94832    512
80bd3e2ca21f49a989386f6f563a97a8                 94570    512
```

Relevant log evidence captured:

- `sglang3060-p4-fix.log` contains the HiCache file-backend startup sequence, including
  Mamba/KV allocation and `Creating storage backend 'file' (...HiCacheFile)` at line 46.
- The same log contains request events for the supplied successful and failed/recomputed IDs;
  for example lines 393169–393180 show `restore_success` for
  `306d949c79574e7fbe96156a26925bec` and admission events for
  `80bd3e2ca21f49a989386f6f563a97a8`.
- `t38c-probe.log` contains repeated KV and sidecar probes. A captured sample at lines
  113148–113153 for `80bd3e2ca21f49a989386f6f563a97a8` shows KV hits followed by
  `sidecar=["mamba"]` with `hit_pages={"mamba": 0}`.
- `grep -ic mamba` returned 71 for `sglang3060-p4-fix.log`; the probe log contains the
  supplied request IDs and sidecar Mamba probe records.

## Changed resources

None on the remote host. Only this local report file was created.

## Verification

- SSH completed with exit status 0 for all inventory commands.
- All three authorized remote paths existed at inspection time.
- Counts, mtimes, inode metadata, basename matches, and log occurrence counts were returned
  directly by the remote shell commands above.
- No command used a mutating operation.

## Followups

None within this Task ID. Extra investigation or interpretation requires a fresh Task ID.

## Open issues

- The supplied failed Mamba keys were abbreviated (`c08bb650...mamba`, `c7c2f7ee...mamba`),
  so basename matching used the unambiguous supplied prefixes (`c08bb650`, `c7c2f7ee`).
- “KV-like” was recorded mechanically as the requested common KV/cache data extensions;
  the observed backend artifacts are all `.bin` files.
