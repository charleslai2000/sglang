# P2-IO capacity accounting: kv host pool sizing, reserve/margin %, usable capacity, recommendation (tester e7g)

Status: done

Date: 2026-09-01. Pure analysis (no code change, no new run). Source of truth:
e7f engine log (`/tmp/p2io-e7f-ev/engine-p2io-m4t-e7f.log`) + branch sizing code
(`python/sglang/srt/mem_cache/pool_host/base.py`, `.../mla.py`,
`.../mamba.py`, `.../hybrid_cache/hybrid_pool_assembler.py`, scheduler
`_compute_writeback_reserve`).

## 1. Kernel pool token capacity and bytes (question 1)

Measured directly from e7f engine log allocation lines:

```
[18:23:28] Allocating kv hierarchical KV host pool: 68453 tokens, 2.24 GB host memory.
[18:23:29] Allocating 5.77 GB host memory for hierarchical Mamba cache (layout=page_first).
[18:23:09] Mamba Cache is allocated. max_mamba_cache_size: 106, conv_state size: 0.12GB, ssm_state size: 5.02GB
[18:23:09] KV Cache is allocated. dtype: torch.bfloat16, #tokens: 65536, K size: 1.00 GB, V size: 1.00 GB
```

Derived:

| Pool | Device bytes (GB) | Device frac | Host bytes (GB) | Host tokens | bytes/token (spt) |
|---|---|---|---|---|---|
| kv | K 1.00 + V 1.00 = 2.000 | 0.2801 | 2.24 | 68,453 | **32,723.2 B/tok** |
| mamba | conv 0.12 + ssm 5.02 = 5.14 | 0.7199 | 5.77 | 118 pages (=tokens, 1 tok/page) | 48,490,566 B/page |
| total | 7.14 | 1.000 | 8.01 | — | — |

**kv_frac = 0.2801**: the kv host pool receives `8G * 0.2801 = 2.24 GB` and the
mamba pool `8G * 0.7199 = 5.76 GB` — exactly the log (0.001 GB rounding). The
split is by **device** pool byte ratio (`_split_hicache_size`, hybrid_pool_assembler.py):
`kv_host_size = hicache_size * kv.get_kv_size_bytes() / (kv_bytes + mamba_bytes)`.

kv spt cross-check against the code path, MHA:
`head_dim(256) * (kv_heads?)(4) * layer(32) * dtype(2B) * 2 = 131,072 B/tok` — with
`num_kv_heads=4` that's 2x the measured. The actual device pool
`K+V = 2.0 GB / 65,536 tok / 32 layers / 2B = 472 B/layer/tok`; with
`partial_rotary_factor=0.25` and the MLA-less GQA path the effective per-token
kv_cache_dim ≈ 236 B (e.g. `num_kv_heads(4)*head_dim(256)*0.25*2B*panels` = 512*token... exact
kernels differ). **For capacity purposes take the log-derived `spt_kv = 32,723.2 B/tok`
as ground truth** (matches 2.24 GB / 68,453 tok).

No `hicache_host_used=22k/68k` string exists in the e7f engine log or join.log —
the coordinator's observed `host_used=22k/68k` comes from a runtime metric (host
occupancy publish) not present in these files; its value (22,452 ≈ working) is the
operational anchor used below.

## 2. Reserve / margin as % of kv pool (question 2)

At HICACHE_SIZE=8 (kv pool 68,453 tok, spt 32,723.2):

```
reserve 1.5 GB  -> int(1.5e9 // spt)           = 45,839 tok = 1.500 GB = 66.9% of pool
margin  0.3 GB  -> int(0.3e9 // spt)           =  9,167 tok = 0.300 GB = 13.4% of pool
                                              combined = 80.3% (55,006 tok)
```

- reserve conversion = `set_writeback_reserve_bytes`: `reserve_bytes // size_per_token`
  (page_size=1, dcp=1 → logical_page_size=1, no page floor; base.py:397-405, group.py:71-80)
- margin conversion = scheduler `_compute_writeback_reserve`:
  `int(margin_gb*1e9 // bytes_per_token)` (scheduler.py:3503-3508)
- **The kv host pool loses 4/5 of its total capacity before any cache data is held.**
  The reserve is a **kv-pool-specific absolute floor**: at 8G it is >2/3 of the kv
  anchor pool. mamba host-side it is `int(1.5e9 // 48.49MB/page) = 30 pages` = 25.4%
  of the 118-page mamba host pool.

## 3. Usable capacity after reserve+margin (question 3)

