# P1 durable-prefix replay — R126 tester report (replication)

## Status: BLOCKED — P1 gate NOT_VERIFIED (Gate 2 NON-EVIDENCE on all 3 replays)

Three faithful R121-p3 replays were executed against the running rebuilt server.
All three reached the FULL live chain (`non-resident T -> HOST_ALLOC park ->
F1 release+1 -> RH issue -> HOST_ALLOC grant -> kv_fetched==D_req`), and **Gates
0, 1 and 3 hold on every run**. **Gate 2 is NON-EVIDENCE on all three runs**: at
T's `restore_host_alloc_wake_decision decision=grant`, **both** blocked domains'
generations had advanced, so the original generation/invalidation branch would
also grant and the fix's NEW capacity clause was never the grant-deciding
condition. The new clause was consulted only at the intermediate *holds* (where
the kv domain still blocked), never at a grant.

This is the same race on mamba-generation quiescence that defeated R125 run 1.
The replication budget (3/3 replays) is now exhausted. No product defect is
implicated; the fix did not misbehave.

## Frozen contract + preflight verification

| item | expected | observed | verdict |
|---|---|---|---|
| R126 contract sha256 | `13ba59c06902d9e7cb2bc205ee7b9118776122e67f3eee107980ce8fdc1667b7` | identical | **VERIFIED** |
| `scheduler.py` sha256 (fix present) | `892efc25e2a9ef7c5ebb4afa09cf6914182b1467981d14cd76c53eea5d8de9d7` | identical | **YES** |
| `driver125.py` sha256 (run unchanged) | `a56ea3c83e1a42f0b08e17af6b9b6112f02f40590d90aed33105011b37efb7a9` | identical | **VERIFIED** |
| server port 30000 `/health` | 200 | 200 (pre-run and after each run) | **OK** |

No server restart/signal; no `/flush_cache`; no `/close_session`; public HTTP
only. HTTP used ≈ 15 requests/run (tokenize 1, builds 2, pressure 5, batch 1,
triggers ≤4), ≈ 45 total « 200.

## Disclosure: harness baseline offsets (deviation from the literal dispatch command)

`R125-bundle/baseline-offsets.txt` = `427088 66104950`, and R125 root's own
`driver_start` records `start_line=427088, probe_start_bytes=66104950`. The R125
reference run therefore set `R125_START_LINE` / `R125_PROBE_START_BYTES` to the
current server-log line count and probe-log size at launch. Those are harness
read offsets, **not** recipe/workload parameters.

The literal R126 command (only `R125_OUT` set) leaves both at `0`, so
`driver125.py::wait_durability` reads the **entire** accumulated probe history
from byte 0 through its `ByteTail` accumulate-then-`split` loop, which is
O(N²) in the file size. With the probe history at 74–76 MB this did not finish
in >10 min (measured); the first literal-command attempt was killed at the
25-min shell cap still inside the pressure phase (never reached the window), so
the contract's own `<=60 min` budget cannot be met that way. The aborted
artifacts are preserved in `work/R126-bundle/run1-aborted-timeout/`.

To execute the faithful recipe within the frozen budget I set, per run,
`R125_START_LINE` = current server-log line count and `R125_PROBE_START_BYTES`
= current probe-log size (saved as `run<N>/baseline-offsets.txt`). All recipe
parameters were left at the faithful defaults and **not** overridden:
`R125_NONCE=p3`, `R125_USE_F2=1`, `R125_TRIGGERS=4`, `R125_BUILD_T=0`,
`R125_PRESSURE_N=5`. No prompt, window, or workload parameter was changed.
This deviation is flagged for orchestrator review; it affects only read offsets
and run duration, not the measured chain.

Replay-series wall clock: run1 04:32:19→04:48:57 (16.6 min), run2
04:49:38→05:02:28 (12.8 min), run3 05:02:38→05:15:22 (12.7 min) = **42.1 min
≤ 60 min** for the 3 valid replays (the separate 25-min aborted literal attempt
is accounted above).

## Gate 0 — identity (PASS all runs)

Every run's T storage query reports the frozen R121 key set:
`key_set_sha256 = 73e15a5fa454204f8ac3b0d1181235999bacaeb59d71f9f5eb208444cf92dcb8`
(8 keys), `kv_hit_pages = 27328`, `storage_hit_count = 27328`,
`query_suffix_len = 27339`, `sidecar_hits = {kv:27328, mamba:27328}`.

| run | probe.log line | kv_hit_pages | key_set_sha256 | verdict |
|---|---|---|---|---|
| run1 | `probe.log:2803` | 27328 | `73e15a5f…dcb8` | PASS |
| run2 | `probe.log:1428` | 27328 | `73e15a5f…dcb8` | PASS |
| run3 | `probe.log:1416` | 27328 | `73e15a5f…dcb8` | PASS |

