status: done

# P0-B-ORACLE-REFREEZE-20260911-R111 — re-freeze predicates 6 and 8

- Task ID: `P0-B-ORACLE-REFREEZE-20260911-R111`
- Invocation: `ses-p0b-oracle-refreeze-r111-20260911` (fresh)
- Role: `coder`
- Epoch: `2026-09-11`
- ENTRY: `ACCEPT`
- Repo: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
  (HEAD `4f41f5bab562b99562f30c67540eb05344d13637`, intentionally dirty).
- Boundary: oracle/reducer + tests + contract doc only. **No product source
  edit, no R107 edit, no commit/push, no children, no server/GPU action.**
- Authoritative inputs: R107 frozen package
  (`.memory/phase2-hicache-design/work/R107-reducer/`), R110 decision table
  (`P0-B-GAP-CLASSIFY-20260911-R110.md`), real captured bundle
  (`R109-bundle/raw.log`, `manifest.json`), and the product sources listed
  below.

## 1. Deliverable

New package `.memory/phase2-hicache-design/work/R111-reducer/` re-freezes the
canonical 11-predicate oracle, changing **only** predicate 6
(`generation_transition`) and predicate 8 (`attempt_lineage`), plus the
`negative_safety` `repeated_retry` scoping that depends on 8.  Exactly eleven
predicates remain with identical names and order.  The reducer is still
stdlib-only, imports no product code, synthesizes no product events, fails
closed, rejects bundle summary/verdict keys, and preserves raw `file:line`
references.  The R107 package is kept byte-identical as history.

## 2. Files and hashes (sha256)

