# P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R123 — verification report

- **Verdict: NOT_VERIFIED.** The frozen R123 chain was not exhibited on the single
  frozen bundle. The measurement window was opened and burned while the R121
  top-level precondition `HOST_HEADROOM_SUFFICIENT` (C5 / Gate A) was not met.
- Bundle: `work/R123-bundle/` (`raw.log`, `probe.log`, `chain.json`,
  `condition-evidence.md`, `manifest.json`, `sha256sums.txt`, `driver123.py`,
  `requests.jsonl`, `state.jsonl`).
- Server untouched (PID 48746 / scheduler 48806, port 30000). No restart, no
  profile/param change, no `/flush_cache`, no `/close_session`, no
  `python/sglang/` edits, no new instrumentation.

## What was run

R123 driver (`driver123.py`, R121-faithful decoy: F1 43107, F2 42930, T 27228,
5x ~43k pressure, plus a pre-window donor completion of F2 to seed evictable host
pages). Window `[R-F1, R-T]` submitted in one request, HTTP 200 in 74.409 s,
`prompt_tokens=70335` (=43107+27228). Window server window: `raw.log` = server
lines 3084733..3222416.

## Gate readings

- **Gate A / C5 (host headroom at window start): FAIL.**
  `raw.log:2340` = server 3087072, `restore_host_alloc_retry_result` (R-F1):
  kv `free_before=1581 free_after=1581 reclaimed=0 evictable=3968 required=43072`;
  `retry_outcome=revoked_alloc_failed`. Under gate v2
  (`host_allocable := free_after_reclaim`) allocable = **1581** vs required
  **43072** (short **41491**). Only window `host_allocability_change`
  (`raw.log:60`, server 3084792) is evictable 5888 -> 5888.
- **Gate B (wake): HELD-ONLY for the decoy F1.** `raw.log:2343` = server 3087075,
  `restore_host_alloc_wake_decision decision=hold_no_generation`,
  generations kv 1496 / mamba 2260 unchanged, blocked `[kv, mamba]`; release at
  deadline (`raw.log:137655`, server 3222387) then
  `restore_recompute cause=timeout` (`raw.log:137657`, server 3222389).

## Frozen-chain result

| leg | result |
|---|---|
| T FULL_DURABLE | EVIDENCED (probe: 14 barriers, all mamba+kv durable, completed before pressure) |
| Gate A | **FAIL** (above) |
| F1 issue | EVIDENCED (`raw.log:1`, prefetch_length 43106) |
| T SPEC_BUDGET park | **ABSENT** (0 SPEC_BUDGET events >= server 3084733; T never got a preadmission decision) |
| F1 revoke/release epoch+1 | epoch 114->115 occurs, but caused by F1 `alloc_failed`/HOST_ALLOC timeout release (`raw.log:2338`, `raw.log:2345`), not a spec-budget release with a waiter |
| T HOST_ALLOC retry | ABSENT (only decoy F1, `raw.log:2342`) |
| t_feasible / t_wake / t_deadline (T) | ABSENT / null — criterion not evaluable |
| FULL stage/restore kv_fetched==D_req | **ABSENT** (0 `restore_success`, 0 `restore_hybrid_finalize`; decoy recomputed) |
| Mamba restore -> generation | ABSENT (T generated via direct prefill) |

T was prefilled straight from the request body: `raw.log:12..61` shows
`#cached-token: 0` for a 27228-token train (13x2048 + 604), i.e. no L3 restore,
no park. This is why no T-side park/wake/feasibility exists.

## C1–C5

- C1 full durable coverage — NOT_EVALUABLE (no T park/query/finalize to join).
- C2 T park uniquely SPEC_BUDGET — **FAIL** (no T park).
- C3 release->wake causality — **FAIL** (T park and T wake absent; epoch +1 not a spec-budget release).
- C4 durable restore boundary — **FAIL** (no restore; durable-prefix recompute on the decoy).
- C5 host headroom sufficient at window start — **FAIL** (1581 << 43072).

## R123 temporal discrimination

Not decided. The frozen criterion `t_feasible < t_wake < t_deadline` (or the
`t_feasible < t_deadline` liveness branch) is **not evaluable**: T never entered
`restore_host_alloc_wait`. The nearest fact is that window host capacity
(free+evictable <= 1581+5888) never approached `D_req` 27228, so feasibility was
never reached — but calling this "capacity/timing shortfall" would still require a
T park, which did not occur. No PRODUCT LIVENESS FAIL is licensed by this run.

## Single decisive file:line

`work/R123-bundle/raw.log:2340` (server `sglang-server-r112.log:3087072`):
`restore_host_alloc_retry_result` R-F1 with `free_after_reclaim=1581`,
`reclaimed=0`, `required=43072` — the window started with host allocable two
orders of magnitude (26x) below the demand, so Gate A / C5 failed before the chain
could begin.

## Classification and open issues

- **Test/harness defect (not a product defect):**
  1. `driver123.py` Phase 4 opens the window without checking the R121 fail-fast
     precondition (`P1-R121-CONTROLLED-EVICTION-CONTRACT.md:10-18`); `DRAIN False`
     and `DONOR_DRAIN False` were ignored.
  2. The donor preprocessing is self-defeating: a host-alloc restore request
     cannot manufacture host-alloc headroom; it timed out and recomputed
     (server 2949888..3084691), adding pressure.
- **Open issues for the owner:**
  - Why did T bypass the restore path entirely (direct prefill, no
    `rh_preadmission_decision` for `r121-r123-R-T`) even though build-side durable
    coverage is complete? Resolve before any re-run; without a T park the R123
    temporal gate cannot be evaluated.
  - Can `HOST_HEADROOM_SUFFICIENT` be established at this profile without a
    product change? If not, the R123 frozen chain is not reachable and the
    contract's "capacity/timing shortfall" branch must be established by a design
    that actually parks T.
- **Remaining budget:** 1 of 2 live runs unused; not spent because the donor
  hypothesis is now falsified and no bounded harness fix is known to establish
  Gate A. Recommend a fresh dispatch (owner decision) before spending it.
