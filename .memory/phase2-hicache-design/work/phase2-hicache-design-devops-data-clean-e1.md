# phase2-hicache-design / devops — /data cleanup on 24052 (Fix A/B precondition)

status: done

## Summary

Cleaned the historical HiCache L3 extent test products on experiment machine
`root@175.155.64.171:24052` `/data` (/dev/sdb, 197G ext4) from **100% full
(1.9G avail)** down to **10% used (170G avail)**, satisfying the user-adjudicated
precondition (must be <90%) for Fix A/B RH/extent validation.

Investigation confirmed the 100% usage was **NOT abnormal residual** and **NOT
live engine occupancy**:

- No HiCache `launch_server`/extent-writer process running. Only `jupyter-lab`
  (pid 282507, port 8000) present; **port 8024 not listening**.
- Every one of the 53 files under `/data` is a sparse `hicache.data_qwen3.5-9b-gptq_0_1`
  extent file (one per test run dir under `/data/l3`). No logs / no evidence files
  in /data. Sizes match expected per-run extent footprints.
- All space was attributable to historical A/B and other test extent products.

Cleanup removed only the three `p2io-gate3-ab-*` A/B extent dirs (the exact
artifact class the user adjudicated as RH/extent evidence pollution and the
dominant consumers). All other test dirs kept intact ("宁可多留").

## Artifacts

- Report: `.../.memory/phase2-hicache-design/work/phase2-hicache-design-devops-data-clean-e1.md`
- Deleted (precise paths, 3 files + 3 empty dirs):
  - `/data/l3/p2io-gate3-ab-a-off/hicache.data_qwen3.5-9b-gptq_0_1` (~90 GB phys) + rmdir
  - `/data/l3/p2io-gate3-ab-cal-off/hicache.data_qwen3.5-9b-gptq_0_1` (~57.7 GB phys) + rmdir
  - `/data/l3/p2io-gate3-ab-a-on/hicache.data_qwen3.5-9b-gptq_0_1` (~32.7 GB phys) + rmdir
- Total freed: ~180.4 GB physical (89,993,039,872 + 57,670,934,528 + 32,728,358,912 bytes)

## Evidence

### Before cleanup
```
Filesystem Size  Used Avail Use% Mounted on
/dev/sdb   197G  186G  1.9G 100% /data
```
Largest physical consumers (stat blocks; sparse files — apparent size misleading):
- p2io-gate3-ab-a-off:   89,993,039,872 B  (~90 GB)
- p2io-gate3-ab-cal-off: 57,670,934,528 B  (~57.7 GB)
- p2io-gate3-ab-a-on:    32,728,358,912 B  (~32.7 GB)
- p2io-gate1-churn:       8,027,705,344 B  (~8.0 GB)
- p2io-warmctx-32k:       5,618,044,928 B  (~5.6 GB)
- p2io-warmctx-128k:      1,932,562,432 B  (~1.9 GB)
- p2io-gen-p32-* (4 dirs): ~1.68 GB
- ~40 smaller dirs: ~50 MB each (apparent 96 GB sparse) or 0 B (fully sparse)

### After cleanup
```
Filesystem Size  Used Avail Use% Mounted on
/dev/sdb   197G   18G  170G  10% /data
```
- Total physical in use: 2,147,483,647 B (~17.42 GB)
- inode baseline: 128 / 13,107,200 used (1%) — no inode pressure
- Remaining non-empty top-level consumers (all historical, all <8.1 GB each):
  p2io-gate1-churn 8.0G, p2io-warmctx-32k 5.6G, p2io-warmctx-128k 1.9G,
  p2io-gen-p32-* ~1.68G, then ~40 dirs at ~50 MB each.
- Verified `p2io-gate3-ab-*` dirs no longer exist.
- All 70 remaining entries under /data/l3 are empty or sparse extent dirs.

### Safety confirmations
- `/root` (evidence logs) is on a **separate `overlay` filesystem**, not /dev/sdb —
  untouched by this cleanup. No /root file deleted or modified.
- Deletion used exact absolute paths; no wildcards; per-item justification recorded.
- Machine 22151 not touched (task scoped to 24052 only).

## Followups

- (non-blocking) If further space is later needed, the remaining historical
  dirs (gate1-churn ~8G, warmctx-* ~7.5G, gen-p32-* ~1.7G, and ~40 small dirs)
  are also non-essential extent products and can be cleared — pending user decision.

## Open Issues

- **Retention decision**: all remaining `/data/l3/*` dirs (53 extent files,
  ~17.4G) were left intact per "宁可多留 / 不确定不删". They are historical test
  products with no logs/evidence in them, but were NOT explicitly authorized for
  deletion in this dispatch. User to adjudicate whether any/all should also be
  cleared for additional headroom.
