# R123 condition evidence — P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R123

- Verdict: **NOT_VERIFIED** (frozen chain not exhibited on this bundle).
- Bundle: `work/R123-bundle/` (this directory). Window server-log slice in `raw.log`
  (server lines 3084733..3222416, 137684 lines, sha256 in `sha256sums.txt`).
- Bindings: R121 contract `2ac86b5a...`, R122 addendum `92ad1c29...`, v2 correction
  `cbd1cf57...`, R123 temporal contract `P1-R123-TEMPORAL-WAKE-GATE-CONTRACT.md`.
- Gate basis: v2 (`host_allocable := free_after_reclaim`; L2 `mem_pool_host` via
  `host_alloc.v1`). v1 device-pool gate invalidated.
- Read-only w.r.t. server/product; server PID 48746 not restarted; no profile change;
  no `/flush_cache`; no `/close_session`; no `python/sglang/` edits.

Line references are physical lines: `raw.log:<n>` and `sglang-server-r112.log:<n>`
(`server n = 3084733 + raw.log n - 1`).

## Window summary

| field | value | source |
|---|---|---|
| HTTP | 200 (74.409 s) | `requests.jsonl` batch-replay |
| prompt_tokens | 70335 = 43107 (F1) + 27228 (T) | `requests.jsonl` |
| choices | idx0 "v" (F1), idx1 "q" (T) | `requests.jsonl` |
| restore_success | 0 | full log >= 3084733 |
| restore_hybrid_finalize | 0 | full log >= 3084733 |
| SPEC_BUDGET | 0 | full log >= 3084733 (last is R121 @ 2416600) |
| restore_recompute | 1 (rid=R-F1, cause=timeout) | `raw.log:137657` / server 3222389 |

## The decisive observation (headroom / Gate A)

`raw.log:2340` / `sglang-server-r112.log:3087072`
`restore_host_alloc_retry_result` for the decoy F1:

```
kv:    free_before=1581 free_after=1581 reclaimed=0 evictable_before=3968 evictable_after=3968 required=43072
mamba: free_before=42   free_after=43   reclaimed=0 evictable_before=32   evictable_after=32   required=1
retry_outcome = revoked_alloc_failed   (kv alloc1=False alloc2=False)
```

`free_after_reclaim` = **1581** vs required **43072** → `host_allocable` short by
**41491**. The only window `host_allocability_change` is `raw.log:60` / server
3084792 (kv evictable 5888 -> 5888; kv generation 1486 -> 1487). No window host
state reaches `D_req` for either identity. The measured window therefore started
with **Gate A unsatisfied**, in violation of the R121 top-level invariant
(`P1-R121-CONTROLLED-EVICTION-CONTRACT.md:10-18`), which requires STOP rather than
burning the window.

The pre-window donor did not change this: `restore_host_alloc_retry_result`
server 2949888 shows kv `free_after_reclaim=418 reclaimed=0 evictable 3776
required 42880`, `WAKE_HOLD hold_no_generation`, then HOST_ALLOC_RELEASE +
`restore_recompute cause=timeout` (server 3084689/3084691, 01:19:21). The donor
timed out and recomputed, i.e. it added host pressure instead of creating
evictable headroom.

## Frozen chain legs (R123 temporal contract lines 24-38)

| leg | status | evidence |
|---|---|---|
| T FULL_DURABLE(D_req) | EVIDENCED | `probe.log`: T build session `r121-s-T-r123` 14x `durability_barrier` + 14x `storage_persisted`, all `mamba_durable=true kv_durable=true`; last barrier ts_ms=1789146733401 |
| T NOT_DEVICE_RESIDENT | PARTIAL (no explicit probe) | T window sequence prefilled with `#cached-token: 0` (`raw.log:12..61`) |
| Gate A host allocable >= F1_D_req+margin | **FAIL** | `raw.log:2340` free_after_reclaim 1581 << 43072 |
| F1 issue | EVIDENCED | `raw.log:1` / server 3084733 `prefetch_issued prefetch_length=43106` |
| T SPEC_BUDGET park (unique cause) | **ABSENT** | no SPEC_BUDGET in window; no `rh_preadmission_decision` for `r121-r123-R-T`; T only at `raw.log:6` admission pos=1 can_run=0 |
| F1 revoke/release spec_budget_release_epoch +1 | PARTIAL / WRONG CAUSE | `raw.log:2338` prefetch_revoke `miss_reason=alloc_failed`; epoch 114 (`raw.log:1692`) -> 115 (`raw.log:2345`) bumps at F1's HOST_ALLOC timeout release, not a spec-budget release; no waiter |
| HOST_ALLOC retry (T) | ABSENT (F1 only) | `raw.log:2342` wait rid=R-F1 blocked=[kv,mamba]; no wait for R-T |
| t_feasible | ABSENT | never reached; see above |
| wake eligibility | HELD-ONLY | `raw.log:2343` `hold_no_generation` gen kv1496/mamba2260 |
| FULL stage/restore kv_fetched==D_req | ABSENT | 0 `restore_success`, 0 `restore_hybrid_finalize`; `raw.log:137657` `restore_recompute cause=timeout` |
| Host-ready -> admission -> Mamba restore -> generation | ABSENT | T generated via direct prefill, not restore |

