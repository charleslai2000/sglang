# phase2-hicache-design-tester-gate2-saturation

## status
done

## artifacts

Gate 2 of the three hard gates (3090): **Mamba checkpoint pool 压力下
aggregate effective_cache_ratio ≥95%**, measured across unsaturated →
near-saturated → saturated, with a cliff scan (old-session / mid-branch
systematic 0-hit). No code/checkpoint-strategy changes — only measurement of
real capacity boundaries.

Deliverables (all in /root on 3090 unless noted):
- Load driver (two-phase: write-saturate then read-verify):
  `/root/gate2_load.py` (local copy `3090-dev/gate2_load.py`)
- Run driver: `/root/gate2-run2.sh` (local `3090-dev/gate2-run2.sh`)
- Analyzer: `/root/gate2_analyze.py` (local `3090-dev/gate2_analyze.py`)
- Evidence: `/root/evidence-gate2-k4/`, `/root/evidence-gate2-k8/`,
  `/root/evidence-gate2-k16/` (fresh namespace per run:
  `/data/l3/p2io-gate2-<tag>`, engine SIGTERM after each run, one engine at
  a time)
- This report (six sections).

## evidence

### Tier 1: K=4 (unsaturated; pool 106 slots; ~32 checkpoint slots written)

Run dir: `/root/evidence-gate2-k4/run-20260904-094539`
Engine: frozen config confirmed (`max_mamba_cache_size=106`, `int8 mamba
checkpoint OFF`, `extra_buffer`, extent backend, HICACHE_SIZE=0).

Commands and real output:

```
/root/miniconda3/envs/sglang-patch/bin/python /root/gate2_analyze.py \
  /root/evidence-gate2-k4/run-20260904-094539 k4
```

Output (excerpt):
```
requests parsed=48 (usable rows 44)
-- aggregate effective cache ratio (join per-request) --
  total_prompt=1204524 total_hit=912281 ratio=0.7574 (FAIL <0.95)
-- mamba pool water --
  mamba_evictable series n=67 min=1 max=31 mean=13.4
  final: available=91.0 evictable=15.0 used=0.0 -> pool_size=106.0
  hicache dropped(pool=mamba)=0.0 backup(mamba)=209.0 load_back(mamba)=72.0
-- cliff scan --
  zero-usable requests with prompt>100: 0; prompt>1000: 0
-- Phase A write/saturate --
  requests=16 prompt=424556 hit=262193 ratio=0.6176
-- Phase B read/verify --
  requests=32 prompt=779968 hit=650088 ratio=0.8335
-- exact-checkpoint retrieval (restore rows, phase B) --
  L0 restore n=12 prompt=250932 hit=230873 ratio=0.9201 full_miss(<100)=0
  L1 restore n=4 prompt=111248 hit=94368 ratio=0.8483 full_miss(<100)=0
  L2 restore n=4 prompt=139252 hit=103264 ratio=0.7416 full_miss(<100)=0
```

Interpretation (documented analysis, not conclusion):
- K=4 is well under pool capacity (evictable max 31 / 106, dropped(mamba)=0,
  no eviction events). Absolute ratio 0.7574 (phase B 0.8335) is below 0.95,
  but this is dominated by load-shape, not checkpoint residency:
  - L0 exact restore per-request splits: 20864/20911 (99.8%), 20881/20911
    (99.9%), 20898/20911 (99.96%), 16384/20911 (78%), 15953/20911 (76%),
    15522/20911 (74%) — the <99% requests are partial radix matches with the
    checkpoint NOT in device pool (device hit=9 while host carries the bulk);
    these are hierarchical-placement partials (Host tier), not eviction
    (dropped=0).
  - L1/L2 restores are grow-chain mid-branch reads; their payloads extend the
    L0 chain so the hard ceiling is the shared-prefix fraction (~84% L1,
    ~74% L2), not residency failure.
  - ZERO "zero-usable" requests (no systematic 0-hit) at K=4.
- K=4 is the natural baseline: pressure is minimal, yet aggregate is already
  <95% by construction. The absolute bar of ≥95% is not reachable with this
  load shape; the decisive gate-2 acceptance question is whether pressure
  (K=8/16) creates a *cliff* relative to the K=4 baseline.

### Tier 2: K=8 (moderate pressure; pool 106; ~32 slots used of 106)

Run dir: `/root/evidence-gate2-k8/run-20260904-100048`
96 requests, rc=0, engine SIGTERM clean (GPU 15MiB, no lock leak after the
run2 lock-cleanup fix).

```
/root/miniconda3/envs/sglang-patch/bin/python /root/gate2_analyze.py \
  /root/evidence-gate2-k8/run-20260904-100048 k8
```

