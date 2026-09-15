# P2-A measurement contract (FROZEN) — 3090 no-disaggregation prefetch path

- task_id: `P2A-MEASUREMENT-20260912`
- epoch: 2026-09-12
- authority: **user ruling** (Option 1 + A=3090/prefetch-side + B=defer #3 to
  P2-B0, approved 2026-09-12). P1 is CLOSED/VERIFIED; this is a separate,
  explicitly authorized stage.
- repo: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
  (branch `3060-12g-qwen35-4b`, HEAD `4f41f5bab5`, intentionally dirty)
- supersedes: the 3060/PD-disaggregation framing of
  `P2P3Q-READINESS-20260911-R65.md` for P2-A. The authoritative gate text
  (`sglang-3090-24g-hicache/.memory/phase2-hicache-design/plan.md:63-91`) is
  otherwise unchanged.

## Scope decisions (binding)

1. **Environment = the current frozen 3090 no-disaggregation profile**
   (`disaggregation_mode: 'null'`). PD-disaggregation is NOT enabled: it would
   change the data path, scheduling, and deployment topology and contaminate the
   P2-A causal attribution.
2. **Observation-only instrumentation is authorized**: timestamps and counters
   only. It MUST NOT change scheduling, cache, admission, prefetch, or storage
   behavior. No new instrumentation beyond the marks below.
3. **`cache-induced idle` (#3) is OUT OF SCOPE** here; deferred to P2-B0 (which
   owns the scorecard and is the right home for a GPU-timeline sampler).

## Target quantities (P2-A, reframed for the live path)

- **Q1 — queue lead time:** `admission_mono_ns - enqueue_mono_ns` per rid.
- **Q2 — L3->L2 stage duration:** `ready_host_mono_ns - prefetch_issue_mono_ns`
  per attempt.
- **Q3 — storage metadata query cost:** enter/exit + component attribution for
  the prefetch-side storage-hit query actually taken on this profile.

P2-A2's question is rewritten to: **on the current 3090 no-disaggregation
prefetch path, does the storage-hit metadata query sit on the task-switch /
prefetch critical path?** The PD-disaggregation decode-side
`__storage_hit_query__` path is NOT exercised here (0 occurrences in the live
probe log); it is out of scope unless the environment changes.

## Exact instrumentation marks (frozen anchors)

All subtractable timestamps MUST use `time.monotonic_ns()` (the same clock
already used by `admission.v2 admission_monotonic_ns`
`scheduler.py:6820-6836`, `ready_stage ts_ns` `scheduler.py:5365`, and
`ready_host ready_monotonic_ns` `scheduler.py:4437-4485`). Wall-clock
(`time.time()*1000`) must never be subtracted from a monotonic mark.

### M1 — `enqueue_mono_ns` (Q1 start)
- Anchor: `scheduler.py` `_add_request_to_queue` NULL branch, at
  `self.waiting_queue.append(req)` (currently `scheduler.py:6072`).
- Emit exactly once per rid: set `req.hicache_enqueue_mono_ns = time.monotonic_ns()`
  only if it is unset. MUST NOT be overwritten on re-entry (retraction/re-queue).
- Emit a log line carrying `rid`, `enqueue_mono_ns`, and the identity fields
  (`node_id`/`build_id`/`session_generation` if available on the req).

### M2 — `prefetch_issue_mono_ns` (Q2 start)
- Anchor: `unified_radix_cache.py` `[P2A] evt=prefetch_issued` emitter
  (currently `unified_radix_cache.py:5543`), which already has
  `operation.prefetch_attempt_id` set (`:5541`).
- Add `prefetch_issue_mono_ns=%d` (`time.monotonic_ns()`) plus `attempt_id`,
  and the identity fields `node_id` / `build_id` / `session_generation`.
