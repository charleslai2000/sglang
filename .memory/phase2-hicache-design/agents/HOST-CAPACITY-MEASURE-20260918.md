# HOST-CAPACITY-MEASURE-20260918

## Task
Read-only capacity measurement of the host to support the phase2-hicache-design decision
for SGLang `--hicache-size <N>` (SI GB of HOST memory for the HiCache host tier), plus
L3/storage context. Report raw numbers; no changes.

## Scope
READ-ONLY measurement. No writes except this artifact. No process signalling, no GPU access,
no port binding, no inference requests, no mkdir/touch/rm. All commands were inspection-only.

Environment: working dir `/home/ubuntu/workspaces/3rdparty`; host Linux, 32 logical CPUs,
up 2 days 20:38 at measurement time (2026-09-18 ~19:02 UTC).

## Result

### Key numbers
| Fact | Value |
|---|---|
| MemTotal | 131,996,980 kB = 135,164,907,520 B = **125.9 GiB** (`free -b` total 135,164,907,520) |
| MemAvailable | 126,940,880 kB = 130,011,461,120 B = **121.1 GiB** |
| Mem used | 5,177,446,400 B = **4.8 GiB** |
| Mem free (unused) | 19,181,735,936 B = **17.9 GiB** |
| buff/cache | 112,034,562,048 B = **104.3 GiB** |
| Swap total / used | **0 / 0** (no swap configured) |
| /data free (avail) | **18.85 GiB** avail (20,243,668,992 B); total fs 484G, 97% used |
| /tmp free (avail) | same single filesystem as /data → **18.85 GiB** avail |
| /opt free (avail) | same single filesystem → **18.85 GiB** avail |
| /mnt/data | exists, same single filesystem → **18.85 GiB** avail |
| /data/l3 total size | **183G** (`du -sh`) |
| /data/l3/local-prod-v1.1 | exists, **53G** (`du -sh`; contains sparse `hicache.data` file of 68,719,476,736 B logical) |
| /dev/shm usage | **1.5M** used of 63G tmpfs; only small 16 KB `sglang_loads_*.shm` + semaphores, no multi-GB host-tier files |
| CPU count | 32 (`nproc`) |
| Load average | 3.32 / 3.15 / 2.75 (1/5/15 min); runnable 4/514 |

### Arithmetic verdict for HiCache host tiers (host RAM)
MemAvailable = 130,011,461,120 B ≈ 130.0 GB (SI).

- **16 GB host tier** (`--hicache-size 16` = 16,000,000,000 B):
  16,000,000,000 / 130,011,461,120 = **12.3% of MemAvailable**. Fits with ~114 GB to spare. **OK**
- **32 GB host tier** (`--hicache-size 32` = 32,000,000,000 B):
  32,000,000,000 / 130,011,461,120 = **24.6% of MemAvailable**. Fits with ~98 GB to spare. **OK**
- Additional sanity: 32 GB is 32/135.16 ≈ 23.7% of total physical RAM. With no swap and no
  serving process currently resident, both tiers are comfortably within headroom. No swap means
  overcommit must be avoided, but neither tier approaches MemTotal.

### Disk verdict (for L3/storage, NOT host RAM)
Single root filesystem `/dev/sda1` (ext4) backs `/`, `/data`, `/tmp`, `/opt`, `/mnt/data`, with
only **18.85 GiB available / 97% used**. If the decision also requires materializing an additional
on-disk L3 tier of 16 GB or 32 GB:
- 16 GB L3: 16,000,000,000 / 20,243,668,992 ≈ **79% of remaining disk** → **MARGINAL**
- 32 GB L3: 32,000,000,000 / 20,243,668,992 ≈ **158% of remaining disk** → **NOT OK** (would not fit)
- **16 GB / 32 GB host-tier RAM: OK / OK**. **16 GB / 32 GB extra L3 on disk: MARGINAL / NOT OK.**

Note the existing `/data/l3/local-prod-v1.1/hicache.data_...` is a sparse file with 68.7 GB logical
size occupying 53G on disk, so already-allocated L3 is significant and reclaimed space would be
needed before adding a new large on-disk tier.

## Evidence

