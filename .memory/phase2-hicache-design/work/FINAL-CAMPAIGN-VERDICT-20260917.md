# FINAL M1 GPU campaign — verdict 2026-09-17 08:55Z (cutoff 09:00)

## New frozen identity (produced, verified)
`/opt/sglang/local-prod-v1.1.2-candidate` = `LOCAL-PROD-v1.1.2`
tree digest `cf32a4292b13c40b53ea0dfb12dd426526abdcc4c3b8911460edc5030b2344e5`
launcher  `6e57bc57c4b5576434e61e5e201602592786f7b73b58db3228d07ec8a5756ba4`
14648 files / 2012804263 B / src `dr-xr-xr-x`; manifest deterministic; preflight PASS.
v1.1 UNTOUCHED (`f0ca9206...97ab9ab7` unchanged). Freeze tooling first re-froze v1.1 to the identical
digest, then built the candidate from exactly the 3 approved files; GGUF delta hard-refused.

## Campaign result: neither gate reached a valid verdict
**Gate A -> INVALID (rc=2).** Content equality HELD (`rec_A_ids_eq_device` OK, `rec_B_ids_eq_device` OK,
`no_cross_session_bleed` OK) but the storage-tier proof FAILED on the L3 arms:
`L3_A/L3_B cached_tokens_details = {device: 64960, host: 0, storage: 0}`; `RECOVERED_B` also
`{device:64960, storage:0}`. L3 console shows `prefetch_revoke ... storage_hit=0 ... miss_reason=miss`.
Per the owner's hard rule (`storage > 0` mandatory, else INVALID) this is **INVALID, not PASS**.

**Gate A-F1 -> FAIL, but the window was never exercised.** `sweep.recycle_events = 0`,
`sweep.slot0_recycles = []`, despite `total_store_written_bytes = 1,493,385,216 > file_size = 1,342,177,280`
and only 51 `evt=extent_write` / **0** `evt=extent_recycle` in the console. `pre_sweep_storage_positive`
also FAILED (`storage=0`). So the deterministic wrap trigger never produced a slot recycle; the head-loss
window this gate exists to create did not occur. **Not-exercised => INVALID for F1 purposes**, even though
the harness recorded FAIL against its own expectation.

**F2 and the short canary never ran** (no dirs, no processes).

## Single blocker
**The final campaign never exercised the L3 storage tier.** Every arm restored from device/L1
(`storage=0`, `l3_tokens=0`), and the F1 wrap trigger produced 0 recycles, so no storage restore and no
slot reclaim occurred in either gate. Cause is on the harness/workload-geometry side (the requests kept
matching in device cache, so storage was never needed), not established as a product defect.

## What this does and does not say about the F1 Option-C fix
* It does NOT show the fix is wrong. The fix's unit-level evidence stands (A-G FAIL->PASS on a real
  backend; lookup paths byte-identical to frozen; suites 115/42/17; no-wrap steady path no regression).
* It does NOT close F1 either: the GPU-level post-wrap proof was never obtained, because the reclaim
  never happened. F1 remains **unproven at GPU level**.

## Also still open
* The interrupted durability adjudication's 4 anomalies (`GEN-6:no-permanent-pinning`,
  `CP1-before-commit:refs-reachable-bytes-exact` FAIL; `payload_bytes` v1-surface and `no_capacity`
  precondition INVALID) were never classified as REAL vs harness artifact — the classification child did
  not return before cutoff.
* Therefore the owner's four acceptance questions are only partly settled: Q2 (no recursive reclaim) and
  Q3 (latest-ref replay oracle) have PASSing oracle evidence; Q1 (genuine test) has the disclosed
  replacement test plus a frozen-tree FAIL; Q4 (no half-publication on no-capacity) is **UNVERIFIED**
  (its oracle returned INVALID on both trees).

## Terminal state
`PRODUCTION BLOCKED` — single blocker: the final campaign did not exercise the L3 storage tier, so neither
Gate A nor the F1 post-wrap proof could be established. M1 is NOT GREEN.
Gate B (native 64K/128K perf) remains a valid PASS and was not re-run.
