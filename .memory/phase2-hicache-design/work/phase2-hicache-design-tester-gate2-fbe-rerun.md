# phase2-hicache-design-tester-gate2-fbe-rerun

## status
done

## artifacts

Gate-2 re-run on 3090 after the flush-before-evict (FBE) fix, K=4/8/16 three
tiers, same config as the gate2-saturation baseline (write_back + extent +
HICACHE_SIZE=0 pool 106 slots + extra_buffer + int8 mamba OFF). Verified FBE
deployed (mamba_component.py md5 MATCH local, unit tests 8/8 green on the live
3090 tree). **Pure verification, no code changes.** Report path
`phase2-hicache-design-tester-gate2-fbe-rerun.md` (3090 + local copy). 3090
left clean (no engine, GPU 15MiB, no locks); three fresh experiment namespaces
`/data/l3/p2io-gate2-fbek{4,8,16}` remain as evidence.

Deliverables / evidence (all on 3090):
- Run dirs: `/root/evidence-gate2-fbek4/run-20260904-132353`,
  `/root/evidence-gate2-fbek8/run-20260904-133157`,
  `/root/evidence-gate2-fbek16/run-20260904-134356`
- Engine logs: `/root/engine-gate2-fbek{4,8,16}.log`
- T38C probes: `/root/evidence-gate2-fbek{4,8,16}/t38c-probe.log`
- Analyzer: `/root/gate2_analyze.py` (same as baseline)
- FBE fix: `mamba_component.py` `drive_host_eviction` :849-936 (md5
  `2a644f7d...` identical local/remote), unit suite 8/8 OK.

## evidence

### FBE deployment verified (pre-requisite)
```
md5sum mamba_component.py  (local == remote == 2a644f7d816d313f125ab0ff44690718)
cd /root/sglang-b1-continuity/3090-dev && python test_fbe_flush_before_evict.py
  -> Ran 8 tests ... OK   (all 8 sparing/flush/pin/ack tests green)
```
Config frozen-identical to baseline (from engine server_args + Mamba alloc):
`max_mamba_cache_size: 106`, `enable_int8_mamba_checkpoint: False`,
`hicache_write_policy: write_back`, `hicache_storage_backend: extent`,
`hicache_size: 0`, `mamba_radix_cache_strategy: extra_buffer`, prefetch
`wait_complete`.

### Analyzer output (baseline-methodology surface) per tier

| metric | K4 base | K4 FBE | K8 base | K8 FBE | K16 base | K16 FBE |
|---|---|---|---|---|---|---|
| usable rows | 44 | 43 | 64 | 67 | 74 | 75 |
| phase-B ratio | 0.8335 | 0.8373 | 0.6905 | 0.7107 | 0.6439 | 0.6265 |
| L0 restore ratio (skip-missing) | 0.9201 | 0.9219 | 0.8743 | 0.8513 | 0.7921 | 0.7843 |
| mamba evictable max | 31 | 31 | 32 | 32 | 32 | 34 |
| dropped(mamba) | 0 | 0 | 1 | 1 | 0 | 0 |

### GENUINE full-miss (missing-sglext, pl>1000, ttft 15-231s, engine
`revoked:miss`) — corrected methodology (the analyzer's `full_miss(<100)`
SKIPS missing-sglext rows, so it prints 0 everywhere and is misleading)

| metric | K4 base | K4 FBE | K8 base | K8 FBE | K16 base | K16 FBE |
|---|---|---|---|---|---|---|
| L0 restore full-miss | 0/12* | 1/12 | 4/24 | 5/24 | 20/48 | **16/48** |
| L1 restore full-miss | n/a | ? | 0/8 | 1/8 | 9/16 | 10/16 |
| L2 restore full-miss | n/a | ? | 0/8 | 0/8 | 7/16 | 6/16 |
| phase-B full-miss | 0/32* | 1/32 | 11/64 | 10/64 | 59/128 | **57/128** |
| L0 full-miss ttft mean | - | 58.6s (n=16) | - | - | 62.1s (n=20) | 58.6s (n=16) |

(*baseline K4 join.log was lost; report reconstructed 0/20 restore full-miss.
FBE K4 has 1/12 L0 full-miss at low pressure — a regression vs the ~0
baseline K4, though n is tiny.)

### restore-side defect: L3 restore never returns tokens (the dominant cause)

Across ALL runs, **storage_hit = 0 for every single usable row** — L3 never
contributes a token to any request in K=4/8/16 baseline or FBE:
```
rows with storage_hit>0: 0      (all runs: fbek4/8/16, and baseline k8/k16)
pc_storage_query ... kv_hit_pages=0 storage_hit_count=0 sidecar_hits={}   (1951 queries)
prefill_effective_tokens_total mode="storage_hit" -> 0.0
load_back_tokens pool=mamba -> 106   (vs backup(mamba)=2110)
```