### 1. Host RAM
```
$ free -b
               total        used        free      shared  buff/cache   available
Mem:     135164907520  5177446400 19181735936     2793472 112034562048 129987461120
Swap:              0           0           0

$ free -h
               total        used        free      shared  buff/cache   available
Mem:           125Gi       4.8Gi        17Gi       2.7Mi       104Gi       121Gi
Swap:             0B          0B          0B

$ grep -E 'MemTotal|MemAvailable' /proc/meminfo
MemTotal:       131996980 kB
MemAvailable:   126940880 kB
```
(Note: `free -b` "total" 135,164,907,520 B == `MemTotal` 131,996,980 kB; consistent.)

### 2. CPU count and load
```
$ nproc
32

$ uptime
 19:02:07 up 2 days, 20:38,  1 user,  load average: 3.32, 3.15, 2.75

$ cat /proc/loadavg
3.32 3.15 2.75 4/514 1850341
```

### 3. Disk for candidate HiCache/L3 locations
```
$ df -h /data
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       484G  465G   19G  97% /

$ df -h /tmp
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       484G  465G   19G  97% /

$ df -h /opt
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       484G  465G   19G  97% /

$ df -h /mnt/data
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       484G  465G   19G  97% /
```
Path existence check (distinguishing absent from not-found):
```
$ for p in /data /tmp /opt /mnt /mnt/data; do if [ -e "$p" ]; then echo "EXISTS: $p"; else echo "ABSENT: $p"; fi; done
EXISTS: /data
EXISTS: /tmp
EXISTS: /opt
EXISTS: /mnt
EXISTS: /mnt/data

$ ls -ld /mnt /mnt/data
drwxr-xr-x 3 root   root   4096 Sep 16 20:18 /mnt
drwxr-xr-x 4 ubuntu ubuntu 4096 Sep 17 17:49 /mnt/data
```
All four candidate paths exist and all resolve to the same root filesystem. Detailed free space
(1K blocks / ext4 block counts):
```
$ df --output=source,size,avail /data
Filesystem     1K-blocks    Avail
/dev/sda1      506771172 19769208

$ stat -f -c 'total_blocks=%b free_blocks=%f avail_blocks=%a block_size=%S' /data
total_blocks=126692793 free_blocks=4946314 avail_blocks=4942218 block_size=4096
free  = 4,946,314 * 4096 = 20,260,446,208 B (~18.87 GiB)
avail = 4,942,218 * 4096 = 20,243,668,992 B (~18.85 GiB)
```