## T bypassed the restore path (per-target detail)

The window request `prompt=[[F1],[T]]` resolves to two sequences. T's sequence ran
FIRST and was prefilled straight from the request body:

```
raw.log:12  pending-token 68287 (= 70335-2048)
raw.log:58  pending-token 43711
raw.log:61  new-token 604, pending-token 43107   -> T consumed 13x2048+604 = 27228 tokens, #cached-token 0
```

Only F1 remained pending (43107); its restore was attempted and failed allocation,
parked 60 s, and was recomputed (`raw.log:137659..137680`, 43107 tokens). No
`prefetch_issued`/`restore_state`/`restore_host_alloc_wait` exists for
`rid=r121-r123-R-T` anywhere in the window. Hence no T park, no T wake, no
t_feasible/t_wake/t_deadline for T.

## C1–C5 (R121 contract lines 73-97)

- **C1 full durable coverage** — NOT_EVALUABLE. Build-side coverage is complete
  (14 barriers), but C1 joins park / storage query / finalize identities and T
  never parked or finalized.
- **C2 T park uniquely SPEC_BUDGET** — **FAIL**. No T park at all; no SPEC_BUDGET
  event in the window.
- **C3 strict release->wake causality** — **FAIL**. (1) F1 issue present; (2) T
  SPEC_BUDGET park absent; (3) epoch +1 exists but caused by F1's HOST_ALLOC
  timeout release; (4) T wake/reissue at the advanced epoch absent.
- **C4 durable restore boundary** — **FAIL**. No `restore_disposition=FULL`,
  no `restore_hybrid_finalize`, no `restore_success`; the decoy recomputed its
  durable prefix.
- **C5 host headroom sufficient at window start** — **FAIL**. `host_allocable`
  (`free_after_reclaim`) = 1581 vs required 43072; window opened anyway.

## R123 temporal criterion (R123 contract lines 40-63)

`t_feasible` (T) / `t_wake` (T) / `t_deadline` (T): all **null / not observed**.
The criterion is **not evaluable** for the target because T never entered
`restore_host_alloc_wait`. The nearest factual statement is that the window's host
pool never reached free+evictable >= 27228 (max observed kv free 1581 + evictable
5888), so host feasibility was never attained before any deadline — which would
fall in the "capacity/timing shortfall at this profile/workload" branch **only if**
T had actually parked, which it did not. Therefore the run does **not**
discriminate host-headroom timing vs multi-domain wake eligibility, and does not
license a PRODUCT LIVENESS FAIL call.

For the decoy F1 (not the target): park mono 16434287970098, deadline
16494287880946 (+60.0 s), wake hold at 16434288335661 (`hold_no_generation`),
release 16494288137965 (deadline +0.26 ms), generations kv 1496->1496 / mamba
2260->2260, `free_after_reclaim` 1581 / reclaimed 0 / required 43072.

## Safety / identity continuity

HTTP 200, `prompt_tokens=70335` covers both identities, server PID 48746 alive,
no `/flush_cache`, no `/close_session`, no product edits, no new instrumentation.
Server was never restarted; no profile/launch parameter changed.

## Classification

- **Product defect**: not established by this run.
- **Test/harness defect**: YES — (a) `driver123.py` executes Phase 4 without a
  Gate A / drain precondition check, violating the R121 fail-fast invariant;
  (b) `wait_idle` returned `DRAIN False` / `DONOR_DRAIN False` yet the window
  proceeded; (c) the donor preprocessing step is self-defeating (a host-alloc
  restore cannot be used to create host-alloc headroom).
- **Missing evidence**: T-side park/wake/feasibility never occurred, so the R123
  temporal discrimination cannot be made from this bundle.
