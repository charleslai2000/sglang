# E001 results

Status: ACTIVE — authorized L3 runtime roots cleaned; fixture run underway.

## OBSERVED

- Canonical branch `3090-24g-opt` was at `6cdde39e1237dbd6570741ce231036fd4de49fda` after the capacity-blocker record commit.
- No SGLang service process was running; RTX 3090 was at 4 MiB used / 24121 MiB free.
- Historical C6.1 root `/data/l3/c61-qwen-20260922-220343` exists, occupies 39 GiB actual disk space, and was not modified.
- `/data` is on `/dev/sda1`, the same 484 GiB filesystem as `/`; at inspection 452 GiB was used and 32 GiB available.
- The user indicates the large-data disk should be mounted at `/mnt/data`; in this process namespace `findmnt -T /mnt/data` resolves to `/dev/sda1`, `/mnt/data` is not a mountpoint, its contents occupy 2.9 GiB, and `/etc/fstab` contains no such mount. This environment discrepancy needs reconciliation.
- Qwen model directory occupies 11 GiB.
- The frozen C6 Qwen profile sets `SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE=50GiB`, `MAX_SIZE=100GiB`, extent size 64 MiB, file address space 64 GiB.
- Source inspection shows there is no minimum-free check at backend constructor/open. `_select_gc_victims()` and `_gc_evict()` treat `f_bavail < min_free_space` as pressure and synchronously select LRU entries for eviction on the write path.
- User explicitly authorized deletion of `/data/l3` runtime HiCache data. All 37 immediate child runtime roots other than the protected C6.1 historical root were confirmed unlocked, with no running SGLang/GPU processes, and removed. No non-L3 data was touched. Available space increased from 32 GiB to 215 GiB (`/dev/sda1`, 56% used); the C6.1 root remains intact at 39 GiB.
- `/mnt/data` is not a separate mount in this environment, but the capacity requirement is satisfied on `/dev/sda1`; use a fresh root under `/data/l3` and retain all production cache settings.

## INFERRED

- `/data/l3` is dedicated runtime HiCache state as the user confirmed. The old non-C6.1 roots were unlocked/inactive runtime data; removing them made enough capacity available without changing the 50 GiB watermark or any cache semantics.

## UNRESOLVED

- Exact request/token/key capture and fixture live-entry proof.
- Cross-process restart restore acceptance.

## Bounded answer

Capacity blocker resolved: 215 GiB is available, C6.1 is preserved, and other authorized runtime L3 roots were cleared. C6.4R fixture/restart execution is now proceeding with a fresh root and unchanged production contract.
