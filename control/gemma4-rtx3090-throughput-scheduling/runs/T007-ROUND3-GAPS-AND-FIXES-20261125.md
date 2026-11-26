# T007 round 3 — gap attribution and hot-path fixes (2026-11-25)

Frozen source baseline `d99c4764a0` (production source equal to `14856c531a`).
Delivery commit for this round is recorded at the end of this file; every number
below comes from a run directory under `/data/sglang-hicache/gemma4/runs/`.

Workload held fixed: original 40×20 C-8, FP8 E5M2 Owner, original Full/SWA
capacity, `chunked-prefill-size 4096`, CUDA graph b32, `write_back` +
`wait_complete`, L1/L2/L3 on, port 31401.

## 1. Two comparisons against the frozen build

### 1a. L1-only C-8 (no host/storage tier), matched chunk

`20261125T-t007-r3-l1only-c8-r2` — **643.77** official output tok/s, bench
window 318.12 s, extend 167.05 s + decode 144.55 s ⇒ forward duty **97.95 %**,
800/800, 0 failed, cache hit 0.9039, identical 800-payload multiset.

`20261125T-t007-r3-l1only-c8` (first attempt) is **superseded**: it was launched
without `T007_CHUNK`, so it ran `chunked-prefill-size 2048` while every full-tier
run used 4096 — 2 919 × 2 048-token prefill batches, 6.04 M new tokens
re-prefilled, 176.37 tok/s. Not a tier effect; a harness mis-invocation, kept for
the record with its intent file.

### 1b. Historical shared-prefix shape, C32

`20261125T-t007-r3-shared-c32b` — 8 192 in (7 168 shared prefix + 1 024 new),
256 out, 32 concurrent, same frozen service argv. 32/32 success, harness wall
15.07 s for 8 192 output tokens, TTFT p50 10.556 s, TPOT p50 14.71 ms
(2 177 tok/s at bs ≈ 30).

## 2. Seconds for the two gaps

### Gap A — short-context C32 → C-8 (same 204 800 output tokens)

Per output token: short-context burst 1.840 ms, C-8 (frozen build) 1.817 ms.

| segment | short C32 (15.07 s) | C-8 frozen (372.14 s) | Δ over 204 800 tokens |
|---|---|---|---|
| new prefill | 1.288 ms/tok | 0.868 ms/tok | **−88.9 s** |
| decode | 0.544 ms/tok | 0.744 ms/tok | **+40.0 s** |
| idle / supply / tail | 0.007 ms/tok | 0.205 ms/tok | **+38.7 s** |
| total | 1.840 | 1.817 | **−10.1 s** |

**There is no short-context headroom to reclaim.** The C-8 shape is already
faster per output token than a short-context 32-way burst: it pays +40 s in
decode (step 21.8 ms vs 14.71 ms at the same ≈29.5 tokens/step, i.e. +48 % for
1 k→25 k context) and buys back 88.9 s of prefill (3-sequence 4 096-token passes
vs 4-way 1 024-token passes; 5 700 vs 3 150 new tokens/s). Batch fill is not the
limiter either: mean running-req 29.47 of the 32 cap (92 %), so full-fill
accounting is worth only ≈12 s of decode. The residual is the 38.7 s idle /
supply / tail bucket — the same bucket as gap B.

### Gap B — C-8 L1-only → C-8 full tiers (identical payload and config)

| | L1-only | full tiers (frozen) | Δ |
|---|---|---|---|
| wall (bench window) | 318.12 s | 372.14 s | **+54.02 s** |
| extend forward | 167.05 s | 177.87 s | +10.83 s |
| decode forward | 144.55 s | 152.34 s | +7.79 s |
| pass-level idle | 6.52 s | 41.93 s | **+35.40 s** |

Identity holds exactly (10.83 + 7.79 + 35.40 = 54.02).

Trace attribution of the idle (`t007_gap_attribution.py`, Nsight window
`20261125T-t007-l3-wb-snapshot-c8`, 120.06 s, gaps ≥ 1 ms, disjoint by
construction): `get_next_batch_to_run` 8.95 s (7.46 % of wall),
`run_batch` before first launch 5.93 s (4.94 %), `process_input_requests`
5.03 s (4.19 %), `process_batch_result` 1.79 s (1.49 %), residual 0.47 s
(includes `reconcile_restore_states` 0.445 s), **submitted_stall 0.000 s,
handoff_after_sync 0.000 s**, sub-millisecond launch gaps 10.08 s (8.39 %).
So the tier penalty is host submission latency, not device dependency; the
L1-only window has the same shape at 7.5 % idle. `WAIT_CAPACITY` restore
intervals overlap 100 % of every bucket, so they cannot attribute idle and are
reported as correlation only.

