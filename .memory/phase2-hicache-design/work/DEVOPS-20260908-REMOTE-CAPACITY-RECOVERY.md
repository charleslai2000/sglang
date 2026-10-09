ENTRY: ACCEPT

# DEVOPS-20260908-REMOTE-CAPACITY-RECOVERY

- Task ID: `DEVOPS-20260908-REMOTE-CAPACITY-RECOVERY`
- Orchestration epoch: `2026-09-08-P0`
- Role: `devops`
- Host: `root@175.155.64.171:24052` (`pytorch-4402`)
- Invocation status: **blocked**
- Report artifact: `/data/sglang-hicache-archive/2026-09-08/MIGRATION-MANIFEST-DEVOPS-20260908-REMOTE-CAPACITY-RECOVERY.txt`

## Summary

The six authorized old 120,000,000,000-byte HiCache storage files were safely
archived from root-backed evidence storage to `/data`, preserving the original
run directories and all non-storage evidence. The files were sparse: only four
had one allocated extent each and two had zero allocated extents. The operation
therefore released only `206,028,800` root bytes (about `196.5 MiB`), not the
requested 130G or a usable root-backed 120G allocation. Root remains 100% full
with 0 bytes available, so the frozen S=25 run cannot be safely re-enabled by
this authorized storage-only action.

No engine, launcher, vehicle, product checkout, launch contract, or evidence
raw/log/report content was modified. No prior evidence was deleted; storage was
copied to the authorized archive and only the verified original storage files
were unlinked.

## Observed environment facts

- Root filesystem before: `overlay`, size `104,828,547,072`, used
  `100,366,422,016`, available `0`, `100%`.
- Root filesystem after: `overlay`, size `104,828,547,072`, used
  `100,160,393,216`, available `0`, `100%`.
- Root release: `206,028,800` bytes, approximately `196.5 MiB`.
- `/data` after: `/dev/sdb`, size `210,779,160,576`, used
  `57,565,483,008`, available `143,533,334,528`, `29%`.
- Inode capacity was not the blocker: root was `14%` and `/data` was `1%`.
- All six storage objects were regular files, not directories or special
  backends, each with apparent size `120,000,000,000` bytes.
- `r2` and `r5` had `0` allocated 512-byte blocks; `r3`, `r4`, `r7`, and `r8`
  each had `100,608` allocated 512-byte blocks and one logical extent
  `0..12575` of length `12576` filesystem blocks.
- Three stability snapshots, two seconds apart, showed unchanged inode, size,
  block count, and mtime for the storage objects before migration.
- No matching `sglang`, launcher, vehicle, gate3, or HiCache runtime process
  was observed. `fuser` found no active handle on any archived storage file.

## Completed authorized actions

1. Created `/data/sglang-hicache-archive/2026-09-08/`.
2. For each storage file, created an equal-size sparse archive file, copied
   only allocated extents, preserved mode/ownership/mtime, and verified size,
   allocated block count, extent layout, and allocated-extent SHA-256 before
   unlinking the original storage file.
3. Left each original run directory and empty `storage/` directory in place.
4. Removed only the confirmed-empty transient marker
   `/tmp/t38c-probe.log`; `/tmp/t38c-durable-trace` was already absent.

## Archive mapping and integrity

