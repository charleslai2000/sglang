# R120 P1 SPEC_BUDGET full-chain — per-condition evidence

Task `P1-SPEC-BUDGET-FULLCHAIN-20260911-R120`. Frozen acceptance
`R120-bundle/P1-ACCEPTANCE-CONDITIONS.md` sha256
`b5ffa106be7863a2baedd528249eb6bccb63469619af73970a4c477813c27822` (verified).
Server PID 48746 / scheduler 48806, health 200, read-only. All `raw.log:N`
refs are the frozen server-log slice (server line = raw line + 2051151);
`probe.log:N` refs are the frozen `/tmp/t38c-probe.log` slice beyond byte
`33890204`.

Workload actually run (one clean line, no decoys):
- F1 build `r120-p1-build-F1` session `r120-s-F1`, 43008 prompt tokens, unique
  first token (rare Unicode), HTTP 200 (13.955 s).
- T build `r120-p1-build-T` session `r120-s-T`, 27521 prompt tokens, unique
  first token, HTTP 200 (15.221 s).
- Replay: one input_ids batch `prompt=[[F1],[T]]`, `rid=[r120-p1-R-F1,
  r120-p1-R-T]`, session `r120-s-R` (a single scalar `session_id` is the only
  batch-level session the API accepts; see note below), HTTP 200 in 11.305 s.

Note on "distinct sessions": per-sub-request `session_id` is not expressible in
one `GenerateReqInput` batch (`io_struct.py:878` copies the scalar
`session_id` to every sub-request; `session_params` lists fail at
`tokenizer_manager.py:1369`). The run therefore used distinct **build**
sessions (`r120-s-F1` gen 39, `r120-s-T` gen 40) and one replay session
(`r120-s-R` gen 41). This is a harness/API limitation, reported, not a
product defect.

## C1 — T full durable coverage: **FAIL**

Requirement: `pc_storage_query.kv_hit_pages == requested_prefix`,
`storage_hit_count == requested_prefix`, `query_suffix_len >= requested_prefix`;
L3 objects exist; Mamba sidecar durable; session/gen/build_rid consistent;
storage-backed (not `durability_barrier`).

Observed field values:
- `probe.log:671` `evt=storage_persisted build_rid=r120-p1-build-T node_id=1313
  kv_completed_tokens=2046 kv_durable=true mamba_durable=true
  session_generation=40` — the ONLY T-build persistence record in the frozen
  window (2046 of 27521 tokens, ~7.4%; a later live re-check reached 3 nodes
  ~6142 tokens / 22.3%, still not full).
- `probe.log:315` `evt=pc_storage_query rid=r120-p1-build-T
  query_suffix_len=27520 kv_hit_pages=0 storage_hit_count=0` (the query ran at
  build admission, before the write, so 0 is expected there).
- `probe.log:583/584` `evt=pc_outcome rid=r120-p1-R-T outcome=attempt
  prefetch_length=0` then `outcome=declined_too_short` — no storage query was
  ever issued for the T replay.
- `raw.log:36547` `rh_match_prepare r120-p1-R-T fill_len=27521
  device_hit_tokens=27520 host_hit_tokens=0 session_generation=41`.
- No T park and no T finalize → session/gen/build_rid consistency across
  park/query/finalize is not demonstrated (park/query/finalize never happened).

Unmet: T was not fully L3-durable and `kv_hit_pages == requested_prefix` cannot
hold (no T storage query exists; the only T-build query returned 0). Frozen
coverage ≈ 2046/27521.

## C2 — T park uniquely SPEC_BUDGET: **FAIL**

Requirement: `spec_budget_used_tokens > speculative_budget_limit_tokens` on the
`spec_budget` epoch; host sufficient; reason is not HOST_ALLOC and not
DEVICE_QUOTA/other; candidate `staging_eligible=True restore_potential=True`.

Observed field values:
- `grep -c SPEC_BUDGET raw.log` = **0** over the entire frozen window.
- `raw.log:36553` `rh_preadmission_decision rid=r120-p1-R-T ... (721,1204,41,0,
  ('r120-p1-R-F1','r120-p1-R-T')),1204,0,65536,0,39321,0,'hold','state_funnel'
  ... staging_eligible=True restore_potential=True speculative_budget_used_tokens=0`
  → `spec_budget=0`, limit `39321`; no park, no negative-cache cursor.
- `raw.log:36554` `ready_stage r120-p1-R-T ... result=held
  reason=declined_too_short speculative_budget_used_tokens=0`.
