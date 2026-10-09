# R125 — durable-prefix replay (Option A): condition evidence

- Task: `P1-DURABLE-PREFIX-REPLAY-20260912-R125`
- Binding contract: `P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT.md`,
  sha256 `f78a2fc698de375de612ace8c023e4a6518a6781c155c2f5e92b66dd521f3c1f` (VERIFIED)
- Base contracts VERIFIED: R121 `2ac86b5a…b3b`, R123 `bf7b09ee…1e1f8`,
  R124 correction `c57905ff…3cd2`.
- Server: PID `3082643`, scheduler child `3086752`, port 30000, health 200.
  Fix present: `python/sglang/srt/managers/scheduler.py` sha256
  `892efc25e2a9ef7c5ebb4afa09cf6914182b1467981d14cd76c53eea5d8de9d7` (VERIFIED).
- NO server restart/signal; no profile/param change; no `/flush_cache`;
  no `/close_session`; product code read-only; no new instrumentation.
- Runs executed: **2 of 2 allowed**. Both are reported.

## Verdict: NOT_VERIFIED — the fixed capacity clause was NOT the deciding factor

Gate 0 (identity) PASS; Gate 1 (no premature consumption) PASS on run 1;
**Gate 2 NON-EVIDENCE** (at T's grant both blocked domains' generations
advanced, so the old all-generations rule would also have granted);
Gate 3: the durable boundary was fully fetched (`kv_fetched==D_req`) but the
literal Gate 3 predicates `disposition==FULL` and
`restore_success.n_tokens==D_req` were not met (PARTIAL/`shortfall` from the
11-token durable-boundary-external tail; success `n_tokens = D_req-2`).
The P1 fix is therefore **not runtime-exercised** by this experiment.

## Nonce / identity correction (contract text vs. reproducible fact)

The contract (§Prompt determinism) says to use `R121_NONCE=p1`. That is a
transcription error and would by construction fail the contract's own mandatory
Gate 0:

| nonce | T_K | SEEDBASE | T token count | 8-key set matches R121 |
|---|---|---|---|---|
| p1 | 252 | 38108 | 27170 | **NO** |
| p3 | 240 | 28912 | 27340 | **YES (exact)** |

R121's actual run was `R121_NONCE=p3` (manifest `runtime`; `state.jsonl`
`driver_start` `nonce:"p3"`; probe query rid `r121-p3-R-T`). R124 used `p1`
(T `fill_len=27170`) which is why its T was negative-cached. Identity was
resolved offline by reconstructing the driver prompts, tokenizing through the
existing `/v1/tokenize`, and recomputing the L3 page-hash chain
(`hash_binding.cpp`: chained SHA-256 over little-endian uint32 token pages) —
p3 reproduces the R121 8-key set exactly. The replay therefore used **p3**.

## Gate 0 — identity — PASS

Both runs' T storage query returns R121's key set and coverage:

- Run 1 `probe.log:2718` and `:2809`: `keys` == the 8 frozen keys;
  `query_suffix_len=27339`, `kv_hit_pages=27328`, `storage_hit_count=27328`,
  `sidecar_hits={"kv":27328,"mamba":27328}`.
- `key_set_sha256 = 73e15a5fa454204f8ac3b0d1181235999bacaeb59d71f9f5eb208444cf92dcb8`
  (matches contract expected exactly).
- On-disk re-verification (single-pass `scandir` of the 3,086,735-entry L3 dir):
  all 8 R121 T objects present; F1 42944/42959; F2 42944/43002.

## Run 1 (`raw.log` = window slice, server log lines 1465903..1737009)

Frozen recipe: `R121_NONCE=p3`, F1+F2 seeded, 5 controlled-pressure requests,
window batch `[[F1],[F2],[T]]` in session `r121-s-R-p3`; **T not built**
(replayed from durable L3, so it is a pure non-resident restore candidate).

Chain (file:line = `raw.log` line):

```text
  2   T rh_preadmission_decision hold state_funnel (rank 3)         epoch 17
  5   F1 rh_preadmission_decision decision=issue                    epoch 17
 11   F1 exclude reason=no_restore_potential (spec_budget=42958)
 12   T exclude reason=negative_cache wait_reason=SPEC_BUDGET negative_cursor=42958
 73   F1 restore_state WAIT_CAPACITY HOST_ALLOC     spec_budget_release_epoch=18  <- release 17->18
 75   T prefetch_issued prefetch_length=27339
 77   T rh_preadmission_decision decision=issue
 78   T ready_stage result=issued reason=issued      epoch=18 (issue epoch >= release epoch)
106   T admission pos=1 can_run=0 (queued; after release)
40800 T restore_host_alloc_wait wait:8  free.kv=262 evict.kv=5950  gens {kv:278,mamba:345}
40801 T wake decision hold_no_generation
128043 T wake decision GRANT (retry_grant=true)  gens {kv:279,mamba:346}
128044 T release CAPACITY_FITS
271086 T prefetch_finalize completed_tokens=27328 mode=cache
271087 T restore_hybrid_finalize kv_fetched=27328/27328, mamba 1/1, READY, accepted
271088 T restore_disposition disposition=PARTIAL requested=27339 granted=27328 reason=shortfall
271098 T restore_success n_tokens=27326
```