### 4. Existing L3 usage
```
$ du -sh /data/l3
183G	/data/l3

$ ls -la /data/l3            # top level only
total 148
drwxr-xr-x 37 ubuntu ubuntu 4096 Sep 18 17:54 .
drwxr-xr-x  4 root   root   4096 Sep 15 21:59 ..
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 18 12:23 f12-frozen-20260918T120901Z-1802823
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 18 12:13 f12-repaired-20260918T120901Z-1802823
drwxrwxr-x  2 ubuntu ubuntu 4096 Sep 16 14:20 fleet-forensics-v2-20260916
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 16 14:20 local-prod-v1
drwxrwxr-x  2 ubuntu ubuntu 4096 Sep 16 23:46 local-prod-v1.1
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 18 00:12 p6-mamba48-20260918T000647Z-1746326
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 18 00:06 p6-mamba56-20260918T000647Z-1746326
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 18 00:06 p6-mamba64-20260918T000647Z-1746326
drwxrwxr-x  8 ubuntu ubuntu 4096 Sep 17 16:52 phase9-gates-final-20260916
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 16:22 prod-20260917T162230Z-1480769
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 18:39 prod-20260917T182323Z-1596154
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 21:17 prod-20260917T190831Z-1602589
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 23:06 prod-20260917T211800Z-1653969
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 23:50 prod-20260917T234749Z-1733936
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 23:56 prod-20260917T235414Z-1738571
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 18 00:10 prod-20260918T000656Z-1746209
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 18 08:34 prod-20260918T002151Z-1750622
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 18 10:08 prod-20260918T084226Z-1761580
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 18 16:46 prod-20260918T164313Z-1823230
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 18 17:19 prod-20260918T171238Z-1827484
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 18 18:00 prod-20260918T175403Z-1833126
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 23:16 sweep-mamba48-20260917T231327Z-1726566
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 23:13 sweep-mamba56-20260917T231327Z-1726566
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 23:13 sweep-mamba64-20260917T231327Z-1726566
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 23:29 sweep2-mamba48-20260917T231910Z-1727975
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 23:40 sweep2-mamba56-20260917T231910Z-1727975
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 23:47 sweep2-mamba64-20260917T231910Z-1727975
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 23:49 sweep2-mamba64b-20260917T234929Z-1736234
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 23:53 sweep3-mamba64-20260917T235029Z-1737059
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 23:58 sweep4-mamba48-20260917T235645Z-1740204
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 23:56 sweep4-mamba56-20260917T235645Z-1740204
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 17 23:56 sweep4-mamba64-20260917T235645Z-1740204
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 18 00:06 sweep5-mamba48-20260918T000006Z-1743252
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 18 00:00 sweep5-mamba56-20260918T000006Z-1743252
drwxr-xr-x  2 ubuntu ubuntu 4096 Sep 18 00:00 sweep5-mamba64-20260918T000006Z-1743252
```
Top-level size breakdown (largest last):
```
$ du -sh /data/l3/* | sort -h | tail -15
184M	/data/l3/prod-20260918T164313Z-1823230
232M	/data/l3/p6-mamba48-20260918T000647Z-1746326
702M	/data/l3/prod-20260918T171238Z-1827484
917M	/data/l3/sweep4-mamba48-20260917T235645Z-1740204
1.6G	/data/l3/local-prod-v1
2.2G	/data/l3/prod-20260918T002151Z-1750622
2.4G	/data/l3/sweep3-mamba64-20260917T235029Z-1737059
4.9G	/data/l3/sweep-mamba48-20260917T231327Z-1726566
7.7G	/data/l3/prod-20260917T190831Z-1602589
8.0G	/data/l3/sweep2-mamba64-20260917T231910Z-1727975
13G	/data/l3/sweep5-mamba48-20260918T000006Z-1743252
17G	/data/l3/sweep2-mamba56-20260917T231910Z-1727975
30G	/data/l3/sweep2-mamba48-20260917T231910Z-1727975
43G	/data/l3/phase9-gates-final-20260916
53G	/data/l3/local-prod-v1.1
```
`/data/l3/local-prod-v1.1` existence and size:
```
$ ls -ld /data/l3/local-prod-v1.1
drwxrwxr-x 2 ubuntu ubuntu 4096 Sep 16 23:46 /data/l3/local-prod-v1.1

$ du -sh /data/l3/local-prod-v1.1
53G	/data/l3/local-prod-v1.1

$ ls -la /data/l3/local-prod-v1.1
total 55179780
drwxrwxr-x  2 ubuntu ubuntu        4096 Sep 16 23:46 .
drwxr-xr-x 37 ubuntu ubuntu        4096 Sep 18 17:54 ..
-rw-r--r--  1 ubuntu ubuntu 68719476736 Sep 16 23:47 hicache.data_-data-models-qwen35-9b-w4a16_0_1
-rw-r--r--  1 ubuntu ubuntu           0 Sep 16 21:18 hicache.meta_-data-models-qwen35-9b-w4a16_0_1.lock
-rw-------  1 ubuntu ubuntu       20604 Sep 16 23:46 hicache.meta_-data-models-qwen35-9b-w4a16_0_1.manifest
-rw-------  1 ubuntu ubuntu           0 Sep 16 23:42 hicache.meta_-data-models-qwen35-9b-w4a16_0_1.manifest.tmp.5oklmxpr
-rw-------  1 ubuntu ubuntu           0 Sep 16 21:40 hicache.meta_-data-models-qwen35-9b-w4a16_0_1.manifest.tmp.qix1u38t
-rw-------  1 ubuntu ubuntu           0 Sep 16 22:30 hicache.meta_-data-models-qwen35-9b-w4a16_0_1.manifest.tmp.tor6mwlz
-rw-------  1 ubuntu ubuntu           0 Sep 16 21:57 hicache.meta_-data-models-qwen35-9b-w4a16_0_1.manifest.tmp.zt1yic06
-rw-r--r--  1 ubuntu ubuntu     7824746 Sep 16 23:47 hicache.meta_-data-models-qwen35-9b-w4a16_0_1.wal.7
-rw-------  1 ubuntu ubuntu           2 Sep 16 23:46 hicache.meta_-data-models-qwen35-9b-w4a16_0_1.wal.current
```
Note the 68,719,476,736-byte `hicache.data_...` file is sparse (du reports 53G); it is not a
64 GiB physical allocation.

