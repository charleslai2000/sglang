# P0-B-REDUCER-FREEZE-20260911-R107

- task_id: `P0-B-REDUCER-FREEZE-20260911-R107`
- invocation: `ses-p0b-reducer-freeze-r107-20260911`
- role: coder
- epoch: 2026-09-11
- repo: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
  (branch `3060-12g-qwen35-4b`, HEAD `4f41f5bab5`, intentionally dirty; no
  commit/push)

## status

**done**

Froze the canonical P0-B oracle at exactly 11 predicates against the real
emitted event names/fields and built one fail-closed offline reducer over real
captured `[HAE]` / `rh_ready_host.v1` / `p0_durable` log lines.  No product
source, existing tests, other reports, or files outside
`.memory/phase2-hicache-design/work/R107-reducer/` were edited.  No
server/GPU/live workload was run.  No children dispatched.

## artifacts

All under
`.memory/phase2-hicache-design/work/R107-reducer/` (the authorized write set):

```
sha256  file
f080886734e5a6b58b35286140697d48050438fda8d6211a02660d608efc19f5  FREEZE-11-PREDICATES.md
253facede369f7e258eab922cc45e4bf959594de18b8b5ae0c11baee9fe211ce  README.md
11de96819a75dc5b82d0ca1d230c3fef9aab3fb81ecee2f0ec903e0e154c4b08  p0b_reducer.py
32b409e0b84222886baabd1a7d56c71ca2939d2866ba9b91405b54318b0599e6  test_reducer.py
b118299381816806c3b96c21171c1501f24276e61a11fae313273e6554f8d852  manifest.sha256
```

`sha256sum -c manifest.sha256` → all four pinned files `OK`.

Report (this file):
`.memory/phase2-hicache-design/work/P0-B-REDUCER-FREEZE-20260911-R107.md`.

## what was frozen / built

- `ORACLE_NAMES` / `oracle_names()` expose **exactly 11** names in canonical
  order: `provenance`, `singular_identity`, `pid_profile_source_binding`,
  `positive_full_hit`, `host_alloc_park`, `generation_transition`,
  `fifo_predecessor`, `attempt_lineage`, `accepted_finalization`,
  `ready_after_finalize`, `negative_safety`.  `raw_provenance` is an input
  gate, not a predicate; `negative_safety` is predicate 11.
- Real event names/fields only, derived from the emission sites:
  `restore_host_alloc_wait` (`scheduler.py:3844`),
  `restore_host_alloc_wake_decision` grant/release/hold
  (`scheduler.py:3985/3661/4183`), `restore_host_alloc_retry_result`
  (`unified_radix_cache.py:5460/6576`), `restore_hybrid_finalize`
  (`unified_radix_cache.py:5683/5718`), `host_allocability_change`
  (`unified_radix_cache.py:3798`), the `[P3] evt=ready_host
  schema=rh_ready_host.v1` line (`scheduler.py:4409`), and
  `p0_durable` `durability_barrier` (`unified_radix_cache.py:7104`).
- Fail-closed: missing required field, contradictory identity/join, hash
  mismatch, or unrecognized lineage reason ⇒ `NOT_VERIFIED` with an explicit
  reason.  The three producer fail-closed reasons
  (`no_released_predecessor`, `predecessor_terminal_incomplete`,
  `predecessor_terminal_state_unrecognized`, plus `no_wait_cursor`) fail
  predicate 7; any unknown reason also fails closed.
- `generation_transition` joins strictly by cache instance + pool +
  generation + ordinal (never timestamps).  FIFO predecessor requires the
  terminal event to precede the grant.  Summary/verdict keys
  (`oracle`/`verdict`/`status`/`summary`/…) are rejected in the manifest and
  in records.  Every consumed record keeps its absolute `file:line` in
  `raw_references`.

## evidence (commands + raw output)

Environment for every command:
`source /mnt/data/neuron/envs/sglang-3090-opt/activate-sglang-3090.sh`.

1. Compile (from the R107 dir):

```
$ python -m py_compile p0b_reducer.py test_reducer.py
PY_COMPILE_OK
```

2. Required unit command (from the R107 dir):