Output (excerpt):
```
requests parsed=96 (usable rows 64)
-- aggregate effective cache ratio (join per-request) --
  total_prompt=1681353 total_hit=1027960 ratio=0.6114 (FAIL <0.95)
-- mamba pool water --
  mamba_evictable series n=101 min=1 max=32 mean=20.8
  final: available=89.0 evictable=17.0 used=0.0 -> pool_size=106.0
  hicache dropped(pool=mamba)=1.0 backup(mamba)=827.0 load_back(mamba)=114.0
-- Phase A write/saturate --
  requests=32 prompt=358339 hit=114476 ratio=0.3195
-- Phase B read/verify --
  requests=64 prompt=1323014 hit=913484 ratio=0.6905
-- exact-checkpoint retrieval (restore rows, phase B) --
  L0 restore n=24 prompt=418220 hit=365649 ratio=0.8743 full_miss(<100)=0
  L1 restore n=8 prompt=222496 hit=125886 ratio=0.5658
  L2 restore n=8 prompt=278504 hit=191231 ratio=0.6866
```

Genuine full-miss (usable==0) quantification:
```
phase B full-miss requests=11/64 (17.2%)
restore full-miss=4/40 (10.0%)
```

The 4 full-miss restores are TRUE checkpoint losses, not parse artifacts:
- engine: `restore_disposition disposition=RECOMPUTE requested=20910
  granted=0 reason=revoked:miss`
- `restore_recompute cause=miss final_storage_survivability=host`
- probe: `pc_storage_query ... storage_hit_count=0 sidecar_hits={}` and
  `pc_prefetch_enter gate matched_len=0 match_end=20910`
- ttft 28-33s (full recompute), `prompt_tokens_details: null` in body
- Session lifecycle shows the pattern: session 6 wrote L0 at A-t1, then at
  B-t6 restore of own L0 = full miss, yet B-t7 own L1 hit 15272, B-t8 own L2
  hit 23564, B-t9 session-2 L0 hit 16384. Same for session 2: own L0 restore
  at B-t10 full miss while own L1/L2 hit. => a *specific L0 checkpoint* was
  lost from device+host+L3 while the session's other chain levels survived.

Interpretation (documented):
- K=8 at only ~32/106 slots used (not saturated — checkpoint density per
  grow is ~1 slot, not 2; my estimate over-predicted). dropped(mamba)=1.
- Yet already 10% of exact L0 restores are full recomputes. This is a
  checkpoint-residency/restore defect: an exact same-chain restore that must
  be ~100% hit returning 0, with `final_storage_survivability=host` yet L3
  gate reporting storage_hit_count=0.