## Gate 1 — no premature consumption (PASS all runs)

`spec_budget_release_epoch` advances on F1's `rh_preadmission_decision` and T's
issue epoch is >= that value. No `admission`/`Prefill batch` for
`rid=r121-p3-R-T` occurs before the release-epoch event in any run.

| run | release-epoch event (F1) | T issue epoch | T admission/Prefill before release | verdict |
|---|---|---|---|---|
| run1 | `raw.log:73` (F1 epoch 38→39) | `raw.log:77`/`:78` epoch 39 | none | PASS |
| run2 | `raw.log:72` (F1 epoch 45→46) | `raw.log:76` epoch 46 | none | PASS |
| run3 | `raw.log:72` (F1 epoch 52→53) | `raw.log:76` epoch 53 | none | PASS |

Note: each run also carries an early `READY_HORIZON demand_restore=False`
speculative `prefetch_issued` for T (`run1:75`, `run2:74`, `run3:74`) which is
revoked `alloc_failed` and never consumes T; T's consuming (demand) prefetch is
issued after the grant and after the release epoch. No T `Prefill batch` occurs
before the release.

## Gate 2 — the fix's NEW clause is the deciding condition (NON-EVIDENCE all runs)

Per-domain record at T's grant (`restore_host_alloc_wake_decision decision=grant`).
`required`: kv = `requested_primary_tokens` = 27328; mamba = `required_aux_units.mamba` = 1.
`new_clause_decides = capacity_satisfied AND generation-unchanged`.

| run | decisive line | domain | gen_before→after | advanced? | free | evictable | free+evict | required | cap_satisfied | new_clause_decides |
|---|---|---|---|---|---|---|---|---|---|---|
| run1 | `raw.log:111254` | kv | 600→601 | yes | 2242 | 1984 | 4226 | 27328 | no | no |
| run1 | `raw.log:111254` | mamba | 685→686 | **yes** | 64 | 21 | 85 | 1 | yes | **no** |
| run2 | `raw.log:103986` | kv | 654→655 | yes | 2242 | 1984 | 4226 | 27328 | no | no |
| run2 | `raw.log:103986` | mamba | 743→744 | **yes** | 64 | 21 | 85 | 1 | yes | **no** |
| run3 | `raw.log:103404` | kv | 708→709 | yes | 2242 | 1984 | 4226 | 27328 | no | no |
| run3 | `raw.log:103404` | mamba | 801→802 | **yes** | 64 | 21 | 85 | 1 | yes | **no** |

Because **both** blocked domains advanced in every run, the original invalidation
branch (`scheduler.py:3736` generation rule) satisfied every domain; the new
capacity branch (`scheduler.py:3743-3754`) was never consulted for the grant.
The old rule would also grant ⇒ **NON-EVIDENCE**, not a PASS and not a FAIL.

The new clause *was* evaluated at the intermediate holds, where the mamba domain
was generation-unchanged and capacity-satisfiable but the kv domain still
blocked (`free+evictable kv = 6212 < 27328`):

| run | hold line | kv gen | kv free+evict | mamba gen | mamba free+evict | decision |
|---|---|---|---|---|---|---|
| run1 | `raw.log:17251` | 600→600 | 262+5950=6212 < 27328 | 685→685 | 42+43=85 ≥ 1 | `hold_no_generation` |
| run2 | `raw.log:13466` | 654→654 | 262+5950=6212 < 27328 | 743→743 | 42+43=85 ≥ 1 | `hold_no_generation` |
| run3 | `raw.log:10546` | 708→708 | 262+5950=6212 < 27328 | 801→801 | 42+43=85 ≥ 1 | `hold_no_generation` |

So mamba quiescence DID occur for the whole wait, but the grant only fired once
the kv generation advanced by one (and, at the same wake, the mamba generation
also advanced by one). This is the exact R125-run-1 race, reproduced
deterministically 3/3.

## Gate 3 — durable-boundary FULL restore (PASS all runs, corrected semantics)

`restore_hybrid_finalize` on the same boundary as T's grant:
`kv_expected = 27328`, `kv_fetched = 27328 == D_req`, `per_sidecar.mamba =
{expected:1, fetched:1}`, `all_or_nothing=true`, `restore_state_after=READY`,
`result=accepted`.

