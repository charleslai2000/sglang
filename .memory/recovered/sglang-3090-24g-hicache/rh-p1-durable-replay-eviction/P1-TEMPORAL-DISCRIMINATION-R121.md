# P1 temporal discrimination computed from the R121 frozen bundle

Status: **DECISIVE FINDING** (orchestrator, read-only re-analysis of frozen data).
Evidence source: `work/R121-bundle/raw.log` (sha256 `2bdca1c2…cca9`), the closest
run — which DID exhibit T's park + release + wake (C1–C3 real). R123 could not
reproduce T's park at all, so it yields no temporal data; R121 does.

## Frozen criterion (R123 contract, sha256 bf7b09ee…1e1f8)

`t_feasible` := first moment on the L2 host pool where, for every blocked domain,
`free + evictable >= required`. If `t_feasible < t_deadline` yet T is held
because a blocked domain's generation did not change -> **PRODUCT LIVENESS FAIL**.

## Exact timeline (R121, rid `r121-p3-R-T`, D_req = 27328, mamba required = 1)

All values from `host_alloc.v1` events (line = raw.log line, ts = ts_mono_ns):

| ln | ts_mono_ns | event | free kv | evict kv | allocable kv | mamba free/req | kv gen | mamba gen | decision |
|---|---|---|---|---|---|---|---|---|---|
| 125841 | 13395611610795 | wait:26 park | 98 | 6080 | 6178 | 42 / 1 | 1227 | 1850 | parked |
| 125842 | 13395612092670 | wake | 98 | 6080 | 6178 | 42 / 1 | 1227 | 1850 | hold_no_generation |
| 179143 | 13417555418851 | wake | 2144 | 4094 | 6238 | 64 / 1 | 1228 | 1851 | **grant** |
| 224763 | 13439589595944 | retry | 2144 | 0 | free_after 24670 | 63 / 1 | 1229 | 1853 | revoked_alloc_failed (24670 < 27328) |
| 224765 | 13439590172510 | wait:27 park | 24670 | 0 | 24670 | 75 / 1 | 1229 | 1853 | parked |
| 224766 | 13439590529133 | wake | 24670 | 0 | 24670 | 75 / 1 | 1229 | 1853 | hold_no_generation |
| **270076** | **13455350325983** | wake | **24672** | **42942** | **67614 ≥ 27328** | **75 / 1 (satisfiable)** | **1230** | **1853** | **hold_no_generation** |
| 270211 | 13455611599850 | release | — | — | — | — | — | — | terminal_reason=`restore_event:TIMEOUT` |
| (270213) | — | `[P2A] restore_recompute rid=…-T cause=timeout` | | | | | | | |

## Computed temporal discrimination

```text
D_req (durable boundary)        = 27328
t_feasible                      = 13455350325983   (ln270076; kv 24672+42942=67614>=27328,
t_wake (held)                   = 13455350325983   (same instant, decision=hold_no_generation)
t_deadline                      = 13455611392193   (wait:26/27 deadline_mono_ns)
t_deadline - t_feasible         = 261,066,210 ns ~= 261 ms   (t_feasible < t_deadline)
T wait duration (park->timeout) = 13455611392193 - 13439590172510 = 16.02 s
generation advance at t_feasible: kv 1229->1230 (yes), mamba 1853->1853 (NO)
blocked_domains                 = [kv, mamba]
```

Underlying release of the capacity: `raw.log:270071` (`host_allocability_change`,
causal_rid `r121-p3-R-F1`, kv `evictable_after=42942`, ts `13455349291603`) — F1's
42942 host pages became reclaimable then.

## Verdict against the frozen rule

`t_feasible < t_deadline` AND T was held with `decision=hold_no_generation`
because the **mamba** generation did not advance (1853->1853) while **kv**
advanced (1229->1230) — even though mamba's requirement was already satisfiable
(free 75 >= required 1). Per the frozen rule this is:

> **PRODUCT LIVENESS FAIL** — `_host_alloc_wait_eligible`'s blocked-domain
> semantics starve a restore that is capacity-feasible.

Root cause (source, already recorded in
`work/P1-HOST-ALLOC-WAKE-ELIGIBILITY-SOURCE-NOTE.md`):
`_host_alloc_wait_eligible` (scheduler.py:3716-3727) requires ALL
`blocked_domains` generations to advance; a generation advances only when that
pool's host evictable signature changes (`_bump_changed_host_allocability`,
unified_radix_cache.py:3823-3835). mamba was never a real constraint
(free 75 >= 1) yet was admitted into `blocked_domains` at
unified_radix_cache.py:6503-6519 because its sidecar hit was incomplete
(`sidecar_hit_pages.mamba = 0`). A non-constraining blocked domain whose
evictable set never changes can therefore block the wake indefinitely.

## Secondary finding (co-occurring, not the same defect)

`t_feasible` arrived only ~261 ms before `t_deadline` because F1 held its 42942
host pages until it completed, which coincided with T's deadline. So the
workload's headroom timing is tight; fixing the wake defect is necessary for
liveness but the workload must also give a window wide enough for the transfer.
Both facts are recorded so the fix is not mis-scoped as "workload only".

## Why R123 adds no temporal data

R123 (`work/R123-bundle/`) did not park T: T was prefilled directly
(`#cached-token: 0`), zero SPEC_BUDGET events, and Gate A was 1581 vs 43072.
Its verdict NOT_VERIFIED is a harness defect (donor preprocessing self-defeating;
fail-fast precondition not enforced). It neither confirms nor refutes the
finding above; R121 does.