## 3. Implemented hot-path fixes

1. **`free_swa` group filter deferral** (`python/sglang/srt/mem_cache/allocator/swa.py`).
   Grouped release now clears the full→SWA mapping at the original instant,
   appends the *unfiltered* indices and applies a single `freed[freed > 0]`
   filter at `group_end`; the ungrouped path keeps the per-call filter because a
   caller cannot prove padding-free mappings. Regression tests cover slot-0
   padding split across a group, duplicate release, and the ungrouped path
   (`test_swa_unittest.py`, 8 passed).
2. **Staged write-back early threshold exit** (`kvcacheio/staged_write_back.cuh`).
   The 128 KiB eligibility check moves ahead of building the
   `batch_srcs/batch_dsts/batch_sizes` vectors: 512 pages 118.6 → 95.5 µs,
   4 096 pages 231 → 109 µs, byte-exactness re-verified for contiguous and
   scattered pages. Contiguous page merging was already in place and was not
   re-developed.
3. **Wrapper official summary repaired** (`t007_c8_profile.sh`). The prom
   parser keyed series by the full label set (`category=...,engine_type=...`),
   so `extend`/`decode` deltas — and therefore duty — were always `null`. It now
   keys by `category`, reports duty against both the bench window and the client
   wall clock, and prints `bench_s`. Re-running the corrected block over the
   stored `.prom` files gives 550.33 / 88.73 % (baseline), 558.52 / 89.06 %
   (delivered), 643.77 / 97.95 % (L1-only).

## 4. Verification of the delivered build

`20261125T-t007-r3-after-swa-staged-c8`, unprofiled, original payload:
**800/800**, 0 failed, bench exit 0, identical 800-payload multiset, cache hit
0.9039, 0 Radix sanity failures, **558.52** official output tok/s in 366.68 s,
extend 175.14 s + decode 151.42 s ⇒ duty **89.06 %** of the bench window.

before → after: 550.33 → 558.52 tok/s (+1.49 %), wall −5.46 s
(extend −2.73, decode −0.92, idle −1.81). That is a real but small gain and it
is **below the 600 tok/s target**; the run-to-run spread of the frozen build on
this payload is 526–550 tok/s, so the gain is quoted with the segment deltas
rather than as a TPS-only claim.

## 5. Remaining largest item

The scheduler thread is saturated, not idle: NVTX inclusive time over the
120.06 s window is `run_batch` 64.05 s + `process_batch_result` 23.44 s +
`get_next_batch_to_run` 16.43 s + `process_input_requests` 15.10 s (2 003
iterations), and the single largest host stall inside it is
**`cudaStreamSynchronize`: 11 302 calls, 48.51 s of the 120 s window (40 %)**.
Joined to NVTX ranges by `correlationId`/`globalTid`:

| range | sync host time | calls | per call |
|---|---|---|---|
| `scheduler.run_batch` | 25.27 s | 4 095 | 6.2 ms |
| `scheduler.process_batch_result` | 16.82 s | 210 | 80.1 ms |
| `scheduler.process_input_requests` | 5.89 s | 4 836 | 1.2 ms |
| `scheduler.get_next_batch_to_run` | 0.53 s | 2 160 | 0.2 ms |

There is no explicit `.synchronize()` on this path (the `copy_done` waits are
`cudaEventSynchronize`: 2 897 calls, 24.6 ms total), so these are **implicit
syncs from `.item()`/`.tolist()` reads**: ≈2 per iteration in `run_batch` and
≈2.4 per iteration in `process_input_requests` (one full pass of waiting each,
≈6 ms and ≈1.2 ms), plus ≈210 one-pass drains in `process_batch_result`. That
is the item to attack next, and it must be attacked by naming the call sites
with `torch.cuda.set_sync_debug_mode("warn")` on a short instrumented window
first: several of the candidate reads are KV/HiCache ownership reads, where
removing the sync would relax persistence ordering — explicitly out of bounds.
Second item: fragmented (non-coalesced) backup copies, ≈1.0 s per 40.5 s host
sample; third: `update_sliding_window_buffer` on the extend path, 2.5 s per
40.5 s sample (≈7 ms per prefill batch, one device sync plus two allocations).

Measurement bases differ and are not interchangeable: the DeviceTimer duty above
(89.06 %) counts event-to-event forward spans, while Nsight kernel/ memcpy
busy-union over the same build is 73.14 % because it also counts the ≈10 s per
window of sub-millisecond inter-kernel launch gaps.
