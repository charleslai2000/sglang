# R116 storage-backed durability reducer

- task_id: `P0-B-STORAGE-DURABILITY-20260911-R116`
- epoch: `2026-09-11`
- role: `coder`
- repo: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`

NEW additive, offline, stdlib-only, fail-closed reducer that re-judges the
FROZEN R114 bundle plus the FROZEN L3 evidence. It does **not** modify or import
the R111/R115 reducers and makes no live calls, no server interaction, and no
product imports.

## Why a new reducer (user ruling A′)

R111's predicate 4 is insufficient: it accepts a `durability_barrier` matching
only `session_generation`, so a small early barrier can be mistaken for proof
that the whole target restore prefix is durable. R115 (barrier coverage) already
FAILs and stays as evidence of telemetry incompleteness — it is not product
failure. R116 instead proves the target prefix's REAL durable storage coverage
plus an actual restore, joined on the full target identity.

## Contents

| file | purpose |
| --- | --- |
| `storage_durability.py` | the reducer (stdlib only) |
| `test_storage_durability.py` | stdlib `unittest` adversarial suite (CLI subprocess) |
| `R114-control.out.json` | real-bundle control verdict (exit 0, all 8 predicates PASS) |
| `README.md` | this file |

## Usage

```sh
source /mnt/data/neuron/envs/sglang-3090-opt/activate-sglang-3090.sh
python -m py_compile storage_durability.py
python -m unittest test_storage_durability -v

python storage_durability.py \
  --raw <abs>/work/R114-bundle/raw.log \
  --probe <abs>/work/R114-bundle/probe.log \
  --manifest <abs>/work/R114-bundle/manifest.json \
  --l3-evidence <abs>/work/R116-l3-evidence/l3-evidence.json --json
```

Exit codes: `0` = `STORAGE_DURABILITY PASS`, `1` = `FAIL` (fail-closed),
`2` = `INVALID_INPUT` (missing/unreadable/structurally invalid input, or a
raw-file hash that does not match the provenance manifest).

With `--json` the reducer prints:

```json
{"status": "...", "rule": "...",
 "target": {"rid": "...", "session_id": "...", "session_generation": "...",
            "build_rid": "...", "prefix_tokens": 27008},
 "predicates": [{"name": "...", "passed": true, "reason": "..."}],
 "failures": ["<name>: <reason>"]}
```

## Target identity T (derived only from frozen evidence)

- `T_rid` = `manifest.target.rid`
- `T_gen` = suffix after the last `:` of `manifest.target.lifecycle_key`
- from the accepted `restore_hybrid_finalize` whose `lifecycle_key` equals the
  manifest target lifecycle key: `T_sid = trace_context.session_id`,
  `T_build = trace_context.build_rid`, requiring
  `trace_context.session_generation == T_gen`
- `T_prefix` = the target `restore_host_alloc_wait.requested_primary_tokens`,
  requiring `== positive_hit_tokens > 0`, and requiring the finalize
  `kv_expected == kv_fetched == T_prefix`

## Predicates (all must pass; fail closed with a precise reason)

1. `identity_consistency` — `T_rid`/`T_sid`/`T_gen`/`T_build`/`T_prefix`
   consistent across the target park, the accepted finalize, the target restore
   `pc_storage_query`/`pc_get_v2`/`pc_l3_host`, and `l3-evidence.json` `target`.
2. `kv_prefix_coverage` — target restore `pc_storage_query` has
   `kv_hit_pages == T_prefix` and `storage_hit_count == T_prefix` and
   `query_suffix_len >= T_prefix`; `sum(pc_get_v2.kv_hits)` over the target rid
   equals `T_prefix`; every kv-batch `pc_get_v2` has `n_keys == kv_hits` (no
   missing pages). This replaces R115's unclear scalar `frontier_end`.
3. `durable_object_existence` — `l3-evidence.key_set_sha256` equals the SHA256
   of `json.dumps(target restore pc_storage_query.keys)` (order preserved); every
   enumerated object exists under `objects/<key>.bin`, is size > 0, and matches
   its recorded `sha256`.
4. `durable_write_then_restore` — there exists a `pc_storage_query` with the
   SAME key-set as the restore query but `kv_hit_pages == 0` under a different
   rid (in the frozen R114 evidence this is the warm/build record
   `25dd9122…`, key-set identical to the target restore query), AND the restore
   query has `kv_hit_pages == T_prefix`.
5. `mamba_sidecar_durable` — a `p0_durable` durable-ACK event
   (`backup_ack_drain`/`durability_barrier`) exists for `T_sid`/`T_gen`/`T_build`
   with `mamba_durable is True`; the finalize `sidecars.mamba.expected ==
   fetched == 1`; the restore `pc_storage_query.sidecar_hits.mamba` is positive.
6. `l3_to_host_completed` — target `pc_l3_host.completed_tokens == T_prefix`
   with `requested_tokens >= T_prefix`.
7. `finalize_consumed_restore` — target finalize `result == "accepted"` and
   `all_or_nothing is True` and `kv_fetched == T_prefix`; its `wake_event_id`
   names a real target grant (`restore_host_alloc_wake_decision` with
   `decision == "grant"`); and no accepted recompute/hybrid-discard path exists
   for the target (`restore_disposition` discard/recompute, `restore_recompute`,
   `MISS_RECOMPUTE`/`negative_cache_blocked`/`NO_L3` markers).
8. `negative_safety` — no unreadable required record and no contradictory
   identity/join; otherwise FAIL.

## Granularity note (recorded observability gap)

The producer emits only a fixed 8-key target object set plus page-level hit
COUNTS (no full per-page hash list). Per-object existence is therefore verified
for every enumerated object, and per-page coverage is proven by the read path's
own hit accounting (`pc_storage_query` + `pc_get_v2`). Full per-page hash
enumeration is absent — recorded as an observability gap, not blocking.

## Non-goals

No product imports, no monkeypatching, no synthesis of product events, no
runtime instrumentation, no server/GPU/live workload, no product or test edits.
The reducer never trusts a bundle's own `oracle`/`verdict`/`status`/`summary`
claims. Independent review and live-chain validation remain out of scope.