| run | finalize line | kv_fetched / D_req | mamba exp/fetched | disposition | restore_success.n_tokens | durable-recompute | hybrid_discard | HTTP | verdict |
|---|---|---|---|---|---|---|---|---|---|
| run1 | `raw.log:256281` | 27328 / 27328 | 1 / 1 | `PARTIAL requested=27339 granted=27328 reason=shortfall` (`raw.log:256282`) | 27326 (`raw.log:256292`) | 0 | 0 | 200 | PASS |
| run2 | `raw.log:227891` | 27328 / 27328 | 1 / 1 | `PARTIAL requested=27339 granted=27328 reason=shortfall` (`raw.log:227892`) | 27326 (`raw.log:227902`) | 0 | 0 | 200 | PASS |
| run3 | `raw.log:230196` | 27328 / 27328 | 1 / 1 | `PARTIAL requested=27339 granted=27328 reason=shortfall` (`raw.log:230197`) | 27326 (`raw.log:230207`) | 0 | 0 | 200 | PASS |

These met the corrected Gate 3 semantics frozen in the R126 contract: the
`PARTIAL reason=shortfall` is exactly the durable-boundary-external tail
`requested(27339) − D_req(27328) = 11`, and `n_tokens = granted − 2` is the
accepted `kv_fetched==D_req` telemetry convention. No durable-prefix recompute,
no `hybrid_discard`; HTTP call completes.

## Required record / timing

`D_req = 27328`; `requested_primary_tokens = 27339` (external tail 11). T is a
pure non-resident durable-restore candidate every run:
`device_hit_tokens=0`, `host_hit_tokens=0`, `fill_len=27340`
(run1 `raw.log:4`, run2 `raw.log:4`, run3 `raw.log:4`). Park:
`restore_state state=WAIT_CAPACITY reason=HOST_ALLOC` (run1 `raw.log:17249`,
run2 `raw.log:13464`, run3 `raw.log:10544`), preceded by
`restore_disposition WAIT reason=revoked:alloc_failed`.

| run | wait line | wait_started_mono_ns | t_wake (grant ts_mono_ns) | t_deadline (deadline_mono_ns) | t_feasible | t_feasible < t_deadline |
|---|---|---|---|---|---|---|
| run1 | `raw.log:17250` | 28661141759136 | 28693900688672 | 28721141759136 | ≈28693900688672 (kv gen-advanced; mamba cap-satisfiable throughout) | yes (+27.2 s) |
| run2 | `raw.log:13465` | 29478553462344 | 29510114057132 | 29538553462344 | ≈29510114057132 | yes (+28.4 s) |
| run3 | `raw.log:10545` | 30251863239809 | 30284893479418 | 30311863239809 | ≈30284893479418 | yes (+27.0 s) |

Caveat: `t_feasible` is the first instant the eligibility predicate holds; kv
reaches it only via the generation-advance branch (kv never becomes
capacity-satisfiable: `free+evictable=4226 < 27328`), so `t_feasible≈t_wake`.
`t_wake < t_deadline` holds in all runs.

## Exact missing transition (why no PASS)

Required for a PASS: at T's HOST_ALLOC grant, at least one blocked domain's
generation must be UNCHANGED while `free+evictable >= required`.
Observed: the mamba generation is unchanged through each entire wait (see the
holds), but at the grant wake the mamba generation advances by exactly +1
simultaneously with the kv generation (+1) — `raw.log:111254` / `:103986` /
`:103404`. Missing transition: a grant wake in which the mamba generation
remains quiescent (`gen_after == gen_before`, e.g. 685→685) while the kv domain
stops blocking, so the new `scheduler.py:3743-3754` capacity clause is the
deciding condition.

Single most decisive raw.log line per run:
- run1 `work/R126-bundle/run1/raw.log:111254`
- run2 `work/R126-bundle/run2/raw.log:103986`
- run3 `work/R126-bundle/run3/raw.log:103404`

## Verdict

**P1 NOT_VERIFIED.** All three replays reached the full durable-restore chain
with Gates 0/1/3 PASS, but Gate 2 was NON-EVIDENCE in every run (both blocked
domains' generations advanced at T's grant), so the HOST_ALLOC wake-liveness
fix's new capacity clause was never runtime-exercised as the deciding grant
condition. Replication budget (3/3) is exhausted. Classification:
harness/workload timing (a race on mamba-generation quiescence), not a product
defect; no product change is licensed.

## Artifacts

`work/R126-bundle/`: `run1/`, `run2/`, `run3/` (each with `raw.log`,
`probe.log`, `requests.jsonl`, `state.jsonl`, `driver.out`,
`baseline-offsets.txt`, `run-context.txt`, `watch.log`, `server-capture.log`,
`sha256sums.txt`), `run1-aborted-timeout/` (literal-command timeout, evidence
only), and `sha256sums.txt` (bundle-level). No R121–R125 artifact was modified.