R111 package (all new, untracked under the repo's untracked `.memory/`):

| file | sha256 |
|---|---|
| `R111-reducer/p0b_reducer.py` | `8d8547d92b9de49bfbbcbfff267afda66a54d32865c062e3cac85933f20e3067` |
| `R111-reducer/test_reducer.py` | `4715fec1573a2d067f421eafdfdbd9f0dd4e5f66ff96a9ffcf369487bd214488` |
| `R111-reducer/FREEZE-11-PREDICATES.md` | `e1da760b9c6cfa92994f9be8934a93e7801ce982101063a19a4d64a07d4c1874` |
| `R111-reducer/README.md` | `44e1081569359c0174b68eea6ea867cc00868a63151a3c7733cc33815c1e1d3b` |
| `R111-reducer/manifest.sha256` (covers the four above) | `373c01fe8bfe061b266fa7681477d6f27058be8a103afffd8cbb72bbe1d91390` |
| `R111-reducer/r109-rerun.out.json` (evidence) | `a1f7d3a29903ce97626998b18f4d233f46e54a8f3fd1915bc891d75b998f0e25` |
| `R111-reducer/test-r111.out.txt` (evidence) | `28df940921496f0b8229e638bfb1f765a180e95a42afb17135418adc861fbaca` |

R107 frozen inputs (verified **unchanged** against their `manifest.sha256`):

| file | sha256 |
|---|---|
| `R107-reducer/p0b_reducer.py` | `11de96819a75dc5b82d0ca1d230c3fef9aab3fb81ecee2f0ec903e0e154c4b08` |
| `R107-reducer/test_reducer.py` | `32b409e0b84222886baabd1a7d56c71ca2939d2866ba9b91405b54318b0599e6` |
| `R107-reducer/FREEZE-11-PREDICATES.md` | `f080886734e5a6b58b35286140697d48050438fda8d6211a02660d608efc19f5` |

Real bundle inputs:

| file | sha256 |
|---|---|
| `R109-bundle/raw.log` | `e96655c1e0dd5bff442ae9527e9ceaca433889e9aa975bb8ec403613f380c971` |
| `R109-bundle/manifest.json` | `618bd0420461e8fcea5c781987f9dc335a2c71f574fa8f4641062b06b8da3edb` |

Product sources (read-only; hashes equal the R109 manifest `source_files`, i.e.
untouched by this task): `scheduler.py`
`daf32da48b2d084976a19280b5b8eff2d232dfc1df2db9b2f4641a8f0ed9dd1d`,
`unified_radix_cache.py`
`5d3db1528638dd1c593b9cd62fc1b380d278cac4cc1b4e1319e6bf89c0ac375b`.

## 3. Change 1 — predicate 6 `generation_transition`

### 3.1 Why the R107 text was unsatisfiable

R107 required, per blocked pool, an **exact contiguous chain** of emitted
`host_allocability_change` edges from `captured` to `current`
(`generation_after == generation_before + 1`, next `before == previous
after`).

Product evidence:

* The generation counters are **complete** and monotonic; the counters are the
  authoritative signal.  `host_allocability_snapshot`
  (`unified_radix_cache.py:3838-3882`) returns
  `generation_by_pool` from `self._host_allocability_generations`, and
  `_bump_host_allocability` is the only writer
  (`unified_radix_cache.py:3748-3753`): every mutation increments the pool
  generation *before* the emit decision.
* Emission is **deliberately sampled** and bounded independently of the
  counters: HEAD 16 per telemetry key, then every 128th mutation, max 64 per
  key and 256 per cache instance
  (`unified_radix_cache.py:155-164`; gate at `3784-3793`; telemetry key
  `(pool, cause, causal_rid, trace_context)` at `3761`).
* Real R109 chain: deciding park `raw.log:1065` captured
  `{"kv":48,"mamba":89}`; deciding grant `raw.log:1131` carried
  `{"kv":49,"mamba":105}`.  The last emitted mamba edge was `48->49` at
  `raw.log:1012` — **zero** in-window mamba edges.  kv happened to have one
  in-window edge (`raw.log:1129`, `48->49`), which is why kv passed and mamba
  did not.  58 of 167 mutations were emitted, 109 suppressed (R110 §2.2).

So the R107 predicate demanded records the producer provably never emits in
general; it measured the sampler, not the generation transition.  It could
only pass when the deciding key had fewer than HEAD(16) mutations.

### 3.2 New text

The deciding park is the valid park whose `fifo_sequence` equals the deciding
grant's; the deciding grant is the unique grant whose `event_id` equals the
accepted finalization's `wake_event_id`.  The predicate now requires:

1. park and grant both present, both carry the **same int**
   `cache_instance_id`, and the park `ordinal` strictly precedes the grant
   `ordinal`;
2. for **every** blocked pool, `captured_generations[pool]` and
   `current_generations[pool]` are present ints and
   `current_generations[pool] > captured_generations[pool]` (strictly
   advanced);
3. sampled edges in `(park.ordinal, grant.ordinal]` for that pool are
   **corroborating, never required**: absence does not fail; each present edge
   must have the cursor `cache_instance_id`, `generation_after ==
   generation_before + 1`, and
   `captured <= generation_before < generation_after <= current`.

The predicate output records `sampled_edges_seen` (per blocked pool) and a
`sampling` fact string.  Fail-closed remains on: missing park/grant, missing
or non-int instance, park/grant instance mismatch, park not strictly before
grant, missing counter fields, non-advancing counters, or any contradictory
sampled edge.

### 3.3 Anti-forgery preserved

A forged chain still fails: raising `current_generations` without a real
advance is the pass condition (so a forgery must actually advance and still
must join to a captured grant via predicate 8); lowering counters fails
non-advance; a mismatched instance fails; and a present-but-wrong sampled edge
(wrong instance, non-`+1` step, below captured or above current) fails instead
of being ignored.  New adversarial tests prove each of these (see §5).

## 4. Change 2 — predicate 8 `attempt_lineage`

### 4.1 Why the R107 text was unsatisfiable

R107 required **exactly one** `restore_host_alloc_retry_result` with a
non-empty `attempt_id` and a `wake_event_id` naming a captured grant.

Product evidence:

* `restore_host_alloc_retry_result` is emitted **only on allocation failure**,
  at `unified_radix_cache.py:5460` (`forfeited_alloc_failed`) and
  `unified_radix_cache.py:6575-6598` (`revoked_alloc_failed`), both passing
  `attempt_id = operation.host_alloc_attempt_id`.  There is **no** retry_result
  on the successful post-wake path.
* Every HOST_ALLOC park is produced by `RestoreEvent.DENIED_ALLOC`
  (`scheduler.py:4329-4330,4353-4357,4369-4370`), whose failure object is
  recorded by the same two failure branches.  So every park is coupled with a
  **pre-wake** failure record.  `host_alloc_attempt_id` is first assigned only
  on the post-wake `RETRY_PREFETCH` (`scheduler.py:4250-4254`), so that
  pre-wake record always has `attempt_id=null` (real R109 `raw.log:1063`,
  `retry_grant=false`, `wake_event_id=null`).
* A post-wake failure emits a **second** retry_result with a non-empty
  host-alloc attempt id; success emits none.
* The successful attempt is recorded by the accepted `restore_hybrid_finalize`
  (`unified_radix_cache.py:5717-5737`) and by READY
  (`scheduler.py:4409-4457`).  Attempt namespaces genuinely differ:
  `_claim_prefetch` builds `f"{rid}:prefetch:{seq}"`
  (`scheduler.py:3130-3139`, READY path `4423-4424`) while the HOST_ALLOC retry
  builds `f"{rid}:{seq}"` (`scheduler.py:4251-4254`), carried by
  finalize/retry_result.

Therefore on a success-first-try chain the single retry is the pre-wake
failure (`attempt_id=null`) → R107 clauses 2 and 4 fail (the R109 reported
reason).  On a post-wake-failure chain the count becomes 2 → R107 clause 1 and
`negative_safety.repeated_retry` both fail.  The R107 canonical fixture also
omitted the mandatory pre-wake record, so the oracle model was not real-shaped
(R110 §2.4).

### 4.2 New text

The non-forgeable lineage join is the producer-emitted `wake_event_id`: the
single accepted finalization and the single target READY must **both** name
the same captured **deciding grant**, and their `attempt_id`s must be present
and namespace-valid (finalize/retry host-alloc `f"{rid}:{seq}"`; READY
prefetch `f"{rid}:prefetch:{seq}"`) but are **not** required to be equal
(different namespaces).  The predicate now requires:

1. **exactly one pre-wake retry** (`retry_grant` not true and empty/null
   `attempt_id`) with a recognized failure `retry_outcome`, no
   `wake_event_id`, and an `ordinal` strictly before the deciding grant;
2. **at most one post-wake retry** (`retry_grant=true` or non-empty
   `attempt_id`); when present it must carry a non-empty host-alloc-namespace
   `attempt_id`, a recognized `retry_outcome`, and a `wake_event_id` naming a
   captured grant whose `ordinal` strictly precedes the retry; if a later park
   exists it must preserve that `attempt_id`;
3. exactly one accepted finalization and exactly one READY, each with a
   namespace-valid `attempt_id`, and each with `wake_event_id ==
   deciding_grant.event_id`.

`negative_safety`'s `repeated_retry` now counts **post-wake** retries only
(the mandatory pre-wake failure is the park's cause, not a repeat).

### 4.3 Anti-forgery preserved

The deciding-grant join is enforced on both finalize and READY (a broken
propagation on either fails); a second post-wake retry fails predicate 8 and
`negative_safety`; a post-wake retry naming a non-captured ("bogus") grant or
a grant that does not precede it fails; a pre-wake record carrying a
`wake_event_id` or a missing/extra pre-wake record fails.  New adversarial
tests prove each (see §5).

### 4.4 Interpretation note (flagged as open issue)

The dispatch text says the post-wake retry's `wake_event_id` "names the
deciding grant".  For the real failure→re-park→re-wake shape the post-wake
retry names the grant that authorized that failed attempt, which precedes the
later deciding grant that leads to the accepted finalize (the R107 canonical
fixture is exactly this two-grant shape: retry names `E1`, finalize/READY name
`E2`).  The implementation therefore requires the post-wake retry to name a
captured grant that **strictly precedes it** (the authorizing wake) and
enforces the strict deciding-grant equality on the finalize/READY join.  This
is strictly stronger than the R107 requirement and fails any bogus/forward
reference; it is flagged in §7 for orchestrator/reviewer confirmation.

## 5. Test evidence

Command sequence (per dispatch):

```sh
source /mnt/data/neuron/envs/sglang-3090-opt/activate-sglang-3090.sh
python -m py_compile p0b_reducer.py test_reducer.py   # exit 0
python -m unittest test_reducer -v                    # exit 0
```

Full output (also saved at `R111-reducer/test-r111.out.txt`):

```
test_absent_park_fails_closed (test_reducer.AdversarialTests.test_absent_park_fails_closed) ... ok
test_absent_sampled_edges_still_verifies (test_reducer.AdversarialTests.test_absent_sampled_edges_still_verifies) ... ok
test_broken_attempt_lineage_fails_closed (test_reducer.AdversarialTests.test_broken_attempt_lineage_fails_closed) ... ok
test_contradictory_sampled_edge_fails_closed (test_reducer.AdversarialTests.test_contradictory_sampled_edge_fails_closed) ... ok
test_fabricated_predecessor_fails_closed (test_reducer.AdversarialTests.test_fabricated_predecessor_fails_closed) ... ok
test_finalize_broken_wake_event_id_fails_closed (test_reducer.AdversarialTests.test_finalize_broken_wake_event_id_fails_closed) ... ok
test_generation_not_advancing_fails_closed (test_reducer.AdversarialTests.test_generation_not_advancing_fails_closed) ... ok
test_generation_wrong_cache_instance_fails_closed (test_reducer.AdversarialTests.test_generation_wrong_cache_instance_fails_closed) ... ok
test_incomplete_finalization_fails_closed (test_reducer.AdversarialTests.test_incomplete_finalization_fails_closed) ... ok
test_missing_pid_profile_binding_fails_closed (test_reducer.AdversarialTests.test_missing_pid_profile_binding_fails_closed) ... ok
test_missing_pre_wake_retry_fails_closed (test_reducer.AdversarialTests.test_missing_pre_wake_retry_fails_closed) ... ok
test_non_contiguous_generation_edge_fails_closed (test_reducer.AdversarialTests.test_non_contiguous_generation_edge_fails_closed) ... ok
test_post_wake_retry_grant_does_not_precede_fails_closed (test_reducer.AdversarialTests.test_post_wake_retry_grant_does_not_precede_fails_closed) ... ok
test_post_wake_retry_wrong_namespace_fails_closed (test_reducer.AdversarialTests.test_post_wake_retry_wrong_namespace_fails_closed) ... ok
test_pre_grant_predecessor_fails_closed (test_reducer.AdversarialTests.test_pre_grant_predecessor_fails_closed) ... ok
test_ready_before_finalize_fails_closed (test_reducer.AdversarialTests.test_ready_before_finalize_fails_closed) ... ok
test_ready_broken_wake_event_id_fails_closed (test_reducer.AdversarialTests.test_ready_broken_wake_event_id_fails_closed) ... ok
test_second_post_wake_retry_fails_closed (test_reducer.AdversarialTests.test_second_post_wake_retry_fails_closed) ... ok
test_wrong_instance_sampled_edge_fails_closed (test_reducer.AdversarialTests.test_wrong_instance_sampled_edge_fails_closed) ... ok
test_wrong_lifecycle_fails_closed (test_reducer.AdversarialTests.test_wrong_lifecycle_fails_closed) ... ok
test_crop_attempted_violation_fails_closed (test_reducer.NegativeSafetyTests.test_crop_attempted_violation_fails_closed) ... ok
test_discarded_hybrid_fails_closed (test_reducer.NegativeSafetyTests.test_discarded_hybrid_fails_closed) ... ok
test_genuine_miss_violation_fails_closed (test_reducer.NegativeSafetyTests.test_genuine_miss_violation_fails_closed) ... ok
test_lower_checkpoint_violation_fails_closed (test_reducer.NegativeSafetyTests.test_lower_checkpoint_violation_fails_closed) ... ok
test_partial_sidecar_fails_closed (test_reducer.NegativeSafetyTests.test_partial_sidecar_fails_closed) ... ok
test_pre_wake_retry_is_not_a_repeated_retry (test_reducer.NegativeSafetyTests.test_pre_wake_retry_is_not_a_repeated_retry) ... ok
test_ready_before_finalization_fails_closed (test_reducer.NegativeSafetyTests.test_ready_before_finalization_fails_closed) ... ok
test_recompute_fallback_fails_closed (test_reducer.NegativeSafetyTests.test_recompute_fallback_fails_closed) ... ok
test_repeated_retry_fails_closed (test_reducer.NegativeSafetyTests.test_repeated_retry_fails_closed) ... ok
test_same_generation_self_wake_fails_closed (test_reducer.NegativeSafetyTests.test_same_generation_self_wake_fails_closed) ... ok
test_skipped_eligible_predecessor_fails_closed (test_reducer.NegativeSafetyTests.test_skipped_eligible_predecessor_fails_closed) ... ok
test_canonical_stream_verifies_all_eleven (test_reducer.OracleContractTests.test_canonical_stream_verifies_all_eleven) ... ok
test_oracle_exposes_exactly_eleven_names (test_reducer.OracleContractTests.test_oracle_exposes_exactly_eleven_names) ... ok
test_event_summary_verdict_field_rejected (test_reducer.RawProvenanceGateTests.test_event_summary_verdict_field_rejected) ... ok
test_manifest_verdict_field_rejected (test_reducer.RawProvenanceGateTests.test_manifest_verdict_field_rejected) ... ok
test_tampered_raw_bundle_hash_fails_closed (test_reducer.RawProvenanceGateTests.test_tampered_raw_bundle_hash_fails_closed) ... ok

----------------------------------------------------------------------
Ran 36 tests in 0.051s

OK
```

36 tests = 11-name contract + canonical VERIFIED + per-defect fail-closed +
provenance-gate tests.  New R111 adversarial tests mapped to the required
anti-forgery cases:

| required case | test |
|---|---|
| counters not advancing | `test_generation_not_advancing_fails_closed` |
| wrong cache instance (park/grant) | `test_generation_wrong_cache_instance_fails_closed` |
| wrong cache instance (sampled edge) | `test_wrong_instance_sampled_edge_fails_closed` |
| contradictory sampled edge (non-monotonic) | `test_contradictory_sampled_edge_fails_closed` |
| contradictory sampled edge (out of range / non-contiguous) | `test_non_contiguous_generation_edge_fails_closed` |
| absence of sampled edges must pass | `test_absent_sampled_edges_still_verifies` (canonical VERIFIED, `sampled_edges_seen={"kv":0}`) |
| broken finalize wake_event_id chain | `test_finalize_broken_wake_event_id_fails_closed` |
| broken READY wake_event_id chain | `test_ready_broken_wake_event_id_fails_closed` |
| missing pre-wake retry | `test_missing_pre_wake_retry_fails_closed` |
| second post-wake retry | `test_second_post_wake_retry_fails_closed`, `NegativeSafetyTests.test_repeated_retry_fails_closed` |
| post-wake retry with bogus wake_event_id | `test_broken_attempt_lineage_fails_closed` |
| post-wake retry naming a non-preceding grant | `test_post_wake_retry_grant_does_not_precede_fails_closed` |
| post-wake retry wrong namespace | `test_post_wake_retry_wrong_namespace_fails_closed` |
| pre-wake failure is not "repeated_retry" | `test_pre_wake_retry_is_not_a_repeated_retry` |

The R111 canonical fixture is now real-shaped: it includes the mandatory
pre-wake `restore_host_alloc_retry_result` (`attempt_id=null`,
`retry_grant=false`) preceding the park, keeps one post-wake retry, and the
accepted finalize + READY both carry the deciding grant's `wake_event_id`; it
verifies all eleven predicates.

## 6. Real-bundle validation (R109)

Command:

```sh
python p0b_reducer.py --events ../R109-bundle/raw.log \
    --manifest ../R109-bundle/manifest.json
```

Result: `status=NOT_VERIFIED`, **exit code 1**, `raw_event_count=80`.  No
oracle tuning was performed; the two newly re-frozen predicates now pass on
the real chain, and the two residual failures are the R110-class-C
configuration/workload gaps, reported honestly.

| # | predicate | result | reason |
|---|---|---|---|
| 1 | `provenance` | PASS | |
| 2 | `singular_identity` | PASS | |
| 3 | `pid_profile_source_binding` | PASS | |
| 4 | `positive_full_hit` | FAIL | `no complete positive KV+Mamba durability_barrier for the target` (durable marker `/tmp/t38c-durable-trace` absent + `T38C_RUN_ID` unset + server launched without `--enable-session-radix-cache`; R110 §2.1) |
| 5 | `host_alloc_park` | PASS | |
| 6 | `generation_transition` | PASS | `sampled_edges_seen={"kv":1,"mamba":0}` — mamba 89→105 proven from authoritative counters with zero in-window sampled edges |
| 7 | `fifo_predecessor` | FAIL | `fail-closed predecessor lineage reason: no_released_predecessor` (only one waiter existed; R110 §2.3) |
| 8 | `attempt_lineage` | PASS | pre-wake failure tolerated; finalize `raw.log:1196` and READY `raw.log:1202` both name grant `run-40675-3216566354667:host-alloc:75` (`raw.log:1131`) |
| 9 | `accepted_finalization` | PASS | |
| 10 | `ready_after_finalize` | PASS | |
| 11 | `negative_safety` | PASS | |

Interpretation: predicates 6 and 8, previously the two proved contract
mismatches, now measure real product semantics on the true captured chain.
Predicates 4 and 7 remain failing for reasons independent of this re-freeze
(missing durable/session configuration and a single-waiter workload); they are
not oracle defects and were not tuned away.

## 7. Open issues / follow-ups (for the orchestrator)

1. **Predicate 8 wording vs real multi-grant lineage** (§4.4): the dispatch
   said the post-wake retry's `wake_event_id` "names the deciding grant"; real
   emission (and the R107 canonical fixture) has it name the authorizing grant
   that precedes the later deciding grant.  Implemented as "captured grant
   that strictly precedes the retry" with the strict deciding-grant equality
   enforced on finalize/READY.  Confirm this interpretation before treating
   the re-freeze as final.
2. `positive_full_hit` (§6 row 4) remains unreachable without enabling the
   marker-gated durable vehicle, setting `T38C_RUN_ID`, and launching with
   `--enable-session-radix-cache`; that is a telemetry-on/workload decision
   (AGENTS.md rule 2), outside this task.
3. `fifo_predecessor` (§6 row 7) needs a two-waiter workload where the first is
   released before the second is granted; no product change required.
4. Evidence hygiene (carried from R110 §0): `R109-bundle/key-lines.txt` and the
   R109 report label the park/grant at `raw.log:1062/1128`; the authoritative
   lines are `1065/1131`.  Not edited here (out of the R111 write set).
5. The dispatch's "write set R111-reducer/ ONLY" and the mandated report path
   `work/P0-B-ORACLE-REFREEZE-20260911-R111.md` conflict; the report is written
   to the explicitly named path as instructed.
6. Independent re-verification (tester/reviewer) of this re-freeze, and a
   decision on whether the corrected predicates should be re-frozen as the new
   canonical oracle, remain out of scope for this implementation invocation.
