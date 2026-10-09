STATUS: done

# COD-20260908-P0-RESIDENCY-BARRIER-DIAGNOSTIC-FIX6

## Invocation

- Task ID: `COD-20260908-P0-RESIDENCY-BARRIER-DIAGNOSTIC-FIX6`
- Epoch: `phase2-hicache-design / 2026-09-08`
- Role: `coder`
- Scope: marker-gated strict residency-fold diagnostics and the authorized
  focused scheduler-checkpoint reproducer only.
- No remote/live run was performed.

## Changed files

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - Added marker-gated `residency_barrier_outcome` telemetry in the strict
    `_t38c_residency_barrier` path.
  - The deduplication key is the exact six-field residency identity plus
    `retry_epoch` and `poll_attempt`; the first returning predicate wins for
    that attempt.
  - Queue fields are sampled only under the controller's
    `_t38c_release_handoff_lock`: `primary_queue_empty`,
    `extra_queue_empty`, and per-extra-queue emptiness.
  - Broad exception handling remains fail-closed and reports only
    `reason=exception` plus `exception_type`.
  - No queue operation, collective, barrier synthesis, predicate relaxation,
    or admission/return behavior was changed. Existing cache-owned `RLock`,
    strict six-field checks, F-1/F-2/F-3/F-4, and at-most-once publication are
    retained.
- `3090-dev/test_p0_residency_barrier_emitter.py`
  - Kept the existing dependency-free focused checks.
  - Added a real-surface TP=1 scheduler probe that binds the production
    controller handoff methods, `_drain_storage_control_queues_impl`, and
    `check_hicache_events` to a minimal harness.
  - Exercises primary KV and extra Mamba release queues through
    `append_host_mem_release`, verifies non-empty suppression, ordinary
    scheduler checkpoint drain/free, exact completion idempotence, and one
    barrier on repeat checkpoint.

## Local verification evidence

All commands ran locally in `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

```text
PYTHONPYCACHEPREFIX=/tmp/codex-p0-residency-fix6-pycache \
  python3 -m py_compile \
  python/sglang/srt/mem_cache/unified_radix_cache.py \
  3090-dev/test_p0_residency_barrier_emitter.py
PASS

python3 3090-dev/test_p0_residency_barrier_emitter.py
PASS: existing emitter, F-1/F-2/F-3/F-4, marker-off, and
      Real TP=1 scheduler checkpoint primary/extra probe

python3 3090-dev/test_p0_trace_context_v4.py
P0 trace-context V4.3 focused checks: PASS

AST parse of both authorized Python files
PASS

git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py
PASS

git diff --no-index --check /dev/null 3090-dev/test_p0_residency_barrier_emitter.py
PASS: expected status 1 for the untracked authorized fixture, with no
      whitespace diagnostics
```

The aggregate worktree was already dirty in unrelated files; no unrelated
file was modified by this task.

## Telemetry examples

The local real-surface probe produced these representative outcome records.
Each record carries the exact identity fields in the real logger envelope;
the abbreviated examples below retain the predicate and queue evidence.

```json
{
  "evt": "residency_barrier_outcome",
  "session_id": "scheduler-primary",
  "reason": "token_incomplete",
  "retry_epoch": 0,
  "poll_attempt": 0,
  "queue_snapshot_locked": true,
  "primary_queue_empty": true,
  "extra_queue_empty": true,
  "result": false
}
```

After exact completion but before the scheduler drains the primary queue:

```json
{
  "evt": "residency_barrier_outcome",
  "session_id": "scheduler-primary",
  "reason": "queue_nonempty",
  "retry_epoch": 1,
  "poll_attempt": 1,
  "queue_snapshot_locked": true,
  "primary_queue_empty": false,
  "extra_queue_empty": true,
  "result": false
}
```

After the ordinary TP=1 `check_hicache_events()` checkpoint drains the
primary queue:

```json
{
  "evt": "residency_barrier_outcome",
  "session_id": "scheduler-primary",
  "reason": "published",
  "retry_epoch": 2,
  "poll_attempt": 1,
  "queue_snapshot_locked": true,
  "primary_queue_empty": true,
  "extra_queue_empty": true,
  "result": true
}
```

The extra-Mamba case produced the corresponding `queue_nonempty` record with
`primary_queue_empty=true`, `extra_queue_empty=false`, and then one
`published` outcome after the same scheduler checkpoint. A second checkpoint
did not produce a second residency barrier.

## Remaining functional diagnosis

FIX6 does not claim that the r14 live root cause is fixed. The r14 report
proved queued host releases drained but had no strict predicate outcome. This
change supplies that missing evidence. A fresh live run must enable the
marker before requests, preserve the existing frozen workload/vehicle, and
collect `residency_barrier_outcome` for every exact identity. The first
predicate for each retry epoch should be classified as follows:

- `queue_nonempty`: retain the accepted queue/handoff contract and investigate
  the scheduler checkpoint or a transient queue owner.
- `token_incomplete`, `live_component_value`, `build_not_ready`, or
  `durability_not_ready`: route a fresh functional diagnosis to the owning
  specialist; FIX6 made no lifecycle change.
- `node_lookup`, `root_or_forced_miss`, `invalid_identity`, or `exception`:
  preserve fail-closed admission and investigate node/context lifecycle with
  the captured identity and exception type only.
- `published`: the strict fold succeeded; continue only with the existing
  live ordering, warm, restore, and vehicle acceptance gates.

No live/remote result is inferred from this local probe. The next live
condition is a fresh S=25 RH-off run with the marker active before request
execution and the outcome records retained alongside the existing durable
trace.

## Status packet

- Status: `done`
- Artifacts: the two authorized source/test files and this report.
- Evidence: focused emitter PASS, real TP=1 scheduler primary/extra probe
  PASS, V4.3 PASS, py_compile PASS, AST PASS, and whitespace checks PASS.
- Summary: strict-fold first-predicate telemetry and a real scheduler-
  checkpoint reproducer were added without changing barrier admission or
  queue behavior.
- Followups: independent reviewer/tester gate and a fresh live run owned by
  their named tasks; use first-failure records before selecting any
  functional fix.
- Open issues: r14's production first failing predicate remains unknown until
  a fresh marked live run; no remote/live evidence is claimed here.