- `raw.log:36547` T was already device-resident (`device_hit_tokens=27520`), so
  no speculative reservation was ever taken for T.
- Host at the replay instant: `raw.log:56235` `promotion_reserve rid=r120-p1-R-F1
  full_free=1114 full_evictable=27558 full_locked=36864`.

Unmet: there is no SPEC_BUDGET park and no `spec_budget_used > limit` for T.
The park reason is neither HOST_ALLOC nor DEVICE_QUOTA — because there is no
park at all (the target was resident and declined `too_short`).

## C3 — strict release → wake causality: **FAIL**

Requirement: F1 issue/reservation → T SPEC_BUDGET park → F1 exactly-once release
advancing the epoch by +1 → T wake/reissue attributable to that epoch.

Observed field values:
- `raw.log:36548` `prefetch_issued rid=r120-p1-R-F1 prefetch_length=2047`.
- `raw.log:36550` F1 `rh_preadmission decision=issue reason=issued`
  `speculative_budget_used_tokens=0` (pre-issue).
- `raw.log:36559` F1 at the next pass `spec_budget=2047
  speculative_budget_limit_tokens=39321 speculative_budget_used_tokens=2047
  decision=exclude reason=no_restore_potential` → the budget was never
  exhausted.
- `probe.log:583/584` T `prefetch_length=0` `declined_too_short`.
- `grep -c SPEC_BUDGET raw.log` = 0.

Unmet: no T park exists, so no release-epoch advance and no attributable wake
can exist. (The build-phase prefetches `build-F1`/`build-T` did exceed the limit
— 43007 and 27520 — but those are issuer builds, both revoked `full_miss`, and
neither was a T park.)

## C4 — full restore gate: **FAIL**

Requirement: `disposition==FULL`, `granted==requested`, `storage_hit==requested`,
`kv_fetched==requested`, Mamba `fetched==expected==1`,
`restore_success.n_tokens==requested`.

Observed field values:
- `raw.log:36552` `restore_disposition rid=r120-p1-R-T disposition=RECOMPUTE
  requested=0 granted=0 reason=too_short` → a FAIL class, not FULL.
- `raw.log:36554` `ready_stage r120-p1-R-T result=held
  reason=declined_too_short`.
- No `restore_hybrid_finalize`, no `restore_success`, no `ready_host` for
  `r120-p1-R-T` in the frozen window (absence checks run).
- For contrast the issuer `raw.log:56231` `restore_recompute rid=r120-p1-R-F1
  cause=miss final_storage_survivability=host` (issuer recompute, not T).

Unmet: T disposed as RECOMPUTE/too_short; none of the FULL-restore equalities
hold. The absence of an explicit `restore_recompute` event for T is not
sufficient (and the disposition itself is RECOMPUTE).

## C5 — host headroom proven sufficient before the run: **FAIL**

Requirement: `F1_required + T_required + margin < host_allocable`, with the
margin and basis stated; record free/evictable/locked at park and stage.

Observed field values:
- `requests.jsonl`: `F1_required=43008`, `T_required=27521`, sum `70529`.
- `raw.log:56235` `evt=promotion_reserve n=4096 rid=r120-p1-R-F1
  full_free=1114 full_evictable=27558 full_locked=36864 mamba_free=20
  mamba_evictable=31 mamba_locked=2` → measured allocable = 1114 + 27558 =
  **28672** tokens.
- `raw.log:56236` `evt=promotion_transfer n=4096 full_free=2010
  full_evictable=22566 full_locked=40960`.
- `raw.log:36550/36553` replay `headroom_tokens=1204`.

Unmet: on the measured live basis `host_allocable=28672 < F1+T=70529` (deficit
≈41857; margin ≥ 0 cannot be satisfied). The static logical pool (131073) would
only pass with margin < 60544 and is not the allocable quantity (36864 tokens
locked plus write-back working set). No park/stage occurred, so park/stage
headroom cannot be recorded at all. Basis: `host_allocable := full_free +
full_evictable` at the replay promotion instant.

## Verdict

**NOT_VERIFIED.** All five conditions are unmet. Primary decisive unmet
condition: **C2/C3 — no SPEC_BUDGET park** (T device-resident → declined
`too_short`; F1 replay prefetch 2047 « 39321 → budget never exhausted), with
**C1** (neither build fully L3-durable without eviction pressure) as the
upstream cause and **C5** (live host allocable 28672 < 70529) as an independent
environmental block.