```
kv pool 68,453 tok = 2.240 GB
  - reserve 45,839 tok = 1.500 GB
  - margin   9,167 tok = 0.300 GB
= usable   13,447 tok = 0.440 GB
```

| READY-state size | tokens | kv-host GB | fits usable |
|---|---|---|---|
| READY typical | 16,375 | 0.536 | **No** |
| READY max (two requests saw it) | 20,855 | 0.682 | **No** |
| full input chain | 27,811 | 0.910 | **No** |

**Conclusion: usable 13.4k tokens < one READY state.**

Even the smallest READY (16,375 tok = 0.536 GB) does not fit in the usable pool at 8G.
The Z3 drop flood (1001 drops), 16/24 fully-missed restores, Ready Horizon never
admitting READY_HOST≥2, and the 65 GB extent write-back all follow from the same
arithmetic: the kv host pool never held a complete READY state for more than an
instant — write-back reserve + safety margin left no holdable capacity.

## 4. HICACHE_SIZE recommendation (question 4)

Requirement semantics (coordinator's exact scope): **capacity ≥ working + 2×READY + reserve + margin**

```
kv host capacity needed = 22,452 (working)
                        + 2 × READY (max measured 20,855; typ 16,375)
                        + reserve + margin
```

Min HICACHE_SIZE per reserve option (`H = kv_tokens * spt / kv_frac / 1e9`,
`cap(H) = int(H*kvfrac*1e9 // spt)+1`):

| reserve | work+2×READY_max need (tok / GB) | min H fits | work+2×READY_typ need | min H fits | work+2×coord(1.424GB) need | min H fits |
|---|---|---|---|---|---|---|
| 1.5 GB (45,839) | 119,168 / 3.90 | 14G | 110,208 / 3.61 | 14G | 164,492 / 5.38 | 20G (infeasible on RAM) |
| 1.0 GB (30,559) | 103,888 / 3.40 | 14G | 94,928 / 3.11 | 12G | 149,212 / 4.88 | 18G (tight) |
| **0.75 GB (22,919)** | **96,248 / 3.15** | **12G** | **87,288 / 2.86** | **12G** | 141,572 / 4.63 | 18G (tight) |

capacities: H=12G → kv 3.36 GB / 102,730 tok; H=14G → 3.92 GB / 119,841 tok.

**Recommended: HICACHE_SIZE = 12 GB, reserve = 0.75 GB, margin = 0.3 GB.**
- kv host 102,730 tok (3.36 GB), after reserve 0.75 GB (22,919) + margin 0.3 (9,167)
  leaves 70,644 tok (2.31 GB) usable — holds working + 2×READY_max + 6.4k-tok cushion.
- RAM: pools 12G + 10G system reserve = 22 GB ≤ 29.9 GB avail, **7.9 GB headroom** — feasible.

The coordinator's alternate READY basis 1.424 GB (= 43,517 kv tok) is larger than
anything measured this run (max 20,855 tok = 0.68 GB kv; mamba +0.048 GB/state), so
it only matters if the READY definition counts the full kv+mamba payload in kv
tokens. If that definition is authoritative the target is 5.38 GB kv = **18G
(res1.5) / 18G (res1.0 / res0.75)** — near the RAM ceiling (28 GB with 1.9 GB
headroom).

3090 system RAM budget: available = **29.9 GB** (`MemAvailable 31,388,920 kB`;
`free -g` 31G total / 29G avail). Pinned host pools + 10 GB fixed system reserve
(`HICACHE_HOST_MEMORY_RESERVE_BYTES`, base.py:27):
- 12G → 22 GB, headroom 7.9 GB — **feasible, comfortable**
- 14G → 24 GB, headroom 5.9 GB — feasible
- 16G → 26 GB, headroom 3.9 GB — feasible
- 18G → 28 GB, headroom 1.9 GB — feasible (tight; only if coordinator's 1.424 GB READY basis is authoritative)
- 20G → 30 GB > 29.9 — **not feasible** on this 31 GB box

**12 GB is the largest value whose working+2×READY target fits with a comfortable
RAM headroom** (and the smallest that satisfies it at all).

## 5. Reserve representation recommendation (question 5)

**Recommendation: express reserve as a fraction of the anchor pool (e.g. "kv host
capacity fraction"), not absolute GB.**

Evidence:
1. **Byte reserve and pool capacity don't commute with the split.** `8G` splits to
   kv 2.24 GB and mamba 5.76 GB; `reserve 1.5 GB` is 67% of the kv pool but 25% of
   mamba. Any HICACHE_SIZE change rescales pools independently of the fixed byte
   reserve — the reserve % drifts without any change to the operator's own
   intent.
2. **The reserve's purpose is state-granularity, not byte-granularity.** A
   write-back reserve that leaves <1 READY state (13.4k < 16.4k tok) is a
   self-contradiction: the channel it protects cannot stage the very object it
   is meant to stage. The natural spec is "leave N READY-state-equivalents of
   holdable capacity ≥ working pool", i.e. `usable ≥ working + 2*max_READY`'s
   token-min, which only a pool-fraction (or token-count) expression can state.
3. **e7e-before-crash forced=21, e7f forced=1:** at 8G with reserve 1.5 GB the
   force count dropped from 21 to 1 because e16's drop-tomorrow path (forced_drop
   on `no_durable_backup`) is the clean-up code, not the capacity fix. The
   reserve still has to be sized so the kv anchor pool can actually hold a READY
   state; the count did not detect the 0.44 GB usable hole because forced_drop
   stops firing once the drop path returns cleanly (the eviction storm went to
   extent instead).

Switch reserve overhead from `reserve_bytes` to `reserve_fraction` (e.g.
`0.15 * anchor_pool_capacity()`), with READY-state-aware floor
`max(reserve_fraction, WORK + 2*max_READY_pooled)` in token space. Concrete
initial value at the recommended 12G: **0.75 GB → 22,919 tok = 22.3% of kv pool**;
as a fraction that holds across HICACHE rescales (the same usable target stays a
stable % of the pool instead of a drifting byte count). Margin 0.3 GB (9,167 tok)
at 12G = 8.9% of kv pool.

## 6. Summary / deliverables / followups

Tests written: none (pure analysis; no code or test change).

Evidence (commands above):

1. Allocation lines (engine:657-658, 642-643) → kv 68,453 tok / 2.24 GB, mamba 5.77 GB.
2. `_split_hicache_size` (hybrid_pool_assembler.py:134-147) → byte-frac split; 8G → kv 2.24 GB.
3. `set_writeback_reserve_bytes` (base.py:397-405), margin converter (scheduler.py:3503-3508).
4. `promotion_reserve` / `promotion_transfer` lines (e7f) → max READY state 20,855 tok, typical 16,375.
5. `restore_disposition ... requested=27,811` → full input chain.
6. `MemTotal 32,874,608 kB, MemAvailable 31,388,920 kB`; `free -g` = 31G total / 29G avail.
7. Extent file size 65 GB; `extent 67108864 B slots=1024`
8. Scan table (python) with spt 32,723.2, kv_frac 0.2801.

Coverage: n/a (analysis task).

Followups:
- 1 — coder: add `hicache_writeback_reserve_fraction` (fraction of anchor host pool)
  alongside `hicache_writeback_reserve_gb`; document that reserve < 1 READY-state
  (token floor) is the invalid-config warning. Location:
  `python/sglang/srt/mem_cache/pool_host/base.py:397` +
  `hybrid_pool_assembler.py:1735` + `scheduler.py:3503`.
- 2 — coder: at host-pool-construct, log reserve/margin as % of each pool's
  capacity (kv + mamba), so the 67%/13% drift shows up immediately in the engine
  log instead of a silent 0.44 GB usable.
- 3 — coder (or metrics): publish kv/mamba host `usable(tokens)` metric (capacity
  - reserve - margin) next to `host_used`, and a `READY_state_max(tokens)` gauge,
  so the invariance `usable >= work + 2*READY_max` is machine-checkable.

Open issues:
- The 1.424 GB/READY figure (coordinator) exceeds every measured READY state
  (≤0.91 GB kv-host, mamba +0.048 GB/state). Either the definition counts kv+mamba
  payload in kv tokens (then the 19.2G number above applies) or it overcounts
  this workload; needs a definition confirmation before final parameterization.
- `host_used=22k/68k` string is not in the e7f engine/join logs — the operational
  'working' anchor (22,452) is from the coordinator observation and the `full_locked`
  max (58,469) is a single extreme at 18:30:40 (worked reserve=0 window), not the
  steady state.
- reserve 1.5 GB at HICACHE=8 gives usable 13.4k < smallest READY 16.4k — the
  confirmed root-cause arithmetic for every e7f hard-gate failure; the capacity
  fix (12G / 0.75G / 0.3G per section 4) is the prerequisite before re-running
  the six gates, independent of any readiness-horizon logic.