```
$ python -m unittest test_reducer -v
test_absent_park_fails_closed ... ok
test_broken_attempt_lineage_fails_closed ... ok
test_fabricated_predecessor_fails_closed ... ok
test_incomplete_finalization_fails_closed ... ok
test_missing_pid_profile_binding_fails_closed ... ok
test_non_contiguous_generation_edge_fails_closed ... ok
test_pre_grant_predecessor_fails_closed ... ok
test_ready_before_finalize_fails_closed ... ok
test_wrong_lifecycle_fails_closed ... ok
test_crop_attempted_violation_fails_closed ... ok
test_discarded_hybrid_fails_closed ... ok
test_genuine_miss_violation_fails_closed ... ok
test_lower_checkpoint_violation_fails_closed ... ok
test_partial_sidecar_fails_closed ... ok
test_ready_before_finalization_fails_closed ... ok
test_recompute_fallback_fails_closed ... ok
test_repeated_retry_fails_closed ... ok
test_same_generation_self_wake_fails_closed ... ok
test_skipped_eligible_predecessor_fails_closed ... ok
test_canonical_stream_verifies_all_eleven ... ok
test_oracle_exposes_exactly_eleven_names ... ok
test_event_summary_verdict_field_rejected ... ok
test_manifest_verdict_field_rejected ... ok
test_tampered_raw_bundle_hash_fails_closed ... ok

----------------------------------------------------------------------
Ran 24 tests in 0.032s

OK
```

3. End-to-end CLI on a generated real-shaped bundle (`NOT` a runtime claim;
   synthetic-but-real-shaped input only):

```
$ python p0b_reducer.py --events .../server.log .../durable.jsonl \
      --manifest .../manifest.json; echo EXIT=$?
{
  "epoch": "2026-09-11",
  "oracle": ["provenance","singular_identity","pid_profile_source_binding",
             "positive_full_hit","host_alloc_park","generation_transition",
             "fifo_predecessor","attempt_lineage","accepted_finalization",
             "ready_after_finalize","negative_safety"],
  "predicates": [ {"name": "...", "passed": true, "reason": ""}, ... x11 ],
  "raw_event_count": 11,
  "raw_references": [".../server.log:1", ..., ".../durable.jsonl:1"],
  "reasons": [],
  "status": "VERIFIED",
  "target": {"lifecycle_key": "p0b-target:5", "rid": "p0b-target"},
  "task_id": "P0-B-REDUCER-FREEZE-20260911-R107"
}
EXIT=0
```

4. Scope check: `git status --porcelain` shows only `?? .memory/` (the whole
   `.memory` tree is untracked in this repo).  `python/sglang/srt/managers/
   scheduler.py` and `3090-dev/test_host_alloc_lineage.py` retain their
   pre-invocation mtimes (`2026-09-11 20:55:59` / `20:56:43`, from R106b); no
   product/test file was modified by this invocation.  The `__pycache__`
   produced by `py_compile` inside the R107 dir was removed before hashing.

## fail-closed coverage (adversarial, each independently FAILS closed)

The canonical real-shaped stream passes all 11.  Each mutation below yields
`NOT_VERIFIED` with the stated predicate failing (24 tests):

* missing PID/profile binding → `pid_profile_source_binding`
* wrong lifecycle → `singular_identity`
* absent park → `host_alloc_park`
* non-contiguous generation edge (5→7) → `generation_transition`
* fabricated/no predecessor → `fifo_predecessor`
* predecessor terminal after the grant → `fifo_predecessor`
* broken attempt lineage (`wake_event_id` not a real grant) → `attempt_lineage`
* incomplete sidecar finalization → `accepted_finalization`
* READY before finalize → `ready_after_finalize`
* negative safety, each independent: genuine_miss, crop_attempted,
  lower_checkpoint_queried, same-generation self-wake, repeated retry,
  skipped eligible predecessor, partial sidecar, discarded hybrid,
  recompute fallback, READY-before-finalization
* raw-provenance gate: event summary field, manifest verdict field, tampered
  raw-file hash

## followups

- Independent review of this package (adversarial) before any use.
- When a live raw bundle is captured, run this reducer and record
  `VERIFIED`/`NOT_VERIFIED`; a live `VERIFIED` is the only thing that can
  close P0-B.  No live evidence exists yet.

## open issues

- `positive_full_hit` binds the `durability_barrier` to the target through the
  session generation parsed from `target.lifecycle_key` plus the target park's
  positive token count.  The durability producer is a distinct event family
  (it carries the nested `producer` identity, not a HOST_ALLOC
  `lifecycle_key`); a future event with multiple same-session artifacts would
  need an explicit per-request join.  Documented in
  `FREEZE-11-PREDICATES.md` as a reviewed boundary, not weakened.
- `attempt_lineage` freezes `restore_host_alloc_retry_result` +
  `wake_event_id` propagation and rejects duplicate retries; it does not
  require the retry attempt id to equal the successful finalize attempt id
  (in the real producer those are different attempts joined by
  `wake_event_id`).  Recorded as a contract decision.
- No live raw bundle exists; public create reachability, HOST_ALLOC
  reachability, telemetry population, and the final READY remain unproven.
  P0-B stays `NOT_VERIFIED` as a goal-level claim.
- Independent review and live-chain validation are out of scope for this
  implementation invocation.