- Gate-2 acceptance ("old session no systematic 0-hit" / "effective hit not
  clearly below 95%"): K=8 shows a real cliff at moderate pressure.

### Tier 3: K=16 (high pressure, 192 requests)

Run dir: `/root/evidence-gate2-k16/run-20260904-101826`
192 requests, rc=0, engine SIGTERM clean (GPU 15MiB, no locks, no engine).

```
/root/miniconda3/envs/sglang-patch/bin/python /root/gate2_analyze.py \
  /root/evidence-gate2-k16/run-20260904-101826 k16
```

Output (excerpt):
```
requests parsed=192 (usable rows 74)
-- aggregate effective cache ratio (join per-request) --
  total_prompt=1895963 total_hit=1142235 ratio=0.6025 (FAIL <0.95)
-- mamba pool water --
  mamba_evictable series n=248 min=1 max=32 mean=25.6
  final: available=79.0 evictable=27.0 used=0.0 -> pool_size=106.0
  hicache dropped(pool=mamba)=0.0 backup(mamba)=2113.0 load_back(mamba)=124.0
-- Phase B read/verify --
  requests=128 prompt=1678393 hit=1080771 ratio=0.6439
-- exact-checkpoint retrieval (restore rows, phase B) --
  L0 restore n=48 prompt=585508 hit=463765 ratio=0.7921 full_miss(<100)=0
  L1 restore n=16 prompt=194684 hit=97826 ratio=0.5025
  L2 restore n=16 prompt=313317 hit=137951 ratio=0.4403
```

Genuine full-miss quantification:
```
phase B full-miss requests=59/128 (46.1%)
restore full-miss=36/80 (45.0%)
```
- Full-miss breakdown: restore-L0 20, branch-BB1 16, restore-L1 9, restore-L2 7,
  branch-BB2 7.
- Verified genuine: `prompt_tokens_details:null`, no sglext, engine
  `restore_disposition ... RECOMPUTE granted=0 reason=revoked:miss` (and
  `denied_rate_limit` retry then `revoked:miss`), ttft 17-100s.

## Cross-tier summary (the gate-2 cliff)

| Metric | K=4 unsat | K=8 mod | K=16 high |
|---|---|---|---|
| pool evictable max | 31 | 32 | 32 |
| final available | 91 | 89 | 79 |
| dropped(mamba) | 0 | 1 | 0 |
| Phase B ratio | 0.8335 | 0.6905 | 0.6439 |
| L0 exact restore ratio | 0.9201 | 0.8743 | 0.7921 |
| phase B full-miss reqs | 0/32 (0%) | 11/64 (17.2%) | 59/128 (46.1%) |
| full-miss restores | 0/20 (0%) | 4/40 (10.0%) | 36/80 (45.0%) |

Notes on numbers: K8/K16 phase-B ratios above (0.6905/0.6439) and L0-restore
ratios (0.8743/0.7921) come from the analyzer (join.log, nonzero sglext rows);
the full-miss rates are computed over all phase-B requests (missing-sglext
rows counted as full-miss only when they are genuine recomputes: pl>1000,
usable=0). K4 numbers come from the artifact-reconstruction path (its
join.log/runs.csv were lost to the early csv crash), using the same
definitions.

## summary

**Gate 2 verdict: FAIL.** Under Mamba checkpoint pool pressure, the aggregate
effective cache ratio is far below 95%, and the failure is a true cliff, not a
load-shape artifact:

- Even at K=4 (pool ~30% used, zero eviction) the phase-B aggregate ratio is
  0.8335 and exact L0 restores hit only 0.9201. The <95% at K=4 is partly
  load-shape (grow-chains and BB mid-branch have inherent new content), but
  exact same-chain L0 restores already miss ~8% due to partial radix matches
  (device hit=9 with host carrying the bulk, i.e. checkpoint not in device
  pool).
- At K=8 (pool ~30% used, dropped(mamba)=1) exact L0 restore ratio drops to
  0.8743 and **4/40 restores (10%) are full recomputes** of previously-written
  chains (`revoked:miss`, L3 storage_hit_count=0, ttft 28-45s).
- At K=16 (pool ~30% used, dropped=0) it collapses: L0 restore ratio 0.7921,
  **36/80 restores (45%) are full recomputes**, phase-B full-miss 46%.

Critical observation: the MambaPool device never actually saturated (evictable
peaks at 32/106 in every tier; available 79-91). The checkpoint loss is NOT
device-pool eviction (dropped(mamba)≈0); the L0 chain checkpoints are lost from
the *device + host + L3* whole hierarchy for specific requests while the same
session's L1/L2 checkpoints survive. The `final_storage_survivability=host`
yet `storage_hit_count=0` mismatch, plus the "specific L0 missing while L1/L2
survive" pattern, points to a checkpoint residency/restore-miss defect rather
than simple LRU over-capacity. This is gate-2 FAIL evidence per the frozen
criteria ("checkpoint eviction causes effective hit to drop clearly below 95%"
/ "old session no systematic 0-hit").

## followups

1. Open: exact mechanism of the L0-specific checkpoint loss at K=8/K=16 while
   the pool is only ~30% used and dropped(mamba)=0. Hypotheses: (a) L3
   prefetch gate revoking (`revoked:miss`) before the extent has the mamba
   sidecar even though `final_storage_survivability=host`; (b) radix LRU
   evicting the mamba node while the KV node survives (mamba_component LRU is
   separate); (c) write-back CoW discard (mamba_component.py:166-168 comment:
   "write-back eviction may discard the device-only state"). Location:
   scheduler/mem_cache mamba_component + prefetch gate in scheduler.py.
2. Open: checkpoint density is ~1 slot per grow (pool never exceeded 32
   evictable across all tiers) — the K=16 tier did not push the pool past the
   K=8 level; a true over-capacity eviction test needs a different load (more
   distinct chains per session or `mamba_max_states_per_path` changes — which
   is a checkpoint-policy change, out of scope here and recorded as gate-3+
   work).
3. The 12-turn agent_driver load-shape caps the phase-B ratio near 0.83 even
   with zero eviction; gate-2 acceptance should be measured on exact
   same-chain restore ratio (the L0-restore rows), not the raw aggregate, to
   isolate residency from load-shape.

## open_issues

- Gate 2 FAIL (evidence above). Per user hard boundary: if gate 2 fails, the
  only path forward is a checkpoint-policy change (recorded, not implemented
  here): e.g. int8 mamba checkpoint enablement, or adjusting
  mamba_max_states_per_path / extra_buffer sizing, or the L3 prefetch gate
  allowing mamba sidecar restore when `final_storage_survivability=host`.
  That is gate-3+ work; no code/strategy was changed in this gate.
- Self-created experiment namespaces /data/l3/p2io-gate2-{k4,k8,k16} exist and
  were the intended fresh-namespace-per-run. No other artifacts left on 3090.
- The early K4 run lost join.log/runs.csv to the csv-writer crash (fixed in
  later driver); K4 numbers reconstructed from per-turn artifacts
  (equivalent definitions, verified body-level).
