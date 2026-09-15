# R111 P0-B offline reducer (re-frozen 11-predicate oracle)

- task_id: `P0-B-ORACLE-REFREEZE-20260911-R111`
- supersedes: `P0-B-REDUCER-FREEZE-20260911-R107` (kept frozen as history)
- epoch: 2026-09-11
- role: coder
- repo: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
  (branch `3060-12g-qwen35-4b`, HEAD `4f41f5bab5`, intentionally dirty; no
  commit/push)

This is an isolated, disposable implementation artifact.  It is **not** live
acceptance and produces no P0-B runtime claim.

## R111 re-freeze delta

Exactly two predicates were corrected because the R107 text was provably
unsatisfiable against real product emission
(`../P0-B-GAP-CLASSIFY-20260911-R110.md`), with no product change:

1. `generation_transition` (6): prove the advance from the authoritative
   producer counters (`captured_generations`/`current_generations`) with a
   same-instance park→grant ordering; treat the deliberately sampled
   `host_allocability_change` records as corroborating (absence allowed,
   contradiction forbidden) and record `sampled_edges_seen` + `sampling`.
2. `attempt_lineage` (8): tolerate the mandatory pre-wake failure
   (`attempt_id=null`), allow at most one post-wake retry with its own
   host-alloc namespace and a captured preceding grant, and key the
   non-forgeable join on the finalize+READY `wake_event_id` both naming the
   same deciding grant.  `negative_safety`'s `repeated_retry` now counts
   post-wake retries only.

See `FREEZE-11-PREDICATES.md` §6/§8 for the exact `file:line` evidence.

## Contents

| file | purpose |
| --- | --- |
| `FREEZE-11-PREDICATES.md` | frozen contract: exact real event names, fields, joins, and fail-closed rules |
| `p0b_reducer.py` | stdlib-only fail-closed offline reducer over captured product log lines |
| `test_reducer.py` | stdlib `unittest` adversarial suite (canonical pass + per-defect fail-closed) |
| `manifest.sha256` | SHA256 of the three source/doc files above |
| `README.md` | this file |

## Non-goals / guarantees

- No product imports, no monkeypatching, no synthesis of product events, no
  runtime instrumentation, no server/GPU/live workload, no product or test
  edits.  Pure standard-library parsing of captured log text.
- The reducer never trusts a bundle's own `oracle`/`verdict`/`status`/summary
  claims; such keys are rejected by the `raw_provenance` input gate.
- Fail closed: any missing required field, contradictory identity/join, hash
  mismatch, or unrecognized lineage reason yields `NOT_VERIFIED` with an
  explicit reason.  Facts are never backfilled from timestamps or nearby rows.
- Every consumed record retains its raw `file:line` reference (emitted in
  `raw_references`).

## Inputs

The reducer consumes the real captured envelopes:

* `[HAE] {json}` records with `schema == "host_alloc.v1"` (`evt` one of
  `restore_host_alloc_wait`, `restore_host_alloc_wake_decision`,
  `restore_host_alloc_retry_result`, `restore_hybrid_finalize`,
  `host_allocability_change`);
* the `[P3] ... evt=ready_host schema=rh_ready_host.v1 ...` line;
* `p0_durable` JSONL (`"trace": "p0_durable"`), including `durability_barrier`.

plus a `p0b.raw-bundle.v3` provenance manifest:

```json
{
  "format": "p0b.raw-bundle.v3",
  "task_id": "P0-B-ORACLE-REFREEZE-20260911-R111",
  "epoch": "2026-09-11",
  "runtime": {
    "process_id": 251004,
    "run_id": "run-251004-...",
    "profile_id": "profile-...",
    "source_build": "<source_head>:<producer-digest>"
  },
  "target": {"rid": "p0b-target", "lifecycle_key": "p0b-target:5"},
  "raw_files": {"/abs/raw.log": "<sha256>", "/abs/durable.jsonl": "<sha256>"},
  "source_files": {"/abs/producer.py": "<sha256>"}
}
```

## Usage

```sh
source /mnt/data/neuron/envs/sglang-3090-opt/activate-sglang-3090.sh
python -m py_compile p0b_reducer.py
python -m unittest test_reducer -v

python p0b_reducer.py --events /abs/raw.log /abs/durable.jsonl \
    --manifest /abs/manifest.json
```

`p0b_reducer.py` exits `0` for `VERIFIED` and `1` for `NOT_VERIFIED`, and
always prints the eleven predicate results plus reasons and raw references.
The only two verdicts are `VERIFIED` and `NOT_VERIFIED`.

## Status boundary

This package freezes the oracle and proves reducer behavior on a
synthetic-but-real-shaped stream.  It does **not** execute a live chain, prove
HOST_ALLOC reachability, or produce P0-B acceptance.  Independent review and
live-chain validation remain out of scope.
