# P2-A live-collection contract (FROZEN) — Q1/Q2/Q3 on the R128 probe build

- task_id: `P2A-COLLECTION-20260912`
- epoch: 2026-09-12
- authority: user-approved `Option 1 + A=3090/prefetch-side + B=defer #3`.
- build under test: **R128 freeze**
  (`work/R128-profile/P0-C-3090-PROFILE-REFREEZE-20260912.md`), server PID
  `616394`/scheduler `617035`, log
  `/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-p2a.log`,
  `SGLANG_P2A_TIMING_PROBE=1`.
- binds the measurement definitions in
  `work/P2A-MEASUREMENT-CONTRACT-20260912.md` (sha `c0551708…1096a`).

## Workload (real multi-turn session workload; not synthetic sleep)

Drive a genuine session workload against the live server over public HTTP
(`/v1/completions`); the driver must NOT import product modules or touch the
server process.

- `N` sessions (agents), each with a distinct long history (unique per-session
  marker so radix branches are distinct), history length well above
  `prefetch_threshold=256` (target 6k-12k tokens per session).
- Per session: turn 1 = COLD prime (full history); turns 2..`TURNS` = warm turns
  re-sending full history + a novel delta, so later turns restore from L2/L3.
- `TURNS >= 5`, `N >= 4`, total requests `>= 40` to give usable distributions.
- Between/among turns, include enough distinct-session pressure that the working
  set is evicted from device (so warm turns exercise the storage query and the
  L3->L2 stage); do NOT use `/flush_cache` or `/close_session`.
- The same server/profile/recipe throughout; no restart during collection.

## Extraction (server-side, from the R128 log window)

Use only monotonic marks on the same clock (`time.monotonic_ns`).

- **Q1 (queue lead time):** for each rid, `admission_monotonic_ns` (from
  `evt=admission.v2`) minus `enqueue_mono_ns` (M1 `evt=enqueue_mono_ns`). Join by
  rid; require exactly one M1 per rid and a later admission.v2.
- **Q2 (L3->L2 stage):** for each attempt, `ready_host` `ready_monotonic_ns`
  minus M2 `prefetch_issue_mono_ns`, joined by `attempt_id`
  (`ready_host.attempt_id` must equal `prefetch_issued.attempt_id`). Report only
  same-attempt pairs; if an attempt has an issue but no ready_host, it is a
  non-completed attempt (report count, do not fabricate an end).
- **Q3 (storage metadata query cost):** from M3 `evt=storage_hit_query`:
  `exit_mono_ns - enter_mono_ns`, `backend_lookup_ns`, `caller`
  (`async_prefetch` vs `sync_decode`), `query_len`, `kv_hit_pages`,
  `lock_wait_ns`/`syscall_wait_ns`/`all_reduce_ns` (expected N/A).

Report for each quantity: sample count, p50/p95/p99/max (ns, and human units).
Separate Q3 by `caller` and by `query_len` bucket (e.g. <1k, 1k-5k, 5k-20k pages).

## Acceptance bands (Q3, from the authoritative contract)

`p99 < 100 µs` = negligible (ignore); `100 µs–1 ms` = observe only; `>= 1 ms` =
optimization candidate; a clear disk-syscall / synchronous-blocking wait =
architectural problem.

For Q1/Q2 the deliverable is the measured distribution plus the direct comparison
question: **is Q1 (queue lead) sufficient to cover Q2 (L3->L2 stage)?** i.e. for
each completed attempt, does `ready_host` occur before the request's
`admission`/switch, and by how much (positive = covered, negative = exposed).

## Overhead / probe hygiene

- Record the probe's own `probe_ns` distribution for M1/M2/M3 and confirm
  per-mark cost stays `<< 1 ms` (already ~6-13 µs off-line; confirm live).
- If any M3 `probe_ns > 1 ms`, report it as a measurement defect.

## Deliverable

`work/R129-bundle/` (driver, raw window logs, extracted tables, sha256sums) and
report `work/P2A-LIVE-COLLECTION-20260912-R129.md` with:
Q1/Q2/Q3 distributions + sample counts, the Q1-vs-Q2 coverage analysis, the Q3
acceptance-band verdict, probe overhead, provenance (R128 freeze + server PIDs +
log hash), and any missing mark / join failure (fail closed, do not impute).

## Constraints

- Read-only w.r.t. product code; no new instrumentation beyond the frozen probe;
  no server restart; no `/flush_cache`, no `/close_session`; no profile change.
- <= 200 HTTP, <= 45 min. Do not modify R121-R128 artifacts.
