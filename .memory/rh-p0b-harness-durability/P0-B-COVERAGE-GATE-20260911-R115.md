# P0-B companion coverage gate — R115

- **Task ID:** `P0-B-COVERAGE-GATE-20260911-R115`
- **Invocation:** `ses-p0b-coverage-gate-r115-20260911` (fresh)
- **Role:** coder
- **Epoch:** 2026-09-11
- **Status:** `done`

## Summary

Implemented a new, additive, fail-closed companion acceptance gate
`durable_frontier_coverage` that verifies the durable frontier/lineage coverage
of a P0-B bundle. The canonical R111 oracle's predicate 4 only checks that a
complete `durability_barrier` exists at the target's `session_generation`; it
does not verify that the barrier's durable lineage covers the frontier the
target restore requires. This gate closes that gap: P0-B closes only when R111
is 11/11 **and** this gate PASSes on the same frozen bundle.

No product code, R111/R113/R114 artifacts, or sibling mirror were modified.

## Rule as implemented (exact)

Target identity `T = (T_sid, T_gen, T_build)`:

1. `T_gen` = suffix after the last `:` of `manifest["target"]["lifecycle_key"]`.
2. `T_sid` / `T_build` = `trace_context.session_id` / `trace_context.build_rid`
   of the target accepted `restore_hybrid_finalize` (`result=="accepted"`,
   `lifecycle_key == manifest target lifecycle_key`); cross-check
   `trace_context.session_generation == T_gen`.

Required frontier `R`:

3. `park` = target `restore_host_alloc_wait` with `state=="WAIT_CAPACITY"`,
   `reason=="HOST_ALLOC"`, `lifecycle_key==target`.
4. `R = park.requested_primary_tokens`; require
   `park.positive_hit_tokens >= R > 0`.
5. Cross-check accepted finalize `kv_expected == kv_fetched == R`.

Target restore node set:

6. `N_target` = string `node_id`s of probe `p0_durable` records matching `T`
   with `evt in {residency_detach, residency_barrier_outcome}` and non-null
   `node_id`; `H_target` = their non-empty `final_kv_hash` values.

Barrier candidates `B`:

7. Probe `evt=="durability_barrier"` matching `T` with `kv_durable is True`,
   `mamba_durable is True`, positive
   `kv_completed_tokens == kv_requested_tokens`, positive
   `mamba_expected_pages == mamba_succeeded_pages`, non-empty `node_id`,
   non-empty `final_kv_hash`.

Linked barrier:

8. Exists `b in B` with `b.node_id in N_target` OR `b.final_kv_hash in
   H_target`.

Covered frontier:

9. Maximum integer `frontier_end` over probe `evt=="storage_persisted"`
   matching `T` with `node_id in N_target`.

Verdict:

10. **PASS** iff a linked barrier exists AND `covered_frontier >= R`; else
    **FAIL**.

Fail-closed reasons: `insufficient_target_identity`,
`insufficient_target_lineage`, `no_durable_barrier`, `no_linked_barrier`,
`insufficient_frontier_evidence`, `frontier_below_required`. The gate never
defaults to PASS.

Exit codes: `0` PASS, `1` FAIL (fail-closed), `2` `INVALID_INPUT`
(unreadable/invalid manifest, missing/unsupported manifest `format`, or
missing event file).

The full write-up is in `work/R115-coverage/README.md`.

## Test list and true results

Command:
```
cd work/R115-coverage && python -m unittest test_coverage_gate -v
```
Result: **`Ran 8 tests ... OK`** (exit 0). Every test builds a synthetic temp
bundle and runs the checker CLI as a subprocess, asserting the exit code and
parsed JSON verdict.