| Original | Archive | Size | Blocks | Integrity |
|---|---|---:|---:|---|
| `/root/evidence-gate3-parked/p0-s25-v43-live-r2/storage/hicache.data_qwen3.5-9b-gptq_0_1` | `/data/sglang-hicache-archive/2026-09-08/p0-s25-v43-live-r2/storage/hicache.data_qwen3.5-9b-gptq_0_1` | 120000000000 | 0 | all-hole sparse file |
| `/root/evidence-gate3-parked/p0-s25-v43-live-r3/storage/hicache.data_qwen3.5-9b-gptq_0_1` | `/data/sglang-hicache-archive/2026-09-08/p0-s25-v43-live-r3/storage/hicache.data_qwen3.5-9b-gptq_0_1` | 120000000000 | 100608 | extent SHA-256 `ff804300447364d6d318760a343840781cdd625a3135d122e02e969c42ab7516` |
| `/root/evidence-gate3-parked/p0-s25-v43-fix1-live-r4/storage/hicache.data_qwen3.5-9b-gptq_0_1` | `/data/sglang-hicache-archive/2026-09-08/p0-s25-v43-fix1-live-r4/storage/hicache.data_qwen3.5-9b-gptq_0_1` | 120000000000 | 100608 | extent SHA-256 `0cd26d5f57d94b153f4d3a943d7f064a65d42d84d59a3e88a6a11207e6919687` |
| `/root/evidence-gate3-parked/p0-s25-v43-fix2-live-r5/storage/hicache.data_qwen3.5-9b-gptq_0_1` | `/data/sglang-hicache-archive/2026-09-08/p0-s25-v43-fix2-live-r5/storage/hicache.data_qwen3.5-9b-gptq_0_1` | 120000000000 | 0 | all-hole sparse file |
| `/root/evidence-gate3-parked/p0-s25-v43-fix2-live-r7/storage/hicache.data_qwen3.5-9b-gptq_0_1` | `/data/sglang-hicache-archive/2026-09-08/p0-s25-v43-fix2-live-r7/storage/hicache.data_qwen3.5-9b-gptq_0_1` | 120000000000 | 100608 | extent SHA-256 `c97be1fc757dfa6f6c0deef51dc0bf7e03ec8a63a8b438514539519a6d86f0d9` |
| `/root/evidence-gate3-parked/p0-s25-v43-fix2-live-r8/storage/hicache.data_qwen3.5-9b-gptq_0_1` | `/data/sglang-hicache-archive/2026-09-08/p0-s25-v43-fix2-live-r8/storage/hicache.data_qwen3.5-9b-gptq_0_1` | 120000000000 | 100608 | extent SHA-256 `0cd26d5f57d94b153f4d3a943d7f064a65d42d84d59a3e88a6a11207e6919687` |

Post-audit found six final archive files and zero `.part.*` files. The archive
manifest SHA-256 is
`37e4aa4e31c906dfb659f5c0902c3330ca5d76142e6bd1f1142148943e06aac2`.

## Evidence preservation

- All six original run directories still exist.
- Original `storage/` directories remain in place, empty after verified move.
- No command targeted `raw/`, `log/`, or `report/`; the post-audit found the
  existing raw trees for `r3`, `r4`, `r5`, and `r7` intact and no `log/` or
  `report/` directories in the six targeted runs. The r9 evidence directory
  was not touched.
- No `evidence`, `raw`, `log`, or `report` path was deleted.

## Rollback

Rollback is reversible only after root capacity is provisioned and no runtime
process is active. For each mapping in the archive manifest, recreate the
original parent/storage path, recreate a same-size sparse file from the
archive's allocated extents, verify size, block count, extent layout, mtime,
and extent SHA-256, then unlink the archive copy. The exact inverse mappings
are recorded in the remote manifest as `rollback_mapping=` entries. Do not
run rollback while root is full.

## Acceptance result and followups

- Safe archive and preservation: **PASS**.
- Integrity and reversibility evidence: **PASS**.
- Root release >=130G: **FAIL**; only `206,028,800` bytes were reclaimable
  because the authorized files were sparse.
- Enough root capacity to create the frozen 120G storage: **NOT VERIFIED / BLOCKED**;
  root still has 0 available bytes.
- Frozen S=25 live run: **must remain blocked**; no engine was started.

Required followup is an authorized capacity operation outside this storage-only
scope, such as provisioning/root-overlay expansion or authorization to use a
different storage location. After capacity is available, dispatch a fresh Task
ID for the live run and re-run all launch preconditions.

## Open issues

1. Root overlay remains at 100% with 0 bytes available.
2. The authorized old-storage set contains only about 196.5 MiB of physical
   blocks despite 720G of apparent logical file sizes.
3. The next capacity action needs new authorization; this invocation does not
   alter the launch contract or substitute `/data` as live storage.

blocked
