# P0-B-LINEAGE-COMPLETE-20260911-R106b

- task_id: `P0-B-LINEAGE-COMPLETE-20260911-R106b` (continuation of R106)
- invocation: `ses-p0b-lineage-complete-r106b-20260911`
- role: coder
- epoch: 2026-09-11
- repo: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` (branch `3060-12g-qwen35-4b`, HEAD `4f41f5bab5`, intentionally dirty; no commit/push)

## status

**done**

The R106 lineage wiring is semantically correct on all five required gaps.  One
real defect was found and fixed in the wiring (stale `wait_id` on a re-park).
Focused stdlib `unittest` coverage was added and all targeted suites pass.

## artifacts

- Report (this file):
  `.memory/phase2-hicache-design/work/P0-B-LINEAGE-COMPLETE-20260911-R106b.md`
- New tests: `3090-dev/test_host_alloc_lineage.py` (417 lines)
- Fixed source: `python/sglang/srt/managers/scheduler.py` (the only source edit
  made by this invocation; line range 3786-3791, replacing the previous
  `if wait_id is None:` guard)

Pre-existing (present before this invocation, verified not blindly trusted):

- `python/sglang/srt/mem_cache/telemetry_context.py` (new, 237 lines):
  producer identity + `next_event_id`/`producer_context`/`lifecycle_key` +
  bounded lineage registry (`record_host_alloc_lineage`,
  `host_alloc_lineage`, `host_alloc_lineage_fields`,
  `clear_host_alloc_lineage`).
- `python/sglang/srt/managers/scheduler_components/hicache_restore.py`
  (+88 lines): `HostAllocWaiterTerminal`, arbiter `record_terminal(...)` and
  `predecessor_for(...)`.
- `python/sglang/srt/managers/scheduler.py` (+~567/-59 before this edit):
  wait/wake/terminal wiring, READY (`rh_ready_host.v1`) producer identity +
  lineage.
- `python/sglang/srt/mem_cache/unified_radix_cache.py` (+78): cache-side
  producer context + `_host_alloc_join_fields` lineage propagation.

## git diff --stat (working tree, HEAD 4f41f5bab5)

```
 3090-dev/test_drain_reentry.py                     |   3 +
 3090-dev/test_hicache_restore_scheduler_feed.py    |  10 +-
 3090-dev/test_prefetch_budget_split_unit.py        |  27 +-
 3090-dev/test_ready_horizon_unit.py                | 157 ++++-
 3090-dev/test_storage_regression.py                |   3 +
 python/sglang/srt/managers/cache_controller.py     |   4 +-
 python/sglang/srt/managers/scheduler.py            | 630 +++++++++++++++++++--
 .../scheduler_components/hicache_restore.py        |  88 +++
 .../managers/scheduler_components/ready_horizon.py |  17 +-
 .../hybrid_cache/hybrid_cache_controller.py        |  13 +
 python/sglang/srt/mem_cache/trace_context.py       |   6 +
 .../unified_cache/components/mamba_component.py    |   2 +
 python/sglang/srt/mem_cache/unified_radix_cache.py |  78 +++
 .../managers/test_hicache_host_allocability.py     |  42 +-
 14 files changed, 1001 insertions(+), 79 deletions(-)
