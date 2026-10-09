ENTRY: ACCEPT

# DBG-20260909-RH-NO-STAGING — RTX3060 RH-ON causal diagnosis

```text
status: done
task_id: DBG3060-RH-NO-STAGING-20260909
orchestration_epoch: 20260909-rh-ab12
role: debugger-deep
scope: read-only local source, supplied reports, and read-only correlated RH-ON remote log inspection
```

## Conclusion

The RH-ON flags were parsed and the scheduler's RH pass did execute.  The
failure is not an HTTP/API path that bypasses the scheduler, nor does this
policy require a separate prediction signal.  Rather, the direct `/generate`
path eagerly calls the ordinary storage prefetch **before** the request enters
the waiting queue.  The RH maintenance pass runs only afterwards.  Under this
five-way burst, the requests therefore entered the RH pass already
`RESTORING` or `WAIT_CAPACITY/PREFETCH_BUDGET`; `RESTORING` is explicitly out
of the RH staging funnel, and the ordinary reconciliation path consumes
`PREFETCH_BUDGET` waits before the RH pass gets an effective speculative
opportunity.

The eventual `HOST_ALLOC` waits are a separate, confirmed physical
allocability failure.  The host-alloc epoch mechanism did run and emitted
request-correlated decisions.  It correctly did **not** wake y/q/w because
the required KV generation never advanced: each required 54,976 KV units,
had only 21,057 free KV units and zero evictable KV units.  Mamba-generation
increments alone cannot satisfy the all-required-domains wake predicate.

Thus, the absence of `RH eligibility`, `prediction`, and `ready_host` events
is mostly an instrumentation absence: those event names do not exist in the
reviewed scheduler source.  It does not prove non-execution.  `ready_stage`
is different: it has one source emission site, and the trace has one y event
only at 14:45:02, after all clients had reached their 180-s terminal bounds.
There is no evidence of a pre-deadline RH staging issue for any RID.  z did
become restore-ready through the ordinary eager-prefetch path, not RH.

No code change is required to fix a lost host-allocation wake.  A product
change is required only if the intended contract is that concurrent direct
HTTP arrivals receive *pre-admission RH staging* rather than eager ordinary
prefetch, or if the requested observability is an acceptance requirement.
That change is architectural/scheduling scope and requires a fresh Task ID
with the mandated Pattern Intake and, if its authority boundary changes, a
Novel Mechanism declaration.

## Confirmed timeline: z (one complete RID)

RID: `TEST20260909RHONBOUNDED_z_1788936092647977306_1788936092651529085`.

| Time (+08:00) | Observed record | Causal interpretation |
|---|---|---|
| 14:41:32 | `prefetch_issued prefetch_length=55000` | The eager call in `Scheduler._add_request_to_queue`, not RH: there is no accompanying `ready_stage`. |
| 14:41:32 | `restore_state=RESTORING` | It is excluded from RH staging candidates by `ReadyHorizonPolicy._state_funnel`. |
| 14:43:00 | `prefetch_io_done`; `restore_hybrid_finalize result=accepted kv_fetched=54976 mamba.fetched=1 restore_state_after=READY` | The L3 query/transfer completed and full hybrid material finalized. |
| 14:43:00 | `restore_success n_tokens=54976` | Admission consumed the ordinary restore. The HTTP 200 was observed at 88.201206 s with storage 54,976 and device/host 0/0. |

The absence of `ready_stage` for z is affirmative path evidence, not merely a
missing telemetry field: `_ready_horizon_pass` emits that record immediately
after every call it makes to `_prefetch_kvcache`.

## Other-RID causal evidence

- x: ordinary capacity retry issued at 14:41:32 and again at 14:43:00; the
  14:44:49 prefetch-I/O completion occurred after the client bound.  It has
  no pre-deadline RH-stage record.