### 5. Current serving-stack memory pressure
No `sglang::scheduler` or `sglang.launch_server` process exists. Explicitly: **none found.**
```
$ ps aux | grep -E 'sglang|launch_server|scheduler' | grep -v grep
(no output; exit=1)

$ ps -eo pid,ppid,comm,args | grep -iE 'sglang|scheduler' | grep -v grep
(no output; grep_exit=1)

$ pgrep -c -x python3 ; pgrep -c -x python
0
0
```
Robust per-PID `/proc` cmdline scan (avoids pgrep matching the scanning shell's own command line):
```
for pid in $(ls /proc | grep -E '^[0-9]+$'); do cl=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null); case "$cl" in *sglang*|*launch_server*) echo "PID $pid: $cl";; esac; done
# -> only match was the scanning shell itself (PID 1850402), no server process.
```
Consequently no `ps -o pid,rss,vsz,cmd -p <pid>` server RSS is available/relevant; there is no
resident serving stack consuming host RAM at measurement time.

### 6. Pre-existing HiCache host-tier footprint
```
$ ls -la /dev/shm          # top level
total 1528
drwxrwxrwt  2 root   root    2000 Sep 18 19:00 .
drwxr-xr-x 21 root   root    4220 Sep 15 22:24 ..
-rw-------  1 ubuntu ubuntu    32 Sep 17 13:54 sem.mp-024qivrh
... (26 sem.mp-* 32-byte semaphores) ...
-rw-------  1 ubuntu ubuntu 16396 Sep 18 18:57 sglang_loads_0675479f4be1_c46910d4.shm
... (~90 sglang_loads_*.shm files, each 16,396 B) ...

$ du -sh /dev/shm
1.5M	/dev/shm

$ df -h /dev/shm
Filesystem      Size  Used Avail Use% Mounted on
tmpfs            63G  1.5M   63G   1% /dev/shm
```
Only small (16 KB) sglang shared-memory bookkeeping files plus 32-byte semaphores are present —
1.5 MB total. **No multi-GB HiCache host-tier file/data was left behind**; no pre-existing host-tier
occupancy of significance. `/dev/shm` is a 63G tmpfs with 63G free.

### 7. Largest single free block (/data and /tmp)
`/data` and `/tmp` are on the **same** filesystem `/dev/sda1` (ext4); the other candidate paths
(`/opt`, `/mnt/data`) are also on it. At df granularity only aggregate free space is reportable:
```
free blocks = 4,946,314 * 4096 = 20,260,446,208 B (~18.87 GiB)
available   = 4,942,218 * 4096 = 20,243,668,992 B (~18.85 GiB)
```
The largest *contiguous* (single) free block is **not determinable from df output** (df reports no
free-extent information, and `dumpe2fs -h /dev/sda1` returned exit=1 — not permitted without root).
The aggregate free/available above is the upper bound; actual largest contiguous run may be smaller.
No filesystem allocation tooling that would modify state was used.

## Defects or blockers
None blocking. Notes:
- `dumpe2fs -h /dev/sda1` exited 1 (permission — block device not readable without root), so
  largest-contiguous-extent could not be determined; aggregate free space from `df`/`stat -f` is
  reported instead.
- The naive `pgrep -f 'sglang.launch_server'` returned exit 0 with its own scanner PID (a known
  false positive: pgrep matches its invoking shell). Cross-checked with per-PID `/proc` scan and
  `ps`/`pgrep -x`; no actual serving process exists.
- Disk headroom is the real constraint: 18.85 GiB free on the single root filesystem. Host RAM is
  not a constraint for either 16 GB or 32 GB host tiers.

## Remaining claims or exclusions
- This is a point-in-time snapshot (2026-09-18 ~19:02 UTC) with no serving stack resident.
  RAM pressure while a full SGLang instance (model weights on host, scheduler, tokenizer, CUDA
  pinned buffers) is live would be higher; this measurement does **not** include a running server's
  footprint. It measures only the idle host baseline.
- `--hicache-size` semantics were assumed to be SI GB of host RAM as stated in the task; no SGLang
  source/config was inspected to re-derive that unit (out of scope).
- No L3 format/retention policy was evaluated; only raw sizes.
- GPU was not touched or queried (as required).
- No process was started/stopped/signalled; no port was bound; no inference was run.

## Terminal state: DONE