Correlation of the 1951 restore queries against the 1287 `pc_write_seed`
(L3-write) hashes (K16 FBE):
```
queries whose first key was EVER written to L3 : 1643
queries with >=1 key written to L3 BEFORE query :  958
  ...and of those 958, still storage_hit=0       :  958  (100%)
  ...and got hit>0                                :    0
queries with nonempty sidecar_hits               :    2
```
So even when the chain's KV was written to L3 BEFORE the restore query, the
L3 lookup returns zero pages. The mamba L3 **restore path never materializes a
checkpoint from L3**, regardless of whether the data is present. Two
sidecar_hits nonempty proves the sidecar can reach the query gate, but never a
usable restore.

Timing also confirms the first full-miss happens at run start (13:43:57, 1s
after healthy), before any pool pressure: `restore_disposition ... granted=0
reason=revoked:miss` and `restore_recompute cause=miss
final_storage_survivability=host` for a full-slot `requested=20910` chain on
the very first L0 restore — the pool is only ~30% used at that point.

### FBE did not regress, and did not close the cliff

FBE is correct at unit level (8/8) and the mechanism (spare non-durable host
victim, post-walk `write_backup_storage`, pin to ack, evict after durable) is
sound. But the gate-2 full-miss count is essentially unchanged: K8 restore
full-miss 4/40 -> 6/40, K16 36/80 -> 32/80, K16 L0 20/48 -> 16/48 (33% residual,
not ~0). The reason: the dominant full-miss mechanism is the **restore-side L3
miss** (query returns 0 even when the chain is in L3), which FBE (a write-side
persist guarantee) cannot fix — the checkpoint never comes back from L3
regardless of whether it was made durable.

## summary

**Primary gate (aggregate effective cache ratio >= 95%, exact-restore
methodology): FAIL.** K=16 L0 exact restore ratio 0.7843 (well below 0.95) and
33% (16/48) genuine full-miss; the L0 0-hit cliff was NOT closed to ~0 as the
dispatch's core expectation predicted.

**FBE verdict: correct but insufficient.** The HOST->L3 break-hop that FBE was
built to close (sidecar dropped at host eviction before deferred L3 persist)
is real and one contributing full-miss mechanism, but it is NOT the dominant
one in this load. The dominant defect is a restore-side issue: the L3 restore
lookup returns 0 pages for a chain even when that chain's KV was written to L3
before the query (958/958 such queries zero-hit). Because the restore can't
read the mamba back from L3 regardless of durability, making it more durable
(FBE) has roughly no effect on the aggregate cliff: full-miss went K16 45% ->
44.5% (phase-B), L0 41.7% -> 33.3%. The tiny improvement (41.7 -> 33.3) likely
reflects the genuine FBE-covered cases (host-eviction sidecar loss), which are
a minority.

Also note: FBE K4 shows 1/12 L0 full-miss at near-zero pressure where baseline
K4 had 0 — a possible low-pool FBE side effect (or load variance), small-n, not
conclusive; worth a confirmation run, but it does not change the FAIL verdict.

## followups

1. **Root cause to transfer (dominant)**: the L3 restore path in this config
   never returns a mamba checkpoint from storage even when the chain KV is
   already in L3. Location: scheduler `_prefetch_kvcache` /
   `_reconcile_restore_states` + `unified_radix_cache.prefetch_from_storage` /
   `_storage_hit_query` (cache_controller) + the mamba sidecar restore feed.
   Evidence: pc_storage_query kv_hit_pages=0 on 958 queries whose key was
   written earlier; zero storage_hit across all 6 runs; `revoked:miss` hard
   fail instead of degrade. This is the gate-2 blocker.
2. **FBE residual**: even if L3 restore were fixed, determine the FBE-covered
   fraction: instrument a spared-vs-evicted host-mamba counter (P3 read-only)
   to see whether FBE is firing at all under this load, or whether the
   non-durable host victims are rare (pool rarely saturates the host mamba
   LRU). The pool never exceeded 34/106 evictable; host mamba pressure may be
   low, making FBE rarely exercisable in this load.
3. K16 phase-B ratio 0.6265 (FBE) vs 0.6439 (base) is within load variance
   (per-request shape), not evidence of regression; the exact-restore rows are
   the load-shape-independent metric.

## open_issues

- Gate-2 remains FAIL. The path forward is a restore-side fix (L3 mamba
  restore must return hits when the data is durable), which is outside the FBE
  write-side scope; recorded for coordinator / coder (gate-3+ work).
- FBE K4 1/12 L0 full-miss is a small-n anomaly to confirm; not blocking.
- Environment left clean except the 3 self-created experiment namespaces
  `/data/l3/p2io-gate2-fbek{4,8,16}`; all engines SIGTERMed, GPU 15MiB, no
  locks. No production code changed (verification only).