```

`3090-dev/test_host_alloc_lineage.py` is untracked (not counted by
`git diff --stat`).

## per-gap verdict

### (a) `predecessor_for` consulted at the grant path; result + reason emitted — CLOSED

- `Scheduler._emit_host_alloc_wake_grant` (`scheduler.py:3956-4060`) always
  calls `_host_alloc_predecessor_lineage` (`scheduler.py:3601-3626`), which
  calls `HostAllocWakeArbiter.predecessor_for` (`hicache_restore.py:159-197`)
  with the current cursor's `fifo_sequence` and `blocked_domains`.
- The grant record emits `predecessor_wait_id`,
  `predecessor_terminal_event_id`, `predecessor_terminal_state`, and
  `predecessor_lineage_reason` (`scheduler.py:4020-4023`).
- Proven end-to-end by
  `test_grant_populates_predecessor_and_terminal_from_release`: after r1 is
  released (TIMEOUT) the r2 grant carries
  `predecessor_wait_id=r1:wait:0`,
  `predecessor_terminal_event_id=<r1 release event_id>`,
  `predecessor_terminal_state=TIMEOUT`, `predecessor_lineage_reason=None`.

### (b) `record_terminal` on every release/abandon/timeout path — CLOSED

- `_record_host_alloc_terminal` (`scheduler.py:3642-3714`) emits the
  `restore_host_alloc_wake_decision` record with `decision="release"` and then
  calls `HostAllocWakeArbiter.record_terminal` (`hicache_restore.py:135-157`).
- It is reached from `_remove_host_alloc_waiter` (`scheduler.py:3903-3910`),
  which is called on:
  - the restore-state transition out of `WAIT_CAPACITY[HOST_ALLOC]`
    (`_apply_restore_event`, `scheduler.py:4560-4578`) — timeout, release,
    miss/recompute, abort event;
  - stale-FIFO pruning (`_select_host_alloc_waiter`, `scheduler.py:3917-3925`)
    and empty waiting queue (`_reconcile_restore_states`,
    `scheduler.py:4069-4075`) → `ABANDONED`;
  - queue-full priority abort (`scheduler.py:6117`), waiting-timeout abort
    (`scheduler.py:6159`), and explicit abort-all (`scheduler.py:8116`) →
    `ABORTED`.
- State mapping is `_host_alloc_terminal_state_for` (`scheduler.py:3628-3640`):
  `TIMEOUT`/`ABORTED`/`RESTORED`/`MISS`/`RECOMPUTE`/`RELEASED`, all members of
  `_HOST_ALLOC_RELEASED_TERMINAL_STATES` (`scheduler.py:497-499`).
- Proven by `test_grant_populates_predecessor_and_terminal_from_release`
  (TIMEOUT: `terminal_event_id == event_id`, `terminal_state=TIMEOUT`) and
  `test_release_terminal_state_for_timeout_and_abandon` (abandon emits
  `terminal_state=ABANDONED` and removes the FIFO entry).

### (c) `lifecycle_key` consistent; scheduler authoritatively `rid:session_generation` — CLOSED

- Scheduler authority: `Scheduler._host_alloc_lifecycle_key`
  (`scheduler.py:3557-3566`) →
  `telemetry_context.lifecycle_key(rid, session_generation)` =
  `f"{rid}:{session_generation}"` (`telemetry_context.py:98-100`).
- The scheduler publishes that key into the process registry at park
  (`scheduler.py:3880-3901`) and at grant (`scheduler.py:4043-4059`).
- Cache producer: `_host_alloc_join_fields` (`unified_radix_cache.py:213-236`)
  reads the scheduler-owned record back via `host_alloc_lineage_fields` instead
  of deriving a divergent `req_id:run_id`; it returns `{}` when there is no
  producer record (fail-closed).
- READY producer: `scheduler.py:4387-4404` reads `host_alloc_lineage` and falls
  back to the scheduler key.
- Proven by `test_cache_producer_reuses_scheduler_lifecycle_key`: a real
  `restore_host_alloc_retry_result` emission through the cache
  `_log_host_alloc_telemetry` carries `lifecycle_key == f"{rid}:{gen}"` and the
  granted `wake_event_id`; an unknown rid joins to `{}`.

### (d) `wake_event_id` propagates into retry/finalize/READY — CLOSED

- Grant sets `req.hicache_host_alloc_wake_event_id = event_id`
  (`scheduler.py:4032`) and the registry `wake_event_id`
  (`scheduler.py:4043-4048`).
- Retry path re-publishes the request's lineage
  (`scheduler.py:4259-4263`).
- Cache `restore_host_alloc_retry_result` / `restore_hybrid_finalize` carry
  `_host_alloc_join_fields(req_id)` (`unified_radix_cache.py:5494, 5695, 5727,
  6594`), which includes `wake_event_id`.
- READY (`rh_ready_host.v1`) reads `host_alloc_lineage(req.rid)` and emits
  `wake_event_id` (`scheduler.py:4395-4397, 4413-4414, 4441`).
- Proven by `test_wake_event_id_reaches_ready_record`: after a real grant, a
  driven finalize → READY emits
  `wake_event_id=<grant event_id>` and
  `lifecycle_key=rid-ready:5` in the `rh_ready_host.v1` line.

### (e) Missing/contradictory predecessor → explicit nulls + reason, no fabricated join — CLOSED

- `predecessor_for` returns `(None, reason)` for
  `no_released_predecessor`, `predecessor_terminal_incomplete`, and
  `predecessor_terminal_state_unrecognized`
  (`hicache_restore.py:187-197`); `_host_alloc_predecessor_lineage` maps a
  missing cursor to `no_wait_cursor` and otherwise passes the reason through
  (`scheduler.py:3601-3626`).
- The grant record always emits the (possibly null) predecessor fields plus
  the reason; `_log_host_alloc_telemetry` explicitly writes `None` values
  (`scheduler.py:468-485`).
- The registry read-back refuses contradictory attempt identity
  (`telemetry_context.py:190-205`) and returns `{}` for an unknown rid.
- Proven by `test_contradictory_predecessor_fails_closed_incomplete`,
  `..._unrecognized`, `test_predecessor_from_other_blocked_domain_is_not_fabricated`,
  and the first-grant assertions in
  `test_grant_populates_predecessor_and_terminal_from_release`.

## defect found and fixed

**Stale `wait_id` on a re-park (lineage identity).**

- Before: `_capture_host_alloc_wait` only set
  `req.hicache_host_alloc_wait_id` when it was `None`:
  ```python
  if getattr(req, "hicache_host_alloc_wait_id", None) is None:
      req.hicache_host_alloc_wait_id = f"{req.rid}:wait:{sequence}"
  ```
  A request that is woken, fails its retry, and re-parks rotates to a new FIFO
  sequence (`record_attempt_result` → `rotate`), but kept the *previous*
  park's `wait_id`.  The probe showed the re-park `wait_id` (`r1:wait:0`)
  equal to its own `predecessor_wait_id`, so "the current wait" and "the
  predecessor wait" were indistinguishable — contradicting the
  "A (re-)park opens a fresh producer-owned wait" comment at
  `scheduler.py:3801`.
- After (this invocation, `scheduler.py:3786-3791`): the wait_id is keyed to
  the current FIFO sequence on every park.  Re-probe: re-park `wait_id`
  `r1:wait:1`, `predecessor_wait_id` `r1:wait:0` (distinct).  Regression
  covered by `test_repark_wait_identity_is_fresh_and_distinct`.
- Blast radius: telemetry identity only; no allocator / ready-horizon / FIFO
  policy change.  `query_storage_hit_length` untouched.  No commit/push.

## test commands + raw results

All commands executed after
`source /mnt/data/neuron/envs/sglang-3090-opt/activate-sglang-3090.sh`.

1. Compile (syntax/typecheck proxy; no mypy in env):

```
$ python -m py_compile python/sglang/srt/managers/scheduler.py \
    python/sglang/srt/mem_cache/unified_radix_cache.py \
    python/sglang/srt/managers/scheduler_components/hicache_restore.py \
    python/sglang/srt/mem_cache/telemetry_context.py \
    3090-dev/test_host_alloc_lineage.py