| Test | Expected | Result |
| --- | --- | --- |
| `test_exact_prefix_coverage_passes` | PASS (exit 0) | ok |
| `test_small_early_barrier_larger_target_fails` | FAIL `frontier_below_required` (exit 1) | ok |
| `test_barrier_wrong_build_or_session_fails` | FAIL `no_durable_barrier` (exit 1) | ok |
| `test_barrier_node_not_on_target_chain_fails` | FAIL `no_linked_barrier` (exit 1) | ok |
| `test_missing_target_trace_context_fails_closed` | FAIL `insufficient_target_identity` (exit 1) | ok |
| `test_missing_target_lineage_fails_closed` | FAIL `insufficient_target_lineage` (exit 1) | ok |
| `test_barrier_without_persisted_frontier_does_not_pass` | FAIL `insufficient_frontier_evidence` (exit 1) | ok |
| `test_invalid_input_exit_2` | INVALID_INPUT (exit 2) | ok |

## R113 control verdict (frozen evidence)

Command:
```
python coverage_gate.py \
  --events <R113>/raw.log <R113>/probe.log \
  --manifest <R113>/manifest.json --json \
  > R115-coverage/R113-control.out.json
```

True result: **exit `1` (COVERAGE FAIL)**, stderr empty.

- `status` = `FAIL`
- `reason` = `no_durable_barrier` (R113 had zero complete
  `durability_barrier` candidates at the target identity; also zero
  `storage_persisted` rows)
- `T_sid` = `r113-p1`
- `T_gen` = `2`
- `T_build` = `f25ad7552ba440a79b47bd8a5044de5f`
- `R` = `46720`
- `target_restore_node_count` = `23`
- `barrier_candidates` = `[]`

## Artifacts + sha256

All under
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/R115-coverage/`:

| File | sha256 |
| --- | --- |
| `coverage_gate.py` | `c6a8492f365f5755a117075d1a74f88979fc89040399a160bf04187f8f74b328` |
| `test_coverage_gate.py` | `a610b88fb3151554acc10688540ba54035b44df3169ba6d24cc8621364ac81a3` |
| `README.md` | `56d9fb0e31a58424bebe1aec9edc65ee86837561a4b2c55559dd3b5f519b329e` |
| `R113-control.out.json` | `a938fdc992571a3615a411d4f1f825698bc91665f8b44df4ac7af0fc90b84760` |

Local deterministic checks run: `python -m unittest test_coverage_gate -v`
(8/8 ok), `python -m py_compile coverage_gate.py test_coverage_gate.py` (ok),
and the R113 control CLI run (exit 1). No project formatter/typechecker is
configured for these stdlib-only tools; formatting follows the R111 reducer
style.

## Open issues / residual assumptions

1. **Strict frontier interpretation.** Rule 6's parenthetical *permits*
   substituting a linked barrier's own `kv_completed_tokens` when that node has
   no `storage_persisted` row, waiving the `storage_persisted` requirement only
   when no `storage_persisted` rows exist at all. This implementation
   deliberately does **not** exercise that permissive fallback for PASS: a PASS
   always requires a `storage_persisted`-derived `frontier_end >= R` on the
   target chain, otherwise `insufficient_frontier_evidence`. This is the
   stricter, fail-closed reading and is pinned by
   `test_barrier_without_persisted_frontier_does_not_pass`. If a future frozen
   bundle legitimately has barriers but no `storage_persisted` producer output,
   this gate will FAIL by design (never PASS-by-default); that producer gap
   should be resolved rather than waived.
2. **`INVALID_INPUT` boundary.** Missing manifest `target` /
   `target.lifecycle_key` are treated as exit-1 FAIL
   (`insufficient_target_identity`) per fail-closed rule 8; exit 2 is reserved
   for a structurally unusable invocation (unreadable/invalid manifest,
   missing/unsupported `format`, missing event file). The required test
   exercises the missing-`format` case.
3. **`session_generation` typing.** Probe records carry integer
   `session_generation`; `T_gen` is a string lifecycle-key suffix. Matching
   normalizes to string (`str(value) == T_gen`), so int/str encodings agree.
4. The gate is additive and does not re-verify R111's other predicates; the
   composite P0-B closure rule (R111 11/11 AND this gate PASS) must be applied
   by the acceptance owner.
