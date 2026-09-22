# E001 results

Status: BLOCKED before runtime launch.

## OBSERVED

- Canonical branch `3090-24g-opt`, HEAD `dde7bb697b6743c690d580d37568217b769a30e3`; worktree clean before experiment files were added.
- No SGLang service process was running; RTX 3090 was at 4 MiB used / 24121 MiB free.
- Historical C6.1 root `/data/l3/c61-qwen-20260922-220343` exists, occupies 39 GiB actual disk space, and was not modified.
- `/data` is on `/dev/sda1`, the same 484 GiB filesystem as `/`; 452 GiB used and 32 GiB available at preflight.
- Qwen model directory occupies 11 GiB.
- Canonical C6 production contract declares `SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE=50GiB`, `MAX_SIZE=100GiB`, extent size 64 MiB, file address space 64 GiB.
- Source inspection of `extent_file_backend.py` shows no minimum-free check at constructor/open. `_select_gc_victims()` and `_gc_evict()` treat `f_bavail < min_free_space` as pressure and synchronously evict LRU entries on writes until free space rises above the watermark or no victims remain.
- No new root was created, no cache writes were made, and no population occurred.

## INFERRED

- With 32 GiB available and a 50 GiB minimum-free watermark, writing into the new production root would trigger GC. Because deleting L3 entries does not reclaim the fixed-size sparse address-space allocation as free blocks, GC can evict the newly written live cache entries without satisfying the disk watermark. Therefore the required live-entry-before-shutdown precondition is not safely achievable under the current filesystem state and frozen production settings.
- Reducing the watermark, freeing/deleting existing data, or using a different storage mount would materially alter the declared production contract or operational environment; none was done.

## UNRESOLVED

- A safe, authorized way to provide at least 50 GiB free on the production storage filesystem (or a production-approved equivalent mount) while preserving C6.1 root and unrelated data.
- Once unblocked: exact runtime key/token capture method, controlled minimal L3 publication, and restart replay acceptance.

## Bounded answer

C6.4R did not launch a server and did not alter persistent cache state. It is blocked by a concrete precondition: 32 GiB filesystem free versus the frozen 50 GiB GC watermark. No acceptance criteria pass is claimed. Do not proceed by lowering the watermark, removing unrelated files, or claiming a different filesystem is production-equivalent without explicit operational authorization and contract evidence.