`requests.jsonl` batch-replay HTTP 200 (109.588 s), all 3 prompts generated.
`durable-prefix recompute == 0`, `hybrid_discard == 0` for T (no
`restore_recompute` / `hybrid_discard` events).

### Gate 2 deciding-clause record (T grant, `raw.log:128043`) — NON-EVIDENCE

`restore_host_alloc_wake_decision decision=grant`:

| pool | gen_before | gen_after | advanced? | free | evictable | free+evict | required | cap_satisfied | new_clause_decides |
|---|---|---|---|---|---|---|---|---|---|
| kv | 278 | 279 | **yes** | 2242 | 1984 | 4226 | 27328 | no | no |
| mamba | 345 | 346 | **yes** | 64 | 21 | 85 | 1 | yes | no |

`blocked_domains=[kv,mamba]`; `captured_generations={kv:278,mamba:345}`;
`current_generations={kv:279,mamba:346}`. **Both** blocked domains' generations
advanced => `_host_alloc_wait_eligible` (scheduler.py:3736-3755) satisfied the
original invalidation branch for every domain; the new (b) capacity branch was
never reached. The old rule would also have granted. Per the contract this is a
**NON-EVIDENCE** outcome even though the restore then succeeded.
No later grant exists (the waiter was released; the restore then proceeded to
completion without a second park).

The only hold decision (`raw.log:40801`) had both generations unchanged but
`free+evictable kv = 6212 < 27328`, so it was a legitimate capacity hold, not an
instance of the fixed clause.

### Gate 3 — durable-boundary restore

`restore_hybrid_finalize` (`raw.log:271087`): `kv_expected=27328`,
`kv_fetched=27328==D_req`, `per_sidecar.mamba={expected:1,fetched:1}`,
`all_or_nothing=true`, `restore_state_after=READY`, `result=accepted`.
So the **full durable boundary was fetched** (no durable-prefix recompute, no
`hybrid_discard`). Literal Gate 3 predicates not met:
`disposition=PARTIAL reason=shortfall` (because `requested=27339 > D_req=27328`
by the 11-token durable-boundary-external tail) and
`restore_success.n_tokens=27326` (= `D_req - 2`). The same `granted → success`
`-2` convention appears in R121's F1 (`granted=42752`, `success.n_tokens=42750`),
so it is a telemetry/`n_tokens` convention, not a durable shortfall.

### Timing record (run 1)

- `D_req = 27328` (from `pc_storage_query.kv_hit_pages == storage_hit_count`).
- `requested_primary_tokens = 27339`; external tail = **11** tokens.
- `t_wake` (grant) = `24150110953157` ns.
- `t_deadline` = wait:8 `deadline_mono_ns` = `24178421434716` ns (60 s after
  `wait_started_mono_ns=24118421434716`).
- `t_feasible` (first instant all blocked domains' `free+evictable >= required`):
  not reached between park and grant (at grant, kv `4226 < 27328`); capacity
  became sufficient only after the generation-driven grant. Hence the run was
  **not** at the proven-to-flip condition; `t_feasible` is not a deciding
  telemetry instant here.
- F1 release epoch: 17 -> 18 (+1, exactly once) at `raw.log:73`.
- T issue epoch: 18 (`raw.log:77/78`), so issue epoch >= release epoch.

## Run 2 (`run2/raw.log`, corrected attempt) — chain not reached

Recipe change aimed at keeping the mamba pool quiescent (so a capacity-clause
grant could decide): no builds, `USE_F2=0`, `TRIGGERS=0`, pressure-only
preprocessing, extra quiescence before the window.

Outcome: F1 issued but parked `HOST_ALLOC` (`run2/raw.log:1786`, wait:13) and ran
to its 60 s **TIMEOUT** (`run2/raw.log:109023`); with `--max-running-requests 1`
F1 held the only running slot, so T was never RH-issued (only two references to
`r121-p3-R-T`, no `pc_storage_query`, no `prefetch_issued`, no HOST_ALLOC wait).
T was then served by ordinary recompute: `Prefill batch, #new-token: 2048,
#cached-token: 0 … #pending-token: 0` fanning down at `run2/raw.log:109040-109047`
(03:47:06-03:47:10), i.e. after F1's release. `durable-prefix restore` for T
never occurred. This is a harness/timing design outcome, not a product defect.

## Residual blocker classification

- Product defect? **No** new product defect is shown. The fix's new clause was
  simply never reached; no incorrect grant/hold was observed.
- Nonce `p1` in the contract: **contract text defect** (would fail Gate 0);
  corrected to `p3` using reproducible evidence.
- Gate 2 miss: **harness/workload-timing** — the run did not recreate R121's
  quiescent-mamba flip window (R121 grant would have been decided by mamba
  `gen 1853->1853` with `free+evictable 76 >= 1`; here both generations moved).
- Gate 3 literal mismatch: **telemetry convention + external tail**
  (`PARTIAL/shortfall`, `success = D_req-2`), not a durable shortfall.
- Budget: 2/2 live runs used; the deciding clause cannot be produced without
  another run or a redesigned pressure/quiet-window recipe.