- Q2 is joined per `attempt_id` against the `ready_host` line, which already
  carries `ready_monotonic_ns` and `attempt_id` on the same clock. Because the
  RH-issued `prefetch:1` and the restoring `prefetch:2` are different attempts,
  the join key is the attempt that actually completes; report the leg(s)
  observed and never subtract across differing attempt ids.

### M3 — storage-hit query probe (Q3)
- Anchor: `HybridCacheController._storage_hit_query`
  (`hybrid_cache/hybrid_cache_controller.py`, currently `:864-932`). This is the
  implementation the live async prefetch thread uses
  (`cache_controller.py:1318` `prefetch_thread_func` ->
  `self._storage_hit_query(operation)`), and also the sync call used by
  `query_storage_hit_length` (`unified_radix_cache.py:5230-5270`).
- Emit one record per call with:
  - `enter_mono_ns`, `exit_mono_ns` (`time.monotonic_ns()`),
  - `backend_lookup_ns`: time around the `storage_backend.batch_exists` /
    `batch_exists_v2` calls,
  - `lock_wait_ns`: `N/A` — this method takes no explicit lock (record 0/N/A,
    do not invent a lock),
  - `syscall_wait_ns`: measured only if a syscall is actually wrapped; the file
    backend's disk I/O is inside `backend_lookup_ns`, so if it cannot be isolated
    record `N/A` and state so,
  - `all_reduce_ns`: the all-reduce is OUTSIDE this method (async:
    `cache_controller.py:1331-1336`; sync: `unified_radix_cache.py:5268-5270`).
    Wrap it at those sites when the probe is on; record `N/A` if the collective
    is a no-op (tp=1). The probe MUST NOT itself call any collective.
  - `caller`: `async_prefetch` (rid != `__storage_hit_query__`) vs
    `sync_decode` (rid == `__storage_hit_query__`),
  - `rid`, `attempt_id`, `query_len`, `kv_hit_pages`.
- `probe_ns`: each mark must also emit the duration of its own probe block
  (the extra work it added), so overhead is directly observable.

### Probe gating and no-op baseline (user hard constraint)
- The probe is gated by env `SGLANG_P2A_TIMING_PROBE` (**default OFF** = current
  behavior unchanged). When OFF, the added code must be inert (no timestamp read,
  no log, no field write on the hot path).
- No-op baseline: a stdlib microbenchmark must measure the per-call overhead of
  the probe helper (timestamp read + f-string formatting + emit). Acceptance:
  per-call overhead `<< 1 ms` (target `< 50 µs`); if any probe block's
  `probe_ns` ever exceeds 1 ms, that is reported as a measurement defect.
- Live A/B (optional): one short baseline run with the flag OFF vs the main run
  with it ON, on the same recipe.

## Acceptance bands (from the authoritative contract)

For Q3: `p99 < 100 µs` = negligible (ignore); `100 µs–1 ms` = observe only;
`>= 1 ms` = optimization candidate; a clear disk-syscall / synchronous-blocking
wait = architectural problem. Report p50/p95/p99/max and the sample count.

## Execution order (user-approved)

`probe patch` -> focused unit/regression -> rebuild -> restart -> **re-freeze
P0-C** -> P2-A live collection.

P0-B/P1 are NOT re-run unless the instrumentation diff unexpectedly touches the
corresponding semantic path. The diff MUST be behaviorally inert (timestamps,
counter fields, log emission only).

## P2-A final questions (the only ones to answer)

1. Is queue lead time sufficient to cover the L3->L2 stage?
2. How long does the L3->L2 stage actually take?
3. Is the storage metadata/query itself worth optimizing?

## Non-goals / explicit non-claims

- No PD-disaggregation, no async redesign, no scheduler/policy change.
- No `cache-induced idle` (deferred to P2-B0).
- No product behavior change; the probe is off by default.
- No mutation of R121-R127 artifacts.

## Deliverable

An observation-only probe patch + stdlib unit test + no-op baseline, and a P2-A
live-collection report with Q1/Q2/Q3 distributions, per-request traces,
source/profile hashes, and the acceptance-band verdicts.