PY_COMPILE_OK
```

2. New focused suite (required command form):

```
$ python -m unittest 3090-dev.test_host_alloc_lineage -v
test_cache_producer_reuses_scheduler_lifecycle_key ... ok
test_contradictory_predecessor_fails_closed_incomplete ... ok
test_contradictory_predecessor_fails_closed_unrecognized ... ok
test_grant_populates_predecessor_and_terminal_from_release ... ok
test_predecessor_from_other_blocked_domain_is_not_fabricated ... ok
test_release_terminal_state_for_timeout_and_abandon ... ok
test_repark_wait_identity_is_fresh_and_distinct ... ok
test_wake_event_id_reaches_ready_record ... ok

----------------------------------------------------------------------
Ran 8 tests in 0.009s

OK
```

3. Adjacent regression suites:

```
$ python -m unittest 3090-dev.test_hicache_restore_scheduler_feed -v
...
Ran 46 tests in 0.011s
OK

$ python test/registered/unit/managers/test_hicache_host_allocability.py -v
...
Ran 11 tests in 0.059s
OK

$ python -m unittest 3090-dev.test_ready_horizon_unit -v
...
Ran 74 tests in 0.013s
OK
```

4. Pure state-machine suite (note: must run with cwd `3090-dev/`, because
   `test_hicache_restore.py` does `import test_drain_reentry`; running it from
   the repo root with `3090-dev.test_hicache_restore` produces 4 spurious
   `ModuleNotFoundError` errors unrelated to this task):

```
$ (cd 3090-dev && python -m unittest test_hicache_restore -v)
...
Ran 92 tests in 7.763s
OK
```

5. Additional adjacent suites:

```
$ (cd 3090-dev && python -m unittest test_drain_reentry test_prefetch_budget_split_unit -v)
...
Ran 55 tests in 0.718s
OK
```

Formatting: `black` / `ruff` are not installed in the local env
(`no black`, `no ruff`), so `.pre-commit-config.yaml` formatting could not be
run.  The edits are minimal and follow the surrounding style.  No `mypy` in
env; `py_compile` is the available typecheck proxy.

## hashes (sha256)

```
daf32da48b2d084976a19280b5b8eff2d232dfc1df2db9b2f4641a8f0ed9dd1d  python/sglang/srt/managers/scheduler.py
5d3db1528638dd1c593b9cd62fc1b380d278cac4cc1b4e1319e6bf89c0ac375b  python/sglang/srt/mem_cache/unified_radix_cache.py
1cc9d2b8277039e271ce65a1e4aa7b128781b378367346edd438daee42bb3604  python/sglang/srt/managers/scheduler_components/hicache_restore.py
d55b057c98a4941c307bb138002340c3e8a5a5361f58417f84a3ea176658f948  python/sglang/srt/mem_cache/telemetry_context.py
ca3176ab5b5c382712b5d9e41b15c5002bd6301a00dd32425671b30518ce0b4d  3090-dev/test_host_alloc_lineage.py
```

`SOURCE_HEAD` in `telemetry_context.py` is `4f41f5bab562b99562f30c67540eb05344d13637`
(HEAD), matching `git log`.  `_SOURCE_BUILD` additionally digests the six
producer files at import time.

## evidence (observed, not assumed)

- Scheduler grant/release/READY records and the pure arbiter were exercised by
  throwaway probes (`/tmp/r106b/probe*.py`, outside the repo) before the final
  tests; raw grant/release/READY JSON is reproduced in the per-gap sections.
- The final `test_host_alloc_lineage.py` imports the real
  `sglang.srt.managers.scheduler`, `...hicache_restore`, and
  `sglang.srt.mem_cache.unified_radix_cache` modules and drives the real
  emission helpers; it is not a re-implementation.

## followups

- Freeze the 11-predicate reducer against the real emitted event names
  (`restore_host_alloc_wait`, `restore_host_alloc_wake_decision`,
  `host_allocability_change`, `restore_host_alloc_retry_result`,
  `restore_hybrid_finalize`, `rh_ready_host.v1`) once the live chain is up.
- Re-run these tests on the frozen 3090 runtime once it is restarted
  (`LOCAL-3090-SERVER-20260911-R105b`).

## open_issues

- `wait_event_id` is declared in `HOST_ALLOC_LINEAGE_FIELDS`
  (`telemetry_context.py:37`) but never populated by the scheduler or read by
  the cache join helper; it remains dead.  Not required by this dispatch; left
  unchanged to avoid scope creep.
- `_capture_host_alloc_wait` hard-codes `attempt_number=0` for the registry and
  the `restore_host_alloc_wait` event (`scheduler.py:3864, 3882`) even on a
  re-park where prior attempts exist.  The grant/retry path uses the live
  `hicache_host_alloc_attempt_number`.  Potential lineage inconsistency,
  outside the five required gaps; not changed.
- `host_allocability_change` (`unified_radix_cache.py:3798-3821`) deliberately
  emits `lifecycle_key=None` / `wait_id=None` even with a `causal_rid`; this is
  fail-closed (never a divergent key) but does not join the causal request's
  lifecycle.  Changing it would be an event-semantics decision, not a wiring
  fix.
- The durability producer (`hybrid_cache_controller._t38c_durable_log`,
  `hybrid_cache_controller.py:99`) defaults `lifecycle_key` to `operation_id`,
  a distinct event family keyed on a durable operation, not on
  `rid:session_generation`.  Reported as a boundary; not unified here.
- Independent review and live-chain validation are out of scope for this
  implementation invocation.
