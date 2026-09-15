# P0-B storage durability — R116 report

- task_id: `P0-B-STORAGE-DURABILITY-20260911-R116`
- invocation: `ses-p0b-storage-durability-r116-20260911` (fresh)
- role: `coder`
- epoch: `2026-09-11`
- status: **done**

## What was built

`R116 storage-backed durability reducer`: a NEW, additive, offline,
stdlib-only, fail-closed checker that re-judges the FROZEN R114 bundle plus the
FROZEN L3 evidence. No live calls, no server interaction, no product imports,
no instrumentation, no synthetic events. R111/R115 were not modified or
imported.

- CLI: `python storage_durability.py --raw <raw.log> --probe <probe.log> --manifest <manifest.json> --l3-evidence <l3-evidence.json> [--json]`
- Exit `0` = STORAGE_DURABILITY PASS, `1` = FAIL (fail-closed), `2` = INVALID_INPUT.

## The 8 predicates as implemented

1. `identity_consistency` — `T_rid`/`T_sid`/`T_gen`/`T_build`/`T_prefix`
   consistent across the target park, accepted finalize, target restore
   `pc_storage_query`/`pc_get_v2`/`pc_l3_host`, and `l3-evidence.json` `target`.
   (Probe records carry no session fields, so their identity join is rid.)
2. `kv_prefix_coverage` — restore query `kv_hit_pages == storage_hit_count ==
   T_prefix` and `query_suffix_len >= T_prefix`; `sum(pc_get_v2.kv_hits)` over
   the target rid `== T_prefix`; every kv-batch `n_keys == kv_hits`.
3. `durable_object_existence` — `key_set_sha256 == sha256(json.dumps(restore
   keys))`; every enumerated `objects/<key>.bin` exists, size>0, size and sha256
   match the record.
4. `durable_write_then_restore` — a `pc_storage_query` with the same key-set and
   `kv_hit_pages == 0` under a different rid, plus restore `kv_hit_pages ==
   T_prefix`.
5. `mamba_sidecar_durable` — `p0_durable` `backup_ack_drain`/`durability_barrier`
   with `mamba_durable is True` for `T_sid`/`T_gen`/`T_build`; finalize
   `sidecars.mamba.expected == fetched == 1`; restore `sidecar_hits.mamba > 0`.
6. `l3_to_host_completed` — `pc_l3_host.completed_tokens == T_prefix` and
   `requested_tokens >= T_prefix`.
7. `finalize_consumed_restore` — accepted + `all_or_nothing is True` +
   `kv_fetched == T_prefix`; `wake_event_id` names a real `decision=="grant"`;
   no target recompute/hybrid-discard path (`restore_disposition`
   discard/recompute, `restore_recompute`, `MISS_RECOMPUTE`,
   `negative_cache_blocked=True`, `NO_L3`).
8. `negative_safety` — no unreadable required record, no contradictory
   identity/join.

## Tests (true results)

`python -m unittest test_storage_durability -v` → `Ran 10 tests ... OK` (all 10
ok; exit 0).

| test | result |
| --- | --- |
| `test_r114_frozen_fixture_passes` (control, exit 0) | ok |
| `test_wrong_identity_fails` | ok (rc 1, FAIL) |
| `test_short_coverage_fails` (kv_hit_pages 2048 < 27008) | ok (rc 1, FAIL) |
| `test_missing_durable_object_fails` | ok (rc 1, FAIL) |
| `test_keyset_mismatch_between_build_and_restore_fails` | ok (rc 1, FAIL) |
| `test_no_build_then_restore_causality_fails` (build hit != 0) | ok (rc 1, FAIL) |
| `test_mamba_ack_missing_fails` | ok (rc 1, FAIL) |
| `test_l3_host_incomplete_fails` | ok (rc 1, FAIL) |
| `test_recompute_or_discard_path_fails` | ok (rc 1, FAIL) |
| `test_invalid_input_exit_2` | ok (rc 2, INVALID_INPUT) |

## R114 control verdict

Command (real frozen inputs) exits **0**; `status: PASS`; all predicates PASS:

| predicate | verdict |
| --- | --- |
| identity_consistency | PASS |
| kv_prefix_coverage | PASS |
| durable_object_existence | PASS |
| durable_write_then_restore | PASS |
| mamba_sidecar_durable | PASS |
| l3_to_host_completed | PASS |
| finalize_consumed_restore | PASS |
| negative_safety | PASS |

Verdict saved to `work/R116-storage-durability/R114-control.out.json`
(`failures: []`, `prefix_tokens: 27008`).

## Artifacts (paths + sha256)

- `work/R116-storage-durability/storage_durability.py`
  `2e6cbdb9943b766a5fc94c17d5bbef58ad61b47fc476bf159938d5f6f2bfea35`
- `work/R116-storage-durability/test_storage_durability.py`
  `368107b2b601e1e4f4fb02212e2e6dc563d3baf51a48d0b3f201c1460a1fa554`
- `work/R116-storage-durability/README.md`
  `523a45469d361372b501220f7998148a193cd01fbc490615c0ef6aaa8e54d937`
- `work/R116-storage-durability/R114-control.out.json`
  `be6a74d74d4a2e582c828848dbee555029c66e7e06179ae9f2a0ba6d5abdea04`

Frozen inputs re-verified unchanged: `raw.log`
`9df12929…dcb8c`, `probe.log` `9f41d92f…0f961`, `l3-evidence.json`
`3f1638a406511851ce8ae9005965f99a5ecef069b6cd16baadc25a8490607a4e`.

## Granularity note (observability gap, recorded, not blocking)

The producer emits only a fixed 8-key target object set plus page-level hit
COUNTS (no full per-page hash list). Per-object existence is verified for every
enumerated object; per-page coverage is proven by the read path's own hit
accounting (`pc_storage_query` + `pc_get_v2`). Full per-page hash enumeration is
absent.

## Residual assumptions

- Predicate 4 is keyed on "same key-set, `kv_hit_pages==0`, different rid" per
  the dispatch text. In the frozen R114 bundle the qualifying record is the
  warm/build rid `25dd9122eff34a0eadcd0fe0168746d6` (suffix 27050, key-set
  identical to the target restore query), NOT the finalize
  `trace_context.build_rid` `1e3dbabc421748acbd27fae9990fff57`, whose own
  storage query carries a different 8-key set (intersection 0/16). This is a
  warm_rid-vs-build_rid naming/observability gap; recorded, not blocking.
- `identity_consistency` joins probe records on `rid` because
  `pc_storage_query`/`pc_get_v2`/`pc_l3_host` carry no session/generation/build
  fields.
