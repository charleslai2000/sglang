# R115 companion gate: `durable_frontier_coverage`

Additive, fail-closed companion acceptance gate for the P0-B final bundle.
P0-B closes only when the canonical R111 oracle is 11/11 **and** this gate
PASSes on the same frozen bundle.

## Why it exists

The R111 oracle's predicate 4 only checks that a *complete* `durability_barrier`
exists at the target's `session_generation`. It does not check that the
barrier's durable lineage actually covers the frontier the target restore
requires. A small, early but locally "complete" barrier can therefore satisfy
predicate 4 while the target restore still needs more tokens than the durable
lineage covers. This gate closes that false-PASS gap.

## Inputs

Read-only, stdlib parsing only, no product imports:

* raw server-log lines carrying `[HAE] {json}` records;
* `p0_durable` JSONL records (`"trace": "p0_durable"`).

## Rule (exact)

Target identity `T = (T_sid, T_gen, T_build)`:

1. `T_gen` = suffix after the last `:` of the manifest
   `target.lifecycle_key`.
2. `T_sid` / `T_build` = `trace_context.session_id` /
   `trace_context.build_rid` of the target's accepted
   `restore_hybrid_finalize` record (`result == "accepted"`,
   `lifecycle_key == manifest target lifecycle_key`); cross-check
   `trace_context.session_generation == T_gen`.

Required frontier `R`:

3. `park` = the target `restore_host_alloc_wait` with
   `state == "WAIT_CAPACITY"`, `reason == "HOST_ALLOC"`,
   `lifecycle_key == target`.
4. `R = park.requested_primary_tokens`; require
   `park.positive_hit_tokens >= R > 0`.
5. Cross-check the accepted finalize `kv_expected == kv_fetched == R`.

Target restore node set:

6. `N_target` = string `node_id`s of probe `p0_durable` records matching `T`
   with `evt in {residency_detach, residency_barrier_outcome}` and non-null
   `node_id`. `H_target` = their non-empty `final_kv_hash` values.

Barrier candidates `B`:

7. Probe records `evt == "durability_barrier"` matching `T` with
   `kv_durable is True`, `mamba_durable is True`,
   positive `kv_completed_tokens == kv_requested_tokens`,
   positive `mamba_expected_pages == mamba_succeeded_pages`, non-empty
   `node_id`, non-empty `final_kv_hash`.

Linked barrier:

8. Exists `b in B` with `b.node_id in N_target` OR
   `b.final_kv_hash in H_target`.

Covered frontier:

9. Maximum integer `frontier_end` over probe `evt == "storage_persisted"`
   records matching `T` with `node_id in N_target`.

Verdict:

10. **PASS** iff a linked barrier exists **and**
    `covered_frontier >= R`. Otherwise **FAIL**.

### Fail-closed reasons

| Reason | Trigger |
| --- | --- |
| `insufficient_target_identity` | missing manifest target/`lifecycle_key`, no accepted finalize, missing/contradictory `trace_context`, generation mismatch |
| `insufficient_target_lineage` | missing target park, non-positive `R`, `positive_hit_tokens < R`, finalize `kv_expected`/`kv_fetched` != `R`, empty `N_target` |
| `no_durable_barrier` | `B` is empty |
| `no_linked_barrier` | `B` non-empty but no candidate is on the target chain |
| `insufficient_frontier_evidence` | linked barrier exists but no `storage_persisted`-derived frontier on the target chain |
| `frontier_below_required` | `covered_frontier < R` |

The gate never defaults to PASS.

### Interpretation note (strict, fail-closed)

Rule 9's parenthetical permits (does not require) using a candidate barrier's
own `kv_completed_tokens` as a frontier when its node has no
`storage_persisted` row, waiving the `storage_persisted` requirement only when
no `storage_persisted` rows exist at all. This implementation deliberately
does **not** exercise that permissive fallback for a PASS: a PASS always
requires a `storage_persisted`-derived `frontier_end >= R` on the target chain.
Absent such evidence the verdict is `insufficient_frontier_evidence`. This is
the stricter, fail-closed reading and is what
`test_barrier_without_persisted_frontier_does_not_pass` pins.

## CLI

```
python coverage_gate.py --events <raw.log> <probe.log> \
    --manifest <manifest.json> [--json]
```

Exit codes:

* `0` = COVERAGE PASS
* `1` = COVERAGE FAIL (fail-closed)
* `2` = INVALID_INPUT (unreadable/invalid manifest, missing/unsupported
  manifest `format`, or missing event file)

`--json` prints a JSON object with: `status`, `rule`, `target`
(`rid`, `lifecycle_key`, `session_id`, `session_generation`, `build_rid`),
`required_frontier`, `target_restore_node_count`, `barrier_candidates`,
`linked_barrier`, `covered_frontier`, `reason`, `failures`.

## Tests

```
python -m unittest test_coverage_gate -v
```

Eight adversarial tests, each running the CLI as a subprocess on a synthetic
temp bundle and asserting the exit code and parsed verdict.
