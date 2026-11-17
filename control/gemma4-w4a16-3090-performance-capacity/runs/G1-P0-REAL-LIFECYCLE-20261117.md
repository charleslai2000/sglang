# G1-P0 production lifecycle qualification — 2026-11-17

## Current disposition

**NO-GO for enabling this E5M2 + HiCache configuration in production.** Do not treat C32 completion or an idle sanity PASS alone as acceptance. The requested critical L2/L3 restore lifecycle has not been proven on the real request path; host eviction/reclaim under capacity pressure was not observed in the two successful C32 runs. P0-A's historical invariant failure remains a correctness risk. P0-B has observed wait/timeout symptoms and is not closed by the existing runs.

## Runtime identity audit

- First failing manifest: Git/source manifest `d7e092a753d1746b00f76b38742161880ea78f34` (run root `20261115T-g1-prod-e5m2-hicache`). The manifest pins a source HEAD, not a runtime Python file digest or dirty overlay.
- Current investigation repository: `sglang-hicache`, branch `3090-24g-hicache`, Git HEAD `db185be2e334e44508d2ae1f458d021926ca9bf8`, no tracked dirty files. It contains trace/idle-reporting instrumentation added after the failure.
- Successful trace replays were attributed in the prior run notes to manifest HEAD `ccf60887c99bd2667850315a07f5e6a7d6ac8447`. Their HAE runtime record names the editable repo `/home/ubuntu/workspaces/3rdparty/sglang`, telemetry `SOURCE_HEAD=4f41f5bab562b99562f30c67540eb05344d13637`, and source-build digest `03750d8519fdae277a0d04938c53c73ff2d5400be8c6f9f51a3d2bc7b3338d07` for six producer files. This HEAD is pinned by a telemetry constant; the historical runtime checkout is dirty (137 paths at its source revision), and its recorded source digest does not match the current checkout's recomputed digest (`e1483ae69d854f1a7ef0531645987ef22ad36a79d024e6bf5f3b1615288cd893`). The prior `/tmp/sglang-f1-r16b-clean` runtime checkout is now absent. Therefore exact runtime bytes loaded by the successful process cannot be reconstructed from the current files.
- Important production changes after the original manifest revision include `7d4186945d` (per-anchor L3 durability version/no-material frontier fast-forward) and `22eddb20f0` (deferred-ACK reconciliation). Both alter HiCache production tree/controller behavior. Thus the failed-vs-successful runtime difference is **not diagnostics-only**. The original failed run's uncommitted runtime overlay is also unavailable; no exact content-level failed/success diff is claimed.
- Do not attribute the two successes to the committed `db185be` checkout. The current `sglang` editable source has substantial unrelated and cache-related dirty state; it is not safe to overwrite or use as a clean reproducibility baseline.

## What the successful real C32 runs establish

Artifacts: `/data/sglang-hicache/gemma4/runs/20261116T-g1-p0-c32-trace-retry/c32-20261117T194046Z/` and `.../c32-20261117T195251Z/`.

- 32/32 responses; original fixture's 63,488 shared-prefix tokens and 32 distinct suffixes; E5M2, context 131072, max-running 32, 0.90 memory fraction, configured full Decode Graph max batch 32, Radix, 2-GiB HiCache, Extent/write-through.
- 5-second continuously scheduler-reported full idle with drained queues, actual production `on_idle()` `sanity_check()` PASS, and launcher cleanup exit 0.
- Second run's bounded lifecycle recorder contains 789 events: 67 backup commits and 131 structural TreeCore splits. No host-leaf eviction/reclaim or invariant violation was observed.
- Crucial request-source evidence from `c32/batch.json`: sampled C32 requests report `cached_tokens_details={device: 63488, host: 0, storage: 0}`. Their shared prefix was an L1 hit; this is not evidence of L2/L3 restore. Logs show many prefetch-budget waits and miss/recompute dispositions. `restore_backup` records are L3 durability publications/writes, not L3→GPU reads. No successful request-source storage restore was recorded. Aggregate C32 does not itself establish a simultaneously active bs32 decode-graph batch.

## Capability and risk ledger

| Capability | Evidence/status |
|---|---|
| Real shared-prefix C32 split/insert/backup and ordinary completion | Exercised twice; 32/32 both |
| Production scheduler full-idle sanity after C32 | PASS twice, explicitly marked |
| Host capacity pressure causing normal eviction/reclaim | **NOT EXERCISED** by the traced C32; no `host_leaf_evict` event |
| L2 Host-source request restore | **NOT PROVEN**; C32 per-request host source count is zero |
| L3 storage-source request restore into GPU | **NOT PROVEN**; storage source count zero, only durability/write events observed |
| Decode continuing after a true L2/L3 restore | **NOT PROVEN** |
| Frontier wait/wake/timeout recovery under the same lifecycle | **NOT PROVEN**; earlier logs have FRONTIER waits/timeouts without a complete waiter-resolution ledger; successful run logs also show PREFETCH_BUDGET WAIT, not proof of Frontier wake recovery |
| Historical parent-prefix invariant bug P0-A | Historical fail is real (11 violations); two later runs did not reproduce; production runtime differed and first-failure trace unavailable. **Unresolved risk** |
| E5M2 numerical acceptance | Separate task; this report makes no new numerical claim |

## Decision

Do not deploy the tested E5M2+HiCache candidate. The preserved historical correctness failure is sufficient for NO-GO, and requested Host/L2/L3 restore-and-decode gates are still absent. No production state/protocol fix is justified by present trace evidence. Do not widen scope into more identical C32 retries: a next acceptance attempt must first use a frozen, identity-verified runtime artifact and explicitly drive Host capacity beyond its available tier, then prove request-source Host restore, storage restore, restore→decode, waiter resolution, and final C32 idle sanity in one auditable run. If runtime source identity/dirty overlay cannot be frozen safely, that is a concrete qualification blocker, not a reason to call the current evidence a pass.

GPU/port final check on this analysis session: GPU 0% / 1 MiB, no compute process listed; port 31401 closed. Lock file was preserved (never forcibly cleared).