- y: ordinary capacity retry attempt 3 issued at 14:43:00.  At 14:43:12 the
  allocator revoked its positive 54,976-token result: first and post-eviction
  KV allocation both failed.  It entered `WAIT_CAPACITY/HOST_ALLOC`.  It
  timed out to recompute at 14:45:02, after which the RH pass emitted the
  trace's sole `ready_stage result=issued state=RESTORING ready=0
  headroom=70209`; that cannot affect the terminal client outcome.
- q: ordinary capacity retry attempt 4 issued at 14:43:12; allocation failed
  at 14:43:41 and entered `HOST_ALLOC`.
- w: ordinary capacity retry attempt 5 issued at 14:43:41; allocation failed
  at 14:43:53 and entered `HOST_ALLOC`.

The supplied bounded trace independently establishes all five L3 queries as
KV+Mamba 54,976 hits.  Those query results establish storage availability;
they do not establish a feasible host allocation for all 54,976 KV units at
the later drain/restore point.

## Source-to-runtime chain

Line references below are the authorized local branch
`3060-12g-qwen35-4b`.  Runtime/source identity was not hash-pinned in this
dispatch; matching event schema and field names are corroboration, not a
substitute for a deploy hash.

1. `Scheduler._add_request_to_queue` calls `_prefetch_kvcache(req)` and only
   then appends to `waiting_queue` (`python/sglang/srt/managers/scheduler.py:4516-4524`).
   This is the decisive direct-request ordering.
2. Each prefill pass runs `check_hicache_events`, then
   `_reconcile_restore_states`, then `_ready_horizon_pass`
   (`scheduler.py:5022-5028`).  RH cannot observe a newly queued direct
   request in `NONE` before the eager call above changes its restore state.
3. RH itself uses only the first `frontier_n` waiting requests and builds a
   view with `staging_eligible=_restore_potential_for(req)`
   (`scheduler.py:3804-3828`, `3943-3972`).  Its potential predicate is
   material/anchor/suffix based, not prediction/API based
   (`scheduler.py:4283-4292`; `unified_radix_cache.py:6009-6046`).
4. The funnel admits `NONE`/`MISS_RECOMPUTE` candidates with potential and a
   narrow subset of `WAIT_CAPACITY`; it explicitly rejects `RESTORING`,
   `HOST_ALLOC`, `FRONTIER`, and `REVALIDATE` (`ready_horizon.py:409-432`).
   This explains why a direct prefetch already in flight is not re-staged.
5. RH executes a stage only from `plan.to_issue` and emits the sole available
   stage marker, `[P3] evt=ready_stage`, immediately afterwards
   (`scheduler.py:3848-3899`, especially `3865-3879`).  Source search found
   no `evt=rh_eligible`, `evt=rh_prediction`, or `evt=ready_host` emitter.
6. Initial/eager calls are speculative (`demand_restore=False`).  With RH
   enabled, they are subject to both physical and speculative prefetch budget
   checks (`unified_radix_cache.py:5205-5220`).  A later ordinary capacity
   retry is made as `demand_restore=True` under RH
   (`scheduler.py:3585-3605`), so it bypasses only the speculative sub-budget,
   not host allocation.
7. A positive storage hit is allocated at drain time.  For a demand restore,
   the authoritative path is `alloc(full) -> evict_host(full) -> alloc(full)`;
   failure revokes it as `alloc_failed` (`unified_radix_cache.py:6494-6548`).
   That matches y/q/w's failure records and preserves the positive L3 hit as
   `DENIED_ALLOC`, not a storage miss (`scheduler.py:3618-3627`).

## Host-allocation epoch finding

The remote HAE records are sufficient to test the wake hypothesis directly.

| RID | failure snapshot | subsequent decision | result |
|---|---|---|---|
| y | KV required 54,976; KV free 21,057; KV evictable 0; required domains `kv,mamba`; generations `kv=0,mamba=1` | Later snapshots reached mamba 2 then 3 but KV remained 0 | `hold_no_generation` / `hold_budget`; no retry grant |
| q | same KV requirement/free/evictable facts; captured `kv=0,mamba=2` | later mamba 3, KV 0 | `hold_no_generation` |
| w | same KV requirement/free/evictable facts; captured `kv=0,mamba=3` | no qualifying KV generation before timeout | `hold_no_generation` |

The required predicate is intentionally conjunctive:
`current.generation_by_pool[pool] > captured...` for **every** failed domain
(`scheduler.py:3217-3228`).  FIFO selection invokes that predicate before it
can grant a retry (`scheduler.py:3336-3365`, `3459-3572`).  The `HOST_ALLOC`
predicate then lets an already-granted retry reach the authoritative allocator
without requiring the full span to be currently free
(`scheduler.py:4136-4171`).

Therefore hypothesis 5 is rejected as stated.  The epoch machinery does not
lose these waiters; it holds them because no relevant KV allocability change
occurred.  The report cannot prove why no KV release/evictability transition
occurred; the remote HAE snapshots do prove that none was exposed as a
generation advance before the observed decisions.

## Ranked hypotheses

1. **Confirmed: direct eager prefetch starves/bypasses the intended
   pre-admission RH opportunity.**  The scheduler is reached, but the
   HTTP-to-queue ordering makes RH observe non-`NONE` states.  This explains
   no pre-deadline `ready_stage` and no RH-ready-before-admission outcome.
2. **Confirmed co-cause: ordinary prefetch pressure and real host capacity
   shortage.**  The RH speculative fraction supplies the initial
   `PREFETCH_BUDGET` pressure; later demand retries reach full allocation and
   fail at 21,057 free versus 54,976 required KV units.  `max_running=1`
   can prolong queue/admission occupancy, but it does not gate invocation of
   `_ready_horizon_pass`, which runs before `PrefillAdder` construction.
3. **Partially confirmed: telemetry is insufficient for eligibility,
   prediction, and ready-host rates.**  Those emitters do not exist.  It is
   not sufficient, however, to explain away the absent pre-deadline staging:
   `ready_stage` exists and is only observed after the client deadline.
4. **Rejected: a prediction signal is required by direct HTTP.**  The RH
   candidate policy has no prediction predicate; it uses frontier, state,
   restore potential, causal epochs, headroom, and budget.
5. **Rejected: flags parsed but scheduler/RH path not reached.**  Parsed
   restart arguments show RH enabled; y's source-unique `ready_stage` proves
   a live RH pass.  The distinction is reached-too-late/with-ineligible
   state, not unreached.
6. **Rejected: host-allocation epoch changes failed to wake waiters.**  No
   relevant KV generation change occurred.  Auxiliary-only generation changes
   correctly fail the hybrid all-domain condition.

## Minimal follow-up scope and test oracle

No narrowly safe code patch follows from this diagnosis alone.  There are two
independent follow-up choices, both requiring fresh Task IDs.

1. **Observability-only task (minimal if product behavior is accepted):** add
   bounded, request-correlated RH decision records for: frontier inclusion,
   input state/wait reason, restore-potential result, negative-cache decision,
   headroom/reserve/budget values, issue kind (ordinary/speculative/demand),
   and a `ready_host` transition joined to the existing restore-finalize and
   admission events.  This lets a test compute the requested rate rather than
   treating absent fields as zero.
2. **Scheduling-contract task (required if the intended behavior is true
   staging before admission for direct concurrent HTTP):** decide whether to
   defer/remove eager `_prefetch_kvcache` from `_add_request_to_queue`, or
   explicitly classify that eager operation as the RH stage with equivalent
   reservations/causal negative cache.  Do not simply call both paths: that
   would duplicate I/O/reservations.  This changes the scheduler/authority
   boundary and needs Pattern Intake; it may need a Novel Mechanism
   declaration.

Follow-up deterministic oracle:

- With five direct `/generate`-equivalent enqueues, RH enabled, frontier 8,
  and a fake L3 KV+Mamba 54,976 hit, assert the chosen pre-admission policy
  produces exactly one request-correlated stage decision **before** ordinary
  admission for each eligible frontier candidate; `RESTORING` candidates must
  never receive a duplicate issue.
- Assert every stage decision records its exclusion reason (state funnel,
  negative cache, headroom/reserve, or physical/speculative budget) and that
  the ready marker joins to finalize and admission.
- Reuse the 54,976/21,057/zero-evictable hybrid fixture: auxiliary-only epoch
  changes must not wake it; a later KV generation advance may grant one FIFO
  retry, which must use full allocation/eviction and return to a cursor on
  failure without spinning.

## Missing evidence / limits

- There is no deploy hash proving the reviewed local source is byte-identical
  to the RH-ON process.  Event names and HAE schema match; this is strong but
  not cryptographic identity evidence.
- No initial-pass RH decision record supplies the actual candidate list,
  headroom, reserve floor, negative-cache state, or budget value.  We cannot
  quantify how much each gate contributed before the requests became
  ineligible.
- No runtime record identifies the holder responsible for absent KV release or
  why KV evictability stayed zero.  The report does not infer an unlock,
  allocator, or storage fault that was not observed.
- The client deadline occurred before y's only RH issue and before x's final
  I/O completion; later cleanup/staging cannot be counted as client success.

## Artifacts, evidence, followups, open issues

Artifacts/evidence:

- `TEST-20260909-RH-ON-BOUNDED-TRACE.md` and RH-OFF comparison baseline.
- `OPS-20260909-RH-ON-RESTART.md` (parsed flags and healthy launch).
- Read-only extracts from `/tmp/sglang3060-rh-on-restart-20260909.log`,
  including P2A and `host_alloc.v1` HAE records for all five RIDs.
- Local source symbols and exact line references listed above.

Summary: RH was enabled and reached, but direct request enqueue eagerly
prefetched before RH could stage queue candidates.  The one observed RH stage
was after terminal client timeouts.  Positive L3 hits subsequently failed on
real KV host allocability; the epoch wake correctly remained parked because
KV did not advance.

Followups: fresh observability task or fresh scheduling-contract task, as
selected by the owner; use the test oracle above.  No implementation or
remote experiment was performed in this task.

Open issues: source-to-runtime hash identity, initial RH decision telemetry,
and the cause of no KV allocability advance remain unproven.

```text
status: done
artifacts: DBG-20260909-RH-NO-STAGING.md; correlated remote P2A/HAE log extracts
evidence: source-order trace; five-RID bounded trace; source-unique late ready_stage; host_alloc.v1 generation/free/evictable snapshots
summary: RH reached but direct eager prefetch removes pre-admission staging opportunity; HOST_ALLOC waits correctly held for no KV generation advance
followups: fresh observability or scheduling-contract Task ID; no code change required for lost-wake theory
open_issues: deploy hash identity; missing initial RH decision records; absent KV release/evictability cause
```
